"""
16_figures.py — Supplementary figures for ECG Benchmark Plan B report.
Generates:
  1. B2 corruption curve (regime 1 vs regime 2) — accuracy vs SNR per corruption family
  2. B1 ResNet training curves (loss per epoch, all 3 seeds)
  3. B1 per-class bar chart (AUPRC / F1 per class)
  4. B6 verification difficulty curve (AUROC/accuracy by level 0-5)
  5. B1 SQI-stratified bar chart (accuracy / AUPRC by SQI tier)
  6. B2 AUC-CC summary (regime 1 vs regime 2 per corruption)
Output: outputs/figures/
"""
import os, json, glob
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm

OUT_DIR      = "../outputs/figures"
TABLES_DIR   = "../outputs/tables"
MODEL_RUN_B1 = "../outputs/model_runs/B1"
os.makedirs(OUT_DIR, exist_ok=True)

HR_NAMES = ["bradycardia", "normal", "tachycardia"]
CORRUPT_ORDER = ["gaussian","baseline_wander","powerline","emg",
                 "electrode_motion","lead_dropout","gain_drift","saturation"]
CORRUPT_LABELS = {
    "gaussian":         "Gaussian",
    "baseline_wander":  "Baseline\nWander",
    "powerline":        "Powerline",
    "emg":              "EMG",
    "electrode_motion": "Electrode\nMotion",
    "lead_dropout":     "Lead\nDropout",
    "gain_drift":       "Gain\nDrift",
    "saturation":       "Saturation",
}
SNR_LEVELS = [30, 20, 10, 5, 0]
COLORS = plt.rcParams["axes.prop_cycle"].by_key()["color"]

# ── Figure 1: B2 Corruption Curves ────────────────────────────────────────────
def fig_corruption_curves():
    r1_path = os.path.join(TABLES_DIR, "B2_regime1_curve.json")
    r2_path = os.path.join(TABLES_DIR, "B2_regime2_curve.json")
    if not os.path.exists(r1_path):
        print("  B2 regime1 curve not found — skipping corruption figure", flush=True)
        return

    with open(r1_path) as f: r1 = json.load(f)
    r2 = None
    if os.path.exists(r2_path):
        with open(r2_path) as f: r2 = json.load(f)

    clean_acc_r1 = r1.get("clean", {}).get("accuracy", None)
    clean_acc_r2 = r2.get("clean", {}).get("accuracy", None) if r2 else None

    n_corrupt = len(CORRUPT_ORDER)
    fig, axes = plt.subplots(2, 4, figsize=(16, 8), sharey=True)
    axes = axes.ravel()

    for i, ctype in enumerate(CORRUPT_ORDER):
        ax = axes[i]
        # Regime 1
        if ctype in r1:
            accs_r1 = [r1[ctype].get(snr, {}).get("accuracy", np.nan) for snr in SNR_LEVELS]
            ax.plot(SNR_LEVELS, accs_r1, "o-", color=COLORS[0], label="Regime 1 (clean-trained)")
        # Regime 2
        if r2 and ctype in r2:
            accs_r2 = [r2[ctype].get(snr, {}).get("accuracy", np.nan) for snr in SNR_LEVELS]
            ax.plot(SNR_LEVELS, accs_r2, "s--", color=COLORS[1], label="Regime 2 (noise-aug)")
        # Clean anchor baseline
        if clean_acc_r1:
            ax.axhline(clean_acc_r1, color=COLORS[0], linestyle=":", alpha=0.5, linewidth=1)
        if clean_acc_r2:
            ax.axhline(clean_acc_r2, color=COLORS[1], linestyle=":", alpha=0.5, linewidth=1)

        ax.set_title(CORRUPT_LABELS.get(ctype, ctype), fontsize=11)
        ax.set_xlabel("SNR (dB)")
        ax.set_ylabel("Accuracy") if i % 4 == 0 else None
        ax.set_xlim([-2, 32]); ax.set_ylim([0, 1.05])
        ax.set_xticks(SNR_LEVELS)
        ax.grid(True, alpha=0.3)
        if i == 0: ax.legend(fontsize=8)

    fig.suptitle("B2 Noise-Robustness Corruption Curves\n(hr_label classification accuracy vs SNR)", fontsize=13)
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "B2_corruption_curves.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}", flush=True)

# ── Figure 2: B1 ResNet training curves ──────────────────────────────────────
def fig_training_curves():
    files = sorted(glob.glob(os.path.join(MODEL_RUN_B1, "B1_seed*_results.json")))
    if not files:
        print("  No seed results found — skipping training curves", flush=True)
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for fi, fpath in enumerate(files):
        with open(fpath) as f: res = json.load(f)
        seed = res["seed"]
        hist = res["training_history"]
        eps   = [h["epoch"]      for h in hist]
        tr_l  = [h["train_loss"] for h in hist]
        va_l  = [h["val_loss"]   for h in hist]
        axes[0].plot(eps, tr_l, label=f"Seed {seed} train", color=COLORS[fi], linestyle="-")
        axes[0].plot(eps, va_l, label=f"Seed {seed} val",   color=COLORS[fi], linestyle="--", alpha=0.7)

    axes[0].set_xlabel("Epoch"); axes[0].set_ylabel("Cross-Entropy Loss")
    axes[0].set_title("B1 ResNet Training Curves (3 seeds)"); axes[0].legend(fontsize=8); axes[0].grid(True, alpha=0.3)

    # Bar: AUPRC / F1 / Acc per seed
    metrics_names = ["macro_auprc", "macro_f1", "accuracy"]
    metric_labels  = ["AUPRC", "Macro-F1", "Accuracy"]
    x = np.arange(len(metrics_names))
    width = 0.25
    for fi, fpath in enumerate(files):
        with open(fpath) as f: res = json.load(f)
        vals = [res[m] for m in metrics_names]
        axes[1].bar(x + fi*width, vals, width, label=f"Seed {res['seed']}", color=COLORS[fi])
    axes[1].set_xticks(x + width); axes[1].set_xticklabels(metric_labels)
    axes[1].set_ylim([0.8, 1.02]); axes[1].set_ylabel("Score")
    axes[1].set_title("B1 ResNet Test Metrics per Seed"); axes[1].legend(); axes[1].grid(True, axis="y", alpha=0.3)

    plt.tight_layout()
    out = os.path.join(OUT_DIR, "B1_training_curves.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}", flush=True)

# ── Figure 3: Model comparison summary ───────────────────────────────────────
def fig_model_comparison():
    nk2_path = os.path.join(TABLES_DIR, "B1_neurokit2_baseline.json")
    b1_files = sorted(glob.glob(os.path.join(MODEL_RUN_B1, "B1_seed*_results.json")))
    if not b1_files: return

    nk2_acc, nk2_f1 = None, None
    if os.path.exists(nk2_path):
        with open(nk2_path) as f: nk2 = json.load(f)
        nk2_acc = nk2.get("hr",{}).get("accuracy")
        nk2_f1  = nk2.get("hr",{}).get("macro_f1")

    resnet_results = []
    for fp in b1_files:
        with open(fp) as f: resnet_results.append(json.load(f))
    resnet_auprc = np.mean([r["macro_auprc"] for r in resnet_results])
    resnet_f1    = np.mean([r["macro_f1"]    for r in resnet_results])
    resnet_acc   = np.mean([r["accuracy"]    for r in resnet_results])
    resnet_auprc_std = np.std([r["macro_auprc"] for r in resnet_results])
    resnet_f1_std    = np.std([r["macro_f1"]    for r in resnet_results])
    resnet_acc_std   = np.std([r["accuracy"]    for r in resnet_results])

    fig, ax = plt.subplots(figsize=(8, 5))
    models = ["NeuroKit2\n(algorithmic)", "1D ResNet\n(3 seeds)"]
    accs   = [nk2_acc  or 0, resnet_acc]
    f1s    = [nk2_f1   or 0, resnet_f1]
    acc_err = [0, resnet_acc_std]
    f1_err  = [0, resnet_f1_std]

    x = np.arange(len(models)); width = 0.35
    bars1 = ax.bar(x - width/2, accs, width, yerr=acc_err, label="Accuracy", color=COLORS[0], capsize=5)
    bars2 = ax.bar(x + width/2, f1s,  width, yerr=f1_err,  label="Macro-F1", color=COLORS[1], capsize=5)
    ax.set_xticks(x); ax.set_xticklabels(models)
    ax.set_ylim([0.7, 1.05]); ax.set_ylabel("Score")
    ax.set_title("B1 hr_label Classification — Model Comparison"); ax.legend(); ax.grid(True, axis="y", alpha=0.3)
    for bar in bars1: ax.annotate(f"{bar.get_height():.3f}", xy=(bar.get_x()+bar.get_width()/2, bar.get_height()+0.005), ha="center", fontsize=9)
    for bar in bars2: ax.annotate(f"{bar.get_height():.3f}", xy=(bar.get_x()+bar.get_width()/2, bar.get_height()+0.005), ha="center", fontsize=9)

    plt.tight_layout()
    out = os.path.join(OUT_DIR, "B1_model_comparison.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}", flush=True)

# ── Figure 4: B6 Verification Difficulty Curve ───────────────────────────────
def fig_b6_difficulty_curve():
    path = os.path.join(TABLES_DIR, "B6_verification_curve.json")
    if not os.path.exists(path):
        print("  B6 results not found — skipping", flush=True)
        return
    with open(path) as f: data = json.load(f)
    levels = data["levels"]
    lvl_ids  = sorted(int(k) for k in levels.keys())
    aurocs   = [levels[str(l)]["auroc"]    for l in lvl_ids]
    accs     = [levels[str(l)]["accuracy"] for l in lvl_ids]
    names    = [f"L{l}\n{levels[str(l)]['name'][:14]}" for l in lvl_ids]

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(lvl_ids))
    ax.bar(x - 0.2, aurocs, 0.35, label="AUROC",    color=COLORS[0], alpha=0.85)
    ax.bar(x + 0.2, accs,   0.35, label="Accuracy", color=COLORS[1], alpha=0.85)
    ax.axhline(0.5, color="grey", linestyle="--", linewidth=1, label="Chance (0.50)")
    ax.set_xticks(x); ax.set_xticklabels(names, fontsize=9)
    ax.set_ylim([0.3, 0.7]); ax.set_ylabel("Score")
    ax.set_title("B6 Difficulty-Stratified Cross-Modal Verification\n"
                 "(AUROC / Accuracy by hard-negative level; baseline model)")
    ax.legend(); ax.grid(True, axis="y", alpha=0.3)
    # Annotate bars
    for xi, (au, ac) in enumerate(zip(aurocs, accs)):
        ax.text(xi-0.2, au+0.005, f"{au:.3f}", ha="center", fontsize=8)
        ax.text(xi+0.2, ac+0.005, f"{ac:.3f}", ha="center", fontsize=8)
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "B6_verification_curve.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}", flush=True)

# ── Figure 5: B1 SQI-Stratified Results ──────────────────────────────────────
def fig_b1_sqi_stratified():
    path = os.path.join(TABLES_DIR, "B1_sqi_stratified.json")
    if not os.path.exists(path):
        print("  B1 SQI results not found — skipping", flush=True)
        return
    with open(path) as f: data = json.load(f)
    tiers  = ["high_sqi", "medium_sqi", "low_sqi"]
    labels = ["High SQI\n(≥0.80)", "Medium SQI\n(0.60–0.80)", "Low SQI\n(<0.60)"]
    accs   = [data[t].get("accuracy", 0) for t in tiers]
    f1s    = [data[t].get("macro_f1", 0) for t in tiers]
    auprcs = [data[t].get("macro_auprc", 0) for t in tiers]
    ns     = [data[t].get("n_ecgs", 0) for t in tiers]

    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(tiers)); width = 0.25
    ax.bar(x - width, accs,   width, label="Accuracy",   color=COLORS[0], alpha=0.85)
    ax.bar(x,          f1s,   width, label="Macro-F1",   color=COLORS[1], alpha=0.85)
    ax.bar(x + width,  auprcs,width, label="Macro-AUPRC",color=COLORS[2], alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{l}\n(n={n})" for l, n in zip(labels, ns)], fontsize=9)
    ax.set_ylim([0.85, 1.02]); ax.set_ylabel("Score")
    ax.set_title("B1 SQI-Stratified Evaluation\n(kurtosis-SQI tiers; spec §6.2)")
    ax.legend(); ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    out = os.path.join(OUT_DIR, "B1_sqi_stratified.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}", flush=True)

# ── Figure 6: B2 AUC-CC comparison (regime 1 vs 2) ───────────────────────────
def fig_b2_auc_cc():
    path = os.path.join(TABLES_DIR, "B2_auc_metrics.json")
    if not os.path.exists(path):
        print("  B2 AUC metrics not found — skipping", flush=True)
        return
    with open(path) as f: data = json.load(f)
    r1 = data["regime1_clean_trained"]["corruptions"]
    r2 = data["regime2_noise_augmented"]["corruptions"]
    corrs = CORRUPT_ORDER
    auc_r1 = [r1.get(c, {}).get("auc_cc", 0) for c in corrs]
    auc_r2 = [r2.get(c, {}).get("auc_cc", 0) for c in corrs]
    drop_r1 = [r1.get(c, {}).get("rel_drop_at_0dB", 0) for c in corrs]
    drop_r2 = [r2.get(c, {}).get("rel_drop_at_0dB", 0) for c in corrs]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    x = np.arange(len(corrs)); width = 0.35
    ax1.bar(x - width/2, auc_r1, width, label="Regime 1 (clean-trained)", color=COLORS[0], alpha=0.85)
    ax1.bar(x + width/2, auc_r2, width, label="Regime 2 (noise-aug)",     color=COLORS[1], alpha=0.85)
    short_labels = [CORRUPT_LABELS[c].replace("\n", " ") for c in corrs]
    ax1.set_xticks(x); ax1.set_xticklabels(short_labels, rotation=30, ha="right", fontsize=9)
    ax1.set_ylim([0.90, 1.0]); ax1.set_ylabel("AUC-CC"); ax1.set_title("B2 Area Under Corruption Curve")
    ax1.legend(); ax1.grid(True, axis="y", alpha=0.3)

    ax2.bar(x - width/2, drop_r1, width, label="Regime 1", color=COLORS[0], alpha=0.85)
    ax2.bar(x + width/2, drop_r2, width, label="Regime 2", color=COLORS[1], alpha=0.85)
    ax2.set_xticks(x); ax2.set_xticklabels(short_labels, rotation=30, ha="right", fontsize=9)
    ax2.set_ylabel("Relative Drop at 0 dB"); ax2.set_title("B2 Relative Performance Drop at 0 dB SNR")
    ax2.legend(); ax2.grid(True, axis="y", alpha=0.3)

    plt.tight_layout()
    out = os.path.join(OUT_DIR, "B2_auc_cc.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}", flush=True)

if __name__ == "__main__":
    print("Generating supplementary figures...", flush=True)
    fig_corruption_curves()
    fig_training_curves()
    fig_model_comparison()
    fig_b6_difficulty_curve()
    fig_b1_sqi_stratified()
    fig_b2_auc_cc()
    print("Done.", flush=True)
