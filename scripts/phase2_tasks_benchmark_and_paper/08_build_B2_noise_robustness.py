"""Stage P2.2 script 08 -- B2: noise-robustness curriculum.

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/08_build_B2_noise_robustness.py [--dev]

Spec §4.B.2 and §7.3. Quantify how far a B1 model degrades on corrupted signals,
across three strictly separated evaluation regimes.

**No corruption is generated here.** §9.3 is explicit: the builder reads
``data/processed/signals_corrupted.parquet`` from Phase 1 Stage 8 and Phase 2
never regenerates it. This script only attaches labels and regime tags to rows
that already exist.

Labels are the anchor's clean B1 labels, inherited unchanged by every corrupted
variant (§4.B.2.3) -- they come from ``_dataset_lib/measurement_task.py``, the
same module A2 and B1 use, so a corrupted row and its anchor can never disagree.

The three regimes (§7.3), and what rows each needs::

    regime_1  clean-trained model  -> frozen corrupted test set
              rows: the corrupted variants, plus each anchor's clean signal as
              the paired reference the performance drop is measured against
    regime_2  noise-augmented model -> the SAME frozen corrupted test set
              rows: B1's train and val rows, to be corrupted ON THE FLY at
              training time, plus the same corrupted test rows
    regime_3  clean-trained model  -> natural test signals, split by SQI tier
              rows: the test-split clean cohort

``regime_2``'s training-time corruption is drawn from the same
``corruption_recipes_LOCKED.yaml`` families and SNR ladder but a **different RNG
stream** (§4.B.2.5), so the augmentation a model trains on is never a row of the
test set. That policy is progress-doc question 12, and this builder proceeds
under its stated default, recorded in the recipe file: p = 0.5 per sample,
family and SNR uniform, RNG salted ``regime2|``. The builder stamps the policy
into the task README so the trainer reads it from one place.

**Anchor-pool description error (progress-doc question 10), unfixable by
rebuilding.** §4.B.2.2 describes the anchor pool as "test-split ECGs with
``sqi_tier='high'``". Phase 1 Stage 8 applied no SQI filter: it took the
test-split ``raw_lead2`` manifest rows in ``(study_id, subject_id)`` order and
truncated to the first 2,000. The corrupted set is frozen, so the anchors are
SQI-representative rather than high-SQI, and this builder measures and records
the actual mix rather than restating the spec's claim.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402
from _dataset_lib import measurement_task as mt  # noqa: E402

STAGE = "P2.2"
SCRIPT = "08_build_B2_noise_robustness"
TASK = "B2_noise_robustness"

CORRUPTED = bc.DATA_PROCESSED / "signals_corrupted.parquet"

SCHEMA = pa.schema([
    ("study_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("split", pa.string()),
    ("sqi_tier", pa.string()),
    ("clean_signal_kind", pa.string()),
    ("corrupted_signal_kind", pa.string()),
    ("corruption_type", pa.string()),
    ("snr_db", pa.int32()),
    ("hr_label", pa.string()),
    ("qrs_label", pa.string()),
    ("qtc_label", pa.string()),
    ("regime", pa.string()),
    ("row_role", pa.string()),
    ("is_anchor", pa.bool_()),
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

    bc.preflight([CORRUPTED, bc.CONFIG_DIR / "corruption_recipes_LOCKED.yaml"])
    recipes = yaml.safe_load(
        (bc.CONFIG_DIR / "corruption_recipes_LOCKED.yaml").read_text(encoding="utf-8")
    )

    labels = mt.measurement_table(dev=args.dev)
    label_cols = ["study_id", "subject_id", "split", "sqi_tier", *mt.HEADS]
    labels = labels[label_cols]
    log.info("B1 label table: %d rows", len(labels))

    corrupted = pd.read_parquet(
        CORRUPTED,
        columns=["study_id", "subject_id", "split", "corruption_type", "snr_db",
                 "corruption_status"],
    )
    log.info("frozen corrupted rows: %d over %d anchors",
             len(corrupted), corrupted.study_id.nunique())

    ok = corrupted.corruption_status.astype(str).str.lower().eq("ok")
    if not ok.all():
        log.warning("%d corrupted rows are not status=ok and are dropped", int((~ok).sum()))
    corrupted = corrupted[ok]

    # An anchor without valid machine measurements has no B1 label to inherit.
    anchors = corrupted[["study_id"]].drop_duplicates()
    anchor_labels = anchors.merge(labels, on="study_id", how="inner", validate="many_to_one")
    log.info("anchors with usable B1 labels: %d of %d", len(anchor_labels), len(anchors))

    frames: list[pd.DataFrame] = []

    # regime_1 -- the frozen corrupted test set, and its paired clean reference.
    corrupt_rows = corrupted.drop(columns=["split", "subject_id", "corruption_status"]).merge(
        anchor_labels, on="study_id", how="inner"
    , validate="many_to_one")
    corrupt_rows = corrupt_rows.assign(
        clean_signal_kind="raw_lead2", corrupted_signal_kind="signal_corrupted",
        regime="regime_1", row_role="corrupted", is_anchor=True,
    )
    frames.append(corrupt_rows)

    clean_reference = anchor_labels.assign(
        corruption_type=None, snr_db=-1,
        clean_signal_kind="raw_lead2", corrupted_signal_kind=None,
        regime="regime_1", row_role="clean_reference", is_anchor=True,
    )
    frames.append(clean_reference)

    # regime_2 -- the corrupted test set again (a different model, the same
    # rows), plus B1's train/val rows to be corrupted on the fly.
    frames.append(corrupt_rows.assign(regime="regime_2"))
    augment_pool = labels[labels.split.isin(["train", "val"])].assign(
        corruption_type=None, snr_db=-1,
        clean_signal_kind="raw_lead2", corrupted_signal_kind="signal_corrupted",
        regime="regime_2", row_role="augment_on_the_fly", is_anchor=False,
    )
    frames.append(augment_pool)

    # regime_3 -- natural test signals, stratified by SQI tier at eval time.
    natural = labels[labels.split == "test"].assign(
        corruption_type=None, snr_db=-1,
        clean_signal_kind="raw_lead2", corrupted_signal_kind=None,
        regime="regime_3", row_role="natural", is_anchor=False,
    )
    frames.append(natural)

    df = pd.concat(frames, ignore_index=True)
    df["snr_db"] = df["snr_db"].astype("int32")
    for col in ("corruption_type", "corrupted_signal_kind"):
        df[col] = df[col].astype("string")
    df = df.sort_values(["regime", "row_role", "study_id", "corruption_type", "snr_db"],
                        kind="mergesort").reset_index(drop=True)

    counts = bc.write_task_split_parquets(df, TASK, schema=SCHEMA)
    log.info("wrote splits: %s", counts)

    # --- validation (§9.2) ---------------------------------------------------
    grid = corrupt_rows.groupby(["corruption_type", "snr_db"]).size()
    anchor_sqi = anchor_labels.sqi_tier.value_counts().to_dict()
    stats = {
        "n_rows_total": int(len(df)),
        "splits_total": counts,
        "rows_per_regime": df.regime.value_counts().to_dict(),
        "rows_per_row_role": df.row_role.value_counts().to_dict(),
        "n_anchors_in_corrupted_file": int(anchors.study_id.nunique()),
        "n_anchors_with_labels": int(len(anchor_labels)),
        "anchor_sqi_tier_mix": anchor_sqi,
        "corruption_types": sorted(corrupt_rows.corruption_type.dropna().unique().tolist()),
        "snr_levels_db": sorted(int(s) for s in corrupt_rows.snr_db.unique()),
        "grid_cells": int(len(grid)),
        "grid_min_rows": int(grid.min()),
        "grid_max_rows": int(grid.max()),
        "anchor_label_mix": mt.label_stats(anchor_labels),
        "regime_2_augmentation_policy": recipes["regimes"]["regime_2"]["augmentation_policy"],
        "spec_anchor_pool_note": (
            "§4.B.2.2 describes the anchors as sqi_tier == 'high'. Phase 1 Stage 8 applied "
            f"no SQI filter; the measured mix is {anchor_sqi}. The corrupted set is frozen "
            "and Phase 2 never regenerates it (§9.3), so the spec text is what must change."
        ),
    }
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str))

    expected_families = set(recipes["families"])
    if set(stats["corruption_types"]) != expected_families:
        raise RuntimeError(
            f"corruption families {stats['corruption_types']} do not match the locked recipe "
            f"{sorted(expected_families)}"
        )
    if stats["grid_cells"] != len(stats["corruption_types"]) * len(stats["snr_levels_db"]):
        raise RuntimeError(f"the corruption grid is not complete: {stats['grid_cells']} cells")
    if int(corrupt_rows.split.nunique() if "split" in corrupt_rows else 0) > 1:
        raise RuntimeError("corrupted anchors span more than one split")

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2, default=str), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# B2 -- noise-robustness curriculum

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.B.2, §7.3 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/08_build_B2_noise_robustness.py`.

**No corruption is generated in Phase 2.** Corrupted signals are read from
`data/processed/signals_corrupted.parquet`, frozen by Phase 1 Stage 8 (§9.3).
Resolve them with
`read_modality(study_id, "signal_corrupted", corruption_type=..., snr_db=...)`.

## Rows by regime

| `regime` | `row_role` | what it is |
| --- | --- | --- |
| `regime_1` | `corrupted` | the frozen corrupted test grid — 8 families x 5 SNRs per anchor |
| `regime_1` | `clean_reference` | each anchor's clean signal, the paired baseline the drop is measured from |
| `regime_2` | `augment_on_the_fly` | B1 train/val rows, corrupted at load time with a **different RNG stream** |
| `regime_2` | `corrupted` | the same frozen test grid, evaluated by the noise-augmented model |
| `regime_3` | `natural` | test-split natural signals, sliced by `sqi_tier` |

`snr_db == -1` marks a row that carries no corruption (clean reference, natural,
or augment-at-load-time).

Regimes 1 and 2 share the identical test grid on purpose: §4.B.2.8's headline
comparison is regime_1 vs regime_2 **on the same rows**, so the difference is
the model and nothing else.

## Labels

Each corrupted variant inherits its anchor's clean B1 labels unchanged
(§4.B.2.3). They come from `_dataset_lib/measurement_task.py` — the same module
A2 and B1 use — so an anchor and its variants cannot disagree.

## The anchor pool is SQI-representative, not high-SQI

§4.B.2.2 says the anchors are test-split ECGs with `sqi_tier == 'high'`. Phase 1
Stage 8 applied no SQI filter: it took the test-split `raw_lead2` manifest rows
in `(study_id, subject_id)` order and truncated to the first 2,000. The measured
mix is in the statistics below. The corrupted set is frozen and Phase 2 never
regenerates it, so **the spec text is what must change**, and the paper must
describe these anchors accurately. Arguably it is the better design — a
high-SQI-only anchor set would overstate robustness — but it has to be stated.

## Forbidden inputs

`raw_12lead`, `preprocessed_12lead`, every image kind, `report_text`,
`machine_measurements`, `structured_features` (§4.B.2.4).

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
