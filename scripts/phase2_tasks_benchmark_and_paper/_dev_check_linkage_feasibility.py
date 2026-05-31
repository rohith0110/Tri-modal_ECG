"""
Quick feasibility check: how many of our ECG records have timestamps (ecg_time)
and thus could be linked to ED/hospital encounters.
Run this now; re-run after ED CSVs are downloaded to get full linkage stats.
"""
import pandas as pd
import os

DATA = r"D:\Coding\MU\Tri-Modal_ECG\data"
PROCESSED = r"D:\Coding\MU\Tri-Modal_ECG\processed"

# ── 1. Load ECG tables ────────────────────────────────────────────────────────
print("Loading record_list and machine_measurements...")
records = pd.read_csv(os.path.join(DATA, "record_list.csv"))
measurements = pd.read_csv(os.path.join(DATA, "machine_measurements.csv"))

print(f"  record_list:          {len(records):,} rows")
print(f"  machine_measurements: {len(measurements):,} rows")

# ── 2. Merge and check ecg_time coverage ─────────────────────────────────────
# record_list already has ecg_time; use measurements only for extra cols
merged = records.merge(measurements[["subject_id", "study_id", "rr_interval", "qrs_onset", "qrs_end"]],
                       on=["subject_id", "study_id"], how="left")

has_time = merged["ecg_time"].notna()
print(f"\n  ECGs with ecg_time:    {has_time.sum():,} / {len(merged):,} "
      f"({100*has_time.mean():.1f}%)")
print(f"  ECGs WITHOUT ecg_time: {(~has_time).sum():,}")

unique_subjects = merged["subject_id"].nunique()
linkable_subjects = merged[has_time]["subject_id"].nunique()
print(f"\n  Unique subjects total:    {unique_subjects:,}")
print(f"  Subjects with ecg_time:   {linkable_subjects:,}")

# ── 3. Check if our processed index subjects match ────────────────────────────
index_dir = os.path.join(PROCESSED, "index")
index_files = [f for f in os.listdir(index_dir) if f.endswith(".csv") or f.endswith(".parquet")]
if index_files:
    print(f"\n  Found index files: {index_files}")
    for f in index_files[:2]:
        path = os.path.join(index_dir, f)
        if f.endswith(".parquet"):
            idx = pd.read_parquet(path)
        else:
            idx = pd.read_csv(path)
        print(f"\n  Index file '{f}': {len(idx):,} rows, columns: {list(idx.columns)}")
        if "subject_id" in idx.columns:
            idx_subjects = set(idx["subject_id"].unique())
            ecg_subjects = set(merged["subject_id"].unique())
            overlap = idx_subjects & ecg_subjects
            print(f"    Subjects in index:      {len(idx_subjects):,}")
            print(f"    Overlap with ECG data:  {len(overlap):,}")

# ── 4. If ED tables exist, run overlap check ──────────────────────────────────
ed_path_options = [
    os.path.join(DATA, "ED", "edstays.csv"),
    os.path.join(DATA, "ED", "ed", "edstays.csv"),
    os.path.join(DATA, "edstays.csv"),
]
edstays_path = next((p for p in ed_path_options if os.path.exists(p)), None)

if edstays_path:
    print(f"\n  Found edstays at: {edstays_path}")
    edstays = pd.read_csv(edstays_path, parse_dates=["intime", "outtime"])
    print(f"  edstays rows: {len(edstays):,}, unique subjects: {edstays['subject_id'].nunique():,}")

    ecg_with_time = merged[has_time].copy()
    ecg_with_time["ecg_time"] = pd.to_datetime(ecg_with_time["ecg_time"])

    joined = ecg_with_time.merge(edstays[["subject_id", "stay_id", "intime", "outtime"]],
                                  on="subject_id", how="inner")
    exact_overlap = joined[
        (joined["ecg_time"] >= joined["intime"]) &
        (joined["ecg_time"] <= joined["outtime"])
    ]
    print(f"\n  ECG-ED exact overlap (ecg_time within ED stay):")
    print(f"    Matched ECGs:     {exact_overlap['study_id'].nunique():,}")
    print(f"    Matched subjects: {exact_overlap['subject_id'].nunique():,}")
    pct = 100 * exact_overlap['study_id'].nunique() / has_time.sum()
    print(f"    % of timestamped ECGs linked: {pct:.1f}%")
    print(f"\n  --> Plan A (ED-linked) is {'VIABLE' if pct >= 15 else 'LIMITED'} at {pct:.1f}% linkage")
else:
    print("\n  ED tables not found yet. Download edstays.csv from PhysioNet to get full linkage stats.")
    print("  --> Cannot assess Plan A viability until ED data is available.")
    pct = 0

# ── 5. Summary ────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print(f"  Total ECGs:                {len(merged):,}")
print(f"  ECGs with timestamp:       {has_time.sum():,} ({100*has_time.mean():.1f}%)")
print(f"  ED tables available:       {'YES' if edstays_path else 'NO — download needed'}")
if edstays_path:
    print(f"  ED-linked ECGs:            {exact_overlap['study_id'].nunique():,} ({pct:.1f}%)")
    print(f"  Plan A viable:             {'YES' if pct >= 15 else 'MARGINAL/NO'}")
print(f"  Plan B viable (no EHR):    YES (always)")
