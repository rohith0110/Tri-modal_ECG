"""
08_neurokit2_baseline_B1.py — Algorithmic baseline for Task B1 (doc §6.2)

Uses NeuroKit2 R-peak detector to estimate HR and QRS duration from raw signal.
Compares against machine-measurement labels in taskB1_measurement_blind.jsonl.
No model training — pure signal processing baseline.

Metrics: accuracy, F1, AUPRC per class (hr_label, qrs_label)
"""

import os, json
import numpy as np
import pandas as pd
from tqdm import tqdm
from sklearn.metrics import (accuracy_score, f1_score, classification_report,
                             average_precision_score, roc_auc_score)
from sklearn.preprocessing import label_binarize

try:
    import neurokit2 as nk
    NK_OK = True
except ImportError:
    NK_OK = False
    print("WARNING: neurokit2 not installed. Run: pip install neurokit2")
    exit(1)

FS           = 500
B1_PATH      = "../processed/taskB1_measurement_blind.jsonl"
OUT_PATH     = "../outputs/tables/B1_neurokit2_baseline.json"
SPLIT        = "test"
MAX_RECORDS  = 5000   # representative test subset for speed

os.makedirs("../outputs/tables", exist_ok=True)

# ── Label definitions ────────────────────────────────────────────────────────

def predict_hr_label(rr_ms):
    if rr_ms is None or np.isnan(rr_ms) or rr_ms <= 0:
        return None
    hr = 60000.0 / rr_ms
    if hr < 60:   return "bradycardia"
    if hr <= 100: return "normal"
    return "tachycardia"

def predict_qrs_label(qrs_dur_ms):
    if qrs_dur_ms is None or np.isnan(qrs_dur_ms) or qrs_dur_ms <= 0:
        return None
    if qrs_dur_ms < 120:  return "normal"
    if qrs_dur_ms <= 150: return "borderline"
    return "wide"

# ── Load test records ─────────────────────────────────────────────────────────

print(f"Loading B1 test records (split={SPLIT})...")
records = []
with open(B1_PATH) as f:
    for line in f:
        rec = json.loads(line)
        if rec["split"] == SPLIT:
            records.append(rec)
            if MAX_RECORDS and len(records) >= MAX_RECORDS:
                break

print(f"  Test records: {len(records):,}")

# ── Run NeuroKit2 on each signal ──────────────────────────────────────────────

y_true_hr, y_pred_hr   = [], []
y_true_qrs, y_pred_qrs = [], []
failed = 0

for rec in tqdm(records, desc="NK2 inference"):
    try:
        sig = np.load(rec["signal_path"])
        if len(sig) != 5000:
            failed += 1
            continue

        # R-peak detection
        _, info = nk.ecg_peaks(sig, sampling_rate=FS, method="neurokit")
        rpeaks = info["ECG_R_Peaks"]

        if len(rpeaks) < 2:
            failed += 1
            continue

        # HR from median RR interval
        rr_intervals = np.diff(rpeaks) / FS * 1000  # ms
        median_rr = np.median(rr_intervals)
        pred_hr = predict_hr_label(median_rr)

        # QRS duration from delineation
        try:
            waves = nk.ecg_delineate(sig, rpeaks, sampling_rate=FS, method="dwt")[1]
            q_onsets  = waves.get("ECG_Q_Onsets", [])
            s_offsets = waves.get("ECG_S_Offsets", [])
            valid_qrs = [(on, off) for on, off in zip(q_onsets, s_offsets)
                         if on is not None and off is not None and not np.isnan(on) and not np.isnan(off)]
            if valid_qrs:
                qrs_durs = [(off - on) / FS * 1000 for on, off in valid_qrs]
                median_qrs = np.median(qrs_durs)
                pred_qrs = predict_qrs_label(median_qrs)
            else:
                pred_qrs = None
        except Exception:
            pred_qrs = None

        if pred_hr is not None:
            y_true_hr.append(rec["hr_label"])
            y_pred_hr.append(pred_hr)

        if pred_qrs is not None:
            y_true_qrs.append(rec["qrs_label"])
            y_pred_qrs.append(pred_qrs)

    except Exception:
        failed += 1

print(f"\nProcessed: {len(y_true_hr):,} HR, {len(y_true_qrs):,} QRS | Failed: {failed:,}")

# ── Evaluate ──────────────────────────────────────────────────────────────────

results = {"split": SPLIT, "n_records": len(records), "failed": failed}

def evaluate_task(y_true, y_pred, classes, task_name):
    if not y_true:
        print(f"{task_name}: no predictions")
        return {}
    acc = accuracy_score(y_true, y_pred)
    f1  = f1_score(y_true, y_pred, average="macro", zero_division=0)
    print(f"\n{task_name}:")
    print(f"  Accuracy: {acc:.4f}  Macro-F1: {f1:.4f}")
    print(classification_report(y_true, y_pred, labels=classes, zero_division=0))
    return {"accuracy": acc, "macro_f1": f1, "n": len(y_true)}

results["hr"]  = evaluate_task(y_true_hr,  y_pred_hr,  ["bradycardia","normal","tachycardia"], "HR (B1)")
results["qrs"] = evaluate_task(y_true_qrs, y_pred_qrs, ["normal","borderline","wide"], "QRS (B1)")

with open(OUT_PATH, "w") as f:
    json.dump(results, f, indent=2)

print(f"\nResults saved: {OUT_PATH}")
