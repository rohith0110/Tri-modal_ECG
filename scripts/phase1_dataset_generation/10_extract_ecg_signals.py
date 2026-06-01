#!/usr/bin/env python3
"""Stage 3.A: extract raw ECG signals into private worker HDF5 partials.

Pattern B implementation:
- workers write only their own private partial HDF5 files under
  data/processed/partial/
- workers return signal_metadata rows to the main process
- the main process writes the worker-returned metadata snapshot for the
  offline packer
- workers never write canonical HDF5 files, manifests, offsets, or shared
  containers

Run from the repository root or from scripts/phase1_dataset_generation:
    ..\\..\\ecg_env\\Scripts\\python.exe 10_extract_ecg_signals.py
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import math
import os
import sys
import time
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd
import psutil
import pyarrow as pa
import pyarrow.parquet as pq
import wfdb
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from _stage1_common import (
    DATA_PROCESSED,
    DATA_RAW,
    LOG_FORMATTER,
    PROJECT_ROOT,
    SCRIPT_DIR,
    STAGE_REPORT_DIR,
    dataset_version_stamp,
    script_commit_hash,
    silence_noisy_libs,
    utc_now_iso,
)

SCRIPT_NAME = Path(__file__).stem
LOG_DIR = SCRIPT_DIR / "logs" / SCRIPT_NAME
PARTIAL_DIR = DATA_PROCESSED / "partial"
INDEX_PATH = DATA_PROCESSED / "index" / "ecg_metadata.parquet"
METADATA_RETURNS_PATH = PARTIAL_DIR / "signal_metadata_worker_returns.parquet"
DONE_MARKER = STAGE_REPORT_DIR / "stage_3_10_extract_ecg_signals.done.json"
STAGE_STATE_PATH = STAGE_REPORT_DIR / "stage_3_state.json"

LEAD_ORDER = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
SAMPLES_PER_RECORD = 5000
HDF5_CHUNK_SHAPE = (64, 5000)
COMPRESSION = "gzip"
COMPRESSION_OPTS = 4
BATCH_SIZE = 32
MAX_WORKERS = max(1, math.floor((os.cpu_count() or 1) * 0.75))
MAX_RAM_GB = max(1.0, psutil.virtual_memory().total / 1024**3 - 8.0)

_worker_tqdm_file = None


def _setup_main_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for old in LOG_DIR.glob("worker_*.log"):
        for attempt in range(20):
            try:
                old.unlink()
                break
            except PermissionError:
                if attempt == 19:
                    stale_dir = LOG_DIR / f"stale_locked_{time.strftime('%Y%m%d_%H%M%S')}"
                    stale_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(old, stale_dir / old.name)
                    logging.getLogger("main").warning("copied locked stale worker log path=%s", old)
                else:
                    time.sleep(0.5)
    for name in ("main.log", "aggregate.log"):
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
    global _worker_tqdm_file
    log_path = Path(log_dir) / f"worker_{os.getpid()}.log"
    original_stderr_fd = os.dup(2)
    _worker_tqdm_file = os.fdopen(original_stderr_fd, "w", buffering=1)
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)
    sys.stdout = os.fdopen(1, "w", buffering=1)
    sys.stderr = os.fdopen(2, "w", buffering=1)
    root = logging.getLogger()
    root.handlers.clear()
    file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    file_handler.setFormatter(LOG_FORMATTER)
    root.addHandler(file_handler)
    root.setLevel(logging.INFO)
    silence_noisy_libs()


def _aggregate_worker_logs() -> Path | None:
    pid_files = sorted(LOG_DIR.glob("worker_*.log"))
    if not pid_files:
        return None
    aggregate = LOG_DIR / "aggregate.log"
    with aggregate.open("w", encoding="utf-8", newline="\n") as dst:
        for path in pid_files:
            text = path.read_text(encoding="utf-8", errors="replace")
            if text and not text.endswith("\n"):
                text += "\n"
            dst.write(text)
    archive = LOG_DIR / f"archive_{time.strftime('%Y%m%d_%H%M%S')}"
    archive.mkdir(parents=True, exist_ok=False)
    for path in pid_files:
        target = archive / path.name
        for attempt in range(20):
            try:
                path.replace(target)
                break
            except PermissionError:
                if attempt == 19:
                    shutil.copy2(path, target)
                    try:
                        path.unlink()
                    except PermissionError:
                        logging.getLogger("main").warning("worker log remained locked after archive copy path=%s", path)
                else:
                    time.sleep(0.5)
    return archive


def _create_partial_file(path: Path, signal_shape: tuple[int, ...], chunk_shape: tuple[int, ...]) -> h5py.File:
    path.parent.mkdir(parents=True, exist_ok=True)
    h5 = h5py.File(path, "a")
    if "signal" not in h5:
        h5.create_dataset(
            "signal",
            shape=(0, *signal_shape),
            maxshape=(None, *signal_shape),
            dtype="float32",
            chunks=chunk_shape,
            compression=COMPRESSION,
            compression_opts=COMPRESSION_OPTS,
            shuffle=True,
        )
        h5.create_dataset("study_id", shape=(0,), maxshape=(None,), dtype="int64", chunks=(4096,))
        h5.create_dataset("subject_id", shape=(0,), maxshape=(None,), dtype="int64", chunks=(4096,))
        h5.attrs["dataset_version"] = dataset_version_stamp()
        h5.attrs["created_at_iso"] = utc_now_iso()
        h5.attrs["modality_kind"] = "worker_partial"
        h5.attrs["chunk_shape"] = json.dumps(HDF5_CHUNK_SHAPE)
        h5.attrs["compression"] = f"{COMPRESSION}-{COMPRESSION_OPTS}"
        h5.attrs["script_commit_hash"] = script_commit_hash()
        h5.attrs["lead_order"] = json.dumps(LEAD_ORDER)
    return h5


def _ensure_lead2_metadata_datasets(h5: h5py.File) -> None:
    n = int(h5["study_id"].shape[0])
    string_dtype = h5py.string_dtype(encoding="utf-8")
    specs = {
        "raw_path": string_dtype,
        "lead_names": string_dtype,
        "num_samples": "int32",
        "num_leads": "int16",
        "missing_values": "int64",
        "waveform_ok": "bool",
    }
    for name, dtype in specs.items():
        if name not in h5:
            h5.create_dataset(name, shape=(n,), maxshape=(None,), dtype=dtype, chunks=(4096,))


def _resize_1d(ds: h5py.Dataset, new_size: int) -> None:
    ds.resize((new_size,))


def _append_batch(lead2_h5: h5py.File, twelve_h5: h5py.File, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    start = int(lead2_h5["study_id"].shape[0])
    end = start + len(rows)
    for h5 in (lead2_h5, twelve_h5):
        h5["signal"].resize((end, *h5["signal"].shape[1:]))
        _resize_1d(h5["study_id"], end)
        _resize_1d(h5["subject_id"], end)
    _ensure_lead2_metadata_datasets(lead2_h5)
    for name in ("raw_path", "lead_names", "num_samples", "num_leads", "missing_values", "waveform_ok"):
        _resize_1d(lead2_h5[name], end)

    lead2_h5["signal"][start:end] = np.stack([row["lead2"] for row in rows]).astype("float32", copy=False)
    twelve_h5["signal"][start:end] = np.stack([row["twelve"] for row in rows]).astype("float32", copy=False)
    study_ids = np.asarray([row["study_id"] for row in rows], dtype="int64")
    subject_ids = np.asarray([row["subject_id"] for row in rows], dtype="int64")
    for h5 in (lead2_h5, twelve_h5):
        h5["study_id"][start:end] = study_ids
        h5["subject_id"][start:end] = subject_ids
    lead2_h5["raw_path"][start:end] = [row["raw_path"] for row in rows]
    lead2_h5["lead_names"][start:end] = [json.dumps(row["lead_names"]) for row in rows]
    lead2_h5["num_samples"][start:end] = np.asarray([row["num_samples"] for row in rows], dtype="int32")
    lead2_h5["num_leads"][start:end] = np.asarray([row["num_leads"] for row in rows], dtype="int16")
    lead2_h5["missing_values"][start:end] = np.asarray([row["missing_values"] for row in rows], dtype="int64")
    lead2_h5["waveform_ok"][start:end] = np.asarray([row["waveform_ok"] for row in rows], dtype="bool")
    lead2_h5.flush()
    twelve_h5.flush()


def _metadata_from_partial(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        with h5py.File(path, "r") as h5:
            _ensure_readable_metadata(h5)
            n = int(h5["study_id"].shape[0])
            for i in range(n):
                out.append(
                    {
                        "study_id": int(h5["study_id"][i]),
                        "subject_id": int(h5["subject_id"][i]),
                        "raw_path": _decode_h5_string(h5["raw_path"][i]),
                        "num_samples": int(h5["num_samples"][i]),
                        "num_leads": int(h5["num_leads"][i]),
                        "missing_values": int(h5["missing_values"][i]),
                        "waveform_ok": bool(h5["waveform_ok"][i]),
                        "lead_names": _decode_h5_string(h5["lead_names"][i]),
                        "dataset_version": dataset_version_stamp(),
                    }
                )
    except OSError:
        corrupt = path.with_suffix(path.suffix + f".corrupt_{int(time.time())}")
        path.replace(corrupt)
        logging.getLogger("worker").warning("partial file was unreadable and was renamed path=%s corrupt_path=%s", path, corrupt)
    return out


def _ensure_readable_metadata(h5: h5py.File) -> None:
    required = {"raw_path", "lead_names", "num_samples", "num_leads", "missing_values", "waveform_ok"}
    missing = sorted(required - set(h5.keys()))
    if missing:
        raise OSError(f"partial metadata datasets missing: {missing}")


def _decode_h5_string(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _completed_study_ids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    try:
        with h5py.File(path, "r") as h5:
            return set(int(x) for x in h5["study_id"][:])
    except OSError:
        corrupt = path.with_suffix(path.suffix + f".corrupt_{int(time.time())}")
        path.replace(corrupt)
        logging.getLogger("worker").warning("partial file was unreadable and was renamed path=%s corrupt_path=%s", path, corrupt)
        return set()


def _cooperative_ram_throttle(process: psutil.Process) -> None:
    limit_gb = (MAX_RAM_GB / MAX_WORKERS) * 1.5
    while process.memory_info().rss / 1024**3 > limit_gb:
        logging.getLogger("worker").warning(
            "worker ram throttle rss_gb=%.2f limit_gb=%.2f",
            process.memory_info().rss / 1024**3,
            limit_gb,
        )
        time.sleep(2)


def _load_partition(worker_id: int, worker_count: int) -> pd.DataFrame:
    df = pd.read_parquet(INDEX_PATH, columns=["study_id", "subject_id", "path"])
    df = df.sort_values("study_id").reset_index(drop=True)
    return df.iloc[worker_id::worker_count].reset_index(drop=True)


def _extract_one(row: Any) -> dict[str, Any]:
    study_id = int(row.study_id)
    subject_id = int(row.subject_id)
    raw_path = str(row.path).replace("\\", "/")
    record_path = DATA_RAW / raw_path
    record = wfdb.rdrecord(str(record_path))
    signal = record.p_signal
    if signal is None:
        raise ValueError("wfdb returned no p_signal")
    signal = np.asarray(signal, dtype="float32")
    lead_names = [str(x) for x in record.sig_name]
    if signal.ndim != 2:
        raise ValueError(f"unexpected signal ndim={signal.ndim}")
    if signal.shape[0] != SAMPLES_PER_RECORD:
        raise ValueError(f"bad length samples={signal.shape[0]}")
    missing = sorted(set(LEAD_ORDER) - set(lead_names))
    if missing:
        raise ValueError(f"missing required leads={missing}")
    if signal.shape[1] != len(lead_names):
        raise ValueError(f"lead name count mismatch signal_cols={signal.shape[1]} lead_names={len(lead_names)}")
    lead_index = {name: idx for idx, name in enumerate(lead_names)}
    ordered = np.stack([signal[:, lead_index[name]] for name in LEAD_ORDER], axis=1).astype("float32", copy=False)
    lead2 = ordered[:, LEAD_ORDER.index("II")].astype("float32", copy=False)
    missing_values = int(np.isnan(ordered).sum() + np.isinf(ordered).sum())
    return {
        "study_id": study_id,
        "subject_id": subject_id,
        "raw_path": raw_path,
        "lead_names": LEAD_ORDER,
        "num_samples": int(ordered.shape[0]),
        "num_leads": int(ordered.shape[1]),
        "missing_values": missing_values,
        "waveform_ok": missing_values == 0,
        "lead2": lead2,
        "twelve": ordered,
    }


def _worker_partition(worker_id: int, worker_count: int) -> dict[str, Any]:
    log = logging.getLogger("worker")
    process = psutil.Process(os.getpid())
    lead2_path = PARTIAL_DIR / f"lead2_worker_{worker_id:03d}.h5"
    twelve_path = PARTIAL_DIR / f"twelve_lead_worker_{worker_id:03d}.h5"
    partition = _load_partition(worker_id, worker_count)
    completed = _completed_study_ids(lead2_path)
    if twelve_path.exists():
        twelve_completed = _completed_study_ids(twelve_path)
        if completed != twelve_completed:
            raise RuntimeError(f"partial mismatch worker_id={worker_id} lead2={len(completed)} twelve={len(twelve_completed)}")

    stats = {
        "worker_id": worker_id,
        "pid": os.getpid(),
        "assigned": int(len(partition)),
        "existing": int(len(completed)),
        "ok": 0,
        "skipped": 0,
        "error": 0,
    }
    pending: list[dict[str, Any]] = []
    started = time.time()
    metadata_rows = _metadata_from_partial(lead2_path)

    with _create_partial_file(lead2_path, (SAMPLES_PER_RECORD,), HDF5_CHUNK_SHAPE) as lead2_h5, _create_partial_file(
        twelve_path,
        (SAMPLES_PER_RECORD, len(LEAD_ORDER)),
        (HDF5_CHUNK_SHAPE[0], HDF5_CHUNK_SHAPE[1], 1),
    ) as twelve_h5:
        _ensure_lead2_metadata_datasets(lead2_h5)
        remaining = max(0, len(partition) - len(completed))
        with tqdm(
            total=remaining,
            position=worker_id,
            desc=f"worker {worker_id:02d}",
            leave=False,
            file=_worker_tqdm_file or sys.stderr,
            dynamic_ncols=True,
            mininterval=0.5,
        ) as bar:
            for idx, row in enumerate(partition.itertuples(index=False), start=1):
                study_id = int(row.study_id)
                if study_id in completed:
                    stats["skipped"] += 1
                    continue
                try:
                    extracted = _extract_one(row)
                    metadata_rows.append(
                        {
                            "study_id": extracted["study_id"],
                            "subject_id": extracted["subject_id"],
                            "raw_path": extracted["raw_path"],
                            "num_samples": extracted["num_samples"],
                            "num_leads": extracted["num_leads"],
                            "missing_values": extracted["missing_values"],
                            "waveform_ok": extracted["waveform_ok"],
                            "lead_names": json.dumps(extracted["lead_names"]),
                            "dataset_version": dataset_version_stamp(),
                        }
                    )
                    pending.append(extracted)
                    completed.add(study_id)
                    stats["ok"] += 1
                    if len(pending) >= BATCH_SIZE:
                        _append_batch(lead2_h5, twelve_h5, pending)
                        pending.clear()
                        _cooperative_ram_throttle(process)
                except Exception as exc:
                    stats["error"] += 1
                    log.exception("study_id=%s extraction failed: %s", study_id, exc)
                finally:
                    bar.update(1)
                if idx % 5000 == 0:
                    log.info(
                        "worker_id=%s progress assigned_done=%d assigned_total=%d ok=%d skipped=%d error=%d elapsed_seconds=%.1f",
                        worker_id,
                        idx,
                        len(partition),
                        stats["ok"],
                        stats["skipped"],
                        stats["error"],
                        time.time() - started,
                    )
        if pending:
            _append_batch(lead2_h5, twelve_h5, pending)
            pending.clear()
        lead2_h5.attrs["n_studies"] = int(lead2_h5["study_id"].shape[0])
        twelve_h5.attrs["n_studies"] = int(twelve_h5["study_id"].shape[0])
        lead2_h5.flush()
        twelve_h5.flush()

    stats["metadata_rows"] = len(metadata_rows)
    stats["elapsed_seconds"] = round(time.time() - started, 3)
    log.info("worker_id=%s complete stats=%s", worker_id, json.dumps(stats, sort_keys=True))
    if _worker_tqdm_file is not None:
        _worker_tqdm_file.close()
    logging.shutdown()
    return {"stats": stats, "metadata": metadata_rows}


def _write_metadata_returns(rows: list[dict[str, Any]]) -> None:
    PARTIAL_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates("study_id", keep="last").sort_values("study_id").reset_index(drop=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata.update(
        {
            b"dataset_version": dataset_version_stamp().encode("utf-8"),
            b"created_at_iso": utc_now_iso().encode("utf-8"),
            b"modality_kind": b"signal_metadata_worker_returns",
            b"n_rows": str(table.num_rows).encode("utf-8"),
            b"script_commit_hash": script_commit_hash().encode("utf-8"),
        }
    )
    tmp = METADATA_RETURNS_PATH.with_suffix(".parquet.tmp")
    pq.write_table(table.replace_schema_metadata(metadata), tmp, compression="snappy")
    os.replace(tmp, METADATA_RETURNS_PATH)


def _write_done_marker(stats: dict[str, Any], elapsed_seconds: float) -> None:
    DONE_MARKER.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "script": SCRIPT_NAME,
        "dataset_version": dataset_version_stamp(),
        "created_at_iso": utc_now_iso(),
        "elapsed_seconds": elapsed_seconds,
        "stats": stats,
    }
    tmp = DONE_MARKER.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, DONE_MARKER)


def _ensure_stage_state() -> None:
    STAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if STAGE_STATE_PATH.exists():
        return
    payload = {
        "stage": 3,
        "started_at_iso": utc_now_iso(),
        "disk_before_gib": psutil.disk_usage(str(PROJECT_ROOT)).free / 1024**3,
    }
    tmp = STAGE_STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, STAGE_STATE_PATH)


def _format_duration(seconds: float) -> str:
    return str(timedelta(seconds=int(round(seconds)))).rjust(8, "0")


def main() -> None:
    start = time.time()
    _ensure_stage_state()
    PARTIAL_DIR.mkdir(parents=True, exist_ok=True)
    log = _setup_main_logger()
    log.info(
        "starting %s max_workers=%d batch_size=%d max_ram_gb=%.2f index=%s partial_dir=%s",
        SCRIPT_NAME,
        MAX_WORKERS,
        BATCH_SIZE,
        MAX_RAM_GB,
        INDEX_PATH,
        PARTIAL_DIR,
    )
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"missing required input: {INDEX_PATH}")

    metadata_rows: list[dict[str, Any]] = []
    totals = {"assigned": 0, "existing": 0, "ok": 0, "skipped": 0, "error": 0, "metadata_rows": 0}
    futures = []
    with ProcessPoolExecutor(max_workers=MAX_WORKERS, initializer=_init_worker, initargs=(str(LOG_DIR),)) as executor:
        for worker_id in range(MAX_WORKERS):
            futures.append(executor.submit(_worker_partition, worker_id, MAX_WORKERS))
        with logging_redirect_tqdm():
            for future in tqdm(
                as_completed(futures),
                total=len(futures),
                file=sys.stderr,
                dynamic_ncols=True,
                mininterval=0.5,
                desc="extract partitions",
            ):
                try:
                    result = future.result()
                except Exception as exc:
                    log.error("worker partition failed: %s", exc, exc_info=True)
                    raise
                stats = result["stats"]
                metadata_rows.extend(result["metadata"])
                for key in totals:
                    totals[key] += int(stats.get(key, 0))
                log.info("partition complete stats=%s", json.dumps(stats, sort_keys=True))

    _write_metadata_returns(metadata_rows)
    archive = _aggregate_worker_logs()
    elapsed = time.time() - start
    totals["metadata_rows"] = len({int(row["study_id"]) for row in metadata_rows})
    _write_done_marker(totals, elapsed)
    log.info(
        "done %s elapsed=%s totals=%s metadata_returns=%s worker_archive=%s",
        SCRIPT_NAME,
        _format_duration(elapsed),
        json.dumps(totals, sort_keys=True),
        METADATA_RETURNS_PATH,
        archive,
    )


if __name__ == "__main__":
    main()
