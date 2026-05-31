#!/usr/bin/env python3
"""Stage 1 script 43: persist all candidates and select final linkage tier."""

import time
import warnings
from pathlib import Path

import pandas as pd

from _stage1_common import DATA_PROCESSED, DATA_RAW, EHR_CACHE, LINKAGE_DIR, setup_main_logger, write_parquet_atomic

SCRIPT_NAME = Path(__file__).stem


def load_ecg_universe() -> pd.DataFrame:
    index = pd.read_parquet(DATA_PROCESSED / "index" / "ecg_metadata.parquet", columns=["study_id", "subject_id"])
    times = pd.read_csv(DATA_RAW / "record_list.csv", usecols=["study_id", "ecg_time"])
    ecg = index.merge(times, on="study_id", how="left", validate="one_to_one")
    ecg["ecg_time"] = pd.to_datetime(ecg["ecg_time"], errors="coerce")
    return ecg


def read_candidates() -> pd.DataFrame:
    frames = []
    for name in (
        "exact_hosp_candidates.parquet",
        "exact_ed_candidates.parquet",
        "tolerance_hosp_candidates.parquet",
        "tolerance_ed_candidates.parquet",
    ):
        path = LINKAGE_DIR / name
        if path.exists():
            frames.append(pd.read_parquet(path))
    if not frames:
        return pd.DataFrame()
    candidates = pd.concat(frames, ignore_index=True)
    candidates["hadm_id"] = candidates["hadm_id"].astype("Int64")
    candidates["stay_id"] = candidates["stay_id"].astype("Int64")
    candidates["tolerance_window_hours"] = candidates["tolerance_window_hours"].astype("Int64")
    candidates = candidates.drop_duplicates(
        subset=["study_id", "source", "link_type", "hadm_id", "stay_id", "tolerance_window_hours"]
    )
    return candidates


def add_candidate_tiers(candidates: pd.DataFrame) -> pd.DataFrame:
    out = candidates.copy()
    out["link_tier"] = "L1"
    out.loc[out["link_type"] == "exact", "link_tier"] = "L3"
    out.loc[(out["link_type"] == "tolerance") & (out["offset_minutes"].abs() <= 1440), "link_tier"] = "L2"
    out["link_type_priority"] = out["link_type"].map({"exact": 0, "tolerance": 1}).fillna(9).astype(int)
    out["id_priority"] = out["hadm_id"].fillna(out["stay_id"]).fillna(9_999_999_999).astype("int64")
    out["tier_priority"] = out["link_tier"].map({"L3": 0, "L2": 1, "L1": 2}).astype(int)
    out["conditional_hosp_priority"] = (
        (out["source"] == "hosp") & out["hadm_id"].notna() & out["stay_id"].notna()
    ).map({True: 0, False: 1}).astype(int)
    out["source_stable_priority"] = out["source"].map({"hosp": 0, "ed": 1}).fillna(9).astype(int)
    return out


def select_final(candidates: pd.DataFrame, ecg: pd.DataFrame) -> pd.DataFrame:
    ranked = add_candidate_tiers(candidates)
    ranked = ranked.sort_values(
        [
            "study_id",
            "abs_tie_minutes",
            "link_type_priority",
            "id_priority",
            "conditional_hosp_priority",
            "source_stable_priority",
        ],
        ascending=[True, True, True, True, True, True],
    )
    selected = ranked.drop_duplicates(subset=["study_id"], keep="first").copy()
    final_cols = [
        "study_id",
        "subject_id",
        "ecg_time",
        "link_tier",
        "source",
        "link_type",
        "hadm_id",
        "stay_id",
        "interval_start",
        "interval_end",
        "offset_minutes",
        "midpoint_offset_minutes",
        "abs_tie_minutes",
        "tolerance_window_hours",
    ]
    selected = selected[final_cols]

    ehr_subjects = set(pd.read_parquet(EHR_CACHE / "admissions.parquet", columns=["subject_id"])["subject_id"].unique())
    ehr_subjects.update(pd.read_parquet(EHR_CACHE / "edstays.parquet", columns=["subject_id"])["subject_id"].unique())
    selected_ids = set(selected["study_id"].unique())
    l1 = ecg[(ecg["subject_id"].isin(ehr_subjects)) & (~ecg["study_id"].isin(selected_ids))].copy()
    if not l1.empty:
        l1["link_tier"] = "L1"
        l1["source"] = pd.NA
        l1["link_type"] = "same_subject_no_temporal_match"
        l1["hadm_id"] = pd.Series([pd.NA] * len(l1), dtype="Int64")
        l1["stay_id"] = pd.Series([pd.NA] * len(l1), dtype="Int64")
        l1["interval_start"] = pd.NaT
        l1["interval_end"] = pd.NaT
        l1["offset_minutes"] = pd.NA
        l1["midpoint_offset_minutes"] = pd.NA
        l1["abs_tie_minutes"] = pd.NA
        l1["tolerance_window_hours"] = pd.Series([pd.NA] * len(l1), dtype="Int64")
        l1 = l1[final_cols]
        selected = pd.concat([selected, l1], ignore_index=True)
    selected["hadm_id"] = selected["hadm_id"].astype("Int64")
    selected["stay_id"] = selected["stay_id"].astype("Int64")
    selected["tolerance_window_hours"] = selected["tolerance_window_hours"].astype("Int64")
    return selected.sort_values("study_id").reset_index(drop=True)


def main() -> None:
    warnings.filterwarnings(
        "ignore",
        category=FutureWarning,
        message="The behavior of DataFrame concatenation with empty or all-NA entries is deprecated.*",
    )
    t0 = time.time()
    log = setup_main_logger(SCRIPT_NAME)
    log.info("starting %s", SCRIPT_NAME)
    ecg = load_ecg_universe()
    candidates = read_candidates()
    if candidates.empty:
        raise ValueError("no exact or tolerance candidates found")
    write_parquet_atomic(candidates, LINKAGE_DIR / "candidate_links.parquet", "linkage_candidate_links")
    final = select_final(candidates, ecg)
    write_parquet_atomic(final, LINKAGE_DIR / "linkage_final.parquet", "linkage_final")
    distribution = final["link_tier"].value_counts().reindex(["L3", "L2", "L1"], fill_value=0)
    for tier, count in distribution.items():
        log.info("linkage_tier=%s count=%d pct_total=%.3f", tier, int(count), count / len(ecg))
    l0_count = len(ecg) - len(final)
    log.info("linkage_tier=L0 count=%d pct_total=%.3f", l0_count, l0_count / len(ecg))
    log.info(
        "done %s elapsed_seconds=%.1f candidate_rows=%d final_rows=%d",
        SCRIPT_NAME,
        time.time() - t0,
        len(candidates),
        len(final),
    )


if __name__ == "__main__":
    main()
