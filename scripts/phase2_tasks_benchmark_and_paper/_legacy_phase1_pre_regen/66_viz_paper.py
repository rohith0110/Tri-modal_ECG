"""Paper-only figures — placed in paper/figures/.

  - fig_feature_matrix.png  : MEETI vs Tri-Modal feature comparison heatmap
  - fig_taskB_before_after.png : per-bin positive fraction BEFORE (global rule)
                                vs AFTER (local detection) — strongest evidence
                                that the temporal localization signal is real
  - fig_taskB_examples.png  : six real cleaned studies, each showing the Lead II
                              waveform with HIGH/LOW/WIDE per-bin labels overlaid
                              on the ECG-paper grid (ground-truth proof)
  - fig_pipeline_paper.png  : compact two-row pipeline diagram suited for a
                              two-column paper layout
  - fig_modality_montage.png: 2x2 montage showing the four modalities for a
                              single study (signal, clean PNG, scan-like JPG,
                              text+measurements) - the "data card"
"""

import json
import os
import shutil

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import Rectangle

ROOT = "D:/Coding/MU/Tri-Modal_ECG"
INDEX = os.path.join(ROOT, "processed", "index", "index_clean_with_measurements.parquet")
SIG2_DIR = os.path.join(ROOT, "processed", "signals_lead2")
CLEAN_DIR = os.path.join(ROOT, "processed", "images_clean")
SCAN_DIR = os.path.join(ROOT, "processed", "images_scanlike")
TASKB_JSONL = os.path.join(ROOT, "processed", "taskB_temporal_grounding.jsonl")
TASKB_STATS = os.path.join(ROOT, "report_assets", "taskB_stats.json")
EX = os.path.join(ROOT, "report_assets", "examples.json")
FIGS = os.path.join(ROOT, "paper", "figures")
ASSETS = os.path.join(ROOT, "report_assets")

os.makedirs(FIGS, exist_ok=True)

with open(EX) as f:
    examples = json.load(f)
with open(TASKB_STATS) as f:
    tb_stats = json.load(f)

plt.rcParams.update({
    "figure.dpi": 140,
    "savefig.dpi": 200,
    "font.size": 9.5,
    "axes.titlesize": 10.5,
    "axes.labelsize": 9.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "legend.fontsize": 9,
    "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5,
    "font.family": "DejaVu Sans",
})


def save(fig, name):
    p = os.path.join(FIGS, name)
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    print("wrote", p)


def draw_ecg_grid(ax, x_max=10, y_min=-2, y_max=2, light=False):
    ax.set_xlim(0, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_facecolor("#fffafa")
    minor = "#ffcaca" if light else "#ffaaaa"
    major = "#ff7090" if light else "#ff5577"
    for x in np.arange(0, x_max + 1e-9, 0.04):
        ax.axvline(x, color=minor, linewidth=0.3, zorder=0)
    for x in np.arange(0, x_max + 1e-9, 0.2):
        ax.axvline(x, color=major, linewidth=0.6, zorder=1)
    for y in np.arange(y_min, y_max + 1e-9, 0.1):
        ax.axhline(y, color=minor, linewidth=0.3, zorder=0)
    for y in np.arange(y_min, y_max + 1e-9, 0.5):
        ax.axhline(y, color=major, linewidth=0.6, zorder=1)


def normalize(s):
    sc = np.percentile(np.abs(s), 99)
    return s / sc * 1.2 if sc > 0 else s


# ---------------------------------------------------------------------------
# 1. MEETI vs Tri-Modal-ECG feature matrix
# ---------------------------------------------------------------------------
features = [
    ("ECG signals (Lead II + 12-lead) on disk", 1, 1),
    ("Clean ECG images (full dataset)", 0, 1),
    ("Scan-like ECG images (deterministic distortion)", 0, 1),
    ("Text reports per study", 1, 1),
    ("Beat-level measurements (PR / QRS / QTc)", 1, 1),
    ("Standardized image rendering script", 1, 1),
    ("Multi-stage QC with persisted JSON audit", 0, 1),
    ("Image-level integrity audit (PIL + OpenCV)", 0, 1),
    ("Patient-level train / val / test split", 0, 1),
    ("Documented leakage-prevention checks", 0, 1),
    ("Cross-modal verification dataset (signal/image/text)", 0, 1),
    ("Hard-negative HR-bucket sampling", 0, 1),
    ("Temporal-grounding labels per 1 s bin", 0, 1),
    ("Local R-peak / QRS-onset detection (NeuroKit2)", 0, 1),
    ("Plausibility claim dataset (SUPP/CONT/UNC)", 0, 1),
    ("Reproducible deterministic generation (no LLM)", 0, 1),
    ("Per-modality storage budget reported", 0, 1),
    ("Full-dataset image coverage (~800K, not ~10K)", 0, 1),
]
fig, ax = plt.subplots(figsize=(8.4, 7.8))
mat = np.array([[a, b] for _, a, b in features])
ax.imshow(mat, aspect="auto", cmap="Greens", vmin=0, vmax=1.4)
ax.set_xticks([0, 1])
ax.set_xticklabels(["MEETI", "Tri-Modal-ECG (ours)"], fontsize=11, weight="bold")
ax.set_yticks(range(len(features)))
ax.set_yticklabels([f[0] for f in features])
for i in range(mat.shape[0]):
    for j in range(mat.shape[1]):
        ax.text(j, i, "yes" if mat[i, j] else "no",
                ha="center", va="center",
                fontsize=10, weight="bold",
                color="white" if mat[i, j] else "#888")
ax.set_title("Feature matrix: Tri-Modal-ECG extends MEETI's MIMIC-IV-ECG release",
             fontsize=11.5, weight="bold")
ax.tick_params(left=False)
fig.tight_layout()
save(fig, "fig_feature_matrix.png")


# ---------------------------------------------------------------------------
# 2. Task B before/after (global rule vs local detection)
# ---------------------------------------------------------------------------
# Old "global rule" baseline: per-query positive rates if we used hr > 100 only.
# Recompute the synthetic baseline from the cleaned index (RR-based):
df = pd.read_parquet(INDEX, columns=["study_id", "rr_interval", "qrs_onset", "qrs_end"])
df["hr"] = 60000.0 / df["rr_interval"].replace(0, np.nan)
df["qrs_dur"] = df["qrs_end"] - df["qrs_onset"]

old_high = int((df["hr"] > 100).sum())
old_low = 0   # the original code never checked HR<60
old_wide = 0  # the original code never checked QRS>120

new_high = tb_stats["any_pos"]["HIGH_HEART_RATE"]
new_low = tb_stats["any_pos"]["LOW_HEART_RATE"]
new_wide = tb_stats["any_pos"]["WIDE_QRS"]

queries = ["HIGH_HEART_RATE", "LOW_HEART_RATE", "WIDE_QRS"]
old_vals = [old_high, old_low, old_wide]
new_vals = [new_high, new_low, new_wide]

fig, axes = plt.subplots(1, 2, figsize=(13, 4.4))

ax = axes[0]
x = np.arange(len(queries))
w = 0.36
ax.bar(x - w / 2, old_vals, w, label="before fix (global rule)", color="#aaaaaa", edgecolor="black")
ax.bar(x + w / 2, new_vals, w, label="after fix (local detection)", color="#54a24b", edgecolor="black")
for i, v in enumerate(old_vals):
    ax.text(i - w / 2, v + 8000, f"{v:,}", ha="center", fontsize=9, weight="bold")
for i, v in enumerate(new_vals):
    ax.text(i + w / 2, v + 8000, f"{v:,}", ha="center", fontsize=9, weight="bold")
ax.set_xticks(x)
ax.set_xticklabels(queries)
ax.set_ylabel("Studies with any positive bin")
ax.set_title("Per-query positive-row count: before vs after")
ax.legend()
ax.set_ylim(0, max(new_vals) * 1.18)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))

ax = axes[1]
mat = np.zeros((3, 10))
for i, q in enumerate(queries):
    pb = np.array(tb_stats["per_bin_pos"][q], dtype=float)
    mat[i, :] = pb / max(tb_stats["totals"][q], 1)
im = ax.imshow(mat, aspect="auto", cmap="Greens", vmin=0, vmax=mat.max() * 1.05)
ax.set_xticks(range(10))
ax.set_xticklabels([f"bin{i}" for i in range(10)])
ax.set_yticks(range(3))
ax.set_yticklabels(queries)
for i in range(mat.shape[0]):
    for j in range(mat.shape[1]):
        ax.text(j, i, f"{mat[i, j]:.2f}", ha="center", va="center", fontsize=8.5,
                color="white" if mat[i, j] > mat.max() * 0.5 else "#222")
ax.set_title("Per-bin positive fraction (after fix)\nNon-uniform = real temporal localization signal")
fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
fig.suptitle("Task B label fix: from global rule (uniform) to local detection (temporal)",
             fontsize=12.5, weight="bold")
fig.tight_layout()
save(fig, "fig_taskB_before_after.png")


# ---------------------------------------------------------------------------
# 3. Real per-study Task B examples — load the actual JSONL labels
# ---------------------------------------------------------------------------
# We want pedagogically clear examples: studies whose label vector has a
# *contiguous* run of positives (so the rhythm change is visually obvious),
# not the first arbitrary mixed row in iteration order.
def _label_score(labels):
    """Higher = more pedagogically compelling.
    Reward 3-7 positives forming a single contiguous block."""
    s = sum(labels)
    if not (3 <= s <= 7):
        return -1
    runs = []
    cur = 0
    for x in labels:
        if x:
            cur += 1
        else:
            if cur:
                runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    longest = max(runs) if runs else 0
    fragmentation = len(runs)
    return longest * 10 - fragmentation


candidates = {"HIGH_HEART_RATE": None, "LOW_HEART_RATE": None, "WIDE_QRS": None}
best_score = {q: -1 for q in candidates}
with open(TASKB_JSONL, "r", encoding="utf-8") as f:
    for line in f:
        rec = json.loads(line)
        q = rec["query"]
        if q not in candidates:
            continue
        sc = _label_score(rec["labels"])
        if sc <= best_score[q]:
            continue
        if not os.path.exists(os.path.join(SIG2_DIR, f"{rec['study_id']}.npy")):
            continue
        candidates[q] = rec
        best_score[q] = sc
        # Score saturates at 69 (single contiguous run of 7); stop early per query.
        if all(v >= 69 for v in best_score.values()):
            break


fig, axes = plt.subplots(3, 1, figsize=(13.5, 7.6), sharex=True)
for ax, q in zip(axes, ["HIGH_HEART_RATE", "LOW_HEART_RATE", "WIDE_QRS"]):
    rec = candidates[q]
    if rec is None:
        ax.set_visible(False)
        continue
    sid = rec["study_id"]
    sig = np.load(os.path.join(SIG2_DIR, f"{sid}.npy"))
    t = np.linspace(0, 10, len(sig))
    draw_ecg_grid(ax)
    ax.plot(t, normalize(sig), color="#222", linewidth=0.85)
    labels = rec["labels"]
    for i in range(10):
        if labels[i] == 1:
            ax.axvspan(i, i + 1, color="#54a24b", alpha=0.22, zorder=0)
    for i in range(10):
        ax.text(i + 0.5, -1.85, f"{labels[i]}",
                ha="center", va="bottom", fontsize=10,
                weight="bold", family="monospace",
                color="#1f7a1f" if labels[i] == 1 else "#888")
        if i > 0:
            ax.axvline(i, color="#999", linestyle=":", linewidth=0.6)
    ax.set_ylabel("Lead II (norm.)")
    ax.set_title(
        f"query='{q}'  •  study {sid}  •  labels={labels}  •  split={rec['split']}",
        loc="left", fontsize=10.5,
    )
axes[-1].set_xlabel("time (s)")
fig.suptitle("Task B local detection: temporally specific labels on real cleaned studies",
             fontsize=12.5, weight="bold")
fig.tight_layout()
save(fig, "fig_taskB_examples.png")


# ---------------------------------------------------------------------------
# 4. Compact pipeline diagram (paper-friendly two-row layout)
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(13.5, 4.6))
ax.axis("off")

row1 = [("Raw MIMIC-IV\n(record_list.csv,\nmachine_measurements,\nWFDB files)", "#cfe8ff"),
        ("build_master_index\n(parquet, chunked)", "#cfe8ff"),
        ("create_patient_split\n(80/10/10, leakage check)", "#cfe8ff"),
        ("extract_ecg_signals\n(WFDB -> .npy,\nLead II + 12-lead)", "#d3f2c2"),
        ("render_clean_images\n(Matplotlib ECG paper)", "#d3f2c2")]

row2 = [("generate_scanlike\n(OpenCV: rotate/skew/\nblur/JPEG, deterministic)", "#d3f2c2"),
        ("image_integrity_check\n+ corrupt_check\n(PIL + OpenCV)", "#ffe2b3"),
        ("qc.py\n(per-study JSON,\ntri-modal validity)", "#ffe2b3"),
        ("cleanup_master_index\n+ add_measurements\n(799,706 rows)", "#ffe2b3"),
        ("task_A / task_B / task_C\n(JSONL, 5.6M / 2.4M / 4.7M)", "#f5c2c2")]


def draw_row(stages, y):
    n = len(stages)
    box_w = 0.16
    gap = (1.0 - n * box_w) / (n + 1)
    centers = []
    for i, (label, color) in enumerate(stages):
        x_left = gap + i * (box_w + gap)
        ax.add_patch(Rectangle((x_left, y - 0.13), box_w, 0.26,
                               facecolor=color, edgecolor="black", linewidth=0.9))
        ax.text(x_left + box_w / 2, y, label, ha="center", va="center",
                fontsize=8.6, weight="bold")
        centers.append((x_left, x_left + box_w))
        if i < n - 1:
            x_next = gap + (i + 1) * (box_w + gap)
            ax.annotate("", xy=(x_next, y), xytext=(x_left + box_w, y),
                        arrowprops=dict(arrowstyle="->", lw=1, color="#444"))
    return centers


cs1 = draw_row(row1, 0.74)
cs2 = draw_row(row2, 0.26)
# row1 right edge to row2 left edge with curved arrow
ax.annotate("", xy=(cs2[0][0], 0.40), xytext=(cs1[-1][1], 0.61),
            arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=-0.3",
                            lw=1.1, color="#444"))
ax.set_xlim(0, 1)
ax.set_ylim(0.06, 0.92)
ax.set_title("Tri-Modal-ECG construction pipeline (10 stages, fully reproducible)",
             fontsize=12, weight="bold")
save(fig, "fig_pipeline_paper.png")


# ---------------------------------------------------------------------------
# 5. Modality montage / data card
# ---------------------------------------------------------------------------
sid_e = examples["normal_high"]
sid = sid_e["study_id"]
sig = np.load(os.path.join(SIG2_DIR, f"{sid}.npy"))
clean = mpimg.imread(os.path.join(CLEAN_DIR, f"{sid}.png"))
scan = mpimg.imread(os.path.join(SCAN_DIR, f"{sid}.jpg"))

fig = plt.figure(figsize=(13, 7.4))
gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.1], hspace=0.45, wspace=0.18)
# (a) Lead II
ax = fig.add_subplot(gs[0, 0])
draw_ecg_grid(ax)
ax.plot(np.linspace(0, 10, len(sig)), normalize(sig), color="#222", linewidth=0.85)
ax.set_xlabel("time (s)")
ax.set_ylabel("Lead II (norm.)")
ax.set_title(f"(a) Modality 1: Lead II waveform — signals_lead2/{sid}.npy",
             fontsize=10.5, loc="left")
# (b) clean PNG
ax = fig.add_subplot(gs[0, 1])
ax.imshow(clean)
ax.axis("off")
ax.set_title(f"(b) Modality 2: clean ECG PNG — images_clean/{sid}.png",
             fontsize=10.5, loc="left")
# (c) scan-like JPG
ax = fig.add_subplot(gs[1, 0])
ax.imshow(scan)
ax.axis("off")
ax.set_title(f"(c) Modality 3: scan-like JPG — images_scanlike/{sid}.jpg",
             fontsize=10.5, loc="left")
# (d) text + measurements
ax = fig.add_subplot(gs[1, 1])
ax.axis("off")
ax.set_title("(d) Modality 4: machine report + structured measurements",
             fontsize=10.5, loc="left")
text = sid_e["T_machine"].strip()
if len(text) > 280:
    text = text[:280] + " ..."
meas = (
    f"study_id     = {sid}\n"
    f"subject_id   = {sid_e['subject_id']}\n"
    f"split        = {sid_e['split']}\n"
    f"rr_interval  = {sid_e['rr_interval']:.0f} ms  (HR = {sid_e['hr']:.0f} bpm)\n"
    f"qrs_onset    = {sid_e['qrs_onset']:.0f} ms\n"
    f"qrs_end      = {sid_e['qrs_end']:.0f} ms\n"
    f"qrs_dur      = {sid_e['qrs_dur']:.0f} ms\n"
    f"qrs_axis     = {sid_e['qrs_axis']:.0f} deg\n"
    f"p_axis       = {sid_e['p_axis']:.0f} deg\n"
    f"t_axis       = {sid_e['t_axis']:.0f} deg"
)
ax.text(0.0, 0.97, "T_machine (concatenated report fields):",
        transform=ax.transAxes, fontsize=9.5, weight="bold", va="top")
ax.text(0.0, 0.83, text, transform=ax.transAxes, fontsize=8.7, family="monospace",
        va="top", wrap=True,
        bbox=dict(facecolor="#f4f4f4", edgecolor="#aaa", boxstyle="round,pad=0.35"))
ax.text(0.0, 0.42, "structured measurements (machine_measurements.csv):",
        transform=ax.transAxes, fontsize=9.5, weight="bold", va="top")
ax.text(0.0, 0.30, meas, transform=ax.transAxes, fontsize=8.7, family="monospace",
        va="top",
        bbox=dict(facecolor="#f4f4f4", edgecolor="#aaa", boxstyle="round,pad=0.35"))
fig.suptitle(f"One Tri-Modal-ECG record (study_id = {sid})", fontsize=12.5, weight="bold")
save(fig, "fig_modality_montage.png")


# ---------------------------------------------------------------------------
# 6. Copy a small set of polished figures from report_assets so the paper is
#    self-contained inside paper/figures/.
# ---------------------------------------------------------------------------
to_copy = [
    "fig_pipeline_architecture.png",
    "fig_dataset_funnel.png",
    "fig_modality_coverage.png",
    "fig_regeneration_before_after.png",
    "fig_qc_outcome.png",
    "fig_split_distribution.png",
    "fig_ecgs_per_patient.png",
    "fig_hr_distribution.png",
    "fig_qrs_duration.png",
    "fig_qrs_axis.png",
    "fig_normalization.png",
    "fig_scanlike_pipeline.png",
    "fig_clean_vs_scan.png",
    "fig_storage_comparison.png",
    "fig_taskA_negatives.png",
    "fig_taskA_distribution.png",
    "fig_taskA_imagetype.png",
    "fig_hr_bucket_logic.png",
    "fig_taskB_distribution.png",
    "fig_taskC_distribution.png",
    "fig_taskC_heatmap.png",
    "fig_taskC_walkthrough.png",
    "fig_axis_examples.png",
    "fig_lead2_conditions.png",
    "fig_hero_tachycardia.png",
    "fig_hero_bradycardia.png",
    "fig_hero_normal_high.png",
    "fig_12lead_montage.png",
]
for fn in to_copy:
    src = os.path.join(ASSETS, fn)
    dst = os.path.join(FIGS, fn)
    if os.path.exists(src):
        shutil.copyfile(src, dst)
        print("copied", fn)
print("done")
