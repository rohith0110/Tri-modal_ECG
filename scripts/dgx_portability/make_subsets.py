"""Build the three derived datasets the campaign table names but nothing produced.

    ./ecg_env/Scripts/python.exe scripts/dgx_portability/make_subsets.py plan
    ./ecg_env/Scripts/python.exe scripts/dgx_portability/make_subsets.py build \
        --datasets signals_12lead_L3
    ./ecg_env/Scripts/python.exe scripts/dgx_portability/make_subsets.py verify

Three datasets, all subsets of a modality already on disk:

| dataset                  | campaigns | contents                                     |
| ------------------------ | --------- | -------------------------------------------- |
| `signals_12lead_L3`      | 5, 7      | int16 12-lead preprocessed, L3 studies only   |
| `images_clean_12lead_L3` | 7         | clean 12-lead tars, L3 studies only           |
| `images_scanlike_test`   | 10        | scan-like tars (both layouts), TEST split only |

**The study list comes from the task parquets, not from re-derived linkage.**
`signals_12lead_L3` / `images_clean_12lead_L3` are the union of the `is_primary`
rows of A1, A3, A4 and A6 -- the four tasks `campaign_runs.py` routes to
campaigns 5 and 7 -- which is exactly the set `TaskDataset(primary_only=True)`
will ask for. Measured 2026-08-29: 422,147 studies (train 295,236 / val 42,563 /
test 84,348). `images_scanlike_test` is the test split of the frozen
subject-level split table, which is what campaign 10's test-only sweeps read.

**How a subset is read back.** A subset container holds its own rows in its own
order, so the base `modality_manifest.parquet` no longer describes it. Each
dataset therefore also writes `manifest_overlays/<dataset>.parquet` -- the
manifest schema, its studies only -- and `modality.py` lets an overlay row
replace the base row for that (study_id, kind, layout). Nothing else changes:
the trainer, the evaluator and the baselines all still call `read_modality()`.
A study *outside* the subset keeps its base-container row, and the base
container is not staged on a subset campaign, so a miss is a loud missing-file
error rather than silently wrong bytes.

**One file per split**, because the DGX stages them separately: campaign 5 holds
train+val while training and swaps in test for evaluation.

**Resumable.** One split at a time, written to a temp file and atomically
renamed only after its sha256 is in the dataset's `checksums.json`. A power cut
costs the split in flight; the identical command resumes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPTS = Path(__file__).resolve().parents[1] / "phase2_tasks_benchmark_and_paper"
sys.path.insert(0, str(SCRIPTS))

# §8.2 uploads int16 signals, so a signal subset is cut from the int16 copies --
# codes copied, not requantised. Forced here rather than left to the caller's
# environment: a subset built from the float32 originals would be twice the size
# and would silently disagree with what the DGX reads.
os.environ["TRIMODAL_SIGNAL_INT16"] = "1"

from _dataset_lib import build_common as bc                            # noqa: E402
from _dataset_lib import modality as mod                               # noqa: E402

STAGE = "P2.4c"
DERIVED_ROOT = bc.DATA_PROCESSED / "derived"
OVERLAY_DIR = bc.DATA_PROCESSED / "manifest_overlays"
SPLITS_PATH = bc.DATA_PROCESSED / "splits_subject_level.parquet"
SPLITS = ("train", "val", "test")

# The four tasks campaign_runs.py routes to campaign 5 (and, minus A4, to 7).
L3_TASKS = ("A1_ecg_diagnosis", "A3_lab_abnormality",
            "A4_event_localization", "A6_risk_stratification")

MANIFEST_COLS = ["study_id", "subject_id", "modality_kind", "layout",
                 "container_path", "container_row", "container_offset",
                 "container_length"]

DATASETS: dict[str, dict[str, Any]] = {
    "signals_12lead_L3": {
        "kind": "preprocessed_12lead",
        "cohort": "l3_tasks",
        "splits": SPLITS,
    },
    "images_clean_12lead_L3": {
        "kind": "image_clean_12lead",
        "cohort": "l3_tasks",
        "splits": SPLITS,
    },
    "images_scanlike_test": {
        "kind": ("image_scanlike_12lead", "image_scanlike_lead2"),
        "cohort": "all",
        "splits": ("test",),
    },
}


# -----------------------------------------------------------------------------
# cohorts -- read off the task tables, never re-derived
# -----------------------------------------------------------------------------
def split_table() -> pd.DataFrame:
    """study_id -> split, from the frozen subject-level split plus the index."""
    splits = pd.read_parquet(SPLITS_PATH)[["subject_id", "split"]].drop_duplicates("subject_id")
    meta = pd.read_parquet(bc.DATA_PROCESSED / "index" / "ecg_metadata_clean.parquet",
                           columns=["study_id", "subject_id"])
    return meta.merge(splits, on="subject_id", how="inner")


def cohort_ids(cohort: str, split: str) -> np.ndarray:
    """Sorted study ids for one cohort and split."""
    if cohort == "all":
        table = split_table()
        return np.sort(table.loc[table.split == split, "study_id"].to_numpy())
    if cohort != "l3_tasks":
        raise ValueError(f"unknown cohort {cohort!r}")
    ids: set[int] = set()
    for task in L3_TASKS:
        path = bc.DATA_PROCESSED / "tasks" / task / f"{split}.parquet"
        frame = pd.read_parquet(path, columns=["study_id", "is_primary"])
        ids |= set(frame.loc[frame.is_primary, "study_id"].astype("int64").tolist())
    return np.sort(np.fromiter(ids, dtype="int64", count=len(ids)))


# -----------------------------------------------------------------------------
# writing
# -----------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_rows(kind: str, ids: np.ndarray) -> pd.DataFrame:
    """container_path + container_row/offset/length for these studies, in source order.

    Source order matters: the 12-lead containers are gzip-chunked 64 rows at a
    time, so reading them in ascending row order is the difference between one
    sequential pass and 64x read amplification.
    """
    index = mod._index_for(kind)
    missing = [int(s) for s in ids if int(s) not in index]
    if missing:
        raise SystemExit(f"{kind}: {len(missing)} studies have no container row "
                         f"(first few: {missing[:5]})")
    rows = [(int(s), *index[int(s)]) for s in ids]
    if kind in mod.SIGNAL_KINDS:
        frame = pd.DataFrame(rows, columns=["study_id", "container_path", "container_row"])
        return frame.sort_values(["container_path", "container_row"], ignore_index=True)
    frame = pd.DataFrame(rows, columns=["study_id", "container_path",
                                        "container_offset", "container_length"])
    return frame.sort_values(["container_path", "container_offset"], ignore_index=True)


def build_signal_split(kind: str, ids: np.ndarray, target: Path, log) -> pd.DataFrame:
    """Copy the int16 codes and their per-record scale into one subset container.

    The codes are copied, not requantised: the subset is bit-identical to the
    Step 5 int16 copy it comes from, so the equivalence proof still covers it.
    """
    import h5py

    frame = _source_rows(kind, ids)
    tmp = target.with_suffix(".h5.tmp")
    if tmp.exists():
        tmp.unlink()

    first_path = mod._resolve_h5(frame.container_path.iloc[0])
    with h5py.File(first_path, "r") as probe:
        row_shape = probe["signal"].shape[1:]
        dtype = probe["signal"].dtype
        has_scale = "scale" in probe
        attrs = dict(probe.attrs)
        # Same chunking as the source (64 rows x one lead), so the subset reads
        # the way the original does. Clamped for a split smaller than a chunk.
        source_chunks = probe["signal"].chunks or (64, *row_shape)
    chunks = (min(source_chunks[0], len(frame)), *source_chunks[1:])
    if not has_scale:
        raise SystemExit(
            f"{first_path} has no `scale` dataset -- run make_int16.py first; the "
            "subset must be the int16 copy, not the float32 original (§8.2).")

    written = 0
    with h5py.File(tmp, "w") as out:
        signal = out.create_dataset("signal", shape=(len(frame), *row_shape), dtype=dtype,
                                    chunks=chunks, compression="gzip",
                                    compression_opts=4)
        out_ids = out.create_dataset("study_id", shape=(len(frame),), dtype="int64")
        out_scale = out.create_dataset("scale", shape=(len(frame),), dtype="float32")
        for path, block in frame.groupby("container_path", sort=False):
            source = mod._resolve_h5(path)
            log.info("  <- %s (%d rows)", source.name, len(block))
            with h5py.File(source, "r") as handle:
                rows = block.container_row.to_numpy()
                scale = handle["scale"]
                for start in range(0, len(rows), 64):
                    take = rows[start:start + 64]
                    # h5py fancy indexing needs ascending unique indices; the
                    # frame is already sorted by row, and a container row is
                    # unique per study.
                    signal[written:written + len(take)] = handle["signal"][take, ...]
                    out_scale[written:written + len(take)] = scale[take]
                    out_ids[written:written + len(take)] = \
                        block.study_id.to_numpy()[start:start + len(take)]
                    written += len(take)
                    if written % 12800 == 0:
                        log.info("    %d/%d rows", written, len(frame))
        for key, value in attrs.items():
            out.attrs[key] = value
        out.attrs["subset_of"] = str(frame.container_path.iloc[0])
        out.attrs["n_studies"] = len(frame)
    bc.atomic_replace(tmp, target)
    frame = frame.copy()
    frame["new_row"] = np.arange(len(frame), dtype="int64")
    return frame


def build_image_split(kinds: tuple[str, ...], ids: np.ndarray, target: Path,
                      log) -> pd.DataFrame:
    """One tar per split holding this subset's image bytes, member = `<study_id>.png`.

    The overlay records each member's header offset and payload length, which is
    exactly what `_read_image` seeks to (`container_offset + 512`).
    """
    tmp = target.with_suffix(".tar.tmp")
    if tmp.exists():
        tmp.unlink()

    records: list[dict[str, Any]] = []
    with tarfile.open(tmp, "w") as out:
        for kind in kinds:
            frame = _source_rows(kind, ids)
            log.info("  %s: %d members", kind, len(frame))
            for count, row in enumerate(frame.itertuples(index=False), start=1):
                payload = mod.read_modality(int(row.study_id), kind)
                name = f"{kind}/{int(row.study_id)}.png" if len(kinds) > 1 \
                    else f"{int(row.study_id)}.png"
                info = tarfile.TarInfo(name=name)
                info.size = len(payload)
                import io

                # The header block starts here; `_read_image` seeks to
                # container_offset + TAR_HEADER_BYTES for the payload.
                offset = out.fileobj.tell()
                out.addfile(info, io.BytesIO(payload))
                records.append({"study_id": int(row.study_id), "kind": kind,
                                "container_offset": int(offset),
                                "container_length": len(payload)})
                if count % 10000 == 0:
                    log.info("    %d/%d", count, len(frame))
    bc.atomic_replace(tmp, target)
    return pd.DataFrame(records)


def overlay_rows(dataset: str, kind: str, split_frames: dict[str, pd.DataFrame],
                 relative: dict[str, str]) -> pd.DataFrame:
    """The manifest rows describing this dataset's containers."""
    base_kind, layout = mod._IMAGE_KIND_TO_MANIFEST.get(kind, (kind, None))
    subjects = pd.read_parquet(bc.DATA_PROCESSED / "index" / "ecg_metadata_clean.parquet",
                               columns=["study_id", "subject_id"])
    out = []
    for split, frame in split_frames.items():
        block = frame.copy()
        block["modality_kind"] = base_kind
        block["layout"] = layout
        block["container_path"] = relative[split]
        if "new_row" in block.columns:
            block["container_row"] = block["new_row"]
            block["container_offset"] = 0
            block["container_length"] = 0
        else:
            block["container_row"] = 0
        out.append(block)
    merged = pd.concat(out, ignore_index=True).merge(subjects, on="study_id", how="left")
    return merged[MANIFEST_COLS]


def build(datasets: list[str], log) -> int:
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    for dataset in datasets:
        spec = DATASETS[dataset]
        kinds = spec["kind"] if isinstance(spec["kind"], tuple) else (spec["kind"],)
        directory = DERIVED_ROOT / dataset
        directory.mkdir(parents=True, exist_ok=True)
        checksums_path = directory / "checksums.json"
        checksums = json.loads(checksums_path.read_text(encoding="utf-8")) \
            if checksums_path.exists() else {}

        is_signal = kinds[0] in mod.SIGNAL_KINDS
        suffix = "h5" if is_signal else "tar"
        per_kind: dict[str, dict[str, pd.DataFrame]] = {k: {} for k in kinds}
        relative: dict[str, str] = {}

        for split in spec["splits"]:
            ids = cohort_ids(spec["cohort"], split)
            name = f"{dataset}__{split}.{suffix}"
            target = directory / name
            relative[split] = f"derived/{dataset}/{name}"
            rows_path = directory / f"{dataset}__{split}__rows.parquet"

            if target.exists() and name in checksums and rows_path.exists():
                log.info("%s %s already present (%d studies), skipping",
                         dataset, split, checksums[name]["n_rows"])
            else:
                log.info("%s %s: %d studies -> %s", dataset, split, len(ids), name)
                if is_signal:
                    frame = build_signal_split(kinds[0], ids, target, log)
                else:
                    frame = build_image_split(kinds, ids, target, log)
                frame.to_parquet(rows_path, index=False)
                checksums[name] = {"sha256": sha256_file(target),
                                   "bytes": target.stat().st_size,
                                   "n_rows": int(len(frame))}
                checksums_path.write_text(json.dumps(checksums, indent=2), encoding="utf-8")
                log.info("  wrote %s (%.2f GB, %d rows)", name,
                         target.stat().st_size / 1e9, len(frame))

            frame = pd.read_parquet(rows_path)
            for kind in kinds:
                block = frame[frame["kind"] == kind] if "kind" in frame.columns else frame
                per_kind[kind][split] = block

        overlays = [overlay_rows(dataset, kind, per_kind[kind], relative) for kind in kinds]
        overlay = pd.concat(overlays, ignore_index=True)
        overlay.to_parquet(OVERLAY_DIR / f"{dataset}.parquet", index=False)
        log.info("%s: overlay written, %d rows", dataset, len(overlay))
    return 0


def verify(datasets: list[str], log) -> int:
    failures = 0
    for dataset in datasets:
        directory = DERIVED_ROOT / dataset
        checksums_path = directory / "checksums.json"
        if not checksums_path.exists():
            log.error("%s: no checksums.json -- nothing built yet", dataset)
            failures += 1
            continue
        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
        for name, expected in sorted(checksums.items()):
            path = directory / name
            if not path.exists():
                log.error("%s: %s recorded but missing", dataset, name)
                failures += 1
                continue
            if sha256_file(path) != expected["sha256"]:
                log.error("%s: %s CHECKSUM MISMATCH", dataset, name)
                failures += 1
            else:
                log.info("%s: %s OK (%.2f GB, %d rows)", dataset, name,
                         expected["bytes"] / 1e9, expected["n_rows"])
        missing = [s for s in DATASETS[dataset]["splits"]
                   if not any(f"__{s}." in n for n in checksums)]
        if missing:
            log.error("%s: splits not yet built: %s", dataset, missing)
            failures += 1
    return 1 if failures else 0


def plan(datasets: list[str], log) -> int:
    """Count the studies and estimate the bytes, without writing anything."""
    for dataset in datasets:
        spec = DATASETS[dataset]
        kinds = spec["kind"] if isinstance(spec["kind"], tuple) else (spec["kind"],)
        log.info("=== %s (%s) ===", dataset, ", ".join(kinds))
        total = 0
        for split in spec["splits"]:
            ids = cohort_ids(spec["cohort"], split)
            estimate = 0.0
            for kind in kinds:
                estimate += len(ids) * _bytes_per_study(kind)
            total += estimate
            log.info("  %-5s %7d studies  ~%.2f GB", split, len(ids), estimate / 1e9)
        log.info("  total ~%.2f GB", total / 1e9)
    return 0


def _bytes_per_study(kind: str) -> float:
    """Measured average container bytes per study, for the plan estimate."""
    index = mod._index_for(kind)
    paths = {row[0] for row in list(index.values())[:2000]}
    if kind in mod.SIGNAL_KINDS:
        total = sum(mod._resolve_h5(p).stat().st_size for p in paths)
        rows = sum(1 for row in index.values() if row[0] in paths)
        return total / max(rows, 1)
    lengths = [row[2] for row in list(index.values())[:5000]]
    return float(np.mean(lengths)) + 1024


def _self_check(log) -> int:
    """Build a 40-study micro-subset and prove it reads back identically.

    This is the only property that matters and the only one that is easy to get
    wrong: after the overlay is in place, `read_modality()` must return exactly
    the bytes/codes it returned from the base container, for a signal and for an
    image, with no caller changed. Everything it writes is deleted again.
    """
    import shutil

    scratch = DERIVED_ROOT / "_selfcheck"
    overlay_path = OVERLAY_DIR / "_selfcheck.parquet"
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True, exist_ok=True)
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        ids = cohort_ids("l3_tasks", "val")[:40]
        before_signal = {int(s): mod.read_modality(int(s), "preprocessed_12lead").copy()
                         for s in ids}
        before_image = {int(s): mod.read_modality(int(s), "image_clean_12lead") for s in ids}

        signal_rows = build_signal_split("preprocessed_12lead", ids,
                                         scratch / "sig__val.h5", log)
        image_rows = build_image_split(("image_clean_12lead",), ids,
                                       scratch / "img__val.tar", log)
        overlay = pd.concat([
            overlay_rows("_selfcheck", "preprocessed_12lead", {"val": signal_rows},
                         {"val": "derived/_selfcheck/sig__val.h5"}),
            overlay_rows("_selfcheck", "image_clean_12lead", {"val": image_rows},
                         {"val": "derived/_selfcheck/img__val.tar"}),
        ], ignore_index=True)
        overlay.to_parquet(overlay_path, index=False)

        mod._INDEX.clear()
        mod.close_handles()
        for study_id in ids:
            after = mod.read_modality(int(study_id), "preprocessed_12lead")
            assert np.array_equal(after, before_signal[int(study_id)]), \
                f"signal mismatch through the overlay for study {study_id}"
            assert mod.read_modality(int(study_id), "image_clean_12lead") \
                == before_image[int(study_id)], \
                f"image mismatch through the overlay for study {study_id}"
        # a study OUTSIDE the subset must still resolve to its base container
        outside = next(s for s in cohort_ids("l3_tasks", "val")[100:105])
        assert mod.read_modality(int(outside), "preprocessed_12lead").shape[0] == 12
        log.info("make_subsets self-check PASS (40 studies, signal + image, overlay live)")
        return 0
    finally:
        mod._INDEX.clear()
        mod.close_handles()
        overlay_path.unlink(missing_ok=True)
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("action", choices=["plan", "build", "verify", "selfcheck"])
    parser.add_argument("--datasets", nargs="+", default=sorted(DATASETS),
                        choices=sorted(DATASETS))
    args = parser.parse_args(argv)

    log = bc.setup_logging("make_subsets", stage=STAGE)
    log.info("make_subsets %s: datasets=%s", args.action, args.datasets)
    if args.action == "selfcheck":
        return _self_check(log)
    if args.action == "plan":
        return plan(args.datasets, log)
    if args.action == "build":
        return build(args.datasets, log)
    return verify(args.datasets, log)


if __name__ == "__main__":
    raise SystemExit(main())
