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
