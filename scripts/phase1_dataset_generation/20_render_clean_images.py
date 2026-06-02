#!/usr/bin/env python3
"""Stage 4.A: render clean ECG images into private worker tar partials.

Pattern B implementation:
- each worker writes only its own private partial tars:
  data/processed/partial/clean_lead2_worker_{wid}.tar
  data/processed/partial/clean_12lead_worker_{wid}.tar
- workers render both clean layouts for their partition
- workers never write canonical tar shards, manifests, or final offsets

Run from the repository root:
    .\\ecg_env\\Scripts\\python.exe scripts\\phase1_dataset_generation\\20_render_clean_images.py
"""

from __future__ import annotations

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

import h5py
import numpy as np
import pandas as pd
import psutil
import pyarrow as pa
import pyarrow.parquet as pq
from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from _stage1_common import (  # noqa: E402
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
SIGNALS_DIR = DATA_PROCESSED / "signals"
INDEX_PATH = DATA_PROCESSED / "index" / "ecg_metadata.parquet"
SIGNALS_MANIFEST = SIGNALS_DIR / "signals_manifest.parquet"
LEAD2_H5 = SIGNALS_DIR / "lead2_raw.h5"
TASKS_PATH = PARTIAL_DIR / "clean_image_render_tasks.parquet"
DONE_MARKER = STAGE_REPORT_DIR / "stage_4_20_render_clean_images.done.json"
STAGE_STATE_PATH = STAGE_REPORT_DIR / "stage_4_state.json"

LEAD_ORDER = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
TWELVE_LAYOUT = [
    ["I", "aVR", "V1", "V4"],
    ["II", "aVL", "V2", "V5"],
    ["III", "aVF", "V3", "V6"],
]
SAMPLES_PER_RECORD = 5000
BATCH_SIZE = 32
MAX_WORKERS = max(1, math.floor((os.cpu_count() or 1) * 0.75))
MAX_RAM_GB = max(1.0, psutil.virtual_memory().total / 1024**3 - 8.0)
LEAD2_CLIP_MV = 1.45
LEAD2_YLIM_MV = 1.5
LEAD2_DPI = 300
LEAD2_WIDTH_PX = 3600
LEAD2_HEIGHT_PX = 750
LEAD2_PX_PER_MM = LEAD2_DPI / 25.4
LEAD2_WIDTH_MM = 250.0
LEAD2_HEIGHT_MM = LEAD2_HEIGHT_PX / LEAD2_PX_PER_MM
LEAD2_LEFT_MM = ((LEAD2_WIDTH_PX / LEAD2_PX_PER_MM) - LEAD2_WIDTH_MM) / 2.0
LEAD2_CENTER_Y_MM = LEAD2_HEIGHT_MM / 2.0

MM_PER_SECOND = 25.0
MM_PER_MV = 10.0
TWELVE_DPI = 100
PX_PER_MM = TWELVE_DPI / 25.4
SEGMENT_SECONDS = 2.5
TOTAL_SECONDS = 10.0
COLS = 4
GRID_ROWS = 4
ROW_HEIGHT_MM = 30.0
WIDTH_MM = TOTAL_SECONDS * MM_PER_SECOND
HEIGHT_MM = GRID_ROWS * ROW_HEIGHT_MM
MARGIN_MM = 4.0
TWELVE_WIDTH_PX = int(round((WIDTH_MM + 2 * MARGIN_MM) * PX_PER_MM))
TWELVE_HEIGHT_PX = int(round((HEIGHT_MM + 2 * MARGIN_MM) * PX_PER_MM))
PALETTE = [
    255,
    250,
    250,  # 0 background
    248,
    214,
    214,  # 1 minor grid
    226,
    147,
    147,  # 2 major grid
    38,
    38,
    38,  # 3 waveform
    90,
    90,
    90,  # 4 labels
] + [0, 0, 0] * 251
_BASE_12LEAD_IMAGE: Image.Image | None = None
DATASET_VERSION = dataset_version_stamp()


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


def _build_render_tasks(log: logging.Logger) -> int:
    existing_valid = False
    if TASKS_PATH.exists():
        try:
            metadata = pq.read_metadata(TASKS_PATH)
            existing_valid = metadata.num_rows > 0
        except Exception:
            existing_valid = False
    if existing_valid:
        rows = pq.read_metadata(TASKS_PATH).num_rows
        log.info("reusing render task table path=%s rows=%d", TASKS_PATH, rows)
        return int(rows)

    index = pd.read_parquet(INDEX_PATH, columns=["study_id", "subject_id"])
    manifest = pd.read_parquet(
        SIGNALS_MANIFEST,
        columns=["study_id", "modality_kind", "container_path", "container_row"],
    )
    lead2 = manifest.loc[manifest["modality_kind"] == "raw_lead2", ["study_id", "container_row"]].rename(columns={"container_row": "lead2_row"})
    twelve = manifest.loc[
        manifest["modality_kind"] == "raw_12lead",
        ["study_id", "container_path", "container_row"],
    ].rename(columns={"container_path": "twelve_path", "container_row": "twelve_row"})
    tasks = index.merge(lead2, on="study_id", how="inner").merge(twelve, on="study_id", how="inner")
    tasks = tasks.sort_values("lead2_row").reset_index(drop=True)
    tasks["study_id"] = tasks["study_id"].astype("int64")
    tasks["subject_id"] = tasks["subject_id"].astype("int64")
    tasks["lead2_row"] = tasks["lead2_row"].astype("int64")
    tasks["twelve_row"] = tasks["twelve_row"].astype("int64")
    table = pa.Table.from_pandas(tasks, preserve_index=False)
    _write_table_atomic(table, TASKS_PATH, "clean_image_render_tasks")
    log.info("wrote render task table path=%s rows=%d", TASKS_PATH, len(tasks))
    return int(len(tasks))


def _ensure_stage_state() -> None:
    STAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if STAGE_STATE_PATH.exists():
        return
    payload = {
        "stage": 4,
        "started_at_iso": utc_now_iso(),
        "disk_before_gib": psutil.disk_usage(str(PROJECT_ROOT)).free / 1024**3,
    }
    tmp = STAGE_STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, STAGE_STATE_PATH)


def _completed_studies(path: Path) -> set[int]:
    if not path.exists():
        return set()
    try:
        with tarfile.open(path, "r") as tar:
            out = set()
            for member in tar:
                if member.isfile() and member.name.endswith(".png"):
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
        "modality_kind": f"partial_clean_{layout}",
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


def _add_png(tar: tarfile.TarFile, study_id: int, png: bytes) -> None:
    info = tarfile.TarInfo(f"{study_id}.png")
    info.size = len(png)
    info.mtime = 0
    tar.addfile(info, io.BytesIO(png))


def _render_lead2_png(signal: np.ndarray) -> bytes:
    signal = np.asarray(signal, dtype="float32")
    signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
    signal = np.clip(signal, -LEAD2_CLIP_MV, LEAD2_CLIP_MV)
    image = Image.new("P", (LEAD2_WIDTH_PX, LEAD2_HEIGHT_PX), 0)
    image.putpalette(PALETTE)
    draw = ImageDraw.Draw(image)
    for mm in np.arange(0.0, LEAD2_WIDTH_PX / LEAD2_PX_PER_MM + 0.001, 1.0):
        x = int(round(mm * LEAD2_PX_PER_MM))
        color = 2 if int(round(mm)) % 5 == 0 else 1
        draw.line([(x, 0), (x, LEAD2_HEIGHT_PX - 1)], fill=color, width=1)
    for mm in np.arange(0.0, LEAD2_HEIGHT_MM + 0.001, 1.0):
        y = int(round(mm * LEAD2_PX_PER_MM))
        color = 2 if int(round(mm)) % 5 == 0 else 1
        draw.line([(0, y), (LEAD2_WIDTH_PX - 1, y)], fill=color, width=1)
    xs_seconds = np.linspace(0.0, TOTAL_SECONDS, len(signal), endpoint=False)
    x_points = (LEAD2_LEFT_MM + xs_seconds * MM_PER_SECOND) * LEAD2_PX_PER_MM
    y_points = (LEAD2_CENTER_Y_MM - signal * MM_PER_MV) * LEAD2_PX_PER_MM
    points = [(int(round(x)), int(round(y))) for x, y in zip(x_points, y_points)]
    draw.line(points, fill=3, width=2)
    font = ImageFont.load_default()
    draw.text((int(round(LEAD2_LEFT_MM * LEAD2_PX_PER_MM)) + 8, 8), "II", fill=4, font=font)
    draw.text((LEAD2_WIDTH_PX - 390, LEAD2_HEIGHT_PX - 28), "25 mm/s 10 mm/mV", fill=4, font=font)
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True, compress_level=9, dpi=(LEAD2_DPI, LEAD2_DPI))
    return buf.getvalue()


def _x_px(seconds: float) -> int:
    return int(round((MARGIN_MM + seconds * MM_PER_SECOND) * PX_PER_MM))


def _y_px(row_index: int, mv: float) -> int:
    center_mm = MARGIN_MM + (row_index + 0.5) * ROW_HEIGHT_MM
    return int(round((center_mm - mv * MM_PER_MV) * PX_PER_MM))


def _draw_grid(draw: ImageDraw.ImageDraw) -> None:
    left = int(round(MARGIN_MM * PX_PER_MM))
    top = int(round(MARGIN_MM * PX_PER_MM))
    right = int(round((MARGIN_MM + WIDTH_MM) * PX_PER_MM))
    bottom = int(round((MARGIN_MM + HEIGHT_MM) * PX_PER_MM))
    for mm in np.arange(0.0, WIDTH_MM + 0.001, 1.0):
        x = int(round((MARGIN_MM + mm) * PX_PER_MM))
        color = 2 if int(round(mm)) % 5 == 0 else 1
        draw.line([(x, top), (x, bottom)], fill=color, width=1)
    for mm in np.arange(0.0, HEIGHT_MM + 0.001, 1.0):
        y = int(round((MARGIN_MM + mm) * PX_PER_MM))
        color = 2 if int(round(mm)) % 5 == 0 else 1
        draw.line([(left, y), (right, y)], fill=color, width=1)


def _draw_signal_segment(
    draw: ImageDraw.ImageDraw,
    signal: np.ndarray,
    lead_idx: int,
    row_idx: int,
    col_idx: int,
    start_sample: int,
    end_sample: int,
) -> None:
    values = np.asarray(signal[start_sample:end_sample, lead_idx], dtype="float32")
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    values = np.clip(values, -1.45, 1.45)
    n = len(values)
    if n < 2:
        return
    col_start_seconds = col_idx * SEGMENT_SECONDS
    xs = np.linspace(col_start_seconds, col_start_seconds + SEGMENT_SECONDS, n, endpoint=False)
    pixel_width = max(1, _x_px(col_start_seconds + SEGMENT_SECONDS) - _x_px(col_start_seconds))
    stride = max(1, int(n / max(1, pixel_width * 1.5)))
    xs = xs[::stride]
    values = values[::stride]
    points = [(_x_px(float(x)), _y_px(row_idx, float(y))) for x, y in zip(xs, values)]
    draw.line(points, fill=3, width=1)


def _draw_rhythm_strip(draw: ImageDraw.ImageDraw, signal: np.ndarray) -> None:
    lead_idx = LEAD_ORDER.index("II")
    values = np.asarray(signal[:, lead_idx], dtype="float32")
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    values = np.clip(values, -1.45, 1.45)
    xs = np.linspace(0.0, TOTAL_SECONDS, len(values), endpoint=False)
    pixel_width = max(1, _x_px(TOTAL_SECONDS) - _x_px(0.0))
    stride = max(1, int(len(values) / max(1, pixel_width * 1.5)))
    xs = xs[::stride]
    values = values[::stride]
    points = [(_x_px(float(x)), _y_px(3, float(y))) for x, y in zip(xs, values)]
    draw.line(points, fill=3, width=1)


def _render_12lead_png(signal: np.ndarray) -> bytes:
    image = _base_12lead_image().copy()
    draw = ImageDraw.Draw(image)
    samples_per_segment = SAMPLES_PER_RECORD // COLS
    for row_idx, row_leads in enumerate(TWELVE_LAYOUT):
        for col_idx, lead_name in enumerate(row_leads):
            lead_idx = LEAD_ORDER.index(lead_name)
            start = col_idx * samples_per_segment
            end = start + samples_per_segment
            _draw_signal_segment(draw, signal, lead_idx, row_idx, col_idx, start, end)
    _draw_rhythm_strip(draw, signal)
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True, compress_level=9)
    return buf.getvalue()


def _base_12lead_image() -> Image.Image:
    global _BASE_12LEAD_IMAGE
    if _BASE_12LEAD_IMAGE is None:
        image = Image.new("P", (TWELVE_WIDTH_PX, TWELVE_HEIGHT_PX), 0)
        image.putpalette(PALETTE)
        draw = ImageDraw.Draw(image)
        _draw_grid(draw)
        font = ImageFont.load_default()
        for row_idx, row_leads in enumerate(TWELVE_LAYOUT):
            for col_idx, lead_name in enumerate(row_leads):
                draw.text((_x_px(col_idx * SEGMENT_SECONDS) + 4, _y_px(row_idx, 1.25)), lead_name, fill=4, font=font)
        draw.text((_x_px(0.0) + 4, _y_px(3, 1.25)), "II", fill=4, font=font)
        draw.text((_x_px(7.35), TWELVE_HEIGHT_PX - int(round(3.5 * PX_PER_MM))), "25 mm/s 10 mm/mV", fill=4, font=font)
        _BASE_12LEAD_IMAGE = image
    return _BASE_12LEAD_IMAGE


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

    lead2_tar_path = PARTIAL_DIR / f"clean_lead2_worker_{worker_id:03d}.tar"
    twelve_tar_path = PARTIAL_DIR / f"clean_12lead_worker_{worker_id:03d}.tar"
    _add_partial_metadata(lead2_tar_path, "lead2", worker_id)
    _add_partial_metadata(twelve_tar_path, "12lead", worker_id)
    lead2_completed = _completed_studies(lead2_tar_path)
    twelve_completed = _completed_studies(twelve_tar_path)
    if lead2_completed != twelve_completed:
        raise RuntimeError(
            f"partial clean image mismatch worker_id={worker_id} lead2={len(lead2_completed)} twelve={len(twelve_completed)}"
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
    twelve_handles: dict[str, h5py.File] = {}
    _write_worker_progress(stats, 0, "starting", None, started)

    with h5py.File(LEAD2_H5, "r") as lead2_h5, _open_append_tar(lead2_tar_path) as lead2_tar, _open_append_tar(twelve_tar_path) as twelve_tar:
        try:
            for idx, row in enumerate(tasks.itertuples(index=False), start=1):
                study_id = int(row.study_id)
                if study_id in lead2_completed:
                    stats["skipped"] += 1
                    _write_worker_progress(stats, idx, "rendering", study_id, started)
                    continue
                try:
                    lead2_signal = lead2_h5["signal"][int(row.lead2_row)]
                    twelve_rel = str(row.twelve_path).replace("/", os.sep)
                    twelve_path = DATA_PROCESSED / twelve_rel
                    handle = twelve_handles.get(str(twelve_path))
                    if handle is None:
                        handle = h5py.File(twelve_path, "r")
                        twelve_handles[str(twelve_path)] = handle
                    twelve_signal = handle["signal"][int(row.twelve_row)]
                    lead2_png = _render_lead2_png(lead2_signal)
                    twelve_png = _render_12lead_png(twelve_signal)
                    _add_png(lead2_tar, study_id, lead2_png)
                    _add_png(twelve_tar, study_id, twelve_png)
                    lead2_completed.add(study_id)
                    twelve_completed.add(study_id)
                    stats["ok"] += 1
                    stats["lead2_bytes"] += len(lead2_png)
                    stats["twelve_bytes"] += len(twelve_png)
                except Exception as exc:
                    stats["error"] += 1
                    log.exception("study_id=%s clean image render failed: %s", study_id, exc)
                finally:
                    _write_worker_progress(stats, idx, "rendering", study_id, started)
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
            for handle in twelve_handles.values():
                handle.close()

    stats["elapsed_seconds"] = round(time.time() - started, 3)
    _write_worker_progress(stats, int(len(tasks)), "complete", None, started)
    log.info("worker_id=%s complete stats=%s", worker_id, json.dumps(stats, sort_keys=True))
    logging.shutdown()
    return stats


def _write_done_marker(stats: dict[str, Any], elapsed_seconds: float) -> None:
    DONE_MARKER.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stage": 4,
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
    for path in (INDEX_PATH, SIGNALS_MANIFEST, LEAD2_H5):
        if not path.exists():
            raise FileNotFoundError(f"missing required input: {path}")

    task_count = _build_render_tasks(log)
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
                desc="render clean image partitions",
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
