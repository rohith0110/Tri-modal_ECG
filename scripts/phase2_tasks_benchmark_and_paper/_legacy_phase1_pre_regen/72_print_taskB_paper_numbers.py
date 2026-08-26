"""After taskB_stats.json is regenerated, print the exact numbers that the
Technical Validation section of the paper must cite. Use these to find/replace
the now-stale percentages in paper/main.tex.
"""

import json

ROOT = "D:/Coding/MU/Tri-Modal_ECG"
STATS = f"{ROOT}/report_assets/taskB_stats.json"

s = json.load(open(STATS))
total = 799_706

print("\n" + "=" * 72)
print("Numbers for paper Technical Validation -> Task B counts paragraph")
print("=" * 72)

print("\nCurrent paper paragraph (locate by 'fraction of studies with at least one positive bin'):\n")

for q in ("HIGH_HEART_RATE", "LOW_HEART_RATE", "WIDE_QRS"):
    ap = s["any_pos"][q]
    mx = s["mixed"][q]
    print(f"  {q:20s}  any_pos = {ap:>9,}  ({100*ap/total:5.2f}%)"
          f"   mixed/any_pos = {100*mx/ap:5.2f}%")

print("\nReplacement text candidate:")
hh = s["any_pos"]["HIGH_HEART_RATE"]
ll = s["any_pos"]["LOW_HEART_RATE"]
ww = s["any_pos"]["WIDE_QRS"]
print(f"  The fraction of studies with at least one positive bin is "
      f"${100*hh/total:.2f}\\%$ for \\texttt{{HIGH\\_HEART\\_RATE}}, "
      f"${100*ll/total:.2f}\\%$ for \\texttt{{LOW\\_HEART\\_RATE}}, and "
      f"${100*ww/total:.2f}\\%$ for \\texttt{{WIDE\\_QRS}}.")

mh = s["mixed"]["HIGH_HEART_RATE"]
ml = s["mixed"]["LOW_HEART_RATE"]
mw = s["mixed"]["WIDE_QRS"]
print(f"  Within the studies that have any positive bin, the fraction with "
      f"\\emph{{mixed}} labels is ${100*mh/hh:.1f}\\%$ for \\texttt{{HIGH\\_HEART\\_RATE}}, "
      f"${100*ml/ll:.1f}\\%$ for \\texttt{{LOW\\_HEART\\_RATE}}, and "
      f"${100*mw/ww:.1f}\\%$ for \\texttt{{WIDE\\_QRS}}.")

print("\n--- Per-bin counts for Table 1 (tab:taskB_perbin) ---")
for q in ("HIGH_HEART_RATE", "LOW_HEART_RATE", "WIDE_QRS"):
    bins = s["per_bin_pos"][q]
    formatted = " & ".join(f"{b:,}".replace(",", "{,}") for b in bins)
    q_escaped = q.replace("_", "\\_")
    print("  \\texttt{" + q_escaped + "} & " + formatted + " \\\\")

print("\n--- Splits (for prose around train/val/test) ---")
sp = s["splits"]
print(f"  train={sp.get('train', 0):,}, val={sp.get('val', 0):,}, test={sp.get('test', 0):,}")

print("\nDone. Use these numbers to edit paper/main.tex.")
