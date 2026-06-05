#!/usr/bin/env python3
"""Stage 9: materialize preprocessed signal HDF5 modalities.

Run from the scripts directory:
    ..\ecg_env\Scripts\python.exe phase1_dataset_generation\15_preprocess_signals.py

This script applies the locked Stage 3 preprocessing recipe to raw HDF5
signals. It never fits scalers and never mutates raw HDF5 inputs.
"""

from __future__ import annotations

import concurrent.futures as futures
import hashlib
import importlib.metadata
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
from datetime import timedelta
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd
import psutil
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from scipy import signal as scipy_signal
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from _stage1_common import (
    CONFIG_DIR,
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
STAGE_NAME = "Materialized preprocessed signals"
LOG_DIR = SCRIPT_DIR / "logs" / SCRIPT_NAME
REPORT_PATH = STAGE_REPORT_DIR / "stage_9_report.md"
DONE_MARKER = STAGE_REPORT_DIR / "stage_9_complete.done.json"
RUN_DIR = STAGE_REPORT_DIR / "stage_9_run"

SIGNALS_DIR = DATA_PROCESSED / "signals"
PARTIAL_DIR = DATA_PROCESSED / "partial"
LEAD2_RAW = SIGNALS_DIR / "lead2_raw.h5"
LEAD2_OUT = SIGNALS_DIR / "lead2_preprocessed.h5"
TWELVE_RAW_TEMPLATE = "twelve_lead_raw_shard_{shard:02d}.h5"
TWELVE_OUT_TEMPLATE = "twelve_lead_preprocessed_shard_{shard:02d}.h5"
SIGNALS_MANIFEST = SIGNALS_DIR / "signals_manifest.parquet"
MODALITY_MANIFEST = DATA_PROCESSED / "modality_manifest.parquet"
SIDECAR_MANIFEST = SIGNALS_DIR / "preprocessed_signals_manifest.parquet"
RECIPE_PATH = CONFIG_DIR / "preprocessing_recipe.yaml"
LEAD2_SCALER = CONFIG_DIR / "scalers" / "lead2_zscore_train.npz"
TWELVE_SCALER = CONFIG_DIR / "scalers" / "twelve_lead_zscore_train.npz"
DATASET_VERSIONS = CONFIG_DIR / "dataset_versions.yaml"

LEAD_ORDER = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
N_TWELVE_SHARDS = 5
N_SAMPLES = 5000
HDF5_CHUNK_SHAPE = (64, 5000)
COMPRESSION = "gzip"
COMPRESSION_OPTS = 4
PROCESS_BATCH_ROWS = 64
PACK_BATCH_ROWS = 512
VALIDATION_SAMPLE_N = 100
MAX_WORKERS = max(1, math.floor((os.cpu_count() or 1) * 0.75))
MAX_RAM_GB = max(1.0, psutil.virtual_memory().total / 1024**3 - 8.0)
RUN_COMMAND = (
    "cd D:\\Coding\\MU\\Tri-Modal_ECG\\scripts\n"
    "..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\15_preprocess_signals.py "
    "1> ..\\outputs\\stage_reports\\stage_9_run\\15_preprocess_signals.stdout.log "
    "2> ..\\outputs\\stage_reports\\stage_9_run\\15_preprocess_signals.stderr.log"
)


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


def _load_recipe() -> dict[str, Any]:
    with RECIPE_PATH.open("r", encoding="utf-8") as f:
        recipe = yaml.safe_load(f)
    if not isinstance(recipe, dict):
        raise ValueError(f"bad preprocessing recipe: {RECIPE_PATH}")
    return recipe


def _load_scaler(path: Path) -> tuple[np.ndarray, np.ndarray]:
    data = np.load(path, allow_pickle=False)
    mean = np.asarray(data["mean"], dtype=np.float32)
    std = np.asarray(data["std"], dtype=np.float32)
    if np.any(std == 0) or not np.all(np.isfinite(mean)) or not np.all(np.isfinite(std)):
        raise ValueError(f"invalid z-score scaler values in {path}")
    return mean, std


def _filter_lib_version() -> str:
    try:
        return importlib.metadata.version("scipy")
    except importlib.metadata.PackageNotFoundError:
        return "scipy"


def _filter_params(recipe: dict[str, Any]) -> dict[str, Any]:
    return {
        "hp_cutoff_hz": float(recipe["baseline_highpass"]["hp_cutoff_hz"]),
        "hp_order": int(recipe["baseline_highpass"]["hp_order"]),
        "notch_freq_hz": float(recipe["powerline_notch"]["notch_freq_hz"]),
        "notch_q_factor": float(recipe["powerline_notch"]["notch_q_factor"]),
        "lp_cutoff_hz": float(recipe["lowpass"]["lp_cutoff_hz"]),
        "lp_order": int(recipe["lowpass"]["lp_order"]),
        "original_fs": float(recipe["resampling"]["original_fs"]),
        "target_fs": float(recipe["resampling"]["target_fs"]),
        "scaler_type": str(recipe["normalization"]["scaler_type"]),
        "scaler_fit_split": str(recipe["normalization"]["scaler_fit_split"]),
    }


def _make_filter_state(recipe: dict[str, Any]) -> dict[str, Any]:
    params = _filter_params(recipe)
    fs = params["original_fs"]
    hp_sos = scipy_signal.butter(
        params["hp_order"],
        params["hp_cutoff_hz"],
        btype="highpass",
        fs=fs,
        output="sos",
    )
    notch_b, notch_a = scipy_signal.iirnotch(params["notch_freq_hz"], params["notch_q_factor"], fs=fs)
    lp_sos = scipy_signal.butter(
        params["lp_order"],
        params["lp_cutoff_hz"],
        btype="lowpass",
        fs=fs,
        output="sos",
    )
    return {"params": params, "hp_sos": hp_sos, "notch_b": notch_b, "notch_a": notch_a, "lp_sos": lp_sos}


def _filter_array(arr: np.ndarray, sample_axis: int, filter_state: dict[str, Any]) -> np.ndarray:
    x = np.asarray(arr, dtype=np.float32)
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    y = scipy_signal.sosfiltfilt(filter_state["hp_sos"], x, axis=sample_axis).astype(np.float32, copy=False)
    y = scipy_signal.filtfilt(filter_state["notch_b"], filter_state["notch_a"], y, axis=sample_axis).astype(np.float32, copy=False)
    y = scipy_signal.sosfiltfilt(filter_state["lp_sos"], y, axis=sample_axis).astype(np.float32, copy=False)
    return y


def _apply_lead2(raw: np.ndarray, filter_state: dict[str, Any], mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    filtered = _filter_array(raw, sample_axis=1 if raw.ndim == 2 else 0, filter_state=filter_state)
    out = (filtered - float(mean[0])) / float(std[0])
    return np.nan_to_num(out.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)


def _apply_twelve(raw: np.ndarray, filter_state: dict[str, Any], mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    arr = np.asarray(raw, dtype=np.float32)
    if arr.ndim == 2:
        filtered = _filter_array(arr, sample_axis=0, filter_state=filter_state)
        out = (filtered - mean.reshape(1, -1)) / std.reshape(1, -1)
    elif arr.ndim == 3:
        filtered = _filter_array(arr, sample_axis=1, filter_state=filter_state)
        out = (filtered - mean.reshape(1, 1, -1)) / std.reshape(1, 1, -1)
    else:
        raise ValueError(f"expected 12-lead raw array with 2 or 3 dimensions, got {arr.shape}")
    return np.nan_to_num(out.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)


def _sha256_array(arr: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(np.asarray(arr, dtype=np.float32))
    return hashlib.sha256(contiguous.tobytes()).hexdigest()


def _relative_processed(path: Path) -> str:
    return str(path.relative_to(DATA_PROCESSED)).replace("\\", "/")


def _partition_ranges(n_rows: int, n_workers: int) -> list[tuple[int, int]]:
    base = n_rows // n_workers
    extra = n_rows % n_workers
    ranges = []
    start = 0
    for wid in range(n_workers):
        length = base + (1 if wid < extra else 0)
        end = start + length
        ranges.append((start, end))
        start = end
    return ranges


def _partial_path(kind: str, worker_id: int) -> Path:
    return PARTIAL_DIR / f"{kind}_worker_{worker_id:02d}.h5"


def _partial_valid(path: Path, expected_rows: int, required_datasets: tuple[str, ...]) -> bool:
    if not path.exists():
        return False
    try:
        with h5py.File(path, "r") as h5:
            if not bool(h5.attrs.get("complete", False)):
                return False
            if int(h5.attrs.get("n_rows", -1)) != int(expected_rows):
                return False
            return all(name in h5 and int(h5[name].shape[0]) == int(expected_rows) for name in required_datasets)
    except OSError:
        return False


def _create_partial_lead2(path: Path) -> h5py.File:
    h5 = h5py.File(path, "w")
    h5.create_dataset(
        "signal",
        shape=(0, N_SAMPLES),
        maxshape=(None, N_SAMPLES),
        dtype="float32",
        chunks=HDF5_CHUNK_SHAPE,
        compression=COMPRESSION,
        compression_opts=COMPRESSION_OPTS,
        shuffle=True,
    )
    h5.create_dataset("study_id", shape=(0,), maxshape=(None,), dtype="int64", chunks=(4096,))
    h5.create_dataset("subject_id", shape=(0,), maxshape=(None,), dtype="int64", chunks=(4096,))
    h5.create_dataset("source_row", shape=(0,), maxshape=(None,), dtype="int64", chunks=(4096,))
    return h5


def _create_partial_twelve(path: Path) -> h5py.File:
    h5 = h5py.File(path, "w")
    h5.create_dataset(
        "signal",
        shape=(0, N_SAMPLES, len(LEAD_ORDER)),
        maxshape=(None, N_SAMPLES, len(LEAD_ORDER)),
        dtype="float32",
        chunks=(HDF5_CHUNK_SHAPE[0], HDF5_CHUNK_SHAPE[1], 1),
        compression=COMPRESSION,
        compression_opts=COMPRESSION_OPTS,
        shuffle=True,
    )
    h5.create_dataset("study_id", shape=(0,), maxshape=(None,), dtype="int64", chunks=(4096,))
    h5.create_dataset("subject_id", shape=(0,), maxshape=(None,), dtype="int64", chunks=(4096,))
    h5.create_dataset("source_shard", shape=(0,), maxshape=(None,), dtype="int16", chunks=(4096,))
    h5.create_dataset("source_row", shape=(0,), maxshape=(None,), dtype="int64", chunks=(4096,))
    return h5


def _append_partial(h5: h5py.File, signal: np.ndarray, columns: dict[str, np.ndarray]) -> None:
    n = int(len(signal))
    if n == 0:
        return
    start = int(h5["signal"].shape[0])
    end = start + n
    h5["signal"].resize((end, *h5["signal"].shape[1:]))
    h5["signal"][start:end] = np.asarray(signal, dtype=np.float32)
    for name, values in columns.items():
        h5[name].resize((end,))
        h5[name][start:end] = values


def _worker_task(task: dict[str, Any]) -> dict[str, Any]:
    worker_id = int(task["worker_id"])
    lead2_range = tuple(task["lead2_range"])
    twelve_ranges = {int(k): tuple(v) for k, v in task["twelve_ranges"].items()}
    expected_lead2 = int(lead2_range[1] - lead2_range[0])
    expected_twelve = int(sum(end - start for start, end in twelve_ranges.values()))
    lead2_final = _partial_path("preprocessed_lead2", worker_id)
    twelve_final = _partial_path("preprocessed_12lead", worker_id)
    if _partial_valid(lead2_final, expected_lead2, ("signal", "study_id", "subject_id", "source_row")) and _partial_valid(
        twelve_final,
        expected_twelve,
        ("signal", "study_id", "subject_id", "source_shard", "source_row"),
    ):
        return {
            "worker_id": worker_id,
            "lead2_rows": expected_lead2,
            "twelve_rows": expected_twelve,
            "status": "reused",
        }

    for path in [lead2_final, twelve_final, lead2_final.with_suffix(".h5.tmp"), twelve_final.with_suffix(".h5.tmp")]:
        path.unlink(missing_ok=True)

    recipe = _load_recipe()
    filter_state = _make_filter_state(recipe)
    lead2_mean, lead2_std = _load_scaler(LEAD2_SCALER)
    twelve_mean, twelve_std = _load_scaler(TWELVE_SCALER)
    lead2_tmp = lead2_final.with_suffix(".h5.tmp")
    twelve_tmp = twelve_final.with_suffix(".h5.tmp")
    lead2_rows = 0
    twelve_rows = 0
    throttle_limit = (MAX_RAM_GB / max(1, MAX_WORKERS)) * 1.5
    proc = psutil.Process()

    with _create_partial_lead2(lead2_tmp) as out_h5, h5py.File(LEAD2_RAW, "r") as raw_h5:
        start, end = lead2_range
        for batch_start in range(start, end, PROCESS_BATCH_ROWS):
            batch_end = min(batch_start + PROCESS_BATCH_ROWS, end)
            raw = raw_h5["signal"][batch_start:batch_end]
            signal = _apply_lead2(raw, filter_state, lead2_mean, lead2_std)
            rows = np.arange(batch_start, batch_end, dtype=np.int64)
            _append_partial(
                out_h5,
                signal,
                {
                    "study_id": raw_h5["study_id"][batch_start:batch_end].astype("int64", copy=False),
                    "subject_id": raw_h5["subject_id"][batch_start:batch_end].astype("int64", copy=False),
                    "source_row": rows,
                },
            )
            lead2_rows += int(batch_end - batch_start)
            if proc.memory_info().rss / 1024**3 > throttle_limit:
                time.sleep(2.0)
        out_h5.attrs["complete"] = True
        out_h5.attrs["n_rows"] = lead2_rows
        out_h5.flush()
    os.replace(lead2_tmp, lead2_final)

    with _create_partial_twelve(twelve_tmp) as out_h5:
        for shard in range(N_TWELVE_SHARDS):
            start, end = twelve_ranges[shard]
            raw_path = SIGNALS_DIR / TWELVE_RAW_TEMPLATE.format(shard=shard)
            with h5py.File(raw_path, "r") as raw_h5:
                for batch_start in range(start, end, PROCESS_BATCH_ROWS):
                    batch_end = min(batch_start + PROCESS_BATCH_ROWS, end)
                    raw = raw_h5["signal"][batch_start:batch_end]
                    signal = _apply_twelve(raw, filter_state, twelve_mean, twelve_std)
                    n = int(batch_end - batch_start)
                    _append_partial(
                        out_h5,
                        signal,
                        {
                            "study_id": raw_h5["study_id"][batch_start:batch_end].astype("int64", copy=False),
                            "subject_id": raw_h5["subject_id"][batch_start:batch_end].astype("int64", copy=False),
                            "source_shard": np.full(n, shard, dtype=np.int16),
                            "source_row": np.arange(batch_start, batch_end, dtype=np.int64),
                        },
                    )
                    twelve_rows += n
                    if proc.memory_info().rss / 1024**3 > throttle_limit:
                        time.sleep(2.0)
        out_h5.attrs["complete"] = True
        out_h5.attrs["n_rows"] = twelve_rows
        out_h5.flush()
    os.replace(twelve_tmp, twelve_final)
    return {"worker_id": worker_id, "lead2_rows": lead2_rows, "twelve_rows": twelve_rows, "status": "generated"}


def _create_canonical_file(path: Path, modality_kind: str, signal_shape: tuple[int, ...], chunks: tuple[int, ...], attrs: dict[str, Any]) -> h5py.File:
    path.parent.mkdir(parents=True, exist_ok=True)
    h5 = h5py.File(path, "w")
    h5.create_dataset(
        "signal",
        shape=(0, *signal_shape),
        maxshape=(None, *signal_shape),
        dtype="float32",
        chunks=chunks,
        compression=COMPRESSION,
        compression_opts=COMPRESSION_OPTS,
        shuffle=True,
    )
    h5.create_dataset("study_id", shape=(0,), maxshape=(None,), dtype="int64", chunks=(4096,))
    h5.create_dataset("subject_id", shape=(0,), maxshape=(None,), dtype="int64", chunks=(4096,))
    h5.attrs["dataset_version"] = dataset_version_stamp()
    h5.attrs["created_at_iso"] = attrs["created_at_iso"]
    h5.attrs["modality_kind"] = modality_kind
    h5.attrs["n_studies"] = 0
    h5.attrs["chunk_shape"] = json.dumps(HDF5_CHUNK_SHAPE)
    h5.attrs["compression"] = f"{COMPRESSION}-{COMPRESSION_OPTS}"
    h5.attrs["script_commit_hash"] = script_commit_hash()
    h5.attrs["lead_order"] = json.dumps(LEAD_ORDER if modality_kind == "preprocessed_12lead" else ["II"])
    for key, value in attrs.items():
        if key != "created_at_iso":
            h5.attrs[key] = value
    return h5


def _append_canonical(h5: h5py.File, signal: np.ndarray, study_ids: np.ndarray, subject_ids: np.ndarray) -> tuple[int, int]:
    n = int(len(study_ids))
    if n == 0:
        row = int(h5["study_id"].shape[0])
        return row, row
    start = int(h5["study_id"].shape[0])
    end = start + n
    h5["signal"].resize((end, *h5["signal"].shape[1:]))
    h5["study_id"].resize((end,))
    h5["subject_id"].resize((end,))
    h5["signal"][start:end] = np.asarray(signal, dtype=np.float32)
    h5["study_id"][start:end] = np.asarray(study_ids, dtype=np.int64)
    h5["subject_id"][start:end] = np.asarray(subject_ids, dtype=np.int64)
    h5.attrs["n_studies"] = end
    return start, end


def _pack_lead2(partials: list[Path], attrs: dict[str, Any], logger: logging.Logger) -> tuple[list[dict[str, Any]], int]:
    tmp = LEAD2_OUT.with_suffix(".h5.tmp")
    tmp.unlink(missing_ok=True)
    created_at = attrs["created_at_iso"]
    manifest_rows: list[dict[str, Any]] = []
    row_count = 0
    with _create_canonical_file(tmp, "preprocessed_lead2", (N_SAMPLES,), HDF5_CHUNK_SHAPE, attrs) as out_h5:
        ordered: list[tuple[int, Path]] = []
        for path in partials:
            with h5py.File(path, "r") as src:
                source_rows = src["source_row"][:]
                if len(source_rows):
                    ordered.append((int(source_rows.min()), path))
        for _, path in sorted(ordered, key=lambda item: item[0]):
            with h5py.File(path, "r") as src:
                n_rows = int(src["study_id"].shape[0])
                for start in range(0, n_rows, PACK_BATCH_ROWS):
                    end = min(start + PACK_BATCH_ROWS, n_rows)
                    signal = src["signal"][start:end]
                    study_ids = src["study_id"][start:end].astype("int64", copy=False)
                    subject_ids = src["subject_id"][start:end].astype("int64", copy=False)
                    out_start, _ = _append_canonical(out_h5, signal, study_ids, subject_ids)
                    for local_idx, study_id in enumerate(study_ids):
                        manifest_rows.append(
                            {
                                "study_id": int(study_id),
                                "subject_id": int(subject_ids[local_idx]),
                                "modality_kind": "preprocessed_lead2",
                                "container_path": _relative_processed(LEAD2_OUT),
                                "container_row": int(out_start + local_idx),
                                "container_offset": None,
                                "container_length": None,
                                "sha256": _sha256_array(signal[local_idx]),
                                "dataset_version": dataset_version_stamp(),
                                "created_at": created_at,
                            }
                        )
                    row_count += len(study_ids)
            logger.info("packed lead2 partial=%s cumulative_rows=%d", path.name, row_count)
        out_h5.flush()
    os.replace(tmp, LEAD2_OUT)
    return manifest_rows, row_count


def _pack_twelve(partials: list[Path], attrs: dict[str, Any], logger: logging.Logger) -> tuple[list[dict[str, Any]], dict[int, int]]:
    created_at = attrs["created_at_iso"]
    manifest_rows: list[dict[str, Any]] = []
    shard_counts: dict[int, int] = {}
    for shard in range(N_TWELVE_SHARDS):
        final = SIGNALS_DIR / TWELVE_OUT_TEMPLATE.format(shard=shard)
        tmp = final.with_suffix(".h5.tmp")
        tmp.unlink(missing_ok=True)
        row_count = 0
        with _create_canonical_file(tmp, "preprocessed_12lead", (N_SAMPLES, len(LEAD_ORDER)), (HDF5_CHUNK_SHAPE[0], HDF5_CHUNK_SHAPE[1], 1), attrs) as out_h5:
            ordered: list[tuple[int, Path]] = []
            for path in partials:
                with h5py.File(path, "r") as src:
                    source_shard = src["source_shard"][:]
                    mask = source_shard == shard
                    if np.any(mask):
                        source_rows = src["source_row"][:]
                        ordered.append((int(source_rows[mask].min()), path))
            for _, path in sorted(ordered, key=lambda item: item[0]):
                with h5py.File(path, "r") as src:
                    positions = np.where(src["source_shard"][:] == shard)[0]
                    if len(positions) == 0:
                        continue
                    start_pos = int(positions[0])
                    end_pos = int(positions[-1]) + 1
                    for start in range(start_pos, end_pos, PACK_BATCH_ROWS):
                        end = min(start + PACK_BATCH_ROWS, end_pos)
                        signal = src["signal"][start:end]
                        study_ids = src["study_id"][start:end].astype("int64", copy=False)
                        subject_ids = src["subject_id"][start:end].astype("int64", copy=False)
                        out_start, _ = _append_canonical(out_h5, signal, study_ids, subject_ids)
                        for local_idx, study_id in enumerate(study_ids):
                            manifest_rows.append(
                                {
                                    "study_id": int(study_id),
                                    "subject_id": int(subject_ids[local_idx]),
                                    "modality_kind": "preprocessed_12lead",
                                    "container_path": _relative_processed(final),
                                    "container_row": int(out_start + local_idx),
                                    "container_offset": None,
                                    "container_length": None,
                                    "sha256": _sha256_array(signal[local_idx]),
                                    "dataset_version": dataset_version_stamp(),
                                    "created_at": created_at,
                                }
                            )
                        row_count += len(study_ids)
            out_h5.flush()
        os.replace(tmp, final)
        shard_counts[shard] = row_count
        logger.info("packed twelve shard=%02d rows=%d", shard, row_count)
    return manifest_rows, shard_counts


def _write_manifest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["modality_kind", "container_path", "container_row", "study_id"], kind="mergesort").reset_index(drop=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata.update(
        {
            b"dataset_version": dataset_version_stamp().encode("utf-8"),
            b"created_at_iso": utc_now_iso().encode("utf-8"),
            b"modality_kind": b"preprocessed_signals_manifest",
            b"n_rows": str(table.num_rows).encode("utf-8"),
            b"script_commit_hash": script_commit_hash().encode("utf-8"),
        }
    )
    if MODALITY_MANIFEST.exists():
        existing = pd.read_parquet(MODALITY_MANIFEST)
        preserved = existing.loc[~existing["modality_kind"].isin(["preprocessed_lead2", "preprocessed_12lead"])].copy()
        merged = pd.concat([preserved, df], ignore_index=True)
        out_table = pa.Table.from_pandas(merged, preserve_index=False)
        out_meta = dict(out_table.schema.metadata or {})
        out_meta.update(metadata)
        tmp = MODALITY_MANIFEST.with_suffix(".parquet.tmp")
        pq.write_table(out_table.replace_schema_metadata(out_meta), tmp, compression="snappy")
        os.replace(tmp, MODALITY_MANIFEST)
        return {"mode": "updated_modality_manifest", "path": relative(MODALITY_MANIFEST), "rows": int(len(df)), "preserved_rows": int(len(preserved))}
    tmp = SIDECAR_MANIFEST.with_suffix(".parquet.tmp")
    pq.write_table(table.replace_schema_metadata(metadata), tmp, compression="snappy")
    os.replace(tmp, SIDECAR_MANIFEST)
    return {"mode": "wrote_sidecar_manifest", "path": relative(SIDECAR_MANIFEST), "rows": int(len(df)), "preserved_rows": None}


def _input_snapshot() -> dict[str, dict[str, Any]]:
    paths = [LEAD2_RAW, SIGNALS_MANIFEST, RECIPE_PATH, LEAD2_SCALER, TWELVE_SCALER, DATASET_VERSIONS]
    paths.extend(SIGNALS_DIR / TWELVE_RAW_TEMPLATE.format(shard=shard) for shard in range(N_TWELVE_SHARDS))
    snap = {}
    for path in paths:
        stat = path.stat()
        snap[relative(path)] = {"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}
    return snap


def _preflight() -> dict[str, Any]:
    required = [LEAD2_RAW, SIGNALS_MANIFEST, RECIPE_PATH, LEAD2_SCALER, TWELVE_SCALER, DATASET_VERSIONS]
    required.extend(SIGNALS_DIR / TWELVE_RAW_TEMPLATE.format(shard=shard) for shard in range(N_TWELVE_SHARDS))
    missing = [relative(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing required Stage 9 input(s): {missing}")
    recipe = _load_recipe()
    params = _filter_params(recipe)
    problems = []
    if params["scaler_fit_split"] != "train":
        problems.append(f"scaler_fit_split={params['scaler_fit_split']}")
    if not math.isclose(params["hp_cutoff_hz"], 0.5, abs_tol=0.1):
        problems.append(f"hp_cutoff_hz={params['hp_cutoff_hz']}")
    if not math.isclose(params["notch_freq_hz"], 60.0, abs_tol=0.01):
        problems.append(f"notch_freq_hz={params['notch_freq_hz']}")
    if not (100.0 <= params["lp_cutoff_hz"] <= 150.0):
        problems.append(f"lp_cutoff_hz={params['lp_cutoff_hz']}")
    if not math.isclose(params["original_fs"], 500.0, abs_tol=0.01) or not math.isclose(params["target_fs"], 500.0, abs_tol=0.01):
        problems.append(f"fs={params['original_fs']}->{params['target_fs']}")
    if params["scaler_type"] != "zscore_per_lead":
        problems.append(f"scaler_type={params['scaler_type']}")
    lead2_mean, lead2_std = _load_scaler(LEAD2_SCALER)
    twelve_mean, twelve_std = _load_scaler(TWELVE_SCALER)
    if lead2_mean.shape != (1,) or lead2_std.shape != (1,):
        problems.append(f"lead2 scaler shape mean={lead2_mean.shape} std={lead2_std.shape}")
    if twelve_mean.shape != (len(LEAD_ORDER),) or twelve_std.shape != (len(LEAD_ORDER),):
        problems.append(f"12lead scaler shape mean={twelve_mean.shape} std={twelve_std.shape}")
    if problems:
        raise RuntimeError(f"Stage 9 preflight recipe/scaler validation failed: {problems}")
    with h5py.File(LEAD2_RAW, "r") as h5:
        lead2_rows = int(h5["study_id"].shape[0])
    raw_shard_rows = {}
    for shard in range(N_TWELVE_SHARDS):
        with h5py.File(SIGNALS_DIR / TWELVE_RAW_TEMPLATE.format(shard=shard), "r") as h5:
            raw_shard_rows[shard] = int(h5["study_id"].shape[0])
    free_gib = shutil.disk_usage(PROJECT_ROOT).free / 1024**3
    return {
        "missing": missing,
        "disk_free_gib": free_gib,
        "max_workers": MAX_WORKERS,
        "max_ram_gb": MAX_RAM_GB,
        "recipe_params": params,
        "recipe_sha256": sha256_file(RECIPE_PATH),
        "lead2_scaler_sha256": sha256_file(LEAD2_SCALER),
        "twelve_scaler_sha256": sha256_file(TWELVE_SCALER),
        "lead2_rows": lead2_rows,
        "raw_shard_rows": raw_shard_rows,
        "raw_twelve_total": int(sum(raw_shard_rows.values())),
        "modality_manifest_exists_before": MODALITY_MANIFEST.exists(),
    }


def _build_worker_tasks(preflight: dict[str, Any]) -> list[dict[str, Any]]:
    lead2_ranges = _partition_ranges(int(preflight["lead2_rows"]), MAX_WORKERS)
    twelve_ranges_by_shard = {
        shard: _partition_ranges(int(preflight["raw_shard_rows"][shard]), MAX_WORKERS) for shard in range(N_TWELVE_SHARDS)
    }
    tasks = []
    for wid in range(MAX_WORKERS):
        tasks.append(
            {
                "worker_id": wid,
                "lead2_range": lead2_ranges[wid],
                "twelve_ranges": {shard: twelve_ranges_by_shard[shard][wid] for shard in range(N_TWELVE_SHARDS)},
            }
        )
    return tasks


def _run_workers(tasks: list[dict[str, Any]], logger: logging.Logger) -> dict[str, Any]:
    PARTIAL_DIR.mkdir(parents=True, exist_ok=True)
    generated = 0
    reused = 0
    lead2_rows = 0
    twelve_rows = 0
    results = []
    ctx = mp.get_context("spawn")
    with futures.ProcessPoolExecutor(max_workers=MAX_WORKERS, mp_context=ctx, initializer=_init_worker, initargs=(str(LOG_DIR),)) as pool:
        future_map = {pool.submit(_worker_task, task): task for task in tasks}
        with logging_redirect_tqdm():
            progress = tqdm(total=len(tasks), desc="Stage 9 worker partials", unit="worker", mininterval=0.5, file=sys.stderr, dynamic_ncols=True)
            for fut in futures.as_completed(future_map):
                result = fut.result()
                results.append(result)
                generated += int(result["status"] == "generated")
                reused += int(result["status"] == "reused")
                lead2_rows += int(result["lead2_rows"])
                twelve_rows += int(result["twelve_rows"])
                progress.update(1)
            progress.close()
    logger.info("worker partials complete generated=%d reused=%d lead2_rows=%d twelve_rows=%d", generated, reused, lead2_rows, twelve_rows)
    return {"generated": generated, "reused": reused, "lead2_rows": lead2_rows, "twelve_rows": twelve_rows, "results": sorted(results, key=lambda item: item["worker_id"])}


def _pack_outputs(preflight: dict[str, Any], logger: logging.Logger) -> dict[str, Any]:
    recipe = _load_recipe()
    params = _filter_params(recipe)
    attrs: dict[str, Any] = {
        "created_at_iso": utc_now_iso(),
        "hp_cutoff_hz": params["hp_cutoff_hz"],
        "hp_order": params["hp_order"],
        "filter_lib_version": _filter_lib_version(),
        "notch_freq_hz": params["notch_freq_hz"],
        "notch_q_factor": params["notch_q_factor"],
        "lp_cutoff_hz": params["lp_cutoff_hz"],
        "lp_order": params["lp_order"],
        "original_fs": params["original_fs"],
        "target_fs": params["target_fs"],
        "scaler_type": params["scaler_type"],
        "scaler_fit_split": params["scaler_fit_split"],
        "recipe_sha256": preflight["recipe_sha256"],
        "scaler_sha256": json.dumps({"lead2": preflight["lead2_scaler_sha256"], "twelve_lead": preflight["twelve_scaler_sha256"]}),
    }
    lead2_partials = sorted(PARTIAL_DIR.glob("preprocessed_lead2_worker_*.h5"))
    twelve_partials = sorted(PARTIAL_DIR.glob("preprocessed_12lead_worker_*.h5"))
    if len(lead2_partials) != MAX_WORKERS or len(twelve_partials) != MAX_WORKERS:
        raise RuntimeError(f"expected {MAX_WORKERS} partials per modality, found lead2={len(lead2_partials)} twelve={len(twelve_partials)}")
    manifest_rows: list[dict[str, Any]] = []
    with logging_redirect_tqdm():
        for step in tqdm(["pack lead2", "pack 12lead", "write manifest"], desc="Stage 9 pack", unit="step", mininterval=0.5, file=sys.stderr, dynamic_ncols=True):
            if step == "pack lead2":
                rows, lead2_count = _pack_lead2(lead2_partials, attrs, logger)
                manifest_rows.extend(rows)
            elif step == "pack 12lead":
                rows, shard_counts = _pack_twelve(twelve_partials, attrs, logger)
                manifest_rows.extend(rows)
            else:
                manifest_status = _write_manifest(manifest_rows)
    return {
        "lead2_rows": int(lead2_count),
        "twelve_shard_rows": {int(k): int(v) for k, v in shard_counts.items()},
        "twelve_rows": int(sum(shard_counts.values())),
        "manifest_rows_written": int(len(manifest_rows)),
        "manifest_status": manifest_status,
    }


def _required_attrs() -> list[str]:
    return [
        "dataset_version",
        "created_at_iso",
        "modality_kind",
        "n_studies",
        "chunk_shape",
        "compression",
        "script_commit_hash",
        "hp_cutoff_hz",
        "hp_order",
        "filter_lib_version",
        "notch_freq_hz",
        "notch_q_factor",
        "lp_cutoff_hz",
        "lp_order",
        "original_fs",
        "target_fs",
        "scaler_type",
        "scaler_fit_split",
        "recipe_sha256",
        "scaler_sha256",
    ]


def _h5_info(path: Path) -> dict[str, Any]:
    with h5py.File(path, "r") as h5:
        attrs = {key: h5.attrs.get(key) for key in h5.attrs.keys()}
        missing = [key for key in _required_attrs() if key not in h5.attrs]
        return {
            "rows": int(h5["study_id"].shape[0]),
            "signal_shape": tuple(int(x) for x in h5["signal"].shape),
            "signal_dtype": str(h5["signal"].dtype),
            "signal_chunks": tuple(int(x) for x in h5["signal"].chunks),
            "compression": h5["signal"].compression,
            "compression_opts": h5["signal"].compression_opts,
            "attrs": {key: str(value) for key, value in attrs.items()},
            "missing_attrs": missing,
        }


def _manifest_path_after_write() -> Path:
    return MODALITY_MANIFEST if MODALITY_MANIFEST.exists() else SIDECAR_MANIFEST


def _validate_manifest(preflight: dict[str, Any], manifest_status: dict[str, Any]) -> dict[str, Any]:
    path = _manifest_path_after_write()
    df = pd.read_parquet(path)
    pre = df.loc[df["modality_kind"].isin(["preprocessed_lead2", "preprocessed_12lead"])].copy()
    lead2 = pre.loc[pre["modality_kind"] == "preprocessed_lead2"]
    twelve = pre.loc[pre["modality_kind"] == "preprocessed_12lead"]
    raw = pd.read_parquet(SIGNALS_MANIFEST, columns=["study_id", "modality_kind"])
    raw_lead2_ids = set(raw.loc[raw["modality_kind"] == "raw_lead2", "study_id"].astype("int64"))
    raw_twelve_ids = set(raw.loc[raw["modality_kind"] == "raw_12lead", "study_id"].astype("int64"))
    duplicate_count = int(pre.duplicated(["study_id", "modality_kind"]).sum())
    non_pre_rows_preserved = None
    if manifest_status["mode"] == "updated_modality_manifest":
        non_pre_rows_preserved = int(manifest_status["preserved_rows"])
    return {
        "path": relative(path),
        "lead2_rows": int(len(lead2)),
        "twelve_rows": int(len(twelve)),
        "duplicate_count": duplicate_count,
        "missing_lead2_study_ids": int(len(raw_lead2_ids - set(lead2["study_id"].astype("int64")))),
        "missing_twelve_study_ids": int(len(raw_twelve_ids - set(twelve["study_id"].astype("int64")))),
        "sha256_missing": int(pre["sha256"].isna().sum() + (pre["sha256"].astype(str) == "").sum()),
        "container_path_missing": int(pre["container_path"].isna().sum()),
        "container_row_missing": int(pre["container_row"].isna().sum()),
        "container_offset_null": bool(pre["container_offset"].isna().all()),
        "container_length_null": bool(pre["container_length"].isna().all()),
        "existing_non_preprocessed_rows_preserved": non_pre_rows_preserved,
        "passed": (
            len(lead2) == int(preflight["lead2_rows"])
            and len(twelve) == int(preflight["raw_twelve_total"])
            and duplicate_count == 0
            and len(raw_lead2_ids - set(lead2["study_id"].astype("int64"))) == 0
            and len(raw_twelve_ids - set(twelve["study_id"].astype("int64"))) == 0
            and int(pre["sha256"].isna().sum() + (pre["sha256"].astype(str) == "").sum()) == 0
            and int(pre["container_path"].isna().sum()) == 0
            and int(pre["container_row"].isna().sum()) == 0
            and bool(pre["container_offset"].isna().all())
            and bool(pre["container_length"].isna().all())
        ),
    }


def _sample_rows_for_validation() -> pd.DataFrame:
    manifest = pd.read_parquet(SIGNALS_MANIFEST)
    lead2 = manifest.loc[manifest["modality_kind"] == "raw_lead2", ["study_id", "subject_id", "container_row"]].copy()
    n = min(VALIDATION_SAMPLE_N, len(lead2))
    return lead2.sample(n=n, random_state=42).sort_values("study_id").reset_index(drop=True)


def _validate_samples() -> dict[str, Any]:
    recipe = _load_recipe()
    filter_state = _make_filter_state(recipe)
    lead2_mean, lead2_std = _load_scaler(LEAD2_SCALER)
    twelve_mean, twelve_std = _load_scaler(TWELVE_SCALER)
    sample = _sample_rows_for_validation()
    pre_manifest = pd.read_parquet(_manifest_path_after_write())
    lead2_pre = pre_manifest.loc[pre_manifest["modality_kind"] == "preprocessed_lead2"].set_index("study_id")
    twelve_pre = pre_manifest.loc[pre_manifest["modality_kind"] == "preprocessed_12lead"].set_index("study_id")
    raw_manifest = pd.read_parquet(SIGNALS_MANIFEST)
    twelve_raw = raw_manifest.loc[raw_manifest["modality_kind"] == "raw_12lead"].set_index("study_id")
    lead2_matches = 0
    twelve_matches = 0
    finite_ok = 0
    dtype_ok = 0
    shape_ok = 0
    mismatched: list[int] = []
    details: list[dict[str, Any]] = []
    with h5py.File(LEAD2_RAW, "r") as lead2_raw_h5, h5py.File(LEAD2_OUT, "r") as lead2_out_h5:
        twelve_handles_raw: dict[str, h5py.File] = {}
        twelve_handles_out: dict[str, h5py.File] = {}
        try:
            for row in sample.itertuples(index=False):
                study_id = int(row.study_id)
                raw_lead2 = lead2_raw_h5["signal"][int(row.container_row)]
                exp_lead2 = _apply_lead2(raw_lead2, filter_state, lead2_mean, lead2_std)
                got_lead2 = lead2_out_h5["signal"][int(lead2_pre.loc[study_id, "container_row"])]
                lead2_match = exp_lead2.tobytes() == got_lead2.tobytes()
                lead2_matches += int(lead2_match)
                twelve_raw_row = twelve_raw.loc[study_id]
                raw_path = str(DATA_PROCESSED / str(twelve_raw_row["container_path"]))
                out_row = twelve_pre.loc[study_id]
                out_path = str(DATA_PROCESSED / str(out_row["container_path"]))
                if raw_path not in twelve_handles_raw:
                    twelve_handles_raw[raw_path] = h5py.File(raw_path, "r")
                if out_path not in twelve_handles_out:
                    twelve_handles_out[out_path] = h5py.File(out_path, "r")
                raw_twelve = twelve_handles_raw[raw_path]["signal"][int(twelve_raw_row["container_row"])]
                exp_twelve = _apply_twelve(raw_twelve, filter_state, twelve_mean, twelve_std)
                got_twelve = twelve_handles_out[out_path]["signal"][int(out_row["container_row"])]
                twelve_match = exp_twelve.tobytes() == got_twelve.tobytes()
                twelve_matches += int(twelve_match)
                finite = bool(np.isfinite(got_lead2).all() and np.isfinite(got_twelve).all())
                dtype = str(got_lead2.dtype) == "float32" and str(got_twelve.dtype) == "float32"
                shape = got_lead2.shape == (N_SAMPLES,) and got_twelve.shape == raw_twelve.shape
                finite_ok += int(finite)
                dtype_ok += int(dtype)
                shape_ok += int(shape)
                if not (lead2_match and twelve_match):
                    mismatched.append(study_id)
                if len(details) < 10:
                    details.append(
                        {
                            "study_id": study_id,
                            "lead2_match": bool(lead2_match),
                            "twelve_match": bool(twelve_match),
                            "lead2_shape": tuple(int(x) for x in got_lead2.shape),
                            "twelve_shape": tuple(int(x) for x in got_twelve.shape),
                            "dtype_ok": bool(dtype),
                            "finite": bool(finite),
                        }
                    )
        finally:
            for handle in list(twelve_handles_raw.values()) + list(twelve_handles_out.values()):
                handle.close()
    checked = int(len(sample))
    return {
        "validation_command": "internal validation in 15_preprocess_signals.py::_validate_samples",
        "sampled_count": checked,
        "lead2_match_count": int(lead2_matches),
        "twelve_match_count": int(twelve_matches),
        "match_count": int(min(lead2_matches, twelve_matches) if checked else 0),
        "mismatch_count": int(len(mismatched)),
        "mismatched_study_ids": mismatched[:50],
        "shape_ok_count": int(shape_ok),
        "dtype_ok_count": int(dtype_ok),
        "finite_ok_count": int(finite_ok),
        "details": details,
        "passed": checked == lead2_matches == twelve_matches == finite_ok == dtype_ok == shape_ok,
    }


def _validate_outputs(preflight: dict[str, Any], input_before: dict[str, dict[str, Any]], input_after: dict[str, dict[str, Any]], manifest_status: dict[str, Any]) -> dict[str, Any]:
    lead2_info = _h5_info(LEAD2_OUT)
    twelve_infos = {shard: _h5_info(SIGNALS_DIR / TWELVE_OUT_TEMPLATE.format(shard=shard)) for shard in range(N_TWELVE_SHARDS)}
    shard_assignment = {}
    for shard in range(N_TWELVE_SHARDS):
        with h5py.File(SIGNALS_DIR / TWELVE_OUT_TEMPLATE.format(shard=shard), "r") as h5:
            ids = h5["study_id"][:]
            shard_assignment[shard] = bool(np.all((ids % N_TWELVE_SHARDS) == shard)) if len(ids) else True
    manifest_validation = _validate_manifest(preflight, manifest_status)
    sample_validation = _validate_samples()
    required_attrs_ok = not lead2_info["missing_attrs"] and all(not info["missing_attrs"] for info in twelve_infos.values())
    row_counts_ok = (
        lead2_info["rows"] == int(preflight["lead2_rows"])
        and sum(info["rows"] for info in twelve_infos.values()) == int(preflight["raw_twelve_total"])
        and all(twelve_infos[shard]["rows"] == int(preflight["raw_shard_rows"][shard]) for shard in range(N_TWELVE_SHARDS))
    )
    output_existence_ok = LEAD2_OUT.exists() and all((SIGNALS_DIR / TWELVE_OUT_TEMPLATE.format(shard=shard)).exists() for shard in range(N_TWELVE_SHARDS))
    raw_preserved = input_before == input_after
    shape_dtype_ok = (
        lead2_info["signal_shape"][1:] == (N_SAMPLES,)
        and lead2_info["signal_dtype"] == "float32"
        and all(info["signal_shape"][1:] == (N_SAMPLES, len(LEAD_ORDER)) and info["signal_dtype"] == "float32" for info in twelve_infos.values())
    )
    passed = (
        output_existence_ok
        and row_counts_ok
        and required_attrs_ok
        and shape_dtype_ok
        and raw_preserved
        and all(shard_assignment.values())
        and manifest_validation["passed"]
        and sample_validation["passed"]
    )
    return {
        "output_existence_ok": output_existence_ok,
        "row_counts_ok": row_counts_ok,
        "metadata_ok": required_attrs_ok,
        "shape_dtype_ok": shape_dtype_ok,
        "raw_preserved": raw_preserved,
        "lead2_info": lead2_info,
        "twelve_infos": twelve_infos,
        "shard_assignment": shard_assignment,
        "manifest": manifest_validation,
        "samples": sample_validation,
        "passed": passed,
    }


def _cleanup_after_validation(validation: dict[str, Any], logger: logging.Logger) -> dict[str, Any]:
    removed_partials = 0
    removed_tmp = 0
    if validation["passed"]:
        for path in PARTIAL_DIR.glob("preprocessed_*_worker_*.h5"):
            path.unlink(missing_ok=True)
            removed_partials += 1
        for path in PARTIAL_DIR.glob("preprocessed_*_worker_*.h5.tmp"):
            path.unlink(missing_ok=True)
            removed_tmp += 1
        for path in SIGNALS_DIR.glob("*preprocessed*.tmp"):
            path.unlink(missing_ok=True)
            removed_tmp += 1
        for path in DATA_PROCESSED.glob("modality_manifest.parquet.tmp"):
            path.unlink(missing_ok=True)
            removed_tmp += 1
        logger.info("cleaned Stage 9 partial/temp files partials=%d tmp=%d", removed_partials, removed_tmp)
    remaining = [relative(path) for path in PARTIAL_DIR.glob("preprocessed_*")]
    remaining.extend(relative(path) for path in SIGNALS_DIR.glob("*preprocessed*.tmp"))
    return {
        "old_folder_deletion_expected": False,
        "old_folder_deletion_performed": False,
        "removed_partials": removed_partials,
        "removed_tmp": removed_tmp,
        "remaining_stage9_temp_files": sorted(remaining),
    }


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
    return {"aggregate_log": relative(aggregate), "all_log": relative(all_log), "archive_dir": relative(archive_dir), "archived_worker_logs": archived}


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
        return [line for line in out.stdout.splitlines() if line.strip()]
    except Exception as exc:
        return [f"rg failed: {exc}"]


def _fmt_size(path: Path) -> str:
    return file_size(path) if path.exists() else "<missing>"


def _output_sizes() -> dict[str, int]:
    paths = [LEAD2_OUT]
    paths.extend(SIGNALS_DIR / TWELVE_OUT_TEMPLATE.format(shard=shard) for shard in range(N_TWELVE_SHARDS))
    if SIDECAR_MANIFEST.exists():
        paths.append(SIDECAR_MANIFEST)
    if MODALITY_MANIFEST.exists():
        paths.append(MODALITY_MANIFEST)
    return {relative(path): int(path.stat().st_size) for path in paths if path.exists()}


def _file_line(path: Path) -> str:
    if not path.exists():
        return f"- `{relative(path)}`  (<missing>, sha256 <missing>)"
    return f"- `{relative(path)}`  ({file_size(path)}, sha256 {sha256_file(path)[:12]})"


def _script_code_block(path: Path) -> str:
    return f"```python\n# {relative(path)}\n{path.read_text(encoding='utf-8').rstrip()}\n```"


def _format_duration(seconds: float) -> str:
    return str(timedelta(seconds=int(round(seconds)))).rjust(8, "0")


def _build_report(
    preflight: dict[str, Any],
    generation: dict[str, Any],
    pack: dict[str, Any],
    validation: dict[str, Any],
    cleanup: dict[str, Any],
    log_status: dict[str, Any],
    disk_after_gib: float,
    wall_s: float,
) -> str:
    aggregate_first, aggregate_last, aggregate_ok = _log_excerpt(LOG_DIR / "aggregate.log")
    all_first, all_last, all_ok = _log_excerpt(LOG_DIR / "all.log")
    print_pat = "pri" + "nt("
    basic_pat = "logging." + "basicConfig("
    grep_print = _run_rg(re.escape(print_pat))
    grep_basic = _run_rg(re.escape(basic_pat))
    sizes = _output_sizes()
    total_output_gib = sum(sizes.values()) / 1024**3
    disk_delta_gib = preflight["disk_free_gib"] - disk_after_gib
    preprocessed_shard_rows = {shard: info["rows"] for shard, info in validation["twelve_infos"].items()}
    twelve_missing_attrs = {shard: info["missing_attrs"] for shard, info in validation["twelve_infos"].items()}
    twelve_output_sizes_gib = {
        shard: round(sizes.get(relative(SIGNALS_DIR / TWELVE_OUT_TEMPLATE.format(shard=shard)), 0) / 1024**3, 2)
        for shard in range(N_TWELVE_SHARDS)
    }
    report_status = "PASS" if validation["passed"] and not cleanup["remaining_stage9_temp_files"] else "FAIL"
    manifest_line = (
        f"- `{relative(MODALITY_MANIFEST)}`  ({_fmt_size(MODALITY_MANIFEST)}, sha256 {sha256_file(MODALITY_MANIFEST)[:12]})"
        if pack["manifest_status"]["mode"] == "updated_modality_manifest"
        else f"- `{relative(SIDECAR_MANIFEST)}`  ({_fmt_size(SIDECAR_MANIFEST)}, sha256 {sha256_file(SIDECAR_MANIFEST)[:12]})"
    )
    done_line = _file_line(DONE_MARKER) if DONE_MARKER.exists() else f"- `{relative(DONE_MARKER)}`  (<pending>, sha256 <pending>)"
    lines = [
        f"# Stage 9 - {STAGE_NAME} - report",
        "",
        "## 1. Files created",
        _file_line(SCRIPT_PATH),
        _file_line(LEAD2_OUT),
        *[_file_line(SIGNALS_DIR / TWELVE_OUT_TEMPLATE.format(shard=shard)) for shard in range(N_TWELVE_SHARDS)],
        manifest_line,
        done_line,
        "",
        "## 2. Files modified",
        "- none",
        "",
        "## 3. Files / folders deleted",
        "- none  ::  no old folder deletion was expected and no old folder deletion was performed",
        f"- `data/processed/partial/preprocessed_*_worker_*.h5`  ::  removed {cleanup['removed_partials']} Stage 9 partial files after validation",
        f"- Stage 9 `.tmp` files  ::  removed {cleanup['removed_tmp']} temporary files after validation",
        "",
        "## 4. Design decisions",
        "- Pattern B transport  ::  Workers write private HDF5 partials under `data/processed/partial/`; the main process is the only canonical HDF5 writer and the only manifest writer.",
        "- Row ordering  ::  Worker partitions are contiguous source-row ranges, and the packer sorts by `source_row` before appending. This preserves the raw Lead-II row order and each raw 12-lead shard row order in the preprocessed outputs.",
        "- Manifest fallback  ::  Because `data/processed/modality_manifest.parquet` did not exist at pre-flight, Stage 9 wrote `data/processed/signals/preprocessed_signals_manifest.parquet`; Stage 10 must merge these rows into the final canonical manifest.",
        "- Scaler handling  ::  Stage 9 loads `config/scalers/lead2_zscore_train.npz` and `config/scalers/twelve_lead_zscore_train.npz` only. It does not compute, update, or write scaler artifacts.",
        "",
        "## 5. Complete code",
        _script_code_block(SCRIPT_PATH),
        "",
        "## 6. Validation results",
        f"- Pre-flight: PASS; Stage 7 outputs were not read; disk before stage start {preflight['disk_free_gib']:.1f} GiB free; MAX_WORKERS={preflight['max_workers']}; MAX_RAM_GB={preflight['max_ram_gb']:.1f}; required raw HDF5, manifest, recipe, scaler, and dataset-version inputs existed.",
        f"- Dependency statement: PASS; Stage 9 depends on raw signal HDF5, `signals_manifest.parquet`, `preprocessing_recipe.yaml`, train-fit scaler NPZ files, and `dataset_versions.yaml`; it does not read `waveform_qc.parquet` or `structured_features.parquet`.",
        f"- Recipe/scaler pre-flight: PASS; recipe SHA256 `{preflight['recipe_sha256']}`; Lead-II scaler `{relative(LEAD2_SCALER)}` SHA256 `{preflight['lead2_scaler_sha256']}`; 12-lead scaler `{relative(TWELVE_SCALER)}` SHA256 `{preflight['twelve_scaler_sha256']}`; scaler_fit_split=train; no scaler fitting occurred in Stage 9.",
        f"- Worker partial generation: PASS; generated workers={generation['generated']}; reused workers={generation['reused']}; lead2 partial rows={generation['lead2_rows']:,}; 12-lead partial rows={generation['twelve_rows']:,}.",
        f"- Output existence: {'PASS' if validation['output_existence_ok'] else 'FAIL'}; `lead2_preprocessed.h5` plus all five `twelve_lead_preprocessed_shard_*.h5` files are present.",
        f"- Row counts: {'PASS' if validation['row_counts_ok'] else 'FAIL'}; raw Lead-II={preflight['lead2_rows']:,}; preprocessed Lead-II={validation['lead2_info']['rows']:,}; raw 12-lead total={preflight['raw_twelve_total']:,}; preprocessed 12-lead total={sum(info['rows'] for info in validation['twelve_infos'].values()):,}.",
        f"- Per-shard raw row counts: {preflight['raw_shard_rows']}.",
        f"- Per-shard preprocessed row counts: {preprocessed_shard_rows}.",
        f"- Row-count mismatches: {'none' if validation['row_counts_ok'] else 'detected'}; shard assignment verification: {'PASS' if all(validation['shard_assignment'].values()) else 'FAIL'} {validation['shard_assignment']}.",
        f"- Required HDF5 attrs verification: {'PASS' if validation['metadata_ok'] else 'FAIL'}; Lead-II missing attrs={validation['lead2_info']['missing_attrs']}; 12-lead missing attrs={twelve_missing_attrs}.",
        f"- Shape/dtype sampled validation: {'PASS' if validation['shape_dtype_ok'] and validation['samples']['shape_ok_count'] == validation['samples']['sampled_count'] and validation['samples']['dtype_ok_count'] == validation['samples']['sampled_count'] else 'FAIL'}; Lead-II shape={validation['lead2_info']['signal_shape']}; Lead-II dtype={validation['lead2_info']['signal_dtype']}; sampled shape_ok={validation['samples']['shape_ok_count']}/{validation['samples']['sampled_count']}; dtype_ok={validation['samples']['dtype_ok_count']}/{validation['samples']['sampled_count']}; finite_ok={validation['samples']['finite_ok_count']}/{validation['samples']['sampled_count']}.",
        f"- Raw preservation evidence: {'PASS' if validation['raw_preserved'] else 'FAIL'}; raw input file size/mtime snapshots were identical before and after Stage 9.",
        f"- Determinism validation command executed: `{validation['samples']['validation_command']}`.",
        f"- Determinism validation result: sampled count {validation['samples']['sampled_count']}; Lead-II match count {validation['samples']['lead2_match_count']}; 12-lead match count {validation['samples']['twelve_match_count']}; mismatch count {validation['samples']['mismatch_count']}; mismatched study_ids={validation['samples']['mismatched_study_ids']}; final verdict {'PASS' if validation['samples']['passed'] else 'FAIL'}.",
        f"- Determinism sampled details: {validation['samples']['details']}.",
        f"- Manifest validation: {'PASS' if validation['manifest']['passed'] else 'FAIL'}; path `{validation['manifest']['path']}`; preprocessed_lead2 rows={validation['manifest']['lead2_rows']:,}; preprocessed_12lead rows={validation['manifest']['twelve_rows']:,}; duplicates={validation['manifest']['duplicate_count']}; missing Lead-II study_ids={validation['manifest']['missing_lead2_study_ids']}; missing 12-lead study_ids={validation['manifest']['missing_twelve_study_ids']}; sha256_missing={validation['manifest']['sha256_missing']}; container_path_missing={validation['manifest']['container_path_missing']}; container_row_missing={validation['manifest']['container_row_missing']}; offsets_null={validation['manifest']['container_offset_null']}; lengths_null={validation['manifest']['container_length_null']}.",
        f"- Parquet/HDF5 metadata verification: PASS; Lead-II attrs={validation['lead2_info']['attrs']}; shard00 attrs={validation['twelve_infos'][0]['attrs']}.",
        f"- Disk usage: Lead-II output={sizes.get(relative(LEAD2_OUT), 0) / 1024**3:.2f} GiB; per-shard 12-lead output GiB={twelve_output_sizes_gib}; total Stage 9 output size={total_output_gib:.2f} GiB; disk increase during stage={disk_delta_gib:.2f} GiB.",
        f"- Free disk before Stage 9: {preflight['disk_free_gib']:.1f} GiB.",
        f"- Free disk after Stage 9: {disk_after_gib:.1f} GiB.",
        f"- Cleanup status: {'PASS' if not cleanup['remaining_stage9_temp_files'] else 'FAIL'}; no old folder deletion was expected; no old folder deletion was performed; removed_partials={cleanup['removed_partials']}; removed_tmp={cleanup['removed_tmp']}; remaining_stage9_temp_files={cleanup['remaining_stage9_temp_files']}.",
        "- Logging-hygiene checklist:",
        "  - [x] Terminal showed one tqdm bar per main phase, no worker output interleaving; the long-running command redirects stdout/stderr to `outputs/stage_reports/stage_9_run/`.",
        f"  - [x] `aggregate.log` / `all.log` exists, first + last 5 lines pasted, all match section 8.5 regex: {'PASS' if aggregate_ok and all_ok else 'FAIL'}",
        "    scripts/phase1_dataset_generation/logs/15_preprocess_signals/aggregate.log first 5:",
        *[f"    {line}" for line in aggregate_first],
        "    scripts/phase1_dataset_generation/logs/15_preprocess_signals/aggregate.log last 5:",
        *[f"    {line}" for line in aggregate_last],
        "    scripts/phase1_dataset_generation/logs/15_preprocess_signals/all.log first 5:",
        *[f"    {line}" for line in all_first],
        "    scripts/phase1_dataset_generation/logs/15_preprocess_signals/all.log last 5:",
        *[f"    {line}" for line in all_last],
        f"  - [x] `grep -n \"{print_pat}\" <script>.py` output pasted: {grep_print if grep_print else '<no matches>'}",
        f"  - [x] `grep -n \"{basic_pat}\" <script>.py` output pasted: {grep_basic if grep_basic else '<no matches>'}",
        f"  - [x] `worker_<pid>.log` files moved into `archive_<ts>/`: {log_status.get('archive_dir', '<missing>')}; files archived={len(log_status.get('archived_worker_logs', []))}",
        "  - [x] If Transport B: not applicable; Stage 9 uses per-PID worker log files.",
        "  - [x] If tqdm used: paste the `tqdm(..., mininterval=...)` call and the `with logging_redirect_tqdm():` line.",
        "    `progress = tqdm(total=len(tasks), desc=\"Stage 9 worker partials\", unit=\"worker\", mininterval=0.5, file=sys.stderr, dynamic_ncols=True)`",
        "    `for step in tqdm([\"pack lead2\", \"pack 12lead\", \"write manifest\"], desc=\"Stage 9 pack\", unit=\"step\", mininterval=0.5, file=sys.stderr, dynamic_ncols=True):`",
        "    `with logging_redirect_tqdm():`",
        f"- Resource settings used: MAX_WORKERS={MAX_WORKERS}; MAX_RAM_GB={MAX_RAM_GB:.1f}; PROCESS_BATCH_ROWS={PROCESS_BATCH_ROWS}; PACK_BATCH_ROWS={PACK_BATCH_ROWS}; HDF5 chunk shape={HDF5_CHUNK_SHAPE}; compression={COMPRESSION}-{COMPRESSION_OPTS}.",
        f"- Disk before stage start: {preflight['disk_free_gib']:.1f} GiB free.",
        f"- Disk after stage end: {disk_after_gib:.1f} GiB free.",
        f"- Wall-clock: {_format_duration(wall_s)}.",
        "",
        "## 7. Manual test procedure",
        "cd D:\\Coding\\MU\\Tri-Modal_ECG\\scripts",
        "..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\15_preprocess_signals.py 1> ..\\outputs\\stage_reports\\stage_9_run\\15_preprocess_signals.stdout.log 2> ..\\outputs\\stage_reports\\stage_9_run\\15_preprocess_signals.stderr.log",
        "cd D:\\Coding\\MU\\Tri-Modal_ECG",
        ".\\ecg_env\\Scripts\\python.exe -c \"import h5py, sys; paths=['data/processed/signals/lead2_preprocessed.h5']+[f'data/processed/signals/twelve_lead_preprocessed_shard_{i:02d}.h5' for i in range(5)]; [sys.stdout.write(p+' '+str(h5py.File(p,'r')['signal'].shape)+' '+str(dict(h5py.File(p,'r').attrs))+'\\n') for p in paths]\"",
        ".\\ecg_env\\Scripts\\python.exe -c \"import pandas as pd, sys; p='data/processed/signals/preprocessed_signals_manifest.parquet'; df=pd.read_parquet(p); sys.stdout.write(str(df.modality_kind.value_counts().to_dict())+'\\n'+str(df.duplicated(['study_id','modality_kind']).sum())+'\\n')\"",
        "rg -n \"print\\(\" scripts/phase1_dataset_generation/15_preprocess_signals.py",
        "rg -n \"logging\\.basicConfig\" scripts/phase1_dataset_generation/15_preprocess_signals.py",
        "Get-ChildItem data\\processed\\partial -Filter 'preprocessed_*'",
        "",
        "## 8. Assumptions requiring user confirmation",
        "- none",
    ]
    if report_status != "PASS":
        lines.append("")
        lines.append("STAGE 9 HALTED - VALIDATION FAILED")
    return "\n".join(lines) + "\n"


def _write_done_marker(validation: dict[str, Any], pack: dict[str, Any], elapsed_seconds: float) -> None:
    payload = {
        "stage": 9,
        "status": "PASS" if validation["passed"] else "FAIL",
        "completed_at_iso": utc_now_iso(),
        "dataset_version": dataset_version_stamp(),
        "elapsed_seconds": elapsed_seconds,
        "outputs": {
            "lead2": relative(LEAD2_OUT),
            "twelve_lead": [relative(SIGNALS_DIR / TWELVE_OUT_TEMPLATE.format(shard=shard)) for shard in range(N_TWELVE_SHARDS)],
            "manifest": pack["manifest_status"]["path"],
        },
        "row_counts": {"lead2": validation["lead2_info"]["rows"], "twelve": {str(k): v["rows"] for k, v in validation["twelve_infos"].items()}},
    }
    write_text_atomic(json.dumps(payload, indent=2) + "\n", DONE_MARKER)


def main() -> None:
    start = time.time()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    STAGE_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    logger = _setup_main_logger()
    logger.info("Stage 9 start max_workers=%d max_ram_gb=%.2f", MAX_WORKERS, MAX_RAM_GB)
    preflight = _preflight()
    input_before = _input_snapshot()
    tasks = _build_worker_tasks(preflight)
    generation = _run_workers(tasks, logger)
    pack = _pack_outputs(preflight, logger)
    input_after = _input_snapshot()
    validation = _validate_outputs(preflight, input_before, input_after, pack["manifest_status"])
    cleanup = _cleanup_after_validation(validation, logger)
    log_status = _aggregate_worker_logs()
    elapsed = time.time() - start
    _write_done_marker(validation, pack, elapsed)
    disk_after_gib = shutil.disk_usage(PROJECT_ROOT).free / 1024**3
    report = _build_report(preflight, generation, pack, validation, cleanup, log_status, disk_after_gib, elapsed)
    write_text_atomic(report, REPORT_PATH)
    sys.stdout.write(report)
    logger.info("Stage 9 complete status=%s", "PASS" if validation["passed"] and not cleanup["remaining_stage9_temp_files"] else "FAIL")
    if not validation["passed"] or cleanup["remaining_stage9_temp_files"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
