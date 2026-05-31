import pandas as pd
import json
import numpy as np
import os

INDEX_PATH = "../processed/index/index.parquet"
OUTPUT_INDEX = "../processed/index/index_with_split.parquet"
OUTPUT_SPLITS = "../processed/index/splits.json"

print("Loading master index...")
df = pd.read_parquet(INDEX_PATH)

print("Total ECG studies:", len(df))

# ---------------------------------------------------
# Step 1: Get unique patients
# ---------------------------------------------------

subjects = df["subject_id"].unique()
print("Total unique patients:", len(subjects))

# ---------------------------------------------------
# Step 2: Shuffle patients (reproducible)
# ---------------------------------------------------

np.random.seed(42)
np.random.shuffle(subjects)

n = len(subjects)

# ---------------------------------------------------
# Step 3: Split patients 80 / 10 / 10
# ---------------------------------------------------

train_sub = subjects[:int(0.8*n)]
val_sub   = subjects[int(0.8*n):int(0.9*n)]
test_sub  = subjects[int(0.9*n):]

print("\nPatient split:")
print("Train subjects:", len(train_sub))
print("Val subjects:", len(val_sub))
print("Test subjects:", len(test_sub))

# ---------------------------------------------------
# Step 4: Map patient split to ECG rows
# ---------------------------------------------------

split_map = {}

for s in train_sub:
    split_map[int(s)] = "train"

for s in val_sub:
    split_map[int(s)] = "val"

for s in test_sub:
    split_map[int(s)] = "test"

df["split"] = df["subject_id"].map(split_map)

# ---------------------------------------------------
# Step 5: Safety check — ensure no missing splits
# ---------------------------------------------------

missing = df["split"].isna().sum()
print("\nRows missing split assignment:", missing)

if missing > 0:
    raise ValueError("Some rows did not receive a split assignment!")

# ---------------------------------------------------
# Step 6: Save new index
# ---------------------------------------------------

os.makedirs("../processed/index", exist_ok=True)

df.to_parquet(OUTPUT_INDEX)

print("\nSaved:", OUTPUT_INDEX)

# ---------------------------------------------------
# Step 7: Save split metadata
# ---------------------------------------------------

with open(OUTPUT_SPLITS, "w") as f:
    json.dump({
        "train_subjects": train_sub.tolist(),
        "val_subjects": val_sub.tolist(),
        "test_subjects": test_sub.tolist()
    }, f, indent=2)

print("Saved:", OUTPUT_SPLITS)

# ---------------------------------------------------
# Step 8: ECG distribution check
# ---------------------------------------------------

print("\nECG distribution:")
print(df["split"].value_counts())

# ---------------------------------------------------
# Step 9: Patient leakage check
# ---------------------------------------------------

train = set(df[df.split=="train"].subject_id)
val   = set(df[df.split=="val"].subject_id)
test  = set(df[df.split=="test"].subject_id)

print("\nLeakage checks (should all be 0):")
print("Train ∩ Val :", len(train & val))
print("Train ∩ Test:", len(train & test))
print("Val ∩ Test  :", len(val & test))

print("\nStep B verification complete.")