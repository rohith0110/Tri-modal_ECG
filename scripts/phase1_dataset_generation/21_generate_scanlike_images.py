import os
import cv2
import numpy as np
import pandas as pd
from multiprocessing import Pool, cpu_count
from tqdm import tqdm

INDEX_PATH = "../processed/index/index_with_split.parquet"

CLEAN_DIR = "../processed/images_clean"
SCAN_DIR = "../processed/images_scanlike"

MAX_WIDTH = 1600

os.makedirs(SCAN_DIR, exist_ok=True)

NUM_WORKERS = max(1, cpu_count() - 2)


def apply_scanlike(study_id):

    in_path = os.path.join(CLEAN_DIR, f"{study_id}.png")
    out_path = os.path.join(SCAN_DIR, f"{study_id}.jpg")

    if not os.path.exists(in_path):
        return "missing"

    img = cv2.imread(in_path)

    if img is None:
        return "error"

    rng = np.random.default_rng(int(study_id))

    h, w = img.shape[:2]

    if w > MAX_WIDTH:

        scale = MAX_WIDTH / w

        img = cv2.resize(
            img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA
        )

        h, w = img.shape[:2]

    angle = rng.uniform(-2, 2)

    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1)

    img = cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)

    shift = rng.uniform(-0.01, 0.01)

    pts1 = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
    pts2 = np.float32([[w * shift, 0], [w + w * shift, 0], [0, h], [w, h]])

    P = cv2.getPerspectiveTransform(pts1, pts2)

    img = cv2.warpPerspective(img, P, (w, h), borderMode=cv2.BORDER_REPLICATE)

    k = int(rng.choice([3, 5]))

    img = cv2.GaussianBlur(img, (k, k), 0)

    alpha = rng.uniform(0.9, 1.1)
    beta = rng.uniform(-10, 10)

    img = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)

    quality = int(rng.uniform(70, 95))

    cv2.imwrite(out_path, img, [cv2.IMWRITE_JPEG_QUALITY, quality])

    return "ok"


if __name__ == "__main__":

    df = pd.read_parquet(INDEX_PATH)

    study_ids = df["study_id"].tolist()

    with Pool(NUM_WORKERS) as pool:

        list(
            tqdm(
                pool.imap_unordered(apply_scanlike, study_ids, chunksize=256),
                total=len(study_ids),
            )
        )
