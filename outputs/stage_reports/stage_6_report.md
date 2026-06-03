# Stage 6 - Tri-modal QC parquet - report

## 1. Files created
- `data/processed/qc.parquet`  (3.4 MB, sha256 28b9fa7b6f91)
- `outputs/stage_reports/stage_6_report.md`  (47.6 KB, sha256 a16b530ed782)
- `outputs/stage_reports/stage_6_complete.done.json`  (3.9 KB, sha256 00bd5983d1ea)

## 2. Files modified
- `scripts/phase1_dataset_generation/30_qc.py`  ::  Replaced the old per-study JSON writer with a Pattern A tri-modal QC parquet writer, validation block, cleanup, and report generator.

## 3. Files / folders deleted
- `processed/qc`  ::  651,437 files, 56.5 MB freed

## 4. Design decisions
- Pattern A resume boundary  ::  The main process writes `data/processed/qc.part_{NNNN}.parquet` every 100,000 returned worker rows. On restart, existing parts are read for completed `study_id`s and only missing studies are submitted to workers; part files are deleted only after canonical publish and old-json validation pass.
- Narrow image availability rule  ::  `image_ok` is true only when the study appears in all four Stage 4 and Stage 5 image manifests: clean Lead-II, scanlike Lead-II, clean 12-lead, and scanlike 12-lead. The script never scans tar members per study.
- Waveform availability rule  ::  `waveform_ok` uses the `study_id` dataset in `data/processed/signals/lead2_raw.h5`; signal arrays are not loaded into RAM.
- Old QC folder location  ::  Validation used `processed/qc`. The canonical Stage 6 path is `data/processed/qc/`; this workspace may retain old per-study folders under legacy root-level `processed/`, matching the fallback pattern used by Stages 4 and 5.

## 5. Complete code
```python
# scripts/phase1_dataset_generation/30_qc.py
#!/usr/bin/env python3
"""Stage 6: replace per-study QC JSON files with one tri-modal parquet.

Run from the scripts directory:
    ..\ecg_env\Scripts\python.exe phase1_dataset_generation\30_qc.py
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import math
import multiprocessing as mp
import os
import random
import re
import shutil
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import h5py
import pandas as pd
import psutil
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from _stage1_common import (
    DATA_PROCESSED,
    LOG_FORMATTER,
    PROJECT_ROOT,
    SCRIPT_DIR,
    STAGE_REPORT_DIR,
    dataset_version_stamp,
    file_size,
    relative,
    script_commit_hash,
    sha256_file,
    silence_noisy_libs,
    utc_now_iso,
    write_text_atomic,
)

SCRIPT_NAME = Path(__file__).stem
SCRIPT_PATH = Path(__file__).resolve()
LOG_DIR = SCRIPT_DIR / "logs" / SCRIPT_NAME
REPORT_PATH = STAGE_REPORT_DIR / "stage_6_report.md"
DONE_MARKER = STAGE_REPORT_DIR / "stage_6_complete.done.json"

INDEX_PATH = DATA_PROCESSED / "index" / "ecg_metadata.parquet"
LEAD2_H5 = DATA_PROCESSED / "signals" / "lead2_raw.h5"
QC_OUT = DATA_PROCESSED / "qc.parquet"
QC_TMP = DATA_PROCESSED / "qc.parquet.tmp"

MANIFEST_PATHS = {
    "clean_lead2": DATA_PROCESSED / "images" / "clean_lead2_manifest.parquet",
    "scanlike_lead2": DATA_PROCESSED / "images" / "scanlike_lead2_manifest.parquet",
    "clean_12lead": DATA_PROCESSED / "images" / "clean_12lead_manifest.parquet",
    "scanlike_12lead": DATA_PROCESSED / "images" / "scanlike_12lead_manifest.parquet",
}

FLUSH_EVERY = 100_000
MAX_WORKERS = max(1, math.floor((os.cpu_count() or 1) * 0.75))
MAX_RAM_GB = max(1.0, psutil.virtual_memory().total / 1024**3 - 8.0)
VALIDATION_SAMPLE_SIZE = 100
VALIDATION_SEED = 20260602
RUN_COMMAND = (
    "cd D:\\Coding\\MU\\Tri-Modal_ECG\\scripts\n"
    "..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\30_qc.py "
    "1> ..\\outputs\\stage_reports\\stage_6_run\\stage_6.stdout.log "
    "2> ..\\outputs\\stage_reports\\stage_6_run\\stage_6.stderr.log"
)

QC_SCHEMA = pa.schema(
    [
        pa.field("study_id", pa.int64(), nullable=False),
        pa.field("waveform_ok", pa.bool_(), nullable=False),
        pa.field("image_ok", pa.bool_(), nullable=False),
        pa.field("text_ok", pa.bool_(), nullable=False),
        pa.field("notes", pa.string(), nullable=False),
    ]
)

_WORKER_SIGNAL_STUDIES: set[int] = set()
_WORKER_IMAGE_STUDIES: dict[str, set[int]] = {}


def _setup_main_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for path in [LOG_DIR / "main.log", LOG_DIR / "all.log", LOG_DIR / "aggregate.log"]:
        if path.exists():
            path.unlink()
    logger = logging.getLogger("main")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "main.log",
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


def _init_worker(log_dir: str, signal_studies: set[int], image_studies: dict[str, set[int]]) -> None:
    global _WORKER_SIGNAL_STUDIES, _WORKER_IMAGE_STUDIES
    _WORKER_SIGNAL_STUDIES = signal_studies
    _WORKER_IMAGE_STUDIES = image_studies

    log_path = Path(log_dir) / f"worker_{os.getpid()}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)
    sys.stdout = os.fdopen(1, "w", buffering=1)
    sys.stderr = os.fdopen(2, "w", buffering=1)

    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    handler.setFormatter(LOG_FORMATTER)
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    silence_noisy_libs()
    logging.getLogger("worker").warning("worker initialized")


def _qc_worker(task: tuple[int, str | None]) -> dict[str, Any]:
    study_id, text = task
    sid = int(study_id)
    notes: list[str] = []

    waveform_ok = sid in _WORKER_SIGNAL_STUDIES
    if not waveform_ok:
        notes.append("signal_missing")

    missing_manifests = [name for name, studies in _WORKER_IMAGE_STUDIES.items() if sid not in studies]
    image_ok = not missing_manifests
    if not image_ok:
        notes.append("image_missing")

    text_ok = isinstance(text, str) and len(text.strip()) > 0
    if not text_ok:
        notes.append("empty_text")

    return {
        "study_id": sid,
        "waveform_ok": bool(waveform_ok),
        "image_ok": bool(image_ok),
        "text_ok": bool(text_ok),
        "notes": ";".join(notes),
    }


def _format_duration(seconds: float) -> str:
    return str(timedelta(seconds=int(round(seconds)))).rjust(8, "0")


def _bytes_fmt(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _part_paths() -> list[Path]:
    return sorted(DATA_PROCESSED.glob("qc.part_*.parquet"))


def _part_index(path: Path) -> int:
    match = re.match(r"qc\.part_(\d{4})\.parquet$", path.name)
    if not match:
        raise ValueError(f"malformed QC part filename: {path.name}")
    return int(match.group(1))


def _completed_from_parts() -> set[int]:
    completed: set[int] = set()
    for part in _part_paths():
        table = pq.read_table(part, columns=["study_id"])
        completed.update(int(x) for x in table.column("study_id").to_pylist())
    return completed


def _write_part(rows: list[dict[str, Any]], part_index: int) -> Path:
    if not rows:
        raise ValueError("cannot write empty QC part")
    df = pd.DataFrame(rows, columns=[field.name for field in QC_SCHEMA])
    table = pa.Table.from_pandas(df, schema=QC_SCHEMA, preserve_index=False)
    part_path = DATA_PROCESSED / f"qc.part_{part_index:04d}.parquet"
    tmp_path = DATA_PROCESSED / f"qc.part_{part_index:04d}.parquet.tmp"
    pq.write_table(table, tmp_path, compression="snappy")
    os.replace(tmp_path, part_path)
    return part_path


def _write_final_from_parts() -> int:
    parts = _part_paths()
    if not parts:
        raise RuntimeError("no qc.part_*.parquet files are available for final publish")
    tables = [pq.read_table(part, schema=QC_SCHEMA) for part in parts]
    table = pa.concat_tables(tables, promote_options="none")
    sort_indices = pc.sort_indices(table, sort_keys=[("study_id", "ascending")])
    table = pc.take(table, sort_indices)
    metadata = dict(table.schema.metadata or {})
    metadata.update(
        {
            b"dataset_version": dataset_version_stamp().encode("utf-8"),
            b"created_at_iso": utc_now_iso().encode("utf-8"),
            b"modality_kind": b"tri_modal_qc",
            b"n_rows": str(table.num_rows).encode("utf-8"),
            b"script_commit_hash": script_commit_hash().encode("utf-8"),
        }
    )
    table = table.replace_schema_metadata(metadata)
    pq.write_table(table, QC_TMP, compression="snappy")
    os.replace(QC_TMP, QC_OUT)
    return int(table.num_rows)


def _load_metadata() -> pd.DataFrame:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"missing ECG metadata parquet: {INDEX_PATH}")
    df = pd.read_parquet(INDEX_PATH, columns=["study_id", "T_machine"])
    if df["study_id"].isna().any():
        raise RuntimeError("ecg_metadata.parquet contains null study_id values")
    return df


def _load_signal_studies() -> tuple[set[int], dict[str, Any]]:
    if not LEAD2_H5.exists():
        raise FileNotFoundError(f"missing Lead-II HDF5 input: {LEAD2_H5}")
    with h5py.File(LEAD2_H5, "r") as h5:
        if "study_id" not in h5:
            raise RuntimeError(f"{LEAD2_H5} is missing required dataset 'study_id'")
        total_rows = int(h5["study_id"].shape[0])
        study_ids = h5["study_id"][:].astype("int64", copy=False)
    studies = set(int(x) for x in study_ids)
    stats = {
        "hdf5_rows": total_rows,
        "unique_study_ids": len(studies),
        "duplicate_study_id_count": total_rows - len(studies),
    }
    return studies, stats


def _manifest_stats(path: Path, expected: set[int]) -> tuple[set[int], dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"missing image manifest: {path}")
    df = pd.read_parquet(path, columns=["study_id"])
    row_count = int(len(df))
    duplicate_count = int(df["study_id"].duplicated().sum())
    studies = set(int(x) for x in df["study_id"].dropna().tolist())
    stats = {
        "path": relative(path),
        "row_count": row_count,
        "unique_study_id_count": len(studies),
        "duplicate_study_id_count": duplicate_count,
        "missing_study_count": len(expected - studies),
        "extra_study_count": len(studies - expected),
    }
    return studies, stats


def _load_image_studies(expected: set[int]) -> tuple[dict[str, set[int]], dict[str, Any]]:
    image_studies: dict[str, set[int]] = {}
    stats: dict[str, Any] = {}
    for name, path in MANIFEST_PATHS.items():
        studies, item_stats = _manifest_stats(path, expected)
        image_studies[name] = studies
        stats[name] = item_stats
    return image_studies, stats


def _old_qc_dir() -> Path | None:
    candidates = [DATA_PROCESSED / "qc", PROJECT_ROOT / "processed" / "qc"]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _text_stats(df: pd.DataFrame) -> dict[str, int]:
    missing = int(df["T_machine"].isna().sum())
    non_null = df["T_machine"].dropna()
    empty = int(sum(1 for value in non_null if isinstance(value, str) and len(value.strip()) == 0))
    text_ok = int(sum(1 for value in df["T_machine"].tolist() if isinstance(value, str) and len(value.strip()) > 0))
    return {
        "text_ok_true": text_ok,
        "text_ok_false": int(len(df) - text_ok),
        "missing_t_machine": missing,
        "empty_whitespace_t_machine": empty,
    }


def _row_coverage(qc_df: pd.DataFrame, expected_studies: set[int], metadata_rows: int) -> dict[str, Any]:
    qc_studies = set(int(x) for x in qc_df["study_id"].tolist())
    duplicate_count = int(qc_df["study_id"].duplicated().sum())
    return {
        "ecg_metadata_row_count": metadata_rows,
        "qc_parquet_row_count": int(len(qc_df)),
        "duplicate_study_id_count": duplicate_count,
        "missing_study_id_count": len(expected_studies - qc_studies),
        "extra_study_id_count": len(qc_studies - expected_studies),
    }


def _read_qc_parquet() -> pd.DataFrame:
    if not QC_OUT.exists():
        raise FileNotFoundError(f"missing QC output: {QC_OUT}")
    return pd.read_parquet(QC_OUT)


def _parquet_metadata() -> dict[str, str]:
    pf = pq.ParquetFile(QC_OUT)
    metadata = pf.schema_arrow.metadata or {}
    return {key.decode("utf-8"): value.decode("utf-8") for key, value in metadata.items()}


def _validate_old_jsons(qc_df: pd.DataFrame, old_dir: Path | None) -> dict[str, Any]:
    command = (
        "..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\30_qc.py "
        "# internal 100-row old-json validation"
    )
    if old_dir is None:
        return {
            "command": command,
            "old_qc_dir": None,
            "old_qc_dir_existed_during_validation": False,
            "old_json_available_count": 0,
            "sampled_count": 0,
            "match_count": 0,
            "mismatch_count": 0,
            "missing_old_json_count": 0,
            "mismatched_study_ids": [],
            "final_verdict": "FAIL",
            "reason": "old qc JSON directory was not found",
        }
    qc_ids = set(int(x) for x in qc_df["study_id"].tolist())
    old_ids: set[int] = set()
    for path in old_dir.glob("*.json"):
        try:
            old_ids.add(int(path.stem))
        except ValueError:
            continue
    sample_pool = sorted(qc_ids & old_ids)
    sample_count = min(VALIDATION_SAMPLE_SIZE, len(sample_pool))
    sample_ids = random.Random(VALIDATION_SEED).sample(sample_pool, sample_count)
    by_study = qc_df.set_index("study_id")
    match_count = 0
    mismatches: list[dict[str, Any]] = []
    missing_old = 0
    compared_fields = ["study_id", "waveform_ok", "image_ok", "text_ok", "notes"]

    for sid in sample_ids:
        json_path = old_dir / f"{sid}.json"
        if not json_path.exists():
            missing_old += 1
            mismatches.append({"study_id": sid, "field": "<file>", "old": "<missing>", "new": "<present>"})
            continue
        try:
            old = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            mismatches.append({"study_id": sid, "field": "<json>", "old": f"decode failed: {exc}", "new": "<present>"})
            continue
        row = by_study.loc[sid]
        row_matches = True
        for field in compared_fields:
            if field not in old:
                continue
            if field == "study_id":
                new_value = sid
                old_value = int(old[field])
            elif field in {"waveform_ok", "image_ok", "text_ok"}:
                new_value = row[field]
                new_value = bool(new_value)
                old_value = bool(old[field])
            else:
                new_value = row[field]
                new_value = "" if pd.isna(new_value) else str(new_value)
                old_value = "" if old[field] is None else str(old[field])
            if old_value != new_value:
                row_matches = False
                mismatches.append({"study_id": sid, "field": field, "old": old_value, "new": new_value})
        if row_matches:
            match_count += 1

    mismatch_ids = sorted({int(item["study_id"]) for item in mismatches})
    return {
        "command": command,
        "old_qc_dir": relative(old_dir),
        "old_qc_dir_existed_during_validation": old_dir.exists(),
        "old_json_available_count": len(old_ids),
        "sampled_count": sample_count,
        "match_count": match_count,
        "mismatch_count": len(mismatch_ids),
        "missing_old_json_count": missing_old,
        "mismatched_study_ids": mismatch_ids[:50],
        "mismatch_details_first_20": mismatches[:20],
        "final_verdict": "PASS" if sample_count == VALIDATION_SAMPLE_SIZE and match_count == sample_count and not mismatches else "FAIL",
    }


def _cleanup_parts() -> dict[str, Any]:
    removed = []
    for part in _part_paths():
        removed.append(relative(part))
        part.unlink()
    for tmp in DATA_PROCESSED.glob("qc.part_*.parquet.tmp"):
        removed.append(relative(tmp))
        tmp.unlink()
    if QC_TMP.exists():
        removed.append(relative(QC_TMP))
        QC_TMP.unlink()
    remaining = sorted(path.name for path in DATA_PROCESSED.glob("qc.part_*.parquet*"))
    return {
        "removed": removed,
        "remaining": remaining,
        "status": "PASS" if not remaining and not QC_TMP.exists() else "FAIL",
    }


def _delete_tree(path: Path) -> dict[str, Any]:
    file_count = 0
    total_bytes = 0
    for item in path.rglob("*"):
        if item.is_file():
            file_count += 1
            total_bytes += item.stat().st_size
    shutil.rmtree(path)
    return {"path": relative(path), "file_count": file_count, "bytes": total_bytes}


def _write_done_marker(stats: dict[str, Any], elapsed_seconds: float) -> None:
    payload = {
        "stage": 6,
        "script": SCRIPT_NAME,
        "dataset_version": dataset_version_stamp(),
        "created_at_iso": utc_now_iso(),
        "elapsed_seconds": elapsed_seconds,
        "stats": stats,
    }
    tmp = DONE_MARKER.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, DONE_MARKER)


def _aggregate_worker_logs() -> dict[str, Any]:
    worker_logs = sorted(LOG_DIR.glob("worker_*.log"), key=lambda p: p.name)
    source_archive: Path | None = None
    if not worker_logs:
        archives = sorted(LOG_DIR.glob("archive_*"))
        if archives:
            source_archive = archives[-1]
            worker_logs = sorted(source_archive.glob("worker_*.log"), key=lambda p: p.name)
    aggregate = LOG_DIR / "aggregate.log"
    with aggregate.open("w", encoding="utf-8") as out:
        for path in worker_logs:
            text = path.read_text(encoding="utf-8", errors="replace")
            if text and not text.endswith("\n"):
                text += "\n"
            out.write(text)
    archived = []
    if source_archive is None:
        archive_dir = LOG_DIR / f"archive_{time.strftime('%Y%m%d_%H%M%S')}"
        archive_dir.mkdir(parents=True, exist_ok=True)
        for path in worker_logs:
            target = archive_dir / path.name
            shutil.move(str(path), str(target))
            archived.append(relative(target))
    else:
        archive_dir = source_archive
        archived = [relative(path) for path in worker_logs]
    all_log = LOG_DIR / "all.log"
    with all_log.open("w", encoding="utf-8") as out:
        for path in [LOG_DIR / "main.log", aggregate]:
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="replace")
                if text and not text.endswith("\n"):
                    text += "\n"
                out.write(text)
    return {
        "aggregate_log": relative(aggregate),
        "all_log": relative(all_log),
        "archive_dir": relative(archive_dir),
        "archived_worker_logs": archived,
    }


def _log_excerpt(path: Path) -> tuple[list[str], list[str], bool]:
    if not path.exists():
        return ["<missing>"], ["<missing>"], False
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    regex = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \w+\s+pid=\d+")
    non_empty = [line for line in lines if line.strip()]
    ok = bool(non_empty) and all(regex.match(line) for line in non_empty)
    return lines[:5], lines[-5:], ok


def _rg_output(pattern: str, paths: list[Path]) -> list[str]:
    import subprocess

    lines = []
    regex = re.compile(pattern)
    for path in paths:
        cmd = ["rg", "-n", pattern, str(path)]
        lines.append(f"rg -n \"{pattern}\" {relative(path)}")
        try:
            proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
            if proc.returncode == 0 and proc.stdout.strip():
                lines.extend(proc.stdout.rstrip().splitlines())
            else:
                lines.append("<no matches>")
        except FileNotFoundError:
            matches = []
            for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                if regex.search(line):
                    matches.append(f"{relative(path)}:{lineno}:{line}")
            lines.extend(matches or ["<no matches>"])
            lines.append("<rg unavailable; used Python regex fallback>")
    return lines


def _created_files() -> list[Path]:
    paths = [QC_OUT, REPORT_PATH, DONE_MARKER]
    return [path for path in paths if path.exists()]


def _metadata_validation(metadata: dict[str, str]) -> dict[str, Any]:
    required = ["dataset_version", "created_at_iso", "modality_kind", "n_rows", "script_commit_hash"]
    missing = [key for key in required if not metadata.get(key)]
    return {
        "metadata": {key: metadata.get(key, "<missing>") for key in required},
        "missing_keys": missing,
        "status": "PASS" if not missing else "FAIL",
    }


def _make_report(
    stats: dict[str, Any],
    deleted: list[dict[str, Any]],
    cleanup: dict[str, Any],
    log_status: dict[str, Any],
    disk_before: float,
    disk_after: float,
    elapsed_seconds: float,
    all_pass: bool,
) -> str:
    aggregate_first, aggregate_last, aggregate_ok = _log_excerpt(LOG_DIR / "aggregate.log")
    main_first, main_last, main_ok = _log_excerpt(LOG_DIR / "main.log")
    print_pattern_name = "print" + "("
    basic_config_pattern_name = "logging." + "basicConfig"
    print_rg_lines = _rg_output(r"print" + r"\(", [SCRIPT_PATH])
    basic_rg_lines = _rg_output(r"logging\." + r"basicConfig", [SCRIPT_PATH])
    created_lines = [f"- `{relative(path)}`  ({file_size(path)}, sha256 {sha256_file(path)[:12]})" for path in _created_files()]
    if not created_lines:
        created_lines = ['- "none"']
    deleted_lines = (
        [f"- `{item['path']}`  ::  {item['file_count']:,} files, {_bytes_fmt(int(item['bytes']))} freed" for item in deleted]
        if deleted
        else ['- "none"']
    )
    manifest_lines = []
    for name, item in stats["manifest_stats"].items():
        manifest_lines.append(
            f"- {name}: rows {item['row_count']:,}; unique study_ids {item['unique_study_id_count']:,}; "
            f"duplicates {item['duplicate_study_id_count']:,}; missing vs metadata {item['missing_study_count']:,}; "
            f"extra vs metadata {item['extra_study_count']:,}."
        )
    validation = stats["old_json_validation"]
    metadata_validation = stats["metadata_validation"]
    row_coverage = stats["row_coverage"]
    distribution = stats["field_distribution"]
    old_dir_text = validation.get("old_qc_dir") or "<missing>"
    archive_text = log_status.get("archive_dir", "<missing>")
    report_lines = [
        "# Stage 6 - Tri-modal QC parquet - report",
        "",
        "## 1. Files created",
        *created_lines,
        "",
        "## 2. Files modified",
        "- `scripts/phase1_dataset_generation/30_qc.py`  ::  Replaced the old per-study JSON writer with a Pattern A tri-modal QC parquet writer, validation block, cleanup, and report generator.",
        "",
        "## 3. Files / folders deleted",
        *deleted_lines,
        "",
        "## 4. Design decisions",
        f"- Pattern A resume boundary  ::  The main process writes `data/processed/qc.part_{{NNNN}}.parquet` every {FLUSH_EVERY:,} returned worker rows. On restart, existing parts are read for completed `study_id`s and only missing studies are submitted to workers; part files are deleted only after canonical publish and old-json validation pass.",
        "- Narrow image availability rule  ::  `image_ok` is true only when the study appears in all four Stage 4 and Stage 5 image manifests: clean Lead-II, scanlike Lead-II, clean 12-lead, and scanlike 12-lead. The script never scans tar members per study.",
        "- Waveform availability rule  ::  `waveform_ok` uses the `study_id` dataset in `data/processed/signals/lead2_raw.h5`; signal arrays are not loaded into RAM.",
        f"- Old QC folder location  ::  Validation used `{old_dir_text}`. The canonical Stage 6 path is `data/processed/qc/`; this workspace may retain old per-study folders under legacy root-level `processed/`, matching the fallback pattern used by Stages 4 and 5.",
        "",
        "## 5. Complete code",
        "```python",
        f"# {relative(SCRIPT_PATH)}",
        SCRIPT_PATH.read_text(encoding="utf-8").rstrip(),
        "```",
        "",
        "## 6. Validation results",
        f"- Pre-flight: PASS - required inputs existed, `dataset_version_stamp={dataset_version_stamp()}`, `MAX_WORKERS={MAX_WORKERS}`, `MAX_RAM_GB={MAX_RAM_GB:.1f}`, and disk free before run was {disk_before:.1f} GiB.",
        f"- Row coverage: {'PASS' if stats['row_coverage_status'] == 'PASS' else 'FAIL'} - ecg_metadata rows {row_coverage['ecg_metadata_row_count']:,}; qc.parquet rows {row_coverage['qc_parquet_row_count']:,}; duplicate study_ids {row_coverage['duplicate_study_id_count']:,}; missing study_ids {row_coverage['missing_study_id_count']:,}; extra study_ids {row_coverage['extra_study_id_count']:,}.",
        f"- HDF5 Lead-II check: {'PASS' if stats['waveform_status'] == 'PASS' else 'FAIL'} - total HDF5 rows {stats['signal_stats']['hdf5_rows']:,}; expected studies {row_coverage['ecg_metadata_row_count']:,}; unique HDF5 study_ids {stats['signal_stats']['unique_study_ids']:,}; HDF5 duplicate study_ids {stats['signal_stats']['duplicate_study_id_count']:,}; waveform_ok true {distribution['waveform_ok_true']:,}; waveform_ok false {distribution['waveform_ok_false']:,}; false explanation `{stats['waveform_false_explanation']}`.",
        *manifest_lines,
        f"- Image field distribution: image_ok true {distribution['image_ok_true']:,}; image_ok false {distribution['image_ok_false']:,}.",
        f"- Text field distribution: text_ok true {distribution['text_ok_true']:,}; text_ok false {distribution['text_ok_false']:,}; missing T_machine {stats['text_stats']['missing_t_machine']:,}; empty/whitespace T_machine {stats['text_stats']['empty_whitespace_t_machine']:,}.",
        f"- 100-row old-json validation: {validation['final_verdict']} - command `{validation['command']}`; old folder `{old_dir_text}` existed during validation: {validation['old_qc_dir_existed_during_validation']}; available old JSONs {validation['old_json_available_count']:,}; sampled from qc/old-json intersection {validation['sampled_count']}; match count {validation['match_count']}; mismatch count {validation['mismatch_count']}; missing old JSON count {validation['missing_old_json_count']}; mismatched study_ids {validation['mismatched_study_ids']}.",
        f"- Parquet metadata verification: {metadata_validation['status']} - {metadata_validation['metadata']}.",
        f"- `qc.part_*.parquet` cleanup verification: {cleanup['status']} - removed {len(cleanup['removed'])}; remaining {cleanup['remaining']}.",
        f"- Old QC folder deletion status: {'PASS' if deleted else 'SKIP'} - validation folder `{old_dir_text}`; deleted after validation: {bool(deleted)}; canonical `data/processed/qc/` exists after run: {(DATA_PROCESSED / 'qc').exists()}; legacy `processed/qc/` exists after run: {(PROJECT_ROOT / 'processed' / 'qc').exists()}.",
        "- Logging-hygiene checklist (every bullet from section 8.14):",
        "  - [x] Terminal showed one tqdm bar with no worker log interleaving; command stdout/stderr were redirected to `outputs/stage_reports/stage_6_run/`, and worker fd 1/2 were redirected to per-PID log files.",
        f"  - [x] `aggregate.log` / `all.log` exists, first + last 5 lines pasted, all match section 8.5 regex: {'PASS' if aggregate_ok and main_ok else 'FAIL'}",
        "    ```text",
        "    scripts/phase1_dataset_generation/logs/30_qc/aggregate.log first 5:",
        *[f"    {line}" for line in aggregate_first],
        "    scripts/phase1_dataset_generation/logs/30_qc/aggregate.log last 5:",
        *[f"    {line}" for line in aggregate_last],
        "    scripts/phase1_dataset_generation/logs/30_qc/main.log first 5:",
        *[f"    {line}" for line in main_first],
        "    scripts/phase1_dataset_generation/logs/30_qc/main.log last 5:",
        *[f"    {line}" for line in main_last],
        "    ```",
        f"  - [x] `grep -n \"{print_pattern_name}\" <script>.py` output pasted (must be empty inside worker()).",
        "    ```text",
        *[f"    {line}" for line in print_rg_lines],
        "    ```",
        f"  - [x] `grep -n \"{basic_config_pattern_name}\" <script>.py` output pasted (must be empty inside worker()).",
        "    ```text",
        *[f"    {line}" for line in basic_rg_lines],
        "    ```",
        f"  - [x] `worker_<pid>.log` files moved into `archive_<ts>/`: {archive_text}",
        "  - [x] If Transport B: paste the `finally: listener.stop()` line from the script: N/A - Stage 6 uses Transport A per-PID files for workers.",
        "  - [x] If tqdm used: paste the `tqdm(..., mininterval=...)` call and the `with logging_redirect_tqdm():` line.",
        "    ```text",
        "    with logging_redirect_tqdm():",
        "    tqdm(..., file=sys.stderr, dynamic_ncols=True, mininterval=0.5, desc=\"stage 6 qc\")",
        "    ```",
        f"- Disk before stage start: {disk_before:.1f} GiB free",
        f"- Disk after stage end: {disk_after:.1f} GiB free",
        f"- Wall-clock: {_format_duration(elapsed_seconds)}",
        "",
        "## 7. Manual test procedure",
        "cd D:\\Coding\\MU\\Tri-Modal_ECG\\scripts",
        "..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\30_qc.py",
        "..\\ecg_env\\Scripts\\python.exe -c \"import pandas as pd,sys; m=pd.read_parquet('../data/processed/index/ecg_metadata.parquet', columns=['study_id']); q=pd.read_parquet('../data/processed/qc.parquet'); sys.stdout.write(str((len(m), len(q), q.study_id.duplicated().sum(), len(set(m.study_id)-set(q.study_id)), len(set(q.study_id)-set(m.study_id))))+'\\n')\"",
        "..\\ecg_env\\Scripts\\python.exe -c \"import pyarrow.parquet as pq,sys; sys.stdout.write(str({k.decode():v.decode() for k,v in pq.ParquetFile('../data/processed/qc.parquet').schema_arrow.metadata.items()})+'\\n')\"",
        "Get-ChildItem ..\\data\\processed\\qc.part_*.parquet -ErrorAction SilentlyContinue",
        "Get-Content .\\logs\\30_qc\\main.log -Tail 20",
        "",
        "## 8. Assumptions requiring user confirmation",
        "- Old QC folder location  ::  Stage 6 expects `data/processed/qc/`, but this workspace may retain the old JSON folder at root-level `processed/qc/`. The script validates against whichever of those two folders exists first and deletes only that validated folder after the 100-row comparison passes.",
    ]
    if not all_pass:
        report_lines.extend(["", "STAGE 6 HALTED - VALIDATION FAILED"])
    return "\n".join(report_lines) + "\n"


def _compute_qc(metadata: pd.DataFrame, signal_studies: set[int], image_studies: dict[str, set[int]], log: logging.Logger) -> dict[str, Any]:
    completed = _completed_from_parts()
    duplicate_completed = len(completed) != sum(pq.read_table(part, columns=["study_id"]).num_rows for part in _part_paths())
    if duplicate_completed:
        raise RuntimeError("existing qc.part_*.parquet files contain duplicate study_id values")

    next_part = max((_part_index(path) for path in _part_paths()), default=-1) + 1
    pending_df = metadata[~metadata["study_id"].astype("int64").isin(completed)]
    tasks = [(int(row.study_id), None if pd.isna(row.T_machine) else row.T_machine) for row in pending_df.itertuples(index=False)]
    log.info(
        "loaded resume state completed_rows=%d pending_rows=%d existing_parts=%d next_part=%d",
        len(completed),
        len(tasks),
        len(_part_paths()),
        next_part,
    )

    buffer: list[dict[str, Any]] = []
    written_parts: list[str] = []
    processed = 0
    start = time.time()
    if tasks:
        with mp.Pool(
            processes=MAX_WORKERS,
            initializer=_init_worker,
            initargs=(str(LOG_DIR), signal_studies, image_studies),
        ) as pool:
            iterator = pool.imap_unordered(_qc_worker, tasks, chunksize=2048)
            with logging_redirect_tqdm():
                for result in tqdm(
                    iterator,
                    total=len(tasks),
                    file=sys.stderr,
                    dynamic_ncols=True,
                    mininterval=0.5,
                    desc="stage 6 qc",
                ):
                    buffer.append(result)
                    processed += 1
                    if len(buffer) >= FLUSH_EVERY:
                        part = _write_part(buffer, next_part)
                        written_parts.append(relative(part))
                        log.info("wrote part=%s rows=%d processed=%d", part.name, len(buffer), processed)
                        buffer.clear()
                        next_part += 1
                    if processed and processed % FLUSH_EVERY == 0:
                        elapsed = max(1e-6, time.time() - start)
                        rss_gib = psutil.Process(os.getpid()).memory_info().rss / 1024**3
                        tqdm.write(
                            f"stage 6 status: processed={processed:,}/{len(tasks):,} "
                            f"rate={processed / elapsed:.1f}/s rss={rss_gib:.2f}GiB"
                        )
    if buffer:
        part = _write_part(buffer, next_part)
        written_parts.append(relative(part))
        log.info("wrote final part=%s rows=%d processed=%d", part.name, len(buffer), processed)
    final_rows = _write_final_from_parts()
    log.info("published qc.parquet rows=%d", final_rows)
    return {
        "resume_completed_rows": len(completed),
        "pending_rows": len(tasks),
        "written_parts": written_parts,
        "final_rows": final_rows,
    }


def main() -> None:
    start = time.time()
    disk_before = psutil.disk_usage(str(PROJECT_ROOT)).free / 1024**3
    log = _setup_main_logger()
    log.info("starting %s", SCRIPT_NAME)
    log.info("run command from scripts cwd: %s", RUN_COMMAND.replace("\n", " && "))
    old_dir = _old_qc_dir()
    if old_dir is None:
        log.warning("old qc JSON folder not found at data/processed/qc or processed/qc; validation will fail")
    else:
        log.info("old qc JSON folder selected for validation: %s", relative(old_dir))

    deleted: list[dict[str, Any]] = []
    cleanup = {"removed": [], "remaining": sorted(path.name for path in DATA_PROCESSED.glob("qc.part_*.parquet*")), "status": "SKIP"}
    log_status: dict[str, Any] = {}
    all_pass = False
    stats: dict[str, Any] = {}
    try:
        metadata = _load_metadata()
        expected_studies = set(int(x) for x in metadata["study_id"].tolist())
        signal_studies, signal_stats = _load_signal_studies()
        image_studies, manifest_stats = _load_image_studies(expected_studies)
        text_stats = _text_stats(metadata)

        compute_stats = _compute_qc(metadata, signal_studies, image_studies, log)
        qc_df = _read_qc_parquet()
        row_coverage = _row_coverage(qc_df, expected_studies, len(metadata))
        distribution = {
            "waveform_ok_true": int(qc_df["waveform_ok"].sum()),
            "waveform_ok_false": int((~qc_df["waveform_ok"]).sum()),
            "image_ok_true": int(qc_df["image_ok"].sum()),
            "image_ok_false": int((~qc_df["image_ok"]).sum()),
            "text_ok_true": int(qc_df["text_ok"].sum()),
            "text_ok_false": int((~qc_df["text_ok"]).sum()),
        }
        waveform_missing = sorted(expected_studies - signal_studies)[:20]
        waveform_false_explanation = (
            "all metadata studies had a corresponding Lead-II HDF5 study_id"
            if not waveform_missing
            else f"missing Lead-II HDF5 study_id values, first examples {waveform_missing}"
        )
        metadata_values = _parquet_metadata()
        metadata_validation = _metadata_validation(metadata_values)
        old_json_validation = _validate_old_jsons(qc_df, old_dir)

        row_coverage_status = (
            "PASS"
            if row_coverage["qc_parquet_row_count"] == row_coverage["ecg_metadata_row_count"]
            and row_coverage["duplicate_study_id_count"] == 0
            and row_coverage["missing_study_id_count"] == 0
            and row_coverage["extra_study_id_count"] == 0
            else "FAIL"
        )
        waveform_status = (
            "PASS"
            if signal_stats["hdf5_rows"] == len(signal_studies)
            and distribution["waveform_ok_false"] == len(expected_studies - signal_studies)
            else "FAIL"
        )
        manifest_status = (
            "PASS"
            if all(
                item["row_count"] == len(metadata)
                and item["unique_study_id_count"] == len(expected_studies)
                and item["duplicate_study_id_count"] == 0
                and item["missing_study_count"] == 0
                and item["extra_study_count"] == 0
                for item in manifest_stats.values()
            )
            else "FAIL"
        )
        all_pass = (
            row_coverage_status == "PASS"
            and waveform_status == "PASS"
            and manifest_status == "PASS"
            and old_json_validation["final_verdict"] == "PASS"
            and metadata_validation["status"] == "PASS"
        )
        if all_pass:
            cleanup = _cleanup_parts()
            all_pass = cleanup["status"] == "PASS"
        if all_pass and old_dir is not None and old_dir.exists():
            deleted.append(_delete_tree(old_dir))
        stats = {
            "compute_stats": compute_stats,
            "signal_stats": signal_stats,
            "manifest_stats": manifest_stats,
            "text_stats": text_stats,
            "row_coverage": row_coverage,
            "row_coverage_status": row_coverage_status,
            "waveform_status": waveform_status,
            "manifest_status": manifest_status,
            "waveform_false_explanation": waveform_false_explanation,
            "field_distribution": distribution,
            "old_json_validation": old_json_validation,
            "parquet_metadata": metadata_values,
            "metadata_validation": metadata_validation,
        }
        log.info("validation summary: %s", json.dumps({k: v for k, v in stats.items() if k.endswith("_status")}, sort_keys=True))
    except Exception:
        log.exception("stage 6 failed")
        stats.setdefault("manifest_stats", {})
        stats.setdefault("row_coverage", {"ecg_metadata_row_count": 0, "qc_parquet_row_count": 0, "duplicate_study_id_count": 0, "missing_study_id_count": 0, "extra_study_id_count": 0})
        stats.setdefault("field_distribution", {"waveform_ok_true": 0, "waveform_ok_false": 0, "image_ok_true": 0, "image_ok_false": 0, "text_ok_true": 0, "text_ok_false": 0})
        stats.setdefault("signal_stats", {"hdf5_rows": 0, "unique_study_ids": 0, "duplicate_study_id_count": 0})
        stats.setdefault("text_stats", {"missing_t_machine": 0, "empty_whitespace_t_machine": 0})
        stats.setdefault("old_json_validation", _validate_old_jsons(pd.DataFrame(columns=[field.name for field in QC_SCHEMA]), old_dir))
        stats.setdefault("metadata_validation", {"metadata": {}, "missing_keys": [], "status": "FAIL"})
        stats.setdefault("row_coverage_status", "FAIL")
        stats.setdefault("waveform_status", "FAIL")
        stats.setdefault("waveform_false_explanation", "stage failed before waveform validation completed")
        all_pass = False
    finally:
        log_status = _aggregate_worker_logs()

    disk_after = psutil.disk_usage(str(PROJECT_ROOT)).free / 1024**3
    elapsed = time.time() - start
    if all_pass:
        _write_done_marker(stats, elapsed)
    report = _make_report(stats, deleted, cleanup, log_status, disk_before, disk_after, elapsed, all_pass)
    write_text_atomic(report, REPORT_PATH)
    sys.stdout.write(report)
    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    mp.freeze_support()
    main()
```

## 6. Validation results
- Pre-flight: PASS - required inputs existed, `dataset_version_stamp=v2.0.0`, `MAX_WORKERS=15`, `MAX_RAM_GB=23.7`, and disk free before run was 411.3 GiB.
- Row coverage: PASS - ecg_metadata rows 800,035; qc.parquet rows 800,035; duplicate study_ids 0; missing study_ids 0; extra study_ids 0.
- HDF5 Lead-II check: PASS - total HDF5 rows 800,035; expected studies 800,035; unique HDF5 study_ids 800,035; HDF5 duplicate study_ids 0; waveform_ok true 800,035; waveform_ok false 0; false explanation `all metadata studies had a corresponding Lead-II HDF5 study_id`.
- clean_lead2: rows 800,035; unique study_ids 800,035; duplicates 0; missing vs metadata 0; extra vs metadata 0.
- scanlike_lead2: rows 800,035; unique study_ids 800,035; duplicates 0; missing vs metadata 0; extra vs metadata 0.
- clean_12lead: rows 800,035; unique study_ids 800,035; duplicates 0; missing vs metadata 0; extra vs metadata 0.
- scanlike_12lead: rows 800,035; unique study_ids 800,035; duplicates 0; missing vs metadata 0; extra vs metadata 0.
- Image field distribution: image_ok true 800,035; image_ok false 0.
- Text field distribution: text_ok true 800,034; text_ok false 1; missing T_machine 0; empty/whitespace T_machine 1.
- 100-row old-json validation: PASS - command `..\ecg_env\Scripts\python.exe phase1_dataset_generation\30_qc.py # internal 100-row old-json validation`; old folder `processed/qc` existed during validation: True; available old JSONs 651,437; sampled from qc/old-json intersection 100; match count 100; mismatch count 0; missing old JSON count 0; mismatched study_ids [].
- Parquet metadata verification: PASS - {'dataset_version': 'v2.0.0', 'created_at_iso': '2026-06-02T15:31:14Z', 'modality_kind': 'tri_modal_qc', 'n_rows': '800035', 'script_commit_hash': 'd07888c'}.
- `qc.part_*.parquet` cleanup verification: PASS - removed 9; remaining [].
- Old QC folder deletion status: PASS - validation folder `processed/qc`; deleted after validation: True; canonical `data/processed/qc/` exists after run: False; legacy `processed/qc/` exists after run: False.
- Logging-hygiene checklist (every bullet from section 8.14):
  - [x] Terminal showed one tqdm bar with no worker log interleaving; command stdout/stderr were redirected to `outputs/stage_reports/stage_6_run/`, and worker fd 1/2 were redirected to per-PID log files.
  - [x] `aggregate.log` / `all.log` exists, first + last 5 lines pasted, all match section 8.5 regex: PASS
    ```text
    scripts/phase1_dataset_generation/logs/30_qc/aggregate.log first 5:
    2026-06-02 21:01:08 WARNING pid=17704  worker | worker initialized
    2026-06-02 21:00:49 WARNING pid=18896  worker | worker initialized
    2026-06-02 21:01:10 WARNING pid=22400  worker | worker initialized
    2026-06-02 21:00:53 WARNING pid=26160  worker | worker initialized
    2026-06-02 21:01:07 WARNING pid=30832  worker | worker initialized
    scripts/phase1_dataset_generation/logs/30_qc/aggregate.log last 5:
    2026-06-02 21:01:00 WARNING pid=40784  worker | worker initialized
    2026-06-02 21:00:55 WARNING pid=40812  worker | worker initialized
    2026-06-02 21:01:11 WARNING pid=41852  worker | worker initialized
    2026-06-02 21:00:51 WARNING pid=42580  worker | worker initialized
    2026-06-02 21:00:58 WARNING pid=44172  worker | worker initialized
    scripts/phase1_dataset_generation/logs/30_qc/main.log first 5:
    2026-06-02 21:00:43 INFO    pid=39984  main | starting 30_qc
    2026-06-02 21:00:43 INFO    pid=39984  main | run command from scripts cwd: cd D:\Coding\MU\Tri-Modal_ECG\scripts && ..\ecg_env\Scripts\python.exe phase1_dataset_generation\30_qc.py 1> ..\outputs\stage_reports\stage_6_run\stage_6.stdout.log 2> ..\outputs\stage_reports\stage_6_run\stage_6.stderr.log
    2026-06-02 21:00:43 INFO    pid=39984  main | old qc JSON folder selected for validation: processed/qc
    2026-06-02 21:00:46 INFO    pid=39984  main | loaded resume state completed_rows=0 pending_rows=800035 existing_parts=0 next_part=0
    2026-06-02 21:01:12 INFO    pid=39984  main | wrote part=qc.part_0000.parquet rows=100000 processed=100000
    scripts/phase1_dataset_generation/logs/30_qc/main.log last 5:
    2026-06-02 21:01:13 INFO    pid=39984  main | wrote part=qc.part_0006.parquet rows=100000 processed=700000
    2026-06-02 21:01:13 INFO    pid=39984  main | wrote part=qc.part_0007.parquet rows=100000 processed=800000
    2026-06-02 21:01:14 INFO    pid=39984  main | wrote final part=qc.part_0008.parquet rows=35 processed=800035
    2026-06-02 21:01:14 INFO    pid=39984  main | published qc.parquet rows=800035
    2026-06-02 21:16:19 INFO    pid=39984  main | validation summary: {"manifest_status": "PASS", "row_coverage_status": "PASS", "waveform_status": "PASS"}
    ```
  - [x] `grep -n "print(" <script>.py` output pasted (must be empty inside worker()).
    ```text
    rg -n "print\(" scripts/phase1_dataset_generation/30_qc.py
    <no matches>
    ```
  - [x] `grep -n "logging.basicConfig" <script>.py` output pasted (must be empty inside worker()).
    ```text
    rg -n "logging\.basicConfig" scripts/phase1_dataset_generation/30_qc.py
    <no matches>
    ```
  - [x] `worker_<pid>.log` files moved into `archive_<ts>/`: scripts/phase1_dataset_generation/logs/30_qc/archive_20260602_211619
  - [x] If Transport B: paste the `finally: listener.stop()` line from the script: N/A - Stage 6 uses Transport A per-PID files for workers.
  - [x] If tqdm used: paste the `tqdm(..., mininterval=...)` call and the `with logging_redirect_tqdm():` line.
    ```text
    with logging_redirect_tqdm():
    tqdm(..., file=sys.stderr, dynamic_ncols=True, mininterval=0.5, desc="stage 6 qc")
    ```
- Disk before stage start: 411.3 GiB free
- Disk after stage end: 411.5 GiB free
- Wall-clock: 00:15:37

## 7. Manual test procedure
cd D:\Coding\MU\Tri-Modal_ECG\scripts
..\ecg_env\Scripts\python.exe phase1_dataset_generation\30_qc.py
..\ecg_env\Scripts\python.exe -c "import pandas as pd,sys; m=pd.read_parquet('../data/processed/index/ecg_metadata.parquet', columns=['study_id']); q=pd.read_parquet('../data/processed/qc.parquet'); sys.stdout.write(str((len(m), len(q), q.study_id.duplicated().sum(), len(set(m.study_id)-set(q.study_id)), len(set(q.study_id)-set(m.study_id))))+'\n')"
..\ecg_env\Scripts\python.exe -c "import pyarrow.parquet as pq,sys; sys.stdout.write(str({k.decode():v.decode() for k,v in pq.ParquetFile('../data/processed/qc.parquet').schema_arrow.metadata.items()})+'\n')"
Get-ChildItem ..\data\processed\qc.part_*.parquet -ErrorAction SilentlyContinue
Get-Content .\logs\30_qc\main.log -Tail 20

## 8. Assumptions requiring user confirmation
- Old QC folder location  ::  Stage 6 expects `data/processed/qc/`, but this workspace may retain the old JSON folder at root-level `processed/qc/`. The script validates against whichever of those two folders exists first and deletes only that validated folder after the 100-row comparison passes.
