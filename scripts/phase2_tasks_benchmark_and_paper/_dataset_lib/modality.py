"""Canonical Phase 2 modality loader (spec §2.1).

Every dataloader, every label builder and every evaluation script in Phase 2
resolves modality bytes through :func:`read_modality`. Nothing else may
``open()`` an HDF5 file or a tar archive directly -- an inheritance violation
is CRITICAL (spec §2, §11).

    from _dataset_lib.modality import read_modality
    sig = read_modality(40000017, "preprocessed_lead2")     # -> (5000,) float32
    png = read_modality(40000017, "image_clean_lead2")      # -> PNG bytes
    bad = read_modality(40000035, "signal_corrupted",
                        corruption_type="gaussian", snr_db=10)

Caching policy (spec §2.1): index-only structures (manifest rows, tar offsets,
open file handles) may be cached; **raw bytes may not** -- that is the on-disk
container's job. Handle caches are keyed by PID so a forked DataLoader worker
never inherits a parent's HDF5 handle, which is not safe to share.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import numpy as np

# --- repo layout -------------------------------------------------------------
# .../scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/modality.py
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
MANIFEST_PATH = DATA_PROCESSED / "modality_manifest.parquet"

# --- the locked modality-kind enum (spec §2.6) -------------------------------
# Adding a kind here is a CRITICAL spec violation.
SIGNAL_KINDS = ("raw_lead2", "raw_12lead", "preprocessed_lead2", "preprocessed_12lead")
IMAGE_KINDS = (
    "image_clean_lead2",
    "image_clean_12lead",
    "image_scanlike_lead2",
    "image_scanlike_12lead",
)
CORRUPTED_KIND = "signal_corrupted"
MODALITY_KINDS = SIGNAL_KINDS + IMAGE_KINDS + (CORRUPTED_KIND,)

# The Phase 2 enum splits image kinds by layout; the Phase 1 manifest stores
# them as (modality_kind, layout) pairs. This is the only place the two
# spellings meet.
_IMAGE_KIND_TO_MANIFEST = {
    "image_clean_lead2": ("image_clean", "lead2"),
    "image_clean_12lead": ("image_clean", "12lead"),
    "image_scanlike_lead2": ("image_scanlike", "lead2"),
    "image_scanlike_12lead": ("image_scanlike", "12lead"),
}

# Tar members are stored as a 512-byte header block followed by the file data.
# `container_offset` in the manifest points at the HEADER, so member bytes begin
# 512 bytes later. Verified against tarfile.TarInfo.offset_data at Stage P2.0.
TAR_HEADER_BYTES = 512

_N_SAMPLES = 5000
_N_LEADS = 12

# Phase 1 stores 12-lead signals as (n_studies, 5000, 12) -- sample-major. The
# §5.2 encoder contract is (B, n_leads, 5000) -- channel-major. read_modality
# returns the CHANNEL-MAJOR view, (12, 5000), so a caller can never silently
# feed a transposed tensor to Conv1d. The transpose is a view plus one
# ascontiguousarray; it does not re-read the container.
LEAD_ORDER_12 = ("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6")
LEAD_II_INDEX = LEAD_ORDER_12.index("II")  # == 1

_index_lock = threading.Lock()
_INDEX: dict[str, dict[int, tuple]] = {}
_HANDLES: dict[tuple[int, str], Any] = {}
_CORRUPT_READER: dict[int, Any] = {}


class ModalityError(KeyError):
    """Raised when a (study_id, kind) pair has no manifest row."""


# -----------------------------------------------------------------------------
# index
# -----------------------------------------------------------------------------
def _build_index(kind: str) -> dict[int, tuple]:
    """Load the manifest rows for one kind into a study_id -> row lookup.

    Index only -- no bytes. Roughly 470 MB is read from the manifest once per
    process and discarded; what is retained is one small dict per kind actually
    used.
    """
    import pandas as pd

    cols = [
        "study_id",
        "modality_kind",
        "layout",
        "container_path",
        "container_row",
        "container_offset",
        "container_length",
    ]
    if kind == CORRUPTED_KIND:
        cols += ["corruption_type", "snr_db"]

    manifest = pd.read_parquet(MANIFEST_PATH, columns=cols)

    if kind in _IMAGE_KIND_TO_MANIFEST:
        manifest_kind, layout = _IMAGE_KIND_TO_MANIFEST[kind]
        rows = manifest[
            (manifest["modality_kind"] == manifest_kind) & (manifest["layout"] == layout)
        ]
    else:
        rows = manifest[manifest["modality_kind"] == kind]

    if rows.empty:
        raise ModalityError(f"manifest has no rows for modality kind {kind!r}")

    if kind == CORRUPTED_KIND:
        # One study has 40 corrupted variants, so the key is the triple.
        return {
            (int(s), str(c), int(n)): (str(p), int(r))
            for s, c, n, p, r in zip(
                rows["study_id"],
                rows["corruption_type"],
                rows["snr_db"],
                rows["container_path"],
                rows["container_row"],
            )
        }

    if kind in SIGNAL_KINDS:
        return {
            int(s): (str(p), int(r))
            for s, p, r in zip(rows["study_id"], rows["container_path"], rows["container_row"])
        }

    return {
        int(s): (str(p), int(o), int(l))
        for s, p, o, l in zip(
            rows["study_id"],
            rows["container_path"],
            rows["container_offset"],
            rows["container_length"],
        )
    }


def _index_for(kind: str) -> dict:
    idx = _INDEX.get(kind)
    if idx is None:
        with _index_lock:
            idx = _INDEX.get(kind)
            if idx is None:
                idx = _build_index(kind)
                _INDEX[kind] = idx
    return idx


# -----------------------------------------------------------------------------
# handles -- keyed by PID so forked workers never share one
# -----------------------------------------------------------------------------
def _h5(path: str):
    import h5py

    key = (os.getpid(), path)
    handle = _HANDLES.get(key)
    if handle is None:
        # swmr=False: we are a plain reader, not a SWMR writer (spec §8.5).
        handle = h5py.File(str(DATA_PROCESSED / path), "r", swmr=False)
        _HANDLES[key] = handle
    return handle


def _tar(path: str):
    key = (os.getpid(), path)
    handle = _HANDLES.get(key)
    if handle is None:
        handle = open(DATA_PROCESSED / path, "rb")
        _HANDLES[key] = handle
    return handle


def _corrupt_reader(path: str):
    """Row-group-cached reader over signals_corrupted.parquet.

    The file is ~0.92 GB, too large to hold whole on the 6 GB laptop alongside a
    model. We keep the row-group boundaries (index only) and materialise one
    row group at a time; sequential access over an anchor's 40 variants hits
    the same group repeatedly.
    """
    import pyarrow.parquet as pq

    key = os.getpid()
    state = _CORRUPT_READER.get(key)
    if state is None or state["path"] != path:
        pf = pq.ParquetFile(DATA_PROCESSED / path)
        bounds = []
        start = 0
        for i in range(pf.num_row_groups):
            n = pf.metadata.row_group(i).num_rows
            bounds.append((start, start + n))
            start += n
        state = {"path": path, "pf": pf, "bounds": bounds, "cached_group": None, "cached": None}
        _CORRUPT_READER[key] = state
    return state


def close_handles() -> None:
    """Close every cached handle for this process. Call at worker teardown."""
    pid = os.getpid()
    for key in [k for k in _HANDLES if k[0] == pid]:
        try:
            _HANDLES.pop(key).close()
        except Exception:  # pragma: no cover - teardown must not raise
            pass
    _CORRUPT_READER.pop(pid, None)


# -----------------------------------------------------------------------------
# the public entry point
# -----------------------------------------------------------------------------
def read_modality(
    study_id: int,
    kind: str,
    *,
    corruption_type: str | None = None,
    snr_db: int | None = None,
) -> bytes | np.ndarray:
    """Resolve a study + modality to bytes (tar) or an array (HDF5 / parquet).

    Resolution always goes through ``data/processed/modality_manifest.parquet``.

    Args:
        study_id: MIMIC-IV-ECG study identifier.
        kind: one of :data:`MODALITY_KINDS` --
            ``raw_lead2``, ``raw_12lead``, ``preprocessed_lead2``,
            ``preprocessed_12lead``, ``image_clean_lead2``,
            ``image_clean_12lead``, ``image_scanlike_lead2``,
            ``image_scanlike_12lead``, ``signal_corrupted``.
        corruption_type: required when ``kind == "signal_corrupted"``; one of the
            8 families in ``config/corruption_recipes_LOCKED.yaml``.
        snr_db: required when ``kind == "signal_corrupted"``; one of 30/20/10/5/0.

    Returns:
        ``(5000,) float32`` for Lead-II signals and corrupted signals,
        ``(12, 5000) float32`` for 12-lead signals -- CHANNEL-MAJOR, in
        :data:`LEAD_ORDER_12`, transposed from the container's sample-major
        layout so it drops straight into a Conv1d -- and raw image ``bytes``
        (PNG/JPEG, exactly as stored) for the four image kinds.

    Raises:
        ValueError: unknown ``kind``, or corruption arguments used incorrectly.
        ModalityError: the study has no manifest row for that kind.
    """
    if kind not in MODALITY_KINDS:
        raise ValueError(
            f"unknown modality kind {kind!r}. The enum is locked (spec §2.6): "
            f"{', '.join(MODALITY_KINDS)}"
        )

    if kind == CORRUPTED_KIND:
        if corruption_type is None or snr_db is None:
            raise ValueError(
                "signal_corrupted requires corruption_type and snr_db "
                "(a study has 8 x 5 = 40 corrupted variants)"
            )
        return _read_corrupted(int(study_id), str(corruption_type), int(snr_db))

    if corruption_type is not None or snr_db is not None:
        raise ValueError(f"corruption_type / snr_db are only valid for {CORRUPTED_KIND!r}")

    if kind in SIGNAL_KINDS:
        return _read_signal(int(study_id), kind)
    return _read_image(int(study_id), kind)


def _read_signal(study_id: int, kind: str) -> np.ndarray:
    row = _index_for(kind).get(study_id)
    if row is None:
        raise ModalityError(f"no {kind} row for study_id {study_id}")
    path, container_row = row
    raw = np.asarray(_h5(path)["signal"][container_row], dtype=np.float32)
    if raw.ndim == 2:
        # (5000, 12) as stored -> (12, 5000) as the encoder expects.
        raw = np.ascontiguousarray(raw.T)
    return raw


def _read_image(study_id: int, kind: str) -> bytes:
    row = _index_for(kind).get(study_id)
    if row is None:
        raise ModalityError(f"no {kind} row for study_id {study_id}")
    path, offset, length = row
    handle = _tar(path)
    handle.seek(offset + TAR_HEADER_BYTES)
    data = handle.read(length)
    if len(data) != length:
        raise ModalityError(
            f"short read for {kind} study_id {study_id}: got {len(data)} of {length} bytes"
        )
    return data


def _read_corrupted(study_id: int, corruption_type: str, snr_db: int) -> np.ndarray:
    row = _index_for(CORRUPTED_KIND).get((study_id, corruption_type, snr_db))
    if row is None:
        raise ModalityError(
            f"no signal_corrupted row for study_id {study_id}, "
            f"corruption_type={corruption_type!r}, snr_db={snr_db}"
        )
    path, container_row = row
    state = _corrupt_reader(path)

    group = next(
        (i for i, (lo, hi) in enumerate(state["bounds"]) if lo <= container_row < hi), None
    )
    if group is None:
        raise ModalityError(f"row {container_row} is out of range in {path}")

    if state["cached_group"] != group:
        state["cached"] = state["pf"].read_row_group(group, columns=["signal"])
        state["cached_group"] = group

    local = container_row - state["bounds"][group][0]
    return np.asarray(state["cached"]["signal"][local].as_py(), dtype=np.float32)


# -----------------------------------------------------------------------------
# self-check -- the spec §9.1 validation for this module
# -----------------------------------------------------------------------------
def _self_check(n_per_kind: int = 10, seed: int = 2026) -> None:
    """Resolve `n_per_kind` random studies per modality kind and assert shapes.

    This is the runnable form of the P2.0 validation item "read_modality()
    resolves 10 random (study_id, kind) calls per modality kind successfully".
    """
    import random

    rng = random.Random(seed)

    for kind in SIGNAL_KINDS + IMAGE_KINDS:
        keys = list(_index_for(kind).keys())
        assert keys, f"{kind}: empty index"
        for study_id in rng.sample(keys, n_per_kind):
            out = read_modality(study_id, kind)
            if kind in SIGNAL_KINDS:
                expected = (_N_SAMPLES,) if kind.endswith("lead2") else (12, _N_SAMPLES)
                assert isinstance(out, np.ndarray), f"{kind}: expected ndarray"
                assert out.shape == expected, f"{kind} {study_id}: {out.shape} != {expected}"
                assert out.dtype == np.float32, f"{kind} {study_id}: dtype {out.dtype}"
                assert np.isfinite(out).all(), f"{kind} {study_id}: non-finite samples"
            else:
                assert isinstance(out, bytes), f"{kind}: expected bytes"
                assert out[:8] == b"\x89PNG\r\n\x1a\n" or out[:2] == b"\xff\xd8", (
                    f"{kind} {study_id}: not a PNG or JPEG"
                )
        print(f"  {kind:24s} OK  ({n_per_kind} studies, {len(keys):,} indexed)")

    keys = list(_index_for(CORRUPTED_KIND).keys())
    assert keys, "signal_corrupted: empty index"
    for study_id, corruption_type, snr_db in rng.sample(keys, n_per_kind):
        out = read_modality(
            study_id, CORRUPTED_KIND, corruption_type=corruption_type, snr_db=snr_db
        )
        assert isinstance(out, np.ndarray), "signal_corrupted: expected ndarray"
        assert out.shape == (_N_SAMPLES,), f"signal_corrupted {study_id}: {out.shape}"
        assert np.isfinite(out).all(), f"signal_corrupted {study_id}: non-finite samples"
    print(f"  {CORRUPTED_KIND:24s} OK  ({n_per_kind} variants, {len(keys):,} indexed)")

    # A Lead-II raw signal must equal lead II of the same study's 12-lead raw.
    study_id = next(iter(_index_for("raw_lead2")))
    lead2 = read_modality(study_id, "raw_lead2")
    twelve = read_modality(study_id, "raw_12lead")
    assert twelve.shape == (_N_LEADS, _N_SAMPLES), f"raw_12lead shape {twelve.shape}"
    assert np.allclose(twelve[LEAD_II_INDEX], lead2, atol=1e-5), (
        f"raw_lead2 for study {study_id} does not match raw_12lead lead "
        f"{LEAD_II_INDEX} ('II') -- the channel-major transpose or the lead "
        f"order is wrong"
    )
    print(f"  cross-check              OK  (raw_lead2 == raw_12lead['II'], index {LEAD_II_INDEX})")

    close_handles()
    print("read_modality self-check: PASS")


if __name__ == "__main__":
    _self_check()
