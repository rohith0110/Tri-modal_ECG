import os
import json
import numpy as np
import pandas as pd
from multiprocessing import Pool, cpu_count
from tqdm import tqdm

INDEX_PATH = "../processed/index/index_with_split.parquet"

SIGNAL_DIR = "../processed/signals_lead2"
IMG_CLEAN_DIR = "../processed/images_clean"
IMG_SCAN_DIR = "../processed/images_scanlike"

QC_DIR = "../processed/qc"
os.makedirs(QC_DIR, exist_ok=True)

df = pd.read_parquet(INDEX_PATH)

NUM_WORKERS = max(1, cpu_count() - 2)


def qc_check(args):

    study_id, text = args

    notes = []

    # ---- waveform check ----
    signal_path = f"{SIGNAL_DIR}/{study_id}.npy"

    waveform_ok = False

    if os.path.exists(signal_path):
        try:
            signal = np.load(signal_path)
            waveform_ok = len(signal) == 5000
        except:
            notes.append("signal_load_fail")
    else:
        notes.append("signal_missing")

    # ---- image check ----
    clean_img = f"{IMG_CLEAN_DIR}/{study_id}.png"
    scan_img = f"{IMG_SCAN_DIR}/{study_id}.jpg"

    image_ok = os.path.exists(clean_img) and os.path.exists(scan_img)

    if not image_ok:
        notes.append("image_missing")

    # ---- text check ----
    text_ok = isinstance(text, str) and len(text.strip()) > 0

    if not text_ok:
        notes.append("empty_text")

    qc = {
        "study_id": int(study_id),
        "waveform_ok": bool(waveform_ok),
        "image_ok": bool(image_ok),
        "text_ok": bool(text_ok),
        "notes": ";".join(notes),
    }

    out = f"{QC_DIR}/{study_id}.json"

    with open(out, "w") as f:
        json.dump(qc, f)


def main():

    # convert to simple tuples → pickle-safe
    rows = list(zip(df["study_id"], df["T_machine"]))

    with Pool(NUM_WORKERS) as p:
        list(tqdm(p.imap(qc_check, rows), total=len(rows)))


if __name__ == "__main__":
    main()
