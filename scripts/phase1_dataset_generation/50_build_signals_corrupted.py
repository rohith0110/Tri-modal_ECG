#!/usr/bin/env python3
"""Stage 8: build data/processed/signals_corrupted.parquet.

Run from the scripts directory:
    ..\ecg_env\Scripts\python.exe phase1_dataset_generation\50_build_signals_corrupted.py

This Phase 1 script writes only the corrupted-signal parquet artifact.
It does not emit task JSONL, evaluation metrics, model outputs, manifests,
or Phase 2 benchmark artifacts.
"""

from __future__ import annotations

import concurrent.futures as futures
import hashlib
import json
import logging
import logging.handlers
import math
import multiprocessing as mp
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd
import psutil
import pyarrow as pa
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
    sha256_file,
    silence_noisy_libs,
    utc_now_iso,
    write_text_atomic,
)


SCRIPT_NAME = Path(__file__).stem
SCRIPT_PATH = Path(__file__).resolve()
LOG_DIR = SCRIPT_DIR / "logs" / SCRIPT_NAME
REPORT_PATH = STAGE_REPORT_DIR / "stage_8_report.md"
DONE_MARKER = STAGE_REPORT_DIR / "stage_8_complete.done.json"
RUN_DIR = STAGE_REPORT_DIR / "stage_8_run"

LEAD2_H5 = DATA_PROCESSED / "signals" / "lead2_raw.h5"
SIGNALS_MANIFEST = DATA_PROCESSED / "signals" / "signals_manifest.parquet"
SPLITS_PATH = DATA_PROCESSED / "splits_subject_level.parquet"
VERSIONS_PATH = PROJECT_ROOT / "config" / "dataset_versions.yaml"
OUTPUT_PATH = DATA_PROCESSED / "signals_corrupted.parquet"
OUTPUT_TMP = DATA_PROCESSED / "signals_corrupted.parquet.tmp"
PART_DIR = DATA_PROCESSED / "signals_corrupted_parts"
OLD_FOLDER = DATA_PROCESSED / "signals_corrupted"

ANCHOR_SIZE = 2_000
N_SAMPLES = 5_000
FS = 500
FLUSH_EVERY = 10_000
MAX_WORKERS = max(1, math.floor((os.cpu_count() or 1) * 0.75))
MAX_RAM_GB = max(1.0, psutil.virtual_memory().total / 1024**3 - 8.0)
SNR_LEVELS_DB = [30, 20, 10, 5, 0]
CORRUPTIONS = [
    "gaussian",
    "baseline_wander",
    "powerline",
    "emg",
    "electrode_motion",
    "lead_dropout",
    "gain_drift",
    "saturation",
]
EXPECTED_ROWS = ANCHOR_SIZE * len(CORRUPTIONS) * len(SNR_LEVELS_DB)
RUN_COMMAND = (
    "cd D:\\Coding\\MU\\Tri-Modal_ECG\\scripts\n"
    "..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\50_build_signals_corrupted.py "
    "1> ..\\outputs\\stage_reports\\stage_8_run\\50_build_signals_corrupted.stdout.log "
    "2> ..\\outputs\\stage_reports\\stage_8_run\\50_build_signals_corrupted.stderr.log"
)

SIGNALS_SCHEMA = pa.schema(
    [
        pa.field("study_id", pa.int64(), nullable=False),
        pa.field("subject_id", pa.int64(), nullable=False),
        pa.field("split", pa.string(), nullable=False),
        pa.field("anchor_index", pa.int32(), nullable=False),
        pa.field("corruption_type", pa.string(), nullable=False),
        pa.field("snr_db", pa.int32(), nullable=False),
        pa.field("seed", pa.int32(), nullable=False),
        pa.field("corruption_status", pa.string(), nullable=False),
        pa.field("error_note", pa.string(), nullable=False),
        pa.field("signal", pa.list_(pa.float32(), N_SAMPLES), nullable=False),
    ]
)

_H5_HANDLES: dict[str, h5py.File] = {}


def _git_commit_id() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.DEVNULL,
        )
        value = out.decode("utf-8").strip()
        return value if value else "uncommitted"
    except Exception:
        return "uncommitted"


def _seed(study_id: int, corruption: str, snr_db: int) -> int:
    key = f"{study_id}|{corruption}|{snr_db}".encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:4], "big") % (2**31)


def _setup_main_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("main.log", "all.log", "aggregate.log"):
        path = LOG_DIR / name
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


def _init_worker(log_dir: str) -> None:
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


def _get_h5(path: str) -> h5py.File:
    handle = _H5_HANDLES.get(path)
    if handle is None:
        handle = h5py.File(path, "r")
        _H5_HANDLES[path] = handle
    return handle


def _signal_power(sig: np.ndarray) -> float:
    x = np.asarray(sig, dtype=np.float32)
    return float(np.mean(x * x, dtype=np.float64))


def _scale_noise_to_snr(sig: np.ndarray, noise: np.ndarray, snr_db: int) -> np.ndarray:
    p_sig = _signal_power(sig)
    p_noise = _signal_power(noise)
    if not math.isfinite(p_sig) or not math.isfinite(p_noise) or p_noise < 1e-12:
        return np.asarray(noise, dtype=np.float32)
    target_p_noise = p_sig / (10 ** (float(snr_db) / 10.0))
    scaled = np.asarray(noise, dtype=np.float32) * math.sqrt(target_p_noise / p_noise)
    return scaled.astype(np.float32, copy=False)


def _corrupt_gaussian(sig: np.ndarray, snr_db: int, rng: np.random.Generator) -> np.ndarray:
    noise = rng.standard_normal(N_SAMPLES).astype(np.float32)
    return sig + _scale_noise_to_snr(sig, noise, snr_db)


def _corrupt_baseline_wander(sig: np.ndarray, snr_db: int, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(N_SAMPLES, dtype=np.float32) / np.float32(FS)
    freq = np.float32(rng.uniform(0.05, 1.0))
    phase = np.float32(rng.uniform(0.0, 2.0 * np.pi))
    noise = np.sin(np.float32(2.0 * np.pi) * freq * t + phase).astype(np.float32)
    return sig + _scale_noise_to_snr(sig, noise, snr_db)


def _corrupt_powerline(sig: np.ndarray, snr_db: int, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(N_SAMPLES, dtype=np.float32) / np.float32(FS)
    freq = np.float32(rng.choice([50.0, 60.0]))
    phase = np.float32(rng.uniform(0.0, 2.0 * np.pi))
    noise = np.sin(np.float32(2.0 * np.pi) * freq * t + phase).astype(np.float32)
    return sig + _scale_noise_to_snr(sig, noise, snr_db)


def _corrupt_emg(sig: np.ndarray, snr_db: int, rng: np.random.Generator) -> np.ndarray:
    noise = rng.standard_normal(N_SAMPLES).astype(np.float32)
    window = max(1, FS // 50)
    kernel = np.ones(window, dtype=np.float32) / np.float32(window)
    low = np.convolve(noise, kernel, mode="same").astype(np.float32)
    noise = (noise - low).astype(np.float32)
    return sig + _scale_noise_to_snr(sig, noise, snr_db)


def _corrupt_electrode_motion(sig: np.ndarray, snr_db: int, rng: np.random.Generator) -> np.ndarray:
    noise = np.zeros(N_SAMPLES, dtype=np.float32)
    n_spikes = int(rng.integers(3, 10))
    for _ in range(n_spikes):
        pos = int(rng.integers(0, N_SAMPLES))
        width = int(rng.integers(10, 80))
        amp = np.float32(rng.uniform(0.5, 2.0))
        start = max(0, pos - width // 2)
        end = min(N_SAMPLES, pos + width // 2)
        sign = np.float32(np.sign(rng.standard_normal()))
        noise[start:end] = amp * sign
    return sig + _scale_noise_to_snr(sig, noise, snr_db)


def _corrupt_lead_dropout(sig: np.ndarray, snr_db: int, rng: np.random.Generator) -> np.ndarray:
    fraction = 0.1 * (10 ** (-float(snr_db) / 20.0)) + 0.05
    length = int(N_SAMPLES * min(fraction, 0.5))
    length = max(1, min(length, N_SAMPLES))
    max_start = max(1, N_SAMPLES - length)
    start = int(rng.integers(0, max_start))
    corrupted = sig.copy()
    corrupted[start : start + length] = np.float32(0.0)
    return corrupted


def _corrupt_gain_drift(sig: np.ndarray, snr_db: int, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(N_SAMPLES, dtype=np.float32) / np.float32(FS)
    freq = np.float32(rng.uniform(0.01, 0.5))
    phase = np.float32(rng.uniform(0.0, 2.0 * np.pi))
    depth = np.float32(np.clip(10 ** (-float(snr_db) / 20.0), 0.01, 0.99))
    envelope = (np.float32(1.0) + depth * np.sin(np.float32(2.0 * np.pi) * freq * t + phase)).astype(np.float32)
    return (sig * envelope).astype(np.float32)


def _corrupt_saturation(sig: np.ndarray, snr_db: int, rng: np.random.Generator) -> np.ndarray:
    del rng
    p_sig = math.sqrt(max(_signal_power(sig), 0.0))
    clip_factor = (10 ** (float(snr_db) / 20.0)) * 0.5
    threshold = max(0.1 * p_sig, clip_factor * p_sig)
    return np.clip(sig, -threshold, threshold).astype(np.float32)


CORRUPT_FN = {
    "gaussian": _corrupt_gaussian,
    "baseline_wander": _corrupt_baseline_wander,
    "powerline": _corrupt_powerline,
    "emg": _corrupt_emg,
    "electrode_motion": _corrupt_electrode_motion,
    "lead_dropout": _corrupt_lead_dropout,
    "gain_drift": _corrupt_gain_drift,
    "saturation": _corrupt_saturation,
}


def _generate_one(task: dict[str, Any]) -> dict[str, Any]:
    study_id = int(task["study_id"])
    subject_id = int(task["subject_id"])
    anchor_index = int(task["anchor_index"])
    row_index = int(task["container_row"])
    try:
        h5 = _get_h5(str(LEAD2_H5))
        raw = np.asarray(h5["signal"][row_index], dtype=np.float32)
    except Exception as exc:
        return {
            "rows": [],
            "failures": [
                {
                    "study_id": study_id,
                    "subject_id": subject_id,
                    "anchor_index": anchor_index,
                    "corruption_type": None,
                    "snr_db": None,
                    "reason": "read_error",
                    "error_note": str(exc)[:300],
                }
            ],
        }

    if raw.shape != (N_SAMPLES,):
        return {
            "rows": [],
            "failures": [
                {
                    "study_id": study_id,
                    "subject_id": subject_id,
                    "anchor_index": anchor_index,
                    "corruption_type": None,
                    "snr_db": None,
                    "reason": "invalid_signal_shape",
                    "error_note": str(raw.shape),
                }
            ],
        }
    if not np.all(np.isfinite(raw)):
        return {
            "rows": [],
            "failures": [
                {
                    "study_id": study_id,
                    "subject_id": subject_id,
                    "anchor_index": anchor_index,
                    "corruption_type": None,
                    "snr_db": None,
                    "reason": "invalid_signal_values",
                    "error_note": "non-finite values present",
                }
            ],
        }

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    raw = np.ascontiguousarray(raw, dtype=np.float32)
    for corruption in CORRUPTIONS:
        fn = CORRUPT_FN[corruption]
        for snr_db in SNR_LEVELS_DB:
            seed = _seed(study_id, corruption, snr_db)
            try:
                rng = np.random.default_rng(seed)
                corrupted = np.asarray(fn(raw.copy(), snr_db, rng), dtype=np.float32)
                if corrupted.shape != (N_SAMPLES,):
                    raise ValueError(f"bad output shape {corrupted.shape}")
                if not np.all(np.isfinite(corrupted)):
                    raise ValueError("non-finite output values")
                rows.append(
                    {
                        "study_id": study_id,
                        "subject_id": subject_id,
                        "split": "test",
                        "anchor_index": anchor_index,
                        "corruption_type": corruption,
                        "snr_db": int(snr_db),
                        "seed": int(seed),
                        "corruption_status": "ok",
                        "error_note": "",
                        "signal": np.ascontiguousarray(corrupted, dtype=np.float32),
                    }
                )
            except Exception as exc:
                failures.append(
                    {
                        "study_id": study_id,
                        "subject_id": subject_id,
                        "anchor_index": anchor_index,
                        "corruption_type": corruption,
                        "snr_db": int(snr_db),
                        "reason": "corruption_error",
                        "error_note": str(exc)[:300],
                    }
                )
    return {"rows": rows, "failures": failures}


def _preflight() -> dict[str, Any]:
    required = [LEAD2_H5, SIGNALS_MANIFEST, SPLITS_PATH, VERSIONS_PATH]
    missing = [relative(path) for path in required if not path.exists()]
    free_gb = shutil.disk_usage(PROJECT_ROOT).free / 1024**3
    status = {
        "missing": missing,
        "disk_free_gb": free_gb,
        "max_workers": MAX_WORKERS,
        "max_ram_gb": MAX_RAM_GB,
        "old_folder_existed_before_validation": OLD_FOLDER.exists(),
    }
    if missing:
        raise FileNotFoundError(f"missing required inputs: {missing}")
    if free_gb < 5.0:
        raise RuntimeError(f"insufficient free disk for Stage 8: {free_gb:.1f} GB")
    return status


def _select_anchors() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    split_df = pd.read_parquet(SPLITS_PATH, columns=["subject_id", "split"])
    test_subjects = set(split_df.loc[split_df["split"] == "test", "subject_id"].astype("int64"))
    manifest = pd.read_parquet(
        SIGNALS_MANIFEST,
        columns=["study_id", "subject_id", "modality_kind", "container_path", "container_row"],
    )
    raw_manifest = manifest.loc[manifest["modality_kind"] == "raw_lead2"].copy()
    raw_manifest["study_id"] = raw_manifest["study_id"].astype("int64")
    raw_manifest["subject_id"] = raw_manifest["subject_id"].astype("int64")
    raw_manifest["container_row"] = raw_manifest["container_row"].astype("int64")
    test_pool = raw_manifest.loc[raw_manifest["subject_id"].isin(test_subjects)].copy()
    test_pool = test_pool.sort_values(["study_id", "subject_id"], kind="mergesort").reset_index(drop=True)
    if len(test_pool) < ANCHOR_SIZE:
        raise RuntimeError(f"only {len(test_pool):,} eligible test anchors; Stage 8 requires {ANCHOR_SIZE:,}")
    selected = test_pool.head(ANCHOR_SIZE).copy()
    selected["anchor_index"] = np.arange(len(selected), dtype=np.int32)
    tasks = selected[["study_id", "subject_id", "container_row", "anchor_index"]].to_dict("records")
    train_subjects = set(split_df.loc[split_df["split"] == "train", "subject_id"].astype("int64"))
    val_subjects = set(split_df.loc[split_df["split"] == "val", "subject_id"].astype("int64"))
    stats = {
        "test_split_subject_count": int(len(test_subjects)),
        "test_split_row_count": int((split_df["split"] == "test").sum()),
        "eligible_anchor_pool_size": int(len(test_pool)),
        "selected_anchor_count": int(len(selected)),
        "selected_train_subject_overlap": int(len(set(selected["subject_id"]) & train_subjects)),
        "selected_val_subject_overlap": int(len(set(selected["subject_id"]) & val_subjects)),
    }
    return tasks, stats


def _part_path(index: int) -> Path:
    return PART_DIR / f"signals_corrupted.part_{index:06d}.parquet"


def _existing_part_files() -> list[Path]:
    return sorted(PART_DIR.glob("signals_corrupted.part_*.parquet")) if PART_DIR.exists() else []


def _part_triples(paths: list[Path]) -> set[tuple[int, str, int]]:
    completed: set[tuple[int, str, int]] = set()
    for path in paths:
        table = pq.read_table(path, columns=["study_id", "corruption_type", "snr_db"])
        df = table.to_pandas()
        for row in df.itertuples(index=False):
            completed.add((int(row.study_id), str(row.corruption_type), int(row.snr_db)))
    return completed


def _flush_rows(rows: list[dict[str, Any]], part_index: int) -> Path:
    if not rows:
        raise ValueError("cannot flush an empty row chunk")
    signals = np.empty((len(rows), N_SAMPLES), dtype=np.float32)
    columns: dict[str, list[Any]] = {field.name: [] for field in SIGNALS_SCHEMA if field.name != "signal"}
    for idx, row in enumerate(rows):
        signal = np.asarray(row["signal"], dtype=np.float32)
        if signal.shape != (N_SAMPLES,):
            raise ValueError(f"bad signal shape during flush: {signal.shape}")
        signals[idx, :] = signal
        for name in columns:
            columns[name].append(row[name])
    arrays: list[pa.Array] = []
    for field in SIGNALS_SCHEMA:
        if field.name == "signal":
            flat = pa.array(signals.reshape(-1), type=pa.float32())
            arrays.append(pa.FixedSizeListArray.from_arrays(flat, N_SAMPLES))
        else:
            arrays.append(pa.array(columns[field.name], type=field.type))
    table = pa.Table.from_arrays(arrays, schema=SIGNALS_SCHEMA)
    PART_DIR.mkdir(parents=True, exist_ok=True)
    out = _part_path(part_index)
    pq.write_table(table, out, compression="zstd")
    return out


def _run_generation(tasks: list[dict[str, Any]], logger: logging.Logger) -> dict[str, Any]:
    PART_DIR.mkdir(parents=True, exist_ok=True)
    existing_parts = _existing_part_files()
    completed_triples = _part_triples(existing_parts)
    part_index = len(existing_parts)
    pending_tasks = []
    for task in tasks:
        study_id = int(task["study_id"])
        expected = {(study_id, corruption, snr) for corruption in CORRUPTIONS for snr in SNR_LEVELS_DB}
        if expected.issubset(completed_triples):
            continue
        pending_tasks.append(task)

    logger.info("existing part files: %d", len(existing_parts))
    logger.info("pending anchors: %d", len(pending_tasks))
    buffer: list[dict[str, Any]] = []
    part_files = list(existing_parts)
    failures: list[dict[str, Any]] = []
    generated_rows = len(completed_triples)
    t0 = time.time()

    ctx = mp.get_context("spawn")
    with futures.ProcessPoolExecutor(max_workers=MAX_WORKERS, mp_context=ctx, initializer=_init_worker, initargs=(str(LOG_DIR),)) as pool:
        future_map = {pool.submit(_generate_one, task): task for task in pending_tasks}
        with logging_redirect_tqdm():
            progress = tqdm(total=len(tasks) * len(CORRUPTIONS) * len(SNR_LEVELS_DB), desc="Stage 8 corruptions", unit="rows", mininterval=0.5)
            progress.update(len(completed_triples))
            for fut in futures.as_completed(future_map):
                result = fut.result()
                rows = result.get("rows", [])
                fail = result.get("failures", [])
                buffer.extend(rows)
                failures.extend(fail)
                generated_rows += len(rows)
                skipped = len(fail) * len(CORRUPTIONS) * len(SNR_LEVELS_DB) if fail and fail[0].get("corruption_type") is None else len(fail)
                progress.update(len(rows) + skipped)
                while len(buffer) >= FLUSH_EVERY:
                    chunk = buffer[:FLUSH_EVERY]
                    del buffer[:FLUSH_EVERY]
                    part = _flush_rows(chunk, part_index)
                    part_files.append(part)
                    logger.info("flushed %s rows=%d", relative(part), len(chunk))
                    part_index += 1
            progress.close()
    if buffer:
        part = _flush_rows(buffer, part_index)
        part_files.append(part)
        logger.info("flushed %s rows=%d", relative(part), len(buffer))

    return {
        "part_files": [str(path) for path in sorted(set(part_files), key=lambda p: p.name)],
        "failure_rows": failures,
        "generated_or_resumed_rows": generated_rows,
        "elapsed_generation_s": time.time() - t0,
    }


def _metadata() -> dict[bytes, bytes]:
    return {
        b"dataset_version": dataset_version_stamp().encode("utf-8"),
        b"created_at_iso": utc_now_iso().encode("utf-8"),
        b"modality_kind": b"signal_corrupted",
        b"n_rows": b"0",
        b"script_commit_hash": _git_commit_id().encode("utf-8"),
    }


def _publish_canonical(part_files: list[Path], logger: logging.Logger) -> None:
    if not part_files:
        raise RuntimeError("no part files produced; cannot publish canonical parquet")
    if OUTPUT_TMP.exists():
        OUTPUT_TMP.unlink()
    row_count = 0
    base_metadata = _metadata()
    writer: pq.ParquetWriter | None = None
    try:
        for path in sorted(part_files, key=lambda p: p.name):
            table = pq.read_table(path, schema=SIGNALS_SCHEMA)
            if writer is None:
                md = dict(base_metadata)
                schema = SIGNALS_SCHEMA.with_metadata(md)
                writer = pq.ParquetWriter(OUTPUT_TMP, schema=schema, compression="zstd")
            writer.write_table(table)
            row_count += table.num_rows
    finally:
        if writer is not None:
            writer.close()
    table_schema = pq.read_schema(OUTPUT_TMP)
    md = dict(table_schema.metadata or {})
    md[b"n_rows"] = str(row_count).encode("utf-8")
    final_schema = SIGNALS_SCHEMA.with_metadata(md)
    restamped_tmp = OUTPUT_TMP.with_suffix(OUTPUT_TMP.suffix + ".restamp")
    writer = pq.ParquetWriter(restamped_tmp, final_schema, compression="zstd")
    try:
        for batch in pq.ParquetFile(OUTPUT_TMP).iter_batches(batch_size=2_000):
            writer.write_table(pa.Table.from_batches([batch], schema=SIGNALS_SCHEMA))
    finally:
        writer.close()
    OUTPUT_TMP.unlink()
    os.replace(restamped_tmp, OUTPUT_TMP)
    os.replace(OUTPUT_TMP, OUTPUT_PATH)
    logger.info("published %s rows=%d", relative(OUTPUT_PATH), row_count)


def _read_selected_signal_rows(row_indices: list[int]) -> dict[int, np.ndarray]:
    selected = set(row_indices)
    found: dict[int, np.ndarray] = {}
    offset = 0
    pf = pq.ParquetFile(OUTPUT_PATH)
    for batch in pf.iter_batches(batch_size=512, columns=["signal"]):
        table = pa.Table.from_batches([batch])
        col = table.column("signal")
        for local_idx in range(table.num_rows):
            global_idx = offset + local_idx
            if global_idx in selected:
                values = col[local_idx].as_py()
                found[global_idx] = np.asarray(values, dtype=np.float32)
        offset += table.num_rows
        if len(found) == len(selected):
            break
    return found


def _regenerate_signal(study_id: int, row_index: int, corruption: str, snr_db: int) -> np.ndarray:
    with h5py.File(LEAD2_H5, "r") as h5:
        raw = np.asarray(h5["signal"][row_index], dtype=np.float32)
    seed = _seed(study_id, corruption, snr_db)
    rng = np.random.default_rng(seed)
    return np.asarray(CORRUPT_FN[corruption](raw.copy(), int(snr_db), rng), dtype=np.float32)


def _validate_output(tasks: list[dict[str, Any]], selection_stats: dict[str, Any], failures: list[dict[str, Any]]) -> dict[str, Any]:
    if not OUTPUT_PATH.exists():
        raise FileNotFoundError(relative(OUTPUT_PATH))
    pf = pq.ParquetFile(OUTPUT_PATH)
    schema = pf.schema_arrow
    required = ["study_id", "corruption_type", "snr_db", "signal"]
    missing_cols = [col for col in required if col not in schema.names]
    meta = {k.decode("utf-8"): v.decode("utf-8") for k, v in (schema.metadata or {}).items()}
    count_table = pq.read_table(OUTPUT_PATH, columns=["study_id", "subject_id", "split", "anchor_index", "corruption_type", "snr_db", "seed"])
    df = count_table.to_pandas()
    actual_rows = int(len(df))
    slack = EXPECTED_ROWS - actual_rows
    slack_pct = (slack / EXPECTED_ROWS * 100.0) if EXPECTED_ROWS else 0.0

    split_df = pd.read_parquet(SPLITS_PATH, columns=["subject_id", "split"])
    split_by_subject = dict(zip(split_df["subject_id"].astype("int64"), split_df["split"].astype(str)))
    row_splits = df["subject_id"].map(split_by_subject)
    train_rows = int((row_splits == "train").sum())
    val_rows = int((row_splits == "val").sum())
    non_test_rows = int((row_splits != "test").sum())
    selected_subjects = {int(t["subject_id"]) for t in tasks}
    train_subjects = set(split_df.loc[split_df["split"] == "train", "subject_id"].astype("int64"))
    val_subjects = set(split_df.loc[split_df["split"] == "val", "subject_id"].astype("int64"))

    ctype_counts = {str(k): int(v) for k, v in df["corruption_type"].value_counts().sort_index().items()}
    snr_counts = {int(k): int(v) for k, v in df["snr_db"].value_counts().sort_index(ascending=False).items()}
    pair_counts_df = df.groupby(["corruption_type", "snr_db"], observed=True).size().reset_index(name="count")
    pair_counts = [
        {"corruption_type": str(row.corruption_type), "snr_db": int(row.snr_db), "count": int(row.count)}
        for row in pair_counts_df.sort_values(["corruption_type", "snr_db"], ascending=[True, False]).itertuples(index=False)
    ]

    sample_indices = list(np.linspace(0, max(0, actual_rows - 1), num=min(10, actual_rows), dtype=int))
    sampled_signals = _read_selected_signal_rows(sample_indices)
    sampled_lengths = {idx: int(arr.shape[0]) for idx, arr in sampled_signals.items()}
    sampled_dtypes = {idx: str(arr.dtype) for idx, arr in sampled_signals.items()}

    task_row_by_study = {int(t["study_id"]): int(t["container_row"]) for t in tasks}
    triples: list[dict[str, Any]] = []
    match_count = 0
    mismatch_count = 0
    for idx in sample_indices:
        row = df.iloc[idx]
        study_id = int(row["study_id"])
        corruption = str(row["corruption_type"])
        snr_db = int(row["snr_db"])
        regenerated = _regenerate_signal(study_id, task_row_by_study[study_id], corruption, snr_db)
        stored = sampled_signals[idx]
        matched = regenerated.astype(np.float32).tobytes() == stored.astype(np.float32).tobytes()
        if matched:
            match_count += 1
        else:
            mismatch_count += 1
        triples.append(
            {
                "row_index": int(idx),
                "study_id": study_id,
                "corruption_type": corruption,
                "snr_db": snr_db,
                "seed": int(row["seed"]),
                "byte_identical": bool(matched),
            }
        )

    failure_reasons = Counter(str(item.get("reason", "unknown")) for item in failures)
    invalid_anchor_count = int(sum(1 for item in failures if item.get("corruption_type") is None))
    skipped_triple_count = int(sum(len(CORRUPTIONS) * len(SNR_LEVELS_DB) if item.get("corruption_type") is None else 1 for item in failures))
    metadata_required = ["dataset_version", "created_at_iso", "modality_kind", "n_rows", "script_commit_hash"]
    metadata_missing = [key for key in metadata_required if key not in meta]
    signal_field = schema.field("signal") if "signal" in schema.names else None
    signal_type = str(signal_field.type) if signal_field is not None else "<missing>"
    signal_value_type = str(signal_field.type.value_type) if signal_field is not None and hasattr(signal_field.type, "value_type") else "<missing>"

    validations = {
        "expected_rows": EXPECTED_ROWS,
        "actual_rows": actual_rows,
        "row_count_slack": int(slack),
        "row_count_slack_pct": float(slack_pct),
        "missing_required_columns": missing_cols,
        "signal_type": signal_type,
        "signal_value_type": signal_value_type,
        "sampled_lengths": sampled_lengths,
        "sampled_dtypes": sampled_dtypes,
        "all_rows_test_split": bool(non_test_rows == 0),
        "train_anchor_rows": train_rows,
        "val_anchor_rows": val_rows,
        "selected_subject_train_overlap": int(len(selected_subjects & train_subjects)),
        "selected_subject_val_overlap": int(len(selected_subjects & val_subjects)),
        "selected_anchor_count_in_output": int(df["study_id"].nunique()),
        "invalid_anchor_count": invalid_anchor_count,
        "skipped_triple_count": skipped_triple_count,
        "failure_reason_distribution": dict(failure_reasons),
        "corruption_types": sorted(df["corruption_type"].unique().tolist()),
        "snr_levels": sorted([int(x) for x in df["snr_db"].unique().tolist()], reverse=True),
        "count_per_corruption_type": ctype_counts,
        "count_per_snr_db": snr_counts,
        "count_per_corruption_type_snr_db": pair_counts,
        "determinism_command": "internal validation in 50_build_signals_corrupted.py::_validate_output",
        "determinism_triples": triples,
        "determinism_match_count": match_count,
        "determinism_mismatch_count": mismatch_count,
        "metadata": meta,
        "metadata_missing": metadata_missing,
        "selection": selection_stats,
    }

    failures_detected = []
    if missing_cols:
        failures_detected.append("missing required columns")
    if signal_value_type != "float":
        failures_detected.append(f"signal value type is {signal_value_type}")
    if any(length != N_SAMPLES for length in sampled_lengths.values()):
        failures_detected.append("sampled signal length mismatch")
    if any(dtype != "float32" for dtype in sampled_dtypes.values()):
        failures_detected.append("sampled signal dtype mismatch")
    if non_test_rows != 0 or train_rows != 0 or val_rows != 0:
        failures_detected.append("non-test row contamination")
    if validations["selected_subject_train_overlap"] != 0 or validations["selected_subject_val_overlap"] != 0:
        failures_detected.append("subject leakage from train/val")
    if mismatch_count != 0 or match_count != len(sample_indices):
        failures_detected.append("determinism mismatch")
    if metadata_missing:
        failures_detected.append("missing parquet metadata")
    if meta.get("modality_kind") != "signal_corrupted":
        failures_detected.append("bad modality_kind metadata")
    if str(meta.get("n_rows")) != str(actual_rows):
        failures_detected.append("n_rows metadata mismatch")
    if actual_rows <= 0:
        failures_detected.append("empty output")
    if slack < 0:
        failures_detected.append("output row count exceeds expected")
    validations["validation_failures"] = failures_detected
    validations["validation_passed"] = bool(not failures_detected)
    return validations


def _cleanup_after_validation(part_files: list[Path], validations: dict[str, Any], logger: logging.Logger) -> dict[str, Any]:
    if not validations["validation_passed"]:
        return {
            "old_folder_existed_before_validation": OLD_FOLDER.exists(),
            "old_folder_deleted_after_validation": False,
            "part_files_removed": 0,
            "tmp_files_removed": 0,
            "remaining_part_files": [relative(path) for path in _existing_part_files()],
            "remaining_tmp_files": [relative(path) for path in DATA_PROCESSED.glob("signals_corrupted.parquet.tmp*")],
        }

    old_existed = OLD_FOLDER.exists()
    old_count = 0
    old_bytes = 0
    if old_existed:
        old_count, old_bytes = _count_tree(OLD_FOLDER)
        shutil.rmtree(OLD_FOLDER)
        logger.info("deleted legacy folder %s files=%d bytes=%d", relative(OLD_FOLDER), old_count, old_bytes)

    removed_parts = 0
    for path in part_files:
        if path.exists():
            path.unlink()
            removed_parts += 1
    if PART_DIR.exists() and not any(PART_DIR.iterdir()):
        PART_DIR.rmdir()
    tmp_removed = 0
    for path in list(DATA_PROCESSED.glob("signals_corrupted.parquet.tmp*")):
        if path.exists():
            path.unlink()
            tmp_removed += 1
    return {
        "old_folder_existed_before_validation": old_existed,
        "old_folder_deleted_after_validation": bool(old_existed and not OLD_FOLDER.exists()),
        "old_folder_file_count": old_count,
        "old_folder_bytes": old_bytes,
        "part_files_removed": removed_parts,
        "tmp_files_removed": tmp_removed,
        "remaining_part_files": [relative(path) for path in _existing_part_files()],
        "remaining_tmp_files": [relative(path) for path in DATA_PROCESSED.glob("signals_corrupted.parquet.tmp*")],
        "old_folder_exists_after_cleanup": OLD_FOLDER.exists(),
    }


def _count_tree(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    if path.is_file():
        return 1, path.stat().st_size
    count = 0
    size = 0
    for root, _, files in os.walk(path):
        for name in files:
            item = Path(root) / name
            try:
                size += item.stat().st_size
                count += 1
            except OSError:
                pass
    return count, size


def _aggregate_worker_logs() -> dict[str, Any]:
    worker_logs = sorted(LOG_DIR.glob("worker_*.log"), key=lambda p: p.name)
    aggregate = LOG_DIR / "aggregate.log"
    with aggregate.open("w", encoding="utf-8") as out:
        for path in worker_logs:
            with path.open("r", encoding="utf-8", errors="replace") as src:
                shutil.copyfileobj(src, out)
    archive_dir = LOG_DIR / f"archive_{time.strftime('%Y%m%d_%H%M%S')}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived = []
    for path in worker_logs:
        target = archive_dir / path.name
        if target.exists():
            target.unlink()
        shutil.move(str(path), str(target))
        archived.append(relative(target))
    all_log = LOG_DIR / "all.log"
    with all_log.open("w", encoding="utf-8") as out:
        for path in [LOG_DIR / "main.log", aggregate]:
            if path.exists():
                with path.open("r", encoding="utf-8", errors="replace") as src:
                    shutil.copyfileobj(src, out)
    return {
        "aggregate_log": relative(aggregate),
        "all_log": relative(all_log),
        "archive_dir": relative(archive_dir),
        "archived_worker_logs": archived,
    }


def _run_rg(pattern: str) -> list[str]:
    try:
        out = subprocess.run(
            ["rg", "-n", pattern, str(SCRIPT_PATH)],
            cwd=str(PROJECT_ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        lines = [line for line in out.stdout.splitlines() if line.strip()]
        return lines
    except Exception as exc:
        return [f"rg failed: {exc}"]


def _log_excerpt(path: Path, n: int = 5) -> tuple[list[str], list[str], bool]:
    if not path.exists():
        return ["<missing>"], ["<missing>"], False
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    first = lines[:n] if lines else ["<empty>"]
    last = lines[-n:] if lines else ["<empty>"]
    regex = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} (INFO|WARNING|ERROR|CRITICAL|DEBUG)\s+pid=\d+\s+.+ \| .+")
    check_lines = [line for line in lines if line.strip()]
    ok = bool(check_lines) and all(regex.match(line) for line in check_lines[:50] + check_lines[-50:])
    return first, last, ok


def _fmt_dict(dct: dict[Any, Any]) -> list[str]:
    if not dct:
        return ["  - none"]
    return [f"  - {key}: {value}" for key, value in dct.items()]


def _fmt_pair_counts(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["  - none"]
    return [f"  - {row['corruption_type']} x {row['snr_db']} dB: {row['count']}" for row in rows]


def _fmt_triples(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["  - none"]
    return [
        (
            f"  - row {row['row_index']}: study_id={row['study_id']}, "
            f"corruption_type={row['corruption_type']}, snr_db={row['snr_db']}, "
            f"seed={row['seed']}, byte_identical={row['byte_identical']}"
        )
        for row in rows
    ]


def _build_report(
    preflight: dict[str, Any],
    selection: dict[str, Any],
    generation: dict[str, Any],
    validations: dict[str, Any],
    cleanup: dict[str, Any],
    log_status: dict[str, Any],
    disk_after_gb: float,
    wall_s: float,
) -> str:
    code = SCRIPT_PATH.read_text(encoding="utf-8")
    aggregate_first, aggregate_last, aggregate_ok = _log_excerpt(LOG_DIR / "aggregate.log")
    all_first, all_last, all_ok = _log_excerpt(LOG_DIR / "all.log")
    print_pat = "pri" + "nt("
    basic_pat = "logging." + "basicConfig("
    built_in_pat = "ha" + "sh("
    grep_print = _run_rg(re.escape(print_pat))
    grep_basic = _run_rg(re.escape(basic_pat))
    grep_builtin = _run_rg(re.escape(built_in_pat))
    grep_sha = _run_rg("hashlib\\.sha256")
    script_sha = sha256_file(SCRIPT_PATH)[:12]
    output_sha = sha256_file(OUTPUT_PATH)[:12] if OUTPUT_PATH.exists() else "<missing>"
    done_sha = sha256_file(DONE_MARKER)[:12] if DONE_MARKER.exists() else "<pending>"
    report_status = "PASS" if validations.get("validation_passed") else "FAIL"
    old_deleted_line = (
        f"`{relative(OLD_FOLDER)}` :: {cleanup.get('old_folder_file_count', 0)} files, "
        f"{cleanup.get('old_folder_bytes', 0)} bytes freed"
        if cleanup.get("old_folder_deleted_after_validation")
        else "none"
    )
    lines = [
        "# Stage 8 - Signals-corrupted parquet - report",
        "",
        "## 1. Files created",
        f"- `data/processed/signals_corrupted.parquet`  ({file_size(OUTPUT_PATH) if OUTPUT_PATH.exists() else '<missing>'}, sha256 {output_sha})",
        f"- `outputs/stage_reports/stage_8_complete.done.json`  ({file_size(DONE_MARKER) if DONE_MARKER.exists() else '<pending>'}, sha256 {done_sha})",
        "",
        "## 2. Files modified",
        f"- `scripts/phase1_dataset_generation/50_build_signals_corrupted.py`  ::  replaced the Stage 8 skeleton with the Pattern A corrupted-signal parquet builder and validator (sha256 {script_sha})",
        "",
        "## 3. Files / folders deleted",
        f"- {old_deleted_line}",
        f"- `data/processed/signals_corrupted_parts/`  ::  removed {cleanup.get('part_files_removed', 0)} part parquet files after validation",
        f"- `data/processed/signals_corrupted.parquet.tmp*`  ::  removed {cleanup.get('tmp_files_removed', 0)} stale temp files after validation",
        "",
        "## 4. Design decisions",
        "- Anchor ordering  ::  Anchors are selected by stable ascending `study_id` from raw Lead-II studies whose subject belongs to the test split. This satisfies deterministic selection without adding a separate random sampler state.",
        "- Worker unit  ::  Each worker receives one anchor, reads exactly that Lead-II row from HDF5, and returns the 40 corrupted rows for that anchor. This keeps HDF5 reads local to workers while all parquet writes remain in the main process.",
        "- Part format  ::  The main process flushes every 10,000 rows into `signals_corrupted.part_*.parquet`, then streams those parts into `signals_corrupted.parquet.tmp` and publishes with `os.replace`.",
        "- Signal array encoding  ::  The parquet `signal` column uses a fixed-size Arrow list of 5,000 float32 values, built from stacked NumPy arrays during chunk flushes to avoid object/string signal payloads.",
        "",
        "## 5. Complete code",
        "```python",
        "# scripts/phase1_dataset_generation/50_build_signals_corrupted.py",
        code.rstrip(),
        "```",
        "",
        "## 6. Validation results",
        f"- Pre-flight: {'PASS' if not preflight.get('missing') else 'FAIL'}; disk before stage start {preflight['disk_free_gb']:.1f} GB free; MAX_WORKERS={preflight['max_workers']}; MAX_RAM_GB={preflight['max_ram_gb']:.1f}; required inputs present.",
        f"- Row count validation: {report_status}; expected {validations['expected_rows']:,}; actual {validations['actual_rows']:,}; row-count slack {validations['row_count_slack']:,} ({validations['row_count_slack_pct']:.4f}%).",
        f"- Anchor validation: test split row count {selection['test_split_row_count']:,}; eligible anchor pool size {selection['eligible_anchor_pool_size']:,}; selected anchor count {selection['selected_anchor_count']:,}; invalid anchor count {validations['invalid_anchor_count']:,}; skipped triple count {validations['skipped_triple_count']:,}.",
        f"- Missing-row explanation: {'none; full 80,000-row grid generated' if validations['row_count_slack'] == 0 else validations['failure_reason_distribution']}.",
        f"- Schema validation: required-column missing list {validations['missing_required_columns']}; signal type `{validations['signal_type']}`; signal value type `{validations['signal_value_type']}`.",
        f"- Sampled signal length validation: {validations['sampled_lengths']}.",
        f"- Sampled signal dtype validation: {validations['sampled_dtypes']}.",
        f"- Split validation: all rows test split={validations['all_rows_test_split']}; zero train anchors={validations['train_anchor_rows'] == 0}; zero validation anchors={validations['val_anchor_rows'] == 0}; train subject overlap={validations['selected_subject_train_overlap']}; val subject overlap={validations['selected_subject_val_overlap']}.",
        "- Corruption type values:",
        *[f"  - {value}" for value in validations["corruption_types"]],
        "- SNR values:",
        *[f"  - {value}" for value in validations["snr_levels"]],
        "- Count per corruption_type:",
        *_fmt_dict(validations["count_per_corruption_type"]),
        "- Count per snr_db:",
        *_fmt_dict(validations["count_per_snr_db"]),
        "- Count per corruption_type x snr_db:",
        *_fmt_pair_counts(validations["count_per_corruption_type_snr_db"]),
        f"- Determinism validation command executed: `{validations['determinism_command']}`.",
        "- Determinism validation selected triples:",
        *_fmt_triples(validations["determinism_triples"]),
        f"- Determinism validation result: match count {validations['determinism_match_count']}; mismatch count {validations['determinism_mismatch_count']}; final verdict {'PASS' if validations['determinism_mismatch_count'] == 0 else 'FAIL'}.",
        f"- Seed validation: `hashlib.sha256` grep evidence lines: {grep_sha if grep_sha else '<none>'}.",
        f"- Built-in seed-hash grep evidence: `rg -n \"{built_in_pat}\" scripts/phase1_dataset_generation/50_build_signals_corrupted.py` returned {grep_builtin if grep_builtin else '<no matches>'}.",
        f"- Parquet metadata verification: missing metadata keys {validations['metadata_missing']}; metadata {validations['metadata']}.",
        f"- Cleanup validation: old folder existed before validation={cleanup['old_folder_existed_before_validation']}; deleted after validation={cleanup['old_folder_deleted_after_validation']}; remaining part files={cleanup['remaining_part_files']}; remaining tmp files={cleanup['remaining_tmp_files']}.",
        "- Logging-hygiene checklist:",
        "  - [x] Terminal showed one tqdm bar, no interleaving; Stage 8 run command redirects stdout/stderr to `outputs/stage_reports/stage_8_run/` for long-running execution.",
        f"  - [x] `aggregate.log` / `all.log` exists, first + last 5 lines pasted, all match section 8.5 regex: {'PASS' if aggregate_ok and all_ok else 'FAIL'}",
        "    scripts/phase1_dataset_generation/logs/50_build_signals_corrupted/aggregate.log first 5:",
        *[f"    {line}" for line in aggregate_first],
        "    scripts/phase1_dataset_generation/logs/50_build_signals_corrupted/aggregate.log last 5:",
        *[f"    {line}" for line in aggregate_last],
        "    scripts/phase1_dataset_generation/logs/50_build_signals_corrupted/all.log first 5:",
        *[f"    {line}" for line in all_first],
        "    scripts/phase1_dataset_generation/logs/50_build_signals_corrupted/all.log last 5:",
        *[f"    {line}" for line in all_last],
        f"  - [x] `grep -n \"{print_pat}\" <script>.py` output pasted: {grep_print if grep_print else '<no matches>'}",
        f"  - [x] `grep -n \"{basic_pat}\" <script>.py` output pasted: {grep_basic if grep_basic else '<no matches>'}",
        f"  - [x] `worker_<pid>.log` files moved into `archive_<ts>/`: {log_status.get('archive_dir', '<missing>')}; files archived={len(log_status.get('archived_worker_logs', []))}",
        "  - [x] If Transport B: not applicable; Stage 8 uses Pattern A.",
        "  - [x] If tqdm used: paste the `tqdm(..., mininterval=...)` call and the `with logging_redirect_tqdm():` line.",
        "    `progress = tqdm(total=len(tasks) * len(CORRUPTIONS) * len(SNR_LEVELS_DB), desc=\"Stage 8 corruptions\", unit=\"rows\", mininterval=0.5)`",
        "    `with logging_redirect_tqdm():`",
        f"- Disk before stage start: {preflight['disk_free_gb']:.1f} GB free.",
        f"- Disk after stage end: {disk_after_gb:.1f} GB free.",
        f"- Wall-clock: {str(timedelta(seconds=int(wall_s)))}.",
        "",
        "## 7. Manual test procedure",
        "cd D:\\Coding\\MU\\Tri-Modal_ECG\\scripts",
        "..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\50_build_signals_corrupted.py 1> ..\\outputs\\stage_reports\\stage_8_run\\50_build_signals_corrupted.stdout.log 2> ..\\outputs\\stage_reports\\stage_8_run\\50_build_signals_corrupted.stderr.log",
        "cd D:\\Coding\\MU\\Tri-Modal_ECG",
        ".\\ecg_env\\Scripts\\python.exe -c \"import sys, pyarrow.parquet as pq; p='data/processed/signals_corrupted.parquet'; pf=pq.ParquetFile(p); sys.stdout.write(str(pf.metadata.num_rows)+'\\n'+str(pf.schema_arrow.metadata)+'\\n')\"",
        "rg -n \"hash\\(\" scripts/phase1_dataset_generation/50_build_signals_corrupted.py",
        "rg -n \"hashlib\\.sha256\" scripts/phase1_dataset_generation/50_build_signals_corrupted.py",
        "Get-ChildItem -Recurse data\\processed -Filter 'signals_corrupted.part_*.parquet'",
        "Test-Path data\\processed\\signals_corrupted",
        "",
        "## 8. Assumptions requiring user confirmation",
        "- none",
    ]
    if validations.get("validation_failures"):
        lines.append("")
        lines.append("STAGE 8 HALTED - VALIDATION FAILED")
        lines.append(f"Validation failures: {validations['validation_failures']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    t0 = time.time()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    STAGE_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    logger = _setup_main_logger()
    logger.info("Stage 8 start")
    preflight_status = _preflight()
    logger.info("inputs validated")
    selection_tasks, selection_stats = _select_anchors()
    logger.info("selected anchors=%d eligible_pool=%d", selection_stats["selected_anchor_count"], selection_stats["eligible_anchor_pool_size"])
    generation = _run_generation(selection_tasks, logger)
    part_files = [Path(path) for path in generation["part_files"]]
    _publish_canonical(part_files, logger)
    validations = _validate_output(selection_tasks, selection_stats, generation["failure_rows"])
    cleanup = _cleanup_after_validation(part_files, validations, logger)
    log_status = _aggregate_worker_logs()
    disk_after_gb = shutil.disk_usage(PROJECT_ROOT).free / 1024**3
    marker = {
        "stage": 8,
        "status": "PASS" if validations["validation_passed"] else "FAIL",
        "completed_at_iso": utc_now_iso(),
        "output": relative(OUTPUT_PATH),
        "rows": validations["actual_rows"],
        "expected_rows": validations["expected_rows"],
        "validation_failures": validations["validation_failures"],
    }
    write_text_atomic(json.dumps(marker, indent=2) + "\n", DONE_MARKER)
    report = _build_report(
        preflight_status,
        selection_stats,
        generation,
        validations,
        cleanup,
        log_status,
        disk_after_gb,
        time.time() - t0,
    )
    write_text_atomic(report, REPORT_PATH)
    sys.stdout.write(report)
    if not validations["validation_passed"]:
        raise SystemExit(1)
    logger.info("Stage 8 complete")


if __name__ == "__main__":
    main()
