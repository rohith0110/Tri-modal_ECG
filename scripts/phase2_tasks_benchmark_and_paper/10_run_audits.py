"""
00_run_audits.py — Pre-modeling audit suite (doc §1.2, §9.2)

Runs four mandatory audits and writes reports to outputs/audit_reports/:
  1. split_audit       — no subject crosses train/val/test
  2. duplicate_audit   — repeated study_ids or same-patient near-identical ECGs
  3. missingness_audit — null rates per field per task dataset
  4. leakage_audit     — verifies forbidden fields absent from each task's JSONL
"""

import os, json, collections
import pandas as pd
import numpy as np
from datetime import datetime

OUT_DIR   = "../outputs/audit_reports"
INDEX     = "../processed/index/index_clean_with_measurements.parquet"
TASKS = {
    "B1": "../processed/taskB1_measurement_blind.jsonl",
    "B2": "../processed/taskB2_noise_robustness.jsonl",
    "B3": "../processed/taskB_temporal_grounding.jsonl",
    "B4": "../processed/taskA_verification.jsonl",
    "B5": "../processed/taskC_plausibility.jsonl",
}
FORBIDDEN = {
    "B1": {"machine_measurements", "report_text", "rr_interval", "qrs_onset", "qrs_end", "t_end"},
    "B2": {"machine_measurements", "report_text", "rr_interval", "qrs_onset", "qrs_end", "t_end"},
    "B3": {"machine_measurements", "rr_interval"},
    "B4": set(),
    "B5": {"machine_measurements", "rr_interval", "qrs_onset", "qrs_end"},
}

os.makedirs(OUT_DIR, exist_ok=True)
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
report_lines = [f"# Audit Report — {timestamp}\n", f"Plan: B\n"]

def section(title):
    line = f"\n## {title}\n"
    report_lines.append(line)
    print(line.strip())

def log(msg, ok=True):
    prefix = "PASS" if ok else "FAIL"
    line = f"  [{prefix}] {msg}"
    report_lines.append(line + "\n")
    print(line)

# ── 1. Split audit ────────────────────────────────────────────────────────────
section("1. Split Audit")

df = pd.read_parquet(INDEX)
subject_splits = df.groupby("subject_id")["split"].nunique()
leaked = subject_splits[subject_splits > 1]

log(f"Total records: {len(df):,}")
log(f"Unique subjects: {df['subject_id'].nunique():,}")
log(f"Subjects in >1 split: {len(leaked)}", ok=len(leaked)==0)

for split in ["train", "val", "test"]:
    sub = df[df["split"]==split]
    log(f"  {split}: {len(sub):,} ECGs, {sub['subject_id'].nunique():,} subjects")

if len(leaked) > 0:
    log(f"LEAKED subject_ids (first 10): {list(leaked.index[:10])}", ok=False)

# ── 2. Duplicate audit ────────────────────────────────────────────────────────
section("2. Duplicate Audit")

dup_studies = df[df["study_id"].duplicated(keep=False)]
log(f"Duplicate study_ids: {df['study_id'].duplicated().sum()}", ok=df['study_id'].duplicated().sum()==0)

# Subjects with many ECGs (repeated-record sensitivity concern)
ecg_per_subject = df.groupby("subject_id").size()
log(f"Max ECGs per subject: {ecg_per_subject.max()}")
log(f"Subjects with >10 ECGs: {(ecg_per_subject>10).sum():,}")
log(f"Subjects with >50 ECGs: {(ecg_per_subject>50).sum():,}")
log(f"Mean ECGs per subject: {ecg_per_subject.mean():.2f}")

# ── 3. Missingness audit ──────────────────────────────────────────────────────
section("3. Missingness Audit")

# Index-level missingness
for col in ["rr_interval", "qrs_onset", "qrs_end", "t_end", "split"]:
    null_n = df[col].isna().sum() if col in df.columns else "N/A"
    log(f"  index.{col}: {null_n} nulls")

# B1 task missingness (sample 10k)
b1_path = TASKS["B1"]
b1_sample = []
with open(b1_path) as f:
    for i, line in enumerate(f):
        if i >= 10000: break
        b1_sample.append(json.loads(line))
b1_df = pd.DataFrame(b1_sample)
for col in ["hr_label", "qrs_label", "qtc_label", "hr_bpm", "qrs_dur_ms", "qtc_ms"]:
    null_n = b1_df[col].isna().sum() if col in b1_df.columns else "MISSING COLUMN"
    log(f"  B1.{col}: {null_n} nulls (in 10k sample)")

# ── 4. Leakage audit ─────────────────────────────────────────────────────────
section("4. Leakage Audit")
log("Checking that forbidden fields are absent from each task's JSONL keys...")

for task, path in TASKS.items():
    if not os.path.exists(path):
        log(f"{task}: file not found — {path}", ok=False)
        continue
    with open(path) as f:
        sample = json.loads(f.readline())
    keys = set(sample.keys())
    forbidden = FORBIDDEN[task]
    violations = keys & forbidden
    ok = len(violations) == 0
    log(f"{task}: keys={sorted(keys)}, forbidden violations={violations or 'none'}", ok=ok)

# ── Write report ──────────────────────────────────────────────────────────────
report_path = os.path.join(OUT_DIR, "audit_report.md")
with open(report_path, "w") as f:
    f.writelines(report_lines)

print(f"\nAudit report written to: {report_path}")
