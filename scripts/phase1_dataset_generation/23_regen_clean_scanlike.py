import os
import cv2
import numpy as np
import matplotlib.pyplot as plt
from multiprocessing import Pool, cpu_count
from tqdm import tqdm


SIGNAL_DIR = "../processed/signals_lead2"
CLEAN_DIR = "../processed/images_clean"
SCAN_DIR = "../processed/images_scanlike"

REGEN_LIST = "./logs/clean_images_to_regenerate.txt"

os.makedirs(CLEAN_DIR, exist_ok=True)
os.makedirs(SCAN_DIR, exist_ok=True)


# --------------------------------------------------
# CLEAN RENDER
# --------------------------------------------------

def render_clean(signal):

    t = np.linspace(0, 10, len(signal))

    scale = np.percentile(np.abs(signal), 99)

    if scale > 0:
        signal = signal / scale * 1.2

    fig, ax = plt.subplots(figsize=(12,2.5))

    ax.plot(t, signal, linewidth=0.8, color="#1f77b4")

    ax.set_xlim(0,10)
    ax.set_ylim(-2,2)

    ax.set_xticks(np.arange(0,10.0001,0.2))
    ax.set_yticks(np.arange(-2,2.0001,0.5))

    ax.set_xticks(np.arange(0,10.0001,0.04), minor=True)
    ax.set_yticks(np.arange(-2,2.0001,0.1), minor=True)

    ax.grid(which="major", linewidth=1, color="#9a9a9a")
    ax.grid(which="minor", linewidth=0.5, color="#d0d0d0")

    ax.set_xticklabels([])
    ax.set_yticklabels([])

    ax.set_frame_on(False)

    ax.set_facecolor("#fffafa")

    plt.tight_layout()

    return fig


# --------------------------------------------------
# SCANLIKE
# --------------------------------------------------

def apply_scanlike(img, study_id):

    rng = np.random.default_rng(int(study_id))

    h, w = img.shape[:2]

    angle = rng.uniform(-2,2)

    M = cv2.getRotationMatrix2D((w*0.5,h*0.5),angle,1.0)

    img = cv2.warpAffine(img, M, (w,h), borderMode=cv2.BORDER_REPLICATE)

    shift = rng.uniform(-0.01,0.01)

    pts1 = np.float32([[0,0],[w,0],[0,h],[w,h]])
    pts2 = np.float32([[w*shift,0],[w+w*shift,0],[0,h],[w,h]])

    P = cv2.getPerspectiveTransform(pts1,pts2)

    img = cv2.warpPerspective(img,P,(w,h),borderMode=cv2.BORDER_REPLICATE)

    k = int(rng.choice([3,5]))
    img = cv2.GaussianBlur(img,(k,k),0)

    alpha = rng.uniform(0.9,1.1)
    beta = rng.uniform(-10,10)

    img = cv2.convertScaleAbs(img,alpha=alpha,beta=beta)

    quality = int(rng.uniform(70,95))

    enc = cv2.imencode(".jpg", img,[cv2.IMWRITE_JPEG_QUALITY,quality])[1]

    img = cv2.imdecode(enc,1)

    return img


# --------------------------------------------------
# PIPELINE
# --------------------------------------------------

def regenerate(study_id):

    try:

        signal_path = os.path.join(SIGNAL_DIR, f"{study_id}.npy")

        if not os.path.exists(signal_path):
            return "missing_signal"

        signal = np.load(signal_path)

        fig = render_clean(signal)

        clean_path = os.path.join(CLEAN_DIR, f"{study_id}.png")

        fig.savefig(clean_path, dpi=300)

        plt.close(fig)

        img = cv2.imread(clean_path)

        scan = apply_scanlike(img, study_id)

        scan_path = os.path.join(SCAN_DIR, f"{study_id}.png")

        cv2.imwrite(scan_path, scan)

        return "ok"

    except Exception:

        return "error"


# --------------------------------------------------
# MAIN
# --------------------------------------------------

if __name__ == "__main__":

    NUM_WORKERS = max(1, cpu_count() - 2)

    print("Workers:", NUM_WORKERS)

    with open(REGEN_LIST) as f:
        study_ids = [line.strip() for line in f]

    print("Images to regenerate:", len(study_ids))

    stats = {"ok":0,"error":0,"missing_signal":0}

    with Pool(NUM_WORKERS) as pool:

        for r in tqdm(
            pool.imap_unordered(regenerate, study_ids, chunksize=64),
            total=len(study_ids)
        ):
            stats[r]+=1

    print("\nRegeneration finished")
    print(stats)