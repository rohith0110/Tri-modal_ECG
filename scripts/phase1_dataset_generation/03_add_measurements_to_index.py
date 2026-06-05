#!/usr/bin/env python3
"""Stage 10A: add raw machine-measurement fields to the ECG index.

Run from the scripts directory:
    ..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\03_add_measurements_to_index.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from _stage1_common import (
    DATA_PROCESSED,
    DATA_RAW,
    STAGE_REPORT_DIR,
    relative,
    setup_main_logger,
    write_parquet_atomic,
    write_text_atomic,
)


SCRIPT_NAME = Path(__file__).stem
INDEX_PATH = DATA_PROCESSED / "index" / "ecg_metadata.parquet"
MEASUREMENTS_PATH = DATA_RAW / "machine_measurements.csv"
OUTPUT_PATH = DATA_PROCESSED / "index" / "ecg_metadata_with_measurements.parquet"
RUN_DIR = STAGE_REPORT_DIR / "stage_10_run"
VALIDATION_PATH = RUN_DIR / "03_add_measurements_to_index.validation.json"

MEASUREMENT_COLUMNS = [
    "rr_interval",
    "p_onset",
    "p_end",
    "qrs_onset",
    "qrs_end",
    "t_end",
    "p_axis",
    "qrs_axis",
    "t_axis",
]


def _load_measurements() -> tuple[pd.DataFrame, dict[str, Any]]:
    usecols = ["study_id", "subject_id", *MEASUREMENT_COLUMNS]
    meas = pd.read_csv(MEASUREMENTS_PATH, usecols=usecols, low_memory=False)
    for col in ["study_id", "subject_id", *MEASUREMENT_COLUMNS]:
        meas[col] = pd.to_numeric(meas[col], errors="coerce")
    duplicate_rows = int(meas.duplicated("study_id").sum())
    deduped = meas.drop_duplicates("study_id", keep="first").copy()
    deduped = deduped.rename(columns={"subject_id": "measurement_subject_id"})
    stats = {
        "machine_measurements_rows": int(len(meas)),
        "machine_measurements_unique_study_ids": int(deduped["study_id"].nunique(dropna=True)),
        "machine_measurements_duplicate_study_id_rows": duplicate_rows,
    }
    return deduped, stats


def _add_measurements(index: pd.DataFrame, measurements: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    before_ids = set(index["study_id"].astype("int64").tolist())
    merged = index.merge(measurements, on="study_id", how="left", validate="one_to_one")
    subject_mismatch = (
        merged["measurement_subject_id"].notna()
        & (merged["subject_id"].astype("Int64") != merged["measurement_subject_id"].astype("Int64"))
    )
    merged = merged.drop(columns=["measurement_subject_id"])
    for col in MEASUREMENT_COLUMNS:
        merged[f"{col}_missing"] = merged[col].isna()
    after_ids = set(merged["study_id"].astype("int64").tolist())
    missing_ids = sorted(before_ids - after_ids)
    extra_ids = sorted(after_ids - before_ids)
    missing_counts = {col: int(merged[col].isna().sum()) for col in MEASUREMENT_COLUMNS}
    zero_counts = {col: int((merged[col] == 0).fillna(False).sum()) for col in MEASUREMENT_COLUMNS}
    zero_with_missing_flag = {
        col: int(((merged[col] == 0).fillna(False) & merged[f"{col}_missing"]).sum())
        for col in MEASUREMENT_COLUMNS
    }
    nonzero_missing_flags = {
        col: int((merged[col].notna() & merged[f"{col}_missing"]).sum())
        for col in MEASUREMENT_COLUMNS
    }
    validation = {
        "ecg_metadata_rows": int(len(index)),
        "ecg_metadata_with_measurements_rows": int(len(merged)),
        "duplicate_study_id_count": int(merged.duplicated("study_id").sum()),
        "missing_study_id_count": len(missing_ids),
        "extra_study_id_count": len(extra_ids),
        "subject_id_mismatch_count": int(subject_mismatch.sum()),
        "added_measurement_columns": MEASUREMENT_COLUMNS,
        "added_missing_flag_columns": [f"{col}_missing" for col in MEASUREMENT_COLUMNS],
        "null_counts_per_measurement": missing_counts,
        "zero_counts_per_measurement": zero_counts,
        "zero_rows_with_missing_flag_true": zero_with_missing_flag,
        "non_null_rows_with_missing_flag_true": nonzero_missing_flags,
        "zeros_and_missing_values_distinguishable": all(v == 0 for v in zero_with_missing_flag.values())
        and all(v == 0 for v in nonzero_missing_flags.values()),
        "sample_missing_ids": missing_ids[:10],
        "sample_extra_ids": extra_ids[:10],
    }
    return merged, validation


def main() -> None:
    logger = setup_main_logger(SCRIPT_NAME)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"missing required index: {INDEX_PATH}")
    if not MEASUREMENTS_PATH.exists():
        raise FileNotFoundError(f"missing required machine measurements CSV: {MEASUREMENTS_PATH}")

    logger.info("loading ECG metadata index from %s", INDEX_PATH)
    index = pd.read_parquet(INDEX_PATH)
    logger.info("loading machine measurements from %s", MEASUREMENTS_PATH)
    measurements, measurement_stats = _load_measurements()
    logger.info("merging raw measurement columns")
    enriched, validation = _add_measurements(index, measurements)
    validation.update(measurement_stats)
    validation["output_path"] = relative(OUTPUT_PATH)

    logger.info("writing %s rows to %s", len(enriched), OUTPUT_PATH)
    write_parquet_atomic(enriched, OUTPUT_PATH, "ecg_metadata_with_measurements")
    write_text_atomic(json.dumps(validation, indent=2, sort_keys=True) + "\n", VALIDATION_PATH)
    sys.stdout.write(json.dumps(validation, indent=2, sort_keys=True) + "\n")

    if validation["ecg_metadata_rows"] != validation["ecg_metadata_with_measurements_rows"]:
        raise SystemExit("row-count mismatch after measurement merge")
    if validation["duplicate_study_id_count"] != 0:
        raise SystemExit("duplicate study_id values after measurement merge")
    if validation["missing_study_id_count"] or validation["extra_study_id_count"]:
        raise SystemExit("study_id set changed after measurement merge")
    if validation["subject_id_mismatch_count"] != 0:
        raise SystemExit("subject_id mismatch between index and machine measurements")
    if not validation["zeros_and_missing_values_distinguishable"]:
        raise SystemExit("missing flags do not distinguish zero from missing")


if __name__ == "__main__":
    main()
