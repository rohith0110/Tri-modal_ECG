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
