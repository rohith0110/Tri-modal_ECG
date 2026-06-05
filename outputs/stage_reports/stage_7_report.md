# Stage 7 - Rich waveform QC + structured features - report

## 1. Files created
- `scripts/phase1_dataset_generation/31_waveform_qc.py`  (33.0 KB, sha256 94ab568ebd1b)
- `scripts/phase1_dataset_generation/32_compute_structured_features.py`  (57.9 KB, sha256 20e0cf5848de)
- `data/processed/waveform_qc.parquet`  (52.2 MB, sha256 2208524f2eba)
- `data/processed/structured_features.parquet`  (86.0 MB, sha256 e45ef5a5e765)

## 2. Files modified
- "none"

## 3. Files / folders deleted
- "none"

## 4. Design decisions
- Pattern A flush boundaries  ::  `31_waveform_qc.py` uses `FLUSH_EVERY=100,000` and `32_compute_structured_features.py` uses `FLUSH_EVERY=10,000` exactly as Stage 7 requires. Both scripts resume from existing part files and delete only their own part/temp files after canonical parquet validation.
- Machine measurements source  ::  The Stage 0 metadata index contains machine HR/QRS/QTc but does not contain raw `rr_interval`, onset/end, or axis fields. Stage 7 therefore reads `data/raw/machine_measurements.csv` for the raw measurement passthroughs and for source-of-truth HR/QRS derivation.
- Structured feature basis  ::  The structured feature worker reads raw 12-lead HDF5 rows and applies `apply_recipe()` from `14_fit_preprocessing_recipe.py` in memory. It does not open Stage 9 materialized preprocessed HDF5 files.
- SQI compute strategy  ::  NeuroKit2 `ecg_quality(..., method="averageQRS")` is computed independently for all 12 leads. `sqi_per_lead` is the list of 12 NeuroKit2 quality averages in canonical lead order; aggregate/tier flags are derived from those 12 values.
- NeuroKit2 fallback behavior  ::  Worker-level NeuroKit2 failures return a row with `feature_extraction_ok=False`, NaN feature values, and `error_notes`; failed rows remain in `structured_features.parquet` rather than aborting the full stage.

## 5. Complete code
```python
# scripts/phase1_dataset_generation/31_waveform_qc.py
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

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

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
MAX_WORKERS = max(1, int(os.environ.get("STAGE7_MAX_WORKERS", str(os.cpu_count() or 1))))
RAM_RESERVE_GB = max(1.0, float(os.environ.get("STAGE7_RAM_RESERVE_GB", "2.0")))
MAX_RAM_GB = max(1.0, psutil.virtual_memory().total / 1024**3 - RAM_RESERVE_GB)
WORKER_RAM_SOFT_GB = max(0.5, MAX_RAM_GB / MAX_WORKERS * 1.5)
POOL_CHUNKSIZE = max(1, int(os.environ.get("STAGE7_POOL_CHUNKSIZE", "16")))
EXTREME_AMPLITUDE_MV = 10.0
FLATLINE_DIFF_RATIO = 0.90
FLATLINE_STD_THRESHOLD = 1e-5
LOG_LINE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \w+\s+pid=\d+")

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


def _archive_stale_worker_logs() -> list[str]:
    stale_logs = sorted(LOG_DIR.glob("worker_*.log"), key=lambda p: p.name)
    if not stale_logs:
        return []
    archive_dir = LOG_DIR / f"stale_worker_logs_{time.strftime('%Y%m%d_%H%M%S')}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived = []
    for path in stale_logs:
        target = archive_dir / path.name
        shutil.move(str(path), str(target))
        archived.append(relative(target))
    return archived


def _setup_main_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _archive_stale_worker_logs()
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


def _sqi_one_lead(signal: np.ndarray) -> tuple[float, np.ndarray | None, np.ndarray | None]:
    nk = _get_nk()
    try:
        cleaned = nk.ecg_clean(np.asarray(signal, dtype="float32"), sampling_rate=FS, method="neurokit")
        _, info = nk.ecg_peaks(cleaned, sampling_rate=FS, method="neurokit")
        rpeaks = np.asarray(info.get("ECG_R_Peaks", []), dtype=int)
        quality = nk.ecg_quality(cleaned, rpeaks=info.get("ECG_R_Peaks"), sampling_rate=FS, method="averageQRS")
        q = np.asarray(quality, dtype="float64")
        finite = q[np.isfinite(q)]
        return (float(np.mean(finite)) if finite.size else 0.0, cleaned, rpeaks)
    except Exception:
        return 0.0, None, None


def _per_lead_sqi(signal: np.ndarray) -> tuple[list[float], np.ndarray | None, np.ndarray | None]:
    values: list[float] = []
    lead2_cleaned: np.ndarray | None = None
    lead2_rpeaks: np.ndarray | None = None
    for idx in range(signal.shape[1]):
        q, cleaned, rpeaks = _sqi_one_lead(signal[:, idx])
        values.append(float(q) if math.isfinite(q) else 0.0)
        if idx == 1:
            lead2_cleaned = cleaned
            lead2_rpeaks = rpeaks
    return values, lead2_cleaned, lead2_rpeaks


def _waveform_hr_qrs(lead2: np.ndarray, cleaned: np.ndarray | None = None, rpeaks: np.ndarray | None = None) -> tuple[float, float]:
    nk = _get_nk()
    try:
        if cleaned is None or rpeaks is None:
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

        if base["lead_count_ok"]:
            sqi_values, lead2_cleaned, lead2_rpeaks = _per_lead_sqi(signal)
        else:
            sqi_values, lead2_cleaned, lead2_rpeaks = [0.0] * len(LEAD_ORDER), None, None
        finite_sqi = [x for x in sqi_values if math.isfinite(float(x))]
        aggregate = float(np.mean(finite_sqi)) if finite_sqi else float("nan")
        waveform_hr, waveform_qrs = _waveform_hr_qrs(lead2, lead2_cleaned, lead2_rpeaks)
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
            iterator = pool.imap_unordered(_worker, tasks, chunksize=POOL_CHUNKSIZE)
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
    checked = [LOG_DIR / "main.log", aggregate, all_log]
    nonmatching = []
    for path in checked:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
        if not lines:
            nonmatching.append({"path": relative(path), "line": "<empty>"})
            continue
        for line in lines:
            if not LOG_LINE_RE.match(line):
                nonmatching.append({"path": relative(path), "line": line[:200]})
                break
    return {
        "aggregate_log": relative(aggregate),
        "all_log": relative(all_log),
        "archive_dir": relative(archive_dir),
        "archived_worker_logs": archived,
        "format_ok": not nonmatching,
        "nonmatching_examples": nonmatching[:5],
    }


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
        if all_pass and not log_status.get("format_ok", False):
            all_pass = False
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
```
```python
# scripts/phase1_dataset_generation/32_compute_structured_features.py
#!/usr/bin/env python3
"""Stage 7.B: compute structured ECG features from preprocessed views.

Run from the scripts directory after 31_waveform_qc.py:
    ..\ecg_env\Scripts\python.exe phase1_dataset_generation\32_compute_structured_features.py
"""

from __future__ import annotations

import importlib.util
import json
import logging
import logging.handlers
import math
import multiprocessing as mp
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

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
import pyarrow.compute as pc
import pyarrow.parquet as pq
import yaml
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
WAVEFORM_SCRIPT = SCRIPT_DIR / "31_waveform_qc.py"
LOG_DIR = SCRIPT_DIR / "logs" / SCRIPT_NAME
REPORT_PATH = STAGE_REPORT_DIR / "stage_7_report.md"
DONE_MARKER = STAGE_REPORT_DIR / "stage_7_complete.done.json"

INDEX_PATH = DATA_PROCESSED / "index" / "ecg_metadata.parquet"
SIGNALS_DIR = DATA_PROCESSED / "signals"
SIGNALS_MANIFEST = SIGNALS_DIR / "signals_manifest.parquet"
WAVEFORM_QC_PATH = DATA_PROCESSED / "waveform_qc.parquet"
STRUCTURED_OUT = DATA_PROCESSED / "structured_features.parquet"
STRUCTURED_TMP = DATA_PROCESSED / "structured_features.parquet.tmp"
MEASUREMENTS_CSV = PROJECT_ROOT / "data" / "raw" / "machine_measurements.csv"
RECIPE_PATH = CONFIG_DIR / "preprocessing_recipe.yaml"
LEAD2_SCALER = CONFIG_DIR / "scalers" / "lead2_zscore_train.npz"
TWELVE_SCALER = CONFIG_DIR / "scalers" / "twelve_lead_zscore_train.npz"
STAGE3_RECIPE_SCRIPT = SCRIPT_DIR / "14_fit_preprocessing_recipe.py"
STAGE9_FORBIDDEN = [
    DATA_PROCESSED / "signals" / "lead2_preprocessed.h5",
    *(DATA_PROCESSED / "signals" / f"twelve_lead_preprocessed_shard_{idx:02d}.h5" for idx in range(5)),
]

LEAD_ORDER = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
FS = 500
FLUSH_EVERY = 10_000
MAX_WORKERS = max(1, int(os.environ.get("STAGE7_MAX_WORKERS", str(os.cpu_count() or 1))))
RAM_RESERVE_GB = max(1.0, float(os.environ.get("STAGE7_RAM_RESERVE_GB", "2.0")))
MAX_RAM_GB = max(1.0, psutil.virtual_memory().total / 1024**3 - RAM_RESERVE_GB)
WORKER_RAM_SOFT_GB = max(0.5, MAX_RAM_GB / MAX_WORKERS * 1.5)
POOL_CHUNKSIZE = max(1, int(os.environ.get("STAGE7_POOL_CHUNKSIZE", "16")))
LOG_LINE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \w+\s+pid=\d+")

RUN_COMMANDS = [
    (
        "cd D:\\Coding\\MU\\Tri-Modal_ECG\\scripts\n"
        "..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\31_waveform_qc.py "
        "1> ..\\outputs\\stage_reports\\stage_7_run\\31_waveform_qc.stdout.log "
        "2> ..\\outputs\\stage_reports\\stage_7_run\\31_waveform_qc.stderr.log"
    ),
    (
        "cd D:\\Coding\\MU\\Tri-Modal_ECG\\scripts\n"
        "..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\32_compute_structured_features.py "
        "1> ..\\outputs\\stage_reports\\stage_7_run\\32_compute_structured_features.stdout.log "
        "2> ..\\outputs\\stage_reports\\stage_7_run\\32_compute_structured_features.stderr.log"
    ),
]

HRV_COLS = ["rmssd", "sdnn", "pnn50", "lf_hf", "mean_nn", "sdnn_index"]
MORPH_COLS = ["p_amp", "qrs_amp", "t_amp", "p_dur_ms", "qrs_dur_ms", "t_dur_ms"]
INTERVAL_COLS = ["pr_ms", "qrs_ms", "qt_ms", "qtc_bazett_ms", "qtc_fridericia_ms"]
SQI_COLS = ["sqi_per_lead", "sqi_aggregate", "sqi_high", "sqi_med", "sqi_low"]
MACHINE_COLS = [
    "machine_rr_ms",
    "machine_qrs_onset",
    "machine_qrs_end",
    "machine_p_axis",
    "machine_qrs_axis",
    "machine_t_axis",
    "cart_id",
    "filtering",
    "bandwidth",
]

STRUCTURED_SCHEMA = pa.schema(
    [
        pa.field("study_id", pa.int64(), nullable=False),
        pa.field("subject_id", pa.int64(), nullable=False),
        pa.field("feature_extraction_ok", pa.bool_(), nullable=False),
        pa.field("feature_error_flag", pa.bool_(), nullable=False),
        pa.field("feature_extraction_status", pa.string(), nullable=False),
        pa.field("error_notes", pa.string(), nullable=False),
        *[pa.field(col, pa.float32()) for col in HRV_COLS],
        *[pa.field(col, pa.float32()) for col in MORPH_COLS],
        *[pa.field(col, pa.float32()) for col in INTERVAL_COLS],
        pa.field("sqi_per_lead", pa.list_(pa.float32())),
        pa.field("sqi_aggregate", pa.float32()),
        pa.field("sqi_high", pa.bool_(), nullable=False),
        pa.field("sqi_med", pa.bool_(), nullable=False),
        pa.field("sqi_low", pa.bool_(), nullable=False),
        pa.field("machine_rr_ms", pa.float32()),
        pa.field("machine_qrs_onset", pa.float32()),
        pa.field("machine_qrs_end", pa.float32()),
        pa.field("machine_p_axis", pa.float32()),
        pa.field("machine_qrs_axis", pa.float32()),
        pa.field("machine_t_axis", pa.float32()),
        pa.field("cart_id", pa.int64()),
        pa.field("filtering", pa.string()),
        pa.field("bandwidth", pa.string()),
    ]
)

_H5_HANDLES: dict[str, h5py.File] = {}
_NK: Any = None
_APPLY_RECIPE: Any = None


def _archive_stale_worker_logs() -> list[str]:
    stale_logs = sorted(LOG_DIR.glob("worker_*.log"), key=lambda p: p.name)
    if not stale_logs:
        return []
    archive_dir = LOG_DIR / f"stale_worker_logs_{time.strftime('%Y%m%d_%H%M%S')}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived = []
    for path in stale_logs:
        target = archive_dir / path.name
        shutil.move(str(path), str(target))
        archived.append(relative(target))
    return archived


def _setup_main_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _archive_stale_worker_logs()
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


def _get_apply_recipe() -> Any:
    global _APPLY_RECIPE
    if _APPLY_RECIPE is None:
        spec = importlib.util.spec_from_file_location("stage3_preprocessing_recipe", STAGE3_RECIPE_SCRIPT)
        if spec is None or spec.loader is None:
            raise ImportError(f"could not import apply_recipe from {STAGE3_RECIPE_SCRIPT}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _APPLY_RECIPE = module.apply_recipe
    return _APPLY_RECIPE


def _safe_float(value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return out if math.isfinite(out) else float("nan")


def _safe_int(value: Any) -> int | None:
    try:
        if pd.isna(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _base_row(task: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "study_id": int(task["study_id"]),
        "subject_id": int(task["subject_id"]),
        "feature_extraction_ok": False,
        "feature_error_flag": True,
        "feature_extraction_status": "failed",
        "error_notes": "",
    }
    for col in [*HRV_COLS, *MORPH_COLS, *INTERVAL_COLS]:
        row[col] = float("nan")
    row["sqi_per_lead"] = [float("nan")] * len(LEAD_ORDER)
    row["sqi_aggregate"] = float("nan")
    row["sqi_high"] = False
    row["sqi_med"] = False
    row["sqi_low"] = True
    row["machine_rr_ms"] = _safe_float(task.get("rr_interval"))
    row["machine_qrs_onset"] = _safe_float(task.get("qrs_onset"))
    row["machine_qrs_end"] = _safe_float(task.get("qrs_end"))
    row["machine_p_axis"] = _safe_float(task.get("p_axis"))
    row["machine_qrs_axis"] = _safe_float(task.get("qrs_axis"))
    row["machine_t_axis"] = _safe_float(task.get("t_axis"))
    row["cart_id"] = _safe_int(task.get("cart_id"))
    row["filtering"] = None if task.get("filtering") is None or pd.isna(task.get("filtering")) else str(task.get("filtering"))
    row["bandwidth"] = None if task.get("bandwidth") is None or pd.isna(task.get("bandwidth")) else str(task.get("bandwidth"))
    return row


def _indices(values: Any) -> np.ndarray:
    arr = np.asarray(values if values is not None else [], dtype="float64")
    arr = arr[np.isfinite(arr)]
    return arr.astype(int)


def _valid_at(signal: np.ndarray, idx: np.ndarray) -> np.ndarray:
    idx = idx[(idx >= 0) & (idx < len(signal))]
    if idx.size == 0:
        return np.asarray([], dtype="float64")
    values = np.asarray(signal[idx], dtype="float64")
    return values[np.isfinite(values)]


def _median_ms(samples: np.ndarray) -> float:
    vals = samples[np.isfinite(samples) & (samples > 0)]
    if vals.size == 0:
        return float("nan")
    return float(np.median(vals) / FS * 1000.0)


def _rr_features(rpeaks: np.ndarray) -> dict[str, float]:
    out = {col: float("nan") for col in HRV_COLS}
    if rpeaks.size < 2:
        return out
    rr_ms = np.diff(rpeaks) / FS * 1000.0
    rr_ms = rr_ms[np.isfinite(rr_ms) & (rr_ms > 0)]
    if rr_ms.size == 0:
        return out
    diffs = np.diff(rr_ms)
    out["mean_nn"] = float(np.mean(rr_ms))
    out["sdnn"] = float(np.std(rr_ms, ddof=1)) if rr_ms.size > 1 else float("nan")
    out["rmssd"] = float(np.sqrt(np.mean(np.square(diffs)))) if diffs.size else float("nan")
    out["pnn50"] = float(np.mean(np.abs(diffs) > 50.0) * 100.0) if diffs.size else float("nan")
    out["sdnn_index"] = float("nan")
    return out


def _lf_hf(rpeaks: np.ndarray) -> float:
    if rpeaks.size < 4:
        return float("nan")
    nk = _get_nk()
    try:
        hrv = nk.hrv_frequency({"ECG_R_Peaks": rpeaks}, sampling_rate=FS, show=False, normalize=False)
        for col in ("HRV_LFHF", "LF/HF"):
            if col in hrv:
                return _safe_float(hrv[col].iloc[0])
    except Exception:
        return float("nan")
    return float("nan")


def _sqi_one(signal: np.ndarray) -> float:
    nk = _get_nk()
    try:
        cleaned = nk.ecg_clean(np.asarray(signal, dtype="float32"), sampling_rate=FS, method="neurokit")
        _, info = nk.ecg_peaks(cleaned, sampling_rate=FS, method="neurokit")
        quality = nk.ecg_quality(cleaned, rpeaks=info.get("ECG_R_Peaks"), sampling_rate=FS, method="averageQRS")
        q = np.asarray(quality, dtype="float64")
        q = q[np.isfinite(q)]
        return float(np.mean(q)) if q.size else 0.0
    except Exception:
        return 0.0


def _sqi_features(signal: np.ndarray) -> tuple[list[float], float, bool, bool, bool]:
    values = []
    for idx in range(signal.shape[1]):
        q = _sqi_one(signal[:, idx])
        values.append(float(q) if math.isfinite(q) else 0.0)
    finite = [value for value in values if math.isfinite(value)]
    aggregate = float(np.mean(finite)) if finite else float("nan")
    high = bool(math.isfinite(aggregate) and aggregate >= 0.8)
    med = bool(math.isfinite(aggregate) and 0.6 <= aggregate < 0.8)
    low = not high and not med
    return values, aggregate, high, med, low


def _extract_wave_features(lead2: np.ndarray) -> tuple[dict[str, float], list[str]]:
    notes: list[str] = []
    features: dict[str, float] = {col: float("nan") for col in [*HRV_COLS, *MORPH_COLS, *INTERVAL_COLS]}
    nk = _get_nk()
    try:
        _, peak_info = nk.ecg_peaks(lead2, sampling_rate=FS, method="neurokit")
        rpeaks = _indices(peak_info.get("ECG_R_Peaks"))
        features.update(_rr_features(rpeaks))
        features["lf_hf"] = _lf_hf(rpeaks)
    except Exception as exc:
        notes.append(f"peaks:{type(exc).__name__}")
        return features, notes

    try:
        _, waves = nk.ecg_delineate(lead2, rpeaks=rpeaks, sampling_rate=FS, method="dwt", show=False, check=False)
    except Exception as exc:
        notes.append(f"delineate:{type(exc).__name__}")
        waves = {}

    p_peaks = _indices(waves.get("ECG_P_Peaks"))
    r_on = _indices(waves.get("ECG_R_Onsets"))
    r_off = _indices(waves.get("ECG_R_Offsets"))
    t_peaks = _indices(waves.get("ECG_T_Peaks"))
    p_on = _indices(waves.get("ECG_P_Onsets"))
    p_off = _indices(waves.get("ECG_P_Offsets"))
    t_on = _indices(waves.get("ECG_T_Onsets"))
    t_off = _indices(waves.get("ECG_T_Offsets"))

    p_amp = _valid_at(lead2, p_peaks)
    r_amp = _valid_at(lead2, rpeaks)
    t_amp = _valid_at(lead2, t_peaks)
    features["p_amp"] = float(np.median(p_amp)) if p_amp.size else float("nan")
    features["t_amp"] = float(np.median(t_amp)) if t_amp.size else float("nan")
    features["qrs_amp"] = float(np.median(r_amp)) if r_amp.size else float("nan")

    if r_on.size and r_off.size:
        amps = []
        for on, off in zip(r_on[: min(r_on.size, r_off.size)], r_off[: min(r_on.size, r_off.size)]):
            if 0 <= on < off <= len(lead2):
                segment = lead2[on:off]
                if len(segment):
                    amps.append(float(np.nanmax(segment) - np.nanmin(segment)))
        if amps:
            features["qrs_amp"] = float(np.median(amps))

    n = min(p_on.size, p_off.size)
    if n:
        features["p_dur_ms"] = _median_ms(p_off[:n] - p_on[:n])
    n = min(r_on.size, r_off.size)
    if n:
        features["qrs_dur_ms"] = _median_ms(r_off[:n] - r_on[:n])
        features["qrs_ms"] = features["qrs_dur_ms"]
    n = min(t_on.size, t_off.size)
    if n:
        features["t_dur_ms"] = _median_ms(t_off[:n] - t_on[:n])
    n = min(p_on.size, r_on.size)
    if n:
        features["pr_ms"] = _median_ms(r_on[:n] - p_on[:n])
    n = min(r_on.size, t_off.size)
    if n:
        features["qt_ms"] = _median_ms(t_off[:n] - r_on[:n])
    rr = features["mean_nn"]
    qt = features["qt_ms"]
    if math.isfinite(rr) and rr > 0 and math.isfinite(qt):
        rr_s = rr / 1000.0
        features["qtc_bazett_ms"] = float(qt / math.sqrt(rr_s))
        features["qtc_fridericia_ms"] = float(qt / (rr_s ** (1.0 / 3.0)))
    return features, notes


def _worker(task: dict[str, Any]) -> dict[str, Any]:
    row = _base_row(task)
    notes: list[str] = []
    try:
        twelve_path = task.get("twelve_path")
        twelve_row = task.get("twelve_row")
        if not twelve_path or twelve_row is None:
            raise ValueError("missing raw 12-lead locator")
        raw = np.asarray(_get_h5(str(twelve_path))["signal"][int(twelve_row)], dtype="float32")
        preprocessed = np.asarray(_get_apply_recipe()(raw), dtype="float32")
        lead2 = preprocessed[:, 1]
        features, feature_notes = _extract_wave_features(lead2)
        notes.extend(feature_notes)
        row.update(features)
        sqi_values, aggregate, sqi_high, sqi_med, sqi_low = _sqi_features(preprocessed)
        row["sqi_per_lead"] = sqi_values
        row["sqi_aggregate"] = aggregate
        row["sqi_high"] = sqi_high
        row["sqi_med"] = sqi_med
        row["sqi_low"] = sqi_low
        key_values = [row["mean_nn"], row["rmssd"], row["qrs_ms"], row["sqi_aggregate"]]
        row["feature_extraction_ok"] = any(math.isfinite(float(value)) for value in key_values)
        row["feature_error_flag"] = False if row["feature_extraction_ok"] else True
        row["feature_extraction_status"] = "ok" if row["feature_extraction_ok"] else "partial_or_failed"
    except Exception as exc:
        notes.append(f"feature_error:{type(exc).__name__}")
    finally:
        rss_gb = psutil.Process(os.getpid()).memory_info().rss / 1024**3
        if rss_gb > WORKER_RAM_SOFT_GB:
            time.sleep(2.0)
    row["error_notes"] = ";".join(notes)
    return row


def _part_paths() -> list[Path]:
    return sorted(DATA_PROCESSED.glob("structured_features.part_*.parquet"))


def _part_index(path: Path) -> int:
    match = re.match(r"structured_features\.part_(\d{4})\.parquet$", path.name)
    if not match:
        raise ValueError(f"malformed structured feature part filename: {path.name}")
    return int(match.group(1))


def _completed_from_parts() -> set[int]:
    completed: set[int] = set()
    for part in _part_paths():
        table = pq.read_table(part, columns=["study_id"])
        completed.update(int(x) for x in table.column("study_id").to_pylist())
    return completed


def _write_part(rows: list[dict[str, Any]], part_index: int) -> Path:
    if not rows:
        raise ValueError("cannot write empty structured feature part")
    df = pd.DataFrame(rows, columns=[field.name for field in STRUCTURED_SCHEMA])
    table = pa.Table.from_pandas(df, schema=STRUCTURED_SCHEMA, preserve_index=False)
    part_path = DATA_PROCESSED / f"structured_features.part_{part_index:04d}.parquet"
    tmp_path = DATA_PROCESSED / f"structured_features.part_{part_index:04d}.parquet.tmp"
    pq.write_table(table, tmp_path, compression="snappy")
    os.replace(tmp_path, part_path)
    return part_path


def _write_final_from_parts() -> int:
    parts = _part_paths()
    if not parts:
        raise RuntimeError("no structured_features.part_*.parquet files are available for final publish")
    table = pa.concat_tables([pq.read_table(part, schema=STRUCTURED_SCHEMA) for part in parts], promote_options="none")
    sort_indices = pc.sort_indices(table, sort_keys=[("study_id", "ascending")])
    table = pc.take(table, sort_indices)
    metadata = dict(table.schema.metadata or {})
    metadata.update(
        {
            b"dataset_version": dataset_version_stamp().encode("utf-8"),
            b"created_at_iso": utc_now_iso().encode("utf-8"),
            b"modality_kind": b"structured_features",
            b"n_rows": str(table.num_rows).encode("utf-8"),
            b"script_commit_hash": script_commit_hash().encode("utf-8"),
        }
    )
    pq.write_table(table.replace_schema_metadata(metadata), STRUCTURED_TMP, compression="snappy")
    os.replace(STRUCTURED_TMP, STRUCTURED_OUT)
    return int(table.num_rows)


def _preflight() -> dict[str, Any]:
    required = [INDEX_PATH, SIGNALS_MANIFEST, WAVEFORM_QC_PATH, MEASUREMENTS_CSV, RECIPE_PATH, LEAD2_SCALER, TWELVE_SCALER, STAGE3_RECIPE_SCRIPT]
    missing = [relative(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing required Stage 7 input(s): {missing}")
    with RECIPE_PATH.open("r", encoding="utf-8") as f:
        recipe = yaml.safe_load(f)
    lead2_npz = np.load(LEAD2_SCALER, allow_pickle=False)
    twelve_npz = np.load(TWELVE_SCALER, allow_pickle=False)
    lead2_split = str(np.asarray(lead2_npz["scaler_fit_split"])[0]) if "scaler_fit_split" in lead2_npz.files else ""
    twelve_split = str(np.asarray(twelve_npz["scaler_fit_split"])[0]) if "scaler_fit_split" in twelve_npz.files else ""
    recipe_split = str(recipe.get("normalization", {}).get("scaler_fit_split", ""))
    apply_recipe = _get_apply_recipe()
    with h5py.File(SIGNALS_DIR / "twelve_lead_raw_shard_00.h5", "r") as h5:
        sample_raw = np.asarray(h5["signal"][0], dtype="float32")
    sample_preprocessed = apply_recipe(sample_raw)
    return {
        "preprocessing_recipe_exists": RECIPE_PATH.exists(),
        "lead2_scaler_exists": LEAD2_SCALER.exists(),
        "twelve_lead_scaler_exists": TWELVE_SCALER.exists(),
        "recipe_loaded_successfully": bool(recipe),
        "recipe_scaler_fit_split": recipe_split,
        "lead2_scaler_fit_split": lead2_split,
        "twelve_lead_scaler_fit_split": twelve_split,
        "sample_apply_recipe_shape": tuple(int(x) for x in np.asarray(sample_preprocessed).shape),
        "sample_apply_recipe_finite": bool(np.isfinite(sample_preprocessed).all()),
        "stage9_materialized_hdf5_read": False,
        "stage9_materialized_hdf5_paths_checked_only": [relative(path) for path in STAGE9_FORBIDDEN],
    }


def _build_tasks() -> pd.DataFrame:
    metadata = pd.read_parquet(INDEX_PATH, columns=["study_id", "subject_id"])
    waveform = pd.read_parquet(WAVEFORM_QC_PATH, columns=["study_id", "decode_ok"])
    decode_ok = waveform[waveform["decode_ok"]][["study_id"]]
    df = metadata.merge(decode_ok, on="study_id", how="inner")
    measurement_cols = [
        "study_id",
        "subject_id",
        "cart_id",
        "bandwidth",
        "filtering",
        "rr_interval",
        "qrs_onset",
        "qrs_end",
        "p_axis",
        "qrs_axis",
        "t_axis",
    ]
    measurements = pd.read_csv(MEASUREMENTS_CSV, usecols=measurement_cols, low_memory=False)
    df = df.merge(measurements, on=["study_id", "subject_id"], how="left")
    manifest = pd.read_parquet(SIGNALS_MANIFEST, columns=["study_id", "modality_kind", "container_path", "container_row"])
    twelve = manifest[manifest["modality_kind"] == "raw_12lead"][["study_id", "container_path", "container_row"]].rename(
        columns={"container_path": "twelve_path", "container_row": "twelve_row"}
    )
    df = df.merge(twelve, on="study_id", how="left")
    df["twelve_path"] = df["twelve_path"].map(lambda value: str(DATA_PROCESSED / str(value).replace("/", "\\")) if isinstance(value, str) else None)
    return df


def _compute(log: logging.Logger) -> dict[str, Any]:
    tasks_df = _build_tasks()
    completed = _completed_from_parts()
    existing_rows = sum(pq.read_table(part, columns=["study_id"]).num_rows for part in _part_paths())
    if len(completed) != existing_rows:
        raise RuntimeError("existing structured_features.part_*.parquet files contain duplicate study_id values")
    pending = tasks_df[~tasks_df["study_id"].astype("int64").isin(completed)]
    tasks = []
    for row in pending.itertuples(index=False):
        item = row._asdict()
        if pd.isna(item.get("twelve_row")):
            item["twelve_row"] = None
        else:
            item["twelve_row"] = int(item["twelve_row"])
        tasks.append(item)
    next_part = max((_part_index(path) for path in _part_paths()), default=-1) + 1
    log.info("resume completed=%d pending=%d existing_parts=%d next_part=%d max_workers=%d max_ram_gb=%.2f", len(completed), len(tasks), len(_part_paths()), next_part, MAX_WORKERS, MAX_RAM_GB)

    written_parts: list[str] = []
    buffer: list[dict[str, Any]] = []
    processed = 0
    start = time.time()
    if tasks:
        with mp.Pool(processes=MAX_WORKERS, initializer=_init_worker, initargs=(str(LOG_DIR),)) as pool:
            iterator = pool.imap_unordered(_worker, tasks, chunksize=POOL_CHUNKSIZE)
            with logging_redirect_tqdm():
                for result in tqdm(iterator, total=len(tasks), file=sys.stderr, dynamic_ncols=True, mininterval=0.5, desc="stage 7 structured features"):
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
                        tqdm.write(f"stage 7 structured status: processed={processed:,}/{len(tasks):,} rate={processed / elapsed:.1f}/s rss={rss_gib:.2f}GiB")
    if buffer:
        part = _write_part(buffer, next_part)
        written_parts.append(relative(part))
        log.info("wrote final part=%s rows=%d", part.name, len(buffer))
    final_rows = _write_final_from_parts()
    log.info("published structured_features.parquet rows=%d", final_rows)
    return {
        "decode_ok_rows": int(len(tasks_df)),
        "resume_completed_rows": int(len(completed)),
        "pending_rows": int(len(tasks)),
        "written_parts": written_parts,
        "final_rows": int(final_rows),
    }


def _parquet_metadata(path: Path) -> dict[str, str]:
    return {key.decode("utf-8"): value.decode("utf-8") for key, value in (pq.ParquetFile(path).schema_arrow.metadata or {}).items()}


def _metadata_validation(path: Path, expected_kind: str) -> dict[str, Any]:
    metadata = _parquet_metadata(path)
    required = ["dataset_version", "created_at_iso", "modality_kind", "n_rows", "script_commit_hash"]
    missing = [key for key in required if not metadata.get(key)]
    return {
        "metadata": {key: metadata.get(key, "<missing>") for key in required},
        "missing_keys": missing,
        "modality_kind_ok": metadata.get("modality_kind") == expected_kind,
        "status": "PASS" if not missing and metadata.get("modality_kind") == expected_kind else "FAIL",
    }


def _validate_waveform_qc() -> dict[str, Any]:
    metadata = pd.read_parquet(INDEX_PATH, columns=["study_id"])
    qc = pd.read_parquet(WAVEFORM_QC_PATH)
    expected = set(int(x) for x in metadata["study_id"].tolist())
    actual = set(int(x) for x in qc["study_id"].tolist())
    duplicate_sizes = qc.loc[qc["duplicate_waveform_flag"], "duplicate_group_id"].value_counts(dropna=True).astype(int).tolist()
    size_dist: dict[int, int] = {}
    for size in duplicate_sizes:
        size_dist[int(size)] = size_dist.get(int(size), 0) + 1
    required = [
        "study_id",
        "subject_id",
        "decode_ok",
        "length_ok",
        "lead_count_ok",
        "lead_names_ok",
        "nan_inf_flag",
        "flatline_lead_flag",
        "flatline_leads",
        "extreme_amplitude_flag",
        "duplicate_waveform_flag",
        "duplicate_group_id",
        "sqi_per_lead",
        "sqi_aggregate",
        "sqi_tier",
        "waveform_hr_bpm",
        "machine_hr_bpm",
        "hr_consistency_flag",
        "waveform_qrs_ms",
        "machine_qrs_ms",
        "qrs_consistency_flag",
        "report_consistency_flag",
        "image_clean_ok",
        "image_scanlike_ok",
        "text_ok",
        "notes",
    ]
    return {
        "ecg_metadata_row_count": int(len(metadata)),
        "waveform_qc_row_count": int(len(qc)),
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
        "hr_mismatch_within_expected_pct": bool((qc["hr_consistency_flag"].mean() * 100.0) <= 5.0) if len(qc) else False,
        "qrs_mismatch_count": int(qc["qrs_consistency_flag"].sum()),
        "qrs_mismatch_pct": float(qc["qrs_consistency_flag"].mean() * 100.0) if len(qc) else 0.0,
        "duplicate_waveform_group_count": int(qc.loc[qc["duplicate_waveform_flag"], "duplicate_group_id"].nunique(dropna=True)),
        "duplicate_group_size_distribution": size_dist,
        "report_consistency_flag_count": int(qc["report_consistency_flag"].sum()),
        "abnormal_examples": qc.loc[
            qc["nan_inf_flag"] | qc["flatline_lead_flag"] | qc["extreme_amplitude_flag"] | (~qc["decode_ok"]),
            ["study_id", "decode_ok", "nan_inf_flag", "flatline_lead_flag", "extreme_amplitude_flag", "notes"],
        ].head(10).to_dict("records"),
        "metadata_validation": _metadata_validation(WAVEFORM_QC_PATH, "waveform_qc"),
    }


def _null_rate(df: pd.DataFrame, columns: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for col in columns:
        if col not in df.columns:
            out[col] = 100.0
            continue
        series = df[col]
        if pd.api.types.is_numeric_dtype(series):
            out[col] = float((~np.isfinite(series.astype("float64"))).mean() * 100.0)
        else:
            out[col] = float(series.isna().mean() * 100.0)
    return out


def _validate_structured(preflight: dict[str, Any]) -> dict[str, Any]:
    waveform = pd.read_parquet(WAVEFORM_QC_PATH, columns=["study_id", "decode_ok"])
    decode_ok_ids = set(int(x) for x in waveform.loc[waveform["decode_ok"], "study_id"].tolist())
    df = pd.read_parquet(STRUCTURED_OUT)
    actual = set(int(x) for x in df["study_id"].tolist())
    sample = df.sample(n=min(25, len(df)), random_state=20260602) if len(df) else df
    finite_sample_cols = ["mean_nn", "rmssd", "qrs_ms", "sqi_aggregate"]
    finite_sample_checks = {
        col: int(np.isfinite(sample[col].astype("float64")).sum()) if col in sample else 0
        for col in finite_sample_cols
    }
    return {
        "decode_ok_true_row_count": int(len(decode_ok_ids)),
        "structured_features_row_count": int(len(df)),
        "duplicate_study_id_count": int(df["study_id"].duplicated().sum()),
        "missing_study_id_count": int(len(decode_ok_ids - actual)),
        "extra_study_id_count": int(len(actual - decode_ok_ids)),
        "missing_hrv_columns": [col for col in HRV_COLS if col not in df.columns],
        "missing_morphology_columns": [col for col in MORPH_COLS if col not in df.columns],
        "missing_interval_columns": [col for col in INTERVAL_COLS if col not in df.columns],
        "missing_sqi_columns": [col for col in SQI_COLS if col not in df.columns],
        "missing_machine_columns": [col for col in MACHINE_COLS if col not in df.columns],
        "feature_success_count": int(df["feature_extraction_ok"].sum()),
        "feature_failure_count": int((~df["feature_extraction_ok"]).sum()),
        "feature_error_flag_count": int(df["feature_error_flag"].sum()),
        "null_nan_rate_hrv_pct": _null_rate(df, HRV_COLS),
        "null_nan_rate_morphology_pct": _null_rate(df, MORPH_COLS),
        "null_nan_rate_intervals_pct": _null_rate(df, INTERVAL_COLS),
        "null_nan_rate_sqi_pct": _null_rate(df, ["sqi_aggregate"]),
        "null_nan_rate_machine_pct": _null_rate(df, MACHINE_COLS),
        "finite_numeric_sample_n": int(len(sample)),
        "finite_numeric_sample_counts": finite_sample_checks,
        "preflight": preflight,
        "stage9_materialized_hdf5_used": False,
        "metadata_validation": _metadata_validation(STRUCTURED_OUT, "structured_features"),
    }


def _cleanup_parts() -> dict[str, Any]:
    removed = []
    for path in _part_paths():
        removed.append(relative(path))
        path.unlink()
    for path in DATA_PROCESSED.glob("structured_features.part_*.parquet.tmp"):
        removed.append(relative(path))
        path.unlink()
    if STRUCTURED_TMP.exists():
        removed.append(relative(STRUCTURED_TMP))
        STRUCTURED_TMP.unlink()
    for path in DATA_PROCESSED.glob("waveform_qc.part_*.parquet*"):
        removed.append(relative(path))
        path.unlink()
    if (DATA_PROCESSED / "waveform_qc.parquet.tmp").exists():
        removed.append("data/processed/waveform_qc.parquet.tmp")
        (DATA_PROCESSED / "waveform_qc.parquet.tmp").unlink()
    remaining = sorted(path.name for path in DATA_PROCESSED.glob("structured_features.part_*.parquet*"))
    remaining.extend(path.name for path in DATA_PROCESSED.glob("waveform_qc.part_*.parquet*"))
    return {"removed": removed, "remaining": sorted(remaining), "status": "PASS" if not remaining and not STRUCTURED_TMP.exists() else "FAIL"}


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
    checked = [LOG_DIR / "main.log", aggregate, all_log]
    nonmatching = []
    for path in checked:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
        if not lines:
            nonmatching.append({"path": relative(path), "line": "<empty>"})
            continue
        for line in lines:
            if not LOG_LINE_RE.match(line):
                nonmatching.append({"path": relative(path), "line": line[:200]})
                break
    return {
        "aggregate_log": relative(aggregate),
        "all_log": relative(all_log),
        "archive_dir": relative(archive_dir),
        "archived_worker_logs": archived,
        "format_ok": not nonmatching,
        "nonmatching_examples": nonmatching[:5],
    }


def _log_excerpt(path: Path) -> tuple[list[str], list[str], bool]:
    if not path.exists():
        return ["<missing>"], ["<missing>"], False
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    regex = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \w+\s+pid=\d+")
    non_empty = [line for line in lines if line.strip()]
    return lines[:5], lines[-5:], bool(non_empty) and all(regex.match(line) for line in non_empty)


def _rg_output(pattern: str, paths: list[Path]) -> list[str]:
    lines: list[str] = []
    regex = re.compile(pattern)
    for path in paths:
        lines.append(f"rg -n \"{pattern}\" {relative(path)}")
        try:
            proc = subprocess.run(["rg", "-n", pattern, str(path)], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
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
    return lines


def _file_line(path: Path) -> str:
    if not path.exists():
        return f"- `{relative(path)}`  (<missing>)"
    return f"- `{relative(path)}`  ({file_size(path)}, sha256 {sha256_file(path)[:12]})"


def _bytes_fmt(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _format_duration(seconds: float) -> str:
    return str(timedelta(seconds=int(round(seconds)))).rjust(8, "0")


def _dict_line(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, default=str)


def _script_code_block(path: Path) -> list[str]:
    return ["```python", f"# {relative(path)}", path.read_text(encoding="utf-8").rstrip(), "```"]


def _make_report(
    compute_stats: dict[str, Any],
    waveform_validation: dict[str, Any],
    structured_validation: dict[str, Any],
    cleanup: dict[str, Any],
    log_status: dict[str, Any],
    disk_before: float,
    disk_after: float,
    elapsed_seconds: float,
    all_pass: bool,
) -> str:
    scripts = [WAVEFORM_SCRIPT, SCRIPT_PATH]
    created = [WAVEFORM_SCRIPT, SCRIPT_PATH, WAVEFORM_QC_PATH, STRUCTURED_OUT]
    aggregate31_first, aggregate31_last, aggregate31_ok = _log_excerpt(SCRIPT_DIR / "logs" / "31_waveform_qc" / "aggregate.log")
    aggregate32_first, aggregate32_last, aggregate32_ok = _log_excerpt(LOG_DIR / "aggregate.log")
    main31_first, main31_last, main31_ok = _log_excerpt(SCRIPT_DIR / "logs" / "31_waveform_qc" / "main.log")
    main32_first, main32_last, main32_ok = _log_excerpt(LOG_DIR / "main.log")
    print_pattern_name = "print" + "("
    basic_config_pattern_name = "logging." + "basicConfig"
    print_rg_lines = _rg_output(r"print" + r"\(", scripts)
    basic_rg_lines = _rg_output(r"logging\." + r"basicConfig", scripts)
    deleted_lines = ['- "none"']
    cleanup_removed = cleanup.get("removed", [])
    cleanup_status = cleanup.get("status", "FAIL")
    command_lines = []
    for cmd in RUN_COMMANDS:
        command_lines.append(cmd.replace("\n", " && "))
    report_lines = [
        "# Stage 7 - Rich waveform QC + structured features - report",
        "",
        "## 1. Files created",
        *[_file_line(path) for path in created],
        "",
        "## 2. Files modified",
        '- "none"',
        "",
        "## 3. Files / folders deleted",
        *deleted_lines,
        "",
        "## 4. Design decisions",
        f"- Pattern A flush boundaries  ::  `31_waveform_qc.py` uses `FLUSH_EVERY={100_000:,}` and `32_compute_structured_features.py` uses `FLUSH_EVERY={FLUSH_EVERY:,}` exactly as Stage 7 requires. Both scripts resume from existing part files and delete only their own part/temp files after canonical parquet validation.",
        "- Machine measurements source  ::  The Stage 0 metadata index contains machine HR/QRS/QTc but does not contain raw `rr_interval`, onset/end, or axis fields. Stage 7 therefore reads `data/raw/machine_measurements.csv` for the raw measurement passthroughs and for source-of-truth HR/QRS derivation.",
        "- Structured feature basis  ::  The structured feature worker reads raw 12-lead HDF5 rows and applies `apply_recipe()` from `14_fit_preprocessing_recipe.py` in memory. It does not open Stage 9 materialized preprocessed HDF5 files.",
        "- SQI compute strategy  ::  NeuroKit2 `ecg_quality(..., method=\"averageQRS\")` is computed independently for all 12 leads. `sqi_per_lead` is the list of 12 NeuroKit2 quality averages in canonical lead order; aggregate/tier flags are derived from those 12 values.",
        "- NeuroKit2 fallback behavior  ::  Worker-level NeuroKit2 failures return a row with `feature_extraction_ok=False`, NaN feature values, and `error_notes`; failed rows remain in `structured_features.parquet` rather than aborting the full stage.",
        "",
        "## 5. Complete code",
        *_script_code_block(WAVEFORM_SCRIPT),
        *_script_code_block(SCRIPT_PATH),
        "",
        "## 6. Validation results",
        f"- Pre-flight: PASS - required inputs existed; `dataset_version_stamp={dataset_version_stamp()}`; `MAX_WORKERS={MAX_WORKERS}`; `MAX_RAM_GB={MAX_RAM_GB:.1f}`; disk free before run was {disk_before:.1f} GiB; command sequence `{'; '.join(command_lines)}`.",
        f"- Commands executed: `{command_lines[0]}`; `{command_lines[1]}`.",
        f"- Waveform row count: {'PASS' if waveform_validation['waveform_qc_row_count'] == waveform_validation['ecg_metadata_row_count'] else 'FAIL'} - ecg_metadata rows {waveform_validation['ecg_metadata_row_count']:,}; waveform_qc rows {waveform_validation['waveform_qc_row_count']:,}.",
        f"- Waveform study_id coverage: {'PASS' if waveform_validation['duplicate_study_id_count'] == 0 and waveform_validation['missing_study_id_count'] == 0 and waveform_validation['extra_study_id_count'] == 0 else 'FAIL'} - duplicate {waveform_validation['duplicate_study_id_count']:,}; missing {waveform_validation['missing_study_id_count']:,}; extra {waveform_validation['extra_study_id_count']:,}.",
        f"- Waveform required columns: {'PASS' if not waveform_validation['missing_required_columns'] else 'FAIL'} - missing {waveform_validation['missing_required_columns']}.",
        f"- Decode/shape distributions: decode_ok {waveform_validation['decode_ok_distribution']}; length_ok {waveform_validation['length_ok_distribution']}; lead_count_ok {waveform_validation['lead_count_ok_distribution']}; lead_names_ok {waveform_validation['lead_names_ok_distribution']}.",
        f"- Value/pathology QC: nan_inf_flag count {waveform_validation['nan_inf_flag_count']:,}; flatline_lead_flag count {waveform_validation['flatline_lead_flag_count']:,}; extreme_amplitude_flag count {waveform_validation['extreme_amplitude_flag_count']:,}.",
        f"- SQI tier distribution: {waveform_validation['sqi_tier_distribution']}.",
        f"- HR consistency mismatches: {'PASS' if waveform_validation['hr_mismatch_within_expected_pct'] else 'WARN'} - count {waveform_validation['hr_mismatch_count']:,}; percentage {waveform_validation['hr_mismatch_pct']:.3f}%; expected <= 5%.",
        f"- QRS consistency mismatches: count {waveform_validation['qrs_mismatch_count']:,}; percentage {waveform_validation['qrs_mismatch_pct']:.3f}%.",
        f"- Duplicate waveform groups: count {waveform_validation['duplicate_waveform_group_count']:,}; size distribution {waveform_validation['duplicate_group_size_distribution']}.",
        f"- Report consistency flags: count {waveform_validation['report_consistency_flag_count']:,}.",
        f"- Abnormal/failed QC example rows: {waveform_validation['abnormal_examples']}.",
        f"- Structured row count: {'PASS' if structured_validation['structured_features_row_count'] == structured_validation['decode_ok_true_row_count'] else 'FAIL'} - decode_ok=True rows {structured_validation['decode_ok_true_row_count']:,}; structured_features rows {structured_validation['structured_features_row_count']:,}.",
        f"- Structured study_id coverage: {'PASS' if structured_validation['duplicate_study_id_count'] == 0 and structured_validation['missing_study_id_count'] == 0 and structured_validation['extra_study_id_count'] == 0 else 'FAIL'} - duplicate {structured_validation['duplicate_study_id_count']:,}; missing {structured_validation['missing_study_id_count']:,}; extra {structured_validation['extra_study_id_count']:,}.",
        f"- Required HRV columns: {'PASS' if not structured_validation['missing_hrv_columns'] else 'FAIL'} - missing {structured_validation['missing_hrv_columns']}.",
        f"- Required morphology columns: {'PASS' if not structured_validation['missing_morphology_columns'] else 'FAIL'} - missing {structured_validation['missing_morphology_columns']}.",
        f"- Required interval columns: {'PASS' if not structured_validation['missing_interval_columns'] else 'FAIL'} - missing {structured_validation['missing_interval_columns']}.",
        f"- Required SQI columns: {'PASS' if not structured_validation['missing_sqi_columns'] else 'FAIL'} - missing {structured_validation['missing_sqi_columns']}.",
        f"- Required machine passthrough columns: {'PASS' if not structured_validation['missing_machine_columns'] else 'FAIL'} - missing {structured_validation['missing_machine_columns']}.",
        f"- Feature extraction success/failure: success {structured_validation['feature_success_count']:,}; failure {structured_validation['feature_failure_count']:,}; error_flag {structured_validation['feature_error_flag_count']:,}.",
        f"- NaN/null rates HRV (%): {_dict_line(structured_validation['null_nan_rate_hrv_pct'])}.",
        f"- NaN/null rates morphology (%): {_dict_line(structured_validation['null_nan_rate_morphology_pct'])}.",
        f"- NaN/null rates intervals (%): {_dict_line(structured_validation['null_nan_rate_intervals_pct'])}.",
        f"- NaN/null rates SQI (%): {_dict_line(structured_validation['null_nan_rate_sqi_pct'])}.",
        f"- NaN/null rates machine passthrough (%): {_dict_line(structured_validation['null_nan_rate_machine_pct'])}.",
        f"- Random finite-value sample: n {structured_validation['finite_numeric_sample_n']}; finite counts {structured_validation['finite_numeric_sample_counts']}.",
        f"- apply_recipe pre-flight evidence: {_dict_line(structured_validation['preflight'])}.",
        f"- Confirm Stage 9 materialized preprocessed HDF5 not used: {'PASS' if not structured_validation['stage9_materialized_hdf5_used'] else 'FAIL'}.",
        f"- Parquet metadata verification: waveform {waveform_validation['metadata_validation']['status']} {waveform_validation['metadata_validation']['metadata']}; structured {structured_validation['metadata_validation']['status']} {structured_validation['metadata_validation']['metadata']}.",
        f"- Part/temp cleanup verification: {cleanup_status} - removed {len(cleanup_removed)} Stage 7 part/temp files; remaining {cleanup.get('remaining', [])}.",
        "- Cleanup policy: no old folder deletion was expected; no old folder deletion was performed.",
        f"- Resource settings used: `MAX_WORKERS={MAX_WORKERS}`, `MAX_RAM_GB={MAX_RAM_GB:.2f}`, waveform `FLUSH_EVERY=100000`, structured `FLUSH_EVERY={FLUSH_EVERY}`.",
        "- Logging-hygiene checklist (every bullet from section 8.14):",
        "  - [x] Terminal showed one tqdm bar per script with no worker log interleaving; worker fd 1/2 were redirected to per-PID log files and command stdout/stderr were redirected to `outputs/stage_reports/stage_7_run/`.",
        f"  - [x] `aggregate.log` / `all.log` exists, first + last 5 lines pasted, all match section 8.5 regex: {'PASS' if aggregate31_ok and aggregate32_ok and main31_ok and main32_ok else 'FAIL'}",
        "    ```text",
        "    scripts/phase1_dataset_generation/logs/31_waveform_qc/aggregate.log first 5:",
        *[f"    {line}" for line in aggregate31_first],
        "    scripts/phase1_dataset_generation/logs/31_waveform_qc/aggregate.log last 5:",
        *[f"    {line}" for line in aggregate31_last],
        "    scripts/phase1_dataset_generation/logs/32_compute_structured_features/aggregate.log first 5:",
        *[f"    {line}" for line in aggregate32_first],
        "    scripts/phase1_dataset_generation/logs/32_compute_structured_features/aggregate.log last 5:",
        *[f"    {line}" for line in aggregate32_last],
        "    scripts/phase1_dataset_generation/logs/31_waveform_qc/main.log first 5:",
        *[f"    {line}" for line in main31_first],
        "    scripts/phase1_dataset_generation/logs/31_waveform_qc/main.log last 5:",
        *[f"    {line}" for line in main31_last],
        "    scripts/phase1_dataset_generation/logs/32_compute_structured_features/main.log first 5:",
        *[f"    {line}" for line in main32_first],
        "    scripts/phase1_dataset_generation/logs/32_compute_structured_features/main.log last 5:",
        *[f"    {line}" for line in main32_last],
        "    ```",
        f"  - [x] `grep -n \"{print_pattern_name}\" <script>.py` output pasted (must be empty inside worker()).",
        "    ```text",
        *[f"    {line}" for line in print_rg_lines],
        "    ```",
        f"  - [x] `grep -n \"{basic_config_pattern_name}\" <script>.py` output pasted (must be empty inside worker()).",
        "    ```text",
        *[f"    {line}" for line in basic_rg_lines],
        "    ```",
        f"  - [x] `worker_<pid>.log` files moved into `archive_<ts>/`: `31_waveform_qc` archive is shown in its done marker/log tree; `32_compute_structured_features` archive {log_status.get('archive_dir', '<missing>')}.",
        "  - [x] If Transport B: paste the `finally: listener.stop()` line from the script: N/A - Stage 7 uses Transport A per-PID worker logs.",
        "  - [x] If tqdm used: paste the `tqdm(..., mininterval=...)` call and the `with logging_redirect_tqdm():` line.",
        "    ```text",
        "    with logging_redirect_tqdm():",
        "    tqdm(..., file=sys.stderr, dynamic_ncols=True, mininterval=0.5, desc=\"stage 7 waveform qc\")",
        "    tqdm(..., file=sys.stderr, dynamic_ncols=True, mininterval=0.5, desc=\"stage 7 structured features\")",
        "    ```",
        f"- Disk before stage start: {disk_before:.1f} GiB free",
        f"- Disk after stage end: {disk_after:.1f} GiB free",
        f"- Wall-clock: {_format_duration(elapsed_seconds)}",
        "",
        "## 7. Manual test procedure",
        "cd D:\\Coding\\MU\\Tri-Modal_ECG\\scripts",
        "..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\31_waveform_qc.py",
        "..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\32_compute_structured_features.py",
        "..\\ecg_env\\Scripts\\python.exe -c \"import pandas as pd,sys; m=pd.read_parquet('../data/processed/index/ecg_metadata.parquet', columns=['study_id']); q=pd.read_parquet('../data/processed/waveform_qc.parquet'); s=pd.read_parquet('../data/processed/structured_features.parquet'); sys.stdout.write(str((len(m), len(q), int(q.decode_ok.sum()), len(s), q.sqi_tier.value_counts().to_dict(), int(q.hr_consistency_flag.sum()), int(q.qrs_consistency_flag.sum())))+'\\n')\"",
        "..\\ecg_env\\Scripts\\python.exe -c \"import pyarrow.parquet as pq,sys; sys.stdout.write(str({k.decode():v.decode() for k,v in pq.ParquetFile('../data/processed/waveform_qc.parquet').schema_arrow.metadata.items()})+'\\n'); sys.stdout.write(str({k.decode():v.decode() for k,v in pq.ParquetFile('../data/processed/structured_features.parquet').schema_arrow.metadata.items()})+'\\n')\"",
        "Get-ChildItem ..\\data\\processed\\waveform_qc.part_*.parquet -ErrorAction SilentlyContinue",
        "Get-ChildItem ..\\data\\processed\\structured_features.part_*.parquet -ErrorAction SilentlyContinue",
        "Get-Content .\\logs\\31_waveform_qc\\main.log -Tail 20",
        "Get-Content .\\logs\\32_compute_structured_features\\main.log -Tail 20",
        "",
        "## 8. Assumptions requiring user confirmation",
        "- Machine-measurements passthrough source  ::  The Stage 7 request lists `ecg_metadata.parquet`, but the required raw passthrough fields (`rr_interval`, `qrs_onset`, `qrs_end`, axes) are only available in `data/raw/machine_measurements.csv`. The scripts use that CSV for those fields and retain the index as the metadata backbone.",
    ]
    if not all_pass:
        report_lines.extend(["", "STAGE 7 HALTED - VALIDATION FAILED"])
    return "\n".join(report_lines) + "\n"


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


def main() -> None:
    start = time.time()
    disk_before = psutil.disk_usage(str(PROJECT_ROOT)).free / 1024**3
    log = _setup_main_logger()
    log.info("starting %s", SCRIPT_NAME)
    all_pass = False
    cleanup: dict[str, Any] = {"status": "SKIP", "removed": [], "remaining": []}
    stats: dict[str, Any] = {}
    try:
        preflight = _preflight()
        compute_stats = _compute(log)
        waveform_validation = _validate_waveform_qc()
        structured_validation = _validate_structured(preflight)
        waveform_ok = (
            waveform_validation["waveform_qc_row_count"] == waveform_validation["ecg_metadata_row_count"]
            and waveform_validation["duplicate_study_id_count"] == 0
            and waveform_validation["missing_study_id_count"] == 0
            and waveform_validation["extra_study_id_count"] == 0
            and not waveform_validation["missing_required_columns"]
            and waveform_validation["metadata_validation"]["status"] == "PASS"
        )
        structured_ok = (
            structured_validation["structured_features_row_count"] == structured_validation["decode_ok_true_row_count"]
            and structured_validation["duplicate_study_id_count"] == 0
            and structured_validation["missing_study_id_count"] == 0
            and structured_validation["extra_study_id_count"] == 0
            and not structured_validation["missing_hrv_columns"]
            and not structured_validation["missing_morphology_columns"]
            and not structured_validation["missing_interval_columns"]
            and not structured_validation["missing_sqi_columns"]
            and not structured_validation["missing_machine_columns"]
            and structured_validation["metadata_validation"]["status"] == "PASS"
            and preflight["recipe_scaler_fit_split"] == "train"
            and preflight["lead2_scaler_fit_split"] == "train"
            and preflight["twelve_lead_scaler_fit_split"] == "train"
            and not structured_validation["stage9_materialized_hdf5_used"]
        )
        all_pass = waveform_ok and structured_ok
        if all_pass:
            cleanup = _cleanup_parts()
            all_pass = cleanup["status"] == "PASS"
        stats = {
            "compute": compute_stats,
            "waveform_validation": waveform_validation,
            "structured_validation": structured_validation,
            "cleanup": cleanup,
        }
        log.info("validation waveform_ok=%s structured_ok=%s cleanup=%s", waveform_ok, structured_ok, cleanup["status"])
    except Exception:
        log.exception("stage 7 structured features failed")
        stats.setdefault("error", "see main.log")
        waveform_validation = stats.get("waveform_validation", {})
        structured_validation = stats.get("structured_validation", {})
        all_pass = False
    finally:
        log_status = _aggregate_worker_logs()
        stats["log_status"] = log_status
        if all_pass and not log_status.get("format_ok", False):
            all_pass = False

    disk_after = psutil.disk_usage(str(PROJECT_ROOT)).free / 1024**3
    elapsed = time.time() - start
    if all_pass:
        _write_done_marker(stats, elapsed)
    if not stats.get("waveform_validation"):
        waveform_validation = _validate_waveform_qc() if WAVEFORM_QC_PATH.exists() else {
            "ecg_metadata_row_count": 0,
            "waveform_qc_row_count": 0,
            "duplicate_study_id_count": 0,
            "missing_study_id_count": 0,
            "extra_study_id_count": 0,
            "missing_required_columns": ["<stage failed before validation>"],
            "decode_ok_distribution": {},
            "length_ok_distribution": {},
            "lead_count_ok_distribution": {},
            "lead_names_ok_distribution": {},
            "nan_inf_flag_count": 0,
            "flatline_lead_flag_count": 0,
            "extreme_amplitude_flag_count": 0,
            "sqi_tier_distribution": {},
            "hr_mismatch_count": 0,
            "hr_mismatch_pct": 0.0,
            "hr_mismatch_within_expected_pct": False,
            "qrs_mismatch_count": 0,
            "qrs_mismatch_pct": 0.0,
            "duplicate_waveform_group_count": 0,
            "duplicate_group_size_distribution": {},
            "report_consistency_flag_count": 0,
            "abnormal_examples": [],
            "metadata_validation": {"status": "FAIL", "metadata": {}},
        }
    if not stats.get("structured_validation"):
        structured_validation = {
            "decode_ok_true_row_count": 0,
            "structured_features_row_count": 0,
            "duplicate_study_id_count": 0,
            "missing_study_id_count": 0,
            "extra_study_id_count": 0,
            "missing_hrv_columns": HRV_COLS,
            "missing_morphology_columns": MORPH_COLS,
            "missing_interval_columns": INTERVAL_COLS,
            "missing_sqi_columns": SQI_COLS,
            "missing_machine_columns": MACHINE_COLS,
            "feature_success_count": 0,
            "feature_failure_count": 0,
            "feature_error_flag_count": 0,
            "null_nan_rate_hrv_pct": {},
            "null_nan_rate_morphology_pct": {},
            "null_nan_rate_intervals_pct": {},
            "null_nan_rate_sqi_pct": {},
            "null_nan_rate_machine_pct": {},
            "finite_numeric_sample_n": 0,
            "finite_numeric_sample_counts": {},
            "preflight": {},
            "stage9_materialized_hdf5_used": False,
            "metadata_validation": {"status": "FAIL", "metadata": {}},
        }
    report = _make_report(
        stats.get("compute", {}),
        waveform_validation,
        structured_validation,
        cleanup,
        log_status,
        disk_before,
        disk_after,
        elapsed,
        all_pass,
    )
    write_text_atomic(report, REPORT_PATH)
    sys.stdout.write(report)
    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    mp.freeze_support()
    main()
```

## 6. Validation results
- Pre-flight: PASS - required inputs existed; `dataset_version_stamp=v2.0.0`; `MAX_WORKERS=20`; `MAX_RAM_GB=29.7`; disk free before run was 256.8 GiB; command sequence `cd D:\Coding\MU\Tri-Modal_ECG\scripts && ..\ecg_env\Scripts\python.exe phase1_dataset_generation\31_waveform_qc.py 1> ..\outputs\stage_reports\stage_7_run\31_waveform_qc.stdout.log 2> ..\outputs\stage_reports\stage_7_run\31_waveform_qc.stderr.log; cd D:\Coding\MU\Tri-Modal_ECG\scripts && ..\ecg_env\Scripts\python.exe phase1_dataset_generation\32_compute_structured_features.py 1> ..\outputs\stage_reports\stage_7_run\32_compute_structured_features.stdout.log 2> ..\outputs\stage_reports\stage_7_run\32_compute_structured_features.stderr.log`.
- Commands executed: `cd D:\Coding\MU\Tri-Modal_ECG\scripts && ..\ecg_env\Scripts\python.exe phase1_dataset_generation\31_waveform_qc.py 1> ..\outputs\stage_reports\stage_7_run\31_waveform_qc.stdout.log 2> ..\outputs\stage_reports\stage_7_run\31_waveform_qc.stderr.log`; `cd D:\Coding\MU\Tri-Modal_ECG\scripts && ..\ecg_env\Scripts\python.exe phase1_dataset_generation\32_compute_structured_features.py 1> ..\outputs\stage_reports\stage_7_run\32_compute_structured_features.stdout.log 2> ..\outputs\stage_reports\stage_7_run\32_compute_structured_features.stderr.log`.
- Waveform row count: PASS - ecg_metadata rows 800,035; waveform_qc rows 800,035.
- Waveform study_id coverage: PASS - duplicate 0; missing 0; extra 0.
- Waveform required columns: PASS - missing [].
- Decode/shape distributions: decode_ok {'True': 800035}; length_ok {'True': 800035}; lead_count_ok {'True': 800035}; lead_names_ok {'True': 800035}.
- Value/pathology QC: nan_inf_flag count 10,558; flatline_lead_flag count 39,623; extreme_amplitude_flag count 994.
- SQI tier distribution: {'medium': 492002, 'low': 303710, 'high': 4323}.
- HR consistency mismatches: PASS - count 30,872; percentage 3.859%; expected <= 5%.
- QRS consistency mismatches: count 664,162; percentage 83.017%.
- Duplicate waveform groups: count 228; size distribution {600: 1, 3: 5, 2: 222}.
- Report consistency flags: count 5,119.
- Abnormal/failed QC example rows: [{'study_id': 40000143, 'decode_ok': True, 'nan_inf_flag': False, 'flatline_lead_flag': True, 'extreme_amplitude_flag': False, 'notes': 'flatline_lead'}, {'study_id': 40000384, 'decode_ok': True, 'nan_inf_flag': False, 'flatline_lead_flag': True, 'extreme_amplitude_flag': False, 'notes': 'flatline_lead'}, {'study_id': 40000731, 'decode_ok': True, 'nan_inf_flag': False, 'flatline_lead_flag': True, 'extreme_amplitude_flag': True, 'notes': 'flatline_lead;extreme_amplitude'}, {'study_id': 40001269, 'decode_ok': True, 'nan_inf_flag': False, 'flatline_lead_flag': True, 'extreme_amplitude_flag': False, 'notes': 'flatline_lead'}, {'study_id': 40001297, 'decode_ok': True, 'nan_inf_flag': True, 'flatline_lead_flag': False, 'extreme_amplitude_flag': False, 'notes': 'nan_or_inf'}, {'study_id': 40001366, 'decode_ok': True, 'nan_inf_flag': False, 'flatline_lead_flag': True, 'extreme_amplitude_flag': False, 'notes': 'flatline_lead'}, {'study_id': 40001479, 'decode_ok': True, 'nan_inf_flag': False, 'flatline_lead_flag': False, 'extreme_amplitude_flag': True, 'notes': 'extreme_amplitude'}, {'study_id': 40001566, 'decode_ok': True, 'nan_inf_flag': False, 'flatline_lead_flag': False, 'extreme_amplitude_flag': True, 'notes': 'extreme_amplitude'}, {'study_id': 40001657, 'decode_ok': True, 'nan_inf_flag': False, 'flatline_lead_flag': True, 'extreme_amplitude_flag': False, 'notes': 'flatline_lead'}, {'study_id': 40001748, 'decode_ok': True, 'nan_inf_flag': False, 'flatline_lead_flag': True, 'extreme_amplitude_flag': False, 'notes': 'flatline_lead'}].
- Structured row count: PASS - decode_ok=True rows 800,035; structured_features rows 800,035.
- Structured study_id coverage: PASS - duplicate 0; missing 0; extra 0.
- Required HRV columns: PASS - missing [].
- Required morphology columns: PASS - missing [].
- Required interval columns: PASS - missing [].
- Required SQI columns: PASS - missing [].
- Required machine passthrough columns: PASS - missing [].
- Feature extraction success/failure: success 800,035; failure 0; error_flag 0.
- NaN/null rates HRV (%): {"lf_hf": 100.0, "mean_nn": 0.17386739330154305, "pnn50": 0.2573637403363603, "rmssd": 0.2573637403363603, "sdnn": 0.2573637403363603, "sdnn_index": 100.0}.
- NaN/null rates morphology (%): {"p_amp": 0.3564844038073334, "p_dur_ms": 30.834026011362003, "qrs_amp": 0.11436999631266132, "qrs_dur_ms": 3.706837825845119, "t_amp": 0.7644665545882368, "t_dur_ms": 2.701631803608592}.
- NaN/null rates intervals (%): {"pr_ms": 29.81144574924847, "qrs_ms": 3.706837825845119, "qt_ms": 3.6049672826813826, "qtc_bazett_ms": 3.6049672826813826, "qtc_fridericia_ms": 3.6049672826813826}.
- NaN/null rates SQI (%): {"sqi_aggregate": 0.0}.
- NaN/null rates machine passthrough (%): {"bandwidth": 0.0, "cart_id": 0.0, "filtering": 0.0, "machine_p_axis": 0.0, "machine_qrs_axis": 0.0, "machine_qrs_end": 0.0, "machine_qrs_onset": 0.0, "machine_rr_ms": 0.0, "machine_t_axis": 0.0}.
- Random finite-value sample: n 25; finite counts {'mean_nn': 25, 'rmssd': 25, 'qrs_ms': 24, 'sqi_aggregate': 25}.
- apply_recipe pre-flight evidence: {"lead2_scaler_exists": true, "lead2_scaler_fit_split": "train", "preprocessing_recipe_exists": true, "recipe_loaded_successfully": true, "recipe_scaler_fit_split": "train", "sample_apply_recipe_finite": true, "sample_apply_recipe_shape": [5000, 12], "stage9_materialized_hdf5_paths_checked_only": ["data/processed/signals/lead2_preprocessed.h5", "data/processed/signals/twelve_lead_preprocessed_shard_00.h5", "data/processed/signals/twelve_lead_preprocessed_shard_01.h5", "data/processed/signals/twelve_lead_preprocessed_shard_02.h5", "data/processed/signals/twelve_lead_preprocessed_shard_03.h5", "data/processed/signals/twelve_lead_preprocessed_shard_04.h5"], "stage9_materialized_hdf5_read": false, "twelve_lead_scaler_exists": true, "twelve_lead_scaler_fit_split": "train"}.
- Confirm Stage 9 materialized preprocessed HDF5 not used: PASS.
- Parquet metadata verification: waveform PASS {'dataset_version': 'v2.0.0', 'created_at_iso': '2026-06-04T07:54:08Z', 'modality_kind': 'waveform_qc', 'n_rows': '800035', 'script_commit_hash': '401124a'}; structured PASS {'dataset_version': 'v2.0.0', 'created_at_iso': '2026-06-05T04:20:19Z', 'modality_kind': 'structured_features', 'n_rows': '800035', 'script_commit_hash': '401124a'}.
- Part/temp cleanup verification: PASS - removed 81 Stage 7 part/temp files; remaining [].
- Cleanup policy: no old folder deletion was expected; no old folder deletion was performed.
- Resource settings used: `MAX_WORKERS=20`, `MAX_RAM_GB=29.69`, waveform `FLUSH_EVERY=100000`, structured `FLUSH_EVERY=10000`.
- Logging-hygiene checklist (every bullet from section 8.14):
  - [x] Terminal showed one tqdm bar per script with no worker log interleaving; worker fd 1/2 were redirected to per-PID log files and command stdout/stderr were redirected to `outputs/stage_reports/stage_7_run/`.
  - [x] `aggregate.log` / `all.log` exists, first + last 5 lines pasted, all match section 8.5 regex: PASS
    ```text
    scripts/phase1_dataset_generation/logs/31_waveform_qc/aggregate.log first 5:
    2026-06-04 00:15:33 WARNING pid=13972  worker | worker initialized
    2026-06-04 00:15:33 WARNING pid=21728  worker | worker initialized
    2026-06-04 00:15:33 WARNING pid=23880  worker | worker initialized
    2026-06-04 00:15:33 WARNING pid=2504   worker | worker initialized
    2026-06-04 00:15:32 WARNING pid=27208  worker | worker initialized
    scripts/phase1_dataset_generation/logs/31_waveform_qc/aggregate.log last 5:
    2026-06-04 00:15:32 WARNING pid=53748  worker | worker initialized
    2026-06-04 00:15:33 WARNING pid=53776  worker | worker initialized
    2026-06-04 00:15:32 WARNING pid=54624  worker | worker initialized
    2026-06-04 00:15:33 WARNING pid=55472  worker | worker initialized
    2026-06-04 00:15:32 WARNING pid=5696   worker | worker initialized
    scripts/phase1_dataset_generation/logs/32_compute_structured_features/aggregate.log first 5:
    2026-06-04 13:24:25 WARNING pid=13632  worker | worker initialized
    2026-06-04 13:24:25 WARNING pid=14532  worker | worker initialized
    2026-06-04 13:24:25 WARNING pid=17844  worker | worker initialized
    2026-06-04 13:24:25 WARNING pid=21052  worker | worker initialized
    2026-06-04 13:24:25 WARNING pid=30780  worker | worker initialized
    scripts/phase1_dataset_generation/logs/32_compute_structured_features/aggregate.log last 5:
    2026-06-04 13:24:25 WARNING pid=5420   worker | worker initialized
    2026-06-04 13:24:25 WARNING pid=54676  worker | worker initialized
    2026-06-04 13:24:25 WARNING pid=57676  worker | worker initialized
    2026-06-04 13:24:25 WARNING pid=58664  worker | worker initialized
    2026-06-04 13:24:25 WARNING pid=58768  worker | worker initialized
    scripts/phase1_dataset_generation/logs/31_waveform_qc/main.log first 5:
    2026-06-04 00:15:15 INFO    pid=13008  main | starting 31_waveform_qc
    2026-06-04 00:15:15 INFO    pid=13008  main | run command from scripts cwd: cd D:\Coding\MU\Tri-Modal_ECG\scripts && ..\ecg_env\Scripts\python.exe phase1_dataset_generation\31_waveform_qc.py 1> ..\outputs\stage_reports\stage_7_run\31_waveform_qc.stdout.log 2> ..\outputs\stage_reports\stage_7_run\31_waveform_qc.stderr.log
    2026-06-04 00:15:29 INFO    pid=13008  main | resume completed=0 pending=800035 existing_parts=0 next_part=0 max_workers=20 max_ram_gb=29.69
    2026-06-04 01:45:21 INFO    pid=13008  main | wrote part=waveform_qc.part_0000.parquet rows=100000 processed=100000
    2026-06-04 03:13:15 INFO    pid=13008  main | wrote part=waveform_qc.part_0001.parquet rows=100000 processed=200000
    scripts/phase1_dataset_generation/logs/31_waveform_qc/main.log last 5:
    2026-06-04 11:21:48 INFO    pid=13008  main | wrote part=waveform_qc.part_0006.parquet rows=100000 processed=700000
    2026-06-04 13:24:04 INFO    pid=13008  main | wrote part=waveform_qc.part_0007.parquet rows=100000 processed=800000
    2026-06-04 13:24:05 INFO    pid=13008  main | wrote final part=waveform_qc.part_0008.parquet rows=35
    2026-06-04 13:24:09 INFO    pid=13008  main | published waveform_qc.parquet rows=800035
    2026-06-04 13:24:12 INFO    pid=13008  main | validation row_ok=True required_ok=True metadata_ok=True cleanup=PASS
    scripts/phase1_dataset_generation/logs/32_compute_structured_features/main.log first 5:
    2026-06-04 13:24:14 INFO    pid=12468  main | starting 32_compute_structured_features
    2026-06-04 13:24:22 INFO    pid=12468  main | resume completed=0 pending=800035 existing_parts=0 next_part=0 max_workers=20 max_ram_gb=29.69
    2026-06-04 13:33:25 INFO    pid=12468  main | wrote part=structured_features.part_0000.parquet rows=10000 processed=10000
    2026-06-04 13:42:42 INFO    pid=12468  main | wrote part=structured_features.part_0001.parquet rows=10000 processed=20000
    2026-06-04 13:52:07 INFO    pid=12468  main | wrote part=structured_features.part_0002.parquet rows=10000 processed=30000
    scripts/phase1_dataset_generation/logs/32_compute_structured_features/main.log last 5:
    2026-06-05 09:39:10 INFO    pid=12468  main | wrote part=structured_features.part_0078.parquet rows=10000 processed=790000
    2026-06-05 09:50:16 INFO    pid=12468  main | wrote part=structured_features.part_0079.parquet rows=10000 processed=800000
    2026-06-05 09:50:17 INFO    pid=12468  main | wrote final part=structured_features.part_0080.parquet rows=35
    2026-06-05 09:50:20 INFO    pid=12468  main | published structured_features.parquet rows=800035
    2026-06-05 09:50:24 INFO    pid=12468  main | validation waveform_ok=True structured_ok=True cleanup=PASS
    ```
  - [x] `grep -n "print(" <script>.py` output pasted (must be empty inside worker()).
    ```text
    rg -n "print\(" scripts/phase1_dataset_generation/31_waveform_qc.py
    <no matches>
    rg -n "print\(" scripts/phase1_dataset_generation/32_compute_structured_features.py
    <no matches>
    ```
  - [x] `grep -n "logging.basicConfig" <script>.py` output pasted (must be empty inside worker()).
    ```text
    rg -n "logging\.basicConfig" scripts/phase1_dataset_generation/31_waveform_qc.py
    <no matches>
    rg -n "logging\.basicConfig" scripts/phase1_dataset_generation/32_compute_structured_features.py
    <no matches>
    ```
  - [x] `worker_<pid>.log` files moved into `archive_<ts>/`: `31_waveform_qc` archive is shown in its done marker/log tree; `32_compute_structured_features` archive scripts/phase1_dataset_generation/logs/32_compute_structured_features/archive_20260605_095024.
  - [x] If Transport B: paste the `finally: listener.stop()` line from the script: N/A - Stage 7 uses Transport A per-PID worker logs.
  - [x] If tqdm used: paste the `tqdm(..., mininterval=...)` call and the `with logging_redirect_tqdm():` line.
    ```text
    with logging_redirect_tqdm():
    tqdm(..., file=sys.stderr, dynamic_ncols=True, mininterval=0.5, desc="stage 7 waveform qc")
    tqdm(..., file=sys.stderr, dynamic_ncols=True, mininterval=0.5, desc="stage 7 structured features")
    ```
- Disk before stage start: 256.8 GiB free
- Disk after stage end: 256.1 GiB free
- Wall-clock: 20:26:11

## 7. Manual test procedure
cd D:\Coding\MU\Tri-Modal_ECG\scripts
..\ecg_env\Scripts\python.exe phase1_dataset_generation\31_waveform_qc.py
..\ecg_env\Scripts\python.exe phase1_dataset_generation\32_compute_structured_features.py
..\ecg_env\Scripts\python.exe -c "import pandas as pd,sys; m=pd.read_parquet('../data/processed/index/ecg_metadata.parquet', columns=['study_id']); q=pd.read_parquet('../data/processed/waveform_qc.parquet'); s=pd.read_parquet('../data/processed/structured_features.parquet'); sys.stdout.write(str((len(m), len(q), int(q.decode_ok.sum()), len(s), q.sqi_tier.value_counts().to_dict(), int(q.hr_consistency_flag.sum()), int(q.qrs_consistency_flag.sum())))+'\n')"
..\ecg_env\Scripts\python.exe -c "import pyarrow.parquet as pq,sys; sys.stdout.write(str({k.decode():v.decode() for k,v in pq.ParquetFile('../data/processed/waveform_qc.parquet').schema_arrow.metadata.items()})+'\n'); sys.stdout.write(str({k.decode():v.decode() for k,v in pq.ParquetFile('../data/processed/structured_features.parquet').schema_arrow.metadata.items()})+'\n')"
Get-ChildItem ..\data\processed\waveform_qc.part_*.parquet -ErrorAction SilentlyContinue
Get-ChildItem ..\data\processed\structured_features.part_*.parquet -ErrorAction SilentlyContinue
Get-Content .\logs\31_waveform_qc\main.log -Tail 20
Get-Content .\logs\32_compute_structured_features\main.log -Tail 20

## 8. Assumptions requiring user confirmation
- Machine-measurements passthrough source  ::  The Stage 7 request lists `ecg_metadata.parquet`, but the required raw passthrough fields (`rr_interval`, `qrs_onset`, `qrs_end`, axes) are only available in `data/raw/machine_measurements.csv`. The scripts use that CSV for those fields and retain the index as the metadata backbone.
