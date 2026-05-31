"""
18_b2_auc_metrics.py — B2 derived robustness scalars.
Computes per-corruption:
  - Area under corruption curve (AUC-CC): trapz over SNR levels [clean,30,20,10,5,0 dB]
  - Relative performance drop at 0 dB vs clean
  - Collapse threshold: first SNR where accuracy < 0.80
Inputs: outputs/tables/B2_regime1_curve.json, B2_regime2_curve.json
Output: outputs/tables/B2_auc_metrics.json
"""
import json, os
import numpy as np

R1_PATH = "../outputs/tables/B2_regime1_curve.json"
R2_PATH = "../outputs/tables/B2_regime2_curve.json"
OUT_DIR = "../outputs/tables"
COLLAPSE_FLOOR = 0.80   # accuracy below this = collapse

SNR_LEVELS = ["30", "20", "10", "5", "0"]  # string keys in the curve JSONs
SNR_VALUES  = [30,   20,   10,   5,   0]   # corresponding dB values for integration

def compute_metrics(curve_data, regime_name):
    clean_acc = curve_data["clean"]["accuracy"]
    corruptions = [k for k in curve_data if k != "clean"]
    metrics = {"clean_accuracy": round(clean_acc, 4), "corruptions": {}}

    for corr in corruptions:
        snr_data = curve_data[corr]
        # Build accuracy array at ordered SNR levels
        accs = [curve_data["clean"]["accuracy"]]  # start with clean
        for snr in SNR_LEVELS:
            if snr in snr_data:
                accs.append(snr_data[snr]["accuracy"])
            else:
                accs.append(clean_acc)  # fallback if level missing
        accs = np.array(accs)
        snr_for_auc = np.array([40] + SNR_VALUES)  # clean as 40 dB reference

        # Area under corruption curve (normalized to [0,1] by range)
        # Integrate accuracy vs SNR from 40dB down to 0dB
        # Higher AUC-CC = more robust across corruption severities
        # Integrate from 0dB (hardest) to 40dB (clean); reverse arrays so x is increasing
        auc_cc = float(np.trapezoid(accs[::-1], snr_for_auc[::-1]) / 40.0)  # normalize by SNR range

        # Relative drop at worst (0 dB)
        worst_acc = float(snr_data.get("0", {}).get("accuracy", clean_acc))
        rel_drop = round(float((clean_acc - worst_acc) / (clean_acc + 1e-10)), 4)

        # Collapse threshold: first SNR where acc < floor
        collapse_snr = None
        for snr_val, snr_key in zip(reversed(SNR_VALUES), reversed(SNR_LEVELS)):
            if snr_key in snr_data and snr_data[snr_key]["accuracy"] < COLLAPSE_FLOOR:
                collapse_snr = snr_val
                break

        metrics["corruptions"][corr] = {
            "clean_acc": round(clean_acc, 4),
            "worst_acc_0dB": round(worst_acc, 4),
            "rel_drop_at_0dB": rel_drop,
            "auc_cc": round(auc_cc, 4),
            "collapse_threshold_dB": collapse_snr,
            "collapsed": collapse_snr is not None,
        }

    # Summary across all corruptions
    all_drops = [v["rel_drop_at_0dB"] for v in metrics["corruptions"].values()]
    all_aucs  = [v["auc_cc"] for v in metrics["corruptions"].values()]
    metrics["summary"] = {
        "mean_rel_drop_at_0dB": round(float(np.mean(all_drops)), 4),
        "max_rel_drop_at_0dB": round(float(np.max(all_drops)), 4),
        "mean_auc_cc": round(float(np.mean(all_aucs)), 4),
        "n_corruptions_collapsed": int(sum(v["collapsed"] for v in metrics["corruptions"].values())),
        "collapse_floor": COLLAPSE_FLOOR,
    }
    return metrics

def main():
    print("B2 AUC-corruption metrics", flush=True)
    with open(R1_PATH) as f: r1 = json.load(f)
    with open(R2_PATH) as f: r2 = json.load(f)

    results = {
        "regime1_clean_trained": compute_metrics(r1, "regime1"),
        "regime2_noise_augmented": compute_metrics(r2, "regime2"),
    }

    # Print summary
    for regime, name in [("regime1_clean_trained","Regime 1"), ("regime2_noise_augmented","Regime 2")]:
        s = results[regime]["summary"]
        print(f"\n{name}:", flush=True)
        print(f"  Mean rel-drop @ 0dB: {s['mean_rel_drop_at_0dB']:.4f}", flush=True)
        print(f"  Mean AUC-CC:         {s['mean_auc_cc']:.4f}", flush=True)
        print(f"  Collapsed corruptions (acc<{COLLAPSE_FLOOR}): {s['n_corruptions_collapsed']}", flush=True)
        for corr, m in results[regime]["corruptions"].items():
            print(f"    {corr:20s}: auc_cc={m['auc_cc']:.4f}  drop={m['rel_drop_at_0dB']:.4f}"
                  f"  collapse={'YES @ '+str(m['collapse_threshold_dB'])+'dB' if m['collapsed'] else 'NO'}", flush=True)

    out = os.path.join(OUT_DIR, "B2_auc_metrics.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out}", flush=True)

if __name__ == "__main__":
    main()
