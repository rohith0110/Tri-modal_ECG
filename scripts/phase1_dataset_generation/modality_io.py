#!/usr/bin/env python3
"""Helpers for reading payloads through the Stage 10 modality manifest."""

from __future__ import annotations

import hashlib
import tarfile
from functools import lru_cache
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

try:
    from _stage1_common import DATA_PROCESSED
except ModuleNotFoundError:  # Support package-style imports from the scripts directory.
    from ._stage1_common import DATA_PROCESSED


MANIFEST_PATH = DATA_PROCESSED / "modality_manifest.parquet"

KIND_ALIASES = {
    "clean_lead2": ("image_clean", "lead2"),
    "clean_12lead": ("image_clean", "12lead"),
    "image_clean_lead2": ("image_clean", "lead2"),
    "image_clean_12lead": ("image_clean", "12lead"),
    "scanlike_lead2": ("image_scanlike", "lead2"),
    "scanlike_12lead": ("image_scanlike", "12lead"),
    "image_scanlike_lead2": ("image_scanlike", "lead2"),
    "image_scanlike_12lead": ("image_scanlike", "12lead"),
}


@lru_cache(maxsize=1)
def _manifest() -> pd.DataFrame:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"missing modality manifest: {MANIFEST_PATH}")
    return pd.read_parquet(MANIFEST_PATH)


def _normalize(kind: str, layout: str | None) -> tuple[str, str | None]:
    if kind in KIND_ALIASES:
        alias_kind, alias_layout = KIND_ALIASES[kind]
        return alias_kind, layout or alias_layout
    return kind, layout


def _selected_row(study_id: int, kind: str, **kwargs: Any) -> pd.Series:
    layout = kwargs.get("layout")
    kind, layout = _normalize(kind, layout)
    df = _manifest()
    mask = df["study_id"].eq(int(study_id)) & df["modality_kind"].eq(kind)
    if layout is not None:
        mask &= df["layout"].fillna("").eq(str(layout))
    if kind == "signal_corrupted":
        if "corruption_type" in kwargs:
            mask &= df["corruption_type"].fillna("").eq(str(kwargs["corruption_type"]))
        if "snr_db" in kwargs:
            mask &= df["snr_db"].astype("Int64").eq(int(kwargs["snr_db"]))
        if "corruption_row" in kwargs:
            mask &= df["corruption_row"].astype("Int64").eq(int(kwargs["corruption_row"]))
    rows = df.loc[mask]
    if len(rows) != 1:
        raise KeyError(f"expected exactly one manifest row for study_id={study_id} kind={kind} kwargs={kwargs}, found {len(rows)}")
    return rows.iloc[0]


def _read_hdf5(row: pd.Series) -> np.ndarray:
    path = DATA_PROCESSED / str(row["container_path"])
    container_row = int(row["container_row"])
    with h5py.File(path, "r") as h5:
        return np.asarray(h5["signal"][container_row], dtype=np.float32)


def _read_tar(row: pd.Series) -> bytes:
    path = DATA_PROCESSED / str(row["container_path"])
    study_id = int(row["study_id"])
    ext = ".jpg" if str(row["modality_kind"]) == "image_scanlike" else ".png"
    expected_sha = str(row["sha256"])
    offset = int(row["container_offset"])
    length = int(row["container_length"])
    with path.open("rb") as f:
        f.seek(offset + 512)
        blob = f.read(length)
    if hashlib.sha256(blob).hexdigest() == expected_sha:
        return blob
    with tarfile.open(path, "r") as tf:
        member = tf.getmember(f"{study_id}{ext}")
        handle = tf.extractfile(member)
        if handle is None:
            raise RuntimeError(f"could not read {study_id}{ext} from {path}")
        blob = handle.read()
    if hashlib.sha256(blob).hexdigest() != expected_sha:
        raise RuntimeError(f"sha256 mismatch for study_id={study_id} path={path}")
    return blob


def _read_corrupted(row: pd.Series) -> np.ndarray:
    path = DATA_PROCESSED / str(row["container_path"])
    target = int(row["container_row"])
    pf = pq.ParquetFile(path)
    start = 0
    for rg_idx in range(pf.metadata.num_row_groups):
        rows = pf.metadata.row_group(rg_idx).num_rows
        if start <= target < start + rows:
            table = pf.read_row_group(rg_idx, columns=["signal"])
            local = target - start
            signal_array = table.column("signal").combine_chunks()
            values = signal_array.values.to_numpy(zero_copy_only=False).reshape(table.num_rows, 5000)
            return np.asarray(values[local], dtype=np.float32)
        start += rows
    raise IndexError(f"container_row {target} out of range for {path}")


def read_modality(study_id: int, kind: str, **kwargs: Any) -> bytes | np.ndarray:
    """Read a modality payload from the canonical manifest."""
    row = _selected_row(study_id, kind, **kwargs)
    path = str(row["container_path"])
    if path.endswith(".h5"):
        return _read_hdf5(row)
    if path.endswith(".tar"):
        return _read_tar(row)
    if path.endswith(".parquet") and str(row["modality_kind"]) == "signal_corrupted":
        return _read_corrupted(row)
    raise ValueError(f"unsupported manifest container for row: {path}")
