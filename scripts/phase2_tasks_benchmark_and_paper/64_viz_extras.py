"""Additional supporting figures for the report.

  - Before vs after amplitude normalization (raw mV vs scaled-to-1.2)
  - Scan-like augmentation pipeline visualization (rotation, blur,
    perspective, JPEG compression — applied to one example)
  - File-size and storage comparison (clean PNG vs scan-like JPG)
  - Pipeline runtime panel (uses the persisted run_metadata.json)
  - Hard-negative HR-bucket sampling diagram
"""

import json
import os
import random

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import cv2
from PIL import Image

ROOT = "D:/Coding/MU/Tri-Modal_ECG"
INDEX = os.path.join(ROOT, "processed", "index", "index_clean_with_measurements.parquet")
SIG2_DIR = os.path.join(ROOT, "processed", "signals_lead2")
CLEAN_DIR = os.path.join(ROOT, "processed", "images_clean")
SCAN_DIR = os.path.join(ROOT, "processed", "images_scanlike")
EX = os.path.join(ROOT, "report_assets", "examples.json")
RUN_META = os.path.join(ROOT, "scripts", "logs", "run_metadata.json")
OUT_DIR = os.path.join(ROOT, "report_assets")

with open(EX) as f:
    examples = json.load(f)

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 150, "font.size": 10.5,
    "axes.titlesize": 11.5, "axes.labelsize": 10.5,
    "axes.spines.top": False, "axes.spines.right": False,
})


def save(fig, name):
    p = os.path.join(OUT_DIR, name)
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    print("wrote", p)


def draw_ecg_grid(ax, x_max=10, y_min=-2, y_max=2):
    ax.set_xlim(0, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_facecolor("#fffafa")
    for x in np.arange(0, x_max + 1e-9, 0.04):
        ax.axvline(x, color="#ffaaaa", linewidth=0.4, zorder=0)
    for x in np.arange(0, x_max + 1e-9, 0.2):
        ax.axvline(x, color="#ff5577", linewidth=0.7, zorder=1)
    for y in np.arange(y_min, y_max + 1e-9, 0.1):
        ax.axhline(y, color="#ffaaaa", linewidth=0.4, zorder=0)
    for y in np.arange(y_min, y_max + 1e-9, 0.5):
        ax.axhline(y, color="#ff5577", linewidth=0.7, zorder=1)


# ---------------------------------------------------------------------------
# 1. Amplitude normalization before vs after
# ---------------------------------------------------------------------------
sid = examples["normal_high"]["study_id"]
sig = np.load(os.path.join(SIG2_DIR, f"{sid}.npy"))
t = np.linspace(0, 10, len(sig))
scale = np.percentile(np.abs(sig), 99)
sig_norm = sig / scale * 1.2 if scale > 0 else sig

fig, axes = plt.subplots(2, 1, figsize=(13, 6), sharex=True)
ax = axes[0]
ax.plot(t, sig, color="#222", linewidth=0.9)
ax.axhline(0, color="#888", linewidth=0.4)
ax.axhline(scale, color="#d62728", linestyle="--", linewidth=1, label=f"99th-pct |signal| = {scale:.3f} mV")
ax.axhline(-scale, color="#d62728", linestyle="--", linewidth=1)
ax.set_ylabel("raw amplitude\n(mV from WFDB)")
ax.set_title(f"Before normalization  •  Lead II raw  •  study {sid}")
ax.legend(loc="upper right")

ax = axes[1]
draw_ecg_grid(ax)
ax.plot(t, sig_norm, color="#222", linewidth=0.9)
ax.set_ylabel("scaled amplitude\n(after divide-by-99th-pct, x1.2)")
ax.set_xlabel("time (s)")
ax.set_title("After normalization  •  what render_clean_images.py actually plots")
fig.suptitle("Normalization step in render_clean_images.py keeps amplitudes in [-2, 2] regardless of raw mV scale",
             fontsize=12.5, weight="bold")
fig.tight_layout()
save(fig, "fig_normalization.png")


# ---------------------------------------------------------------------------
# 2. Scan-like augmentation pipeline: clean -> rotate -> perspective ->
#    blur -> brightness/contrast -> JPEG-compressed final
#    (Replicates generate_scanlike_images.py logic on one study.)
# ---------------------------------------------------------------------------
sid = examples["normal_high"]["study_id"]
img_clean = cv2.imread(os.path.join(CLEAN_DIR, f"{sid}.png"))

# Replicate generate_scanlike_images.py
rng = np.random.default_rng(int(sid))
h, w = img_clean.shape[:2]
new_w = min(1600, w)
img1 = cv2.resize(img_clean, (new_w, int(h * new_w / w)))

# rotation
angle = float(rng.uniform(-2, 2))
H, W = img1.shape[:2]
M = cv2.getRotationMatrix2D((W / 2, H / 2), angle, 1.0)
img2 = cv2.warpAffine(img1, M, (W, H), borderValue=(255, 255, 255))

# perspective
shift = float(rng.uniform(-1, 1) / 100 * W)
pts1 = np.float32([[0, 0], [W, 0], [0, H], [W, H]])
pts2 = np.float32([[0 + shift, 0], [W - shift, 0], [0, H], [W, H]])
P = cv2.getPerspectiveTransform(pts1, pts2)
img3 = cv2.warpPerspective(img2, P, (W, H), borderValue=(255, 255, 255))

# blur
k = int(rng.choice([3, 5]))
img4 = cv2.GaussianBlur(img3, (k, k), 0)

# brightness/contrast
alpha = float(rng.uniform(0.85, 1.15))
beta = float(rng.uniform(-15, 15))
img5 = cv2.convertScaleAbs(img4, alpha=alpha, beta=beta)

# jpeg compression (encode + decode to show the artifact)
quality = int(rng.integers(70, 96))
ok, buf = cv2.imencode(".jpg", img5, [cv2.IMWRITE_JPEG_QUALITY, quality])
img6 = cv2.imdecode(buf, cv2.IMREAD_COLOR)


def to_rgb(im):
    return cv2.cvtColor(im, cv2.COLOR_BGR2RGB)


fig, axes = plt.subplots(2, 3, figsize=(15, 6.5))
panels = [
    (img_clean, "1. Clean PNG (input)"),
    (img2, f"2. Rotation ({angle:+.2f}°)"),
    (img3, f"3. Perspective shift ({shift:+.1f} px)"),
    (img4, f"4. Gaussian blur (kernel={k})"),
    (img5, f"5. Brightness/contrast (alpha={alpha:.2f}, beta={beta:+.1f})"),
    (img6, f"6. JPEG compress (quality={quality}) -> final scan-like JPG"),
]
for ax, (im, title) in zip(axes.flat, panels):
    ax.imshow(to_rgb(im))
    ax.axis("off")
    ax.set_title(title, fontsize=10.5)
fig.suptitle(f"Scan-like augmentation pipeline (deterministic per study_id={sid})",
             fontsize=13, weight="bold")
fig.tight_layout()
save(fig, "fig_scanlike_pipeline.png")


# ---------------------------------------------------------------------------
# 3. File-size comparison: clean PNG vs scan-like JPG (sampled)
# ---------------------------------------------------------------------------
df = pd.read_parquet(INDEX)
sample_ids = df["study_id"].head(2000).tolist()
clean_sizes = []
scan_sizes = []
for sid in sample_ids:
    cp = os.path.join(CLEAN_DIR, f"{sid}.png")
    sp = os.path.join(SCAN_DIR, f"{sid}.jpg")
    if os.path.exists(cp) and os.path.exists(sp):
        clean_sizes.append(os.path.getsize(cp))
        scan_sizes.append(os.path.getsize(sp))

fig, axes = plt.subplots(1, 2, figsize=(11, 4.0))
ax = axes[0]
ax.hist(np.array(clean_sizes) / 1024, bins=40, color="#4c78a8", edgecolor="black",
        alpha=0.85, label=f"Clean PNG (n={len(clean_sizes):,})")
ax.hist(np.array(scan_sizes) / 1024, bins=40, color="#e58606", edgecolor="black",
        alpha=0.85, label=f"Scan-like JPG (n={len(scan_sizes):,})")
ax.set_xlabel("File size (KB)")
ax.set_ylabel("ECG studies")
ax.set_title("Per-image file size (random 2,000 study sample)")
ax.legend()

ax = axes[1]
totals = {
    "Lead II .npy\n(800,033)": 16472663136,
    "12-lead .npy\n(800,031)": 196615360384,
    "Clean PNG\n(800,033)": 147623940034,
    "Scan-like JPG\n(800,033)": 71565027783,
}
labels = list(totals.keys())
gb_vals = [v / 1024 ** 3 for v in totals.values()]
colors = ["#4c78a8", "#54a24b", "#e58606", "#b279a2"]
bars = ax.bar(labels, gb_vals, color=colors, edgecolor="black")
for bar, v in zip(bars, gb_vals):
    ax.text(bar.get_x() + bar.get_width() / 2, v + max(gb_vals) * 0.02,
            f"{v:.1f} GB", ha="center", fontsize=10, weight="bold")
ax.set_ylabel("Total bytes (GB)")
ax.set_title("Total storage by modality directory")
ax.set_ylim(0, max(gb_vals) * 1.18)
fig.tight_layout()
save(fig, "fig_storage_comparison.png")


# ---------------------------------------------------------------------------
# 4. Pipeline runtime panel
# ---------------------------------------------------------------------------
with open(RUN_META) as f:
    rm = json.load(f)
fig, ax = plt.subplots(figsize=(8.2, 3.6))
ax.axis("off")
text = (
    f"Persisted scan-like generation run (scripts/logs/run_metadata.json)\n\n"
    f"  timestamp        : {rm['timestamp']}\n"
    f"  num_workers      : {rm['num_workers']}\n"
    f"  total_studies    : {rm['total_studies']:,}\n"
    f"  ok               : {rm['stats']['ok']:,}\n"
    f"  skipped          : {rm['stats']['skip']:,}\n"
    f"  missing          : {rm['stats']['missing']:,}\n"
    f"  errored          : {rm['stats']['error']:,}\n"
    f"  elapsed (mins)   : {rm['elapsed_minutes']:.2f}\n"
)
ax.text(0.0, 1.0, text, family="monospace", fontsize=11.5, va="top",
        bbox=dict(facecolor="#f4f4f4", edgecolor="#aaa", boxstyle="round,pad=0.6"))
ax.set_title("Persisted runtime evidence (intermediate scan-like pass)",
             fontsize=12.5, weight="bold", loc="left")
save(fig, "fig_runtime_panel.png")


# ---------------------------------------------------------------------------
# 5. Hard-negative HR-bucket sampling diagram
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(12, 4.6))
ax.axis("off")
buckets = [("brady", "HR < 60", 123353, "#5fa8d3"),
           ("normal_low", "60-80", 362372, "#54a24b"),
           ("normal_high", "80-100", 206115, "#a5c953"),
           ("tachy", "HR >= 100", 107679, "#e58606")]

for i, (name, rng_str, n, color) in enumerate(buckets):
    x_left = 0.04 + i * 0.24
    box_w = 0.20
    ax.add_patch(plt.Rectangle((x_left, 0.42), box_w, 0.32, facecolor=color,
                                edgecolor="black", linewidth=0.9))
    ax.text(x_left + box_w / 2, 0.65, name, ha="center", weight="bold", fontsize=11.5)
    ax.text(x_left + box_w / 2, 0.57, rng_str, ha="center", fontsize=10)
    ax.text(x_left + box_w / 2, 0.48, f"{n:,} studies", ha="center", fontsize=9.5,
            family="monospace")
    # self-loop arrow above each bucket showing intra-bucket sampling
    cx = x_left + box_w / 2
    ax.annotate(
        "", xy=(cx + 0.04, 0.78), xytext=(cx - 0.04, 0.78),
        arrowprops=dict(arrowstyle="-|>", connectionstyle="arc3,rad=-0.7",
                        color="#444", lw=1.3),
    )
    ax.text(cx, 0.83, "anchor <-> hard-neg\n(within bucket)",
            ha="center", fontsize=8.5, color="#444")

ax.text(0.02, 0.32,
        "HARD_NEGATIVE_TEXT sampling (Task A): for each anchor, swap text with another\n"
        "study from the SAME HR bucket. The model cannot shortcut the decision using\n"
        "obvious heart-rate cues in the text. Studies with invalid RR (n=187) cannot\n"
        "participate, which is why HARD_NEGATIVE_TEXT has 799,519 rows instead of 799,706.",
        fontsize=10.5, va="top",
        bbox=dict(facecolor="#fffce6", edgecolor="#aaa", boxstyle="round,pad=0.4"))
ax.set_xlim(0, 1)
ax.set_ylim(0.05, 1.0)
ax.set_title("HR-bucket logic for hard text negatives in Task A",
             fontsize=12.5, weight="bold", loc="left")
save(fig, "fig_hr_bucket_logic.png")


# ---------------------------------------------------------------------------
# 6. Axis-deviation example (left axis vs right axis vs normal)
# ---------------------------------------------------------------------------
fig, axes = plt.subplots(3, 1, figsize=(13, 6.6), sharex=True)
panels = [("left_axis", "Left axis deviation"),
          ("normal_axis", "Normal axis"),
          ("right_axis", "Right axis deviation")]
for ax, (key, label) in zip(axes, panels):
    e = examples[key]
    sig = np.load(os.path.join(SIG2_DIR, f"{e['study_id']}.npy"))
    s = np.percentile(np.abs(sig), 99)
    sn = sig / s * 1.2 if s > 0 else sig
    t = np.linspace(0, 10, len(sn))
    draw_ecg_grid(ax)
    ax.plot(t, sn, color="#222", linewidth=0.9)
    ax.set_ylabel("Lead II (norm.)")
    ax.set_title(
        f"{label}  •  study {e['study_id']}  •  qrs_axis = {e['qrs_axis']:.0f}°  "
        f"•  HR={e['hr']:.0f} bpm",
        loc="left", fontsize=11,
    )
axes[-1].set_xlabel("time (s)")
fig.suptitle("Axis-deviation evidence drives Task C 'left/right axis deviation' claims",
             fontsize=12.5, weight="bold")
fig.tight_layout()
save(fig, "fig_axis_examples.png")


# ---------------------------------------------------------------------------
# 7. QC pass/fail visualization
# ---------------------------------------------------------------------------
total_split = 800033
qc_pass = 799706
qc_fail = total_split - qc_pass
fig, ax = plt.subplots(figsize=(7.5, 3.6))
ax.barh(["QC pass\n(waveform_ok &\nimage_ok &\ntext_ok)",
        "QC fail\n(any modality\nmissing or invalid)"],
        [qc_pass, qc_fail], color=["#54a24b", "#d62728"], edgecolor="black")
ax.text(qc_pass - 30000, 0, f"{qc_pass:,}", va="center", ha="right",
        color="white", weight="bold", fontsize=12)
ax.text(qc_fail + total_split * 0.005, 1, f"{qc_fail:,}",
        va="center", color="#444", weight="bold", fontsize=11)
ax.set_xlabel("Studies in index_with_split.parquet")
ax.set_title(f"Tri-modal QC outcome (gates index_clean.parquet)",
             fontsize=12, weight="bold")
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))
save(fig, "fig_qc_outcome.png")

print("done")
