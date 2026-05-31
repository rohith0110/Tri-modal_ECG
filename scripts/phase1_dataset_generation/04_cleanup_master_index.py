import json
import os
import pandas as pd

INDEX_PATH = "../processed/index/index_with_split.parquet"
QC_DIR = "../processed/qc"

df = pd.read_parquet(INDEX_PATH)

good_ids = []

for sid in df.study_id:

    qc_file = f"{QC_DIR}/{sid}.json"

    with open(qc_file) as f:
        qc = json.load(f)

    if qc["waveform_ok"] and qc["image_ok"] and qc["text_ok"]:
        good_ids.append(sid)

df_clean = df[df.study_id.isin(good_ids)]

print("Original:", len(df))
print("Clean:", len(df_clean))

df_clean.to_parquet("../processed/index/index_clean.parquet")