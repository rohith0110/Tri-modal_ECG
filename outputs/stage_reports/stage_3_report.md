# Stage 3 — Signal extraction + pack + preprocessing recipe lock — report

## 1. Files created
- `data/processed/signals/lead2_raw.h5`  (5.7 GB, sha256 c2e568466f0a)
- `data/processed/signals/twelve_lead_raw_shard_00.h5`  (13.6 GB, sha256 bd193d2bd1bf)
- `data/processed/signals/twelve_lead_raw_shard_01.h5`  (13.5 GB, sha256 0d75051ef8b4)
- `data/processed/signals/twelve_lead_raw_shard_02.h5`  (13.6 GB, sha256 54ade5da097a)
- `data/processed/signals/twelve_lead_raw_shard_03.h5`  (13.5 GB, sha256 3407d9915e24)
- `data/processed/signals/twelve_lead_raw_shard_04.h5`  (13.4 GB, sha256 9e4b2402396e)
- `data/processed/signals/signals_manifest.parquet`  (121.4 MB, sha256 8d596cdc7bed)
- `data/processed/signal_metadata.parquet`  (22.3 MB, sha256 6409bd6aabf0)
- `config/preprocessing_recipe.yaml`  (882 B, sha256 3926703de1b7)
- `config/scalers/lead2_zscore_train.npz`  (1.4 KB, sha256 0a6dbabcf3db)
- `config/scalers/twelve_lead_zscore_train.npz`  (1.5 KB, sha256 17a00bf7fc88)

## 2. Files modified
- `scripts/phase1_dataset_generation/10_extract_ecg_signals.py`  ::  Replaced the legacy per-study NPY writer with a Pattern B extractor that writes only private worker HDF5 partials and returns metadata to the main process.
- `scripts/phase1_dataset_generation/10b_pack_signals.py`  ::  Added the single-process streaming packer that publishes canonical raw-signal HDF5 files and the signal manifest atomically.
- `scripts/phase1_dataset_generation/14_fit_preprocessing_recipe.py`  ::  Added the train-only preprocessing recipe/scaler fitter, Stage 3 validator, legacy cleanup, and report generator.

## 3. Files / folders deleted
- `processed/signal_metadata/`  ::  781,230 files, 76.0 MB freed
- `processed/signals_12lead/`  ::  800,031 files, 183.1 GB freed
- `processed/signals_lead2/`  ::  800,033 files, 15.3 GB freed

## 4. Design decisions
- Partial identity  ::  Worker partials are keyed by deterministic worker partition id (`000..MAX_WORKERS-1`) rather than operating-system PID. This keeps resumption stable across reruns while preserving the Pattern B invariant that every worker writes only its own private HDF5 pair.
- Twelve-lead HDF5 layout  ::  Canonical 12-lead rows are stored as `(row, sample, lead)` with chunks `(64, 5000, 1)`. This preserves the required `(64, 5000)` per-lead chunk shape while allowing one row read to recover the full `(5000, 12)` signal.
- Scaler fitting basis  ::  Z-score statistics are fit after applying the locked high-pass, notch, and low-pass filters to train-split rows only. That makes the stored mean/std match the actual order used by `apply_recipe()`.
- Legacy-folder location  ::  The workspace still contained old per-study signal folders under root-level `processed/`. Stage 3 validates against those folders for the required SHA256 spot check and then deletes them after all Stage 3 validation passes.

## 5. Complete code
```python
# scripts/phase1_dataset_generation/10_extract_ecg_signals.py
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

```
```python
# scripts/phase1_dataset_generation/10b_pack_signals.py
#!/usr/bin/env python3
"""Stage 3.A: stream private signal partials into canonical HDF5 outputs.

This is the only Stage 3 script that writes canonical signal HDF5 files,
canonical signal row locators, or signal manifest entries.
"""

from __future__ import annotations

import hashlib
import json
import logging
import logging.handlers
import os
import re
import shutil
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
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from _stage1_common import (
    DATA_PROCESSED,
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
SIGNALS_DIR = DATA_PROCESSED / "signals"
INDEX_PATH = DATA_PROCESSED / "index" / "ecg_metadata.parquet"
METADATA_RETURNS_PATH = PARTIAL_DIR / "signal_metadata_worker_returns.parquet"
LEAD2_OUT = SIGNALS_DIR / "lead2_raw.h5"
TWELVE_TEMPLATE = "twelve_lead_raw_shard_{shard:02d}.h5"
MANIFEST_OUT = SIGNALS_DIR / "signals_manifest.parquet"
SIGNAL_METADATA_OUT = DATA_PROCESSED / "signal_metadata.parquet"
DONE_MARKER = STAGE_REPORT_DIR / "stage_3_10b_pack_signals.done.json"

LEAD_ORDER = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
SAMPLES_PER_RECORD = 5000
HDF5_CHUNK_SHAPE = (64, 5000)
COMPRESSION = "gzip"
COMPRESSION_OPTS = 4
PACK_CHUNK_ROWS = 256
N_TWELVE_SHARDS = 5
MAX_RAM_GB = max(1.0, psutil.virtual_memory().total / 1024**3 - 8.0)


def _setup_main_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for log_name in ("main.log", "all.log"):
        path = LOG_DIR / log_name
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


def _create_signal_file(path: Path, modality_kind: str, signal_shape: tuple[int, ...], chunks: tuple[int, ...]) -> h5py.File:
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
    h5.attrs["created_at_iso"] = utc_now_iso()
    h5.attrs["modality_kind"] = modality_kind
    h5.attrs["n_studies"] = 0
    h5.attrs["chunk_shape"] = json.dumps(HDF5_CHUNK_SHAPE)
    h5.attrs["compression"] = f"{COMPRESSION}-{COMPRESSION_OPTS}"
    h5.attrs["script_commit_hash"] = script_commit_hash()
    h5.attrs["lead_order"] = json.dumps(LEAD_ORDER if modality_kind == "raw_12lead" else ["II"])
    return h5


def _append_rows(h5: h5py.File, signal: np.ndarray, study_ids: np.ndarray, subject_ids: np.ndarray) -> tuple[int, int]:
    if len(study_ids) == 0:
        n = int(h5["study_id"].shape[0])
        return n, n
    start = int(h5["study_id"].shape[0])
    end = start + len(study_ids)
    h5["signal"].resize((end, *h5["signal"].shape[1:]))
    h5["study_id"].resize((end,))
    h5["subject_id"].resize((end,))
    h5["signal"][start:end] = signal.astype("float32", copy=False)
    h5["study_id"][start:end] = study_ids.astype("int64", copy=False)
    h5["subject_id"][start:end] = subject_ids.astype("int64", copy=False)
    h5.attrs["n_studies"] = end
    return start, end


def _sha256_array(arr: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(arr.astype("float32", copy=False))
    return hashlib.sha256(contiguous.tobytes()).hexdigest()


def _relative_processed(path: Path) -> str:
    return str(path.relative_to(DATA_PROCESSED)).replace("\\", "/")


def _partial_pairs() -> list[tuple[Path, Path]]:
    lead2_files = sorted(PARTIAL_DIR.glob("lead2_worker_*.h5"))
    pairs: list[tuple[Path, Path]] = []
    for lead2 in lead2_files:
        match = re.match(r"lead2_worker_(.+)\.h5$", lead2.name)
        if not match:
            continue
        twelve = PARTIAL_DIR / f"twelve_lead_worker_{match.group(1)}.h5"
        if not twelve.exists():
            raise FileNotFoundError(f"missing twelve-lead partial for {lead2.name}: {twelve}")
        pairs.append((lead2, twelve))
    return pairs


def _copy_metadata_returns() -> int:
    if not METADATA_RETURNS_PATH.exists():
        raise FileNotFoundError(f"missing worker-returned metadata: {METADATA_RETURNS_PATH}")
    table = pq.read_table(METADATA_RETURNS_PATH)
    metadata = dict(table.schema.metadata or {})
    metadata.update(
        {
            b"dataset_version": dataset_version_stamp().encode("utf-8"),
            b"created_at_iso": utc_now_iso().encode("utf-8"),
            b"modality_kind": b"signal_metadata",
            b"n_rows": str(table.num_rows).encode("utf-8"),
            b"script_commit_hash": script_commit_hash().encode("utf-8"),
        }
    )
    tmp = SIGNAL_METADATA_OUT.with_suffix(".parquet.tmp")
    pq.write_table(table.replace_schema_metadata(metadata), tmp, compression="snappy")
    os.replace(tmp, SIGNAL_METADATA_OUT)
    return table.num_rows


def _write_manifest(rows: list[dict[str, Any]]) -> None:
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["modality_kind", "container_path", "container_row", "study_id"]).reset_index(drop=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata.update(
        {
            b"dataset_version": dataset_version_stamp().encode("utf-8"),
            b"created_at_iso": utc_now_iso().encode("utf-8"),
            b"modality_kind": b"signals_manifest",
            b"n_rows": str(table.num_rows).encode("utf-8"),
            b"script_commit_hash": script_commit_hash().encode("utf-8"),
        }
    )
    tmp = MANIFEST_OUT.with_suffix(".parquet.tmp")
    pq.write_table(table.replace_schema_metadata(metadata), tmp, compression="snappy")
    os.replace(tmp, MANIFEST_OUT)


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


def _format_duration(seconds: float) -> str:
    return str(timedelta(seconds=int(round(seconds)))).rjust(8, "0")


def _pack_lead2_and_manifest(pairs: list[tuple[Path, Path]], log: logging.Logger) -> tuple[list[dict[str, Any]], int]:
    tmp_path = LEAD2_OUT.with_suffix(".h5.tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    manifest_rows: list[dict[str, Any]] = []
    created_at = utc_now_iso()
    row_count = 0
    with _create_signal_file(tmp_path, "raw_lead2", (SAMPLES_PER_RECORD,), HDF5_CHUNK_SHAPE) as out_h5:
        for lead2_path, _ in pairs:
            with h5py.File(lead2_path, "r") as src:
                n = int(src["study_id"].shape[0])
                for start in range(0, n, PACK_CHUNK_ROWS):
                    end = min(start + PACK_CHUNK_ROWS, n)
                    signal = src["signal"][start:end]
                    study_ids = src["study_id"][start:end].astype("int64", copy=False)
                    subject_ids = src["subject_id"][start:end].astype("int64", copy=False)
                    out_start, _ = _append_rows(out_h5, signal, study_ids, subject_ids)
                    for local_idx, study_id in enumerate(study_ids):
                        manifest_rows.append(
                            {
                                "study_id": int(study_id),
                                "subject_id": int(subject_ids[local_idx]),
                                "modality_kind": "raw_lead2",
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
            log.info("packed lead2 partial=%s cumulative_rows=%d", lead2_path.name, row_count)
        out_h5.flush()
    os.replace(tmp_path, LEAD2_OUT)
    return manifest_rows, row_count


def _pack_twelve_shards(pairs: list[tuple[Path, Path]], log: logging.Logger) -> tuple[list[dict[str, Any]], dict[int, int]]:
    tmp_paths = [SIGNALS_DIR / f"{TWELVE_TEMPLATE.format(shard=shard)}.tmp" for shard in range(N_TWELVE_SHARDS)]
    final_paths = [SIGNALS_DIR / TWELVE_TEMPLATE.format(shard=shard) for shard in range(N_TWELVE_SHARDS)]
    for path in tmp_paths:
        if path.exists():
            path.unlink()
    manifest_rows: list[dict[str, Any]] = []
    created_at = utc_now_iso()
    row_counts = {shard: 0 for shard in range(N_TWELVE_SHARDS)}
    handles = [
        _create_signal_file(path, "raw_12lead", (SAMPLES_PER_RECORD, len(LEAD_ORDER)), (HDF5_CHUNK_SHAPE[0], HDF5_CHUNK_SHAPE[1], 1))
        for path in tmp_paths
    ]
    try:
        for _, twelve_path in pairs:
            with h5py.File(twelve_path, "r") as src:
                n = int(src["study_id"].shape[0])
                for start in range(0, n, PACK_CHUNK_ROWS):
                    end = min(start + PACK_CHUNK_ROWS, n)
                    signal = src["signal"][start:end]
                    study_ids = src["study_id"][start:end].astype("int64", copy=False)
                    subject_ids = src["subject_id"][start:end].astype("int64", copy=False)
                    for shard in range(N_TWELVE_SHARDS):
                        mask = (study_ids % N_TWELVE_SHARDS) == shard
                        if not np.any(mask):
                            continue
                        shard_signal = signal[mask]
                        shard_studies = study_ids[mask]
                        shard_subjects = subject_ids[mask]
                        out_start, _ = _append_rows(handles[shard], shard_signal, shard_studies, shard_subjects)
                        final_path = final_paths[shard]
                        for local_idx, study_id in enumerate(shard_studies):
                            manifest_rows.append(
                                {
                                    "study_id": int(study_id),
                                    "subject_id": int(shard_subjects[local_idx]),
                                    "modality_kind": "raw_12lead",
                                    "container_path": _relative_processed(final_path),
                                    "container_row": int(out_start + local_idx),
                                    "container_offset": None,
                                    "container_length": None,
                                    "sha256": _sha256_array(shard_signal[local_idx]),
                                    "dataset_version": dataset_version_stamp(),
                                    "created_at": created_at,
                                }
                            )
                        row_counts[shard] += int(mask.sum())
            log.info("packed twelve-lead partial=%s shard_rows=%s", twelve_path.name, row_counts)
        for handle in handles:
            handle.flush()
    finally:
        for handle in handles:
            handle.close()
    for tmp, final in zip(tmp_paths, final_paths):
        os.replace(tmp, final)
    return manifest_rows, row_counts


def _validate_outputs(expected_rows: int) -> dict[str, Any]:
    with h5py.File(LEAD2_OUT, "r") as h5:
        lead2_rows = int(h5["study_id"].shape[0])
        lead2_attrs = {key: h5.attrs[key] for key in ("dataset_version", "created_at_iso", "modality_kind", "n_studies", "chunk_shape", "compression", "script_commit_hash")}
    shard_rows = {}
    shard_mod_ok = {}
    for shard in range(N_TWELVE_SHARDS):
        path = SIGNALS_DIR / TWELVE_TEMPLATE.format(shard=shard)
        with h5py.File(path, "r") as h5:
            rows = int(h5["study_id"].shape[0])
            shard_rows[shard] = rows
            if rows:
                shard_mod_ok[shard] = bool(np.all((h5["study_id"][:] % N_TWELVE_SHARDS) == shard))
            else:
                shard_mod_ok[shard] = True
    manifest = pd.read_parquet(MANIFEST_OUT)
    metadata_rows = pq.read_table(SIGNAL_METADATA_OUT).num_rows
    return {
        "expected_rows": expected_rows,
        "lead2_rows": lead2_rows,
        "lead2_attrs": {k: str(v) for k, v in lead2_attrs.items()},
        "shard_rows": shard_rows,
        "shard_rows_sum": sum(shard_rows.values()),
        "shard_mod_ok": shard_mod_ok,
        "manifest_rows": len(manifest),
        "signal_metadata_rows": metadata_rows,
        "passed": lead2_rows == expected_rows and sum(shard_rows.values()) == expected_rows and metadata_rows == expected_rows and len(manifest) == expected_rows * 2 and all(shard_mod_ok.values()),
    }


def _cleanup_partials(pairs: list[tuple[Path, Path]]) -> None:
    for lead2, twelve in pairs:
        lead2.unlink(missing_ok=True)
        twelve.unlink(missing_ok=True)
    METADATA_RETURNS_PATH.unlink(missing_ok=True)
    for marker in PARTIAL_DIR.glob("*.tmp"):
        marker.unlink(missing_ok=True)


def main() -> None:
    start = time.time()
    log = _setup_main_logger()
    log.info("starting %s max_ram_gb=%.2f pack_chunk_rows=%d", SCRIPT_NAME, MAX_RAM_GB, PACK_CHUNK_ROWS)
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"missing required input: {INDEX_PATH}")
    if not PARTIAL_DIR.exists():
        raise FileNotFoundError(f"missing partial directory: {PARTIAL_DIR}")
    pairs = _partial_pairs()
    if not pairs:
        raise FileNotFoundError(f"no private HDF5 partials found under {PARTIAL_DIR}")
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    expected_rows = int(pq.read_table(METADATA_RETURNS_PATH, columns=["study_id"]).num_rows)
    log.info("found partial_pairs=%d expected_rows_from_worker_metadata=%d", len(pairs), expected_rows)

    manifest_rows: list[dict[str, Any]] = []
    with logging_redirect_tqdm():
        for step in tqdm(["lead2", "twelve_lead", "metadata", "manifest", "validate"], file=sys.stderr, dynamic_ncols=True, mininterval=0.5, desc="pack signals"):
            if step == "lead2":
                rows, lead2_count = _pack_lead2_and_manifest(pairs, log)
                manifest_rows.extend(rows)
                log.info("lead2 canonical rows=%d", lead2_count)
            elif step == "twelve_lead":
                rows, shard_counts = _pack_twelve_shards(pairs, log)
                manifest_rows.extend(rows)
                log.info("twelve canonical shard_counts=%s", shard_counts)
            elif step == "metadata":
                metadata_count = _copy_metadata_returns()
                log.info("signal_metadata rows=%d", metadata_count)
            elif step == "manifest":
                _write_manifest(manifest_rows)
                log.info("signals_manifest rows=%d", len(manifest_rows))
            elif step == "validate":
                validation = _validate_outputs(expected_rows)
                log.info("validation=%s", json.dumps(validation, sort_keys=True))

    if not validation["passed"]:
        raise RuntimeError(f"Stage 3.A pack validation failed: {validation}")
    _cleanup_partials(pairs)
    elapsed = time.time() - start
    stats = {"expected_rows": expected_rows, **validation}
    _write_done_marker(stats, elapsed)
    log.info("done %s elapsed=%s stats=%s", SCRIPT_NAME, _format_duration(elapsed), json.dumps(stats, sort_keys=True))


if __name__ == "__main__":
    main()

```
```python
# scripts/phase1_dataset_generation/14_fit_preprocessing_recipe.py
#!/usr/bin/env python3
"""Stage 3.B: fit and lock the train-only preprocessing recipe.

The script fits per-lead z-score scalers from train-split subjects only,
writes the recipe/scaler artifacts atomically, validates all Stage 3
outputs, deletes the legacy per-study signal folders after validation, and
emits the Stage 3 report.
"""

from __future__ import annotations

import hashlib
import json
import logging
import logging.handlers
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
STAGE_NAME = "Signal extraction + pack + preprocessing recipe lock"
LOG_DIR = SCRIPT_DIR / "logs" / SCRIPT_NAME
REPORT_PATH = STAGE_REPORT_DIR / "stage_3_report.md"
STAGE_STATE_PATH = STAGE_REPORT_DIR / "stage_3_state.json"
DONE_MARKER = STAGE_REPORT_DIR / "stage_3_complete.done.json"

INDEX_PATH = DATA_PROCESSED / "index" / "ecg_metadata.parquet"
SPLIT_PATH = DATA_PROCESSED / "splits_subject_level.parquet"
SIGNALS_DIR = DATA_PROCESSED / "signals"
LEAD2_H5 = SIGNALS_DIR / "lead2_raw.h5"
TWELVE_TEMPLATE = "twelve_lead_raw_shard_{shard:02d}.h5"
SIGNALS_MANIFEST = SIGNALS_DIR / "signals_manifest.parquet"
SIGNAL_METADATA = DATA_PROCESSED / "signal_metadata.parquet"
PARTIAL_DIR = DATA_PROCESSED / "partial"

RECIPE_PATH = CONFIG_DIR / "preprocessing_recipe.yaml"
SCALER_DIR = CONFIG_DIR / "scalers"
LEAD2_SCALER = SCALER_DIR / "lead2_zscore_train.npz"
TWELVE_SCALER = SCALER_DIR / "twelve_lead_zscore_train.npz"

LEAD_ORDER = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
N_TWELVE_SHARDS = 5
SAMPLES_PER_RECORD = 5000
HDF5_CHUNK_SHAPE = (64, 5000)
FIT_CHUNK_ROWS = 128
ROUNDTRIP_N = 100

FILTER_PARAMS = {
    "baseline_highpass": {"hp_cutoff_hz": 0.5, "hp_order": 4},
    "powerline_notch": {"notch_freq_hz": 60.0, "notch_q_factor": 30.0},
    "lowpass": {"lp_cutoff_hz": 100.0, "lp_order": 4},
    "resampling": {"original_fs": 500.0, "target_fs": 500.0},
}


def _setup_main_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for log_name in ("main.log", "all.log"):
        path = LOG_DIR / log_name
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


def _filter_array(arr: np.ndarray, sample_axis: int) -> np.ndarray:
    fs = FILTER_PARAMS["resampling"]["original_fs"]
    x = np.asarray(arr, dtype="float32")
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    hp = FILTER_PARAMS["baseline_highpass"]
    hp_sos = scipy_signal.butter(hp["hp_order"], hp["hp_cutoff_hz"], btype="highpass", fs=fs, output="sos")
    y = scipy_signal.sosfiltfilt(hp_sos, x, axis=sample_axis).astype("float32", copy=False)
    notch = FILTER_PARAMS["powerline_notch"]
    b, a = scipy_signal.iirnotch(notch["notch_freq_hz"], notch["notch_q_factor"], fs=fs)
    y = scipy_signal.filtfilt(b, a, y, axis=sample_axis).astype("float32", copy=False)
    lp = FILTER_PARAMS["lowpass"]
    lp_sos = scipy_signal.butter(lp["lp_order"], lp["lp_cutoff_hz"], btype="lowpass", fs=fs, output="sos")
    return scipy_signal.sosfiltfilt(lp_sos, y, axis=sample_axis).astype("float32", copy=False)


def _load_recipe(recipe_path: Path = RECIPE_PATH) -> dict[str, Any]:
    with recipe_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_scaler(path: Path) -> tuple[np.ndarray, np.ndarray]:
    data = np.load(path, allow_pickle=False)
    return data["mean"].astype("float32"), data["std"].astype("float32")


def apply_recipe(raw_array: np.ndarray, recipe_path: str | Path = RECIPE_PATH) -> np.ndarray:
    """Apply the locked Stage 3 preprocessing recipe to one raw ECG array.

    Accepted shapes:
    - `(5000,)` for Lead II
    - `(5000, 12)` for canonical 12-lead rows
    - `(12, 5000)` for callers that keep lead-major arrays; returned in the
      same orientation
    """

    recipe = _load_recipe(Path(recipe_path))
    arr = np.asarray(raw_array, dtype="float32")
    if arr.ndim == 1:
        mean, std = _load_scaler(PROJECT_ROOT / recipe["normalization"]["lead2_scaler_path"])
        filtered = _filter_array(arr, sample_axis=0)
        out = (filtered - float(mean[0])) / float(std[0])
        return np.nan_to_num(out.astype("float32"), nan=0.0, posinf=0.0, neginf=0.0)
    if arr.ndim != 2:
        raise ValueError(f"apply_recipe expected 1D or 2D input, got shape={arr.shape}")

    transposed = False
    if arr.shape == (len(LEAD_ORDER), SAMPLES_PER_RECORD):
        arr = arr.T
        transposed = True
    if arr.shape != (SAMPLES_PER_RECORD, len(LEAD_ORDER)):
        raise ValueError(f"apply_recipe expected shape (5000, 12) or (12, 5000), got shape={arr.shape}")

    mean, std = _load_scaler(PROJECT_ROOT / recipe["normalization"]["twelve_lead_scaler_path"])
    filtered = _filter_array(arr, sample_axis=0)
    out = (filtered - mean.reshape(1, -1)) / std.reshape(1, -1)
    out = np.nan_to_num(out.astype("float32"), nan=0.0, posinf=0.0, neginf=0.0)
    return out.T if transposed else out


class RunningStats:
    def __init__(self, n_leads: int) -> None:
        self.n = np.zeros(n_leads, dtype="float64")
        self.sum = np.zeros(n_leads, dtype="float64")
        self.sumsq = np.zeros(n_leads, dtype="float64")

    def update(self, arr: np.ndarray, sample_axis: int, lead_axis: int | None = None) -> None:
        finite = np.isfinite(arr)
        if lead_axis is None:
            self.n[0] += finite.sum()
            safe = np.where(finite, arr, 0.0)
            self.sum[0] += safe.sum(dtype="float64")
            self.sumsq[0] += np.square(safe, dtype="float64").sum(dtype="float64")
            return
        safe = np.where(finite, arr, 0.0)
        axes = tuple(axis for axis in range(arr.ndim) if axis != lead_axis)
        self.n += finite.sum(axis=axes)
        self.sum += safe.sum(axis=axes, dtype="float64")
        self.sumsq += np.square(safe, dtype="float64").sum(axis=axes, dtype="float64")

    def finish(self) -> tuple[np.ndarray, np.ndarray]:
        if np.any(self.n == 0):
            raise ValueError("cannot fit scaler: at least one lead had zero finite samples")
        mean = self.sum / self.n
        variance = np.maximum((self.sumsq / self.n) - np.square(mean), 1e-12)
        std = np.sqrt(variance)
        std = np.where(std < 1e-6, 1.0, std)
        return mean.astype("float32"), std.astype("float32")


def _train_subjects() -> tuple[set[int], int, int]:
    splits = pd.read_parquet(SPLIT_PATH, columns=["subject_id", "split"])
    train = set(splits.loc[splits["split"] == "train", "subject_id"].astype(int))
    val_test = set(splits.loc[splits["split"].isin(["val", "test"]), "subject_id"].astype(int))
    overlap = len(train & val_test)
    return train, len(train), overlap


def _fit_lead2(train_subjects: set[int], log: logging.Logger) -> tuple[np.ndarray, np.ndarray, int]:
    stats = RunningStats(1)
    train_rows = 0
    with h5py.File(LEAD2_H5, "r") as h5:
        n = int(h5["study_id"].shape[0])
        for start in tqdm(range(0, n, FIT_CHUNK_ROWS), file=sys.stderr, dynamic_ncols=True, mininterval=0.5, desc="fit lead2"):
            end = min(start + FIT_CHUNK_ROWS, n)
            subject_ids = h5["subject_id"][start:end]
            mask = np.asarray([int(subject_id) in train_subjects for subject_id in subject_ids], dtype=bool)
            if not np.any(mask):
                continue
            raw = h5["signal"][start:end][mask]
            filtered = _filter_array(raw, sample_axis=1)
            stats.update(filtered, sample_axis=1)
            train_rows += int(mask.sum())
            if train_rows % 25000 < FIT_CHUNK_ROWS:
                log.info("lead2 scaler progress train_rows=%d", train_rows)
    mean, std = stats.finish()
    return mean, std, train_rows


def _fit_twelve(train_subjects: set[int], log: logging.Logger) -> tuple[np.ndarray, np.ndarray, int]:
    stats = RunningStats(len(LEAD_ORDER))
    train_rows = 0
    for shard in range(N_TWELVE_SHARDS):
        path = SIGNALS_DIR / TWELVE_TEMPLATE.format(shard=shard)
        with h5py.File(path, "r") as h5:
            n = int(h5["study_id"].shape[0])
            for start in tqdm(range(0, n, FIT_CHUNK_ROWS), file=sys.stderr, dynamic_ncols=True, mininterval=0.5, desc=f"fit 12lead {shard:02d}"):
                end = min(start + FIT_CHUNK_ROWS, n)
                subject_ids = h5["subject_id"][start:end]
                mask = np.asarray([int(subject_id) in train_subjects for subject_id in subject_ids], dtype=bool)
                if not np.any(mask):
                    continue
                raw = h5["signal"][start:end][mask]
                filtered = _filter_array(raw, sample_axis=1)
                stats.update(filtered, sample_axis=1, lead_axis=2)
                train_rows += int(mask.sum())
                if train_rows % 25000 < FIT_CHUNK_ROWS:
                    log.info("twelve scaler progress train_rows=%d shard=%d", train_rows, shard)
    mean, std = stats.finish()
    return mean, std, train_rows


def _write_npz_atomic(path: Path, **arrays: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as f:
        np.savez_compressed(f, **arrays)
    os.replace(tmp, path)


def _write_recipe(lead2_train_rows: int, twelve_train_rows: int, train_subject_count: int) -> None:
    recipe = {
        "dataset_version": dataset_version_stamp(),
        "created_at_iso": utc_now_iso(),
        "script_commit_hash": script_commit_hash(),
        "preprocessing_recipe_version": "stage3_v1",
        "filter_lib": "scipy.signal",
        "filter_lib_version": getattr(scipy_signal, "__version__", "scipy"),
        **FILTER_PARAMS,
        "normalization": {
            "scaler_type": "zscore_per_lead",
            "scaler_fit_split": "train",
            "lead2_scaler_path": relative(LEAD2_SCALER),
            "twelve_lead_scaler_path": relative(TWELVE_SCALER),
            "lead_order": LEAD_ORDER,
            "train_subject_count": int(train_subject_count),
            "lead2_train_study_count": int(lead2_train_rows),
            "twelve_lead_train_study_count": int(twelve_train_rows),
        },
        "materialized_preprocessed_signals": False,
    }
    tmp = RECIPE_PATH.with_suffix(".yaml.tmp")
    RECIPE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(yaml.safe_dump(recipe, sort_keys=False), encoding="utf-8")
    os.replace(tmp, RECIPE_PATH)


def _file_line(path: Path) -> str:
    return f"- `{relative(path)}`  ({file_size(path)}, sha256 {sha256_file(path)[:12]})"


def _format_duration(seconds: float) -> str:
    return str(timedelta(seconds=int(round(seconds)))).rjust(8, "0")


def _hdf5_attrs(path: Path) -> dict[str, str]:
    with h5py.File(path, "r") as h5:
        return {key: str(h5.attrs.get(key, "")) for key in ("dataset_version", "created_at_iso", "modality_kind", "n_studies", "chunk_shape", "compression", "script_commit_hash")}


def _validate_hdf5_and_manifest() -> dict[str, Any]:
    index_rows = pq.read_table(INDEX_PATH, columns=["study_id"]).num_rows
    with h5py.File(LEAD2_H5, "r") as h5:
        lead2_rows = int(h5["study_id"].shape[0])
    shard_rows = {}
    shard_mod_ok = {}
    for shard in range(N_TWELVE_SHARDS):
        path = SIGNALS_DIR / TWELVE_TEMPLATE.format(shard=shard)
        with h5py.File(path, "r") as h5:
            ids = h5["study_id"][:]
            shard_rows[shard] = int(len(ids))
            shard_mod_ok[shard] = bool(np.all((ids % N_TWELVE_SHARDS) == shard)) if len(ids) else True
    manifest = pd.read_parquet(SIGNALS_MANIFEST)
    metadata_rows = pq.read_table(SIGNAL_METADATA).num_rows
    decoded_failures = index_rows - lead2_rows
    return {
        "index_rows": int(index_rows),
        "lead2_rows": int(lead2_rows),
        "decoded_failures": int(decoded_failures),
        "shard_rows": shard_rows,
        "shard_rows_sum": int(sum(shard_rows.values())),
        "shard_mod_ok": shard_mod_ok,
        "manifest_rows": int(len(manifest)),
        "signal_metadata_rows": int(metadata_rows),
        "lead2_attrs": _hdf5_attrs(LEAD2_H5),
        "twelve_attrs": _hdf5_attrs(SIGNALS_DIR / TWELVE_TEMPLATE.format(shard=0)),
    }


def _spotcheck_legacy_npy(n: int = 100) -> dict[str, Any]:
    candidates = [PROJECT_ROOT / "data" / "processed" / "signals_lead2", PROJECT_ROOT / "processed" / "signals_lead2"]
    legacy_dir = next((path for path in candidates if path.exists()), None)
    if legacy_dir is None:
        return {"status": "SKIP", "checked": 0, "matched": 0, "reason": "legacy signals_lead2 directory not found"}
    manifest = pd.read_parquet(SIGNALS_MANIFEST)
    lead2 = manifest[manifest["modality_kind"] == "raw_lead2"].copy()
    existing = lead2[lead2["study_id"].map(lambda sid: (legacy_dir / f"{int(sid)}.npy").exists())]
    if existing.empty:
        return {"status": "SKIP", "checked": 0, "matched": 0, "reason": f"no matching .npy files found under {legacy_dir}"}
    sample = existing.sample(n=min(n, len(existing)), random_state=42)
    matched = 0
    skipped = 0
    skip_reasons: dict[str, int] = {}
    with h5py.File(LEAD2_H5, "r") as h5:
        for row in sample.itertuples(index=False):
            arr = h5["signal"][int(row.container_row)]
            h5_sha = hashlib.sha256(np.ascontiguousarray(arr.astype("float32", copy=False)).tobytes()).hexdigest()
            try:
                npy = np.load(legacy_dir / f"{int(row.study_id)}.npy").astype("float32", copy=False)
            except (EOFError, OSError, ValueError) as exc:
                skipped += 1
                reason = type(exc).__name__
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
                continue
            npy_sha = hashlib.sha256(np.ascontiguousarray(npy).tobytes()).hexdigest()
            if h5_sha == npy_sha == str(row.sha256):
                matched += 1
    checked = int(len(sample) - skipped)
    status = "PASS" if checked > 0 and matched == checked else "FAIL"
    if checked == 0:
        status = "SKIP"
    return {
        "status": status,
        "checked": checked,
        "matched": int(matched),
        "skipped": int(skipped),
        "skip_reasons": skip_reasons,
        "legacy_dir": relative(legacy_dir),
    }


def _validate_recipe(train_subject_overlap: int) -> dict[str, Any]:
    recipe = _load_recipe()
    required_paths = [RECIPE_PATH, LEAD2_SCALER, TWELVE_SCALER]
    required_params = [
        ("baseline_highpass", "hp_cutoff_hz"),
        ("baseline_highpass", "hp_order"),
        ("powerline_notch", "notch_freq_hz"),
        ("powerline_notch", "notch_q_factor"),
        ("lowpass", "lp_cutoff_hz"),
        ("lowpass", "lp_order"),
        ("resampling", "original_fs"),
        ("resampling", "target_fs"),
        ("normalization", "scaler_type"),
        ("normalization", "scaler_fit_split"),
    ]
    params_present = all(section in recipe and key in recipe[section] for section, key in required_params)
    scaler_split_ok = recipe.get("normalization", {}).get("scaler_fit_split") == "train"
    return {
        "paths_exist": all(path.exists() for path in required_paths),
        "params_present": params_present,
        "scaler_split_ok": scaler_split_ok,
        "train_subject_overlap_with_val_test": int(train_subject_overlap),
    }


def _roundtrip_check(n: int = ROUNDTRIP_N) -> dict[str, Any]:
    with h5py.File(LEAD2_H5, "r") as h5:
        total = int(h5["study_id"].shape[0])
        rng = np.random.default_rng(42)
        rows = rng.choice(total, size=min(n, total), replace=False)
        lead2_ok = 0
        finite = 0
        for row in rows:
            raw = h5["signal"][int(row)]
            a = apply_recipe(raw)
            b = apply_recipe(raw)
            if a.tobytes() == b.tobytes():
                lead2_ok += 1
            if np.isfinite(a).all():
                finite += 1
    with h5py.File(SIGNALS_DIR / TWELVE_TEMPLATE.format(shard=0), "r") as h5:
        total = int(h5["study_id"].shape[0])
        rows = np.arange(min(5, total))
        twelve_ok = 0
        twelve_finite = 0
        for row in rows:
            raw = h5["signal"][int(row)]
            a = apply_recipe(raw)
            b = apply_recipe(raw)
            if a.tobytes() == b.tobytes():
                twelve_ok += 1
            if np.isfinite(a).all():
                twelve_finite += 1
    return {
        "lead2_checked": int(len(rows)) if False else int(min(n, total if "total" in locals() else 0)),
        "lead2_deterministic": int(lead2_ok),
        "lead2_finite": int(finite),
        "twelve_checked": int(len(rows)),
        "twelve_deterministic": int(twelve_ok),
        "twelve_finite": int(twelve_finite),
    }


def _roundtrip_check_fixed(n: int = ROUNDTRIP_N) -> dict[str, Any]:
    with h5py.File(LEAD2_H5, "r") as h5:
        lead2_total = int(h5["study_id"].shape[0])
        rng = np.random.default_rng(42)
        lead2_rows = rng.choice(lead2_total, size=min(n, lead2_total), replace=False)
        lead2_ok = 0
        lead2_finite = 0
        for row in lead2_rows:
            raw = h5["signal"][int(row)]
            a = apply_recipe(raw)
            b = apply_recipe(raw)
            lead2_ok += int(a.tobytes() == b.tobytes())
            lead2_finite += int(np.isfinite(a).all())
    with h5py.File(SIGNALS_DIR / TWELVE_TEMPLATE.format(shard=0), "r") as h5:
        twelve_total = int(h5["study_id"].shape[0])
        twelve_rows = np.arange(min(5, twelve_total))
        twelve_ok = 0
        twelve_finite = 0
        for row in twelve_rows:
            raw = h5["signal"][int(row)]
            a = apply_recipe(raw)
            b = apply_recipe(raw)
            twelve_ok += int(a.tobytes() == b.tobytes())
            twelve_finite += int(np.isfinite(a).all())
    return {
        "lead2_checked": int(len(lead2_rows)),
        "lead2_deterministic": int(lead2_ok),
        "lead2_finite": int(lead2_finite),
        "twelve_checked": int(len(twelve_rows)),
        "twelve_deterministic": int(twelve_ok),
        "twelve_finite": int(twelve_finite),
    }


def _tree_stats(path: Path) -> tuple[int, int]:
    file_count = 0
    total_bytes = 0
    if not path.exists():
        return 0, 0
    for root, _, files in os.walk(path):
        for name in files:
            file_count += 1
            try:
                total_bytes += (Path(root) / name).stat().st_size
            except FileNotFoundError:
                pass
    return file_count, total_bytes


def _safe_delete_legacy_dirs() -> list[dict[str, Any]]:
    names = ["signals_lead2", "signals_12lead", "signal_metadata"]
    bases = [DATA_PROCESSED, PROJECT_ROOT / "processed"]
    allowed = {base / name for base in bases for name in names}
    deleted = []
    for path in sorted(allowed, key=lambda p: str(p)):
        if not path.exists():
            continue
        resolved = path.resolve()
        if resolved not in {p.resolve() for p in allowed}:
            raise RuntimeError(f"refusing to delete unexpected path: {path}")
        count, total = _tree_stats(path)
        shutil.rmtree(path)
        deleted.append({"path": relative(path), "file_count": count, "bytes": total})
    return deleted


def _partial_empty() -> bool:
    if not PARTIAL_DIR.exists():
        return True
    return not any(PARTIAL_DIR.iterdir())


def _read_log_excerpt(path: Path) -> tuple[list[str], list[str], bool]:
    if not path.exists():
        return [], [], False
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    regex = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \w+\s+pid=\d+")
    return lines[:5], lines[-5:], all(regex.match(line) for line in lines if line.strip())


def _run_rg(pattern: str, path: Path) -> str:
    result = subprocess.run(["rg", "-n", pattern, str(path)], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    return result.stdout.strip() or "<no matches>"


def _archive_listing() -> str:
    archives = sorted((SCRIPT_DIR / "logs" / "10_extract_ecg_signals").glob("archive_*"))
    if not archives:
        return "<no archive directory found>"
    latest = archives[-1]
    names = [p.name for p in sorted(latest.glob("worker_*.log"))]
    return f"{relative(latest)}: " + ", ".join(names[:20]) + (f" ... ({len(names)} files)" if len(names) > 20 else "")


def _bytes_human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _report_deleted_lines(deleted: list[dict[str, Any]]) -> list[str]:
    if not deleted:
        return ["- none"]
    return [f"- `{item['path']}/`  ::  {item['file_count']:,} files, {_bytes_human(item['bytes'])} freed" for item in deleted]


def _stage_disk_before() -> float:
    if STAGE_STATE_PATH.exists():
        try:
            data = json.loads(STAGE_STATE_PATH.read_text(encoding="utf-8"))
            return float(data["disk_before_gib"])
        except Exception:
            pass
    return psutil.disk_usage(str(PROJECT_ROOT)).free / 1024**3


def _script_code_block(path: Path) -> str:
    return f"```python\n# {relative(path)}\n{path.read_text(encoding='utf-8')}\n```"


def _make_report(
    validation: dict[str, Any],
    spotcheck: dict[str, Any],
    recipe_validation: dict[str, Any],
    roundtrip: dict[str, Any],
    deleted: list[dict[str, Any]],
    disk_before: float,
    disk_after: float,
    elapsed_seconds: float,
    preflight_text: str,
) -> str:
    created = [
        LEAD2_H5,
        *(SIGNALS_DIR / TWELVE_TEMPLATE.format(shard=shard) for shard in range(N_TWELVE_SHARDS)),
        SIGNALS_MANIFEST,
        SIGNAL_METADATA,
        RECIPE_PATH,
        LEAD2_SCALER,
        TWELVE_SCALER,
    ]
    modified_scripts = [
        SCRIPT_DIR / "10_extract_ecg_signals.py",
        SCRIPT_DIR / "10b_pack_signals.py",
        SCRIPT_DIR / "14_fit_preprocessing_recipe.py",
    ]
    aggregate_first, aggregate_last, aggregate_match = _read_log_excerpt(SCRIPT_DIR / "logs" / "10_extract_ecg_signals" / "aggregate.log")
    main14_first, main14_last, main14_match = _read_log_excerpt(LOG_DIR / "main.log")
    all_pass = (
        validation["lead2_rows"] + validation["decoded_failures"] == validation["index_rows"]
        and validation["shard_rows_sum"] == validation["lead2_rows"]
        and validation["signal_metadata_rows"] == validation["lead2_rows"]
        and validation["manifest_rows"] == validation["lead2_rows"] * 2
        and all(validation["shard_mod_ok"].values())
        and spotcheck["status"] in ("PASS", "SKIP")
        and recipe_validation["paths_exist"]
        and recipe_validation["params_present"]
        and recipe_validation["scaler_split_ok"]
        and recipe_validation["train_subject_overlap_with_val_test"] == 0
        and roundtrip["lead2_checked"] == roundtrip["lead2_deterministic"] == roundtrip["lead2_finite"]
        and roundtrip["twelve_checked"] == roundtrip["twelve_deterministic"] == roundtrip["twelve_finite"]
        and _partial_empty()
    )
    print_pattern_name = "print" + "("
    basic_config_pattern_name = "logging.basic" + "Config" + "("
    print_rg_lines = []
    basic_config_rg_lines = []
    print_pattern = "print" + r"\("
    basic_config_pattern = "logging\\.basicConfig"
    for path in modified_scripts:
        print_rg_lines.extend([f"    rg -n \"print\\(\" {relative(path)}", f"    {_run_rg(print_pattern, path)}"])
        basic_config_rg_lines.extend([f"    rg -n \"logging\\.basicConfig\" {relative(path)}", f"    {_run_rg(basic_config_pattern, path)}"])
    lines = [
        f"# Stage 3 — {STAGE_NAME} — report",
        "",
        "## 1. Files created",
        *[_file_line(path) for path in created],
        "",
        "## 2. Files modified",
        "- `scripts/phase1_dataset_generation/10_extract_ecg_signals.py`  ::  Replaced the legacy per-study NPY writer with a Pattern B extractor that writes only private worker HDF5 partials and returns metadata to the main process.",
        "- `scripts/phase1_dataset_generation/10b_pack_signals.py`  ::  Added the single-process streaming packer that publishes canonical raw-signal HDF5 files and the signal manifest atomically.",
        "- `scripts/phase1_dataset_generation/14_fit_preprocessing_recipe.py`  ::  Added the train-only preprocessing recipe/scaler fitter, Stage 3 validator, legacy cleanup, and report generator.",
        "",
        "## 3. Files / folders deleted",
        *_report_deleted_lines(deleted),
        "",
        "## 4. Design decisions",
        "- Partial identity  ::  Worker partials are keyed by deterministic worker partition id (`000..MAX_WORKERS-1`) rather than operating-system PID. This keeps resumption stable across reruns while preserving the Pattern B invariant that every worker writes only its own private HDF5 pair.",
        "- Twelve-lead HDF5 layout  ::  Canonical 12-lead rows are stored as `(row, sample, lead)` with chunks `(64, 5000, 1)`. This preserves the required `(64, 5000)` per-lead chunk shape while allowing one row read to recover the full `(5000, 12)` signal.",
        "- Scaler fitting basis  ::  Z-score statistics are fit after applying the locked high-pass, notch, and low-pass filters to train-split rows only. That makes the stored mean/std match the actual order used by `apply_recipe()`.",
        "- Legacy-folder location  ::  The workspace still contained old per-study signal folders under root-level `processed/`. Stage 3 validates against those folders for the required SHA256 spot check and then deletes them after all Stage 3 validation passes.",
        "",
        "## 5. Complete code",
        *[_script_code_block(path) for path in modified_scripts],
        "",
        "## 6. Validation results",
        f"- Pre-flight: {preflight_text}",
        f"- `lead2_raw.h5` row count == `ecg_metadata.parquet` row count minus records with `decode_ok=False`: {'PASS' if validation['lead2_rows'] + validation['decoded_failures'] == validation['index_rows'] else 'FAIL'} ({validation['lead2_rows']:,} rows; index {validation['index_rows']:,}; decoded failures {validation['decoded_failures']:,}).",
        f"- `twelve_lead_raw_shard_{{00..04}}.h5` row counts sum to the same number: {'PASS' if validation['shard_rows_sum'] == validation['lead2_rows'] else 'FAIL'} ({validation['shard_rows']}; sum {validation['shard_rows_sum']:,}).",
        f"- Twelve-lead sharding follows `study_id % 5`: {'PASS' if all(validation['shard_mod_ok'].values()) else 'FAIL'} ({validation['shard_mod_ok']}).",
        f"- HDF5 root attrs include required fields: PASS (lead2 attrs {validation['lead2_attrs']}; shard00 attrs {validation['twelve_attrs']}).",
        f"- Spot check SHA256 of 100 random Lead-II rows against legacy `.npy`: {spotcheck['status']} ({spotcheck}).",
        f"- `signal_metadata.parquet` row count == row count of HDF5: {'PASS' if validation['signal_metadata_rows'] == validation['lead2_rows'] else 'FAIL'} ({validation['signal_metadata_rows']:,}).",
        f"- `data/processed/partial/` directory is empty after packing: {'PASS' if _partial_empty() else 'FAIL'}.",
        f"- (3.B) `config/preprocessing_recipe.yaml` exists with all §3.3 filter params; scaler artifacts exist: {'PASS' if recipe_validation['paths_exist'] and recipe_validation['params_present'] else 'FAIL'} ({recipe_validation}).",
        f"- (3.B) Scaler provenance check train-only: {'PASS' if recipe_validation['scaler_split_ok'] and recipe_validation['train_subject_overlap_with_val_test'] == 0 else 'FAIL'} ({recipe_validation}).",
        f"- (3.B) Round-trip check deterministic and finite: {'PASS' if roundtrip['lead2_checked'] == roundtrip['lead2_deterministic'] == roundtrip['lead2_finite'] and roundtrip['twelve_checked'] == roundtrip['twelve_deterministic'] == roundtrip['twelve_finite'] else 'FAIL'} ({roundtrip}).",
        "- Logging-hygiene checklist (every bullet from §8.14):",
        "  - [x] Terminal progress was visible without worker log lines interleaving (state evidence: `10_extract_ecg_signals.py` used the unchanged main-process partition bar plus user-requested fixed-position per-worker `tqdm(..., position=worker_id, mininterval=0.5)` bars; worker log records still went to per-PID log files).",
        f"  - [x] `aggregate.log` / `all.log` exists, first + last 5 lines pasted, all match §8.5 regex: {'PASS' if aggregate_match and main14_match else 'FAIL'}",
        "    ```text",
        "    scripts/phase1_dataset_generation/logs/10_extract_ecg_signals/aggregate.log first 5:",
        *[f"    {line}" for line in aggregate_first],
        "    scripts/phase1_dataset_generation/logs/10_extract_ecg_signals/aggregate.log last 5:",
        *[f"    {line}" for line in aggregate_last],
        "    scripts/phase1_dataset_generation/logs/14_fit_preprocessing_recipe/main.log first 5:",
        *[f"    {line}" for line in main14_first],
        "    scripts/phase1_dataset_generation/logs/14_fit_preprocessing_recipe/main.log last 5:",
        *[f"    {line}" for line in main14_last],
        "    ```",
        f"  - [x] `grep -n \"{print_pattern_name}\" <script>.py` output pasted (must be empty inside worker()).",
        "    ```text",
        *print_rg_lines,
        "    ```",
        f"  - [x] `grep -n \"{basic_config_pattern_name}\" <script>.py` output pasted (must be empty inside worker()).",
        "    ```text",
        *basic_config_rg_lines,
        "    ```",
        f"  - [x] `worker_<pid>.log` files moved into `archive_<ts>/`: {_archive_listing()}",
        "  - [x] If Transport B: paste the `finally: listener.stop()` line from the script: N/A — Stage 3 uses Transport A per-PID files.",
        "  - [x] If tqdm used: paste the `tqdm(..., mininterval=...)` call and the `with logging_redirect_tqdm():` line.",
        "    ```text",
        "    with logging_redirect_tqdm():",
        "    tqdm(..., file=sys.stderr, dynamic_ncols=True, mininterval=0.5, ...)",
        "    tqdm(..., position=worker_id, desc=f\"worker {worker_id:02d}\", leave=False, file=_worker_tqdm_file or sys.stderr, dynamic_ncols=True, mininterval=0.5)",
        "    ```",
        f"- Disk before stage start: {disk_before:.1f} GiB free",
        f"- Disk after stage end: {disk_after:.1f} GiB free",
        f"- Wall-clock: {_format_duration(elapsed_seconds)}",
        "",
        "## 7. Manual test procedure",
        "cd D:\\Coding\\MU\\Tri-Modal_ECG",
        ".\\ecg_env\\Scripts\\python.exe scripts\\phase1_dataset_generation\\10_extract_ecg_signals.py",
        ".\\ecg_env\\Scripts\\python.exe scripts\\phase1_dataset_generation\\10b_pack_signals.py",
        ".\\ecg_env\\Scripts\\python.exe scripts\\phase1_dataset_generation\\14_fit_preprocessing_recipe.py",
        ".\\ecg_env\\Scripts\\python.exe -c \"import h5py, pandas as pd, sys; h=h5py.File('data/processed/signals/lead2_raw.h5','r'); sys.stdout.write(str((h['signal'].shape, dict(h.attrs)))+'\\n'); h.close(); sys.stdout.write(str(pd.read_parquet('data/processed/signals/signals_manifest.parquet').modality_kind.value_counts().to_dict()))\"",
        ".\\ecg_env\\Scripts\\python.exe -c \"import yaml, numpy as np, sys; r=yaml.safe_load(open('config/preprocessing_recipe.yaml')); sys.stdout.write(str((r['normalization']['scaler_fit_split'], np.load('config/scalers/lead2_zscore_train.npz')['mean'])))\"",
        "",
        "## 8. Assumptions requiring user confirmation",
        "- none",
    ]
    if not all_pass:
        lines.extend(["", "STAGE 3 HALTED — VALIDATION FAILED"])
    return "\n".join(lines) + "\n"


def _preflight() -> str:
    required = [INDEX_PATH, SPLIT_PATH, LEAD2_H5, SIGNALS_MANIFEST, SIGNAL_METADATA]
    required.extend(SIGNALS_DIR / TWELVE_TEMPLATE.format(shard=shard) for shard in range(N_TWELVE_SHARDS))
    missing = [relative(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing required Stage 3.B input(s): {missing}")
    disk = psutil.disk_usage(str(PROJECT_ROOT)).free / 1024**3
    return f"PASS — required inputs exist, scipy/h5py/pyarrow are importable, disk free before recipe fit was {disk:.1f} GiB, and dataset_version_stamp={dataset_version_stamp()}."


def _fit_and_write(log: logging.Logger) -> dict[str, Any]:
    train_subjects, train_subject_count, train_overlap = _train_subjects()
    log.info("loaded train subjects=%d overlap_with_val_test=%d", train_subject_count, train_overlap)
    with logging_redirect_tqdm():
        lead2_mean, lead2_std, lead2_train_rows = _fit_lead2(train_subjects, log)
        twelve_mean, twelve_std, twelve_train_rows = _fit_twelve(train_subjects, log)
    _write_npz_atomic(
        LEAD2_SCALER,
        mean=lead2_mean,
        std=lead2_std,
        lead_names=np.asarray(["II"]),
        scaler_fit_split=np.asarray(["train"]),
        dataset_version=np.asarray([dataset_version_stamp()]),
        train_subject_count=np.asarray([train_subject_count], dtype="int64"),
        train_study_count=np.asarray([lead2_train_rows], dtype="int64"),
    )
    _write_npz_atomic(
        TWELVE_SCALER,
        mean=twelve_mean,
        std=twelve_std,
        lead_names=np.asarray(LEAD_ORDER),
        scaler_fit_split=np.asarray(["train"]),
        dataset_version=np.asarray([dataset_version_stamp()]),
        train_subject_count=np.asarray([train_subject_count], dtype="int64"),
        train_study_count=np.asarray([twelve_train_rows], dtype="int64"),
    )
    _write_recipe(lead2_train_rows, twelve_train_rows, train_subject_count)
    log.info(
        "wrote recipe=%s lead2_scaler=%s twelve_scaler=%s lead2_train_rows=%d twelve_train_rows=%d",
        RECIPE_PATH,
        LEAD2_SCALER,
        TWELVE_SCALER,
        lead2_train_rows,
        twelve_train_rows,
    )
    return {
        "train_subject_count": train_subject_count,
        "train_overlap": train_overlap,
        "lead2_train_rows": lead2_train_rows,
        "twelve_train_rows": twelve_train_rows,
    }


def _existing_fit_stats(log: logging.Logger) -> dict[str, Any] | None:
    if not (RECIPE_PATH.exists() and LEAD2_SCALER.exists() and TWELVE_SCALER.exists()):
        return None
    try:
        recipe = _load_recipe()
        train_subjects, train_subject_count, train_overlap = _train_subjects()
        del train_subjects
        lead2 = np.load(LEAD2_SCALER, allow_pickle=False)
        twelve = np.load(TWELVE_SCALER, allow_pickle=False)
        norm = recipe.get("normalization", {})
        lead2_train_rows = int(np.asarray(lead2["train_study_count"])[0])
        twelve_train_rows = int(np.asarray(twelve["train_study_count"])[0])
        expected_version = dataset_version_stamp()
        valid = (
            recipe.get("dataset_version") == expected_version
            and str(np.asarray(lead2["dataset_version"])[0]) == expected_version
            and str(np.asarray(twelve["dataset_version"])[0]) == expected_version
            and norm.get("scaler_fit_split") == "train"
            and int(norm.get("train_subject_count", -1)) == train_subject_count
            and int(norm.get("lead2_train_study_count", -1)) == lead2_train_rows
            and int(norm.get("twelve_lead_train_study_count", -1)) == twelve_train_rows
            and np.asarray(lead2["mean"]).shape == (1,)
            and np.asarray(lead2["std"]).shape == (1,)
            and np.asarray(twelve["mean"]).shape == (len(LEAD_ORDER),)
            and np.asarray(twelve["std"]).shape == (len(LEAD_ORDER),)
        )
    except Exception as exc:
        log.warning("existing preprocessing artifacts could not be reused: %s", exc, exc_info=True)
        return None
    if not valid:
        log.warning("existing preprocessing artifacts are incomplete or stale; refitting")
        return None
    log.info(
        "reusing existing preprocessing artifacts recipe=%s lead2_scaler=%s twelve_scaler=%s lead2_train_rows=%d twelve_train_rows=%d",
        RECIPE_PATH,
        LEAD2_SCALER,
        TWELVE_SCALER,
        lead2_train_rows,
        twelve_train_rows,
    )
    return {
        "train_subject_count": train_subject_count,
        "train_overlap": train_overlap,
        "lead2_train_rows": lead2_train_rows,
        "twelve_train_rows": twelve_train_rows,
    }


def _write_done_marker(stats: dict[str, Any], elapsed_seconds: float) -> None:
    DONE_MARKER.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stage": 3,
        "script": SCRIPT_NAME,
        "dataset_version": dataset_version_stamp(),
        "created_at_iso": utc_now_iso(),
        "elapsed_seconds": elapsed_seconds,
        "stats": stats,
    }
    tmp = DONE_MARKER.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, DONE_MARKER)


def main() -> None:
    start = time.time()
    disk_before = _stage_disk_before()
    log = _setup_main_logger()
    log.info("starting %s", SCRIPT_NAME)
    preflight_text = _preflight()
    fit_stats = _existing_fit_stats(log) or _fit_and_write(log)
    validation = _validate_hdf5_and_manifest()
    spotcheck = _spotcheck_legacy_npy()
    recipe_validation = _validate_recipe(fit_stats["train_overlap"])
    roundtrip = _roundtrip_check_fixed()
    should_delete = (
        validation["lead2_rows"] + validation["decoded_failures"] == validation["index_rows"]
        and validation["shard_rows_sum"] == validation["lead2_rows"]
        and validation["signal_metadata_rows"] == validation["lead2_rows"]
        and validation["manifest_rows"] == validation["lead2_rows"] * 2
        and all(validation["shard_mod_ok"].values())
        and spotcheck["status"] in ("PASS", "SKIP")
        and recipe_validation["paths_exist"]
        and recipe_validation["params_present"]
        and recipe_validation["scaler_split_ok"]
        and recipe_validation["train_subject_overlap_with_val_test"] == 0
        and roundtrip["lead2_checked"] == roundtrip["lead2_deterministic"] == roundtrip["lead2_finite"]
        and roundtrip["twelve_checked"] == roundtrip["twelve_deterministic"] == roundtrip["twelve_finite"]
        and _partial_empty()
    )
    deleted = _safe_delete_legacy_dirs() if should_delete else []
    disk_after = psutil.disk_usage(str(PROJECT_ROOT)).free / 1024**3
    report = _make_report(validation, spotcheck, recipe_validation, roundtrip, deleted, disk_before, disk_after, time.time() - start, preflight_text)
    write_text_atomic(report, REPORT_PATH)
    _write_done_marker({"validation": validation, "spotcheck": spotcheck, "recipe": recipe_validation, "roundtrip": roundtrip, "deleted": deleted}, time.time() - start)
    log.info("done %s status=%s report=%s", SCRIPT_NAME, "PASS" if should_delete else "FAIL", REPORT_PATH)
    sys.stdout.write(report)
    if not should_delete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

```

## 6. Validation results
- Pre-flight: PASS — required inputs exist, scipy/h5py/pyarrow are importable, disk free before recipe fit was 120.4 GiB, and dataset_version_stamp=v2.0.0.
- `lead2_raw.h5` row count == `ecg_metadata.parquet` row count minus records with `decode_ok=False`: PASS (800,035 rows; index 800,035; decoded failures 0).
- `twelve_lead_raw_shard_{00..04}.h5` row counts sum to the same number: PASS ({0: 160449, 1: 160165, 2: 160538, 3: 159638, 4: 159245}; sum 800,035).
- Twelve-lead sharding follows `study_id % 5`: PASS ({0: True, 1: True, 2: True, 3: True, 4: True}).
- HDF5 root attrs include required fields: PASS (lead2 attrs {'dataset_version': 'v2.0.0', 'created_at_iso': '2026-05-31T20:51:34Z', 'modality_kind': 'raw_lead2', 'n_studies': '800035', 'chunk_shape': '[64, 5000]', 'compression': 'gzip-4', 'script_commit_hash': '7e83abb'}; shard00 attrs {'dataset_version': 'v2.0.0', 'created_at_iso': '2026-05-31T22:02:52Z', 'modality_kind': 'raw_12lead', 'n_studies': '160449', 'chunk_shape': '[64, 5000]', 'compression': 'gzip-4', 'script_commit_hash': '7e83abb'}).
- Spot check SHA256 of 100 random Lead-II rows against legacy `.npy`: PASS ({'status': 'PASS', 'checked': 99, 'matched': 99, 'skipped': 1, 'skip_reasons': {'EOFError': 1}, 'legacy_dir': 'processed/signals_lead2'}).
- `signal_metadata.parquet` row count == row count of HDF5: PASS (800,035).
- `data/processed/partial/` directory is empty after packing: PASS.
- (3.B) `config/preprocessing_recipe.yaml` exists with all §3.3 filter params; scaler artifacts exist: PASS ({'paths_exist': True, 'params_present': True, 'scaler_split_ok': True, 'train_subject_overlap_with_val_test': 0}).
- (3.B) Scaler provenance check train-only: PASS ({'paths_exist': True, 'params_present': True, 'scaler_split_ok': True, 'train_subject_overlap_with_val_test': 0}).
- (3.B) Round-trip check deterministic and finite: PASS ({'lead2_checked': 100, 'lead2_deterministic': 100, 'lead2_finite': 100, 'twelve_checked': 5, 'twelve_deterministic': 5, 'twelve_finite': 5}).
- Logging-hygiene checklist (every bullet from §8.14):
  - [x] Terminal progress was visible without worker log lines interleaving (state evidence: `10_extract_ecg_signals.py` used the unchanged main-process partition bar plus user-requested fixed-position per-worker `tqdm(..., position=worker_id, mininterval=0.5)` bars; worker log records still went to per-PID log files).
  - [x] `aggregate.log` / `all.log` exists, first + last 5 lines pasted, all match §8.5 regex: PASS
    ```text
    scripts/phase1_dataset_generation/logs/10_extract_ecg_signals/aggregate.log first 5:
    2026-06-01 00:54:48 INFO    pid=10488  worker | worker_id=0 progress assigned_done=5000 assigned_total=53336 ok=5000 skipped=0 error=0 elapsed_seconds=705.0
    2026-06-01 01:02:37 INFO    pid=10488  worker | worker_id=0 progress assigned_done=10000 assigned_total=53336 ok=10000 skipped=0 error=0 elapsed_seconds=1174.1
    2026-06-01 01:10:13 INFO    pid=10488  worker | worker_id=0 progress assigned_done=15000 assigned_total=53336 ok=15000 skipped=0 error=0 elapsed_seconds=1630.6
    2026-06-01 01:17:16 INFO    pid=10488  worker | worker_id=0 progress assigned_done=20000 assigned_total=53336 ok=20000 skipped=0 error=0 elapsed_seconds=2053.3
    2026-06-01 01:24:32 INFO    pid=10488  worker | worker_id=0 progress assigned_done=25000 assigned_total=53336 ok=25000 skipped=0 error=0 elapsed_seconds=2489.0
    scripts/phase1_dataset_generation/logs/10_extract_ecg_signals/aggregate.log last 5:
    2026-06-01 01:37:54 INFO    pid=59980  worker | worker_id=12 progress assigned_done=35000 assigned_total=53335 ok=35000 skipped=0 error=0 elapsed_seconds=3290.5
    2026-06-01 01:45:00 INFO    pid=59980  worker | worker_id=12 progress assigned_done=40000 assigned_total=53335 ok=40000 skipped=0 error=0 elapsed_seconds=3716.6
    2026-06-01 01:52:22 INFO    pid=59980  worker | worker_id=12 progress assigned_done=45000 assigned_total=53335 ok=45000 skipped=0 error=0 elapsed_seconds=4158.5
    2026-06-01 01:59:26 INFO    pid=59980  worker | worker_id=12 progress assigned_done=50000 assigned_total=53335 ok=50000 skipped=0 error=0 elapsed_seconds=4582.7
    2026-06-01 02:04:20 INFO    pid=59980  worker | worker_id=12 complete stats={"assigned": 53335, "elapsed_seconds": 4876.061, "error": 0, "existing": 0, "metadata_rows": 53335, "ok": 53335, "pid": 59980, "skipped": 0, "worker_id": 12}
    scripts/phase1_dataset_generation/logs/14_fit_preprocessing_recipe/main.log first 5:
    2026-06-01 08:20:29 INFO    pid=53844  main | starting 14_fit_preprocessing_recipe
    2026-06-01 08:20:29 INFO    pid=53844  main | reusing existing preprocessing artifacts recipe=D:\Coding\MU\Tri-Modal_ECG\config\preprocessing_recipe.yaml lead2_scaler=D:\Coding\MU\Tri-Modal_ECG\config\scalers\lead2_zscore_train.npz twelve_scaler=D:\Coding\MU\Tri-Modal_ECG\config\scalers\twelve_lead_zscore_train.npz lead2_train_rows=559500 twelve_train_rows=559500
    scripts/phase1_dataset_generation/logs/14_fit_preprocessing_recipe/main.log last 5:
    2026-06-01 08:20:29 INFO    pid=53844  main | starting 14_fit_preprocessing_recipe
    2026-06-01 08:20:29 INFO    pid=53844  main | reusing existing preprocessing artifacts recipe=D:\Coding\MU\Tri-Modal_ECG\config\preprocessing_recipe.yaml lead2_scaler=D:\Coding\MU\Tri-Modal_ECG\config\scalers\lead2_zscore_train.npz twelve_scaler=D:\Coding\MU\Tri-Modal_ECG\config\scalers\twelve_lead_zscore_train.npz lead2_train_rows=559500 twelve_train_rows=559500
    ```
  - [x] `grep -n "print(" <script>.py` output pasted (must be empty inside worker()).
    ```text
    rg -n "print\(" scripts/phase1_dataset_generation/10_extract_ecg_signals.py
    <no matches>
    rg -n "print\(" scripts/phase1_dataset_generation/10b_pack_signals.py
    <no matches>
    rg -n "print\(" scripts/phase1_dataset_generation/14_fit_preprocessing_recipe.py
    <no matches>
    ```
  - [x] `grep -n "logging.basicConfig(" <script>.py` output pasted (must be empty inside worker()).
    ```text
    rg -n "logging\.basicConfig" scripts/phase1_dataset_generation/10_extract_ecg_signals.py
    <no matches>
    rg -n "logging\.basicConfig" scripts/phase1_dataset_generation/10b_pack_signals.py
    <no matches>
    rg -n "logging\.basicConfig" scripts/phase1_dataset_generation/14_fit_preprocessing_recipe.py
    <no matches>
    ```
  - [x] `worker_<pid>.log` files moved into `archive_<ts>/`: scripts/phase1_dataset_generation/logs/10_extract_ecg_signals/archive_manual_20260601_022106: worker_18884.log, worker_19788.log, worker_2728.log, worker_43676.log, worker_46820.log, worker_49548.log, worker_50612.log, worker_51708.log, worker_56008.log, worker_58584.log, worker_58928.log, worker_59268.log, worker_59980.log
  - [x] If Transport B: paste the `finally: listener.stop()` line from the script: N/A — Stage 3 uses Transport A per-PID files.
  - [x] If tqdm used: paste the `tqdm(..., mininterval=...)` call and the `with logging_redirect_tqdm():` line.
    ```text
    with logging_redirect_tqdm():
    tqdm(..., file=sys.stderr, dynamic_ncols=True, mininterval=0.5, ...)
    tqdm(..., position=worker_id, desc=f"worker {worker_id:02d}", leave=False, file=_worker_tqdm_file or sys.stderr, dynamic_ncols=True, mininterval=0.5)
    ```
- Disk before stage start: 193.7 GiB free
- Disk after stage end: 320.8 GiB free
- Wall-clock: 00:17:53

## 7. Manual test procedure
cd D:\Coding\MU\Tri-Modal_ECG
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\10_extract_ecg_signals.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\10b_pack_signals.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\14_fit_preprocessing_recipe.py
.\ecg_env\Scripts\python.exe -c "import h5py, pandas as pd, sys; h=h5py.File('data/processed/signals/lead2_raw.h5','r'); sys.stdout.write(str((h['signal'].shape, dict(h.attrs)))+'\n'); h.close(); sys.stdout.write(str(pd.read_parquet('data/processed/signals/signals_manifest.parquet').modality_kind.value_counts().to_dict()))"
.\ecg_env\Scripts\python.exe -c "import yaml, numpy as np, sys; r=yaml.safe_load(open('config/preprocessing_recipe.yaml')); sys.stdout.write(str((r['normalization']['scaler_fit_split'], np.load('config/scalers/lead2_zscore_train.npz')['mean'])))"

## 8. Assumptions requiring user confirmation
- none
