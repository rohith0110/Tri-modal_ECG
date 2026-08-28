"""Stage P2.3 script 21 -- the cohort audit (spec §9.4, §1.2).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/21_audit_tasks_cohort.py

Writes `outputs/audit_reports/cohort_audit.md`. Exit 0 on PASS, 1 on a
violation. It is one of the three files `30_train.py` reads before any
full-scale run (§4.C invariant 4).

§9.4 asks for the description: "for every task: n_ECG, n_subjects, per-class
prevalence, missingness, linkage-tier breakdown, SQI-tier breakdown, cart_id
top-5". §1.2 adds `n_pos per class`. All of that is produced below. But a
description is not an audit, so every task also carries assertions, and the
question they answer is: **would a training run on this cohort produce a
defined number?**

* Every head must have at least two label values present in every split among
  the rows the head is actually scored on. A one-class slice makes AUPRC
  undefined (`_train_lib/metrics.py` returns NaN for it by design), and a head
  that is NaN in the test split is a table cell the paper cannot fill.
* An absent *class* is a different matter and is **reported, not failed**. A3's
  `abnormal_unknown_direction` exists on 1 of 500 K rows and troponin has no
  `low_abnormal` at all -- neither is a build defect, both are facts about
  MIMIC-IV lab data, and `multiclass_macro_auprc` averages over the classes
  present in the slice. The absent classes are listed per task so the §11
  reviewer sees them without having to re-derive them.
* A masked head (`mortality_observable`, `readmission_eligible`,
  `is_corrupted`) must carry a non-null label wherever its mask is True.
  Anything else means the mask and the label disagree about which rows exist.
* The primary cohort must obey the §4 rule for its task -- L3 for the Plan A
  tasks, plus `sqi_tier ∈ {high, medium}` for A2 and A4 (§4 decision 10) -- and
  where a cohort size was locked by a decision, the measured size must equal it.

The counts here are measured off the parquets, never copied from a builder's
own state file, so this audit can contradict Stage P2.1/P2.2 if they ever drift.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import audit_common as ac                              # noqa: E402
from _dataset_lib import build_common as bc                              # noqa: E402
from _dataset_lib.task_spec import TASK_KEYS, TaskSpec, get_task         # noqa: E402

STAGE = "P2.3"
SCRIPT = "21_audit_tasks_cohort"

# -----------------------------------------------------------------------------
# the §4 cohort rules, one row per task. `locked_rows` is a number a §12
# decision froze; measuring a different one means the builder changed under a
# locked decision, which is a violation even if nothing else is wrong.
# -----------------------------------------------------------------------------
COHORT_RULES: dict[str, dict[str, Any]] = {
    "A1_ecg_diagnosis": {
        "spec": "§4.A.1.2", "primary_link_tier": {"L3"},
        "row_key": ["study_id"],
    },
    "A2_measurement_blind": {
        "spec": "§4.A.2.2 as amended by §4 decision 10",
        "primary_link_tier": {"L3"}, "primary_sqi_tier": {"high", "medium"},
        "locked_rows": 275_088, "row_key": ["study_id"],
    },
    "A3_lab_abnormality": {
        "spec": "§4.A.3.2", "primary_link_tier": {"L3"}, "row_key": ["study_id"],
    },
    "A4_event_localization": {
        "spec": "§4.A.4.2 as amended by §4 decision 10",
        "primary_link_tier": {"L3"}, "primary_sqi_tier": {"high", "medium"},
        "row_key": ["study_id"],
    },
    "A5_cross_modal_verification": {
        "spec": "§4.A.5.2 — every clean-cohort ECG, 2 positives + 5 negatives",
        "rows_per_anchor": 7, "row_key": ["anchor_study_id", "neg_type", "image_type"],
    },
    "A6_risk_stratification": {
        "spec": "§4.A.6.2", "primary_link_tier": {"L3"}, "row_key": ["study_id"],
    },
    "B1_measurement_blind": {
        "spec": "§4.B.1.2 — the full clean cohort", "all_primary": True,
        "row_key": ["study_id"],
    },
    "B2_noise_robustness": {
        "spec": "§4.B.2.2 — the frozen Stage 8 corruption set",
        "row_key": ["study_id", "regime", "row_role", "corruption_type", "snr_db"],
    },
    "B3_temporal_grounding": {
        "spec": "§4.B.3.2 — the full clean cohort x 4 queries",
        "rows_per_study": 4, "row_key": ["study_id", "query"],
    },
    "B4_cross_modal_verification": {
        "spec": "§4.B.4.2 — identical rows to A5 (§4.B.4.8)",
        "rows_per_anchor": 7, "row_key": ["anchor_study_id", "neg_type", "image_type"],
    },
    "B5_contradiction_detection": {
        "spec": "§4.B.5.2 as amended by §4 decisions 11 and 17",
        "all_primary": True, "locked_rows": 128_653, "row_key": ["study_id"],
    },
    "B6_difficulty_stratified": {
        "spec": "§4.B.6.2 — a pointer table over B4's rows",
        # No row-key uniqueness here: (study_id, neg_type, difficulty_tier)
        # repeats by design, because B4 gives every anchor TWO positive rows
        # (clean and scan-like image) and the pointer table does not carry
        # `image_type`. Coverage against B4 is the check that means something.
        "rows_per_anchor": 7,
    },
}

MAX_TABLE_ROWS = 400        # A3 alone is 35 heads x 3 splits x 5 classes


# -----------------------------------------------------------------------------
def split_files(spec: TaskSpec) -> dict[str, Path]:
    directory = bc.TASKS_DIR / spec.key
    return {"train": directory / spec.train_file,
            "val": directory / spec.val_file,
            "test": directory / spec.test_file}


def read_split(spec: TaskSpec, path: Path, split: str) -> pd.DataFrame:
    """One split's rows, as the DATALOADER would see them.

    B6's three 'files' are one pointer table (§4.B.6.5), and A5's three
    masked-attribute heads take their labels from a sibling parquet the loader
    joins on `anchor_study_id`. An audit that read the verification parquet
    alone would report those three heads as having no label column at all, so
    it performs the same join, through the same function
    (`task_dataset.join_masked_attributes`).
    """
    frame = pd.read_parquet(path)
    if "split" in frame.columns:
        frame = frame[frame["split"] == split]
    frame = frame.reset_index(drop=True)
    if spec.key == "A5_cross_modal_verification":
        from _dataset_lib.task_dataset import join_masked_attributes

        masked = pd.read_parquet(
            path.parent / f"masked_attribute_{split}.parquet",
            columns=["study_id", "hr_label", "qrs_label", "qtc_label"],
        )
        frame = join_masked_attributes(frame, masked)
    return frame


def head_slice(frame: pd.DataFrame, head) -> pd.Series:
    """The label values this head is actually scored on (mask applied)."""
    values = frame[head.label_column]
    if head.mask_column and head.mask_column in frame.columns:
        mask = frame[head.mask_column].fillna(False).infer_objects(copy=False).astype(bool)
        values = values[mask]
    return values


def label_counts(values: pd.Series, head) -> dict[str, int]:
    if head.kind == "binary":
        clean = values.dropna()
        positive = int(clean.astype(bool).sum())
        return {"positive": positive, "negative": int(len(clean) - positive),
                "null": int(values.isna().sum())}
    if head.kind == "multiclass":
        counts = {cls: int((values == cls).sum()) for cls in head.classes}
        counts["null"] = int(values.isna().sum())
        return counts
    if head.kind == "regression":
        # A continuous head has no classes to count; what the §1.1 table needs
        # instead is the distribution, so a shifted or truncated target shows up.
        numeric = pd.to_numeric(values, errors="coerce").dropna()
        if numeric.empty:
            return {"rows": int(len(values)), "null": int(values.isna().sum())}
        return {"rows": int(len(values)), "null": int(values.isna().sum()),
                "mean": round(float(numeric.mean()), 2),
                "sd": round(float(numeric.std()), 2),
                "min": round(float(numeric.min()), 2),
                "p50": round(float(numeric.median()), 2),
                "max": round(float(numeric.max()), 2)}
    return {"rows": int(len(values)), "null": int(values.isna().sum())}


# -----------------------------------------------------------------------------
def audit_task(audit: ac.Audit, task_key: str, log) -> None:
    spec = get_task(task_key)
    rules = COHORT_RULES[task_key]
    audit.heading(f"`{task_key}`", level=2)
    audit.add(f"Cohort rule: {rules['spec']}. Heads: {len(spec.heads)} "
              f"({', '.join(dict.fromkeys(h.kind for h in spec.heads))}).", "")

    frames: dict[str, pd.DataFrame] = {}
    for split, path in split_files(spec).items():
        if not path.exists():
            audit.check(task_key, f"split_file[{split}]", False, f"{path.name} is missing")
            continue
        frames[split] = read_split(spec, path, split)
    audit.check(task_key, "all_three_splits_present", len(frames) == 3,
                f"read {sorted(frames)}")
    if len(frames) != 3:
        return
    if spec.eval_only:
        audit_pointer_table(audit, spec, frames)
        return

    # -- n_ECG / n_subjects ----------------------------------------------------
    id_column = spec.id_column
    rows = []
    total_rows = total_primary = 0
    for split, frame in frames.items():
        primary = frame
        if spec.primary_flag_column and spec.primary_flag_column in frame.columns:
            primary = frame[frame[spec.primary_flag_column].fillna(False)
                            .infer_objects(copy=False).astype(bool)]
        total_rows += len(frame)
        total_primary += len(primary)
        rows.append([split, f"{len(frame):,}", f"{frame[id_column].nunique():,}",
                     f"{frame.subject_id.nunique():,}", f"{len(primary):,}",
                     f"{primary.subject_id.nunique():,}" if len(primary) else "0"])
    all_rows = pd.concat(frames.values(), ignore_index=True)
    rows.append(["**all**", f"**{total_rows:,}**", f"**{all_rows[id_column].nunique():,}**",
                 f"**{all_rows.subject_id.nunique():,}**", f"**{total_primary:,}**", ""])
    audit.table(["split", "rows", f"unique `{id_column}`", "subjects",
                 "primary rows", "primary subjects"], rows)
    audit.check(task_key, "cohort_non_empty",
                total_rows > 0 and all_rows.subject_id.nunique() > 0,
                f"{total_rows:,} rows over {all_rows.subject_id.nunique():,} subjects")

    # -- row uniqueness --------------------------------------------------------
    key = [c for c in rules["row_key"] if c in all_rows.columns]
    duplicated = int(all_rows.assign(**{c: all_rows[c].fillna("~") for c in key
                                        if all_rows[c].dtype == object})
                     .duplicated(subset=key).sum())
    audit.check(task_key, "row_key_unique", duplicated == 0,
                f"key {key}: {duplicated} duplicate row(s) across the three splits")

    # -- linkage / SQI / cart_id ----------------------------------------------
    breakdown = []
    for column in ("link_tier", "sqi_tier", "cart_id"):
        if column not in all_rows.columns:
            breakdown.append([f"`{column}`", "(not in this task's schema)"])
            continue
        counts = all_rows[column].value_counts(dropna=False).to_dict()
        top = 5 if column == "cart_id" else None
        breakdown.append([f"`{column}`", ac.fmt_counts(counts, top=top) +
                          (f"  (top 5 of {len(counts)})" if top and len(counts) > 5 else "")])
    audit.table(["breakdown", "counts over all three splits"], breakdown)

    declared = [c for c in spec.subgroup_columns if c not in all_rows.columns]
    audit.check(task_key, "subgroup_columns_present", not declared,
                f"every subgroup column `task_spec` declares is on the rows"
                if not declared else f"missing: {declared}")

    # -- the §4 cohort rule ----------------------------------------------------
    primary_all = all_rows
    if spec.primary_flag_column and spec.primary_flag_column in all_rows.columns:
        primary_all = all_rows[all_rows[spec.primary_flag_column].fillna(False)
                               .infer_objects(copy=False).astype(bool)]
    if "primary_link_tier" in rules:
        seen = set(primary_all.link_tier.dropna().unique())
        audit.check(task_key, "primary_cohort_link_tier",
                    seen <= rules["primary_link_tier"],
                    f"primary rows carry link_tier {sorted(seen)}, "
                    f"{rules['spec']} allows {sorted(rules['primary_link_tier'])}")
    if "primary_sqi_tier" in rules:
        seen = set(primary_all.sqi_tier.dropna().unique())
        audit.check(task_key, "primary_cohort_sqi_tier",
                    seen <= rules["primary_sqi_tier"],
                    f"primary rows carry sqi_tier {sorted(seen)}, "
                    f"{rules['spec']} allows {sorted(rules['primary_sqi_tier'])}")
    if rules.get("all_primary"):
        audit.check(task_key, "whole_cohort_is_primary", len(primary_all) == len(all_rows),
                    f"{len(primary_all):,} of {len(all_rows):,} rows flagged primary")
    if "locked_rows" in rules:
        audit.check(task_key, "locked_cohort_size", len(primary_all) == rules["locked_rows"],
                    f"measured {len(primary_all):,} primary rows against the locked "
                    f"{rules['locked_rows']:,}")
    if "rows_per_anchor" in rules:
        anchors = all_rows[id_column].nunique()
        expected = anchors * rules["rows_per_anchor"]
        audit.check(task_key, "rows_per_anchor", len(all_rows) == expected,
                    f"{anchors:,} anchors x {rules['rows_per_anchor']} = {expected:,}, "
                    f"measured {len(all_rows):,}")
    if "rows_per_study" in rules:
        studies = all_rows[id_column].nunique()
        expected = studies * rules["rows_per_study"]
        audit.check(task_key, "rows_per_study", len(all_rows) == expected,
                    f"{studies:,} studies x {rules['rows_per_study']} = {expected:,}, "
                    f"measured {len(all_rows):,}")

    # -- per-class n_pos and prevalence ---------------------------------------
    audit.add("", "**Per-head class counts and prevalence** (`n` is the rows the head is "
                  "scored on after its mask; prevalence is within that slice).", "")
    prevalence_rows = []
    absent_classes: list[str] = []
    for head in spec.heads:
        if head.label_column not in all_rows.columns:
            audit.check(task_key, f"label_column[{head.name}]", False,
                        f"`{head.label_column}` is not in the parquet")
            continue
        per_split_ok = True
        for split, frame in frames.items():
            values = head_slice(frame, head)
            counts = label_counts(values, head)
            n = int(len(values))
            if head.kind in ("binary", "multiclass"):
                shown = {k: v for k, v in counts.items() if k != "null"}
                distinct = sum(1 for v in shown.values() if v > 0)
                per_split_ok = per_split_ok and distinct >= 2
                prevalence_rows.append([
                    head.name, split, f"{n:,}",
                    " · ".join(f"{k} {v:,}" for k, v in shown.items()),
                    " · ".join(f"{k} {v / n:.4f}" for k, v in shown.items()) if n else "-",
                    counts["null"],
                ])
                if split == "test":
                    absent_classes += [f"`{head.name}`.{k}" for k, v in shown.items()
                                       if v == 0]
            else:
                prevalence_rows.append([head.name, split, f"{n:,}", head.kind,
                                        "(sequence / span target)", counts["null"]])
        if head.kind in ("binary", "multiclass"):
            audit.check(task_key, f"head_metric_computable[{head.name}]", per_split_ok,
                        "at least two label values present in every split"
                        if per_split_ok else
                        "a split has only one label value — AUPRC is undefined there")
        # a masked head must carry a label wherever the mask says the row exists
        if head.mask_column:
            null_where_valid = sum(int(head_slice(frame, head).isna().sum())
                                   for frame in frames.values())
            audit.check(task_key, f"mask_implies_label[{head.name}]", null_where_valid == 0,
                        f"`{head.mask_column}` is True on {null_where_valid} row(s) whose "
                        f"`{head.label_column}` is null")
        if head.kind == "multiclass":
            stray = set(pd.concat([f[head.label_column] for f in frames.values()])
                        .dropna().unique()) - set(head.classes)
            audit.check(task_key, f"label_vocabulary[{head.name}]", not stray,
                        f"values outside the declared classes: {sorted(stray)}"
                        if stray else f"every value is one of {list(head.classes)}")

    audit.table(["head", "split", "n scored", "counts", "prevalence", "null"],
                prevalence_rows[:MAX_TABLE_ROWS])
    if len(prevalence_rows) > MAX_TABLE_ROWS:
        audit.add(f"*({len(prevalence_rows) - MAX_TABLE_ROWS} further head x split rows "
                  f"omitted from this table; every one of them is covered by the "
                  f"`head_metric_computable` checks below.)*", "")
    if absent_classes:
        audit.add("", f"**Classes absent from the test split** (reported, not a violation "
                      f"— `multiclass_macro_auprc` averages over the classes present): "
                      f"{', '.join(sorted(set(absent_classes)))}.", "")

    # -- missingness -----------------------------------------------------------
    nulls = all_rows.isna().sum()
    missing_rows = [[f"`{c}`", f"{int(nulls[c]):,}", f"{nulls[c] / len(all_rows):.4f}"]
                    for c in all_rows.columns if nulls[c] > 0]
    audit.add("", "**Missingness** (columns with at least one null, over all three "
                  "splits). Nulls in a label column are only legitimate where a mask "
                  "column declares the row out of scope; the `mask_implies_label` checks "
                  "above are what enforce that.", "")
    audit.table(["column", "nulls", "fraction"],
                missing_rows or [["(none)", "0", "0.0000"]])

    log.info("%s: %d rows, %d subjects, %d checks so far",
             task_key, total_rows, all_rows.subject_id.nunique(), len(audit.checks))


def audit_pointer_table(audit: ac.Audit, spec: TaskSpec,
                        frames: dict[str, pd.DataFrame]) -> None:
    """B6: an evaluation-time slicing of another task's rows (§4.B.6.2, §4.B.6.5).

    It carries no labels of its own -- `y_match` comes from the base task's
    prediction file -- so the head checks the other eleven tasks run do not
    apply. What must hold is that the pointer table addresses exactly the base
    task's rows, and that its tier vocabulary matches
    `task_definitions.yaml`.
    """
    import yaml

    task_key = spec.key
    rules = COHORT_RULES[task_key]
    definitions = yaml.safe_load(
        (bc.CONFIG_DIR / "task_definitions.yaml").read_text(encoding="utf-8"))
    tiers = definitions["tasks"][task_key]["difficulty_tiers"]

    pointer = pd.concat(frames.values(), ignore_index=True)
    base = get_task(spec.base_task)
    base_counts = {s: len(pd.read_parquet(bc.TASKS_DIR / base.key / f"{s}.parquet",
                                          columns=["anchor_study_id"]))
                   for s in bc.SPLITS}

    audit.add(f"An evaluation-time stratification of `{base.key}` "
              f"({rules['spec']}): the table points at rows, it does not own labels. "
              f"`y_match` is read from the base task's prediction file at eval time.", "")
    audit.table(["split", "pointer rows", f"`{base.key}` rows", "match"],
                [[s, f"{len(frames[s]):,}", f"{base_counts[s]:,}",
                  "yes" if len(frames[s]) == base_counts[s] else "NO"] for s in bc.SPLITS])
    audit.check(task_key, "pointer_covers_base_task_rows",
                all(len(frames[s]) == base_counts[s] for s in bc.SPLITS),
                f"pointer rows per split {[len(frames[s]) for s in bc.SPLITS]} against "
                f"{base.key}'s {[base_counts[s] for s in bc.SPLITS]}")

    per_tier = pointer.groupby(["difficulty_tier", "neg_type"], dropna=False).size()
    audit.table(["difficulty_tier", "neg_type", "rows"],
                [[t, "(positive row)" if pd.isna(n) else n, f"{v:,}"]
                 for (t, n), v in per_tier.items()])

    seen_tiers = set(pointer.difficulty_tier.dropna().unique())
    audit.check(task_key, "difficulty_tier_vocabulary",
                seen_tiers <= set(tiers) | {"positive"},
                f"tiers present {sorted(seen_tiers)}; `task_definitions.yaml` declares "
                f"{sorted(tiers)} plus the positive rows")
    for tier, block in tiers.items():
        declared = set(block.get("neg_types") or ())
        present = set(pointer.loc[pointer.difficulty_tier == tier, "neg_type"]
                      .dropna().unique())
        audit.check(task_key, f"tier_neg_types[{tier}]", present == declared,
                    f"`{tier}` holds {sorted(present) or 'no rows'}; the config declares "
                    f"{sorted(declared) or 'none (RESERVED, ships empty)'}")

    anchors = pointer[spec.id_column].nunique()
    audit.check(task_key, "rows_per_anchor",
                len(pointer) == anchors * rules["rows_per_anchor"],
                f"{anchors:,} anchors x {rules['rows_per_anchor']} = "
                f"{anchors * rules['rows_per_anchor']:,}, measured {len(pointer):,}")

    audit.add("", f"Subjects: {pointer.subject_id.nunique():,}. "
                  f"Splits: {ac.fmt_counts(pointer.split.value_counts().to_dict())}.", "")


def audit_b2_grid(audit: ac.Audit) -> None:
    """B2's frozen 8 x 5 corruption grid must be complete (§4.B.2.3)."""
    task_key = "B2_noise_robustness"
    frame = pd.concat([pd.read_parquet(bc.TASKS_DIR / task_key / f"{s}.parquet")
                       for s in ("train", "val", "test")], ignore_index=True)
    corrupted = frame[frame.row_role == "corrupted"]
    cells = corrupted.groupby(["corruption_type", "snr_db"]).size()
    audit.heading("B2 — the frozen corruption grid", level=3)
    audit.add("§4.B.2.3 locks 8 corruption families x 5 SNR levels. The builder attaches "
              "labels to Phase 1's frozen rows and generates nothing, so a missing cell "
              "here means rows were dropped, not that a corruption was never made.", "")
    audit.table(["corruption_type", "snr_db", "rows"],
                [[t, s, f"{n:,}"] for (t, s), n in cells.items()])
    audit.check(task_key, "corruption_grid_complete",
                len(cells) == 40 and int(cells.min()) > 0,
                f"{len(cells)} of 40 (family, SNR) cells present, smallest holds "
                f"{int(cells.min()):,} rows")
    audit.table(["regime", "row_role", "rows"],
                [[r, k, f"{n:,}"] for (r, k), n in
                 frame.groupby(["regime", "row_role"]).size().items()])
    anchors = frame[frame.is_anchor.astype(bool)].study_id.nunique()
    audit.check(task_key, "frozen_anchor_count", anchors == 1871,
                f"{anchors} frozen Phase 1 anchors carry usable B1 labels "
                f"(§5 question 10: 1,871 of the 1,998 that exist)")


def audit_a5_b4_equality(audit: ac.Audit) -> None:
    """§4.B.4.8 compares A5 against B4, which is only meaningful on equal rows."""
    audit.heading("A5 / B4 — row equality", level=3)
    sizes = {}
    for task_key in ("A5_cross_modal_verification", "B4_cross_modal_verification"):
        sizes[task_key] = {s: len(pd.read_parquet(bc.TASKS_DIR / task_key / f"{s}.parquet",
                                                  columns=["anchor_study_id"]))
                           for s in ("train", "val", "test")}
    audit.table(["task", "train", "val", "test"],
                [[f"`{k}`"] + [f"{v[s]:,}" for s in ("train", "val", "test")]
                 for k, v in sizes.items()])
    equal = sizes["A5_cross_modal_verification"] == sizes["B4_cross_modal_verification"]
    audit.check("B4_cross_modal_verification", "a5_b4_row_counts_equal", equal,
                "A5 and B4 carry identical per-split row counts (§4.B.4.8 compares the "
                "two, which is only meaningful on the same rows)" if equal
                else f"row counts differ: {sizes}")


# -----------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", nargs="*", default=list(TASK_KEYS),
                        help="audit a subset (debugging only; a partial run cannot PASS "
                             "the training gate because the report names what it skipped)")
    args = parser.parse_args()

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT)
    state.reset()
    started = time.time()
    bc.preflight([bc.TASKS_DIR], need_free_gb=0.5)

    audit = ac.Audit(
        title="Cohort audit — Phase 2 tasks (Stage P2.3)",
        filename="cohort_audit.md",
        spec="§9.4 (Stage P2.3), §1.2 audit inventory",
        script=f"{SCRIPT}.py",
        intro=[
            "Per task: n_ECG, n_subjects, per-class counts and prevalence, missingness, "
            "linkage-tier and SQI-tier breakdowns and the cart_id top 5 — every number "
            "measured off the task parquets rather than copied from a builder's state "
            "file, so this audit can contradict Stage P2.1/P2.2 if they have drifted.",
            "",
            "The assertions behind the verdict ask one question: **would a training run "
            "on this cohort produce a defined number?** A head needs at least two label "
            "values in every split for AUPRC to exist; a masked head needs a label "
            "wherever its mask is True; the primary cohort must obey its §4 rule; and a "
            "cohort size a §12 decision locked must still measure the same. An absent "
            "*class* is reported rather than failed — A3's `abnormal_unknown_direction` "
            "occurs once in half a million rows and troponin has no `low_abnormal`, "
            "which is MIMIC-IV, not a build defect.",
        ],
    )

    if sorted(args.tasks) != sorted(TASK_KEYS):
        audit.check("(all tasks)", "every_task_audited", False,
                    f"only {args.tasks} were audited; §9.4 requires all 12")

    for task_key in args.tasks:
        audit_task(audit, task_key, log)
    if "B2_noise_robustness" in args.tasks:
        audit_b2_grid(audit)
    if {"A5_cross_modal_verification", "B4_cross_modal_verification"} <= set(args.tasks):
        audit_a5_b4_equality(audit)

    path = audit.write(log)
    state.finish(verdict=audit.verdict, n_checks=len(audit.checks),
                 n_violations=len(audit.violations),
                 report=str(path.relative_to(bc.PROJECT_ROOT)),
                 elapsed_s=round(time.time() - started, 1))
    log.info("cohort audit %s — %d checks, %d violations, %.1f s",
             audit.verdict, len(audit.checks), len(audit.violations), time.time() - started)
    return audit.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
