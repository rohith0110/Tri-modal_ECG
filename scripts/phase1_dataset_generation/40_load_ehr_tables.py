#!/usr/bin/env python3
"""
Stage 1 script 40: cache EHR tables as Parquet for linkage joins.

Run from repository root:
    .\\ecg_env\\Scripts\\python.exe scripts\\phase1_dataset_generation\\40_load_ehr_tables.py
"""

import os
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from _stage1_common import (
    DATA_RAW,
    DATASET_VERSIONS,
    EHR_CACHE,
    append_or_replace_yaml_section,
    dataset_version_stamp,
    script_commit_hash,
    setup_main_logger,
    sha256_file,
    utc_now_iso,
    write_parquet_atomic,
)

SCRIPT_NAME = Path(__file__).stem
CHUNK_ROWS = 1_000_000

TABLES = {
    "admissions": {
        "path": DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "admissions.csv.gz",
        "columns": [
            "subject_id",
            "hadm_id",
            "admittime",
            "dischtime",
            "deathtime",
            "hospital_expire_flag",
        ],
        "date_columns": ["admittime", "dischtime", "deathtime"],
    },
    "patients": {
        "path": DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "patients.csv.gz",
        "columns": ["subject_id", "gender", "anchor_age", "anchor_year", "anchor_year_group", "dod"],
        "date_columns": ["dod"],
    },
    "diagnoses_icd": {
        "path": DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "diagnoses_icd.csv.gz",
        "columns": ["subject_id", "hadm_id", "seq_num", "icd_code", "icd_version"],
        "date_columns": [],
    },
    "d_icd_diagnoses": {
        "path": DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "d_icd_diagnoses.csv.gz",
        "columns": ["icd_code", "icd_version", "long_title"],
        "date_columns": [],
    },
    "d_labitems": {
        "path": DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "d_labitems.csv.gz",
        "columns": ["itemid", "label", "fluid", "category"],
        "date_columns": [],
    },
    "edstays": {
        "path": DATA_RAW / "mimic-iv-ed-2.2" / "ed" / "edstays.csv.gz",
        "columns": ["subject_id", "hadm_id", "stay_id", "intime", "outtime", "disposition"],
        "date_columns": ["intime", "outtime"],
    },
    "ed_diagnosis": {
        "path": DATA_RAW / "mimic-iv-ed-2.2" / "ed" / "diagnosis.csv.gz",
        "columns": ["subject_id", "stay_id", "seq_num", "icd_code", "icd_version", "icd_title"],
        "date_columns": [],
    },
    "triage": {
        "path": DATA_RAW / "mimic-iv-ed-2.2" / "ed" / "triage.csv.gz",
        "columns": [
            "subject_id",
            "stay_id",
            "temperature",
            "heartrate",
            "resprate",
            "o2sat",
            "sbp",
            "dbp",
            "pain",
            "acuity",
            "chiefcomplaint",
        ],
        "date_columns": [],
    },
}

LABEVENTS = {
    "path": DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "labevents.csv.gz",
    "columns": ["labevent_id", "subject_id", "hadm_id", "itemid", "charttime", "valuenum", "valueuom"],
    "date_columns": ["charttime"],
}


def normalize_dates(df: pd.DataFrame, date_columns: list[str]) -> pd.DataFrame:
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def cache_small_table(name: str, spec: dict, log) -> tuple[int, str]:
    output_path = EHR_CACHE / f"{name}.parquet"
    log.info("caching table=%s path=%s", name, spec["path"])
    df = pd.read_csv(spec["path"], compression="gzip", usecols=spec["columns"], low_memory=False)
    df = normalize_dates(df, spec["date_columns"])
    if "hadm_id" in df.columns:
        df["hadm_id"] = df["hadm_id"].astype("Int64")
    write_parquet_atomic(df, output_path, f"ehr_cache_{name}")
    checksum = sha256_file(output_path)
    log.info("cached table=%s rows=%d sha256=%s", name, len(df), checksum[:12])
    return len(df), checksum


def cache_labevents(log) -> tuple[int, str]:
    input_path = LABEVENTS["path"]
    output_path = EHR_CACHE / "labevents.parquet"
    tmp_path = output_path.with_suffix(".parquet.tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    row_count = 0
    writer = None
    with DATASET_VERSIONS.open("r", encoding="utf-8") as f:
        expected_rows = int(yaml.safe_load(f)["mimic_iv_hosp"]["table_row_counts"]["labevents"])
    metadata = {
        b"dataset_version": dataset_version_stamp().encode("utf-8"),
        b"created_at_iso": utc_now_iso().encode("utf-8"),
        b"modality_kind": b"ehr_cache_labevents",
        b"n_rows": str(expected_rows).encode("utf-8"),
        b"script_commit_hash": script_commit_hash().encode("utf-8"),
    }
    try:
        reader = pd.read_csv(
            input_path,
            compression="gzip",
            usecols=LABEVENTS["columns"],
            chunksize=CHUNK_ROWS,
            low_memory=False,
        )
        with logging_redirect_tqdm():
            for chunk in tqdm(reader, file=None, dynamic_ncols=True, mininterval=0.5, desc="labevents"):
                chunk = normalize_dates(chunk, LABEVENTS["date_columns"])
                chunk["hadm_id"] = chunk["hadm_id"].astype("Int64")
                table = pa.Table.from_pandas(chunk, preserve_index=False)
                if writer is None:
                    table = table.replace_schema_metadata(metadata)
                    writer = pq.ParquetWriter(tmp_path, table.schema, compression="snappy")
                writer.write_table(table)
                row_count += len(chunk)
                if row_count % 10_000_000 == 0:
                    log.info("labevents cached rows=%d", row_count)
    finally:
        if writer is not None:
            writer.close()
    if row_count != expected_rows:
        raise ValueError(f"labevents row count {row_count} != expected {expected_rows}")
    os.replace(tmp_path, output_path)
    if tmp_path.exists():
        tmp_path.unlink()
    checksum = sha256_file(output_path)
    log.info("cached table=labevents rows=%d sha256=%s", row_count, checksum[:12])
    return row_count, checksum


def update_dataset_versions(row_counts: dict[str, int], checksums: dict[str, str]) -> None:
    lines = [
        "ehr_cache:",
        f'  generated_at: "{utc_now_iso()}"',
        '  source: "Stage 1 40_load_ehr_tables.py"',
        '  source_path: "data/raw/ehr_cache/"',
        "  table_row_counts:",
    ]
    for name, rows in row_counts.items():
        lines.append(f"    {name}: {rows}")
    lines.append("  file_checksums:")
    for name, checksum in checksums.items():
        lines.append(f'    {name}: "{checksum}"')
    append_or_replace_yaml_section("ehr_cache", "\n".join(lines))


def main() -> None:
    t0 = time.time()
    log = setup_main_logger(SCRIPT_NAME)
    EHR_CACHE.mkdir(parents=True, exist_ok=True)
    log.info("starting %s", SCRIPT_NAME)
    row_counts: dict[str, int] = {}
    checksums: dict[str, str] = {}
    for name, spec in TABLES.items():
        rows, checksum = cache_small_table(name, spec, log)
        row_counts[name] = rows
        checksums[name] = checksum
    rows, checksum = cache_labevents(log)
    row_counts["labevents"] = rows
    checksums["labevents"] = checksum
    update_dataset_versions(row_counts, checksums)
    elapsed = time.time() - t0
    log.info("dataset_versions.yaml updated with ehr_cache row counts")
    log.info("done %s elapsed_seconds=%.1f", SCRIPT_NAME, elapsed)


if __name__ == "__main__":
    main()
