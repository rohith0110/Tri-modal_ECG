# Tri-Modal ECG Pipeline — Source of Truth (Phase 2)

**Status (updated 2026-08-26):** Plan only — no Phase 2 code is
authoritative yet. Every Phase 2 script currently under
`scripts/phase2_tasks_benchmark_and_paper/` predates the Phase 1 regen
and is **stale** (see §2.4); `data/processed/task_jsonl/` no longer
exists on disk. This document is the single source of truth for
**constructing the Phase 2 task suite, training the baselines,
evaluating them, and producing every artifact the paper requires**, on
top of the consolidated Phase 1 dataset produced by
`docs/PIPELINE_SOURCE_OF_TRUTH.md`.

**Phase 1 is COMPLETE.** Stages 8, 9 and 10 closed on 2026-06-03 /
2026-06-05; all five pre-flight checks in §9.0 pass. Phase 2 is
unblocked and has not started — `data/processed/tasks/` does not exist,
`config/task_definitions.yaml` and `config/task_input_policy.yaml` are
still the Plan-B-only files awaiting the Stage P2.0 rewrite, and none of
the four `*_LOCKED.yaml` files exist yet.

**Companion document.** `docs/PHASE2_EXECUTION_PLAN_DGX.md` governs
*where each stage runs and how bytes move* under the real hardware
constraints (MU DGX A100, 50 GB quota, Slurm, off-campus access, laptop
power instability). It changes no scientific decision in this document.
Where the two touch — resource policy (§8), stage placement (§9) — this
document has been updated to match, and Round 5 (§12.7) records the
decisions that made it necessary.

An agent following this document should not need to open
`ECG_Benchmark_Neutral_Implementation_Plan_Plan_A_B.docx` or
`TriModal_ECG_Truth.docx` while working on Phase 2; every binding rule
that affects task construction, training, or evaluation has been quoted
or summarized here. The agent may still need to consult Phase 1's doc
(`docs/PIPELINE_SOURCE_OF_TRUTH.md`) for manifest schemas, recipe
locations, and audit outputs — those are inputs to Phase 2, not duplicated
here.

**Authority hierarchy.** Where the two source docs disagree, **Plan A/B
wins** (Phase 1 doc §1 inheritance). Truth-doc–only constraints are
preserved when they don't conflict. Decisions in this document override
both source docs (the user has explicitly resolved several clashes — see
§12).

**Medical-grade discipline.** Every choice in this doc is a clinical-claim
choice. The reviewer (§11) verifies that no rule from Plan A/B doc §1.1
(non-negotiables) or §7.2 (statistical reporting) is silently violated
by an implementation. When in doubt, the agent halts and asks rather
than guesses; "I made a sensible default" is never acceptable on a
medical-grade benchmark.

---

## 0. Quick orientation

Phase 1 produced (per `docs/PIPELINE_SOURCE_OF_TRUTH.md` and the stage
reports under `outputs/stage_reports/`) the consolidated tri-modal ECG
dataset plus EHR-linkage tables and a `chosen_path=plan_a` decision
(`config/decision.yaml`, frozen 2026-05-31). Phase 2 turns that dataset
into:

1. **12 task datasets** — 6 Plan-A tasks (A1–A6) as the main paper, plus
   6 Plan-B tasks (B1–B6) as the supplementary robustness/shortcut
   benchmark. The user's Round-1 decision is **Plan A primary + Plan B
   supplementary** (§13.1). Plan B is not dropped: B2 noise-robustness
   curriculum and B5 contradiction-detection are unique contributions
   that don't fit cleanly into A1–A6.
2. **Three model tiers per task** — algorithmic baseline (Plan A/B
   §5.8 / §6.2 mandate), single-modality 1D ResNet, multi-modal fusion.
   Architecture choices in §5 follow the Truth doc §9.2 recommendations.
3. **Three random seeds per task per tier** (42, 123, 456), patient-level
   bootstrap with **n=10,000** for 95 % CIs on every primary metric.
   This exceeds the Plan A/B §7.2 minimum and gives clinical-grade CI
   precision (Round-1 decision §13.4).
4. **Audited, leakage-free training** — every task respects the
   per-task input policy locked in `config/task_input_policy.yaml`
   (rewritten in Phase 2 Stage P2.0 — the current file is Plan B only).
5. **The paper deliverables** — main-paper tables/figures, full
   supplementary material, release scripts, audit reports.

Phase 2 does **not** re-run Phase 1, regenerate raw signals/images, or
touch `data/raw/`. It consumes:

| Phase 1 artifact                                                       | Used by Phase 2 to                                                                  |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `data/processed/modality_manifest.parquet`                             | resolve `(study_id, modality_kind) -> bytes` for every loader                       |
| `data/processed/splits_subject_level.parquet`                          | enforce patient-level train/val/test split (70/10/20)                               |
| `data/processed/index/ecg_metadata_clean_with_measurements.parquet`    | cohort filtering, machine-measurement passthrough for label generation              |
| `data/processed/qc.parquet` + `waveform_qc.parquet`                    | exclude broken records, stratify by SQI tier, report missingness                    |
| `data/processed/structured_features.parquet`                           | feed structured-feature baselines (only when allowed by `task_input_policy.yaml`)   |
| `data/processed/signals/{lead2,twelve_lead_*}_{raw,preprocessed}.h5`   | signal-modality inputs, raw vs preprocessed ablation per Plan A/B §4.4              |
| `data/processed/signals_corrupted.parquet`                             | B2 noise-robustness test set (regime 1: clean-trained, corrupted-tested)            |
| `data/processed/images/{clean,scanlike}_{lead2,12lead}_shard_*.tar`    | image-modality inputs and B6 difficulty stratification                              |
| `data/processed/linkage/linkage_final.parquet`                         | A1/A3/A6 cohorts (L3 primary, L2 sensitivity)                                       |
| `data/processed/linkage/label_availability.parquet`                    | per-study label-existence flags so missingness audit is exact                       |
| `data/raw/ehr_cache/*.parquet`                                         | Plan A label generators (diagnoses_icd, labevents, admissions, patients)            |
| `config/decision.yaml`                                                 | Plan-A activation flag, threshold_pass record, frozen_at timestamp                  |
| `config/dataset_versions.yaml`                                         | stamp `dataset_version` into every Phase 2 artifact                                 |
| `config/preprocessing_recipe.yaml` + `config/scalers/`                 | apply consistent normalization for any Phase 2 component that takes raw signal      |
| `config/key_labs.yaml`                                                 | A3 lab-itemid universe (locked; never derived from free-text search at train time)  |

Phase 2 produces (final tree in §3):
- `data/processed/tasks/<task>/{train,val,test}.parquet` — leakage-audited per-task datasets (parquet, not JSONL — see §3 rationale)
- `outputs/model_runs/<task>/<arch>/seed_<n>/` — checkpoints, predictions, logs
- `outputs/results/<task>/<arch>.csv` — three-seed mean ± std + bootstrap CI for every metric
- `outputs/tables/` and `outputs/figures/` — paper tables and figures
- `outputs/audit_reports/{leakage,split,duplicate,missingness,linkage}_audit_phase2.md`
- `outputs/release_package/` — reproducibility bundle (scripts + configs, never raw data)

---

## 1. Non-negotiable rules (from Plan A/B §1.1 and §7.2)

These rules apply to every task, every training run, every result table
in Phase 2. If a downstream design choice would violate one of these,
the choice is wrong, not the rule.

| Rule                                | Implementation requirement                                                                                                                                                                                                                |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Patient-level split only**        | Phase 2 inherits `data/processed/splits_subject_level.parquet`. No task may re-split. A task may **subset** this split (e.g., L3-only cohort for A1) but never reshuffle.                                                                  |
| **No label-to-input leakage**       | Every task declares allowed/forbidden modalities in `config/task_input_policy.yaml` (rewritten in Stage P2.0 to include all 12 tasks). `outputs/audit_reports/leakage_audit_phase2.md` verifies zero forbidden fields touch any input.    |
| **Timing rules before labels**      | For every task: state retrospective-association vs prospective-prediction in the per-task spec (§4). A1 ICD is "encounter-associated diagnosis" (Plan A/B §5.3), not strict prospective; A6 mortality is prospective from ECG time.       |
| **Report missingness as data**      | Every cohort table records `n_subjects, n_ECGs, n_positives, prevalence, missingness%` per Plan A/B §1.1 and §7.2. Absence of a lab/diagnosis is **never** silently coded as normal. A3 explicitly stores `missing` as a label class.    |
| **Confidence intervals**            | Every primary metric in every results table includes a 95 % CI from **patient-level** bootstrap with **n=10,000** iterations (§13.4). Bootstrap by `subject_id`, not by ECG. CIs use BCa (bias-corrected accelerated) when n_pos ≥ 100. |
| **Three seeds**                     | Every trained model is run for seeds 42, 123, 456. Tables report mean ± std across seeds **plus** bootstrap CI on pooled predictions. (Doc §7.2: "three random seeds minimum if compute allows.")                                         |
| **Threshold on validation only**    | Classification thresholds, calibration cutoffs, and class-imbalance weights are chosen using **train+val only**. Test-set leakage into threshold selection is a CRITICAL failure (§11.2).                                                |
| **AUPRC primary for imbalance**     | Primary metric for any imbalanced classification task is AUPRC. AUROC is secondary. (Plan A/B §7.2.)                                                                                                                                       |
| **Calibration for risk/lab**        | A3 and A6 results include reliability diagram, ECE, and Brier score in addition to AUPRC/AUROC. (Plan A/B §7.2.)                                                                                                                          |
| **Subject-level bootstrap, never ECG-level** | Bootstrap samples patients with replacement, then includes all that patient's ECGs in the resampled set. Sampling ECGs directly would inflate apparent precision because patients contribute correlated ECGs.                       |
| **Identical test cohort per comparison** | When two architectures or two tiers are compared, both must run on the **identical** set of test subjects and ECGs. If cohorts differ (e.g., A1 L3-only vs L3+L2 sensitivity), the comparison is reported in a separate table.        |
| **Repeated ECGs sensitivity (A6)**  | Plan A/B §5.8: run risk tasks both on "all ECGs" and "first ECG per admission" / "first ECG per patient." Report both. The first-ECG result is the primary number.                                                                        |
| **Do not overclaim novelty**        | The paper claim is "EHR-grounded, leakage-audited multimodal ECG benchmark." Never "first multimodal ECG benchmark." Must cite MEETI [R4], CardioLab [R5], SignalMC-MED [R6], ECG survival benchmarks [R7]. (Plan A/B §1.1.)              |
| **Raw MIMIC never published**       | Release package contains scripts, configs, locked YAMLs — **never** raw data, never derived dataset rows that contain MIMIC identifiers in a form that could leak the underlying data.                                                    |
| **Dataset version stamp**           | Every Phase 2 artifact embeds `dataset_version` (Phase 1 stamp) **and** `phase2_version` (incremented per Phase 2 run cycle). Stamped into parquet schema metadata, CSV header comments, and checkpoint metadata.                          |
| **Reproducibility**                 | Every main-paper number must be regenerable from a single script invocation against the locked dataset. (Plan A/B §9.3.)                                                                                                                  |
| **`config/decision.yaml` honored**  | Plan A is active because `chosen_path: plan_a` is frozen. If the YAML is mutated, the change history is recorded and Phase 2 is re-run end-to-end. No mid-run mutations.                                                                  |

### 1.1 Statistical reporting template (every results table follows this)

Every Phase 2 results table — main paper or supplementary — must contain
exactly these columns, in this order:

```
| arch | seed | n_ecg_test | n_subj_test | n_pos_test | missingness_% |
| metric | metric_mean | metric_std | ci_low_95 | ci_high_95 | calibration_ece | calibration_brier |
```

Tables that aggregate across seeds (the main paper view) collapse `seed`
into the `metric_mean / metric_std` pair and add a `seed_pool_ci` column
holding the pooled-prediction bootstrap interval (i.e., concatenate test
predictions from all three seeds, then bootstrap). The per-seed view
(separate seed column) goes into supplementary.

### 1.2 Required Phase 2 audit logs

| Audit                                                        | What it contains                                                                                                                                                       | Output                                                                |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `leakage_audit_phase2.md`                                    | Every task's allowed/forbidden field list + per-task verification that no forbidden column appears in the on-disk task parquet inputs                                  | `outputs/audit_reports/leakage_audit_phase2.md`                       |
| `split_audit_phase2.md`                                      | Re-verify zero subject overlap across train/val/test for every task's cohort (each task is a subset of the global split)                                               | `outputs/audit_reports/split_audit_phase2.md`                         |
| `cohort_audit.md` (one file aggregating all 12 task cohorts) | Per-task: n_ECG, n_subjects, n_pos per class, prevalence, missingness, linkage-tier breakdown, SQI-tier breakdown, cart_id distribution                                | `outputs/audit_reports/cohort_audit.md`                               |
| `threshold_audit.md`                                         | Every classifier's threshold + the validation-set objective used to choose it. Asserts test-set predictions never touched threshold tuning.                            | `outputs/audit_reports/threshold_audit.md`                            |
| `calibration_audit.md`                                       | A3/A6 reliability diagrams, ECE, Brier scores per seed and pooled. Sanity check: monotonic calibration curve, no degenerate constant-predictor.                        | `outputs/audit_reports/calibration_audit.md`                          |
| `sensitivity_audit.md`                                       | A3 lab-window sensitivity, A6 first-ECG-per-admission sensitivity, A1 L3-only vs L3+L2, raw-vs-preprocessed signal ablation, no-text-input ablation for cross-modal tasks | `outputs/audit_reports/sensitivity_audit.md`                          |
| `reproducibility_audit.md`                                   | Every main-paper number → script invocation → exact reproduced number. Doc §9.3 requirement.                                                                          | `outputs/audit_reports/reproducibility_audit.md`                      |

All seven must be PASS before paper submission.

---

## 2. Inheritance from Phase 1 (binding inputs, do not re-derive)

Phase 2 treats every artifact below as **read-only ground truth**. The
loader contract is "go through `modality_manifest.parquet` for any
modality access; never `open()` an HDF5 or tar directly." Inheritance
violations are CRITICAL (§11).

### 2.1 Canonical modality loader

Phase 2 builds and uses **one** helper module
(`scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/modality.py`):

```python
def read_modality(study_id: int, kind: str) -> bytes | np.ndarray:
    """Resolve study + modality to bytes (tar/parquet) or array (HDF5)
    via data/processed/modality_manifest.parquet.

    kind ∈ {raw_lead2, raw_12lead, preprocessed_lead2, preprocessed_12lead,
            image_clean_lead2, image_clean_12lead,
            image_scanlike_lead2, image_scanlike_12lead,
            signal_corrupted}
    """
```

Every dataloader, every label-builder, every evaluation script reads
through this single helper. The function MAY cache index-only structures
(manifest rows in memory) but MUST NOT cache raw bytes — that's the
on-disk container's job.

### 2.2 Splits — frozen, immutable

`data/processed/splits_subject_level.parquet` is the **only** split
Phase 2 uses. Per Phase 1 §3.5 it is stratified 70/10/20 on
`(hr_bucket, linkage_tier)`. Phase 2 may subset by:

- linkage tier (L3 only for A1 primary, L3+L2 for sensitivity)
- SQI tier (high only for A2 primary, high+medium for sensitivity)
- modality availability (e.g., A5 requires text+image+signal; drop the
  one study where `text_ok=false`)

…but **never** changes which subject is in which split. The audit script
checks that every Phase 2 cohort's `subject_id` membership is a strict
subset of the global split.

### 2.3 Decision-gate context

`config/decision.yaml` (frozen 2026-05-31, sha256 = first 12 hex of
contents at freeze) records `chosen_path: plan_a` plus the
threshold-pass block. If a future re-run of Stage 1 changes the path,
the `frozen_at` timestamp differs and Phase 2 halts at Stage P2.0 with
"`decision.yaml` mutated since last Phase 2 lock — re-confirm." The
threshold values quoted (e.g., 547,827 L3/L2 ECGs) are reproduced in
every Phase 2 report header so the reviewer can verify the inheritance
hasn't drifted.

### 2.4 Stale-artifact removal (mandatory Stage P2.0 first action)

> **Update 2026-08-26:** `data/processed/task_jsonl/` no longer exists on
> disk — step 1 below is already satisfied and needs no action beyond
> recording it. Steps 2–4 (quarantining the stale builder scripts) are
> still outstanding. Note that the numeric-slot collisions are wider than
> this section anticipated: the new Phase 2 scripts also need slots 20–22
> (audits), 30–31 (train/eval), 40 (aggregate), 50 (baselines) and 60–61
> (tables/figures), all of which are occupied by Plan-B-era scripts. Stage
> P2.0 therefore quarantines **every** pre-regen script in
> `scripts/phase2_tasks_benchmark_and_paper/`, not only `01..06_task_*.py`.
> Quarantine, never delete — the Plan-B paper's numbers came from those
> scripts and must stay reproducible.

The current contents of `data/processed/task_jsonl/`
(`taskA_verification.jsonl`, `taskB_temporal_grounding.jsonl`,
`taskC_plausibility.jsonl`, `taskB1_measurement_blind.jsonl`,
`taskB2_noise_robustness.jsonl`, `taskB5_contradiction_detection.jsonl`)
and the now-stale scripts under
`scripts/phase2_tasks_benchmark_and_paper/01–06_task_*.py` reference the
deleted per-study NPY/PNG/JPG paths and the wrong split ratio (80/10/10
not 70/10/20). They are **NOT** part of the final Phase 2 tree. Stage
P2.0's first action is:

1. Move the legacy `data/processed/task_jsonl/` directory to
   `data/archive_phase1_old/task_jsonl_<timestamp>/` (NOT deleted yet —
   the reviewer may want to compare schemas) and `os.replace` it; do
   not `os.remove`.
2. Move the stale builder scripts
   `scripts/phase2_tasks_benchmark_and_paper/01_task_A_verification.py`
   through `06_task_B5_contradiction_detection.py` to
   `scripts/phase2_tasks_benchmark_and_paper/_legacy_phase1_pre_regen/`
   so the new Stage P2.1 builders can take their numerical slots
   without name collisions.
3. Record both moves in the Stage P2.0 §10 stage report.
4. Defer outright deletion until the Phase 2 regen completes
   end-to-end and the reviewer signs off (mirrors Phase 1 §6.4 "do not
   delete until validation passes").

### 2.5 Task-input policy file — rewrite

The current `config/task_input_policy.yaml` covers only B1, B2, B3, B4,
B5, B6 (Plan B). Stage P2.0 rewrites it in-place to include all 12 task
keys (A1, A2, A3, A4, A5, A6, B1, B2, B3, B4, B5, B6). Schema unchanged.
Rewrite is governed by the per-task spec in §4; the rewrite is a
mechanical translation of those `allowed_inputs / forbidden_inputs`
blocks.

`config/task_definitions.yaml` is similarly rewritten — currently
"Plan B only (no EHR access)". The replacement records target classes,
primary/secondary metrics, baseline list, subgroup analyses for every
task in §4.

### 2.6 Modality-kind enum (locked)

Phase 2 dataloaders use exactly this enum (matches Phase 1 §2.1 and
adds nothing). Adding a kind is a CRITICAL spec violation:

```txt
raw_lead2, raw_12lead,
preprocessed_lead2, preprocessed_12lead,
image_clean_lead2, image_clean_12lead,
image_scanlike_lead2, image_scanlike_12lead,
signal_corrupted
```

Text is **not** a `modality_kind` because it lives directly in
`ecg_metadata_clean_with_measurements.parquet` (column `T_machine`,
plus optional `T_cardio`). The text loader is a parquet column read.

### 2.7 Compute inheritance

`config/preprocessing_recipe.yaml` provides the canonical signal
normalization. Any Phase 2 model that takes "preprocessed signal" as
input reads from `signals/lead2_preprocessed.h5` (or the 12-lead
shards); models that take "raw signal" read from `signals/lead2_raw.h5`.
Phase 2 never re-applies the recipe — the materialized HDF5 from Stage
9 of Phase 1 is the only source of preprocessed signal bytes.

---

## 3. Final Phase 2 artifact tree

```plaintext
config/
├── task_definitions.yaml         # rewritten in Stage P2.0 (12 tasks)
├── task_input_policy.yaml        # rewritten in Stage P2.0 (12 tasks)
├── icd_label_map_LOCKED.yaml     # NEW — Plan A/B Appendix B (A1 cohort)
├── lab_itemid_map_LOCKED.yaml    # NEW — Plan A/B Appendix C (A3 cohort);
│                                 #       superset of key_labs.yaml
├── corruption_recipes_LOCKED.yaml # NEW — B2 noise-injection params per family
├── claim_dictionary_LOCKED.yaml  # NEW — B5/C plausibility rule dictionary
├── model_configs/                # NEW — one YAML per (task, arch)
│   ├── A1_signal_resnet18.yaml
│   ├── A1_image_resnet50.yaml
│   ├── A1_text_bioclinicalbert.yaml
│   ├── A1_multimodal_fusion.yaml
│   ├── A2_signal_resnet18.yaml
│   ├── ... (one per task × arch tier)
│   └── B6_multimodal_fusion.yaml
├── eval_configs/                 # NEW — bootstrap n, CI method, subgroup keys
│   ├── default.yaml
│   ├── A6_risk.yaml              # adds calibration eval block
│   └── B2_robustness.yaml        # adds regime-1/2/3 split block
└── decision_phase2.yaml          # NEW — Phase-2 run lock (architecture
                                  #       choices, seeds, scope frozen)

data/processed/tasks/             # NEW — Phase 2 task datasets
├── A1_ecg_diagnosis/
│   ├── train.parquet  val.parquet  test.parquet
│   ├── cohort_manifest.parquet           # one row per study with label,
│                                         # linkage tier, SQI tier, cart_id
│   └── README.md                          # schema, derivation, prevalence
├── A2_measurement_blind/
├── A3_lab_abnormality/
├── A4_event_localization/
├── A5_cross_modal_verification/
├── A6_risk_stratification/
├── B1_measurement_blind/
├── B2_noise_robustness/                   # uses signals_corrupted.parquet
├── B3_temporal_grounding/
├── B4_cross_modal/
├── B5_contradiction_detection/
└── B6_difficulty_stratified/

outputs/
├── model_runs/                            # NEW — one tree per task × arch × seed
│   ├── A1_ecg_diagnosis/
│   │   ├── signal_resnet18/seed_42/
│   │   │   ├── checkpoint_best.pt
│   │   │   ├── checkpoint_last.pt
│   │   │   ├── train_log.jsonl
│   │   │   ├── val_predictions.parquet
│   │   │   ├── test_predictions.parquet
│   │   │   └── train_config.yaml          # snapshot
│   │   ├── signal_resnet18/seed_123/...
│   │   ├── signal_resnet18/seed_456/...
│   │   ├── image_resnet50/seed_{42,123,456}/...
│   │   ├── text_bioclinicalbert/seed_{42,123,456}/...
│   │   └── multimodal_fusion/seed_{42,123,456}/...
│   └── … (one tree per task)
├── results/                               # NEW — per-task aggregated CSVs
│   ├── A1_ecg_diagnosis.csv
│   ├── A1_ecg_diagnosis_sensitivity.csv   # L3-only vs L3+L2, raw vs preprocessed
│   ├── ... (per task)
│   └── all_tasks_summary.csv              # cross-task headline numbers
├── tables/                                # NEW — paper tables (final form)
│   ├── main/
│   │   ├── table1_overview.tex            # Plan A/B doc §7 evidence matrix
│   │   ├── table2_planA_results.tex
│   │   ├── table3_planB_results.tex
│   │   ├── table4_calibration.tex         # A3/A6
│   │   └── table5_robustness_AUCC.tex     # B2
│   ├── supplementary/
│   │   ├── stable_per_seed.tex
│   │   ├── stable_per_sqi_tier.tex
│   │   ├── stable_per_cart_id.tex
│   │   ├── stable_per_linkage_tier.tex
│   │   ├── stable_first_ecg_sensitivity.tex
│   │   ├── stable_lab_window_sensitivity.tex
│   │   ├── stable_raw_vs_preprocessed.tex
│   │   └── stable_corruption_per_family.tex
│   └── README.md                          # how each table was generated
├── figures/                               # NEW — paper figures
│   ├── main/
│   │   ├── fig1_pipeline_diagram.png
│   │   ├── fig2_per_task_AUPRC.png
│   │   ├── fig3_corruption_curves.png     # B2 regime-1 collapse threshold
│   │   ├── fig4_calibration.png           # A6 reliability diagrams
│   │   └── fig5_cross_modal_difficulty.png # B6 per-difficulty Recall@1
│   ├── supplementary/
│   │   ├── sfig_per_sqi_tier.png
│   │   ├── sfig_per_cart_id.png
│   │   ├── sfig_b5_localization.png       # contradiction span examples
│   │   ├── sfig_ehr_linkage_distribution.png
│   │   └── ... (one per supplementary table)
│   └── README.md                          # script + invocation per figure
├── audit_reports/                         # NEW — Phase 2 audit suite
│   ├── leakage_audit_phase2.md
│   ├── split_audit_phase2.md
│   ├── cohort_audit.md
│   ├── threshold_audit.md
│   ├── calibration_audit.md
│   ├── sensitivity_audit.md
│   └── reproducibility_audit.md
├── stage_reports/                         # NEW — one per Phase 2 stage
│   ├── stage_P2.0_report.md
│   ├── stage_P2.0_review.md
│   ├── stage_P2.1_report.md
│   ├── … (through stage_P2.N_report.md)
└── release_package/                       # NEW — paper reproducibility bundle
    ├── README.md                          # how to reproduce every number
    ├── scripts/                           # frozen copy of Phase 2 scripts
    ├── configs/                           # frozen copy of every locked YAML
    ├── notebooks/                         # one .ipynb per main-paper figure
    └── checksums.txt                      # sha256 of every config + script

scripts/phase2_tasks_benchmark_and_paper/  # rewritten — see Stage P2.0
├── _dataset_lib/                          # NEW — shared loader code
│   ├── modality.py                        # read_modality(study_id, kind)
│   ├── cohorts.py                         # per-task cohort filters
│   ├── labels.py                          # label-generation helpers
│   └── bootstrap.py                       # patient-level BCa bootstrap n=10000
├── _model_lib/                            # NEW — encoder + head modules
│   ├── signal_encoders.py                 # 1D ResNet-18 / 1D ResNet-34
│   ├── image_encoders.py                  # ResNet-50 / ViT-S/16
│   ├── text_encoders.py                   # Bio-ClinicalBERT / TF-IDF
│   ├── fusion_heads.py                    # late-fusion MLP / cross-attention
│   └── algorithmic_baselines.py           # NeuroKit2 R-peak/QRS detector wrappers
├── _train_lib/                            # NEW — shared training infrastructure
│   ├── trainer.py                         # train loop, mixed precision, ckpt
│   ├── threshold.py                       # val-only threshold selection
│   ├── calibration.py                     # ECE, Brier, reliability
│   └── seed.py                            # deterministic seed + reproducibility
├── _legacy_phase1_pre_regen/              # quarantined stale builders (Stage P2.0)
│   └── 01..06_task_*.py
├── 01_build_A1_ecg_diagnosis.py           # NEW — Plan A label builders (Stage P2.1)
├── 02_build_A2_measurement_blind.py
├── 03_build_A3_lab_abnormality.py
├── 04_build_A4_event_localization.py
├── 05_build_A5_cross_modal_verification.py
├── 06_build_A6_risk_stratification.py
├── 07_build_B1_measurement_blind.py       # NEW — Plan B label builders (Stage P2.2)
├── 08_build_B2_noise_robustness.py
├── 09_build_B3_temporal_grounding.py
├── 10_build_B4_cross_modal.py
├── 11_build_B5_contradiction_detection.py
├── 12_build_B6_difficulty_stratified.py
├── 20_audit_tasks_leakage.py              # NEW — Stage P2.3 leakage audit
├── 21_audit_tasks_cohort.py               # NEW — cohort_audit.md
├── 22_audit_tasks_split.py                # NEW — split_audit_phase2.md
├── 30_train.py                            # NEW — unified trainer entry
├── 31_eval.py                             # NEW — unified eval entry
├── 40_aggregate_results.py                # NEW — per-task results.csv builder
├── 41_run_sensitivity.py                  # NEW — A1/A3/A6 sensitivity sweeps
├── 50_run_baselines_algorithmic.py        # NeuroKit2 baselines (A2/B1, B3)
├── 60_make_paper_tables.py                # NEW — paper LaTeX tables
├── 61_make_paper_figures.py               # NEW — paper figures
├── 70_build_release_package.py            # NEW — release bundle
└── README.md                              # rewritten — Phase 2 reproduction blocks
```

**Naming convention.** Stage prefix uses `P2.<n>` to distinguish from
Phase 1 stages. Script numerical prefixes mirror Phase 1 conventions
(`01–12` builders, `20–22` audits, `30–31` train/eval, `40–41`
aggregation/sensitivity, `50` algorithmic baselines, `60–61` paper
artifacts, `70` release).

**Why parquet instead of JSONL for task datasets.** The Phase 1 Truth
doc used JSONL for `taskA_verification.jsonl` etc. because per-study
NPY/PNG paths were stored as strings inside each row. After the Phase 1
regen, every modality lookup is via `modality_manifest.parquet`, so
task rows hold only `(study_id, label, split, cohort_flags)` — no
modality bytes — and parquet's columnar storage gives ~5× smaller files
and faster filtered reads. JSONL would be wasteful. (The B6
difficulty-stratification metadata that was a `neg_type` enum in
`taskA_verification.jsonl` becomes a categorical column in the new
`B6_difficulty_stratified/{train,val,test}.parquet`.)

---

## 4. Per-task implementation specs

This section defines each task's **data contract** — cohort, label
generation, allowed/forbidden inputs, output schema, primary metrics,
required baselines, sensitivity analyses. The **model contract** (which
architecture / loss / scheduler) is in §5–§7 and is intentionally
separated so the data contract can be audited without reference to any
specific model.

Every task subsection follows the same eight-block layout:

```
4.X.1 Purpose                — what the task evaluates
4.X.2 Cohort                 — subject filter, expected n, sensitivity subsets
4.X.3 Label generation       — deterministic, version-locked, with provenance columns
4.X.4 Input policy           — allowed/forbidden modalities + leakage rationale
4.X.5 Output schema          — column list of {train,val,test}.parquet
4.X.6 Metrics                — primary, secondary, calibration where relevant
4.X.7 Baselines              — algorithmic (mandatory per doc) + signal + (image/text/multi)
4.X.8 Sensitivity analyses   — sub-cohorts and ablations required for supplementary
```

**Notation.** `n_ECG_expected` numbers are from Phase 1 Stage 1
linkage/availability reports (`outputs/audit_reports/linkage_feasibility_report.md`
and `data/processed/linkage/label_availability.parquet`) and from
Phase 1 Stage 6/7 QC reports. They are the agent's expected positive
counts at cohort-build time; the actual numbers go into `cohort_audit.md`
at Stage P2.3.

---

### 4.A — Plan A tasks (main paper)

Plan A tasks all depend on `data/processed/linkage/linkage_final.parquet`
and `data/raw/ehr_cache/*.parquet`. They are conditional on
`config/decision.yaml.chosen_path == 'plan_a'` (currently true).

#### 4.A.1 — A1: EHR diagnosis prediction (multi-label ICD)

**4.A.1.1 Purpose.** Predict whether each of five clinically meaningful
ICD-grouped diagnoses was assigned to the encounter that the ECG
overlaps with. Multi-label binary heads. Plan A/B §5.3.

**4.A.1.2 Cohort.**

| Filter                                                    | Expected effect                 |
| --------------------------------------------------------- | ------------------------------- |
| `link_tier == 'L3'` (primary) on hospital admission       | ~468,176 ECGs                   |
| `icd_available == True` on the linked `hadm_id`           | ~315 K of the L3 hosp subset    |
| Subject in train/val/test per `splits_subject_level.parquet` | 70/10/20 keeps subjects intact |
| Boundary flag included; sensitivity reports excluded set  | Plan A/B §3.4                   |
| ECGs that fail `waveform_qc.parquet.decode_ok==False`    | drop                            |

Sensitivity cohort: `link_tier ∈ {L3, L2}` (~547,671 ECGs with ICD).
Reported separately, not pooled with primary.

ED-linked diagnoses (`ed_diagnosis.parquet`) are NOT pooled with
hospital diagnoses in the primary cohort. They are a secondary
analysis only (per Plan A/B §5.3 "Do not mix hospital and ED labels
without a provenance column"). When included, the `label_source`
column is `hosp` or `ed`.

**4.A.1.3 Label generation.** Per Plan A/B Appendix B. Map `diagnoses_icd.icd_code`
(after stripping whitespace, preserving `icd_version`) to five group
heads using the locked
`config/icd_label_map_LOCKED.yaml`:

```yaml
atrial_fibrillation_flutter:
  icd10_prefix: ["I48"]
  icd9_exact:   ["42731", "42732"]
heart_failure_narrow:
  icd10_prefix: ["I50"]
  icd10_exact_optional: ["I110", "I130", "I132"]
  icd9_prefix:  ["428"]
acute_myocardial_infarction:
  icd10_prefix: ["I21", "I22"]
  icd9_prefix:  ["410"]
conduction_disorder:
  icd10_prefix: ["I44", "I45"]
  icd9_prefix:  ["426"]
ventricular_arrhythmia_or_arrest:
  icd10_prefix: ["I472", "I490", "I46"]
  icd9_prefix:  ["4271", "4274"]
```

Per Plan A/B Appendix B: "Validate every included pattern by joining to
`d_icd_diagnoses` and reading the long_title list." The builder
script (`01_build_A1_ecg_diagnosis.py`) outputs the resolved
`long_title` join into the cohort_manifest so the reviewer can verify
each included code.

The label timing classification (Plan A/B §1.1 mandates this be
stated): A1 is **encounter-associated diagnosis prediction**, not
strict prospective diagnosis. The ICD code is assigned at the
end of the admission, after the ECG. We do NOT claim prospective
diagnosis prediction.

**4.A.1.4 Input policy.**

```yaml
A1_ecg_diagnosis:
  allowed:   [raw_lead2, raw_12lead, preprocessed_lead2, preprocessed_12lead,
              image_clean_lead2, image_clean_12lead,
              image_scanlike_lead2, image_scanlike_12lead,
              report_text]
  forbidden: [machine_measurements, structured_features]
  leakage_rationale: |
    Labels are EHR-derived, not ECG-measurement-derived, so machine
    measurements and structured features are not direct leakage. They
    are still forbidden because the report_text already encodes machine
    interpretations of the same measurements, and admitting structured
    features would let the model side-channel-learn the report text via
    correlated numerical features (e.g., a model predicting AF could
    learn 'irregular RR' from rr_interval std).
```

**4.A.1.5 Output schema (`tasks/A1_ecg_diagnosis/{train,val,test}.parquet`).**

```
study_id                int64
subject_id              int64
split                   str         # one of {train,val,test}
hadm_id                 int64?
ecg_time                timestamp_ns
link_tier               str         # L3 in primary; L2 in sensitivity
boundary_flag           bool        # within ±2h of admittime or dischtime
label_atrial_fibrillation_flutter         bool
label_heart_failure_narrow                bool
label_acute_myocardial_infarction         bool
label_conduction_disorder                 bool
label_ventricular_arrhythmia_or_arrest    bool
label_source            str         # "hosp" or "ed" (primary == "hosp")
n_icd_codes_on_admission int32      # provenance — how many ICD codes contributed
icd_codes_matched       list<str>   # the actual codes that triggered each label
sqi_tier                str         # high/medium/low — for subgroup analysis
cart_id                 str?        # for cart_id subgroup analysis
```

**4.A.1.6 Metrics.**

- Primary: macro-AUPRC across the 5 heads; per-head AUPRC.
- Secondary: macro-AUROC, per-head AUROC, per-head F1 at val-optimal
  threshold.
- Calibration: NOT reported for A1 (not the headline calibration task).
- Threshold selection: validation set only, per-head Youden's J on
  val ROC.

**4.A.1.7 Baselines.**

| Tier               | Baseline                                                                 | Required |
| ------------------ | ------------------------------------------------------------------------ | -------- |
| Algorithmic        | Logistic regression on machine-measurement summary stats (HR/QRS/QTc bins, axis). FORBIDDEN as model input (§4.A.1.4) but allowed as **baseline-only**. | Yes      |
| Signal             | 1D ResNet (depth in §5) on `raw_lead2`                                   | Yes      |
| Signal preprocessed | Same architecture on `preprocessed_lead2` (raw-vs-preprocessed ablation) | Yes      |
| Image              | Image backbone (§5) on `image_clean_lead2`                                | Yes      |
| Text               | Text backbone (§5) on `report_text`                                       | Yes      |
| Multimodal         | Fusion head (§5) on raw_lead2 + image_clean_lead2 + report_text          | Yes      |
| Multimodal-12-lead | Fusion head on raw_12lead + image_clean_12lead + report_text             | Yes      |

**4.A.1.8 Sensitivity analyses.**

- L3 only (primary) vs L3+L2 (sensitivity table).
- Boundary excluded sensitivity.
- Raw vs preprocessed signal.
- Per-SQI-tier breakdown (high / medium / low) in supplementary.
- Per-cart_id breakdown for the top 5 cart_ids by count.
- Hospital ICD only vs Hospital + ED ICD (provenance-tagged).
- First-ECG-per-admission vs all-ECGs (repeated-ECG sensitivity).
- No-text ablation: same multimodal architecture but text dropped.

---

#### 4.A.2 — A2: Measurement-blind physiological inference

**4.A.2.1 Purpose.** Sanity-check task: predict binned HR, QRS duration,
QTc from signal alone. Per Plan A/B §5.4: "Use this task as a sanity
check, not as the main novelty claim." Mirrors Plan B's B1; the
difference is cohort scope (A2 = L3 EHR-linked; B1 = full clean
cohort). Both report by SQI tier.

**4.A.2.2 Cohort.**

| Filter                                                            | Expected effect |
| ----------------------------------------------------------------- | --------------- |
| `link_tier == 'L3'` (primary)                                     | ~468 K          |
| Machine measurements present + valid for HR, QRS, QTc             | drop ~0.1 %     |
| `waveform_qc.decode_ok == True` and `length_ok == True`           |                 |
| sqi_tier ∈ {high} for primary; high+medium for sensitivity        | ~445 K primary  |

**4.A.2.3 Label generation.** Three binary-per-class heads from
machine measurements:

```python
hr_bpm = 60000 / rr_interval   # ms → bpm
hr_label = {
    "bradycardia": hr_bpm < 60,
    "normal":      60 <= hr_bpm < 100,
    "tachycardia": hr_bpm >= 100,
}
qrs_ms = qrs_end - qrs_onset
qrs_label = {
    "normal":     qrs_ms < 100,
    "borderline": 100 <= qrs_ms < 120,
    "wide":       qrs_ms >= 120,
}
qtc_ms = … (Bazett: qt_ms / sqrt(rr_interval/1000), already in
            structured_features.parquet.qtc_bazett_ms)
qtc_label = {
    "short":     qtc_ms < 350,
    "normal":    350 <= qtc_ms < 450,   # (women 460)
    "prolonged": qtc_ms >= 450,
}
```

(Threshold values and class definitions match the existing
`config/task_definitions.yaml` for B1.)

**4.A.2.4 Input policy.**

```yaml
A2_measurement_blind:
  allowed:   [raw_lead2, raw_12lead, preprocessed_lead2, preprocessed_12lead]
  forbidden: [image_clean_lead2, image_clean_12lead,
              image_scanlike_lead2, image_scanlike_12lead,
              report_text, machine_measurements, structured_features]
  leakage_rationale: |
    Labels are computed directly from rr_interval, qrs_end-qrs_onset,
    and qtc_bazett_ms. Any input containing these values allows trivial
    copying. Image rendering doesn't embed text but does embed the
    waveform shape and amplitude; image is forbidden in A2 (matches B1
    decision) to keep this strictly signal-only — the task is meant as
    a signal-encoder sanity check.
```

**4.A.2.5 Output schema.**

```
study_id, subject_id, split, link_tier, sqi_tier, cart_id
hr_bpm float32                # provenance
qrs_ms float32                # provenance
qtc_ms float32                # provenance
hr_label  str                 # bradycardia | normal | tachycardia
qrs_label str                 # normal | borderline | wide
qtc_label str                 # short | normal | prolonged
```

**4.A.2.6 Metrics.** Per-head macro-AUPRC primary, per-class AUPRC,
per-class F1 at val-optimal threshold.

**Regression heads (Round 10.1).** A2 also carries three continuous heads —
`hr_bpm`, `qrs_ms`, `qtc_ms` — alongside the bins. Plan A/B §5.4 makes
MAE/RMSE the PRIMARY metric for heart rate and QRS duration ("MAE, RMSE,
Pearson/Spearman, Bland-Altman"; "MAE/RMSE; percentage within 10 ms") and §7.1
repeats it for the whole regression/measurement task type; bins alone cannot
produce a limits-of-agreement plot, which is the standard figure for an ECG
measurement paper. Reported per head, in real units:

| metric | note |
| --- | --- |
| MAE, RMSE | Plan §7.1 primary pair for this task type |
| R², Pearson r, Spearman r | Plan §5.4 secondary |
| bias, SD of differences, 95 % limits of agreement | Bland-Altman (Plan §5.4) |
| percentage within tolerance | QRS ±10 ms is Plan-mandated; **HR ±5 bpm and QTc ±20 ms are declared conventions, not from the plan** — disclose |

Targets are standardised by DECLARED PHYSIOLOGICAL CONSTANTS
(`task_spec.MEASUREMENT_REGRESSION`), never by statistics fitted to a split, so
no split can leak through the scaling; `31_eval.py` inverts it and every
reported number is in bpm or ms. The bins remain the early-stopping metric —
§4.A.2.6's macro-AUPRC is unchanged — so this adds no run. **B2 keeps bins
only**: its parquet carries no continuous columns and Plan §7.1 scores the
robustness task type on AUCC and relative drop, not MAE.

**4.A.2.7 Baselines.**

| Tier              | Baseline                                                                                       | Required |
| ----------------- | ---------------------------------------------------------------------------------------------- | -------- |
| Algorithmic       | NeuroKit2 R-peak detector → instantaneous HR mean; NeuroKit2 QRS delineator → QRS duration mean | Yes      |
| Signal raw        | 1D ResNet (§5) on `raw_lead2`                                                                  | Yes      |
| Signal pre-proc   | 1D ResNet (§5) on `preprocessed_lead2`                                                         | Yes      |
| Signal 12-lead    | 1D ResNet (§5) on `raw_12lead`                                                                 | Yes      |

**4.A.2.8 Sensitivity analyses.** Per Plan A/B §5.4: "Report performance
by SQI tier to show where automatic label reproduction fails." Required:

- Per-SQI tier (high / medium / low) for each head.
- Per-cart_id top-5.
- Lead-II vs 12-lead head-to-head.
- L3 only vs L3+L2 (A2 is L3 primary; B1 covers the broader cohort).

---

#### 4.A.3 — A3: Lab abnormality prediction (7 labs × 5 windows)

**4.A.3.1 Purpose.** Predict whether each of seven primary labs is
abnormal in time-windowed proximity to the ECG. Plan A/B §5.5.

**4.A.3.2 Cohort.** All ECGs with `link_tier == 'L3'` (primary) or
`L3+L2` (sensitivity). Subject filter via global split.

**Pre-requisite:** the locked
`config/lab_itemid_map_LOCKED.yaml` extends `config/key_labs.yaml`
with calcium and magnesium itemids. The agent must:

1. Search `d_labitems` for case-insensitive labels per Plan A/B
   Appendix C step 1 (calcium / ionized calcium / magnesium).
2. Manually review units and fluids per Appendix C step 2 (serum
   only, no urine / CSF).
3. Lock the final itemid list as `config/lab_itemid_map_LOCKED.yaml`
   with both `key_labs.yaml`'s existing items and the new Ca/Mg
   items, and stamp the row count back into
   `config/dataset_versions.yaml` and `config/decision.yaml`
   `key_labs:` block.
4. Re-run `phase1_dataset_generation/44_label_availability.py`
   restricted to the new lab set to refresh
   `data/processed/linkage/label_availability.parquet`'s key_lab
   columns. This is a small incremental rerun, not a Phase 1 full
   regen.
5. Verify Ca and Mg ±24 h coverage in the L3 cohort is ≥ 50 %
   before locking; if lower, downgrade the locked lab set to the
   5-lab default and flag in the cohort_audit.md.

**4.A.3.3 Label generation.** Per Plan A/B Appendix C lab-abnormality
logic. For each ECG × lab × window combination, find candidate lab
events with same `subject_id` (optionally same `hadm_id`) within the
window. Choose the lab with smallest absolute time difference to
ecg_time. Then:

```python
if valuenum is null:
    label = "missing"
elif ref_range_lower is not null and valuenum < ref_range_lower:
    label = "low_abnormal"
elif ref_range_upper is not null and valuenum > ref_range_upper:
    label = "high_abnormal"
elif flag indicates abnormal:
    label = "abnormal_unknown_direction"
else:
    label = "normal"
```

5-class label space. Per Plan A/B §5.5 "Selection bias: Labs are drawn
because clinicians suspect problems. Report lab availability as a
modelable missingness process." The "missing" class is **NOT** dropped
— it's a real class in the cohort table.

**Windows** (per Plan A/B §5.5):

| Window            | Definition                                  |
| ----------------- | ------------------------------------------- |
| `pm24h` (primary) | nearest lab in `[-24h, +24h]`               |
| `pre_24h`         | nearest lab in `[-24h, 0]`                  |
| `post_24h`        | nearest lab in `[0, +24h]`                  |
| `pm6h`            | sensitivity: nearest lab in `[-6h, +6h]`    |
| `pm12h`           | sensitivity: nearest lab in `[-12h, +12h]`  |

5 windows × 7 labs = 35 binary heads. Multi-label classifier.

**4.A.3.4 Input policy.**

```yaml
A3_lab_abnormality:
  allowed:   [raw_lead2, raw_12lead, preprocessed_lead2, preprocessed_12lead,
              image_clean_lead2, image_clean_12lead,
              image_scanlike_lead2, image_scanlike_12lead,
              report_text]
  forbidden: [machine_measurements, structured_features]
  leakage_rationale: |
    Lab labels are EHR-derived, not ECG-derived, so signal/image/text are
    legitimate inputs. Structured features are forbidden because some
    labs (K, troponin) have stereotypical ECG signatures (peaked T waves,
    ST elevation) that the model should learn from raw signal — feeding
    pre-computed morphology features would short-circuit that learning
    and bias the comparison.
```

**4.A.3.5 Output schema.**

```
study_id, subject_id, split, link_tier, sqi_tier, cart_id
boundary_flag bool
hadm_id int64?
ecg_time timestamp_ns
# 35 columns of form: lab_<name>_<window>_label  (categorical 5-class)
# 35 columns of form: lab_<name>_<window>_signed_hours_from_ecg (float32)
# 35 columns of form: lab_<name>_<window>_abnormal_method (str)  # ref_range | flag | locked_threshold
```

**4.A.3.6 Metrics.**

- Primary: per-(lab,window) AUPRC for `low_abnormal`, `high_abnormal`,
  and combined `any_abnormal`. macro-AUPRC across 7 labs (the primary
  pm24h window only) as the headline number.
- Calibration: reliability diagram, ECE, Brier for K, troponin, Na,
  Cr at pm24h (the 4 labs with the strongest clinical signal).
- Missingness model: separate logistic regression predicting `missing`
  vs `not_missing` from ECG features. Reported in supplementary;
  documents the modelable missingness process per Plan A/B §5.5.

**4.A.3.7 Baselines.** Same matrix as A1, **including the algorithmic tier**
(Round 10.3). This section previously waived it — "no rule-based ECG → lab
predictor exists" — which is true of a *rule* but not of what Plan A/B §5.9
asks for: §5.9 requires the structured baseline (logistic regression / XGBoost
on machine measurements and/or NeuroKit features) for **A1, A3 and A6**, and
reference [R5] (CardioLab, ECG features → lab values) is precisely that
comparison. Without it A3's neural numbers have no floor, and the obvious
reviewer question — "does a logistic regression on HR/QRS/QTc already predict
hyperkalaemia?" — has no answer.

| Tier | Baseline | Required |
| --- | --- | -------- |
| Algorithmic | Multinomial logistic regression on machine-measurement summary stats (HR/QRS/QTc/axis/PR), fit on train, scored on test, one model per (lab × window) head. FORBIDDEN as model input; permitted here under the `baseline_only_exemptions` block A3 now declares, exactly as A1 does. | Yes |

Everything else is A1's matrix unchanged.

**4.A.3.8 Sensitivity analyses.**

- Lab window sensitivity table: per-lab AUPRC across the 5 windows.
- pre_24h vs post_24h: does ECG predict labs done after it (causality
  direction sanity check).
- L3 only vs L3+L2.
- Per-SQI-tier breakdown.
- Same-hadm restriction (require lab to share `hadm_id` with the ECG's
  linked admission).

---

#### 4.A.4 — A4: Temporal/waveform event localization (R-peaks + QRS bounds)

**4.A.4.1 Purpose.** Predict R-peak sample positions and QRS onset/offset
spans within the 10-second strip. Per Plan A/B §5.6: "Prefer QRS/
fiducial/local artifact localization." Round-2.5 decision: R-peak +
QRS bound localization (not 10-bin queries — that's B3).

**4.A.4.2 Cohort.**

| Filter                                                            | Expected effect |
| ----------------------------------------------------------------- | --------------- |
| `link_tier == 'L3'` (primary)                                     | ~468 K          |
| `waveform_qc.decode_ok == True` and `length_ok == True`           |                 |
| `sqi_tier ∈ {high, medium}` (low-SQI signals don't give reliable fiducial ground truth) | drop ~1 K       |
| Ground-truth R-peaks exist (computed by NeuroKit2 in Phase 1 Stage 7) |                 |

Sensitivity cohort: full clean cohort regardless of link_tier
(reported separately) — this is essentially the B3 cohort but with
fiducial-only labels.

**4.A.4.3 Label generation.** Ground truth from NeuroKit2 wavelet
delineation.

> **CORRECTION 2026-08-26 (Round 5.2).** This section previously stated
> that the per-study fiducial arrays were "already cached during Phase 1
> Stage 7 … extract from the per-study lists in
> `structured_features.parquet`". **They were not.** Verified against the
> on-disk file: `structured_features.parquet` (800,035 rows) has exactly
> one list column, `sqi_per_lead: list<float>` (12 values), plus scalar
> aggregates (`qrs_ms`, `qt_ms`, `pr_ms`, `qtc_bazett_ms`,
> `machine_qrs_onset`, `machine_qrs_end`, …). **No sample-position arrays
> exist anywhere in Phase 1's outputs.**
>
> Resolution: Stage P2.1 gains a new first script,
> `00_extract_fiducials.py`, which re-runs NeuroKit2 wavelet delineation
> over the A4 cohort and writes the arrays below to
> `data/processed/fiducials_lead2.parquet`. It is CPU-only and
> embarrassingly parallel (~5–10 h on 20 threads; runs on `cpu_student`
> per the execution plan). **It must reuse the corrected Pan–Tompkins
> R-peak code path from the Phase 1 regen** — the detector bug fixed in
> that regen must not be reintroduced by a fresh implementation. B3's
> oracle baseline reads the same file.
>
> Storage: the arrays are stored **sparse** (peak positions), not as
> dense 5000-sample masks. Dense int8 masks would cost 2.3 GB for the
> 468 K cohort; the sparse form is ~25 MB. The dataloader expands to a
> dense mask at batch time. Same information, no science change.

Schema (in `data/processed/fiducials_lead2.parquet`, one row per study):

```
r_peaks_lead2     list<int32>  # sample positions, 0-indexed into 5000-sample signal
qrs_onsets_lead2  list<int32>  # one per R-peak
qrs_offsets_lead2 list<int32>  # one per R-peak
n_peaks           int32
```

Plan A/B §5.6 metric: tolerance window for "hit" = ±10 ms (= ±5 samples
at 500 Hz). For QRS boundaries: ±10 ms tolerance per boundary.

**4.A.4.4 Input policy.**

```yaml
A4_event_localization:
  allowed:   [raw_lead2, raw_12lead, preprocessed_lead2, preprocessed_12lead]
  forbidden: [machine_measurements, structured_features, report_text,
              image_clean_lead2, image_clean_12lead,
              image_scanlike_lead2, image_scanlike_12lead]
  leakage_rationale: |
    Labels are derived from NeuroKit2 wavelet delineation of the
    Lead-II raw signal. Structured features carry aggregate timing
    information from the same delineation, so including them would
    leak the labels. report_text and machine_measurements summarize
    timings (qrs_onset/end) which are global aggregates of the
    per-peak labels — also leakage. Image is forbidden because the
    rendered ECG image visually shows the QRS complex boundaries
    (model could pixel-trace).
```

**4.A.4.5 Output schema.**

```
study_id, subject_id, split, link_tier, sqi_tier, cart_id
r_peaks_lead2  list<int32>
qrs_onsets_lead2  list<int32>
qrs_offsets_lead2 list<int32>
n_peaks int32
# Pre-computed binary masks at 500 Hz (5000-sample length) for fast loader:
r_peak_mask  list<bool>  # length 5000, True within ±5 samples of any R-peak
qrs_mask     list<bool>  # length 5000, True within any QRS onset–offset span
```

**4.A.4.6 Metrics.**

- Primary: F1 of R-peak detection at ±10 ms tolerance; mean absolute
  timing error per R-peak.
- Secondary: F1 of QRS-onset detection at ±10 ms; F1 of QRS-offset
  at ±10 ms; mean absolute QRS duration error.
- Event-count distribution: per-study `(predicted_n_peaks,
  true_n_peaks)` histogram in supplementary.

**4.A.4.7 Baselines.**

| Tier        | Baseline                                                                                         | Required |
| ----------- | ------------------------------------------------------------------------------------------------ | -------- |
| Algorithmic | NeuroKit2 Pan-Tompkins R-peak detector + wavelet QRS delineator (same as ground truth → oracle) | Yes      |
| Signal      | 1D U-Net-style sequence-to-sequence head (§5) on `raw_lead2`                                     | Yes      |
| Signal preproc | Same on `preprocessed_lead2`                                                                  | Yes      |

The algorithmic baseline is the same algorithm that generated the
ground truth, so its F1 is by construction 1.0 — it's reported as an
oracle reference. The interesting question is whether a learned
detector matches or exceeds it under noise (covered by B2 cross-task
analysis).

**4.A.4.8 Sensitivity analyses.**

- Per-SQI-tier (high / medium / low) F1.
- L3 only vs full clean cohort.
- Raw vs preprocessed signal.
- Per-cart_id top-5.

---

#### 4.A.5 — A5: Cross-modal verification + masked attribute prediction

**4.A.5.1 Purpose.** Two heads on a shared tri-encoder: (1) verify that
signal+image+text triple belongs to one study; (2) given signal+image,
predict masked HR/QRS/QTc bins from text. Per Plan A/B §5.7 and
Round-2.5 decision.

**4.A.5.2 Cohort.** All ECGs in the clean cohort, regardless of EHR
linkage tier (the cross-modal alignment is signal/image/text-internal;
EHR isn't needed). 70/10/20 split inherited.

**4.A.5.3 Label generation.**

**Verification head (5 negative types per Phase 1 Truth doc Task A
§6.2):**

| Negative type        | Construction                                                                                 |
| -------------------- | -------------------------------------------------------------------------------------------- |
| `TEXT_SWAP`          | Replace text with text from a different subject's study                                      |
| `IMAGE_SWAP`         | Replace image with image from a different subject's study                                    |
| `SIGNAL_SWAP`        | Replace signal with signal from a different subject's study                                  |
| `HARD_NEGATIVE_TEXT` | Replace text with text from a same-HR-bucket-but-different-subject study (hard mismatch)     |
| `PARTIAL_MISMATCH`   | Replace two modalities, keep one anchor-aligned                                              |

For each anchor study: 2 positives (clean image + scanlike image) and
5 negatives = 7 rows per study (HARD_NEGATIVE_TEXT only when a
same-HR-bucket alternative exists).

**Masked attribute head:** for each anchor study, generate an
attribute-masked text variant where numeric mentions of HR, QRS, QT,
QTc, axis, and intervals are replaced with `[MASK]`. The model must
predict the binned HR/QRS/QTc from signal+image inputs. Labels are the
A2-bin definitions.

**4.A.5.4 Input policy.**

```yaml
A5_cross_modal_verification:
  allowed:   [raw_lead2, raw_12lead, preprocessed_lead2, preprocessed_12lead,
              image_clean_lead2, image_clean_12lead,
              image_scanlike_lead2, image_scanlike_12lead,
              report_text, report_text_masked]
  forbidden: [machine_measurements, structured_features]
  leakage_rationale: |
    The verification head needs all three modalities — that IS the
    task. The masked-attribute head needs signal + image as inputs and
    predicts binned attributes; report_text_masked is the source of
    the "what's been masked" provenance and is allowed only because
    its numeric content has been removed. Structured features are
    forbidden because they encode the same numerics by another route.
```

**4.A.5.5 Output schema.**

```
# verification rows:
anchor_study_id  int64
signal_id        int64
image_id         int64
text_id          int64
image_type       str    # clean | scanlike | clean_12lead | scanlike_12lead
y_match          int8   # 0 or 1
neg_type         str?   # null for positives
split            str

# masked-attribute rows (one per study, but generated as a separate parquet
# tasks/A5_cross_modal_verification/masked_attribute_{train,val,test}.parquet):
study_id              int64
subject_id            int64
split                 str
report_text_masked    str       # numerics → [MASK]
hr_label              str       # bradycardia | normal | tachycardia
qrs_label             str       # normal | borderline | wide
qtc_label             str       # short | normal | prolonged
masked_positions      list<int> # char positions of masked tokens
```

**4.A.5.6 Metrics.**

- Verification: AUPRC, AUROC, macro-F1, per-`neg_type` F1.
- Masked attribute: per-head macro-AUPRC (matches A2 metric for fair
  comparison).
- Retrieval-style metric (Recall@1 at 100-pool) reported for the
  verification model as a secondary check — does the same model rank
  correctly under retrieval framing?

**4.A.5.7 Baselines.**

| Tier        | Baseline                                                       | Required |
| ----------- | -------------------------------------------------------------- | -------- |
| Embedding   | Cosine-similarity between frozen S/I/T embeddings (Truth §9.1) | Yes      |
| Tri-encoder | Tri-encoder + small fusion MLP (Truth §9.3)                    | Yes      |
| Cross-attention | Tri-encoder + cross-attention fusion (§5)                  | Yes      |
| Algorithmic | NONE — no rule baseline exists for cross-modal                 | n/a      |

**4.A.5.8 Sensitivity analyses.**

- Per-`neg_type` F1 table (easy random vs hard same-HR-bucket).
- Clean vs scan-like image breakdown.
- Lead-II vs 12-lead image.
- With vs without HARD_NEGATIVE_TEXT in train (does the model
  generalize to hard mismatches it didn't see?).
- Masked-attribute performance with and without the verification head
  (multi-task ablation).

---

#### 4.A.6 — A6: Risk stratification (mortality + readmission at 30d + 90d)

**4.A.6.1 Purpose.** Predict observed 30- and 90-day mortality and
readmission after the ECG. Plan A/B §5.8.

**4.A.6.2 Cohort.**

| Filter                                                                  | Expected effect              |
| ----------------------------------------------------------------------- | ---------------------------- |
| `link_tier == 'L3'` (primary)                                           | ~468 K                       |
| `mortality_observable == True` per `label_availability.parquet`         | ~494,411 (61.8 %) any link    |
| `link_type ∈ {hospital_exact, hospital_tolerance}` (readmission only)   | ED-only ECGs excluded from readmission head |
| Boundary flag included; sensitivity reports excluded set                |                              |

ED-only ECGs ARE included in mortality head (`patients.dod` is observable
regardless of admission). They're excluded from readmission per Plan
A/B §5.8: "For ED-only ECGs, define carefully or exclude from
readmission main analysis."

**4.A.6.3 Label generation.**

```python
# Mortality
dod = patients.dod[subject_id]                # may be null
deathtime_hosp = admissions.deathtime[hadm_id]  # may be null
death_time = dod if not null else deathtime_hosp
mortality_30d = (death_time is not null) and (0 < death_time - ecg_time <= 30 days)
mortality_90d = (death_time is not null) and (0 < death_time - ecg_time <= 90 days)
# If no death observed, label is 0 for both (with mortality_observable flag in
# cohort row so sensitivity can account for follow-up censoring).

# Readmission
# For an ECG during an admission with hadm_id:
discharge_time = admissions.dischtime[hadm_id]
next_admission = min(other admissions.admittime where subject_id matches and
                     admittime > discharge_time and not same hadm_id and
                     not just a transfer)
readmission_30d = (next_admission - discharge_time <= 30 days)
readmission_90d = (next_admission - discharge_time <= 90 days)
# Exclude rows where the readmission censoring window cannot be observed
# (e.g., ECG too recent to the end-of-data cutoff).
```

Index time per Plan A/B §5.8: ecg_time. No post-ECG features.

**4.A.6.4 Input policy.**

```yaml
A6_risk_stratification:
  allowed:   [raw_lead2, raw_12lead, preprocessed_lead2, preprocessed_12lead,
              image_clean_lead2, image_clean_12lead,
              image_scanlike_lead2, image_scanlike_12lead,
              report_text]
  forbidden: [machine_measurements, structured_features]
  leakage_rationale: |
    Labels are derived from EHR mortality/readmission, not from any ECG
    measurement, so signal/image/text are legitimate. structured_features
    and machine_measurements are forbidden because they side-channel
    encode the ECG into a small numeric vector that would let the
    multimodal model achieve high performance via tabular shortcut
    rather than learning ECG-from-modality. Letting them in would also
    bias the comparison vs single-modality baselines.
```

**4.A.6.5 Output schema.**

```
study_id, subject_id, split, link_tier, sqi_tier, cart_id
boundary_flag bool
hadm_id int64?     # null for ED-only
ecg_time timestamp_ns
mortality_30d bool
mortality_90d bool
mortality_observable bool      # provenance; false if follow-up window unobservable
readmission_30d bool?          # null for ED-only ECGs
readmission_90d bool?          # null for ED-only ECGs
readmission_eligible bool      # provenance; false if observed window < horizon
days_to_death float32?         # provenance; null if alive at observation
days_to_readmission float32?   # provenance
```

**4.A.6.6 Metrics.**

- Primary: per-head AUPRC (4 heads: mort_30, mort_90, readm_30, readm_90).
  AUROC secondary.
- Calibration: reliability diagram, ECE, Brier per head. Required.
- Threshold selection: validation-set Youden's J per head; also report
  precision @ recall=0.5 and recall @ precision=0.5.
- Decision-curve analysis: net benefit at clinically relevant
  thresholds (e.g., 5 %, 10 % risk) per head. Supplementary.

**4.A.6.7 Baselines.**

**The nested clinical ladder is mandatory (Round 10.2).** Plan A/B §5.8
specifies six baseline tiers and its Figure 5 is the nested curve across them;
Plan §7 names the failure condition outright — *"Only compared to
random/prevalence baseline"* — and §1.1 makes this ladder the evidence for the
claim **"ECG adds prognostic signal beyond demographics."** This section
previously carried one Cox model that bundled age, sex and the machine
measurements together, then jumped straight to the neural tiers, so the
intermediate rungs did not exist — and neither did the columns to build them.
A6's schema now carries them (see §4.A.6.5), every one knowable at `ecg_time`.

| Tier            | Baseline                                                                 | Required |
| --------------- | ------------------------------------------------------------------------ | -------- |
| Prevalence      | Intercept only — the train prevalence per head. Plan §5.8's "minimum sanity baseline" | Yes |
| Demographics    | Logistic regression on `age_at_ecg + sex_male + race + insurance`         | Yes      |
| + comorbidities | Adds the five `prior_dx_*` flags — prior ICD from admissions **discharged before the ECG**, using the locked A1 group map | Yes |
| + utilization   | Adds `n_prior_admissions`, `n_prior_ecgs`, `days_since_last_discharge`, `admission_type`, `ed_disposition`. Plan §5.8: "controls for sick-patient ECG frequency" | Yes |
| Algorithmic     | Cox proportional hazards on age + sex + machine HR + QRS + QTc (FORBIDDEN as model input, ALLOWED as baseline-only) | Yes      |
| Signal          | 1D ResNet (§5) on `raw_lead2`                                            | Yes      |
| Signal 12-lead  | 1D ResNet on `raw_12lead`                                                | Yes      |
| Image           | Image backbone on `image_clean_lead2`                                    | Yes      |
| Text            | Text backbone on `report_text`                                           | Yes      |
| Multimodal      | Fusion head on raw_lead2 + image + text                                  | Yes      |
| Multimodal-12   | Fusion head on raw_12lead + image_clean_12lead + text                    | Yes      |

**4.A.6.8 Sensitivity analyses.**

- First-ECG-per-admission only (primary supplementary table per
  Plan A/B §5.8).
- First-ECG-per-patient only.
- L3 only vs L3+L2 (primary in L3).
- Boundary excluded sensitivity.
- Mortality-observable only (drop censored rows).
- Per-SQI-tier breakdown.
- Per-cart_id top-5.
- Raw vs preprocessed signal.

---

### 4.B — Plan B tasks (supplementary)

Plan B tasks do not require EHR linkage and use the full clean ECG
cohort.

#### 4.B.1 — B1: Measurement-blind physiological inference (Plan B primary task)

**4.B.1.1 Purpose.** Same as A2 (predict binned HR/QRS/QTc from signal
alone) but on the full clean cohort (not L3-restricted). Plan A/B §6.2:
"Same implementation as Task A2, but this becomes one of the central
Plan B tasks."

**4.B.1.2 Cohort.** Full clean cohort (`ecg_metadata_clean.parquet` ∩
`waveform_qc.decode_ok=True ∩ length_ok=True`). ~799,K ECGs.
70/10/20 split inherited.

**4.B.1.3 Label generation.** Identical to §4.A.2.3.

**4.B.1.4 Input policy.** Identical to §4.A.2.4 (same `allowed` /
`forbidden`).

**4.B.1.5 Output schema.** Identical to §4.A.2.5 (but with `link_tier`
populated for all rows; can be L0 for unlinked ECGs).

**4.B.1.6 Metrics.** Identical to §4.A.2.6.

**4.B.1.7 Baselines.** Identical matrix to §4.A.2.7.

**4.B.1.8 Sensitivity analyses.**

- Per-SQI tier.
- Per-cart_id top-5.
- Per-linkage-tier (L3/L2/L1/L0) — does the Plan B model perform
  uniformly across linkage status? Adds a Plan A/B-distinct claim.
- Lead-II vs 12-lead.

---

#### 4.B.2 — B2: Noise-robustness curriculum

**4.B.2.1 Purpose.** Quantify performance degradation of B1 models on
corrupted signals. Plan A/B §6.3. Three evaluation regimes.

**4.B.2.2 Cohort.**

| Subset                | Source                                                                     | Size            |
| --------------------- | -------------------------------------------------------------------------- | --------------- |
| Anchor pool           | Test-split ECGs with `sqi_tier='high'`                                     | ~2,000 anchors  |
| Corrupted variants    | `data/processed/signals_corrupted.parquet` from Phase 1 Stage 8            | 80,000 rows (2K × 8 × 5) |
| Held-out clean test   | Anchors' clean signal from `signals/lead2_raw.h5`                          | 2,000           |
| Natural-SQI test      | Test-split ECGs split by SQI tier from `waveform_qc.parquet`               | ~78 K total     |

Corruption families: gaussian, baseline_wander, powerline, EMG,
electrode_motion, lead_dropout, gain_drift, saturation. SNR levels:
30, 20, 10, 5, 0 dB.

**4.B.2.3 Label generation.** B1 labels (hr_label, qrs_label, qtc_label)
attached to each anchor; the corrupted variants inherit the anchor's
labels. The corruption metadata (`corruption_type`, `snr_db`) attaches
as provenance columns.

**4.B.2.4 Input policy.**

```yaml
B2_noise_robustness:
  allowed:   [raw_lead2, preprocessed_lead2, signal_corrupted]
  forbidden: [raw_12lead, preprocessed_12lead,
              image_clean_lead2, image_clean_12lead,
              image_scanlike_lead2, image_scanlike_12lead,
              report_text, machine_measurements, structured_features]
  leakage_rationale: |
    Same as B1 — labels derive from clean machine measurements; any
    input containing those values trivially leaks. Image is also
    forbidden because the corrupted signal's rendered image would
    show the corruption visually; we want the model to learn from
    signal directly.
```

**4.B.2.5 Output schema (`tasks/B2_noise_robustness/{train,val,test}.parquet`).**

```
study_id  int64           # anchor study id
subject_id int64
split    str
clean_signal_kind    str  # always "raw_lead2"
corrupted_signal_kind str  # always "signal_corrupted" for the corrupted row
corruption_type str
snr_db int
hr_label, qrs_label, qtc_label str
regime  str       # regime_1 | regime_2 | regime_3
```

Train rows for regime_2 (noise-augmented training) include synthetic
corruption applied **on the fly** during training; the training-time
corruption is drawn from the same `corruption_recipes_LOCKED.yaml`
distribution but uses a different RNG seed than the test set. Test
rows always read from the locked `signals_corrupted.parquet`.

**4.B.2.6 Metrics.**

- Primary: area under corruption curve (AUCC) per corruption type
  (AUPRC averaged across SNR levels), relative-performance-drop
  (clean − corrupted) per (type, SNR), collapse threshold (SNR at
  which AUPRC drops below 50 % of clean).
- Per-(corruption_type, snr_db) AUPRC table (8 × 5 grid).
- Regime-comparison summary: regime_1 vs regime_2 average drop;
  regime_3 SQI-tier breakdown.

**4.B.2.7 Baselines.**

| Tier               | Baseline                                                                                | Required |
| ------------------ | --------------------------------------------------------------------------------------- | -------- |
| Algorithmic        | NeuroKit2 R-peak detector + thresholded HR — evaluate the algorithm on corrupted signals | Yes      |
| Signal clean-train | 1D ResNet trained on clean only, tested on corrupted (regime_1)                          | Yes      |
| Signal noise-aug   | 1D ResNet with on-the-fly corruption augmentation (regime_2)                             | Yes      |
| Signal preprocessed | Same on `preprocessed_lead2` to test whether preprocessing helps                        | Yes      |

**4.B.2.8 Sensitivity analyses.**

- Regime_1 vs regime_2 head-to-head on identical corrupted test set.
- Per-corruption-family ranking (which family hits hardest).
- Per-SQI tier on natural data (regime_3).
- Raw vs preprocessed signal across regimes.

---

#### 4.B.3 — B3: Temporal grounding (10-bin queries)

**4.B.3.1 Purpose.** Predict per-bin presence of physiological queries
within a 10-second strip. Plan A/B §6.4 + Round-2.5 decision.

**4.B.3.2 Cohort.** Full clean cohort, signal/text-only modalities.
70/10/20 split inherited.

**4.B.3.3 Label generation.** 10 one-second bins per study. Queries
(4 total per Round 2.5):

| Query              | Bin-label rule                                                                                            |
| ------------------ | --------------------------------------------------------------------------------------------------------- |
| `HIGH_HEART_RATE`  | bin label 1 if local instantaneous HR (NeuroKit2 RR midpoints in bin) > 100 bpm                           |
| `LOW_HEART_RATE`   | bin label 1 if local instantaneous HR < 60 bpm                                                            |
| `WIDE_QRS`         | bin label 1 if any beat with QRS onset in bin has duration > 60 samples (120 ms)                          |
| `NOISY_SEGMENT`    | bin label 1 if SQI per-second (windowed NeuroKit2 ecg_quality) < 0.6 in this bin (locked train-set threshold) |

Threshold for `NOISY_SEGMENT` is fixed on the **train** set: compute
per-bin SQI distribution on train, pick the 25th percentile as the
"noisy" threshold, lock it in `config/task_definitions.yaml`. Doc
mandates threshold from train only.

**4.B.3.4 Input policy.**

```yaml
B3_temporal_grounding:
  allowed:   [raw_lead2, raw_12lead, preprocessed_lead2, preprocessed_12lead]
  forbidden: [machine_measurements, structured_features, report_text,
              image_clean_lead2, image_clean_12lead,
              image_scanlike_lead2, image_scanlike_12lead]
  leakage_rationale: |
    Bin labels derived from local R-peak detection + per-bin SQI.
    Aggregate machine measurements (rr_interval, qrs_*) summarize the
    same quantities and would leak. Image is forbidden for the same
    fiducial-leakage reason as A4.
```

**4.B.3.5 Output schema.**

```
study_id, subject_id, split, link_tier, sqi_tier, cart_id
query        str       # HIGH_HEART_RATE | LOW_HEART_RATE | WIDE_QRS | NOISY_SEGMENT
labels       list<int8>  # length 10, binary per-bin
fallback_used  bool       # provenance: true if R-peak detection failed
```

**4.B.3.6 Metrics.**

- Primary: mIoU across all queries (Truth doc §7.4).
- Secondary: Recall@1 with IoU ≥ 0.3, Recall@1 with IoU ≥ 0.5,
  no-evidence accuracy (per Truth doc §7.4).
- Per-query AUPRC at bin level.
- Event-count distribution per query.

**4.B.3.7 Baselines.**

| Tier        | Baseline                                                                          | Required |
| ----------- | --------------------------------------------------------------------------------- | -------- |
| Algorithmic | Rule-based per-bin labeler from NeuroKit2 R-peaks + SQI (oracle by construction)   | Yes      |
| Signal     | 1D U-Net query-conditioned per-bin head on `raw_lead2`                            | Yes      |
| Signal preprocessed | Same on `preprocessed_lead2`                                              | Yes      |

**4.B.3.8 Sensitivity analyses.**

- Per-query mIoU.
- Per-SQI tier.
- Lead-II vs 12-lead.
- Show example successes and failures (Plan A/B §6.4) in supplementary.

---

#### 4.B.4 — B4: Cross-modal verification (Plan B counterpart to A5)

**4.B.4.1 Purpose.** Verification-only counterpart to A5. Plan A/B §6.5.

**4.B.4.2 Cohort.** Full clean cohort. Identical to A5 cohort.

**4.B.4.3 Label generation.** Same 5-negative-type construction as
A5's verification head (no masked-attribute head in B4). One verification
sample stream.

**4.B.4.4 Input policy.** Same as A5's verification head:

```yaml
B4_cross_modal_verification:
  allowed:   [raw_lead2, raw_12lead, preprocessed_lead2, preprocessed_12lead,
              image_clean_lead2, image_clean_12lead,
              image_scanlike_lead2, image_scanlike_12lead,
              report_text]
  forbidden: [machine_measurements, structured_features]
  leakage_rationale: same as A5 verification head
```

**4.B.4.5 Output schema.** Same as A5 verification rows.

**4.B.4.6 Metrics.** AUPRC, AUROC, macro-F1, per-`neg_type` F1,
Recall@1 retrieval secondary.

**4.B.4.7 Baselines.** Same matrix as A5 verification.

**4.B.4.8 Sensitivity analyses.**

- Same as A5 verification head, minus the masked-attribute ablation.
- B4 vs A5-verification: does training jointly with masked-attribute
  hurt or help pure verification?

---

#### 4.B.5 — B5: Contradiction detection in reports

**4.B.5.1 Purpose.** Detect injected contradictions in machine reports
and localize the corrupted span. Plan A/B §6.6 + Round-2 decision:
HR + QRS + axis + PR (4 families).

**4.B.5.2 Cohort.** Full clean cohort. ECGs with valid measurements
for the relevant family — see contradiction injection rules below.

**4.B.5.3 Label generation.** For each ECG, generate one **uncorrupted**
row (`is_corrupted=False`) and (with 50 % probability — balanced) one
**corrupted** row from one of four families. Plan A/B §6.6: "Inject
only when measurement is far from decision boundary."

| Family | Injection condition                                                  | Swap                                                                                                                                          |
| ------ | -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| HR     | hr_bpm ≤ 50 (clear brady) OR hr_bpm ≥ 120 (clear tachy)              | swap "bradycardia"↔"tachycardia" in report text; record span                                                                                  |
| QRS    | qrs_ms ≥ 140 (clear wide) OR qrs_ms ≤ 90 (clear normal)              | swap "wide QRS"↔"narrow / normal QRS" in report text                                                                                          |
| Axis   | qrs_axis < -45 (clear LAD) OR qrs_axis > +105 (clear RAD)            | swap "left axis deviation"↔"right axis deviation" in report text                                                                              |
| PR     | pr_ms > 240 (clear first-deg AVB) OR pr_ms ≤ 160 (clear normal PR)   | swap "first-degree AV block"↔"normal PR" in report text. Requires `structured_features.parquet.pr_ms` present (sparse — drop rows where null) |

Injection-free zone (the doc-mandated "no swap" gap):

- HR 58–105: no HR injection.
- QRS 95–135: no QRS injection.
- Axis −35 to +95: no axis injection.
- PR 165–230: no PR injection.

Mid-range measurements have no contradiction row (only the
`is_corrupted=False` row).

**4.B.5.4 Input policy.**

```yaml
B5_contradiction_detection:
  allowed:   [raw_lead2, raw_12lead, preprocessed_lead2, preprocessed_12lead,
              report_text]                # the report being audited
  forbidden: [machine_measurements, structured_features,
              image_clean_lead2, image_clean_12lead,
              image_scanlike_lead2, image_scanlike_12lead]
  leakage_rationale: |
    machine_measurements and structured_features ARE the contradiction
    source — including them lets the model trivially recompute HR /
    QRS / axis / PR and detect mismatch. report_text is needed because
    that's the input being audited. Image is forbidden because a
    rendered ECG image visually shows HR / QRS / axis (model could
    pixel-trace and short-circuit signal+text comparison).
```

**4.B.5.5 Output schema.**

```
study_id, subject_id, split, link_tier, sqi_tier, cart_id
is_corrupted          bool
contradiction_type    str?   # null for is_corrupted=False; else HR | QRS | axis | PR
contradiction_family  str?   # for table reporting
original_report_text  str
corrupted_report_text str?   # null for is_corrupted=False
corrupted_span_start  int32? # char-offset in corrupted_report_text
corrupted_span_end    int32?
source_measurement    str?   # JSON of {measurement_name, value} that drove injection
label                 str    # "clean" | "corrupted_HR" | "corrupted_QRS" | "corrupted_axis" | "corrupted_PR"
```

**4.B.5.6 Metrics.**

- Primary: AUPRC for binary `is_corrupted` head; macro-F1 across the
  5-class `label` head.
- Span localization: char-IoU between predicted and true spans; spans
  reported per family.
- Per-family detection rate (HR / QRS / axis / PR).

**4.B.5.7 Baselines.**

| Tier         | Baseline                                                                                | Required |
| ------------ | --------------------------------------------------------------------------------------- | -------- |
| Rule         | NeuroKit2 HR/QRS detector vs report-text regex → flag inconsistency (oracle-style)      | Yes      |
| Text-only    | Bio-ClinicalBERT classifier on `report_text` (does the report self-contradict?)         | Yes      |
| Signal-only  | 1D ResNet predicts HR/QRS/axis/PR, then compare predictions to report-text claims        | Yes      |
| Multimodal   | Tri-encoder (signal + text) with cross-attention; joint detection + span-prediction heads | Yes      |

**4.B.5.8 Sensitivity analyses.**

- Per-family detection AUPRC.
- Per-SQI tier (does noisy signal hurt detection?).
- Per-cart_id top-5.
- Lead-II vs 12-lead.

---

#### 4.B.6 — B6: Difficulty-stratified cross-modal verification

**4.B.6.1 Purpose.** Subset of B4 stratified by `neg_type` to expose
per-difficulty performance. Plan A/B §6.7.

**4.B.6.2 Cohort.** Same as B4. Reads from the same on-disk parquet —
B6 is an evaluation-time stratification, not a separate task dataset.
A separate `tasks/B6_difficulty_stratified/eval_keys.parquet` lists
the test-row groupings per difficulty tier.

Difficulty tiers:

**Six levels, not three (Round 10.4).** Plan A/B §6.7 specifies Levels 0–5 and
its Figure 4 is the *curve* across them — the evidence for Plan B's core
shortcut-elimination claim, whose predicted behaviour is "most shortcut models
plateau". The three tiers below originally collapsed to two, because the third
shipped empty; a two-point curve is not a curve, and the missing Level 4 is the
rung that tests the patient-identity shortcut, the one most likely to be real in
MIMIC where a subject carries many ECGs.

| Tier | Source rows | Plan §6.7 level |
| ---- | ----------- | --------------- |
| `level_0_random` | `neg_type ∈ {TEXT_SWAP, IMAGE_SWAP, SIGNAL_SWAP, PARTIAL_MISMATCH}` | 0 |
| `level_1_hr` | `HARD_NEGATIVE_TEXT` — same-HR-bucket swap | 1 |
| `level_2_hr_qrs` | `HARD_NEGATIVE_L2` — donor matched on HR + QRS bucket | 2 |
| `level_3_full_physio` | `HARD_NEGATIVE_L3` — matched on HR + QRS + axis + QTc | 3 |
| `level_4_same_patient` | `HARD_NEGATIVE_L4` — **the anchor's own subject**, another study | 4 |
| `level_5_near_duplicate` | `HARD_NEGATIVE_L5` — the anchor's own report with one claim swapped, reusing B5's locked injection | 5 |

**Levels 2–5 exist only in the TEST split**, and are therefore added to A5 and
B4 alike so §4.B.4.8's controlled comparison still holds. Two reasons, pointing
the same way: the levels measure *generalisation* to harder negatives, so
training on them would train away the plateau §6.7 predicts and Figure 4 would
describe the training distribution instead of the model; and keeping them out of
train means **no model is retrained** to obtain the curve. Round 3's reserved
"hard" tier is closed by this — its same-subject idea is Level 4.

Axis bucketing for Level 3 reads the locked clear zones in
`claim_dictionary_LOCKED.yaml` (LAD < −45°, normal −35…95°, RAD > 105°,
everything else `borderline`); no new threshold is invented.

**4.B.6.3 Label generation.** Inherited from B4 + `neg_type` column.

**4.B.6.4 Input policy.** Identical to B4.

**4.B.6.5 Output schema.** Pointer table only:

```
study_id, subject_id, neg_type, difficulty_tier, split
```

The actual rows live in B4 parquet.

**4.B.6.6 Metrics.** Per-difficulty-tier Recall@1, AUPRC.

**4.B.6.7 Baselines.** Inherited from B4 — same models, different
evaluation slice.

**4.B.6.8 Sensitivity analyses.** Per-difficulty per-`neg_type` table.

---

### 4.C — Cross-task invariants

These hold for every task above:

1. **No subject in two splits.** Every task's cohort is a subset of
   `data/processed/splits_subject_level.parquet` joined by `subject_id`.
   The split column is **always** populated from that join, never
   re-derived.
2. **Deterministic provenance.** Every label-generation step is
   deterministic given Phase 1 artifacts + locked YAMLs. Re-running
   the same builder on the same Phase 1 dataset produces byte-identical
   parquets.
3. **Manifest passthrough.** Task parquets carry `study_id` only for
   modality lookups; the loader resolves to bytes via §2.1 helper. No
   task parquet stores signal/image bytes directly. (Exception:
   `B5_contradiction_detection` stores `corrupted_report_text` because
   it is a derived text artifact, not a raw modality.)
4. **Audit gate before training.** No model training script may run
   until `outputs/audit_reports/leakage_audit_phase2.md`,
   `split_audit_phase2.md`, and `cohort_audit.md` are PASS for **every**
   task. The train script reads these files at start and halts if any
   is missing or FAIL.

---

## 5. Model architecture spec

This section defines every encoder, every fusion head, every algorithmic
baseline used in Phase 2. Architectures are **locked** here — no
per-task tweaking. The only per-task variability allowed is in the head
(number of output classes, multi-label vs single-label vs sequence
output) and the input modality subset (per `config/task_input_policy.yaml`).

**Locked choices (Round 3 + 3.5):**
- Signal encoder: **1D ResNet-18** trained from scratch.
- Image encoder: **ResNet-50** pretrained on ImageNet-1k.
- Text encoders: **TF-IDF + linear projection** (simple) and
  **Bio-ClinicalBERT** (strong). Both trained for every text-using
  task; the paper reports the stronger as primary and the simpler in
  supplementary.
- Fusion head: **late-fusion concat + MLP**.
- Primary signal modality: **preprocessed**.
- Primary image modality: **clean**.
- Primary lead set: **12-lead** (Lead-II reported separately as Track-1).

### 5.1 Algorithmic baselines (mandatory per Plan A/B §5.8, §6.2; Truth §9.1)

Implemented in `_model_lib/algorithmic_baselines.py`. No learned parameters.

| Task   | Algorithm                                                                                                     |
| ------ | ------------------------------------------------------------------------------------------------------------- |
| A2, B1 | NeuroKit2 R-peak detector → instantaneous HR mean → bin to {brady/normal/tachy}; NeuroKit2 wavelet QRS → QRS-duration mean → bin |
| A3     | Multinomial logistic regression on machine-measurement summary stats, per (lab × window) head — Plan A/B §5.9's structured baseline, restored (Round 10.3; §4.A.3.7 had waived it) |
| A6 ×4  | The Plan A/B §5.8 nested ladder: prevalence → demographics → +comorbidities → +utilization. Four sibling `arch_tier`s so §7 scores each rung with the trained-model code (Round 10.2) |
| A4     | NeuroKit2 Pan-Tompkins R-peak + wavelet QRS delineator — F1=1.0 oracle (the same algorithm that built ground truth) |
| A6     | Cox proportional hazards on `age + sex + machine_hr_bpm + machine_qrs_ms + machine_qtc_ms`, fit on train, scored on test (Note: machine features are forbidden as MODEL input but allowed as BASELINE input for this single baseline) |
| B3     | Rule-based per-bin labeler from NeuroKit2 R-peaks + per-bin SQI threshold (oracle by construction)             |
| B5     | NeuroKit2 HR/QRS detector vs report-text regex inconsistency flag                                              |

Algorithmic baselines run once on test set (no seed variability). CIs
from patient-level bootstrap n=10,000 like all other models.

### 5.2 Signal encoder — 1D ResNet-18

`_model_lib/signal_encoders.py::ECGResNet1D18`

```
Input:  (B, n_leads, 5000) float32 where n_leads ∈ {1, 12}
Stem:   Conv1d(n_leads, 64, kernel=15, stride=2, padding=7) + BN + ReLU + MaxPool1d(3, stride=2)
Stage 1: 2 × BasicBlock1D(64,  64,  stride=1)
Stage 2: 2 × BasicBlock1D(64,  128, stride=2)
Stage 3: 2 × BasicBlock1D(128, 256, stride=2)
Stage 4: 2 × BasicBlock1D(256, 512, stride=2)
Head:   AdaptiveAvgPool1d(1) → flatten → Linear(512, embed_dim=512)
Output: (B, 512) embedding
```

`BasicBlock1D` is the standard 2-conv ResNet basic block (Conv1d/BN/ReLU
× 2 + identity skip; kernel=7 for the two convs; stride applied to the
first conv only when the block is the first in a stage).

Initialization: He / Kaiming normal for Conv1d, ones / zeros for BN.

A `lead_subset` flag at construction time switches between 1-channel
(Lead-II, n_leads=1) and 12-channel (full 12-lead) inputs. **Same
backbone class, two instantiations.** Weights are NOT shared across the
two instantiations — Track-1 and Track-2 are trained independently per
seed.

### 5.3 Image encoder — ResNet-50 pretrained

`_model_lib/image_encoders.py::ImageResNet50`

```
Input:    (B, 3, H, W) — H × W resized to 224 × 224 (Lead-II strip)
                          or 384 × 384 (12-lead grid, taller image)
Backbone: torchvision.models.resnet50(weights=IMAGENET1K_V2)
Head:     final fc replaced with Linear(2048, embed_dim=512)
Output:   (B, 512) embedding
```

Image preprocessing pipeline (deterministic, no random augmentation at
test time):

```
PIL load → convert to RGB → Resize(short_side) → CenterCrop(target_h, target_w) →
ToTensor → Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
```

Training-time augmentation (when `augment=True`):

```
Resize(short_side) → RandomCrop(target) → RandomHorizontalFlip(p=0)
  # no flip — flipping an ECG image is medically invalid (inverts leads)
ColorJitter(brightness=0.1, contrast=0.1, saturation=0.05, hue=0)
RandomRotation(degrees=2)  # mild rotation matches scan-like artifact distribution
ToTensor → Normalize
```

Image-augmentation is **off** for clean-only training and **on** when
training on scan-like or mixed clean+scanlike (B2/B4/B6 ablation regimes).

`target_h, target_w` per layout:

| Image kind                          | Target H × W |
| ----------------------------------- | ------------ |
| `image_clean_lead2 / image_scanlike_lead2`     | 224 × 672 (preserves 1:3 strip aspect ratio) |
| `image_clean_12lead / image_scanlike_12lead`   | 384 × 512 (preserves the 3×4 grid aspect ratio) |

Fine-tuning policy: all layers trainable; smaller LR for the backbone
(1e-5) vs the new fc head (1e-3). Same policy for both layouts.

### 5.4 Text encoders

#### 5.4.1 TF-IDF baseline — `text_encoders.py::TfidfTextEncoder`

```
Vocabulary: top 50,000 char-n-grams (n ∈ {2, 3, 4}) + word unigrams + word bigrams
            fit on TRAIN split only, frozen for val/test
Vectorizer: sklearn TfidfVectorizer with sublinear_tf=True, max_df=0.95, min_df=10
Projection: TruncatedSVD to 512 dimensions, fit on TRAIN only
Output:     (B, 512) embedding
```

This is a feature extractor — no GPU, no parameters in the embedding
sense. The downstream MLP head per task is trained.

#### 5.4.2 Bio-ClinicalBERT — `text_encoders.py::BioClinicalBertEncoder`

```
Backbone: emilyalsentzer/Bio_ClinicalBERT (BERT-base, 110M params,
          pretrained on PubMed + MIMIC-III clinical notes)
Tokenization: max_length=512 with truncation from the right (MIMIC machine reports
              rarely exceed 256 tokens, but keep the buffer)
Pooling:  [CLS] hidden state (first token, last layer)
Head:     Linear(768, embed_dim=512)
Output:   (B, 512) embedding
```

Fine-tuning policy: full backbone trainable with discriminative LRs
(transformer layers 1e-5, head 1e-3, embedding layer 1e-6).

License & provenance: Bio-ClinicalBERT is MIT-licensed via HuggingFace.
The release package records the exact model SHA at the time of Phase 2
freeze.

### 5.5 Fusion head — late-concat + MLP

`_model_lib/fusion_heads.py::LateFusionMLP`

```
Input:   per-modality embeddings, each (B, 512)
         missing modalities → all-zeros vector + a mask bit
Concat:  cat([sig_emb, img_emb, txt_emb, presence_mask_3]) → (B, 1539)
MLP:     Linear(1539, 1024) + GELU + Dropout(0.2) +
         Linear(1024, 512)  + GELU + Dropout(0.2) +
         Linear(512, task_out)
Output:  task-specific shape
```

`presence_mask_3` = three bits indicating whether each modality is
present for this study (the loader emits zero-padded embeddings + a
mask bit when a modality is unavailable — e.g., A5 SIGNAL_SWAP
negatives have the signal swapped, not missing, so the mask remains
all-ones).

This single fusion head is shared across all multimodal tasks; only
the final `task_out` layer differs (number of classes / output shape).

### 5.6 Per-task head specs

Each task instantiates one or more of the above encoders + fusion. The
head adapts to the task:

| Task                          | Signal | Image | Text | Fusion | Output                                                  |
| ----------------------------- | :----: | :---: | :--: | :----: | ------------------------------------------------------- |
| A1 (5-label ICD)              | ✓      | ✓     | ✓    | ✓      | sigmoid × 5                                              |
| A2 (HR/QRS/QTc bins)          | ✓      | ✗     | ✗    | ✗      | softmax × 3 heads (3/3/3 classes)                       |
| A3 (35 lab-window-class heads) | ✓      | ✓     | ✓    | ✓      | softmax × 35 (5-class each: low/high/abnormal/normal/missing) |
| A4 (R-peak + QRS bound)        | ✓      | ✗     | ✗    | ✗      | per-sample sigmoid (5000) + onset/offset regression     |
| A5 (verification + masked attr) | ✓      | ✓     | ✓    | ✓      | binary head (verification) + 3 softmax heads (attributes) |
| A6 (mort + readm × 30/90)      | ✓      | ✓     | ✓    | ✓      | sigmoid × 4                                              |
| B1 (HR/QRS/QTc bins)           | ✓      | ✗     | ✗    | ✗      | softmax × 3 heads                                        |
| B2 (HR/QRS/QTc on corrupted)   | ✓      | ✗     | ✗    | ✗      | softmax × 3 heads (shared with B1 head, separate weights)|
| B3 (10-bin × 4 query)          | ✓      | ✗     | ✗    | ✗      | per-bin sigmoid (10) × 4 queries                         |
| B4 (verification)              | ✓      | ✓     | ✓    | ✓      | binary head                                              |
| B5 (corruption detect + span)  | ✓      | ✗     | ✓    | ✓ (sig+txt) | binary head + 5-class head + span-start/end regression |
| B6 (verification per difficulty) | ✓     | ✓     | ✓    | ✓      | binary head (same as B4; evaluation-time only)           |

The "✗" cells mean the modality is forbidden by `task_input_policy.yaml`
(§4 per-task spec). Where signal-only is the only allowed input, no
fusion head is used — the signal encoder's 512-d embedding feeds
directly into a task-specific MLP.

### 5.7 Why these defaults are defensible for paper reviewers

1. Truth doc §9.2 explicitly endorses ResNet-50 / ViT-S and
   Bio-ClinicalBERT.
2. 1D ResNet-18 is the most commonly used ECG backbone in current
   MIMIC-IV-ECG benchmark literature (Hong et al. ECG-NET, ECG-FM
   itself uses transformer but reports ResNet variants).
3. Late-fusion concat + MLP is the doc-§9.3-endorsed Task A architecture
   ("encode S, I, T separately… create pairwise features… feed all
   these features to a small MLP").
4. Pretrained image / text encoders match what every published
   medical-imaging benchmark does; reviewers will not question this.
5. **Algorithmic baseline mandatory per task** — most often missed by
   benchmark papers; including these gives reviewers a sanity reference.

### 5.8 Model architecture configs — per-task YAMLs

For every (task, arch tier, lead_subset) combination, a YAML lives in
`config/model_configs/`:

```yaml
# example: config/model_configs/A1_multimodal_fusion_12lead.yaml
task: A1_ecg_diagnosis
arch_tier: multimodal_fusion
lead_subset: 12-lead

signal:
  encoder: ECGResNet1D18
  n_leads: 12
  input_modality: preprocessed_12lead   # primary signal modality
  embed_dim: 512
image:
  encoder: ImageResNet50
  input_modality: image_clean_12lead    # primary image modality
  target_h: 384
  target_w: 512
  augmentation: false                   # off for clean-only primary
text:
  encoder: BioClinicalBert              # OR TfidfTextEncoder for the supplementary baseline
  hf_id: emilyalsentzer/Bio_ClinicalBERT
  max_length: 512
fusion:
  head: LateFusionMLP
  hidden_dims: [1024, 512]
  dropout: 0.2
head:
  output: sigmoid
  n_classes: 5
loss: BCEWithLogitsLoss
class_weights: from_train  # see §6.4
```

Locked at Phase 2 freeze. Mutations re-trigger §11 reviewer check.

---

## 6. Training infrastructure

### 6.1 Trainer entry point

`scripts/phase2_tasks_benchmark_and_paper/30_train.py` is the **only**
training entry. Invocation:

```bash
python 30_train.py \
    --model-config config/model_configs/A1_multimodal_fusion_12lead.yaml \
    --task A1_ecg_diagnosis \
    --seed 42 \
    --output-dir outputs/model_runs/A1_ecg_diagnosis/multimodal_fusion_12lead/seed_42/
```

The trainer reads `eval_configs/default.yaml` for shared settings and
the task-specific YAML (e.g., `eval_configs/A6_risk.yaml`) for
calibration / decision-curve add-ons.

### 6.2 Seeds and determinism

Seeds: **42, 123, 456** for every task × arch combination. Per Round
1.4. Implementation in `_train_lib/seed.py`:

```python
def set_seed(seed: int):
    random.seed(seed); np.random.seed(seed)
    torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    os.environ["PYTHONHASHSEED"] = str(seed)
```

`cudnn.benchmark=False` is required for reproducibility; we accept the
~5–15 % throughput hit. Mixed-precision determinism is
implementation-dependent; we record per-run the exact PyTorch + CUDA
versions in the checkpoint metadata.

### 6.3 Optimizer and schedule

| Component        | Default                                                                                   |
| ---------------- | ----------------------------------------------------------------------------------------- |
| Optimizer        | AdamW with weight_decay=0.01, betas=(0.9, 0.999)                                          |
| LR head          | 1e-3 (per-task heads + linear projections)                                                |
| LR backbone (Signal ResNet-18) | 1e-3 — trained from scratch, same as head                                   |
| LR backbone (Image ResNet-50)  | 1e-5 — pretrained, fine-tune slowly                                          |
| LR backbone (Bio-ClinicalBERT) | 1e-5 layers, 1e-6 embeddings — discriminative LRs                            |
| Schedule         | Linear warmup over first 5 % of total steps → cosine decay to 0                            |
| Total epochs     | 30 (signal-only and image-only tasks) / 20 (text-only and multimodal) — empirical default |
| Early stop       | Patience 5 epochs on val primary metric                                                   |
| Gradient clipping | global norm 1.0                                                                          |

These defaults are locked. Per-task overrides go into the model-config
YAML's `train:` block. Any override is captured by the audit (§11) so
the reviewer sees "task X overrode default LR — here's why."

### 6.4 Loss + class-imbalance handling

| Task family               | Loss                                                                  | Imbalance handling                                                                                     |
| ------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Multi-label binary (A1)   | BCEWithLogitsLoss + pos_weight per head from train prevalence         | pos_weight = (1 - prev) / prev, capped at 20 to avoid runaway gradients on very rare labels             |
| Multi-class 5 (A3)        | CrossEntropyLoss with class_weights from train inverse-frequency      | "missing" class is a real class; not down-weighted                                                      |
| Multi-class 3 (A2, B1)    | CrossEntropyLoss (lightly imbalanced; no weights by default)          | Weighted random sampler optional via `--balanced-sampler` flag                                          |
| Per-sample sigmoid (A4)   | BCEWithLogitsLoss summed over samples, normalized per study           | None — positives are ~7 % of samples (one per peak in a 10-s strip); a global pos_weight=14 default     |
| Binary verification (A5, B4, B6) | BCEWithLogitsLoss                                                | Hard-negative oversampling via per-batch ratio (every batch contains ≥ 1 HARD_NEGATIVE_TEXT example)    |
| Binary corruption detection (B5) | BCEWithLogitsLoss + auxiliary 5-class CE for `label` head        | Balanced 50/50 clean/corrupted by dataset design (Round 2 decision)                                     |
| Risk binary heads (A6)    | BCEWithLogitsLoss + pos_weight from train prevalence per head         | Calibration matters — post-hoc Platt scaling or isotonic regression fit on **val only** if ECE > 0.05  |
| Span regression (B5)      | SmoothL1Loss on (start, end) char offsets, normalized by report length | Spans only defined on `is_corrupted=True` rows; loss masked otherwise                                  |

All loss weights and class-frequency normalization use **train statistics
only**.

### 6.5 Threshold selection

For every classification head, the binary threshold (or per-class threshold
for multi-class softmax-binarized analyses) is chosen by maximizing
Youden's J on the **validation** set. The selected threshold + its
val-set value are logged into `outputs/audit_reports/threshold_audit.md`
per (task, arch, seed). Spot check: any test-set prediction file must
have used the val-chosen threshold, never re-tuned on test.

Special cases:

- A6 calibration tasks: report performance at val-optimal threshold
  AND at clinically relevant thresholds (5 %, 10 %, 20 % risk).
- A3 multi-class: per-class threshold not directly meaningful;
  report macro-AUPRC instead of threshold-dependent F1.

### 6.6 Mixed precision + memory

Mixed precision: **bf16 on GPUs that support it (RTX 30/40, H100, A100);
fall back to fp16 + GradScaler on older GPUs.** Decision recorded in
the `train_config.yaml` snapshot per run. (The DGX H100 supports bf16
natively, which is also more stable than fp16 for our deeper
multimodal runs.)

Per-task GPU-memory budget (single GPU; values are for batch size that
fits in 24 GB VRAM, the local-workstation default):

| Task family               | Batch size | VRAM         | Notes                                                                                  |
| ------------------------- | ---------- | ------------ | -------------------------------------------------------------------------------------- |
| Signal-only A2/B1/B3      | 256        | ~6 GB        | 5000-sample 1D inputs are tiny                                                          |
| Signal-only A4 (per-sample)| 128       | ~8 GB        | 5000-sample sigmoid output increases activation memory                                  |
| Signal-only A6            | 128        | ~6 GB        | Same as A2                                                                              |
| Image-only A1/A3/A5/B4    | 64         | ~14 GB       | 384×512 images for 12-lead grids                                                        |
| Text-only A1/A3/A6/B4/B5  | 32         | ~10 GB       | Bio-ClinicalBERT max_length=512                                                         |
| Multimodal (S+I+T)        | 16         | ~22 GB       | Largest VRAM consumer; reduce to 8 if VRAM < 24 GB                                       |
| B2 regime_2 (signal + augmentation) | 256 | ~7 GB     | Augmentation on-the-fly adds slight CPU pressure                                        |

Gradient accumulation steps: 1 × batch_size by default; tunable per
task via `--accumulation-steps` to reach a larger effective batch on
memory-constrained GPUs. A6 multimodal training uses 4-step
accumulation to reach effective batch 64 for calibration stability.

### 6.7 Patient-level bootstrap (n=10,000, BCa)

`_dataset_lib/bootstrap.py::patient_bootstrap`. For every metric on every
test-prediction file:

```python
def patient_bootstrap(predictions: pd.DataFrame, metric_fn, n_iter=10000,
                      ci_method="bca", seed=2026) -> Tuple[float, float, float]:
    """Return (point_estimate, ci_low, ci_high) for `metric_fn(predictions)`.

    Resampling: draw subject_ids WITH replacement, take all ECGs for each
    drawn subject, compute metric. Repeat n_iter times.

    BCa correction applied when n_positive >= 100; otherwise percentile.
    """
```

CI method:

- BCa (bias-corrected and accelerated) when test-positive count ≥ 100
  per head. Standard for medical AUPRC reporting.
- Percentile (simple 2.5 / 97.5 quantile) otherwise (some rare labels
  in A1 or A3 may fall below the threshold).

The bootstrap is patient-level, not ECG-level, per the
non-negotiable rule §1.

### 6.8 Calibration (A3 / A6)

`_train_lib/calibration.py`. Per-head:

- Reliability diagram: 10 quantile bins, overlay perfect-calibration
  line. Saved as PNG per (task, arch, seed).
- ECE: weighted mean absolute gap between bin confidence and bin
  accuracy.
- Brier score.

If ECE > 0.05 at the val-optimal threshold, apply **post-hoc Platt
scaling** (sigmoid scaler fit on val predictions). Re-evaluate ECE; if
still > 0.05, switch to **isotonic regression** (monotonic
non-parametric). Whatever scaler wins on val carries forward to test —
the scaler is part of the trained model artifact.

A3 / A6 only by default. Other tasks compute ECE for completeness
(supplementary) but don't auto-recalibrate.

### 6.9 Resume / restart semantics

Phase 2 trainings are checkpoint-resumable. Each checkpoint contains:

```
model_state_dict, optimizer_state_dict, scheduler_state_dict,
seed, epoch, global_step, val_metric_best, val_metric_best_epoch,
rng_states {python, numpy, torch, cuda}, train_config_snapshot
```

On crash: re-run the same command; the trainer detects
`checkpoint_last.pt` and resumes from that step. The rng states are
restored, so the post-resume training trajectory matches an
uninterrupted run modulo non-determinism in cuDNN convolution algorithms
(documented).

### 6.10 Logging hygiene

Inherits Phase 1 §8 wholesale. Workers in dataloaders (PyTorch
DataLoader has worker subprocesses) use the per-PID file transport
(§8.3 of Phase 1 doc). Main process emits the single tqdm bar +
periodic status. Mixed-precision warnings, h5py thread warnings, and
HuggingFace tokenizer warnings are silenced per §8.9. The per-task
`train_log.jsonl` is the canonical machine-readable log (one row per
epoch with train_loss, val_metric, lr, ema, etc.).

---

## 7. Evaluation regimes

### 7.1 Default per-task evaluation

Every trained model produces `test_predictions.parquet` containing:

```
study_id, subject_id, link_tier, sqi_tier, cart_id,
y_true_<head>, y_pred_proba_<head>, y_pred_label_<head>,
seed, arch_tier, lead_subset, signal_input_modality, image_input_modality
```

`31_eval.py` reads these per-seed prediction files plus the cohort
table for the task, then for every (head, group) computes:

1. Primary metric ± std across 3 seeds.
2. Pooled-prediction bootstrap CI (concatenate test predictions across
   seeds → resample subjects).
3. Per-subgroup metric: SQI tier (high/medium/low), cart_id top-5,
   linkage tier (L3/L2/L1/L0 where relevant), Plan A boundary flag.

Outputs land in `outputs/results/<task>.csv` with the §1.1 column
layout.

### 7.2 Sensitivity / ablation sweeps

`41_run_sensitivity.py` automates these sweeps per task. Required
sweeps (matrix in §4 per-task spec):

| Sweep                                      | Tasks affected           |
| ------------------------------------------ | ------------------------ |
| L3-only vs L3+L2                           | A1, A3, A6               |
| Boundary excluded                          | A1, A6                   |
| Raw vs preprocessed signal                 | All signal-using tasks   |
| Lead-II vs 12-lead                         | All signal-using tasks   |
| Clean vs scan-like image                   | All image-using tasks    |
| TF-IDF text vs Bio-ClinicalBERT text       | A1, A3, A5, A6, B4, B5, B6 |
| First-ECG-per-admission                    | A6                       |
| First-ECG-per-patient                      | A6                       |
| Lab window {pm6h, pm12h, pre_24h, post_24h, pm24h} | A3            |
| ED-included vs hospital-only ICD           | A1                       |
| Same-hadm restriction                      | A3                       |
| No-text ablation — **RETRAINED**, see below | A1, A3, A5, A6, B4      |

Each sweep produces its own `outputs/results/<task>_sensitivity_<sweep>.csv`
that is included in the supplementary tables. Most sweeps do NOT
retrain; they re-evaluate the same trained model on the
filtered cohort (cheap). When a sweep requires retraining (e.g.,
"swap TF-IDF for Bio-ClinicalBERT"), that's a separate `30_train.py`
invocation with a different model config.

**The no-text ablation is one of those, and this section used to say
otherwise (Round 10.5).** Plan A/B §5.3 ablation 6, Figure 2 and Appendix F all
make the no-text multimodal run the **primary leakage-controlled setting** —
Appendix F: *"include no-text multimodal as primary leakage-controlled
setting."* Re-evaluating with the text branch zeroed was defensible while fusion
was frozen late fusion; Round 5.1 made fusion **end-to-end fine-tuned**, and
feeding zeros to a jointly-trained text encoder does not produce "the same model
without text", it produces a forward pass outside the model's own training
distribution. The resulting number would not be an ablation.

The ablation therefore has its own trained tier,
`multimodal_fusion_notext_{lead2,12lead}` — 10 configs across A1/A3/A5/A6/B4,
**+30 runs** in campaigns 7 and 8. B5 is excluded: its only other modality is
signal, so dropping text collapses it to the signal-only tier that already
exists.

### 7.3 B2-specific three-regime evaluation

| Regime    | Train data                                  | Test data                                   | Metric output                                 |
| --------- | ------------------------------------------- | ------------------------------------------- | --------------------------------------------- |
| regime_1  | clean signals from B1 train split           | corrupted signals from `signals_corrupted.parquet` | AUPRC degradation per (corruption_type, snr_db) |
| regime_2  | clean + on-the-fly synthetic corruption     | corrupted signals (same test set as regime_1) | AUPRC improvement over regime_1                |
| regime_3  | same as regime_1 trainer                    | natural test signals stratified by SQI tier (no synthetic corruption) | AUPRC per SQI tier            |

`eval_configs/B2_robustness.yaml` controls these. The corruption
generation in regime_2 (TRAIN-TIME) uses
`config/corruption_recipes_LOCKED.yaml` with a DIFFERENT RNG seed than
the locked test set in `signals_corrupted.parquet` (Phase 1 Stage 8) —
this prevents the regime_2 model from memorizing test corruption
realizations.

Primary B2 metrics: area under corruption curve (AUCC) per family,
collapse threshold (SNR at which AUPRC < 50 % of clean), regime_1 vs
regime_2 average drop.

### 7.4 A4-specific fiducial evaluation

`eval_configs/A4_fiducial.yaml`. Beyond default metrics:

- Per-peak match: a predicted R-peak matches a true R-peak if within
  ±10 ms. Compute F1 with this matcher. For each unmatched peak (false
  positive or false negative), record the timing error to the nearest
  true peak (false-positive timing = inf if no nearby true peak).
- Per-onset / per-offset same matcher.
- Event-count distribution: (predicted_n_peaks − true_n_peaks)
  histogram bucketed at {-5, -3, -1, 0, +1, +3, +5} for the
  supplementary figure.

### 7.5 A5 / B4 / B6 verification + retrieval evaluation

`eval_configs/cross_modal.yaml`. The same trained model emits both:

- Verification: probability that a given triple is a positive. AUPRC,
  per-`neg_type` F1.
- Retrieval (secondary check): given an anchor study_id and a
  modality, rank the 100-candidate pool of other-subject studies by
  embedding similarity → report Recall@1, Recall@5, MRR.

The 100-candidate pool is sampled deterministically per anchor
(seed=2026 + anchor_id) so all three seeds are evaluated on the same
pool. Pool composition: 50 same-HR-bucket + 50 different-HR-bucket
non-anchor subjects.

B6 evaluation slices the B4 prediction file by `neg_type` /
`difficulty_tier` (§4.B.6.2) and reports per-tier metrics.

### 7.6 A3 / A6 calibration evaluation

`eval_configs/A6_risk.yaml`. Beyond default metrics:

- Reliability diagram per head (10 quantile bins).
- ECE, Brier, log-loss.
- Net benefit (decision curve analysis) at 5 %, 10 %, 20 % risk
  thresholds for A6 (supplementary).
- Pre vs post-Platt-scaling ECE comparison.

### 7.7 Cross-task summary table

`40_aggregate_results.py` produces
`outputs/results/all_tasks_summary.csv`:

```
task, arch_tier, lead_subset, primary_metric_name,
metric_mean, metric_std, ci_low, ci_high,
n_ecg_test, n_subj_test, n_pos_test
```

One row per (task, arch, lead). This is the data source for the
main-paper headline figure (`figures/main/fig2_per_task_AUPRC.png`).

---

## 8. Resource policy (GPU, batch size, mixed precision, DGX)

> **REWRITTEN 2026-08-26 (Round 5.3).** §8.1 and §8.2 previously assumed a
> local workstation as the primary compute and treated DGX access as
> hypothetical. That is now inverted. **The MU DGX A100 is the primary
> compute for every trained model**; the laptop (RTX 3060 Laptop, 6 GB)
> is a development machine only — it writes and smoke-tests scripts
> against small samples and does not produce any number that reaches the
> paper. Reason: the laptop cannot hold a mains supply reliably enough
> for multi-day runs, and 6 GB VRAM cannot fit ResNet-50 at 384×512
> (~14 GB) or Bio-ClinicalBERT at batch 32 (~10 GB) at the §6.6 batch
> sizes. Operational detail — quotas, campaigns, data staging, Slurm
> submission, access model — lives in `docs/PHASE2_EXECUTION_PLAN_DGX.md`
> and is not duplicated here.

### 8.0 DGX A100 (primary compute)

| Fact | Value | Consequence for this document |
| ---- | ----- | ----------------------------- |
| Hardware | NVIDIA DGX **A100**, nodes `dgxa` / `dgxb`, login `dgx-login01` | bf16 native (§6.6 auto-detect resolves to bf16, not fp16+GradScaler) |
| Scheduler | Slurm, partitions `cpu_student`, `gpu_student` | every stage in §9 is submitted as a batch job or job array; §6.9 resume semantics must survive Slurm preemption/requeue |
| Storage quota | **50 GB total**, shared across env, data, checkpoints, logs | drives §8.1's checkpoint policy and the campaign schedule in the execution plan |
| Access | MU network only; no inbound route from outside campus | stages must run unattended to completion; no interactive babysitting |
| Account expiry | 2026-12-31, data purged 10 days later | no Phase 2 artifact may exist only on the DGX; results are pushed off-node as they are produced |
| CPU partition | `cpu_student` available | Stage P2.1/P2.2 task building, P2.3 audits and P2.4 algorithmic baselines run here, not on the laptop |

`config/decision_phase2.yaml` records the DGX identity, the Slurm
partition names, and the observed CUDA/torch versions at Phase 2 freeze,
so the reproducibility audit (§1.2) can name the exact machine.

### 8.1 Per-run knobs

Inherits Phase 1 §6 wholesale. Phase 2 additionally:

| Knob                                    | Value                                                                                                  |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| GPU presence                            | Required for §6.5–§6.8. CPU-only training disallowed for multimodal tasks (Bio-ClinicalBERT too slow). |
| `CUDA_VISIBLE_DEVICES`                  | set by Slurm via `--gres=gpu:N`; never hard-coded.                                                     |
| `torch.set_float32_matmul_precision`    | `"high"` (TF32 on Ampere+) — non-determinism is bounded and reproducible across runs.                  |
| Mixed precision                         | bf16 (A100 native). fp16 + GradScaler remains implemented for the laptop smoke-test path only. Auto-detect at trainer startup; record in config snapshot. |
| Per-task batch size                     | §6.6 defaults, sized for 24 GB. A100 40/80 GB permits them unchanged; the laptop smoke path halves until it fits. Trainer aborts if final batch ≤ 1 after halving. |
| **Checkpoint disk budget**              | **≤ 5 GB resident (Round 5.4, supersedes Round 4.4's 150–200 GB).** The 50 GB quota makes "keep best + last for every run" impossible: 12 tasks × ~4 tiers × 3 seeds ≈ 144 runs, and an end-to-end fusion checkpoint alone is ~2.3 GB with optimizer state. New policy below. |
| Checkpoint retention                    | Per **running** job: `checkpoint_last.pt` (weights + optimizer + RNG, for resume) and `checkpoint_best.pt` (**weights only**, ~0.6 GB for fusion). On run completion: push `best` + `test_predictions.parquet` + `train_log.jsonl` off-node, delete both local files. Nothing accumulates. |
| Concurrency cap                         | At most 3 concurrent end-to-end fusion jobs per user (3 × ~2.4 GB in-flight checkpoints). Lighter tiers are not capped by disk. |
| Preemption safety                       | `checkpoint_last.pt` is written every N minutes (not only per epoch) and re-pulled from off-node storage if a requeued job finds it missing. Slurm `--requeue` is assumed on `gpu_student`. |
| Disk priority                           | Every campaign launcher checks free quota **before** submitting and refuses to start if the campaign will not fit under 45 GB. A refusal is always better than a job that dies at 90 %. |

### 8.2 Data residency — the campaign model

The 50 GB quota cannot hold the Phase 1 dataset (355 GB on disk). Phase 2
therefore never stages "the dataset"; it stages **one campaign at a
time** — the smallest set of files that lets a group of runs complete —
then evicts it. `scripts/dgx_portability/` (created in Stage P2.0) holds
the real launchers, not templates:

```
scripts/dgx_portability/
├── README.md                 # campaign table, quota rules, recovery steps
├── stage_data.sh             # pull one campaign's data, verify checksums, refuse if it won't fit
├── evict_data.sh             # wipe the current campaign's data after results are pushed
├── push_results.sh           # best checkpoint + predictions + logs off-node, then delete local
├── make_chunks.py            # cut oversized modalities into aligned i.i.d. pieces (below)
├── make_subsets.py           # the derived datasets (L3, val/test, scan-like test) + their overlays
├── upload_data.py            # push a campaign's data to R2 in the layout stage_data.sh reads
└── slurm/campaign_<n>.sbatch # one submission file per campaign (14 of them)
```

> **AMENDED 2026-08-29 (open questions 14 and 15).** Three things about the
> campaign model changed, all of them measured rather than estimated, and none
> of them touching the two rules below.
>
> 1. **There are 15 campaigns, not 11.** A campaign that reads a whole lead set
>    does not fit: campaigns 7, 8 and 11 had configs covering both, which put
>    campaign 7 at 69 GB against the 45 GB ceiling. They are split by lead
>    subset: **7/8/11 are the 12-lead halves, 12/13/14 the Lead-II ones.**
>    **Campaign 10 was split the same way on 2026-09-30** (§12.10), into 10
>    (12-lead) and **15** (Lead-II), once it was settled that the scan-like
>    image tier trains rather than only re-tests and therefore needs scan-like
>    train+val for each layout.
>    `campaign_runs.py --table` still reports 104 configs and 312 runs — the
>    same work, partitioned differently. Step-ledger references to campaign
>    numbers were updated with it.
> 2. **A campaign is staged in two phases.** It does not hold its test split
>    while it trains, so the table carries a train-phase size and an eval-phase
>    size, and `stage_data.sh --phase` stages one or the other; the campaign
>    body swaps between them after the training runs finish. Every campaign now
>    passes the quota gate in both phases with 5 GB of checkpoints resident.
> 3. **Pieces are cut from TRAIN only, and val/test ship whole.** Rule 1 below
>    is about the training split, so campaigns 6, 8 and 9 had no val split to
>    early-stop on and no test split to evaluate. Measured: 12-lead int16 is
>    101.6 KiB/study, clean 12-lead images 11.7 KiB/study, raw 12-lead float32
>    88.5 KiB/study — val and test fit beside two resident pieces as plain
>    datasets, so **nothing beyond the training split is ever chunked**.

Two rules bind the science, not just the operations:

1. **Chunking is i.i.d. and modality-aligned.** When a campaign's data
   exceeds the quota, the *training* split is cut into equal pieces keyed
   by a hash of `study_id` — never by subject, admission, label, cart_id,
   or time. Signal and image pieces use the **same** key, so piece *k* of
   each modality covers the same studies (required for the fusion
   dataloader). Each piece is a fair miniature of the split.
2. **Chunks cycle *within* each epoch, never across epochs.** Every epoch
   visits every piece in a reshuffled order, with a shuffle buffer inside
   each piece; two pieces are resident at a time (train on *k*, prefetch
   *k+1*, evict *k−1*). Training to convergence on piece 1 and then
   moving to piece 2 is **forbidden** — that is block-local SGD and it
   catastrophically forgets. The block-shuffled sampling that *is* used
   must be recorded as a documented deviation from global shuffling in
   `config/decision_phase2.yaml` and disclosed in the supplementary.

Storage-format note: signals are staged as **int16 with a per-record
scale factor** rather than float32 (56.7 GB instead of 141.8 GB for the
12-lead preprocessed set). Measured max abs error 1.1e-3 against signals
whose amplitude reaches 70 — finer than the int16 ADC resolution of the
source MIMIC-IV-ECG recordings, so this is a storage change, not a
precision compromise. Stage P2.0 validates it empirically by training one
task on both encodings and confirming the metrics agree; that comparison
ships in the supplementary.

> **AMENDED 2026-08-28 (Step 5, measured).** The three numbers above were
> estimates and two of them are wrong. The conversion has now been run for
> real; use these instead.
>
> **Size: 77.5 GiB, not 56.7.** The 12-lead preprocessed set converts to
> **83.24 GB / 77.5 GiB from 152.25 GB / 141.8 GiB — 54.7 %, not ~40 %.**
> The estimate assumed int16 would roughly halve the file, but the float32
> source is *already* gzip-4 compressed, and int16 does not compress as much
> further as that assumed. Adding `lead2_preprocessed` (12.73 → 7.42 GB,
> 58.3 %) the whole conversion is **164.98 GB → 90.66 GB (55.0 %)**.
> **Consequence:** the §6 upload budget rises from ~142 GB to **~163 GB**.
> The campaign model is unaffected — 77.5 GiB over 8 pieces is ~10 GiB each,
> two resident ~20 GiB, well under the 45 GB ceiling.
>
> **Error: bounded by half a quantisation step, exactly.** The "1.1e-3
> against amplitude 70" figure does not describe this data — the preprocessed
> signals are z-scored per lead and their amplitude reaches **1923**, so the
> absolute error scales with it. The correct statement is the relative one:
> the error is **≤ half a quantisation step by construction, measured at
> 1.000000 of one on every file**, i.e. a round-trip relative error of
> **1.53e-05**. Worst absolute error over all six files is 3.34e-02, on a
> record whose own amplitude is ~1900.
>
> **The empirical validation is Stage P2.5, not P2.0**, and it needed four
> arms rather than two: float32, an identical float32 repeat, int16, and
> float32 at a different seed. The repeat comes back bit-identical, which
> proves determinism but makes its floor exactly zero — a bar nothing
> perturbed can clear — so the *seed* arm is the yardstick. Result:
> **int16 moves the reported metrics 0.42x as much as changing the seed
> does** (2.90e-03 vs 6.90e-03, and int16 is the smaller effect on every one
> of the six metrics). Report:
> `outputs/stage_reports/int16_equivalence.md`. Tools:
> `scripts/dgx_portability/make_int16.py` and `prove_int16_equivalence.py`.

### 8.2.1 Laptop role (development only)

The laptop authors and smoke-tests every script against a fixed
5,000-study sample (`data/processed/dev_sample/`), and renders paper
tables/figures from downloaded result CSVs. It trains nothing that
appears in the paper. Any laptop-run script must checkpoint its progress
and resume cleanly, because mains power is unreliable.

### 8.3 Training-queue priority (Round 4.2)

Locked execution order for §9 stages P2.5–P2.8:

1. Plan A: **A2 → A1 → A4 → A3 → A6 → A5**.
2. Plan B: **B1 → B2 → B3 → B4 → B5 → B6**.

Within each task, the architecture-tier order is:

```
algorithmic baseline → signal-only → image-only → text-only → multimodal
```

Within each tier, seed order is 42 → 123 → 456. This ordering
guarantees:

- A2 is first and exercises the entire trainer stack on the simplest
  task. Failures show up early.
- A1, A4, A3, A6 each produce a defensible single-modality result table
  before more complex multimodal work begins.
- A5 is last in Plan A because it's the most architecture-complex
  (verification + masked attribute heads sharing a tri-encoder).
- B1 reuses A2's signal-encoder code, then B2 reuses B1's signal head
  with regime_2 augmentation, then B3 starts the next code stream.

### 8.4 Cohort wall-clock budget (refined from §0)

> **SUPERSEDED 2026-08-26 (Round 5.3).** The local-only table below is
> retained for reference but no longer describes the plan. Revised
> estimate on one A100, bf16, locked batch sizes, with end-to-end fusion
> (Round 5.1) replacing frozen-encoder fusion:
>
> | Campaign | Runs | Est. GPU-h |
> | -------- | ---: | ---------: |
> | P2.1–P2.4 task building, audits, algorithmic baselines (`cpu_student`) | — | ~2 days CPU |
> | Text-only (Bio-ClinicalBERT ×7 tasks ×3 seeds) | 21 | ~23 |
> | Image-only, 12-lead then Lead-II | 42 | ~28 |
> | Signal-only, Lead-II | 33 | ~8 |
> | Signal-only, 12-lead (L3 cohorts resident; full cohorts chunked) | 30 | ~16 |
> | **Fusion end-to-end, L3 cohorts (A1/A3/A6)** — fits resident | 9 | ~20 |
> | **Fusion end-to-end, full cohorts (A5/B4/B5/B6)** — chunked | 12 | ~30 |
> | Re-training sweeps (raw-vs-preprocessed, TF-IDF-vs-BERT) | ~30 | ~25 |
> | Re-evaluation sweeps + final eval + calibration | — | ~10 |
> | **Total** | **~180** | **~160 GPU-h** |
>
> ~160 GPU-hours is roughly one week of queue time on a single
> `gpu_student` GPU, or 2–3 days across three or four. Allowing for queue
> waits, data staging between campaigns and re-runs, budget **3–5 weeks
> of DGX wall-clock**, preceded by ~2 weeks of laptop script development.
> The chunked campaigns are compute-bound rather than transfer-bound
> (~8 min of A100 work per epoch against ~41 GB of staging that prefetch
> hides), which is what makes end-to-end fusion affordable under a 50 GB
> quota; if measured bandwidth makes them transfer-bound, co-schedule
> jobs over a shared piece stream so one staging pass serves several runs.

Original local-only budget. Per-task seed-time is for a
single GPU + bf16 + locked batch sizes:

| Stage | Tasks                                             | Per-task per-seed | Sub-total |
| ----- | ------------------------------------------------- | ----------------- | --------- |
| P2.4  | algorithmic baselines (no training)               | n/a               | ~3 h      |
| P2.5  | signal-only × 12 tasks × 3 seeds                  | 1 h               | 36 h      |
| P2.6  | image-only × 7 tasks × 3 seeds                    | 1.5 h             | 31.5 h    |
| P2.7  | text-only × 7 tasks × 3 seeds                     | 1 h               | 21 h      |
| P2.8  | multimodal × 7 tasks × 3 seeds (S+I+T fusion)     | 2.5 h             | 52.5 h    |
| P2.9  | eval                                              |                   | ~4 h      |
| P2.10 | sensitivity sweeps                                |                   | ~12 h     |
| P2.11–P2.13 | calibration, tables, figures, release       |                   | ~6 h      |

**Total local-only wall-clock:** ~166 h ≈ **7 calendar days** running
24×7. If DGX burst lands during the project, P2.6/P2.7/P2.8 are the
biggest beneficiaries (~105 h moved) and total drops to ~3 days.

### 8.5 Memory pressure invariants

- DataLoader `num_workers` per Phase 1 §6.1 (75 % of cores). Workers
  use per-PID logging (Phase 1 §8.3).
- HDF5 readers in the signal dataloader: each worker opens its own
  `h5py.File` handle (HDF5 is not thread-safe across processes
  sharing one handle). Open in `swmr=False` mode (Phase 1 §7.4 also
  applies — we are not a SWMR writer here, just a reader).
- Tar readers in the image dataloader: cache the tar index after the
  first open per worker; use `tarfile.open(...).extractfile(name)` to
  stream individual member bytes. Manifest provides offset and length
  so we can `seek+read` directly without re-scanning the tar.

### 8.6 Crash recovery / idempotency

- `30_train.py` resumes from `checkpoint_last.pt` automatically. Per
  §6.9.
- `31_eval.py` is idempotent (reads checkpoint, writes
  `test_predictions.parquet`, atomic via `.tmp` + `os.replace`).
- `40_aggregate_results.py` reads all prediction files and overwrites
  the per-task CSV. Safe to re-run.
- `60_make_paper_tables.py` / `61_make_paper_figures.py` are pure
  read-only consumers and always safe to re-run.

---

## 9. Stage-by-stage execution plan

Phase 2 is split into 14 stages numbered **P2.0 through P2.13** plus a
mandatory pre-flight (`P2.-1`). Each stage is a self-contained chunk:
scripts to author / modify, inputs read, outputs produced, validation
checklist. After every stage the agent halts, emits the §10 output
summary, and waits for the reviewer (§11) to sign off before the next
stage begins.

### 9.0 Pre-flight (P2.-1) — Phase 1 completion gate

Phase 1 must be FULLY COMPLETE before any Phase 2 stage runs. The
pre-flight checks:

1. `outputs/stage_reports/stage_8_complete.done.json` exists with
   `validation: PASS`. (Signals-corrupted parquet built.)
2. `outputs/stage_reports/stage_9_complete.done.json` exists with
   `validation: PASS`. (Preprocessed signals materialized — mandatory
   per Phase 1 §3.3.)
3. `outputs/stage_reports/stage_10_complete.done.json` exists with
   `validation: PASS`. (Canonical manifest + 4 audit reports
   all PASS.)
4. `data/processed/modality_manifest.parquet` exists, includes rows
   for every modality_kind enumerated in §2.6, and is read-only
   (file mtime matches Stage 10 freeze).
5. `config/decision.yaml` has `chosen_path: plan_a` AND its
   `frozen_at` matches Phase 1 Stage 1's freeze timestamp.

If any check FAILS, Phase 2 halts with explicit instructions to
return to Phase 1's doc and finish the pending stages. No silent
fallback.

**Current state of Phase 1 (verified 2026-08-26): COMPLETE — all five
checks PASS.** Phase 2 is unblocked.

| Check | Evidence | Result |
| ----- | -------- | ------ |
| 1. Stage 8 | `stage_8_complete.done.json` — `status: PASS`, 79,920 rows in `signals_corrupted.parquet`, closed 2026-06-03T09:35Z | PASS |
| 2. Stage 9 | `stage_9_complete.done.json` — PASS, `lead2_preprocessed.h5` + 5 × `twelve_lead_preprocessed_shard_*.h5`, 800,035 rows, closed 2026-06-03T17:15Z | PASS |
| 3. Stage 10 | `stage_10_complete.done.json` — PASS, all 5 audit reports linked, closed 2026-06-05T04:23Z | PASS |
| 4. Manifest | `modality_manifest.parquet`, 6,480,200 rows, all §2.6 kinds present | PASS |
| 5. Decision gate | `config/decision.yaml` — `chosen_path: plan_a`, `frozen_at: 2026-06-03T08:53:27Z`, 4/4 thresholds true | PASS |

*(The paragraph this replaces described the 2026-06-03 state, when
Stages 8–10 were still open. They closed on 2026-06-03 and 2026-06-05.)*

### 9.1 Stage P2.0 — Foundation (rewrite config + quarantine stale)

**Purpose.** Establish Phase 2 config files, quarantine the stale
legacy builders, prepare the directory tree.

**Scripts to author / modify:**

| #   | Script                                  | Status                   | Purpose                                                                                                                                       |
| --- | --------------------------------------- | ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | n/a (no script)                         | manual + recorded in report | Move `data/processed/task_jsonl/` → `data/archive_phase1_old/task_jsonl_<ts>/`. Move `01..06_task_*.py` builders → `_legacy_phase1_pre_regen/`. |
| 2   | rewrite `config/task_definitions.yaml`  | Modify                   | Replace Plan-B-only with the 12-task spec (one block per task per §4).                                                                       |
| 3   | rewrite `config/task_input_policy.yaml` | Modify                   | Replace Plan-B-only with the 12-task allowed/forbidden block per §4.                                                                          |
| 4   | author `config/icd_label_map_LOCKED.yaml` | New                    | Plan A/B Appendix B 5-group template (Round 2.1 decision).                                                                                    |
| 5   | author `config/lab_itemid_map_LOCKED.yaml` | New                   | 7-lab universe (Round 2.2 decision); merge existing `key_labs.yaml` and add Ca+Mg itemids found in `d_labitems`.                              |
| 6   | author `config/corruption_recipes_LOCKED.yaml` | New                | 8 corruption families, 5 SNRs each (matches Phase 1 Stage 8 corruption metadata).                                                            |
| 7   | author `config/claim_dictionary_LOCKED.yaml` | New                  | B5 contradiction injection rules (4 families, thresholds + injection-free zones from §4.B.5.3).                                              |
| 8   | author `config/decision_phase2.yaml`    | New                      | Records frozen architecture (§5), training infra (§6), eval regimes (§7) at Phase 2 start.                                                    |
| 9   | scaffold `outputs/stage_reports/`, `outputs/results/`, `outputs/tables/`, `outputs/figures/`, `outputs/audit_reports/`, `outputs/model_runs/`, `outputs/release_package/`, `data/processed/tasks/`, `scripts/dgx_portability/` | New | Empty directory tree with placeholder READMEs so future stages can write without scaffolding races. |
| 10  | author `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/modality.py` | New | The §2.1 canonical `read_modality()` helper.                                                                                                  |

**Inputs:** All Phase 1 artifacts; `data/raw/ehr_cache/d_labitems.parquet`
for Ca/Mg lookup.

**Outputs:** rewritten configs; new LOCKED YAMLs; quarantine destinations;
scaffolded output tree; canonical modality loader.

**Deletes:** none (quarantine only, deletion deferred per §2.4).

**Validation:**

- The 4 new LOCKED YAMLs schema-validate against a Pydantic schema
  in `_dataset_lib/schema_validators.py`.
- `task_definitions.yaml` has all 12 task keys; each block matches
  the §4 spec.
- `task_input_policy.yaml` has all 12 task keys; every `allowed` and
  `forbidden` entry is a valid modality kind from §2.6 (plus the
  special `report_text` and `report_text_masked` text references).
- `decision_phase2.yaml` records architecture choices verbatim from
  §5 + §6 + §7 (signal=resnet18, image=resnet50_imagenet, text= both
  tfidf and bio_clinicalbert, fusion=late_concat_mlp, primary
  signal=preprocessed, primary image=clean, primary lead=12-lead,
  seeds=[42,123,456], bootstrap=10000_bca).
- `read_modality()` resolves 10 random `(study_id, kind)` calls per
  modality kind successfully.
- Quarantine destinations exist, contain the moved files, and the
  origin paths are gone.

### 9.2 Stage P2.1 — Build Plan A task datasets

**Purpose.** Materialize the 6 Plan A task parquets.

**Scripts to author (all new):**

| #   | Script                                          | What it does                                                                                                       |
| --- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| 1   | `01_build_A1_ecg_diagnosis.py`                  | Resolve ICD groups per `icd_label_map_LOCKED.yaml`; produce A1 train/val/test parquets + cohort_manifest.            |
| 2   | `02_build_A2_measurement_blind.py`              | Bin HR / QRS / QTc per §4.A.2.3; produce A2 parquets.                                                              |
| 3   | `03_build_A3_lab_abnormality.py`                | 7 labs × 5 windows; produce A3 parquets. Requires `lab_itemid_map_LOCKED.yaml` and the Phase 1 label_availability incremental rerun. |
| 4   | `04_build_A4_event_localization.py`             | R-peaks + QRS bounds per §4.A.4.3; produce A4 parquets.                                                            |
| 5   | `05_build_A5_cross_modal_verification.py`       | Verification rows + masked-attribute rows; produce A5 parquets.                                                    |
| 6   | `06_build_A6_risk_stratification.py`            | Mortality + readmission at 30d + 90d; produce A6 parquets.                                                         |

**Inputs:** every Phase 1 artifact + the LOCKED YAMLs from P2.0.

**Outputs:** `data/processed/tasks/A{1..6}_*/{train,val,test}.parquet`,
`data/processed/tasks/A{1..6}_*/cohort_manifest.parquet`,
`data/processed/tasks/A{1..6}_*/README.md`.

**Validation:** per-task spec in §4 (n_ECG, n_subjects, prevalence
within ±5 % of expected, every subject in exactly one split,
boundary-flag distribution recorded).

### 9.3 Stage P2.2 — Build Plan B task datasets

**Purpose.** Materialize the 6 Plan B task parquets.

**Scripts to author:** mirror P2.1 (07–12 indexed builders for B1–B6).

**B2 specifics:** the B2 builder reads
`data/processed/signals_corrupted.parquet` directly; no new corruption
generation occurs in Phase 2 (Phase 1 §3.11 / Stage 8 owns that).

**B5 specifics:** the B5 builder writes `corrupted_report_text` strings
directly into the task parquet because they are derived artifacts
(corrupted text), not raw modalities.

**Validation:** per-task spec in §4.

### 9.4 Stage P2.3 — Phase 2 audits

**Purpose.** Produce `leakage_audit_phase2.md`, `split_audit_phase2.md`,
`cohort_audit.md`, `threshold_audit.md` (pre-flight version with empty
threshold values).

**Scripts to author:**

| #   | Script                       | What it does                                                                                                                          |
| --- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| 20  | `20_audit_tasks_leakage.py`  | For every task: read the parquet, list every column, cross-check against `task_input_policy.yaml`. Flag any forbidden column.         |
| 21  | `21_audit_tasks_cohort.py`   | For every task: n_ECG, n_subjects, per-class prevalence, missingness, linkage-tier breakdown, SQI-tier breakdown, cart_id top-5.       |
| 22  | `22_audit_tasks_split.py`    | For every task: verify zero subject overlap across train/val/test.                                                                    |

**Validation:** all four audits PASS. Any FAIL halts P2.3 and blocks
training stages until fixed.

### 9.5 Stage P2.4 — Algorithmic baselines

**Purpose.** Run the doc-mandated rule baselines for A2, A4, A6, B1,
B3, B5.

**Scripts to author / modify:**

| #   | Script                                | What it does                                                                                                                                                      |
| --- | ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 50  | `50_run_baselines_algorithmic.py`     | Read trained-arch-free baselines from `_model_lib/algorithmic_baselines.py`; produce `outputs/model_runs/<task>/algorithmic/test_predictions.parquet` per task.   |

**Validation:** prediction parquets exist for A2, A4, A6, B1, B3, B5;
metrics match the expected oracle behavior (A4 / B3 should hit F1=1.0
within the algorithmic-baseline's own noise tolerance).

### 9.6 Stage P2.5 — Train signal-only baselines

**Purpose.** Train the 1D ResNet-18 backbone per §5.2 on every
signal-using task, for 3 seeds, per Round 4.2 order.

**Per-task per-seed wall-clock budget:** ~1 h (§8.4).

**Validation:** per task: 3 prediction parquets (one per seed); test
metrics within ±2 std of A2/B1 known baselines from prior pilot work;
`train_log.jsonl` files exist; checkpoints (best + last) exist per
seed; threshold_audit row added.

### 9.7 Stage P2.6 — Train image-only baselines

**Purpose.** Train ResNet-50 (§5.3) on tasks that allow image inputs
(A1, A3, A5, A6, B4, B5, B6).

**Validation:** as P2.5; clean-image-only is default; augmentation off.

### 9.8 Stage P2.7 — Train text-only baselines

**Purpose.** Train Bio-ClinicalBERT (§5.4.2) AND TF-IDF (§5.4.1) on
tasks that allow text inputs.

**Validation:** as P2.5. Two prediction parquets per task per seed
(one per text encoder).

### 9.9 Stage P2.8 — Train multimodal fusion

**Purpose.** Train the late-fusion MLP (§5.5) on top of the modality
encoders, per §5.6 table.

> **RESOLVED 2026-08-26 (Round 5.1).** This stage previously said
> "frozen-**or**-fine-tuned" and never picked one. The answer is
> **end-to-end fine-tuned, everywhere**: the signal, image and text
> encoders train jointly with the fusion head, with the §5.3/§5.4
> discriminative learning rates (backbone 1e-5, new heads 1e-3, BERT
> embeddings 1e-6). No frozen-encoder shortcut is used for any primary
> result. This is the more expensive option and the user has accepted the
> cost explicitly.
>
> The frozen-encoder variant is still **reported as a supplementary
> ablation** ("end-to-end vs frozen late fusion"), because the per-study
> embeddings are a near-free by-product of the P2.5–P2.7 checkpoints and
> it pre-empts an obvious reviewer question.
>
> Consequence for §8.2: fusion is the only stage needing signal + image +
> text co-resident. The L3-cohort tasks (A1/A3/A6, 468 K ECGs) fit the
> quota outright; the full-cohort tasks (A5/B4/B5/B6, 749 K) use the
> aligned-chunk protocol.

**Per-task per-seed budget:** ~2.5 h.

**Validation:** as P2.5; verify multimodal beats the best single-modality
baseline by at least a small margin on the val set (sanity check;
small inversion is acceptable but flagged in cohort_audit).

### 9.10 Stage P2.9 — Evaluate

**Purpose.** Run `31_eval.py` against every prediction parquet and
write `outputs/results/<task>.csv`.

**Validation:** `outputs/results/all_tasks_summary.csv` has one row per
(task, arch_tier, lead_subset); per-(task,arch,seed) metrics are
within ±0.5 std of three-seed mean (sanity check that no seed is wildly
off).

### 9.11 Stage P2.10 — Sensitivity sweeps

**Purpose.** Run §7.2 sensitivity matrix.

**Validation:** every sensitivity sweep listed in §7.2 produces a
`outputs/results/<task>_sensitivity_<sweep>.csv` file.

### 9.12 Stage P2.11 — Calibration + threshold + reproducibility audits

**Purpose.** Close out the audit suite.

**Scripts to author:** all three audit consumers read the prediction
parquets, threshold_audit pre-flight, and emit the final audit reports.

**Validation:** every audit PASS. Reproducibility audit must include
at least 5 entries per task (one per primary metric).

### 9.13 Stage P2.12 — Paper tables + figures

**Purpose.** Generate the locked 5 main tables, 5 main figures, 15
supplementary tables, 8 supplementary figures (Round 4.3 decision).

**Validation:** every figure file exists; every table .tex compiles
in a smoke check; every figure has a corresponding row in
`outputs/figures/README.md` recording the script + invocation that
produced it.

### 9.14 Stage P2.13 — Release package

**Purpose.** Build `outputs/release_package/`.

**Validation:** `outputs/release_package/README.md` walks a reviewer
through reproducing every main-paper number. `checksums.txt` includes
sha256 of every shipped config / script.

### 9.15 Resume semantics across stages

Each stage's `30_train.py` / `31_eval.py` / etc. invocation is
idempotent and resumable (§8.6). Re-running a stage that has already
PASSED its validation is safe and skips completed sub-units (per-task
per-seed completion is tracked in
`outputs/stage_reports/stage_P2.<n>_state.json` — mirrors Phase 1
state-file convention).

---

## 10. Per-stage agent output format

Mirrors Phase 1 §10. After completing a stage, the agent halts, emits
`outputs/stage_reports/stage_P2.<n>_report.md`, AND prints it to stdout
in a single block. The report contains **exactly these eight numbered
sections** in this order:

```txt
# Stage P2.<n> — <stage name> — report

## 1. Files created
- <relative path>  (<size>, sha256 <hex prefix 12>)
...

## 2. Files modified
- <relative path>  ::  <one-line summary of what changed>
...

## 3. Files / folders deleted
- <relative path>  ::  <file count, total bytes freed>
(or: "none — quarantine only")

## 4. Design decisions
- <decision 1>  ::  <one-paragraph reasoning>
...

## 5. Complete code
For every script in §2 (modified) or §1 (created) under `scripts/`,
paste the full final file contents in a fenced code block labeled
with the file's path. No "..." elisions.

## 6. Validation results
- Pre-flight: <PASS/FAIL with disk-free + Phase 1 stage-complete checks>
- Per-validation-bullet from §9.<n>: <PASS/FAIL with numbers>
- Logging-hygiene checklist (Phase 1 §8.14 all bullets):
  - [ ] Terminal showed one tqdm bar, no interleaving
  - [ ] aggregate.log / all.log exists, first + last 5 lines pasted
  - [ ] no `print(` in worker bodies (paste grep result)
  - [ ] no `logging.basicConfig` in worker (paste grep result)
  - [ ] worker_<pid>.log files moved into archive_<ts>/
  - [ ] If Transport B: `listener.stop()` in finally block
  - [ ] If tqdm used: `mininterval=0.5` and `logging_redirect_tqdm()`
- Disk before stage start: <GB free>
- Disk after stage end: <GB free>
- Wall-clock: <hh:mm:ss>

## 7. Manual test procedure
Specific commands the user can run to independently re-verify the
stage's outputs. Each command on its own line, no shell pipelines
spanning multiple lines.

## 8. Assumptions requiring user confirmation
- <assumption>  ::  <why it matters / what changes if it's wrong>
(or: "none")
```

If any §6 validation bullet is FAIL, the agent **does not delete** any
old artifact for this stage and halts with an explicit
`STAGE P2.<n> HALTED — VALIDATION FAILED` line at the bottom of the
report.

---

## 11. Reviewer checklist

The reviewer reads the stage report and verifies it against this doc.
**Review only — do not rewrite the code.**

### 11.1 Coverage areas

| Area                          | What to look for                                                                                                                                                                                                                                                                                                |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Plan-A-specific compliance    | Every Plan A task's primary cohort is L3; L3+L2 sensitivity reported separately; ICD/lab mapping references the locked YAMLs; boundary-flag distribution recorded.                                                                                                                                              |
| Plan-B-specific compliance    | B2 corruption metadata read from `signals_corrupted.parquet` (NOT regenerated); B5 contradiction injection thresholds match §4.B.5.3 exactly; B3 NOISY_SEGMENT threshold computed on TRAIN only.                                                                                                                |
| Statistical-rigor compliance  | Every results table includes the §1.1 columns; bootstrap is patient-level with n=10,000 BCa (when n_pos ≥ 100); 3-seed mean ± std AND pooled-prediction CI both reported.                                                                                                                                       |
| Architecture compliance       | Encoders match §5 exactly (1D ResNet-18 from scratch, ResNet-50 ImageNet, Bio-ClinicalBERT, TF-IDF+SVD, late-fusion MLP). No surprise architecture swaps. Per-task YAML in `config/model_configs/` matches.                                                                                                     |
| Calibration compliance        | A3, A6 results include reliability diagram + ECE + Brier; recalibration applied if ECE > 0.05.                                                                                                                                                                                                                  |
| Sensitivity compliance        | Every sweep listed in §7.2 produces its CSV.                                                                                                                                                                                                                                                                    |
| Reproducibility compliance    | `reproducibility_audit.md` has at least 5 entries per task.                                                                                                                                                                                                                                                     |
| Cross-task fairness           | When two architectures are compared on the same task, they used identical test subjects, identical input modalities (or differed only in one allowed-input dimension), identical CI method.                                                                                                                     |
| Leakage compliance            | `leakage_audit_phase2.md` PASS for every task. Spot-check: for A2/B1/B2/B3/A4, no `rr_interval/qrs_*/t_axis/structured_features` columns appear in any feature loader or feature parquet read at train time.                                                                                                    |
| Threshold compliance          | Every classification threshold logged in `threshold_audit.md` with its val-set Youden's J value; no test-set threshold tuning.                                                                                                                                                                                  |
| Boundary-case sensitivity     | A1, A6 include the boundary-excluded sensitivity table in supplementary.                                                                                                                                                                                                                                        |
| First-ECG sensitivity (A6)    | First-ECG-per-admission AND first-ECG-per-patient sensitivity tables both present in A6 supplementary.                                                                                                                                                                                                          |
| Logging-hygiene compliance    | Same as Phase 1 §8.14 — full checklist must pass.                                                                                                                                                                                                                                                              |
| DGX deferred                  | `scripts/dgx_portability/` exists as templates only; no code path silently depends on DGX.                                                                                                                                                                                                                      |

### 11.2 Severity classification

- **CRITICAL** — blocks Phase 2 completion or compromises data integrity
  (e.g., test-set threshold tuning; raw vs preprocessed input mislabeled
  in results CSV; forbidden field leaks into a task parquet; missing
  primary metric; subject overlap across splits; bootstrap is ECG-level
  instead of patient-level; algorithmic baseline missing for a doc-mandated task).
- **MAJOR** — spec violation that lets the stage proceed but creates
  downstream risk (e.g., calibration not applied when ECE > 0.05;
  sensitivity sweep missing for a doc-required cell; wrong CI method;
  per-cart_id breakdown missing).
- **MINOR** — cosmetic / pre-existing (e.g., docstring outdated, table
  column ordering different from §1.1).

### 11.3 Finding format (one per issue, in this exact shape)

```txt
## <SEVERITY>: <one-line title>

**Spec section:** <quote the exact source-of-truth section, e.g. "§6.5 — Threshold selection on validation only">

**Violation:** <one-paragraph description of what the agent did wrong>

**Fix:** <specific instructions on what change to make. Do NOT paste rewritten code; describe the change as a directive>
```

### 11.4 Rules for the reviewer

- Do not rewrite code; describe the change.
- Only review against this doc + Phase 1 doc + Plan A/B doc + Truth doc.
  No new requirements that aren't in source-of-truth.
- Quote, don't paraphrase. Every finding cites a section and quotes
  the binding sentence.
- Be decisive: CRITICAL, MAJOR, or MINOR.
- Conclude with either
  `## REVIEW VERDICT: PASS — proceed to Stage P2.<n+1>` or
  `## REVIEW VERDICT: HALT — <count CRITICAL> CRITICAL, <count MAJOR> MAJOR findings; address before re-submitting Stage P2.<n>`.

---

## 12. Resolved decisions

### 12.1 Round 1 (locked 2026-06-03)

1. **Plan scope:** Plan A primary (A1–A6) + Plan B supplementary
   (B1–B6). All 12 tasks first-class deliverables.
2. **Model architecture strategy:** Shared backbone per modality +
   task-specific heads, doc-recommended encoders (Truth §9.2).
3. **Compute strategy:** Local Windows + single CUDA GPU primary, all
   stages run to completion locally. DGX H100 burst is optional —
   never blocks Phase 2.
4. **Statistical rigor:** 3 seeds (42, 123, 456), patient-level
   bootstrap n=10,000, BCa CI when n_pos ≥ 100.

### 12.2 Round 2 (locked 2026-06-03)

1. **A1 ICD groups:** Plan A/B Appendix B verbatim — 5 groups
   (atrial_fibrillation_flutter, heart_failure_narrow,
   acute_myocardial_infarction, conduction_disorder,
   ventricular_arrhythmia_or_arrest).
2. **A3 lab universe:** 7 labs (K, Na, Ca, Mg, Cr, troponin, lactate).
   Requires extending `key_labs.yaml` with Ca / Mg itemids and
   re-running Phase 1's `44_label_availability.py` incrementally
   (§4.A.3.2 pre-requisite). Abnormality definition: ref_range → flag
   → locked_threshold, per Plan A/B Appendix C.
3. **A6 horizons:** 30d + 90d mortality + 30d + 90d readmission. ED-only
   ECGs excluded from readmission head. First-ECG-per-admission +
   first-ECG-per-patient sensitivity required.
4. **B5 contradiction types:** HR + QRS + axis + PR (4 families).
   Injection-free zones in §4.B.5.3 prevent unsafe injections. PR
   sourced from `structured_features.parquet.pr_ms`.

### 12.3 Round 2.5 (locked 2026-06-03)

1. **A4 events:** R-peak detection + QRS boundary localization
   (fiducials only; 10-bin queries handled by B3).
2. **A5 framing:** Verification with 5 negative types + masked-attribute
   prediction (two heads on shared tri-encoder).
3. **B3 queries:** HIGH_HR + LOW_HR + WIDE_QRS + NOISY_SEGMENT
   (extends current dataset with NOISY_SEGMENT; threshold locked on
   train).
4. **Boundary cases (A1/A6):** Include in primary cohort, sensitivity
   table reports boundary-excluded.

### 12.4 Round 3 (locked 2026-06-03)

1. **Signal encoder:** 1D ResNet-18 trained from scratch.
2. **Image encoder:** ResNet-50 pretrained on ImageNet-1k.
3. **Text encoder:** TF-IDF + linear projection (simple) + Bio-ClinicalBERT
   (strong). Both run for every text-using task.
4. **Fusion strategy:** Late-fusion concat + MLP.

### 12.5 Round 3.5 (locked 2026-06-03)

1. **Primary signal modality:** Preprocessed.
2. **Primary image modality:** Clean.
3. **Primary lead set:** 12-lead (Lead-II reported as Track-1).

### 12.6 Round 4 (locked 2026-06-03)

1. **DGX portability:** Don't know access model yet — keep doc generic,
   defer until access tested. Local-only path is the primary; DGX adds
   nothing the doc relies on. Scaffold templates under
   `scripts/dgx_portability/`.
2. **Training queue priority:** Plan A first
   (A2 → A1 → A4 → A3 → A6 → A5), Plan B after
   (B1 → B2 → B3 → B4 → B5 → B6). Within task,
   algorithmic → signal → image → text → multimodal.
3. **Paper scope:** Main 5 figures + 5 tables; Supplementary 8 figures
   + 15 tables (Plan A/B §7/§8 alignment).
4. **Checkpoint retention:** Keep best + last for every (task, arch,
   seed) — disk budget ~150–200 GB for Phase 2 model_runs.

### 12.7 Round 5 (locked 2026-08-26)

Raised once the real DGX allocation was granted (MU HPCF, 2026-06-22
email: DGX A100, Slurm `cpu_student`/`gpu_student`, **50 GB** quota,
MU-network-only access, account expiry 2026-12-31) and the user's
compute constraints became concrete.

1. **Fusion protocol → end-to-end fine-tuned.** §9.9's
   "frozen-or-fine-tuned" is resolved to fully fine-tuned for every
   primary multimodal result. Frozen late fusion is kept as a
   supplementary ablation only. User's words: "for 1 full end to end",
   "publishing grade work … we cannot compromise on that no matter what".
2. **A4/B3 fiducial source → re-run NeuroKit2 at build time.** This was
   listed as open in §13.4.2, and the choice is now forced rather than
   preferred: the "pre-computed R-peaks" alternative does not exist on
   disk (see the correction in §4.A.4.3). New script
   `00_extract_fiducials.py`, reusing the Phase 1 corrected detector.
3. **Compute placement → DGX-primary, laptop development-only.** §8
   rewritten. The laptop's 6 GB VRAM cannot fit the §6.6 image/text batch
   sizes, and its mains supply is unreliable for multi-day runs. Every
   trained number in the paper comes from the DGX; CPU-heavy stages
   (P2.1–P2.4) run on `cpu_student`, not locally.
4. **Checkpoint retention → best-only, evicted on completion.** Round
   4.4's "keep best + last for every run, ~150–200 GB" is impossible
   under a 50 GB quota and is superseded by the §8.1 policy.
5. **Signal staging format → int16 + per-record scale.** Storage change,
   not a precision change (§8.2); validated empirically in Stage P2.0 and
   the comparison ships in the supplementary.
6. **Oversized campaigns → aligned i.i.d. chunk cycling within each
   epoch** (§8.2 rule 2), recorded as a documented sampling deviation.
   Sequential per-chunk training is explicitly forbidden.
7. **Scope unchanged.** Round 1.3 ("we do not skip anything at all no
   matter what") is reaffirmed under the new constraints: no task, seed,
   sweep, or lead-set track is dropped to save compute or transfer.

**Still open, pending the first DGX session** (does not block Stage
P2.0): whether compute nodes expose scratch space beyond the 50 GB quota
(would remove chunking from three campaigns); whether the DGX has
outbound internet (decides the staging path); Slurm wall-time and GPU
limits on `gpu_student`; and whether an NGC PyTorch container exists
(would free ~12 GB of quota).

### 12.8 Round 6 — locked 2026-08-26 (during Stage P2.0)

Every item here was forced by checking this document's claims against the
Phase 1 artifacts on disk, not by preference. Items 1, 4 and 5 are
**documented deviations from the text of §4** and must be disclosed in the
paper's supplementary material.

1. **Measurement source → the MACHINE measurement, everywhere.** Binding
   for B5's four families and for the A2 / B1 / A5-masked-attribute bins:
   `machine_hr_bpm`, `machine_qrs_ms`, `qrs_axis`, and `qrs_onset −
   p_onset` for PR, all from
   `ecg_metadata_clean_with_measurements.parquet`. §4.B.5.3 named
   `structured_features.parquet.pr_ms`; that column is the NeuroKit2
   interval (median 120 ms, max 9468 ms), and `structured_features.qrs_ms`
   is byte-identical to `structured_features.qrs_dur_ms` rather than the
   machine `qrs_end − qrs_onset` that §4.A.2.3's own formula specifies.
   Using the NeuroKit PR would have placed 425,562 studies in the "clear
   normal PR" zone and shipped 9,035 studies whose report already says
   "1st degree A-V block" as **clean** B5 rows. The machine PR yields
   1,083 such disagreements against 13,111 coherent ones. No builder may
   read `structured_features.qrs_ms` or `.pr_ms` by name.

2. **Missing-value sentinel → `29999`; the `*_missing` flag columns are
   unusable.** `p_onset_missing`, `qrs_onset_missing`, `qrs_end_missing`,
   `qrs_axis_missing` and `rr_interval_missing` are **False for all
   749,112 rows** — they mark nothing. The real encoding is the literal
   value `29999` (`p_onset` 119,385 rows, `p_axis` 119,483, `qrs_axis`
   1,531, `rr_interval` 487, `qrs_onset` / `qrs_end` 341 each). Unmasked,
   PR has mean −4600 ms; masked, mean 162.7 ms (median 160, sd 37). Every
   builder touching a machine measurement masks the sentinel and applies
   the plausible range in `config/claim_dictionary_LOCKED.yaml`.

3. **B5 injections → swaps only, never insertions.** A study is eligible
   for a family only when the measurement is valid and inside a clear zone
   **and** the report carries a matching surface form. §4.B.5.3 specifies a
   swap and requires a recorded span; an inserted claim would produce a
   span with no original counterpart and would make the corrupted class
   separable by length or phrasing rather than by the contradiction.
   Measured: 128,674 of 749,112 studies (17.2 %) are eligible.

4. **A2 primary cohort → `sqi_tier ∈ {high, medium}`,** superseding
   §4.A.2.2's `sqi_tier == 'high'`. Measured, `high` is 4,166 of the
   749,112-study clean cohort (0.56 %), of which **3,110 are L3** — against
   the "~445 K primary" §4.A.2.2 estimates. Built to the letter A2 would
   train on 3,110 ECGs while being both the whole-cohort sanity check §5.4
   calls for and the first task in the §8.3 queue, whose job is to exercise
   the entire trainer stack. `{high, medium}` gives **275,088 L3 ECGs**
   (94,025 subjects; train 192,087 / val 27,820 / test 55,181). high-only
   becomes one row of the §4.A.2.8 per-SQI sensitivity table rather than
   the definition of the cohort. A4 already specifies `{high, medium}`
   (§4.A.4.2) and is unaffected; the two tasks now share one SQI rule.
   *Not chosen:* re-cutting the Phase 1 SQI tier boundaries — it would
   silently change A4, B3 and every per-SQI table at once, and Phase 1 is
   frozen (§2).

5. **B5 row emission → one row per ELIGIBLE study, corrupted with
   p = 0.5.** This reconciles §4.B.5.3 with §6.4, which cannot both hold as
   written: §4.B.5.3's "one uncorrupted row per ECG plus a corrupted row
   with 50 % probability" yields 749,112 clean against ~64,000 corrupted
   (12:1), while §6.4 asserts "balanced 50/50 clean/corrupted by dataset
   design". Emitting exactly one row per eligible study at p = 0.5 is the
   only reading under which both sentences are true, and it is what §6.4
   relies on when it declines to apply any `pos_weight` to the B5 binary
   head. Cohort: **128,674 rows**, 38,438 subjects (train 89,855 / val
   12,944 / test 25,875). Studies eligible for no family contribute no row.
   Drawing the clean rows from the same eligible pool is deliberate — it
   stops "the report contains a swappable claim" from being a signal for
   the label. *Not chosen:* keeping all 749,112 clean rows and handling
   12:1 with `pos_weight`.

6. **CPU-only stages run on the laptop, not `cpu_student`.** Amends Round
   5.3 (§12.7.3), which sent Stages P2.1–P2.4 to the DGX CPU partition. The
   user has approved long local runs. Stage P2.1's `00_extract_fiducials.py`
   (~5–10 h over the 468 K A4 cohort), the twelve task builders, the P2.3
   audits and the P2.4 algorithmic baselines all execute at full scale on the
   laptop. **Round 5.3's core holds unchanged: every TRAINED model in the paper
   still comes from the DGX.** Consequences: the EHR cache never leaves the
   laptop (which also suits the data-use agreement), the upload budget drops
   from ~145 GB to ~142 GB, one campaign disappears from the schedule, and the
   §4.C invariant-4 audit gate closes before the first upload instead of after
   it. The cost is that every long local script MUST checkpoint and resume —
   mains power is unreliable — which §8.2.1 already required.

7. **The cached lab table is missing the three columns A3's label rule needs.**
   `data/raw/ehr_cache/labevents.parquet` (158,374,764 rows) carries only
   `labevent_id, subject_id, hadm_id, itemid, charttime, valuenum, valueuom`.
   §4.A.3.3's rule branches on `ref_range_lower`, `ref_range_upper` and `flag`,
   none of which were kept. Without them A3 collapses to `missing` vs
   `not_missing` and the low/high/abnormal distinction is unrecoverable. The
   columns DO exist in the original download
   (`data/raw/mimic-iv-hosp-3.1/hosp/labevents.csv.gz`, 16 columns including
   all three). **Resolution: Stage P2.1 re-extracts the lab cache for the 18
   locked itemids, keeping `ref_range_lower`, `ref_range_upper`, `flag`,
   `valueuom` and `value`, before `03_build_A3_lab_abnormality.py` runs.** This
   extends an EHR cache; it re-runs no Phase 1 stage and changes no Phase 1
   output, so the §2 "never re-run Phase 1" rule is not engaged. §4.A.3.5's
   `abnormal_method` column already anticipates the three provenance values
   (`ref_range | flag | locked_threshold`), so no schema change follows.

**Also verified at Stage P2.0 and PASSING, recorded so it is not
re-checked:** the §4.A.3.2 step-5 coverage gate (Ca 75.81 %, Mg 77.25 %
±24 h in the L3 cohort, both ≥ 50 %), so the 7-lab universe locks; and all
five §4.A.1.3 ICD groups resolve against `d_icd_diagnoses` (175 distinct
codes, 275,334 assignment rows).

**One §4.B.2.2 description error is NOT resolvable by rebuilding.** That
section describes the B2 anchor pool as "test-split ECGs with
`sqi_tier='high'`". Phase 1 Stage 8 applied no SQI filter: it took the
`raw_lead2` manifest rows for test-split subjects, sorted by
`(study_id, subject_id)`, and truncated to the first 2,000. The 1,872
anchors present in the clean cohort are 8 high / 1,119 medium / 745 low.
The corrupted set is frozen and Phase 2 never regenerates it (§9.3), so
the correct action is to amend §4.B.2.2's wording and describe B2 anchors
in the paper as an SQI-representative test-split sample — arguably the
better design, since a high-SQI-only anchor set would overstate
robustness, but it must be described accurately.

---

### 12.10 Round 11 — locked 2026-09-30 (the scan-like staging round)

Two questions were settled while closing the A5/B4 scan-like data gap. Neither
changes a cohort, a metric, a split or a model; both change **what a campaign
stages**, and the second corrects a mis-description in the execution plan.

1. **A5/B4 read two image containers, not one, and the campaign table has to
   say so.** §4.A.5 gives every anchor a clean positive *and* a scan-like
   positive (Truth doc §6.1, "Positive type 2"), and `task_dataset.py` builds
   the modality kind from the ROW's `image_type`, so an A5/B4 run's config
   names only the layout. Every A5/B4 config that touches images therefore
   reads `image_scanlike_<layout>` as well as `image_clean_<layout>`. That set
   is 599,470 of 749,112 studies for train+val — **50.08 GB for 12-lead**, more
   than the whole storage ceiling — so the scan-like TRAIN split is cut into
   **eight aligned i.i.d. pieces under §8.2 rule 1** and cycled under rule 2,
   and val/test ship as per-layout containers. No cohort changes: the pieces
   are a partition of the same studies, keyed by
   `blake2b(salt|study_id) % 8`, which is independent of subject, label, cart
   and time by construction and measured to be so.

2. **The scan-like image tier is a TRAINED arm, not a test-time sweep.** §5.3
   turns image augmentation **on** "when training on scan-like or mixed
   clean+scanlike" and off for clean-only training, and `model_configs.py`
   emits exactly that — `augmentation: true` on every `*_scanlike` config and
   `false` on every `*_clean` one. Augmentation is applied only when
   `split == "train"`, so the setting is meaningless unless the tier trains.
   It is the image-side analogue of §7.3's B2 regimes, where regime_1 is the
   clean-trained arm and regime_2 the corruption-augmented one, and both are
   trained. The 30 runs it contributes are part of the **104 configs / 312
   runs** this spec counts; treating it as evaluation-only would silently drop
   them.

   `docs/PHASE2_EXECUTION_PLAN_DGX.md` described that campaign as "the sweeps
   that only need re-testing… test split only", which is **wrong** and has been
   corrected. Because the tier covers both layouts and a trained scan-like arm
   needs train+val for each, the campaign is **split by lead subset** exactly as
   Round 5's campaigns 7/8/11 were into 12/13/14: campaign 10 is the 12-lead
   half and campaign 15 the Lead-II half, 5 configs and 15 runs each. **No
   config was renamed, no run or seed dropped** — `campaign_runs.py --table`
   still reports 104 configs and 312 runs.

### 12.11 Round 12 — locked 2026-11-03 (chunk cycling, pair mode)

- **Pair-mode chunk cycling for runs whose rows span two pieces.** Mismatched
  A5/B4 pairs read the signal of one study and the image of another, so under
  the §8.2 cut 1,375,455 of campaign 8's 3,667,615 train rows need two
  different pieces resident together (job 29648 refused them). Such a run's
  epoch walks **every pair of pieces** as a two-piece window (28 for 8 pieces),
  reshuffled every epoch; split rows train in their pair's window, single-piece
  rows in a window holding their piece, drawn per epoch. §8.2 rule 2 holds:
  every piece every epoch, reshuffled, two resident, never sequential per
  piece. Runs with no split row are unchanged. Cost: ~28 piece fetches per
  epoch instead of 8. Disclosed with the block-shuffle deviation
  (`config/decision_phase2.yaml` `chunking.pair_mode`).

### 12.9 Round 10 — locked 2026-08-28 (the Plan A/B compliance audit)

A cold re-read of `ECG_Benchmark_Neutral_Implementation_Plan_Plan_A_B.docx`
against what is actually on disk (`docs/PLAN_DOCX_COMPLIANCE_AUDIT.md`) found
six gaps between the plan and this spec. All six are closed here. **Nothing had
been trained yet**, so five cost no GPU time at all and the sixth costs +30 runs.

1. **A2 and B1 gain regression heads.** Plan §5.4 makes MAE/RMSE the *primary*
   metric for HR and QRS and asks for Bland-Altman limits; §7.1 repeats it for
   the whole regression/measurement task type. We had bins only, with the
   continuous truth sitting unused in the parquet as provenance. Three
   regression heads now ride alongside the three binned heads on the same
   encoder — **no extra run** — and the bins remain the early-stopping metric.
   Standardisation uses declared physiological constants, not fitted statistics,
   so no split can leak through it. Tolerances: QRS ±10 ms is Plan-mandated;
   **HR ±5 bpm and QTc ±20 ms are conventions declared here — disclose in the
   supplementary.** B2 keeps bins only (no continuous columns; Plan §7.1 scores
   robustness on AUCC). See §4.A.2.6.

2. **A6 gains the Plan §5.8 nested clinical ladder, and the columns to build
   it.** §5.8 requires six baseline tiers and Figure 5 is the nested curve;
   Plan §7 names *"Only compared to random/prevalence baseline"* as a failure
   condition, and §1.1 makes this the evidence for "ECG adds prognostic signal
   beyond demographics". We had one Cox model bundling age + sex + machine
   measurements, then a jump straight to the neural tiers — and the A6 parquet
   carried **no age, sex, race, insurance, prior-admission count, prior-ECG
   count or admission type**, so the intermediate rungs were not merely missing,
   they were unbuildable. A6's schema now carries fifteen strictly pre-ECG
   covariates and four nested baselines are emitted as sibling `arch_tier`s.
   Every covariate is knowable at `ecg_time` — prior counts read admissions
   *discharged* before the ECG, prior diagnoses come from those admissions only
   (ICD codes are assigned at discharge, so the current admission's codes
   describe the very episode being predicted), the ED disposition comes from a
   stay that had already ended — and the builder asserts the one-sided cut
   rather than assuming it. Plan Appendix F lists "using future covariates for
   risk" as a named failure mode. The comorbidity vocabulary is the **locked A1
   ICD map**, imported not copied, so A1 and A6 cannot drift. CPU only; no GPU
   time. See §4.A.6.7.

3. **A3's structured baseline is restored.** Plan §5.9 requires it for A1, A3
   *and* A6; §4.A.3.7 had waived A3's on the grounds that no rule-based
   ECG → lab predictor exists. True of a *rule*, but §5.9 asks for a *fitted*
   feature model, and reference [R5] (CardioLab) is exactly that comparison.
   A3 was shipping with no floor. A multinomial logistic on the machine
   measurements now runs per (lab × window) head, under a `baseline_only`
   exemption A3 declares like A1's. See §4.A.3.7, §5.1.

4. **B6's difficulty ladder goes from two rungs to six.** Plan §6.7 specifies
   Levels 0–5 and Figure 4 is the curve across them — the evidence for Plan B's
   core shortcut-elimination claim. We had Level 0, Level 1, and a "hard" tier
   that shipped empty. Levels 2–5 are added to A5 and B4 alike (§4.B.4.8's
   comparison requires identical rows) and **only in the TEST split**: the
   levels measure generalisation to harder negatives, so training on them would
   train away the plateau §6.7 predicts, and keeping them out of train means
   **no model is retrained** to get the curve. Level 5 reuses B5's locked
   contradiction injection rather than inventing a second text-alteration rule.
   Round 3's reserved "hard" tier is closed by this; its same-subject idea is
   Level 4. See §4.B.6.2.

5. **The no-text ablation is retrained, not simulated.** Plan §5.3 ablation 6,
   Figure 2 and Appendix F make the no-text multimodal run the *primary
   leakage-controlled setting*. §7.2 listed it among the sweeps that
   "re-evaluate the same trained model" — reasoning written when fusion was
   frozen late fusion. Round 5.1 made fusion end-to-end fine-tuned, and zeroing
   the text branch of a jointly-trained encoder yields a forward pass outside
   the model's training distribution, not an ablation. Ten
   `multimodal_fusion_notext_*` configs (A1/A3/A5/A6/B4 × 2 lead sets) now
   exist: **+30 runs**, in campaigns 7 and 8. This is the only one of the six
   gaps that costs GPU time, and it buys the word "leakage-audited" in the
   title. B5 is excluded — dropping text there collapses to the existing
   signal-only tier. See §7.2.

6. **Contrastive / CLIP-style pretraining is DECLINED, explicitly.** Plan §5.9
   lists it as a model family ("CLIP-style alignment among signal, image and
   text; then fine-tune on tasks. Tasks: A5 plus downstream A1/A3/A6"). Round 3
   locked late-concat fusion and this spec has never mentioned contrastive
   learning at all — a silent omission a reviewer would read as an oversight.
   The decision is to **not build it**, for stated reasons: it is a whole
   pretraining regime rather than a baseline, it would need its own
   hyperparameter search on a 50 GB quota, and §5.9 frames its table as a menu
   of families rather than a required set. `A5/B4_embedding_cosine_*` already
   supplies the no-fusion alignment reference point that §7.5's retrieval
   evaluation needs. **State this as a limitation in the paper**, not as a
   result. Revisit only if a reviewer asks.

7. **B5's fourth contradiction family is PR, not QTc — recorded as a
   deviation.** Plan §6.6 lists HR, QRS width, QTc, axis and an optional
   lead/findings phrase; the locked `claim_dictionary_LOCKED.yaml` implements
   HR, QRS, axis and **PR**. The substitution was made at Round 2 and never
   written down as a divergence from the plan. It stands — PR has a clean
   surface form in this report vocabulary and a defensible clear zone, where a
   QTc claim rarely appears as swappable text — but it is **a documented
   deviation and must be disclosed in the supplementary**, alongside the other
   Round 6/7 measurement deviations.

**Audit consequences.** `20_audit_tasks_leakage.py` gained three rules: a column
that is a head's *target* is not an input (A2/B1's `hr_bpm`/`qrs_ms`/`qtc_ms`
are now labels, and gate 3 remains what proves unreachability); `baseline
covariate` is a declared role backed by the policy's `baseline_only_exemptions`;
and the exemption roster is now A1, A3, A6. `12_build_B6_*.py` gained a gate
that **fails if any of the six levels has no test rows** — the check that would
have caught the empty "hard" tier the first time.

---

## 13. Open-decision queue

### 13.0 Round 1 — DONE

### 13.1 Round 2 — DONE

### 13.2 Round 2.5 — DONE

### 13.3 Rounds 3, 3.5, 4 — DONE

### 13.4 Round 5 — PARTIALLY RESOLVED (see §12.7, locked 2026-08-26)

| # | Question | Status |
| - | -------- | ------ |
| 1 | **A3 lab-window join policy** — `same_subject` only vs `same_subject AND same_hadm_id` for the primary cohort | **OPEN** — raise at Stage P2.1 when building A3 |
| 2 | **A4 ground-truth source** — cached R-peaks vs re-running NeuroKit2 | **RESOLVED** (§12.7.2). Forced, not chosen: the cached arrays do not exist. See §4.A.4.3 correction. |
| 3 | **A5 anchor-pool construction** — random vs stratified over the 5 neg_types | **OPEN** — raise at Stage P2.1 when building A5 |
| 4 | **B5 span tokenization** — character vs token offsets | **OPEN** — raise at Stage P2.2 when building B5 |
| 5 | **DGX access details** | **RESOLVED** (§12.7.3). A100, Slurm, 50 GB, MU-network-only, expiry 2026-12-31. Four sub-questions remain, listed at the end of §12.7. |

The three still-open items are all Stage P2.1/P2.2 builder questions and
none of them block Stage P2.0. When the implementing agent reaches one,
it raises a Round-5 question via the AskUserQuestion harness and records
the answer here.

### 13.5 Round 6 — RESOLVED (see §12.8, locked 2026-08-26)

| # | Question | Status |
| - | -------- | ------ |
| 1 | **Measurement source** — machine measurements vs the `structured_features` NeuroKit columns | **RESOLVED** (§12.8.1). Machine, everywhere. Documented deviation from §4.B.5.3. |
| 2 | **Missing-value encoding** — the `*_missing` flags mark nothing | **RESOLVED** (§12.8.2). Sentinel is `29999`. |
| 3 | **B5 injection mechanic** — swap vs insert | **RESOLVED** (§12.8.3). Swap only. |
| 4 | **A2 primary cohort** — `sqi == high` (3,110 ECGs) vs `sqi ∈ {high, medium}` (275,088) | **RESOLVED** (§12.8.4). `{high, medium}`. Documented deviation from §4.A.2.2. |
| 5 | **B5 row emission** — §4.B.5.3's 12:1 vs §6.4's "balanced 50/50" | **RESOLVED** (§12.8.5). One row per eligible study at p = 0.5; 128,674 rows. |
| 6 | **B2 anchor-pool description** — §4.B.2.2 says high-SQI; Stage 8 applied no SQI filter | **OPEN (wording only)** — the data is frozen and correct; §4.B.2.2's text needs amending before the B2 write-up. |

### 13.6 Round 7 — reserved

For decisions arising after the first DGX session returns the four
environment answers listed at the end of §12.7.

---

## 14. What this leaves for paper writing

Out of scope for this document, but tracked so it's not forgotten:

- Manuscript writing itself (prose, related-work positioning vs
  MEETI/CardioLab/SignalMC-MED/ECG-mortality benchmarks per Plan A/B
  §1.1 references).
- Camera-ready typesetting.
- External reviewer responses.
- Reviewer-suggested experiments that don't already appear in the §4
  task list — those will require an additional Phase 2 doc revision.
