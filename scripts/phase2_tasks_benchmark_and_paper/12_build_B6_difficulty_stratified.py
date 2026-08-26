"""Stage P2.2 script 12 -- B6: difficulty-stratified cross-modal verification.

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/12_build_B6_difficulty_stratified.py [--dev]

Spec §4.B.6. B6 is **not a separate trained task**: it is an evaluation-time
stratification of B4 by negative-type difficulty, reusing B4's trained models and
B4's rows. This builder therefore writes a pointer table only
(``eval_keys.parquet``), exactly as §4.B.6.5 specifies -- the rows live in the
B4 parquet.

Tiers (§4.B.6.2):

| tier | ``neg_type`` |
| --- | --- |
| easy | TEXT_SWAP, IMAGE_SWAP, SIGNAL_SWAP, PARTIAL_MISMATCH -- cross-subject swaps |
| medium | HARD_NEGATIVE_TEXT -- same-HR-bucket swap |
| hard | RESERVED, ships empty |

**Open question 13, proceeding under the stated default.** The hard tier would
be a same-HR-bucket, SAME-SUBJECT swap; Round 3 left it RESERVED and the
progress-doc default is "ship the hard tier empty". It ships empty. The tier is
declared in the output's tier vocabulary so adding it later is a rebuild of this
one small table, not of B4.

Positives carry no ``neg_type`` and so belong to no difficulty tier, but they
are still needed to compute AUPRC and Recall@1 within a tier. They are emitted
with ``difficulty_tier == 'positive'`` so an evaluator can select
"tier X plus the positives" without going back to B4.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402

STAGE = "P2.2"
SCRIPT = "12_build_B6_difficulty_stratified"
TASK = "B6_difficulty_stratified"
B4_TASK = "B4_cross_modal_verification"

TIERS = {
    "easy": ["TEXT_SWAP", "IMAGE_SWAP", "SIGNAL_SWAP", "PARTIAL_MISMATCH"],
    "medium": ["HARD_NEGATIVE_TEXT"],
    "hard": [],          # RESERVED -- progress-doc question 13, default: empty
}

SCHEMA = pa.schema([
    ("study_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("neg_type", pa.string()),
    ("difficulty_tier", pa.string()),
    ("split", pa.string()),
])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    bc.add_std_args(parser)
    args = parser.parse_args()
    bc.set_dev(args.dev)

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT + ("_dev" if args.dev else ""))
    if state.done and not args.force:
        log.info("already complete (%s rows) -- pass --force to rebuild", state.data.get("n_rows"))
        return 0
    state.reset()
    started = time.time()

    b4_dir = bc.tasks_root() / B4_TASK
    bc.preflight([b4_dir / f"{split}.parquet" for split in bc.SPLITS])

    b4 = pd.concat(
        [pd.read_parquet(b4_dir / f"{split}.parquet",
                         columns=["anchor_study_id", "subject_id", "neg_type", "split"])
         for split in bc.SPLITS],
        ignore_index=True,
    )
    log.info("B4 rows: %d", len(b4))

    tier_of = {neg: tier for tier, negs in TIERS.items() for neg in negs}
    df = b4.rename(columns={"anchor_study_id": "study_id"}).copy()
    df["difficulty_tier"] = df["neg_type"].map(tier_of)
    df.loc[df["neg_type"].isna(), "difficulty_tier"] = "positive"

    unassigned = df[df.difficulty_tier.isna()]
    if len(unassigned):
        raise RuntimeError(
            f"{len(unassigned)} rows carry a neg_type with no difficulty tier: "
            f"{sorted(unassigned.neg_type.dropna().unique())}"
        )

    df["neg_type"] = df["neg_type"].astype("string")
    df = df.sort_values(["split", "difficulty_tier", "study_id"],
                        kind="mergesort").reset_index(drop=True)

    out_dir = bc.task_dir(TASK)
    import pyarrow.parquet as pq

    table = pa.Table.from_pandas(df[[f.name for f in SCHEMA]], schema=SCHEMA, preserve_index=False)
    tmp = out_dir / "eval_keys.parquet.tmp"
    pq.write_table(table, tmp, compression="snappy")
    bc.atomic_replace(tmp, out_dir / "eval_keys.parquet")
    log.info("wrote %s rows=%d", out_dir / "eval_keys.parquet", len(df))

    test = df[df.split == "test"]
    stats = {
        "n_rows": int(len(df)),
        "n_studies": int(df.study_id.nunique()),
        "rows_per_tier": df.difficulty_tier.value_counts().to_dict(),
        "test_rows_per_tier": test.difficulty_tier.value_counts().to_dict(),
        "test_rows_per_neg_type": {
            str(k): int(v) for k, v in test.neg_type.value_counts(dropna=False).items()
        },
        "hard_tier_status": "RESERVED, empty (progress-doc question 13, stated default)",
        "n_subjects": int(df.subject_id.nunique()),
    }
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str))

    if stats["rows_per_tier"].get("medium", 0) == 0:
        raise RuntimeError("the medium tier is empty -- B4 emitted no HARD_NEGATIVE_TEXT rows")

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2, default=str), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# B6 -- difficulty-stratified cross-modal verification

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.B.6 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/12_build_B6_difficulty_stratified.py`.

**This directory holds a pointer table, not a dataset.** B6 is an
evaluation-time stratification of B4 (§4.B.6.2): it reuses B4's trained models
and B4's rows, and `eval_keys.parquet` only says which row belongs to which
difficulty tier.

| tier | `neg_type` |
| --- | --- |
| `easy` | TEXT_SWAP, IMAGE_SWAP, SIGNAL_SWAP, PARTIAL_MISMATCH (cross-subject swaps) |
| `medium` | HARD_NEGATIVE_TEXT (same-HR-bucket swap) |
| `hard` | RESERVED — **ships empty** |
| `positive` | the `y_match == 1` rows, tier-free but needed to score any tier |

## The hard tier is empty on purpose

Round 3 reserved it, and progress-doc question 13 asks whether to add a
same-HR-bucket, **same-subject** swap. The stated default is to ship it empty,
and that is what this table does. Adding it later rebuilds this one pointer
table plus the corresponding B4 rows — not the trained models.

## Scoring a tier

Select `difficulty_tier in ('<tier>', 'positive')` and join to B4 on
`(study_id, neg_type, split)`. Positives are shared across tiers by design:
Recall@1 and AUPRC are undefined without them.

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
