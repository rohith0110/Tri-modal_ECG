"""Stage P2.1 script 00 -- per-study Lead-II fiducials (A4 ground truth, B3 input).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/00_extract_fiducials.py [--dev]

Why this exists (spec §4.A.4.3 CORRECTION, Round 5.2). The spec originally
claimed Phase 1 cached per-study R-peak arrays in
``structured_features.parquet``. It did not: that file has exactly one list
column, ``sqi_per_lead``. No sample-position array exists anywhere in Phase 1's
outputs, so A4 has no ground truth and B3 has no per-bin evidence until this
script runs.

**The detector path is copied verbatim from the CORRECTED Phase 1 regen**
(``phase1_dataset_generation/32_compute_structured_features.py::_extract_wave_features``,
lines 364-390, mirrored in ``31_waveform_qc.py:272-283``). A fresh
implementation would reintroduce the Pan-Tompkins bug that regen fixed -- it had
produced ~74 K false labels. Three details carry over exactly (progress-doc
trap 2):

1. ``method="neurokit"``, **not** ``"pantompkins"``. The corrected detector is
   NeuroKit's default.
2. The input is lead II of the **preprocessed** 12-lead signal, fed to
   ``ecg_peaks`` **without** a preceding ``ecg_clean``. (``_sqi_one`` cleans
   first; the fiducial path does not. Do not "fix" this.) Verified at Stage
   P2.1: ``read_modality(sid, "preprocessed_lead2")`` is bit-identical to
   ``read_modality(sid, "preprocessed_12lead")[1]`` for every study sampled, so
   reading the 11.85 GB Lead-II container instead of the 141.8 GB 12-lead shards
   takes the same code path on the same numbers.
3. ``ecg_delineate`` runs on the same array as ``ecg_peaks``, with
   ``check=False``.

Cohort: the **full clean cohort** (749,112 studies), not just A4's
L3 x {high,medium} primary. A4's own sensitivity cohort is "full clean cohort
regardless of link_tier" (§4.A.4.8) and B3's cohort is the full clean cohort
(§4.B.3.2), so one pass serves all three. Builders subset it.

Schema (``data/processed/fiducials_lead2.parquet``, one row per study)::

    study_id          int64
    n_peaks           int32
    r_peaks_lead2     list<int32>    # sample positions, 0-indexed into 5000
    qrs_onsets_lead2  list<int32>    # one per R-peak; -1 where not delineated
    qrs_offsets_lead2 list<int32>    # one per R-peak; -1 where not delineated
    sqi_per_bin       list<float32>  # 10 values, one per 1-second bin
    fallback_used     bool           # R-peak detection failed or found < 2 peaks
    delineate_ok      bool
    notes             string

The four columns §4.A.4.3 specifies are the first four. ``sqi_per_bin`` is an
additive extension: B3's ``NOISY_SEGMENT`` query needs per-second
``ecg_quality`` (§4.B.3.3) and computing it here reuses the signal read instead
of paying a second full pass over 11.85 GB. It is computed exactly the way
Phase 1's ``_sqi_one`` computes ``sqi_aggregate`` -- clean, re-detect, then
``ecg_quality(method="averageQRS")`` -- so a per-bin value sits on the same
scale as ``waveform_qc.sqi_aggregate``, just not averaged away.

Storage is **sparse** (peak positions), not dense 5000-sample masks: dense int8
masks would cost 2.3 GB for the A4 cohort alone. The dataloader expands to a
dense mask at batch time. Same information, no science change.

Resume: parts land in ``data/processed/_p2_parts/fiducials/``; a killed run
restarts from the last flush. Expect ~5-9 h at full scale on 15 workers.
"""

from __future__ import annotations

import argparse
import functools
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402
from _dataset_lib.modality import read_modality  # noqa: E402

STAGE = "P2.1"
SCRIPT = "00_extract_fiducials"
PART_NAME = "fiducials"
OUT_PATH = bc.DATA_PROCESSED / "fiducials_lead2.parquet"

FS = 500                 # Hz, as Phase 1
N_SAMPLES = 5000         # 10 s strip
N_BINS = 10              # B3's 1-second bins (§4.B.3.3)
BIN_SAMPLES = N_SAMPLES // N_BINS
NOT_DELINEATED = -1      # sentinel inside qrs_onsets/offsets

SCHEMA = pa.schema([
    ("study_id", pa.int64()),
    ("n_peaks", pa.int32()),
    ("r_peaks_lead2", pa.list_(pa.int32())),
    ("qrs_onsets_lead2", pa.list_(pa.int32())),
    ("qrs_offsets_lead2", pa.list_(pa.int32())),
    ("sqi_per_bin", pa.list_(pa.float32())),
    ("fallback_used", pa.bool_()),
    ("delineate_ok", pa.bool_()),
    ("notes", pa.string()),
])

_NK: Any = None


def _get_nk() -> Any:
    """Import NeuroKit2 lazily, once per worker process (Phase 1 convention)."""
    global _NK
    if _NK is None:
        import neurokit2 as nk

        _NK = nk
    return _NK


def _aligned(values: Any, n: int) -> np.ndarray:
    """NeuroKit delineation output -> an int32 array of length ``n``.

    ``ecg_delineate`` returns one entry per R-peak with ``NaN`` where the
    boundary was not found. Phase 1's ``_indices`` dropped the NaNs, which is
    correct for a median but destroys the peak alignment A4 needs, so the NaNs
    become ``NOT_DELINEATED`` here instead of vanishing.
    """
    arr = np.asarray(values if values is not None else [], dtype="float64")
    out = np.full(n, NOT_DELINEATED, dtype="int32")
    take = min(n, arr.size)
    if take:
        head = arr[:take]
        good = np.isfinite(head) & (head >= 0) & (head < N_SAMPLES)
        out[:take] = np.where(good, np.rint(np.nan_to_num(head, nan=-1.0)), NOT_DELINEATED)
    return out


def _sqi_per_bin(lead2: np.ndarray, nk: Any) -> tuple[list[float], str]:
    """Per-1-second ``ecg_quality``, on the same code path as Phase 1's SQI.

    Phase 1's ``_sqi_one`` cleans, re-detects peaks on the cleaned signal, then
    averages ``ecg_quality(method="averageQRS")``. Everything here is identical
    except that the mean is taken per bin instead of over the whole strip.
    """
    try:
        cleaned = nk.ecg_clean(np.asarray(lead2, dtype="float32"), sampling_rate=FS,
                               method="neurokit")
        _, info = nk.ecg_peaks(cleaned, sampling_rate=FS, method="neurokit")
        quality = nk.ecg_quality(cleaned, rpeaks=info.get("ECG_R_Peaks"),
                                 sampling_rate=FS, method="averageQRS")
        q = np.asarray(quality, dtype="float64")
    except Exception as exc:  # noqa: BLE001 - a bad strip must not kill the pool
        return [0.0] * N_BINS, f"sqi:{type(exc).__name__}"

    if q.size < N_SAMPLES:
        q = np.pad(q, (0, N_SAMPLES - q.size), constant_values=np.nan)
    q = q[:N_SAMPLES].reshape(N_BINS, BIN_SAMPLES)
    with np.errstate(invalid="ignore"):
        means = np.nanmean(np.where(np.isfinite(q), q, np.nan), axis=1)
    return [float(v) if np.isfinite(v) else 0.0 for v in means], ""


def worker(study_id: int) -> dict[str, Any]:
    nk = _get_nk()
    notes: list[str] = []
    row: dict[str, Any] = {
        "study_id": int(study_id),
        "n_peaks": 0,
        "r_peaks_lead2": [],
        "qrs_onsets_lead2": [],
        "qrs_offsets_lead2": [],
        "sqi_per_bin": [0.0] * N_BINS,
        "fallback_used": True,
        "delineate_ok": False,
        "notes": "",
    }
    try:
        lead2 = np.asarray(read_modality(int(study_id), "preprocessed_lead2"), dtype="float32")
    except Exception as exc:  # noqa: BLE001
        row["notes"] = f"read:{type(exc).__name__}"
        return row

    # --- the corrected Phase 1 detector path, verbatim (trap 2) --------------
    rpeaks = np.asarray([], dtype="int64")
    try:
        _, peak_info = nk.ecg_peaks(lead2, sampling_rate=FS, method="neurokit")
        found = peak_info.get("ECG_R_Peaks")
        raw = np.asarray([] if found is None else found, dtype="float64")
        raw = raw[np.isfinite(raw)]
        rpeaks = raw.astype("int64")
        rpeaks = rpeaks[(rpeaks >= 0) & (rpeaks < N_SAMPLES)]
    except Exception as exc:  # noqa: BLE001
        notes.append(f"peaks:{type(exc).__name__}")

    n = int(rpeaks.size)
    row["n_peaks"] = n
    row["r_peaks_lead2"] = [int(x) for x in rpeaks]
    row["fallback_used"] = n < 2

    if n:
        try:
            _, waves = nk.ecg_delineate(lead2, rpeaks=rpeaks, sampling_rate=FS,
                                        method="dwt", show=False, check=False)
            onsets = _aligned(waves.get("ECG_R_Onsets"), n)
            offsets = _aligned(waves.get("ECG_R_Offsets"), n)
            # A boundary pair is only usable when onset < offset; otherwise the
            # beat contributes no QRS span rather than a negative-width one.
            bad = (onsets == NOT_DELINEATED) | (offsets == NOT_DELINEATED) | (onsets >= offsets)
            onsets = np.where(bad, NOT_DELINEATED, onsets)
            offsets = np.where(bad, NOT_DELINEATED, offsets)
            row["qrs_onsets_lead2"] = [int(x) for x in onsets]
            row["qrs_offsets_lead2"] = [int(x) for x in offsets]
            row["delineate_ok"] = bool((~bad).any())
        except Exception as exc:  # noqa: BLE001
            notes.append(f"delineate:{type(exc).__name__}")
            row["qrs_onsets_lead2"] = [NOT_DELINEATED] * n
            row["qrs_offsets_lead2"] = [NOT_DELINEATED] * n

    sqi, sqi_note = _sqi_per_bin(lead2, nk)
    row["sqi_per_bin"] = sqi
    if sqi_note:
        notes.append(sqi_note)
    row["notes"] = ";".join(notes)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    bc.add_std_args(parser)
    parser.add_argument("--workers", type=int, default=bc.MAX_WORKERS)
    args = parser.parse_args()

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    part_name = PART_NAME + ("_dev" if args.dev else "")
    out_path = OUT_PATH.with_name("fiducials_lead2_dev.parquet") if args.dev else OUT_PATH
    state = bc.StageState(STAGE, SCRIPT + ("_dev" if args.dev else ""))

    if state.done and not args.force:
        log.info("already complete (%s rows) -- pass --force to rebuild",
                 state.data.get("n_rows"))
        return 0
    if args.force:
        for part in bc.part_dir(part_name).glob("part_*.parquet"):
            part.unlink()
        state.reset()

    bc.preflight([bc.DATA_PROCESSED / "signals" / "lead2_preprocessed.h5",
                  bc.DATA_PROCESSED / "modality_manifest.parquet"], need_free_gb=5.0)

    cohort = bc.load_clean_cohort(dev=args.dev)
    study_ids = [int(x) for x in cohort.study_id]
    if args.limit:
        study_ids = study_ids[: args.limit]
    log.info("cohort: %d studies (dev=%s)", len(study_ids), args.dev)

    started = time.time()
    processed = bc.run_chunked(
        name=part_name,
        units=study_ids,
        worker=worker,
        schema=SCHEMA,
        state=state,
        initializer=functools.partial(bc.worker_log_init, SCRIPT, STAGE),
        chunk_size=10_000 if not args.dev else 1_000,
        desc="P2.1 fiducials",
        workers=args.workers,
    )
    log.info("processed %d studies this run in %.1f min", processed, (time.time() - started) / 60)

    n = bc.publish_parts(part_name, out_path, SCHEMA,
                         metadata={"spec": "PHASE2_SOURCE_OF_TRUTH.md §4.A.4.3",
                                   "detector": "neurokit2 ecg_peaks(method=neurokit) + ecg_delineate(method=dwt)",
                                   "input_modality": "preprocessed_lead2"})
    log.info("published %s rows=%d", out_path, n)

    # --- validation (§9.2) ---------------------------------------------------
    import pandas as pd

    got = pd.read_parquet(out_path, columns=["study_id", "n_peaks", "fallback_used",
                                             "delineate_ok", "sqi_per_bin", "notes"])
    if got.study_id.duplicated().any():
        raise RuntimeError("duplicate study_id in the published fiducials")
    if len(got) != len(study_ids):
        raise RuntimeError(f"published {len(got)} rows for a {len(study_ids)}-study cohort")

    hr_equiv = got.n_peaks * 6.0     # peaks per 10 s -> bpm
    stats = {
        "n_rows": int(len(got)),
        "n_fallback_used": int(got.fallback_used.sum()),
        "pct_fallback_used": round(100 * float(got.fallback_used.mean()), 3),
        "n_delineate_ok": int(got.delineate_ok.sum()),
        "pct_delineate_ok": round(100 * float(got.delineate_ok.mean()), 3),
        "n_peaks_mean": round(float(got.n_peaks.mean()), 2),
        "n_peaks_median": int(got.n_peaks.median()),
        "implied_hr_bpm_mean": round(float(hr_equiv.mean()), 1),
        "sqi_per_bin_mean": round(float(np.mean([np.mean(v) for v in got.sqi_per_bin.head(20000)])), 4),
        "n_with_notes": int((got.notes.fillna("") != "").sum()),
        "elapsed_seconds": round(time.time() - started, 1),
    }
    log.info("validation: %s", stats)

    # Sanity gate: an implied mean HR far from the machine's would mean the
    # detector path drifted from Phase 1's.
    machine = bc.machine_measurements(dev=args.dev).set_index("study_id").hr_bpm
    joined = got.set_index("study_id").join(machine).dropna(subset=["hr_bpm"])
    joined = joined[~joined.fallback_used]
    corr = float(np.corrcoef(joined.n_peaks * 6.0, joined.hr_bpm)[0, 1]) if len(joined) > 10 else float("nan")
    stats["corr_peakrate_vs_machine_hr"] = round(corr, 4)
    log.info("R-peak rate vs machine HR correlation: %.4f (n=%d)", corr, len(joined))
    if np.isfinite(corr) and corr < 0.8:
        raise RuntimeError(
            f"R-peak rate correlates with the machine HR at only {corr:.3f}; the detector "
            "path does not reproduce Phase 1's fiducials -- do not use this file"
        )

    state.finish(**stats)
    log.info("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
