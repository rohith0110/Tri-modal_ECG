#!/usr/bin/env python3
"""Shared helpers for Stage 1 EHR linkage scripts."""

import hashlib
import logging
import logging.handlers
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
EHR_CACHE = DATA_RAW / "ehr_cache"
LINKAGE_DIR = DATA_PROCESSED / "linkage"
CONFIG_DIR = PROJECT_ROOT / "config"
AUDIT_DIR = PROJECT_ROOT / "outputs" / "audit_reports"
STAGE_REPORT_DIR = PROJECT_ROOT / "outputs" / "stage_reports"
DATASET_VERSIONS = CONFIG_DIR / "dataset_versions.yaml"

LOG_FORMATTER = logging.Formatter(
    fmt="%(asctime)s %(levelname)-7s pid=%(process)-6d %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def setup_main_logger(script_name: str) -> logging.Logger:
    log_dir = SCRIPT_DIR / "logs" / script_name
    log_dir.mkdir(parents=True, exist_ok=True)
    for log_name in ("main.log", "all.log"):
        log_path = log_dir / log_name
        if log_path.exists():
            log_path.unlink()
    logger = logging.getLogger("main")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "main.log",
        mode="w",
        maxBytes=50_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    stream_handler = logging.StreamHandler(sys.stderr)
    for handler in (file_handler, stream_handler):
        handler.setFormatter(LOG_FORMATTER)
        logger.addHandler(handler)
    silence_noisy_libs()
    return logger


def silence_noisy_libs() -> None:
    for name in (
        "matplotlib",
        "PIL",
        "PIL.PngImagePlugin",
        "h5py",
        "fontTools",
        "urllib3",
        "neurokit2",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)


def dataset_version_stamp() -> str:
    with DATASET_VERSIONS.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return str(cfg["dataset_version_stamp"])


def script_commit_hash() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.DEVNULL,
        ).decode("utf-8").strip()
        if out:
            return out
    except Exception:
        pass
    return "uncommitted"


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def write_parquet_atomic(df, output_path: Path, modality_kind: str, compression: str = "snappy") -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata.update(
        {
            b"dataset_version": dataset_version_stamp().encode("utf-8"),
            b"created_at_iso": utc_now_iso().encode("utf-8"),
            b"modality_kind": modality_kind.encode("utf-8"),
            b"n_rows": str(len(df)).encode("utf-8"),
            b"script_commit_hash": script_commit_hash().encode("utf-8"),
        }
    )
    table = table.replace_schema_metadata(metadata)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    pq.write_table(table, tmp_path, compression=compression)
    os.replace(tmp_path, output_path)


def write_table_atomic(table: pa.Table, output_path: Path, modality_kind: str, compression: str = "snappy") -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = dict(table.schema.metadata or {})
    metadata.update(
        {
            b"dataset_version": dataset_version_stamp().encode("utf-8"),
            b"created_at_iso": utc_now_iso().encode("utf-8"),
            b"modality_kind": modality_kind.encode("utf-8"),
            b"n_rows": str(table.num_rows).encode("utf-8"),
            b"script_commit_hash": script_commit_hash().encode("utf-8"),
        }
    )
    table = table.replace_schema_metadata(metadata)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    pq.write_table(table, tmp_path, compression=compression)
    os.replace(tmp_path, output_path)


def write_text_atomic(text: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, output_path)


def append_or_replace_yaml_section(section_name: str, section_text: str) -> None:
    text = DATASET_VERSIONS.read_text(encoding="utf-8").rstrip()
    marker = f"\n{section_name}:"
    idx = text.find(marker)
    if idx >= 0:
        text = text[:idx].rstrip()
    new_text = text + "\n\n" + section_text.rstrip() + "\n"
    tmp_path = DATASET_VERSIONS.with_suffix(".yaml.tmp")
    tmp_path.write_text(new_text, encoding="utf-8")
    os.replace(tmp_path, DATASET_VERSIONS)


def relative(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def file_size(path: Path) -> str:
    size = path.stat().st_size
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
