"""Stage P2.2 script 10 -- B4: cross-modal verification (Plan B counterpart to A5).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/10_build_B4_cross_modal_verification.py [--dev]

Spec §4.B.4. Verification only -- A5's construction without the masked-attribute
head. §4.B.4.3 says "same 5-negative-type construction as A5's verification
head", and §4.B.4.8 asks whether training jointly with the masked-attribute head
helps or hurts pure verification.

That comparison is only interpretable if A5 and B4 see the **same rows**, so
both call ``_dataset_lib/verification_task.py``. The construction is a pure
function of the cohort and a splitmix64 hash of (anchor, negative type), so this
builder reproduces A5's rows exactly without reading A5's output -- no ordering
dependency between the two scripts, and no silent drift if one is re-run.
Equality against A5's parquets is asserted here whenever they exist.

B6 (§4.B.6) is an evaluation-time stratification of this table and stores only a
pointer table; the rows live here.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402
from _dataset_lib import verification_task as vt  # noqa: E402

STAGE = "P2.2"
SCRIPT = "10_build_B4_cross_modal_verification"
TASK = "B4_cross_modal_verification"
A5_TASK = "A5_cross_modal_verification"


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

    cohort = bc.load_clean_cohort(dev=args.dev)
    df = vt.build_verification(dev=args.dev)
    vt.assert_no_cross_split_donor(df, cohort)
    vt.assert_negatives_are_mismatched(df, cohort)
    vt.assert_rendering_balanced(df)
    log.info("B4 verification rows: %d", len(df))

    counts = bc.write_task_split_parquets(df, TASK, schema=vt.SCHEMA)
    log.info("wrote splits: %s", counts)

    # A5 and B4 must be the same rows, or §4.B.4.8's comparison is not a
    # controlled one. Assert it rather than trusting that both ran the same code.
    identical: bool | None = None
    a5_dir = bc.tasks_root() / A5_TASK
    if all((a5_dir / f"{split}.parquet").exists() for split in bc.SPLITS):
        a5 = pd.concat(
            [pd.read_parquet(a5_dir / f"{split}.parquet") for split in bc.SPLITS],
            ignore_index=True,
        ).sort_values(["anchor_study_id", "y_match", "neg_type"],
                      kind="mergesort").reset_index(drop=True)
        mine = df.sort_values(["anchor_study_id", "y_match", "neg_type"],
                              kind="mergesort").reset_index(drop=True)
        identical = bool(len(a5) == len(mine)) and bool(
            (a5[list(mine.columns)].fillna("").to_numpy() == mine.fillna("").to_numpy()).all()
        )
        if not identical:
            raise RuntimeError(
                "B4's verification rows differ from A5's. They are built by the same "
                "deterministic function, so a difference means one of the two ran against "
                "a different cohort -- rebuild both before training either."
            )
        log.info("A5 / B4 row equality: PASS (%d rows)", len(mine))
    else:
        log.warning("A5 verification parquets absent -- equality check skipped")

    stats = vt.verification_stats(df)
    stats["splits"] = counts
    stats["identical_to_A5_verification"] = identical
    stats.update(bc.split_summary(df))
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str))

    if stats["n_rows"] == 0:
        raise RuntimeError("B4 verification table is empty")

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2, default=str), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# B4 -- cross-modal verification (Plan B counterpart to A5)

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.B.4 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/10_build_B4_cross_modal_verification.py`.

Row-for-row identical to A5's verification table, by construction and by
assertion. Both call `_dataset_lib/verification_task.py`, whose output is a pure
function of the cohort and a splitmix64 hash of (anchor, negative type). The
builder checks equality against A5's parquets when they exist and refuses to
finish if they disagree.

Identity is the point: §4.B.4.8 compares B4 against A5's verification head to
ask whether the masked-attribute head helps or hurts. If the two tasks saw
different rows, the comparison would measure the data, not the multitasking.

| Analysis | Filter |
| --- | --- |
| Per-`neg_type` F1 (§4.B.4.8) | `neg_type` |
| Clean vs scan-like image | `image_type` (positives and negatives are 50/50, §12.12) |
| Lead-II vs 12-lead image | resolve a different modality kind for the same `image_id` |
| Difficulty tiers | see `B6_difficulty_stratified/eval_keys.parquet` |

See the A5 README for the construction table and the two split-safety rules.

## Forbidden inputs

`machine_measurements`, `structured_features` (§4.B.4.4). Unlike A5, there is no
`report_text_masked` here — B4 has no masked-attribute head.

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
