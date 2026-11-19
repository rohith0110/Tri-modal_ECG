"""Bring the `image_type` column of A5/B4 text and signal predictions onto the §12.12 rows.

    ecg_env/bin/python scripts/dgx_portability/q18_relabel_image_type.py \
        --data-root /dgxa_home/se23ucse027/se23ucse027/data/processed            # dry run
    ecg_env/bin/python scripts/dgx_portability/q18_relabel_image_type.py \
        --data-root ... --apply

Open question 18 (spec §12.12): A5/B4 negatives were rebuilt with their
rendering drawn clean/scan-like 50/50. Only `image_type` on negative rows
changed -- every pointer, row count and order is byte-identical. A tier that
reads no image (text_*, signal_*) trains on exactly the same inputs either way,
so its weights and scores are valid; but `30_train.py` copied `image_type` into
its prediction files, and `31_eval.py` reads it from there for the
`image_type` subgroup. Those subgroup rows would describe the OLD rendering.

Rather than retrain eighteen runs to get bit-identical models (user decision,
2026-11-19), this rewrites `image_type` -- and nothing else -- in each such
run's `test_predictions.parquet` / `val_predictions.parquet` from the fixed
task parquet, after proving row by row that the two files describe the same
rows in the same order. The original file is kept under
`outputs/_stale_q18/model_runs/...` and a `q18_relabel.json` beside the new one
records both hashes. Image-reading tiers are never touched: they are retrained.

Refuses to run against a task parquet that still has the shortcut (negatives
not ~50 % scan-like).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

TASKS = ("A5_cross_modal_verification", "B4_cross_modal_verification")
IMAGE_READING = ("image_", "multimodal_", "embedding_")
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT") or Path(__file__).resolve().parents[2])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fixed_rows(data_root: Path, task: str, split: str) -> pd.DataFrame:
    path = data_root / "tasks" / task / f"{split}.parquet"
    frame = pd.read_parquet(path, columns=["anchor_study_id", "subject_id", "neg_type",
                                           "y_match", "image_type"])
    scan = frame["image_type"].astype(str).eq("scanlike")
    negative_share = scan[frame["y_match"] == 0].mean()
    if not 0.45 <= negative_share <= 0.55:
        raise SystemExit(f"{path}: negatives are {negative_share:.3f} scan-like -- this is "
                         f"the pre-§12.12 build. Point --data-root at the fixed rows.")
    return frame


def relabel(pred_path: Path, fixed: pd.DataFrame) -> tuple[pd.DataFrame | None, dict]:
    pred = pd.read_parquet(pred_path)
    report: dict = {"rows": int(len(pred))}
    if len(pred) != len(fixed):
        raise SystemExit(f"{pred_path}: {len(pred)} rows, task parquet has {len(fixed)}")
    checks = {
        "study_id": ("study_id", "anchor_study_id"),
        "subject_id": ("subject_id", "subject_id"),
        "neg_type": ("neg_type", "neg_type"),
        "y_match": ("y_true_y_match", "y_match"),
    }
    for name, (ours, theirs) in checks.items():
        if ours not in pred.columns:
            raise SystemExit(f"{pred_path}: no `{ours}` column to align on")
        a = pred[ours].astype(str).to_numpy() if name == "neg_type" else pred[ours].to_numpy()
        b = fixed[theirs].astype(str).to_numpy() if name == "neg_type" else fixed[theirs].to_numpy()
        if not np.array_equal(a, b):
            bad = int((a != b).sum())
            raise SystemExit(f"{pred_path}: `{ours}` differs from the task parquet on {bad} "
                             f"row(s) -- rows are not aligned, refusing to relabel")
    old = pred["image_type"].astype(str).to_numpy()
    new = fixed["image_type"].astype(str).to_numpy()
    changed = old != new
    report["changed"] = int(changed.sum())
    if changed.any() and not (fixed["y_match"].to_numpy()[changed] == 0).all():
        raise SystemExit(f"{pred_path}: image_type differs on a POSITIVE row; §12.12 "
                         f"changed negatives only, so something else is wrong")
    if not changed.any():
        return None, report
    out = pred.copy()
    if isinstance(pred["image_type"].dtype, pd.CategoricalDtype):
        out["image_type"] = pd.Categorical(new, categories=sorted(set(new) | set(old)))
    else:
        out["image_type"] = pd.Series(new, index=pred.index).astype(pred["image_type"].dtype)
    untouched = [c for c in pred.columns if c != "image_type"]
    assert out[untouched].equals(pred[untouched])
    return out, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--data-root", type=Path, required=True,
                        help="a data/processed holding the FIXED A5/B4 task parquets")
    parser.add_argument("--run-root", type=Path, default=PROJECT_ROOT / "outputs" / "model_runs")
    parser.add_argument("--archive-root", type=Path,
                        default=PROJECT_ROOT / "outputs" / "_stale_q18" / "model_runs")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total = 0
    for task in TASKS:
        task_dir = args.run_root / task
        if not task_dir.is_dir():
            continue
        cache: dict[str, pd.DataFrame] = {}
        for tier_dir in sorted(p for p in task_dir.iterdir() if p.is_dir()):
            if tier_dir.name.startswith(IMAGE_READING):
                continue
            for seed_dir in sorted(tier_dir.glob("seed_*")):
                for split in ("test", "val"):
                    pred_path = seed_dir / f"{split}_predictions.parquet"
                    if not pred_path.exists():
                        continue
                    if split not in cache:
                        cache[split] = fixed_rows(args.data_root, task, split)
                    out, report = relabel(pred_path, cache[split])
                    rel = pred_path.relative_to(args.run_root)
                    if out is None:
                        print(f"  ok      {rel}: already on the fixed rows")
                        continue
                    total += 1
                    print(f"  {'RELABEL' if args.apply else 'would'} {rel}: "
                          f"{report['changed']} of {report['rows']} rows")
                    if not args.apply:
                        continue
                    archive = args.archive_root / rel
                    archive.parent.mkdir(parents=True, exist_ok=True)
                    if not archive.exists():
                        shutil.copy2(pred_path, archive)
                    before = sha256(archive)
                    tmp = pred_path.with_suffix(".parquet.tmp")
                    out.to_parquet(tmp, index=False)
                    os.replace(tmp, pred_path)
                    record_path = seed_dir / "q18_relabel.json"
                    record = (json.loads(record_path.read_text(encoding="utf-8"))
                              if record_path.exists() else {})
                    record[split] = {"when": stamp, "rows": report["rows"],
                                     "image_type_changed": report["changed"],
                                     "sha256_before": before, "sha256_after": sha256(pred_path),
                                     "original": str(archive),
                                     "source": str(args.data_root / "tasks" / task / f"{split}.parquet"),
                                     "why": "spec §12.12 / open question 18"}
                    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"{total} prediction file(s) {'relabelled' if args.apply else 'to relabel'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
