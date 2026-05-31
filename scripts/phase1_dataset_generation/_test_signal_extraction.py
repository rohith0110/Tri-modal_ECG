import pandas as pd
import wfdb
import numpy as np
import os

INDEX_PATH = "../processed/index/index_with_split.parquet"
DATA_ROOT = "../Data"

OUTPUT_DIR = "../processed/signals_lead2_test"
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Loading dataset index...")
df = pd.read_parquet(INDEX_PATH)

print("Selecting 10 random ECG studies...")
sample = df.sample(10, random_state=42)

print(sample[["study_id", "path"]])

for _, row in sample.iterrows():

    study_id = row.study_id
    record_path = os.path.join(DATA_ROOT, row.path)

    print("\nProcessing:", study_id)

    try:
        record = wfdb.rdrecord(record_path)

        leads = record.sig_name

        if "II" not in leads:
            print("Lead II missing — skipping")
            continue

        lead_index = leads.index("II")

        signal = record.p_signal[:, lead_index]

        print("Signal length:", len(signal))
        print("Sampling rate:", record.fs)

        if len(signal) != 5000:
            print("⚠ Unexpected length — skipping")
            continue

        out_path = os.path.join(OUTPUT_DIR, f"{study_id}.npy")

        np.save(out_path, signal)

        print("Saved:", out_path)

    except Exception as e:
        print("Failed:", e)

print("\nSanity test completed.")
