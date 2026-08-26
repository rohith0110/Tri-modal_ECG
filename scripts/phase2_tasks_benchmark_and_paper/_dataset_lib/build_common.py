"""Shared plumbing for the Stage P2.1 / P2.2 task builders.

Every builder in ``scripts/phase2_tasks_benchmark_and_paper/`` imports from here
so the thirteen scripts share one cohort join, one resume convention, one
logging transport and one output writer.

What this module guarantees (spec §4.C, §8.5, §8.6, progress-doc traps 4/5/8):

* **The split is never re-derived.** :func:`load_clean_cohort` joins
  ``splits_subject_level.parquet`` on ``subject_id`` and asserts the result
  agrees with the split column already carried by the Phase 1 index.
* **Machine measurements are masked.** :func:`machine_measurements` applies the
  ``29999`` sentinel rule and the locked plausible ranges; the useless
  ``*_missing`` flag columns are never read.
* **Long runs resume.** :class:`StageState` plus :func:`run_chunked` checkpoint
  to part parquets after every chunk, so a power cut costs at most one chunk.
* **Modalities resolve through** :mod:`_dataset_lib.modality` only.

Run any builder with ``./ecg_env/Scripts/python.exe``. Never the system Python.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# --- repo layout -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
DATA_RAW = PROJECT_ROOT / "data" / "raw"
EHR_CACHE = DATA_RAW / "ehr_cache"
CONFIG_DIR = PROJECT_ROOT / "config"
TASKS_DIR = DATA_PROCESSED / "tasks"
STAGE_REPORTS = PROJECT_ROOT / "outputs" / "stage_reports"
PARTS_ROOT = DATA_PROCESSED / "_p2_parts"
DEV_SAMPLE = DATA_PROCESSED / "dev_sample" / "dev_sample_studies.parquet"

# --- resource policy (Phase 1 §6.1) ------------------------------------------
MAX_WORKERS = max(1, math.floor((os.cpu_count() or 1) * 0.75))
CHUNK_STUDIES = 20_000          # part-parquet granularity for the heavy passes
BATCH_SIZE = 32                 # ProcessPoolExecutor chunksize (Phase 1 §6.1)

MISSING_SENTINEL = 29999        # trap 8 / spec §12.8.2
SPLITS = ("train", "val", "test")

# --- dev-mode output isolation ------------------------------------------------
# A --dev smoke test must never write where the full-scale run writes. Without
# this, a two-minute sanity check silently replaces a task's real parquets with
# 5,000 dev-sample rows, and nothing downstream can tell. set_dev(True)
# redirects every task output under data/processed/tasks/_dev/.
_DEV_MODE = False


def set_dev(dev: bool) -> None:
    """Route task outputs to the dev tree. Call once, right after arg parsing."""
    global _DEV_MODE
    _DEV_MODE = bool(dev)


def tasks_root() -> Path:
    return TASKS_DIR / "_dev" if _DEV_MODE else TASKS_DIR


def task_dir(task_key: str) -> Path:
    path = tasks_root() / task_key
    path.mkdir(parents=True, exist_ok=True)
    return path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_replace(tmp: Path, final: Path, attempts: int = 12) -> None:
    """``os.replace`` with a retry ladder.

    On Windows a just-written file is routinely held for a few hundred
    milliseconds by the AV scanner or the search indexer, and ``os.replace``
    then fails with ``PermissionError: [WinError 5]``. Losing a nine-hour run's
    final state write to that is not acceptable, so retry before giving up.
    """
    delay = 0.1
    for attempt in range(attempts):
        try:
            os.replace(tmp, final)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 5.0)


# -----------------------------------------------------------------------------
# logging -- Transport A, per-PID worker files (Phase 1 §8.3)
# -----------------------------------------------------------------------------
_LOG_FMT = "%(asctime)s %(levelname)-7s pid=%(process)-6d %(name)s | %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(script_name: str, *, stage: str) -> logging.Logger:
    """Main-process logger writing to console *and* ``stage_<stage>_<script>.log``."""
    STAGE_REPORTS.mkdir(parents=True, exist_ok=True)
    log_path = STAGE_REPORTS / f"stage_{stage}_{script_name}.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    fmt = logging.Formatter(_LOG_FMT, _LOG_DATEFMT)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    log = logging.getLogger("main")
    log.info("log file: %s", log_path)
    return log


def worker_log_init(script_name: str, stage: str) -> None:
    """Pool initializer: redirect this worker's fd 1/2 into its own PID log.

    Workers never write to the parent's stdout/stderr (Phase 1 §8.2) -- that is
    what garbles a tqdm bar.
    """
    run_dir = STAGE_REPORTS / f"stage_{stage}_run" / script_name
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"worker_{os.getpid()}.log"
    handle = open(path, "a", buffering=1, encoding="utf-8")
    os.dup2(handle.fileno(), 1)
    os.dup2(handle.fileno(), 2)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for existing in list(root.handlers):
        root.removeHandler(existing)
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(_LOG_FMT, _LOG_DATEFMT))
    root.addHandler(file_handler)


# -----------------------------------------------------------------------------
# resume state
# -----------------------------------------------------------------------------
class StageState:
    """Small JSON state file, written atomically after every checkpoint.

    Mirrors the Phase 1 convention (``outputs/stage_reports/stage_<n>_state.json``)
    with one file per script, because Stage P2.1 has seven scripts where Phase 1
    stages had one. ``state["done"]`` is the idempotency flag: a completed script
    re-run is a no-op unless ``--force`` is passed.
    """

    def __init__(self, stage: str, script_name: str) -> None:
        STAGE_REPORTS.mkdir(parents=True, exist_ok=True)
        self.path = STAGE_REPORTS / f"stage_{stage}_{script_name}_state.json"
        self.data: dict[str, Any] = {
            "stage": stage,
            "script": script_name,
            "done": False,
            "started_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }
        if self.path.exists():
            try:
                self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                # The write is atomic (tmp + os.replace), so a power cut cannot
                # corrupt this file. A corrupt file means something else wrote
                # it -- start clean rather than guess.
                pass

    @property
    def done(self) -> bool:
        return bool(self.data.get("done"))

    def update(self, **kwargs: Any) -> "StageState":
        self.data.update(kwargs)
        self.data["updated_at"] = utc_now_iso()
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2, default=str), encoding="utf-8")
        atomic_replace(tmp, self.path)
        return self

    def finish(self, **kwargs: Any) -> "StageState":
        return self.update(done=True, finished_at=utc_now_iso(), **kwargs)

    def reset(self) -> "StageState":
        self.data = {
            "stage": self.data["stage"],
            "script": self.data["script"],
            "done": False,
            "started_at": utc_now_iso(),
        }
        return self.update()


def preflight(paths: Sequence[Path], *, need_free_gb: float = 2.0) -> None:
    """Fail before doing work, not after: inputs present, disk and RAM headroom."""
    import psutil

    missing = [str(p) for p in paths if not Path(p).exists()]
    if missing:
        raise FileNotFoundError(f"missing required input(s): {missing}")
    free_gb = shutil.disk_usage(str(DATA_PROCESSED.anchor)).free / 1024**3
    if free_gb < need_free_gb:
        raise RuntimeError(
            f"only {free_gb:.1f} GB free on {DATA_PROCESSED.anchor}, need {need_free_gb}"
        )
    avail_gb = psutil.virtual_memory().available / 1024**3
    logging.getLogger("main").info(
        "preflight OK: %d inputs present, %.1f GB free disk, %.1f GB free RAM, MAX_WORKERS=%d",
        len(paths), free_gb, avail_gb, MAX_WORKERS,
    )


# -----------------------------------------------------------------------------
# the cohort join -- one definition, thirteen callers
# -----------------------------------------------------------------------------
_COHORT_CACHE: dict[tuple[bool, bool], pd.DataFrame] = {}


def load_clean_cohort(dev: bool = False, *, with_text: bool = False) -> pd.DataFrame:
    """The Phase 1 clean cohort with every column a builder filters on.

    Columns: ``study_id, subject_id, split, link_tier, link_type, source,
    hadm_id, stay_id, ecg_time, cart_id, sqi_tier, decode_ok, length_ok,
    text_ok, image_clean_ok, image_scanlike_ok, icd_available,
    mortality_observable, readmission_eligible, hr_bucket`` (+ ``report_text``
    when ``with_text``).

    ``split`` comes from ``splits_subject_level.parquet`` and nothing else
    (§4.C invariant 1, trap 4). The Phase 1 index carries its own copy; this
    function asserts the two agree rather than trusting either alone.
    """
    key = (dev, with_text)
    cached = _COHORT_CACHE.get(key)
    if cached is not None:
        return cached.copy()

    meta_cols = ["study_id", "subject_id", "split", "link_tier", "cart_id", "hr_bucket"]
    if with_text:
        meta_cols.append("T_machine")
    meta = pd.read_parquet(
        DATA_PROCESSED / "index" / "ecg_metadata_clean_with_measurements.parquet",
        columns=meta_cols,
    ).rename(columns={"split": "_split_index", "T_machine": "report_text"})

    qc = pd.read_parquet(
        DATA_PROCESSED / "waveform_qc.parquet",
        columns=["study_id", "decode_ok", "length_ok", "sqi_tier", "text_ok",
                 "image_clean_ok", "image_scanlike_ok"],
    )
    avail = pd.read_parquet(
        DATA_PROCESSED / "linkage" / "label_availability.parquet",
        columns=["study_id", "ecg_time", "link_type", "source", "hadm_id", "stay_id",
                 "icd_available", "mortality_observable", "readmission_eligible"],
    )
    splits = pd.read_parquet(
        DATA_PROCESSED / "splits_subject_level.parquet", columns=["subject_id", "split"]
    )

    df = meta.merge(qc, on="study_id", how="left").merge(avail, on="study_id", how="left")
    df = df.merge(splits, on="subject_id", how="left", validate="many_to_one")

    if df["split"].isna().any():
        raise RuntimeError(
            f"{int(df['split'].isna().sum())} studies have no subject in "
            "splits_subject_level.parquet -- the cohort is not a subset of the frozen split"
        )
    mismatch = int((df["split"] != df["_split_index"]).sum())
    if mismatch:
        raise RuntimeError(
            f"{mismatch} studies disagree between splits_subject_level.parquet and the "
            "split column cached in the Phase 1 index. The frozen split is authoritative; "
            "investigate before building any task."
        )
    df = df.drop(columns=["_split_index"])

    # The clean index is already post-QC; assert rather than silently re-filter.
    if not (df["decode_ok"].fillna(False).all() and df["length_ok"].fillna(False).all()):
        raise RuntimeError("ecg_metadata_clean_with_measurements contains decode/length failures")

    if dev:
        keep = set(pd.read_parquet(DEV_SAMPLE, columns=["study_id"]).study_id)
        df = df[df.study_id.isin(keep)]

    df = df.sort_values("study_id", kind="mergesort").reset_index(drop=True)
    _COHORT_CACHE[key] = df
    return df.copy()


def _mask_sentinel(series: pd.Series) -> pd.Series:
    return series.astype("float64").mask(series == MISSING_SENTINEL)


def machine_measurements(dev: bool = False) -> pd.DataFrame:
    """Machine HR / QRS / QTc / axis / PR per study, sentinel-masked and range-gated.

    Never reads ``structured_features.qrs_ms`` or ``.pr_ms`` -- both are the
    NeuroKit2 values, not the machine measurement (spec §12.8.1, traps 1 and 8).

    ``qtc_ms`` is ``machine_qtc_ms``. §4.A.2.3 names
    ``structured_features.qtc_bazett_ms``, but that column belongs to the same
    defective family: it correlates with the machine QTc at r = 0.024 and is
    valid for only 656,358 studies against the machine column's 748,618. Round
    6.1's "every measurement threshold reads the MACHINE measurement" therefore
    extends to QTc; the NeuroKit value is carried as ``qtc_ms_bazett`` for the
    §4.A.2.8 sensitivity row and for provenance, and is never a label source.

    Returned measurement columns are float64 with ``NaN`` for "not measurable";
    each has a companion ``<name>_valid`` boolean.
    """
    meta = pd.read_parquet(
        DATA_PROCESSED / "index" / "ecg_metadata_clean_with_measurements.parquet",
        columns=["study_id", "rr_interval", "p_onset", "qrs_onset", "qrs_end",
                 "qrs_axis", "machine_hr_bpm", "machine_qrs_ms", "machine_qtc_ms"],
    )
    sf = pd.read_parquet(
        DATA_PROCESSED / "structured_features.parquet", columns=["study_id", "qtc_bazett_ms"]
    )
    df = meta.merge(sf, on="study_id", how="left")

    rr = _mask_sentinel(df["rr_interval"])
    p_on = _mask_sentinel(df["p_onset"])
    qrs_on = _mask_sentinel(df["qrs_onset"])
    qrs_end = _mask_sentinel(df["qrs_end"])
    axis = _mask_sentinel(df["qrs_axis"])

    out = pd.DataFrame({"study_id": df["study_id"]})
    out["hr_bpm"] = np.where(rr > 0, 60000.0 / rr, np.nan)
    out["qrs_ms"] = qrs_end - qrs_on
    out["pr_ms"] = qrs_on - p_on
    out["qrs_axis"] = axis
    out["qtc_ms"] = df["machine_qtc_ms"].astype("float64")
    out["qtc_ms_bazett"] = df["qtc_bazett_ms"].astype("float64")

    ranges = {"hr_bpm": (20, 300), "qrs_ms": (40, 300), "pr_ms": (50, 400),
              "qrs_axis": (-180, 180), "qtc_ms": (200, 800), "qtc_ms_bazett": (200, 800)}
    for col, (lo, hi) in ranges.items():
        out[col] = out[col].where(out[col].between(lo, hi))
        out[f"{col}_valid"] = out[col].notna()

    if dev:
        keep = set(pd.read_parquet(DEV_SAMPLE, columns=["study_id"]).study_id)
        out = out[out.study_id.isin(keep)]
    return out.reset_index(drop=True)


# The A2 / B1 / B2 / A5-masked-attribute bin definitions (§4.A.2.3), one place.
def hr_label(hr: pd.Series) -> pd.Series:
    out = pd.Series(
        np.select([hr < 60, hr < 100], ["bradycardia", "normal"], default="tachycardia"),
        index=hr.index, dtype=object,
    )
    return out.where(hr.notna())


def qrs_label(qrs: pd.Series) -> pd.Series:
    out = pd.Series(
        np.select([qrs < 100, qrs < 120], ["normal", "borderline"], default="wide"),
        index=qrs.index, dtype=object,
    )
    return out.where(qrs.notna())


def qtc_label(qtc: pd.Series) -> pd.Series:
    out = pd.Series(
        np.select([qtc < 350, qtc < 450], ["short", "normal"], default="prolonged"),
        index=qtc.index, dtype=object,
    )
    return out.where(qtc.notna())


def report_text_series(dev: bool = False) -> pd.DataFrame:
    """``study_id -> report_text`` (the ``T_machine`` column, §2.5 policy name)."""
    df = pd.read_parquet(
        DATA_PROCESSED / "index" / "ecg_metadata_clean_with_measurements.parquet",
        columns=["study_id", "T_machine"],
    ).rename(columns={"T_machine": "report_text"})
    if dev:
        keep = set(pd.read_parquet(DEV_SAMPLE, columns=["study_id"]).study_id)
        df = df[df.study_id.isin(keep)]
    return df.reset_index(drop=True)


# -----------------------------------------------------------------------------
# deterministic per-row RNG (§4.C invariant 2)
# -----------------------------------------------------------------------------
def stable_seed(*parts: Any) -> int:
    """SHA-256 of ``'|'.join(parts)`` -> a 31-bit seed. Identical on every run."""
    key = "|".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest()[:4], "big") % 2_147_483_648


def stable_uniform(keys: Iterable[Any], salt: str) -> np.ndarray:
    """Deterministic U[0,1) draw, one per key. Same value every run, no RNG state."""
    return np.array(
        [
            int.from_bytes(hashlib.sha256(f"{salt}|{k}".encode()).digest()[:8], "big") / 2**64
            for k in keys
        ],
        dtype="float64",
    )


# -----------------------------------------------------------------------------
# chunked parallel execution with part-parquet checkpointing
# -----------------------------------------------------------------------------
def part_dir(name: str) -> Path:
    path = PARTS_ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def completed_ids(name: str, id_column: str = "study_id") -> set[int]:
    done: set[int] = set()
    for part in sorted(part_dir(name).glob("part_*.parquet")):
        done.update(int(x) for x in pq.read_table(part, columns=[id_column])[id_column].to_pylist())
    return done


def write_part(name: str, rows: list[dict[str, Any]] | pd.DataFrame, schema: pa.Schema) -> Path:
    directory = part_dir(name)
    existing = sorted(directory.glob("part_*.parquet"))
    index = 0 if not existing else int(existing[-1].stem.split("_")[-1]) + 1
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    table = pa.Table.from_pandas(
        frame[[f.name for f in schema]], schema=schema, preserve_index=False
    )
    final = directory / f"part_{index:04d}.parquet"
    tmp = directory / f"part_{index:04d}.parquet.tmp"
    pq.write_table(table, tmp, compression="snappy")
    atomic_replace(tmp, final)
    return final


def publish_parts(name: str, out_path: Path, schema: pa.Schema, *, sort_by: str = "study_id",
                  metadata: dict[str, str] | None = None) -> int:
    import pyarrow.compute as pc

    parts = sorted(part_dir(name).glob("part_*.parquet"))
    if not parts:
        raise RuntimeError(f"no parts to publish for {name}")
    table = pa.concat_tables(
        [pq.read_table(p, schema=schema) for p in parts], promote_options="none"
    )
    table = pc.take(table, pc.sort_indices(table, sort_keys=[(sort_by, "ascending")]))
    meta = {b"created_at_iso": utc_now_iso().encode(), b"n_rows": str(table.num_rows).encode()}
    meta.update({k.encode(): str(v).encode() for k, v in (metadata or {}).items()})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".parquet.tmp")
    pq.write_table(table.replace_schema_metadata(meta), tmp, compression="snappy")
    atomic_replace(tmp, out_path)
    return int(table.num_rows)


def run_chunked(
    *,
    name: str,
    units: Sequence[int],
    worker: Callable[[int], dict[str, Any] | None],
    schema: pa.Schema,
    state: StageState,
    initializer: Callable[[], None] | None = None,
    chunk_size: int = CHUNK_STUDIES,
    desc: str = "",
    id_column: str = "study_id",
    workers: int | None = None,
) -> int:
    """Map ``worker`` over ``units`` in one process pool, flushing a part every
    ``chunk_size`` results.

    One pool for the whole run, not one per chunk: a worker's first
    ``read_modality`` call builds a modality index from the 470 MB manifest, and
    a fresh pool per chunk would pay that cost tens of times over.

    Resume: any unit already present in a part parquet is skipped, so a killed
    run loses at most the results buffered since the last flush. Returns the
    number of units processed in *this* invocation.
    """
    from concurrent.futures import ProcessPoolExecutor

    from tqdm import tqdm
    from tqdm.contrib.logging import logging_redirect_tqdm

    log = logging.getLogger("main")
    n_workers = workers or MAX_WORKERS
    done = completed_ids(name, id_column)
    pending = [u for u in units if u not in done]
    log.info(
        "%s: %d units total, %d already in parts, %d pending, workers=%d, flush every %d",
        name, len(units), len(done), len(pending), n_workers, chunk_size,
    )
    state.update(n_units=len(units), n_done=len(done), n_pending=len(pending))
    if not pending:
        return 0

    processed = 0
    started = time.time()
    rows: list[dict[str, Any]] = []

    def flush() -> None:
        if rows:
            path = write_part(name, rows, schema)
            log.info("wrote %s rows=%d", path.name, len(rows))
            rows.clear()

    with logging_redirect_tqdm():
        bar = tqdm(total=len(pending), file=sys.stderr, dynamic_ncols=True,
                   mininterval=0.5, desc=desc or name)
        with ProcessPoolExecutor(max_workers=n_workers, initializer=initializer) as pool:
            for row in pool.map(worker, pending, chunksize=BATCH_SIZE):
                if row is not None:
                    rows.append(row)
                processed += 1
                bar.update(1)
                if processed % chunk_size == 0:
                    flush()
                    rate = processed / max(1e-6, time.time() - started)
                    state.update(n_done=len(done) + processed, rate_per_s=round(rate, 2),
                                 eta_minutes=round((len(pending) - processed) / max(rate, 1e-6) / 60, 1))
                    log.info("%s: %d/%d done this run, %.1f units/s",
                             name, processed, len(pending), rate)
        flush()
        bar.close()
    state.update(n_done=len(done) + processed,
                 rate_per_s=round(processed / max(1e-6, time.time() - started), 2))
    return processed


# -----------------------------------------------------------------------------
# task output writer
# -----------------------------------------------------------------------------
def write_task_split_parquets(
    df: pd.DataFrame,
    task_key: str,
    *,
    schema: pa.Schema | None = None,
    prefix: str = "",
    split_column: str = "split",
) -> dict[str, int]:
    """Write ``{train,val,test}.parquet`` (or ``<prefix>{train,...}``) for one task."""
    out_dir = task_dir(task_key)
    counts: dict[str, int] = {}
    for split in SPLITS:
        part = df[df[split_column] == split]
        if schema is not None:
            table = pa.Table.from_pandas(
                part[[f.name for f in schema]], schema=schema, preserve_index=False
            )
        else:
            table = pa.Table.from_pandas(part, preserve_index=False)
        table = table.replace_schema_metadata(
            {b"task": task_key.encode(), b"split": split.encode(),
             b"created_at_iso": utc_now_iso().encode(), b"n_rows": str(len(part)).encode()}
        )
        name = f"{prefix}{split}.parquet"
        tmp = out_dir / (name + ".tmp")
        pq.write_table(table, tmp, compression="snappy")
        atomic_replace(tmp, out_dir / name)
        counts[split] = int(len(part))
    return counts


def write_cohort_manifest(df: pd.DataFrame, task_key: str,
                          name: str = "cohort_manifest.parquet") -> int:
    out_dir = task_dir(task_key)
    tmp = out_dir / (name + ".tmp")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), tmp, compression="snappy")
    atomic_replace(tmp, out_dir / name)
    return int(len(df))


def write_task_readme(task_key: str, body: str) -> Path:
    out_dir = task_dir(task_key)
    path = out_dir / "README.md"
    path.write_text(body.rstrip() + "\n", encoding="utf-8")
    return path


def split_summary(df: pd.DataFrame, split_column: str = "split") -> dict[str, Any]:
    """Rows and subjects per split, and the zero-overlap assertion (§9.2, §4.C)."""
    out: dict[str, Any] = {"n_rows": int(len(df)), "n_subjects": int(df.subject_id.nunique())}
    seen: dict[str, set[int]] = {}
    for split in SPLITS:
        part = df[df[split_column] == split]
        seen[split] = set(part.subject_id)
        out[f"n_rows_{split}"] = int(len(part))
        out[f"n_subjects_{split}"] = int(part.subject_id.nunique())
    overlap = (
        (seen["train"] & seen["val"]) | (seen["train"] & seen["test"]) | (seen["val"] & seen["test"])
    )
    out["subject_overlap"] = len(overlap)
    if overlap:
        raise RuntimeError(
            f"{len(overlap)} subjects appear in more than one split -- §4.C invariant 1"
        )
    return out


def add_std_args(parser: Any) -> None:
    """``--dev`` (smoke test on dev_sample), ``--force`` (ignore the done flag)."""
    parser.add_argument("--dev", action="store_true",
                        help="run on data/processed/dev_sample/ instead of the full cohort")
    parser.add_argument("--force", action="store_true",
                        help="ignore the state file's done flag and rebuild from scratch")
    parser.add_argument("--limit", type=int, default=0,
                        help="cap the number of studies processed (debugging only)")
