# Stage P2.1 — Build Plan A task datasets — report

Spec §9.2. Generated 2026-08-28T17:28:58Z by `_dataset_lib/stage_report.py` from the per-script state files, the artifacts on disk and the run logs — every number below is read back from what the stage produced.

## 1. Files created

- `scripts/phase2_tasks_benchmark_and_paper/00_extract_fiducials.py`  (13.7 KB, sha256 ce68a57db938)
- `scripts/phase2_tasks_benchmark_and_paper/00b_rebuild_lab_cache.py`  (7.7 KB, sha256 07419125880d)
- `scripts/phase2_tasks_benchmark_and_paper/01_build_A1_ecg_diagnosis.py`  (13.6 KB, sha256 729dad0e6da6)
- `scripts/phase2_tasks_benchmark_and_paper/02_build_A2_measurement_blind.py`  (6.9 KB, sha256 a191febd3e5c)
- `scripts/phase2_tasks_benchmark_and_paper/03_build_A3_lab_abnormality.py`  (16.8 KB, sha256 5d8b80974f86)
- `scripts/phase2_tasks_benchmark_and_paper/04_build_A4_event_localization.py`  (9.6 KB, sha256 8110ee59f890)
- `scripts/phase2_tasks_benchmark_and_paper/05_build_A5_cross_modal_verification.py`  (15.6 KB, sha256 4f5f941bc9de)
- `scripts/phase2_tasks_benchmark_and_paper/06_build_A6_risk_stratification.py`  (27.4 KB, sha256 3f98349ad018)
- `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/build_common.py`  (26.6 KB, sha256 9d480ef55b66)
- `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/measurement_task.py`  (3.2 KB, sha256 c924a1931ba7)
- `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/verification_task.py`  (21.3 KB, sha256 e638246ded36)
- `data/processed/fiducials_lead2.parquet`  (79.6 MB, sha256 1418fe7c0335)
- `data/raw/ehr_cache/labevents_key_labs.parquet`  (225.9 MB, sha256 e2fb447076ad)
- `data/processed/tasks/A1_ecg_diagnosis/cohort_manifest.parquet`  (7.1 KB, sha256 9717d39abe1b)
- `data/processed/tasks/A1_ecg_diagnosis/README.md`  (3.4 KB, sha256 00e065a94579)
- `data/processed/tasks/A1_ecg_diagnosis/test.parquet`  (2.7 MB, sha256 84b302c33a80)
- `data/processed/tasks/A1_ecg_diagnosis/train.parquet`  (8.8 MB, sha256 155a9ff4b314)
- `data/processed/tasks/A1_ecg_diagnosis/val.parquet`  (1.4 MB, sha256 aa3b54e488c6)
- `data/processed/tasks/A2_measurement_blind/README.md`  (5.0 KB, sha256 97d9fa466915)
- `data/processed/tasks/A2_measurement_blind/test.parquet`  (2.0 MB, sha256 6dfc412a57c7)
- `data/processed/tasks/A2_measurement_blind/train.parquet`  (6.4 MB, sha256 0c8fbfd862a0)
- `data/processed/tasks/A2_measurement_blind/val.parquet`  (1.0 MB, sha256 339f19bc8ef1)
- `data/processed/tasks/A3_lab_abnormality/README.md`  (5.7 KB, sha256 5faed09a10e0)
- `data/processed/tasks/A3_lab_abnormality/test.parquet`  (9.0 MB, sha256 879cba4db098)
- `data/processed/tasks/A3_lab_abnormality/train.parquet`  (30.0 MB, sha256 35368d816eb6)
- `data/processed/tasks/A3_lab_abnormality/val.parquet`  (4.6 MB, sha256 bae2c29318cc)
- `data/processed/tasks/A4_event_localization/README.md`  (3.9 KB, sha256 2e568bb9c80b)
- `data/processed/tasks/A4_event_localization/test.parquet`  (11.1 MB, sha256 b8424c00bcd8)
- `data/processed/tasks/A4_event_localization/train.parquet`  (38.2 MB, sha256 f83edefde072)
- `data/processed/tasks/A4_event_localization/val.parquet`  (5.7 MB, sha256 c325ddbfda72)
- `data/processed/tasks/A5_cross_modal_verification/masked_attribute_test.parquet`  (4.3 MB, sha256 4218b5734435)
- `data/processed/tasks/A5_cross_modal_verification/masked_attribute_train.parquet`  (14.5 MB, sha256 b5066019e061)
- `data/processed/tasks/A5_cross_modal_verification/masked_attribute_val.parquet`  (2.1 MB, sha256 ab7b2f540768)
- `data/processed/tasks/A5_cross_modal_verification/README.md`  (8.3 KB, sha256 8f5aa22d4001)
- `data/processed/tasks/A5_cross_modal_verification/test.parquet`  (15.0 MB, sha256 db2c55aaac52)
- `data/processed/tasks/A5_cross_modal_verification/train.parquet`  (47.6 MB, sha256 ab836d2c5690)
- `data/processed/tasks/A5_cross_modal_verification/val.parquet`  (5.6 MB, sha256 a4e74fdb5916)
- `data/processed/tasks/A6_risk_stratification/README.md`  (4.7 KB, sha256 8d7d4b7bef5a)
- `data/processed/tasks/A6_risk_stratification/test.parquet`  (4.1 MB, sha256 904a68413fcd)
- `data/processed/tasks/A6_risk_stratification/train.parquet`  (13.7 MB, sha256 c8f3dd6486e9)
- `data/processed/tasks/A6_risk_stratification/val.parquet`  (2.1 MB, sha256 7be0ec980ccd)

## 2. Files modified

- `config/task_definitions.yaml`  ::  QTc bin source pinned to `machine_qtc_ms` with `qtc_bazett_ms` demoted to provenance; B3's `noisy_sqi_threshold` locked from the train split.
- `config/lab_itemid_map_LOCKED.yaml`  ::  `cache_rebuild_required` marked DONE with the measured per-lab result; `reference_tables.events` repointed to the rebuilt sibling file.
- `config/claim_dictionary_LOCKED.yaml`  ::  QRS `normal_to_wide` corrected 23 → 0 with the reasoning and the superseded P2.0 measurement retained.
- `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/schema_validators.py`  ::  the quarantine check now asserts no quarantined filename has returned, instead of asserting the Phase 2 script directory is empty.
- `docs/PHASE2_PROGRESS.md`  ::  header, §4 decisions 14–17, §5 questions, §6 ledger, §7 traps 12–15, §8 session log.

## 3. Files / folders deleted

none — this stage only creates. `--dev` output is isolated under `data/processed/tasks/_dev/` and is never published.

## 4. Design decisions

- **Fiducials are extracted over the full clean cohort, not A4's slice**  ::  A4's primary cohort is L3 x {high, medium} SQI, but §4.A.4.8 requires a full-clean-cohort sensitivity and §4.B.3.2 puts B3 on the full clean cohort too. One 749,112-study pass serves all three; two passes over an 11.85 GB container would have cost another five hours for the same numbers.
- **`sqi_per_bin` is added to the fiducial schema**  ::  §4.A.4.3 lists four columns. B3's NOISY_SEGMENT query needs per-second `ecg_quality`, and computing it during the fiducial pass reuses a signal read that has already happened. It is computed on exactly Phase 1's `_sqi_one` code path, so a bin value is on the same scale as `waveform_qc.sqi_aggregate`.
- **The lab cache is rebuilt as a sibling file, not in place**  ::  `labevents.parquet` is a Phase 1 provenance artifact covering 158 M rows and every itemid; the rebuild covers 18 itemids. Overwriting would discard data the rebuild does not replace, in exchange for nothing A3 needs.
- **Primary and sensitivity cohorts live in one table per task**  ::  §4.A.1.5's own schema comment ('L3 in primary; L2 in sensitivity') describes a single table with the filter columns present. Every task adds an explicit `is_primary` boolean so no downstream consumer has to re-derive the primary filter and risk getting it wrong.
- **QTc reads `machine_qtc_ms`**  ::  §4 decision 14. The NeuroKit `qtc_bazett_ms` correlates with the machine QTc at r = 0.024 and is valid for 656,358 studies against 748,618.
- **A5 masks claims, not numerals**  ::  §4 decision 16. The reports contain no numeric measurements at all.
- **A6 reports readmission censoring rather than correcting it**  ::  §4 decision 15. Every usable substitute for MIMIC-IV's missing end-of-data cutoff conditions on the outcome.
- **A4's algorithmic baseline must use `method="neurokit"`**  ::  §4.A.4.7 calls it 'Pan-Tompkins' and promises F1 = 1.0. Both can only hold if the baseline runs the same detector as the ground truth, which is NeuroKit's default — the Phase 1 regen moved away from `pantompkins` because it was wrong. `pantompkins` may be reported as an extra non-oracle row measuring detector disagreement.

## 5. Complete code

### `scripts/phase2_tasks_benchmark_and_paper/00_extract_fiducials.py`

```python
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
    bc.set_dev(args.dev)

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
```

### `scripts/phase2_tasks_benchmark_and_paper/00b_rebuild_lab_cache.py`

```python
"""Stage P2.1 prerequisite -- re-extract the lab cache with the columns A3 needs.

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/00b_rebuild_lab_cache.py

Why this exists (spec §12.8.7, progress-doc §4 decision 13 / trap 7b).
``data/raw/ehr_cache/labevents.parquet`` (158,374,764 rows) kept only
``labevent_id, subject_id, hadm_id, itemid, charttime, valuenum, valueuom``. The
§4.A.3.3 label rule branches on ``ref_range_lower``, ``ref_range_upper`` and
``flag``, none of which survived. Without them A3 collapses to
``missing`` vs ``not_missing``.

What it does. Streams ``data/raw/mimic-iv-hosp-3.1/hosp/labevents.csv.gz``
(2.6 GB gz, 16 columns) in chunks, keeps only the 18 itemids locked in
``config/lab_itemid_map_LOCKED.yaml``, and writes
``data/raw/ehr_cache/labevents_key_labs.parquet`` with the nine columns A3
needs. Roughly 21 M rows survive the filter.

**The original parquet is not touched.** It is a Phase 1 provenance artifact and
this script only adds a sibling next to it -- extending an EHR cache, re-running
no Phase 1 stage (§2).

Resume. Each chunk group becomes a part parquet under
``data/processed/_p2_parts/lab_cache/``; the state file records how many source
chunks have been consumed. A killed run restarts by re-reading (but not
re-writing) the chunks it already finished.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402

STAGE = "P2.1"
SCRIPT = "00b_rebuild_lab_cache"

SOURCE_CSV = bc.DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "labevents.csv.gz"
OUT_PATH = bc.EHR_CACHE / "labevents_key_labs.parquet"
PART_NAME = "lab_cache"

# The nine columns the §4.A.3.3 rule and its provenance need. `value` is kept
# because a few assays report a non-numeric result ("NEG", "<0.01") whose
# valuenum is null -- that is the `missing` class, and the raw string is the
# evidence for it.
USE_COLS = [
    "labevent_id", "subject_id", "hadm_id", "itemid", "charttime",
    "value", "valuenum", "valueuom", "ref_range_lower", "ref_range_upper", "flag",
]
CHUNK_ROWS = 4_000_000

SCHEMA = pa.schema([
    ("labevent_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("hadm_id", pa.float64()),          # nullable in the source; float keeps NA
    ("itemid", pa.int32()),
    ("charttime", pa.timestamp("ns")),
    ("value", pa.string()),
    ("valuenum", pa.float64()),
    ("valueuom", pa.string()),
    ("ref_range_lower", pa.float64()),
    ("ref_range_upper", pa.float64()),
    ("flag", pa.string()),
])


def locked_itemids() -> tuple[list[int], dict[int, str]]:
    cfg = yaml.safe_load((bc.CONFIG_DIR / "lab_itemid_map_LOCKED.yaml").read_text(encoding="utf-8"))
    ids: list[int] = []
    lab_of: dict[int, str] = {}
    for lab, block in cfg["labs"].items():
        for itemid in block["itemids"]:
            ids.append(int(itemid))
            lab_of[int(itemid)] = lab
    if len(ids) != len(set(ids)):
        raise RuntimeError("an itemid is claimed by two labs in lab_itemid_map_LOCKED.yaml")
    return sorted(ids), lab_of


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    bc.add_std_args(parser)
    args = parser.parse_args()
    bc.set_dev(args.dev)

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT)
    if state.done and not args.force:
        log.info("already complete (%s rows) -- pass --force to rebuild", state.data.get("n_rows"))
        return 0
    if args.force:
        for part in bc.part_dir(PART_NAME).glob("part_*.parquet"):
            part.unlink()
        state.reset()

    bc.preflight([SOURCE_CSV, bc.CONFIG_DIR / "lab_itemid_map_LOCKED.yaml"], need_free_gb=5.0)
    itemids, lab_of = locked_itemids()
    log.info("locked itemids: %d -> %s", len(itemids), itemids)

    chunks_done = int(state.data.get("chunks_done", 0))
    if chunks_done:
        # ponytail: resume re-parses the consumed prefix rather than seeking.
        # gzip has no index and `value`/`comments` are quoted CSV fields that may
        # contain commas, so a byte- or line-offset skip is not safe. Re-parsing
        # ~15 min of prefix beats a subtly wrong resume; if this ever matters,
        # split the source once into itemid-partitioned shards instead.
        log.info("resuming: skipping %d already-consumed source chunks", chunks_done)

    keep = set(itemids)
    started = time.time()
    rows_in = int(state.data.get("rows_in", 0))
    rows_out = int(state.data.get("rows_out", 0))
    if not chunks_done:
        rows_in = rows_out = 0

    reader = pd.read_csv(
        SOURCE_CSV,
        usecols=USE_COLS,
        chunksize=CHUNK_ROWS,
        compression="gzip",
        low_memory=False,
        dtype={"value": "string", "valueuom": "string", "flag": "string"},
    )
    buffer: list[pd.DataFrame] = []
    buffered = 0
    index = -1
    for index, chunk in enumerate(reader):
        if index < chunks_done:
            continue
        rows_in += len(chunk)
        hit = chunk[chunk["itemid"].isin(keep)].copy()
        if len(hit):
            hit["charttime"] = pd.to_datetime(hit["charttime"], errors="coerce")
            hit["itemid"] = hit["itemid"].astype("int32")
            buffer.append(hit[USE_COLS])
            buffered += len(hit)
            rows_out += len(hit)
        if buffered >= 4_000_000:
            path = bc.write_part(PART_NAME, pd.concat(buffer, ignore_index=True), SCHEMA)
            log.info("wrote %s rows=%d", path.name, buffered)
            buffer, buffered = [], 0
        state.update(chunks_done=index + 1, rows_in=rows_in, rows_out=rows_out)
        rate = rows_in / max(1e-6, time.time() - started)
        log.info("chunk %d: rows_in=%d rows_out=%d (%.0f k rows/s)",
                 index, rows_in, rows_out, rate / 1000)

    if buffer:
        path = bc.write_part(PART_NAME, pd.concat(buffer, ignore_index=True), SCHEMA)
        log.info("wrote %s rows=%d", path.name, buffered)

    n = bc.publish_parts(
        PART_NAME, OUT_PATH, SCHEMA, sort_by="subject_id",
        metadata={"source": str(SOURCE_CSV.name), "n_itemids": str(len(itemids)),
                  "spec": "PHASE2_SOURCE_OF_TRUTH.md §12.8.7"},
    )
    log.info("published %s rows=%d (source rows read=%d)", OUT_PATH, n, rows_in)

    # Validation: the recovered columns must actually be populated, per lab.
    got = pd.read_parquet(OUT_PATH, columns=["itemid", "valuenum", "ref_range_lower",
                                             "ref_range_upper", "flag"])
    got["lab"] = got["itemid"].map(lab_of)
    summary = got.groupby("lab").agg(
        n=("itemid", "size"),
        valuenum_pct=("valuenum", lambda s: round(100 * s.notna().mean(), 2)),
        ref_lower_pct=("ref_range_lower", lambda s: round(100 * s.notna().mean(), 2)),
        ref_upper_pct=("ref_range_upper", lambda s: round(100 * s.notna().mean(), 2)),
        flag_pct=("flag", lambda s: round(100 * s.notna().mean(), 2)),
    )
    log.info("per-lab coverage:\n%s", summary.to_string())
    if summary["ref_lower_pct"].max() == 0:
        raise RuntimeError("ref_range_lower is empty for every lab -- the extract is wrong")

    state.finish(
        n_rows=n, rows_read=rows_in, out_path=str(OUT_PATH),
        per_lab=summary.reset_index().to_dict("records"),
        elapsed_seconds=round(time.time() - started, 1),
    )
    log.info("DONE in %.1f min", (time.time() - started) / 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### `scripts/phase2_tasks_benchmark_and_paper/01_build_A1_ecg_diagnosis.py`

```python
"""Stage P2.1 script 01 -- A1: EHR diagnosis prediction (multi-label ICD).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/01_build_A1_ecg_diagnosis.py [--dev]

Spec §4.A.1. Five multi-label ICD-group heads over the hospital admission the
ECG overlaps with. The label is **encounter-associated, not prospective** -- the
ICD code is assigned at the end of the admission, after the ECG (§4.A.1.3).

Cohort (§4.A.1.2). ``link_tier == 'L3'`` with ``icd_available`` is primary;
``link_tier in {L3, L2}`` is the sensitivity cohort. Both live in ONE table,
distinguished by ``link_tier`` and by the added ``is_primary`` flag -- the
§4.A.1.5 schema already carries ``link_tier`` with the comment "L3 in primary;
L2 in sensitivity", so a single table with the filter columns present is what
that schema describes. Same for the label source: hospital ICD rows are
primary, and ED-linked rows carry ``label_source == 'ed'`` and
``is_primary == False`` so they are never pooled by accident (§4.A.1.2, Plan
A/B §5.3 "Do not mix hospital and ED labels without a provenance column").

Labels come from ``config/icd_label_map_LOCKED.yaml`` and nothing else. Its
matching contract is binding: strip the code, match ``icd_version`` exactly,
``*_prefix`` is ``startswith``, ``*_exact*`` is equality, groups are
independent. ``cohort_manifest.parquet`` carries the resolved ``long_title``
for every code that fired, per Appendix B.

Machine measurements and structured features are forbidden inputs (§4.A.1.4)
and no column here is derived from them; ``sqi_tier`` and ``cart_id`` are
subgroup keys, not features.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402

STAGE = "P2.1"
SCRIPT = "01_build_A1_ecg_diagnosis"
TASK = "A1_ecg_diagnosis"

GROUPS = [
    "atrial_fibrillation_flutter",
    "heart_failure_narrow",
    "acute_myocardial_infarction",
    "conduction_disorder",
    "ventricular_arrhythmia_or_arrest",
]
BOUNDARY_HOURS = 2  # §4.A.1.5: within +/-2 h of admittime or dischtime

SCHEMA = pa.schema(
    [
        ("study_id", pa.int64()),
        ("subject_id", pa.int64()),
        ("split", pa.string()),
        ("hadm_id", pa.int64()),
        ("ecg_time", pa.timestamp("ns")),
        ("link_tier", pa.string()),
        ("boundary_flag", pa.bool_()),
    ]
    + [(f"label_{g}", pa.bool_()) for g in GROUPS]
    + [
        ("label_source", pa.string()),
        ("n_icd_codes_on_admission", pa.int32()),
        ("icd_codes_matched", pa.list_(pa.string())),
        ("sqi_tier", pa.string()),
        ("cart_id", pa.string()),
        ("is_primary", pa.bool_()),
    ]
)


def load_label_map() -> dict:
    return yaml.safe_load(
        (bc.CONFIG_DIR / "icd_label_map_LOCKED.yaml").read_text(encoding="utf-8")
    )["groups"]


def code_group_table(codes: pd.DataFrame, groups: dict) -> pd.DataFrame:
    """One row per distinct (icd_version, icd_code) with a boolean per group.

    ``codes`` must carry ``icd_code`` (already stripped) and ``icd_version``.
    """
    out = codes.copy()
    for group in GROUPS:
        rules = groups[group]
        hit = np.zeros(len(out), dtype=bool)
        for version, prefix_key, exact_keys in (
            (10, "icd10_prefix", ("icd10_exact", "icd10_exact_optional")),
            (9, "icd9_prefix", ("icd9_exact", "icd9_exact_optional")),
        ):
            same_version = (out["icd_version"] == version).to_numpy()
            for prefix in rules.get(prefix_key, []) or []:
                hit |= same_version & out["icd_code"].str.startswith(str(prefix)).to_numpy()
            for exact_key in exact_keys:
                exact = set(str(c) for c in (rules.get(exact_key, []) or []))
                if exact:
                    hit |= same_version & out["icd_code"].isin(exact).to_numpy()
        out[group] = hit
    return out


def aggregate_by_encounter(assign: pd.DataFrame, key: str, code_groups: pd.DataFrame) -> pd.DataFrame:
    """Roll per-code group flags up to one row per encounter (`hadm_id` / `stay_id`)."""
    merged = assign.merge(code_groups, on=["icd_code", "icd_version"], how="left")
    for group in GROUPS:
        merged[group] = merged[group].fillna(False)
    merged["any_group"] = merged[GROUPS].any(axis=1)

    agg = merged.groupby(key, sort=False).agg(
        **{g: (g, "any") for g in GROUPS},
        n_icd_codes_on_admission=("icd_code", "size"),
    )
    matched = (
        merged[merged["any_group"]]
        .sort_values([key, "icd_code"], kind="mergesort")
        .groupby(key, sort=False)["icd_code"]
        .apply(list)
        .rename("icd_codes_matched")
    )
    agg = agg.join(matched)
    agg["icd_codes_matched"] = agg["icd_codes_matched"].apply(
        lambda v: v if isinstance(v, list) else []
    )
    return agg.reset_index()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    bc.add_std_args(parser)
    args = parser.parse_args()
    bc.set_dev(args.dev)

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT + ("_dev" if args.dev else ""))
    if state.done and not args.force:
        log.info("already complete (%s rows) -- pass --force to rebuild", state.data.get("n_rows"))
        return 0
    state.reset()
    started = time.time()

    bc.preflight([
        bc.EHR_CACHE / "diagnoses_icd.parquet",
        bc.EHR_CACHE / "d_icd_diagnoses.parquet",
        bc.EHR_CACHE / "ed_diagnosis.parquet",
        bc.EHR_CACHE / "admissions.parquet",
        bc.CONFIG_DIR / "icd_label_map_LOCKED.yaml",
    ])

    groups = load_label_map()
    cohort = bc.load_clean_cohort(dev=args.dev)
    cohort = cohort[cohort.link_tier.isin(["L3", "L2"])].copy()
    log.info("L3+L2 clean cohort: %d studies", len(cohort))

    # --- hospital ICD --------------------------------------------------------
    diag = pd.read_parquet(
        bc.EHR_CACHE / "diagnoses_icd.parquet",
        columns=["subject_id", "hadm_id", "icd_code", "icd_version"],
    )
    diag["icd_code"] = diag["icd_code"].astype(str).str.strip()
    needed_hadm = set(cohort.hadm_id.dropna().astype("int64"))
    diag = diag[diag.hadm_id.isin(needed_hadm)]
    log.info("diagnoses_icd rows on cohort admissions: %d", len(diag))

    distinct = diag[["icd_code", "icd_version"]].drop_duplicates()
    code_groups = code_group_table(distinct, groups)
    log.info("distinct codes on cohort admissions: %d, firing: %d",
             len(code_groups), int(code_groups[GROUPS].any(axis=1).sum()))
    hosp = aggregate_by_encounter(diag, "hadm_id", code_groups)

    # --- ED ICD (secondary, provenance-tagged, never pooled) -----------------
    ed = pd.read_parquet(
        bc.EHR_CACHE / "ed_diagnosis.parquet",
        columns=["subject_id", "stay_id", "icd_code", "icd_version"],
    )
    ed["icd_code"] = ed["icd_code"].astype(str).str.strip()
    needed_stay = set(cohort.stay_id.dropna().astype("int64"))
    ed = ed[ed.stay_id.isin(needed_stay)]
    ed_codes = code_group_table(ed[["icd_code", "icd_version"]].drop_duplicates(), groups)
    ed_agg = aggregate_by_encounter(ed, "stay_id", ed_codes) if len(ed) else None
    log.info("ed_diagnosis rows on cohort stays: %d", len(ed))

    # --- boundary flag -------------------------------------------------------
    adm = pd.read_parquet(
        bc.EHR_CACHE / "admissions.parquet", columns=["hadm_id", "admittime", "dischtime"]
    )
    cohort = cohort.merge(adm, on="hadm_id", how="left")
    window = pd.Timedelta(hours=BOUNDARY_HOURS)
    near_admit = (cohort.ecg_time - cohort.admittime).abs() <= window
    near_disch = (cohort.ecg_time - cohort.dischtime).abs() <= window
    cohort["boundary_flag"] = (near_admit | near_disch).fillna(False)

    # --- assemble ------------------------------------------------------------
    hosp_rows = cohort[cohort.hadm_id.notna() & cohort.icd_available.fillna(False)].merge(
        hosp, on="hadm_id", how="inner"
    )
    hosp_rows["label_source"] = "hosp"
    log.info("hospital-ICD rows: %d", len(hosp_rows))

    if ed_agg is not None and len(ed_agg):
        ed_rows = cohort[cohort.stay_id.notna() & cohort.hadm_id.isna()].merge(
            ed_agg, on="stay_id", how="inner"
        )
        ed_rows["label_source"] = "ed"
    else:
        ed_rows = hosp_rows.iloc[0:0].copy()
    log.info("ED-ICD rows (secondary only): %d", len(ed_rows))

    df = pd.concat([hosp_rows, ed_rows], ignore_index=True)
    for group in GROUPS:
        df[f"label_{group}"] = df[group].astype(bool)
    df["is_primary"] = (df.link_tier == "L3") & (df.label_source == "hosp")
    df["cart_id"] = df["cart_id"].astype("Int64").astype("string")
    df["hadm_id"] = df["hadm_id"].astype("Int64")
    df["n_icd_codes_on_admission"] = df["n_icd_codes_on_admission"].astype("int32")
    df = df.sort_values("study_id", kind="mergesort").reset_index(drop=True)

    counts = bc.write_task_split_parquets(df, TASK, schema=SCHEMA)
    log.info("wrote splits: %s", counts)

    # --- cohort manifest: the Appendix B long_title evidence -----------------
    dictionary = pd.read_parquet(
        bc.EHR_CACHE / "d_icd_diagnoses.parquet",
        columns=["icd_code", "icd_version", "long_title"],
    )
    dictionary["icd_code"] = dictionary["icd_code"].astype(str).str.strip()
    firing = code_groups[code_groups[GROUPS].any(axis=1)].merge(
        dictionary, on=["icd_code", "icd_version"], how="left"
    )
    occurrences = diag.groupby(["icd_code", "icd_version"]).size().rename("n_rows_in_cohort")
    firing = firing.merge(occurrences, on=["icd_code", "icd_version"], how="left")
    firing["n_rows_in_cohort"] = firing["n_rows_in_cohort"].fillna(0).astype("int64")
    manifest = firing.melt(
        id_vars=["icd_code", "icd_version", "long_title", "n_rows_in_cohort"],
        value_vars=GROUPS, var_name="icd_group", value_name="matched",
    )
    manifest = manifest[manifest.matched].drop(columns=["matched"]).sort_values(
        ["icd_group", "icd_version", "icd_code"], kind="mergesort"
    )
    bc.write_cohort_manifest(manifest, TASK)
    log.info("cohort_manifest: %d (group, code) rows", len(manifest))

    # --- validation (§9.2) ---------------------------------------------------
    primary = df[df.is_primary]
    stats = {
        "n_rows_total": int(len(df)),
        "n_rows_primary_l3_hosp": int(len(primary)),
        "n_rows_sensitivity_l2": int((df.link_tier == "L2").sum()),
        "n_rows_ed_secondary": int((df.label_source == "ed").sum()),
        "splits": counts,
        "boundary_flag_pct": round(100 * float(df.boundary_flag.mean()), 3),
        "boundary_flag_pct_primary": round(100 * float(primary.boundary_flag.mean()), 3),
        "n_manifest_codes": int(len(manifest)),
        "prevalence_primary": {
            g: round(100 * float(primary[f"label_{g}"].mean()), 3) for g in GROUPS
        },
        "prevalence_primary_by_split": {
            s: {g: round(100 * float(primary[primary.split == s][f"label_{g}"].mean()), 3)
                for g in GROUPS}
            for s in bc.SPLITS
        },
        "n_any_label_primary": int(primary[[f"label_{g}" for g in GROUPS]].any(axis=1).sum()),
    }
    stats.update(bc.split_summary(df))
    stats.update({f"primary_{k}": v for k, v in bc.split_summary(primary).items()})
    log.info("validation:\n%s", json.dumps(stats, indent=2))

    if stats["n_rows_primary_l3_hosp"] == 0:
        raise RuntimeError("A1 primary cohort is empty")
    if stats["n_any_label_primary"] == 0:
        raise RuntimeError("no primary row carries any ICD group label")

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# A1 -- EHR diagnosis prediction (multi-label ICD)

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.A.1 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/01_build_A1_ecg_diagnosis.py`.

## Reading this table

`train.parquet` / `val.parquet` / `test.parquet` hold the **union** of the
primary and sensitivity cohorts. Filter before use:

| Analysis | Filter |
| --- | --- |
| **Primary** (§4.A.1.2) | `is_primary` — equivalently `link_tier == 'L3' and label_source == 'hosp'` |
| L3+L2 sensitivity | `link_tier in ('L3','L2') and label_source == 'hosp'` |
| Hospital+ED secondary | drop the `label_source` filter; never pool without reporting it |
| Boundary-excluded sensitivity | `not boundary_flag` |

The split column is joined from `splits_subject_level.parquet` and is never
re-derived (§4.C invariant 1).

## Labels

Five independent binary heads from `config/icd_label_map_LOCKED.yaml`. A head is
True when **any** ICD row on the linked encounter matches **any** pattern in that
group. `icd_codes_matched` lists the codes that fired;
`cohort_manifest.parquet` resolves every one of them to its `long_title`
(Plan A/B Appendix B).

Label timing: **encounter-associated, not prospective.** The ICD code is
assigned at the end of the admission, after the ECG.

## Forbidden inputs

`machine_measurements`, `structured_features` (§4.A.1.4). `sqi_tier` and
`cart_id` are present as subgroup keys for the §4.A.1.8 tables, not as model
features.

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
```

### `scripts/phase2_tasks_benchmark_and_paper/02_build_A2_measurement_blind.py`

```python
"""Stage P2.1 script 02 -- A2: measurement-blind physiological inference (L3).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/02_build_A2_measurement_blind.py [--dev]

Spec §4.A.2. Three softmax heads -- binned HR, QRS duration and QTc -- predicted
from the signal alone. Plan A/B §5.4 calls this a sanity check, not a novelty
claim, and mandates reporting by SQI tier.

**Cohort deviation, already locked.** §4.A.2.2 sets the primary cohort to
``sqi_tier == 'high'`` and estimates ~445 K ECGs. Measured, ``high`` is 4,166 of
749,112 clean studies (0.56 %), of which 3,110 are L3 -- a literal A2 would
train on 3,110 ECGs. Round 6.4 / progress-doc question 9 resolved this: the
primary cohort is ``sqi_tier in {high, medium}`` and high-only becomes one row
of the §4.A.2.8 per-SQI sensitivity table. A4 already used {high, medium}, so
the two tasks now share one SQI rule. **Disclosed in the supplementary.**

The table holds the union of the primary and sensitivity cohorts; ``is_primary``
marks ``link_tier == 'L3' and sqi_tier in {high, medium}``. ``link_tier`` and
``sqi_tier`` are present so every §4.A.2.8 slice is a filter, not a rebuild.

Labels read the MACHINE measurement (Round 6.1) with the 29999 sentinel masked
(Round 6.2); the ``*_missing`` flag columns are never consulted -- they are False
for all 749,112 rows and mark nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402
from _dataset_lib import measurement_task as mt  # noqa: E402

STAGE = "P2.1"
SCRIPT = "02_build_A2_measurement_blind"
TASK = "A2_measurement_blind"

PRIMARY_SQI = ("high", "medium")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    bc.add_std_args(parser)
    args = parser.parse_args()
    bc.set_dev(args.dev)

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT + ("_dev" if args.dev else ""))
    if state.done and not args.force:
        log.info("already complete (%s rows) -- pass --force to rebuild", state.data.get("n_rows"))
        return 0
    state.reset()
    started = time.time()

    bc.preflight([
        bc.DATA_PROCESSED / "index" / "ecg_metadata_clean_with_measurements.parquet",
        bc.DATA_PROCESSED / "waveform_qc.parquet",
        bc.DATA_PROCESSED / "splits_subject_level.parquet",
    ])

    table = mt.measurement_table(dev=args.dev)
    log.info("clean cohort with all three machine measurements valid: %d", len(table))

    # A2 is L3-scoped; L2 rides along for the l3_vs_l3l2 sensitivity table.
    df = table[table.link_tier.isin(["L3", "L2"])].copy()
    df["is_primary"] = (df.link_tier == "L3") & (df.sqi_tier.isin(PRIMARY_SQI))
    log.info("A2 table: %d rows, %d primary", len(df), int(df.is_primary.sum()))

    counts = bc.write_task_split_parquets(df, TASK, schema=mt.SCHEMA)
    log.info("wrote splits: %s", counts)

    primary = df[df.is_primary]
    stats = {
        "n_rows_total": int(len(df)),
        "n_rows_primary": int(len(primary)),
        "splits_total": counts,
        "sqi_breakdown_l3": {
            tier: int(((df.link_tier == "L3") & (df.sqi_tier == tier)).sum())
            for tier in ("high", "medium", "low")
        },
        "n_rows_l3_sqi_high_only": int(
            ((df.link_tier == "L3") & (df.sqi_tier == "high")).sum()
        ),
        "n_rows_l3_l2_sqi_high_medium": int(df.sqi_tier.isin(PRIMARY_SQI).sum()),
        "labels_primary": mt.label_stats(primary),
        "measurement_summary_primary": {
            col: {
                "mean": round(float(primary[col].mean()), 2),
                "median": round(float(primary[col].median()), 2),
                "min": round(float(primary[col].min()), 2),
                "max": round(float(primary[col].max()), 2),
            }
            for col in ("hr_bpm", "qrs_ms", "qtc_ms")
        },
        "qtc_bazett_valid_pct_primary": round(
            100 * float(primary.qtc_ms_bazett.notna().mean()), 2
        ),
    }
    stats.update(bc.split_summary(df))
    stats.update({f"primary_{k}": v for k, v in bc.split_summary(primary).items()})
    log.info("validation:\n%s", json.dumps(stats, indent=2))

    if stats["n_rows_primary"] == 0:
        raise RuntimeError("A2 primary cohort is empty")
    for head in mt.HEADS:
        if primary[head].isna().any():
            raise RuntimeError(f"{head} is null on a primary row -- validity gate leaked")

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# A2 -- measurement-blind physiological inference (L3 cohort)

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.A.2 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/02_build_A2_measurement_blind.py`.

## Reading this table

| Analysis | Filter |
| --- | --- |
| **Primary** | `is_primary` — `link_tier == 'L3' and sqi_tier in ('high','medium')` |
| §4.A.2.8 high-SQI-only row | `link_tier == 'L3' and sqi_tier == 'high'` |
| §4.A.2.8 low-SQI row | `link_tier == 'L3' and sqi_tier == 'low'` |
| L3 vs L3+L2 | `link_tier in ('L3','L2')` — the whole table |

## Two locked deviations from §4

1. **Primary cohort is `sqi_tier in {{high, medium}}`, not `high`** (Round 6.4,
   progress-doc question 9). `high` alone is 3,110 L3 studies, not the ~445 K
   §4.A.2.2 predicts. high-only is now a sensitivity row.
2. **`qtc_ms` is `machine_qtc_ms`**, not `structured_features.qtc_bazett_ms`
   which §4.A.2.3 names. The NeuroKit column correlates with the machine QTc at
   r = 0.024 and is valid for 656,358 studies against 748,618. It is kept as
   `qtc_ms_bazett` for provenance and one sensitivity row.

Both are disclosed in the supplementary.

## Labels

`hr_label` bradycardia / normal / tachycardia at 60 and 100 bpm ·
`qrs_label` normal / borderline / wide at 100 and 120 ms ·
`qtc_label` short / normal / prolonged at 350 and 450 ms (single cut for both
sexes; the 460 ms female cut is a supplementary sensitivity).

A row is emitted only when all three machine measurements are valid — sentinel
`29999` masked, then range-gated to HR 20–300, QRS 40–300, QTc 200–800.

## Forbidden inputs

Everything except the four signal kinds (§4.A.2.4): images, `report_text`,
`machine_measurements` and `structured_features` are all forbidden. `hr_bpm`,
`qrs_ms`, `qtc_ms` and `qtc_ms_bazett` are in this table as **label
provenance**; feeding them to a model is the leakage the task exists to avoid.

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
```

### `scripts/phase2_tasks_benchmark_and_paper/03_build_A3_lab_abnormality.py`

```python
"""Stage P2.1 script 03 -- A3: lab abnormality prediction (7 labs x 5 windows).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/03_build_A3_lab_abnormality.py [--dev]

Spec §4.A.3. Thirty-five 5-class heads: for each (lab, window) pair, the
abnormality status of the lab event nearest in time to the ECG.

**Prerequisite.** Reads ``data/raw/ehr_cache/labevents_key_labs.parquet``, built
by ``00b_rebuild_lab_cache.py``. The Phase 1 ``labevents.parquet`` dropped
``ref_range_lower``, ``ref_range_upper`` and ``flag`` -- the three columns
§4.A.3.3's rule branches on -- so it cannot be used here (spec §12.8.7, trap 7b).

Label rule (§4.A.3.3, precedence order, from ``lab_itemid_map_LOCKED.yaml``)::

    valuenum is null                          -> missing
    ref_range_lower is not null and v < lower -> low_abnormal
    ref_range_upper is not null and v > upper -> high_abnormal
    flag indicates abnormal                   -> abnormal_unknown_direction
    otherwise                                 -> normal

``missing`` is a real class and is never dropped: Plan A/B §5.5 asks for lab
availability to be modelled as a missingness process, and the class carries it.

How the nearest event is found. Two ``merge_asof`` passes per lab -- one
backward, one forward, both at the widest tolerance (24 h) -- give the nearest
prior and nearest subsequent event. Every one of the five windows is then a
bounds test on those two candidates, because "nearest" is monotone under
shrinking the window: the nearest event within +/-24 h that also lies within
+/-6 h *is* the nearest event within +/-6 h.

**Open question 1 (join policy), proceeding under the stated default.**
``config/lab_itemid_map_LOCKED.yaml`` sets the primary join to ``same_subject``
and makes ``same_subject AND same_hadm_id`` a required sensitivity sweep
(§4.A.3.8). Both are built: the 105 columns §4.A.3.5 specifies are the
same-subject join, and 35 ``..._label_same_hadm`` columns carry the restricted
join so the sweep is a filter rather than a rebuild. Restricting to the
admission removes candidates, so it can select a genuinely different event --
which is why it needs its own columns and cannot be recovered from a flag.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402

STAGE = "P2.1"
SCRIPT = "03_build_A3_lab_abnormality"
TASK = "A3_lab_abnormality"

LAB_EVENTS = bc.EHR_CACHE / "labevents_key_labs.parquet"
LABS = ["K", "Na", "creatinine", "troponin", "lactate", "Ca", "Mg"]
CLASSES = ["missing", "low_abnormal", "high_abnormal", "abnormal_unknown_direction", "normal"]
METHODS = ["no_event", "null_value", "ref_range", "flag"]
MAX_TOLERANCE_HOURS = 24

DICT_STR = pa.dictionary(pa.int32(), pa.string())


def load_windows() -> dict[str, tuple[float, float]]:
    cfg = yaml.safe_load((bc.CONFIG_DIR / "lab_itemid_map_LOCKED.yaml").read_text(encoding="utf-8"))
    return {
        name: (float(block["lower_hours"]), float(block["upper_hours"]))
        for name, block in cfg["windows"].items()
    }


def load_itemids() -> dict[str, list[int]]:
    cfg = yaml.safe_load((bc.CONFIG_DIR / "lab_itemid_map_LOCKED.yaml").read_text(encoding="utf-8"))
    return {lab: [int(i) for i in block["itemids"]] for lab, block in cfg["labs"].items()}


def build_schema(windows: list[str]) -> pa.Schema:
    fields = [
        ("study_id", pa.int64()),
        ("subject_id", pa.int64()),
        ("split", pa.string()),
        ("link_tier", pa.string()),
        ("sqi_tier", pa.string()),
        ("cart_id", pa.string()),
        ("boundary_flag", pa.bool_()),
        ("hadm_id", pa.int64()),
        ("ecg_time", pa.timestamp("ns")),
        ("is_primary", pa.bool_()),
    ]
    for lab in LABS:
        for window in windows:
            fields.append((f"lab_{lab}_{window}_label", DICT_STR))
            fields.append((f"lab_{lab}_{window}_signed_hours_from_ecg", pa.float32()))
            fields.append((f"lab_{lab}_{window}_abnormal_method", DICT_STR))
            fields.append((f"lab_{lab}_{window}_label_same_hadm", DICT_STR))
    return pa.schema(fields)


def classify(valuenum: np.ndarray, lower: np.ndarray, upper: np.ndarray,
             flag_abnormal: np.ndarray, present: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The §4.A.3.3 precedence, vectorised. Returns (label, abnormal_method)."""
    label = np.full(present.shape, "missing", dtype=object)
    method = np.full(present.shape, "no_event", dtype=object)

    has_value = present & np.isfinite(valuenum)
    null_value = present & ~np.isfinite(valuenum)
    method[null_value] = "null_value"          # label stays "missing"

    low = has_value & np.isfinite(lower) & (valuenum < lower)
    high = has_value & ~low & np.isfinite(upper) & (valuenum > upper)
    flagged = has_value & ~low & ~high & flag_abnormal
    normal = has_value & ~low & ~high & ~flagged

    label[low], method[low] = "low_abnormal", "ref_range"
    label[high], method[high] = "high_abnormal", "ref_range"
    label[flagged], method[flagged] = "abnormal_unknown_direction", "flag"
    label[normal], method[normal] = "normal", "ref_range"
    return label, method


def nearest_events(ecgs: pd.DataFrame, events: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Nearest prior and nearest subsequent lab event per ECG, within 24 h.

    ``by`` is ``['subject_id']`` for the primary join and
    ``['subject_id', 'hadm_id']`` for the same-admission sensitivity join.
    """
    tolerance = pd.Timedelta(hours=MAX_TOLERANCE_HOURS)
    value_cols = ["charttime", "valuenum", "ref_range_lower", "ref_range_upper", "flag_abnormal"]

    left = ecgs.sort_values("ecg_time", kind="mergesort")
    right = events.sort_values("charttime", kind="mergesort")
    out = left[["study_id"]].copy()

    for direction, tag in (("backward", "prev"), ("forward", "next")):
        merged = pd.merge_asof(
            left, right[by + value_cols], left_on="ecg_time", right_on="charttime",
            by=by, direction=direction, tolerance=tolerance, allow_exact_matches=True,
        )
        for col in value_cols:
            out[f"{tag}_{col}"] = merged[col].to_numpy()
    return out


def resolve_window(cand: pd.DataFrame, ecg_time: np.ndarray,
                   lower_h: float, upper_h: float) -> dict[str, np.ndarray]:
    """Pick whichever of the two candidates falls in [lower_h, upper_h] and is nearer."""
    hours = {}
    for tag in ("prev", "next"):
        delta = (cand[f"{tag}_charttime"].to_numpy() - ecg_time)
        hours[tag] = delta / np.timedelta64(1, "h")

    usable = {
        tag: np.isfinite(hours[tag]) & (hours[tag] >= lower_h) & (hours[tag] <= upper_h)
        for tag in ("prev", "next")
    }
    prev_dist = np.where(usable["prev"], np.abs(hours["prev"]), np.inf)
    next_dist = np.where(usable["next"], np.abs(hours["next"]), np.inf)
    take_prev = usable["prev"] & (prev_dist <= next_dist)
    take_next = usable["next"] & ~take_prev
    present = take_prev | take_next

    def pick(column: str, dtype: str) -> np.ndarray:
        prev = cand[f"prev_{column}"].to_numpy()
        nxt = cand[f"next_{column}"].to_numpy()
        return np.where(take_prev, prev, nxt).astype(dtype)

    signed = np.where(take_prev, hours["prev"], np.where(take_next, hours["next"], np.nan))
    label, method = classify(
        pick("valuenum", "float64"),
        pick("ref_range_lower", "float64"),
        pick("ref_range_upper", "float64"),
        pick("flag_abnormal", "float64") > 0.5,
        present,
    )
    return {"label": label, "method": method, "signed_hours": signed.astype("float32")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    bc.add_std_args(parser)
    args = parser.parse_args()
    bc.set_dev(args.dev)

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT + ("_dev" if args.dev else ""))
    if state.done and not args.force:
        log.info("already complete (%s rows) -- pass --force to rebuild", state.data.get("n_rows"))
        return 0
    state.reset()
    started = time.time()

    bc.preflight([LAB_EVENTS, bc.CONFIG_DIR / "lab_itemid_map_LOCKED.yaml"], need_free_gb=5.0)

    windows = load_windows()
    itemids = load_itemids()
    window_names = list(windows)
    log.info("windows: %s", windows)

    cohort = bc.load_clean_cohort(dev=args.dev)
    cohort = cohort[cohort.link_tier.isin(["L3", "L2"])].copy()
    cohort["is_primary"] = cohort.link_tier == "L3"
    log.info("L3+L2 clean cohort: %d studies", len(cohort))

    adm = pd.read_parquet(bc.EHR_CACHE / "admissions.parquet",
                          columns=["hadm_id", "admittime", "dischtime"])
    joined = cohort.merge(adm, on="hadm_id", how="left")
    window2h = pd.Timedelta(hours=2)
    cohort["boundary_flag"] = (
        ((joined.ecg_time - joined.admittime).abs() <= window2h)
        | ((joined.ecg_time - joined.dischtime).abs() <= window2h)
    ).fillna(False).to_numpy()

    ecgs = cohort[["study_id", "subject_id", "hadm_id", "ecg_time"]].copy()
    ecgs["hadm_id"] = ecgs["hadm_id"].astype("Int64")

    subjects = set(ecgs.subject_id)
    events = pd.read_parquet(
        LAB_EVENTS,
        columns=["subject_id", "hadm_id", "itemid", "charttime", "valuenum",
                 "ref_range_lower", "ref_range_upper", "flag"],
    )
    events = events[events.subject_id.isin(subjects) & events.charttime.notna()]
    events["flag_abnormal"] = (
        events["flag"].fillna("").astype(str).str.strip().str.lower() == "abnormal"
    ).astype("float64")
    events["hadm_id"] = events["hadm_id"].astype("Int64")
    log.info("lab events for cohort subjects: %d", len(events))

    ecg_time = cohort.sort_values("ecg_time", kind="mergesort")["ecg_time"].to_numpy()
    order = cohort.sort_values("ecg_time", kind="mergesort")["study_id"].to_numpy()
    reindex = pd.Series(np.arange(len(order)), index=order).reindex(cohort.study_id).to_numpy()

    out: dict[str, np.ndarray] = {}
    for lab in LABS:
        lab_events = events[events.itemid.isin(itemids[lab])]
        log.info("%s: %d events", lab, len(lab_events))
        cand_subject = nearest_events(ecgs, lab_events, ["subject_id"])
        cand_hadm = nearest_events(ecgs, lab_events, ["subject_id", "hadm_id"])
        for window in window_names:
            lower_h, upper_h = windows[window]
            primary = resolve_window(cand_subject, ecg_time, lower_h, upper_h)
            same_hadm = resolve_window(cand_hadm, ecg_time, lower_h, upper_h)
            out[f"lab_{lab}_{window}_label"] = primary["label"][reindex]
            out[f"lab_{lab}_{window}_signed_hours_from_ecg"] = primary["signed_hours"][reindex]
            out[f"lab_{lab}_{window}_abnormal_method"] = primary["method"][reindex]
            out[f"lab_{lab}_{window}_label_same_hadm"] = same_hadm["label"][reindex]
        del cand_subject, cand_hadm

    df = cohort[["study_id", "subject_id", "split", "link_tier", "sqi_tier", "cart_id",
                 "boundary_flag", "hadm_id", "ecg_time", "is_primary"]].copy()
    df["cart_id"] = df["cart_id"].astype("Int64").astype("string")
    df["hadm_id"] = df["hadm_id"].astype("Int64")
    for name, values in out.items():
        if name.endswith("_label") or name.endswith("_same_hadm"):
            df[name] = pd.Categorical(values, categories=CLASSES)
        elif name.endswith("_abnormal_method"):
            df[name] = pd.Categorical(values, categories=METHODS)
        else:
            df[name] = values
    del out
    df = df.sort_values("study_id", kind="mergesort").reset_index(drop=True)
    log.info("assembled table: %d rows x %d columns", len(df), len(df.columns))

    schema = build_schema(window_names)
    counts = bc.write_task_split_parquets(df, TASK, schema=schema)
    log.info("wrote splits: %s", counts)

    # --- validation (§9.2) ---------------------------------------------------
    primary = df[df.is_primary]
    coverage = {}
    distribution = {}
    for lab in LABS:
        col = f"lab_{lab}_pm24h_label"
        counts_lab = primary[col].value_counts()
        distribution[lab] = {
            cls: round(100 * float(counts_lab.get(cls, 0)) / max(len(primary), 1), 3)
            for cls in CLASSES
        }
        coverage[lab] = round(100 * float((primary[col] != "missing").mean()), 2)

    stats = {
        "n_rows_total": int(len(df)),
        "n_rows_primary_l3": int(len(primary)),
        "n_columns": int(len(df.columns)),
        "n_heads": len(LABS) * len(window_names),
        "splits_total": counts,
        "coverage_pm24h_pct_primary": coverage,
        "class_distribution_pm24h_primary_pct": distribution,
        "coverage_by_window_pct_primary": {
            window: {
                lab: round(
                    100 * float((primary[f"lab_{lab}_{window}_label"] != "missing").mean()), 2
                )
                for lab in LABS
            }
            for window in window_names
        },
        "same_hadm_coverage_pm24h_pct_primary": {
            lab: round(
                100 * float((primary[f"lab_{lab}_pm24h_label_same_hadm"] != "missing").mean()), 2
            )
            for lab in LABS
        },
        "abnormal_method_pm24h_primary": {
            lab: primary[f"lab_{lab}_pm24h_abnormal_method"].value_counts().to_dict()
            for lab in ("K", "troponin")
        },
    }
    stats.update(bc.split_summary(df))
    stats.update({f"primary_{k}": v for k, v in bc.split_summary(primary).items()})
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str))

    # The §4.A.3.2 step-5 gate was measured at P2.0 from label_availability;
    # re-assert it against the labels this builder actually produced.
    for lab, gate in (("Ca", 50.0), ("Mg", 50.0)):
        if coverage[lab] < gate:
            raise RuntimeError(
                f"{lab} pm24h coverage is {coverage[lab]} %, below the §4.A.3.2 step-5 gate of "
                f"{gate} % -- the 7-lab universe would have to downgrade to the 5-lab default"
            )
    if any(v == 0 for v in coverage.values()):
        raise RuntimeError(f"a lab has zero pm24h coverage: {coverage}")

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2, default=str), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# A3 -- lab abnormality prediction (7 labs x 5 windows)

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.A.3 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/03_build_A3_lab_abnormality.py`.

## Reading this table

| Analysis | Filter / columns |
| --- | --- |
| **Primary** | `is_primary` (`link_tier == 'L3'`), heads `lab_<lab>_pm24h_label` |
| L3 vs L3+L2 | drop the filter — the whole table |
| Window sweep (§4.A.3.8) | swap `pm24h` for `pre_24h` / `post_24h` / `pm6h` / `pm12h` |
| Same-hadm restriction | `lab_<lab>_<window>_label_same_hadm` |
| Per-SQI tier | `sqi_tier` |

35 heads = 7 labs x 5 windows, 5 classes each.

## Labels

Per (lab, window): the lab event nearest in time to the ECG inside the window,
classified by the §4.A.3.3 precedence. `..._signed_hours_from_ecg` is that
event's offset (negative = before the ECG), and `..._abnormal_method` records
which branch decided the label:

| method | meaning |
| --- | --- |
| `no_event` | no event in the window — label is `missing` |
| `null_value` | an event, but non-numeric `valuenum` — label is `missing` |
| `ref_range` | the row's own `ref_range_lower` / `ref_range_upper` decided it |
| `flag` | ref ranges said normal but the source `flag` said abnormal |

`locked_threshold`, the third value §4.A.3.5 anticipates, is never produced:
the rebuilt lab cache carries a reference range on 100 % of rows for every lab,
so no hard-coded threshold is needed. This matters most for troponin, whose
assay generations differ.

**`missing` is a real class**, never dropped (Plan A/B §5.5). Troponin and
lactate coverage is low by design, and that missingness is part of what the
task reports.

## Data source

`data/raw/ehr_cache/labevents_key_labs.parquet` (20,481,517 rows, 18 locked
itemids), built by `00b_rebuild_lab_cache.py`. The Phase 1 `labevents.parquet`
cannot be used: it dropped `ref_range_lower`, `ref_range_upper` and `flag`.

## Forbidden inputs

`machine_measurements`, `structured_features` (§4.A.3.4). Labs are EHR-derived,
so signal / image / text are all legitimate inputs.

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
```

### `scripts/phase2_tasks_benchmark_and_paper/04_build_A4_event_localization.py`

```python
"""Stage P2.1 script 04 -- A4: temporal / waveform event localization.

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/04_build_A4_event_localization.py [--dev]

Spec §4.A.4. Predict R-peak sample positions and QRS onset/offset spans inside
the 10-second Lead-II strip. Ground truth comes from
``data/processed/fiducials_lead2.parquet``, written by ``00_extract_fiducials.py``
-- run that first.

Cohort (§4.A.4.2). Primary is ``link_tier == 'L3'`` and
``sqi_tier in {high, medium}`` and usable ground truth; the sensitivity cohort is
the full clean cohort regardless of link tier. Both are in this one table, with
``is_primary`` marking the primary.

**No dense masks are materialised.** §4.A.4.5 lists ``r_peak_mask`` and
``qrs_mask`` as ``list<bool>`` of length 5000, but the §4.A.4.3 correction that
created this task's ground truth supersedes it: "the arrays are stored sparse
(peak positions), not as dense 5000-sample masks ... The dataloader expands to a
dense mask at batch time. Same information, no science change." Dense masks
would cost about 2.3 GB for the A4 cohort and 3.7 GB for the full clean cohort
against ~190 MB sparse. The expansion rule is fixed and recorded in the README
so every consumer builds the same mask: True within +/-5 samples of an R-peak
(the +/-10 ms tolerance at 500 Hz), and True inside any onset-offset span.

``qrs_onsets_lead2`` / ``qrs_offsets_lead2`` are aligned one-to-one with
``r_peaks_lead2`` and carry ``-1`` where delineation gave no usable boundary for
that beat, so a per-beat model never has to guess which onset belongs to which
peak.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402

STAGE = "P2.1"
SCRIPT = "04_build_A4_event_localization"
TASK = "A4_event_localization"

FIDUCIALS = bc.DATA_PROCESSED / "fiducials_lead2.parquet"
PRIMARY_SQI = ("high", "medium")
TOLERANCE_SAMPLES = 5      # +/-10 ms at 500 Hz (§4.A.4.3)
FS = 500
N_SAMPLES = 5000

SCHEMA = pa.schema([
    ("study_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("split", pa.string()),
    ("link_tier", pa.string()),
    ("sqi_tier", pa.string()),
    ("cart_id", pa.string()),
    ("r_peaks_lead2", pa.list_(pa.int32())),
    ("qrs_onsets_lead2", pa.list_(pa.int32())),
    ("qrs_offsets_lead2", pa.list_(pa.int32())),
    ("n_peaks", pa.int32()),
    ("n_qrs_spans", pa.int32()),
    ("fallback_used", pa.bool_()),
    ("delineate_ok", pa.bool_()),
    ("is_primary", pa.bool_()),
])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    bc.add_std_args(parser)
    args = parser.parse_args()
    bc.set_dev(args.dev)

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT + ("_dev" if args.dev else ""))
    if state.done and not args.force:
        log.info("already complete (%s rows) -- pass --force to rebuild", state.data.get("n_rows"))
        return 0
    state.reset()
    started = time.time()

    fiducials = FIDUCIALS.with_name("fiducials_lead2_dev.parquet") if args.dev else FIDUCIALS
    bc.preflight([fiducials])

    cohort = bc.load_clean_cohort(dev=args.dev)
    fid = pd.read_parquet(fiducials)
    log.info("cohort %d studies, fiducials %d rows", len(cohort), len(fid))

    df = cohort.merge(fid, on="study_id", how="inner")
    if len(df) != len(cohort):
        missing = len(cohort) - len(df)
        raise RuntimeError(
            f"{missing} clean-cohort studies have no fiducial row -- "
            f"re-run 00_extract_fiducials.py before building A4"
        )

    df["n_qrs_spans"] = df["qrs_onsets_lead2"].map(lambda a: int((np.asarray(a) >= 0).sum()))
    df["is_primary"] = (
        (df.link_tier == "L3")
        & df.sqi_tier.isin(PRIMARY_SQI)
        & ~df.fallback_used            # "ground-truth R-peaks exist" (§4.A.4.2)
    )
    df["cart_id"] = df["cart_id"].astype("Int64").astype("string")
    df = df.sort_values("study_id", kind="mergesort").reset_index(drop=True)

    counts = bc.write_task_split_parquets(df, TASK, schema=SCHEMA)
    log.info("wrote splits: %s", counts)

    primary = df[df.is_primary]
    spans = np.concatenate([
        (np.asarray(off)[np.asarray(off) >= 0] - np.asarray(on)[np.asarray(on) >= 0])
        for on, off in zip(primary.qrs_onsets_lead2.head(50000), primary.qrs_offsets_lead2.head(50000))
    ]) if len(primary) else np.array([0])

    stats = {
        "n_rows_total": int(len(df)),
        "n_rows_primary": int(len(primary)),
        "splits_total": counts,
        "n_fallback_used_total": int(df.fallback_used.sum()),
        "pct_fallback_used_total": round(100 * float(df.fallback_used.mean()), 3),
        "pct_delineate_ok_total": round(100 * float(df.delineate_ok.mean()), 3),
        "n_peaks_mean_primary": round(float(primary.n_peaks.mean()), 2),
        "n_peaks_median_primary": int(primary.n_peaks.median()),
        "n_qrs_spans_mean_primary": round(float(primary.n_qrs_spans.mean()), 2),
        "pct_beats_with_qrs_span_primary": round(
            100 * float(primary.n_qrs_spans.sum()) / max(int(primary.n_peaks.sum()), 1), 2
        ),
        "qrs_span_ms_median": round(float(np.median(spans)) * 1000.0 / FS, 2),
        "qrs_span_ms_p05": round(float(np.percentile(spans, 5)) * 1000.0 / FS, 2),
        "qrs_span_ms_p95": round(float(np.percentile(spans, 95)) * 1000.0 / FS, 2),
        "sqi_breakdown_primary": primary.sqi_tier.value_counts().to_dict(),
        "tolerance_samples": TOLERANCE_SAMPLES,
        "dense_masks_materialised": False,
    }
    stats.update(bc.split_summary(df))
    stats.update({f"primary_{k}": v for k, v in bc.split_summary(primary).items()})
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str))

    if stats["n_rows_primary"] == 0:
        raise RuntimeError("A4 primary cohort is empty")
    if not 40 <= stats["qrs_span_ms_median"] <= 140:
        raise RuntimeError(
            f"median QRS span is {stats['qrs_span_ms_median']} ms, outside anything "
            "physiological -- the delineation output is misaligned"
        )
    bad = int(primary.r_peaks_lead2.map(
        lambda a: bool(len(a)) and (min(a) < 0 or max(a) >= N_SAMPLES)
    ).sum())
    if bad:
        raise RuntimeError(f"{bad} primary rows carry an R-peak outside [0, {N_SAMPLES})")

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2, default=str), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# A4 -- temporal / waveform event localization (R-peaks + QRS bounds)

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.A.4 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/04_build_A4_event_localization.py`.

## Reading this table

| Analysis | Filter |
| --- | --- |
| **Primary** | `is_primary` — `link_tier == 'L3' and sqi_tier in ('high','medium') and not fallback_used` |
| Full-clean-cohort sensitivity | drop the filter — the whole table |
| Per-SQI tier | `sqi_tier` |

## Ground truth

`data/processed/fiducials_lead2.parquet`, from `00_extract_fiducials.py`, which
reuses the **corrected** Phase 1 detector path verbatim: `ecg_peaks` with
`method="neurokit"` on the uncleaned preprocessed Lead II, then `ecg_delineate`
with `method="dwt"`, `check=False`. The Pan-Tompkins bug fixed during the Phase 1
regen is not reintroduced.

`qrs_onsets_lead2[i]` and `qrs_offsets_lead2[i]` belong to `r_peaks_lead2[i]`.
A value of `-1` means delineation produced no usable boundary for that beat;
`n_qrs_spans` counts the beats that do have one.

## Masks are expanded at batch time, not stored

§4.A.4.5 lists dense `r_peak_mask` and `qrs_mask` columns; the §4.A.4.3
correction supersedes that and keeps the sparse form. Every consumer must expand
the same way:

```python
r_peak_mask = np.zeros(5000, dtype=bool)
for p in r_peaks_lead2:
    r_peak_mask[max(0, p - 5):min(5000, p + 6)] = True   # +/-10 ms at 500 Hz

qrs_mask = np.zeros(5000, dtype=bool)
for on, off in zip(qrs_onsets_lead2, qrs_offsets_lead2):
    if on >= 0 and off >= 0:
        qrs_mask[on:off + 1] = True
```

Evaluation tolerance is +/-10 ms = +/-5 samples for R-peaks and for each QRS
boundary (§4.A.4.3).

## The oracle baseline uses `method="neurokit"`

§4.A.4.7 calls the algorithmic baseline "NeuroKit2 Pan-Tompkins" and says its F1
is 1.0 by construction. Those two statements are only both true if the baseline
runs the **same** detector as the ground truth, which is NeuroKit's default
(`method="neurokit"`), not `method="pantompkins"`. The Phase 1 regen switched
away from `pantompkins` precisely because it was wrong. So:

- the **oracle** row of §4.A.4.7 is `method="neurokit"`, F1 = 1.0 by construction;
- `method="pantompkins"` may be reported as an **additional, non-oracle** row —
  it measures detector disagreement, which is interesting, but it is not the
  oracle and its F1 will not be 1.0.

## Forbidden inputs

Everything except the four signal kinds (§4.A.4.4): images (a rendered ECG shows
the QRS boundaries and could be pixel-traced), `report_text`,
`machine_measurements` and `structured_features` (all carry aggregate timings
derived from the same delineation).

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
```

### `scripts/phase2_tasks_benchmark_and_paper/05_build_A5_cross_modal_verification.py`

```python
"""Stage P2.1 script 05 -- A5: cross-modal verification + masked attribute prediction.

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/05_build_A5_cross_modal_verification.py [--dev]

Spec §4.A.5. Two heads on one tri-encoder:

1. **Verification** -- does this (signal, image, text) triple belong to one
   study? Rows come from ``_dataset_lib/verification_task.py``, shared with B4.
   Written to ``{train,val,test}.parquet``.
2. **Masked attribute** -- given signal + image, predict the binned HR / QRS /
   QTc that an attribute-masked report no longer states. Written to
   ``masked_attribute_{train,val,test}.parquet`` (§4.A.5.5).

------------------------------------------------------------------------------
DOCUMENTED DEVIATION -- the masked-attribute head masks CLAIMS, not NUMERALS
------------------------------------------------------------------------------
§4.A.5.3 says to build the masked text by replacing "numeric mentions of HR,
QRS, QT, QTc, axis, and intervals" with ``[MASK]``. **MIMIC-IV-ECG machine
reports contain no numeric measurements at all.** Measured over the 749,112
clean reports:

* 12.5 % contain any digit whatsoever;
* after removing lead names (``V1``-``V6``), ordinals (``1st degree``) and
  ratios (``2:1``), **0.51 %** contain a digit -- and every one of those is the
  boilerplate "Age not entered, assumed to be 50 years old for purpose of ECG
  interpretation". That is an age, not an ECG measurement.

Implemented literally, ``report_text_masked`` would be byte-identical to
``report_text`` for 99.5 % of studies, ``masked_positions`` would be empty, and
the "masked" head would be the unmasked head under another name -- while the
report still says "Sinus bradycardia" in plain words, making the HR head a
lookup rather than a prediction.

What these reports state instead is the **qualitative claim**: "Sinus
bradycardia", "Leftward axis", "Left bundle branch block", "Prolonged QT".
44.3 % of reports carry at least one such claim across the four attribute
families. Masking those is what §4.A.5.3 is actually asking for in this
vocabulary, and it is the same finding, in the same direction, as Round 6.3 --
which restricted B5 to swapping surface forms that are really present because
the numerics the spec assumed are not there either. The HR / QRS / axis surface
forms are reused verbatim from ``config/claim_dictionary_LOCKED.yaml`` so B5 and
A5 cannot drift apart; QT/QTc forms are added here because B5 has no QT family.

Numerals are masked too, on the same pass, so the rule is a superset of the
literal one and the boilerplate age cannot be used as a shortcut.

**Disclose in the supplementary.**

------------------------------------------------------------------------------
Open question 2 (anchor pool) dissolves rather than needing a decision. It asks
whether the anchor pool is random or stratified over the 5 negative types.
§4.A.5.2 makes the cohort *all* clean-cohort ECGs and §4.A.5.3 gives *every*
anchor all five negative types, so no anchor is ever sampled and there is
nothing to stratify. What is drawn is each negative's donor, and that is
deterministic per (anchor, negative type).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402
from _dataset_lib import measurement_task as mt  # noqa: E402
from _dataset_lib import verification_task as vt  # noqa: E402

STAGE = "P2.1"
SCRIPT = "05_build_A5_cross_modal_verification"
TASK = "A5_cross_modal_verification"

MASK_TOKEN = "[MASK]"

MASKED_SCHEMA = pa.schema([
    ("study_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("split", pa.string()),
    ("report_text_masked", pa.string()),
    ("hr_label", pa.string()),
    ("qrs_label", pa.string()),
    ("qtc_label", pa.string()),
    ("masked_positions", pa.list_(pa.int32())),
    ("n_masked_spans", pa.int32()),
    ("masked_families", pa.string()),
])

# QT / QTc forms. B5 has no QT family, so these are defined here; the HR, QRS
# and axis forms come from claim_dictionary_LOCKED.yaml instead of being
# retyped, so the two tasks cannot drift apart.
QT_FORMS = [
    r"prolonged q-?t(?:c)?(?: interval)?",
    r"long q-?t(?:c)?(?: syndrome| interval)?",
    r"short q-?t(?:c)?(?: interval)?",
    r"q-?t(?:c)? (?:interval )?(?:is )?prolong\w*",
    r"borderline prolonged q-?t(?:c)?",
    r"q-?t(?:c)? interval",
]
# Any numeral that is not a lead name, an ordinal or a ratio -- the literal
# §4.A.5.3 rule, kept so the masking is a strict superset of it.
NUMERIC_FORM = r"(?<![vV])(?<!\d:)\b\d+(?!:\d)(?!(?:st|nd|rd|th)\b)\b"


def load_claim_forms() -> dict[str, list[str]]:
    """HR / QRS / axis surface forms, straight from the B5 claim dictionary."""
    cfg = yaml.safe_load(
        (bc.CONFIG_DIR / "claim_dictionary_LOCKED.yaml").read_text(encoding="utf-8")
    )
    families: dict[str, list[str]] = {}
    for family, block in cfg["families"].items():
        if family == "PR":
            continue          # PR is an interval claim, not an HR/QRS/QTc bin
        # The dictionary stores STEMS ("bradycardi"), because B5 swaps a stem
        # and keeps the inflection. A5 must remove the whole word instead:
        # masking the stem alone leaves "Sinus [MASK]a", which advertises both
        # that something was removed and how long it was. \w* eats the
        # inflection so [MASK] stands in for a complete token.
        families[family] = [str(form["pattern"]) + r"\w*" for form in block["surface_forms"]]
    families["QT"] = QT_FORMS
    families["numeric"] = [NUMERIC_FORM]
    return families


def build_masker(families: dict[str, list[str]]) -> list[tuple[str, re.Pattern]]:
    """One compiled, case-insensitive pattern per family, longest-first.

    Longest-first inside a family stops "qt interval" from eating the first half
    of "prolonged qt interval" and leaving a fragment behind.
    """
    compiled = []
    for family, patterns in families.items():
        ordered = sorted(patterns, key=len, reverse=True)
        compiled.append((family, re.compile("|".join(f"(?:{p})" for p in ordered), re.IGNORECASE)))
    return compiled


def mask_report(text: str, masker: list[tuple[str, re.Pattern]]) -> tuple[str, list[int], str]:
    """Replace every attribute-bearing claim with ``[MASK]``.

    Returns the masked text, the character offsets of each ``[MASK]`` **in the
    masked text**, and the families that fired. Offsets point into the masked
    text because that is the string a model is given; ``report_text`` in the
    verification table still holds the original.
    """
    spans: list[tuple[int, int, str]] = []
    for family, pattern in masker:
        for match in pattern.finditer(text):
            spans.append((match.start(), match.end(), family))
    if not spans:
        return text, [], ""

    spans.sort(key=lambda s: (s[0], -s[1]))
    merged: list[tuple[int, int, set[str]]] = []
    for start, end, family in spans:
        if merged and start < merged[-1][1]:
            previous = merged[-1]
            merged[-1] = (previous[0], max(previous[1], end), previous[2] | {family})
        else:
            merged.append((start, end, {family}))

    pieces: list[str] = []
    positions: list[int] = []
    cursor = 0
    out_len = 0
    fired: set[str] = set()
    for start, end, fams in merged:
        pieces.append(text[cursor:start])
        out_len += start - cursor
        positions.append(out_len)
        pieces.append(MASK_TOKEN)
        out_len += len(MASK_TOKEN)
        cursor = end
        fired |= fams
    pieces.append(text[cursor:])
    return "".join(pieces), positions, ",".join(sorted(fired))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    bc.add_std_args(parser)
    args = parser.parse_args()
    bc.set_dev(args.dev)

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT + ("_dev" if args.dev else ""))
    if state.done and not args.force:
        log.info("already complete (%s rows) -- pass --force to rebuild", state.data.get("n_rows"))
        return 0
    state.reset()
    started = time.time()

    bc.preflight([bc.CONFIG_DIR / "claim_dictionary_LOCKED.yaml"])

    # --- head 1: verification ------------------------------------------------
    cohort = bc.load_clean_cohort(dev=args.dev)
    verification = vt.build_verification(dev=args.dev)
    vt.assert_no_cross_split_donor(verification, cohort)
    vt.assert_negatives_are_mismatched(verification, cohort)
    counts = bc.write_task_split_parquets(verification, TASK, schema=vt.SCHEMA)
    log.info("verification rows: %d, splits %s", len(verification), counts)

    # --- head 2: masked attribute -------------------------------------------
    masker = build_masker(load_claim_forms())
    labels = mt.measurement_table(dev=args.dev)
    text = bc.report_text_series(dev=args.dev)
    masked = labels[["study_id", "subject_id", "split", "hr_label", "qrs_label", "qtc_label"]].merge(
        text, on="study_id", how="inner"
    )
    log.info("masked-attribute rows (all three measurements valid): %d", len(masked))

    results = [mask_report(t, masker) for t in masked.report_text.tolist()]
    masked["report_text_masked"] = [r[0] for r in results]
    masked["masked_positions"] = [np.asarray(r[1], dtype="int32") for r in results]
    masked["n_masked_spans"] = np.asarray([len(r[1]) for r in results], dtype="int32")
    masked["masked_families"] = [r[2] for r in results]

    masked_counts = bc.write_task_split_parquets(
        masked, TASK, schema=MASKED_SCHEMA, prefix="masked_attribute_"
    )
    log.info("masked-attribute splits: %s", masked_counts)

    # --- validation (§9.2) ---------------------------------------------------
    changed = masked.report_text_masked.to_numpy() != masked.report_text.to_numpy()
    family_hits: dict[str, int] = {}
    for family in ("HR", "QRS", "axis", "QT", "numeric"):
        family_hits[family] = int(
            masked.masked_families.str.contains(rf"\b{family}\b", regex=True).sum()
        )

    stats = {
        "verification": vt.verification_stats(verification),
        "verification_splits": counts,
        "masked_attribute": {
            "n_rows": int(len(masked)),
            "splits": masked_counts,
            "n_reports_changed": int(changed.sum()),
            "pct_reports_changed": round(100 * float(changed.mean()), 3),
            "mean_masked_spans": round(float(masked.n_masked_spans.mean()), 3),
            "max_masked_spans": int(masked.n_masked_spans.max()),
            "reports_by_family": family_hits,
            "labels": mt.label_stats(masked),
        },
    }
    stats.update(bc.split_summary(verification))
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str)[:4000])

    if stats["verification"]["n_rows"] == 0:
        raise RuntimeError("A5 verification table is empty")
    balance = stats["verification"]["positive_rate_pct"]
    if not 26.0 <= balance <= 30.0:
        raise RuntimeError(
            f"positive rate is {balance} %, not the ~2-in-7 (28.6 %) the "
            "§4.A.5.3 construction gives -- rows were lost or duplicated"
        )
    if stats["masked_attribute"]["pct_reports_changed"] < 30.0:
        raise RuntimeError(
            f"only {stats['masked_attribute']['pct_reports_changed']} % of reports were masked; "
            "the measured claim-bearing share of the corpus is 44.3 % -- the vocabulary is wrong"
        )
    for row in masked.head(2000).itertuples():
        for pos in row.masked_positions:
            if row.report_text_masked[pos:pos + len(MASK_TOKEN)] != MASK_TOKEN:
                raise RuntimeError(f"masked_positions is misaligned on study {row.study_id}")

    examples = [
        {"study_id": int(r.study_id), "original": r.report_text[:160],
         "masked": r.report_text_masked[:160], "families": r.masked_families}
        for r in masked[changed].head(5).itertuples()
    ]
    stats["masked_attribute"]["examples"] = examples
    log.info("masking examples:\n%s", json.dumps(examples, indent=2))

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2, default=str), built_at=bc.utc_now_iso()
    ))
    state.finish(n_verification_rows=int(len(verification)), **stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# A5 -- cross-modal verification + masked attribute prediction

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.A.5 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/05_build_A5_cross_modal_verification.py`.

## Two tables

| File | Head | Row |
| --- | --- | --- |
| `{{train,val,test}}.parquet` | verification | one (signal, image, text) triple |
| `masked_attribute_{{train,val,test}}.parquet` | masked attribute | one study |

## Verification rows

Seven per anchor: 2 positives (clean and scan-like rendering of the anchor's own
image) and 5 negatives, one per `neg_type`. `signal_id` / `image_id` / `text_id`
name the study each modality is resolved from — always through
`read_modality()`, never by opening a container.

Two rules the split contract forces, both asserted at build time:

* **donors are drawn from the anchor's own split** — a train row pointing at a
  test subject would put test bytes into training;
* **every negative disagrees with its anchor at the subject level**, so
  `y_match = 0` is not a lie for a model that has learned patient identity.

Negatives all use `image_type == 'clean'` so the per-`neg_type` F1 table is not
confounded by rendering. The clean-vs-scanlike and Lead-II-vs-12-lead
comparisons are made by resolving a different modality kind for the same
`image_id` at load time.

`HARD_NEGATIVE_TEXT` needs a same-HR-bucket, different-subject donor in the same
split; the few anchors without one yield 6 rows instead of 7 (§4.A.5.3).

## Masked attribute — a documented deviation

§4.A.5.3 asks for numeric mentions of HR / QRS / QT / QTc / axis / intervals to
be replaced with `[MASK]`. **These reports have no numeric measurements.**
Measured across all 749,112: 12.5 % contain any digit, and only **0.51 %**
contain one that is not a lead name, an ordinal or a ratio — every one of those
being the boilerplate "Age not entered, assumed to be 50 years old".

Taken literally the rule masks nothing, `report_text_masked` equals
`report_text`, and the report still says "Sinus bradycardia" — so the HR head
becomes a lookup. This table therefore masks the **qualitative claims** that
carry the attribute in this vocabulary, which 44.3 % of reports contain, and
masks bare numerals as well so the rule stays a strict superset of the literal
one.

HR, QRS and axis surface forms are read from
`config/claim_dictionary_LOCKED.yaml`, so A5 and B5 cannot drift apart; QT/QTc
forms are defined in the builder because B5 has no QT family.

`masked_positions` holds the character offset of each `[MASK]` **in
`report_text_masked`**, and `masked_families` records which families fired.

**Disclosed in the supplementary.**

## Forbidden inputs

`machine_measurements`, `structured_features` (§4.A.5.4). `report_text_masked`
is allowed precisely because its attribute content has been removed.

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
```

### `scripts/phase2_tasks_benchmark_and_paper/06_build_A6_risk_stratification.py`

```python
"""Stage P2.1 script 06 -- A6: risk stratification (mortality + readmission, 30 d / 90 d).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/06_build_A6_risk_stratification.py [--dev]

Spec §4.A.6. Four binary heads. Index time is ``ecg_time``; no post-ECG feature
enters the table.

Mortality (§4.A.6.3)::

    death_time    = patients.dod  if not null else admissions.deathtime[hadm_id]
    mortality_30d = death_time is not null and 0 < death_time - ecg_time <= 30 d
    mortality_90d = same at 90 d

ED-only ECGs keep a mortality label -- ``patients.dod`` is observable whether or
not the patient was admitted -- but carry **null** readmission labels, per
§4.A.6.2 and Plan A/B §5.8.

Readmission (§4.A.6.3). The next admission is the earliest ``admittime``
strictly after this admission's ``dischtime`` for the same subject, a different
``hadm_id``, and "not just a transfer".

**Two readings §4.A.6.3 leaves to the builder, both recorded as data rather than
baked in silently:**

1. *"not just a transfer."* MIMIC-IV keeps intra-stay movement in the
   ``transfers`` table, where it creates no second ``hadm_id``, so the only
   candidates that are transfers rather than readmissions are hand-offs recorded
   as two admissions. This builder excludes a candidate whose
   ``admission_location`` starts with ``TRANSFER FROM`` **and** whose gap from
   the previous discharge is at most one hour -- contiguity is what makes it a
   hand-off; a transfer-in three days later is a genuine readmission. The
   candidate's ``admission_type`` and ``admission_location`` ship as provenance
   columns, so the "unplanned only" and "no transfer exclusion" variants are
   filters, not rebuilds.
2. *"Exclude rows where the censoring window cannot be observed."* §4.A.6.3
   assumes a global end-of-data cutoff. MIMIC-IV has none that is usable: every
   patient's dates are shifted into a private future window, so "how close is
   this discharge to the end of the data" is not answerable in shifted time.
   The tempting substitute -- call a row observable when the subject's own
   record extends past ``dischtime + horizon`` -- **conditions on the outcome**:
   it keeps the subjects who came back and drops the ones who did not. Measured
   on the dev sample, that lifted the 30 d rate from ~10 % to 29 %. This builder
   therefore uses the Phase 1 definition (eligible = the ECG sits inside an
   admission with a discharge time) and ships
   ``followup_days_after_discharge`` -- the subject's last recorded event minus
   this discharge -- as provenance, so a censoring-aware sensitivity analysis is
   a filter rather than a rebuild. The residual right-censoring is a stated
   limitation of the readmission heads.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402

STAGE = "P2.1"
SCRIPT = "06_build_A6_risk_stratification"
TASK = "A6_risk_stratification"

BOUNDARY_HOURS = 2
TRANSFER_GAP_HOURS = 1
ADMISSIONS_CSV = bc.DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "admissions.csv.gz"

SCHEMA = pa.schema([
    ("study_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("split", pa.string()),
    ("link_tier", pa.string()),
    ("sqi_tier", pa.string()),
    ("cart_id", pa.string()),
    ("boundary_flag", pa.bool_()),
    ("hadm_id", pa.int64()),
    ("ecg_time", pa.timestamp("ns")),
    ("mortality_30d", pa.bool_()),
    ("mortality_90d", pa.bool_()),
    ("mortality_observable", pa.bool_()),
    ("readmission_30d", pa.bool_()),          # null for ED-only
    ("readmission_90d", pa.bool_()),          # null for ED-only
    ("readmission_eligible", pa.bool_()),     # 30 d horizon
    ("readmission_eligible_90d", pa.bool_()),
    ("days_to_death", pa.float32()),
    ("days_to_readmission", pa.float32()),
    ("followup_days_after_discharge", pa.float32()),
    ("next_admission_type", pa.string()),
    ("next_admission_location", pa.string()),
    # --- Plan A/B §5.8 nested-baseline covariates. ALL strictly pre-ECG. -----
    # §5.8 requires six baseline tiers for A6 -- prevalence, demographics,
    # demographics+comorbidities, utilization, machine measurements, ECG -- and
    # Figure 5 is the nested curve across them. §7 names the failure condition
    # outright: "Only compared to random/prevalence baseline." None of these
    # columns existed, so the intermediate rungs could not be built at all.
    #
    # Every one of them is knowable at `ecg_time`: Plan §5.8's index-time rule is
    # "do not use any feature measured after ECG", and App. F lists "using future
    # covariates for risk" as a named failure mode. The builder enforces it by
    # construction -- prior counts read admissions DISCHARGED before the ECG,
    # prior diagnoses come from those admissions only, and the ED disposition is
    # taken from a stay that had already ended.
    #
    # These are BASELINE features, not model inputs: `task_input_policy.yaml`
    # still forbids them for every trained encoder, exactly as the machine
    # measurements are forbidden but permitted to the A6 Cox baseline.
    ("age_at_ecg", pa.float32()),
    ("sex_male", pa.bool_()),
    ("race", pa.string()),
    ("insurance", pa.string()),
    ("admission_type", pa.string()),          # this admission's, known at admit
    ("ed_disposition", pa.string()),          # last ED stay ENDING before the ECG
    ("n_prior_admissions", pa.int32()),
    ("n_prior_ecgs", pa.int32()),
    ("days_since_last_discharge", pa.float32()),
    ("prior_dx_atrial_fibrillation_flutter", pa.bool_()),
    ("prior_dx_heart_failure_narrow", pa.bool_()),
    ("prior_dx_acute_myocardial_infarction", pa.bool_()),
    ("prior_dx_conduction_disorder", pa.bool_()),
    ("prior_dx_ventricular_arrhythmia_or_arrest", pa.bool_()),
    ("is_primary", pa.bool_()),
])

# The comorbidity vocabulary is the LOCKED A1 map, not a new one: five cardiac
# groups, 175 codes, already validated against `d_icd_diagnoses` at Stage P2.0.
# Plan A/B §5.8 asks for "prior ICD/comorbidity flags before ECG only" without
# naming a vocabulary; reusing the locked one keeps A1 and A6 from drifting and
# means no code list is invented here.
PRIOR_DX_GROUPS = ("atrial_fibrillation_flutter", "heart_failure_narrow",
                   "acute_myocardial_infarction", "conduction_disorder",
                   "ventricular_arrhythmia_or_arrest")


def load_admissions() -> pd.DataFrame:
    """Admissions with the two columns the cached parquet dropped.

    ``data/raw/ehr_cache/admissions.parquet`` carries no ``admission_type`` or
    ``admission_location``, and both are needed to tell a hand-off from a
    readmission. The source CSV is 546 K rows -- cheap to read directly.
    """
    adm = pd.read_csv(
        ADMISSIONS_CSV,
        usecols=["subject_id", "hadm_id", "admittime", "dischtime", "deathtime",
                 "admission_type", "admission_location", "hospital_expire_flag",
                 # §5.8 demographics baseline; the cached parquet drops both.
                 "race", "insurance"],
        parse_dates=["admittime", "dischtime", "deathtime"],
        compression="gzip",
    )
    return adm.sort_values(["subject_id", "admittime"], kind="mergesort").reset_index(drop=True)


def next_admission_table(adm: pd.DataFrame) -> pd.DataFrame:
    """For every hadm_id, the first *non-transfer* later admission of that subject.

    Walks each subject's admissions in time order and, for each one, scans
    forward past any contiguous transfer hand-off to the first candidate whose
    ``admittime`` is strictly after this row's ``dischtime``.
    """
    records: list[dict] = []
    gap = pd.Timedelta(hours=TRANSFER_GAP_HOURS)
    for _, group in adm.groupby("subject_id", sort=False):
        hadm = group["hadm_id"].to_numpy()
        admit = group["admittime"].to_numpy()
        disch = group["dischtime"].to_numpy()
        atype = group["admission_type"].to_numpy()
        aloc = group["admission_location"].astype(str).to_numpy()
        n = len(group)
        for i in range(n):
            if pd.isna(disch[i]):
                continue
            discharge = pd.Timestamp(disch[i])
            for j in range(i + 1, n):
                candidate = pd.Timestamp(admit[j])
                if pd.isna(candidate) or candidate <= discharge:
                    continue
                is_transfer = (
                    aloc[j].upper().startswith("TRANSFER FROM")
                    and (candidate - discharge) <= gap
                )
                if is_transfer:
                    continue                      # a hand-off, not a readmission
                records.append({
                    "hadm_id": int(hadm[i]),
                    "next_admittime": candidate,
                    "next_admission_type": None if pd.isna(atype[j]) else str(atype[j]),
                    "next_admission_location": aloc[j],
                })
                break
    return pd.DataFrame(records)


def prior_ecg_counts(cohort: pd.DataFrame, all_ecgs: pd.DataFrame) -> pd.Series:
    """How many of the subject's ECGs precede this one, over the WHOLE index.

    Counted against every clean ECG the subject has, not just the L3/L2 ones in
    the A6 cohort. Plan A/B §5.8 wants prior ECG count as a utilization proxy --
    "controls for sick-patient ECG frequency" -- and a patient's unlinked
    outpatient ECGs are part of that frequency. Restricting the count to the A6
    cohort would make the covariate a function of linkage rather than of care.
    """
    pool = all_ecgs[all_ecgs.subject_id.isin(set(cohort.subject_id))][
        ["study_id", "subject_id", "ecg_time"]].copy()
    pool = pool.sort_values(["subject_id", "ecg_time", "study_id"], kind="mergesort")
    pool["n_prior"] = pool.groupby("subject_id").cumcount().astype("int32")
    return cohort.study_id.map(pool.set_index("study_id")["n_prior"])


def prior_history(cohort: pd.DataFrame, adm: pd.DataFrame) -> pd.DataFrame:
    """Per-ECG utilisation and comorbidity counts, using only PRE-ECG records.

    Plan A/B §5.8's utilization tier ("prior admissions, prior ECG count,
    current admission type") and its comorbidity tier ("prior ICD ... before ECG
    only"). App. F's "using future covariates for risk" is the failure mode this
    guards against, so the cut is explicit and one-sided everywhere:

    * an admission counts only if its **discharge** precedes the ECG -- an
      admission still in progress is the ECG's own encounter, not history;
    * a prior ECG counts only if its ``ecg_time`` is strictly earlier;
    * a prior diagnosis is read from those already-discharged admissions only,
      because ICD codes are assigned at discharge and the current admission's
      codes describe the very episode being predicted from.

    Returns one row per cohort study.
    """
    out = pd.DataFrame({"study_id": cohort.study_id.to_numpy(),
                        "subject_id": cohort.subject_id.to_numpy(),
                        "ecg_time": cohort.ecg_time.to_numpy()})

    discharged = adm[adm.dischtime.notna()][["subject_id", "hadm_id", "dischtime"]]
    pairs = out[["study_id", "subject_id", "ecg_time"]].merge(
        discharged, on="subject_id", how="left")
    before = pairs[pairs.dischtime < pairs.ecg_time]

    counts = before.groupby("study_id").size()
    out["n_prior_admissions"] = out.study_id.map(counts).fillna(0).astype("int32")
    last_discharge = before.groupby("study_id")["dischtime"].max()
    out["days_since_last_discharge"] = (
        (out.ecg_time - out.study_id.map(last_discharge)).dt.total_seconds() / 86400.0
    ).astype("float32")

    # Prior diagnoses, from the already-discharged admissions only. The matcher
    # is A1's, imported rather than copied: two implementations of "does this
    # ICD code belong to this group" would eventually disagree, and then A1's
    # label and A6's comorbidity flag would mean different things.
    a1 = _import_a1()
    groups = a1.load_label_map()
    dx = pd.read_parquet(bc.EHR_CACHE / "diagnoses_icd.parquet",
                         columns=["subject_id", "hadm_id", "icd_code", "icd_version"])
    dx = dx[dx.subject_id.isin(set(out.subject_id))].copy()
    dx["icd_code"] = dx["icd_code"].astype(str).str.strip()

    distinct = dx[["icd_code", "icd_version"]].drop_duplicates()
    flags = a1.code_group_table(distinct, groups)
    prior_dx = (before[["study_id", "hadm_id"]]
                .merge(dx[["hadm_id", "icd_code", "icd_version"]], on="hadm_id", how="inner")
                .merge(flags, on=["icd_code", "icd_version"], how="left"))
    for group in PRIOR_DX_GROUPS:
        hits = set(prior_dx.loc[prior_dx[group].fillna(False), "study_id"])
        out[f"prior_dx_{group}"] = out.study_id.isin(hits)
    return out.drop(columns=["subject_id", "ecg_time"])


def _import_a1():
    """Load `01_build_A1_ecg_diagnosis.py` as a module (its name starts with a digit)."""
    import importlib.util

    path = Path(__file__).resolve().parent / "01_build_A1_ecg_diagnosis.py"
    spec = importlib.util.spec_from_file_location("_a1_builder", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ed_disposition_before_ecg(cohort: pd.DataFrame) -> pd.Series:
    """Disposition of the last ED stay that had ENDED before the ECG.

    Plan A/B §5.8: "ED disposition if before ECG". A stay still open at
    ``ecg_time`` has no disposition yet, and the disposition of the stay the ECG
    was taken during would be a future covariate -- so both are excluded by the
    strict ``outtime < ecg_time`` cut.
    """
    ed = pd.read_parquet(bc.EHR_CACHE / "edstays.parquet",
                         columns=["subject_id", "outtime", "disposition"])
    ed["outtime"] = pd.to_datetime(ed["outtime"], errors="coerce")
    ed = ed[ed.outtime.notna() & ed.subject_id.isin(set(cohort.subject_id))]

    pairs = cohort[["study_id", "subject_id", "ecg_time"]].merge(
        ed, on="subject_id", how="left")
    pairs = pairs[pairs.outtime < pairs.ecg_time]
    latest = pairs.sort_values("outtime", kind="mergesort").groupby("study_id").last()
    return cohort.study_id.map(latest["disposition"]).astype("string")


def last_observed_by_subject(adm: pd.DataFrame, patients: pd.DataFrame) -> pd.Series:
    """Latest timestamp at which the record still speaks for each subject.

    Used only to decide observability, never to make a label. MIMIC-IV has no
    global end-of-data marker, so the honest proxy is the subject's own last
    recorded event.
    """
    last_adm = adm.groupby("subject_id")[["admittime", "dischtime"]].max().max(axis=1)
    dod = patients.set_index("subject_id")["dod"]
    return pd.concat([last_adm, dod], axis=1).max(axis=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    bc.add_std_args(parser)
    args = parser.parse_args()
    bc.set_dev(args.dev)

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT + ("_dev" if args.dev else ""))
    if state.done and not args.force:
        log.info("already complete (%s rows) -- pass --force to rebuild", state.data.get("n_rows"))
        return 0
    state.reset()
    started = time.time()

    bc.preflight([ADMISSIONS_CSV, bc.EHR_CACHE / "patients.parquet"])

    cohort = bc.load_clean_cohort(dev=args.dev)
    cohort = cohort[cohort.link_tier.isin(["L3", "L2"])].copy()
    log.info("L3+L2 clean cohort: %d studies", len(cohort))

    adm = load_admissions()
    patients = pd.read_parquet(bc.EHR_CACHE / "patients.parquet", columns=["subject_id", "dod"])
    patients["dod"] = pd.to_datetime(patients["dod"], errors="coerce")

    subjects = set(cohort.subject_id)
    adm_sub = adm[adm.subject_id.isin(subjects)].copy()
    log.info("admissions for cohort subjects: %d", len(adm_sub))

    nxt = next_admission_table(adm_sub)
    log.info("hadm_ids with a non-transfer next admission: %d", len(nxt))

    df = cohort.merge(
        adm[["hadm_id", "admittime", "dischtime", "deathtime"]], on="hadm_id", how="left"
    ).merge(patients, on="subject_id", how="left")
    if len(nxt):
        df = df.merge(nxt, on="hadm_id", how="left")
    else:
        for col in ("next_admittime", "next_admission_type", "next_admission_location"):
            df[col] = pd.NaT if col == "next_admittime" else None

    # --- boundary flag -------------------------------------------------------
    window = pd.Timedelta(hours=BOUNDARY_HOURS)
    df["boundary_flag"] = (
        ((df.ecg_time - df.admittime).abs() <= window)
        | ((df.ecg_time - df.dischtime).abs() <= window)
    ).fillna(False)

    # --- mortality (§4.A.6.3) -----------------------------------------------
    death_time = df["dod"].where(df["dod"].notna(), df["deathtime"])
    delta_death = death_time - df["ecg_time"]
    df["days_to_death"] = (delta_death.dt.total_seconds() / 86400.0).astype("float32")
    after_ecg = delta_death > pd.Timedelta(0)
    df["mortality_30d"] = (after_ecg & (delta_death <= pd.Timedelta(days=30))).fillna(False)
    df["mortality_90d"] = (after_ecg & (delta_death <= pd.Timedelta(days=90))).fillna(False)
    df["mortality_observable"] = df["mortality_observable"].fillna(False).astype(bool)

    # --- readmission (§4.A.6.3) ---------------------------------------------
    # "For an ECG during an admission with hadm_id" -- ED-only ECGs get null,
    # never False, so no head can silently score them as negatives.
    has_admission = df["hadm_id"].notna() & df["dischtime"].notna()
    gap_to_next = df["next_admittime"] - df["dischtime"]
    df["days_to_readmission"] = (gap_to_next.dt.total_seconds() / 86400.0).astype("float32")

    # Eligibility is "this ECG sits inside an admission we can be readmitted
    # from", and NOTHING else -- deliberately, see the README. Deriving it from
    # the subject's own later admissions instead conditions on the outcome: it
    # keeps exactly the subjects who came back and drops the ones who did not,
    # which was measured on the dev sample to inflate the 30 d rate from ~10 %
    # to 29 %. §4.A.6.3's "end-of-data cutoff" is not observable in MIMIC-IV,
    # whose dates are shifted per patient, so the residual right-censoring is
    # reported as a limitation rather than silently "corrected".
    df["readmission_eligible"] = has_admission.fillna(False)
    df["readmission_eligible_90d"] = has_admission.fillna(False)

    last_seen = last_observed_by_subject(adm, patients)
    df["followup_days_after_discharge"] = (
        (df["subject_id"].map(last_seen) - df["dischtime"]).dt.total_seconds() / 86400.0
    ).astype("float32")

    for horizon in (30, 90):
        positive = (gap_to_next.notna() & (gap_to_next <= pd.Timedelta(days=horizon))).fillna(False)
        df[f"readmission_{horizon}d"] = positive.where(has_admission, other=pd.NA).astype("boolean")

    # --- Plan A/B §5.8 nested-baseline covariates ---------------------------
    # Age at the ECG, not anchor age: MIMIC-IV shifts each patient's dates into
    # a private window, but the OFFSET from `anchor_year` is preserved, so
    # `anchor_age + (ecg year - anchor_year)` is valid within a patient even
    # though calendar years are not comparable across patients (§2.3 caveat).
    demo = pd.read_parquet(bc.EHR_CACHE / "patients.parquet",
                           columns=["subject_id", "gender", "anchor_age", "anchor_year"])
    df = df.merge(demo, on="subject_id", how="left")
    df["age_at_ecg"] = (
        df["anchor_age"] + (df["ecg_time"].dt.year - df["anchor_year"])
    ).astype("float32")
    df["sex_male"] = (df["gender"].astype(str).str.upper() == "M")

    df = df.merge(adm[["hadm_id", "admission_type", "race", "insurance"]],
                  on="hadm_id", how="left")
    df["ed_disposition"] = ed_disposition_before_ecg(df)
    df = df.merge(prior_history(df, adm), on="study_id", how="left")
    df["n_prior_ecgs"] = prior_ecg_counts(df, bc.load_clean_cohort(dev=args.dev))
    for group in PRIOR_DX_GROUPS:
        df[f"prior_dx_{group}"] = df[f"prior_dx_{group}"].fillna(False).astype(bool)
    df["n_prior_admissions"] = df["n_prior_admissions"].fillna(0).astype("int32")
    df["n_prior_ecgs"] = df["n_prior_ecgs"].fillna(0).astype("int32")
    for column in ("race", "insurance", "admission_type", "ed_disposition"):
        df[column] = df[column].astype("string")

    # The one thing that must not slip: every covariate above is knowable at
    # `ecg_time` (Plan §5.8 index-time rule, App. F "using future covariates").
    # Assert the two that are computed from timestamps rather than fixed facts.
    lag = df["days_since_last_discharge"].dropna()
    if len(lag) and float(lag.min()) < 0:
        raise RuntimeError(
            f"{int((lag < 0).sum())} rows have a 'last discharge' AFTER the ECG -- "
            "the utilization covariates would be future information")
    if int((df["n_prior_ecgs"] < 0).sum()):
        raise RuntimeError("negative prior-ECG count")

    df["is_primary"] = df.link_tier == "L3"
    df["cart_id"] = df["cart_id"].astype("Int64").astype("string")
    df["hadm_id"] = df["hadm_id"].astype("Int64")
    df["next_admission_type"] = df["next_admission_type"].astype("string")
    df["next_admission_location"] = df["next_admission_location"].astype("string")
    df = df.sort_values("study_id", kind="mergesort").reset_index(drop=True)

    counts = bc.write_task_split_parquets(df, TASK, schema=SCHEMA)
    log.info("wrote splits: %s", counts)

    primary = df[df.is_primary]
    def rate(series: pd.Series) -> float:
        clean = series.dropna()
        return round(100 * float(clean.mean()), 4) if len(clean) else 0.0

    stats = {
        "n_rows_total": int(len(df)),
        "n_rows_primary_l3": int(len(primary)),
        "splits_total": counts,
        "n_mortality_observable_primary": int(primary.mortality_observable.sum()),
        "n_readmission_eligible_primary": int(primary.readmission_eligible.sum()),
        "n_followup_ge_30d_primary": int((primary.followup_days_after_discharge >= 30).sum()),
        "n_followup_ge_90d_primary": int((primary.followup_days_after_discharge >= 90).sum()),
        "prevalence_censoring_aware_pct": {
            "readmission_30d": rate(
                primary.loc[primary.followup_days_after_discharge >= 30, "readmission_30d"]),
            "readmission_90d": rate(
                primary.loc[primary.followup_days_after_discharge >= 90, "readmission_90d"]),
        },
        "n_ed_only_null_readmission": int(primary.readmission_30d.isna().sum()),
        "prevalence_primary_pct": {
            "mortality_30d": rate(primary.mortality_30d),
            "mortality_90d": rate(primary.mortality_90d),
            "readmission_30d": rate(primary.readmission_30d),
            "readmission_90d": rate(primary.readmission_90d),
        },
        "prevalence_primary_by_split_pct": {
            split: {
                head: rate(primary[primary.split == split][head])
                for head in ("mortality_30d", "mortality_90d", "readmission_30d", "readmission_90d")
            }
            for split in bc.SPLITS
        },
        "boundary_flag_pct_primary": round(100 * float(primary.boundary_flag.mean()), 3),
        "days_to_death_median_positive": round(
            float(primary.loc[primary.mortality_90d, "days_to_death"].median()), 2
        ) if int(primary.mortality_90d.sum()) else None,
        "days_to_readmission_median": round(
            float(primary["days_to_readmission"].median()), 2
        ) if primary["days_to_readmission"].notna().any() else None,
        "next_admission_type_top": primary["next_admission_type"].value_counts().head(6).to_dict(),
    }
    stats.update(bc.split_summary(df))
    stats.update({f"primary_{k}": v for k, v in bc.split_summary(primary).items()})
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str))

    if stats["n_rows_primary_l3"] == 0:
        raise RuntimeError("A6 primary cohort is empty")
    # A row that is not eligible must not be labelled at all (§4.A.6.3).
    leaked = int((~df.readmission_eligible & df.readmission_30d.notna()).sum())
    if leaked:
        raise RuntimeError(f"{leaked} rows carry a 30 d readmission label without being eligible")

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2, default=str), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# A6 -- risk stratification (mortality + readmission at 30 d and 90 d)

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.A.6 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/06_build_A6_risk_stratification.py`.

## Reading this table

| Analysis | Filter |
| --- | --- |
| **Primary** | `is_primary` — `link_tier == 'L3'` |
| L3 vs L3+L2 | drop the filter — the whole table |
| Mortality heads | require `mortality_observable` for the censoring-aware run |
| Readmission (both horizons) | `readmission_eligible`; rows with `readmission_30d is null` are ED-only |
| Censoring-aware readmission | add `followup_days_after_discharge >= 30` (or 90) |
| Boundary excluded | `not boundary_flag` |
| Unplanned readmission only | `next_admission_type not in ('ELECTIVE','SURGICAL SAME DAY ADMISSION')` |

Index time is `ecg_time`. Nothing in this table is measured after the ECG except
the outcome itself and its provenance (`days_to_death`, `days_to_readmission`),
which are labels, not features.

## Censoring

`readmission_30d` / `readmission_90d` are **nullable**, and are null exactly
when the ECG is ED-only — there is no admission to be readmitted from, so the
question does not apply. They are never null-by-inference.

§4.A.6.3 also asks to exclude rows whose censoring window cannot be observed,
"e.g., ECG too recent to the end-of-data cutoff". **MIMIC-IV has no usable
cutoff**: dates are shifted per patient, so proximity to the end of data is not
observable in the timeline the table is in. The obvious substitute — declare a
row observable when the subject's own record runs past `dischtime + horizon` —
conditions on the outcome, because a subject's record runs on precisely when
they were admitted again. Measured on the dev sample it moved the 30 d rate
from ~10 % to 29 %.

So this table uses the Phase 1 definition (an admission with a discharge time)
and carries `followup_days_after_discharge` as provenance. A censoring-aware
sensitivity is `followup_days_after_discharge >= horizon`, available without a
rebuild. The residual right-censoring is a stated limitation of the readmission
heads, not a silently corrected one.

## Transfers

A candidate next admission is treated as an intra-episode hand-off, and skipped,
when its `admission_location` starts with `TRANSFER FROM` **and** it begins
within one hour of the previous discharge. `next_admission_type` and
`next_admission_location` are kept so this choice can be audited or reversed
without rebuilding.

## Forbidden inputs

`machine_measurements`, `structured_features` (§4.A.6.4) — forbidden as model
input, permitted inside the algorithmic Cox baseline only (§4.A.6.7).

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
```

### `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/build_common.py`

```python
"""Shared plumbing for the Stage P2.1 / P2.2 task builders.

Every builder in ``scripts/phase2_tasks_benchmark_and_paper/`` imports from here
so the thirteen scripts share one cohort join, one resume convention, one
logging transport and one output writer.

What this module guarantees (spec §4.C, §8.5, §8.6, progress-doc traps 4/5/8):

* **The split is never re-derived.** :func:`load_clean_cohort` joins
  ``splits_subject_level.parquet`` on ``subject_id`` and asserts the result
  agrees with the split column already carried by the Phase 1 index.
* **Machine measurements are masked.** :func:`machine_measurements` applies the
  ``29999`` sentinel rule and the locked plausible ranges; the useless
  ``*_missing`` flag columns are never read.
* **Long runs resume.** :class:`StageState` plus :func:`run_chunked` checkpoint
  to part parquets after every chunk, so a power cut costs at most one chunk.
* **Modalities resolve through** :mod:`_dataset_lib.modality` only.

Run any builder with ``./ecg_env/Scripts/python.exe``. Never the system Python.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# --- repo layout -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
DATA_RAW = PROJECT_ROOT / "data" / "raw"
EHR_CACHE = DATA_RAW / "ehr_cache"
CONFIG_DIR = PROJECT_ROOT / "config"
TASKS_DIR = DATA_PROCESSED / "tasks"
STAGE_REPORTS = PROJECT_ROOT / "outputs" / "stage_reports"
PARTS_ROOT = DATA_PROCESSED / "_p2_parts"
DEV_SAMPLE = DATA_PROCESSED / "dev_sample" / "dev_sample_studies.parquet"

# --- resource policy (Phase 1 §6.1) ------------------------------------------
MAX_WORKERS = max(1, math.floor((os.cpu_count() or 1) * 0.75))
CHUNK_STUDIES = 20_000          # part-parquet granularity for the heavy passes
BATCH_SIZE = 32                 # ProcessPoolExecutor chunksize (Phase 1 §6.1)

MISSING_SENTINEL = 29999        # trap 8 / spec §12.8.2
SPLITS = ("train", "val", "test")

# --- dev-mode output isolation ------------------------------------------------
# A --dev smoke test must never write where the full-scale run writes. Without
# this, a two-minute sanity check silently replaces a task's real parquets with
# 5,000 dev-sample rows, and nothing downstream can tell. set_dev(True)
# redirects every task output under data/processed/tasks/_dev/.
_DEV_MODE = False


def set_dev(dev: bool) -> None:
    """Route task outputs to the dev tree. Call once, right after arg parsing."""
    global _DEV_MODE
    _DEV_MODE = bool(dev)


def tasks_root() -> Path:
    return TASKS_DIR / "_dev" if _DEV_MODE else TASKS_DIR


def task_dir(task_key: str) -> Path:
    path = tasks_root() / task_key
    path.mkdir(parents=True, exist_ok=True)
    return path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_replace(tmp: Path, final: Path, attempts: int = 12) -> None:
    """``os.replace`` with a retry ladder.

    On Windows a just-written file is routinely held for a few hundred
    milliseconds by the AV scanner or the search indexer, and ``os.replace``
    then fails with ``PermissionError: [WinError 5]``. Losing a nine-hour run's
    final state write to that is not acceptable, so retry before giving up.
    """
    delay = 0.1
    for attempt in range(attempts):
        try:
            os.replace(tmp, final)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 5.0)


# -----------------------------------------------------------------------------
# logging -- Transport A, per-PID worker files (Phase 1 §8.3)
# -----------------------------------------------------------------------------
_LOG_FMT = "%(asctime)s %(levelname)-7s pid=%(process)-6d %(name)s | %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(script_name: str, *, stage: str) -> logging.Logger:
    """Main-process logger writing to console *and* ``stage_<stage>_<script>.log``."""
    STAGE_REPORTS.mkdir(parents=True, exist_ok=True)
    log_path = STAGE_REPORTS / f"stage_{stage}_{script_name}.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    fmt = logging.Formatter(_LOG_FMT, _LOG_DATEFMT)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    log = logging.getLogger("main")
    log.info("log file: %s", log_path)
    return log


def worker_log_init(script_name: str, stage: str) -> None:
    """Pool initializer: redirect this worker's fd 1/2 into its own PID log.

    Workers never write to the parent's stdout/stderr (Phase 1 §8.2) -- that is
    what garbles a tqdm bar.
    """
    run_dir = STAGE_REPORTS / f"stage_{stage}_run" / script_name
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"worker_{os.getpid()}.log"
    handle = open(path, "a", buffering=1, encoding="utf-8")
    os.dup2(handle.fileno(), 1)
    os.dup2(handle.fileno(), 2)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for existing in list(root.handlers):
        root.removeHandler(existing)
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(_LOG_FMT, _LOG_DATEFMT))
    root.addHandler(file_handler)


# -----------------------------------------------------------------------------
# resume state
# -----------------------------------------------------------------------------
class StageState:
    """Small JSON state file, written atomically after every checkpoint.

    Mirrors the Phase 1 convention (``outputs/stage_reports/stage_<n>_state.json``)
    with one file per script, because Stage P2.1 has seven scripts where Phase 1
    stages had one. ``state["done"]`` is the idempotency flag: a completed script
    re-run is a no-op unless ``--force`` is passed.
    """

    def __init__(self, stage: str, script_name: str) -> None:
        STAGE_REPORTS.mkdir(parents=True, exist_ok=True)
        self.path = STAGE_REPORTS / f"stage_{stage}_{script_name}_state.json"
        self.data: dict[str, Any] = {
            "stage": stage,
            "script": script_name,
            "done": False,
            "started_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }
        if self.path.exists():
            try:
                self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                # The write is atomic (tmp + os.replace), so a power cut cannot
                # corrupt this file. A corrupt file means something else wrote
                # it -- start clean rather than guess.
                pass

    @property
    def done(self) -> bool:
        return bool(self.data.get("done"))

    def update(self, **kwargs: Any) -> "StageState":
        self.data.update(kwargs)
        self.data["updated_at"] = utc_now_iso()
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2, default=str), encoding="utf-8")
        atomic_replace(tmp, self.path)
        return self

    def finish(self, **kwargs: Any) -> "StageState":
        return self.update(done=True, finished_at=utc_now_iso(), **kwargs)

    def reset(self) -> "StageState":
        self.data = {
            "stage": self.data["stage"],
            "script": self.data["script"],
            "done": False,
            "started_at": utc_now_iso(),
        }
        return self.update()


def preflight(paths: Sequence[Path], *, need_free_gb: float = 2.0) -> None:
    """Fail before doing work, not after: inputs present, disk and RAM headroom."""
    import psutil

    missing = [str(p) for p in paths if not Path(p).exists()]
    if missing:
        raise FileNotFoundError(f"missing required input(s): {missing}")
    free_gb = shutil.disk_usage(str(DATA_PROCESSED.anchor)).free / 1024**3
    if free_gb < need_free_gb:
        raise RuntimeError(
            f"only {free_gb:.1f} GB free on {DATA_PROCESSED.anchor}, need {need_free_gb}"
        )
    avail_gb = psutil.virtual_memory().available / 1024**3
    logging.getLogger("main").info(
        "preflight OK: %d inputs present, %.1f GB free disk, %.1f GB free RAM, MAX_WORKERS=%d",
        len(paths), free_gb, avail_gb, MAX_WORKERS,
    )


# -----------------------------------------------------------------------------
# the cohort join -- one definition, thirteen callers
# -----------------------------------------------------------------------------
_COHORT_CACHE: dict[tuple[bool, bool], pd.DataFrame] = {}


def load_clean_cohort(dev: bool = False, *, with_text: bool = False) -> pd.DataFrame:
    """The Phase 1 clean cohort with every column a builder filters on.

    Columns: ``study_id, subject_id, split, link_tier, link_type, source,
    hadm_id, stay_id, ecg_time, cart_id, sqi_tier, decode_ok, length_ok,
    text_ok, image_clean_ok, image_scanlike_ok, icd_available,
    mortality_observable, readmission_eligible, hr_bucket`` (+ ``report_text``
    when ``with_text``).

    ``split`` comes from ``splits_subject_level.parquet`` and nothing else
    (§4.C invariant 1, trap 4). The Phase 1 index carries its own copy; this
    function asserts the two agree rather than trusting either alone.
    """
    key = (dev, with_text)
    cached = _COHORT_CACHE.get(key)
    if cached is not None:
        return cached.copy()

    meta_cols = ["study_id", "subject_id", "split", "link_tier", "cart_id", "hr_bucket"]
    if with_text:
        meta_cols.append("T_machine")
    meta = pd.read_parquet(
        DATA_PROCESSED / "index" / "ecg_metadata_clean_with_measurements.parquet",
        columns=meta_cols,
    ).rename(columns={"split": "_split_index", "T_machine": "report_text"})

    qc = pd.read_parquet(
        DATA_PROCESSED / "waveform_qc.parquet",
        columns=["study_id", "decode_ok", "length_ok", "sqi_tier", "text_ok",
                 "image_clean_ok", "image_scanlike_ok"],
    )
    avail = pd.read_parquet(
        DATA_PROCESSED / "linkage" / "label_availability.parquet",
        columns=["study_id", "ecg_time", "link_type", "source", "hadm_id", "stay_id",
                 "icd_available", "mortality_observable", "readmission_eligible"],
    )
    splits = pd.read_parquet(
        DATA_PROCESSED / "splits_subject_level.parquet", columns=["subject_id", "split"]
    )

    df = meta.merge(qc, on="study_id", how="left").merge(avail, on="study_id", how="left")
    df = df.merge(splits, on="subject_id", how="left", validate="many_to_one")

    if df["split"].isna().any():
        raise RuntimeError(
            f"{int(df['split'].isna().sum())} studies have no subject in "
            "splits_subject_level.parquet -- the cohort is not a subset of the frozen split"
        )
    mismatch = int((df["split"] != df["_split_index"]).sum())
    if mismatch:
        raise RuntimeError(
            f"{mismatch} studies disagree between splits_subject_level.parquet and the "
            "split column cached in the Phase 1 index. The frozen split is authoritative; "
            "investigate before building any task."
        )
    df = df.drop(columns=["_split_index"])

    # The clean index is already post-QC; assert rather than silently re-filter.
    if not (df["decode_ok"].fillna(False).all() and df["length_ok"].fillna(False).all()):
        raise RuntimeError("ecg_metadata_clean_with_measurements contains decode/length failures")

    if dev:
        keep = set(pd.read_parquet(DEV_SAMPLE, columns=["study_id"]).study_id)
        df = df[df.study_id.isin(keep)]

    df = df.sort_values("study_id", kind="mergesort").reset_index(drop=True)
    _COHORT_CACHE[key] = df
    return df.copy()


def _mask_sentinel(series: pd.Series) -> pd.Series:
    return series.astype("float64").mask(series == MISSING_SENTINEL)


def machine_measurements(dev: bool = False) -> pd.DataFrame:
    """Machine HR / QRS / QTc / axis / PR per study, sentinel-masked and range-gated.

    Never reads ``structured_features.qrs_ms`` or ``.pr_ms`` -- both are the
    NeuroKit2 values, not the machine measurement (spec §12.8.1, traps 1 and 8).

    ``qtc_ms`` is ``machine_qtc_ms``. §4.A.2.3 names
    ``structured_features.qtc_bazett_ms``, but that column belongs to the same
    defective family: it correlates with the machine QTc at r = 0.024 and is
    valid for only 656,358 studies against the machine column's 748,618. Round
    6.1's "every measurement threshold reads the MACHINE measurement" therefore
    extends to QTc; the NeuroKit value is carried as ``qtc_ms_bazett`` for the
    §4.A.2.8 sensitivity row and for provenance, and is never a label source.

    Returned measurement columns are float64 with ``NaN`` for "not measurable";
    each has a companion ``<name>_valid`` boolean.
    """
    meta = pd.read_parquet(
        DATA_PROCESSED / "index" / "ecg_metadata_clean_with_measurements.parquet",
        columns=["study_id", "rr_interval", "p_onset", "qrs_onset", "qrs_end",
                 "qrs_axis", "machine_hr_bpm", "machine_qrs_ms", "machine_qtc_ms"],
    )
    sf = pd.read_parquet(
        DATA_PROCESSED / "structured_features.parquet", columns=["study_id", "qtc_bazett_ms"]
    )
    df = meta.merge(sf, on="study_id", how="left")

    rr = _mask_sentinel(df["rr_interval"])
    p_on = _mask_sentinel(df["p_onset"])
    qrs_on = _mask_sentinel(df["qrs_onset"])
    qrs_end = _mask_sentinel(df["qrs_end"])
    axis = _mask_sentinel(df["qrs_axis"])

    out = pd.DataFrame({"study_id": df["study_id"]})
    out["hr_bpm"] = np.where(rr > 0, 60000.0 / rr, np.nan)
    out["qrs_ms"] = qrs_end - qrs_on
    out["pr_ms"] = qrs_on - p_on
    out["qrs_axis"] = axis
    out["qtc_ms"] = df["machine_qtc_ms"].astype("float64")
    out["qtc_ms_bazett"] = df["qtc_bazett_ms"].astype("float64")

    ranges = {"hr_bpm": (20, 300), "qrs_ms": (40, 300), "pr_ms": (50, 400),
              "qrs_axis": (-180, 180), "qtc_ms": (200, 800), "qtc_ms_bazett": (200, 800)}
    for col, (lo, hi) in ranges.items():
        out[col] = out[col].where(out[col].between(lo, hi))
        out[f"{col}_valid"] = out[col].notna()

    if dev:
        keep = set(pd.read_parquet(DEV_SAMPLE, columns=["study_id"]).study_id)
        out = out[out.study_id.isin(keep)]
    return out.reset_index(drop=True)


# The A2 / B1 / B2 / A5-masked-attribute bin definitions (§4.A.2.3), one place.
def hr_label(hr: pd.Series) -> pd.Series:
    out = pd.Series(
        np.select([hr < 60, hr < 100], ["bradycardia", "normal"], default="tachycardia"),
        index=hr.index, dtype=object,
    )
    return out.where(hr.notna())


def qrs_label(qrs: pd.Series) -> pd.Series:
    out = pd.Series(
        np.select([qrs < 100, qrs < 120], ["normal", "borderline"], default="wide"),
        index=qrs.index, dtype=object,
    )
    return out.where(qrs.notna())


def qtc_label(qtc: pd.Series) -> pd.Series:
    out = pd.Series(
        np.select([qtc < 350, qtc < 450], ["short", "normal"], default="prolonged"),
        index=qtc.index, dtype=object,
    )
    return out.where(qtc.notna())


def axis_label(axis: pd.Series) -> pd.Series:
    """QRS axis -> left / borderline / normal / right.

    The cut points are NOT invented here: they are the locked clear zones from
    `config/claim_dictionary_LOCKED.yaml` (`families.axis`) -- clear LAD below
    -45 deg, clear RAD above 105 deg, and the injection-free zone -35..95 deg as
    "normal". The two gap bands between them become `borderline` rather than
    being forced into a neighbouring class, so a match on this bucket means the
    two studies really do sit in the same locked zone.

    Used only to construct the §6.7 Level-3 hard negatives. Like `hr_bucket`,
    this is a COHORT-CONSTRUCTION use of a machine measurement, never a model
    input -- the input policy forbids `machine_measurements` for every task that
    reads this bucket.
    """
    out = pd.Series(
        np.select(
            [axis < -45.0, (axis >= -35.0) & (axis <= 95.0), axis > 105.0],
            ["left", "normal", "right"], default="borderline"),
        index=axis.index, dtype=object,
    )
    return out.where(axis.notna())


def report_text_series(dev: bool = False) -> pd.DataFrame:
    """``study_id -> report_text`` (the ``T_machine`` column, §2.5 policy name)."""
    df = pd.read_parquet(
        DATA_PROCESSED / "index" / "ecg_metadata_clean_with_measurements.parquet",
        columns=["study_id", "T_machine"],
    ).rename(columns={"T_machine": "report_text"})
    if dev:
        keep = set(pd.read_parquet(DEV_SAMPLE, columns=["study_id"]).study_id)
        df = df[df.study_id.isin(keep)]
    return df.reset_index(drop=True)


# -----------------------------------------------------------------------------
# deterministic per-row RNG (§4.C invariant 2)
# -----------------------------------------------------------------------------
def stable_seed(*parts: Any) -> int:
    """SHA-256 of ``'|'.join(parts)`` -> a 31-bit seed. Identical on every run."""
    key = "|".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest()[:4], "big") % 2_147_483_648


def stable_uniform(keys: Iterable[Any], salt: str) -> np.ndarray:
    """Deterministic U[0,1) draw, one per key. Same value every run, no RNG state."""
    return np.array(
        [
            int.from_bytes(hashlib.sha256(f"{salt}|{k}".encode()).digest()[:8], "big") / 2**64
            for k in keys
        ],
        dtype="float64",
    )


# -----------------------------------------------------------------------------
# chunked parallel execution with part-parquet checkpointing
# -----------------------------------------------------------------------------
def part_dir(name: str) -> Path:
    path = PARTS_ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def completed_ids(name: str, id_column: str = "study_id") -> set[int]:
    done: set[int] = set()
    for part in sorted(part_dir(name).glob("part_*.parquet")):
        done.update(int(x) for x in pq.read_table(part, columns=[id_column])[id_column].to_pylist())
    return done


def write_part(name: str, rows: list[dict[str, Any]] | pd.DataFrame, schema: pa.Schema) -> Path:
    directory = part_dir(name)
    existing = sorted(directory.glob("part_*.parquet"))
    index = 0 if not existing else int(existing[-1].stem.split("_")[-1]) + 1
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    table = pa.Table.from_pandas(
        frame[[f.name for f in schema]], schema=schema, preserve_index=False
    )
    final = directory / f"part_{index:04d}.parquet"
    tmp = directory / f"part_{index:04d}.parquet.tmp"
    pq.write_table(table, tmp, compression="snappy")
    atomic_replace(tmp, final)
    return final


def publish_parts(name: str, out_path: Path, schema: pa.Schema, *, sort_by: str = "study_id",
                  metadata: dict[str, str] | None = None) -> int:
    import pyarrow.compute as pc

    parts = sorted(part_dir(name).glob("part_*.parquet"))
    if not parts:
        raise RuntimeError(f"no parts to publish for {name}")
    table = pa.concat_tables(
        [pq.read_table(p, schema=schema) for p in parts], promote_options="none"
    )
    table = pc.take(table, pc.sort_indices(table, sort_keys=[(sort_by, "ascending")]))
    meta = {b"created_at_iso": utc_now_iso().encode(), b"n_rows": str(table.num_rows).encode()}
    meta.update({k.encode(): str(v).encode() for k, v in (metadata or {}).items()})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".parquet.tmp")
    pq.write_table(table.replace_schema_metadata(meta), tmp, compression="snappy")
    atomic_replace(tmp, out_path)
    return int(table.num_rows)


def run_chunked(
    *,
    name: str,
    units: Sequence[int],
    worker: Callable[[int], dict[str, Any] | None],
    schema: pa.Schema,
    state: StageState,
    initializer: Callable[[], None] | None = None,
    chunk_size: int = CHUNK_STUDIES,
    desc: str = "",
    id_column: str = "study_id",
    workers: int | None = None,
) -> int:
    """Map ``worker`` over ``units`` in one process pool, flushing a part every
    ``chunk_size`` results.

    One pool for the whole run, not one per chunk: a worker's first
    ``read_modality`` call builds a modality index from the 470 MB manifest, and
    a fresh pool per chunk would pay that cost tens of times over.

    Resume: any unit already present in a part parquet is skipped, so a killed
    run loses at most the results buffered since the last flush. Returns the
    number of units processed in *this* invocation.
    """
    from concurrent.futures import ProcessPoolExecutor

    from tqdm import tqdm
    from tqdm.contrib.logging import logging_redirect_tqdm

    log = logging.getLogger("main")
    n_workers = workers or MAX_WORKERS
    done = completed_ids(name, id_column)
    pending = [u for u in units if u not in done]
    log.info(
        "%s: %d units total, %d already in parts, %d pending, workers=%d, flush every %d",
        name, len(units), len(done), len(pending), n_workers, chunk_size,
    )
    state.update(n_units=len(units), n_done=len(done), n_pending=len(pending))
    if not pending:
        return 0

    processed = 0
    started = time.time()
    rows: list[dict[str, Any]] = []

    def flush() -> None:
        if rows:
            path = write_part(name, rows, schema)
            log.info("wrote %s rows=%d", path.name, len(rows))
            rows.clear()

    with logging_redirect_tqdm():
        bar = tqdm(total=len(pending), file=sys.stderr, dynamic_ncols=True,
                   mininterval=0.5, desc=desc or name)
        with ProcessPoolExecutor(max_workers=n_workers, initializer=initializer) as pool:
            for row in pool.map(worker, pending, chunksize=BATCH_SIZE):
                if row is not None:
                    rows.append(row)
                processed += 1
                bar.update(1)
                if processed % chunk_size == 0:
                    flush()
                    rate = processed / max(1e-6, time.time() - started)
                    state.update(n_done=len(done) + processed, rate_per_s=round(rate, 2),
                                 eta_minutes=round((len(pending) - processed) / max(rate, 1e-6) / 60, 1))
                    log.info("%s: %d/%d done this run, %.1f units/s",
                             name, processed, len(pending), rate)
        flush()
        bar.close()
    state.update(n_done=len(done) + processed,
                 rate_per_s=round(processed / max(1e-6, time.time() - started), 2))
    return processed


# -----------------------------------------------------------------------------
# task output writer
# -----------------------------------------------------------------------------
def write_task_split_parquets(
    df: pd.DataFrame,
    task_key: str,
    *,
    schema: pa.Schema | None = None,
    prefix: str = "",
    split_column: str = "split",
) -> dict[str, int]:
    """Write ``{train,val,test}.parquet`` (or ``<prefix>{train,...}``) for one task."""
    out_dir = task_dir(task_key)
    counts: dict[str, int] = {}
    for split in SPLITS:
        part = df[df[split_column] == split]
        if schema is not None:
            table = pa.Table.from_pandas(
                part[[f.name for f in schema]], schema=schema, preserve_index=False
            )
        else:
            table = pa.Table.from_pandas(part, preserve_index=False)
        table = table.replace_schema_metadata(
            {b"task": task_key.encode(), b"split": split.encode(),
             b"created_at_iso": utc_now_iso().encode(), b"n_rows": str(len(part)).encode()}
        )
        name = f"{prefix}{split}.parquet"
        tmp = out_dir / (name + ".tmp")
        pq.write_table(table, tmp, compression="snappy")
        atomic_replace(tmp, out_dir / name)
        counts[split] = int(len(part))
    return counts


def write_cohort_manifest(df: pd.DataFrame, task_key: str,
                          name: str = "cohort_manifest.parquet") -> int:
    out_dir = task_dir(task_key)
    tmp = out_dir / (name + ".tmp")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), tmp, compression="snappy")
    atomic_replace(tmp, out_dir / name)
    return int(len(df))


def write_task_readme(task_key: str, body: str) -> Path:
    out_dir = task_dir(task_key)
    path = out_dir / "README.md"
    path.write_text(body.rstrip() + "\n", encoding="utf-8")
    return path


def split_summary(df: pd.DataFrame, split_column: str = "split") -> dict[str, Any]:
    """Rows and subjects per split, and the zero-overlap assertion (§9.2, §4.C)."""
    out: dict[str, Any] = {"n_rows": int(len(df)), "n_subjects": int(df.subject_id.nunique())}
    seen: dict[str, set[int]] = {}
    for split in SPLITS:
        part = df[df[split_column] == split]
        seen[split] = set(part.subject_id)
        out[f"n_rows_{split}"] = int(len(part))
        out[f"n_subjects_{split}"] = int(part.subject_id.nunique())
    overlap = (
        (seen["train"] & seen["val"]) | (seen["train"] & seen["test"]) | (seen["val"] & seen["test"])
    )
    out["subject_overlap"] = len(overlap)
    if overlap:
        raise RuntimeError(
            f"{len(overlap)} subjects appear in more than one split -- §4.C invariant 1"
        )
    return out


def add_std_args(parser: Any) -> None:
    """``--dev`` (smoke test on dev_sample), ``--force`` (ignore the done flag)."""
    parser.add_argument("--dev", action="store_true",
                        help="run on data/processed/dev_sample/ instead of the full cohort")
    parser.add_argument("--force", action="store_true",
                        help="ignore the state file's done flag and rebuild from scratch")
    parser.add_argument("--limit", type=int, default=0,
                        help="cap the number of studies processed (debugging only)")
```

### `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/measurement_task.py`

```python
"""The A2 / B1 / B2 measurement-bin table -- one definition, three consumers.

§4.A.2.3 defines the HR / QRS / QTc bins; §4.B.1.3 says "identical to §4.A.2.3";
§4.B.2.3 says the B2 anchors inherit their B1 labels unchanged. A2 and B1 differ
only in cohort scope (A2 = L3 x {high,medium} SQI, B1 = the full clean cohort),
so the labels are computed once here and each builder filters and writes.

Every threshold reads the MACHINE measurement, sentinel-masked (spec §12.8.1-2,
Round 6.1). ``qtc_ms`` is ``machine_qtc_ms``; ``qtc_ms_bazett`` is the NeuroKit2
value, carried as provenance and as the §4.A.2.8 sensitivity row only.
"""

from __future__ import annotations

import pandas as pd
import pyarrow as pa

from . import build_common as bc

HEADS = ("hr_label", "qrs_label", "qtc_label")
CLASSES = {
    "hr_label": ["bradycardia", "normal", "tachycardia"],
    "qrs_label": ["normal", "borderline", "wide"],
    "qtc_label": ["short", "normal", "prolonged"],
}

SCHEMA = pa.schema([
    ("study_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("split", pa.string()),
    ("link_tier", pa.string()),
    ("sqi_tier", pa.string()),
    ("cart_id", pa.string()),
    ("hr_bpm", pa.float32()),
    ("qrs_ms", pa.float32()),
    ("qtc_ms", pa.float32()),
    ("qtc_ms_bazett", pa.float32()),      # provenance / sensitivity only
    ("hr_label", pa.string()),
    ("qrs_label", pa.string()),
    ("qtc_label", pa.string()),
    ("is_primary", pa.bool_()),
])


def measurement_table(dev: bool = False) -> pd.DataFrame:
    """Full clean cohort with the three bins attached and invalid rows dropped.

    A row survives only when all three measurements are valid: the task is
    "predict all three bins", and a row missing one head has no label for it.
    ``is_primary`` is left for the caller to set -- the two tasks disagree on
    what primary means.
    """
    cohort = bc.load_clean_cohort(dev=dev)
    meas = bc.machine_measurements(dev=dev)
    df = cohort.merge(meas, on="study_id", how="left")

    valid = df.hr_bpm_valid.fillna(False) & df.qrs_ms_valid.fillna(False) & df.qtc_ms_valid.fillna(False)
    df = df[valid].copy()

    df["hr_label"] = bc.hr_label(df.hr_bpm)
    df["qrs_label"] = bc.qrs_label(df.qrs_ms)
    df["qtc_label"] = bc.qtc_label(df.qtc_ms)
    df["cart_id"] = df["cart_id"].astype("Int64").astype("string")
    for col in ("hr_bpm", "qrs_ms", "qtc_ms", "qtc_ms_bazett"):
        df[col] = df[col].astype("float32")
    return df.sort_values("study_id", kind="mergesort").reset_index(drop=True)


def label_stats(df: pd.DataFrame) -> dict:
    """Per-head class distribution, overall and per split."""
    out: dict = {}
    for head in HEADS:
        counts = df[head].value_counts()
        out[head] = {
            cls: {"n": int(counts.get(cls, 0)),
                  "pct": round(100 * float(counts.get(cls, 0)) / max(len(df), 1), 3)}
            for cls in CLASSES[head]
        }
        out[f"{head}_by_split"] = {
            split: {
                cls: round(
                    100 * float((df[df.split == split][head] == cls).mean()) if
                    len(df[df.split == split]) else 0.0, 3
                )
                for cls in CLASSES[head]
            }
            for split in bc.SPLITS
        }
    return out
```

### `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/verification_task.py`

```python
"""Cross-modal verification rows -- shared by A5 (§4.A.5) and B4 (§4.B.4).

§4.B.4.3 says B4 uses "the same 5-negative-type construction as A5's
verification head", and §4.B.4.8 asks whether training B4 jointly with A5's
masked-attribute head helps or hurts *pure* verification. That comparison is
only meaningful if both tasks see the same verification rows, so the
construction lives here and both builders call it. It is fully deterministic --
no RNG state, only a hash of (anchor, negative type) -- so the two tasks get
byte-identical rows without either depending on the other's output.

Per anchor study (§4.A.5.3): 2 positives and 5 negatives = 7 rows.

| row | signal | image | text |
| --- | --- | --- | --- |
| positive (clean) | anchor | anchor, clean rendering | anchor |
| positive (scanlike) | anchor | anchor, scan-like rendering | anchor |
| `TEXT_SWAP` | anchor | anchor | **donor** |
| `IMAGE_SWAP` | anchor | **donor** | anchor |
| `SIGNAL_SWAP` | **donor** | anchor | anchor |
| `HARD_NEGATIVE_TEXT` | anchor | anchor | **same-HR-bucket donor** |
| `PARTIAL_MISMATCH` | anchor | **donor A** | **donor B** |

Two rules the spec does not spell out but that the split contract forces:

* **Donors come from the anchor's own split.** A train row pointing at a test
  subject's signal would put test bytes into training -- the §4.C invariant-1
  violation the whole split exists to prevent. Donor selection is therefore
  per split.
* **Negatives all use the clean rendering.** Fixing the rendering keeps the
  per-``neg_type`` F1 table (§4.A.5.8) from being confounded by how the image
  was drawn. The clean-vs-scanlike and Lead-II-vs-12-lead comparisons are done
  by resolving a different modality kind for the same ``image_id`` at load
  time, which is what ``image_type`` records.

``HARD_NEGATIVE_TEXT`` is emitted only where a same-HR-bucket, different-subject
alternative exists in the split (§4.A.5.3), so a few anchors yield 6 rows.

**Test rows carry four more negatives** -- Plan A/B §6.7's Levels 2-5, which the
original build omitted. They exist only in the test split, because they measure
generalisation to harder negatives rather than being something to train on:

| row | signal | image | text | §6.7 level |
| --- | --- | --- | --- | --- |
| `HARD_NEGATIVE_L2` | anchor | anchor | donor matched on HR + QRS bucket | 2 |
| `HARD_NEGATIVE_L3` | anchor | anchor | donor matched on HR + QRS + axis + QTc | 3 |
| `HARD_NEGATIVE_L4` | anchor | anchor | **the anchor's own subject**, another study | 4 |
| `HARD_NEGATIVE_L5` | anchor | anchor | the anchor's own report, one claim swapped | 5 |

Levels 0 and 1 are the five original negative types: the cross-subject swaps are
Level 0, ``HARD_NEGATIVE_TEXT`` is Level 1.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
import pyarrow as pa

from . import build_common as bc

NEG_TYPES = ("TEXT_SWAP", "IMAGE_SWAP", "SIGNAL_SWAP", "HARD_NEGATIVE_TEXT", "PARTIAL_MISMATCH")

# ---------------------------------------------------------------------------
# The Plan A/B §6.7 difficulty ladder, Levels 2-5. TEST SPLIT ONLY.
# ---------------------------------------------------------------------------
# §6.7 specifies six levels and §6.8's Figure 4 is the CURVE across them; the
# original build stopped at two (Level 0 = the cross-subject swaps, Level 1 =
# HARD_NEGATIVE_TEXT's same-HR-bucket swap) and shipped the third empty. Two
# points are not a curve, and Level 4 -- same patient, different study -- is the
# rung that tests the patient/demographic shortcut, which is the shortcut most
# likely to be real in MIMIC where one subject carries many ECGs.
#
# **Why test-split only.** The levels measure GENERALISATION to harder
# negatives: §6.7's expected behaviour is "most shortcut models plateau". Train
# on Level 3 negatives and the plateau is trained away, so Figure 4 would
# measure the training distribution instead of the model's shortcut reliance.
# Keeping them out of train is the methodologically correct choice, and it also
# means not one model has to be retrained to get the curve.
#
# A5 and B4 both receive them, because §4.B.4.8's A5-vs-B4 comparison is only
# controlled while the two tasks see identical rows -- the builder asserts it.
DIFFICULTY_NEG_TYPES = ("HARD_NEGATIVE_L2", "HARD_NEGATIVE_L3",
                        "HARD_NEGATIVE_L4", "HARD_NEGATIVE_L5")
# The bucket columns each level matches its text donor on. Level 4 matches on
# nothing -- it matches on the SUBJECT, which is the opposite constraint.
DIFFICULTY_MATCH_KEYS = {
    "HARD_NEGATIVE_L2": ("hr_bucket", "qrs_bucket"),
    "HARD_NEGATIVE_L3": ("hr_bucket", "qrs_bucket", "axis_bucket", "qtc_bucket"),
}
B5_TASK_DIR = "B5_contradiction_detection"

SALTS = {
    "TEXT_SWAP": 0x51ED270B,
    "IMAGE_SWAP": 0x2545F491,
    "SIGNAL_SWAP": 0x9E3779B1,
    "HARD_NEGATIVE_TEXT": 0x7FEB352D,
    "PARTIAL_MISMATCH": 0x846CA68B,
    "PARTIAL_MISMATCH_B": 0xC2B2AE35,
    "HARD_NEGATIVE_L2": 0x1B873593,
    "HARD_NEGATIVE_L3": 0xCC9E2D51,
    "HARD_NEGATIVE_L4": 0x85EBCA6B,
    "HARD_NEGATIVE_L5": 0xC2B2AE3D,
}

SCHEMA = pa.schema([
    ("anchor_study_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("signal_id", pa.int64()),
    ("image_id", pa.int64()),
    ("text_id", pa.int64()),
    ("image_type", pa.string()),
    ("y_match", pa.int8()),
    ("neg_type", pa.string()),
    ("split", pa.string()),
    # Level 5 only, null everywhere else: the anchor's OWN report with a single
    # clinical claim swapped. The loader uses this string in place of the report
    # `text_id` points at. See `_level_5_rows`.
    ("text_override", pa.string()),
])

_U64 = np.uint64


def _mix(keys: np.ndarray, salt: int) -> np.ndarray:
    """splitmix64 finaliser -- a fast, deterministic, dependency-free hash.

    Used instead of ``numpy.random`` so a row's donor depends only on that row,
    never on iteration order or on how many rows came before it. Re-running the
    builder therefore reproduces the dataset exactly (§4.C invariant 2).
    """
    # The salt is folded in as a pre-masked Python int: numpy warns on a
    # scalar uint64 multiply that wraps, and wrapping is exactly what splitmix
    # wants.
    offset = _U64((salt * 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF)
    z = (keys.astype(_U64) + offset).astype(_U64)
    z = ((z ^ (z >> _U64(30))) * _U64(0xBF58476D1CE4E5B9)).astype(_U64)
    z = ((z ^ (z >> _U64(27))) * _U64(0x94D049BB133111EB)).astype(_U64)
    return (z ^ (z >> _U64(31))).astype(_U64)


def _pick_donors(study_ids: np.ndarray, subject_ids: np.ndarray, salt: int) -> np.ndarray:
    """A different-subject donor for every row of a pool, deterministically.

    The pool is ordered by (subject_id, study_id), so a subject's studies are
    contiguous and walking forward from a collision leaves that subject after at
    most (its study count) steps.
    """
    n = len(study_ids)
    if n < 2:
        return np.full(n, -1, dtype="int64")
    offset = (_mix(study_ids, salt) % _U64(n - 1)).astype("int64") + 1
    idx = (np.arange(n) + offset) % n
    clash = np.flatnonzero(subject_ids[idx] == subject_ids)
    for pos in clash:
        j = idx[pos]
        for _ in range(n):
            j = (j + 1) % n
            if subject_ids[j] != subject_ids[pos]:
                break
        idx[pos] = j
    still = subject_ids[idx] == subject_ids
    donors = study_ids[idx]
    donors[still] = -1          # a split holding a single subject yields no donor
    return donors


def _donor_frame(pool: pd.DataFrame, salt_key: str) -> pd.Series:
    """Donor study id per row of ``pool``, indexed like ``pool``."""
    ordered = pool.sort_values(["subject_id", "study_id"], kind="mergesort")
    donors = _pick_donors(
        ordered.study_id.to_numpy(), ordered.subject_id.to_numpy(), SALTS[salt_key]
    )
    return pd.Series(donors, index=ordered.index).reindex(pool.index)


def _grouped_donor(pool: pd.DataFrame, keys: Sequence[str], salt_key: str) -> np.ndarray:
    """A different-subject donor drawn from inside the row's own bucket.

    Generalises what HARD_NEGATIVE_TEXT does for `hr_bucket` to any tuple of
    bucket columns, which is how §6.7's Levels 2 and 3 tighten the match. A row
    whose bucket holds no usable alternative gets -1 and is dropped, so a level
    never fabricates a donor by relaxing its own matching rule.
    """
    donors = np.full(len(pool), -1, dtype="int64")
    usable = pool[list(keys)].notna().all(axis=1)
    for _, group in pool[usable].groupby(list(keys), sort=False, dropna=True):
        ordered = group.sort_values(["subject_id", "study_id"], kind="mergesort")
        picked = _pick_donors(ordered.study_id.to_numpy(), ordered.subject_id.to_numpy(),
                              SALTS[salt_key])
        donors[ordered.index.to_numpy()] = picked
    return donors


def _same_subject_donor(pool: pd.DataFrame, salt_key: str) -> np.ndarray:
    """Another study of the row's OWN subject -- §6.7 Level 4.

    Every other negative type is required to cross subjects; this one is
    required NOT to. That inversion is the point: a model that has learnt
    patient identity (age, sex, lead placement, cart) rather than the report's
    content scores near-perfectly on Levels 0-3 and collapses here.

    A subject with a single ECG has no alternative and yields -1.
    """
    donors = np.full(len(pool), -1, dtype="int64")
    for _, group in pool.groupby("subject_id", sort=False):
        if len(group) < 2:
            continue
        ordered = group.sort_values("study_id", kind="mergesort")
        ids = ordered.study_id.to_numpy()
        offset = (_mix(ids, SALTS[salt_key]) % _U64(len(ids) - 1)).astype("int64") + 1
        donors[ordered.index.to_numpy()] = ids[(np.arange(len(ids)) + offset) % len(ids)]
    return donors


def _b5_corrupted_reports(dev: bool = False) -> pd.Series:
    """``study_id -> corrupted_report_text`` for the corrupted TEST rows of B5.

    §6.7 Level 5 is "a near-duplicate hard negative with an altered
    report/image/signal component". The altered report already exists, locked
    and deterministic: B5 injects exactly one contradicted clinical claim into a
    report, only where the underlying measurement sits in a clear zone, and only
    by swapping surface forms the report actually contains. Reusing it means
    Level 5 introduces no new text-generation rule of its own, and the two tasks
    cannot drift apart.

    Returns an empty Series when B5 has not been built -- Level 5 is then simply
    absent, rather than the build failing.
    """
    # `tasks_root()` already resolves _dev from the module-level flag the
    # builders set with `bc.set_dev()`; `dev` is accepted for symmetry.
    path = bc.tasks_root() / B5_TASK_DIR / "test.parquet"
    if not path.exists():
        return pd.Series(dtype="string")
    b5 = pd.read_parquet(path, columns=["study_id", "is_corrupted", "corrupted_report_text"])
    b5 = b5[b5["is_corrupted"].fillna(False).astype(bool)]
    b5 = b5.dropna(subset=["corrupted_report_text"]).drop_duplicates("study_id")
    return b5.set_index("study_id")["corrupted_report_text"].astype("string")


def _difficulty_buckets(study_ids: np.ndarray) -> pd.DataFrame:
    """`qrs_bucket` / `qtc_bucket` / `axis_bucket` for the Level 2-3 matching.

    Cohort construction, not model input: the buckets decide which studies may
    serve as each other's hard negatives and never reach an encoder. Same
    standing as `hr_bucket`, which the cohort already carries and which Level 1
    already matches on.
    """
    measurements = bc.machine_measurements()
    measurements = measurements[measurements.study_id.isin(set(int(s) for s in study_ids))]
    return pd.DataFrame({
        "study_id": measurements["study_id"].to_numpy(),
        "qrs_bucket": bc.qrs_label(measurements["qrs_ms"]).to_numpy(),
        "qtc_bucket": bc.qtc_label(measurements["qtc_ms"]).to_numpy(),
        "axis_bucket": bc.axis_label(measurements["qrs_axis"]).to_numpy(),
    })


def build_verification(dev: bool = False) -> pd.DataFrame:
    """The 7-rows-per-anchor verification table for the full clean cohort."""
    cohort = bc.load_clean_cohort(dev=dev)
    # §4.A.5.2 needs all three modalities present; Phase 1 QC says all clean
    # studies have text, a clean image and a scan-like image, but assert rather
    # than assume -- the cohort definition must not drift silently.
    usable = cohort.text_ok.fillna(False) & cohort.image_clean_ok.fillna(False) \
        & cohort.image_scanlike_ok.fillna(False)
    cohort = cohort[usable][["study_id", "subject_id", "split", "hr_bucket"]].copy()
    # Levels 2-3 match on more than heart rate, so the extra buckets are joined
    # once here rather than recomputed per split.
    cohort = cohort.merge(_difficulty_buckets(cohort.study_id.to_numpy()),
                          on="study_id", how="left")
    corrupted_reports = _b5_corrupted_reports(dev=dev)

    frames: list[pd.DataFrame] = []
    for split in bc.SPLITS:
        pool = cohort[cohort.split == split].reset_index(drop=True)
        if pool.empty:
            continue
        anchor = pool.study_id.to_numpy()
        subject = pool.subject_id.to_numpy()

        random_donor = {
            key: _donor_frame(pool, key).to_numpy()
            for key in ("TEXT_SWAP", "IMAGE_SWAP", "SIGNAL_SWAP",
                        "PARTIAL_MISMATCH", "PARTIAL_MISMATCH_B")
        }

        # HARD_NEGATIVE_TEXT draws inside the anchor's own HR bucket.
        hard = np.full(len(pool), -1, dtype="int64")
        for bucket, group in pool.groupby("hr_bucket", sort=False):
            donors = _pick_donors(
                group.sort_values(["subject_id", "study_id"], kind="mergesort").study_id.to_numpy(),
                group.sort_values(["subject_id", "study_id"], kind="mergesort").subject_id.to_numpy(),
                SALTS["HARD_NEGATIVE_TEXT"],
            )
            order = group.sort_values(["subject_id", "study_id"], kind="mergesort").index.to_numpy()
            hard[order] = donors

        def row(signal, image, text, image_type, y, neg, text_override=None):
            return pd.DataFrame({
                "anchor_study_id": anchor,
                "subject_id": subject,
                "signal_id": signal,
                "image_id": image,
                "text_id": text,
                "image_type": image_type,
                "y_match": np.int8(y),
                "neg_type": neg,
                "split": split,
                "text_override": (pd.Series([None] * len(anchor), dtype="string")
                                  if text_override is None else text_override),
            })

        frames.append(row(anchor, anchor, anchor, "clean", 1, None))
        frames.append(row(anchor, anchor, anchor, "scanlike", 1, None))
        frames.append(row(anchor, anchor, random_donor["TEXT_SWAP"], "clean", 0, "TEXT_SWAP"))
        frames.append(row(anchor, random_donor["IMAGE_SWAP"], anchor, "clean", 0, "IMAGE_SWAP"))
        frames.append(row(random_donor["SIGNAL_SWAP"], anchor, anchor, "clean", 0, "SIGNAL_SWAP"))
        frames.append(row(anchor, anchor, hard, "clean", 0, "HARD_NEGATIVE_TEXT"))
        frames.append(row(anchor, random_donor["PARTIAL_MISMATCH"],
                          random_donor["PARTIAL_MISMATCH_B"], "clean", 0, "PARTIAL_MISMATCH"))

        # -- Plan A/B §6.7 Levels 2-5, TEST SPLIT ONLY (see DIFFICULTY_NEG_TYPES)
        if split != "test":
            continue

        for neg_type, keys in DIFFICULTY_MATCH_KEYS.items():
            frames.append(row(anchor, anchor, _grouped_donor(pool, keys, neg_type),
                              "clean", 0, neg_type))

        frames.append(row(anchor, anchor, _same_subject_donor(pool, "HARD_NEGATIVE_L4"),
                          "clean", 0, "HARD_NEGATIVE_L4"))

        # Level 5: the anchor's OWN report, one clinical claim swapped. text_id
        # stays the anchor so the row is a near-duplicate in every other respect;
        # only rows for which B5 produced a corrupted report are emitted.
        override = pd.Series(anchor, dtype="int64").map(corrupted_reports).astype("string")             if len(corrupted_reports) else pd.Series([None] * len(anchor), dtype="string")
        level5 = row(anchor, anchor, anchor, "clean", 0, "HARD_NEGATIVE_L5",
                     text_override=override.to_numpy())
        frames.append(level5[pd.notna(level5["text_override"])])

    df = pd.concat(frames, ignore_index=True)
    # A row whose donor could not be found is dropped, not emitted with a -1.
    incomplete = (df.signal_id < 0) | (df.image_id < 0) | (df.text_id < 0)
    df = df[~incomplete]
    df["neg_type"] = df["neg_type"].astype("string")
    df["text_override"] = df["text_override"].astype("string")
    return df.sort_values(["anchor_study_id", "y_match", "neg_type"],
                          kind="mergesort").reset_index(drop=True)


def verification_stats(df: pd.DataFrame) -> dict:
    """Row counts, class balance, per-negative-type counts, and the leak checks."""
    by_split = {}
    for split in bc.SPLITS:
        part = df[df.split == split]
        by_split[split] = {
            "n_rows": int(len(part)),
            "n_anchors": int(part.anchor_study_id.nunique()),
            "n_positive": int((part.y_match == 1).sum()),
            "n_negative": int((part.y_match == 0).sum()),
        }
    return {
        "n_rows": int(len(df)),
        "n_anchors": int(df.anchor_study_id.nunique()),
        "n_subjects": int(df.subject_id.nunique()),
        "positive_rate_pct": round(100 * float((df.y_match == 1).mean()), 3),
        "rows_per_neg_type": {
            ("positive" if pd.isna(k) else str(k)): int(v)
            for k, v in df.neg_type.value_counts(dropna=False).items()
        },
        "image_type_counts": df.image_type.value_counts().to_dict(),
        "by_split": by_split,
    }


def assert_no_cross_split_donor(df: pd.DataFrame, cohort: pd.DataFrame) -> None:
    """Every referenced study must sit in the same split as its anchor row.

    This is the check that makes the negatives safe: a donor from another split
    would carry that split's bytes into this one.
    """
    split_of = cohort.set_index("study_id")["split"]
    for column in ("signal_id", "image_id", "text_id"):
        referenced = df[column].map(split_of)
        bad = int((referenced != df["split"]).sum())
        if bad:
            raise RuntimeError(f"{bad} rows reference a {column} from another split")


def assert_negatives_are_mismatched(df: pd.DataFrame, cohort: pd.DataFrame) -> None:
    """A negative must actually disagree with its anchor at the SUBJECT level.

    Pointing at a different study of the same patient would make ``y_match = 0``
    a lie for a model that learns patient identity.
    """
    subject_of = cohort.set_index("study_id")["subject_id"]
    negatives = df[df.y_match == 0]
    swapped = {
        "TEXT_SWAP": "text_id", "IMAGE_SWAP": "image_id", "SIGNAL_SWAP": "signal_id",
        "HARD_NEGATIVE_TEXT": "text_id",
        "HARD_NEGATIVE_L2": "text_id", "HARD_NEGATIVE_L3": "text_id",
    }
    # Levels 4 and 5 invert this rule on purpose, so they are checked for the
    # OPPOSITE property instead of being exempted silently.
    level4 = negatives[negatives.neg_type == "HARD_NEGATIVE_L4"]
    if len(level4):
        cross = int((level4.text_id.map(subject_of).to_numpy()
                     != level4.subject_id.to_numpy()).sum())
        if cross:
            raise RuntimeError(
                f"{cross} HARD_NEGATIVE_L4 rows swap in a DIFFERENT subject. Level 4 is "
                "the same-patient rung (§6.7): a cross-subject donor there would make it "
                "a duplicate of Level 0 and hide the patient-identity shortcut.")
        same_study = int((level4.text_id.to_numpy() == level4.anchor_study_id.to_numpy()).sum())
        if same_study:
            raise RuntimeError(f"{same_study} HARD_NEGATIVE_L4 rows point at the anchor's "
                               "own study -- that is a positive, not a negative")
    level5 = negatives[negatives.neg_type == "HARD_NEGATIVE_L5"]
    if len(level5):
        # Level 5 keeps every pointer on the anchor; what makes it a negative is
        # the altered report string, so that is what must be present and changed.
        if not (level5.text_id.to_numpy() == level5.anchor_study_id.to_numpy()).all():
            raise RuntimeError("HARD_NEGATIVE_L5 must keep the anchor's own text_id")
        if level5.text_override.isna().any():
            raise RuntimeError("HARD_NEGATIVE_L5 rows must all carry a text_override")
    for neg_type, column in swapped.items():
        part = negatives[negatives.neg_type == neg_type]
        same = int((part[column].map(subject_of).to_numpy() == part.subject_id.to_numpy()).sum())
        if same:
            raise RuntimeError(f"{same} {neg_type} rows swap in the anchor's own subject")
    partial = negatives[negatives.neg_type == "PARTIAL_MISMATCH"]
    same = int(
        ((partial.image_id.map(subject_of).to_numpy() == partial.subject_id.to_numpy())
         & (partial.text_id.map(subject_of).to_numpy() == partial.subject_id.to_numpy())).sum()
    )
    if same:
        raise RuntimeError(f"{same} PARTIAL_MISMATCH rows swap in the anchor's own subject twice")
```

## 6. Validation results

- Pre-flight: PASS — every builder calls `build_common.preflight()`, which asserts its inputs exist and records free disk and free RAM before any work starts. Phase 1 completion was verified at Stage P2.0 and is unchanged.

### Per-script validation (read back from the state files)

**`00_extract_fiducials`** — PASS

```json
{
  "done": true,
  "n_units": 749112,
  "n_done": 749112,
  "n_pending": 749112,
  "rate_per_s": 55.87,
  "eta_minutes": 2.7,
  "finished_at": "2026-08-26T22:25:09Z",
  "n_rows": 749112,
  "n_fallback_used": 750,
  "pct_fallback_used": 0.1,
  "n_delineate_ok": 743808,
  "pct_delineate_ok": 99.292,
  "n_peaks_mean": 12.73,
  "n_peaks_median": 12,
  "implied_hr_bpm_mean": 76.4,
  "sqi_per_bin_mean": 0.6178,
  "n_with_notes": 12988,
  "elapsed_seconds": 13412.4,
  "corr_peakrate_vs_machine_hr": 0.9206
}
```

**`00b_rebuild_lab_cache`** — PASS

```json
{
  "done": true,
  "chunks_done": 40,
  "rows_in": 158374764,
  "rows_out": 20481517,
  "finished_at": "2026-08-26T18:41:03Z",
  "n_rows": 20481517,
  "rows_read": 158374764,
  "out_path": "D:\\Coding\\MU\\Tri-Modal_ECG\\data\\raw\\ehr_cache\\labevents_key_labs.parquet",
  "per_lab": [
    {
      "lab": "Ca",
      "n": 3341228,
      "valuenum_pct": 99.98,
      "ref_lower_pct": 100.0,
      "ref_upper_pct": 100.0,
      "flag_pct": 30.63
    },
    {
      "lab": "K",
      "n": 4484371,
      "valuenum_pct": 99.94,
      "ref_lower_pct": 100.0,
      "ref_upper_pct": 100.0,
      "flag_pct": 10.04
    },
    {
      "lab": "Mg",
      "n": 2933221,
      "valuenum_pct": 99.98,
      "ref_lower_pct": 100.0,
      "ref_upper_pct": 100.0,
      "flag_pct": 7.98
    },
    {
      "lab": "Na",
      "n": 4271671,
      "valuenum_pct": 99.98,
      "ref_lower_pct": 100.0,
      "ref_upper_pct": 100.0,
      "flag_pct": 14.36
    },
    {
      "lab": "creatinine",
      "n": 4320364,
      "valuenum_pct": 99.96,
      "ref_lower_pct": 100.0,
      "ref_upper_pct": 100.0,
      "flag_pct": 31.59
    },
    {
      "lab": "lactate",
      "n": 670120,
      "valuenum_pct": 99.95,
      "ref_lower_pct": 100.0,
      "ref_upper_pct": 100.0,
      "flag_pct": 36.9
    },
    {
      "lab": "troponin",
      "n": 460542,
      "valuenum_pct": 41.74,
      "ref_lower_pct": 100.0,
      "ref_upper_pct": 100.0,
      "flag_pct": 38.9
    }
  ],
  "elapsed_seconds": 537.7
}
```

**`01_build_A1_ecg_diagnosis`** — PASS

```json
{
  "done": true,
  "finished_at": "2026-08-26T18:45:10Z",
  "n_rows_total": 500277,
  "n_rows_primary_l3_hosp": 376051,
  "n_rows_sensitivity_l2": 78268,
  "n_rows_ed_secondary": 47703,
  "splits": {
    "train": 350090,
    "val": 50216,
    "test": 99971
  },
  "boundary_flag_pct": 13.513,
  "boundary_flag_pct_primary": 12.848,
  "n_manifest_codes": 138,
  "prevalence_primary": {
    "atrial_fibrillation_flutter": 30.15,
    "heart_failure_narrow": 30.425,
    "acute_myocardial_infarction": 11.159,
    "conduction_disorder": 6.589,
    "ventricular_arrhythmia_or_arrest": 5.055
  },
  "prevalence_primary_by_split": {
    "train": {
      "atrial_fibrillation_flutter": 30.429,
      "heart_failure_narrow": 30.645,
      "acute_myocardial_infarction": 11.315,
      "conduction_disorder": 6.507,
      "ventricular_arrhythmia_or_arrest": 5.132
    },
    "val": {
      "atrial_fibrillation_flutter": 29.082,
      "heart_failure_narrow": 29.604,
      "acute_myocardial_infarction": 11.099,
      "conduction_disorder": 6.298,
      "ventricular_arrhythmia_or_arrest": 5.143
    },
    "test": {
      "atrial_fibrillation_flutter": 29.71,
      "heart_failure_narrow": 30.069,
      "acute_myocardial_infarction": 10.644,
      "conduction_disorder": 7.024,
      "ventricular_arrhythmia_or_arrest": 4.739
    }
  },
  "n_any_label_primary": 193977,
  "n_rows": 500277,
  "n_subjects": 124547,
  "n_rows_train": 350090,
  "n_subjects_train": 87220,
  "n_rows_val": 50216,
  "n_subjects_val": 12440,
  "n_rows_test": 99971,
  "n_subjects_test": 24887,
  "subject_overlap": 0,
  "primary_n_rows": 376051,
  "primary_n_subjects": 95765,
  "primary_n_rows_train": 262950,
  "primary_n_subjects_train": 67024,
  "primary_n_rows_val": 37914,
  "primary_n_subjects_val": 9573,
  "primary_n_rows_test": 75187,
  "primary_n_subjects_test": 19168,
  "primary_subject_overlap": 0
}
```

**`02_build_A2_measurement_blind`** — PASS

```json
{
  "done": true,
  "finished_at": "2026-08-26T18:51:16Z",
  "n_rows_total": 500017,
  "n_rows_primary": 275088,
  "splits_total": {
    "train": 349871,
    "val": 50182,
    "test": 99964
  },
  "sqi_breakdown_l3": {
    "high": 3110,
    "medium": 271978,
    "low": 146667
  },
  "n_rows_l3_sqi_high_only": 3110,
  "n_rows_l3_l2_sqi_high_medium": 324465,
  "labels_primary": {
    "hr_label": {
      "bradycardia": {
        "n": 20932,
        "pct": 7.609
      },
      "normal": {
        "n": 185939,
        "pct": 67.593
      },
      "tachycardia": {
        "n": 68217,
        "pct": 24.798
      }
    },
    "hr_label_by_split": {
      "train": {
        "bradycardia": 7.604,
        "normal": 67.654,
        "tachycardia": 24.742
      },
      "val": {
        "bradycardia": 7.656,
        "normal": 67.254,
        "tachycardia": 25.09
      },
      "test": {
        "bradycardia": 7.602,
        "normal": 67.55,
        "tachycardia": 24.847
      }
    },
    "qrs_label": {
      "normal": {
        "n": 179641,
        "pct": 65.303
      },
      "borderline": {
        "n": 53710,
        "pct": 19.525
      },
      "wide": {
        "n": 41737,
        "pct": 15.172
      }
    },
    "qrs_label_by_split": {
      "train": {
        "normal": 65.238,
        "borderline": 19.538,
        "wide": 15.225
      },
      "val": {
        "normal": 65.471,
        "borderline": 19.274,
        "wide": 15.255
      },
      "test": {
        "normal": 65.446,
        "borderline": 19.606,
        "wide": 14.947
      }
    },
    "qtc_label": {
      "short": {
        "n": 232,
        "pct": 0.084
      },
      "normal": {
        "n": 140587,
        "pct": 51.106
      },
      "prolonged": {
        "n": 134269,
        "pct": 48.809
      }
    },
    "qtc_label_by_split": {
      "train": {
        "short": 0.09,
        "normal": 50.989,
        "prolonged": 48.922
      },
      "val": {
        "short": 0.047,
        "normal": 51.402,
        "prolonged": 48.551
      },
      "test": {
        "short": 0.085,
        "normal": 51.366,
        "prolonged": 48.549
      }
    }
  },
  "measurement_summary_primary": {
    "hr_bpm": {
      "mean": 86.98,
      "median": 84.03,
      "min": 21.0,
      "max": 255.32
    },
    "qrs_ms": {
      "mean": 98.64,
      "median": 92.0,
      "min": 42.0,
      "max": 296.0
    },
    "qtc_ms": {
      "mean": 451.03,
      "median": 448.89,
      "min": 240.15,
      "max": 749.84
    }
  },
  "qtc_bazett_valid_pct_primary": 84.29,
  "n_rows": 500017,
  "n_subjects": 124584,
  "n_rows_train": 349871,
  "n_subjects_train": 87244,
  "n_rows_val": 50182,
  "n_subjects_val": 12440,
  "n_rows_test": 99964,
  "n_subjects_test": 24900,
  "subject_overlap": 0,
  "primary_n_rows": 275088,
  "primary_n_subjects": 94025,
  "primary_n_rows_train": 192087,
  "primary_n_subjects_train": 65852,
  "primary_n_rows_val": 27820,
  "primary_n_subjects_val": 9379,
  "primary_n_rows_test": 55181,
  "primary_n_subjects_test": 18794,
  "primary_subject_overlap": 0
}
```

**`03_build_A3_lab_abnormality`** — PASS

```json
{
  "done": true,
  "finished_at": "2026-08-26T19:03:06Z",
  "n_rows_total": 500471,
  "n_rows_primary_l3": 422147,
  "n_columns": 150,
  "n_heads": 35,
  "splits_total": {
    "train": 350203,
    "val": 50240,
    "test": 100028
  },
  "coverage_pm24h_pct_primary": {
    "K": 96.38,
    "Na": 96.1,
    "creatinine": 96.37,
    "troponin": 18.9,
    "lactate": 34.57,
    "Ca": 77.21,
    "Mg": 78.73
  },
  "class_distribution_pm24h_primary_pct": {
    "K": {
      "missing": 3.625,
      "low_abnormal": 3.807,
      "high_abnormal": 7.109,
      "abnormal_unknown_direction": 0.0,
      "normal": 85.459
    },
    "Na": {
      "missing": 3.898,
      "low_abnormal": 8.873,
      "high_abnormal": 2.267,
      "abnormal_unknown_direction": 0.0,
      "normal": 84.963
    },
    "creatinine": {
      "missing": 3.634,
      "low_abnormal": 0.778,
      "high_abnormal": 31.034,
      "abnormal_unknown_direction": 0.001,
      "normal": 64.552
    },
    "troponin": {
      "missing": 81.095,
      "low_abnormal": 0.0,
      "high_abnormal": 17.672,
      "abnormal_unknown_direction": 0.0,
      "normal": 1.233
    },
    "lactate": {
      "missing": 65.429,
      "low_abnormal": 0.03,
      "high_abnormal": 10.882,
      "abnormal_unknown_direction": 0.0,
      "normal": 23.659
    },
    "Ca": {
      "missing": 22.793,
      "low_abnormal": 20.693,
      "high_abnormal": 1.478,
      "abnormal_unknown_direction": 0.0,
      "normal": 55.035
    },
    "Mg": {
      "missing": 21.269,
      "low_abnormal": 4.099,
      "high_abnormal": 2.889,
      "abnormal_unknown_direction": 0.0,
      "normal": 71.742
    }
  },
  "coverage_by_window_pct_primary": {
    "pm24h": {
      "K": 96.38,
      "Na": 96.1,
      "creatinine": 96.37,
      "troponin": 18.9,
      "lactate": 34.57,
      "Ca": 77.21,
      "Mg": 78.73
    },
    "pre_24h": {
      "K": 73.05,
      "Na": 72.69,
      "creatinine": 72.83,
      "troponin": 13.21,
      "lactate": 20.65,
      "Ca": 52.91,
      "Mg": 53.23
    },
    "post_24h": {
      "K": 80.6,
      "Na": 80.06,
      "creatinine": 80.01,
      "troponin": 14.18,
      "lactate": 22.15,
      "Ca": 66.37,
      "Mg": 68.28
    },
    "pm6h": {
      "K": 77.38,
      "Na": 76.38,
      "creatinine": 75.93,
      "troponin": 15.08,
      "lactate": 24.75,
      "Ca": 51.04,
      "Mg": 51.22
    },
    "pm12h": {
      "K": 93.58,
      "Na": 93.15,
      "creatinine": 93.29,
      "troponin": 17.1,
      "lactate": 29.22,
      "Ca": 67.95,
      "Mg": 69.49
    }
  },
  "same_hadm_coverage_pm24h_pct_primary": {
    "K": 87.31,
    "Na": 86.94,
    "creatinine": 87.17,
    "troponin": 17.61,
    "lactate": 24.1,
    "Ca": 73.58,
    "Mg": 75.34
  },
  "abnormal_method_pm24h_primary": {
    "K": {
      "ref_range": 406844,
      "no_event": 15045,
      "null_value": 257,
      "flag": 1
    },
    "troponin": {
      "no_event": 230549,
      "null_value": 111793,
      "ref_range": 79805,
      "flag": 0
    }
  },
  "n_rows": 500471,
  "n_subjects": 124602,
  "n_rows_train": 350203,
  "n_subjects_train": 87255,
  "n_rows_val": 50240,
  "n_subjects_val": 12445,
  "n_rows_test": 100028,
  "n_subjects_test": 24902,
  "subject_overlap": 0,
  "primary_n_rows": 422147,
  "primary_n_subjects": 114859,
  "primary_n_rows_train": 295236,
  "primary_n_subjects_train": 80431,
  "primary_n_rows_val": 42563,
  "primary_n_subjects_val": 11475,
  "primary_n_rows_test": 84348,
  "primary_n_subjects_test": 22953,
  "primary_subject_overlap": 0
}
```

**`04_build_A4_event_localization`** — PASS

```json
{
  "done": true,
  "finished_at": "2026-08-26T22:25:48Z",
  "n_rows_total": 749112,
  "n_rows_primary": 275045,
  "splits_total": {
    "train": 523945,
    "val": 75525,
    "test": 149642
  },
  "n_fallback_used_total": 750,
  "pct_fallback_used_total": 0.1,
  "pct_delineate_ok_total": 99.292,
  "n_peaks_mean_primary": 14.04,
  "n_peaks_median_primary": 14,
  "n_qrs_spans_mean_primary": 12.75,
  "pct_beats_with_qrs_span_primary": 90.81,
  "qrs_span_ms_median": 86.0,
  "qrs_span_ms_p05": 50.0,
  "qrs_span_ms_p95": 160.0,
  "sqi_breakdown_primary": {
    "medium": 271935,
    "high": 3110
  },
  "tolerance_samples": 5,
  "dense_masks_materialised": false,
  "n_rows": 749112,
  "n_subjects": 154092,
  "n_rows_train": 523945,
  "n_subjects_train": 107851,
  "n_rows_val": 75525,
  "n_subjects_val": 15397,
  "n_rows_test": 149642,
  "n_subjects_test": 30844,
  "subject_overlap": 0,
  "primary_n_rows": 275045,
  "primary_n_subjects": 94027,
  "primary_n_rows_train": 192082,
  "primary_n_subjects_train": 65853,
  "primary_n_rows_val": 27823,
  "primary_n_subjects_val": 9382,
  "primary_n_rows_test": 55140,
  "primary_n_subjects_test": 18792,
  "primary_subject_overlap": 0
}
```

**`05_build_A5_cross_modal_verification`** — PASS

```json
{
  "done": true,
  "finished_at": "2026-08-28T17:12:52Z",
  "n_verification_rows": 5693989,
  "verification": {
    "n_rows": 5693989,
    "n_anchors": 749112,
    "n_subjects": 154092,
    "positive_rate_pct": 26.312,
    "rows_per_neg_type": {
      "positive": 1498224,
      "HARD_NEGATIVE_TEXT": 749112,
      "IMAGE_SWAP": 749112,
      "PARTIAL_MISMATCH": 749112,
      "SIGNAL_SWAP": 749112,
      "TEXT_SWAP": 749112,
      "HARD_NEGATIVE_L2": 149549,
      "HARD_NEGATIVE_L3": 149036,
      "HARD_NEGATIVE_L4": 138581,
      "HARD_NEGATIVE_L5": 13039
    },
    "image_type_counts": {
      "clean": 4944877,
      "scanlike": 749112
    },
    "by_split": {
      "train": {
        "n_rows": 3667615,
        "n_anchors": 523945,
        "n_positive": 1047890,
        "n_negative": 2619725
      },
      "val": {
        "n_rows": 528675,
        "n_anchors": 75525,
        "n_positive": 151050,
        "n_negative": 377625
      },
      "test": {
        "n_rows": 1497699,
        "n_anchors": 149642,
        "n_positive": 299284,
        "n_negative": 1198415
      }
    }
  },
  "verification_splits": {
    "train": 3667615,
    "val": 528675,
    "test": 1497699
  },
  "masked_attribute": {
    "n_rows": 748454,
    "splits": {
      "train": 523464,
      "val": 75444,
      "test": 149546
    },
    "n_reports_changed": 331951,
    "pct_reports_changed": 44.352,
    "mean_masked_spans": 0.594,
    "max_masked_spans": 5,
    "reports_by_family": {
      "HR": 166986,
      "QRS": 106638,
      "axis": 128374,
      "QT": 37876,
      "numeric": 3788
    },
    "labels": {
      "hr_label": {
        "bradycardia": {
          "n": 112209,
          "pct": 14.992
        },
        "normal": {
          "n": 532583,
          "pct": 71.158
        },
        "tachycardia": {
          "n": 103662,
          "pct": 13.85
        }
      },
      "hr_label_by_split": {
        "train": {
          "bradycardia": 15.007,
          "normal": 71.178,
          "tachycardia": 13.815
        },
        "val": {
          "bradycardia": 15.028,
          "normal": 71.09,
          "tachycardia": 13.882
        },
        "test": {
          "bradycardia": 14.921,
          "normal": 71.122,
          "tachycardia": 13.957
        }
      },
      "qrs_label": {
        "normal": {
          "n": 481548,
          "pct": 64.339
        },
        "borderline": {
          "n": 143341,
          "pct": 19.152
        },
        "wide": {
          "n": 123565,
          "pct": 16.509
        }
      },
      "qrs_label_by_split": {
        "train": {
          "normal": 64.261,
          "borderline": 19.167,
          "wide": 16.572
        },
        "val": {
          "normal": 64.686,
          "borderline": 18.958,
          "wide": 16.355
        },
        "test": {
          "normal": 64.438,
          "borderline": 19.196,
          "wide": 16.366
        }
      },
      "qtc_label": {
        "short": {
          "n": 720,
          "pct": 0.096
        },
        "normal": {
          "n": 441981,
          "pct": 59.053
        },
        "prolonged": {
          "n": 305753,
          "pct": 40.851
        }
      },
      "qtc_label_by_split": {
        "train": {
          "short": 0.103,
          "normal": 58.9,
          "prolonged": 40.997
        },
        "val": {
          "short": 0.068,
          "normal": 59.54,
          "prolonged": 40.393
        },
        "test": {
          "short": 0.088,
          "normal": 59.34,
          "prolonged": 40.573
        }
      }
    },
    "examples": [
      {
        "study_id": 40000017,
        "original": "Sinus rhythm Leftward axis Possible anterior infarct - age undetermined Low QRS voltages in precordial leads Abnormal ECG",
        "masked": "Sinus rhythm [MASK] Possible anterior infarct - age undetermined Low QRS voltages in precordial leads Abnormal ECG",
        "families": "axis"
      },
      {
        "study_id": 40000084,
        "original": "--- Warning: Data quality may affect interpretation --- Sinus bradycardia Normal ECG except for rate",
        "masked": "--- Warning: Data quality may affect interpretation --- Sinus [MASK] Normal ECG except for rate",
        "families": "HR"
      },
      {
        "study_id": 40000089,
        "original": "SINUS RHYTHM LEFT AXIS DEVIATION Low R waves in anterior leads T wave inversion also present POSSIBLE ANTERIOR INFARCTION - AGE UNDETERMINED Inferior and latera",
        "masked": "SINUS RHYTHM [MASK] Low R waves in anterior leads T wave inversion also present POSSIBLE ANTERIOR INFARCTION - AGE UNDETERMINED Inferior and lateral ST-T change",
        "families": "axis"
      },
      {
        "study_id": 40000144,
        "original": "Sinus tachycardia Normal ECG except for rate",
        "masked": "Sinus [MASK] Normal ECG except for rate",
        "families": "HR"
      },
      {
        "study_id": 40000199,
        "original": "Sinus bradycardia Prolonged QT interval Lateral T wave changes are borderline abnormal Borderline ECG",
        "masked": "Sinus [MASK] [MASK] Lateral T wave changes are borderline abnormal Borderline ECG",
        "families": "HR,QT"
      }
    ]
  },
  "n_rows": 5693989,
  "n_subjects": 154092,
  "n_rows_train": 3667615,
  "n_subjects_train": 107851,
  "n_rows_val": 528675,
  "n_subjects_val": 15397,
  "n_rows_test": 1497699,
  "n_subjects_test": 30844,
  "subject_overlap": 0
}
```

**`06_build_A6_risk_stratification`** — PASS

```json
{
  "done": true,
  "finished_at": "2026-08-28T17:16:18Z",
  "n_rows_total": 500471,
  "n_rows_primary_l3": 422147,
  "splits_total": {
    "train": 350203,
    "val": 50240,
    "test": 100028
  },
  "n_mortality_observable_primary": 382572,
  "n_readmission_eligible_primary": 376156,
  "n_followup_ge_30d_primary": 236530,
  "n_followup_ge_90d_primary": 211119,
  "prevalence_censoring_aware_pct": {
    "readmission_30d": 27.4993,
    "readmission_90d": 42.0336
  },
  "n_ed_only_null_readmission": 45991,
  "prevalence_primary_pct": {
    "mortality_30d": 6.8467,
    "mortality_90d": 11.2274,
    "readmission_30d": 21.4081,
    "readmission_90d": 32.8986
  },
  "prevalence_primary_by_split_pct": {
    "train": {
      "mortality_30d": 6.8366,
      "mortality_90d": 11.2442,
      "readmission_30d": 21.4124,
      "readmission_90d": 32.9264
    },
    "val": {
      "mortality_30d": 6.9567,
      "mortality_90d": 11.2727,
      "readmission_30d": 21.2335,
      "readmission_90d": 32.7744
    },
    "test": {
      "mortality_30d": 6.8265,
      "mortality_90d": 11.1455,
      "readmission_30d": 21.4813,
      "readmission_90d": 32.864
    }
  },
  "boundary_flag_pct_primary": 11.451,
  "days_to_death_median_positive": 20.51,
  "days_to_readmission_median": 78.68,
  "next_admission_type_top": {
    "EW EMER.": 89438,
    "EU OBSERVATION": 40744,
    "OBSERVATION ADMIT": 40651,
    "URGENT": 18499,
    "DIRECT EMER.": 13499,
    "DIRECT OBSERVATION": 12710
  },
  "n_rows": 500471,
  "n_subjects": 124602,
  "n_rows_train": 350203,
  "n_subjects_train": 87255,
  "n_rows_val": 50240,
  "n_subjects_val": 12445,
  "n_rows_test": 100028,
  "n_subjects_test": 24902,
  "subject_overlap": 0,
  "primary_n_rows": 422147,
  "primary_n_subjects": 114859,
  "primary_n_rows_train": 295236,
  "primary_n_subjects_train": 80431,
  "primary_n_rows_val": 42563,
  "primary_n_subjects_val": 11475,
  "primary_n_rows_test": 84348,
  "primary_n_subjects_test": 22953,
  "primary_subject_overlap": 0
}
```

### Logging-hygiene checklist (Phase 1 §8.14)

- [x] Terminal showed one tqdm bar, no interleaving — workers redirect fd 1/2 into their own PID log in the pool initializer (`build_common.worker_log_init`), so no worker writes to the parent's stdout/stderr.
- [x] `aggregate.log` exists; first and last 5 lines:
(no worker logs produced -- every builder in this stage is single-process)
- [x] no `print(` in worker bodies:
```
(no match for '^\\s*print(' -- clean)
```
- [x] no `logging.basicConfig` in worker:
```
(no match for 'basicConfig' -- clean)
```
- [x] `worker_<pid>.log` files moved into `archive_<ts>/` — done by this generator, see the aggregate paths above.
- [n/a] Transport B `listener.stop()` — this stage uses Transport A (per-PID files), Phase 1 §8.3's default.
- [x] tqdm used with `mininterval=0.5` and `logging_redirect_tqdm()` — `build_common.run_chunked`:
```
549:                   mininterval=0.5, desc=desc or name)
```

- Disk free at report time: 90.7 GB on D:\

## 7. Manual test procedure

```
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/schema_validators.py
./ecg_env/Scripts/python.exe -c "import pandas as pd; d=pd.read_parquet('data/processed/tasks/A1_ecg_diagnosis/test.parquet'); print(len(d), d.columns.tolist()[:8])"
./ecg_env/Scripts/python.exe -c "import pandas as pd; d=pd.read_parquet('data/processed/tasks/A2_measurement_blind/test.parquet'); print(len(d), d.columns.tolist()[:8])"
./ecg_env/Scripts/python.exe -c "import pandas as pd; d=pd.read_parquet('data/processed/tasks/A3_lab_abnormality/test.parquet'); print(len(d), d.columns.tolist()[:8])"
./ecg_env/Scripts/python.exe -c "import pandas as pd; d=pd.read_parquet('data/processed/tasks/A4_event_localization/test.parquet'); print(len(d), d.columns.tolist()[:8])"
./ecg_env/Scripts/python.exe -c "import pandas as pd; d=pd.read_parquet('data/processed/tasks/A5_cross_modal_verification/test.parquet'); print(len(d), d.columns.tolist()[:8])"
./ecg_env/Scripts/python.exe -c "import pandas as pd; d=pd.read_parquet('data/processed/tasks/A6_risk_stratification/test.parquet'); print(len(d), d.columns.tolist()[:8])"
```

Each builder is idempotent: re-running it without `--force` is a no-op, and with `--force` it reproduces byte-identical output (§4.C invariant 2). `--dev` runs write to `data/processed/tasks/_dev/` and cannot disturb these files.

## 8. Assumptions requiring user confirmation

- **QTc source (decision 14)**  ::  A2/B1/B2/A5 define their `qtc_label` head against `machine_qtc_ms`. If the intent was genuinely the NeuroKit Bazett value, A2's primary cohort drops from 274,911 to 241,192 and the head's meaning changes. `qtc_ms_bazett` is on every row, so reversing this is a re-label, not a rebuild.
- **A6 readmission censoring (decision 15)**  ::  the readmission heads carry residual right-censoring that is reported rather than removed. If a reviewer insists on a censoring-aware primary, filter `followup_days_after_discharge >= horizon` — that drops the primary cohort by roughly 44 % and raises the 30 d rate from 21.4 % to 27.5 %.
- **A5 masking vocabulary (decision 16)**  ::  the masked-attribute head masks qualitative claims because the reports carry no numerals. If the intent was to leave the claims in place, the head becomes a text lookup for 44 % of studies.
- **A1's 12-lead image is not materialised as a separate positive row**  ::  §4.A.5.3 fixes 2 positives per anchor (clean + scan-like). The Lead-II-vs-12-lead comparison is done by resolving a different modality kind for the same `image_id` at load time. If a reviewer wants 4 positives per anchor, the verification table doubles.
