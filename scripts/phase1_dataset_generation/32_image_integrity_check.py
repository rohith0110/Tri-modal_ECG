import os
import cv2
import json
import pandas as pd
from PIL import Image
from tqdm import tqdm
from multiprocessing import Pool, cpu_count

INDEX_PATH = "../processed/index/index_with_split.parquet"

CLEAN_DIR = "../processed/images_clean"
SCAN_DIR = "../processed/images_scanlike"

LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)

NUM_WORKERS = max(1, cpu_count() - 4)

CLEAN_MISSING = os.path.join(LOG_DIR, "clean_missing.txt")
CLEAN_CORRUPT = os.path.join(LOG_DIR, "clean_corrupt.txt")
SCAN_MISSING = os.path.join(LOG_DIR, "scan_missing.txt")
SCAN_CORRUPT = os.path.join(LOG_DIR, "scan_corrupt.txt")

REGEN_CLEAN = os.path.join(LOG_DIR, "regen_clean_images.txt")
REGEN_SCAN = os.path.join(LOG_DIR, "regen_scan_images.txt")

SUMMARY_FILE = os.path.join(LOG_DIR, "dataset_integrity_summary.json")


# --------------------------------------------------
# CHECK FUNCTION
# --------------------------------------------------


def check_image(args):

    sid, CLEAN_DIR, SCAN_DIR = args
    sid = str(sid)

    clean_path = os.path.join(CLEAN_DIR, f"{sid}.png")
    scan_path = os.path.join(SCAN_DIR, f"{sid}.jpg")

    result = {
        "clean_missing": False,
        "clean_corrupt": False,
        "scan_missing": False,
        "scan_corrupt": False,
    }

    if not os.path.exists(clean_path):
        result["clean_missing"] = True

    else:
        try:
            with Image.open(clean_path) as img:
                img.verify()

            img = cv2.imread(clean_path)
            if img is None:
                result["clean_corrupt"] = True

        except Exception:
            result["clean_corrupt"] = True

    if not os.path.exists(scan_path):
        result["scan_missing"] = True

    else:
        try:
            img = cv2.imread(scan_path)
            if img is None:
                result["scan_corrupt"] = True

        except Exception:
            result["scan_corrupt"] = True

    return sid, result


# --------------------------------------------------
# MAIN
# --------------------------------------------------

if __name__ == "__main__":

    print("Loading index...")
    df = pd.read_parquet(INDEX_PATH)
    study_ids = df["study_id"].tolist()

    EXPECTED = len(study_ids)

    print("Expected studies:", EXPECTED)
    print("Workers:", NUM_WORKERS)

    clean_missing = []
    clean_corrupt = []

    scan_missing = []
    scan_corrupt = []

    args = [(sid, CLEAN_DIR, SCAN_DIR) for sid in study_ids]

    with Pool(NUM_WORKERS) as pool:

        for sid, res in tqdm(
            pool.imap_unordered(check_image, args, chunksize=256),
            total=EXPECTED,
        ):

            if res["clean_missing"]:
                clean_missing.append(sid)

            if res["clean_corrupt"]:
                clean_corrupt.append(sid)

            if res["scan_missing"]:
                scan_missing.append(sid)

            if res["scan_corrupt"]:
                scan_corrupt.append(sid)

    # write logs
    def write_list(path, data):
        with open(path, "w") as f:
            for x in data:
                f.write(str(x) + "\n")

    write_list(CLEAN_MISSING, clean_missing)
    write_list(CLEAN_CORRUPT, clean_corrupt)

    write_list(SCAN_MISSING, scan_missing)
    write_list(SCAN_CORRUPT, scan_corrupt)

    regen_clean = clean_missing + clean_corrupt
    regen_scan = scan_missing + scan_corrupt

    write_list(REGEN_CLEAN, regen_clean)
    write_list(REGEN_SCAN, regen_scan)

    summary = {
        "expected_studies": EXPECTED,
        "clean_images": {
            "missing": len(clean_missing),
            "corrupt": len(clean_corrupt),
            "valid": EXPECTED - len(clean_missing) - len(clean_corrupt),
        },
        "scanlike_images": {
            "missing": len(scan_missing),
            "corrupt": len(scan_corrupt),
            "valid": EXPECTED - len(scan_missing) - len(scan_corrupt),
        },
    }

    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n========== DATASET AUDIT ==========")
    print(json.dumps(summary, indent=2))
