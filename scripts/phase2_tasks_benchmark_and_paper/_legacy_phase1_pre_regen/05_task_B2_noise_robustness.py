"""
task_B2.py — Plan B, Task 2 (Noise-Robustness Benchmark, Phase 2 only)

SPLIT NOTICE (per PIPELINE_SOURCE_OF_TRUTH.md §3.11, §9.3 Stage 8, §13):
The corruption-dataset generation half of this script has moved to
Phase 1: see scripts/phase1_dataset_generation/50_build_signals_corrupted.py,
which writes data/processed/signals_corrupted.parquet.

After Phase 1 regen this Phase 2 script keeps ONLY the benchmark task /
evaluation / metrics half (jsonl, eval regimes, AUC, etc.) and reads
the corrupted signals from the consolidated parquet via the modality
manifest — it no longer regenerates them.

The legacy text below documents the original combined behavior and is
retained for reference until the rewrite lands.

---
Selects a clean anchor subset (waveform_ok=True, test split) and generates
corrupted versions at fixed SNR levels for 8 corruption families.

Corruption families:
  1. gaussian          — additive white Gaussian noise
  2. baseline_wander   — low-frequency sinusoidal drift (0.05–1 Hz)
  3. powerline         — 50/60 Hz sinusoidal interference
  4. emg               — bandpass-filtered high-frequency noise (100–250 Hz)
  5. electrode_motion  — random-amplitude transient spikes
  6. lead_dropout      — zero-out a contiguous segment
  7. gain_drift        — slow sinusoidal amplitude modulation
  8. saturation        — hard clipping at amplitude threshold

SNR levels (dB): 30, 20, 10, 5, 0  (plus clean as reference)

Output:
  processed/signals_corrupted/{study_id}_{corruption}_{snr}dB.npy
  processed/taskB2_noise_robustness.jsonl
"""

import os
import json
import time
import numpy as np
import pandas as pd
from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────────────────────

INDEX_PATH       = "../processed/index/index_clean_with_measurements.parquet"
SIGNAL_DIR       = "../processed/signals_lead2"
CORRUPTED_DIR    = "../processed/signals_corrupted"
OUT_PATH         = "../processed/taskB2_noise_robustness.jsonl"

ANCHOR_SIZE      = 2000        # number of clean test signals to corrupt
FS               = 500         # Hz
N_SAMPLES        = 5000        # samples per signal (10s × 500Hz)
SEED             = 42

SNR_LEVELS_DB    = [30, 20, 10, 5, 0]

CORRUPTIONS = [
    "gaussian",
    "baseline_wander",
    "powerline",
    "emg",
    "electrode_motion",
    "lead_dropout",
    "gain_drift",
    "saturation",
]

os.makedirs(CORRUPTED_DIR, exist_ok=True)
rng = np.random.default_rng(SEED)

# ── Noise injection functions ─────────────────────────────────────────────────

def signal_power(sig):
    return np.mean(sig ** 2)

def scale_noise_to_snr(sig, noise, snr_db):
    """Scale noise so that SNR = 10*log10(P_signal / P_noise)."""
    p_sig = signal_power(sig)
    p_noise = signal_power(noise)
    if p_noise < 1e-12:
        return noise
    target_p_noise = p_sig / (10 ** (snr_db / 10.0))
    return noise * np.sqrt(target_p_noise / p_noise)

def corrupt_gaussian(sig, snr_db, rng):
    noise = rng.standard_normal(len(sig)).astype(np.float32)
    return sig + scale_noise_to_snr(sig, noise, snr_db)

def corrupt_baseline_wander(sig, snr_db, rng):
    t = np.arange(N_SAMPLES) / FS
    freq = rng.uniform(0.05, 1.0)
    phase = rng.uniform(0, 2 * np.pi)
    noise = np.sin(2 * np.pi * freq * t + phase).astype(np.float32)
    return sig + scale_noise_to_snr(sig, noise, snr_db)

def corrupt_powerline(sig, snr_db, rng):
    t = np.arange(N_SAMPLES) / FS
    freq = rng.choice([50.0, 60.0])
    phase = rng.uniform(0, 2 * np.pi)
    noise = np.sin(2 * np.pi * freq * t + phase).astype(np.float32)
    return sig + scale_noise_to_snr(sig, noise, snr_db)

def corrupt_emg(sig, snr_db, rng):
    # High-frequency burst noise — approximate EMG with band-limited noise
    noise = rng.standard_normal(N_SAMPLES).astype(np.float32)
    # Simple high-pass: subtract low-frequency component (moving average)
    window = max(1, FS // 50)   # ~10ms window preserves > ~100Hz
    kernel = np.ones(window, dtype=np.float32) / window
    low = np.convolve(noise, kernel, mode="same")
    noise = noise - low
    return sig + scale_noise_to_snr(sig, noise, snr_db)

def corrupt_electrode_motion(sig, snr_db, rng):
    noise = np.zeros(N_SAMPLES, dtype=np.float32)
    n_spikes = rng.integers(3, 10)
    for _ in range(n_spikes):
        pos = rng.integers(0, N_SAMPLES)
        width = rng.integers(10, 80)        # 20–160 ms spike
        amp = rng.uniform(0.5, 2.0)
        start = max(0, pos - width // 2)
        end = min(N_SAMPLES, pos + width // 2)
        noise[start:end] = amp * np.sign(rng.standard_normal())
    return sig + scale_noise_to_snr(sig, noise, snr_db)

def corrupt_lead_dropout(sig, snr_db, rng):
    # Zero out a contiguous segment; snr_db controls segment length
    # Lower SNR → longer dropout
    fraction = 0.1 * (10 ** (-snr_db / 20.0)) + 0.05   # ~5–10%
    length = int(N_SAMPLES * min(fraction, 0.5))
    start = rng.integers(0, N_SAMPLES - length)
    corrupted = sig.copy()
    corrupted[start:start + length] = 0.0
    return corrupted

def corrupt_gain_drift(sig, snr_db, rng):
    t = np.arange(N_SAMPLES) / FS
    freq = rng.uniform(0.01, 0.5)
    phase = rng.uniform(0, 2 * np.pi)
    # Amplitude modulation — gain oscillates around 1.0
    # snr_db controls depth of modulation
    depth = 10 ** (-snr_db / 20.0)
    depth = np.clip(depth, 0.01, 0.99)
    envelope = 1.0 + depth * np.sin(2 * np.pi * freq * t + phase)
    return (sig * envelope.astype(np.float32))

def corrupt_saturation(sig, snr_db, rng):
    # Clip at threshold controlled by SNR — lower SNR → lower threshold
    p_sig = np.sqrt(signal_power(sig))
    clip_factor = 10 ** (snr_db / 20.0) * 0.5   # heuristic mapping
    threshold = max(0.1 * p_sig, clip_factor * p_sig)
    return np.clip(sig, -threshold, threshold).astype(np.float32)

CORRUPT_FN = {
    "gaussian":         corrupt_gaussian,
    "baseline_wander":  corrupt_baseline_wander,
    "powerline":        corrupt_powerline,
    "emg":              corrupt_emg,
    "electrode_motion": corrupt_electrode_motion,
    "lead_dropout":     corrupt_lead_dropout,
    "gain_drift":       corrupt_gain_drift,
    "saturation":       corrupt_saturation,
}

# ── Load index and select anchor subset ───────────────────────────────────────

print("=" * 60)
print("TASK B2: NOISE-ROBUSTNESS CURRICULUM DATASET")
print("=" * 60)

t0 = time.time()
# index_clean already has QC filtering applied (waveform_ok=True subset)
df = pd.read_parquet(INDEX_PATH)
print(f"Index loaded: {len(df):,} clean records")

# Select clean anchor: test split only (no per-file QC loading needed)
test_df = df[df["split"] == "test"].copy()

# Verify signal files exist and shuffle
test_df["sig_path"] = test_df["study_id"].apply(
    lambda sid: os.path.join(SIGNAL_DIR, f"{sid}.npy")
)
test_df = test_df[test_df["sig_path"].apply(os.path.exists)]
test_df = test_df.sample(frac=1, random_state=SEED)

anchor = test_df.head(ANCHOR_SIZE)
print(f"  Anchor size: {len(anchor):,} (requested {ANCHOR_SIZE})")

# ── Generate corrupted signals ────────────────────────────────────────────────

print(f"\nGenerating corruptions ({len(CORRUPTIONS)} types × {len(SNR_LEVELS_DB)} SNRs)...")
total_files = len(anchor) * len(CORRUPTIONS) * len(SNR_LEVELS_DB)
print(f"  Total files to write: {total_files:,}")

records = []
file_rng_seeds = {}    # deterministic per (study_id, corruption, snr)

with tqdm(total=total_files, desc="Corrupting") as pbar:
    for row in anchor.itertuples():
        sig = np.load(row.sig_path)
        if len(sig) != N_SAMPLES:
            pbar.update(len(CORRUPTIONS) * len(SNR_LEVELS_DB))
            continue

        # Clean reference record
        records.append({
            "study_id":           int(row.study_id),
            "subject_id":         int(row.subject_id),
            "clean_signal_path":  row.sig_path,
            "corrupted_signal_path": row.sig_path,
            "corruption_type":    "clean",
            "snr_db":             None,
            "split":              "test",
        })

        for corruption in CORRUPTIONS:
            for snr_db in SNR_LEVELS_DB:
                # Deterministic seed per (study, corruption, snr)
                seed_key = abs(hash((int(row.study_id), corruption, snr_db))) % (2**31)
                local_rng = np.random.default_rng(seed_key)

                corrupted = CORRUPT_FN[corruption](sig.copy(), snr_db, local_rng)
                corrupted = corrupted.astype(np.float32)

                out_name = f"{row.study_id}_{corruption}_{snr_db}dB.npy"
                out_path = os.path.join(CORRUPTED_DIR, out_name)
                np.save(out_path, corrupted)

                records.append({
                    "study_id":            int(row.study_id),
                    "subject_id":          int(row.subject_id),
                    "clean_signal_path":   row.sig_path,
                    "corrupted_signal_path": out_path,
                    "corruption_type":     corruption,
                    "snr_db":              snr_db,
                    "split":               "test",
                })
                pbar.update(1)

# ── Write JSONL ───────────────────────────────────────────────────────────────

print(f"\nWriting JSONL ({len(records):,} records)...")
with open(OUT_PATH, "w") as fout:
    for rec in records:
        fout.write(json.dumps(rec) + "\n")

# ── Summary ───────────────────────────────────────────────────────────────────

elapsed = time.time() - t0
print(f"\n{'='*60}")
print(f"TASK B2 COMPLETE  ({elapsed:.1f}s)")
print(f"{'='*60}")
print(f"Anchor signals:     {len(anchor):,}")
print(f"Corrupted files:    {len(anchor) * len(CORRUPTIONS) * len(SNR_LEVELS_DB):,}")
print(f"Total JSONL rows:   {len(records):,}")
print(f"Output JSONL:       {OUT_PATH}")
print(f"Corrupted signals:  {CORRUPTED_DIR}")

corruption_counts = {}
for r in records:
    k = r["corruption_type"]
    corruption_counts[k] = corruption_counts.get(k, 0) + 1
print("\nRecords per corruption type:")
for k, v in corruption_counts.items():
    print(f"  {k:20s}: {v:,}")
