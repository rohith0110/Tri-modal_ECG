"""
09_evaluate.py — Aggregate results across seeds and produce final result tables (doc §7, §9.3)

Reads all B1_seed*_results.json from outputs/model_runs/B1/
Aggregates: mean ± std across seeds, combined bootstrap CI
Writes outputs/tables/B1_final_results.json and B1_final_results.csv
"""

import os, json, glob
import numpy as np
import pandas as pd

MODEL_RUN_DIR = "../outputs/model_runs"
OUT_DIR       = "../outputs/tables"
os.makedirs(OUT_DIR, exist_ok=True)

TASKS = ["B1"]

def aggregate_seeds(task):
    pattern = os.path.join(MODEL_RUN_DIR, task, f"{task}_seed*_results.json")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"No seed results found for {task} at {pattern}")
        return None

    print(f"\n{task}: found {len(files)} seed runs")
    results = []
    for fpath in files:
        with open(fpath) as f:
            results.append(json.load(f))

    metrics = ["macro_auprc", "macro_auroc", "macro_f1", "accuracy"]
    summary = {"task": task, "n_seeds": len(results)}

    for metric in metrics:
        vals = [r[metric] for r in results if metric in r]
        summary[f"{metric}_mean"] = round(float(np.mean(vals)), 4)
        summary[f"{metric}_std"]  = round(float(np.std(vals)),  4)

    # CI from first seed (representative)
    if "auprc_ci_95" in results[0]:
        summary["auprc_ci_95_seed0"] = results[0]["auprc_ci_95"]

    # Cohort info from first seed
    summary["n_test_ecg"]    = results[0].get("n_test_ecg")
    summary["n_per_class"]   = results[0].get("n_per_class")
    summary["model"]         = results[0].get("model")

    return summary

all_summaries = []
for task in TASKS:
    s = aggregate_seeds(task)
    if s:
        all_summaries.append(s)
        print(json.dumps(s, indent=2))

if all_summaries:
    out_json = os.path.join(OUT_DIR, "final_results.json")
    with open(out_json, "w") as f:
        json.dump(all_summaries, f, indent=2)

    # Flatten to CSV for paper table
    rows = []
    for s in all_summaries:
        rows.append({
            "Task":        s["task"],
            "Model":       s.get("model",""),
            "N_ECG_test":  s.get("n_test_ecg",""),
            "AUPRC_mean":  s.get("macro_auprc_mean",""),
            "AUPRC_std":   s.get("macro_auprc_std",""),
            "AUROC_mean":  s.get("macro_auroc_mean",""),
            "F1_mean":     s.get("macro_f1_mean",""),
            "Accuracy":    s.get("accuracy_mean",""),
            "N_seeds":     s.get("n_seeds",""),
        })
    df = pd.DataFrame(rows)
    out_csv = os.path.join(OUT_DIR, "final_results.csv")
    df.to_csv(out_csv, index=False)
    print(f"\nResults written:\n  {out_json}\n  {out_csv}")
