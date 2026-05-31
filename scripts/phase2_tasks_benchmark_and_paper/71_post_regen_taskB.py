"""Post-regen driver. Run AFTER task_B.py finishes producing the new JSONL.

Steps:
 1. Sanity-check JSONL row count = 2,399,118.
 2. Re-stream JSONL into report_assets/taskB_stats.json.
 3. Re-run viz_tasks_bc.py  (regenerates fig_taskB_distribution + Task C figs).
 4. Re-run viz_paper.py     (regenerates fig_taskB_examples, fig_taskB_before_after,
                              and copies polished fig_taskB_distribution into paper/figures/).
 5. Print a concise diff-summary so the paper Method/Limitations text can be re-checked.

Usage:
    cd D:\\Coding\\MU\\Tri-Modal_ECG
    .\\ecg_env\\Scripts\\python.exe scripts\\post_regen_taskB.py
"""

import json
import os
import subprocess
import sys

ROOT = "D:/Coding/MU/Tri-Modal_ECG"
PY = os.path.join(ROOT, "ecg_env", "Scripts", "python.exe")
JSONL = os.path.join(ROOT, "processed", "taskB_temporal_grounding.jsonl")
STATS_OLD_BACKUP = os.path.join(ROOT, "report_assets", "taskB_stats.v1.json")
STATS = os.path.join(ROOT, "report_assets", "taskB_stats.json")
SCRIPTS = os.path.join(ROOT, "scripts")


def step(msg):
    print("\n" + "=" * 72)
    print("STEP:", msg)
    print("=" * 72)


def run(cmd, cwd=None):
    print(">", " ".join(cmd))
    r = subprocess.run(cmd, cwd=cwd or ROOT)
    if r.returncode != 0:
        print(f"FAILED with exit code {r.returncode}", file=sys.stderr)
        sys.exit(r.returncode)


# 1. Row count sanity check
step("1) JSONL row count sanity check")
n = 0
with open(JSONL, "r", encoding="utf-8") as f:
    for _ in f:
        n += 1
print(f"  rows in JSONL: {n:,}  (expected 2,399,118)")
if n != 2_399_118:
    print("  WARNING: row count mismatch — Task B regen may have failed mid-stream.")
    sys.exit(1)

# 2. Save a copy of the old taskB_stats.json before overwriting
if os.path.exists(STATS) and not os.path.exists(STATS_OLD_BACKUP):
    import shutil
    shutil.copyfile(STATS, STATS_OLD_BACKUP)
    print(f"  backed up old stats -> {STATS_OLD_BACKUP}")

# 3. Recompute taskB_stats.json
step("2) Recompute report_assets/taskB_stats.json from new JSONL")
run([PY, os.path.join(SCRIPTS, "paper_stream_taskB.py")])

# 4. Print diff between old and new stats so the change is visible
if os.path.exists(STATS_OLD_BACKUP):
    with open(STATS_OLD_BACKUP) as f:
        old = json.load(f)
    with open(STATS) as f:
        new = json.load(f)
    print("\n--- diff: any_pos counts ---")
    for q in ("HIGH_HEART_RATE", "LOW_HEART_RATE", "WIDE_QRS"):
        oa = old["any_pos"].get(q, 0)
        na = new["any_pos"].get(q, 0)
        print(f"  {q:20s} old={oa:>9,}  new={na:>9,}  delta={na-oa:+,}")
    print("--- diff: per-bin positive (bin 0 only, where the artefact lives) ---")
    for q in ("HIGH_HEART_RATE", "LOW_HEART_RATE", "WIDE_QRS"):
        ob = old["per_bin_pos"][q][0]
        nb = new["per_bin_pos"][q][0]
        print(f"  {q:20s}  bin0 old={ob:>9,}  new={nb:>9,}  delta={nb-ob:+,}")

# 5. Regenerate Task B/C figures in report_assets/
step("3) Regenerate report_assets figures (viz_tasks_bc.py)")
run([PY, "viz_tasks_bc.py"], cwd=SCRIPTS)

# 6. Regenerate paper-only figures + copy into paper/figures/
step("4) Regenerate paper figures (viz_paper.py)")
run([PY, "viz_paper.py"], cwd=SCRIPTS)

step("DONE")
print("Now recompile the paper:")
print("  cd paper && pdflatex main; bibtex main; pdflatex main; pdflatex main")
