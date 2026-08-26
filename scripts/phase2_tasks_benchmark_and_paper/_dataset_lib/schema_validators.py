"""Pydantic schemas + the Stage P2.0 validation gate (spec §9.1).

Run it:

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/schema_validators.py

Every check in the spec §9.1 "Validation" list is implemented here except the
``read_modality`` resolution check, which lives in ``modality.py`` next door and
is invoked from this runner. The gate is re-runnable and read-only: it asserts,
it never repairs.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG = PROJECT_ROOT / "config"
SCRIPTS = PROJECT_ROOT / "scripts"
PHASE2_SCRIPTS = SCRIPTS / "phase2_tasks_benchmark_and_paper"
LEGACY_DIR = PHASE2_SCRIPTS / "_legacy_phase1_pre_regen"

# --- the locked enums (spec §2.6, §4) ----------------------------------------
MODALITY_KINDS = {
    "raw_lead2",
    "raw_12lead",
    "preprocessed_lead2",
    "preprocessed_12lead",
    "image_clean_lead2",
    "image_clean_12lead",
    "image_scanlike_lead2",
    "image_scanlike_12lead",
    "signal_corrupted",
}
NON_MODALITY_REFS = {
    "report_text",
    "report_text_masked",
    "machine_measurements",
    "structured_features",
}
VALID_POLICY_REFS = MODALITY_KINDS | NON_MODALITY_REFS

TASK_KEYS = [
    "A1_ecg_diagnosis",
    "A2_measurement_blind",
    "A3_lab_abnormality",
    "A4_event_localization",
    "A5_cross_modal_verification",
    "A6_risk_stratification",
    "B1_measurement_blind",
    "B2_noise_robustness",
    "B3_temporal_grounding",
    "B4_cross_modal_verification",
    "B5_contradiction_detection",
    "B6_difficulty_stratified",
]

ICD_GROUPS = [
    "atrial_fibrillation_flutter",
    "heart_failure_narrow",
    "acute_myocardial_infarction",
    "conduction_disorder",
    "ventricular_arrhythmia_or_arrest",
]
LAB_KEYS = ["K", "Na", "creatinine", "troponin", "lactate", "Ca", "Mg"]
LAB_WINDOWS = ["pm24h", "pre_24h", "post_24h", "pm6h", "pm12h"]
LAB_CLASSES = [
    "missing",
    "low_abnormal",
    "high_abnormal",
    "abnormal_unknown_direction",
    "normal",
]
CORRUPTION_FAMILIES = [
    "gaussian",
    "baseline_wander",
    "powerline",
    "emg",
    "electrode_motion",
    "lead_dropout",
    "gain_drift",
    "saturation",
]
SNR_LEVELS_DB = [30, 20, 10, 5, 0]
B5_FAMILIES = ["HR", "QRS", "axis", "PR"]

SEEDS = [42, 123, 456]


# =============================================================================
# Pydantic schemas for the four LOCKED YAMLs
# =============================================================================
class _Strict(BaseModel):
    model_config = ConfigDict(extra="allow")  # provenance blocks are additive


class IcdGroup(_Strict):
    icd10_prefix: list[str] = Field(default_factory=list)
    icd10_exact_optional: list[str] = Field(default_factory=list)
    icd9_prefix: list[str] = Field(default_factory=list)
    icd9_exact: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _non_empty(self):
        if not (
            self.icd10_prefix or self.icd10_exact_optional or self.icd9_prefix or self.icd9_exact
        ):
            raise ValueError("ICD group matches nothing -- every group needs >= 1 pattern")
        return self


class IcdLabelMap(_Strict):
    lock: dict[str, Any]
    groups: dict[str, IcdGroup]
    validation_at_lock: dict[str, Any]

    @field_validator("groups")
    @classmethod
    def _exact_groups(cls, v):
        if sorted(v) != sorted(ICD_GROUPS):
            raise ValueError(f"expected exactly the 5 Round-2.1 groups, got {sorted(v)}")
        return v


class LabItem(_Strict):
    itemid: int
    label: str
    fluid: str
    category: str
    n_events: int

    @field_validator("fluid")
    @classmethod
    def _blood_only(cls, v):
        if v != "Blood":
            raise ValueError(f"Appendix C step 2 permits serum/blood only, got fluid={v!r}")
        return v


class LabEntry(_Strict):
    label: str
    itemids: list[int]
    items: list[LabItem]

    @model_validator(mode="after")
    def _items_match_itemids(self):
        if [i.itemid for i in self.items] != self.itemids:
            raise ValueError(
                f"{self.label}: items[] itemids {[i.itemid for i in self.items]} "
                f"!= itemids {self.itemids}"
            )
        return self


class LabWindow(_Strict):
    primary: bool
    lower_hours: int
    upper_hours: int
    description: str

    @model_validator(mode="after")
    def _ordered(self):
        if self.lower_hours >= self.upper_hours:
            raise ValueError(f"window {self.description!r}: lower >= upper")
        return self


class LabItemIdMap(_Strict):
    lock: dict[str, Any]
    labs: dict[str, LabEntry]
    windows: dict[str, LabWindow]
    label_rule: dict[str, Any]
    coverage_gate: dict[str, Any]
    excluded_candidates: list[dict[str, Any]]

    @field_validator("labs")
    @classmethod
    def _exact_labs(cls, v):
        if sorted(v) != sorted(LAB_KEYS):
            raise ValueError(f"expected the 7-lab Round-2.2 universe, got {sorted(v)}")
        return v

    @field_validator("windows")
    @classmethod
    def _exact_windows(cls, v):
        if sorted(v) != sorted(LAB_WINDOWS):
            raise ValueError(f"expected the 5 §4.A.3.3 windows, got {sorted(v)}")
        if sum(1 for w in v.values() if w.primary) != 1:
            raise ValueError("exactly one window must be primary (pm24h)")
        return v

    @model_validator(mode="after")
    def _rule_and_gate(self):
        classes = self.label_rule.get("classes")
        if classes != LAB_CLASSES:
            raise ValueError(f"label_rule.classes must be the 5 §4.A.3.3 classes, got {classes}")
        if self.label_rule.get("missing_class_is_real") is not True:
            raise ValueError("the 'missing' class is a real class and must not be dropped")
        gate = self.coverage_gate
        threshold = float(gate["threshold_pct"])
        for lab in gate["gate_labs"]:
            pct = float(gate["coverage_pm24h_pct"][lab])
            if pct < threshold:
                raise ValueError(
                    f"§4.A.3.2 step 5: {lab} coverage {pct} % < {threshold} % -- the locked lab "
                    f"set must downgrade to the 5-lab default"
                )
        return self


class CorruptionFamily(_Strict):
    order: int
    kind: Literal["additive", "replacement", "multiplicative", "clipping"]
    snr_semantics: Literal["power_ratio", "severity"]
    description: str
    params: dict[str, Any]


class CorruptionRecipes(_Strict):
    lock: dict[str, Any]
    frozen_test_set: dict[str, Any]
    signal_geometry: dict[str, Any]
    snr_levels_db: list[int]
    noise_scaling: dict[str, Any]
    rng: dict[str, Any]
    families: dict[str, CorruptionFamily]
    regimes: dict[str, Any]

    @field_validator("snr_levels_db")
    @classmethod
    def _exact_snr(cls, v):
        if v != SNR_LEVELS_DB:
            raise ValueError(f"SNR ladder must be {SNR_LEVELS_DB}, got {v}")
        return v

    @field_validator("families")
    @classmethod
    def _exact_families(cls, v):
        if sorted(v) != sorted(CORRUPTION_FAMILIES):
            raise ValueError(f"expected the 8 Stage-8 families, got {sorted(v)}")
        if sorted(f.order for f in v.values()) != list(range(8)):
            raise ValueError("family `order` must be a permutation of 0..7")
        return v

    @model_validator(mode="after")
    def _frozen_and_disjoint(self):
        fts = self.frozen_test_set
        expected = int(fts["anchors_materialised"]) * len(CORRUPTION_FAMILIES) * len(SNR_LEVELS_DB)
        if int(fts["n_rows"]) != expected:
            raise ValueError(
                f"frozen_test_set.n_rows {fts['n_rows']} != anchors x 8 x 5 = {expected}"
            )
        if self.lock.get("regeneration_in_phase2") != "forbidden":
            raise ValueError("Phase 2 must never regenerate the corrupted test set (§9.3)")
        test_key = self.rng["test_set"]["key_template"]
        train_key = self.rng["train_augmentation"]["key_template"]
        if test_key == train_key:
            raise ValueError(
                "regime_2 train-time corruption must use a DIFFERENT RNG stream than the "
                "frozen test set (§7.3) -- the key templates are identical"
            )
        if not train_key.startswith("regime2|"):
            raise ValueError("the train_augmentation key needs a literal salt to guarantee disjointness")
        return self


class ClearZone(_Strict):
    condition: str
    truth: str
    spec: str


class FreeZone(_Strict):
    lower: float
    upper: float
    rule: str

    @model_validator(mode="after")
    def _ordered(self):
        if self.lower >= self.upper:
            raise ValueError(f"injection-free zone lower {self.lower} >= upper {self.upper}")
        return self


class SurfaceForm(_Strict):
    polarity: str
    pattern: str
    replace_with: str

    @field_validator("pattern")
    @classmethod
    def _compiles(cls, v):
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"surface-form pattern {v!r} is not a valid regex: {exc}") from exc
        return v


class ClaimFamily(_Strict):
    order: int
    measurement: str
    clear_zones: dict[str, ClearZone]
    injection_free_zone: FreeZone
    surface_forms: list[SurfaceForm]

    @model_validator(mode="after")
    def _polarity_and_zones(self):
        zones = set(self.clear_zones)
        if len(zones) != 2:
            raise ValueError(f"family expects exactly 2 clear zones, got {sorted(zones)}")
        for form in self.surface_forms:
            if form.polarity not in zones:
                raise ValueError(
                    f"surface form polarity {form.polarity!r} is not one of the clear "
                    f"zones {sorted(zones)}"
                )
        return self


class ClaimDictionary(_Strict):
    lock: dict[str, Any]
    report_text: dict[str, Any]
    measurement_source: dict[str, Any]
    validity: dict[str, Any]
    families: dict[str, ClaimFamily]
    injection_policy: dict[str, Any]

    @field_validator("families")
    @classmethod
    def _exact_families(cls, v):
        if sorted(v) != sorted(B5_FAMILIES):
            raise ValueError(f"expected the 4 Round-2 B5 families, got {sorted(v)}")
        return v

    @model_validator(mode="after")
    def _sentinel_and_swap(self):
        if int(self.validity["missing_sentinel"]) != 29999:
            raise ValueError("the machine-measurement missing sentinel is 29999")
        if self.injection_policy.get("swap_only") is not True:
            raise ValueError(
                "§4.B.5.3 specifies a SWAP with a recorded span; inserting a claim the "
                "report never made is not permitted"
            )
        for name, fam in self.families.items():
            if fam.measurement not in self.validity["plausible_range"]:
                raise ValueError(
                    f"family {name}: measurement {fam.measurement!r} has no plausible_range"
                )
        return self


# =============================================================================
# the gate
# =============================================================================
class Gate:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.n_checks = 0

    def check(self, name: str, fn) -> None:
        self.n_checks += 1
        try:
            detail = fn()
        except Exception as exc:  # noqa: BLE001 - the gate reports, it does not raise
            self.failures.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"  FAIL  {name}\n          {type(exc).__name__}: {exc}")
        else:
            print(f"  PASS  {name}" + (f"  ({detail})" if detail else ""))


def _load(name: str) -> dict:
    with open(CONFIG / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def run() -> int:
    gate = Gate()

    print("\n[1] LOCKED YAMLs -- Pydantic schema validation")
    icd = _load("icd_label_map_LOCKED.yaml")
    lab = _load("lab_itemid_map_LOCKED.yaml")
    corr = _load("corruption_recipes_LOCKED.yaml")
    claim = _load("claim_dictionary_LOCKED.yaml")
    gate.check("icd_label_map_LOCKED.yaml", lambda: f"{len(IcdLabelMap(**icd).groups)} groups")
    gate.check("lab_itemid_map_LOCKED.yaml", lambda: f"{len(LabItemIdMap(**lab).labs)} labs x 5 windows")
    gate.check("corruption_recipes_LOCKED.yaml", lambda: f"{len(CorruptionRecipes(**corr).families)} families x 5 SNRs")
    gate.check("claim_dictionary_LOCKED.yaml", lambda: f"{len(ClaimDictionary(**claim).families)} families")

    print("\n[2] LOCKED YAMLs -- cross-checks against Phase 1 artifacts")

    def _labs_match_key_labs():
        key_labs = _load("key_labs.yaml")["key_labs"]
        mismatched = {
            k: (sorted(lab["labs"][k]["itemids"]), sorted(key_labs[k]["itemids"]))
            for k in LAB_KEYS
            if sorted(lab["labs"][k]["itemids"]) != sorted(key_labs[k]["itemids"])
        }
        if mismatched:
            raise AssertionError(f"itemids drifted from key_labs.yaml: {mismatched}")
        return f"{sum(len(v['itemids']) for v in key_labs.values())} itemids identical to key_labs.yaml"

    gate.check("lab itemids == config/key_labs.yaml", _labs_match_key_labs)

    def _corruption_matches_stage8():
        src = (
            SCRIPTS / "phase1_dataset_generation" / "50_build_signals_corrupted.py"
        ).read_text(encoding="utf-8")
        snr = re.search(r"^SNR_LEVELS_DB = (\[.*?\])", src, re.M)
        fams = re.search(r"^CORRUPTIONS = \[(.*?)\]", src, re.M | re.S)
        assert snr and fams, "could not parse the Stage 8 constants"
        stage8_snr = eval(snr.group(1))  # noqa: S307 - a literal list in our own repo
        stage8_fams = re.findall(r'"([a-z_]+)"', fams.group(1))
        assert stage8_snr == corr["snr_levels_db"], f"SNR drift: {stage8_snr} vs {corr['snr_levels_db']}"
        assert stage8_fams == sorted(corr["families"], key=lambda k: corr["families"][k]["order"]), (
            f"family drift: {stage8_fams} vs {sorted(corr['families'])}"
        )
        return f"{len(stage8_fams)} families and {len(stage8_snr)} SNRs match Stage 8 source"

    gate.check("corruption recipe == Stage 8 constants", _corruption_matches_stage8)

    def _decision_gate_unmutated():
        d1 = _load("decision.yaml")
        d2 = _load("decision_phase2.yaml")
        inherited = d2["inherited_from_phase1"]
        assert d1["frozen_at"] == inherited["decision_yaml_frozen_at"], (
            f"decision.yaml mutated since the Phase 2 lock: {d1['frozen_at']} != "
            f"{inherited['decision_yaml_frozen_at']} -- re-confirm (§2.3)"
        )
        assert d1["chosen_path"] == inherited["chosen_path"] == "plan_a"
        assert d1["linkage_distribution"] == inherited["linkage_distribution"]
        return f"chosen_path=plan_a frozen_at={d1['frozen_at']}"

    gate.check("decision.yaml inheritance (§2.3)", _decision_gate_unmutated)

    print("\n[3] task_definitions.yaml (§4)")
    td = _load("task_definitions.yaml")

    def _td_keys():
        got = list(td["tasks"])
        assert got == TASK_KEYS, f"expected the 12 §4 keys in order, got {got}"
        return "12/12 task keys"

    gate.check("all 12 task keys present", _td_keys)

    def _td_blocks():
        missing = {}
        for key, block in td["tasks"].items():
            need = ["plan", "name", "spec_section", "description", "cohort", "targets", "metrics",
                    "baselines", "sensitivity_analyses"]
            gaps = [f for f in need if f not in block]
            if gaps:
                missing[key] = gaps
        assert not missing, f"incomplete task blocks: {missing}"
        return "every task carries cohort / targets / metrics / baselines / sensitivity"

    gate.check("each block matches the §4 layout", _td_blocks)

    def _td_shared_defs():
        bins = td["shared_label_defs"]["measurement_bins"]

        def classes(head):
            # `note` is prose alongside the class rules, not a class.
            return {k for k in bins[head] if k != "note"}

        for head, expected in (
            ("hr_label", {"bradycardia", "normal", "tachycardia"}),
            ("qrs_label", {"normal", "borderline", "wide"}),
            ("qtc_label", {"short", "normal", "prolonged"}),
        ):
            got = classes(head)
            assert got == expected, f"{head}: {sorted(got)} != {sorted(expected)}"
        assert int(bins["validity"]["missing_sentinel"]) == 29999
        assert set(td["shared_label_defs"]["negative_types"]) == {
            "TEXT_SWAP", "IMAGE_SWAP", "SIGNAL_SWAP", "HARD_NEGATIVE_TEXT", "PARTIAL_MISMATCH"
        }
        return "HR/QRS/QTc bins + 5 negative types + sentinel rule"

    gate.check("shared label definitions (§4.A.2.3)", _td_shared_defs)

    def _td_meta():
        assert td["meta"]["seeds"] == SEEDS
        assert td["meta"]["bootstrap"]["n_iter"] == 10000
        assert td["meta"]["bootstrap"]["method"] == "bca"
        assert "splits_subject_level.parquet" in td["meta"]["split_source"]
        for key in ("no_subject_in_two_splits", "deterministic_provenance",
                    "manifest_passthrough", "audit_gate_before_training"):
            assert key in td["invariants"], f"missing §4.C invariant {key}"
        return "seeds 42/123/456, bootstrap 10000 BCa, 4 §4.C invariants"

    gate.check("meta + §4.C invariants", _td_meta)

    print("\n[4] task_input_policy.yaml (§4.X.4, §2.6)")
    tip = _load("task_input_policy.yaml")

    def _tip_keys():
        got = list(tip["tasks"])
        assert sorted(got) == sorted(TASK_KEYS), f"expected the 12 §4 keys, got {got}"
        return "12/12 task keys"

    gate.check("all 12 task keys present", _tip_keys)

    def _tip_refs():
        bad = {}
        for key, block in tip["tasks"].items():
            for field in ("allowed_inputs", "forbidden_inputs"):
                unknown = [v for v in block[field] if v not in VALID_POLICY_REFS]
                if unknown:
                    bad[f"{key}.{field}"] = unknown
        assert not bad, f"references outside the §2.6 enum: {bad}"
        return "every allowed/forbidden entry is a locked modality kind or a valid text reference"

    gate.check("every entry is a valid reference", _tip_refs)

    def _tip_disjoint():
        bad = {}
        for key, block in tip["tasks"].items():
            overlap = set(block["allowed_inputs"]) & set(block["forbidden_inputs"])
            if overlap:
                bad[key] = sorted(overlap)
            if not block.get("leakage_rationale", "").strip():
                bad[f"{key}.leakage_rationale"] = "empty"
        assert not bad, f"policy defects: {bad}"
        return "allowed and forbidden are disjoint; every task states a rationale"

    gate.check("allowed/forbidden disjoint + rationale present", _tip_disjoint)

    def _tip_enum():
        assert set(tip["modality_kind_enum"]) == MODALITY_KINDS, "the §2.6 enum drifted"
        return f"{len(MODALITY_KINDS)} locked kinds"

    gate.check("modality_kind_enum == §2.6", _tip_enum)

    def _tip_measurement_blind():
        # The three measurement-blind tasks must forbid every non-signal input,
        # because their labels ARE the machine measurements.
        for key in ("A2_measurement_blind", "B1_measurement_blind", "B2_noise_robustness"):
            forbidden = set(tip["tasks"][key]["forbidden_inputs"])
            for must in ("report_text", "machine_measurements", "structured_features"):
                assert must in forbidden, f"{key} must forbid {must}"
            assert not any(v.startswith("image_") for v in tip["tasks"][key]["allowed_inputs"]), (
                f"{key} must not allow image inputs"
            )
        return "A2 / B1 / B2 are strictly signal-only"

    gate.check("measurement-blind tasks are signal-only", _tip_measurement_blind)

    print("\n[5] decision_phase2.yaml (§5 + §6 + §7 + §8)")
    dp = _load("decision_phase2.yaml")

    def _dp_arch():
        arch = dp["architecture"]
        assert arch["signal_encoder"]["name"] == "ECGResNet1D18"
        assert arch["signal_encoder"]["pretrained"] is False
        assert arch["image_encoder"]["name"] == "ImageResNet50"
        assert "IMAGENET1K_V2" in arch["image_encoder"]["backbone"]
        assert arch["text_encoders"]["primary"]["hf_id"] == "emilyalsentzer/Bio_ClinicalBERT"
        assert arch["text_encoders"]["supplementary"]["name"] == "TfidfTextEncoder"
        assert arch["text_encoders"]["both_trained_for_every_text_task"] is True
        assert arch["fusion_head"]["style"] == "late_concat_mlp"
        assert arch["fusion_head"]["concat_dim"] == 1539
        assert arch["fusion_training_mode"]["mode"] == "end_to_end_fine_tuned"
        assert arch["fusion_training_mode"]["encoders_frozen"] is False
        pm = arch["primary_modalities"]
        assert (pm["signal"], pm["image"], pm["lead_set"]) == ("preprocessed", "clean", "12-lead")
        return "resnet18_1d / resnet50_imagenet / tfidf+bio_clinicalbert / late_concat_mlp, end-to-end"

    gate.check("architecture recorded verbatim (§5)", _dp_arch)

    def _dp_training():
        tr = dp["training"]
        assert tr["seeds"] == SEEDS
        assert tr["determinism"]["cudnn_deterministic"] is True
        assert tr["determinism"]["cudnn_benchmark"] is False
        assert tr["optimizer"]["name"] == "AdamW"
        lrs = tr["learning_rates"]
        assert (lrs["head"], lrs["image_backbone"], lrs["text_backbone_layers"],
                lrs["text_embeddings"]) == (1e-3, 1e-5, 1e-5, 1e-6)
        assert tr["gradient_clipping"]["value"] == 1.0
        assert tr["threshold_selection"]["never_tuned_on_test"] is True
        assert tr["checkpointing"]["retention_policy"] == "best_only_evicted_on_completion"
        assert tr["checkpointing"]["resident_budget_gb"] == 5
        return "seeds, AdamW, discriminative LRs, val-only thresholds, best-only checkpoints"

    gate.check("training infrastructure recorded (§6)", _dp_training)

    def _dp_eval():
        ev = dp["evaluation"]
        b = ev["bootstrap"]
        assert (b["method"], b["n_iter"], b["unit"]) == ("bca", 10000, "patient")
        assert b["fallback"] == "percentile"
        assert ev["retrieval_pool"]["size"] == 100
        assert "AUPRC" in ev["primary_metric_policy"]
        return "bootstrap 10000 BCa patient-level, AUPRC primary"

    gate.check("evaluation regimes recorded (§7)", _dp_eval)

    def _dp_compute():
        c = dp["compute"]["primary"]
        assert c["hardware"] == "NVIDIA DGX A100"
        assert c["scheduler"] == "slurm"
        assert c["partitions"] == {"cpu": "cpu_student", "gpu": "gpu_student"}
        assert c["storage_quota_gb"] == 50
        assert c["mixed_precision_resolved"] == "bf16"
        dr = dp["data_residency"]
        assert dr["chunking"]["key"] == "hash of study_id"
        assert dr["chunking"]["cycling"] == "within_epoch"
        assert dr["chunking"]["sequential_per_chunk_training"] == "forbidden"
        assert dr["chunking"]["modality_aligned"] is True
        assert dp["compute"]["development"]["interpreter"].endswith("ecg_env/Scripts/python.exe")
        return "DGX A100 identity, Slurm partitions, 50 GB quota, within-epoch chunk cycling"

    gate.check("DGX identity + data residency (§8)", _dp_compute)

    def _dp_queue():
        q = dp["training_queue"]
        assert q["plan_a_order"][0] == "A2_measurement_blind"
        assert q["plan_a_order"][-1] == "A5_cross_modal_verification"
        assert q["arch_tier_order"] == [
            "algorithmic_baseline", "signal_only", "image_only", "text_only", "multimodal"
        ]
        assert q["seed_order"] == SEEDS
        assert sorted(q["plan_a_order"] + q["plan_b_order"]) == sorted(TASK_KEYS)
        return "Round 4.2 order, 12 tasks, 5 arch tiers, 3 seeds"

    gate.check("training-queue order (§8.3)", _dp_queue)

    print("\n[6] quarantine (§2.4)")

    def _quarantine():
        assert LEGACY_DIR.is_dir(), f"{LEGACY_DIR} does not exist"
        moved = sorted(p.name for p in LEGACY_DIR.glob("*.py"))
        assert moved, "the legacy directory holds no scripts"
        stragglers = sorted(p.name for p in PHASE2_SCRIPTS.glob("*.py"))
        assert not stragglers, f"pre-regen scripts still at the origin path: {stragglers}"
        for slot in ("01_task_A_verification.py", "06_task_B5_contradiction_detection.py",
                     "20_train_B1_bank.py", "30_neurokit2_baseline_B1.py",
                     "40_aggregate_seeds.py", "50_benchmark_figures.py", "60_find_examples.py"):
            assert slot in moved, f"{slot} was not quarantined"
        return f"{len(moved)} scripts moved, 0 left at the origin path"

    gate.check("legacy scripts quarantined, origin clear", _quarantine)

    def _task_jsonl_gone():
        legacy = PROJECT_ROOT / "data" / "processed" / "task_jsonl"
        assert not legacy.exists(), f"{legacy} still exists -- §2.4 step 1 is not satisfied"
        return "data/processed/task_jsonl/ absent"

    gate.check("legacy task_jsonl removed", _task_jsonl_gone)

    print("\n[7] scaffolded tree (§3, §9.1 item 9)")

    def _scaffold():
        required = [
            "outputs/stage_reports", "outputs/results", "outputs/tables", "outputs/figures",
            "outputs/audit_reports", "outputs/model_runs", "outputs/release_package",
            "outputs/tables/main", "outputs/tables/supplementary",
            "outputs/figures/main", "outputs/figures/supplementary",
            "data/processed/tasks", "data/processed/dev_sample",
            "config/model_configs", "config/eval_configs",
            "scripts/dgx_portability", "scripts/dgx_portability/slurm",
            "scripts/phase2_tasks_benchmark_and_paper/_dataset_lib",
            "scripts/phase2_tasks_benchmark_and_paper/_model_lib",
            "scripts/phase2_tasks_benchmark_and_paper/_train_lib",
        ]
        missing = [d for d in required if not (PROJECT_ROOT / d).is_dir()]
        assert not missing, f"missing directories: {missing}"
        readmes = ["outputs/results", "outputs/release_package", "outputs/tables",
                   "outputs/figures", "outputs/model_runs", "data/processed/tasks",
                   "config/model_configs", "config/eval_configs", "scripts/dgx_portability"]
        no_readme = [d for d in readmes if not (PROJECT_ROOT / d / "README.md").is_file()]
        assert not no_readme, f"scaffolded without a placeholder README: {no_readme}"
        return f"{len(required)} directories, {len(readmes)} placeholder READMEs"

    gate.check("output + script tree scaffolded", _scaffold)

    print("\n[8] read_modality (§2.1)")

    def _modality():
        sys.path.insert(0, str(PHASE2_SCRIPTS))
        from _dataset_lib import modality  # noqa: PLC0415

        modality._self_check(n_per_kind=10)
        return "10 studies resolved per kind, all 9 kinds"

    gate.check("read_modality resolves every kind", _modality)

    print("\n[9] dev sample (§8.2.1)")

    def _dev_sample():
        import pandas as pd  # noqa: PLC0415

        path = PROJECT_ROOT / "data" / "processed" / "dev_sample" / "dev_sample_studies.parquet"
        assert path.is_file(), f"{path} missing -- run _dataset_lib/dev_sample.py"
        df = pd.read_parquet(path)
        assert len(df) == 5000, f"dev sample has {len(df)} rows, expected 5000"
        assert df.study_id.is_unique, "duplicate study_id in the dev sample"
        assert set(df.split) == {"train", "val", "test"}, f"splits present: {sorted(set(df.split))}"
        return f"5,000 studies, {df.subject_id.nunique():,} subjects, splits {sorted(set(df.split))}"

    gate.check("dev_sample built and well-formed", _dev_sample)

    print("\n" + "=" * 72)
    if gate.failures:
        print(f"STAGE P2.0 VALIDATION: FAIL -- {len(gate.failures)} of {gate.n_checks} checks failed")
        for f in gate.failures:
            print(f"  - {f}")
        return 1
    print(f"STAGE P2.0 VALIDATION: PASS -- {gate.n_checks}/{gate.n_checks} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
