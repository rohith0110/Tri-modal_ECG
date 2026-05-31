#!/usr/bin/env python3
"""
01_build_master_index.py — Stage 0, Script 3
==============================================
Build the master ECG metadata parquet from the three raw ECG CSVs.
Output: data/processed/index/ecg_metadata.parquet

Columns added (per §9.3 Stage 0 and §4.2 line 541):
  - report_lines   : list<string>   (the 18 report_0..report_17 lines)
  - T_machine       : string         (concatenated report text)
  - T_cardio        : nullable string (note_id from waveform_note_links.csv, §12 res. 4)
  - has_machine_measurements : bool
  - has_machine_report_text  : bool
  - machine_hr_bpm   : float64 nullable (60000 / rr_interval)
  - machine_qrs_ms   : float64 nullable (qrs_end - qrs_onset)
  - machine_qtc_ms   : float64 nullable (Bazett: (t_end - qrs_onset) / sqrt(rr/1000))
  - cart_id           : int64 nullable
  - filtering         : string nullable
  - bandwidth         : string nullable

No imputation. Sequential script. Logging per §8.13 (sequential scripts).

Run from: scripts/phase1_dataset_generation/
    cd D:\\Coding\\MU\\Tri-Modal_ECG\\scripts\\phase1_dataset_generation
    ..\\..\\ecg_env\\Scripts\\python.exe 01_build_master_index.py
"""

import logging
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import psutil
import pyarrow as pa
import pyarrow.parquet as pq

# ---------------------------------------------------------------------------
# Paths — all relative to PROJECT_ROOT per §2.4
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "index"
OUTPUT_FILE = OUTPUT_DIR / "ecg_metadata.parquet"

RECORD_LIST = DATA_RAW / "record_list.csv"
MACHINE_MEAS = DATA_RAW / "machine_measurements.csv"
WAVEFORM_NOTES = DATA_RAW / "waveform_note_links.csv"

# ---------------------------------------------------------------------------
# Logging — sequential script per §8.13 (sequential scripts)
# ---------------------------------------------------------------------------
LOG_DIR = SCRIPT_DIR / "logs" / Path(__file__).stem
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("main")
logger.setLevel(logging.INFO)
fh = logging.FileHandler(LOG_DIR / "main.log", mode="w", encoding="utf-8")
sh = logging.StreamHandler(sys.stderr)
fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
fh.setFormatter(fmt)
sh.setFormatter(fmt)
logger.addHandler(fh)
logger.addHandler(sh)

# ---------------------------------------------------------------------------
# Resource limits per §6
# ---------------------------------------------------------------------------
MAX_RAM_GB = psutil.virtual_memory().total / 1024**3 - 8
process = psutil.Process(os.getpid())

REPORT_COLS = [f"report_{i}" for i in range(18)]


def _script_commit_hash() -> str:
    """Return the short git commit hash for the §2.2 stamp.

    Falls back to the script filename when the repo has no commits yet
    or git is unavailable, so the stamp is never empty.
    """
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        if out:
            return out
    except Exception:
        pass
    return f"uncommitted:{Path(__file__).name}"


def check_ram(label: str = ""):
    """Halt if process RSS exceeds the computed ceiling."""
    rss_gb = process.memory_info().rss / (1024**3)
    if rss_gb > MAX_RAM_GB:
        raise MemoryError(
            f"Process RSS {rss_gb:.2f} GB exceeds ceiling "
            f"{MAX_RAM_GB:.1f} GB [{label}]"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    logger.info("=" * 60)
    logger.info("01_build_master_index.py — Stage 0, Script 3")
    logger.info("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Load record_list.csv (800 K rows)
    # ------------------------------------------------------------------
    logger.info("Loading record_list.csv ...")
    records = pd.read_csv(
        RECORD_LIST,
        usecols=["study_id", "subject_id", "path"],
    )
    n_records = len(records)
    logger.info(f"  record_list rows: {n_records:,}")
    check_ram("after record_list")

    # ------------------------------------------------------------------
    # 2. Load machine_measurements.csv (800 K rows)
    # ------------------------------------------------------------------
    logger.info("Loading machine_measurements.csv ...")
    mm_cols = (
        ["study_id", "cart_id", "bandwidth", "filtering",
         "rr_interval", "qrs_onset", "qrs_end", "t_end"]
        + REPORT_COLS
    )
    mm = pd.read_csv(MACHINE_MEAS, usecols=mm_cols, low_memory=False)
    logger.info(f"  machine_measurements rows: {len(mm):,}")
    check_ram("after machine_measurements")

    # ------------------------------------------------------------------
    # 3. Build report_lines list column and T_machine
    # ------------------------------------------------------------------
    logger.info("Building report_lines + T_machine ...")

    # report_lines: list of non-null report strings
    def _make_report_lines(row):
        return [str(row[c]) for c in REPORT_COLS if pd.notna(row[c]) and str(row[c]).strip()]

    mm["report_lines"] = mm[REPORT_COLS].apply(_make_report_lines, axis=1)

    # T_machine: concatenated report text (all 18 fields)
    mm["T_machine"] = (
        mm[REPORT_COLS]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    # has_machine_report_text: True if T_machine is non-empty
    mm["has_machine_report_text"] = mm["T_machine"].str.len() > 0

    # Drop individual report columns — no longer needed
    mm.drop(columns=REPORT_COLS, inplace=True)
    check_ram("after report_lines")

    # ------------------------------------------------------------------
    # 4. Derived machine measurement fields
    # ------------------------------------------------------------------
    logger.info("Deriving machine measurement fields ...")

    # has_machine_measurements: True if rr_interval is present (key field)
    mm["has_machine_measurements"] = mm["rr_interval"].notna()

    # machine_hr_bpm = 60000 / rr_interval
    mm["machine_hr_bpm"] = np.where(
        mm["rr_interval"].notna() & (mm["rr_interval"] > 0),
        60000.0 / mm["rr_interval"],
        np.nan,
    )

    # machine_qrs_ms = qrs_end - qrs_onset
    mm["machine_qrs_ms"] = np.where(
        mm["qrs_end"].notna() & mm["qrs_onset"].notna(),
        mm["qrs_end"] - mm["qrs_onset"],
        np.nan,
    )

    # machine_qtc_ms = Bazett's: (t_end - qrs_onset) / sqrt(rr_interval / 1000)
    qt_interval = mm["t_end"] - mm["qrs_onset"]
    rr_sec = mm["rr_interval"] / 1000.0
    mm["machine_qtc_ms"] = np.where(
        qt_interval.notna() & rr_sec.notna() & (rr_sec > 0),
        qt_interval / np.sqrt(rr_sec),
        np.nan,
    )

    # Drop raw interval columns — now captured in derived fields
    mm.drop(columns=["rr_interval", "qrs_onset", "qrs_end", "t_end"], inplace=True)
    check_ram("after derived fields")

    # ------------------------------------------------------------------
    # 5. Load waveform_note_links.csv for T_cardio (§12 res. 4)
    # ------------------------------------------------------------------
    logger.info("Loading waveform_note_links.csv for T_cardio ...")
    wn = pd.read_csv(WAVEFORM_NOTES, usecols=["study_id", "note_id"])
    logger.info(f"  waveform_note_links rows: {len(wn):,}")

    # Deduplicate to one note per study (take the first if multiple)
    wn = wn.drop_duplicates(subset="study_id", keep="first")

    # T_cardio is nullable string — the note_id identifies the cardiologist note
    wn = wn.rename(columns={"note_id": "T_cardio"})
    wn["T_cardio"] = wn["T_cardio"].astype(str)
    check_ram("after waveform_note_links")

    # ------------------------------------------------------------------
    # 6. Merge: records <- machine_measurements <- waveform_note_links
    # ------------------------------------------------------------------
    logger.info("Merging record_list + machine_measurements ...")
    df = records.merge(mm, on="study_id", how="left")
    del mm
    logger.info(f"  After merge with mm: {len(df):,} rows")
    check_ram("after merge mm")

    assert len(df) == n_records, (
        f"Merge changed row count: {len(df)} vs {n_records}"
    )

    logger.info("Merging with waveform_note_links (T_cardio) ...")
    df = df.merge(wn, on="study_id", how="left")
    del wn
    logger.info(f"  After merge with wn: {len(df):,} rows")
    check_ram("after merge wn")

    assert len(df) == n_records, (
        f"Merge changed row count: {len(df)} vs {n_records}"
    )

    # Fill missing boolean flags
    df["has_machine_measurements"] = df["has_machine_measurements"].fillna(False)
    df["has_machine_report_text"] = df["has_machine_report_text"].fillna(False)

    # Ensure T_cardio is nullable string (pd.StringDtype for Arrow)
    df["T_cardio"] = df["T_cardio"].astype(pd.StringDtype())

    # ------------------------------------------------------------------
    # 7. Write parquet atomically per §7.5
    # ------------------------------------------------------------------
    logger.info(f"Writing {OUTPUT_FILE} ...")

    # Convert to Arrow table with proper types
    table = pa.Table.from_pandas(df, preserve_index=False)

    # Stamp metadata per §2.2
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = {
        b"dataset_version": b"v2.0.0",
        b"created_at_iso": now_iso.encode(),
        b"modality_kind": b"ecg_metadata_index",
        b"n_rows": str(len(df)).encode(),
        b"script_commit_hash": _script_commit_hash().encode(),
    }
    existing_meta = table.schema.metadata or {}
    existing_meta.update(meta)
    table = table.replace_schema_metadata(existing_meta)

    tmp_path = OUTPUT_FILE.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp_path, compression="snappy")
    os.replace(tmp_path, OUTPUT_FILE)

    file_size_mb = OUTPUT_FILE.stat().st_size / (1024 * 1024)
    logger.info(f"  Written: {len(df):,} rows, {file_size_mb:.1f} MB")
    del table

    # ------------------------------------------------------------------
    # 8. Validation per §9.3 Stage 0
    # ------------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("VALIDATION")
    logger.info("=" * 60)

    # V1: Row count == record_list rows ± 0
    assert len(df) == n_records, (
        f"FAIL: ecg_metadata rows ({len(df)}) != record_list rows ({n_records})"
    )
    logger.info(f"  V1 PASS: ecg_metadata rows ({len(df):,}) == record_list rows ({n_records:,})")

    # V2: 50 random rows printed for manual sanity check
    logger.info("  V2: 50 random rows for manual inspection:")
    sample = df.sample(n=50, random_state=42)
    display_cols = [
        "study_id", "subject_id", "path",
        "T_machine", "T_cardio",
        "has_machine_measurements", "has_machine_report_text",
        "machine_hr_bpm", "machine_qrs_ms", "machine_qtc_ms",
        "cart_id", "filtering", "bandwidth",
    ]
    # Print to both log and stderr
    for _, row in sample.iterrows():
        parts = []
        for c in display_cols:
            val = row.get(c, "N/A")
            if c == "T_machine" and isinstance(val, str) and len(val) > 60:
                val = val[:60] + "..."
            parts.append(f"{c}={val}")
        line = " | ".join(parts)
        logger.info(f"    {line}")

    # V3: T_cardio column present and dtype is nullable string
    assert "T_cardio" in df.columns, "FAIL: T_cardio column missing"
    assert df["T_cardio"].dtype == pd.StringDtype(), (
        f"FAIL: T_cardio dtype is {df['T_cardio'].dtype}, expected StringDtype"
    )
    n_t_cardio = df["T_cardio"].notna().sum()
    logger.info(
        f"  V3 PASS: T_cardio present, dtype={df['T_cardio'].dtype}, "
        f"non-null={n_t_cardio:,} / {len(df):,} ({n_t_cardio/len(df)*100:.1f}%)"
    )

    # Additional stats
    n_has_mm = df["has_machine_measurements"].sum()
    n_has_report = df["has_machine_report_text"].sum()
    logger.info(f"  Stats: has_machine_measurements={n_has_mm:,}, has_machine_report_text={n_has_report:,}")
    logger.info(f"  Stats: machine_hr_bpm non-null={df['machine_hr_bpm'].notna().sum():,}")
    logger.info(f"  Stats: machine_qrs_ms non-null={df['machine_qrs_ms'].notna().sum():,}")
    logger.info(f"  Stats: machine_qtc_ms non-null={df['machine_qtc_ms'].notna().sum():,}")

    elapsed = time.time() - t0
    logger.info(f"Elapsed: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    logger.info("=" * 60)
    logger.info("01_build_master_index.py COMPLETE")
    logger.info("=" * 60)

    # Print summary to stdout
    print(f"\n{'=' * 60}")
    print(f"MASTER INDEX: COMPLETE")
    print(f"{'=' * 60}")
    print(f"Rows: {len(df):,} (must equal record_list: {n_records:,})")
    print(f"File: {OUTPUT_FILE} ({file_size_mb:.1f} MB)")
    print(f"T_cardio non-null: {n_t_cardio:,} / {len(df):,}")
    print(f"has_machine_measurements: {n_has_mm:,}")
    print(f"has_machine_report_text: {n_has_report:,}")
    print(f"Elapsed: {elapsed:.1f}s ({elapsed/60:.1f} min)")


if __name__ == "__main__":
    main()