import os
import json
import random
import time
import pandas as pd
from tqdm import tqdm
from collections import defaultdict

INDEX_PATH = "../processed/index/index_clean_with_measurements.parquet"
OUT_PATH = "../processed/taskA_verification.jsonl"

random.seed(42)

print("=" * 60)
print("TASK A DATASET GENERATION (SPEC COMPLIANT)")
print("=" * 60)

start = time.time()

df = pd.read_parquet(INDEX_PATH)

print("Studies:", len(df))

study_ids = df.study_id.tolist()

# -------------------------
# Build lookup dictionaries
# -------------------------

split_map = dict(zip(df.study_id, df.split))
subject_map = dict(zip(df.study_id, df.subject_id))
rr_map = dict(zip(df.study_id, df.rr_interval))


# -------------------------
# HR bucket function
# -------------------------


def hr_bucket(rr):

    if pd.isna(rr) or rr <= 0:
        return None

    hr = 60000 / rr

    if hr < 60:
        return "brady"
    elif hr < 80:
        return "normal_low"
    elif hr < 100:
        return "normal_high"
    else:
        return "tachy"


# -------------------------
# Build HR bucket groups
# -------------------------

bucket_groups = defaultdict(list)

for sid, rr in rr_map.items():

    b = hr_bucket(rr)

    if b is not None:
        bucket_groups[b].append(sid)


print("HR buckets built")

# -------------------------
# Generation
# -------------------------

pos_count = 0
neg_count = 0

with open(OUT_PATH, "w") as f:

    for sid in tqdm(study_ids):

        split = split_map[sid]

        # --------------------
        # POSITIVES
        # --------------------

        pos_clean = {
            "anchor_study_id": int(sid),
            "signal_id": int(sid),
            "image_id": int(sid),
            "text_id": int(sid),
            "image_type": "clean",
            "y_match": 1,
            "neg_type": None,
            "split": split,
        }

        pos_scan = {
            "anchor_study_id": int(sid),
            "signal_id": int(sid),
            "image_id": int(sid),
            "text_id": int(sid),
            "image_type": "scanlike",
            "y_match": 1,
            "neg_type": None,
            "split": split,
        }

        f.write(json.dumps(pos_clean) + "\n")
        f.write(json.dumps(pos_scan) + "\n")

        pos_count += 2

        # choose random different study
        sid2 = sid
        while sid2 == sid:
            sid2 = random.choice(study_ids)

        # --------------------
        # TEXT_SWAP
        # --------------------

        text_swap = {
            "anchor_study_id": int(sid),
            "signal_id": int(sid),
            "image_id": int(sid),
            "text_id": int(sid2),
            "image_type": "clean",
            "y_match": 0,
            "neg_type": "TEXT_SWAP",
            "split": split,
        }

        # --------------------
        # IMAGE_SWAP
        # --------------------

        image_swap = {
            "anchor_study_id": int(sid),
            "signal_id": int(sid),
            "image_id": int(sid2),
            "text_id": int(sid),
            "image_type": "clean",
            "y_match": 0,
            "neg_type": "IMAGE_SWAP",
            "split": split,
        }

        # --------------------
        # SIGNAL_SWAP
        # --------------------

        signal_swap = {
            "anchor_study_id": int(sid),
            "signal_id": int(sid2),
            "image_id": int(sid),
            "text_id": int(sid),
            "image_type": "clean",
            "y_match": 0,
            "neg_type": "SIGNAL_SWAP",
            "split": split,
        }

        f.write(json.dumps(text_swap) + "\n")
        f.write(json.dumps(image_swap) + "\n")
        f.write(json.dumps(signal_swap) + "\n")

        neg_count += 3

        # --------------------
        # HARD_NEGATIVE_TEXT
        # --------------------

        bucket = hr_bucket(rr_map[sid])

        if bucket and len(bucket_groups[bucket]) > 1:

            sid3 = sid

            while sid3 == sid:
                sid3 = random.choice(bucket_groups[bucket])

            hard_text = {
                "anchor_study_id": int(sid),
                "signal_id": int(sid),
                "image_id": int(sid),
                "text_id": int(sid3),
                "image_type": "clean",
                "y_match": 0,
                "neg_type": "HARD_NEGATIVE_TEXT",
                "split": split,
            }

            f.write(json.dumps(hard_text) + "\n")

            neg_count += 1

        # --------------------
        # PARTIAL_MISMATCH
        # --------------------

        partial = {
            "anchor_study_id": int(sid),
            "signal_id": int(sid),
            "image_id": int(sid2),
            "text_id": int(sid2),
            "image_type": "clean",
            "y_match": 0,
            "neg_type": "PARTIAL_MISMATCH",
            "split": split,
        }

        f.write(json.dumps(partial) + "\n")

        neg_count += 1


elapsed = time.time() - start

print("\n" + "=" * 60)
print("DATASET BUILD COMPLETE")
print("=" * 60)

print("Positives:", pos_count)
print("Negatives:", neg_count)
print("Total samples:", pos_count + neg_count)

size = os.path.getsize(OUT_PATH) / (1024**3)

print("Output file:", OUT_PATH)
print("Size:", round(size, 2), "GB")
print("Time:", round(elapsed / 60, 2), "minutes")
