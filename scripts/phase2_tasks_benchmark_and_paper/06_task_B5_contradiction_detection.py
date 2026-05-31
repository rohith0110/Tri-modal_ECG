"""
task_B5_rebuild.py — Rebuild B5 contradiction detection to match doc §6.6 spec.

Doc requires per-record fields:
  study_id, subject_id, split,
  original_report_text, corrupted_report_text,
  contradiction_type, corrupted_span_start, corrupted_span_end,
  source_measurement, is_corrupted (bool), label (clean/corrupted)

Safe injection rules (doc §6.6):
  - HR <= 50: bradycardia → tachycardia flip
  - HR >= 120: tachycardia → bradycardia flip
  - Do NOT inject if 58 < HR < 105 (too close to boundary)
  - Balance: 50% clean, 50% corrupted
"""

import os, json, re, random
import pandas as pd
import numpy as np
from tqdm import tqdm

INDEX_PATH = "../processed/index/index_clean_with_measurements.parquet"
MEAS_PATH  = "../data/machine_measurements.csv"
OUT_PATH   = "../processed/taskB5_contradiction_detection.jsonl"

random.seed(42)
np.random.seed(42)

HR_BRADY_MAX  = 50    # safe to flip to tachy
HR_TACHY_MIN  = 120   # safe to flip to brady

# ── Load data ─────────────────────────────────────────────────────────────────
print("Loading index and measurements...")
df = pd.read_parquet(INDEX_PATH)
meas = pd.read_csv(MEAS_PATH, low_memory=False)

# Build report text per study
report_cols = [f"report_{i}" for i in range(18)]
avail_cols = [c for c in report_cols if c in meas.columns]
meas["report_text"] = meas[avail_cols].fillna("").apply(
    lambda row: " ".join(x.strip() for x in row if x.strip()), axis=1
)
meas["hr"] = 60000.0 / meas["rr_interval"].replace(0, np.nan)

# Merge
merged = df.merge(
    meas[["study_id", "subject_id", "report_text", "hr", "rr_interval"]],
    on=["study_id", "subject_id"], how="inner"
)
merged = merged[merged["report_text"].str.len() > 10]

# ── Contradiction injection helpers ───────────────────────────────────────────

BRADY_PATTERNS = [
    r"\bbradycardia\b", r"\bbradycardic\b", r"\bbradyarrhythmia\b"
]
TACHY_PATTERNS = [
    r"\btachycardia\b", r"\btachycardic\b", r"\btachyarrhythmia\b"
]

def find_span(text, patterns):
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.start(), m.end(), m.group()
    return None, None, None

def inject_contradiction(text, hr, rng_local):
    """Return (corrupted_text, contradiction_type, span_start, span_end) or None."""
    if hr <= HR_BRADY_MAX:
        # Should say brady — flip to tachy
        start, end, match = find_span(text, BRADY_PATTERNS)
        if start is not None:
            replacement = re.sub(r"brady", "tachy", match, flags=re.IGNORECASE)
            corrupted = text[:start] + replacement + text[end:]
            return corrupted, "brady_to_tachy", start, end
    elif hr >= HR_TACHY_MIN:
        # Should say tachy — flip to brady
        start, end, match = find_span(text, TACHY_PATTERNS)
        if start is not None:
            replacement = re.sub(r"tachy", "brady", match, flags=re.IGNORECASE)
            corrupted = text[:start] + replacement + text[end:]
            return corrupted, "tachy_to_brady", start, end
    return None

# ── Find injectable candidates ────────────────────────────────────────────────
print("Finding injectable candidates...")

brady_cands = merged[merged["hr"] <= HR_BRADY_MAX].copy()
tachy_cands = merged[merged["hr"] >= HR_TACHY_MIN].copy()

# Only keep those that actually contain the expected term in their report
injectable = []
for _, row in tqdm(brady_cands.iterrows(), total=len(brady_cands), desc="Brady cands"):
    s, e, _ = find_span(row["report_text"], BRADY_PATTERNS)
    if s is not None:
        injectable.append(("brady_to_tachy", row))

for _, row in tqdm(tachy_cands.iterrows(), total=len(tachy_cands), desc="Tachy cands"):
    s, e, _ = find_span(row["report_text"], TACHY_PATTERNS)
    if s is not None:
        injectable.append(("tachy_to_brady", row))

print(f"Injectable candidates: {len(injectable):,}")

# ── Build balanced dataset ────────────────────────────────────────────────────
# 50% corrupted (from injectable), 50% clean (random sample from all)
random.shuffle(injectable)
n_corrupted = min(len(injectable), 200000)   # cap at 200K corrupted
injectable = injectable[:n_corrupted]

# Clean sample — avoid subjects used in corrupted set
corrupted_subjects = set(row["subject_id"] for _, row in injectable)
clean_pool = merged[~merged["subject_id"].isin(corrupted_subjects)]
clean_sample = clean_pool.sample(n=n_corrupted, random_state=42, replace=len(clean_pool) < n_corrupted)

print(f"Corrupted examples: {n_corrupted:,}")
print(f"Clean examples:     {len(clean_sample):,}")

records = []

# Corrupted records
for ctype, row in tqdm(injectable, desc="Building corrupted"):
    rng_local = random.Random(int(row["study_id"]))
    result = inject_contradiction(row["report_text"], row["hr"], rng_local)
    if result is None:
        continue
    corrupted_text, ctype_out, span_s, span_e = result
    records.append({
        "study_id":              int(row["study_id"]),
        "subject_id":            int(row["subject_id"]),
        "split":                 row["split"],
        "original_report_text":  row["report_text"],
        "corrupted_report_text": corrupted_text,
        "contradiction_type":    ctype_out,
        "corrupted_span_start":  span_s,
        "corrupted_span_end":    span_e,
        "source_measurement":    f"hr={row['hr']:.1f}",
        "is_corrupted":          True,
        "label":                 "corrupted",
    })

# Clean records
for _, row in tqdm(clean_sample.iterrows(), total=len(clean_sample), desc="Building clean"):
    records.append({
        "study_id":              int(row["study_id"]),
        "subject_id":            int(row["subject_id"]),
        "split":                 row["split"],
        "original_report_text":  row["report_text"],
        "corrupted_report_text": row["report_text"],   # same — no corruption
        "contradiction_type":    "none",
        "corrupted_span_start":  None,
        "corrupted_span_end":    None,
        "source_measurement":    f"hr={row['hr']:.1f}" if pd.notna(row["hr"]) else "hr=NA",
        "is_corrupted":          False,
        "label":                 "clean",
    })

random.shuffle(records)

# ── Write JSONL ───────────────────────────────────────────────────────────────
print(f"Writing {len(records):,} records...")
with open(OUT_PATH, "w") as f:
    for rec in records:
        f.write(json.dumps(rec) + "\n")

corrupted_n = sum(1 for r in records if r["is_corrupted"])
clean_n     = sum(1 for r in records if not r["is_corrupted"])
brady_n     = sum(1 for r in records if r["contradiction_type"] == "brady_to_tachy")
tachy_n     = sum(1 for r in records if r["contradiction_type"] == "tachy_to_brady")

print(f"\n{'='*60}")
print(f"B5 REBUILD COMPLETE")
print(f"{'='*60}")
print(f"Total records:    {len(records):,}")
print(f"  Corrupted:      {corrupted_n:,} ({100*corrupted_n/len(records):.1f}%)")
print(f"  Clean:          {clean_n:,} ({100*clean_n/len(records):.1f}%)")
print(f"  brady->tachy:   {brady_n:,}")
print(f"  tachy->brady:   {tachy_n:,}")
print(f"Output: {OUT_PATH}")
