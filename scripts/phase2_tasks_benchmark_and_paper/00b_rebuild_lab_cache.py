"""Stage P2.1 prerequisite -- re-extract the lab cache with the columns A3 needs.

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/00b_rebuild_lab_cache.py

Why this exists (spec §12.8.7, progress-doc §4 decision 13 / trap 7b).
``data/raw/ehr_cache/labevents.parquet`` (158,374,764 rows) kept only
``labevent_id, subject_id, hadm_id, itemid, charttime, valuenum, valueuom``. The
§4.A.3.3 label rule branches on ``ref_range_lower``, ``ref_range_upper`` and
``flag``, none of which survived. Without them A3 collapses to
``missing`` vs ``not_missing``.

What it does. Streams ``data/raw/mimic-iv-hosp-3.1/hosp/labevents.csv.gz``
(2.6 GB gz, 16 columns) in chunks, keeps only the 18 itemids locked in
``config/lab_itemid_map_LOCKED.yaml``, and writes
``data/raw/ehr_cache/labevents_key_labs.parquet`` with the nine columns A3
needs. Roughly 21 M rows survive the filter.

**The original parquet is not touched.** It is a Phase 1 provenance artifact and
this script only adds a sibling next to it -- extending an EHR cache, re-running
no Phase 1 stage (§2).

Resume. Each chunk group becomes a part parquet under
``data/processed/_p2_parts/lab_cache/``; the state file records how many source
chunks have been consumed. A killed run restarts by re-reading (but not
re-writing) the chunks it already finished.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402

STAGE = "P2.1"
SCRIPT = "00b_rebuild_lab_cache"

SOURCE_CSV = bc.DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "labevents.csv.gz"
OUT_PATH = bc.EHR_CACHE / "labevents_key_labs.parquet"
PART_NAME = "lab_cache"

# The nine columns the §4.A.3.3 rule and its provenance need. `value` is kept
# because a few assays report a non-numeric result ("NEG", "<0.01") whose
# valuenum is null -- that is the `missing` class, and the raw string is the
# evidence for it.
USE_COLS = [
    "labevent_id", "subject_id", "hadm_id", "itemid", "charttime",
    "value", "valuenum", "valueuom", "ref_range_lower", "ref_range_upper", "flag",
]
CHUNK_ROWS = 4_000_000

SCHEMA = pa.schema([
    ("labevent_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("hadm_id", pa.float64()),          # nullable in the source; float keeps NA
    ("itemid", pa.int32()),
    ("charttime", pa.timestamp("ns")),
    ("value", pa.string()),
    ("valuenum", pa.float64()),
    ("valueuom", pa.string()),
    ("ref_range_lower", pa.float64()),
    ("ref_range_upper", pa.float64()),
    ("flag", pa.string()),
])


def locked_itemids() -> tuple[list[int], dict[int, str]]:
    cfg = yaml.safe_load((bc.CONFIG_DIR / "lab_itemid_map_LOCKED.yaml").read_text(encoding="utf-8"))
    ids: list[int] = []
    lab_of: dict[int, str] = {}
    for lab, block in cfg["labs"].items():
        for itemid in block["itemids"]:
            ids.append(int(itemid))
            lab_of[int(itemid)] = lab
    if len(ids) != len(set(ids)):
        raise RuntimeError("an itemid is claimed by two labs in lab_itemid_map_LOCKED.yaml")
    return sorted(ids), lab_of


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    bc.add_std_args(parser)
    args = parser.parse_args()
    bc.set_dev(args.dev)

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT)
    if state.done and not args.force:
        log.info("already complete (%s rows) -- pass --force to rebuild", state.data.get("n_rows"))
        return 0
    if args.force:
        for part in bc.part_dir(PART_NAME).glob("part_*.parquet"):
            part.unlink()
        state.reset()

    bc.preflight([SOURCE_CSV, bc.CONFIG_DIR / "lab_itemid_map_LOCKED.yaml"], need_free_gb=5.0)
    itemids, lab_of = locked_itemids()
    log.info("locked itemids: %d -> %s", len(itemids), itemids)

    chunks_done = int(state.data.get("chunks_done", 0))
    if chunks_done:
        # ponytail: resume re-parses the consumed prefix rather than seeking.
        # gzip has no index and `value`/`comments` are quoted CSV fields that may
        # contain commas, so a byte- or line-offset skip is not safe. Re-parsing
        # ~15 min of prefix beats a subtly wrong resume; if this ever matters,
        # split the source once into itemid-partitioned shards instead.
        log.info("resuming: skipping %d already-consumed source chunks", chunks_done)

    keep = set(itemids)
    started = time.time()
    rows_in = int(state.data.get("rows_in", 0))
    rows_out = int(state.data.get("rows_out", 0))
    if not chunks_done:
        rows_in = rows_out = 0

    reader = pd.read_csv(
        SOURCE_CSV,
        usecols=USE_COLS,
        chunksize=CHUNK_ROWS,
        compression="gzip",
        low_memory=False,
        dtype={"value": "string", "valueuom": "string", "flag": "string"},
    )
    buffer: list[pd.DataFrame] = []
    buffered = 0
    index = -1
    for index, chunk in enumerate(reader):
        if index < chunks_done:
            continue
        rows_in += len(chunk)
        hit = chunk[chunk["itemid"].isin(keep)].copy()
        if len(hit):
            hit["charttime"] = pd.to_datetime(hit["charttime"], errors="coerce")
            hit["itemid"] = hit["itemid"].astype("int32")
            buffer.append(hit[USE_COLS])
            buffered += len(hit)
            rows_out += len(hit)
        if buffered >= 4_000_000:
            path = bc.write_part(PART_NAME, pd.concat(buffer, ignore_index=True), SCHEMA)
            log.info("wrote %s rows=%d", path.name, buffered)
            buffer, buffered = [], 0
        state.update(chunks_done=index + 1, rows_in=rows_in, rows_out=rows_out)
        rate = rows_in / max(1e-6, time.time() - started)
        log.info("chunk %d: rows_in=%d rows_out=%d (%.0f k rows/s)",
                 index, rows_in, rows_out, rate / 1000)

    if buffer:
        path = bc.write_part(PART_NAME, pd.concat(buffer, ignore_index=True), SCHEMA)
        log.info("wrote %s rows=%d", path.name, buffered)

    n = bc.publish_parts(
        PART_NAME, OUT_PATH, SCHEMA, sort_by="subject_id",
        metadata={"source": str(SOURCE_CSV.name), "n_itemids": str(len(itemids)),
                  "spec": "PHASE2_SOURCE_OF_TRUTH.md §12.8.7"},
    )
    log.info("published %s rows=%d (source rows read=%d)", OUT_PATH, n, rows_in)

    # Validation: the recovered columns must actually be populated, per lab.
    got = pd.read_parquet(OUT_PATH, columns=["itemid", "valuenum", "ref_range_lower",
                                             "ref_range_upper", "flag"])
    got["lab"] = got["itemid"].map(lab_of)
    summary = got.groupby("lab").agg(
        n=("itemid", "size"),
        valuenum_pct=("valuenum", lambda s: round(100 * s.notna().mean(), 2)),
        ref_lower_pct=("ref_range_lower", lambda s: round(100 * s.notna().mean(), 2)),
        ref_upper_pct=("ref_range_upper", lambda s: round(100 * s.notna().mean(), 2)),
        flag_pct=("flag", lambda s: round(100 * s.notna().mean(), 2)),
    )
    log.info("per-lab coverage:\n%s", summary.to_string())
    if summary["ref_lower_pct"].max() == 0:
        raise RuntimeError("ref_range_lower is empty for every lab -- the extract is wrong")

    state.finish(
        n_rows=n, rows_read=rows_in, out_path=str(OUT_PATH),
        per_lab=summary.reset_index().to_dict("records"),
        elapsed_seconds=round(time.time() - started, 1),
    )
    log.info("DONE in %.1f min", (time.time() - started) / 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
