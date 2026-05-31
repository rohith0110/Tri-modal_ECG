"""Static sanity check for main.tex.

  - every \includegraphics{...} resolves to a file in figures/
  - every \cite{...} key is defined in references.bib
  - every \ref{...} has a matching \label{...}

Run from paper/:    python check_paper.py
"""

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
tex = open(os.path.join(HERE, "main.tex"), encoding="utf-8").read()
bib = open(os.path.join(HERE, "references.bib"), encoding="utf-8").read()
fig_dir = os.path.join(HERE, "figures")

# 1. Figures referenced from \includegraphics
fig_calls = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", tex)
unique_figs = sorted(set(fig_calls))
missing_figs = []
for f in unique_figs:
    found = False
    for ext in ("", ".png", ".pdf", ".jpg", ".jpeg"):
        if os.path.exists(os.path.join(fig_dir, f + ext)):
            found = True
            break
    if not found:
        missing_figs.append(f)

# 2. Cite keys
cite_keys = set()
for m in re.finditer(r"\\cite\{([^}]+)\}", tex):
    for k in m.group(1).split(","):
        cite_keys.add(k.strip())
bib_keys = set(re.findall(r"@\w+\{([^,]+),", bib))
missing_keys = sorted(cite_keys - bib_keys)
unused_keys = sorted(bib_keys - cite_keys)

# 3. Refs/labels (also recognise listings package "label={...}" inside lstlisting opts)
labels = set(re.findall(r"\\label\{([^}]+)\}", tex))
labels |= set(re.findall(r"\\begin\{lstlisting\}\[[^\]]*label\s*=\s*\{?([^,}\]]+)\}?", tex))
refs = set(re.findall(r"\\(?:ref|eqref)\{([^}]+)\}", tex))
missing_refs = sorted(refs - labels)

print(f"=== Figure check ===")
print(f"  unique figures referenced : {len(unique_figs)}")
print(f"  missing figures           : {missing_figs if missing_figs else 'none'}")
print()
print(f"=== Citation check ===")
print(f"  cite keys used            : {len(cite_keys)}")
print(f"  bib keys present          : {len(bib_keys)}")
print(f"  missing cite keys         : {missing_keys if missing_keys else 'none'}")
print(f"  unused bib keys           : {len(unused_keys)} (informational)")
print()
print(f"=== Cross-reference check ===")
print(f"  labels present            : {len(labels)}")
print(f"  refs used                 : {len(refs)}")
print(f"  missing refs              : {missing_refs if missing_refs else 'none'}")
print()
print("All checks passed." if not (missing_figs or missing_keys or missing_refs)
      else "FAILED — see lists above.")
