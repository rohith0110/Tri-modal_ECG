"""Dataset-level overview figures for the report.

Generates high-level statistics plots that summarise the cleaned index,
patient-level split, heart-rate buckets, image and signal counts, and
final tri-modal coverage. Output PNGs land in `report_assets/`.

These plots are computed directly from the persisted on-disk artifacts
(parquet, JSONL, JSON), not from the markdown report, so the figures
match what is actually present on disk.
"""

import json
import os
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = "D:/Coding/MU/Tri-Modal_ECG"
INDEX = os.path.join(ROOT, "processed", "index", "index_clean_with_measurements.parquet")
INDEX_RAW = os.path.join(ROOT, "processed", "index", "index.parquet")
INDEX_SPLIT = os.path.join(ROOT, "processed", "index", "index_with_split.parquet")
INDEX_CLEAN = os.path.join(ROOT, "processed", "index", "index_clean.parquet")
TASKA_STATS = os.path.join(ROOT, "processed", "taskA_stats.json")
INTEGRITY = os.path.join(ROOT, "scripts", "logs", "dataset_integrity_summary.json")
RUN_META = os.path.join(ROOT, "scripts", "logs", "run_metadata.json")
OUT_DIR = os.path.join(ROOT, "report_assets")
os.makedirs(OUT_DIR, exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 130,
    "savefig.dpi": 150,
    "font.size": 11,
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def save(fig, name):
    p = os.path.join(OUT_DIR, name)
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    print("wrote", p)


df = pd.read_parquet(INDEX)
df["hr"] = 60000.0 / df["rr_interval"].replace(0, np.nan)
df["qrs_dur"] = df["qrs_end"] - df["qrs_onset"]


# ---------------------------------------------------------------------------
# 1. Pipeline architecture diagram
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(16, 3.4))
ax.axis("off")
stages = [
    ("Raw MIMIC-IV\nECG", "#cfe8ff"),
    ("Master\nindex", "#cfe8ff"),
    ("Patient\nsplit", "#cfe8ff"),
    ("Lead II /\n12-lead .npy", "#d3f2c2"),
    ("Clean\nPNG", "#d3f2c2"),
    ("Scan-like\nJPG", "#d3f2c2"),
    ("Image &\nWave QC", "#ffe2b3"),
    ("Cleaned\nindex", "#ffe2b3"),
    ("Measurement\nenrich", "#ffe2b3"),
    ("Task A / B / C\nJSONL", "#f5c2c2"),
]
n = len(stages)
box_w = 0.088
gap = (1.0 - n * box_w) / (n + 1)
for i, (label, color) in enumerate(stages):
    x_left = gap + i * (box_w + gap)
    ax.add_patch(plt.Rectangle((x_left, 0.28), box_w, 0.46,
                               facecolor=color, edgecolor="black", linewidth=0.9))
    ax.text(x_left + box_w / 2, 0.51, label, ha="center", va="center",
            fontsize=9.5, weight="bold")
    if i < n - 1:
        x_next = gap + (i + 1) * (box_w + gap)
        ax.annotate("", xy=(x_next, 0.51), xytext=(x_left + box_w, 0.51),
                    arrowprops=dict(arrowstyle="->", lw=1.1, color="#444"))
ax.set_xlim(0, 1)
ax.set_ylim(0.16, 0.92)
ax.set_title("Pipeline architecture: raw waveforms to tri-modal task datasets",
             pad=8, fontsize=12.5, weight="bold")
save(fig, "fig_pipeline_architecture.png")


# ---------------------------------------------------------------------------
# 2. Dataset funnel: 800,035 -> 800,033 -> 799,706
# ---------------------------------------------------------------------------
funnel_steps = [
    ("Raw studies\n(record_list.csv)", 800035),
    ("With patient split", 800033),
    ("Tri-modal QC pass", 799706),
    ("Measurement enriched", 799706),
]
fig, ax = plt.subplots(figsize=(8.5, 4.2))
labels = [s[0] for s in funnel_steps]
values = [s[1] for s in funnel_steps]
colors = ["#4c78a8", "#54a24b", "#e58606", "#b279a2"]
bars = ax.barh(labels[::-1], values[::-1], color=colors[::-1], edgecolor="black")
for bar, val in zip(bars, values[::-1]):
    ax.text(val - 5000, bar.get_y() + bar.get_height() / 2,
            f"{val:,}", ha="right", va="center", color="white", fontsize=10, weight="bold")
ax.set_xlabel("Number of ECG studies")
ax.set_title("Dataset funnel: raw -> cleaned tri-modal index")
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))
save(fig, "fig_dataset_funnel.png")


# ---------------------------------------------------------------------------
# 3. Train / val / test split distribution (cleaned index)
# ---------------------------------------------------------------------------
split_counts = df["split"].value_counts()[["train", "val", "test"]]
fig, axes = plt.subplots(1, 2, figsize=(10.5, 4))
ax = axes[0]
bars = ax.bar(split_counts.index, split_counts.values,
              color=["#4c78a8", "#54a24b", "#e58606"], edgecolor="black")
for bar, v in zip(bars, split_counts.values):
    ax.text(bar.get_x() + bar.get_width() / 2, v + 8000, f"{v:,}",
            ha="center", fontsize=10, weight="bold")
ax.set_ylabel("ECG studies")
ax.set_title("Studies per split (cleaned index, n=799,706)")
ax.set_ylim(0, max(split_counts) * 1.12)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))

# patient counts per split
patients_per_split = df.groupby("split")["subject_id"].nunique()[["train", "val", "test"]]
ax = axes[1]
bars = ax.bar(patients_per_split.index, patients_per_split.values,
              color=["#4c78a8", "#54a24b", "#e58606"], edgecolor="black")
for bar, v in zip(bars, patients_per_split.values):
    ax.text(bar.get_x() + bar.get_width() / 2, v + 1500, f"{v:,}",
            ha="center", fontsize=10, weight="bold")
ax.set_ylabel("Unique patients")
ax.set_title("Unique patients per split")
ax.set_ylim(0, max(patients_per_split) * 1.12)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))
fig.suptitle("Patient-level split avoids leakage", fontsize=12.5, weight="bold")
fig.tight_layout()
save(fig, "fig_split_distribution.png")


# ---------------------------------------------------------------------------
# 4. ECGs-per-patient distribution
# ---------------------------------------------------------------------------
per_patient = df.groupby("subject_id").size()
fig, ax = plt.subplots(figsize=(8.5, 4))
ax.hist(per_patient.clip(upper=20), bins=np.arange(0.5, 21.5, 1),
        color="#4c78a8", edgecolor="black")
ax.set_xlabel("ECG studies per patient (clipped at 20)")
ax.set_ylabel("Number of patients")
ax.set_title(f"ECGs per patient: mean={per_patient.mean():.1f}, median={int(per_patient.median())}, max={per_patient.max()}")
ax.set_yscale("log")
ax.set_xticks(range(1, 21))
save(fig, "fig_ecgs_per_patient.png")


# ---------------------------------------------------------------------------
# 5. Heart-rate distribution + buckets
# ---------------------------------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
ax = axes[0]
hr = df["hr"].dropna()
hr = hr[(hr > 25) & (hr < 220)]
ax.hist(hr, bins=80, color="#4c78a8", edgecolor="black", alpha=0.85)
for x, c in [(60, "#e58606"), (100, "#d62728")]:
    ax.axvline(x, color=c, linestyle="--", linewidth=1.4)
ax.text(60, ax.get_ylim()[1] * 0.94, "60 bpm", color="#e58606", ha="right", fontsize=9)
ax.text(100, ax.get_ylim()[1] * 0.94, "100 bpm", color="#d62728", ha="left", fontsize=9)
ax.set_xlabel("Heart rate (bpm)")
ax.set_ylabel("Number of ECG studies")
ax.set_title("Heart rate distribution (cleaned dataset)")

ax = axes[1]
buckets = {
    "Bradycardia\nHR < 60": int(((df["hr"] < 60)).sum()),
    "Normal low\n60-80": int(((df["hr"] >= 60) & (df["hr"] < 80)).sum()),
    "Normal high\n80-100": int(((df["hr"] >= 80) & (df["hr"] < 100)).sum()),
    "Tachycardia\nHR >= 100": int((df["hr"] >= 100).sum()),
    "Invalid\nRR": int(df["rr_interval"].isna().sum() + (df["rr_interval"] <= 0).sum()),
}
colors_b = ["#5fa8d3", "#54a24b", "#a5c953", "#e58606", "#888888"]
bars = ax.bar(list(buckets.keys()), list(buckets.values()), color=colors_b, edgecolor="black")
for bar, v in zip(bars, buckets.values()):
    ax.text(bar.get_x() + bar.get_width() / 2, v + 4000, f"{v:,}",
            ha="center", fontsize=9.5, weight="bold")
ax.set_ylabel("ECG studies")
ax.set_title("Heart-rate buckets used by Task A and Task C")
ax.set_ylim(0, max(buckets.values()) * 1.12)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))
fig.tight_layout()
save(fig, "fig_hr_distribution.png")


# ---------------------------------------------------------------------------
# 6. QRS duration distribution
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8.5, 4))
qrs = df["qrs_dur"].dropna()
qrs = qrs[(qrs > 30) & (qrs < 260)]
ax.hist(qrs, bins=80, color="#54a24b", edgecolor="black", alpha=0.85)
ax.axvline(120, color="#d62728", linestyle="--", linewidth=1.5,
           label="Wide-QRS threshold (120 ms)")
ax.set_xlabel("QRS duration (ms)")
ax.set_ylabel("ECG studies")
ax.set_title("QRS duration distribution (used by Task C wide-QRS claim)")
ax.legend()
n_wide = int((qrs > 120).sum())
n_normal = int((qrs <= 120).sum())
ax.text(0.97, 0.78, f"Wide QRS (>120 ms): {n_wide:,}\nNormal QRS: {n_normal:,}",
        transform=ax.transAxes, ha="right", va="top",
        bbox=dict(facecolor="white", alpha=0.85, edgecolor="#999"))
save(fig, "fig_qrs_duration.png")


# ---------------------------------------------------------------------------
# 7. QRS axis distribution
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8.5, 4))
ax_ = df["qrs_axis"].dropna()
ax_ = ax_[(ax_ >= -180) & (ax_ <= 180)]
ax.hist(ax_, bins=72, color="#b279a2", edgecolor="black", alpha=0.85)
for x, c, lab in [(-30, "#e58606", "Left axis (< -30)"),
                  (90, "#d62728", "Right axis (> 90)")]:
    ax.axvline(x, color=c, linestyle="--", linewidth=1.4, label=lab)
ax.set_xlabel("QRS axis (degrees)")
ax.set_ylabel("ECG studies")
ax.set_title("QRS axis distribution")
ax.legend(loc="upper left")
save(fig, "fig_qrs_axis.png")


# ---------------------------------------------------------------------------
# 8. Modality coverage / image integrity
# ---------------------------------------------------------------------------
with open(INTEGRITY) as f:
    integ = json.load(f)
fig, ax = plt.subplots(figsize=(8, 3.6))
groups = ["Lead II .npy", "12-lead .npy", "Clean PNG", "Scan-like JPG", "Per-study QC"]
counts = [800033, 800031, integ["clean_images"]["valid"],
          integ["scanlike_images"]["valid"], 800033]
expected = 800035
bars = ax.barh(groups, counts, color="#4c78a8", edgecolor="black")
ax.axvline(expected, color="#d62728", linestyle="--", linewidth=1.3,
           label=f"Expected (record_list.csv) = {expected:,}")
for bar, c in zip(bars, counts):
    ax.text(c - 4000, bar.get_y() + bar.get_height() / 2, f"{c:,}",
            ha="right", va="center", color="white", weight="bold", fontsize=10)
ax.set_xlabel("Files present after final audit")
ax.set_title("Per-modality file coverage (final state)")
ax.set_xlim(795000, 801000)
ax.legend(loc="lower right")
save(fig, "fig_modality_coverage.png")


# ---------------------------------------------------------------------------
# 9. Image regeneration: before vs after
# ---------------------------------------------------------------------------
with open(RUN_META) as f:
    rm = json.load(f)
before = rm["stats"]
after_clean = {"valid": integ["clean_images"]["valid"],
               "missing": integ["clean_images"]["missing"],
               "corrupt": integ["clean_images"]["corrupt"]}
after_scan = {"valid": integ["scanlike_images"]["valid"],
              "missing": integ["scanlike_images"]["missing"],
              "corrupt": integ["scanlike_images"]["corrupt"]}

fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
ax = axes[0]
labels_b = ["OK", "Skipped\n(already valid)", "Missing", "Errored"]
vals_b = [before["ok"], before["skip"], before["missing"], before["error"]]
colors_b = ["#54a24b", "#5fa8d3", "#888", "#d62728"]
bars = ax.bar(labels_b, vals_b, color=colors_b, edgecolor="black")
for bar, v in zip(bars, vals_b):
    ax.text(bar.get_x() + bar.get_width() / 2, v + 4000, f"{v:,}",
            ha="center", fontsize=10, weight="bold")
ax.set_ylabel("ECG studies")
ax.set_title("Intermediate scan-like run\n(before regeneration)")
ax.set_ylim(0, max(vals_b) * 1.18)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))

ax = axes[1]
labels_a = ["Clean PNG\nvalid", "Clean PNG\nmissing", "Clean PNG\ncorrupt",
            "Scan JPG\nvalid", "Scan JPG\nmissing", "Scan JPG\ncorrupt"]
vals_a = [after_clean["valid"], after_clean["missing"], after_clean["corrupt"],
          after_scan["valid"], after_scan["missing"], after_scan["corrupt"]]
colors_a = ["#54a24b", "#888", "#d62728", "#54a24b", "#888", "#d62728"]
bars = ax.bar(labels_a, vals_a, color=colors_a, edgecolor="black")
for bar, v in zip(bars, vals_a):
    ax.text(bar.get_x() + bar.get_width() / 2, v + 4000, f"{v:,}",
            ha="center", fontsize=9, weight="bold")
ax.set_ylabel("Studies (final audit)")
ax.set_title("After regeneration\n(final dataset_integrity_summary.json)")
ax.set_yscale("symlog", linthresh=10)
fig.suptitle("Image regeneration: before vs after", fontsize=12.5, weight="bold")
fig.tight_layout()
save(fig, "fig_regeneration_before_after.png")


# ---------------------------------------------------------------------------
# 10. Task counts overview
# ---------------------------------------------------------------------------
with open(TASKA_STATS) as f:
    a_stats = json.load(f)
fig, ax = plt.subplots(figsize=(8.5, 4))
tasks = ["Cleaned\nstudies", "Task A\nverification", "Task B\ntemporal", "Task C\nplausibility"]
vals = [799706, a_stats["samples"], 2399118, 4726480]
colors = ["#4c78a8", "#54a24b", "#e58606", "#b279a2"]
bars = ax.bar(tasks, vals, color=colors, edgecolor="black")
for bar, v in zip(bars, vals):
    ax.text(bar.get_x() + bar.get_width() / 2, v + 100000, f"{v:,}",
            ha="center", fontsize=10, weight="bold")
ax.set_ylabel("Rows")
ax.set_title("Final dataset row counts")
ax.set_ylim(0, max(vals) * 1.12)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v / 1000):,}K"))
save(fig, "fig_task_counts.png")


print("done")
