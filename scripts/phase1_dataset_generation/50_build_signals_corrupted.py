#!/usr/bin/env python3
"""Stage 8 (Phase 1): build data/processed/signals_corrupted.parquet.

This is the Phase 1 corruption-dataset writer split out from the legacy
phase2_tasks_benchmark_and_paper/05_task_B2_noise_robustness.py. It
writes ONLY signals_corrupted.parquet — no JSONL, no eval, no metrics.
The Plan B B2 benchmark task and its evaluation regimes stay in Phase 2.

Spec: PIPELINE_SOURCE_OF_TRUTH.md §3.11, §9.3 Stage 8, §2 storage table
row for signals_corrupted.

Schema (one row per (study_id, corruption_type, snr_db)):
    study_id        int64
    subject_id      int64
    corruption_type string  (one of: gaussian, baseline_wander, powerline,
                             emg, electrode_motion, lead_dropout,
                             gain_drift, saturation)
    snr_db          int32
    signal          list<float32>[5000]

Anchor set: 2000 anchors (test split, waveform_ok=True) per §12.1 res. 3.
Total rows: 2000 anchors x 8 corruptions x 5 SNR levels = 80_000 rows.

Deterministic seeding per §3.11:
    seed = int.from_bytes(
        hashlib.sha256(f"{study_id}|{corruption}|{snr_db}".encode()).digest()[:4],
        "big",
    ) % (2**31)

Pattern A writer with FLUSH_EVERY=10_000 per §6.2 / §7.1.

This file is a skeleton. The full implementation will be authored when
Stage 8 runs. Do NOT run it yet — Stages 0–7 must complete first.
"""

from __future__ import annotations

import hashlib

SNR_LEVELS_DB = [30, 20, 10, 5, 0]
CORRUPTIONS = (
    "gaussian",
    "baseline_wander",
    "powerline",
    "emg",
    "electrode_motion",
    "lead_dropout",
    "gain_drift",
    "saturation",
)
ANCHOR_SIZE = 2000
N_SAMPLES = 5000
FS = 500


def deterministic_seed(study_id: int, corruption: str, snr_db: int) -> int:
    """Per §3.11 — replaces non-deterministic Python hash()."""
    key = f"{study_id}|{corruption}|{snr_db}".encode("ascii")
    return int.from_bytes(hashlib.sha256(key).digest()[:4], "big") % (2**31)


def main() -> None:
    raise NotImplementedError(
        "Stage 8 has not been run yet. See PIPELINE_SOURCE_OF_TRUTH.md "
        "§9.3 Stage 8 for the full spec; this script is a skeleton."
    )


if __name__ == "__main__":
    main()
