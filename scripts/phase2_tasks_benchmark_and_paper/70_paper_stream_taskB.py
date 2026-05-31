"""Re-stream the regenerated Task B JSONL to extract per-query statistics
the paper needs (positive rates, mixed-label counts, per-bin distributions).

Writes report_assets/taskB_stats.json so figure scripts and the paper
text use a single source of truth.
"""

import json
import os
from collections import Counter, defaultdict

import numpy as np

ROOT = "D:/Coding/MU/Tri-Modal_ECG"
JSONL = os.path.join(ROOT, "processed", "taskB_temporal_grounding.jsonl")
OUT = os.path.join(ROOT, "report_assets", "taskB_stats.json")

q_total = Counter()
q_any_pos = Counter()
q_all_zero = Counter()
q_all_one = Counter()
q_mixed = Counter()
q_pos_bin = defaultdict(lambda: np.zeros(10, dtype=np.int64))
split_counter = Counter()

with open(JSONL, "r", encoding="utf-8") as f:
    for line in f:
        rec = json.loads(line)
        q = rec["query"]
        labels = rec["labels"]
        q_total[q] += 1
        s = sum(labels)
        if s > 0:
            q_any_pos[q] += 1
        if s == 0:
            q_all_zero[q] += 1
        if s == len(labels):
            q_all_one[q] += 1
        if 0 < s < len(labels):
            q_mixed[q] += 1
        q_pos_bin[q] += np.asarray(labels, dtype=np.int64)
        split_counter[rec["split"]] += 1

out = {
    "totals": dict(q_total),
    "any_pos": dict(q_any_pos),
    "all_zero": dict(q_all_zero),
    "all_one": dict(q_all_one),
    "mixed": dict(q_mixed),
    "per_bin_pos": {q: q_pos_bin[q].tolist() for q in q_total},
    "splits": dict(split_counter),
}

with open(OUT, "w") as f:
    json.dump(out, f, indent=2)

print("wrote", OUT)
print(json.dumps(out, indent=2)[:1500])
