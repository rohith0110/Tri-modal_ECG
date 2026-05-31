#!/usr/bin/env python3
"""Stage 1 script 41: exact temporal ECG-to-EHR overlap linkage."""

import time
from pathlib import Path

import numpy as np
import pandas as pd

from _stage1_common import EHR_CACHE, LINKAGE_DIR, DATA_PROCESSED, DATA_RAW, setup_main_logger, write_parquet_atomic

SCRIPT_NAME = Path(__file__).stem


def load_ecg_universe() -> pd.DataFrame:
    index = pd.read_parquet(DATA_PROCESSED / "index" / "ecg_metadata.parquet", columns=["study_id", "subject_id"])
    times = pd.read_csv(DATA_RAW / "record_list.csv", usecols=["study_id", "ecg_time"])
    df = index.merge(times, on="study_id", how="left", validate="one_to_one")
    df["ecg_time"] = pd.to_datetime(df["ecg_time"], errors="coerce")
    return df


def exact_candidates(ecg: pd.DataFrame, intervals: pd.DataFrame, source: str) -> pd.DataFrame:
    joined = ecg.merge(intervals, on="subject_id", how="inner")
    mask = (joined["ecg_time"] >= joined["interval_start"]) & (joined["ecg_time"] <= joined["interval_end"])
    out = joined.loc[mask].copy()
    if out.empty:
        return out
    out["midpoint_time"] = out["interval_start"] + (out["interval_end"] - out["interval_start"]) / 2
    out["offset_minutes"] = 0.0
    out["midpoint_offset_minutes"] = (out["ecg_time"] - out["midpoint_time"]).dt.total_seconds() / 60.0
    out["abs_tie_minutes"] = out["midpoint_offset_minutes"].abs()
    out["source"] = source
    out["link_type"] = "exact"
    out["tolerance_window_hours"] = pd.Series([pd.NA] * len(out), dtype="Int64")
    keep = [
        "study_id",
        "subject_id",
        "ecg_time",
        "source",
        "link_type",
        "hadm_id",
        "stay_id",
        "interval_start",
        "interval_end",
        "midpoint_time",
        "offset_minutes",
        "midpoint_offset_minutes",
        "abs_tie_minutes",
        "tolerance_window_hours",
    ]
    for col in keep:
        if col not in out.columns:
            out[col] = pd.NA
    return out[keep].sort_values(["study_id", "source", "hadm_id", "stay_id"]).reset_index(drop=True)


def main() -> None:
    t0 = time.time()
    log = setup_main_logger(SCRIPT_NAME)
    LINKAGE_DIR.mkdir(parents=True, exist_ok=True)
    log.info("starting %s", SCRIPT_NAME)
    ecg = load_ecg_universe()
    if ecg["ecg_time"].isna().any():
        missing = int(ecg["ecg_time"].isna().sum())
        raise ValueError(f"{missing} ECG rows are missing ecg_time")
    log.info("loaded ecg universe rows=%d subjects=%d", len(ecg), ecg["subject_id"].nunique())

    admissions = pd.read_parquet(EHR_CACHE / "admissions.parquet")
    admissions = admissions.rename(columns={"admittime": "interval_start", "dischtime": "interval_end"})
    admissions["stay_id"] = pd.Series([pd.NA] * len(admissions), dtype="Int64")
    admissions["hadm_id"] = admissions["hadm_id"].astype("Int64")
    admissions = admissions[["subject_id", "hadm_id", "stay_id", "interval_start", "interval_end"]].dropna(
        subset=["interval_start", "interval_end"]
    )
    hosp = exact_candidates(ecg, admissions, "hosp")
    write_parquet_atomic(hosp, LINKAGE_DIR / "exact_hosp_candidates.parquet", "linkage_exact_hosp_candidates")
    log.info("wrote exact_hosp_candidates rows=%d linked_studies=%d", len(hosp), hosp["study_id"].nunique())

    ed = pd.read_parquet(EHR_CACHE / "edstays.parquet")
    ed = ed.rename(columns={"intime": "interval_start", "outtime": "interval_end"})
    ed["hadm_id"] = ed["hadm_id"].astype("Int64")
    ed["stay_id"] = ed["stay_id"].astype("Int64")
    ed = ed[["subject_id", "hadm_id", "stay_id", "interval_start", "interval_end"]].dropna(
        subset=["interval_start", "interval_end"]
    )
    ed_out = exact_candidates(ecg, ed, "ed")
    write_parquet_atomic(ed_out, LINKAGE_DIR / "exact_ed_candidates.parquet", "linkage_exact_ed_candidates")
    log.info("wrote exact_ed_candidates rows=%d linked_studies=%d", len(ed_out), ed_out["study_id"].nunique())

    log.info(
        "done %s elapsed_seconds=%.1f exact_any_studies=%d",
        SCRIPT_NAME,
        time.time() - t0,
        len(set(hosp["study_id"]) | set(ed_out["study_id"])),
    )


if __name__ == "__main__":
    main()
