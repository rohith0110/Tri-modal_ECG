#!/usr/bin/env python3
"""Stage 7.A: rich waveform QC and cross-source consistency parquet.

Run from the scripts directory:
    ..\ecg_env\Scripts\python.exe phase1_dataset_generation\31_waveform_qc.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import logging.handlers
import math
import multiprocessing as mp
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
    relative,
    script_commit_hash,
    silence_noisy_libs,
    utc_now_iso,
)

SCRIPT_NAME = Path(__file__).stem
SCRIPT_PATH = Path(__file__).resolve()
LOG_DIR = SCRIPT_DIR / "logs" / SCRIPT_NAME
INDEX_PATH = DATA_PROCESSED / "index" / "ecg_metadata.parquet"
SIGNALS_DIR = DATA_PROCESSED / "signals"
SIGNALS_MANIFEST = SIGNALS_DIR / "signals_manifest.parquet"
MEASUREMENTS_CSV = PROJECT_ROOT / "data" / "raw" / "machine_measurements.csv"
QC_LIGHT_PATH = DATA_PROCESSED / "qc.parquet"
WAVEFORM_QC_OUT = DATA_PROCESSED / "waveform_qc.parquet"
WAVEFORM_QC_TMP = DATA_PROCESSED / "waveform_qc.parquet.tmp"
DONE_MARKER = STAGE_REPORT_DIR / "stage_7_waveform_qc.done.json"

IMAGE_MANIFESTS = {
    "clean_lead2": DATA_PROCESSED / "images" / "clean_lead2_manifest.parquet",
    "clean_12lead": DATA_PROCESSED / "images" / "clean_12lead_manifest.parquet",
    "scanlike_lead2": DATA_PROCESSED / "images" / "scanlike_lead2_manifest.parquet",
    "scanlike_12lead": DATA_PROCESSED / "images" / "scanlike_12lead_manifest.parquet",
}

LEAD_ORDER = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
EXPECTED_LEADS = set(LEAD_ORDER)
FS = 500
SAMPLES_PER_RECORD = 5000
FLUSH_EVERY = 100_000
MAX_WORKERS = max(1, math.floor((os.cpu_count() or 1) * 0.75))
MAX_RAM_GB = max(1.0, psutil.virtual_memory().total / 1024**3 - 8.0)
WORKER_RAM_SOFT_GB = max(0.5, MAX_RAM_GB / MAX_WORKERS * 1.5)
EXTREME_AMPLITUDE_MV = 10.0
FLATLINE_DIFF_RATIO = 0.90
FLATLINE_STD_THRESHOLD = 1e-5

RUN_COMMAND = (
    "cd D:\\Coding\\MU\\Tri-Modal_ECG\\scripts\n"
    "..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\31_waveform_qc.py "
    "1> ..\\outputs\\stage_reports\\stage_7_run\\31_waveform_qc.stdout.log "
    "2> ..\\outputs\\stage_reports\\stage_7_run\\31_waveform_qc.stderr.log"
)

PART_SCHEMA = pa.schema(
    [
        pa.field("study_id", pa.int64(), nullable=False),
        pa.field("subject_id", pa.int64(), nullable=False),
        pa.field("decode_ok", pa.bool_(), nullable=False),
        pa.field("length_ok", pa.bool_(), nullable=False),
        pa.field("lead_count_ok", pa.bool_(), nullable=False),
        pa.field("lead_names_ok", pa.bool_(), nullable=False),
        pa.field("nan_inf_flag", pa.bool_(), nullable=False),
        pa.field("flatline_lead_flag", pa.bool_(), nullable=False),
        pa.field("flatline_leads", pa.list_(pa.string())),
        pa.field("extreme_amplitude_flag", pa.bool_(), nullable=False),
        pa.field("duplicate_waveform_flag", pa.bool_(), nullable=False),
        pa.field("duplicate_group_id", pa.int64()),
        pa.field("sqi_per_lead", pa.list_(pa.float32())),
        pa.field("sqi_aggregate", pa.float32()),
        pa.field("sqi_tier", pa.string(), nullable=False),
        pa.field("waveform_hr_bpm", pa.float32()),
        pa.field("machine_hr_bpm", pa.float32()),
        pa.field("hr_consistency_flag", pa.bool_(), nullable=False),
        pa.field("waveform_qrs_ms", pa.float32()),
        pa.field("machine_qrs_ms", pa.float32()),
        pa.field("qrs_consistency_flag", pa.bool_(), nullable=False),
        pa.field("report_consistency_flag", pa.bool_(), nullable=False),
        pa.field("image_clean_ok", pa.bool_(), nullable=False),
        pa.field("image_scanlike_ok", pa.bool_(), nullable=False),
        pa.field("text_ok", pa.bool_(), nullable=False),
        pa.field("notes", pa.string(), nullable=False),
        pa.field("_duplicate_key", pa.string()),
    ]
)

FINAL_SCHEMA = pa.schema([field for field in PART_SCHEMA if field.name != "_duplicate_key"])

_H5_HANDLES: dict[str, h5py.File] = {}
_NK: Any = None


def _setup_main_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("main.log", "all.log", "aggregate.log"):
        path = LOG_DIR / name
        if path.exists():
            path.unlink()
    logger = logging.getLogger("main")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    file_handler = logging.handlers.RotatingFileHandler(LOG_DIR / "main.log", mode="w", maxBytes=50_000_000, backupCount=3, encoding="utf-8")
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


def _get_nk() -> Any:
    global _NK
    if _NK is None:
        import warnings

        warnings.filterwarnings("ignore")
        import neurokit2 as nk

        _NK = nk
    return _NK


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _nan_float(value: Any) -> float:
    out = _safe_float(value)
    return float("nan") if out is None else float(out)


def _signal_key(lead2: np.ndarray) -> str:
    arr = np.ascontiguousarray(np.asarray(lead2[::10], dtype="float32"))
    return hashlib.sha256(arr.tobytes()).hexdigest()


def _flatline_leads(signal: np.ndarray) -> list[str]:
    leads: list[str] = []
    for idx, lead in enumerate(LEAD_ORDER):
        x = np.asarray(signal[:, idx], dtype="float32")
        finite = x[np.isfinite(x)]
        if finite.size < 2:
            leads.append(lead)
            continue
        diff_ratio = float(np.mean(np.abs(np.diff(finite)) <= 1e-8))
        if diff_ratio > FLATLINE_DIFF_RATIO or float(np.std(finite)) < FLATLINE_STD_THRESHOLD:
            leads.append(lead)
    return leads


def _sqi_one_lead(signal: np.ndarray) -> tuple[float, np.ndarray | None]:
    nk = _get_nk()
    try:
        cleaned = nk.ecg_clean(np.asarray(signal, dtype="float32"), sampling_rate=FS, method="neurokit")
        _, info = nk.ecg_peaks(cleaned, sampling_rate=FS, method="neurokit")
        quality = nk.ecg_quality(cleaned, rpeaks=info.get("ECG_R_Peaks"), sampling_rate=FS, method="averageQRS")
        q = np.asarray(quality, dtype="float64")
        finite = q[np.isfinite(q)]
        return (float(np.mean(finite)) if finite.size else float("nan"), np.asarray(info.get("ECG_R_Peaks", []), dtype=int))
    except Exception:
        return float("nan"), None


def _proxy_sqi_lead(signal: np.ndarray) -> float:
    x = np.asarray(signal, dtype="float32")
    finite = x[np.isfinite(x)]
    if finite.size < FS:
        return 0.0
    score = 1.0
    finite_ratio = float(finite.size / max(1, x.size))
    score *= finite_ratio
    amp = float(np.nanmax(finite) - np.nanmin(finite))
    std = float(np.nanstd(finite))
    if std < FLATLINE_STD_THRESHOLD or amp < 0.02:
        score *= 0.1
    if float(np.nanmax(np.abs(finite))) > EXTREME_AMPLITUDE_MV:
        score *= 0.4
    diff = np.diff(finite)
    if diff.size:
        mad = float(np.median(np.abs(diff - np.median(diff)))) + 1e-8
        noise_ratio = min(1.0, mad / (std + 1e-8)) if std > 0 else 1.0
        score *= max(0.25, 1.0 - 0.5 * noise_ratio)
    return float(max(0.0, min(1.0, score)))


def _per_lead_sqi(signal: np.ndarray) -> list[float]:
    values: list[float] = []
    for idx in range(signal.shape[1]):
        if idx == 1:
            q, _ = _sqi_one_lead(signal[:, idx])
            values.append(float(q) if math.isfinite(q) else _proxy_sqi_lead(signal[:, idx]))
        else:
            values.append(_proxy_sqi_lead(signal[:, idx]))
    return values


def _waveform_hr_qrs(lead2: np.ndarray) -> tuple[float, float]:
    nk = _get_nk()
    try:
        cleaned = nk.ecg_clean(np.asarray(lead2, dtype="float32"), sampling_rate=FS, method="neurokit")
        _, peaks_info = nk.ecg_peaks(cleaned, sampling_rate=FS, method="neurokit")
        rpeaks = np.asarray(peaks_info.get("ECG_R_Peaks", []), dtype=int)
        hr = float("nan")
        if rpeaks.size >= 2:
            rr_ms = np.diff(rpeaks) / FS * 1000.0
            rr_ms = rr_ms[np.isfinite(rr_ms) & (rr_ms > 0)]
            if rr_ms.size:
                hr = float(60000.0 / np.mean(rr_ms))
        qrs = float("nan")
        if rpeaks.size:
            _, waves = nk.ecg_delineate(cleaned, rpeaks=rpeaks, sampling_rate=FS, method="dwt", show=False, check=False)
            onsets = np.asarray(waves.get("ECG_R_Onsets", []), dtype="float64")
            offsets = np.asarray(waves.get("ECG_R_Offsets", []), dtype="float64")
            if onsets.size and offsets.size:
                n = min(onsets.size, offsets.size)
                dur = (offsets[:n] - onsets[:n]) / FS * 1000.0
                dur = dur[np.isfinite(dur) & (dur > 0) & (dur < 300)]
                if dur.size:
                    qrs = float(np.median(dur))
        return hr, qrs
    except Exception:
        return float("nan"), float("nan")


def _sqi_tier(sqi: float | None) -> str:
    if sqi is None or not math.isfinite(float(sqi)):
        return "low"
    if sqi >= 0.8:
        return "high"
    if sqi >= 0.6:
        return "medium"
    return "low"


def _report_flag(text: str, waveform_hr: float, machine_hr: float) -> bool:
    t = (text or "").lower()
    rates = [x for x in (waveform_hr, machine_hr) if math.isfinite(float(x))]
    if not rates:
        return False
    says_tachy = "tachy" in t
    says_brady = "brady" in t or "bradic" in t
    says_af = bool(re.search(r"\b(a[- ]?fib|afib|atrial fibrillation)\b", t))
    if says_tachy and max(rates) < 100:
        return True
    if says_brady and min(rates) > 60:
        return True
    if says_af and len(rates) == 2 and abs(rates[0] - rates[1]) > 25:
        return True
    return False


def _worker(task: dict[str, Any]) -> dict[str, Any]:
    notes: list[str] = []
    sid = int(task["study_id"])
    subject_id = int(task["subject_id"])
    machine_hr = float("nan")
    rr = _safe_float(task.get("rr_interval"))
    if rr and rr > 0:
        machine_hr = float(60000.0 / rr)
    else:
        fallback_hr = _safe_float(task.get("machine_hr_bpm"))
        if fallback_hr is not None:
            machine_hr = float(fallback_hr)
    qrs_onset = _safe_float(task.get("qrs_onset"))
    qrs_end = _safe_float(task.get("qrs_end"))
    machine_qrs = float("nan")
    if qrs_onset is not None and qrs_end is not None:
        machine_qrs = float(qrs_end - qrs_onset)
    elif _safe_float(task.get("machine_qrs_ms")) is not None:
        machine_qrs = float(task["machine_qrs_ms"])

    text = "" if task.get("T_machine") is None else str(task.get("T_machine"))
    text_ok = bool(text.strip())
    image_clean_ok = bool(task.get("image_clean_ok", False))
    image_scanlike_ok = bool(task.get("image_scanlike_ok", False))

    base = {
        "study_id": sid,
        "subject_id": subject_id,
        "decode_ok": False,
        "length_ok": False,
        "lead_count_ok": False,
        "lead_names_ok": False,
        "nan_inf_flag": False,
        "flatline_lead_flag": False,
        "flatline_leads": [],
        "extreme_amplitude_flag": False,
        "duplicate_waveform_flag": False,
        "duplicate_group_id": None,
        "sqi_per_lead": [float("nan")] * len(LEAD_ORDER),
        "sqi_aggregate": float("nan"),
        "sqi_tier": "low",
        "waveform_hr_bpm": float("nan"),
        "machine_hr_bpm": machine_hr,
        "hr_consistency_flag": False,
        "waveform_qrs_ms": float("nan"),
        "machine_qrs_ms": machine_qrs,
        "qrs_consistency_flag": False,
        "report_consistency_flag": False,
        "image_clean_ok": image_clean_ok,
        "image_scanlike_ok": image_scanlike_ok,
        "text_ok": text_ok,
        "notes": "",
        "_duplicate_key": None,
    }
    try:
        lead2_row = task.get("lead2_row")
        twelve_row = task.get("twelve_row")
        lead2_path = task.get("lead2_path")
        twelve_path = task.get("twelve_path")
        if lead2_row is None or twelve_row is None or not lead2_path or not twelve_path:
            notes.append("signal_locator_missing")
            base["notes"] = ";".join(notes)
            return base
        lead2 = np.asarray(_get_h5(str(lead2_path))["signal"][int(lead2_row)], dtype="float32")
        twelve_h5 = _get_h5(str(twelve_path))
        signal = np.asarray(twelve_h5["signal"][int(twelve_row)], dtype="float32")
        attr_leads = json.loads(str(twelve_h5.attrs.get("lead_order", "[]")))
        base["decode_ok"] = True
        base["length_ok"] = bool(signal.shape[0] == SAMPLES_PER_RECORD and lead2.shape[0] == SAMPLES_PER_RECORD)
        base["lead_count_ok"] = bool(signal.ndim == 2 and signal.shape[1] == len(LEAD_ORDER))
        base["lead_names_ok"] = bool(set(attr_leads) == EXPECTED_LEADS and list(attr_leads) == LEAD_ORDER)
        base["nan_inf_flag"] = bool((not np.isfinite(signal).all()) or (not np.isfinite(lead2).all()))
        base["extreme_amplitude_flag"] = bool(np.nanmax(np.abs(signal)) > EXTREME_AMPLITUDE_MV) if signal.size else False
        flat = _flatline_leads(signal) if signal.ndim == 2 and signal.shape[1] == len(LEAD_ORDER) else LEAD_ORDER[:]
        base["flatline_leads"] = flat
        base["flatline_lead_flag"] = bool(flat)
        base["_duplicate_key"] = _signal_key(lead2)

        sqi_values = _per_lead_sqi(signal) if base["lead_count_ok"] else [float("nan")] * len(LEAD_ORDER)
        finite_sqi = [x for x in sqi_values if math.isfinite(float(x))]
        aggregate = float(np.mean(finite_sqi)) if finite_sqi else float("nan")
        waveform_hr, waveform_qrs = _waveform_hr_qrs(lead2)
        base["sqi_per_lead"] = sqi_values
        base["sqi_aggregate"] = aggregate
        base["sqi_tier"] = _sqi_tier(aggregate)
        base["waveform_hr_bpm"] = waveform_hr
        base["waveform_qrs_ms"] = waveform_qrs
        if math.isfinite(waveform_hr) and math.isfinite(machine_hr) and machine_hr > 0:
            abs_diff = abs(waveform_hr - machine_hr)
            rel_diff = abs_diff / machine_hr
            base["hr_consistency_flag"] = bool(abs_diff > 10.0 and rel_diff > 0.15)
        if math.isfinite(waveform_qrs) and math.isfinite(machine_qrs):
            base["qrs_consistency_flag"] = bool(abs(waveform_qrs - machine_qrs) > 20.0)
        base["report_consistency_flag"] = _report_flag(text, waveform_hr, machine_hr)
        if not text_ok:
            notes.append("empty_text")
        if base["nan_inf_flag"]:
            notes.append("nan_or_inf")
        if base["flatline_lead_flag"]:
            notes.append("flatline_lead")
        if base["extreme_amplitude_flag"]:
            notes.append("extreme_amplitude")
    except Exception as exc:
        notes.append(f"decode_or_qc_error:{type(exc).__name__}")
    finally:
        rss_gb = psutil.Process(os.getpid()).memory_info().rss / 1024**3
        if rss_gb > WORKER_RAM_SOFT_GB:
            time.sleep(2.0)
    base["notes"] = ";".join(notes)
    return base


def _part_paths() -> list[Path]:
    return sorted(DATA_PROCESSED.glob("waveform_qc.part_*.parquet"))


def _part_index(path: Path) -> int:
    match = re.match(r"waveform_qc\.part_(\d{4})\.parquet$", path.name)
    if not match:
        raise ValueError(f"malformed waveform QC part filename: {path.name}")
    return int(match.group(1))


def _completed_from_parts() -> set[int]:
    completed: set[int] = set()
    for part in _part_paths():
        table = pq.read_table(part, columns=["study_id"])
        completed.update(int(x) for x in table.column("study_id").to_pylist())
    return completed


def _write_part(rows: list[dict[str, Any]], part_index: int) -> Path:
    if not rows:
        raise ValueError("cannot write empty waveform QC part")
    df = pd.DataFrame(rows, columns=[field.name for field in PART_SCHEMA])
    table = pa.Table.from_pandas(df, schema=PART_SCHEMA, preserve_index=False)
    part_path = DATA_PROCESSED / f"waveform_qc.part_{part_index:04d}.parquet"
    tmp_path = DATA_PROCESSED / f"waveform_qc.part_{part_index:04d}.parquet.tmp"
    pq.write_table(table, tmp_path, compression="snappy")
    os.replace(tmp_path, part_path)
    return part_path


def _write_final_from_parts() -> int:
    parts = _part_paths()
    if not parts:
        raise RuntimeError("no waveform_qc.part_*.parquet files are available for final publish")
    table = pa.concat_tables([pq.read_table(part, schema=PART_SCHEMA) for part in parts], promote_options="none")
    df = table.to_pandas()
    df = df.sort_values("study_id").reset_index(drop=True)
    duplicate_counts = df["_duplicate_key"].value_counts(dropna=True)
    duplicate_keys = set(duplicate_counts[duplicate_counts > 1].index.tolist())
    group_map = {key: idx + 1 for idx, key in enumerate(sorted(duplicate_keys))}
    df["duplicate_waveform_flag"] = df["_duplicate_key"].map(lambda key: bool(key in duplicate_keys) if isinstance(key, str) else False)
    df["duplicate_group_id"] = df["_duplicate_key"].map(lambda key: group_map.get(key) if isinstance(key, str) else None)
    df = df[[field.name for field in FINAL_SCHEMA]]
    final_table = pa.Table.from_pandas(df, schema=FINAL_SCHEMA, preserve_index=False)
    sort_indices = pc.sort_indices(final_table, sort_keys=[("study_id", "ascending")])
    final_table = pc.take(final_table, sort_indices)
    metadata = dict(final_table.schema.metadata or {})
    metadata.update(
        {
            b"dataset_version": dataset_version_stamp().encode("utf-8"),
            b"created_at_iso": utc_now_iso().encode("utf-8"),
            b"modality_kind": b"waveform_qc",
            b"n_rows": str(final_table.num_rows).encode("utf-8"),
            b"script_commit_hash": script_commit_hash().encode("utf-8"),
        }
    )
    pq.write_table(final_table.replace_schema_metadata(metadata), WAVEFORM_QC_TMP, compression="snappy")
    os.replace(WAVEFORM_QC_TMP, WAVEFORM_QC_OUT)
    return int(final_table.num_rows)


def _load_image_sets() -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    for name, path in IMAGE_MANIFESTS.items():
        if not path.exists():
            out[name] = set()
            continue
        df = pd.read_parquet(path, columns=["study_id"])
        out[name] = set(int(x) for x in df["study_id"].dropna().tolist())
    return out


def _build_tasks() -> pd.DataFrame:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"missing metadata index: {INDEX_PATH}")
    if not SIGNALS_MANIFEST.exists():
        raise FileNotFoundError(f"missing signals manifest: {SIGNALS_MANIFEST}")
    if not MEASUREMENTS_CSV.exists():
        raise FileNotFoundError(f"missing machine measurements CSV: {MEASUREMENTS_CSV}")

    metadata = pd.read_parquet(
        INDEX_PATH,
        columns=["study_id", "subject_id", "T_machine", "machine_hr_bpm", "machine_qrs_ms"],
    )
    measurement_cols = ["study_id", "subject_id", "rr_interval", "qrs_onset", "qrs_end"]
    measurements = pd.read_csv(MEASUREMENTS_CSV, usecols=measurement_cols, low_memory=False)
    df = metadata.merge(measurements, on=["study_id", "subject_id"], how="left")

    manifest = pd.read_parquet(SIGNALS_MANIFEST, columns=["study_id", "modality_kind", "container_path", "container_row"])
    lead2 = manifest[manifest["modality_kind"] == "raw_lead2"][["study_id", "container_path", "container_row"]].rename(
        columns={"container_path": "lead2_path", "container_row": "lead2_row"}
    )
    twelve = manifest[manifest["modality_kind"] == "raw_12lead"][["study_id", "container_path", "container_row"]].rename(
        columns={"container_path": "twelve_path", "container_row": "twelve_row"}
    )
    df = df.merge(lead2, on="study_id", how="left").merge(twelve, on="study_id", how="left")
    for col in ("lead2_path", "twelve_path"):
        df[col] = df[col].map(lambda value: str(DATA_PROCESSED / str(value).replace("/", "\\")) if isinstance(value, str) else None)

    image_sets = _load_image_sets()
    clean_ok = image_sets.get("clean_lead2", set()) & image_sets.get("clean_12lead", set())
    scan_ok = image_sets.get("scanlike_lead2", set()) & image_sets.get("scanlike_12lead", set())
    df["image_clean_ok"] = df["study_id"].map(lambda sid: int(sid) in clean_ok)
    df["image_scanlike_ok"] = df["study_id"].map(lambda sid: int(sid) in scan_ok)
    return df


def _compute(log: logging.Logger) -> dict[str, Any]:
    tasks_df = _build_tasks()
    completed = _completed_from_parts()
    existing_rows = sum(pq.read_table(part, columns=["study_id"]).num_rows for part in _part_paths())
    if len(completed) != existing_rows:
        raise RuntimeError("existing waveform_qc.part_*.parquet files contain duplicate study_id values")
    pending = tasks_df[~tasks_df["study_id"].astype("int64").isin(completed)]
    tasks = []
    for row in pending.itertuples(index=False):
        item = row._asdict()
        for key in ("lead2_row", "twelve_row"):
            if pd.isna(item.get(key)):
                item[key] = None
            else:
                item[key] = int(item[key])
        tasks.append(item)
    next_part = max((_part_index(path) for path in _part_paths()), default=-1) + 1
    log.info("resume completed=%d pending=%d existing_parts=%d next_part=%d max_workers=%d max_ram_gb=%.2f", len(completed), len(tasks), len(_part_paths()), next_part, MAX_WORKERS, MAX_RAM_GB)

    written_parts: list[str] = []
    buffer: list[dict[str, Any]] = []
    processed = 0
    start = time.time()
    if tasks:
        with mp.Pool(processes=MAX_WORKERS, initializer=_init_worker, initargs=(str(LOG_DIR),)) as pool:
            iterator = pool.imap_unordered(_worker, tasks, chunksize=64)
            with logging_redirect_tqdm():
                for result in tqdm(iterator, total=len(tasks), file=sys.stderr, dynamic_ncols=True, mininterval=0.5, desc="stage 7 waveform qc"):
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
                        tqdm.write(f"stage 7 waveform_qc status: processed={processed:,}/{len(tasks):,} rate={processed / elapsed:.1f}/s rss={rss_gib:.2f}GiB")
    if buffer:
        part = _write_part(buffer, next_part)
        written_parts.append(relative(part))
        log.info("wrote final part=%s rows=%d", part.name, len(buffer))
    final_rows = _write_final_from_parts()
    log.info("published waveform_qc.parquet rows=%d", final_rows)
    return {
        "metadata_rows": int(len(tasks_df)),
        "resume_completed_rows": int(len(completed)),
        "pending_rows": int(len(tasks)),
        "written_parts": written_parts,
        "final_rows": int(final_rows),
    }


def _aggregate_worker_logs() -> dict[str, Any]:
    worker_logs = sorted(LOG_DIR.glob("worker_*.log"), key=lambda p: p.name)
    aggregate = LOG_DIR / "aggregate.log"
    with aggregate.open("w", encoding="utf-8") as out:
        for path in worker_logs:
            text = path.read_text(encoding="utf-8", errors="replace")
            if text and not text.endswith("\n"):
                text += "\n"
            out.write(text)
    archive_dir = LOG_DIR / f"archive_{time.strftime('%Y%m%d_%H%M%S')}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived = []
    for path in worker_logs:
        target = archive_dir / path.name
        shutil.move(str(path), str(target))
        archived.append(relative(target))
    all_log = LOG_DIR / "all.log"
    with all_log.open("w", encoding="utf-8") as out:
        for path in [LOG_DIR / "main.log", aggregate]:
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="replace")
                if text and not text.endswith("\n"):
                    text += "\n"
                out.write(text)
    return {"aggregate_log": relative(aggregate), "all_log": relative(all_log), "archive_dir": relative(archive_dir), "archived_worker_logs": archived}


def _validate() -> dict[str, Any]:
    metadata = pd.read_parquet(INDEX_PATH, columns=["study_id"])
    qc = pd.read_parquet(WAVEFORM_QC_OUT)
    expected = set(int(x) for x in metadata["study_id"].tolist())
    actual = set(int(x) for x in qc["study_id"].tolist())
    duplicate_sizes = qc.loc[qc["duplicate_waveform_flag"], "duplicate_group_id"].value_counts(dropna=True).astype(int).tolist()
    size_dist: dict[int, int] = {}
    for size in duplicate_sizes:
        size_dist[int(size)] = size_dist.get(int(size), 0) + 1
    required = [field.name for field in FINAL_SCHEMA]
    metadata_values = {k.decode("utf-8"): v.decode("utf-8") for k, v in (pq.ParquetFile(WAVEFORM_QC_OUT).schema_arrow.metadata or {}).items()}
    return {
        "metadata_rows": int(len(metadata)),
        "waveform_qc_rows": int(len(qc)),
        "duplicate_study_id_count": int(qc["study_id"].duplicated().sum()),
        "missing_study_id_count": int(len(expected - actual)),
        "extra_study_id_count": int(len(actual - expected)),
        "missing_required_columns": [col for col in required if col not in qc.columns],
        "decode_ok_distribution": {str(k): int(v) for k, v in qc["decode_ok"].value_counts(dropna=False).to_dict().items()},
        "length_ok_distribution": {str(k): int(v) for k, v in qc["length_ok"].value_counts(dropna=False).to_dict().items()},
        "lead_count_ok_distribution": {str(k): int(v) for k, v in qc["lead_count_ok"].value_counts(dropna=False).to_dict().items()},
        "lead_names_ok_distribution": {str(k): int(v) for k, v in qc["lead_names_ok"].value_counts(dropna=False).to_dict().items()},
        "nan_inf_flag_count": int(qc["nan_inf_flag"].sum()),
        "flatline_lead_flag_count": int(qc["flatline_lead_flag"].sum()),
        "extreme_amplitude_flag_count": int(qc["extreme_amplitude_flag"].sum()),
        "sqi_tier_distribution": {str(k): int(v) for k, v in qc["sqi_tier"].value_counts(dropna=False).to_dict().items()},
        "hr_mismatch_count": int(qc["hr_consistency_flag"].sum()),
        "hr_mismatch_pct": float(qc["hr_consistency_flag"].mean() * 100.0) if len(qc) else 0.0,
        "qrs_mismatch_count": int(qc["qrs_consistency_flag"].sum()),
        "qrs_mismatch_pct": float(qc["qrs_consistency_flag"].mean() * 100.0) if len(qc) else 0.0,
        "duplicate_group_count": int(qc.loc[qc["duplicate_waveform_flag"], "duplicate_group_id"].nunique(dropna=True)),
        "duplicate_group_size_distribution": size_dist,
        "report_consistency_flag_count": int(qc["report_consistency_flag"].sum()),
        "abnormal_examples": qc.loc[
            qc["nan_inf_flag"] | qc["flatline_lead_flag"] | qc["extreme_amplitude_flag"] | (~qc["decode_ok"]),
            ["study_id", "decode_ok", "nan_inf_flag", "flatline_lead_flag", "extreme_amplitude_flag", "notes"],
        ].head(10).to_dict("records"),
        "metadata": metadata_values,
    }


def _cleanup_parts() -> dict[str, Any]:
    removed = []
    for path in _part_paths():
        removed.append(relative(path))
        path.unlink()
    for path in DATA_PROCESSED.glob("waveform_qc.part_*.parquet.tmp"):
        removed.append(relative(path))
        path.unlink()
    if WAVEFORM_QC_TMP.exists():
        removed.append(relative(WAVEFORM_QC_TMP))
        WAVEFORM_QC_TMP.unlink()
    remaining = sorted(path.name for path in DATA_PROCESSED.glob("waveform_qc.part_*.parquet*"))
    return {"removed": removed, "remaining": remaining, "status": "PASS" if not remaining and not WAVEFORM_QC_TMP.exists() else "FAIL"}


def _write_done_marker(stats: dict[str, Any], elapsed_seconds: float) -> None:
    payload = {
        "stage": 7,
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
    disk_before = psutil.disk_usage(str(PROJECT_ROOT)).free / 1024**3
    log = _setup_main_logger()
    log.info("starting %s", SCRIPT_NAME)
    log.info("run command from scripts cwd: %s", RUN_COMMAND.replace("\n", " && "))
    all_pass = False
    stats: dict[str, Any] = {}
    cleanup: dict[str, Any] = {"status": "SKIP", "removed": [], "remaining": []}
    try:
        compute_stats = _compute(log)
        validation = _validate()
        row_ok = validation["waveform_qc_rows"] == validation["metadata_rows"] and validation["duplicate_study_id_count"] == 0 and validation["missing_study_id_count"] == 0 and validation["extra_study_id_count"] == 0
        required_ok = not validation["missing_required_columns"]
        metadata_ok = all(validation["metadata"].get(key) for key in ("dataset_version", "created_at_iso", "modality_kind", "n_rows", "script_commit_hash"))
        all_pass = row_ok and required_ok and metadata_ok
        if all_pass:
            cleanup = _cleanup_parts()
            all_pass = cleanup["status"] == "PASS"
        stats = {"compute": compute_stats, "validation": validation, "cleanup": cleanup, "disk_before_gib": disk_before, "disk_after_gib": psutil.disk_usage(str(PROJECT_ROOT)).free / 1024**3}
        log.info("validation row_ok=%s required_ok=%s metadata_ok=%s cleanup=%s", row_ok, required_ok, metadata_ok, cleanup["status"])
    except Exception:
        log.exception("stage 7 waveform QC failed")
        all_pass = False
        stats.setdefault("error", "see main.log")
    finally:
        log_status = _aggregate_worker_logs()
        stats["log_status"] = log_status
    elapsed = time.time() - start
    if all_pass:
        _write_done_marker(stats, elapsed)
    status_line = {
        "script": SCRIPT_NAME,
        "status": "PASS" if all_pass else "FAIL",
        "elapsed": _format_duration(elapsed),
        "output": relative(WAVEFORM_QC_OUT) if WAVEFORM_QC_OUT.exists() else None,
        "rows": stats.get("validation", {}).get("waveform_qc_rows"),
        "cleanup": cleanup.get("status"),
        "log_archive": stats.get("log_status", {}).get("archive_dir"),
    }
    sys.stdout.write(json.dumps(status_line, indent=2) + "\n")
    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    mp.freeze_support()
    main()
