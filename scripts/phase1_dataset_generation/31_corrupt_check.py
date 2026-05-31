import os
import cv2
import pandas as pd
from PIL import Image
from tqdm import tqdm
from multiprocessing import Pool, cpu_count

INDEX_PATH = "../processed/index/index_with_split.parquet"
IMAGE_DIR = "../processed/images_clean"

LOG_DIR = "./logs"

os.makedirs(LOG_DIR, exist_ok=True)

MISSING_LOG = os.path.join(LOG_DIR, "missing_clean_images.txt")
CORRUPT_LOG = os.path.join(LOG_DIR, "corrupt_clean_images.txt")
REGENERATE_LIST = os.path.join(LOG_DIR, "clean_images_to_regenerate.txt")

NUM_WORKERS = max(1, cpu_count() - 2)

print("Workers:", NUM_WORKERS)
print("Loading index...")

df = pd.read_parquet(INDEX_PATH)
study_ids = df["study_id"].tolist()

print("Expected images:", len(study_ids))


def check_image(sid):

    path = os.path.join(IMAGE_DIR, f"{sid}.png")

    if not os.path.exists(path):
        return ("missing", sid)

    try:

        # Verify PNG structure
        with Image.open(path) as img:
            img.verify()

        # Verify OpenCV decoding
        img = cv2.imread(path, cv2.IMREAD_COLOR)

        if img is None:
            return ("corrupt", sid)

        h, w = img.shape[:2]

        if h == 0 or w == 0:
            return ("corrupt", sid)

        return ("ok", sid)

    except Exception:
        return ("corrupt", sid)


if __name__ == "__main__":

    missing = []
    corrupt = []

    with Pool(NUM_WORKERS) as pool:

        for status, sid in tqdm(
            pool.imap_unordered(check_image, study_ids, chunksize=256),
            total=len(study_ids)
        ):

            if status == "missing":
                missing.append(sid)

            elif status == "corrupt":
                corrupt.append(sid)

    # ---------- Write logs ----------

    with open(MISSING_LOG, "w") as f:
        for sid in missing:
            f.write(str(sid) + "\n")

    with open(CORRUPT_LOG, "w") as f:
        for sid in corrupt:
            f.write(str(sid) + "\n")

    regen = missing + corrupt

    with open(REGENERATE_LIST, "w") as f:
        for sid in regen:
            f.write(str(sid) + "\n")

    print("\nValidation complete")
    print("Missing:", len(missing))
    print("Corrupt:", len(corrupt))
    print("Total to regenerate:", len(regen))

    print("\nLogs saved:")
    print(MISSING_LOG)
    print(CORRUPT_LOG)
    print(REGENERATE_LIST)