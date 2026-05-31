import pandas as pd
import wfdb
import numpy as np
import os
import time
from concurrent.futures import ProcessPoolExecutor
import psutil
from tqdm import tqdm
import json

INDEX_PATH = "../processed/index/index_with_split.parquet"
DATA_ROOT = "../Data"

OUT_LEAD2 = "../processed/signals_lead2"
OUT_12LEAD = "../processed/signals_12lead"
OUT_META = "../processed/signal_metadata"

MAX_RAM_GB = 16
MAX_WORKERS = min(8, os.cpu_count())
BATCH_SIZE = 32

os.makedirs(OUT_LEAD2, exist_ok=True)
os.makedirs(OUT_12LEAD, exist_ok=True)
os.makedirs(OUT_META, exist_ok=True)

process = psutil.Process(os.getpid())


def get_ram():
    return process.memory_info().rss / (1024**3)


def check_ram():

    ram = get_ram()

    if ram > MAX_RAM_GB:

        print(f"\n[RAM LIMIT] {ram:.2f}GB > {MAX_RAM_GB}GB — waiting")

        while get_ram() > MAX_RAM_GB:
            time.sleep(2)

        print("[RAM LIMIT] Resuming\n")


def process_batch(batch):

    results = {
        "ok": 0,
        "skipped": 0,
        "missing_lead": 0,
        "bad_length": 0,
        "error": 0,
    }

    for study_id, path in batch:

        try:

            lead2_file = os.path.join(OUT_LEAD2, f"{study_id}.npy")

            if os.path.exists(lead2_file):
                results["skipped"] += 1
                continue

            record_path = os.path.join(DATA_ROOT, path)

            # load waveform in PHYSICAL units
            record = wfdb.rdrecord(record_path)

            leads = record.sig_name
            signal = record.p_signal
            if signal.shape[1] != 12:
                results["error"] += 1
                continue

            if signal is None:
                results["error"] += 1
                continue

            if "II" not in leads:
                results["missing_lead"] += 1
                continue

            lead_index = leads.index("II")

            lead2 = signal[:, lead_index]

            if len(lead2) != 5000:
                results["bad_length"] += 1
                continue

            nan_count = int(np.isnan(signal).sum())

            waveform_ok = nan_count == 0

            # save signals
            np.save(
                os.path.join(OUT_LEAD2, f"{study_id}.npy"), lead2.astype(np.float32)
            )
            np.save(
                os.path.join(OUT_12LEAD, f"{study_id}.npy"), signal.astype(np.float32)
            )

            # metadata
            meta = {
                "study_id": int(study_id),
                "num_samples": int(signal.shape[0]),
                "num_leads": int(signal.shape[1]),
                "missing_values": nan_count,
                "waveform_ok": waveform_ok,
            }

            with open(os.path.join(OUT_META, f"{study_id}.json"), "w") as f:
                json.dump(meta, f)

            results["ok"] += 1

        except Exception:
            results["error"] += 1

    return results


def create_batches(tasks, size):

    batch = []

    for t in tasks:

        batch.append(t)

        if len(batch) == size:
            yield batch
            batch = []

    if batch:
        yield batch


def main():

    print("\n==============================")
    print("ECG SIGNAL EXTRACTION STARTED")
    print("==============================\n")

    print("Loading dataset index...")

    df = pd.read_parquet(INDEX_PATH)

    df = df.sort_values("path")

    tasks = zip(df.study_id.values, df.path.values)

    total_ecg = len(df)

    print("Total ECGs:", total_ecg)
    print("Workers:", MAX_WORKERS)
    print("Batch size:", BATCH_SIZE)
    print("RAM limit:", MAX_RAM_GB, "GB\n")

    results = {
        "ok": 0,
        "skipped": 0,
        "missing_lead": 0,
        "bad_length": 0,
        "error": 0,
    }

    start_time = time.time()

    completed_ecg = 0

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:

        batches = create_batches(tasks, BATCH_SIZE)

        total_batches = (total_ecg // BATCH_SIZE) + 1

        for batch_result in tqdm(
            executor.map(process_batch, batches), total=total_batches
        ):

            check_ram()

            for k in results:
                results[k] += batch_result[k]

            completed_ecg = (
                results["ok"]
                + results["skipped"]
                + results["missing_lead"]
                + results["bad_length"]
                + results["error"]
            )

            if completed_ecg % 5000 == 0:

                elapsed = time.time() - start_time
                speed = completed_ecg / elapsed

                print(
                    f"\n[STATUS] {completed_ecg}/{total_ecg}"
                    f" | Speed: {speed:.2f} ECG/s"
                    f" | RAM: {get_ram():.2f} GB"
                )

    print("\n==============================")
    print("EXTRACTION COMPLETE")
    print("==============================\n")

    for k, v in results.items():
        print(f"{k}: {v}")

    total_time = time.time() - start_time

    print(f"\nTotal time: {total_time / 60:.2f} minutes")


if __name__ == "__main__":
    main()
