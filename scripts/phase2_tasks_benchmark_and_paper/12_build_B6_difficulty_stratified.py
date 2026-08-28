"""Stage P2.2 script 12 -- B6: difficulty-stratified cross-modal verification.

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/12_build_B6_difficulty_stratified.py [--dev]

Spec §4.B.6. B6 is **not a separate trained task**: it is an evaluation-time
stratification of B4 by negative-type difficulty, reusing B4's trained models and
B4's rows. This builder therefore writes a pointer table only
(``eval_keys.parquet``), exactly as §4.B.6.5 specifies -- the rows live in the
B4 parquet.

Tiers (§4.B.6.2):

Tiers are Plan A/B §6.7's six levels (§4.B.6.2 originally named three, of which
the third shipped empty -- see below):

| tier | ``neg_type`` | §6.7 level |
| --- | --- | --- |
| level_0_random | TEXT_SWAP, IMAGE_SWAP, SIGNAL_SWAP, PARTIAL_MISMATCH | 0 |
| level_1_hr | HARD_NEGATIVE_TEXT -- same-HR-bucket swap | 1 |
| level_2_hr_qrs | HARD_NEGATIVE_L2 -- HR + QRS matched | 2 |
| level_3_full_physio | HARD_NEGATIVE_L3 -- HR + QRS + axis + QTc matched | 3 |
| level_4_same_patient | HARD_NEGATIVE_L4 -- same patient, different study | 4 |
| level_5_near_duplicate | HARD_NEGATIVE_L5 -- own report, one claim swapped | 5 |

**Open question 13 is now closed, and closed differently.** The old "hard" tier
was to be a same-HR-bucket SAME-SUBJECT swap and shipped empty, leaving a
two-point "curve" where §6.8's Figure 4 needs six. Levels 2-5 replace it and
subsume the same-subject idea as Level 4. They live only in the TEST split, so
the curve measures generalisation to harder negatives -- §6.7's predicted
plateau -- rather than something the model was trained on, and no model needs
retraining to produce it.

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

# Plan A/B §6.7's six levels, in the order Figure 4 plots them. The tier NAME is
# the level, so the curve reads off `difficulty_tier` directly.
TIERS = {
    # Level 0 -- a random different-subject study. "All competent models
    # should be high" (§6.7).
    "level_0_random": ["TEXT_SWAP", "IMAGE_SWAP", "SIGNAL_SWAP", "PARTIAL_MISMATCH"],
    # Level 1 -- matched on HR bin. "Performance drops if model used only HR."
    "level_1_hr": ["HARD_NEGATIVE_TEXT"],
    # Level 2 -- matched on HR + QRS bin.
    "level_2_hr_qrs": ["HARD_NEGATIVE_L2"],
    # Level 3 -- matched on HR + QRS + axis + QTc. "Most shortcut models plateau."
    "level_3_full_physio": ["HARD_NEGATIVE_L3"],
    # Level 4 -- same patient, different study. Prevents the patient/demographic
    # shortcut; the rung that matters most in MIMIC, where one subject carries
    # many ECGs.
    "level_4_same_patient": ["HARD_NEGATIVE_L4"],
    # Level 5 -- the anchor's own report with one clinical claim swapped
    # (B5's locked injection). "Only robust multimodal models should remain high."
    "level_5_near_duplicate": ["HARD_NEGATIVE_L5"],
}
# Levels 2-5 exist only in the TEST split by design -- see
# `_dataset_lib/verification_task.py`. Their tier rows therefore cover test only,
# and no model is retrained to obtain the curve.
TEST_ONLY_TIERS = ("level_2_hr_qrs", "level_3_full_physio",
                   "level_4_same_patient", "level_5_near_duplicate")

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
        "levels_2_to_5_are_test_only": True,
        "n_subjects": int(df.subject_id.nunique()),
    }
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str))

    # Every one of Plan A/B §6.7's six levels must have rows in TEST, or Figure 4
    # has a gap. This is the check that would have caught the empty "hard" tier
    # the first time round.
    empty = [tier for tier in TIERS if int(stats["test_rows_per_tier"].get(tier, 0)) == 0]
    if empty:
        raise RuntimeError(
            f"§6.7 requires all six difficulty levels; these have no TEST rows: {empty}. "
            "Rebuild A5/B4 first -- levels 2-5 come from "
            "`_dataset_lib/verification_task.py`.")
    # Levels 2-5 are test-only by design; a train row for one means the ladder
    # leaked into training and Figure 4 would measure the training distribution.
    leaked = df[(df.split != "test") & df.difficulty_tier.isin(TEST_ONLY_TIERS)]
    if len(leaked):
        raise RuntimeError(
            f"{len(leaked)} level-2..5 rows sit outside the test split. Those levels "
            "must never be trained on -- see verification_task.DIFFICULTY_NEG_TYPES.")

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
