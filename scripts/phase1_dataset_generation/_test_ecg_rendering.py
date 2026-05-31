import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os

INDEX_PATH = "../processed/index/index_with_split.parquet"
SIGNAL_DIR = "../processed/signals_lead2"
OUT_DIR = "../processed/images_test"

os.makedirs(OUT_DIR, exist_ok=True)

print("Loading dataset index...")
df = pd.read_parquet(INDEX_PATH)

sample = df.sample(10, random_state=42)

print("Rendering 10 ECG strips...\n")

for _, row in sample.iterrows():

    study_id = row.study_id
    sig_path = os.path.join(SIGNAL_DIR, f"{study_id}.npy")

    if not os.path.exists(sig_path):
        print("Missing signal:", study_id)
        continue

    signal = np.load(sig_path)

    # time axis (10 seconds)
    t = np.linspace(0, 10, len(signal))

    # normalize amplitude slightly for consistent scaling
    scale = np.percentile(np.abs(signal), 99)
    if scale > 0:
        signal = signal / scale * 1.2

    fig, ax = plt.subplots(figsize=(12, 2.5))

    # ECG waveform
    ax.plot(t, signal, linewidth=0.8, color="#1f77b4")

    # ----- ECG PAPER GRID -----

    ax.set_xlim(0, 10)
    ax.set_ylim(-2, 2)

    # major grid (large squares)
    ax.set_xticks(np.arange(0, 10.0001, 0.2))
    ax.set_yticks(np.arange(-2, 2.0001, 0.5))

    # minor grid (small squares)
    ax.set_xticks(np.arange(0, 10.0001, 0.04), minor=True)
    ax.set_yticks(np.arange(-2, 2.0001, 0.1), minor=True)

    # grid styling
    ax.grid(which="major", linewidth=1, color="#9a9a9a")
    ax.grid(which="minor", linewidth=0.5, color="#d0d0d0")

    # remove axis labels
    ax.set_xticklabels([])
    ax.set_yticklabels([])

    ax.set_frame_on(False)

    # light ECG paper background
    ax.set_facecolor("#fffafa")

    plt.tight_layout()

    out_path = os.path.join(OUT_DIR, f"{study_id}.png")

    plt.savefig(out_path, dpi=300)
    plt.close()

    print("Saved:", out_path)

print("\nTest rendering complete.")
