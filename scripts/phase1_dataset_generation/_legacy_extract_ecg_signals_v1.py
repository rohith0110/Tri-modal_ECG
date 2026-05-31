import pandas as pd
import wfdb
import numpy as np
import os
import torch
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Queue
import threading
from tqdm import tqdm

INDEX_PATH = "../processed/index/index_with_split.parquet"
DATA_ROOT = "../Data"

OUT_LEAD2 = "../processed/signals_lead2"
OUT_12LEAD = "../processed/signals_12lead"

MAX_WORKERS = 8
CPU_BATCH = 32
GPU_BATCH = 512

os.makedirs(OUT_LEAD2, exist_ok=True)
os.makedirs(OUT_12LEAD, exist_ok=True)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def read_batch(batch):

    results = []

    for study_id, path in batch:

        record_path = os.path.join(DATA_ROOT, path)

        try:

            record = wfdb.rdrecord(record_path, physical=False)

            leads = record.sig_name
            signal = record.p_signal

            if "II" not in leads:
                continue

            lead_index = leads.index("II")
            lead2 = signal[:, lead_index]

            if len(lead2) != 5000:
                continue

            results.append((study_id, signal, lead2))

        except Exception:
            continue

    return results


def gpu_worker(queue):

    buffer = []

    while True:

        item = queue.get()

        if item is None:
            break

        buffer.extend(item)

        if len(buffer) >= GPU_BATCH:

            process_gpu_batch(buffer[:GPU_BATCH])
            buffer = buffer[GPU_BATCH:]

    if buffer:
        process_gpu_batch(buffer)


def process_gpu_batch(batch):

    study_ids = [x[0] for x in batch]
    signals = [x[1] for x in batch]
    lead2s = [x[2] for x in batch]

    signals = torch.tensor(np.stack(signals)).to(device)
    lead2s = torch.tensor(np.stack(lead2s)).to(device)

    # Example GPU operation (normalization)
    lead2s = (lead2s - lead2s.mean(dim=1, keepdim=True)) / (
        lead2s.std(dim=1, keepdim=True) + 1e-6
    )

    lead2s = lead2s.cpu().numpy()
    signals = signals.cpu().numpy()

    for i, study_id in enumerate(study_ids):

        np.save(os.path.join(OUT_LEAD2, f"{study_id}.npy"), lead2s[i])
        np.save(os.path.join(OUT_12LEAD, f"{study_id}.npy"), signals[i])


def create_batches(tasks, size):

    for i in range(0, len(tasks), size):
        yield tasks[i : i + size]


def main():

    print("\nGPU ECG PREPROCESSING PIPELINE\n")

    df = pd.read_parquet(INDEX_PATH)
    df = df.sort_values("path")

    tasks = list(zip(df.study_id.values, df.path.values))

    batches = list(create_batches(tasks, CPU_BATCH))

    print("Total ECG:", len(tasks))
    print("CPU workers:", MAX_WORKERS)
    print("GPU device:", device)
    print()

    queue = Queue(maxsize=50)

    gpu_thread = threading.Thread(target=gpu_worker, args=(queue,))
    gpu_thread.start()

    start = time.time()

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:

        for result in tqdm(executor.map(read_batch, batches), total=len(batches)):

            queue.put(result)

    queue.put(None)
    gpu_thread.join()

    elapsed = time.time() - start

    print("\nFinished in", elapsed / 60, "minutes")


if __name__ == "__main__":
    main()
