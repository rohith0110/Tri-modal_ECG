#!/usr/bin/env python3
"""Stage 1 script 42: nearest tolerance-window EHR linkage."""

import time
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from _stage1_common import DATA_PROCESSED, DATA_RAW, EHR_CACHE, LINKAGE_DIR, setup_main_logger, write_parquet_atomic

SCRIPT_NAME = Path(__file__).stem
WINDOWS = [(6, 360), (12, 720), (24, 1440), (168, 10080)]
MAX_TOLERANCE_MINUTES = 10_080
MAX_TOLERANCE_NS = MAX_TOLERANCE_MINUTES * 60_000_000_000


def load_ecg_without_exact() -> pd.DataFrame:
    index = pd.read_parquet(DATA_PROCESSED / "index" / "ecg_metadata.parquet", columns=["study_id", "subject_id"])
    times = pd.read_csv(DATA_RAW / "record_list.csv", usecols=["study_id", "ecg_time"])
    ecg = index.merge(times, on="study_id", how="left", validate="one_to_one")
    ecg["ecg_time"] = pd.to_datetime(ecg["ecg_time"], errors="coerce")
    exact_ids: set[int] = set()
    for name in ("exact_hosp_candidates.parquet", "exact_ed_candidates.parquet"):
        path = LINKAGE_DIR / name
        if path.exists():
            exact = pd.read_parquet(path, columns=["study_id"])
            exact_ids.update(int(x) for x in exact["study_id"].unique())
    return ecg[~ecg["study_id"].isin(exact_ids)].reset_index(drop=True)


def window_for_gap(abs_minutes: float) -> int | None:
    for hours, minutes in WINDOWS:
        if abs_minutes <= minutes:
            return hours
    return None


def build_interval_lookup(intervals: pd.DataFrame) -> dict[int, dict[str, np.ndarray]]:
    lookup: dict[int, dict[str, np.ndarray]] = {}
    for subject_id, group in intervals.groupby("subject_id", sort=False):
        g = group.sort_values("interval_start")
        starts = g["interval_start"].astype("int64").to_numpy()
        ends = g["interval_end"].astype("int64").to_numpy()
        lookup[int(subject_id)] = {
            "starts": starts,
            "ends": ends,
            "hadm_id": g["hadm_id"].to_numpy(),
            "stay_id": g["stay_id"].to_numpy(),
            "interval_start": g["interval_start"].to_numpy(),
            "interval_end": g["interval_end"].to_numpy(),
        }
    return lookup


def make_row(ecg_row, interval_data: dict[str, np.ndarray], idx: int, gap_minutes: float, source: str) -> dict | None:
    abs_gap = abs(gap_minutes)
    window = window_for_gap(abs_gap)
    if window is None:
        return None
    interval_start = pd.Timestamp(interval_data["interval_start"][idx])
    interval_end = pd.Timestamp(interval_data["interval_end"][idx])
    midpoint = interval_start + (interval_end - interval_start) / 2
    return {
        "study_id": int(ecg_row.study_id),
        "subject_id": int(ecg_row.subject_id),
        "ecg_time": ecg_row.ecg_time,
        "source": source,
        "link_type": "tolerance",
        "hadm_id": interval_data["hadm_id"][idx],
        "stay_id": interval_data["stay_id"][idx],
        "interval_start": interval_start,
        "interval_end": interval_end,
        "midpoint_time": midpoint,
        "offset_minutes": float(gap_minutes),
        "midpoint_offset_minutes": float((ecg_row.ecg_time - midpoint).total_seconds() / 60.0),
        "abs_tie_minutes": float(abs_gap),
        "tolerance_window_hours": int(window),
    }


def tolerance_candidates(ecg: pd.DataFrame, intervals: pd.DataFrame, source: str, log) -> pd.DataFrame:
    lookup = build_interval_lookup(intervals)
    rows: list[dict] = []
    with logging_redirect_tqdm():
        iterator = tqdm(
            ecg.itertuples(index=False),
            total=len(ecg),
            file=None,
            dynamic_ncols=True,
            mininterval=0.5,
            desc=f"tolerance-{source}",
        )
        for row in iterator:
            subject = int(row.subject_id)
            data = lookup.get(subject)
            if data is None or pd.isna(row.ecg_time):
                continue
            t_ns = int(pd.Timestamp(row.ecg_time).value)
            candidate_indices = np.flatnonzero(
                (data["ends"] >= t_ns - MAX_TOLERANCE_NS)
                & (data["starts"] <= t_ns + MAX_TOLERANCE_NS)
            )
            for idx in candidate_indices:
                if data["starts"][idx] <= t_ns <= data["ends"][idx]:
                    continue
                if t_ns < data["starts"][idx]:
                    gap = (t_ns - data["starts"][idx]) / 60_000_000_000
                else:
                    gap = (t_ns - data["ends"][idx]) / 60_000_000_000
                out = make_row(row, data, idx, gap, source)
                if out is not None:
                    rows.append(out)
    out_df = pd.DataFrame(rows)
    if out_df.empty:
        columns = [
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
        return pd.DataFrame(columns=columns)
    out_df["hadm_id"] = out_df["hadm_id"].astype("Int64")
    out_df["stay_id"] = out_df["stay_id"].astype("Int64")
    out_df["tolerance_window_hours"] = out_df["tolerance_window_hours"].astype("Int64")
    out_df = out_df.sort_values(["study_id", "source", "abs_tie_minutes", "hadm_id", "stay_id"]).reset_index(drop=True)
    log.info("built tolerance source=%s rows=%d linked_studies=%d", source, len(out_df), out_df["study_id"].nunique())
    return out_df


def main() -> None:
    t0 = time.time()
    log = setup_main_logger(SCRIPT_NAME)
    log.info("starting %s", SCRIPT_NAME)
    ecg = load_ecg_without_exact()
    log.info("ECGs without exact overlap rows=%d subjects=%d", len(ecg), ecg["subject_id"].nunique())

    admissions = pd.read_parquet(EHR_CACHE / "admissions.parquet")
    admissions = admissions.rename(columns={"admittime": "interval_start", "dischtime": "interval_end"})
    admissions["stay_id"] = pd.Series([pd.NA] * len(admissions), dtype="Int64")
    admissions["hadm_id"] = admissions["hadm_id"].astype("Int64")
    admissions = admissions[["subject_id", "hadm_id", "stay_id", "interval_start", "interval_end"]].dropna(
        subset=["interval_start", "interval_end"]
    )
    hosp = tolerance_candidates(ecg, admissions, "hosp", log)
    write_parquet_atomic(hosp, LINKAGE_DIR / "tolerance_hosp_candidates.parquet", "linkage_tolerance_hosp_candidates")

    ed = pd.read_parquet(EHR_CACHE / "edstays.parquet")
    ed = ed.rename(columns={"intime": "interval_start", "outtime": "interval_end"})
    ed["hadm_id"] = ed["hadm_id"].astype("Int64")
    ed["stay_id"] = ed["stay_id"].astype("Int64")
    ed = ed[["subject_id", "hadm_id", "stay_id", "interval_start", "interval_end"]].dropna(
        subset=["interval_start", "interval_end"]
    )
    ed_out = tolerance_candidates(ecg, ed, "ed", log)
    write_parquet_atomic(ed_out, LINKAGE_DIR / "tolerance_ed_candidates.parquet", "linkage_tolerance_ed_candidates")

    log.info(
        "done %s elapsed_seconds=%.1f tolerance_any_studies=%d",
        SCRIPT_NAME,
        time.time() - t0,
        len(set(hosp["study_id"]) | set(ed_out["study_id"])),
    )


if __name__ == "__main__":
    main()
