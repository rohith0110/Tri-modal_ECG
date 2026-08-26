"""Standalone 12-lead montage figure for the raw-data section."""
import json
import os
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = "D:/Coding/MU/Tri-Modal_ECG"
SIG12_DIR = os.path.join(ROOT, "processed", "signals_12lead")
SIG2_DIR = os.path.join(ROOT, "processed", "signals_lead2")
EX = os.path.join(ROOT, "report_assets", "examples.json")
OUT = os.path.join(ROOT, "report_assets", "fig_12lead_montage.png")

with open(EX) as f:
    examples = json.load(f)

LEAD_NAMES = ["I", "II", "III", "aVR", "aVL", "aVF",
              "V1", "V2", "V3", "V4", "V5", "V6"]


def normalize(s):
    sc = np.percentile(np.abs(s), 99)
    return s / sc * 1.2 if sc > 0 else s


sid = examples["normal_high"]["study_id"]
sig = np.load(os.path.join(SIG12_DIR, f"{sid}.npy"))
t = np.linspace(0, 10, sig.shape[0])

fig, axes = plt.subplots(6, 2, figsize=(14, 9), sharex=True)
for i in range(12):
    r, c = divmod(i, 2)
    ax = axes[r, c]
    ax.plot(t, normalize(sig[:, i]), color="#222", linewidth=0.8)
    ax.set_facecolor("#fffafa")
    ax.set_ylim(-2, 2)
    for x in np.arange(0, 10.01, 0.04):
        ax.axvline(x, color="#ffaaaa", linewidth=0.3, zorder=0)
    for x in np.arange(0, 10.01, 0.2):
        ax.axvline(x, color="#ff5577", linewidth=0.6, zorder=1)
    for y in np.arange(-2, 2.01, 0.1):
        ax.axhline(y, color="#ffaaaa", linewidth=0.3, zorder=0)
    for y in np.arange(-2, 2.01, 0.5):
        ax.axhline(y, color="#ff5577", linewidth=0.6, zorder=1)
    ax.text(0.01, 0.92, LEAD_NAMES[i], transform=ax.transAxes,
            fontsize=10, weight="bold",
            bbox=dict(facecolor="white", edgecolor="none", boxstyle="round,pad=0.15"))
    if r < 5:
        ax.set_xticklabels([])
    else:
        ax.set_xlabel("time (s)")
    ax.tick_params(axis="y", labelsize=8)
fig.suptitle(
    f"Raw 12-lead WFDB record decoded by extract_ecg_signals.py  •  study {sid}  •  "
    f"5,000 samples / lead at 500 Hz",
    fontsize=13, weight="bold", y=0.995,
)
fig.tight_layout()
fig.savefig(OUT, bbox_inches="tight", dpi=150)
print("wrote", OUT)
