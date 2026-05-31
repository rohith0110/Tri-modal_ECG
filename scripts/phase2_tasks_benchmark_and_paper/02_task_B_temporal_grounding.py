"""
task_B.py — Temporal Grounding Dataset Generator (Fixed)

Generates 10 per-second binary labels for each of three queries:
  HIGH_HEART_RATE  : bin = 1 if local HR > 100 bpm
  LOW_HEART_RATE   : bin = 1 if local HR < 60 bpm
  WIDE_QRS         : bin = 1 if a wide QRS complex (> 120 ms) onset falls in that bin

Label logic is LOCAL (per 1-second bin), not global.
Fallback to global rule if R-peak detection fails for a study.
"""

import os
import json
import time
import numpy as np
import pandas as pd
from tqdm import tqdm
from multiprocessing import Pool, cpu_count

import warnings
warnings.filterwarnings("ignore")  # suppress neurokit2 runtime warnings

try:
    import neurokit2 as nk
    NK_AVAILABLE = True
except ImportError:
    NK_AVAILABLE = False
    print("WARNING: neurokit2 not found. Falling back to global labels for all studies.")

# -----------------------------
# CONFIG
# -----------------------------

INDEX_PATH = "../processed/index/index_clean_with_measurements.parquet"
SIGNAL_DIR = "../processed/signals_lead2"
OUT_PATH = "../processed/taskB_temporal_grounding.jsonl"

NUM_WORKERS = max(1, cpu_count() - 2)

FS = 500           # Hz
BIN_SAMPLES = FS   # 500 samples per 1-second bin
N_BINS = 10

QUERIES = [
    "HIGH_HEART_RATE",
    "LOW_HEART_RATE",
    "WIDE_QRS",
]

# QRS duration threshold: 120 ms at 500 Hz = 60 samples
WIDE_QRS_SAMPLES = int(0.120 * FS)

# -----------------------------
# LOGGING
# -----------------------------


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


# -----------------------------
# CORE LABEL COMPUTATION
# -----------------------------


def _global_fallback(rr_interval, query):
    """Return global all-same-label bins when local detection is unavailable."""
    bins = np.zeros(N_BINS, dtype=int)
    if rr_interval is not None and not np.isnan(rr_interval) and rr_interval > 0:
        hr = 60000.0 / rr_interval
        if query == "HIGH_HEART_RATE" and hr > 100:
            bins[:] = 1
        elif query == "LOW_HEART_RATE" and hr < 60:
            bins[:] = 1
        # WIDE_QRS cannot be inferred from global RR — leave as zeros
    return bins.tolist()


def _detect_r_peaks(signal):
    """Detect R-peaks using neurokit2. Returns array of sample indices.
    Uses nk.ecg_peaks (lightweight) instead of nk.ecg_process (full pipeline).
    Filters out start-of-signal Pan-Tompkins artefacts (see _filter_start_artefact)."""
    # Clean the signal first (bandpass filter), then detect peaks
    cleaned = nk.ecg_clean(signal, sampling_rate=FS, method="pantompkins1985")
    _, info = nk.ecg_peaks(cleaned, sampling_rate=FS, method="pantompkins1985")
    rpeaks = np.array(info["ECG_R_Peaks"], dtype=int)
    return _filter_start_artefact(rpeaks)


def _filter_start_artefact(rpeaks):
    """Drop a leading R-peak that is implausibly close to the second one.

    Pan-Tompkins frequently emits a spurious "peak" within the first ~300 ms
    of a recording, caused by filter ringing / signal-onset transient. The
    spurious peak typically appears at sample 150-160 (roughly 0.30-0.32 s),
    and the *real* first beat follows shortly after. The resulting first RR
    interval is ~150 samples (= ~200 bpm), which is implausible for an adult
    resting ECG, then the rate drops to physiologic levels for the rest of
    the strip.

    We drop the first R-peak only when BOTH conditions hold:
      (1) RR1 < 50% of median(RR[1:])  -- relative anomaly
      (2) RR1 < 175 samples (= 350 ms = 171 bpm)  -- absolute implausibility
    The combined test catches the start-of-signal artefact without dropping
    real ectopic / tachycardic first beats.
    """
    if len(rpeaks) < 4:
        return rpeaks
    rr_samples = np.diff(rpeaks)
    rr1 = float(rr_samples[0])
    rest_median = float(np.median(rr_samples[1:]))
    if rr1 < 0.5 * rest_median and rr1 < 175:
        return rpeaks[1:]
    return rpeaks


def _hr_labels(r_peaks, query):
    """
    Compute per-bin HIGH or LOW heart rate labels.

    Strategy:
      - Compute instantaneous HR at the midpoint of each RR interval.
      - For each bin, average the HR estimates whose midpoint falls inside it.
      - If no midpoint falls inside a bin, interpolate from the nearest estimate.
    """
    bins = np.zeros(N_BINS, dtype=int)

    if len(r_peaks) < 2:
        return bins.tolist()  # cannot compute RR intervals

    rr_samples = np.diff(r_peaks).astype(float)        # samples between beats
    hr_estimates = 60.0 * FS / rr_samples               # bpm per interval
    midpoints = (r_peaks[:-1] + r_peaks[1:]) / 2.0      # midpoint sample index

    for i in range(N_BINS):
        bin_start = i * BIN_SAMPLES
        bin_end = (i + 1) * BIN_SAMPLES

        mask = (midpoints >= bin_start) & (midpoints < bin_end)

        if mask.sum() > 0:
            local_hr = hr_estimates[mask].mean()
        else:
            # nearest midpoint outside this bin
            nearest = int(np.argmin(np.abs(midpoints - (bin_start + bin_end) / 2.0)))
            local_hr = hr_estimates[nearest]

        if query == "HIGH_HEART_RATE" and local_hr > 100:
            bins[i] = 1
        elif query == "LOW_HEART_RATE" and local_hr < 60:
            bins[i] = 1

    return bins.tolist()


def _wide_qrs_labels(signal, r_peaks):
    """
    Compute per-bin WIDE_QRS labels.

    Strategy:
      - Delineate QRS boundaries (onset and offset) per beat using wavelet method.
      - For each beat whose QRS onset falls inside a bin, check if duration > 120 ms.
      - Label the bin 1 if any wide beat onset falls in it.
    """
    bins = np.zeros(N_BINS, dtype=int)

    if len(r_peaks) < 1:
        return bins.tolist()

    try:
        _, waves = nk.ecg_delineate(
            signal, r_peaks, sampling_rate=FS, method="dwt"
        )
        onsets = np.array(waves.get("ECG_R_Onsets", [np.nan] * len(r_peaks)))
        offsets = np.array(waves.get("ECG_R_Offsets", [np.nan] * len(r_peaks)))
    except Exception:
        return bins.tolist()

    for onset, offset in zip(onsets, offsets):
        if np.isnan(onset) or np.isnan(offset):
            continue
        onset = int(onset)
        offset = int(offset)
        duration_samples = offset - onset
        if duration_samples <= 0:
            continue
        bin_idx = onset // BIN_SAMPLES
        if 0 <= bin_idx < N_BINS and duration_samples > WIDE_QRS_SAMPLES:
            bins[bin_idx] = 1

    return bins.tolist()


# -----------------------------
# WORKER
# -----------------------------


def process_row(args):
    """Process one study: detect R-peaks once, then compute all 3 query labels."""

    sid, rr_interval, split = args

    signal_path = f"{SIGNAL_DIR}/{sid}.npy"

    if not os.path.exists(signal_path):
        return []

    try:
        signal = np.load(signal_path)
    except Exception:
        return []

    if len(signal) != FS * N_BINS:  # must be exactly 5000 samples
        return []

    # Detect R-peaks once for this study (shared across all queries)
    r_peaks = None
    if NK_AVAILABLE:
        try:
            r_peaks = _detect_r_peaks(signal)
        except Exception:
            r_peaks = None

    outputs = []

    for q in QUERIES:

        if r_peaks is not None:
            # Use local detection
            try:
                if q in ("HIGH_HEART_RATE", "LOW_HEART_RATE"):
                    labels = _hr_labels(r_peaks, q)
                elif q == "WIDE_QRS":
                    labels = _wide_qrs_labels(signal, r_peaks)
                else:
                    labels = np.zeros(N_BINS, dtype=int).tolist()
            except Exception:
                labels = _global_fallback(rr_interval, q)
        else:
            # Fall back to global rule
            labels = _global_fallback(rr_interval, q)

        outputs.append(
            {"study_id": int(sid), "query": q, "labels": labels, "split": split}
        )

    return outputs


# -----------------------------
# MAIN
# -----------------------------

if __name__ == "__main__":

    start_time = time.time()

    log("TASK B DATASET GENERATION (FIXED — LOCAL PER-BIN DETECTION)")
    log("=" * 60)

    log(f"Loading index: {INDEX_PATH}")

    df = pd.read_parquet(INDEX_PATH, columns=["study_id", "rr_interval", "split"])

    worker_inputs = list(zip(df.study_id, df.rr_interval, df.split))

    total = len(worker_inputs)

    log(f"Studies: {total}")
    log(f"Workers: {NUM_WORKERS}")
    log(f"Output: {OUT_PATH}")
    log(f"neurokit2 available: {NK_AVAILABLE}")

    rows_written = 0

    with open(OUT_PATH, "w") as f:

        with Pool(NUM_WORKERS) as pool:

            for outputs in tqdm(
                pool.imap_unordered(process_row, worker_inputs, chunksize=64),
                total=total,
            ):

                for item in outputs:

                    f.write(json.dumps(item) + "\n")
                    rows_written += 1

    elapsed = time.time() - start_time

    log("=" * 60)
    log("DATASET BUILD COMPLETE")
    log(f"Rows written: {rows_written}")
    log(f"Expected:     {total * len(QUERIES)}")
    log(f"Output file: {OUT_PATH}")
    log(f"Time: {elapsed/60:.2f} minutes")

    # Quick label stats
    log("Computing label statistics (streaming)...")
    query_pos = {q: 0 for q in QUERIES}
    query_total = {q: 0 for q in QUERIES}
    with open(OUT_PATH, "r") as f:
        for line in f:
            row = json.loads(line)
            q = row["query"]
            query_total[q] += 1
            query_pos[q] += int(any(row["labels"]))

    log("")
    log("Per-query positive rate (at least one bin = 1):")
    for q in QUERIES:
        t = query_total[q]
        p = query_pos[q]
        log(f"  {q:25s}: {p:>9,} / {t:>9,}  ({100*p/t:.1f}%)")
