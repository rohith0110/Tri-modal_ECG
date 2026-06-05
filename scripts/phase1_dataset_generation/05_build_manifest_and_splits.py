#!/usr/bin/env python3
"""Stage 10A: build the canonical modality manifest.

Run from the scripts directory:
    ..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\05_build_manifest_and_splits.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from _stage1_common import (
    DATA_PROCESSED,
    STAGE_REPORT_DIR,
    dataset_version_stamp,
    relative,
    script_commit_hash,
    setup_main_logger,
    utc_now_iso,
    write_text_atomic,
)


SCRIPT_NAME = Path(__file__).stem
INDEX_PATH = DATA_PROCESSED / "index" / "ecg_metadata.parquet"
OUTPUT_PATH = DATA_PROCESSED / "modality_manifest.parquet"
RUN_DIR = STAGE_REPORT_DIR / "stage_10_run"
VALIDATION_PATH = RUN_DIR / "05_build_manifest_and_splits.validation.json"

SIGNALS_MANIFEST = DATA_PROCESSED / "signals" / "signals_manifest.parquet"
PREPROCESSED_MANIFEST = DATA_PROCESSED / "signals" / "preprocessed_signals_manifest.parquet"
IMAGE_MANIFESTS = [
    (DATA_PROCESSED / "images" / "clean_lead2_manifest.parquet", "image_clean", "lead2"),
    (DATA_PROCESSED / "images" / "clean_12lead_manifest.parquet", "image_clean", "12lead"),
    (DATA_PROCESSED / "images" / "scanlike_lead2_manifest.parquet", "image_scanlike", "lead2"),
    (DATA_PROCESSED / "images" / "scanlike_12lead_manifest.parquet", "image_scanlike", "12lead"),
]
CORRUPTED_PATH = DATA_PROCESSED / "signals_corrupted.parquet"

MANIFEST_COLUMNS = [
    "study_id",
    "subject_id",
    "modality_kind",
    "layout",
    "container_path",
    "container_row",
    "container_offset",
    "container_length",
    "sha256",
    "dataset_version",
    "created_at",
    "corruption_type",
    "snr_db",
    "corruption_row",
    "source_manifest",
]

NON_CORRUPTED_EXPECTED = [
    ("raw_lead2", None),
    ("raw_12lead", None),
    ("preprocessed_lead2", None),
    ("preprocessed_12lead", None),
    ("image_clean", "lead2"),
    ("image_clean", "12lead"),
    ("image_scanlike", "lead2"),
    ("image_scanlike", "12lead"),
]


def _created_at_from_metadata(path: Path) -> pd.Timestamp:
    metadata = pq.ParquetFile(path).schema_arrow.metadata or {}
    raw = metadata.get(b"created_at_iso") or metadata.get(b"created_at")
    if raw:
        try:
            return pd.Timestamp(raw.decode("utf-8")).tz_localize(None)
        except Exception:
            pass
    return pd.Timestamp.utcnow().tz_localize(None)


def _base_frame(path: Path, source_manifest: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"missing modality source manifest: {path}")
    df = pd.read_parquet(path)
    for col in ["study_id", "subject_id", "modality_kind", "container_path", "sha256", "dataset_version", "created_at"]:
        if col not in df.columns:
            raise ValueError(f"{path} is missing required column {col}")
    out = pd.DataFrame()
    out["study_id"] = df["study_id"].astype("int64")
    out["subject_id"] = df["subject_id"].astype("int64")
    out["modality_kind"] = df["modality_kind"].astype(str)
    out["layout"] = pd.Series([None] * len(df), dtype="object")
    out["container_path"] = df["container_path"].astype(str)
    out["container_row"] = df["container_row"].astype("Int64") if "container_row" in df.columns else pd.Series([pd.NA] * len(df), dtype="Int64")
    out["container_offset"] = (
        df["container_offset"].astype("Int64") if "container_offset" in df.columns else pd.Series([pd.NA] * len(df), dtype="Int64")
    )
    out["container_length"] = (
        df["container_length"].astype("Int64") if "container_length" in df.columns else pd.Series([pd.NA] * len(df), dtype="Int64")
    )
    out["sha256"] = df["sha256"].astype(str)
    out["dataset_version"] = df["dataset_version"].astype(str)
    out["created_at"] = pd.to_datetime(df["created_at"], utc=True, errors="coerce").dt.tz_localize(None)
    out["corruption_type"] = pd.Series([None] * len(df), dtype="object")
    out["snr_db"] = pd.Series([pd.NA] * len(df), dtype="Int32")
    out["corruption_row"] = pd.Series([pd.NA] * len(df), dtype="Int64")
    out["source_manifest"] = source_manifest
    return out[MANIFEST_COLUMNS]


def _image_frame(path: Path, modality_kind: str, layout: str) -> pd.DataFrame:
    out = _base_frame(path, relative(path))
    out["modality_kind"] = modality_kind
    out["layout"] = layout
    return out


def _sha256_float32_signal(values: np.ndarray) -> str:
    arr = np.ascontiguousarray(np.asarray(values, dtype=np.float32))
    return hashlib.sha256(arr.tobytes()).hexdigest()


def _corrupted_frame() -> pd.DataFrame:
    if not CORRUPTED_PATH.exists():
        raise FileNotFoundError(f"missing corrupted signal parquet: {CORRUPTED_PATH}")
    pf = pq.ParquetFile(CORRUPTED_PATH)
    source_created = _created_at_from_metadata(CORRUPTED_PATH)
    rows: list[pd.DataFrame] = []
    global_start = 0
    columns = ["study_id", "subject_id", "corruption_type", "snr_db", "signal"]
    for rg_idx in range(pf.metadata.num_row_groups):
        table = pf.read_row_group(rg_idx, columns=columns)
        n = table.num_rows
        signal_array = table.column("signal").combine_chunks()
        values = signal_array.values.to_numpy(zero_copy_only=False).reshape(n, 5000)
        hashes = [_sha256_float32_signal(values[i]) for i in range(n)]
        frame = table.select(["study_id", "subject_id", "corruption_type", "snr_db"]).to_pandas()
        frame["modality_kind"] = "signal_corrupted"
        frame["layout"] = None
        frame["container_path"] = "signals_corrupted.parquet"
        frame["container_row"] = pd.Series(np.arange(global_start, global_start + n), dtype="Int64")
        frame["container_offset"] = pd.Series([pd.NA] * n, dtype="Int64")
        frame["container_length"] = pd.Series([pd.NA] * n, dtype="Int64")
        frame["sha256"] = hashes
        frame["dataset_version"] = dataset_version_stamp()
        frame["created_at"] = source_created
        frame["corruption_row"] = pd.Series(np.arange(global_start, global_start + n), dtype="Int64")
        frame["source_manifest"] = relative(CORRUPTED_PATH)
        rows.append(frame[MANIFEST_COLUMNS])
        global_start += n
    return pd.concat(rows, ignore_index=True)


def _canonical_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("study_id", pa.int64(), nullable=False),
            pa.field("subject_id", pa.int64(), nullable=False),
            pa.field("modality_kind", pa.string(), nullable=False),
            pa.field("layout", pa.string(), nullable=True),
            pa.field("container_path", pa.string(), nullable=False),
            pa.field("container_row", pa.int64(), nullable=True),
            pa.field("container_offset", pa.int64(), nullable=True),
            pa.field("container_length", pa.int64(), nullable=True),
            pa.field("sha256", pa.string(), nullable=False),
            pa.field("dataset_version", pa.string(), nullable=False),
            pa.field("created_at", pa.timestamp("ns"), nullable=False),
            pa.field("corruption_type", pa.string(), nullable=True),
            pa.field("snr_db", pa.int32(), nullable=True),
            pa.field("corruption_row", pa.int64(), nullable=True),
            pa.field("source_manifest", pa.string(), nullable=False),
        ]
    )


def _write_manifest_atomic(df: pd.DataFrame) -> None:
    table = pa.Table.from_pandas(df[MANIFEST_COLUMNS], schema=_canonical_schema(), preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata.update(
        {
            b"dataset_version": dataset_version_stamp().encode("utf-8"),
            b"created_at_iso": utc_now_iso().encode("utf-8"),
            b"modality_kind": b"modality_manifest",
            b"n_rows": str(table.num_rows).encode("utf-8"),
            b"script_commit_hash": script_commit_hash().encode("utf-8"),
        }
    )
    tmp = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".tmp")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table.replace_schema_metadata(metadata), tmp, compression="snappy")
    os.replace(tmp, OUTPUT_PATH)


def _validate_manifest(df: pd.DataFrame, index: pd.DataFrame) -> dict[str, Any]:
    index_ids = set(index["study_id"].astype("int64").tolist())
    manifest_ids = set(df["study_id"].astype("int64").tolist())
    key = pd.DataFrame(
        {
            "study_id": df["study_id"].astype("int64"),
            "modality_kind": df["modality_kind"].astype(str),
            "layout": df["layout"].fillna("").astype(str),
            "corruption_type": df["corruption_type"].fillna("").astype(str),
            "snr_db": df["snr_db"].fillna(-999999).astype("int64"),
        }
    )
    non_corrupted = df["modality_kind"] != "signal_corrupted"
    missing_expected: dict[str, int] = {}
    for modality_kind, layout in NON_CORRUPTED_EXPECTED:
        mask = df["modality_kind"].eq(modality_kind)
        if layout is None:
            mask &= df["layout"].isna()
            label = modality_kind
        else:
            mask &= df["layout"].eq(layout)
            label = f"{modality_kind}:{layout}"
        missing_expected[label] = int(len(index_ids - set(df.loc[mask, "study_id"].astype("int64").tolist())))
    unique_paths = sorted(set(df["container_path"].astype(str).tolist()))
    path_exists = {path: (DATA_PROCESSED / path).exists() for path in unique_paths}
    hdf5_or_parquet = df["container_path"].astype(str).str.endswith((".h5", ".parquet"))
    tar_rows = df["container_path"].astype(str).str.endswith(".tar")
    validation = {
        "manifest_total_row_count": int(len(df)),
        "row_count_by_modality_kind": {str(k): int(v) for k, v in df["modality_kind"].value_counts(dropna=False).to_dict().items()},
        "row_count_by_image_layout": {
            f"{kind}:{layout}": int(count)
            for (kind, layout), count in df.loc[df["layout"].notna()].groupby(["modality_kind", "layout"]).size().to_dict().items()
        },
        "row_count_by_corruption_type_and_snr_db": {
            f"{ctype}:{int(snr)}": int(count)
            for (ctype, snr), count in df.loc[df["modality_kind"].eq("signal_corrupted")]
            .groupby(["corruption_type", "snr_db"])
            .size()
            .to_dict()
            .items()
        },
        "duplicate_key_count": int(key.duplicated().sum()),
        "orphan_study_id_count": int(len(manifest_ids - index_ids)),
        "missing_expected_modality_rows": missing_expected,
        "invalid_container_path_count": int(sum(not ok for ok in path_exists.values())),
        "invalid_container_paths_sample": [path for path, ok in path_exists.items() if not ok][:20],
        "missing_hdf5_or_parquet_row_locator_count": int(df.loc[hdf5_or_parquet, "container_row"].isna().sum()),
        "missing_tar_offset_or_length_count": int(
            (df.loc[tar_rows, "container_offset"].isna() | df.loc[tar_rows, "container_length"].isna()).sum()
        ),
        "missing_sha256_count": int(df["sha256"].isna().sum() + df["sha256"].eq("").sum()),
        "dataset_version_null_count": int(df["dataset_version"].isna().sum() + df["dataset_version"].eq("").sum()),
        "created_at_null_count": int(df["created_at"].isna().sum()),
        "preprocessed_lead2_rows": int(df["modality_kind"].eq("preprocessed_lead2").sum()),
        "preprocessed_12lead_rows": int(df["modality_kind"].eq("preprocessed_12lead").sum()),
        "structured_features_included": bool(df["modality_kind"].eq("structured_features").any()),
        "expected_non_corrupted_rows": int(len(index) * len(NON_CORRUPTED_EXPECTED)),
        "actual_non_corrupted_rows": int(non_corrupted.sum()),
        "output_path": relative(OUTPUT_PATH),
    }
    validation["passed"] = (
        validation["duplicate_key_count"] == 0
        and validation["orphan_study_id_count"] == 0
        and all(v == 0 for v in missing_expected.values())
        and validation["invalid_container_path_count"] == 0
        and validation["missing_hdf5_or_parquet_row_locator_count"] == 0
        and validation["missing_tar_offset_or_length_count"] == 0
        and validation["missing_sha256_count"] == 0
        and validation["dataset_version_null_count"] == 0
        and validation["created_at_null_count"] == 0
        and validation["preprocessed_lead2_rows"] > 0
        and validation["preprocessed_12lead_rows"] > 0
        and not validation["structured_features_included"]
    )
    return validation


def main() -> None:
    logger = setup_main_logger(SCRIPT_NAME)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"missing metadata index: {INDEX_PATH}")
    index = pd.read_parquet(INDEX_PATH, columns=["study_id", "subject_id"])
    logger.info("building signal manifest rows")
    frames = [
        _base_frame(SIGNALS_MANIFEST, relative(SIGNALS_MANIFEST)),
        _base_frame(PREPROCESSED_MANIFEST, relative(PREPROCESSED_MANIFEST)),
    ]
    logger.info("building image manifest rows")
    frames.extend(_image_frame(path, kind, layout) for path, kind, layout in IMAGE_MANIFESTS)
    logger.info("building corrupted signal manifest rows with payload hashes")
    frames.append(_corrupted_frame())
    manifest = pd.concat(frames, ignore_index=True)
    manifest["created_at"] = pd.to_datetime(manifest["created_at"], errors="coerce")
    validation = _validate_manifest(manifest, index)
    logger.info("writing canonical manifest rows=%d", len(manifest))
    _write_manifest_atomic(manifest)
    write_text_atomic(json.dumps(validation, indent=2, sort_keys=True) + "\n", VALIDATION_PATH)
    sys.stdout.write(json.dumps(validation, indent=2, sort_keys=True) + "\n")
    if not validation["passed"]:
        raise SystemExit("modality manifest validation failed")


if __name__ == "__main__":
    main()
