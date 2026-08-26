"""Stage P2.1 script 02 -- A2: measurement-blind physiological inference (L3).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/02_build_A2_measurement_blind.py [--dev]

Spec §4.A.2. Three softmax heads -- binned HR, QRS duration and QTc -- predicted
from the signal alone. Plan A/B §5.4 calls this a sanity check, not a novelty
claim, and mandates reporting by SQI tier.

**Cohort deviation, already locked.** §4.A.2.2 sets the primary cohort to
``sqi_tier == 'high'`` and estimates ~445 K ECGs. Measured, ``high`` is 4,166 of
749,112 clean studies (0.56 %), of which 3,110 are L3 -- a literal A2 would
train on 3,110 ECGs. Round 6.4 / progress-doc question 9 resolved this: the
primary cohort is ``sqi_tier in {high, medium}`` and high-only becomes one row
of the §4.A.2.8 per-SQI sensitivity table. A4 already used {high, medium}, so
the two tasks now share one SQI rule. **Disclosed in the supplementary.**

The table holds the union of the primary and sensitivity cohorts; ``is_primary``
marks ``link_tier == 'L3' and sqi_tier in {high, medium}``. ``link_tier`` and
``sqi_tier`` are present so every §4.A.2.8 slice is a filter, not a rebuild.

Labels read the MACHINE measurement (Round 6.1) with the 29999 sentinel masked
(Round 6.2); the ``*_missing`` flag columns are never consulted -- they are False
for all 749,112 rows and mark nothing.
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

STAGE = "P2.1"
SCRIPT = "02_build_A2_measurement_blind"
TASK = "A2_measurement_blind"

PRIMARY_SQI = ("high", "medium")


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

    bc.preflight([
        bc.DATA_PROCESSED / "index" / "ecg_metadata_clean_with_measurements.parquet",
        bc.DATA_PROCESSED / "waveform_qc.parquet",
        bc.DATA_PROCESSED / "splits_subject_level.parquet",
    ])

    table = mt.measurement_table(dev=args.dev)
    log.info("clean cohort with all three machine measurements valid: %d", len(table))

    # A2 is L3-scoped; L2 rides along for the l3_vs_l3l2 sensitivity table.
    df = table[table.link_tier.isin(["L3", "L2"])].copy()
    df["is_primary"] = (df.link_tier == "L3") & (df.sqi_tier.isin(PRIMARY_SQI))
    log.info("A2 table: %d rows, %d primary", len(df), int(df.is_primary.sum()))

    counts = bc.write_task_split_parquets(df, TASK, schema=mt.SCHEMA)
    log.info("wrote splits: %s", counts)

    primary = df[df.is_primary]
    stats = {
        "n_rows_total": int(len(df)),
        "n_rows_primary": int(len(primary)),
        "splits_total": counts,
        "sqi_breakdown_l3": {
            tier: int(((df.link_tier == "L3") & (df.sqi_tier == tier)).sum())
            for tier in ("high", "medium", "low")
        },
        "n_rows_l3_sqi_high_only": int(
            ((df.link_tier == "L3") & (df.sqi_tier == "high")).sum()
        ),
        "n_rows_l3_l2_sqi_high_medium": int(df.sqi_tier.isin(PRIMARY_SQI).sum()),
        "labels_primary": mt.label_stats(primary),
        "measurement_summary_primary": {
            col: {
                "mean": round(float(primary[col].mean()), 2),
                "median": round(float(primary[col].median()), 2),
                "min": round(float(primary[col].min()), 2),
                "max": round(float(primary[col].max()), 2),
            }
            for col in ("hr_bpm", "qrs_ms", "qtc_ms")
        },
        "qtc_bazett_valid_pct_primary": round(
            100 * float(primary.qtc_ms_bazett.notna().mean()), 2
        ),
    }
    stats.update(bc.split_summary(df))
    stats.update({f"primary_{k}": v for k, v in bc.split_summary(primary).items()})
    log.info("validation:\n%s", json.dumps(stats, indent=2))

    if stats["n_rows_primary"] == 0:
        raise RuntimeError("A2 primary cohort is empty")
    for head in mt.HEADS:
        if primary[head].isna().any():
            raise RuntimeError(f"{head} is null on a primary row -- validity gate leaked")

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# A2 -- measurement-blind physiological inference (L3 cohort)

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.A.2 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/02_build_A2_measurement_blind.py`.

## Reading this table

| Analysis | Filter |
| --- | --- |
| **Primary** | `is_primary` — `link_tier == 'L3' and sqi_tier in ('high','medium')` |
| §4.A.2.8 high-SQI-only row | `link_tier == 'L3' and sqi_tier == 'high'` |
| §4.A.2.8 low-SQI row | `link_tier == 'L3' and sqi_tier == 'low'` |
| L3 vs L3+L2 | `link_tier in ('L3','L2')` — the whole table |

## Two locked deviations from §4

1. **Primary cohort is `sqi_tier in {{high, medium}}`, not `high`** (Round 6.4,
   progress-doc question 9). `high` alone is 3,110 L3 studies, not the ~445 K
   §4.A.2.2 predicts. high-only is now a sensitivity row.
2. **`qtc_ms` is `machine_qtc_ms`**, not `structured_features.qtc_bazett_ms`
   which §4.A.2.3 names. The NeuroKit column correlates with the machine QTc at
   r = 0.024 and is valid for 656,358 studies against 748,618. It is kept as
   `qtc_ms_bazett` for provenance and one sensitivity row.

Both are disclosed in the supplementary.

## Labels

`hr_label` bradycardia / normal / tachycardia at 60 and 100 bpm ·
`qrs_label` normal / borderline / wide at 100 and 120 ms ·
`qtc_label` short / normal / prolonged at 350 and 450 ms (single cut for both
sexes; the 460 ms female cut is a supplementary sensitivity).

A row is emitted only when all three machine measurements are valid — sentinel
`29999` masked, then range-gated to HR 20–300, QRS 40–300, QTc 200–800.

## Forbidden inputs

Everything except the four signal kinds (§4.A.2.4): images, `report_text`,
`machine_measurements` and `structured_features` are all forbidden. `hr_bpm`,
`qrs_ms`, `qtc_ms` and `qtc_ms_bazett` are in this table as **label
provenance**; feeding them to a model is the leakage the task exists to avoid.

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
