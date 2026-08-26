"""Pick a small set of representative study IDs for the report figures.

We need at least one study per clinical bucket so the report can show
condition-specific evidence next to every claim:
  - bradycardia (HR < 60)
  - normal_low (60 <= HR < 80)
  - normal_high (80 <= HR < 100)
  - tachycardia (HR >= 100)
  - wide_qrs (QRS duration > 120 ms)
  - left_axis (QRS axis < -30)
  - right_axis (QRS axis > 90)
  - normal_axis
We deliberately pick studies that already have clean PNG and signal .npy
on disk so the downstream plotting script is guaranteed to find them.
"""

import json
import os
import pandas as pd
import numpy as np

ROOT = "D:/Coding/MU/Tri-Modal_ECG"
INDEX = os.path.join(ROOT, "processed", "index", "index_clean_with_measurements.parquet")
CLEAN_DIR = os.path.join(ROOT, "processed", "images_clean")
SCAN_DIR = os.path.join(ROOT, "processed", "images_scanlike")
SIG2_DIR = os.path.join(ROOT, "processed", "signals_lead2")
SIG12_DIR = os.path.join(ROOT, "processed", "signals_12lead")
OUT = os.path.join(ROOT, "report_assets", "examples.json")

df = pd.read_parquet(INDEX)
print("rows", len(df))
print(df.columns.tolist())

df = df.copy()
df["hr"] = 60000.0 / df["rr_interval"].replace(0, np.nan)
df["qrs_dur"] = df["qrs_end"] - df["qrs_onset"]

# Drop unphysiological rows (sentinel values like 29999, negative durations, etc.)
sane = (
    df["rr_interval"].between(300, 2000)
    & df["qrs_dur"].between(40, 250)
    & df["qrs_axis"].between(-180, 180)
    & df["p_axis"].between(-180, 180)
    & df["t_axis"].between(-180, 180)
)
df = df[sane].reset_index(drop=True)
print("rows after sanity filter", len(df))


def assets_exist(sid):
    return (
        os.path.exists(os.path.join(CLEAN_DIR, f"{sid}.png"))
        and os.path.exists(os.path.join(SCAN_DIR, f"{sid}.jpg"))
        and os.path.exists(os.path.join(SIG2_DIR, f"{sid}.npy"))
        and os.path.exists(os.path.join(SIG12_DIR, f"{sid}.npy"))
    )


def pick(mask, k=20):
    sub = df[mask].head(2000)
    for _, row in sub.iterrows():
        if assets_exist(int(row["study_id"])):
            return row
    return None


examples = {}

# heart-rate buckets
examples["bradycardia"] = pick((df["hr"] < 55) & (df["hr"] > 35))
examples["normal_low"] = pick((df["hr"] >= 65) & (df["hr"] < 75))
examples["normal_high"] = pick((df["hr"] >= 85) & (df["hr"] < 95))
examples["tachycardia"] = pick((df["hr"] >= 110) & (df["hr"] < 140))
# QRS duration
examples["wide_qrs"] = pick(df["qrs_dur"] > 130)
examples["normal_qrs"] = pick((df["qrs_dur"] >= 80) & (df["qrs_dur"] <= 100))
# axis
examples["left_axis"] = pick(df["qrs_axis"] < -45)
examples["right_axis"] = pick(df["qrs_axis"] > 100)
examples["normal_axis"] = pick((df["qrs_axis"] >= 0) & (df["qrs_axis"] <= 60))

out = {}
for k, row in examples.items():
    if row is None:
        print("NO MATCH for", k)
        continue
    out[k] = {
        "study_id": int(row["study_id"]),
        "subject_id": int(row["subject_id"]),
        "rr_interval": float(row["rr_interval"]) if pd.notna(row["rr_interval"]) else None,
        "hr": float(row["hr"]) if pd.notna(row["hr"]) else None,
        "qrs_onset": float(row["qrs_onset"]) if pd.notna(row["qrs_onset"]) else None,
        "qrs_end": float(row["qrs_end"]) if pd.notna(row["qrs_end"]) else None,
        "qrs_dur": float(row["qrs_dur"]) if pd.notna(row["qrs_dur"]) else None,
        "qrs_axis": float(row["qrs_axis"]) if pd.notna(row["qrs_axis"]) else None,
        "p_axis": float(row["p_axis"]) if pd.notna(row["p_axis"]) else None,
        "t_axis": float(row["t_axis"]) if pd.notna(row["t_axis"]) else None,
        "split": str(row["split"]),
        "T_machine": str(row["T_machine"])[:300],
    }
    print(k, out[k]["study_id"], "hr=", out[k]["hr"], "qrs=", out[k]["qrs_dur"], "axis=", out[k]["qrs_axis"])

with open(OUT, "w") as f:
    json.dump(out, f, indent=2)
print("wrote", OUT)
