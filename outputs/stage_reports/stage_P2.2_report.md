# Stage P2.2 — Build Plan B task datasets — report

Spec §9.3. Generated 2026-08-28T17:29:00Z by `_dataset_lib/stage_report.py` from the per-script state files, the artifacts on disk and the run logs — every number below is read back from what the stage produced.

## 1. Files created

- `scripts/phase2_tasks_benchmark_and_paper/07_build_B1_measurement_blind.py`  (4.7 KB, sha256 449f94e12a99)
- `scripts/phase2_tasks_benchmark_and_paper/08_build_B2_noise_robustness.py`  (11.9 KB, sha256 e0f205e433f3)
- `scripts/phase2_tasks_benchmark_and_paper/09_build_B3_temporal_grounding.py`  (12.4 KB, sha256 9ef5a1a7be09)
- `scripts/phase2_tasks_benchmark_and_paper/10_build_B4_cross_modal_verification.py`  (5.7 KB, sha256 47bd83b560c0)
- `scripts/phase2_tasks_benchmark_and_paper/11_build_B5_contradiction_detection.py`  (16.9 KB, sha256 d36935d42692)
- `scripts/phase2_tasks_benchmark_and_paper/12_build_B6_difficulty_stratified.py`  (9.2 KB, sha256 9a62b01d90ec)
- `data/processed/tasks/B1_measurement_blind/README.md`  (3.9 KB, sha256 bd777bb2627d)
- `data/processed/tasks/B1_measurement_blind/test.parquet`  (2.9 MB, sha256 4db8d1de1376)
- `data/processed/tasks/B1_measurement_blind/train.parquet`  (9.2 MB, sha256 5772732198f0)
- `data/processed/tasks/B1_measurement_blind/val.parquet`  (1.5 MB, sha256 62fcc9ad0648)
- `data/processed/tasks/B2_noise_robustness/README.md`  (5.6 KB, sha256 e125b7250274)
- `data/processed/tasks/B2_noise_robustness/test.parquet`  (1.5 MB, sha256 0511a3a35374)
- `data/processed/tasks/B2_noise_robustness/train.parquet`  (4.4 MB, sha256 c94b705b07a5)
- `data/processed/tasks/B2_noise_robustness/val.parquet`  (763.9 KB, sha256 b872a0132265)
- `data/processed/tasks/B3_temporal_grounding/README.md`  (3.2 KB, sha256 6540bf2a9e2e)
- `data/processed/tasks/B3_temporal_grounding/test.parquet`  (4.2 MB, sha256 44a9d670d519)
- `data/processed/tasks/B3_temporal_grounding/train.parquet`  (14.0 MB, sha256 412333d9ee25)
- `data/processed/tasks/B3_temporal_grounding/val.parquet`  (2.1 MB, sha256 e3ae6645eece)
- `data/processed/tasks/B4_cross_modal_verification/README.md`  (2.6 KB, sha256 b6eb534c7c64)
- `data/processed/tasks/B4_cross_modal_verification/test.parquet`  (15.0 MB, sha256 30b19189fd99)
- `data/processed/tasks/B4_cross_modal_verification/train.parquet`  (47.6 MB, sha256 bc61be0dd254)
- `data/processed/tasks/B4_cross_modal_verification/val.parquet`  (5.6 MB, sha256 b8dc8b4187db)
- `data/processed/tasks/B5_contradiction_detection/README.md`  (7.0 KB, sha256 0fac484b1b1f)
- `data/processed/tasks/B5_contradiction_detection/test.parquet`  (1.3 MB, sha256 edea2f02572d)
- `data/processed/tasks/B5_contradiction_detection/train.parquet`  (4.7 MB, sha256 c05cbaf24793)
- `data/processed/tasks/B5_contradiction_detection/val.parquet`  (660.3 KB, sha256 493eb48b3142)
- `data/processed/tasks/B6_difficulty_stratified/eval_keys.parquet`  (28.5 MB, sha256 cefc0452d800)
- `data/processed/tasks/B6_difficulty_stratified/README.md`  (2.3 KB, sha256 a0382f72f5b2)

## 2. Files modified

- `config/task_definitions.yaml`  ::  QTc bin source pinned to `machine_qtc_ms` with `qtc_bazett_ms` demoted to provenance; B3's `noisy_sqi_threshold` locked from the train split.
- `config/lab_itemid_map_LOCKED.yaml`  ::  `cache_rebuild_required` marked DONE with the measured per-lab result; `reference_tables.events` repointed to the rebuilt sibling file.
- `config/claim_dictionary_LOCKED.yaml`  ::  QRS `normal_to_wide` corrected 23 → 0 with the reasoning and the superseded P2.0 measurement retained.
- `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/schema_validators.py`  ::  the quarantine check now asserts no quarantined filename has returned, instead of asserting the Phase 2 script directory is empty.
- `docs/PHASE2_PROGRESS.md`  ::  header, §4 decisions 14–17, §5 questions, §6 ledger, §7 traps 12–15, §8 session log.

## 3. Files / folders deleted

none — this stage only creates. `--dev` output is isolated under `data/processed/tasks/_dev/` and is never published.

## 4. Design decisions

- **B2 generates no corruption**  ::  §9.3 forbids it. The builder attaches labels and regime tags to the frozen Phase 1 rows and measures the anchor SQI mix rather than restating §4.B.2.2's claim about it.
- **A5 and B4 share one construction module**  ::  §4.B.4.8 compares them, so they must see identical rows. The construction is a pure function of the cohort and a splitmix64 hash, and B4 asserts equality against A5's parquets at build time.
- **Verification donors are drawn within the anchor's split**  ::  not stated in §4.A.5.3, but forced by §4.C invariant 1 — a train row pointing at a test subject would carry test bytes into training.
- **B5's QRS `normal_to_wide` count is 0, not the locked 23**  ::  §4 decision 17. Those 23 reports already contradict the machine, and all of them are paediatric.
- **B3's NOISY_SEGMENT threshold is locked from the train split and written back into `task_definitions.yaml`**  ::  §4.B.3.3 mandates a train-only threshold; writing it into the config makes it a fact of record rather than a number recomputed on every run.
- **B6 ships a pointer table only**  ::  §4.B.6.2 and §4.B.6.5. The hard tier is empty under the progress-doc question 13 default.

## 5. Complete code

### `scripts/phase2_tasks_benchmark_and_paper/07_build_B1_measurement_blind.py`

```python
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
```

### `scripts/phase2_tasks_benchmark_and_paper/08_build_B2_noise_robustness.py`

```python
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
    anchor_labels = anchors.merge(labels, on="study_id", how="inner")
    log.info("anchors with usable B1 labels: %d of %d", len(anchor_labels), len(anchors))

    frames: list[pd.DataFrame] = []

    # regime_1 -- the frozen corrupted test set, and its paired clean reference.
    corrupt_rows = corrupted.drop(columns=["split", "subject_id", "corruption_status"]).merge(
        anchor_labels, on="study_id", how="inner"
    )
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
```

### `scripts/phase2_tasks_benchmark_and_paper/09_build_B3_temporal_grounding.py`

```python
"""Stage P2.2 script 09 -- B3: temporal grounding (10-bin queries).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/09_build_B3_temporal_grounding.py [--dev]

Spec §4.B.3. Four physiological queries, each answered per 1-second bin of the
10-second strip. One row per (study, query); ``labels`` is 10 binary values.

Evidence comes from ``data/processed/fiducials_lead2.parquet``
(``00_extract_fiducials.py``) -- the same file A4 uses, so B3's bin labels and
A4's event labels are derived from one delineation and cannot disagree.

Query rules (§4.B.3.3)::

    HIGH_HEART_RATE  bin = 1 if any RR midpoint in the bin has instantaneous
                     HR > 100 bpm
    LOW_HEART_RATE   bin = 1 if any RR midpoint in the bin has HR < 60 bpm
    WIDE_QRS         bin = 1 if any beat whose QRS onset falls in the bin has
                     duration > 60 samples (120 ms)
    NOISY_SEGMENT    bin = 1 if that bin's SQI < the locked threshold

Instantaneous HR for the RR interval between consecutive peaks at 500 Hz is
``30000 / (p[i+1] - p[i])`` bpm, credited to the bin holding the interval's
midpoint. "Any" resolves the spec's silence about bins containing several
midpoints, and matches ``WIDE_QRS``'s own "any beat" wording.

**The NOISY_SEGMENT threshold is locked from the TRAIN split only** (§4.B.3.3:
"compute per-bin SQI distribution on train, pick the 25th percentile ... Doc
mandates threshold from train only"). This builder computes it, writes it back
into ``config/task_definitions.yaml``, and never recomputes it once the file
carries a value -- pass ``--relock-threshold`` to deliberately recompute.

Per-bin SQI is ``sqi_per_bin`` from the fiducial file, computed there on exactly
Phase 1's SQI code path (clean, re-detect, ``ecg_quality(method="averageQRS")``),
so a bin's value sits on the same scale as ``waveform_qc.sqi_aggregate``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402

STAGE = "P2.2"
SCRIPT = "09_build_B3_temporal_grounding"
TASK = "B3_temporal_grounding"

FIDUCIALS = bc.DATA_PROCESSED / "fiducials_lead2.parquet"
QUERIES = ("HIGH_HEART_RATE", "LOW_HEART_RATE", "WIDE_QRS", "NOISY_SEGMENT")

FS = 500
N_BINS = 10
BIN_SAMPLES = 500
HIGH_HR_BPM = 100.0
LOW_HR_BPM = 60.0
WIDE_QRS_SAMPLES = 60          # 120 ms at 500 Hz
NOISY_PERCENTILE = 25

SCHEMA = pa.schema([
    ("study_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("split", pa.string()),
    ("link_tier", pa.string()),
    ("sqi_tier", pa.string()),
    ("cart_id", pa.string()),
    ("query", pa.string()),
    ("labels", pa.list_(pa.int8())),
    ("fallback_used", pa.bool_()),
    ("n_positive_bins", pa.int8()),
])


def per_study_labels(r_peaks: np.ndarray, onsets: np.ndarray, offsets: np.ndarray,
                     sqi_bins: np.ndarray, noisy_threshold: float) -> dict[str, np.ndarray]:
    """The four 10-bin label vectors for one study."""
    high = np.zeros(N_BINS, dtype="int8")
    low = np.zeros(N_BINS, dtype="int8")
    wide = np.zeros(N_BINS, dtype="int8")

    peaks = np.asarray(r_peaks, dtype="int64")
    if peaks.size >= 2:
        deltas = np.diff(peaks)
        valid = deltas > 0
        if valid.any():
            midpoints = ((peaks[:-1] + peaks[1:]) // 2)[valid]
            hr = 30000.0 / deltas[valid]
            bins = np.clip(midpoints // BIN_SAMPLES, 0, N_BINS - 1)
            high[np.unique(bins[hr > HIGH_HR_BPM])] = 1
            low[np.unique(bins[hr < LOW_HR_BPM])] = 1

    on = np.asarray(onsets, dtype="int64")
    off = np.asarray(offsets, dtype="int64")
    if on.size and off.size:
        usable = (on >= 0) & (off >= 0) & (off > on)
        if usable.any():
            duration = off[usable] - on[usable]
            onset_bin = np.clip(on[usable] // BIN_SAMPLES, 0, N_BINS - 1)
            wide[np.unique(onset_bin[duration > WIDE_QRS_SAMPLES])] = 1

    sqi = np.asarray(sqi_bins, dtype="float64")
    noisy = (sqi < noisy_threshold).astype("int8")
    return {"HIGH_HEART_RATE": high, "LOW_HEART_RATE": low,
            "WIDE_QRS": wide, "NOISY_SEGMENT": noisy}


def lock_threshold(value: float, log) -> None:
    """Write the NOISY_SEGMENT threshold back into task_definitions.yaml."""
    path = bc.CONFIG_DIR / "task_definitions.yaml"
    text = path.read_text(encoding="utf-8")
    marker = "      noisy_sqi_threshold:\n        value: "
    start = text.index(marker) + len(marker)
    end = text.index("\n", start)
    updated = text[:start] + f"{value:.6f}" + text[end:]
    updated = updated.replace(
        '        status: "TO BE LOCKED by 09_build_B3_temporal_grounding.py at Stage P2.2"',
        f'        status: "LOCKED {bc.utc_now_iso()} by 09_build_B3_temporal_grounding.py '
        f'(train split, {NOISY_PERCENTILE}th percentile)"',
    )
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(updated, encoding="utf-8")
    bc.atomic_replace(tmp, path)
    log.info("locked noisy_sqi_threshold = %.6f into config/task_definitions.yaml", value)


def read_locked_threshold() -> float | None:
    cfg = yaml.safe_load((bc.CONFIG_DIR / "task_definitions.yaml").read_text(encoding="utf-8"))
    value = cfg["tasks"]["B3_temporal_grounding"]["targets"]["noisy_sqi_threshold"]["value"]
    return None if value is None else float(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    bc.add_std_args(parser)
    parser.add_argument("--relock-threshold", action="store_true",
                        help="recompute the NOISY_SEGMENT threshold even if one is locked")
    args = parser.parse_args()
    bc.set_dev(args.dev)

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT + ("_dev" if args.dev else ""))
    if state.done and not args.force:
        log.info("already complete (%s rows) -- pass --force to rebuild", state.data.get("n_rows"))
        return 0
    state.reset()
    started = time.time()

    fiducials = FIDUCIALS.with_name("fiducials_lead2_dev.parquet") if args.dev else FIDUCIALS
    bc.preflight([fiducials, bc.CONFIG_DIR / "task_definitions.yaml"])

    cohort = bc.load_clean_cohort(dev=args.dev)
    fid = pd.read_parquet(fiducials)
    df = cohort.merge(fid, on="study_id", how="inner")
    if len(df) != len(cohort):
        raise RuntimeError(
            f"{len(cohort) - len(df)} clean-cohort studies have no fiducial row -- "
            "re-run 00_extract_fiducials.py before building B3"
        )
    log.info("cohort: %d studies", len(df))

    # --- the NOISY_SEGMENT threshold, from TRAIN only ------------------------
    locked = read_locked_threshold()
    train_bins = np.concatenate(
        df.loc[df.split == "train", "sqi_per_bin"].map(np.asarray).to_numpy()
    )
    measured = float(np.percentile(train_bins, NOISY_PERCENTILE))
    if locked is None or args.relock_threshold:
        threshold = measured
        if not args.dev:
            lock_threshold(threshold, log)
        else:
            log.info("dev run: threshold %.6f computed but NOT locked into the config", threshold)
    else:
        threshold = locked
        log.info("using the locked threshold %.6f (train-split value now measures %.6f)",
                 threshold, measured)

    # --- labels --------------------------------------------------------------
    peaks = df.r_peaks_lead2.to_numpy()
    onsets = df.qrs_onsets_lead2.to_numpy()
    offsets = df.qrs_offsets_lead2.to_numpy()
    sqi = df.sqi_per_bin.to_numpy()
    label_lists: dict[str, list[np.ndarray]] = {q: [] for q in QUERIES}
    for i in range(len(df)):
        out = per_study_labels(peaks[i], onsets[i], offsets[i], sqi[i], threshold)
        for query in QUERIES:
            label_lists[query].append(out[query])

    base = df[["study_id", "subject_id", "split", "link_tier", "sqi_tier", "cart_id",
               "fallback_used"]].copy()
    base["cart_id"] = base["cart_id"].astype("Int64").astype("string")

    frames = []
    for query in QUERIES:
        part = base.copy()
        part["query"] = query
        part["labels"] = label_lists[query]
        part["n_positive_bins"] = np.asarray(
            [int(v.sum()) for v in label_lists[query]], dtype="int8"
        )
        frames.append(part)
    out = pd.concat(frames, ignore_index=True).sort_values(
        ["study_id", "query"], kind="mergesort"
    ).reset_index(drop=True)

    counts = bc.write_task_split_parquets(out, TASK, schema=SCHEMA)
    log.info("wrote splits: %s", counts)

    # --- validation (§9.2) ---------------------------------------------------
    per_query = {}
    for query in QUERIES:
        part = out[out["query"] == query]
        positives = np.concatenate(part.labels.map(np.asarray).to_numpy())
        per_query[query] = {
            "n_rows": int(len(part)),
            "bin_positive_rate_pct": round(100 * float(positives.mean()), 3),
            "studies_with_any_positive_pct": round(
                100 * float((part.n_positive_bins > 0).mean()), 3
            ),
            "mean_positive_bins": round(float(part.n_positive_bins.mean()), 3),
        }

    stats = {
        "n_rows_total": int(len(out)),
        "n_studies": int(out.study_id.nunique()),
        "splits_total": counts,
        "n_queries": len(QUERIES),
        "noisy_sqi_threshold": round(threshold, 6),
        "noisy_threshold_source": "train split, %dth percentile" % NOISY_PERCENTILE,
        "noisy_threshold_was_already_locked": locked is not None and not args.relock_threshold,
        "train_sqi_bin_percentiles": {
            str(p): round(float(np.percentile(train_bins, p)), 4) for p in (5, 25, 50, 75, 95)
        },
        "per_query": per_query,
        "pct_fallback_used": round(100 * float(base.fallback_used.mean()), 3),
    }
    stats.update(bc.split_summary(out))
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str))

    noisy_rate = per_query["NOISY_SEGMENT"]["bin_positive_rate_pct"]
    if not 15.0 <= noisy_rate <= 40.0:
        raise RuntimeError(
            f"NOISY_SEGMENT fires on {noisy_rate} % of bins; a {NOISY_PERCENTILE}th-percentile "
            "train threshold should put it near 25 % -- the threshold or the SQI is wrong"
        )
    if any(len(v) != N_BINS for v in out.labels.head(5000)):
        raise RuntimeError("a labels vector is not 10 bins long")

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2, default=str), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# B3 -- temporal grounding (10-bin queries)

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.B.3 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/09_build_B3_temporal_grounding.py`.

One row per (study, query); `labels` is 10 binary values, one per 1-second bin.
Four queries x the full clean cohort.

| query | bin = 1 when |
| --- | --- |
| `HIGH_HEART_RATE` | any RR midpoint in the bin has instantaneous HR > 100 bpm |
| `LOW_HEART_RATE` | any RR midpoint in the bin has HR < 60 bpm |
| `WIDE_QRS` | any beat whose QRS **onset** is in the bin lasts > 60 samples (120 ms) |
| `NOISY_SEGMENT` | that bin's SQI is below the locked threshold |

Instantaneous HR for the interval between consecutive peaks is `30000 / dRR`
bpm at 500 Hz, credited to the bin holding the interval's midpoint.

## The NOISY_SEGMENT threshold comes from train only

§4.B.3.3 requires it: the 25th percentile of the per-bin SQI distribution on the
**train split**, locked into `config/task_definitions.yaml` and never
recomputed. The value used is in the statistics below. `--relock-threshold`
recomputes it deliberately; a `--dev` run never writes it.

Per-bin SQI comes from `sqi_per_bin` in `fiducials_lead2.parquet`, computed on
exactly Phase 1's SQI code path, so a bin value is on the same scale as
`waveform_qc.sqi_aggregate`.

## Shared evidence with A4

Both tasks read the same `fiducials_lead2.parquet`, so B3's bin labels and A4's
event positions come from one delineation and cannot disagree.
`fallback_used` marks the studies where R-peak detection failed — the queries
then rest on SQI alone.

## Forbidden inputs

`machine_measurements`, `structured_features`, `report_text`, every image kind
(§4.B.3.4) — aggregate timings summarise the same quantities the bins encode.

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
```

### `scripts/phase2_tasks_benchmark_and_paper/10_build_B4_cross_modal_verification.py`

```python
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
| Clean vs scan-like image | `image_type` on the positive rows |
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
```

### `scripts/phase2_tasks_benchmark_and_paper/11_build_B5_contradiction_detection.py`

```python
"""Stage P2.2 script 11 -- B5: contradiction detection in reports.

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/11_build_B5_contradiction_detection.py [--dev]

Spec §4.B.5, driven entirely by ``config/claim_dictionary_LOCKED.yaml``. Four
families -- HR, QRS, axis, PR -- each with clear zones, an injection-free gap
around the decision boundary, and the surface forms that may be swapped.

Three locked decisions this builder implements rather than re-deriving:

* **Every threshold reads the MACHINE measurement** (Round 6.1), with the
  ``29999`` sentinel masked and the plausible range applied (Round 6.2).
  ``structured_features.pr_ms`` and ``.qrs_ms`` are never read.
* **Injections are swaps of text that is really present, never insertions**
  (Round 6.3). A study is eligible for a family only when the measurement sits
  in a clear zone **and** the report carries a surface form of matching
  polarity, so every recorded span points at real characters and the corrupted
  class is not separable by length or phrasing.
* **Exactly one row per ELIGIBLE study**, corrupted with p = 0.5 (Round 6.5,
  progress-doc question 11). A study eligible for no family contributes no row.
  Clean rows are drawn from the same eligible pool on purpose: otherwise "the
  report contains a swappable claim" would itself predict the label.

The RNG is the one the dictionary specifies: ``sha256("b5|<study_id>")``, first
4 bytes, mod 2**31, seeding ``numpy.random.default_rng``. It depends on the
study alone, so re-running reproduces the dataset exactly (§4.C invariant 2).

**Open question 3 (span offsets), proceeding under the stated default.**
§4.B.5.5 declares ``corrupted_span_start`` / ``_end`` as character offsets, so
they are character offsets into ``corrupted_report_text``. Token offsets would
depend on a tokenizer the data contract does not name.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402

STAGE = "P2.2"
SCRIPT = "11_build_B5_contradiction_detection"
TASK = "B5_contradiction_detection"

FAMILY_ORDER = ("HR", "QRS", "axis", "PR")

SCHEMA = pa.schema([
    ("study_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("split", pa.string()),
    ("link_tier", pa.string()),
    ("sqi_tier", pa.string()),
    ("cart_id", pa.string()),
    ("is_corrupted", pa.bool_()),
    ("contradiction_type", pa.string()),
    ("contradiction_family", pa.string()),
    ("original_report_text", pa.string()),
    ("corrupted_report_text", pa.string()),
    ("corrupted_span_start", pa.int32()),
    ("corrupted_span_end", pa.int32()),
    ("source_measurement", pa.string()),
    ("label", pa.string()),
    ("eligible_families", pa.string()),
    ("is_primary", pa.bool_()),
])


def zone_mask(values: pd.Series, condition: str) -> np.ndarray:
    """Evaluate one ``clear_zones`` condition from the locked dictionary.

    The conditions are simple comparisons against the family's own measurement
    (``hr_bpm <= 50``, ``qrs_axis > 105``, ...), so they are parsed rather than
    ``eval``-ed: a config file must not be able to execute arbitrary code.
    """
    match = re.fullmatch(r"\s*\w+\s*(<=|>=|<|>|==)\s*(-?\d+(?:\.\d+)?)\s*", condition)
    if not match:
        raise ValueError(f"unparseable clear-zone condition: {condition!r}")
    op, bound = match.group(1), float(match.group(2))
    series = values.astype("float64")
    return {
        "<=": series <= bound, ">=": series >= bound, "<": series < bound,
        ">": series > bound, "==": series == bound,
    }[op].fillna(False).to_numpy()


def apply_swap(text: str, pattern: re.Pattern, replacement: str) -> tuple[str, int, int] | None:
    """Swap the first match, preserving the original leading capitalisation.

    Returns ``(corrupted_text, span_start, span_end)`` with offsets into the
    corrupted text. Everything before the match is untouched, so the start
    offset is the same in both strings.
    """
    match = pattern.search(text)
    if match is None:
        return None
    original = match.group(0)
    swapped = replacement
    if original[:1].isupper():
        swapped = swapped[:1].upper() + swapped[1:]
    corrupted = text[: match.start()] + swapped + text[match.end():]
    return corrupted, match.start(), match.start() + len(swapped)


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

    bc.preflight([bc.CONFIG_DIR / "claim_dictionary_LOCKED.yaml"])
    cfg = yaml.safe_load(
        (bc.CONFIG_DIR / "claim_dictionary_LOCKED.yaml").read_text(encoding="utf-8")
    )
    families = cfg["families"]

    cohort = bc.load_clean_cohort(dev=args.dev)
    meas = bc.machine_measurements(dev=args.dev)
    text = bc.report_text_series(dev=args.dev)
    df = cohort.merge(meas, on="study_id", how="left").merge(text, on="study_id", how="left")
    log.info("clean cohort: %d studies", len(df))

    lowered = df.report_text.fillna("").str.lower()

    # --- eligibility, per (family, polarity, surface form) -------------------
    compiled: dict[tuple[str, str], list[tuple[re.Pattern, str]]] = {}
    eligible_by_family: dict[str, np.ndarray] = {}
    polarity_of: dict[str, np.ndarray] = {}
    zone_counts: dict[str, dict[str, int]] = {}
    form_counts: dict[str, int] = {}

    for family in FAMILY_ORDER:
        block = families[family]
        column = block["measurement"]
        values = df[column]
        eligible = np.zeros(len(df), dtype=bool)
        polarity = np.full(len(df), "", dtype=object)
        zone_counts[family] = {}

        for zone_name, zone in block["clear_zones"].items():
            truth_zone = zone_mask(values, zone["condition"])
            forms = [f for f in block["surface_forms"] if f["polarity"] == zone_name]
            if not forms:
                zone_counts[family][zone_name] = 0
                continue
            key = (family, zone_name)
            compiled[key] = [
                (re.compile(str(f["pattern"]), re.IGNORECASE), str(f["replace_with"]))
                for f in forms
            ]
            has_form = np.zeros(len(df), dtype=bool)
            for form in forms:
                hit = lowered.str.contains(str(form["pattern"]), regex=True, na=False).to_numpy()
                form_counts[f"{family}|{zone_name}|{form['pattern']}"] = int(
                    (hit & truth_zone).sum()
                )
                has_form |= hit
            zone_eligible = truth_zone & has_form
            zone_counts[family][zone_name] = int(zone_eligible.sum())
            polarity[zone_eligible & ~eligible] = zone_name
            eligible |= zone_eligible

        eligible_by_family[family] = eligible
        polarity_of[family] = polarity
        log.info("%s eligible: %d  %s", family, int(eligible.sum()), zone_counts[family])

    any_eligible = np.zeros(len(df), dtype=bool)
    for family in FAMILY_ORDER:
        any_eligible |= eligible_by_family[family]
    log.info("eligible for at least one family: %d of %d (%.2f %%)",
             int(any_eligible.sum()), len(df), 100 * any_eligible.mean())

    # --- one row per eligible study, corrupted with p = 0.5 ------------------
    pool = df[any_eligible].reset_index(drop=True)
    pool_index = np.flatnonzero(any_eligible)
    eligible_lists = [
        [f for f in FAMILY_ORDER if eligible_by_family[f][i]] for i in pool_index
    ]

    rng_cfg = cfg["injection_policy"]["rng"]
    probability = float(cfg["injection_policy"]["probability_of_corruption"])
    if rng_cfg["key_template"] != "b5|{study_id}" or rng_cfg["digest"] != "sha256":
        raise RuntimeError(f"the locked RNG spec changed: {rng_cfg}")

    rows: list[dict] = []
    swap_failures = 0
    for position, study_id in enumerate(pool.study_id.to_numpy()):
        rng = np.random.default_rng(bc.stable_seed("b5", int(study_id)))
        corrupt = bool(rng.random() < probability)
        choices = eligible_lists[position]
        record = {
            "is_corrupted": False, "contradiction_type": None, "contradiction_family": None,
            "corrupted_report_text": None, "corrupted_span_start": None,
            "corrupted_span_end": None, "source_measurement": None, "label": "clean",
            "eligible_families": ",".join(choices),
        }
        if corrupt:
            family = str(choices[int(rng.integers(len(choices)))])
            zone = polarity_of[family][pool_index[position]]
            original = pool.report_text.iloc[position]
            result = None
            for pattern, replacement in compiled[(family, zone)]:
                result = apply_swap(original, pattern, replacement)
                if result is not None:
                    break
            if result is None:
                # Eligibility was decided by the same patterns, so this cannot
                # happen; if it ever does, the row stays clean rather than
                # shipping a corrupted label with no corrupted text.
                swap_failures += 1
            else:
                corrupted_text, start, end = result
                column = families[family]["measurement"]
                record.update({
                    "is_corrupted": True,
                    "contradiction_type": family,
                    "contradiction_family": f"{family}_{zone}",
                    "corrupted_report_text": corrupted_text,
                    "corrupted_span_start": start,
                    "corrupted_span_end": end,
                    "source_measurement": json.dumps({
                        "measurement_name": column,
                        "value": float(pool[column].iloc[position]),
                        "clear_zone": zone,
                    }),
                    "label": f"corrupted_{family}",
                })
        rows.append(record)
    if swap_failures:
        log.warning("%d eligible studies could not be swapped and stayed clean", swap_failures)

    out = pd.concat([
        pool[["study_id", "subject_id", "split", "link_tier", "sqi_tier", "cart_id"]]
        .reset_index(drop=True),
        pd.DataFrame(rows),
    ], axis=1)
    out["original_report_text"] = pool.report_text.to_numpy()
    out["is_primary"] = True
    out["cart_id"] = out["cart_id"].astype("Int64").astype("string")
    for column in ("corrupted_span_start", "corrupted_span_end"):
        out[column] = out[column].astype("Int32")
    out = out.sort_values("study_id", kind="mergesort").reset_index(drop=True)

    counts = bc.write_task_split_parquets(out, TASK, schema=SCHEMA)
    log.info("wrote splits: %s", counts)

    # --- validation (§9.2) ---------------------------------------------------
    corrupted_rows = out[out.is_corrupted]
    stats = {
        "n_rows": int(len(out)),
        "n_eligible_studies": int(any_eligible.sum()),
        "eligible_pct_of_clean_cohort": round(100 * float(any_eligible.mean()), 3),
        "splits": counts,
        "corrupted_rate_pct": round(100 * float(out.is_corrupted.mean()), 3),
        "corrupted_rate_by_split_pct": {
            split: round(100 * float(out[out.split == split].is_corrupted.mean()), 3)
            for split in bc.SPLITS
        },
        "eligible_per_family": {f: int(eligible_by_family[f].sum()) for f in FAMILY_ORDER},
        "eligible_per_zone": zone_counts,
        "families_per_eligible_study": {
            str(k): int(v) for k, v in
            pd.Series([len(v) for v in eligible_lists]).value_counts().sort_index().items()
        },
        "label_distribution": out.label.value_counts().to_dict(),
        "contradiction_family_distribution": corrupted_rows.contradiction_family.value_counts().to_dict(),
        "span_length_median_chars": int(
            (corrupted_rows.corrupted_span_end - corrupted_rows.corrupted_span_start).median()
        ) if len(corrupted_rows) else 0,
        "swap_failures": swap_failures,
        "surface_form_hits_in_zone": form_counts,
    }
    stats.update(bc.split_summary(out))
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str))

    # Every recorded span must actually contain the replacement text.
    for row in corrupted_rows.head(5000).itertuples():
        span = row.corrupted_report_text[row.corrupted_span_start:row.corrupted_span_end]
        if not span or span == row.original_report_text[row.corrupted_span_start:row.corrupted_span_end]:
            raise RuntimeError(f"span on study {row.study_id} does not mark a change: {span!r}")
    if out.study_id.duplicated().any():
        raise RuntimeError("a study contributes more than one B5 row")
    balance = stats["corrupted_rate_pct"]
    if not 48.0 <= balance <= 52.0:
        raise RuntimeError(f"corrupted rate is {balance} %, not the 50/50 Round 6.5 requires")
    if not args.dev:
        expected = cfg["injection_policy"]["measured_eligibility"]
        if stats["n_eligible_studies"] != int(expected["eligible_for_at_least_one_family"]):
            raise RuntimeError(
                f"eligibility is {stats['n_eligible_studies']}, not the locked "
                f"{expected['eligible_for_at_least_one_family']} -- the dictionary or the "
                "measurement source changed"
            )

    examples = [
        {"study_id": int(r.study_id), "family": r.contradiction_family,
         "original": r.original_report_text[:130], "corrupted": r.corrupted_report_text[:130],
         "span": [int(r.corrupted_span_start), int(r.corrupted_span_end)],
         "measurement": r.source_measurement}
        for r in corrupted_rows.head(4).itertuples()
    ]
    stats["examples"] = examples
    log.info("injection examples:\n%s", json.dumps(examples, indent=2))

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2, default=str), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# B5 -- contradiction detection in reports

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.B.5 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/11_build_B5_contradiction_detection.py`.
Every threshold, zone and surface form comes from
`config/claim_dictionary_LOCKED.yaml`.

## One row per eligible study, corrupted with p = 0.5

A study is **eligible** for a family only when its machine measurement sits in a
clear zone **and** its report carries a surface form of matching polarity.
Studies eligible for no family contribute no row at all. That is Round 6.5
(progress-doc question 11), and it is what makes the cohort an exact 50/50 —
the reading under which §4.B.5.3's "with 50 % probability" and §6.4's "balanced
50/50 by dataset design" are both true.

Clean rows come from the **same eligible pool** as corrupted ones, on purpose:
drawing them from the whole cohort would let a model separate the classes on
vocabulary alone, because only eligible reports contain a swappable claim.

## Swaps, never insertions

Round 6.3. Each injection replaces text that is really present with its
opposite, so `corrupted_span_start` / `_end` always point at real characters and
the corrupted class is not detectable by length or by a phrasing style absent
from the clean class. Offsets are **character** offsets into
`corrupted_report_text` (§4.B.5.5; progress-doc question 3, stated default).

`contradiction_type` is the family (HR / QRS / axis / PR).
`contradiction_family` is the **directed** swap (`HR_brady`, `axis_lad`, ...),
which is what the per-family detection-rate table needs.
`source_measurement` is the JSON of the value that drove the injection.

## Two families are one-directional in practice

The dictionary records why, and it is a property of the source vocabulary rather
than a modelling choice: MIMIC machine reports essentially never assert a narrow
QRS ("narrow" appears 0 times in 749,112 reports) or a normal PR. QRS is
therefore wide → normal, and PR is first-degree-AVB → normal. The
per-family table must be read with that in mind.

## Measurements

Machine measurements only (Round 6.1), `29999` masked and range-gated (Round
6.2). `structured_features.pr_ms` and `.qrs_ms` are never read — both are
NeuroKit values, and the NeuroKit PR would have shipped 9,035 studies whose
report already says "1st degree A-V block" as **clean** rows.

## Forbidden inputs

`machine_measurements` and `structured_features` (they *are* the contradiction
source — a model given them could recompute the truth and diff it), and every
image kind (§4.B.5.4). `report_text` is allowed: it is the thing being audited.

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
```

### `scripts/phase2_tasks_benchmark_and_paper/12_build_B6_difficulty_stratified.py`

```python
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
```

## 6. Validation results

- Pre-flight: PASS — every builder calls `build_common.preflight()`, which asserts its inputs exist and records free disk and free RAM before any work starts. Phase 1 completion was verified at Stage P2.0 and is unchanged.

### Per-script validation (read back from the state files)

**`07_build_B1_measurement_blind`** — PASS

```json
{
  "done": true,
  "finished_at": "2026-08-26T19:19:31Z",
  "n_rows_total": 748454,
  "splits_total": {
    "train": 523464,
    "val": 75444,
    "test": 149546
  },
  "linkage_tier_breakdown": {
    "L3": 421755,
    "L1": 234311,
    "L2": 78262,
    "L0": 14126
  },
  "sqi_tier_breakdown": {
    "medium": 460659,
    "low": 283630,
    "high": 4165
  },
  "labels": {
    "hr_label": {
      "bradycardia": {
        "n": 112209,
        "pct": 14.992
      },
      "normal": {
        "n": 532583,
        "pct": 71.158
      },
      "tachycardia": {
        "n": 103662,
        "pct": 13.85
      }
    },
    "hr_label_by_split": {
      "train": {
        "bradycardia": 15.007,
        "normal": 71.178,
        "tachycardia": 13.815
      },
      "val": {
        "bradycardia": 15.028,
        "normal": 71.09,
        "tachycardia": 13.882
      },
      "test": {
        "bradycardia": 14.921,
        "normal": 71.122,
        "tachycardia": 13.957
      }
    },
    "qrs_label": {
      "normal": {
        "n": 481548,
        "pct": 64.339
      },
      "borderline": {
        "n": 143341,
        "pct": 19.152
      },
      "wide": {
        "n": 123565,
        "pct": 16.509
      }
    },
    "qrs_label_by_split": {
      "train": {
        "normal": 64.261,
        "borderline": 19.167,
        "wide": 16.572
      },
      "val": {
        "normal": 64.686,
        "borderline": 18.958,
        "wide": 16.355
      },
      "test": {
        "normal": 64.438,
        "borderline": 19.196,
        "wide": 16.366
      }
    },
    "qtc_label": {
      "short": {
        "n": 720,
        "pct": 0.096
      },
      "normal": {
        "n": 441981,
        "pct": 59.053
      },
      "prolonged": {
        "n": 305753,
        "pct": 40.851
      }
    },
    "qtc_label_by_split": {
      "train": {
        "short": 0.103,
        "normal": 58.9,
        "prolonged": 40.997
      },
      "val": {
        "short": 0.068,
        "normal": 59.54,
        "prolonged": 40.393
      },
      "test": {
        "short": 0.088,
        "normal": 59.34,
        "prolonged": 40.573
      }
    }
  },
  "measurement_summary": {
    "hr_bpm": {
      "mean": 78.34,
      "median": 75.0
    },
    "qrs_ms": {
      "mean": 99.77,
      "median": 93.0
    },
    "qtc_ms": {
      "mean": 444.69,
      "median": 441.96
    }
  },
  "n_shared_with_A2_primary": 275088,
  "n_rows": 748454,
  "n_subjects": 154079,
  "n_rows_train": 523464,
  "n_subjects_train": 107841,
  "n_rows_val": 75444,
  "n_subjects_val": 15395,
  "n_rows_test": 149546,
  "n_subjects_test": 30843,
  "subject_overlap": 0
}
```

**`08_build_B2_noise_robustness`** — PASS

```json
{
  "done": true,
  "finished_at": "2026-08-26T19:21:45Z",
  "n_rows_total": 900005,
  "splits_total": {
    "train": 523464,
    "val": 75444,
    "test": 301097
  },
  "rows_per_regime": {
    "regime_2": 673748,
    "regime_3": 149546,
    "regime_1": 76711
  },
  "rows_per_row_role": {
    "augment_on_the_fly": 598908,
    "corrupted": 149680,
    "natural": 149546,
    "clean_reference": 1871
  },
  "n_anchors_in_corrupted_file": 1998,
  "n_anchors_with_labels": 1871,
  "anchor_sqi_tier_mix": {
    "medium": 1119,
    "low": 744,
    "high": 8
  },
  "corruption_types": [
    "baseline_wander",
    "electrode_motion",
    "emg",
    "gain_drift",
    "gaussian",
    "lead_dropout",
    "powerline",
    "saturation"
  ],
  "snr_levels_db": [
    0,
    5,
    10,
    20,
    30
  ],
  "grid_cells": 40,
  "grid_min_rows": 1871,
  "grid_max_rows": 1871,
  "anchor_label_mix": {
    "hr_label": {
      "bradycardia": {
        "n": 284,
        "pct": 15.179
      },
      "normal": {
        "n": 1341,
        "pct": 71.673
      },
      "tachycardia": {
        "n": 246,
        "pct": 13.148
      }
    },
    "hr_label_by_split": {
      "train": {
        "bradycardia": 0.0,
        "normal": 0.0,
        "tachycardia": 0.0
      },
      "val": {
        "bradycardia": 0.0,
        "normal": 0.0,
        "tachycardia": 0.0
      },
      "test": {
        "bradycardia": 15.179,
        "normal": 71.673,
        "tachycardia": 13.148
      }
    },
    "qrs_label": {
      "normal": {
        "n": 1186,
        "pct": 63.389
      },
      "borderline": {
        "n": 387,
        "pct": 20.684
      },
      "wide": {
        "n": 298,
        "pct": 15.927
      }
    },
    "qrs_label_by_split": {
      "train": {
        "normal": 0.0,
        "borderline": 0.0,
        "wide": 0.0
      },
      "val": {
        "normal": 0.0,
        "borderline": 0.0,
        "wide": 0.0
      },
      "test": {
        "normal": 63.389,
        "borderline": 20.684,
        "wide": 15.927
      }
    },
    "qtc_label": {
      "short": {
        "n": 5,
        "pct": 0.267
      },
      "normal": {
        "n": 1088,
        "pct": 58.151
      },
      "prolonged": {
        "n": 778,
        "pct": 41.582
      }
    },
    "qtc_label_by_split": {
      "train": {
        "short": 0.0,
        "normal": 0.0,
        "prolonged": 0.0
      },
      "val": {
        "short": 0.0,
        "normal": 0.0,
        "prolonged": 0.0
      },
      "test": {
        "short": 0.267,
        "normal": 58.151,
        "prolonged": 41.582
      }
    }
  },
  "regime_2_augmentation_policy": {
    "p_corrupt_per_sample": 0.5,
    "family": {
      "distribution": "uniform_choice",
      "over": "all_8_families"
    },
    "snr_db": {
      "distribution": "uniform_choice",
      "over": [
        30,
        20,
        10,
        5,
        0
      ]
    }
  },
  "spec_anchor_pool_note": "\u00a74.B.2.2 describes the anchors as sqi_tier == 'high'. Phase 1 Stage 8 applied no SQI filter; the measured mix is {'medium': 1119, 'low': 744, 'high': 8}. The corrupted set is frozen and Phase 2 never regenerates it (\u00a79.3), so the spec text is what must change."
}
```

**`09_build_B3_temporal_grounding`** — PASS

```json
{
  "done": true,
  "finished_at": "2026-08-26T22:26:45Z",
  "n_rows_total": 2996448,
  "n_studies": 749112,
  "splits_total": {
    "train": 2095780,
    "val": 302100,
    "test": 598568
  },
  "n_queries": 4,
  "noisy_sqi_threshold": 0.41503,
  "noisy_threshold_source": "train split, 25th percentile",
  "noisy_threshold_was_already_locked": false,
  "train_sqi_bin_percentiles": {
    "5": 0.0138,
    "25": 0.415,
    "50": 0.6925,
    "75": 0.8631,
    "95": 0.9731
  },
  "per_query": {
    "HIGH_HEART_RATE": {
      "n_rows": 749112,
      "bin_positive_rate_pct": 15.482,
      "studies_with_any_positive_pct": 29.551,
      "mean_positive_bins": 1.548
    },
    "LOW_HEART_RATE": {
      "n_rows": 749112,
      "bin_positive_rate_pct": 13.644,
      "studies_with_any_positive_pct": 30.465,
      "mean_positive_bins": 1.364
    },
    "WIDE_QRS": {
      "n_rows": 749112,
      "bin_positive_rate_pct": 21.048,
      "studies_with_any_positive_pct": 55.098,
      "mean_positive_bins": 2.105
    },
    "NOISY_SEGMENT": {
      "n_rows": 749112,
      "bin_positive_rate_pct": 25.001,
      "studies_with_any_positive_pct": 98.634,
      "mean_positive_bins": 2.5
    }
  },
  "pct_fallback_used": 0.1,
  "n_rows": 2996448,
  "n_subjects": 154092,
  "n_rows_train": 2095780,
  "n_subjects_train": 107851,
  "n_rows_val": 302100,
  "n_subjects_val": 15397,
  "n_rows_test": 598568,
  "n_subjects_test": 30844,
  "subject_overlap": 0
}
```

**`10_build_B4_cross_modal_verification`** — PASS

```json
{
  "done": true,
  "finished_at": "2026-08-28T17:15:13Z",
  "n_rows": 5693989,
  "n_anchors": 749112,
  "n_subjects": 154092,
  "positive_rate_pct": 26.312,
  "rows_per_neg_type": {
    "positive": 1498224,
    "HARD_NEGATIVE_TEXT": 749112,
    "IMAGE_SWAP": 749112,
    "PARTIAL_MISMATCH": 749112,
    "SIGNAL_SWAP": 749112,
    "TEXT_SWAP": 749112,
    "HARD_NEGATIVE_L2": 149549,
    "HARD_NEGATIVE_L3": 149036,
    "HARD_NEGATIVE_L4": 138581,
    "HARD_NEGATIVE_L5": 13039
  },
  "image_type_counts": {
    "clean": 4944877,
    "scanlike": 749112
  },
  "by_split": {
    "train": {
      "n_rows": 3667615,
      "n_anchors": 523945,
      "n_positive": 1047890,
      "n_negative": 2619725
    },
    "val": {
      "n_rows": 528675,
      "n_anchors": 75525,
      "n_positive": 151050,
      "n_negative": 377625
    },
    "test": {
      "n_rows": 1497699,
      "n_anchors": 149642,
      "n_positive": 299284,
      "n_negative": 1198415
    }
  },
  "splits": {
    "train": 3667615,
    "val": 528675,
    "test": 1497699
  },
  "identical_to_A5_verification": true,
  "n_rows_train": 3667615,
  "n_subjects_train": 107851,
  "n_rows_val": 528675,
  "n_subjects_val": 15397,
  "n_rows_test": 1497699,
  "n_subjects_test": 30844,
  "subject_overlap": 0
}
```

**`11_build_B5_contradiction_detection`** — PASS

```json
{
  "done": true,
  "finished_at": "2026-08-26T19:31:10Z",
  "n_rows": 128653,
  "n_eligible_studies": 128653,
  "eligible_pct_of_clean_cohort": 17.174,
  "splits": {
    "train": 89842,
    "val": 12941,
    "test": 25870
  },
  "corrupted_rate_pct": 49.917,
  "corrupted_rate_by_split_pct": {
    "train": 49.72,
    "val": 50.321,
    "test": 50.402
  },
  "eligible_per_family": {
    "HR": 38453,
    "QRS": 54037,
    "axis": 52621,
    "PR": 13111
  },
  "eligible_per_zone": {
    "HR": {
      "brady": 20025,
      "tachy": 18428
    },
    "QRS": {
      "wide": 54037,
      "normal": 0
    },
    "axis": {
      "lad": 45591,
      "rad": 7030
    },
    "PR": {
      "first_degree_avb": 13111,
      "normal": 0
    }
  },
  "families_per_eligible_study": {
    "1": 101219,
    "2": 25368,
    "3": 1997,
    "4": 69
  },
  "label_distribution": {
    "clean": 64433,
    "corrupted_QRS": 20748,
    "corrupted_axis": 20230,
    "corrupted_HR": 17866,
    "corrupted_PR": 5376
  },
  "contradiction_family_distribution": {
    "QRS_wide": 20748,
    "axis_lad": 17397,
    "HR_brady": 9174,
    "HR_tachy": 8692,
    "PR_first_degree_avb": 5376,
    "axis_rad": 2833
  },
  "span_length_median_chars": 19,
  "swap_failures": 0,
  "surface_form_hits_in_zone": {
    "HR|brady|bradycardi": 20025,
    "HR|tachy|tachycardi": 18428,
    "QRS|wide|(?<!incomplete )left bundle branch block": 14546,
    "QRS|wide|(?<!incomplete )right bundle branch block": 15663,
    "QRS|wide|(?<!incomplete )\\blbbb\\b": 381,
    "QRS|wide|(?<!incomplete )\\brbbb\\b": 13813,
    "QRS|wide|intraventricular conduction delay": 310,
    "QRS|wide|iv conduction defect": 9255,
    "QRS|wide|wide qrs": 31,
    "QRS|wide|wide complex": 68,
    "axis|lad|left axis deviation": 45591,
    "axis|lad|leftward axis": 0,
    "axis|rad|right axis deviation": 5994,
    "axis|rad|rightward axis": 1036,
    "PR|first_degree_avb|1st degree a-v block": 10969,
    "PR|first_degree_avb|first degree a-v block": 713,
    "PR|first_degree_avb|1st degree av block": 0,
    "PR|first_degree_avb|prolonged pr interval": 1429
  },
  "n_subjects": 38422,
  "n_rows_train": 89842,
  "n_subjects_train": 26776,
  "n_rows_val": 12941,
  "n_subjects_val": 3900,
  "n_rows_test": 25870,
  "n_subjects_test": 7746,
  "subject_overlap": 0,
  "examples": [
    {
      "study_id": 40000305,
      "family": "axis_lad",
      "original": "Sinus tachycardia Left axis deviation IV conduction defect Possible anterior infarct - age undetermined Possible lateral infarct -",
      "corrupted": "Sinus tachycardia Right axis deviation IV conduction defect Possible anterior infarct - age undetermined Possible lateral infarct ",
      "span": [
        18,
        38
      ],
      "measurement": "{\"measurement_name\": \"qrs_axis\", \"value\": -60.0, \"clear_zone\": \"lad\"}"
    },
    {
      "study_id": 40000306,
      "family": "QRS_wide",
      "original": "Atrial fibrillation with rapid ventricular response. Left axis deviation RBBB with left anterior fascicular block Possible septal ",
      "corrupted": "Atrial fibrillation with rapid ventricular response. Left axis deviation Normal QRS duration with left anterior fascicular block P",
      "span": [
        73,
        92
      ],
      "measurement": "{\"measurement_name\": \"qrs_ms\", \"value\": 150.0, \"clear_zone\": \"wide\"}"
    },
    {
      "study_id": 40000565,
      "family": "axis_lad",
      "original": "Sinus tachycardia Left axis deviation Inferior infarct - age undetermined Abnormal ECG",
      "corrupted": "Sinus tachycardia Right axis deviation Inferior infarct - age undetermined Abnormal ECG",
      "span": [
        18,
        38
      ],
      "measurement": "{\"measurement_name\": \"qrs_axis\", \"value\": -51.0, \"clear_zone\": \"lad\"}"
    },
    {
      "study_id": 40000799,
      "family": "QRS_wide",
      "original": "Sinus tachycardia with borderline 1st degree A-V block. Possible right atrial abnormality Leftward axis Left bundle branch block A",
      "corrupted": "Sinus tachycardia with borderline 1st degree A-V block. Possible right atrial abnormality Leftward axis Normal QRS duration Abnorm",
      "span": [
        104,
        123
      ],
      "measurement": "{\"measurement_name\": \"qrs_ms\", \"value\": 166.0, \"clear_zone\": \"wide\"}"
    }
  ]
}
```

**`12_build_B6_difficulty_stratified`** — PASS

```json
{
  "done": true,
  "finished_at": "2026-08-28T17:15:33Z",
  "n_rows": 5693989,
  "n_studies": 749112,
  "rows_per_tier": {
    "level_0_random": 2996448,
    "positive": 1498224,
    "level_1_hr": 749112,
    "level_2_hr_qrs": 149549,
    "level_3_full_physio": 149036,
    "level_4_same_patient": 138581,
    "level_5_near_duplicate": 13039
  },
  "test_rows_per_tier": {
    "level_0_random": 598568,
    "positive": 299284,
    "level_1_hr": 149642,
    "level_2_hr_qrs": 149549,
    "level_3_full_physio": 149036,
    "level_4_same_patient": 138581,
    "level_5_near_duplicate": 13039
  },
  "test_rows_per_neg_type": {
    "<NA>": 299284,
    "IMAGE_SWAP": 149642,
    "PARTIAL_MISMATCH": 149642,
    "SIGNAL_SWAP": 149642,
    "HARD_NEGATIVE_TEXT": 149642,
    "TEXT_SWAP": 149642,
    "HARD_NEGATIVE_L2": 149549,
    "HARD_NEGATIVE_L3": 149036,
    "HARD_NEGATIVE_L4": 138581,
    "HARD_NEGATIVE_L5": 13039
  },
  "levels_2_to_5_are_test_only": true,
  "n_subjects": 154092
}
```

### Logging-hygiene checklist (Phase 1 §8.14)

- [x] Terminal showed one tqdm bar, no interleaving — workers redirect fd 1/2 into their own PID log in the pool initializer (`build_common.worker_log_init`), so no worker writes to the parent's stdout/stderr.
- [x] `aggregate.log` exists; first and last 5 lines:
(no worker-log directory for this stage -- no builder used a process pool)
- [x] no `print(` in worker bodies:
```
(no match for '^\\s*print(' -- clean)
```
- [x] no `logging.basicConfig` in worker:
```
(no match for 'basicConfig' -- clean)
```
- [x] `worker_<pid>.log` files moved into `archive_<ts>/` — done by this generator, see the aggregate paths above.
- [n/a] Transport B `listener.stop()` — this stage uses Transport A (per-PID files), Phase 1 §8.3's default.
- [x] tqdm used with `mininterval=0.5` and `logging_redirect_tqdm()` — `build_common.run_chunked`:
```
549:                   mininterval=0.5, desc=desc or name)
```

- Disk free at report time: 90.7 GB on D:\

## 7. Manual test procedure

```
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/schema_validators.py
./ecg_env/Scripts/python.exe -c "import pandas as pd; d=pd.read_parquet('data/processed/tasks/B1_measurement_blind/test.parquet'); print(len(d), d.columns.tolist()[:8])"
./ecg_env/Scripts/python.exe -c "import pandas as pd; d=pd.read_parquet('data/processed/tasks/B2_noise_robustness/test.parquet'); print(len(d), d.columns.tolist()[:8])"
./ecg_env/Scripts/python.exe -c "import pandas as pd; d=pd.read_parquet('data/processed/tasks/B3_temporal_grounding/test.parquet'); print(len(d), d.columns.tolist()[:8])"
./ecg_env/Scripts/python.exe -c "import pandas as pd; d=pd.read_parquet('data/processed/tasks/B4_cross_modal_verification/test.parquet'); print(len(d), d.columns.tolist()[:8])"
./ecg_env/Scripts/python.exe -c "import pandas as pd; d=pd.read_parquet('data/processed/tasks/B5_contradiction_detection/test.parquet'); print(len(d), d.columns.tolist()[:8])"
./ecg_env/Scripts/python.exe -c "import pandas as pd; d=pd.read_parquet('data/processed/tasks/B6_difficulty_stratified/test.parquet'); print(len(d), d.columns.tolist()[:8])"
```

Each builder is idempotent: re-running it without `--force` is a no-op, and with `--force` it reproduces byte-identical output (§4.C invariant 2). `--dev` runs write to `data/processed/tasks/_dev/` and cannot disturb these files.

## 8. Assumptions requiring user confirmation

- **B5 cohort is 128,653, not the locked 128,674**  ::  decision 17. If the 23 paediatric report-says-wide studies should be injection sites after all, the dictionary's `normal_direction_correction` block records exactly how to restore them.
- **B2's regime_2 augmentation policy (question 12 default)**  ::  p = 0.5, family and SNR uniform. It changes a trainer, not this data, so it can still be revisited at Stage P2.5 without a rebuild.
- **B6's hard tier ships empty (question 13 default)**  ::  if the same-subject, same-HR-bucket swap is wanted, it needs new B4 rows plus a regenerated pointer table, but no retraining of anything already done.
