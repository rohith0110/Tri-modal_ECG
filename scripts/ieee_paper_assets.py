"""Compute the dataset statistics and figures used by IEEE/conference_101719.tex.

Everything here is read straight off the Phase 1 artifacts; nothing is
hand-entered. Run from the repo root with ecg_env's python.

    ecg_env/Scripts/python.exe scripts/ieee_paper_assets.py

Writes IEEE/paper_stats.json plus the figure PNGs referenced by the paper.
"""

import io
import json
import os
import tarfile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
OUT = os.path.join(ROOT, "IEEE")

stats = {}


def p(path):
    return os.path.join(PROC, path)


# ---------------------------------------------------------------- indexes
clean = pd.read_parquet(
    p("index/ecg_metadata_clean_with_measurements.parquet"),
    columns=["study_id", "subject_id", "split", "machine_hr_bpm", "report_lines"],
)
clean_ids = set(clean["study_id"].tolist())

# ---------------------------------------------------------------- splits
split_rows = []
for s in ["train", "val", "test"]:
    sub = clean[clean["split"] == s]
    split_rows.append(
        {"split": s, "subjects": int(sub["subject_id"].nunique()), "ecgs": int(len(sub))}
    )
stats["splits"] = split_rows
stats["n_clean"] = int(len(clean))
stats["n_subjects"] = int(clean["subject_id"].nunique())

# ---------------------------------------------------------------- HR
hr = clean["machine_hr_bpm"].dropna()
hr = hr[(hr >= 20) & (hr <= 300)]
bins = [(0, 50), (50, 60), (60, 100), (100, 120), (120, 1e9)]
names = ["$<$50 (marked bradycardia)", "50--59 (bradycardia)", "60--100 (normal)",
         "101--120 (tachycardia)", "$>$120 (marked tachycardia)"]
stats["hr"] = {
    "n": int(len(hr)),
    "mean": round(float(hr.mean()), 1),
    "std": round(float(hr.std()), 1),
    "median": round(float(hr.median()), 1),
    "q1": round(float(hr.quantile(0.25)), 1),
    "q3": round(float(hr.quantile(0.75)), 1),
    "buckets": [
        {"range": nm, "n": int(((hr >= lo) & (hr < hi)).sum()),
         "pct": round(100.0 * ((hr >= lo) & (hr < hi)).sum() / len(hr), 1)}
        for nm, (lo, hi) in zip(names, bins)
    ],
}

# ---------------------------------------------------------------- age / sex
pat = pd.read_parquet(
    os.path.join(ROOT, "data", "raw", "ehr_cache", "patients.parquet"),
    columns=["subject_id", "gender", "anchor_age"],
)
subj = clean[["subject_id"]].drop_duplicates().merge(pat, on="subject_id", how="left")
demo = subj.dropna(subset=["anchor_age"])
age = demo["anchor_age"].astype(float)
abins = [(18, 30), (30, 45), (45, 60), (60, 75), (75, 90), (90, 1e9)]
anames = ["18--29", "30--44", "45--59", "60--74", "75--89", "$\\geq$90"]
stats["demographics"] = {
    "n_subjects_with_demo": int(len(demo)),
    "n_subjects_total": int(len(subj)),
    "age_mean": round(float(age.mean()), 1),
    "age_std": round(float(age.std()), 1),
    "age_median": round(float(age.median()), 1),
    "age_buckets": [
        {"range": nm, "n": int(((age >= lo) & (age < hi)).sum()),
         "pct": round(100.0 * ((age >= lo) & (age < hi)).sum() / len(age), 1)}
        for nm, (lo, hi) in zip(anames, abins)
    ],
    "sex": [
        {"label": k, "n": int(v), "pct": round(100.0 * v / len(demo), 1)}
        for k, v in demo["gender"].value_counts().items()
    ],
}

# ECG-level sex split too (per-study, not per-subject)
ecg_demo = clean[["study_id", "subject_id"]].merge(pat, on="subject_id", how="left")
stats["demographics"]["sex_ecg_level"] = [
    {"label": k, "n": int(v), "pct": round(100.0 * v / len(ecg_demo.dropna(subset=["gender"])), 1)}
    for k, v in ecg_demo["gender"].value_counts().items()
]

# ---------------------------------------------------------------- SQI
wqc = pd.read_parquet(
    p("waveform_qc.parquet"), columns=["study_id", "sqi_tier", "sqi_aggregate"]
)
wqc = wqc[wqc["study_id"].isin(clean_ids)]
tier = wqc["sqi_tier"].value_counts()
stats["sqi"] = {
    "n": int(len(wqc)),
    "mean": round(float(wqc["sqi_aggregate"].dropna().mean()), 3),
    "median": round(float(wqc["sqi_aggregate"].dropna().median()), 3),
    "tiers": [
        {"tier": str(k), "n": int(v), "pct": round(100.0 * v / len(wqc), 1)}
        for k, v in tier.items()
    ],
}

# ---------------------------------------------------------------- report statements
expl = clean["report_lines"].explode().dropna().astype(str).str.strip()
expl = expl[expl != ""]
top = expl.value_counts().head(15)
stats["report_statements"] = {
    "n_statements": int(len(expl)),
    "n_unique": int(expl.nunique()),
    "mean_per_ecg": round(float(len(expl)) / len(clean), 2),
    "top": [
        {"statement": k, "n": int(v), "pct": round(100.0 * v / len(clean), 1)}
        for k, v in top.items()
    ],
}

# claim families used by Task C (same keyword dictionary as the benchmark)
low = expl.str.lower()
fam = {
    "Bradycardia": low.str.contains("bradycard"),
    "Tachycardia": low.str.contains("tachycard"),
    "Wide QRS / bundle branch block": low.str.contains("bundle branch|wide qrs|intraventricular conduction"),
    "First-degree AV block": low.str.contains("a-v block|av block|atrioventricular block"),
    "Atrial fibrillation / flutter": low.str.contains("fibrillation|flutter"),
    "Myocardial infarction": low.str.contains("infarct"),
}
# explode() keeps the originating row label, so expl.index maps back to `clean`
stats["claim_families"] = []
for k, mask in fam.items():
    studies = clean.loc[low.index[mask.to_numpy()], "study_id"].nunique()
    stats["claim_families"].append(
        {"claim": k, "ecgs": int(studies), "pct": round(100.0 * studies / len(clean), 1)}
    )

# --------------------------------------------- Task C rule-based reference
# Deterministic audit of every report claim against the machine measurement
# for the same study. No model, no training: this is the algorithmic
# reference point the learned baselines will be compared against.
meas = pd.read_parquet(
    p("index/ecg_metadata_clean_with_measurements.parquet"),
    columns=["study_id", "machine_hr_bpm", "p_onset", "qrs_onset", "qrs_end"],
)
SENTINELS = {29999, 32767, 65535, -32768, 0}


def clean_ms(s, lo, hi):
    s = s.astype("float64")
    s = s.where(~s.isin(SENTINELS))
    return s.where((s >= lo) & (s <= hi))


meas["hr"] = clean_ms(meas["machine_hr_bpm"], 20, 300)
qrs_on = clean_ms(meas["qrs_onset"], 1, 1000)
qrs_end_ = clean_ms(meas["qrs_end"], 1, 1000)
p_on = clean_ms(meas["p_onset"], 1, 1000)
meas["qrs_dur"] = (qrs_end_ - qrs_on).where(lambda v: (v > 0) & (v < 500))
meas["pr"] = (qrs_on - p_on).where(lambda v: (v > 0) & (v < 500))

claim_rules = {
    "Bradycardia": ("bradycard", "hr", lambda v: v < 60),
    "Tachycardia": ("tachycard", "hr", lambda v: v > 100),
    "Wide QRS": ("bundle branch|wide qrs|intraventricular conduction", "qrs_dur",
                 lambda v: v >= 120),
    "First-degree AV block": ("first degree a-v block|first-degree a-v block|"
                              "1st degree a-v block|first degree av block", "pr",
                              lambda v: v > 200),
}
meas = meas.set_index("study_id")
stats["task_c_reference"] = []
for name, (pattern, col, rule) in claim_rules.items():
    hit = low.str.contains(pattern)
    sids = clean.loc[low.index[hit.to_numpy()], "study_id"].unique()
    v = meas.loc[sids, col]
    n = int(len(v))
    unc = int(v.isna().sum())
    sup = int(rule(v.dropna()).sum())
    stats["task_c_reference"].append(
        {"claim": name, "n_claims": n, "supported": sup,
         "contradicted": n - unc - sup, "uncertain": unc,
         "support_rate": round(100.0 * sup / max(n - unc, 1), 1)}
    )

# ------------------------------- signal-vs-report consistency (waveform QC)
cons = pd.read_parquet(
    p("waveform_qc.parquet"),
    columns=["study_id", "hr_consistency_flag", "qrs_consistency_flag",
             "report_consistency_flag"],
)
cons = cons[cons["study_id"].isin(clean_ids)]
stats["consistency_flags"] = {
    c: {str(k): int(v) for k, v in cons[c].value_counts(dropna=False).items()}
    for c in ["hr_consistency_flag", "qrs_consistency_flag", "report_consistency_flag"]
}

# ---------------------------------------------------------------- manifest
man = pd.read_parquet(p("modality_manifest.parquet"), columns=["modality_kind", "layout"])
key = man["modality_kind"].astype(str)
lay = man["layout"].astype(str)
combo = np.where(key.str.startswith("image_"), key + "_" + lay, key)
stats["modality_counts"] = {
    str(k): int(v) for k, v in pd.Series(combo).value_counts().items()
}
stats["n_manifest"] = int(len(man))

# ---------------------------------------------------------------- linkage
link = pd.read_parquet(p("linkage/linkage_final.parquet"), columns=["study_id", "link_tier", "source"])
stats["linkage"] = {
    "records": int(len(link)),
    "unique_ecgs": int(link["study_id"].nunique()),
    "by_tier": {str(k): int(v) for k, v in link["link_tier"].value_counts().items()},
    "by_source": {str(k): int(v) for k, v in link["source"].value_counts().items()},
}

with open(os.path.join(OUT, "paper_stats.json"), "w") as f:
    json.dump(stats, f, indent=2)
print(json.dumps(stats, indent=2)[:4000])

# ================================================================ figures
plt.rcParams.update({"font.size": 9, "font.family": "sans-serif", "axes.grid": False})

# Fig 3 - modality composition
order = [
    ("raw_lead2", "Lead-II signal (raw)"),
    ("preprocessed_lead2", "Lead-II signal (preproc.)"),
    ("raw_12lead", "12-lead signal (raw)"),
    ("preprocessed_12lead", "12-lead signal (preproc.)"),
    ("image_clean_lead2", "Clean image (Lead-II)"),
    ("image_clean_12lead", "Clean image (12-lead)"),
    ("image_scanlike_lead2", "Scan-like image (Lead-II)"),
    ("image_scanlike_12lead", "Scan-like image (12-lead)"),
    ("signal_corrupted", "Corrupted Lead-II signal"),
]
labels, vals = [], []
for key, lab in order:
    if key in stats["modality_counts"]:
        labels.append(lab)
        vals.append(stats["modality_counts"][key])
for key, v in stats["modality_counts"].items():
    if key not in dict(order):
        labels.append(key)
        vals.append(v)

fam_color = {"signal": "#4878a8", "image": "#7fa8cd", "corrupt": "#c2d5e8"}
colors = [
    fam_color["corrupt"] if "Corrupted" in l
    else fam_color["image"] if "image" in l
    else fam_color["signal"]
    for l in labels
]
fig, ax = plt.subplots(figsize=(3.45, 2.35))
y = np.arange(len(labels))
ax.barh(y, [v / 1000.0 for v in vals], color=colors, height=0.7)
ax.set_yticks(y)
ax.set_yticklabels(labels, fontsize=7)
ax.invert_yaxis()
ax.set_xlabel(r"Modality records ($\times 10^3$)", fontsize=8)
ax.set_xlim(0, max(vals) / 1000.0 * 1.30)
ax.tick_params(axis="x", labelsize=7)
for i, v in enumerate(vals):
    ax.text(v / 1000.0 + 12, i, f"{v:,}", va="center", fontsize=6.5)
for sp in ("top", "right"):
    ax.spines[sp].set_visible(False)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig_modality_composition.png"), dpi=400)
plt.close(fig)

# Fig 5 - split distribution
fig, ax = plt.subplots(figsize=(3.4, 2.2))
names = ["Train", "Validation", "Test"]
ecgs = [r["ecgs"] for r in split_rows]
subs = [r["subjects"] for r in split_rows]
x = np.arange(3)
w = 0.38
b1 = ax.bar(x - w / 2, ecgs, w, label="ECG studies", color="#4878a8")
b2 = ax.bar(x + w / 2, subs, w, label="Subjects", color="#a8c4de")
ax.set_xticks(x)
ax.set_xticklabels(names)
ax.set_ylabel(r"Count ($\times 10^3$)")
ax.set_ylim(0, max(ecgs) * 1.22)
ax.yaxis.set_major_formatter(
    matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}")
)
for bars in (b1, b2):
    for b in bars:
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{int(b.get_height()):,}",
                ha="center", va="bottom", fontsize=7)
ax.legend(frameon=False, fontsize=8)
for sp in ("top", "right"):
    ax.spines[sp].set_visible(False)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig_split_distribution.png"), dpi=400)
plt.close(fig)

# Fig 6 - HR distribution
fig, ax = plt.subplots(figsize=(3.4, 2.0))
ax.hist(hr, bins=np.arange(20, 201, 2), color="#4878a8")
ax.axvline(60, color="#b03030", lw=0.9, ls="--")
ax.axvline(100, color="#b03030", lw=0.9, ls="--")
ax.set_xlabel("Machine-reported heart rate (bpm)")
ax.set_ylabel("ECG studies")
ax.set_xlim(20, 200)
for sp in ("top", "right"):
    ax.spines[sp].set_visible(False)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig_hr_distribution.png"), dpi=400)
plt.close(fig)

# Fig 4 - benchmark task overview (schematic, same box style as pipeline.png)
from matplotlib.patches import FancyArrow, FancyBboxPatch

fig, axes = plt.subplots(3, 1, figsize=(3.45, 4.1))


def box(ax, x, y, w, h, title, body, fc):
    ax.add_patch(
        FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02",
                       fc=fc, ec="#5a5a5a", lw=0.7)
    )
    ax.text(x + w / 2, y + h - 0.13, title, ha="center", va="top",
            fontsize=7, fontweight="bold")
    ax.text(x + w / 2, y + h - 0.40, body, ha="center", va="top", fontsize=6, linespacing=1.35)


def arrow(ax, x0, x1, y):
    ax.annotate("", xy=(x1, y), xytext=(x0, y),
                arrowprops=dict(arrowstyle="-|>", color="#333333", lw=0.8))


for ax in axes:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

# Task A
ax = axes[0]
ax.text(0.0, 0.95, "Task A: Tri-modal Consistency Verification", fontsize=7.5,
        fontweight="bold", va="top")
box(ax, 0.00, 0.10, 0.30, 0.68, "Inputs", "signal $S$\nimage $I$\nreport $T$", "#dbe7f3")
box(ax, 0.36, 0.10, 0.30, 0.68, "Perturbation",
    "TEXT / IMAGE /\nSIGNAL swap,\nhard negatives", "#fdf0d5")
box(ax, 0.70, 0.10, 0.29, 0.68, "Output", "$y_{match}$\n$\\in\\{0,1\\}$", "#dff0e4")
arrow(ax, 0.305, 0.355, 0.44)
arrow(ax, 0.665, 0.695, 0.44)

# Task B
ax = axes[1]
ax.text(0.0, 0.95, "Task B: Temporal Grounding Verification", fontsize=7.5,
        fontweight="bold", va="top")
box(ax, 0.00, 0.10, 0.30, 0.68, "Inputs", "10 s signal $S$\nquery $q$", "#dbe7f3")
box(ax, 0.36, 0.10, 0.30, 0.68, "Bin split",
    "$b_1 \\ldots b_{10}$\n(1 s bins)", "#fdf0d5")
box(ax, 0.70, 0.10, 0.29, 0.68, "Output", "$y_{bins}$\n$\\in\\{0,1\\}^{10}$", "#dff0e4")
arrow(ax, 0.305, 0.355, 0.44)
arrow(ax, 0.665, 0.695, 0.44)

# Task C
ax = axes[2]
ax.text(0.0, 0.95, "Task C: Plausibility and Contradiction Auditing", fontsize=7.5,
        fontweight="bold", va="top")
box(ax, 0.00, 0.10, 0.30, 0.68, "Inputs", "report claim $c$\nsignal evidence", "#dbe7f3")
box(ax, 0.36, 0.10, 0.30, 0.68, "Rule check",
    "HR, QRS$_{dur}$,\nPR thresholds", "#fdf0d5")
box(ax, 0.70, 0.10, 0.29, 0.68, "Output",
    "Supported /\nContradicted /\nUncertain", "#dff0e4")
arrow(ax, 0.305, 0.355, 0.44)
arrow(ax, 0.665, 0.695, 0.44)

fig.tight_layout(h_pad=0.6)
fig.savefig(os.path.join(OUT, "fig_benchmark_tasks.png"), dpi=400)
plt.close(fig)

# Fig 2 - construction pipeline. Same layout as the internal Phase 1 report
# figure, resized for a single IEEE column and without the burned-in title
# (the caption carries it) or internal "Phase 1" vocabulary.
fig, ax = plt.subplots(figsize=(7.0, 4.0))
ax.axis("off")
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)


def pbox(x, y, w, h, title, text, color):
    ax.add_patch(plt.Rectangle((x, y), w, h, facecolor=color, edgecolor="#3a3a3a", lw=0.9))
    ax.text(x + w / 2, y + h * 0.74, title, ha="center", va="center",
            fontsize=8.5, fontweight="bold")
    ax.text(x + w / 2, y + h * 0.33, text, ha="center", va="center",
            fontsize=6.6, linespacing=1.25)
    return x, y, w, h


def _top(b):
    return b[0] + b[2] / 2, b[1] + b[3]


def _bot(b):
    return b[0] + b[2] / 2, b[1]


def _left(b):
    return b[0], b[1] + b[3] / 2


def _right(b):
    return b[0] + b[2], b[1] + b[3] / 2


def parrow(start, end):
    ax.annotate("", xy=end, xytext=start,
                arrowprops=dict(arrowstyle="->", color="#303030", lw=1.1))


raw = pbox(0.02, 0.80, 0.22, 0.15, "Raw sources",
           "MIMIC-IV-ECG\nHosp + ED tables\nMachine measurements", "#d9eaf7")
found = pbox(0.30, 0.80, 0.22, 0.15, "Foundation",
             "Version lock\nAccess checks\nMaster index setup", "#e8f3df")
master = pbox(0.58, 0.80, 0.22, 0.15, "Master ECG index",
              "800,035 ECGs\nStudy + subject keys\nMeasurement fields", "#fff0cc")

split = pbox(0.02, 0.45, 0.24, 0.15, "Patient split",
             "Subject-level\nTrain / val / test\n0 overlap", "#e8f3df")
linkage = pbox(0.36, 0.45, 0.26, 0.15, "EHR linkage + decision",
               "Exact / tolerance links\nTie-break selection\nPlan A selected", "#fff0cc")
modal = pbox(0.72, 0.45, 0.26, 0.15, "Modality generation",
             "Raw / preprocessed signals\nClean + scan-like images\nCorrupted Lead-II", "#d9eaf7")

qc = pbox(0.72, 0.24, 0.26, 0.14, "QC + features",
          "Tri-modal QC\nWaveform SQI\nStructured features", "#efe2f7")
final = pbox(0.20, 0.03, 0.26, 0.14, "Final dataset",
             "Clean index\nCanonical manifest\nLeakage policy", "#d8f1ee")
audits = pbox(0.56, 0.03, 0.28, 0.14, "Final audits",
              "Split / duplicate\nMissingness / leakage\nLinkage validation", "#d8f1ee")

parrow(_right(raw), _left(found))
parrow(_right(found), _left(master))

fan_y = 0.70
mb = _bot(master)
ax.plot([mb[0], mb[0]], [mb[1], fan_y], color="#303030", lw=1.0)
centers = [_top(split)[0], _top(linkage)[0], _top(modal)[0]]
ax.plot([min(centers), max(centers)], [fan_y, fan_y], color="#303030", lw=1.0)
for b in (split, linkage, modal):
    parrow((_top(b)[0], fan_y), _top(b))

parrow(_bot(modal), _top(qc))

merge_y = 0.20
ins = [_bot(split), _bot(linkage), _bot(qc)]
ax.plot([min(q[0] for q in ins), max(q[0] for q in ins)], [merge_y, merge_y],
        color="#303030", lw=1.0)
for x, y in ins:
    ax.plot([x, x], [y, merge_y], color="#303030", lw=1.0)
parrow((_top(final)[0], merge_y), _top(final))
parrow(_right(final), _left(audits))

fig.tight_layout(pad=0.2)
fig.savefig(os.path.join(OUT, "pipeline.png"), dpi=400, bbox_inches="tight")
plt.close(fig)

# ================================================================ raw ECG images
# Byte-for-byte extraction of one study's clean and scan-like Lead-II renders.
cm = pd.read_parquet(p("images/clean_lead2_manifest.parquet"))
sm = pd.read_parquet(p("images/scanlike_lead2_manifest.parquet"))
common = cm.merge(sm, on="study_id", suffixes=("_c", "_s"))
common = common[common["study_id"].isin(clean_ids)]
row = common.iloc[0]


def extract(container, offset, length, dest):
    # manifest offset points at the 512-byte tar header; payload follows it
    with open(os.path.join(PROC, container), "rb") as f:
        f.seek(int(offset) + tarfile.BLOCKSIZE)
        blob = f.read(int(length))
    assert blob[:4] in (b"\x89PNG", b"\xff\xd8\xff\xe0"), blob[:8]
    with open(dest, "wb") as f:
        f.write(blob)


extract(row["container_path_c"], row["offset_c"], row["length_c"],
        os.path.join(OUT, "example_clean_lead2.png"))
extract(row["container_path_s"], row["offset_s"], row["length_s"],
        os.path.join(OUT, "example_scanlike_lead2.jpg"))
print("example study_id:", row["study_id"])
