"""Per-condition multimodal evidence figures.

For each clinical condition (tachycardia, bradycardia, normal, wide QRS,
left/right axis, normal axis), this script lays out the four modalities
that the dataset stores for that exact study:
  - Lead II waveform (annotated with measurements)
  - 12-lead waveform montage
  - Clean ECG PNG (from images_clean/)
  - Scan-like ECG JPG (from images_scanlike/)
  - Machine report text (T_machine snippet)

It also writes:
  - A combined "clean vs scan-like" before/after figure
  - A 12-lead reference plot
  - A "10-bin segmentation" figure used by Task B
"""

import json
import os

import numpy as np
import pandas as pd
from PIL import Image
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

ROOT = "D:/Coding/MU/Tri-Modal_ECG"
INDEX = os.path.join(ROOT, "processed", "index", "index_clean_with_measurements.parquet")
CLEAN_DIR = os.path.join(ROOT, "processed", "images_clean")
SCAN_DIR = os.path.join(ROOT, "processed", "images_scanlike")
SIG2_DIR = os.path.join(ROOT, "processed", "signals_lead2")
SIG12_DIR = os.path.join(ROOT, "processed", "signals_12lead")
EX = os.path.join(ROOT, "report_assets", "examples.json")
OUT_DIR = os.path.join(ROOT, "report_assets")

with open(EX) as f:
    examples = json.load(f)

plt.rcParams.update({
    "figure.dpi": 130,
    "savefig.dpi": 150,
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

LEAD_NAMES = ["I", "II", "III", "aVR", "aVL", "aVF",
              "V1", "V2", "V3", "V4", "V5", "V6"]


def save(fig, name):
    p = os.path.join(OUT_DIR, name)
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    print("wrote", p)


def load_lead2(sid):
    path = os.path.join(SIG2_DIR, f"{sid}.npy")
    return np.load(path)


def load_12lead(sid):
    path = os.path.join(SIG12_DIR, f"{sid}.npy")
    return np.load(path)


def load_img(p):
    return mpimg.imread(p)


def draw_ecg_grid(ax, x_max=10, y_min=-2, y_max=2, color_major="#ff5577",
                  color_minor="#ffaaaa"):
    """Draw a classic ECG-paper grid with 0.2 s major / 0.04 s minor lines."""
    ax.set_xlim(0, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_facecolor("#fffafa")
    for x in np.arange(0, x_max + 1e-9, 0.04):
        ax.axvline(x, color=color_minor, linewidth=0.4, zorder=0)
    for x in np.arange(0, x_max + 1e-9, 0.2):
        ax.axvline(x, color=color_major, linewidth=0.7, zorder=1)
    for y in np.arange(y_min, y_max + 1e-9, 0.1):
        ax.axhline(y, color=color_minor, linewidth=0.4, zorder=0)
    for y in np.arange(y_min, y_max + 1e-9, 0.5):
        ax.axhline(y, color=color_major, linewidth=0.7, zorder=1)


def normalize(signal):
    scale = np.percentile(np.abs(signal), 99)
    if scale > 0:
        return signal / scale * 1.2
    return signal


# ---------------------------------------------------------------------------
# 1. Tri-modal "one study, four modalities" hero figure
# ---------------------------------------------------------------------------
def make_trimodal_hero(key, title_suffix):
    e = examples[key]
    sid = e["study_id"]
    sig2 = load_lead2(sid)
    sig12 = load_12lead(sid)
    clean = load_img(os.path.join(CLEAN_DIR, f"{sid}.png"))
    scan = load_img(os.path.join(SCAN_DIR, f"{sid}.jpg"))

    fig = plt.figure(figsize=(15, 9))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.4, 1.4, 1.6], hspace=0.55, wspace=0.18)

    # row 0: clean image (left), scan-like image (right)
    ax = fig.add_subplot(gs[0, 0])
    ax.imshow(clean)
    ax.set_title("Modality 2: Clean ECG image (images_clean/{sid}.png)".format(sid=sid),
                 fontsize=11)
    ax.axis("off")
    ax = fig.add_subplot(gs[0, 1])
    ax.imshow(scan)
    ax.set_title("Modality 3: Scan-like ECG image (images_scanlike/{sid}.jpg)".format(sid=sid),
                 fontsize=11)
    ax.axis("off")

    # row 1: Lead II waveform (left, ECG paper style), 12-lead montage (right)
    t = np.linspace(0, 10, len(sig2))
    ax = fig.add_subplot(gs[1, 0])
    draw_ecg_grid(ax)
    ax.plot(t, normalize(sig2), color="#222", linewidth=0.9)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("Lead II (norm.)")
    ax.set_title("Modality 1: Lead II waveform (signals_lead2/{sid}.npy)".format(sid=sid),
                 fontsize=11)

    ax = fig.add_subplot(gs[1, 1])
    ax.set_facecolor("#fffafa")
    spacing = 2.0
    t12 = np.linspace(0, 10, sig12.shape[0])
    for i in range(12):
        s = sig12[:, i]
        s = normalize(s) * 0.6
        ax.plot(t12, s + (11 - i) * spacing, color="#222", linewidth=0.7)
        ax.text(-0.2, (11 - i) * spacing, LEAD_NAMES[i], ha="right", va="center",
                fontsize=9, weight="bold")
    ax.set_xlim(0, 10)
    ax.set_ylim(-1.5, 12 * spacing)
    ax.set_xlabel("time (s)")
    ax.set_yticks([])
    ax.set_title("12-lead montage (signals_12lead/{sid}.npy)".format(sid=sid), fontsize=11)

    # row 2: text + measurements panel (full width)
    ax = fig.add_subplot(gs[2, :])
    ax.axis("off")

    measurements = (
        f"study_id = {sid}    subject_id = {e['subject_id']}    split = {e['split']}\n"
        f"rr_interval = {e['rr_interval']:.1f} ms        HR = {e['hr']:.1f} bpm\n"
        f"qrs_onset = {e['qrs_onset']:.1f} ms    qrs_end = {e['qrs_end']:.1f} ms    "
        f"QRS duration = {e['qrs_dur']:.1f} ms\n"
        f"p_axis = {e['p_axis']:.0f}°    qrs_axis = {e['qrs_axis']:.0f}°    "
        f"t_axis = {e['t_axis']:.0f}°"
    )
    ax.text(0.01, 0.96, "Modality 4: Machine-generated report (T_machine)",
            transform=ax.transAxes, fontsize=11, weight="bold", va="top")
    text = e["T_machine"].strip()
    if len(text) > 320:
        text = text[:320] + " ..."
    ax.text(0.01, 0.83, text, transform=ax.transAxes, fontsize=10, va="top",
            family="monospace",
            bbox=dict(facecolor="#f4f4f4", edgecolor="#aaa", boxstyle="round,pad=0.4"))
    ax.text(0.01, 0.40, "Structured measurements (from machine_measurements.csv merge)",
            transform=ax.transAxes, fontsize=11, weight="bold", va="top")
    ax.text(0.01, 0.30, measurements, transform=ax.transAxes, fontsize=10, va="top",
            family="monospace",
            bbox=dict(facecolor="#f4f4f4", edgecolor="#aaa", boxstyle="round,pad=0.4"))

    fig.suptitle(f"Tri-modal example: {title_suffix} (study_id={sid})",
                 fontsize=13.5, weight="bold", y=0.995)
    return fig


for key, label in [("tachycardia", "Tachycardia (HR=123 bpm)"),
                   ("bradycardia", "Bradycardia (HR=50 bpm)"),
                   ("normal_high", "Normal heart rate (HR=91 bpm)")]:
    if key in examples:
        fig = make_trimodal_hero(key, label)
        save(fig, f"fig_hero_{key}.png")


# ---------------------------------------------------------------------------
# 2. Clean vs scan-like before/after for several conditions
# ---------------------------------------------------------------------------
def make_clean_vs_scan(keys_and_labels, out_name):
    n = len(keys_and_labels)
    fig, axes = plt.subplots(n, 2, figsize=(14, 2.4 * n))
    if n == 1:
        axes = np.array([axes])
    for i, (key, label) in enumerate(keys_and_labels):
        e = examples[key]
        sid = e["study_id"]
        clean = load_img(os.path.join(CLEAN_DIR, f"{sid}.png"))
        scan = load_img(os.path.join(SCAN_DIR, f"{sid}.jpg"))
        axes[i, 0].imshow(clean)
        axes[i, 0].axis("off")
        axes[i, 0].set_title(f"Clean PNG  •  {label}  •  study {sid}", fontsize=10)
        axes[i, 1].imshow(scan)
        axes[i, 1].axis("off")
        axes[i, 1].set_title(f"Scan-like JPG  •  same study (deterministic transform)", fontsize=10)
    fig.suptitle("Clean vs scan-like image: deterministic per-study transform",
                 fontsize=12.5, weight="bold", y=1.0)
    fig.tight_layout()
    return fig


fig = make_clean_vs_scan(
    [("tachycardia", "Tachycardia, HR=123"),
     ("bradycardia", "Bradycardia, HR=50"),
     ("wide_qrs", "Wide QRS, 138 ms"),
     ("normal_high", "Normal HR=91")],
    "fig_clean_vs_scan.png",
)
save(fig, "fig_clean_vs_scan.png")


# ---------------------------------------------------------------------------
# 3. Lead II waveform comparison for tachy / brady / normal / wide-QRS
# ---------------------------------------------------------------------------
fig, axes = plt.subplots(4, 1, figsize=(13, 9), sharex=True)
panels = [
    ("bradycardia", "Bradycardia"),
    ("normal_high", "Normal HR"),
    ("tachycardia", "Tachycardia"),
    ("wide_qrs", "Wide QRS"),
]
for ax, (key, label) in zip(axes, panels):
    e = examples[key]
    sid = e["study_id"]
    sig = load_lead2(sid)
    t = np.linspace(0, 10, len(sig))
    draw_ecg_grid(ax)
    ax.plot(t, normalize(sig), color="#222", linewidth=0.9)
    ax.set_ylabel("Lead II (norm.)")
    ax.set_title(
        f"{label}  •  study {sid}  •  HR={e['hr']:.0f} bpm  •  QRS={e['qrs_dur']:.0f} ms  •  axis={e['qrs_axis']:.0f}°",
        loc="left", fontsize=10.5,
    )
axes[-1].set_xlabel("time (s)")
fig.suptitle("Lead II waveform across HR / QRS conditions", fontsize=12.5, weight="bold")
fig.tight_layout()
save(fig, "fig_lead2_conditions.png")


# ---------------------------------------------------------------------------
# 4. Task B 10-bin temporal segmentation (using a tachycardia study so the
#    bins are labelled 1)
# ---------------------------------------------------------------------------
def make_taskB_bins(key, query):
    e = examples[key]
    sid = e["study_id"]
    sig = load_lead2(sid)
    t = np.linspace(0, 10, len(sig))
    sig = normalize(sig)
    # Replicate task_B.py logic
    hr = e["hr"]
    if hr is not None and hr > 100:
        labels = [1] * 10
    else:
        labels = [0] * 10

    fig, ax = plt.subplots(figsize=(13, 4.2))
    draw_ecg_grid(ax)
    ax.plot(t, sig, color="#222", linewidth=0.95)
    for i in range(10):
        x0, x1 = i, i + 1
        if labels[i] == 1:
            ax.axvspan(x0, x1, color="#54a24b", alpha=0.22, zorder=0)
        ax.text(x0 + 0.5, -1.85, f"bin{i}\n{labels[i]}", ha="center", va="bottom",
                fontsize=8.5, fontfamily="monospace",
                color="#54a24b" if labels[i] == 1 else "#666")
        if i > 0:
            ax.axvline(x0, color="#888", linestyle=":", linewidth=0.7)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("Lead II (norm.)")
    ax.set_title(
        f"Task B label format  •  query='{query}'  •  study {sid}  •  HR={hr:.0f} bpm  •  labels={labels}",
        fontsize=11,
    )
    return fig


fig = make_taskB_bins("tachycardia", "HIGH_HEART_RATE")
save(fig, "fig_taskB_bins_tachy.png")

fig = make_taskB_bins("normal_high", "HIGH_HEART_RATE")
save(fig, "fig_taskB_bins_normal.png")


# ---------------------------------------------------------------------------
# 5. Task A negative construction visual: positive vs each negative type
# ---------------------------------------------------------------------------
anchor = examples["normal_high"]
swap_text = examples["bradycardia"]
swap_image = examples["tachycardia"]
swap_signal = examples["wide_qrs"]
hard_neg = examples["normal_low"]

fig, axes = plt.subplots(7, 3, figsize=(13.5, 14),
                         gridspec_kw={"width_ratios": [1.2, 1.2, 1.5]})


def cell_label(ax, text, color="#444"):
    ax.axis("off")
    ax.text(0.5, 0.5, text, ha="center", va="center", wrap=True,
            fontsize=10.5, color=color)


def cell_signal(ax, sid):
    sig = load_lead2(sid)
    t = np.linspace(0, 10, len(sig))
    draw_ecg_grid(ax)
    ax.plot(t, normalize(sig), color="#222", linewidth=0.7)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"signal_id={sid}", fontsize=9)


def cell_image(ax, sid, kind):
    if kind == "clean":
        path = os.path.join(CLEAN_DIR, f"{sid}.png")
    else:
        path = os.path.join(SCAN_DIR, f"{sid}.jpg")
    ax.imshow(load_img(path))
    ax.axis("off")
    ax.set_title(f"image_id={sid} ({kind})", fontsize=9)


def cell_text(ax, sid, text):
    ax.axis("off")
    snippet = text.strip()
    if len(snippet) > 220:
        snippet = snippet[:220] + " ..."
    ax.text(0.02, 0.97, f"text_id={sid}", fontsize=9, weight="bold",
            transform=ax.transAxes, va="top")
    ax.text(0.02, 0.85, snippet, fontsize=8.5, family="monospace",
            transform=ax.transAxes, va="top", wrap=True,
            bbox=dict(facecolor="#f4f4f4", edgecolor="#aaa", boxstyle="round,pad=0.3"))


rows = [
    ("Positive (clean)\nsignal+image+text\nFROM SAME study", anchor, anchor, anchor, "clean", "#1f7a1f"),
    ("Positive (scan-like)\nsame study, scan image", anchor, anchor, anchor, "scanlike", "#1f7a1f"),
    ("TEXT_SWAP\nsignal+image OK,\ntext from another study", anchor, anchor, swap_text, "clean", "#b00020"),
    ("IMAGE_SWAP\nsignal+text OK,\nimage from another study", anchor, swap_image, anchor, "clean", "#b00020"),
    ("SIGNAL_SWAP\nimage+text OK,\nsignal from another study", swap_signal, anchor, anchor, "clean", "#b00020"),
    ("HARD_NEGATIVE_TEXT\ntext from another study\nin the SAME HR bucket", anchor, anchor, hard_neg, "clean", "#b00020"),
    ("PARTIAL_MISMATCH\nimage+text from one study,\nsignal from anchor", anchor, swap_image, swap_image, "clean", "#b00020"),
]

for r, (label, sig, img, txt, kind, color) in enumerate(rows):
    axes[r, 0].axis("off")
    axes[r, 0].text(0.02, 0.5, label, transform=axes[r, 0].transAxes,
                    fontsize=10.5, va="center", weight="bold", color=color)
    cell_signal(axes[r, 1], sig["study_id"])
    cell_image(axes[r, 1], img["study_id"], kind)  # last image overwrites; we need both...

# Actually we need separate columns for image; redo with 4 columns instead.
plt.close(fig)

fig, axes = plt.subplots(7, 4, figsize=(15, 16),
                         gridspec_kw={"width_ratios": [1.4, 1.1, 1.4, 1.6]})
for r, (label, sig, img, txt, kind, color) in enumerate(rows):
    axes[r, 0].axis("off")
    axes[r, 0].text(0.02, 0.5, label, transform=axes[r, 0].transAxes,
                    fontsize=10.5, va="center", weight="bold", color=color)
    cell_signal(axes[r, 1], sig["study_id"])
    cell_image(axes[r, 2], img["study_id"], kind)
    cell_text(axes[r, 3], txt["study_id"], txt["T_machine"])

fig.suptitle("Task A construction: 1 anchor study yields 2 positives + 5 negative types",
             fontsize=13, weight="bold", y=1.0)
fig.tight_layout()
save(fig, "fig_taskA_negatives.png")


# ---------------------------------------------------------------------------
# 6. Task A counts visual
# ---------------------------------------------------------------------------
import json as _json
with open(os.path.join(ROOT, "processed", "taskA_stats.json")) as f:
    a_stats = _json.load(f)

fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))
ax = axes[0]
labels_neg = list(a_stats["neg_types"].keys())
vals_neg = list(a_stats["neg_types"].values())
colors_neg = ["#4c78a8", "#54a24b", "#e58606", "#b279a2", "#d62728"]
bars = ax.bar(labels_neg, vals_neg, color=colors_neg, edgecolor="black")
for bar, v in zip(bars, vals_neg):
    ax.text(bar.get_x() + bar.get_width() / 2, v + 5000, f"{v:,}",
            ha="center", fontsize=9.5, weight="bold")
ax.set_title("Task A negative-type distribution")
ax.set_ylabel("Samples")
ax.tick_params(axis="x", rotation=18)
ax.set_ylim(0, max(vals_neg) * 1.1)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))

ax = axes[1]
labels_p = ["Positives", "Negatives"]
vals_p = [a_stats["positives"], a_stats["negatives"]]
colors_p = ["#54a24b", "#d62728"]
bars = ax.bar(labels_p, vals_p, color=colors_p, edgecolor="black")
for bar, v in zip(bars, vals_p):
    ax.text(bar.get_x() + bar.get_width() / 2, v + 50000, f"{v:,}",
            ha="center", fontsize=10, weight="bold")
ax.set_title(f"Task A overall ({a_stats['samples']:,} rows)")
ax.set_ylabel("Samples")
ax.set_ylim(0, max(vals_p) * 1.12)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))
fig.tight_layout()
save(fig, "fig_taskA_distribution.png")


# ---------------------------------------------------------------------------
# 7. Task A image-type distribution
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(6.2, 4.0))
labels_img = ["Clean image\n(positives + negatives)", "Scan-like image\n(positives only)"]
vals_img = [4798049, 799706]
bars = ax.bar(labels_img, vals_img, color=["#4c78a8", "#e58606"], edgecolor="black")
for bar, v in zip(bars, vals_img):
    ax.text(bar.get_x() + bar.get_width() / 2, v + 70000, f"{v:,}",
            ha="center", fontsize=10, weight="bold")
ax.set_title("Task A image-type distribution")
ax.set_ylabel("Samples")
ax.set_ylim(0, max(vals_img) * 1.12)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))
save(fig, "fig_taskA_imagetype.png")


print("done")
