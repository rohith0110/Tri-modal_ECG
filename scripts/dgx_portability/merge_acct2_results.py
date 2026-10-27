#!/usr/bin/env python3
"""Merge account 2's results (R2 `acct2/`) into the root results in R2.

    python3 merge_acct2_results.py            # dry run: download, merge, report
    python3 merge_acct2_results.py --apply    # ...and upload the merged files

Account 2 pushes everything under `trimodal-results/acct2/` (docs/DGX_ACCOUNTS.md)
so the two accounts never overwrite each other's per-task CSVs. Campaigns 11
and 14 stage `results` from the ROOT, so this has to run before either of them.

What it does, per kind:

* `model_runs/` -- run paths are disjoint between accounts (one account per
  campaign), so a plain `rclone copy --ignore-existing`. A run present on both
  sides is reported and the root copy kept.
* `results/<task>.csv` -- one row per (arch_tier, head, metric, group). A tier
  is evaluated by exactly one account, so rows are unioned by tier. A tier
  present on BOTH sides stops the merge: that means a campaign ran twice.
* `results/<task>_extras.json` -- `{section: {arch_tier: ...}}`, unioned per
  section and tier the same way.
* `figures/` -- copied with `--ignore-existing`.
* `audit_reports/threshold_audit.md` -- an append-only log each account wrote
  separately; account 2's is stored beside it as `threshold_audit.acct2.md`.

Runs on a login node: it moves a few MB of CSVs and the run artifacts, no
compute. Idempotent: running it twice changes nothing the second time.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = os.environ.get("R2_RESULTS_ROOT", "r2-results:trimodal-results")
ACCT2 = f"{ROOT}/acct2"
SORT = ["arch_tier", "head", "metric", "group_key", "group_value"]


def rclone() -> str:
    for candidate in (os.environ.get("RCLONE"), shutil.which("rclone"),
                      str(Path.home() / "se23ucse027/bin/rclone")):
        if candidate and Path(candidate).is_file():
            return candidate
    sys.exit("rclone not found; set RCLONE")


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([rclone(), *args], capture_output=True, text=True, check=check)


def merge_csv(root: Path | None, acct2: Path) -> tuple[pd.DataFrame, list[str]]:
    theirs = pd.read_csv(acct2)
    if root is None:
        return theirs, sorted(theirs["arch_tier"].unique())
    ours = pd.read_csv(root)
    both = sorted(set(ours["arch_tier"]) & set(theirs["arch_tier"]))
    if both:
        identical = all(
            ours[ours.arch_tier == t].sort_values(SORT).reset_index(drop=True).equals(
                theirs[theirs.arch_tier == t].sort_values(SORT).reset_index(drop=True))
            for t in both)
        if not identical:
            raise SystemExit(f"{acct2.name}: tiers {both} were evaluated on BOTH accounts "
                             f"with different numbers -- a campaign ran twice. Stopping.")
        theirs = theirs[~theirs.arch_tier.isin(both)]
    added = sorted(theirs["arch_tier"].unique())
    merged = pd.concat([ours, theirs.reindex(columns=ours.columns)], ignore_index=True)
    return merged.sort_values(SORT, kind="mergesort").reset_index(drop=True), added


def merge_extras(root: Path | None, acct2: Path) -> dict:
    merged = json.loads(root.read_text(encoding="utf-8")) if root else {}
    for section, tiers in json.loads(acct2.read_text(encoding="utf-8")).items():
        target = merged.setdefault(section, {})
        for tier, value in tiers.items():
            if tier in target and target[tier] != value:
                raise SystemExit(f"{acct2.name}: {section}/{tier} differs between accounts")
            target[tier] = value
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="upload the merge")
    args = parser.parse_args()
    verb = "copying" if args.apply else "would copy"

    # ---- model_runs and figures: disjoint trees ---------------------------
    for tree in ("model_runs", "figures"):
        listing = run("lsf", "-R", "--files-only", f"{ACCT2}/{tree}", check=False)
        theirs = set(listing.stdout.split())
        mine = set(run("lsf", "-R", "--files-only", f"{ROOT}/{tree}", check=False).stdout.split())
        clash = sorted(theirs & mine)
        print(f"{tree}: {len(theirs)} files in acct2, {len(theirs - mine)} new to root")
        for path in clash[:20]:
            print(f"  ON BOTH, root kept: {tree}/{path}")
        if args.apply and theirs - mine:
            run("copy", "--ignore-existing", "--s3-no-check-bucket",
                f"{ACCT2}/{tree}", f"{ROOT}/{tree}")
            print(f"  {verb} {len(theirs - mine)} files")

    # ---- results: union by tier -------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root_dir, acct2_dir, out_dir = (Path(tmp) / n for n in ("root", "acct2", "out"))
        for remote, local in ((f"{ROOT}/results", root_dir), (f"{ACCT2}/results", acct2_dir)):
            run("copy", "--exclude", "_dev/**", "--exclude", ".eval_checkpoints/**",
                remote, str(local), check=False)
        out_dir.mkdir()
        acct2_dir.mkdir(exist_ok=True)
        for theirs in sorted(acct2_dir.glob("*.csv")):
            mine = root_dir / theirs.name
            merged, added = merge_csv(mine if mine.exists() else None, theirs)
            merged.to_csv(out_dir / theirs.name, index=False)
            print(f"results/{theirs.name}: + tiers {added}")
        for theirs in sorted(acct2_dir.glob("*_extras.json")):
            mine = root_dir / theirs.name
            merged = merge_extras(mine if mine.exists() else None, theirs)
            (out_dir / theirs.name).write_text(json.dumps(merged, indent=2, default=str),
                                               encoding="utf-8")
            print(f"results/{theirs.name}: merged")
        if args.apply and any(out_dir.iterdir()):
            run("copy", "--s3-no-check-bucket", str(out_dir), f"{ROOT}/results")
            print(f"  uploaded {len(list(out_dir.iterdir()))} merged result files")

    # ---- the threshold audit: kept beside, never interleaved ---------------
    audit = f"{ACCT2}/audit_reports/threshold_audit.md"
    if run("lsf", audit, check=False).stdout.strip():
        print(f"audit_reports: {verb} acct2's threshold_audit.md -> threshold_audit.acct2.md")
        if args.apply:
            run("copyto", "--s3-no-check-bucket", audit,
                f"{ROOT}/audit_reports/threshold_audit.acct2.md")

    if not args.apply:
        print("dry run -- nothing uploaded. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
