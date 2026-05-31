import os
import cv2
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from multiprocessing import Pool, cpu_count, Manager
from tqdm import tqdm
from PIL import Image
import traceback

INDEX_PATH = "../processed/index/index_with_split.parquet"
SIGNAL_DIR = "../processed/signals_lead2"
CLEAN_DIR = "../processed/images_clean"

LOG_DIR = "./logs"

MISSING_LOG = os.path.join(LOG_DIR, "missing_clean_images.txt")
CORRUPT_LOG = os.path.join(LOG_DIR, "corrupt_clean_images.txt")
REGEN_LIST = os.path.join(LOG_DIR, "clean_images_to_regenerate.txt")

os.makedirs(CLEAN_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

NUM_WORKERS = max(1, cpu_count() - 2)


# --------------------------------------------------
# CLEAN RENDER
# --------------------------------------------------


def render_clean(signal):

    t = np.linspace(0, 10, len(signal))

    scale = np.percentile(np.abs(signal), 99)
    if scale > 0:
        signal = signal / scale * 1.2

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

    return fig


# --------------------------------------------------
# IMAGE CHECK
# --------------------------------------------------


def check_image(sid):

    path = os.path.join(CLEAN_DIR, f"{sid}.png")

    if not os.path.exists(path):
        return ("missing", sid)

    try:

        with Image.open(path) as img:
            img.verify()

        img = cv2.imread(path)

        if img is None:
            return ("corrupt", sid)

        h, w = img.shape[:2]

        if h == 0 or w == 0:
            return ("corrupt", sid)

        return ("ok", sid)

    except Exception:
        return ("corrupt", sid)


# --------------------------------------------------
# CLEAN REGENERATION
# --------------------------------------------------


def regenerate_clean(sid):

    try:

        signal_path = os.path.join(SIGNAL_DIR, f"{sid}.npy")

        if not os.path.exists(signal_path):
            return "missing_signal"

        signal = np.load(signal_path)

        fig = render_clean(signal)

        out_path = os.path.join(CLEAN_DIR, f"{sid}.png")

        fig.savefig(out_path, dpi=300)

        plt.close(fig)

        return "ok"

    except Exception:
        return "error"


# --------------------------------------------------
# MAIN
# --------------------------------------------------

if __name__ == "__main__":

    print("Workers:", NUM_WORKERS)

    df = pd.read_parquet(INDEX_PATH)
    study_ids = df["study_id"].tolist()

    print("Checking clean images...")

    missing = []
    corrupt = []

    with Pool(NUM_WORKERS) as pool:

        for status, sid in tqdm(
            pool.imap_unordered(check_image, study_ids, chunksize=256),
            total=len(study_ids),
        ):

            if status == "missing":
                missing.append(sid)

            elif status == "corrupt":
                corrupt.append(sid)

    with open(MISSING_LOG, "w") as f:
        for x in missing:
            f.write(str(x) + "\n")

    with open(CORRUPT_LOG, "w") as f:
        for x in corrupt:
            f.write(str(x) + "\n")

    regen = missing + corrupt

    with open(REGEN_LIST, "w") as f:
        for x in regen:
            f.write(str(x) + "\n")

    print("Images to regenerate:", len(regen))

    print("Regenerating clean images...")

    with Pool(NUM_WORKERS) as pool:

        list(
            tqdm(
                pool.imap_unordered(regenerate_clean, regen, chunksize=64),
                total=len(regen),
            )
        )

    print("Clean image recovery complete.")
