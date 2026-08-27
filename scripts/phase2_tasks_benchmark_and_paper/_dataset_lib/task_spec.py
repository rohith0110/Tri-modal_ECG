"""One declarative description of every task's heads, labels and metrics.

The dataloader, the model builder, the trainer, the evaluator and the
algorithmic baselines all read this module. Without it each of the five would
carry its own copy of "A3 has 35 five-class heads whose label columns are named
``lab_<name>_<window>_label``", and the five copies would drift.

Nothing here decides *architecture* -- that is `config/decision_phase2.yaml`
(§5) and the per-run model config. This is the DATA + HEAD contract, mirroring
`config/task_definitions.yaml` §5.6 and §6.4, in the form Python needs.

    from _dataset_lib.task_spec import get_task
    spec = get_task("A2_measurement_blind")
    spec.heads[0].name, spec.heads[0].classes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

# --- head kinds ---------------------------------------------------------------
# binary      : one sigmoid logit, label column is bool/0-1
# multiclass  : softmax over `classes`, label column is the class string
# peak_seq    : per-sample sigmoid over 5000 samples + 2 regression channels (A4)
# bins        : per-bin sigmoid over 10 one-second bins, one query per row (B3)
# span        : two regression outputs, normalised character offsets (B5)
HEAD_KINDS = ("binary", "multiclass", "peak_seq", "bins", "span")

MEASUREMENT_CLASSES = {
    "hr_label": ["bradycardia", "normal", "tachycardia"],
    "qrs_label": ["normal", "borderline", "wide"],
    "qtc_label": ["short", "normal", "prolonged"],
}
LAB_CLASSES = ["missing", "low_abnormal", "high_abnormal",
               "abnormal_unknown_direction", "normal"]
LABS = ("K", "Na", "creatinine", "troponin", "lactate", "Ca", "Mg")
LAB_WINDOWS = ("pm24h", "pre_24h", "post_24h", "pm6h", "pm12h")
PRIMARY_LAB_WINDOW = "pm24h"
B3_QUERIES = ("HIGH_HEART_RATE", "LOW_HEART_RATE", "WIDE_QRS", "NOISY_SEGMENT")
B5_CLASSES = ["clean", "corrupted_HR", "corrupted_QRS", "corrupted_axis", "corrupted_PR"]
NEG_TYPES = ("TEXT_SWAP", "IMAGE_SWAP", "SIGNAL_SWAP", "HARD_NEGATIVE_TEXT",
             "PARTIAL_MISMATCH")

N_SAMPLES = 5000
FS_HZ = 500
N_BINS = 10


@dataclass(frozen=True)
class Head:
    """One output head: its name, shape, label column and optional row mask."""

    name: str
    kind: str
    label_column: str
    classes: Sequence[str] = ()
    # A row where `mask_column` is False contributes NO loss for this head and
    # no prediction row for it. A6's readmission heads are the reason this
    # exists: a row that is not readmission-eligible has no label, and zeroing
    # it would invent 4,790 negatives per split.
    mask_column: str | None = None
    loss: str = "auto"
    pos_weight: float | None = None

    @property
    def n_out(self) -> int:
        if self.kind == "binary":
            return 1
        if self.kind == "multiclass":
            return len(self.classes)
        if self.kind == "peak_seq":
            return 3 * N_SAMPLES        # 1 sigmoid channel + 2 regression channels
        if self.kind == "bins":
            return len(B3_QUERIES) * N_BINS
        if self.kind == "span":
            return 2
        raise ValueError(f"unknown head kind {self.kind!r}")


@dataclass(frozen=True)
class TaskSpec:
    """Everything the training/eval stack needs to know about one task."""

    key: str
    plan: str
    heads: tuple[Head, ...]
    primary_metric: str
    # Where the row's own identity lives, and where each modality's study_id
    # lives. For A5/B4 the three modalities can point at three DIFFERENT
    # studies -- that IS the verification task.
    id_column: str = "study_id"
    signal_id_column: str = "study_id"
    image_id_column: str = "study_id"
    text_id_column: str = "study_id"
    # image_type_column names a per-row column ('clean'/'scanlike') that
    # overrides the model config's image kind. Only A5/B4 use it.
    image_type_column: str | None = None
    # Text that lives in the task parquet rather than being looked up by
    # study_id (B5's audited report; A5's masked report).
    text_column: str | None = None
    primary_flag_column: str | None = "is_primary"
    subgroup_columns: tuple[str, ...] = ("sqi_tier", "cart_id", "link_tier")
    extra_columns: tuple[str, ...] = ()
    train_file: str = "train.parquet"
    val_file: str = "val.parquet"
    test_file: str = "test.parquet"
    eval_only: bool = False
    base_task: str | None = None
    notes: str = ""

    def head(self, name: str) -> Head:
        for candidate in self.heads:
            if candidate.name == name:
                return candidate
        raise KeyError(f"{self.key} has no head {name!r}")

    @property
    def label_columns(self) -> list[str]:
        return [h.label_column for h in self.heads]

    @property
    def mask_columns(self) -> list[str]:
        return [h.mask_column for h in self.heads if h.mask_column]


def _measurement_heads() -> tuple[Head, ...]:
    return tuple(
        Head(name=name, kind="multiclass", label_column=name, classes=classes)
        for name, classes in MEASUREMENT_CLASSES.items()
    )


def _lab_heads() -> tuple[Head, ...]:
    return tuple(
        Head(name=f"lab_{lab}_{window}", kind="multiclass",
             label_column=f"lab_{lab}_{window}_label", classes=LAB_CLASSES)
        for lab in LABS
        for window in LAB_WINDOWS
    )


TASKS: dict[str, TaskSpec] = {

    "A1_ecg_diagnosis": TaskSpec(
        key="A1_ecg_diagnosis", plan="A",
        heads=tuple(
            Head(name=name, kind="binary", label_column=name)
            for name in (
                "label_atrial_fibrillation_flutter",
                "label_heart_failure_narrow",
                "label_acute_myocardial_infarction",
                "label_conduction_disorder",
                "label_ventricular_arrhythmia_or_arrest",
            )
        ),
        primary_metric="macro_AUPRC",
        subgroup_columns=("sqi_tier", "cart_id", "link_tier", "boundary_flag"),
        extra_columns=("boundary_flag",),
    ),

    "A2_measurement_blind": TaskSpec(
        key="A2_measurement_blind", plan="A",
        heads=_measurement_heads(),
        primary_metric="mean_head_macro_AUPRC",
        subgroup_columns=("sqi_tier", "cart_id", "link_tier"),
    ),

    "A3_lab_abnormality": TaskSpec(
        key="A3_lab_abnormality", plan="A",
        heads=_lab_heads(),
        primary_metric="macro_AUPRC_pm24h",
        subgroup_columns=("sqi_tier", "cart_id", "link_tier", "boundary_flag"),
        extra_columns=("boundary_flag",),
    ),

    "A4_event_localization": TaskSpec(
        key="A4_event_localization", plan="A",
        heads=(Head(name="fiducials", kind="peak_seq", label_column="r_peaks_lead2",
                    pos_weight=14.0),),
        primary_metric="r_peak_F1_10ms",
        subgroup_columns=("sqi_tier", "cart_id", "link_tier"),
        extra_columns=("qrs_onsets_lead2", "qrs_offsets_lead2", "n_peaks",
                       "fallback_used", "delineate_ok"),
    ),

    # Verification rows. The masked-attribute heads ride along on the rows whose
    # signal AND image are still the anchor's own (positives, TEXT_SWAP,
    # HARD_NEGATIVE_TEXT); elsewhere `masked_attr_valid` is False and the three
    # heads contribute no loss. §5.6 puts both on one shared tri-encoder, and
    # §4.A.5.8 asks whether the joint training helps -- which needs them joint.
    "A5_cross_modal_verification": TaskSpec(
        key="A5_cross_modal_verification", plan="A",
        heads=(
            Head(name="y_match", kind="binary", label_column="y_match"),
            Head(name="hr_label", kind="multiclass", label_column="hr_label",
                 classes=MEASUREMENT_CLASSES["hr_label"], mask_column="masked_attr_valid"),
            Head(name="qrs_label", kind="multiclass", label_column="qrs_label",
                 classes=MEASUREMENT_CLASSES["qrs_label"], mask_column="masked_attr_valid"),
            Head(name="qtc_label", kind="multiclass", label_column="qtc_label",
                 classes=MEASUREMENT_CLASSES["qtc_label"], mask_column="masked_attr_valid"),
        ),
        primary_metric="AUPRC_y_match",
        id_column="anchor_study_id",
        signal_id_column="signal_id", image_id_column="image_id", text_id_column="text_id",
        image_type_column="image_type",
        primary_flag_column=None,
        subgroup_columns=("neg_type", "image_type"),
        extra_columns=("neg_type", "image_type"),
        notes="masked-attribute targets are joined from masked_attribute_<split>.parquet",
    ),

    "A6_risk_stratification": TaskSpec(
        key="A6_risk_stratification", plan="A",
        heads=(
            Head(name="mortality_30d", kind="binary", label_column="mortality_30d",
                 mask_column="mortality_observable"),
            Head(name="mortality_90d", kind="binary", label_column="mortality_90d",
                 mask_column="mortality_observable"),
            Head(name="readmission_30d", kind="binary", label_column="readmission_30d",
                 mask_column="readmission_eligible"),
            Head(name="readmission_90d", kind="binary", label_column="readmission_90d",
                 mask_column="readmission_eligible_90d"),
        ),
        primary_metric="mean_head_AUPRC",
        subgroup_columns=("sqi_tier", "cart_id", "link_tier", "boundary_flag"),
        extra_columns=("boundary_flag", "followup_days_after_discharge"),
    ),

    "B1_measurement_blind": TaskSpec(
        key="B1_measurement_blind", plan="B",
        heads=_measurement_heads(),
        primary_metric="mean_head_macro_AUPRC",
        subgroup_columns=("sqi_tier", "cart_id", "link_tier"),
    ),

    "B2_noise_robustness": TaskSpec(
        key="B2_noise_robustness", plan="B",
        heads=_measurement_heads(),
        primary_metric="mean_head_macro_AUPRC",
        primary_flag_column=None,
        subgroup_columns=("sqi_tier", "corruption_type", "snr_db", "regime"),
        extra_columns=("corruption_type", "snr_db", "regime", "row_role", "is_anchor",
                       "clean_signal_kind", "corrupted_signal_kind"),
    ),

    "B3_temporal_grounding": TaskSpec(
        key="B3_temporal_grounding", plan="B",
        heads=(Head(name="bins", kind="bins", label_column="labels"),),
        primary_metric="mIoU",
        primary_flag_column=None,
        subgroup_columns=("sqi_tier", "cart_id", "query"),
        extra_columns=("query", "fallback_used", "n_positive_bins"),
    ),

    "B4_cross_modal_verification": TaskSpec(
        key="B4_cross_modal_verification", plan="B",
        heads=(Head(name="y_match", kind="binary", label_column="y_match"),),
        primary_metric="AUPRC_y_match",
        id_column="anchor_study_id",
        signal_id_column="signal_id", image_id_column="image_id", text_id_column="text_id",
        image_type_column="image_type",
        primary_flag_column=None,
        subgroup_columns=("neg_type", "image_type"),
        extra_columns=("neg_type", "image_type"),
    ),

    "B5_contradiction_detection": TaskSpec(
        key="B5_contradiction_detection", plan="B",
        heads=(
            Head(name="is_corrupted", kind="binary", label_column="is_corrupted"),
            Head(name="label", kind="multiclass", label_column="label", classes=B5_CLASSES),
            Head(name="span", kind="span", label_column="corrupted_span_start",
                 mask_column="is_corrupted"),
        ),
        primary_metric="AUPRC_is_corrupted",
        text_column="audited_report_text",
        subgroup_columns=("sqi_tier", "cart_id", "contradiction_family"),
        extra_columns=("contradiction_family", "contradiction_type",
                       "corrupted_span_start", "corrupted_span_end"),
    ),

    # Evaluation-time only (§4.B.6, §7.5). B6 has no train/val rows of its own:
    # it slices B4's test predictions with eval_keys.parquet.
    "B6_difficulty_stratified": TaskSpec(
        key="B6_difficulty_stratified", plan="B",
        heads=(Head(name="y_match", kind="binary", label_column="y_match"),),
        primary_metric="AUPRC_y_match",
        id_column="study_id",
        primary_flag_column=None,
        subgroup_columns=("difficulty_tier", "neg_type"),
        extra_columns=("difficulty_tier", "neg_type"),
        train_file="eval_keys.parquet", val_file="eval_keys.parquet",
        test_file="eval_keys.parquet",
        eval_only=True, base_task="B4_cross_modal_verification",
    ),
}

TASK_KEYS = tuple(TASKS)


def get_task(key: str) -> TaskSpec:
    try:
        return TASKS[key]
    except KeyError:
        raise KeyError(
            f"unknown task {key!r}. The twelve Phase 2 tasks are: {', '.join(TASK_KEYS)}"
        ) from None


def _self_check() -> None:
    """Cross-check this module against config/task_definitions.yaml."""
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[3]
    defs = yaml.safe_load((root / "config" / "task_definitions.yaml").read_text(encoding="utf-8"))
    policy = yaml.safe_load(
        (root / "config" / "task_input_policy.yaml").read_text(encoding="utf-8")
    )

    assert set(TASK_KEYS) == set(defs["tasks"]), (
        f"task set differs from task_definitions.yaml: "
        f"{set(TASK_KEYS) ^ set(defs['tasks'])}"
    )
    assert set(TASK_KEYS) == set(policy["tasks"]), "task set differs from task_input_policy.yaml"

    expected_head_counts = {
        "A1_ecg_diagnosis": 5, "A2_measurement_blind": 3, "A3_lab_abnormality": 35,
        "A4_event_localization": 1, "A5_cross_modal_verification": 4,
        "A6_risk_stratification": 4, "B1_measurement_blind": 3, "B2_noise_robustness": 3,
        "B3_temporal_grounding": 1, "B4_cross_modal_verification": 1,
        "B5_contradiction_detection": 3, "B6_difficulty_stratified": 1,
    }
    for key, spec in TASKS.items():
        assert len(spec.heads) == expected_head_counts[key], (
            f"{key}: {len(spec.heads)} heads, §5.6 says {expected_head_counts[key]}"
        )
        for head in spec.heads:
            assert head.kind in HEAD_KINDS, f"{key}.{head.name}: bad kind {head.kind!r}"
            if head.kind == "multiclass":
                assert head.classes, f"{key}.{head.name}: multiclass head with no classes"

    # A1's five heads must be the five locked ICD groups, in the config's order.
    assert [h.name for h in TASKS["A1_ecg_diagnosis"].heads] == \
        defs["tasks"]["A1_ecg_diagnosis"]["targets"]["heads"], "A1 head order drifted"
    assert [h.name for h in TASKS["A6_risk_stratification"].heads] == \
        defs["tasks"]["A6_risk_stratification"]["targets"]["heads"], "A6 head order drifted"
    assert list(LAB_CLASSES) == defs["tasks"]["A3_lab_abnormality"]["targets"]["classes"]
    assert list(LABS) == defs["tasks"]["A3_lab_abnormality"]["targets"]["labs"]
    assert list(LAB_WINDOWS) == defs["tasks"]["A3_lab_abnormality"]["targets"]["windows"]
    assert list(B5_CLASSES) == \
        defs["tasks"]["B5_contradiction_detection"]["targets"]["class_head"]["classes"]
    assert set(B3_QUERIES) == set(
        defs["tasks"]["B3_temporal_grounding"]["targets"]["queries"]
    ), "B3 query set drifted"
    assert set(NEG_TYPES) == set(defs["shared_label_defs"]["negative_types"])

    # The measurement bins are written in the YAML as rules keyed by class name
    # ("bradycardia: hr_bpm < 60"), so compare the class SETS, not the values.
    for head, classes in MEASUREMENT_CLASSES.items():
        declared = set(defs["shared_label_defs"]["measurement_bins"][head]) - {"note"}
        assert set(classes) == declared, (
            f"{head} classes drifted from shared_label_defs.measurement_bins"
        )

    print(f"task_spec self-check: PASS  ({len(TASKS)} tasks, "
          f"{sum(len(t.heads) for t in TASKS.values())} heads)")


if __name__ == "__main__":
    _self_check()
