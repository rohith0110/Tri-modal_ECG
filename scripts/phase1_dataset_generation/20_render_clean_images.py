import os
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")  # FIX 1: non-interactive backend, safer for multiprocessing
matplotlib.rcParams["figure.max_open_warning"] = 0  # FIX 1: suppress memory warnings
import matplotlib.pyplot as plt
from multiprocessing import Pool, cpu_count, Manager
from tqdm import tqdm
import time
import traceback

INDEX_PATH = "../processed/index/index_with_split.parquet"
SIGNAL_DIR = "../processed/signals_lead2"
OUT_DIR = "../processed/images_clean"
os.makedirs(OUT_DIR, exist_ok=True)
NUM_WORKERS = max(1, cpu_count() - 2)
print("=" * 60)
print("ECG IMAGE GENERATION PIPELINE")
print("=" * 60)
print("Workers:", NUM_WORKERS)
df = pd.read_parquet(INDEX_PATH)
study_ids = df["study_id"].tolist()
print("Total studies:", len(study_ids))
print("Output directory:", OUT_DIR)
print("=" * 60)


def render_ecg(args):
    study_id, log_lock = args  # FIX 3: unpack lock alongside study_id
    out_path = os.path.join(OUT_DIR, f"{study_id}.png")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 50000:
        return "skipped"
    sig_path = os.path.join(SIGNAL_DIR, f"{study_id}.npy")
    if not os.path.exists(sig_path):
        return "missing"
    try:
        signal = np.load(sig_path)
        t = np.linspace(0, 10, len(signal))
        scale = np.percentile(np.abs(signal), 99)
        if scale > 0:
            signal = signal / scale * 1.2
        else:
            # FIX 4: log flatline/corrupt signals and skip rendering
            with log_lock:
                with open("render_errors.log", "a") as f:
                    f.write(f"{study_id} — scale==0 (flatline or corrupt signal)\n\n")
            return "error"
        fig, ax = plt.subplots(figsize=(12, 2.5))
        ax.plot(t, signal, linewidth=0.8, color="#1f77b4")
        ax.set_xlim(0, 10)
        ax.set_ylim(-2, 2)
        ax.set_xticks(np.arange(0, 10.0001, 0.2))
        ax.set_yticks(np.arange(-2, 2.0001, 0.5))
        ax.set_xticks(np.arange(0, 10.0001, 0.04), minor=True)
        ax.set_yticks(np.arange(-2, 2.0001, 0.1), minor=True)
        ax.grid(which="major", linewidth=1, color="#9a9a9a")
        ax.grid(which="minor", linewidth=0.5, color="#d0d0d0")
        ax.set_xticklabels([])
        ax.set_yticklabels([])
        ax.set_frame_on(False)
        ax.set_facecolor("#fffafa")
        plt.tight_layout()
        plt.savefig(out_path, dpi=300)
        plt.close()
        return "success"
    except Exception as e:
        # FIX 3: acquire lock before writing so workers don't interleave
        with log_lock:
            with open("render_errors.log", "a") as f:
                f.write(f"{study_id}\n")
                f.write(traceback.format_exc())
                f.write("\n\n")
        return "error"


if __name__ == "__main__":
    start_time = time.time()
    success = 0
    skipped = 0
    missing = 0
    error = 0

    # FIX 3: create a cross-process lock via Manager
    with Manager() as manager:
        log_lock = manager.Lock()
        args = [(sid, log_lock) for sid in study_ids]
        with Pool(NUM_WORKERS) as p:
            for result in tqdm(p.imap(render_ecg, args), total=len(study_ids)):
                if result == "success":
                    success += 1
                elif result == "skipped":
                    skipped += 1
                elif result == "missing":
                    missing += 1
                elif result == "error":
                    error += 1

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print("Success:", success)
    print("Skipped (resume):", skipped)
    print("Missing signals:", missing)
    print("Errors:", error)
    print("Total time:", round(elapsed / 60, 2), "minutes")
    print("Images/sec:", round(success / elapsed, 2))
    print("=" * 60)
