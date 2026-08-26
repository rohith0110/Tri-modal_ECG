"""Stage P2.2 script 07 -- B1: measurement-blind physiological inference (full cohort).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/07_build_B1_measurement_blind.py [--dev]

Spec §4.B.1. Same labels and same input policy as A2 (§4.B.1.3: "Identical to
§4.A.2.3"); the only difference is cohort scope -- B1 takes the **full clean
cohort** rather than A2's L3 x {high, medium} SQI slice, so ``link_tier`` runs
all the way down to L0 (§4.B.1.5).

Because the labels are identical by specification, they are computed once in
``_dataset_lib/measurement_task.py`` and both builders filter it. A second copy
of the thresholds is exactly how A2 and B1 would silently diverge.

The Plan-B-distinct claim (§4.B.1.8) is the per-linkage-tier breakdown: does the
model perform uniformly across L3 / L2 / L1 / L0? ``link_tier`` is on every row,
so that table is a groupby.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402
from _dataset_lib import measurement_task as mt  # noqa: E402

STAGE = "P2.2"
SCRIPT = "07_build_B1_measurement_blind"
TASK = "B1_measurement_blind"


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

    bc.preflight([bc.DATA_PROCESSED / "index" / "ecg_metadata_clean_with_measurements.parquet"])

    df = mt.measurement_table(dev=args.dev)
    df["is_primary"] = True          # the full clean cohort IS the B1 cohort
    log.info("B1 cohort: %d rows", len(df))

    counts = bc.write_task_split_parquets(df, TASK, schema=mt.SCHEMA)
    log.info("wrote splits: %s", counts)

    stats = {
        "n_rows_total": int(len(df)),
        "splits_total": counts,
        "linkage_tier_breakdown": df.link_tier.value_counts().to_dict(),
        "sqi_tier_breakdown": df.sqi_tier.value_counts().to_dict(),
        "labels": mt.label_stats(df),
        "measurement_summary": {
            col: {"mean": round(float(df[col].mean()), 2),
                  "median": round(float(df[col].median()), 2)}
            for col in ("hr_bpm", "qrs_ms", "qtc_ms")
        },
        "n_shared_with_A2_primary": int(
            ((df.link_tier == "L3") & df.sqi_tier.isin(["high", "medium"])).sum()
        ),
    }
    stats.update(bc.split_summary(df))
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str))

    if stats["n_rows_total"] == 0:
        raise RuntimeError("B1 cohort is empty")
    for head in mt.HEADS:
        if df[head].isna().any():
            raise RuntimeError(f"{head} is null on a B1 row -- validity gate leaked")

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2, default=str), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# B1 -- measurement-blind physiological inference (full clean cohort)

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.B.1 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/07_build_B1_measurement_blind.py`.

Same three heads and the same thresholds as A2 (§4.B.1.3), on the **full clean
cohort** instead of A2's L3 x {{high, medium}} slice. `is_primary` is True on
every row: here the whole cohort is the cohort.

| Analysis | Filter |
| --- | --- |
| **Primary** | none — the whole table |
| Per-linkage-tier (the Plan-B-distinct claim, §4.B.1.8) | `link_tier` — L3 / L2 / L1 / L0 |
| Per-SQI tier | `sqi_tier` |
| Overlap with A2's primary cohort | `link_tier == 'L3' and sqi_tier in ('high','medium')` |

Labels come from `_dataset_lib/measurement_task.py`, shared with A2 and B2, so
the three tasks cannot drift apart. `qtc_ms` is `machine_qtc_ms`; see the A2
README for why the NeuroKit `qtc_bazett_ms` is provenance only.

A row exists only when all three machine measurements are valid — the `29999`
sentinel masked, then range-gated.

## Forbidden inputs

Everything except the four signal kinds (§4.B.1.4 = §4.A.2.4). The measurement
columns in this table are label provenance, not features.

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
