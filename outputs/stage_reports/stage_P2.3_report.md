# Stage P2.3 — The three Phase 2 audits — leakage, cohort, split — report

Spec §9.4. Generated 2026-08-27T12:37:49Z by `_dataset_lib/stage_report.py` from the per-script state files, the artifacts on disk and the run logs — every number below is read back from what the stage produced.

## 1. Files created

- `scripts/phase2_tasks_benchmark_and_paper/20_audit_tasks_leakage.py`  (31.4 KB, sha256 5bcc9ec353b6)
- `scripts/phase2_tasks_benchmark_and_paper/21_audit_tasks_cohort.py`  (26.6 KB, sha256 d726493e4c50)
- `scripts/phase2_tasks_benchmark_and_paper/22_audit_tasks_split.py`  (15.1 KB, sha256 60d1826a4447)
- `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/audit_common.py`  (9.9 KB, sha256 c902cabc9416)
- `outputs/audit_reports/leakage_audit_phase2.md`  (72.1 KB, sha256 554df3de2d4b)
- `outputs/audit_reports/cohort_audit.md`  (87.8 KB, sha256 fd7bebeb4a6d)
- `outputs/audit_reports/split_audit_phase2.md`  (18.3 KB, sha256 5942d20a8620)

## 2. Files modified

- `scripts/.../30_train.py`  ::  `check_audit_gate` now parses the audit's `**VERDICT:**` line through `audit_common.report_verdict` instead of scanning the report body for the token. The old scan read a clean leakage audit as blocked, because that audit lists every column of every task and A1's heads are named `label_heart_failure_narrow`.
- `scripts/.../_dataset_lib/task_dataset.py`  ::  `_join_masked_attributes` lifted to a module-level `join_masked_attributes(frame, masked)`; the method now calls it. A5's HR/QRS/QTc labels live in `masked_attribute_<split>.parquet`, so the cohort audit has to perform the same join the loader does — through the same function, not a second copy of it.
- `scripts/.../_dataset_lib/stage_report.py`  ::  a P2.3 stage entry, `p23_validation()` (which parses the three reports rather than restating them), and `MANUAL_TEST_NOTES` so §7's prose is per-stage instead of P2.4's.
- `docs/PHASE2_PROGRESS.md`  ::  header, §4 decision 19, §6 ledger (Step 10 and the §1.2 audit checklist), §7 trap 20, §8 session log.

## 3. Files / folders deleted

none — this stage only creates. `--dev` output is isolated under `data/processed/tasks/_dev/` and is never published.

## 4. Design decisions

- **A forbidden quantity may sit in a task parquet only where §4 puts it there, and only if the dataloader is shown not to reach it**  ::  §9.4 says to flag any forbidden column, but §4.A.2.5 lists `hr_bpm`, `qrs_ms` and `qtc_ms` under the comment `# provenance` and §4.B.5.5 lists `source_measurement`. Read literally, the two rules contradict each other and A2, B1 and B5 would be permanent violations of a spec that mandated their own schemas. The audit instead names every such column with the section that mandates it, treats an unlisted one as a violation, and proves unreachability by constructing the real `TaskDataset` for every (task, arch-tier family) and checking the tensor keys it returns.
- **An unclassified column is a violation**  ::  a column list is only an audit if every entry has been looked at. Each column resolves to a role from `task_spec`, `task_definitions.yaml` or §4's output schema; anything left over blocks. That is what makes a column added by a future builder edit fail loudly instead of arriving unexamined.
- **The training gate parses a verdict LINE, not the word 'FAIL' anywhere in the body**  ::  `30_train.py` used to scan the whole report for the token. The leakage audit lists every column of every task, and A1's heads are named `label_heart_failure_narrow` — so a clean report was read as a blocked one. `audit_common.report_verdict` is now the single parser and `30_train.py` imports it; each audit parses its own rendered report with it before the file lands, so an audit cannot emit a report the gate would misread.
- **An absent CLASS is reported, not failed; an undefined METRIC is failed**  ::  A3's `abnormal_unknown_direction` occurs once in 500,471 rows and troponin has no `low_abnormal` at all. Neither is a build defect — they are facts about MIMIC-IV lab data, and `multiclass_macro_auprc` averages over the classes present in the slice. What the cohort audit does fail on is a head with fewer than two label values in some split, because that head's AUPRC is NaN and the paper has a cell it cannot fill.
- **The split audit checks donor containment, not just anchor disjointness**  ::  §9.4 asks for zero subject overlap. An A5/B4 row points at up to three studies, so §4.C invariant 1 is about the bytes a row loads, not its anchor: a train row pointing at a test subject's signal carries test bytes into training and anchor-level disjointness would never show it. All three pointer columns are resolved to subjects and checked against the row's own split, and a swapped modality on a negative is checked to come from a different subject.
- **Every task's split is checked against the frozen global partition, not only against itself**  ::  a task can partition its own rows perfectly and still have re-derived the split, which §4.C invariant 1 forbids. Agreement with `splits_subject_level.parquet` is what makes the twelve tasks consistent with each other rather than each internally consistent.
- **A partial run cannot PASS**  ::  both `--tasks` and `--skip-dataloader` record their own omission as a violation. An audit that skipped a task is not a weaker PASS; it is not a PASS.

## 5. Complete code

### `scripts/phase2_tasks_benchmark_and_paper/20_audit_tasks_leakage.py`

```python
"""Stage P2.3 script 20 -- the leakage audit (spec §9.4, §4.C invariant 4).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/20_audit_tasks_leakage.py

Writes `outputs/audit_reports/leakage_audit_phase2.md`. Exit 0 on PASS, 1 on a
violation. `30_train.py` reads the report back and refuses to start a
full-scale run until it says PASS.

§9.4 asks for one thing: "for every task, read the parquet, list every column,
cross-check against `task_input_policy.yaml`; flag any forbidden column". That
alone would be too weak in one direction and too strong in the other, so this
audit runs six gates rather than one.

**Too weak**, because a column is not the leakage surface -- the *dataloader*
is. `task_input_policy.yaml` forbids modality KINDS, and nothing in a parquet's
column list says which bytes `TaskDataset` will actually fetch. Gates 2, 3 and 5
close that: every model config that will ever be trained is resolved to its
modality kinds and pushed through `check_input_policy`; every (task, arch-tier
family) the policy allows is constructed for real and the tensor keys it hands
the model are compared against an allowlist; and A5's masked-attribute head is
shown, by forward pass, to be numerically independent of the text branch.

**Too strong**, because §4's own output schemas mandate provenance columns that
name forbidden quantities -- §4.A.2.5 lists `hr_bpm`, `qrs_ms`, `qtc_ms` under
the comment `# provenance`, and §4.B.5.5 lists `source_measurement`. Flagging
those as leaks would mean the spec contradicts itself. The rule this audit
applies instead: **a forbidden quantity may sit in a task parquet only if §4
declares it there, and only if gate 3 proves the dataloader never hands it to a
model.** Every such column is listed in `PROVENANCE` below with the section that
mandates it, and an unlisted one is a violation. A column that matches nothing
at all is also a violation -- an unclassified column is an unaudited column.

The six gates:

1. **Column inventory.** Every column of every task parquet is classified
   (identity / split / label / mask / subgroup / model-text / declared
   provenance) and cross-checked against the task's forbidden list.
2. **Model-config gate.** All 94 generated configs resolve to modality kinds
   that `check_input_policy` accepts, and no config names a forbidden kind.
3. **Dataloader tensor gate.** For each (task, arch-tier family) the policy
   allows, a real `TaskDataset` is built on the test split and one item pulled;
   its keys must lie inside the locked batch-key allowlist. This is what proves
   the provenance columns of gate 1 are unreachable.
4. **B5 single-report gate.** The policy's own note: B5 stores both reports but
   a model is fed exactly one per row. Checked on the real parquet.
5. **A5 masked-attribute isolation** (progress-doc trap 17). On an A5 positive
   row the text IS the unmasked anchor report, so a masked-attribute head that
   saw the fused embedding would be handed its own answer. Proven by forward
   pass: the text branch changes, the three attribute heads do not.
6. **Source-tree gate** (§11.1 "no ... columns appear in any feature loader or
   feature parquet read at train time"). No module on the model path may read
   `structured_features.parquet` or the machine measurements; the single
   permitted reader is `algorithmic_baselines.py`, under the A1/A6
   `baseline_only_exemptions` the policy file declares.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import audit_common as ac                              # noqa: E402
from _dataset_lib import build_common as bc                              # noqa: E402
from _dataset_lib.task_spec import TASK_KEYS, get_task                   # noqa: E402

STAGE = "P2.3"
SCRIPT = "20_audit_tasks_leakage"

POLICY_PATH = bc.CONFIG_DIR / "task_input_policy.yaml"
MODEL_CONFIG_DIR = bc.CONFIG_DIR / "model_configs"

# -----------------------------------------------------------------------------
# what "a forbidden quantity" means as a COLUMN NAME
# -----------------------------------------------------------------------------
# `task_input_policy.yaml` forbids the references `machine_measurements` and
# `structured_features`. Those resolve to concrete column names, listed here
# exactly -- not as globs. A glob on `qrs_*` would flag A4's `qrs_onsets_lead2`
# (a label) and A2's `qrs_label` (a label), which is how an audit trains its
# reader to ignore it.
MACHINE_MEASUREMENT_COLUMNS = {
    "rr_interval", "p_onset", "p_end", "qrs_onset", "qrs_end", "t_end",
    "p_axis", "qrs_axis", "t_axis",
    "machine_hr_bpm", "machine_qrs_ms", "machine_qtc_ms",
    "hr_bpm", "qrs_ms", "qtc_ms", "pr_ms",
}
STRUCTURED_FEATURE_COLUMNS = {
    "qtc_ms_bazett", "qtc_bazett_ms", "qrs_dur_ms", "sqi_per_lead", "sqi_aggregate",
    "p_wave_present", "st_deviation_mv", "t_wave_amplitude_mv", "heart_rate_std",
}
FORBIDDEN_COLUMNS = {
    **{c: "machine_measurements" for c in MACHINE_MEASUREMENT_COLUMNS},
    **{c: "structured_features" for c in STRUCTURED_FEATURE_COLUMNS},
}

# -----------------------------------------------------------------------------
# columns §4 mandates in a task parquet even though they name a forbidden
# quantity, or that no other classifier reaches. (task, column) -> (role, spec).
# A `re:` prefix on the column makes it a pattern -- A3 has 35 heads x 3
# provenance columns and writing 105 literals would only hide the shape.
# -----------------------------------------------------------------------------
PROVENANCE: dict[str, dict[str, tuple[str, str]]] = {
    "A1_ecg_diagnosis": {
        "label_source": ("label provenance", "§4.A.1.5"),
        "n_icd_codes_on_admission": ("label provenance", "§4.A.1.5"),
        "icd_codes_matched": ("label provenance", "§4.A.1.5"),
    },
    "A2_measurement_blind": {
        "hr_bpm": ("declared provenance", "§4.A.2.5 `# provenance`"),
        "qrs_ms": ("declared provenance", "§4.A.2.5 `# provenance`"),
        "qtc_ms": ("declared provenance", "§4.A.2.5 `# provenance`"),
        "qtc_ms_bazett": ("declared provenance", "§4 decision 14 sensitivity row"),
    },
    "B1_measurement_blind": {
        "hr_bpm": ("declared provenance", "§4.B.1.5 = §4.A.2.5"),
        "qrs_ms": ("declared provenance", "§4.B.1.5 = §4.A.2.5"),
        "qtc_ms": ("declared provenance", "§4.B.1.5 = §4.A.2.5"),
        "qtc_ms_bazett": ("declared provenance", "§4 decision 14 sensitivity row"),
    },
    "A3_lab_abnormality": {
        "re:^lab_.+_signed_hours_from_ecg$": ("label provenance", "§4.A.3.5"),
        "re:^lab_.+_abnormal_method$": ("label provenance", "§4.A.3.5"),
        "re:^lab_.+_label_same_hadm$": ("sensitivity filter", "§4.A.3.8"),
    },
    "A4_event_localization": {
        "n_qrs_spans": ("label provenance", "§4.A.4.3"),
    },
    "A5_cross_modal_verification": {
        "report_text_masked": ("model text input (masked)", "§4.A.5.4 allowed input"),
        "masked_positions": ("masking provenance", "§4.A.5.3"),
        "n_masked_spans": ("masking provenance", "§4.A.5.3"),
        "masked_families": ("masking provenance", "§4 decision 16"),
    },
    "A6_risk_stratification": {
        "days_to_death": ("label provenance", "§4.A.6.5"),
        "days_to_readmission": ("label provenance", "§4.A.6.5"),
        "next_admission_type": ("label provenance", "§4.A.6.5"),
        "next_admission_location": ("label provenance", "§4.A.6.5"),
    },
    "B3_temporal_grounding": {
        "link_tier": ("cohort provenance", "§4.B.3.5"),
    },
    "B5_contradiction_detection": {
        "link_tier": ("cohort provenance", "§4.B.5.5"),
        "original_report_text": ("declared provenance", "§4.B.5.5; gate 4 resolves one"),
        "corrupted_report_text": ("declared provenance", "§4.B.5.5; gate 4 resolves one"),
        "source_measurement": ("declared provenance", "§4.B.5.5 `# JSON of ... injection`"),
        "eligible_families": ("cohort provenance", "§4 decision 11 eligibility pool"),
    },
}

# The only keys `TaskDataset.__getitem__` may put in a batch. Anything else is
# an unaudited path from a parquet column to a model.
STATIC_BATCH_KEYS = {"signal", "image", "input_ids", "attention_mask", "text_vec",
                     "presence", "row_index", "query_idx"}

# Modules on the model path. `algorithmic_baselines.py` is deliberately absent:
# it holds the A1/A6 exemptions the policy file declares, and gate 6 checks
# that it is the ONLY file in this tree that reads a machine measurement.
MODEL_PATH_MODULES = ["30_train.py", "31_eval.py",
                      "_dataset_lib/task_dataset.py", "_dataset_lib/task_spec.py",
                      "_dataset_lib/corruption.py", "_dataset_lib/bootstrap.py",
                      "_model_lib/signal_encoders.py", "_model_lib/image_encoders.py",
                      "_model_lib/text_encoders.py", "_model_lib/fusion_heads.py",
                      "_model_lib/task_models.py", "_model_lib/model_configs.py",
                      "_train_lib/trainer.py", "_train_lib/metrics.py",
                      "_train_lib/threshold.py", "_train_lib/calibration.py",
                      "_train_lib/seed.py"]
SOURCE_FORBIDDEN = ("structured_features.parquet", "machine_measurements(",
                    "machine_hr_bpm", "machine_qrs_ms", "machine_qtc_ms", "rr_interval")


# -----------------------------------------------------------------------------
# gate 1 -- column inventory
# -----------------------------------------------------------------------------
def classify(task_key: str, column: str) -> tuple[str, str]:
    """(role, why) for one column of one task. `role` 'UNCLASSIFIED' is a violation."""
    spec = get_task(task_key)
    identity = {"study_id", "subject_id", "anchor_study_id", "signal_id", "image_id",
                "text_id", "hadm_id", "ecg_time"}
    if column in identity:
        return "identity", "row / modality lookup key (§4.C invariant 3)"
    if column == "split":
        return "split", "the global patient split, joined never re-derived (§4.C.1)"
    if column in spec.label_columns:
        return "label", f"target of head `{[h.name for h in spec.heads if h.label_column == column][0]}`"
    if column in spec.mask_columns:
        return "mask", "gates a head's loss; carries no signal about the label"
    if column == spec.primary_flag_column:
        return "cohort filter", "primary-vs-sensitivity cohort flag"
    if column in spec.subgroup_columns:
        return "subgroup", "reported-on stratum (§4.X.8); reaches the prediction file, not the model"
    if column in spec.extra_columns:
        return "provenance", "declared in `task_spec.extra_columns`"
    table = PROVENANCE.get(task_key, {})
    if column in table:
        return table[column]
    for key, value in table.items():
        if key.startswith("re:") and re.match(key[3:], column):
            return value
    return "UNCLASSIFIED", "no role in task_spec, task_definitions or §4's output schema"


def gate_columns(audit: ac.Audit) -> None:
    audit.heading("Gate 1 — column inventory against `task_input_policy.yaml`")
    audit.add(
        "Every column of every task parquet, classified. A column whose name resolves "
        "to a **forbidden reference** (`machine_measurements` / `structured_features`) "
        "is a violation unless §4's own output schema mandates it as provenance — those "
        "are named in `PROVENANCE` with their section, and gate 3 proves the dataloader "
        "cannot reach them. A column matching nothing is a violation: an unclassified "
        "column is an unaudited column.", "")
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))["tasks"]

    for task_key in TASK_KEYS:
        directory = bc.TASKS_DIR / task_key
        files = sorted(p for p in directory.glob("*.parquet")
                       if p.name != "cohort_manifest.parquet")
        audit.check(task_key, "parquets_present", bool(files),
                    f"{len(files)} task parquet(s): {', '.join(p.name for p in files)}")
        if not files:
            continue

        schemas = {p.name: pq.read_schema(p) for p in files}
        columns: dict[str, str] = {}
        for schema in schemas.values():
            for name, dtype in zip(schema.names, schema.types):
                columns.setdefault(name, str(dtype))

        rows, unclassified, forbidden_hits = [], [], []
        for name in sorted(columns):
            role, why = classify(task_key, name)
            reference = FORBIDDEN_COLUMNS.get(name)
            verdict = ac.PASS
            if role == "UNCLASSIFIED":
                unclassified.append(name)
                verdict = "UNCLASSIFIED"
            elif reference and reference in policy[task_key].get("forbidden_inputs", ()):
                if role.startswith("declared provenance"):
                    verdict = "provenance"
                else:
                    forbidden_hits.append(f"{name} ({reference})")
                    verdict = "FORBIDDEN"
            rows.append([f"`{name}`", columns[name], role, why, verdict])

        audit.heading(f"`{task_key}` — {len(columns)} columns", level=3)
        audit.add(f"Allowed inputs: {', '.join('`' + k + '`' for k in policy[task_key]['allowed_inputs'])}", "")
        audit.add(f"Forbidden inputs: {', '.join('`' + k + '`' for k in policy[task_key].get('forbidden_inputs', []))}", "")
        audit.table(["column", "dtype", "role", "why", "verdict"], rows)

        audit.check(task_key, "no_unclassified_columns", not unclassified,
                    "every column has a declared role" if not unclassified
                    else f"unclassified: {', '.join(unclassified)}")
        audit.check(task_key, "no_forbidden_column_as_input", not forbidden_hits,
                    "no column resolves to a forbidden reference outside §4's declared "
                    "provenance" if not forbidden_hits
                    else f"forbidden references present: {', '.join(forbidden_hits)}")

        declared = [n for n in columns
                    if FORBIDDEN_COLUMNS.get(n) in policy[task_key].get("forbidden_inputs", ())]
        if declared:
            audit.add(f"Declared-provenance columns naming a forbidden quantity: "
                      f"{', '.join('`' + d + '`' for d in sorted(declared))}. "
                      f"Gate 3 proves none reaches a model.", "")


# -----------------------------------------------------------------------------
# gate 2 -- every model config resolves to allowed modality kinds
# -----------------------------------------------------------------------------
def gate_model_configs(audit: ac.Audit) -> None:
    from _dataset_lib.task_dataset import check_input_policy, plan_from_config
    from _model_lib.model_configs import load_model_config

    audit.heading("Gate 2 — every generated model config resolves to allowed inputs")
    audit.add(
        "`config/model_configs/` is generated from `task_input_policy.yaml`, so this "
        "gate is checking that the generator and the policy have not drifted apart. "
        "Each config is resolved to the modality kinds it would actually load and "
        "pushed through the same `check_input_policy` a training run calls.", "")

    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))["tasks"]
    configs = sorted(MODEL_CONFIG_DIR.glob("*.yaml"))
    audit.check("(all tasks)", "model_configs_present", len(configs) > 0,
                f"{len(configs)} config YAMLs under config/model_configs/")

    rows, bad = [], []
    per_task: dict[str, int] = {}
    for path in configs:
        config = load_model_config(path)
        task_key = config["task"]
        kinds = plan_from_config(config).kinds()
        per_task[task_key] = per_task.get(task_key, 0) + 1
        try:
            check_input_policy(task_key, kinds)
            verdict = ac.PASS
        except Exception as error:                       # PermissionError / KeyError
            verdict = "REJECTED"
            bad.append(f"{path.name}: {error}")
        rows.append([f"`{path.name}`", f"`{task_key}`", config["arch_tier"],
                     ", ".join(f"`{k}`" for k in kinds) or "(none)", verdict])
    audit.table(["config", "task", "arch tier", "modality kinds resolved", "policy"], rows)

    audit.check("(all tasks)", "all_model_configs_allowed", not bad,
                f"{len(configs)} configs, every resolved modality kind is on its task's "
                f"allowed list" if not bad else "; ".join(bad))

    for task_key in TASK_KEYS:
        if get_task(task_key).eval_only:
            continue
        forbidden = set(policy[task_key].get("forbidden_inputs", ()))
        named = set()
        for path in configs:
            config = load_model_config(path)
            if config["task"] != task_key:
                continue
            named |= set(plan_from_config(config).kinds())
        audit.check(task_key, "config_kinds_disjoint_from_forbidden", not (named & forbidden),
                    f"{per_task.get(task_key, 0)} configs name "
                    f"{{{', '.join(sorted(named)) or 'no modality'}}}; overlap with the "
                    f"forbidden set: {sorted(named & forbidden) or 'none'}")


# -----------------------------------------------------------------------------
# gate 3 -- what the dataloader actually hands the model
# -----------------------------------------------------------------------------
def _family(arch_tier: str) -> str:
    return arch_tier.split("_")[0]


def gate_dataloader(audit: ac.Audit, log) -> None:
    from _dataset_lib.task_dataset import ModalityPlan, TaskDataset, plan_from_config
    from _model_lib.model_configs import load_model_config

    audit.heading("Gate 3 — the tensor keys the dataloader hands the model")
    audit.add(
        "The parquet column list is not the leakage surface; `TaskDataset.__getitem__` "
        "is. One representative config per (task, arch-tier family) is constructed for "
        "real on the **test** split and one item pulled. Every key it returns must be "
        "either a locked batch key or a `y__`/`m__` target for a head this task "
        "declares. A provenance column reaching the model would have to appear here.", "")

    configs = [load_model_config(p) for p in sorted(MODEL_CONFIG_DIR.glob("*.yaml"))]
    rows = []
    for task_key in TASK_KEYS:
        spec = get_task(task_key)
        if spec.eval_only:
            audit.check(task_key, "dataloader_keys",
                        True, "evaluation-only task (§4.B.6): it slices "
                              f"`{spec.base_task}` predictions and constructs no loader")
            continue
        allowed_keys = set(STATIC_BATCH_KEYS)
        for head in spec.heads:
            allowed_keys |= {f"y__{head.name}", f"m__{head.name}"}
        allowed_keys |= {"y__fiducials_onset", "y__fiducials_offset", "y__fiducials_regmask"}

        seen_families: set[str] = set()
        for config in configs:
            if config["task"] != task_key:
                continue
            family = _family(config["arch_tier"])
            if family in seen_families:
                continue
            seen_families.add(family)
            plan: ModalityPlan = plan_from_config(config)
            label = f"{task_key}/{config['arch_tier']}"
            try:
                dataset = TaskDataset(task_key, "test", plan, limit=4)
                if plan.text_encoder == "tfidf":
                    # The trainer fits the vectoriser on TRAIN and injects the
                    # matrix; a zero matrix exercises the same code path and
                    # keeps this audit off the training data.
                    dataset.precompute_text_features(
                        np.zeros((len(dataset), 512), dtype="float32"))
                item = dataset[0]
                extra = sorted(set(item) - allowed_keys)
                ok = not extra
                detail = (f"{len(item)} tensor keys, all inside the allowlist"
                          if ok else f"unexpected keys: {extra}")
            except Exception as error:                   # pragma: no cover - reported
                ok, extra = False, []
                detail = f"could not construct the loader: {type(error).__name__}: {error}"
            log.info("gate 3 %s -> %s", label, "PASS" if ok else "VIOLATION")
            audit.check(task_key, f"dataloader_keys[{config['arch_tier']}]", ok, detail)
            rows.append([f"`{task_key}`", config["arch_tier"],
                         ", ".join(f"`{k}`" for k in plan.kinds()) or "(none)",
                         detail, ac.PASS if ok else "VIOLATION"])
    audit.table(["task", "arch tier", "kinds loaded", "measured", "verdict"], rows)


# -----------------------------------------------------------------------------
# gate 4 -- B5 is fed exactly one report per row
# -----------------------------------------------------------------------------
def gate_b5_single_report(audit: ac.Audit) -> None:
    import pandas as pd

    from _dataset_lib.task_dataset import TaskDataset

    task_key = "B5_contradiction_detection"
    audit.heading("Gate 4 — B5 is fed exactly one report per row")
    audit.add(
        "`task_input_policy.yaml` on B5: *\"the task parquet stores both columns, but a "
        "model is fed exactly ONE of them per row — feeding both would trivially reveal "
        "the label by diff. The leakage audit checks the dataloader, not just the "
        "parquet, for this task.\"* Measured on the whole test split.", "")

    frame = pd.read_parquet(bc.TASKS_DIR / task_key / "test.parquet")
    resolved = TaskDataset._resolve_b5_text(frame)

    dropped = {"original_report_text", "corrupted_report_text"} & set(resolved.columns)
    audit.check(task_key, "b5_source_texts_dropped", not dropped,
                "the resolver drops both source columns; the frame carries only "
                "`audited_report_text`" if not dropped else f"still present: {sorted(dropped)}")

    corrupt = frame["is_corrupted"].to_numpy(dtype=bool)
    audited = resolved["audited_report_text"].to_numpy()
    right_on_corrupt = bool(
        (audited[corrupt] == frame["corrupted_report_text"].to_numpy()[corrupt]).all())
    right_on_clean = bool(
        (audited[~corrupt] == frame["original_report_text"].to_numpy()[~corrupt]).all())
    audit.check(task_key, "b5_audited_text_is_the_right_one",
                right_on_corrupt and right_on_clean,
                f"{int(corrupt.sum()):,} corrupted rows show `corrupted_report_text`, "
                f"{int((~corrupt).sum()):,} clean rows show `original_report_text`")

    text_columns = [c for c in resolved.columns
                    if resolved[c].dtype == object and "report_text" in c]
    audit.check(task_key, "b5_one_text_column_only", text_columns == ["audited_report_text"],
                f"text columns after resolution: {text_columns}")

    # Length is the other way a corrupted row could give itself away for free.
    lengths = pd.Series(audited).str.len()
    audit.add(
        f"Mean audited-report length: corrupted {lengths[corrupt].mean():.1f} chars, "
        f"clean {lengths[~corrupt].mean():.1f} chars — decision 9's swap-not-insert rule "
        f"is why these are close, and it is why length is not a shortcut feature.", "")


# -----------------------------------------------------------------------------
# gate 5 -- A5's masked-attribute head cannot see the text branch
# -----------------------------------------------------------------------------
def gate_a5_masked_head(audit: ac.Audit) -> None:
    import torch

    from _dataset_lib.task_dataset import ModalityPlan
    from _model_lib.task_models import build_model

    task_key = "A5_cross_modal_verification"
    audit.heading("Gate 5 — A5's masked-attribute head is independent of the text branch")
    audit.add(
        "Progress-doc trap 17: on an A5 **positive** row the text IS the unmasked anchor "
        "report, so a masked-attribute head reading the fused embedding would be handed "
        "the HR/QRS/QTc answer it is asked to predict. Proven rather than asserted — the "
        "same model is run twice on one batch, changing only the text vector, with the "
        "backbones in eval mode and gradients off.", "")

    spec = get_task(task_key)
    plan = ModalityPlan(signal_kind="preprocessed_lead2", n_leads=1,
                        image_kind="image_clean_lead2", image_h=224, image_w=672,
                        text_encoder="tfidf")
    torch.manual_seed(2026)
    model = build_model(spec, plan, pretrained=False).eval()

    batch = {
        "signal": torch.randn(2, 1, 5000),
        "image": torch.randn(2, 3, 224, 672),
        "text_vec": torch.randn(2, 512),
        "presence": torch.ones(2, 3),
    }
    with torch.no_grad():
        first = model(batch)
        batch_two = dict(batch, text_vec=torch.randn(2, 512))
        second = model(batch_two)

    attribute_heads = [h.name for h in spec.heads[1:]]
    unchanged = [name for name in attribute_heads
                 if torch.equal(first[name], second[name])]
    audit.check(task_key, "a5_masked_head_text_independent",
                sorted(unchanged) == sorted(attribute_heads),
                f"changing `text_vec` leaves {sorted(unchanged)} bit-identical "
                f"(expected {sorted(attribute_heads)})")

    verification_moved = not torch.equal(first["y_match"], second["y_match"])
    audit.check(task_key, "a5_verification_head_does_read_text", verification_moved,
                "the verification head's logits DO move with the text — the control that "
                "proves the batch change reached the model at all")

    audit.check(task_key, "a5_masked_head_input_dim",
                model.masked_head is not None,
                f"masked head input width = EMBED_DIM x (signal + image) = "
                f"{512 * (int(plan.uses_signal) + int(plan.uses_image))}, "
                f"text contributes 0")


# -----------------------------------------------------------------------------
# gate 6 -- the source tree on the model path
# -----------------------------------------------------------------------------
def gate_source_tree(audit: ac.Audit) -> None:
    audit.heading("Gate 6 — no module on the model path reads a forbidden source")
    audit.add(
        "§11.1: *\"for A2/B1/B2/B3/A4, no `rr_interval/qrs_*/t_axis/structured_features` "
        "columns appear in any feature loader or feature parquet read at train time.\"* "
        "Docstrings and comments are stripped first, so a module that only *names* a "
        "forbidden column while explaining why it does not read it stays clean.", "",
        "`_dataset_lib/build_common.py` is deliberately not on this list: it is the "
        "**builders'** shared library and owns `machine_measurements()`, the sentinel-"
        "masking reader A2/B1/B2 need to compute their labels. What matters is that no "
        "module on the model path calls it — the token `machine_measurements(` in the "
        "scan below is that call site.", "")

    root = Path(__file__).resolve().parent
    rows, offenders = [], []
    for name in MODEL_PATH_MODULES:
        path = root / name
        if not path.exists():
            offenders.append(f"{name} is missing from the model path")
            continue
        source = _strip_comments(path.read_text(encoding="utf-8"))
        hits = sorted({token for token in SOURCE_FORBIDDEN if token in source})
        if hits:
            offenders.append(f"{name} reads {hits}")
        rows.append([f"`{name}`", ", ".join(hits) if hits else "none", len(source.splitlines())])
    audit.table(["module on the model path", "forbidden source read", "code lines"], rows)
    audit.check("(all tasks)", "model_path_reads_no_forbidden_source", not offenders,
                f"{len(MODEL_PATH_MODULES)} modules scanned, none reads "
                f"`structured_features.parquet` or a machine measurement"
                if not offenders else "; ".join(offenders))

    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))["tasks"]
    baselines = root / "_model_lib" / "algorithmic_baselines.py"
    baseline_source = _strip_comments(baselines.read_text(encoding="utf-8"))
    reads_machine = any(token in baseline_source for token in SOURCE_FORBIDDEN)
    declared = [key for key in TASK_KEYS if policy[key].get("baseline_only_exemptions")]
    audit.check("(all tasks)", "baseline_exemptions_declared",
                (not reads_machine) or sorted(declared) == ["A1_ecg_diagnosis",
                                                            "A6_risk_stratification"],
                f"`algorithmic_baselines.py` reads machine measurements: {reads_machine}; "
                f"tasks declaring `baseline_only_exemptions`: {declared}")


def _strip_comments(source: str) -> str:
    """Drop docstrings and `#` comments so prose about a column is not a read."""
    quote = '"' * 3
    source = re.sub("(?s)" + quote + ".*?" + quote, "", source)
    source = re.sub("(?s)'''.*?'''", "", source)
    return "\n".join(line.split("#")[0] for line in source.splitlines())


# -----------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-dataloader", action="store_true",
                        help="skip gate 3 (it reads real signal/image bytes); "
                             "the report then records the gate as not run, which "
                             "blocks the training gate")
    args = parser.parse_args()

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT)
    state.reset()
    started = time.time()
    bc.preflight([POLICY_PATH, MODEL_CONFIG_DIR, bc.TASKS_DIR], need_free_gb=0.5)

    audit = ac.Audit(
        title="Leakage audit — Phase 2 tasks (Stage P2.3)",
        filename="leakage_audit_phase2.md",
        spec="§9.4 (Stage P2.3), §4.C invariant 4, §11.1 leakage compliance",
        script=f"{SCRIPT}.py",
        intro=[
            "`config/task_input_policy.yaml` is the single authority on leakage. This "
            "audit checks the 12 task parquets and the code that loads them against it "
            "in six gates: the column inventory §9.4 asks for, plus the model-config, "
            "dataloader, B5-single-report, A5-head-isolation and source-tree gates that "
            "cover the part of the leakage surface a column list cannot see.",
            "",
            "A **declared provenance** column is one §4's own output schema puts in the "
            "parquet even though it names a forbidden quantity (§4.A.2.5's `hr_bpm`, "
            "§4.B.5.5's `source_measurement`). Those are permitted **only** because "
            "gate 3 shows the dataloader never hands them to a model.",
        ],
    )

    gate_columns(audit)
    gate_model_configs(audit)
    if args.skip_dataloader:
        audit.check("(all tasks)", "dataloader_gate_ran", False,
                    "gate 3 was skipped with --skip-dataloader; the audit cannot certify "
                    "that the declared-provenance columns are unreachable")
    else:
        gate_dataloader(audit, log)
    gate_b5_single_report(audit)
    gate_a5_masked_head(audit)
    gate_source_tree(audit)

    path = audit.write(log)
    state.finish(verdict=audit.verdict, n_checks=len(audit.checks),
                 n_violations=len(audit.violations), report=str(path.relative_to(bc.PROJECT_ROOT)),
                 elapsed_s=round(time.time() - started, 1))
    log.info("leakage audit %s — %d checks, %d violations, %.1f s",
             audit.verdict, len(audit.checks), len(audit.violations), time.time() - started)
    return audit.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
```

### `scripts/phase2_tasks_benchmark_and_paper/21_audit_tasks_cohort.py`

```python
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
```

### `scripts/phase2_tasks_benchmark_and_paper/22_audit_tasks_split.py`

```python
"""Stage P2.3 script 22 -- the split audit (spec §9.4, §4.C invariant 1).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/22_audit_tasks_split.py

Writes `outputs/audit_reports/split_audit_phase2.md`. Exit 0 on PASS, 1 on a
violation. The third of the three files `30_train.py` reads before any
full-scale run (§4.C invariant 4).

§9.4 asks for: "for every task, verify zero subject overlap across
train/val/test". That is check 2 below. It is necessary and, on its own, not
sufficient -- a task could partition its own rows perfectly and still have
re-derived the split, which §4.C invariant 1 forbids ("the split column is
**always** populated from that join, never re-derived"). A task built off a
re-derived split would be internally consistent and still put a patient in
training who is in another task's test set, which is exactly the leak a
patient-level split exists to prevent.

So five things are checked per task:

1. **The split column matches the file.** Every row in `train.parquet` says
   `train`. A row filed under the wrong name is invisible to the overlap check.
2. **Zero subject overlap** across the three splits -- §9.4's requirement.
3. **Agreement with the frozen global split.** Every subject's split equals
   `splits_subject_level.parquet`'s, and every subject is in it. This is what
   makes the twelve tasks mutually consistent rather than each internally
   consistent.
4. **No study crosses a split**, which subject-level disjointness implies but
   which is worth measuring separately: it catches a study_id joined to the
   wrong subject.
5. **Donor containment** for the verification tasks. A5/B4 rows point at up to
   three different studies, and §4.C invariant 1 is about the BYTES a row
   loads, not just its anchor. A train row pointing at a test subject's signal
   carries test bytes into training, and no amount of anchor-level disjointness
   would show it. Every `signal_id` / `image_id` / `text_id` must resolve to a
   subject in the row's own split -- and, on a negative, to a DIFFERENT subject
   than the anchor, or the "negative" is a positive with a different label.

Nothing here re-splits anything, and this audit writes no parquet.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import audit_common as ac                              # noqa: E402
from _dataset_lib import build_common as bc                              # noqa: E402
from _dataset_lib.task_spec import TASK_KEYS, TaskSpec, get_task         # noqa: E402

STAGE = "P2.3"
SCRIPT = "22_audit_tasks_split"

DONOR_COLUMNS = ("signal_id", "image_id", "text_id")


def global_split() -> pd.Series:
    """`subject_id -> split`, the frozen Phase 1 partition (trap 4)."""
    frame = pd.read_parquet(bc.DATA_PROCESSED / "splits_subject_level.parquet",
                            columns=["subject_id", "split"])
    return frame.set_index("subject_id")["split"]


def study_to_subject() -> pd.Series:
    """`study_id -> subject_id` over the clean cohort, for donor resolution."""
    cohort = bc.load_clean_cohort()
    return cohort.set_index("study_id")["subject_id"]


def split_frames(spec: TaskSpec) -> dict[str, pd.DataFrame]:
    directory = bc.TASKS_DIR / spec.key
    files = {"train": spec.train_file, "val": spec.val_file, "test": spec.test_file}
    out: dict[str, pd.DataFrame] = {}
    for split, filename in files.items():
        frame = pd.read_parquet(directory / filename)
        if "split" in frame.columns:
            frame = frame[frame["split"] == split]
        out[split] = frame.reset_index(drop=True)
    return out


def declared_split(spec: TaskSpec) -> dict[str, int]:
    """Rows whose `split` column disagrees with the file they are stored in.

    Read straight off the file, before any filtering -- `split_frames` filters
    on the split column, so by the time it has run a misfiled row is gone.
    """
    directory = bc.TASKS_DIR / spec.key
    files = {"train": spec.train_file, "val": spec.val_file, "test": spec.test_file}
    if len(set(files.values())) == 1:            # B6's one pointer table
        return {}
    wrong: dict[str, int] = {}
    for split, filename in files.items():
        column = pd.read_parquet(directory / filename, columns=["split"])["split"]
        wrong[split] = int((column != split).sum())
    return wrong


# -----------------------------------------------------------------------------
def audit_task(audit: ac.Audit, task_key: str, splits: pd.Series,
               s2s: pd.Series, log) -> None:
    spec = get_task(task_key)
    audit.heading(f"`{task_key}`", level=2)
    frames = split_frames(spec)

    # 1 -- the split column agrees with the file it is stored in
    wrong = declared_split(spec)
    if wrong:
        audit.check(task_key, "split_column_matches_file", sum(wrong.values()) == 0,
                    f"rows filed under the wrong split: {wrong}")
    else:
        audit.check(task_key, "split_column_matches_file", True,
                    "one pointer table for all three splits (§4.B.6.5); rows are "
                    "separated by the `split` column alone")

    subjects = {split: set(frame.subject_id.unique()) for split, frame in frames.items()}
    studies = {split: set(frame[spec.id_column].unique()) for split, frame in frames.items()}

    rows = []
    for split in bc.SPLITS:
        rows.append([split, f"{len(frames[split]):,}", f"{len(studies[split]):,}",
                     f"{len(subjects[split]):,}"])
    audit.table(["split", "rows", f"unique `{spec.id_column}`", "subjects"], rows)

    # 2 -- zero subject overlap, the §9.4 requirement
    pairs = [("train", "val"), ("train", "test"), ("val", "test")]
    overlaps = {f"{a}/{b}": len(subjects[a] & subjects[b]) for a, b in pairs}
    audit.check(task_key, "zero_subject_overlap", sum(overlaps.values()) == 0,
                f"pairwise subject intersections {overlaps}")

    # 3 -- agreement with the frozen global split
    all_rows = pd.concat(frames.values(), ignore_index=True)
    mapped = splits.reindex(all_rows.subject_id.to_numpy())
    unknown = int(mapped.isna().sum())
    disagree = int((mapped.to_numpy() != all_rows["split"].to_numpy()).sum()) - unknown
    audit.check(task_key, "subjects_exist_in_global_split", unknown == 0,
                f"{unknown} row(s) carry a subject absent from "
                f"splits_subject_level.parquet")
    audit.check(task_key, "split_matches_global_split", disagree == 0,
                f"{disagree} row(s) sit in a split other than the one the frozen "
                f"patient partition assigns (§4.C invariant 1)")

    # 4 -- no study crosses a split
    study_overlaps = {f"{a}/{b}": len(studies[a] & studies[b]) for a, b in pairs}
    audit.check(task_key, "zero_study_overlap", sum(study_overlaps.values()) == 0,
                f"pairwise {spec.id_column} intersections {study_overlaps}")

    # 5 -- donor containment, for the tasks whose rows point at other studies
    donors = [c for c in DONOR_COLUMNS if c in all_rows.columns]
    if donors:
        donor_rows = []
        for column in donors:
            donor_subject = s2s.reindex(all_rows[column].to_numpy())
            donor_split = splits.reindex(donor_subject.to_numpy())
            unresolved = int(donor_subject.isna().sum())
            crossing = int((donor_split.to_numpy() != all_rows["split"].to_numpy()).sum())
            audit.check(task_key, f"donor_in_same_split[{column}]",
                        unresolved == 0 and crossing == 0,
                        f"{unresolved} `{column}` value(s) resolve to no clean-cohort "
                        f"subject; {crossing} point at a subject in another split")

            negative = all_rows["y_match"].to_numpy() == 0
            swapped = all_rows[column].to_numpy() != all_rows[spec.id_column].to_numpy()
            same_subject = (donor_subject.to_numpy() == all_rows.subject_id.to_numpy())
            leaked = int((negative & swapped & same_subject).sum())
            audit.check(task_key, f"negative_donor_is_another_subject[{column}]", leaked == 0,
                        f"{leaked} negative row(s) take `{column}` from the anchor's own "
                        f"subject — that row would be a near-positive labelled negative")
            donor_rows.append([f"`{column}`", f"{int(swapped.sum()):,}",
                               f"{unresolved}", f"{crossing}", f"{leaked}"])
        audit.add("", "**Donor containment.** Each verification row points at up to three "
                      "studies; every one of them must belong to a subject in the row's "
                      "own split, and a swapped modality on a negative must come from a "
                      "different subject.", "")
        audit.table(["pointer column", "rows where it is not the anchor",
                     "unresolved", "crossing a split", "same-subject on a negative"],
                    donor_rows)

    # A5's masked-attribute sibling table is a second file per split
    if task_key == "A5_cross_modal_verification":
        sibling_bad, sibling_rows = 0, []
        for split in bc.SPLITS:
            masked = pd.read_parquet(
                bc.TASKS_DIR / task_key / f"masked_attribute_{split}.parquet",
                columns=["study_id", "subject_id", "split"])
            wrong_split = int((masked["split"] != split).sum())
            mapped = splits.reindex(masked.subject_id.to_numpy())
            wrong_global = int((mapped.to_numpy() != split).sum())
            sibling_bad += wrong_split + wrong_global
            sibling_rows.append([f"`masked_attribute_{split}.parquet`", f"{len(masked):,}",
                                 f"{masked.subject_id.nunique():,}", wrong_split,
                                 wrong_global])
        audit.table(["file", "rows", "subjects", "wrong split column",
                     "disagreeing with the global split"], sibling_rows)
        audit.check(task_key, "masked_attribute_files_respect_the_split", sibling_bad == 0,
                    f"{sibling_bad} row(s) across the three masked-attribute files sit in "
                    f"the wrong split")

    log.info("%s: %s", task_key, {s: len(f) for s, f in frames.items()})


def audit_global(audit: ac.Audit, splits: pd.Series) -> None:
    audit.heading("The frozen patient split this audit checks against")
    counts = splits.value_counts().to_dict()
    audit.add("`data/processed/splits_subject_level.parquet`, inherited from Phase 1 and "
              "never re-split (§4.C invariant 1, progress-doc trap 4). Every task is a "
              "subset of it; no task reshuffles it.", "")
    audit.table(["split", "subjects"],
                [[s, f"{counts.get(s, 0):,}"] for s in bc.SPLITS] +
                [["**all**", f"**{len(splits):,}**"]])
    audit.check("(global)", "global_split_is_a_partition",
                splits.index.is_unique and set(counts) == set(bc.SPLITS),
                f"{len(splits):,} subjects, each in exactly one of {sorted(counts)}")


def audit_b2_anchors(audit: ac.Audit) -> None:
    """The frozen B2 anchor set is a TEST-split sample (§4.B.2.2, §5 question 10)."""
    task_key = "B2_noise_robustness"
    frame = pd.concat([pd.read_parquet(bc.TASKS_DIR / task_key / f"{s}.parquet",
                                       columns=["subject_id", "split", "is_anchor"])
                       for s in bc.SPLITS], ignore_index=True)
    anchors = frame[frame.is_anchor.astype(bool)]
    seen = set(anchors.split.unique())
    audit.heading("B2 — the frozen anchor set stays in test", level=3)
    audit.add("The 1,871 anchors were frozen in Phase 1 Stage 8 and must never be "
              "regenerated. They are a test-split sample, so a train or val row flagged "
              "`is_anchor` would mean the frozen evaluation set had reached training.", "")
    audit.check(task_key, "frozen_anchors_are_test_only", seen == {"test"},
                f"{len(anchors):,} anchor rows over {anchors.subject_id.nunique():,} "
                f"subjects, all in {sorted(seen)}")


# -----------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", nargs="*", default=list(TASK_KEYS),
                        help="audit a subset (debugging only; a partial run records the "
                             "omission and therefore cannot PASS)")
    args = parser.parse_args()

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT)
    state.reset()
    started = time.time()
    bc.preflight([bc.TASKS_DIR, bc.DATA_PROCESSED / "splits_subject_level.parquet"],
                 need_free_gb=0.5)

    audit = ac.Audit(
        title="Split audit — Phase 2 tasks (Stage P2.3)",
        filename="split_audit_phase2.md",
        spec="§9.4 (Stage P2.3), §4.C invariant 1",
        script=f"{SCRIPT}.py",
        intro=[
            "§9.4 asks for zero subject overlap across train/val/test for every task. "
            "That is checked, and so are the four things it does not cover on its own: "
            "that each row's `split` column matches the file it is stored in; that every "
            "subject's split equals the frozen `splits_subject_level.parquet` rather "
            "than anything re-derived (§4.C invariant 1); that no study crosses a split; "
            "and — for A5 and B4, whose rows point at up to three different studies "
            "— that every pointed-at modality belongs to a subject in the row's own "
            "split, and that a swapped modality on a negative comes from a different "
            "subject than the anchor.",
            "",
            "A task can partition its own rows perfectly and still be wrong, if it "
            "partitioned them itself. The global-agreement check is what makes the "
            "twelve tasks consistent with each other and with Phase 1.",
        ],
    )

    splits = global_split()
    s2s = study_to_subject()
    audit_global(audit, splits)

    if sorted(args.tasks) != sorted(TASK_KEYS):
        audit.check("(global)", "every_task_audited", False,
                    f"only {args.tasks} were audited; §9.4 requires all 12")

    for task_key in args.tasks:
        audit_task(audit, task_key, splits, s2s, log)
    if "B2_noise_robustness" in args.tasks:
        audit_b2_anchors(audit)

    path = audit.write(log)
    state.finish(verdict=audit.verdict, n_checks=len(audit.checks),
                 n_violations=len(audit.violations),
                 report=str(path.relative_to(bc.PROJECT_ROOT)),
                 elapsed_s=round(time.time() - started, 1))
    log.info("split audit %s — %d checks, %d violations, %.1f s",
             audit.verdict, len(audit.checks), len(audit.violations), time.time() - started)
    return audit.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
```

### `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/audit_common.py`

```python
"""Shared plumbing for the three Stage P2.3 audits (spec §9.4).

`20_audit_tasks_leakage.py`, `21_audit_tasks_cohort.py` and
`22_audit_tasks_split.py` each produce one markdown report under
`outputs/audit_reports/`, and `30_train.py::check_audit_gate` reads all three
back before a single batch is loaded (§4.C invariant 4). That gate is a text
match, so the report format is a machine contract, not decoration:

* every report carries exactly one verdict line, `**VERDICT: PASS**` or
  `**VERDICT: FAIL**`, as its first non-heading line;
* :func:`report_verdict` is the ONE parser for that line, and `30_train.py`
  imports it rather than carrying a second copy.

The parser exists because the obvious implementation -- scan the whole report
for the substring "FAIL" -- is wrong on this dataset. A1's heads are named
`label_heart_failure_narrow` and friends, so a leakage audit that does its job
and lists every column emits the token inside a column name and a substring
scan reads a clean report as a blocked one. The verdict is a line, not a word
somewhere in the prose.

:meth:`Audit.write` parses its own rendered report back with
:func:`report_verdict` before the file lands, so an audit cannot emit a report
the gate would misread.

Nothing here decides what a check *is*; the three scripts do that. This module
owns the bookkeeping, the markdown, and the contract with the gate.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _dataset_lib import build_common as bc  # noqa: E402

AUDIT_DIR = bc.PROJECT_ROOT / "outputs" / "audit_reports"

# The verdict tokens `30_train.py::check_audit_gate` reads.
PASS = "PASS"
BLOCK = "FAIL"
NO_VERDICT = "NO_VERDICT"

VERDICT_LINE = re.compile(r"^\*\*VERDICT:\s*(PASS|FAIL)\*\*", re.MULTILINE)


def report_verdict(text: str) -> str:
    """`PASS`, `FAIL` or `NO_VERDICT` for one audit report's text.

    The single reader of the audit-gate contract (§4.C invariant 4). A report
    with no verdict line, or with two that disagree, is `NO_VERDICT` and blocks
    -- an audit that cannot state its own outcome has not run.
    """
    found = VERDICT_LINE.findall(text)
    if not found or len(set(found)) != 1:
        return NO_VERDICT
    return found[0]


@dataclass
class Check:
    """One assertion, its subject, and what it measured."""

    task: str
    check_id: str
    ok: bool
    detail: str

    @property
    def verdict(self) -> str:
        return PASS if self.ok else BLOCK


@dataclass
class Audit:
    """Collects checks and markdown blocks, then renders one audit report."""

    title: str
    filename: str
    spec: str
    script: str
    intro: Sequence[str] = ()
    checks: list[Check] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)

    # -- recording -------------------------------------------------------------
    def check(self, task: str, check_id: str, ok: bool, detail: str) -> bool:
        self.checks.append(Check(task, check_id, bool(ok), detail))
        return bool(ok)

    def add(self, *lines: str) -> None:
        self.blocks.extend(lines)

    def heading(self, text: str, level: int = 2) -> None:
        self.blocks += ["", "#" * level + " " + text, ""]

    def table(self, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
        self.blocks.append("| " + " | ".join(str(h) for h in header) + " |")
        self.blocks.append("| " + " | ".join("---" for _ in header) + " |")
        for row in rows:
            self.blocks.append("| " + " | ".join(_cell(v) for v in row) + " |")
        self.blocks.append("")

    # -- outcome ---------------------------------------------------------------
    @property
    def violations(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    @property
    def verdict(self) -> str:
        return BLOCK if self.violations else PASS

    def tasks(self) -> list[str]:
        seen: list[str] = []
        for check in self.checks:
            if check.task not in seen:
                seen.append(check.task)
        return seen

    def task_verdict(self, task: str) -> str:
        bad = [c for c in self.checks if c.task == task and not c.ok]
        return BLOCK if bad else PASS

    # -- rendering -------------------------------------------------------------
    def render(self) -> str:
        n_ok = len(self.checks) - len(self.violations)
        out: list[str] = [
            f"# {self.title}",
            "",
            f"**VERDICT: {self.verdict}** — {len(self.checks)} checks run, "
            f"{n_ok} passed, {len(self.violations)} violations.",
            "",
            f"Spec {self.spec}. Generated {bc.utc_now_iso()} by "
            f"`scripts/phase2_tasks_benchmark_and_paper/{self.script}` from the task "
            f"parquets on disk — every number below is measured, none is restated from "
            f"a builder's own report.",
            "",
        ]
        out += list(self.intro)
        out += ["", "## Verdict by task", ""]
        out.append("| Task | Checks | Verdict |")
        out.append("| --- | ---: | --- |")
        for task in self.tasks():
            n = sum(1 for c in self.checks if c.task == task)
            out.append(f"| `{task}` | {n} | **{self.task_verdict(task)}** |")
        out.append("")

        if self.violations:
            out += ["## Violations", "",
                    "Each of these is CRITICAL under §11.2 and blocks every training "
                    "stage. The fix belongs in the builder that produced the artifact, "
                    "not in this audit.", ""]
            out.append("| Task | Check | Detail |")
            out.append("| --- | --- | --- |")
            for check in self.violations:
                out.append(f"| `{check.task}` | `{check.check_id}` | {_cell(check.detail)} |")
            out.append("")

        out += self.blocks

        out += ["", "## Every check, in the order it ran", ""]
        out.append("| # | Task | Check | Verdict | Measured |")
        out.append("| ---: | --- | --- | --- | --- |")
        for i, check in enumerate(self.checks, 1):
            out.append(f"| {i} | `{check.task}` | `{check.check_id}` | {check.verdict} | "
                       f"{_cell(check.detail)} |")
        out += ["",
                "## Reproduce",
                "",
                "```",
                f"./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/"
                f"{self.script}",
                "```",
                "",
                "The audit reads only artifacts already on disk and writes only this "
                "report, so it is safe to re-run at any time.",
                ""]
        return "\n".join(out)

    def write(self, log: Any = None) -> Path:
        """Render, enforce the gate contract, then land the file atomically."""
        text = self.render()
        parsed = report_verdict(text)
        if parsed != self.verdict:
            raise RuntimeError(
                f"{self.filename} would be read by the training gate as {parsed!r} "
                f"while this audit's own verdict is {self.verdict!r}. The report is "
                f"not written; fix the renderer before anything reads it."
            )
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        path = AUDIT_DIR / self.filename
        tmp = path.with_suffix(".md.tmp")
        tmp.write_text(text, encoding="utf-8")
        bc.atomic_replace(tmp, path)
        if log is not None:
            log.info("%s — %s (%d checks, %d violations) -> %s",
                     self.title, self.verdict, len(self.checks), len(self.violations),
                     path.relative_to(bc.PROJECT_ROOT))
        return path

    def exit_code(self) -> int:
        return 0 if self.verdict == PASS else 1


def _cell(value: Any) -> str:
    """Markdown-table-safe one-line rendering of a value."""
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= 300 else text[:297] + "..."


def fmt_counts(counts: dict[Any, int], top: int | None = None) -> str:
    """`a 3 · b 1` — deterministic, compact, and safe inside a table cell."""
    items = sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))
    if top:
        items = items[:top]
    return " · ".join(f"{k} {v:,}" for k, v in items) or "(none)"


def _self_check() -> None:
    """The gate contract is the only thing here worth a test."""
    good = Audit(title="t", filename="_selfcheck.md", spec="§9.4", script="audit_common.py")
    good.check("A1", "c1", True, "0 violations")
    assert good.verdict == PASS
    assert report_verdict(good.render()) == PASS

    bad = Audit(title="t", filename="_selfcheck.md", spec="§9.4", script="audit_common.py")
    bad.check("A1", "c1", False, "1 forbidden column")
    assert bad.verdict == BLOCK and report_verdict(bad.render()) == BLOCK
    assert bad.exit_code() == 1

    # The reason the parser exists: A1's head names carry the block token, and a
    # substring scan would read this clean report as a blocked one.
    collides = Audit(title="t", filename="_selfcheck.md", spec="§9.4",
                     script="audit_common.py")
    collides.check("A1_ecg_diagnosis", "c1", True, "head `label_heart_failure_narrow` ok")
    assert collides.verdict == PASS
    assert BLOCK in collides.render().upper(), "this fixture is pointless if it does not collide"
    assert report_verdict(collides.render()) == PASS, \
        "a column name containing the token must not flip the verdict"

    assert report_verdict("no verdict line here") == NO_VERDICT
    assert report_verdict("**VERDICT: PASS**\n**VERDICT: FAIL**") == NO_VERDICT

    assert fmt_counts({"b": 1, "a": 3}) == "a 3 · b 1"
    print("audit_common self-check: PASS  (verdict parser holds, and survives a "
          "column name that contains the token)")


if __name__ == "__main__":
    _self_check()
```

## 6. Validation results

- **`leakage_audit_phase2.md`** — **VERDICT: PASS** — 88 checks run, 88 passed, 0 violations.  (72.1 KB, written by `20_audit_tasks_leakage.py`)
- **`cohort_audit.md`** — **VERDICT: PASS** — 184 checks run, 184 passed, 0 violations.  (87.8 KB, written by `21_audit_tasks_cohort.py`)
- **`split_audit_phase2.md`** — **VERDICT: PASS** — 75 checks run, 75 passed, 0 violations.  (18.3 KB, written by `22_audit_tasks_split.py`)

- **§4.C invariant 4 audit gate: OPEN.** `30_train.py::check_audit_gate` reads exactly these three files and parses their `**VERDICT:**` line; measured now, it returns {'leakage_audit_phase2.md': 'PASS', 'cohort_audit.md': 'PASS', 'split_audit_phase2.md': 'PASS'}.

- Per-script check counts, read from the state files:
  - `20_audit_tasks_leakage` — PASS, 88 checks, 0 violations, 69.8 s
  - `21_audit_tasks_cohort` — PASS, 184 checks, 0 violations, 55.5 s
  - `22_audit_tasks_split` — PASS, 75 checks, 0 violations, 27.7 s

- **`threshold_audit.md` is deliberately still absent.** §9.4 lists it as a pre-flight artifact with empty threshold values; `_train_lib/threshold.py` appends to it, and only a full-scale `30_train.py` run has thresholds to append. Nothing in Stage P2.3 selects a threshold.

- Pre-flight: PASS — every builder calls `build_common.preflight()`, which asserts its inputs exist and records free disk and free RAM before any work starts. Phase 1 completion was verified at Stage P2.0 and is unchanged.

### Per-script validation (read back from the state files)

**`20_audit_tasks_leakage`** — PASS

```json
{
  "done": true,
  "finished_at": "2026-08-27T12:11:01Z",
  "verdict": "PASS",
  "n_checks": 88,
  "n_violations": 0,
  "report": "outputs\\audit_reports\\leakage_audit_phase2.md",
  "elapsed_s": 69.8
}
```

**`21_audit_tasks_cohort`** — PASS

```json
{
  "done": true,
  "finished_at": "2026-08-27T12:18:20Z",
  "verdict": "PASS",
  "n_checks": 184,
  "n_violations": 0,
  "report": "outputs\\audit_reports\\cohort_audit.md",
  "elapsed_s": 55.5
}
```

**`22_audit_tasks_split`** — PASS

```json
{
  "done": true,
  "finished_at": "2026-08-27T12:21:20Z",
  "verdict": "PASS",
  "n_checks": 75,
  "n_violations": 0,
  "report": "outputs\\audit_reports\\split_audit_phase2.md",
  "elapsed_s": 27.7
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
525:                   mininterval=0.5, desc=desc or name)
```

- Disk free at report time: 177.0 GB on D:\

## 7. Manual test procedure

```
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/audit_common.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/20_audit_tasks_leakage.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/21_audit_tasks_cohort.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/22_audit_tasks_split.py
```

Each audit exits 0 on PASS and 1 on a violation, reads only artifacts already on disk, and writes only its own report — so all three are safe to re-run at any time, and re-running them is the intended way to re-open the training gate after any rebuild. `audit_common.py` runs the gate-contract self-check.

The gate itself can be exercised directly:

```
./ecg_env/Scripts/python.exe -c "import sys, logging; sys.path.insert(0, 'scripts/phase2_tasks_benchmark_and_paper'); import importlib.util as u; s = u.spec_from_file_location('t', 'scripts/phase2_tasks_benchmark_and_paper/30_train.py'); m = u.module_from_spec(s); s.loader.exec_module(m); print(m.check_audit_gate(False, logging.getLogger()))"
```

## 8. Assumptions requiring user confirmation

- **The declared-provenance allowlist is a reading of §4, and a reviewer may disagree with an entry**  ::  `20_audit_tasks_leakage.py::PROVENANCE` names every column that stays in a task parquet despite naming a forbidden quantity, each with its section. The strongest case is A2/B1's `hr_bpm`/`qrs_ms`/`qtc_ms`, which §4.A.2.5 marks `# provenance` in the schema itself; the ones worth a second look are B5's `source_measurement` (non-null exactly on the corrupted rows, so it is label-equivalent) and A6's `days_to_death`/`days_to_readmission`. None is reachable — gate 3 checks the tensor keys — but if a reviewer would rather they were not on disk at all, that is a builder change plus a rebuild of that task, not an audit change.
- **A3's `abnormal_unknown_direction` class is effectively empty**  ::  1 row in 500,471, in the test split, and it is the only row where §4.A.3.3's `flag`-only branch fired. Troponin has no `low_abnormal` row at all. Both are reported rather than failed, and `multiclass_macro_auprc` averages over the classes present. If the paper needs a per-class row for every declared class, those cells will be empty by construction and should be marked n/a rather than 0.
- **B6's hard tier is still empty**  ::  the audit checks the tier vocabulary against `task_definitions.yaml`, where `hard` is `RESERVED` with an empty `neg_types` list (progress-doc question 13's default). The check passes because the config and the data agree; it would start failing the moment the tier is given members without the pointer table being rebuilt.
- **`threshold_audit.md` is not produced by this stage**  ::  §9.4 lists a pre-flight version with empty threshold values, but nothing in P2.3 selects a threshold and `_train_lib/threshold.py` appends the file's rows on the first full-scale training run. The three audits the §4.C gate actually reads are all present and PASS.
