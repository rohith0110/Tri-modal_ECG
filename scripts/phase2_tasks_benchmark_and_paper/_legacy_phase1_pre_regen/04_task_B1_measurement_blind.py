"""
task_B1.py — Measurement-Blind Inference Dataset (Plan B, Task 1)

For each ECG in the clean index, pairs the raw signal path with binned
physiological targets derived solely from machine measurements.
Models must predict these targets from waveform only — no text, no structured
features allowed as inputs.

Targets:
  hr_label   : bradycardia / normal / tachycardia
  qrs_label  : normal / borderline / wide
  qtc_label  : short / normal / prolonged  (Bazett formula)

Sentinel filtering: rr_interval=65535 and fiducial=29999 are MIMIC null markers.
"""

import os
import json
import math
import time
import numpy as np
import pandas as pd
from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────────────────────

INDEX_PATH  = "../processed/index/index_clean_with_measurements.parquet"
SIGNAL_DIR  = "../processed/signals_lead2"
OUT_PATH    = "../processed/taskB1_measurement_blind.jsonl"

# Clinical validity windows (excludes sentinels and implausible values)
RR_MIN, RR_MAX       = 250, 2500    # ms  → HR 24–240 bpm
QRS_DUR_MIN          = 40           # ms  (qrs_end - qrs_onset)
QRS_DUR_MAX          = 400          # ms
T_END_MAX            = 29000        # ms  (29999 = sentinel)
QTC_MIN, QTC_MAX     = 200, 800     # ms  (hard physiological limits)

# ── Binning functions ─────────────────────────────────────────────────────────

def hr_label(rr_ms):
    hr = 60000.0 / rr_ms
    if hr < 60:   return "bradycardia"
    if hr <= 100: return "normal"
    return "tachycardia"

def qrs_label(qrs_dur_ms):
    if qrs_dur_ms < 120:  return "normal"
    if qrs_dur_ms <= 150: return "borderline"
    return "wide"

def qtc_label(qtc_ms):
    if qtc_ms < 350:  return "short"
    if qtc_ms <= 450: return "normal"
    return "prolonged"

# ── Load index ────────────────────────────────────────────────────────────────

print("=" * 60)
print("TASK B1: MEASUREMENT-BLIND INFERENCE DATASET")
print("=" * 60)

t0 = time.time()
df = pd.read_parquet(INDEX_PATH)
print(f"Index loaded: {len(df):,} records")

# ── Filter valid measurements ─────────────────────────────────────────────────

valid = (
    df["rr_interval"].between(RR_MIN, RR_MAX) &
    df["qrs_onset"].lt(T_END_MAX) &
    df["qrs_end"].lt(T_END_MAX) &
    (df["qrs_end"] - df["qrs_onset"]).between(QRS_DUR_MIN, QRS_DUR_MAX) &
    df["t_end"].lt(T_END_MAX) &
    df["t_end"].gt(df["qrs_onset"])
)

df_valid = df[valid].copy()
print(f"Valid measurements:  {len(df_valid):,} / {len(df):,} "
      f"({100*len(df_valid)/len(df):.1f}%)")

# ── Compute derived measurements ──────────────────────────────────────────────

df_valid["hr_bpm"]     = 60000.0 / df_valid["rr_interval"]
df_valid["qrs_dur_ms"] = df_valid["qrs_end"] - df_valid["qrs_onset"]
df_valid["qt_ms"]      = df_valid["t_end"]   - df_valid["qrs_onset"]
df_valid["qtc_ms"]     = df_valid["qt_ms"] / np.sqrt(df_valid["rr_interval"] / 1000.0)

# Filter implausible QTc
df_valid = df_valid[df_valid["qtc_ms"].between(QTC_MIN, QTC_MAX)]
print(f"After QTc filter:    {len(df_valid):,}")

# ── Build JSONL ───────────────────────────────────────────────────────────────

print("\nGenerating JSONL...")
written = 0
skipped_no_signal = 0

label_counts = {
    "hr":  {"bradycardia": 0, "normal": 0, "tachycardia": 0},
    "qrs": {"normal": 0, "borderline": 0, "wide": 0},
    "qtc": {"short": 0, "normal": 0, "prolonged": 0},
}

with open(OUT_PATH, "w") as fout:
    for row in tqdm(df_valid.itertuples(), total=len(df_valid)):
        signal_path = os.path.join(SIGNAL_DIR, f"{row.study_id}.npy")
        if not os.path.exists(signal_path):
            skipped_no_signal += 1
            continue

        hl = hr_label(row.rr_interval)
        ql = qrs_label(row.qrs_dur_ms)
        cl = qtc_label(row.qtc_ms)

        label_counts["hr"][hl]  += 1
        label_counts["qrs"][ql] += 1
        label_counts["qtc"][cl] += 1

        record = {
            "study_id":    int(row.study_id),
            "subject_id":  int(row.subject_id),
            "signal_path": signal_path,
            "split":       row.split,
            # Labels (model targets)
            "hr_label":    hl,
            "qrs_label":   ql,
            "qtc_label":   cl,
            # Continuous values (for regression evaluation / auditing)
            "hr_bpm":      round(float(row.hr_bpm), 2),
            "qrs_dur_ms":  round(float(row.qrs_dur_ms), 1),
            "qtc_ms":      round(float(row.qtc_ms), 1),
        }
        fout.write(json.dumps(record) + "\n")
        written += 1

# ── Summary ───────────────────────────────────────────────────────────────────

elapsed = time.time() - t0
print(f"\n{'='*60}")
print(f"TASK B1 COMPLETE  ({elapsed:.1f}s)")
print(f"{'='*60}")
print(f"Written:         {written:,}")
print(f"Skipped (no .npy): {skipped_no_signal:,}")
print(f"Output:          {OUT_PATH}")

print("\nLabel distribution:")
for task, counts in label_counts.items():
    total = sum(counts.values())
    print(f"  {task}:")
    for label, n in counts.items():
        print(f"    {label:15s}: {n:>8,}  ({100*n/total:.1f}%)")

split_counts = df_valid["split"].value_counts()
print(f"\nSplit breakdown (of valid records):")
for split, n in split_counts.items():
    print(f"  {split}: {n:,}")
