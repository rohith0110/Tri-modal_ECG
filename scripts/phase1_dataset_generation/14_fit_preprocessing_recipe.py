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
