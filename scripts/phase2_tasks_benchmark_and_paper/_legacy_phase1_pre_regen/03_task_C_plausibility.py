import json
import time
import random
import numpy as np
import pandas as pd
from tqdm import tqdm
from multiprocessing import Pool, cpu_count

# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

INDEX_PATH = "../processed/index/index_clean_with_measurements.parquet"
OUT_PATH = "../processed/taskC_plausibility.jsonl"

NUM_WORKERS = max(1, cpu_count() // 2)

random.seed(42)

# ---------------------------------------------------
# LOGGING
# ---------------------------------------------------


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


# ---------------------------------------------------
# CLAIM LOGIC
# ---------------------------------------------------


def heart_rate_claims(rr):

    claims = []

    if rr is None or np.isnan(rr) or rr <= 0:
        claims.append(("tachycardia present", "UNCERTAIN"))
        claims.append(("bradycardia present", "UNCERTAIN"))
        return claims

    hr = 60000 / rr

    if hr > 100:
        claims.append(("tachycardia present", "SUPPORTED"))
        claims.append(("bradycardia present", "CONTRADICTED"))

    elif hr < 60:
        claims.append(("bradycardia present", "SUPPORTED"))
        claims.append(("tachycardia present", "CONTRADICTED"))

    else:
        claims.append(("normal heart rate", "SUPPORTED"))
        claims.append(("tachycardia present", "CONTRADICTED"))
        claims.append(("bradycardia present", "CONTRADICTED"))

    return claims


def qrs_claims(qrs_on, qrs_end):

    claims = []

    if qrs_on is None or qrs_end is None or np.isnan(qrs_on) or np.isnan(qrs_end):
        claims.append(("wide qrs complex", "UNCERTAIN"))
        return claims

    duration = qrs_end - qrs_on

    if duration > 120:
        claims.append(("wide qrs complex", "SUPPORTED"))
        claims.append(("normal qrs duration", "CONTRADICTED"))

    else:
        claims.append(("wide qrs complex", "CONTRADICTED"))
        claims.append(("normal qrs duration", "SUPPORTED"))

    return claims


def axis_claims(axis):

    claims = []

    if axis is None or np.isnan(axis):
        claims.append(("axis deviation present", "UNCERTAIN"))
        return claims

    if axis < -30:
        claims.append(("left axis deviation", "SUPPORTED"))
        claims.append(("right axis deviation", "CONTRADICTED"))

    elif axis > 90:
        claims.append(("right axis deviation", "SUPPORTED"))
        claims.append(("left axis deviation", "CONTRADICTED"))

    else:
        claims.append(("axis normal", "SUPPORTED"))

    return claims


# ---------------------------------------------------
# WORKER
# ---------------------------------------------------


def process_row(args):

    sid, rr, qrs_on, qrs_end, axis, split = args

    outputs = []

    claims = []
    claims.extend(heart_rate_claims(rr))
    claims.extend(qrs_claims(qrs_on, qrs_end))
    claims.extend(axis_claims(axis))

    for claim, label in claims:

        outputs.append(
            {"study_id": int(sid), "claim": claim, "label": label, "split": split}
        )

    return outputs


# ---------------------------------------------------
# MAIN
# ---------------------------------------------------

if __name__ == "__main__":

    start = time.time()

    log("TASK C DATASET GENERATION")
    log("=" * 60)

    log("Loading index")

    df = pd.read_parquet(INDEX_PATH)

    worker_inputs = list(
        zip(
            df.study_id, df.rr_interval, df.qrs_onset, df.qrs_end, df.qrs_axis, df.split
        )
    )

    total = len(worker_inputs)

    log(f"Studies: {total}")
    log(f"Workers: {NUM_WORKERS}")
    log(f"Output: {OUT_PATH}")

    rows_written = 0

    with open(OUT_PATH, "w") as f:

        with Pool(NUM_WORKERS) as pool:

            for outputs in tqdm(
                pool.imap_unordered(process_row, worker_inputs, chunksize=256),
                total=total,
            ):

                for item in outputs:
                    f.write(json.dumps(item) + "\n")
                    rows_written += 1

    elapsed = time.time() - start

    log("=" * 60)
    log("DATASET BUILD COMPLETE")
    log(f"Rows written: {rows_written}")
    log(f"Output file: {OUT_PATH}")
    log(f"Time: {elapsed/60:.2f} minutes")
