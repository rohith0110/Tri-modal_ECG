#!/usr/bin/env python3
"""Stage 10A: build clean ECG metadata indexes from QC parquets.

Run from the scripts directory:
    ..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\04_cleanup_master_index.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from _stage1_common import (
    DATA_PROCESSED,
    STAGE_REPORT_DIR,
    relative,
    setup_main_logger,
    write_parquet_atomic,
    write_text_atomic,
)


SCRIPT_NAME = Path(__file__).stem
INDEX_PATH = DATA_PROCESSED / "index" / "ecg_metadata.parquet"
WITH_MEASUREMENTS_PATH = DATA_PROCESSED / "index" / "ecg_metadata_with_measurements.parquet"
QC_PATH = DATA_PROCESSED / "qc.parquet"
WAVEFORM_QC_PATH = DATA_PROCESSED / "waveform_qc.parquet"
SPLITS_PATH = DATA_PROCESSED / "splits_subject_level.parquet"
LABEL_AVAILABILITY_PATH = DATA_PROCESSED / "linkage" / "label_availability.parquet"
OUTPUT_CLEAN_PATH = DATA_PROCESSED / "index" / "ecg_metadata_clean.parquet"
OUTPUT_CLEAN_WITH_MEASUREMENTS_PATH = DATA_PROCESSED / "index" / "ecg_metadata_clean_with_measurements.parquet"
RUN_DIR = STAGE_REPORT_DIR / "stage_10_run"
VALIDATION_PATH = RUN_DIR / "04_cleanup_master_index.validation.json"

PASS_TRUE_COLUMNS = ["decode_ok", "length_ok", "lead_count_ok", "lead_names_ok"]
PASS_FALSE_COLUMNS = ["nan_inf_flag", "flatline_lead_flag", "extreme_amplitude_flag", "duplicate_waveform_flag"]
TRI_MODAL_COLUMNS = ["waveform_ok", "image_ok", "text_ok"]


def _read_required(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"missing required input: {path}")
    return pd.read_parquet(path, columns=columns)


def _attach_split_and_linkage(index: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    out = index.copy()
    stats: dict[str, Any] = {
        "split_source": None,
        "linkage_tier_source": None,
        "split_null_count": None,
        "link_tier_null_count": None,
    }
    if SPLITS_PATH.exists():
        split_cols = ["subject_id", "split"]
        optional = ["linkage_tier", "hr_bucket", "stratum"]
        split_schema_cols = pd.read_parquet(SPLITS_PATH, columns=["subject_id"]).columns.tolist()
        del split_schema_cols
        splits_all = pd.read_parquet(SPLITS_PATH)
        keep_cols = [c for c in [*split_cols, *optional] if c in splits_all.columns]
        splits = splits_all[keep_cols].drop_duplicates("subject_id", keep="first")
        rename = {}
        if "linkage_tier" in splits.columns and "subject_linkage_tier" not in out.columns:
            rename["linkage_tier"] = "subject_linkage_tier"
        splits = splits.rename(columns=rename)
        out = out.merge(splits, on="subject_id", how="left", validate="many_to_one")
        stats["split_source"] = relative(SPLITS_PATH)
        stats["split_null_count"] = int(out["split"].isna().sum()) if "split" in out.columns else None
        if "subject_linkage_tier" in out.columns:
            stats["linkage_tier_source"] = relative(SPLITS_PATH)
    if LABEL_AVAILABILITY_PATH.exists() and "link_tier" not in out.columns:
        labels = pd.read_parquet(LABEL_AVAILABILITY_PATH, columns=["study_id", "link_tier"])
        labels = labels.drop_duplicates("study_id", keep="first")
        out = out.merge(labels, on="study_id", how="left", validate="one_to_one")
        stats["linkage_tier_source"] = relative(LABEL_AVAILABILITY_PATH)
        stats["link_tier_null_count"] = int(out["link_tier"].isna().sum())
    return out, stats


def _build_filter_frame(index: pd.DataFrame, qc: pd.DataFrame, waveform_qc: pd.DataFrame) -> pd.DataFrame:
    qc = qc.drop_duplicates("study_id", keep="first")
    waveform_qc = waveform_qc.drop_duplicates("study_id", keep="first")
    waveform_cols = ["study_id", "subject_id", *PASS_TRUE_COLUMNS, *PASS_FALSE_COLUMNS]
    waveform_qc = waveform_qc[waveform_cols]
    frame = index[["study_id", "subject_id"]].merge(qc, on="study_id", how="left", validate="one_to_one")
    frame = frame.merge(waveform_qc, on=["study_id", "subject_id"], how="left", validate="one_to_one")
    for col in TRI_MODAL_COLUMNS + PASS_TRUE_COLUMNS + PASS_FALSE_COLUMNS:
        if col not in frame.columns:
            raise ValueError(f"required QC column is missing: {col}")
    frame["exclude_waveform_ok_false"] = ~frame["waveform_ok"].fillna(False)
    frame["exclude_image_ok_false"] = ~frame["image_ok"].fillna(False)
    frame["exclude_text_ok_false"] = ~frame["text_ok"].fillna(False)
    for col in PASS_TRUE_COLUMNS:
        frame[f"exclude_{col}_false"] = ~frame[col].fillna(False)
    for col in PASS_FALSE_COLUMNS:
        frame[f"exclude_{col}_true"] = frame[col].fillna(True)
    reason_cols = [c for c in frame.columns if c.startswith("exclude_")]
    frame["stage10_keep"] = ~frame[reason_cols].any(axis=1)
    frame["stage10_exclusion_reason_count"] = frame[reason_cols].sum(axis=1).astype("int64")
    return frame


def _subject_split_overlap(clean: pd.DataFrame) -> dict[str, Any]:
    if "split" not in clean.columns:
        return {"status": "FAIL", "reason": "split column missing", "overlaps": {}}
    split_sets = {
        split: set(clean.loc[clean["split"] == split, "subject_id"].astype("int64").tolist())
        for split in ["train", "val", "test"]
    }
    overlaps = {
        "train_val": len(split_sets["train"] & split_sets["val"]),
        "train_test": len(split_sets["train"] & split_sets["test"]),
        "val_test": len(split_sets["val"] & split_sets["test"]),
    }
    return {"status": "PASS" if all(v == 0 for v in overlaps.values()) else "FAIL", "overlaps": overlaps}


def _validation(
    index: pd.DataFrame,
    with_measurements: pd.DataFrame,
    qc: pd.DataFrame,
    waveform_qc: pd.DataFrame,
    filter_frame: pd.DataFrame,
    clean: pd.DataFrame,
    clean_with_measurements: pd.DataFrame,
    attach_stats: dict[str, Any],
) -> dict[str, Any]:
    reason_cols = [c for c in filter_frame.columns if c.startswith("exclude_")]
    reason_counts = {col: int(filter_frame[col].sum()) for col in reason_cols}
    combo_counts = (
        filter_frame.loc[filter_frame["stage10_exclusion_reason_count"] > 0, reason_cols]
        .astype("int8")
        .astype(str)
        .agg("".join, axis=1)
        .value_counts()
        .head(12)
        .to_dict()
    )
    missing_flags = [c for c in clean_with_measurements.columns if c.endswith("_missing")]
    validation = {
        "ecg_metadata_rows": int(len(index)),
        "ecg_metadata_with_measurements_rows": int(len(with_measurements)),
        "qc_parquet_rows": int(len(qc)),
        "waveform_qc_parquet_rows": int(len(waveform_qc)),
        "ecg_metadata_clean_rows": int(len(clean)),
        "ecg_metadata_clean_with_measurements_rows": int(len(clean_with_measurements)),
        "exclusion_reason_counts": reason_counts,
        "excluded_by_waveform_ok_false": reason_counts["exclude_waveform_ok_false"],
        "excluded_by_image_ok_false": reason_counts["exclude_image_ok_false"],
        "excluded_by_text_ok_false": reason_counts["exclude_text_ok_false"],
        "excluded_by_waveform_qc_criteria": int(
            filter_frame[[c for c in reason_cols if c not in {
                "exclude_waveform_ok_false",
                "exclude_image_ok_false",
                "exclude_text_ok_false",
            }]].any(axis=1).sum()
        ),
        "overlap_among_exclusion_reasons_count": int((filter_frame["stage10_exclusion_reason_count"] > 1).sum()),
        "top_exclusion_reason_combinations_binary": {str(k): int(v) for k, v in combo_counts.items()},
        "final_retained_percentage": float(100.0 * len(clean) / max(1, len(index))),
        "duplicate_study_ids_clean": int(clean.duplicated("study_id").sum()),
        "duplicate_study_ids_clean_with_measurements": int(clean_with_measurements.duplicated("study_id").sum()),
        "subject_split_overlap": _subject_split_overlap(clean),
        "measurement_missing_flag_columns_preserved": missing_flags,
        "measurement_missing_flag_column_count": len(missing_flags),
        "output_paths": [relative(OUTPUT_CLEAN_PATH), relative(OUTPUT_CLEAN_WITH_MEASUREMENTS_PATH)],
        "index_vs_clean_explanation": (
            "ecg_metadata_clean is the subset of ecg_metadata that passes qc.parquet narrow tri-modal "
            "completeness and waveform_qc.parquet hard waveform-quality criteria. Low SQI tier is retained "
            "as an analysis flag rather than used as a Stage 10A exclusion."
        ),
    }
    validation.update(attach_stats)
    return validation


def main() -> None:
    logger = setup_main_logger(SCRIPT_NAME)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("loading Stage 10 cleanup inputs")
    index = _read_required(INDEX_PATH)
    with_measurements = _read_required(WITH_MEASUREMENTS_PATH)
    qc = _read_required(QC_PATH)
    waveform_qc = _read_required(WAVEFORM_QC_PATH)

    logger.info("attaching subject split and linkage tier columns")
    index, attach_stats = _attach_split_and_linkage(index)
    with_measurements, _ = _attach_split_and_linkage(with_measurements)

    logger.info("building tri-modal and waveform QC filters")
    filter_frame = _build_filter_frame(index, qc, waveform_qc)
    clean_ids = set(filter_frame.loc[filter_frame["stage10_keep"], "study_id"].astype("int64").tolist())
    clean = index.loc[index["study_id"].isin(clean_ids)].copy()
    clean_with_measurements = with_measurements.loc[with_measurements["study_id"].isin(clean_ids)].copy()

    validation = _validation(index, with_measurements, qc, waveform_qc, filter_frame, clean, clean_with_measurements, attach_stats)
    logger.info("writing clean indexes rows=%d", len(clean))
    write_parquet_atomic(clean, OUTPUT_CLEAN_PATH, "ecg_metadata_clean")
    write_parquet_atomic(clean_with_measurements, OUTPUT_CLEAN_WITH_MEASUREMENTS_PATH, "ecg_metadata_clean_with_measurements")
    write_text_atomic(json.dumps(validation, indent=2, sort_keys=True) + "\n", VALIDATION_PATH)
    sys.stdout.write(json.dumps(validation, indent=2, sort_keys=True) + "\n")

    if validation["ecg_metadata_clean_rows"] != validation["ecg_metadata_clean_with_measurements_rows"]:
        raise SystemExit("clean index row counts differ")
    if validation["duplicate_study_ids_clean"] or validation["duplicate_study_ids_clean_with_measurements"]:
        raise SystemExit("clean index contains duplicate study_id values")
    if validation["subject_split_overlap"]["status"] != "PASS":
        raise SystemExit("subject split overlap validation failed")
    if validation["measurement_missing_flag_column_count"] == 0:
        raise SystemExit("measurement missing flags were not preserved")


if __name__ == "__main__":
    main()
