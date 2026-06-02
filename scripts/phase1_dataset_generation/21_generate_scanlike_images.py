#!/usr/bin/env python3
"""Stage 5.A: generate scanlike ECG images into private worker tar partials.

Pattern B implementation:
- each worker writes only its own private partial tars:
  data/processed/partial/scanlike_lead2_worker_{wid}.tar
  data/processed/partial/scanlike_12lead_worker_{wid}.tar
- workers read clean PNG bytes from canonical Stage 4 tar shards
- workers never write canonical tar shards, manifests, or final offsets

Run from the repository root:
    .\\ecg_env\\Scripts\\python.exe scripts\\phase1_dataset_generation\\21_generate_scanlike_images.py
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import logging.handlers
import math
import os
import shutil
import sys
import tarfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path
from typing import Any

import cv2
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
PROGRESS_DIR = LOG_DIR / "worker_progress"
PARTIAL_DIR = DATA_PROCESSED / "partial"
IMAGES_DIR = DATA_PROCESSED / "images"
TASKS_PATH = PARTIAL_DIR / "scanlike_image_tasks.parquet"
DONE_MARKER = STAGE_REPORT_DIR / "stage_5_21_generate_scanlike_images.done.json"
STAGE_STATE_PATH = STAGE_REPORT_DIR / "stage_5_state.json"

BATCH_SIZE = 32
PROGRESS_EVERY = 250
MAX_WORKERS = max(1, math.floor((os.cpu_count() or 1) * 0.75))
MAX_RAM_GB = max(1.0, psutil.virtual_memory().total / 1024**3 - 8.0)
MAX_WIDTH = 1600
DATASET_VERSION = dataset_version_stamp()

LAYOUTS = {
    "lead2": {
        "clean_manifest": IMAGES_DIR / "clean_lead2_manifest.parquet",
        "partial_template": "scanlike_lead2_worker_{worker_id:03d}.tar",
    },
    "12lead": {
        "clean_manifest": IMAGES_DIR / "clean_12lead_manifest.parquet",
        "partial_template": "scanlike_12lead_worker_{worker_id:03d}.tar",
    },
}


def _setup_main_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
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
    for old in PROGRESS_DIR.glob("worker_*.progress.*"):
        old.unlink(missing_ok=True)
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


def _relative_processed(path: Path) -> str:
    return str(path.relative_to(DATA_PROCESSED)).replace("\\", "/")


def _write_table_atomic(table: pa.Table, path: Path, modality_kind: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table.replace_schema_metadata(metadata), tmp, compression="snappy")
    os.replace(tmp, path)


def _ensure_stage_state() -> None:
    STAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if STAGE_STATE_PATH.exists():
        return
    payload = {
        "stage": 5,
        "started_at_iso": utc_now_iso(),
        "disk_before_gib": psutil.disk_usage(str(PROJECT_ROOT)).free / 1024**3,
    }
    tmp = STAGE_STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, STAGE_STATE_PATH)


def _build_tasks(log: logging.Logger) -> int:
    existing_valid = False
    if TASKS_PATH.exists():
        try:
            existing_valid = pq.read_metadata(TASKS_PATH).num_rows > 0
        except Exception:
            existing_valid = False
    if existing_valid:
        rows = int(pq.read_metadata(TASKS_PATH).num_rows)
        log.info("reusing scanlike task table path=%s rows=%d", TASKS_PATH, rows)
        return rows

    lead2 = pd.read_parquet(
        LAYOUTS["lead2"]["clean_manifest"],
        columns=["study_id", "subject_id", "container_path"],
    ).rename(columns={"container_path": "clean_lead2_path"})
    twelve = pd.read_parquet(
        LAYOUTS["12lead"]["clean_manifest"],
        columns=["study_id", "container_path"],
    ).rename(columns={"container_path": "clean_12lead_path"})
    tasks = lead2.merge(twelve, on="study_id", how="inner")
    tasks = tasks.sort_values("study_id").reset_index(drop=True)
    tasks["study_id"] = tasks["study_id"].astype("int64")
    tasks["subject_id"] = tasks["subject_id"].astype("int64")
    table = pa.Table.from_pandas(tasks, preserve_index=False)
    _write_table_atomic(table, TASKS_PATH, "scanlike_image_tasks")
    log.info("wrote scanlike task table path=%s rows=%d", TASKS_PATH, len(tasks))
    return int(len(tasks))


def _stable_cv_seed(study_id: int) -> int:
    digest = hashlib.sha256(f"scanlike:{int(study_id)}".encode("ascii")).digest()
    return int.from_bytes(digest[:4], "little") & 0x7FFFFFFF


def _opencv_uniforms(study_id: int, count: int) -> np.ndarray:
    seed = _stable_cv_seed(study_id)
    cv2.setRNGSeed(seed)
    values = np.empty((count,), dtype=np.float32)
    cv2.randu(values, 0.0, 1.0)
    return values.astype("float64")


def apply_scanlike_bytes(study_id: int, clean_png: bytes) -> bytes:
    """Return deterministic scanlike JPEG bytes for a clean ECG PNG."""
    arr = np.frombuffer(clean_png, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"OpenCV could not decode clean PNG for study_id={study_id}")

    u = _opencv_uniforms(study_id, 6)
    h, w = img.shape[:2]
    if w > MAX_WIDTH:
        scale = MAX_WIDTH / float(w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        h, w = img.shape[:2]

    angle = -2.0 + 4.0 * float(u[0])
    matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
    img = cv2.warpAffine(img, matrix, (w, h), borderMode=cv2.BORDER_REPLICATE)

    shift = -0.01 + 0.02 * float(u[1])
    pts1 = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
    pts2 = np.float32([[w * shift, 0], [w + w * shift, 0], [0, h], [w, h]])
    perspective = cv2.getPerspectiveTransform(pts1, pts2)
    img = cv2.warpPerspective(img, perspective, (w, h), borderMode=cv2.BORDER_REPLICATE)

    kernel = 3 if float(u[2]) < 0.5 else 5
    img = cv2.GaussianBlur(img, (kernel, kernel), 0)

    alpha = 0.9 + 0.2 * float(u[3])
    beta = -10.0 + 20.0 * float(u[4])
    img = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)

    quality = min(94, max(70, 70 + int(float(u[5]) * 25.0)))
    ok, encoded = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:
        raise ValueError(f"OpenCV could not encode scanlike JPEG for study_id={study_id}")
    return bytes(encoded)


def _completed_studies(path: Path) -> set[int]:
    if not path.exists():
        return set()
    try:
        with tarfile.open(path, "r") as tar:
            out = set()
            for member in tar:
                if member.isfile() and member.name.endswith(".jpg"):
                    out.add(int(Path(member.name).stem))
            return out
    except (tarfile.TarError, OSError, ValueError):
        corrupt = path.with_suffix(path.suffix + f".corrupt_{int(time.time())}")
        path.replace(corrupt)
        logging.getLogger("worker").warning("partial tar was unreadable and was renamed path=%s corrupt_path=%s", path, corrupt)
        return set()


def _add_partial_metadata(path: Path, layout: str, worker_id: int) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    payload = {
        "dataset_version": DATASET_VERSION,
        "created_at_iso": utc_now_iso(),
        "modality_kind": f"partial_scanlike_{layout}",
        "worker_id": worker_id,
        "script_commit_hash": script_commit_hash(),
    }
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    info = tarfile.TarInfo("PARTIAL_MANIFEST.json")
    info.size = len(data)
    info.mtime = 0
    with tarfile.open(path, "w") as tar:
        tar.addfile(info, io.BytesIO(data))


def _open_append_tar(path: Path) -> tarfile.TarFile:
    if path.exists() and path.stat().st_size > 0:
        return tarfile.open(path, "a")
    return tarfile.open(path, "w")


def _add_jpg(tar: tarfile.TarFile, study_id: int, blob: bytes) -> None:
    info = tarfile.TarInfo(f"{study_id}.jpg")
    info.size = len(blob)
    info.mtime = 0
    tar.addfile(info, io.BytesIO(blob))


def _read_clean_png(
    path: Path,
    study_id: int,
    handles: dict[str, tarfile.TarFile],
) -> bytes:
    key = str(path)
    handle = handles.get(key)
    if handle is None:
        handle = tarfile.open(path, "r")
        member_map = {member.name: member for member in handle.getmembers() if member.isfile()}
        original_getmember = handle.getmember

        def fast_getmember(name: str) -> tarfile.TarInfo:
            try:
                return member_map[name]
            except KeyError:
                return original_getmember(name)

        handle.getmember = fast_getmember  # type: ignore[method-assign]
        handles[key] = handle
    src = handle.extractfile(f"{int(study_id)}.png")
    if src is None:
        raise RuntimeError(f"missing clean PNG member study_id={study_id} path={path}")
    return src.read()


def _cooperative_ram_throttle(process: psutil.Process) -> None:
    limit_gb = (MAX_RAM_GB / MAX_WORKERS) * 1.5
    while process.memory_info().rss / 1024**3 > limit_gb:
        logging.getLogger("worker").warning(
            "worker ram throttle rss_gb=%.2f limit_gb=%.2f",
            process.memory_info().rss / 1024**3,
            limit_gb,
        )
        time.sleep(2)


def _write_worker_progress(stats: dict[str, Any], assigned_done: int, phase: str, last_study_id: int | None, started: float) -> None:
    try:
        payload = {
            "dataset_version": DATASET_VERSION,
            "updated_at_iso": utc_now_iso(),
            "phase": phase,
            "worker_id": int(stats["worker_id"]),
            "pid": int(stats["pid"]),
            "assigned_done": int(assigned_done),
            "assigned_total": int(stats["assigned"]),
            "ok": int(stats["ok"]),
            "skipped": int(stats["skipped"]),
            "error": int(stats["error"]),
            "existing": int(stats["existing"]),
            "last_study_id": None if last_study_id is None else int(last_study_id),
            "lead2_mib": round(float(stats["lead2_bytes"]) / 1024**2, 2),
            "twelve_mib": round(float(stats["twelve_bytes"]) / 1024**2, 2),
            "elapsed_seconds": round(time.time() - started, 1),
        }
        PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
        json_path = PROGRESS_DIR / f"worker_{int(stats['worker_id']):03d}.progress.json"
        text_path = PROGRESS_DIR / f"worker_{int(stats['worker_id']):03d}.progress.txt"
        tmp_json = json_path.with_suffix(".json.tmp")
        tmp_text = text_path.with_suffix(".txt.tmp")
        tmp_json.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp_json, json_path)
        percent = 100.0 * assigned_done / max(1, int(stats["assigned"]))
        tmp_text.write_text(
            (
                f"worker={payload['worker_id']:03d} pid={payload['pid']} phase={phase} "
                f"{assigned_done}/{payload['assigned_total']} ({percent:.2f}%) "
                f"ok={payload['ok']} skipped={payload['skipped']} error={payload['error']} "
                f"last_study_id={payload['last_study_id']} elapsed_s={payload['elapsed_seconds']}\n"
            ),
            encoding="utf-8",
        )
        os.replace(tmp_text, text_path)
    except OSError as exc:
        logging.getLogger("worker").warning("worker progress update failed worker_id=%s error=%s", stats.get("worker_id"), exc)


def _partition_bounds(total: int, worker_id: int, worker_count: int) -> tuple[int, int]:
    start = worker_id * total // worker_count
    end = (worker_id + 1) * total // worker_count
    return start, end


def _worker_partition(worker_id: int, worker_count: int) -> dict[str, Any]:
    log = logging.getLogger("worker")
    process = psutil.Process(os.getpid())
    tasks_all = pd.read_parquet(TASKS_PATH)
    start, end = _partition_bounds(len(tasks_all), worker_id, worker_count)
    tasks = tasks_all.iloc[start:end].reset_index(drop=True)
    del tasks_all

    lead2_tar_path = PARTIAL_DIR / LAYOUTS["lead2"]["partial_template"].format(worker_id=worker_id)
    twelve_tar_path = PARTIAL_DIR / LAYOUTS["12lead"]["partial_template"].format(worker_id=worker_id)
    _add_partial_metadata(lead2_tar_path, "lead2", worker_id)
    _add_partial_metadata(twelve_tar_path, "12lead", worker_id)
    lead2_completed = _completed_studies(lead2_tar_path)
    twelve_completed = _completed_studies(twelve_tar_path)
    if lead2_completed != twelve_completed:
        raise RuntimeError(
            f"partial scanlike mismatch worker_id={worker_id} lead2={len(lead2_completed)} twelve={len(twelve_completed)}"
        )

    stats = {
        "worker_id": worker_id,
        "pid": os.getpid(),
        "assigned": int(len(tasks)),
        "existing": int(len(lead2_completed)),
        "ok": 0,
        "skipped": 0,
        "error": 0,
        "lead2_bytes": 0,
        "twelve_bytes": 0,
    }
    started = time.time()
    clean_handles: dict[str, tarfile.TarFile] = {}
    _write_worker_progress(stats, 0, "starting", None, started)

    with _open_append_tar(lead2_tar_path) as lead2_tar, _open_append_tar(twelve_tar_path) as twelve_tar:
        try:
            for idx, row in enumerate(tasks.itertuples(index=False), start=1):
                study_id = int(row.study_id)
                if study_id in lead2_completed:
                    stats["skipped"] += 1
                    if idx % PROGRESS_EVERY == 0 or idx == len(tasks):
                        _write_worker_progress(stats, idx, "scanlike", study_id, started)
                    continue
                try:
                    clean_lead2_path = DATA_PROCESSED / str(row.clean_lead2_path).replace("/", os.sep)
                    clean_12lead_path = DATA_PROCESSED / str(row.clean_12lead_path).replace("/", os.sep)
                    lead2_png = _read_clean_png(clean_lead2_path, study_id, clean_handles)
                    twelve_png = _read_clean_png(clean_12lead_path, study_id, clean_handles)
                    lead2_jpg = apply_scanlike_bytes(study_id, lead2_png)
                    twelve_jpg = apply_scanlike_bytes(study_id, twelve_png)
                    _add_jpg(lead2_tar, study_id, lead2_jpg)
                    _add_jpg(twelve_tar, study_id, twelve_jpg)
                    lead2_completed.add(study_id)
                    twelve_completed.add(study_id)
                    stats["ok"] += 1
                    stats["lead2_bytes"] += len(lead2_jpg)
                    stats["twelve_bytes"] += len(twelve_jpg)
                except Exception as exc:
                    stats["error"] += 1
                    log.exception("study_id=%s scanlike image render failed: %s", study_id, exc)
                finally:
                    if idx % PROGRESS_EVERY == 0 or idx == len(tasks):
                        _write_worker_progress(stats, idx, "scanlike", study_id, started)
                if idx % BATCH_SIZE == 0:
                    _cooperative_ram_throttle(process)
                if idx % 5000 == 0:
                    log.info(
                        "worker_id=%s progress assigned_done=%d assigned_total=%d ok=%d skipped=%d error=%d elapsed_seconds=%.1f",
                        worker_id,
                        idx,
                        len(tasks),
                        stats["ok"],
                        stats["skipped"],
                        stats["error"],
                        time.time() - started,
                    )
        finally:
            for handle in clean_handles.values():
                handle.close()

    stats["elapsed_seconds"] = round(time.time() - started, 3)
    _write_worker_progress(stats, int(len(tasks)), "complete", None, started)
    log.info("worker_id=%s complete stats=%s", worker_id, json.dumps(stats, sort_keys=True))
    logging.shutdown()
    return stats


def _write_done_marker(stats: dict[str, Any], elapsed_seconds: float) -> None:
    DONE_MARKER.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stage": 5,
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


def main() -> None:
    start = time.time()
    _ensure_stage_state()
    PARTIAL_DIR.mkdir(parents=True, exist_ok=True)
    log = _setup_main_logger()
    log.info(
        "starting %s max_workers=%d batch_size=%d max_ram_gb=%.2f tasks_path=%s",
        SCRIPT_NAME,
        MAX_WORKERS,
        BATCH_SIZE,
        MAX_RAM_GB,
        TASKS_PATH,
    )
    for spec in LAYOUTS.values():
        path = spec["clean_manifest"]
        if not path.exists():
            raise FileNotFoundError(f"missing required input: {path}")

    task_count = _build_tasks(log)
    totals = {"assigned": 0, "existing": 0, "ok": 0, "skipped": 0, "error": 0, "lead2_bytes": 0, "twelve_bytes": 0}
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
                desc="scanlike image partitions",
            ):
                try:
                    stats = future.result()
                except Exception as exc:
                    log.error("worker partition failed: %s", exc, exc_info=True)
                    raise
                for key in totals:
                    totals[key] += int(stats.get(key, 0))
                log.info("partition complete stats=%s", json.dumps(stats, sort_keys=True))

    archive = _aggregate_worker_logs()
    elapsed = time.time() - start
    totals["task_count"] = int(task_count)
    totals["worker_archive"] = str(archive) if archive else None
    _write_done_marker(totals, elapsed)
    log.info("done %s elapsed=%s totals=%s", SCRIPT_NAME, _format_duration(elapsed), json.dumps(totals, sort_keys=True))


if __name__ == "__main__":
    main()
