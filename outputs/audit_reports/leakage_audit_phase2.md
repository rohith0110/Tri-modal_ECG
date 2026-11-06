# Leakage audit — Phase 2 tasks (Stage P2.3)

**VERDICT: PASS** — 88 checks run, 88 passed, 0 violations.

Spec §9.4 (Stage P2.3), §4.C invariant 4, §11.1 leakage compliance. Generated 2026-11-06T11:58:17Z by `scripts/phase2_tasks_benchmark_and_paper/20_audit_tasks_leakage.py` from the task parquets on disk — every number below is measured, none is restated from a builder's own report.

`config/task_input_policy.yaml` is the single authority on leakage. This audit checks the 12 task parquets and the code that loads them against it in six gates: the column inventory §9.4 asks for, plus the model-config, dataloader, B5-single-report, A5-head-isolation and source-tree gates that cover the part of the leakage surface a column list cannot see.

A **declared provenance** column is one §4's own output schema puts in the parquet even though it names a forbidden quantity (§4.A.2.5's `hr_bpm`, §4.B.5.5's `source_measurement`). Those are permitted **only** because gate 3 shows the dataloader never hands them to a model.

## Verdict by task

| Task | Checks | Verdict |
| --- | ---: | --- |
| `A1_ecg_diagnosis` | 8 | **PASS** |
| `A2_measurement_blind` | 5 | **PASS** |
| `A3_lab_abnormality` | 8 | **PASS** |
| `A4_event_localization` | 5 | **PASS** |
| `A5_cross_modal_verification` | 12 | **PASS** |
| `A6_risk_stratification` | 8 | **PASS** |
| `B1_measurement_blind` | 5 | **PASS** |
| `B2_noise_robustness` | 5 | **PASS** |
| `B3_temporal_grounding` | 5 | **PASS** |
| `B4_cross_modal_verification` | 9 | **PASS** |
| `B5_contradiction_detection` | 10 | **PASS** |
| `B6_difficulty_stratified` | 4 | **PASS** |
| `(all tasks)` | 4 | **PASS** |


## Gate 1 — column inventory against `task_input_policy.yaml`

Every column of every task parquet, classified. A column whose name resolves to a **forbidden reference** (`machine_measurements` / `structured_features`) is a violation unless §4's own output schema mandates it as provenance — those are named in `PROVENANCE` with their section, and gate 3 proves the dataloader cannot reach them. A column matching nothing is a violation: an unclassified column is an unaudited column.


### `A1_ecg_diagnosis` — 18 columns

Allowed inputs: `raw_lead2`, `raw_12lead`, `preprocessed_lead2`, `preprocessed_12lead`, `image_clean_lead2`, `image_clean_12lead`, `image_scanlike_lead2`, `image_scanlike_12lead`, `report_text`

Forbidden inputs: `machine_measurements`, `structured_features`

| column | dtype | role | why | verdict |
| --- | --- | --- | --- | --- |
| `boundary_flag` | bool | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `cart_id` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `ecg_time` | timestamp[ns] | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `hadm_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `icd_codes_matched` | list<element: string> | label provenance | §4.A.1.5 | PASS |
| `is_primary` | bool | cohort filter | primary-vs-sensitivity cohort flag | PASS |
| `label_acute_myocardial_infarction` | bool | label | target of head `label_acute_myocardial_infarction` | PASS |
| `label_atrial_fibrillation_flutter` | bool | label | target of head `label_atrial_fibrillation_flutter` | PASS |
| `label_conduction_disorder` | bool | label | target of head `label_conduction_disorder` | PASS |
| `label_heart_failure_narrow` | bool | label | target of head `label_heart_failure_narrow` | PASS |
| `label_source` | string | label provenance | §4.A.1.5 | PASS |
| `label_ventricular_arrhythmia_or_arrest` | bool | label | target of head `label_ventricular_arrhythmia_or_arrest` | PASS |
| `link_tier` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `n_icd_codes_on_admission` | int32 | label provenance | §4.A.1.5 | PASS |
| `split` | string | split | the global patient split, joined never re-derived (§4.C.1) | PASS |
| `sqi_tier` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `study_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `subject_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |


### `A2_measurement_blind` — 14 columns

Allowed inputs: `raw_lead2`, `raw_12lead`, `preprocessed_lead2`, `preprocessed_12lead`

Forbidden inputs: `image_clean_lead2`, `image_clean_12lead`, `image_scanlike_lead2`, `image_scanlike_12lead`, `report_text`, `machine_measurements`, `structured_features`

| column | dtype | role | why | verdict |
| --- | --- | --- | --- | --- |
| `cart_id` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `hr_bpm` | float | label | target of head `hr_bpm` | label (target, not input) |
| `hr_label` | string | label | target of head `hr_label` | PASS |
| `is_primary` | bool | cohort filter | primary-vs-sensitivity cohort flag | PASS |
| `link_tier` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `qrs_label` | string | label | target of head `qrs_label` | PASS |
| `qrs_ms` | float | label | target of head `qrs_ms` | label (target, not input) |
| `qtc_label` | string | label | target of head `qtc_label` | PASS |
| `qtc_ms` | float | label | target of head `qtc_ms` | label (target, not input) |
| `qtc_ms_bazett` | float | declared provenance | §4 decision 14 sensitivity row | provenance |
| `split` | string | split | the global patient split, joined never re-derived (§4.C.1) | PASS |
| `sqi_tier` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `study_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `subject_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |

Declared-provenance columns naming a forbidden quantity: `hr_bpm`, `qrs_ms`, `qtc_ms`, `qtc_ms_bazett`. Gate 3 proves none reaches a model.


### `A3_lab_abnormality` — 150 columns

Allowed inputs: `raw_lead2`, `raw_12lead`, `preprocessed_lead2`, `preprocessed_12lead`, `image_clean_lead2`, `image_clean_12lead`, `image_scanlike_lead2`, `image_scanlike_12lead`, `report_text`

Forbidden inputs: `machine_measurements`, `structured_features`

| column | dtype | role | why | verdict |
| --- | --- | --- | --- | --- |
| `boundary_flag` | bool | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `cart_id` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `ecg_time` | timestamp[ns] | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `hadm_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `is_primary` | bool | cohort filter | primary-vs-sensitivity cohort flag | PASS |
| `lab_Ca_pm12h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_Ca_pm12h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_Ca_pm12h` | PASS |
| `lab_Ca_pm12h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_Ca_pm12h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_Ca_pm24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_Ca_pm24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_Ca_pm24h` | PASS |
| `lab_Ca_pm24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_Ca_pm24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_Ca_pm6h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_Ca_pm6h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_Ca_pm6h` | PASS |
| `lab_Ca_pm6h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_Ca_pm6h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_Ca_post_24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_Ca_post_24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_Ca_post_24h` | PASS |
| `lab_Ca_post_24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_Ca_post_24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_Ca_pre_24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_Ca_pre_24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_Ca_pre_24h` | PASS |
| `lab_Ca_pre_24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_Ca_pre_24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_K_pm12h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_K_pm12h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_K_pm12h` | PASS |
| `lab_K_pm12h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_K_pm12h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_K_pm24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_K_pm24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_K_pm24h` | PASS |
| `lab_K_pm24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_K_pm24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_K_pm6h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_K_pm6h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_K_pm6h` | PASS |
| `lab_K_pm6h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_K_pm6h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_K_post_24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_K_post_24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_K_post_24h` | PASS |
| `lab_K_post_24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_K_post_24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_K_pre_24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_K_pre_24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_K_pre_24h` | PASS |
| `lab_K_pre_24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_K_pre_24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_Mg_pm12h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_Mg_pm12h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_Mg_pm12h` | PASS |
| `lab_Mg_pm12h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_Mg_pm12h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_Mg_pm24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_Mg_pm24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_Mg_pm24h` | PASS |
| `lab_Mg_pm24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_Mg_pm24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_Mg_pm6h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_Mg_pm6h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_Mg_pm6h` | PASS |
| `lab_Mg_pm6h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_Mg_pm6h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_Mg_post_24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_Mg_post_24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_Mg_post_24h` | PASS |
| `lab_Mg_post_24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_Mg_post_24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_Mg_pre_24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_Mg_pre_24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_Mg_pre_24h` | PASS |
| `lab_Mg_pre_24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_Mg_pre_24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_Na_pm12h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_Na_pm12h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_Na_pm12h` | PASS |
| `lab_Na_pm12h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_Na_pm12h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_Na_pm24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_Na_pm24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_Na_pm24h` | PASS |
| `lab_Na_pm24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_Na_pm24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_Na_pm6h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_Na_pm6h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_Na_pm6h` | PASS |
| `lab_Na_pm6h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_Na_pm6h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_Na_post_24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_Na_post_24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_Na_post_24h` | PASS |
| `lab_Na_post_24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_Na_post_24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_Na_pre_24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_Na_pre_24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_Na_pre_24h` | PASS |
| `lab_Na_pre_24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_Na_pre_24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_creatinine_pm12h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_creatinine_pm12h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_creatinine_pm12h` | PASS |
| `lab_creatinine_pm12h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_creatinine_pm12h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_creatinine_pm24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_creatinine_pm24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_creatinine_pm24h` | PASS |
| `lab_creatinine_pm24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_creatinine_pm24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_creatinine_pm6h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_creatinine_pm6h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_creatinine_pm6h` | PASS |
| `lab_creatinine_pm6h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_creatinine_pm6h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_creatinine_post_24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_creatinine_post_24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_creatinine_post_24h` | PASS |
| `lab_creatinine_post_24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_creatinine_post_24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_creatinine_pre_24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_creatinine_pre_24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_creatinine_pre_24h` | PASS |
| `lab_creatinine_pre_24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_creatinine_pre_24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_lactate_pm12h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_lactate_pm12h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_lactate_pm12h` | PASS |
| `lab_lactate_pm12h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_lactate_pm12h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_lactate_pm24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_lactate_pm24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_lactate_pm24h` | PASS |
| `lab_lactate_pm24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_lactate_pm24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_lactate_pm6h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_lactate_pm6h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_lactate_pm6h` | PASS |
| `lab_lactate_pm6h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_lactate_pm6h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_lactate_post_24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_lactate_post_24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_lactate_post_24h` | PASS |
| `lab_lactate_post_24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_lactate_post_24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_lactate_pre_24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_lactate_pre_24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_lactate_pre_24h` | PASS |
| `lab_lactate_pre_24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_lactate_pre_24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_troponin_pm12h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_troponin_pm12h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_troponin_pm12h` | PASS |
| `lab_troponin_pm12h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_troponin_pm12h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_troponin_pm24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_troponin_pm24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_troponin_pm24h` | PASS |
| `lab_troponin_pm24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_troponin_pm24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_troponin_pm6h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_troponin_pm6h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_troponin_pm6h` | PASS |
| `lab_troponin_pm6h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_troponin_pm6h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_troponin_post_24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_troponin_post_24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_troponin_post_24h` | PASS |
| `lab_troponin_post_24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_troponin_post_24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `lab_troponin_pre_24h_abnormal_method` | dictionary<values=string, indices=int32, ordered=0> | label provenance | §4.A.3.5 | PASS |
| `lab_troponin_pre_24h_label` | dictionary<values=string, indices=int32, ordered=0> | label | target of head `lab_troponin_pre_24h` | PASS |
| `lab_troponin_pre_24h_label_same_hadm` | dictionary<values=string, indices=int32, ordered=0> | sensitivity filter | §4.A.3.8 | PASS |
| `lab_troponin_pre_24h_signed_hours_from_ecg` | float | label provenance | §4.A.3.5 | PASS |
| `link_tier` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `split` | string | split | the global patient split, joined never re-derived (§4.C.1) | PASS |
| `sqi_tier` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `study_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `subject_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |


### `A4_event_localization` — 14 columns

Allowed inputs: `raw_lead2`, `raw_12lead`, `preprocessed_lead2`, `preprocessed_12lead`

Forbidden inputs: `machine_measurements`, `structured_features`, `report_text`, `image_clean_lead2`, `image_clean_12lead`, `image_scanlike_lead2`, `image_scanlike_12lead`

| column | dtype | role | why | verdict |
| --- | --- | --- | --- | --- |
| `cart_id` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `delineate_ok` | bool | provenance | declared in `task_spec.extra_columns` | PASS |
| `fallback_used` | bool | provenance | declared in `task_spec.extra_columns` | PASS |
| `is_primary` | bool | cohort filter | primary-vs-sensitivity cohort flag | PASS |
| `link_tier` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `n_peaks` | int32 | provenance | declared in `task_spec.extra_columns` | PASS |
| `n_qrs_spans` | int32 | label provenance | §4.A.4.3 | PASS |
| `qrs_offsets_lead2` | list<element: int32> | provenance | declared in `task_spec.extra_columns` | PASS |
| `qrs_onsets_lead2` | list<element: int32> | provenance | declared in `task_spec.extra_columns` | PASS |
| `r_peaks_lead2` | list<element: int32> | label | target of head `fiducials` | PASS |
| `split` | string | split | the global patient split, joined never re-derived (§4.C.1) | PASS |
| `sqi_tier` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `study_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `subject_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |


### `A5_cross_modal_verification` — 18 columns

Allowed inputs: `raw_lead2`, `raw_12lead`, `preprocessed_lead2`, `preprocessed_12lead`, `image_clean_lead2`, `image_clean_12lead`, `image_scanlike_lead2`, `image_scanlike_12lead`, `report_text`, `report_text_masked`

Forbidden inputs: `machine_measurements`, `structured_features`

| column | dtype | role | why | verdict |
| --- | --- | --- | --- | --- |
| `anchor_study_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `hr_label` | string | label | target of head `hr_label` | PASS |
| `image_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `image_type` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `masked_families` | string | masking provenance | §4 decision 16 | PASS |
| `masked_positions` | list<element: int32> | masking provenance | §4.A.5.3 | PASS |
| `n_masked_spans` | int32 | masking provenance | §4.A.5.3 | PASS |
| `neg_type` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `qrs_label` | string | label | target of head `qrs_label` | PASS |
| `qtc_label` | string | label | target of head `qtc_label` | PASS |
| `report_text_masked` | string | model text input (masked) | §4.A.5.4 allowed input | PASS |
| `signal_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `split` | string | split | the global patient split, joined never re-derived (§4.C.1) | PASS |
| `study_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `subject_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `text_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `text_override` | string | provenance | declared in `task_spec.extra_columns` | PASS |
| `y_match` | int8 | label | target of head `y_match` | PASS |


### `A6_risk_stratification` — 36 columns

Allowed inputs: `raw_lead2`, `raw_12lead`, `preprocessed_lead2`, `preprocessed_12lead`, `image_clean_lead2`, `image_clean_12lead`, `image_scanlike_lead2`, `image_scanlike_12lead`, `report_text`

Forbidden inputs: `machine_measurements`, `structured_features`

| column | dtype | role | why | verdict |
| --- | --- | --- | --- | --- |
| `admission_type` | string | baseline covariate | Plan A/B §5.8 utilization tier | PASS |
| `age_at_ecg` | float | baseline covariate | Plan A/B §5.8 demographics tier | PASS |
| `boundary_flag` | bool | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `cart_id` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `days_since_last_discharge` | float | baseline covariate | Plan A/B §5.8 utilization tier | PASS |
| `days_to_death` | float | label provenance | §4.A.6.5 | PASS |
| `days_to_readmission` | float | label provenance | §4.A.6.5 | PASS |
| `ecg_time` | timestamp[ns] | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `ed_disposition` | string | baseline covariate | Plan A/B §5.8 utilization tier | PASS |
| `followup_days_after_discharge` | float | provenance | declared in `task_spec.extra_columns` | PASS |
| `hadm_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `insurance` | string | baseline covariate | Plan A/B §5.8 demographics tier | PASS |
| `is_primary` | bool | cohort filter | primary-vs-sensitivity cohort flag | PASS |
| `link_tier` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `mortality_30d` | bool | label | target of head `mortality_30d` | PASS |
| `mortality_90d` | bool | label | target of head `mortality_90d` | PASS |
| `mortality_observable` | bool | mask | gates a head's loss; carries no signal about the label | PASS |
| `n_prior_admissions` | int32 | baseline covariate | Plan A/B §5.8 utilization tier | PASS |
| `n_prior_ecgs` | int32 | baseline covariate | Plan A/B §5.8 utilization tier | PASS |
| `next_admission_location` | string | label provenance | §4.A.6.5 | PASS |
| `next_admission_type` | string | label provenance | §4.A.6.5 | PASS |
| `prior_dx_acute_myocardial_infarction` | bool | baseline covariate | Plan A/B §5.8 comorbidity tier — prior ICD before the ECG, using the locked A1 group map | PASS |
| `prior_dx_atrial_fibrillation_flutter` | bool | baseline covariate | Plan A/B §5.8 comorbidity tier — prior ICD before the ECG, using the locked A1 group map | PASS |
| `prior_dx_conduction_disorder` | bool | baseline covariate | Plan A/B §5.8 comorbidity tier — prior ICD before the ECG, using the locked A1 group map | PASS |
| `prior_dx_heart_failure_narrow` | bool | baseline covariate | Plan A/B §5.8 comorbidity tier — prior ICD before the ECG, using the locked A1 group map | PASS |
| `prior_dx_ventricular_arrhythmia_or_arrest` | bool | baseline covariate | Plan A/B §5.8 comorbidity tier — prior ICD before the ECG, using the locked A1 group map | PASS |
| `race` | string | baseline covariate | Plan A/B §5.8 demographics tier | PASS |
| `readmission_30d` | bool | label | target of head `readmission_30d` | PASS |
| `readmission_90d` | bool | label | target of head `readmission_90d` | PASS |
| `readmission_eligible` | bool | mask | gates a head's loss; carries no signal about the label | PASS |
| `readmission_eligible_90d` | bool | mask | gates a head's loss; carries no signal about the label | PASS |
| `sex_male` | bool | baseline covariate | Plan A/B §5.8 demographics tier | PASS |
| `split` | string | split | the global patient split, joined never re-derived (§4.C.1) | PASS |
| `sqi_tier` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `study_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `subject_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |


### `B1_measurement_blind` — 14 columns

Allowed inputs: `raw_lead2`, `raw_12lead`, `preprocessed_lead2`, `preprocessed_12lead`

Forbidden inputs: `image_clean_lead2`, `image_clean_12lead`, `image_scanlike_lead2`, `image_scanlike_12lead`, `report_text`, `machine_measurements`, `structured_features`

| column | dtype | role | why | verdict |
| --- | --- | --- | --- | --- |
| `cart_id` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `hr_bpm` | float | label | target of head `hr_bpm` | label (target, not input) |
| `hr_label` | string | label | target of head `hr_label` | PASS |
| `is_primary` | bool | cohort filter | primary-vs-sensitivity cohort flag | PASS |
| `link_tier` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `qrs_label` | string | label | target of head `qrs_label` | PASS |
| `qrs_ms` | float | label | target of head `qrs_ms` | label (target, not input) |
| `qtc_label` | string | label | target of head `qtc_label` | PASS |
| `qtc_ms` | float | label | target of head `qtc_ms` | label (target, not input) |
| `qtc_ms_bazett` | float | declared provenance | §4 decision 14 sensitivity row | provenance |
| `split` | string | split | the global patient split, joined never re-derived (§4.C.1) | PASS |
| `sqi_tier` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `study_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `subject_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |

Declared-provenance columns naming a forbidden quantity: `hr_bpm`, `qrs_ms`, `qtc_ms`, `qtc_ms_bazett`. Gate 3 proves none reaches a model.


### `B2_noise_robustness` — 14 columns

Allowed inputs: `raw_lead2`, `preprocessed_lead2`, `signal_corrupted`

Forbidden inputs: `raw_12lead`, `preprocessed_12lead`, `image_clean_lead2`, `image_clean_12lead`, `image_scanlike_lead2`, `image_scanlike_12lead`, `report_text`, `machine_measurements`, `structured_features`

| column | dtype | role | why | verdict |
| --- | --- | --- | --- | --- |
| `clean_signal_kind` | string | provenance | declared in `task_spec.extra_columns` | PASS |
| `corrupted_signal_kind` | string | provenance | declared in `task_spec.extra_columns` | PASS |
| `corruption_type` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `hr_label` | string | label | target of head `hr_label` | PASS |
| `is_anchor` | bool | provenance | declared in `task_spec.extra_columns` | PASS |
| `qrs_label` | string | label | target of head `qrs_label` | PASS |
| `qtc_label` | string | label | target of head `qtc_label` | PASS |
| `regime` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `row_role` | string | provenance | declared in `task_spec.extra_columns` | PASS |
| `snr_db` | int32 | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `split` | string | split | the global patient split, joined never re-derived (§4.C.1) | PASS |
| `sqi_tier` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `study_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `subject_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |


### `B3_temporal_grounding` — 10 columns

Allowed inputs: `raw_lead2`, `raw_12lead`, `preprocessed_lead2`, `preprocessed_12lead`

Forbidden inputs: `machine_measurements`, `structured_features`, `report_text`, `image_clean_lead2`, `image_clean_12lead`, `image_scanlike_lead2`, `image_scanlike_12lead`

| column | dtype | role | why | verdict |
| --- | --- | --- | --- | --- |
| `cart_id` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `fallback_used` | bool | provenance | declared in `task_spec.extra_columns` | PASS |
| `labels` | list<element: int8> | label | target of head `bins` | PASS |
| `link_tier` | string | cohort provenance | §4.B.3.5 | PASS |
| `n_positive_bins` | int8 | provenance | declared in `task_spec.extra_columns` | PASS |
| `query` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `split` | string | split | the global patient split, joined never re-derived (§4.C.1) | PASS |
| `sqi_tier` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `study_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `subject_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |


### `B4_cross_modal_verification` — 10 columns

Allowed inputs: `raw_lead2`, `raw_12lead`, `preprocessed_lead2`, `preprocessed_12lead`, `image_clean_lead2`, `image_clean_12lead`, `image_scanlike_lead2`, `image_scanlike_12lead`, `report_text`

Forbidden inputs: `machine_measurements`, `structured_features`

| column | dtype | role | why | verdict |
| --- | --- | --- | --- | --- |
| `anchor_study_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `image_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `image_type` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `neg_type` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `signal_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `split` | string | split | the global patient split, joined never re-derived (§4.C.1) | PASS |
| `subject_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `text_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `text_override` | string | provenance | declared in `task_spec.extra_columns` | PASS |
| `y_match` | int8 | label | target of head `y_match` | PASS |


### `B5_contradiction_detection` — 17 columns

Allowed inputs: `raw_lead2`, `raw_12lead`, `preprocessed_lead2`, `preprocessed_12lead`, `report_text`

Forbidden inputs: `machine_measurements`, `structured_features`, `image_clean_lead2`, `image_clean_12lead`, `image_scanlike_lead2`, `image_scanlike_12lead`

| column | dtype | role | why | verdict |
| --- | --- | --- | --- | --- |
| `cart_id` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `contradiction_family` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `contradiction_type` | string | provenance | declared in `task_spec.extra_columns` | PASS |
| `corrupted_report_text` | string | declared provenance | §4.B.5.5; gate 4 resolves one | PASS |
| `corrupted_span_end` | int32 | provenance | declared in `task_spec.extra_columns` | PASS |
| `corrupted_span_start` | int32 | label | target of head `span` | PASS |
| `eligible_families` | string | cohort provenance | §4 decision 11 eligibility pool | PASS |
| `is_corrupted` | bool | label | target of head `is_corrupted` | PASS |
| `is_primary` | bool | cohort filter | primary-vs-sensitivity cohort flag | PASS |
| `label` | string | label | target of head `label` | PASS |
| `link_tier` | string | cohort provenance | §4.B.5.5 | PASS |
| `original_report_text` | string | declared provenance | §4.B.5.5; gate 4 resolves one | PASS |
| `source_measurement` | string | declared provenance | §4.B.5.5 `# JSON of ... injection` | PASS |
| `split` | string | split | the global patient split, joined never re-derived (§4.C.1) | PASS |
| `sqi_tier` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `study_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `subject_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |


### `B6_difficulty_stratified` — 5 columns

Allowed inputs: `raw_lead2`, `raw_12lead`, `preprocessed_lead2`, `preprocessed_12lead`, `image_clean_lead2`, `image_clean_12lead`, `image_scanlike_lead2`, `image_scanlike_12lead`, `report_text`

Forbidden inputs: `machine_measurements`, `structured_features`

| column | dtype | role | why | verdict |
| --- | --- | --- | --- | --- |
| `difficulty_tier` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `neg_type` | string | subgroup | reported-on stratum (§4.X.8); reaches the prediction file, not the model | PASS |
| `split` | string | split | the global patient split, joined never re-derived (§4.C.1) | PASS |
| `study_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |
| `subject_id` | int64 | identity | row / modality lookup key (§4.C invariant 3) | PASS |


## Gate 2 — every generated model config resolves to allowed inputs

`config/model_configs/` is generated from `task_input_policy.yaml`, so this gate is checking that the generator and the policy have not drifted apart. Each config is resolved to the modality kinds it would actually load and pushed through the same `check_input_policy` a training run calls.

| config | task | arch tier | modality kinds resolved | policy |
| --- | --- | --- | --- | --- |
| `A1_image_resnet50_12lead_clean.yaml` | `A1_ecg_diagnosis` | image_resnet50_12lead_clean | `image_clean_12lead` | PASS |
| `A1_image_resnet50_12lead_scanlike.yaml` | `A1_ecg_diagnosis` | image_resnet50_12lead_scanlike | `image_scanlike_12lead` | PASS |
| `A1_image_resnet50_lead2_clean.yaml` | `A1_ecg_diagnosis` | image_resnet50_lead2_clean | `image_clean_lead2` | PASS |
| `A1_image_resnet50_lead2_scanlike.yaml` | `A1_ecg_diagnosis` | image_resnet50_lead2_scanlike | `image_scanlike_lead2` | PASS |
| `A1_multimodal_fusion_12lead.yaml` | `A1_ecg_diagnosis` | multimodal_fusion_12lead | `preprocessed_12lead`, `image_clean_12lead`, `report_text` | PASS |
| `A1_multimodal_fusion_lead2.yaml` | `A1_ecg_diagnosis` | multimodal_fusion_lead2 | `preprocessed_lead2`, `image_clean_lead2`, `report_text` | PASS |
| `A1_multimodal_fusion_notext_12lead.yaml` | `A1_ecg_diagnosis` | multimodal_fusion_notext_12lead | `preprocessed_12lead`, `image_clean_12lead` | PASS |
| `A1_multimodal_fusion_notext_lead2.yaml` | `A1_ecg_diagnosis` | multimodal_fusion_notext_lead2 | `preprocessed_lead2`, `image_clean_lead2` | PASS |
| `A1_signal_resnet18_12lead_preprocessed.yaml` | `A1_ecg_diagnosis` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | PASS |
| `A1_signal_resnet18_12lead_raw.yaml` | `A1_ecg_diagnosis` | signal_resnet18_12lead_raw | `raw_12lead` | PASS |
| `A1_signal_resnet18_lead2_preprocessed.yaml` | `A1_ecg_diagnosis` | signal_resnet18_lead2_preprocessed | `preprocessed_lead2` | PASS |
| `A1_signal_resnet18_lead2_raw.yaml` | `A1_ecg_diagnosis` | signal_resnet18_lead2_raw | `raw_lead2` | PASS |
| `A1_text_bioclinicalbert.yaml` | `A1_ecg_diagnosis` | text_bioclinicalbert | `report_text` | PASS |
| `A1_text_tfidf.yaml` | `A1_ecg_diagnosis` | text_tfidf | `report_text` | PASS |
| `A2_signal_resnet18_12lead_preprocessed.yaml` | `A2_measurement_blind` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | PASS |
| `A2_signal_resnet18_12lead_raw.yaml` | `A2_measurement_blind` | signal_resnet18_12lead_raw | `raw_12lead` | PASS |
| `A2_signal_resnet18_lead2_preprocessed.yaml` | `A2_measurement_blind` | signal_resnet18_lead2_preprocessed | `preprocessed_lead2` | PASS |
| `A2_signal_resnet18_lead2_raw.yaml` | `A2_measurement_blind` | signal_resnet18_lead2_raw | `raw_lead2` | PASS |
| `A3_image_resnet50_12lead_clean.yaml` | `A3_lab_abnormality` | image_resnet50_12lead_clean | `image_clean_12lead` | PASS |
| `A3_image_resnet50_12lead_scanlike.yaml` | `A3_lab_abnormality` | image_resnet50_12lead_scanlike | `image_scanlike_12lead` | PASS |
| `A3_image_resnet50_lead2_clean.yaml` | `A3_lab_abnormality` | image_resnet50_lead2_clean | `image_clean_lead2` | PASS |
| `A3_image_resnet50_lead2_scanlike.yaml` | `A3_lab_abnormality` | image_resnet50_lead2_scanlike | `image_scanlike_lead2` | PASS |
| `A3_multimodal_fusion_12lead.yaml` | `A3_lab_abnormality` | multimodal_fusion_12lead | `preprocessed_12lead`, `image_clean_12lead`, `report_text` | PASS |
| `A3_multimodal_fusion_lead2.yaml` | `A3_lab_abnormality` | multimodal_fusion_lead2 | `preprocessed_lead2`, `image_clean_lead2`, `report_text` | PASS |
| `A3_multimodal_fusion_notext_12lead.yaml` | `A3_lab_abnormality` | multimodal_fusion_notext_12lead | `preprocessed_12lead`, `image_clean_12lead` | PASS |
| `A3_multimodal_fusion_notext_lead2.yaml` | `A3_lab_abnormality` | multimodal_fusion_notext_lead2 | `preprocessed_lead2`, `image_clean_lead2` | PASS |
| `A3_signal_resnet18_12lead_preprocessed.yaml` | `A3_lab_abnormality` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | PASS |
| `A3_signal_resnet18_12lead_raw.yaml` | `A3_lab_abnormality` | signal_resnet18_12lead_raw | `raw_12lead` | PASS |
| `A3_signal_resnet18_lead2_preprocessed.yaml` | `A3_lab_abnormality` | signal_resnet18_lead2_preprocessed | `preprocessed_lead2` | PASS |
| `A3_signal_resnet18_lead2_raw.yaml` | `A3_lab_abnormality` | signal_resnet18_lead2_raw | `raw_lead2` | PASS |
| `A3_text_bioclinicalbert.yaml` | `A3_lab_abnormality` | text_bioclinicalbert | `report_text` | PASS |
| `A3_text_tfidf.yaml` | `A3_lab_abnormality` | text_tfidf | `report_text` | PASS |
| `A4_signal_resnet18_12lead_preprocessed.yaml` | `A4_event_localization` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | PASS |
| `A4_signal_resnet18_12lead_raw.yaml` | `A4_event_localization` | signal_resnet18_12lead_raw | `raw_12lead` | PASS |
| `A4_signal_resnet18_lead2_preprocessed.yaml` | `A4_event_localization` | signal_resnet18_lead2_preprocessed | `preprocessed_lead2` | PASS |
| `A4_signal_resnet18_lead2_raw.yaml` | `A4_event_localization` | signal_resnet18_lead2_raw | `raw_lead2` | PASS |
| `A5_embedding_cosine_12lead.yaml` | `A5_cross_modal_verification` | embedding_cosine_12lead | `preprocessed_12lead`, `image_clean_12lead`, `report_text` | PASS |
| `A5_embedding_cosine_lead2.yaml` | `A5_cross_modal_verification` | embedding_cosine_lead2 | `preprocessed_lead2`, `image_clean_lead2`, `report_text` | PASS |
| `A5_image_resnet50_12lead_clean.yaml` | `A5_cross_modal_verification` | image_resnet50_12lead_clean | `image_clean_12lead` | PASS |
| `A5_image_resnet50_12lead_scanlike.yaml` | `A5_cross_modal_verification` | image_resnet50_12lead_scanlike | `image_scanlike_12lead` | PASS |
| `A5_image_resnet50_lead2_clean.yaml` | `A5_cross_modal_verification` | image_resnet50_lead2_clean | `image_clean_lead2` | PASS |
| `A5_image_resnet50_lead2_scanlike.yaml` | `A5_cross_modal_verification` | image_resnet50_lead2_scanlike | `image_scanlike_lead2` | PASS |
| `A5_multimodal_fusion_12lead.yaml` | `A5_cross_modal_verification` | multimodal_fusion_12lead | `preprocessed_12lead`, `image_clean_12lead`, `report_text` | PASS |
| `A5_multimodal_fusion_lead2.yaml` | `A5_cross_modal_verification` | multimodal_fusion_lead2 | `preprocessed_lead2`, `image_clean_lead2`, `report_text` | PASS |
| `A5_multimodal_fusion_notext_12lead.yaml` | `A5_cross_modal_verification` | multimodal_fusion_notext_12lead | `preprocessed_12lead`, `image_clean_12lead` | PASS |
| `A5_multimodal_fusion_notext_lead2.yaml` | `A5_cross_modal_verification` | multimodal_fusion_notext_lead2 | `preprocessed_lead2`, `image_clean_lead2` | PASS |
| `A5_signal_resnet18_12lead_preprocessed.yaml` | `A5_cross_modal_verification` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | PASS |
| `A5_signal_resnet18_12lead_raw.yaml` | `A5_cross_modal_verification` | signal_resnet18_12lead_raw | `raw_12lead` | PASS |
| `A5_signal_resnet18_lead2_preprocessed.yaml` | `A5_cross_modal_verification` | signal_resnet18_lead2_preprocessed | `preprocessed_lead2` | PASS |
| `A5_signal_resnet18_lead2_raw.yaml` | `A5_cross_modal_verification` | signal_resnet18_lead2_raw | `raw_lead2` | PASS |
| `A5_text_bioclinicalbert.yaml` | `A5_cross_modal_verification` | text_bioclinicalbert | `report_text` | PASS |
| `A5_text_tfidf.yaml` | `A5_cross_modal_verification` | text_tfidf | `report_text` | PASS |
| `A6_image_resnet50_12lead_clean.yaml` | `A6_risk_stratification` | image_resnet50_12lead_clean | `image_clean_12lead` | PASS |
| `A6_image_resnet50_12lead_scanlike.yaml` | `A6_risk_stratification` | image_resnet50_12lead_scanlike | `image_scanlike_12lead` | PASS |
| `A6_image_resnet50_lead2_clean.yaml` | `A6_risk_stratification` | image_resnet50_lead2_clean | `image_clean_lead2` | PASS |
| `A6_image_resnet50_lead2_scanlike.yaml` | `A6_risk_stratification` | image_resnet50_lead2_scanlike | `image_scanlike_lead2` | PASS |
| `A6_multimodal_fusion_12lead.yaml` | `A6_risk_stratification` | multimodal_fusion_12lead | `preprocessed_12lead`, `image_clean_12lead`, `report_text` | PASS |
| `A6_multimodal_fusion_lead2.yaml` | `A6_risk_stratification` | multimodal_fusion_lead2 | `preprocessed_lead2`, `image_clean_lead2`, `report_text` | PASS |
| `A6_multimodal_fusion_notext_12lead.yaml` | `A6_risk_stratification` | multimodal_fusion_notext_12lead | `preprocessed_12lead`, `image_clean_12lead` | PASS |
| `A6_multimodal_fusion_notext_lead2.yaml` | `A6_risk_stratification` | multimodal_fusion_notext_lead2 | `preprocessed_lead2`, `image_clean_lead2` | PASS |
| `A6_signal_resnet18_12lead_preprocessed.yaml` | `A6_risk_stratification` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | PASS |
| `A6_signal_resnet18_12lead_raw.yaml` | `A6_risk_stratification` | signal_resnet18_12lead_raw | `raw_12lead` | PASS |
| `A6_signal_resnet18_lead2_preprocessed.yaml` | `A6_risk_stratification` | signal_resnet18_lead2_preprocessed | `preprocessed_lead2` | PASS |
| `A6_signal_resnet18_lead2_raw.yaml` | `A6_risk_stratification` | signal_resnet18_lead2_raw | `raw_lead2` | PASS |
| `A6_text_bioclinicalbert.yaml` | `A6_risk_stratification` | text_bioclinicalbert | `report_text` | PASS |
| `A6_text_tfidf.yaml` | `A6_risk_stratification` | text_tfidf | `report_text` | PASS |
| `B1_signal_resnet18_12lead_preprocessed.yaml` | `B1_measurement_blind` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | PASS |
| `B1_signal_resnet18_12lead_raw.yaml` | `B1_measurement_blind` | signal_resnet18_12lead_raw | `raw_12lead` | PASS |
| `B1_signal_resnet18_lead2_preprocessed.yaml` | `B1_measurement_blind` | signal_resnet18_lead2_preprocessed | `preprocessed_lead2` | PASS |
| `B1_signal_resnet18_lead2_raw.yaml` | `B1_measurement_blind` | signal_resnet18_lead2_raw | `raw_lead2` | PASS |
| `B2_signal_resnet18_lead2_preprocessed.yaml` | `B2_noise_robustness` | signal_resnet18_lead2_preprocessed | `preprocessed_lead2` | PASS |
| `B2_signal_resnet18_lead2_preprocessed_regime_1.yaml` | `B2_noise_robustness` | signal_resnet18_lead2_preprocessed_regime_1 | `preprocessed_lead2` | PASS |
| `B2_signal_resnet18_lead2_preprocessed_regime_2.yaml` | `B2_noise_robustness` | signal_resnet18_lead2_preprocessed_regime_2 | `preprocessed_lead2` | PASS |
| `B2_signal_resnet18_lead2_raw.yaml` | `B2_noise_robustness` | signal_resnet18_lead2_raw | `raw_lead2` | PASS |
| `B2_signal_resnet18_lead2_raw_regime_1.yaml` | `B2_noise_robustness` | signal_resnet18_lead2_raw_regime_1 | `raw_lead2` | PASS |
| `B2_signal_resnet18_lead2_raw_regime_2.yaml` | `B2_noise_robustness` | signal_resnet18_lead2_raw_regime_2 | `raw_lead2` | PASS |
| `B3_signal_resnet18_12lead_preprocessed.yaml` | `B3_temporal_grounding` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | PASS |
| `B3_signal_resnet18_12lead_raw.yaml` | `B3_temporal_grounding` | signal_resnet18_12lead_raw | `raw_12lead` | PASS |
| `B3_signal_resnet18_lead2_preprocessed.yaml` | `B3_temporal_grounding` | signal_resnet18_lead2_preprocessed | `preprocessed_lead2` | PASS |
| `B3_signal_resnet18_lead2_raw.yaml` | `B3_temporal_grounding` | signal_resnet18_lead2_raw | `raw_lead2` | PASS |
| `B4_embedding_cosine_12lead.yaml` | `B4_cross_modal_verification` | embedding_cosine_12lead | `preprocessed_12lead`, `image_clean_12lead`, `report_text` | PASS |
| `B4_embedding_cosine_lead2.yaml` | `B4_cross_modal_verification` | embedding_cosine_lead2 | `preprocessed_lead2`, `image_clean_lead2`, `report_text` | PASS |
| `B4_image_resnet50_12lead_clean.yaml` | `B4_cross_modal_verification` | image_resnet50_12lead_clean | `image_clean_12lead` | PASS |
| `B4_image_resnet50_12lead_scanlike.yaml` | `B4_cross_modal_verification` | image_resnet50_12lead_scanlike | `image_scanlike_12lead` | PASS |
| `B4_image_resnet50_lead2_clean.yaml` | `B4_cross_modal_verification` | image_resnet50_lead2_clean | `image_clean_lead2` | PASS |
| `B4_image_resnet50_lead2_scanlike.yaml` | `B4_cross_modal_verification` | image_resnet50_lead2_scanlike | `image_scanlike_lead2` | PASS |
| `B4_multimodal_fusion_12lead.yaml` | `B4_cross_modal_verification` | multimodal_fusion_12lead | `preprocessed_12lead`, `image_clean_12lead`, `report_text` | PASS |
| `B4_multimodal_fusion_lead2.yaml` | `B4_cross_modal_verification` | multimodal_fusion_lead2 | `preprocessed_lead2`, `image_clean_lead2`, `report_text` | PASS |
| `B4_multimodal_fusion_notext_12lead.yaml` | `B4_cross_modal_verification` | multimodal_fusion_notext_12lead | `preprocessed_12lead`, `image_clean_12lead` | PASS |
| `B4_multimodal_fusion_notext_lead2.yaml` | `B4_cross_modal_verification` | multimodal_fusion_notext_lead2 | `preprocessed_lead2`, `image_clean_lead2` | PASS |
| `B4_signal_resnet18_12lead_preprocessed.yaml` | `B4_cross_modal_verification` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | PASS |
| `B4_signal_resnet18_12lead_raw.yaml` | `B4_cross_modal_verification` | signal_resnet18_12lead_raw | `raw_12lead` | PASS |
| `B4_signal_resnet18_lead2_preprocessed.yaml` | `B4_cross_modal_verification` | signal_resnet18_lead2_preprocessed | `preprocessed_lead2` | PASS |
| `B4_signal_resnet18_lead2_raw.yaml` | `B4_cross_modal_verification` | signal_resnet18_lead2_raw | `raw_lead2` | PASS |
| `B4_text_bioclinicalbert.yaml` | `B4_cross_modal_verification` | text_bioclinicalbert | `report_text` | PASS |
| `B4_text_tfidf.yaml` | `B4_cross_modal_verification` | text_tfidf | `report_text` | PASS |
| `B5_multimodal_fusion_12lead.yaml` | `B5_contradiction_detection` | multimodal_fusion_12lead | `preprocessed_12lead`, `report_text` | PASS |
| `B5_multimodal_fusion_lead2.yaml` | `B5_contradiction_detection` | multimodal_fusion_lead2 | `preprocessed_lead2`, `report_text` | PASS |
| `B5_signal_resnet18_12lead_preprocessed.yaml` | `B5_contradiction_detection` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | PASS |
| `B5_signal_resnet18_12lead_raw.yaml` | `B5_contradiction_detection` | signal_resnet18_12lead_raw | `raw_12lead` | PASS |
| `B5_signal_resnet18_lead2_preprocessed.yaml` | `B5_contradiction_detection` | signal_resnet18_lead2_preprocessed | `preprocessed_lead2` | PASS |
| `B5_signal_resnet18_lead2_raw.yaml` | `B5_contradiction_detection` | signal_resnet18_lead2_raw | `raw_lead2` | PASS |
| `B5_text_bioclinicalbert.yaml` | `B5_contradiction_detection` | text_bioclinicalbert | `report_text` | PASS |
| `B5_text_tfidf.yaml` | `B5_contradiction_detection` | text_tfidf | `report_text` | PASS |


## Gate 3 — the tensor keys the dataloader hands the model

The parquet column list is not the leakage surface; `TaskDataset.__getitem__` is. One representative config per (task, arch-tier family) is constructed for real on the **test** split and one item pulled. Every key it returns must be either a locked batch key or a `y__`/`m__` target for a head this task declares. A provenance column reaching the model would have to appear here.

| task | arch tier | kinds loaded | measured | verdict |
| --- | --- | --- | --- | --- |
| `A1_ecg_diagnosis` | image_resnet50_12lead_clean | `image_clean_12lead` | 13 tensor keys, all inside the allowlist | PASS |
| `A1_ecg_diagnosis` | multimodal_fusion_12lead | `preprocessed_12lead`, `image_clean_12lead`, `report_text` | 16 tensor keys, all inside the allowlist | PASS |
| `A1_ecg_diagnosis` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | 13 tensor keys, all inside the allowlist | PASS |
| `A1_ecg_diagnosis` | text_bioclinicalbert | `report_text` | 14 tensor keys, all inside the allowlist | PASS |
| `A2_measurement_blind` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | 18 tensor keys, all inside the allowlist | PASS |
| `A3_lab_abnormality` | image_resnet50_12lead_clean | `image_clean_12lead` | 73 tensor keys, all inside the allowlist | PASS |
| `A3_lab_abnormality` | multimodal_fusion_12lead | `preprocessed_12lead`, `image_clean_12lead`, `report_text` | 76 tensor keys, all inside the allowlist | PASS |
| `A3_lab_abnormality` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | 73 tensor keys, all inside the allowlist | PASS |
| `A3_lab_abnormality` | text_bioclinicalbert | `report_text` | 74 tensor keys, all inside the allowlist | PASS |
| `A4_event_localization` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | 8 tensor keys, all inside the allowlist | PASS |
| `A5_cross_modal_verification` | embedding_cosine_12lead | `preprocessed_12lead`, `image_clean_12lead`, `report_text` | 14 tensor keys, all inside the allowlist | PASS |
| `A5_cross_modal_verification` | image_resnet50_12lead_clean | `image_clean_12lead` | 11 tensor keys, all inside the allowlist | PASS |
| `A5_cross_modal_verification` | multimodal_fusion_12lead | `preprocessed_12lead`, `image_clean_12lead`, `report_text` | 14 tensor keys, all inside the allowlist | PASS |
| `A5_cross_modal_verification` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | 11 tensor keys, all inside the allowlist | PASS |
| `A5_cross_modal_verification` | text_bioclinicalbert | `report_text` | 12 tensor keys, all inside the allowlist | PASS |
| `A6_risk_stratification` | image_resnet50_12lead_clean | `image_clean_12lead` | 11 tensor keys, all inside the allowlist | PASS |
| `A6_risk_stratification` | multimodal_fusion_12lead | `preprocessed_12lead`, `image_clean_12lead`, `report_text` | 14 tensor keys, all inside the allowlist | PASS |
| `A6_risk_stratification` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | 11 tensor keys, all inside the allowlist | PASS |
| `A6_risk_stratification` | text_bioclinicalbert | `report_text` | 12 tensor keys, all inside the allowlist | PASS |
| `B1_measurement_blind` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | 18 tensor keys, all inside the allowlist | PASS |
| `B2_noise_robustness` | signal_resnet18_lead2_preprocessed | `preprocessed_lead2` | 9 tensor keys, all inside the allowlist | PASS |
| `B3_temporal_grounding` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | 6 tensor keys, all inside the allowlist | PASS |
| `B4_cross_modal_verification` | embedding_cosine_12lead | `preprocessed_12lead`, `image_clean_12lead`, `report_text` | 8 tensor keys, all inside the allowlist | PASS |
| `B4_cross_modal_verification` | image_resnet50_12lead_clean | `image_clean_12lead` | 5 tensor keys, all inside the allowlist | PASS |
| `B4_cross_modal_verification` | multimodal_fusion_12lead | `preprocessed_12lead`, `image_clean_12lead`, `report_text` | 8 tensor keys, all inside the allowlist | PASS |
| `B4_cross_modal_verification` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | 5 tensor keys, all inside the allowlist | PASS |
| `B4_cross_modal_verification` | text_bioclinicalbert | `report_text` | 6 tensor keys, all inside the allowlist | PASS |
| `B5_contradiction_detection` | multimodal_fusion_12lead | `preprocessed_12lead`, `report_text` | 11 tensor keys, all inside the allowlist | PASS |
| `B5_contradiction_detection` | signal_resnet18_12lead_preprocessed | `preprocessed_12lead` | 9 tensor keys, all inside the allowlist | PASS |
| `B5_contradiction_detection` | text_bioclinicalbert | `report_text` | 10 tensor keys, all inside the allowlist | PASS |


## Gate 4 — B5 is fed exactly one report per row

`task_input_policy.yaml` on B5: *"the task parquet stores both columns, but a model is fed exactly ONE of them per row — feeding both would trivially reveal the label by diff. The leakage audit checks the dataloader, not just the parquet, for this task."* Measured on the whole test split.

Mean audited-report length: corrupted 129.6 chars, clean 129.6 chars — decision 9's swap-not-insert rule is why these are close, and it is why length is not a shortcut feature.


## Gate 5 — A5's masked-attribute head is independent of the text branch

Progress-doc trap 17: on an A5 **positive** row the text IS the unmasked anchor report, so a masked-attribute head reading the fused embedding would be handed the HR/QRS/QTc answer it is asked to predict. Proven rather than asserted — the same model is run twice on one batch, changing only the text vector, with the backbones in eval mode and gradients off.


## Gate 6 — no module on the model path reads a forbidden source

§11.1: *"for A2/B1/B2/B3/A4, no `rr_interval/qrs_*/t_axis/structured_features` columns appear in any feature loader or feature parquet read at train time."* Docstrings and comments are stripped first, so a module that only *names* a forbidden column while explaining why it does not read it stays clean.

`_dataset_lib/build_common.py` is deliberately not on this list: it is the **builders'** shared library and owns `machine_measurements()`, the sentinel-masking reader A2/B1/B2 need to compute their labels. What matters is that no module on the model path calls it — the token `machine_measurements(` in the scan below is that call site.

| module on the model path | forbidden source read | code lines |
| --- | --- | --- |
| `30_train.py` | none | 468 |
| `31_eval.py` | none | 1038 |
| `_dataset_lib/task_dataset.py` | none | 633 |
| `_dataset_lib/task_spec.py` | none | 416 |
| `_dataset_lib/corruption.py` | none | 123 |
| `_dataset_lib/bootstrap.py` | none | 207 |
| `_model_lib/signal_encoders.py` | none | 160 |
| `_model_lib/image_encoders.py` | none | 63 |
| `_model_lib/text_encoders.py` | none | 189 |
| `_model_lib/fusion_heads.py` | none | 114 |
| `_model_lib/task_models.py` | none | 481 |
| `_model_lib/model_configs.py` | none | 314 |
| `_train_lib/trainer.py` | none | 831 |
| `_train_lib/metrics.py` | none | 375 |
| `_train_lib/threshold.py` | none | 207 |
| `_train_lib/calibration.py` | none | 194 |
| `_train_lib/seed.py` | none | 126 |


## Every check, in the order it ran

| # | Task | Check | Verdict | Measured |
| ---: | --- | --- | --- | --- |
| 1 | `A1_ecg_diagnosis` | `parquets_present` | PASS | 3 task parquet(s): test.parquet, train.parquet, val.parquet |
| 2 | `A1_ecg_diagnosis` | `no_unclassified_columns` | PASS | every column has a declared role |
| 3 | `A1_ecg_diagnosis` | `no_forbidden_column_as_input` | PASS | no column resolves to a forbidden reference outside §4's declared provenance |
| 4 | `A2_measurement_blind` | `parquets_present` | PASS | 3 task parquet(s): test.parquet, train.parquet, val.parquet |
| 5 | `A2_measurement_blind` | `no_unclassified_columns` | PASS | every column has a declared role |
| 6 | `A2_measurement_blind` | `no_forbidden_column_as_input` | PASS | no column resolves to a forbidden reference outside §4's declared provenance |
| 7 | `A3_lab_abnormality` | `parquets_present` | PASS | 3 task parquet(s): test.parquet, train.parquet, val.parquet |
| 8 | `A3_lab_abnormality` | `no_unclassified_columns` | PASS | every column has a declared role |
| 9 | `A3_lab_abnormality` | `no_forbidden_column_as_input` | PASS | no column resolves to a forbidden reference outside §4's declared provenance |
| 10 | `A4_event_localization` | `parquets_present` | PASS | 3 task parquet(s): test.parquet, train.parquet, val.parquet |
| 11 | `A4_event_localization` | `no_unclassified_columns` | PASS | every column has a declared role |
| 12 | `A4_event_localization` | `no_forbidden_column_as_input` | PASS | no column resolves to a forbidden reference outside §4's declared provenance |
| 13 | `A5_cross_modal_verification` | `parquets_present` | PASS | 6 task parquet(s): masked_attribute_test.parquet, masked_attribute_train.parquet, masked_attribute_val.parquet, test.parquet, train.parquet, val.parquet |
| 14 | `A5_cross_modal_verification` | `no_unclassified_columns` | PASS | every column has a declared role |
| 15 | `A5_cross_modal_verification` | `no_forbidden_column_as_input` | PASS | no column resolves to a forbidden reference outside §4's declared provenance |
| 16 | `A6_risk_stratification` | `parquets_present` | PASS | 3 task parquet(s): test.parquet, train.parquet, val.parquet |
| 17 | `A6_risk_stratification` | `no_unclassified_columns` | PASS | every column has a declared role |
| 18 | `A6_risk_stratification` | `no_forbidden_column_as_input` | PASS | no column resolves to a forbidden reference outside §4's declared provenance |
| 19 | `B1_measurement_blind` | `parquets_present` | PASS | 3 task parquet(s): test.parquet, train.parquet, val.parquet |
| 20 | `B1_measurement_blind` | `no_unclassified_columns` | PASS | every column has a declared role |
| 21 | `B1_measurement_blind` | `no_forbidden_column_as_input` | PASS | no column resolves to a forbidden reference outside §4's declared provenance |
| 22 | `B2_noise_robustness` | `parquets_present` | PASS | 3 task parquet(s): test.parquet, train.parquet, val.parquet |
| 23 | `B2_noise_robustness` | `no_unclassified_columns` | PASS | every column has a declared role |
| 24 | `B2_noise_robustness` | `no_forbidden_column_as_input` | PASS | no column resolves to a forbidden reference outside §4's declared provenance |
| 25 | `B3_temporal_grounding` | `parquets_present` | PASS | 3 task parquet(s): test.parquet, train.parquet, val.parquet |
| 26 | `B3_temporal_grounding` | `no_unclassified_columns` | PASS | every column has a declared role |
| 27 | `B3_temporal_grounding` | `no_forbidden_column_as_input` | PASS | no column resolves to a forbidden reference outside §4's declared provenance |
| 28 | `B4_cross_modal_verification` | `parquets_present` | PASS | 3 task parquet(s): test.parquet, train.parquet, val.parquet |
| 29 | `B4_cross_modal_verification` | `no_unclassified_columns` | PASS | every column has a declared role |
| 30 | `B4_cross_modal_verification` | `no_forbidden_column_as_input` | PASS | no column resolves to a forbidden reference outside §4's declared provenance |
| 31 | `B5_contradiction_detection` | `parquets_present` | PASS | 3 task parquet(s): test.parquet, train.parquet, val.parquet |
| 32 | `B5_contradiction_detection` | `no_unclassified_columns` | PASS | every column has a declared role |
| 33 | `B5_contradiction_detection` | `no_forbidden_column_as_input` | PASS | no column resolves to a forbidden reference outside §4's declared provenance |
| 34 | `B6_difficulty_stratified` | `parquets_present` | PASS | 1 task parquet(s): eval_keys.parquet |
| 35 | `B6_difficulty_stratified` | `no_unclassified_columns` | PASS | every column has a declared role |
| 36 | `B6_difficulty_stratified` | `no_forbidden_column_as_input` | PASS | no column resolves to a forbidden reference outside §4's declared provenance |
| 37 | `(all tasks)` | `model_configs_present` | PASS | 104 config YAMLs under config/model_configs/ |
| 38 | `(all tasks)` | `all_model_configs_allowed` | PASS | 104 configs, every resolved modality kind is on its task's allowed list |
| 39 | `A1_ecg_diagnosis` | `config_kinds_disjoint_from_forbidden` | PASS | 14 configs name {image_clean_12lead, image_clean_lead2, image_scanlike_12lead, image_scanlike_lead2, preprocessed_12lead, preprocessed_lead2, raw_12lead, raw_lead2, report_text}; overlap with the forbidden set: none |
| 40 | `A2_measurement_blind` | `config_kinds_disjoint_from_forbidden` | PASS | 4 configs name {preprocessed_12lead, preprocessed_lead2, raw_12lead, raw_lead2}; overlap with the forbidden set: none |
| 41 | `A3_lab_abnormality` | `config_kinds_disjoint_from_forbidden` | PASS | 14 configs name {image_clean_12lead, image_clean_lead2, image_scanlike_12lead, image_scanlike_lead2, preprocessed_12lead, preprocessed_lead2, raw_12lead, raw_lead2, report_text}; overlap with the forbidden set: none |
| 42 | `A4_event_localization` | `config_kinds_disjoint_from_forbidden` | PASS | 4 configs name {preprocessed_12lead, preprocessed_lead2, raw_12lead, raw_lead2}; overlap with the forbidden set: none |
| 43 | `A5_cross_modal_verification` | `config_kinds_disjoint_from_forbidden` | PASS | 16 configs name {image_clean_12lead, image_clean_lead2, image_scanlike_12lead, image_scanlike_lead2, preprocessed_12lead, preprocessed_lead2, raw_12lead, raw_lead2, report_text}; overlap with the forbidden set: none |
| 44 | `A6_risk_stratification` | `config_kinds_disjoint_from_forbidden` | PASS | 14 configs name {image_clean_12lead, image_clean_lead2, image_scanlike_12lead, image_scanlike_lead2, preprocessed_12lead, preprocessed_lead2, raw_12lead, raw_lead2, report_text}; overlap with the forbidden set: none |
| 45 | `B1_measurement_blind` | `config_kinds_disjoint_from_forbidden` | PASS | 4 configs name {preprocessed_12lead, preprocessed_lead2, raw_12lead, raw_lead2}; overlap with the forbidden set: none |
| 46 | `B2_noise_robustness` | `config_kinds_disjoint_from_forbidden` | PASS | 6 configs name {preprocessed_lead2, raw_lead2}; overlap with the forbidden set: none |
| 47 | `B3_temporal_grounding` | `config_kinds_disjoint_from_forbidden` | PASS | 4 configs name {preprocessed_12lead, preprocessed_lead2, raw_12lead, raw_lead2}; overlap with the forbidden set: none |
| 48 | `B4_cross_modal_verification` | `config_kinds_disjoint_from_forbidden` | PASS | 16 configs name {image_clean_12lead, image_clean_lead2, image_scanlike_12lead, image_scanlike_lead2, preprocessed_12lead, preprocessed_lead2, raw_12lead, raw_lead2, report_text}; overlap with the forbidden set: none |
| 49 | `B5_contradiction_detection` | `config_kinds_disjoint_from_forbidden` | PASS | 8 configs name {preprocessed_12lead, preprocessed_lead2, raw_12lead, raw_lead2, report_text}; overlap with the forbidden set: none |
| 50 | `A1_ecg_diagnosis` | `dataloader_keys[image_resnet50_12lead_clean]` | PASS | 13 tensor keys, all inside the allowlist |
| 51 | `A1_ecg_diagnosis` | `dataloader_keys[multimodal_fusion_12lead]` | PASS | 16 tensor keys, all inside the allowlist |
| 52 | `A1_ecg_diagnosis` | `dataloader_keys[signal_resnet18_12lead_preprocessed]` | PASS | 13 tensor keys, all inside the allowlist |
| 53 | `A1_ecg_diagnosis` | `dataloader_keys[text_bioclinicalbert]` | PASS | 14 tensor keys, all inside the allowlist |
| 54 | `A2_measurement_blind` | `dataloader_keys[signal_resnet18_12lead_preprocessed]` | PASS | 18 tensor keys, all inside the allowlist |
| 55 | `A3_lab_abnormality` | `dataloader_keys[image_resnet50_12lead_clean]` | PASS | 73 tensor keys, all inside the allowlist |
| 56 | `A3_lab_abnormality` | `dataloader_keys[multimodal_fusion_12lead]` | PASS | 76 tensor keys, all inside the allowlist |
| 57 | `A3_lab_abnormality` | `dataloader_keys[signal_resnet18_12lead_preprocessed]` | PASS | 73 tensor keys, all inside the allowlist |
| 58 | `A3_lab_abnormality` | `dataloader_keys[text_bioclinicalbert]` | PASS | 74 tensor keys, all inside the allowlist |
| 59 | `A4_event_localization` | `dataloader_keys[signal_resnet18_12lead_preprocessed]` | PASS | 8 tensor keys, all inside the allowlist |
| 60 | `A5_cross_modal_verification` | `dataloader_keys[embedding_cosine_12lead]` | PASS | 14 tensor keys, all inside the allowlist |
| 61 | `A5_cross_modal_verification` | `dataloader_keys[image_resnet50_12lead_clean]` | PASS | 11 tensor keys, all inside the allowlist |
| 62 | `A5_cross_modal_verification` | `dataloader_keys[multimodal_fusion_12lead]` | PASS | 14 tensor keys, all inside the allowlist |
| 63 | `A5_cross_modal_verification` | `dataloader_keys[signal_resnet18_12lead_preprocessed]` | PASS | 11 tensor keys, all inside the allowlist |
| 64 | `A5_cross_modal_verification` | `dataloader_keys[text_bioclinicalbert]` | PASS | 12 tensor keys, all inside the allowlist |
| 65 | `A6_risk_stratification` | `dataloader_keys[image_resnet50_12lead_clean]` | PASS | 11 tensor keys, all inside the allowlist |
| 66 | `A6_risk_stratification` | `dataloader_keys[multimodal_fusion_12lead]` | PASS | 14 tensor keys, all inside the allowlist |
| 67 | `A6_risk_stratification` | `dataloader_keys[signal_resnet18_12lead_preprocessed]` | PASS | 11 tensor keys, all inside the allowlist |
| 68 | `A6_risk_stratification` | `dataloader_keys[text_bioclinicalbert]` | PASS | 12 tensor keys, all inside the allowlist |
| 69 | `B1_measurement_blind` | `dataloader_keys[signal_resnet18_12lead_preprocessed]` | PASS | 18 tensor keys, all inside the allowlist |
| 70 | `B2_noise_robustness` | `dataloader_keys[signal_resnet18_lead2_preprocessed]` | PASS | 9 tensor keys, all inside the allowlist |
| 71 | `B3_temporal_grounding` | `dataloader_keys[signal_resnet18_12lead_preprocessed]` | PASS | 6 tensor keys, all inside the allowlist |
| 72 | `B4_cross_modal_verification` | `dataloader_keys[embedding_cosine_12lead]` | PASS | 8 tensor keys, all inside the allowlist |
| 73 | `B4_cross_modal_verification` | `dataloader_keys[image_resnet50_12lead_clean]` | PASS | 5 tensor keys, all inside the allowlist |
| 74 | `B4_cross_modal_verification` | `dataloader_keys[multimodal_fusion_12lead]` | PASS | 8 tensor keys, all inside the allowlist |
| 75 | `B4_cross_modal_verification` | `dataloader_keys[signal_resnet18_12lead_preprocessed]` | PASS | 5 tensor keys, all inside the allowlist |
| 76 | `B4_cross_modal_verification` | `dataloader_keys[text_bioclinicalbert]` | PASS | 6 tensor keys, all inside the allowlist |
| 77 | `B5_contradiction_detection` | `dataloader_keys[multimodal_fusion_12lead]` | PASS | 11 tensor keys, all inside the allowlist |
| 78 | `B5_contradiction_detection` | `dataloader_keys[signal_resnet18_12lead_preprocessed]` | PASS | 9 tensor keys, all inside the allowlist |
| 79 | `B5_contradiction_detection` | `dataloader_keys[text_bioclinicalbert]` | PASS | 10 tensor keys, all inside the allowlist |
| 80 | `B6_difficulty_stratified` | `dataloader_keys` | PASS | evaluation-only task (§4.B.6): it slices `B4_cross_modal_verification` predictions and constructs no loader |
| 81 | `B5_contradiction_detection` | `b5_source_texts_dropped` | PASS | the resolver drops both source columns; the frame carries only `audited_report_text` |
| 82 | `B5_contradiction_detection` | `b5_audited_text_is_the_right_one` | PASS | 13,039 corrupted rows show `corrupted_report_text`, 12,831 clean rows show `original_report_text` |
| 83 | `B5_contradiction_detection` | `b5_one_text_column_only` | PASS | text columns after resolution: ['audited_report_text'] |
| 84 | `A5_cross_modal_verification` | `a5_masked_head_text_independent` | PASS | changing `text_vec` leaves ['hr_label', 'qrs_label', 'qtc_label'] bit-identical (expected ['hr_label', 'qrs_label', 'qtc_label']) |
| 85 | `A5_cross_modal_verification` | `a5_verification_head_does_read_text` | PASS | the verification head's logits DO move with the text — the control that proves the batch change reached the model at all |
| 86 | `A5_cross_modal_verification` | `a5_masked_head_input_dim` | PASS | masked head input width = EMBED_DIM x (signal + image) = 1024, text contributes 0 |
| 87 | `(all tasks)` | `model_path_reads_no_forbidden_source` | PASS | 17 modules scanned, none reads `structured_features.parquet` or a machine measurement |
| 88 | `(all tasks)` | `baseline_exemptions_declared` | PASS | `algorithmic_baselines.py` reads machine measurements: True; tasks declaring `baseline_only_exemptions`: ['A1_ecg_diagnosis', 'A3_lab_abnormality', 'A6_risk_stratification'] (expected ['A1_ecg_diagnosis', 'A3_lab_abnormality', 'A6_risk_stratification']) |

## Reproduce

```
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/20_audit_tasks_leakage.py
```

The audit reads only artifacts already on disk and writes only this report, so it is safe to re-run at any time.
