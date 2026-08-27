# Split audit — Phase 2 tasks (Stage P2.3)

**VERDICT: PASS** — 75 checks run, 75 passed, 0 violations.

Spec §9.4 (Stage P2.3), §4.C invariant 1. Generated 2026-08-27T12:21:20Z by `scripts/phase2_tasks_benchmark_and_paper/22_audit_tasks_split.py` from the task parquets on disk — every number below is measured, none is restated from a builder's own report.

§9.4 asks for zero subject overlap across train/val/test for every task. That is checked, and so are the four things it does not cover on its own: that each row's `split` column matches the file it is stored in; that every subject's split equals the frozen `splits_subject_level.parquet` rather than anything re-derived (§4.C invariant 1); that no study crosses a split; and — for A5 and B4, whose rows point at up to three different studies — that every pointed-at modality belongs to a subject in the row's own split, and that a swapped modality on a negative comes from a different subject than the anchor.

A task can partition its own rows perfectly and still be wrong, if it partitioned them itself. The global-agreement check is what makes the twelve tasks consistent with each other and with Phase 1.

## Verdict by task

| Task | Checks | Verdict |
| --- | ---: | --- |
| `(global)` | 1 | **PASS** |
| `A1_ecg_diagnosis` | 5 | **PASS** |
| `A2_measurement_blind` | 5 | **PASS** |
| `A3_lab_abnormality` | 5 | **PASS** |
| `A4_event_localization` | 5 | **PASS** |
| `A5_cross_modal_verification` | 12 | **PASS** |
| `A6_risk_stratification` | 5 | **PASS** |
| `B1_measurement_blind` | 5 | **PASS** |
| `B2_noise_robustness` | 6 | **PASS** |
| `B3_temporal_grounding` | 5 | **PASS** |
| `B4_cross_modal_verification` | 11 | **PASS** |
| `B5_contradiction_detection` | 5 | **PASS** |
| `B6_difficulty_stratified` | 5 | **PASS** |


## The frozen patient split this audit checks against

`data/processed/splits_subject_level.parquet`, inherited from Phase 1 and never re-split (§4.C invariant 1, progress-doc trap 4). Every task is a subset of it; no task reshuffles it.

| split | subjects |
| --- | --- |
| train | 112,947 |
| val | 16,135 |
| test | 32,270 |
| **all** | **161,352** |


## `A1_ecg_diagnosis`

| split | rows | unique `study_id` | subjects |
| --- | --- | --- | --- |
| train | 350,090 | 350,090 | 87,220 |
| val | 50,216 | 50,216 | 12,440 |
| test | 99,971 | 99,971 | 24,887 |


## `A2_measurement_blind`

| split | rows | unique `study_id` | subjects |
| --- | --- | --- | --- |
| train | 349,871 | 349,871 | 87,244 |
| val | 50,182 | 50,182 | 12,440 |
| test | 99,964 | 99,964 | 24,900 |


## `A3_lab_abnormality`

| split | rows | unique `study_id` | subjects |
| --- | --- | --- | --- |
| train | 350,203 | 350,203 | 87,255 |
| val | 50,240 | 50,240 | 12,445 |
| test | 100,028 | 100,028 | 24,902 |


## `A4_event_localization`

| split | rows | unique `study_id` | subjects |
| --- | --- | --- | --- |
| train | 523,945 | 523,945 | 107,851 |
| val | 75,525 | 75,525 | 15,397 |
| test | 149,642 | 149,642 | 30,844 |


## `A5_cross_modal_verification`

| split | rows | unique `anchor_study_id` | subjects |
| --- | --- | --- | --- |
| train | 3,667,615 | 523,945 | 107,851 |
| val | 528,675 | 75,525 | 15,397 |
| test | 1,047,494 | 149,642 | 30,844 |


**Donor containment.** Each verification row points at up to three studies; every one of them must belong to a subject in the row's own split, and a swapped modality on a negative must come from a different subject.

| pointer column | rows where it is not the anchor | unresolved | crossing a split | same-subject on a negative |
| --- | --- | --- | --- | --- |
| `signal_id` | 749,112 | 0 | 0 | 0 |
| `image_id` | 1,498,224 | 0 | 0 | 0 |
| `text_id` | 2,247,336 | 0 | 0 | 0 |

| file | rows | subjects | wrong split column | disagreeing with the global split |
| --- | --- | --- | --- | --- |
| `masked_attribute_train.parquet` | 523,464 | 107,841 | 0 | 0 |
| `masked_attribute_val.parquet` | 75,444 | 15,395 | 0 | 0 |
| `masked_attribute_test.parquet` | 149,546 | 30,843 | 0 | 0 |


## `A6_risk_stratification`

| split | rows | unique `study_id` | subjects |
| --- | --- | --- | --- |
| train | 350,203 | 350,203 | 87,255 |
| val | 50,240 | 50,240 | 12,445 |
| test | 100,028 | 100,028 | 24,902 |


## `B1_measurement_blind`

| split | rows | unique `study_id` | subjects |
| --- | --- | --- | --- |
| train | 523,464 | 523,464 | 107,841 |
| val | 75,444 | 75,444 | 15,395 |
| test | 149,546 | 149,546 | 30,843 |


## `B2_noise_robustness`

| split | rows | unique `study_id` | subjects |
| --- | --- | --- | --- |
| train | 523,464 | 523,464 | 107,841 |
| val | 75,444 | 75,444 | 15,395 |
| test | 301,097 | 149,546 | 30,843 |


## `B3_temporal_grounding`

| split | rows | unique `study_id` | subjects |
| --- | --- | --- | --- |
| train | 2,095,780 | 523,945 | 107,851 |
| val | 302,100 | 75,525 | 15,397 |
| test | 598,568 | 149,642 | 30,844 |


## `B4_cross_modal_verification`

| split | rows | unique `anchor_study_id` | subjects |
| --- | --- | --- | --- |
| train | 3,667,615 | 523,945 | 107,851 |
| val | 528,675 | 75,525 | 15,397 |
| test | 1,047,494 | 149,642 | 30,844 |


**Donor containment.** Each verification row points at up to three studies; every one of them must belong to a subject in the row's own split, and a swapped modality on a negative must come from a different subject.

| pointer column | rows where it is not the anchor | unresolved | crossing a split | same-subject on a negative |
| --- | --- | --- | --- | --- |
| `signal_id` | 749,112 | 0 | 0 | 0 |
| `image_id` | 1,498,224 | 0 | 0 | 0 |
| `text_id` | 2,247,336 | 0 | 0 | 0 |


## `B5_contradiction_detection`

| split | rows | unique `study_id` | subjects |
| --- | --- | --- | --- |
| train | 89,842 | 89,842 | 26,776 |
| val | 12,941 | 12,941 | 3,900 |
| test | 25,870 | 25,870 | 7,746 |


## `B6_difficulty_stratified`

| split | rows | unique `study_id` | subjects |
| --- | --- | --- | --- |
| train | 3,667,615 | 523,945 | 107,851 |
| val | 528,675 | 75,525 | 15,397 |
| test | 1,047,494 | 149,642 | 30,844 |


### B2 — the frozen anchor set stays in test

The 1,871 anchors were frozen in Phase 1 Stage 8 and must never be regenerated. They are a test-split sample, so a train or val row flagged `is_anchor` would mean the frozen evaluation set had reached training.


## Every check, in the order it ran

| # | Task | Check | Verdict | Measured |
| ---: | --- | --- | --- | --- |
| 1 | `(global)` | `global_split_is_a_partition` | PASS | 161,352 subjects, each in exactly one of ['test', 'train', 'val'] |
| 2 | `A1_ecg_diagnosis` | `split_column_matches_file` | PASS | rows filed under the wrong split: {'train': 0, 'val': 0, 'test': 0} |
| 3 | `A1_ecg_diagnosis` | `zero_subject_overlap` | PASS | pairwise subject intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 4 | `A1_ecg_diagnosis` | `subjects_exist_in_global_split` | PASS | 0 row(s) carry a subject absent from splits_subject_level.parquet |
| 5 | `A1_ecg_diagnosis` | `split_matches_global_split` | PASS | 0 row(s) sit in a split other than the one the frozen patient partition assigns (§4.C invariant 1) |
| 6 | `A1_ecg_diagnosis` | `zero_study_overlap` | PASS | pairwise study_id intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 7 | `A2_measurement_blind` | `split_column_matches_file` | PASS | rows filed under the wrong split: {'train': 0, 'val': 0, 'test': 0} |
| 8 | `A2_measurement_blind` | `zero_subject_overlap` | PASS | pairwise subject intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 9 | `A2_measurement_blind` | `subjects_exist_in_global_split` | PASS | 0 row(s) carry a subject absent from splits_subject_level.parquet |
| 10 | `A2_measurement_blind` | `split_matches_global_split` | PASS | 0 row(s) sit in a split other than the one the frozen patient partition assigns (§4.C invariant 1) |
| 11 | `A2_measurement_blind` | `zero_study_overlap` | PASS | pairwise study_id intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 12 | `A3_lab_abnormality` | `split_column_matches_file` | PASS | rows filed under the wrong split: {'train': 0, 'val': 0, 'test': 0} |
| 13 | `A3_lab_abnormality` | `zero_subject_overlap` | PASS | pairwise subject intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 14 | `A3_lab_abnormality` | `subjects_exist_in_global_split` | PASS | 0 row(s) carry a subject absent from splits_subject_level.parquet |
| 15 | `A3_lab_abnormality` | `split_matches_global_split` | PASS | 0 row(s) sit in a split other than the one the frozen patient partition assigns (§4.C invariant 1) |
| 16 | `A3_lab_abnormality` | `zero_study_overlap` | PASS | pairwise study_id intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 17 | `A4_event_localization` | `split_column_matches_file` | PASS | rows filed under the wrong split: {'train': 0, 'val': 0, 'test': 0} |
| 18 | `A4_event_localization` | `zero_subject_overlap` | PASS | pairwise subject intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 19 | `A4_event_localization` | `subjects_exist_in_global_split` | PASS | 0 row(s) carry a subject absent from splits_subject_level.parquet |
| 20 | `A4_event_localization` | `split_matches_global_split` | PASS | 0 row(s) sit in a split other than the one the frozen patient partition assigns (§4.C invariant 1) |
| 21 | `A4_event_localization` | `zero_study_overlap` | PASS | pairwise study_id intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 22 | `A5_cross_modal_verification` | `split_column_matches_file` | PASS | rows filed under the wrong split: {'train': 0, 'val': 0, 'test': 0} |
| 23 | `A5_cross_modal_verification` | `zero_subject_overlap` | PASS | pairwise subject intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 24 | `A5_cross_modal_verification` | `subjects_exist_in_global_split` | PASS | 0 row(s) carry a subject absent from splits_subject_level.parquet |
| 25 | `A5_cross_modal_verification` | `split_matches_global_split` | PASS | 0 row(s) sit in a split other than the one the frozen patient partition assigns (§4.C invariant 1) |
| 26 | `A5_cross_modal_verification` | `zero_study_overlap` | PASS | pairwise anchor_study_id intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 27 | `A5_cross_modal_verification` | `donor_in_same_split[signal_id]` | PASS | 0 `signal_id` value(s) resolve to no clean-cohort subject; 0 point at a subject in another split |
| 28 | `A5_cross_modal_verification` | `negative_donor_is_another_subject[signal_id]` | PASS | 0 negative row(s) take `signal_id` from the anchor's own subject — that row would be a near-positive labelled negative |
| 29 | `A5_cross_modal_verification` | `donor_in_same_split[image_id]` | PASS | 0 `image_id` value(s) resolve to no clean-cohort subject; 0 point at a subject in another split |
| 30 | `A5_cross_modal_verification` | `negative_donor_is_another_subject[image_id]` | PASS | 0 negative row(s) take `image_id` from the anchor's own subject — that row would be a near-positive labelled negative |
| 31 | `A5_cross_modal_verification` | `donor_in_same_split[text_id]` | PASS | 0 `text_id` value(s) resolve to no clean-cohort subject; 0 point at a subject in another split |
| 32 | `A5_cross_modal_verification` | `negative_donor_is_another_subject[text_id]` | PASS | 0 negative row(s) take `text_id` from the anchor's own subject — that row would be a near-positive labelled negative |
| 33 | `A5_cross_modal_verification` | `masked_attribute_files_respect_the_split` | PASS | 0 row(s) across the three masked-attribute files sit in the wrong split |
| 34 | `A6_risk_stratification` | `split_column_matches_file` | PASS | rows filed under the wrong split: {'train': 0, 'val': 0, 'test': 0} |
| 35 | `A6_risk_stratification` | `zero_subject_overlap` | PASS | pairwise subject intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 36 | `A6_risk_stratification` | `subjects_exist_in_global_split` | PASS | 0 row(s) carry a subject absent from splits_subject_level.parquet |
| 37 | `A6_risk_stratification` | `split_matches_global_split` | PASS | 0 row(s) sit in a split other than the one the frozen patient partition assigns (§4.C invariant 1) |
| 38 | `A6_risk_stratification` | `zero_study_overlap` | PASS | pairwise study_id intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 39 | `B1_measurement_blind` | `split_column_matches_file` | PASS | rows filed under the wrong split: {'train': 0, 'val': 0, 'test': 0} |
| 40 | `B1_measurement_blind` | `zero_subject_overlap` | PASS | pairwise subject intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 41 | `B1_measurement_blind` | `subjects_exist_in_global_split` | PASS | 0 row(s) carry a subject absent from splits_subject_level.parquet |
| 42 | `B1_measurement_blind` | `split_matches_global_split` | PASS | 0 row(s) sit in a split other than the one the frozen patient partition assigns (§4.C invariant 1) |
| 43 | `B1_measurement_blind` | `zero_study_overlap` | PASS | pairwise study_id intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 44 | `B2_noise_robustness` | `split_column_matches_file` | PASS | rows filed under the wrong split: {'train': 0, 'val': 0, 'test': 0} |
| 45 | `B2_noise_robustness` | `zero_subject_overlap` | PASS | pairwise subject intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 46 | `B2_noise_robustness` | `subjects_exist_in_global_split` | PASS | 0 row(s) carry a subject absent from splits_subject_level.parquet |
| 47 | `B2_noise_robustness` | `split_matches_global_split` | PASS | 0 row(s) sit in a split other than the one the frozen patient partition assigns (§4.C invariant 1) |
| 48 | `B2_noise_robustness` | `zero_study_overlap` | PASS | pairwise study_id intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 49 | `B3_temporal_grounding` | `split_column_matches_file` | PASS | rows filed under the wrong split: {'train': 0, 'val': 0, 'test': 0} |
| 50 | `B3_temporal_grounding` | `zero_subject_overlap` | PASS | pairwise subject intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 51 | `B3_temporal_grounding` | `subjects_exist_in_global_split` | PASS | 0 row(s) carry a subject absent from splits_subject_level.parquet |
| 52 | `B3_temporal_grounding` | `split_matches_global_split` | PASS | 0 row(s) sit in a split other than the one the frozen patient partition assigns (§4.C invariant 1) |
| 53 | `B3_temporal_grounding` | `zero_study_overlap` | PASS | pairwise study_id intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 54 | `B4_cross_modal_verification` | `split_column_matches_file` | PASS | rows filed under the wrong split: {'train': 0, 'val': 0, 'test': 0} |
| 55 | `B4_cross_modal_verification` | `zero_subject_overlap` | PASS | pairwise subject intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 56 | `B4_cross_modal_verification` | `subjects_exist_in_global_split` | PASS | 0 row(s) carry a subject absent from splits_subject_level.parquet |
| 57 | `B4_cross_modal_verification` | `split_matches_global_split` | PASS | 0 row(s) sit in a split other than the one the frozen patient partition assigns (§4.C invariant 1) |
| 58 | `B4_cross_modal_verification` | `zero_study_overlap` | PASS | pairwise anchor_study_id intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 59 | `B4_cross_modal_verification` | `donor_in_same_split[signal_id]` | PASS | 0 `signal_id` value(s) resolve to no clean-cohort subject; 0 point at a subject in another split |
| 60 | `B4_cross_modal_verification` | `negative_donor_is_another_subject[signal_id]` | PASS | 0 negative row(s) take `signal_id` from the anchor's own subject — that row would be a near-positive labelled negative |
| 61 | `B4_cross_modal_verification` | `donor_in_same_split[image_id]` | PASS | 0 `image_id` value(s) resolve to no clean-cohort subject; 0 point at a subject in another split |
| 62 | `B4_cross_modal_verification` | `negative_donor_is_another_subject[image_id]` | PASS | 0 negative row(s) take `image_id` from the anchor's own subject — that row would be a near-positive labelled negative |
| 63 | `B4_cross_modal_verification` | `donor_in_same_split[text_id]` | PASS | 0 `text_id` value(s) resolve to no clean-cohort subject; 0 point at a subject in another split |
| 64 | `B4_cross_modal_verification` | `negative_donor_is_another_subject[text_id]` | PASS | 0 negative row(s) take `text_id` from the anchor's own subject — that row would be a near-positive labelled negative |
| 65 | `B5_contradiction_detection` | `split_column_matches_file` | PASS | rows filed under the wrong split: {'train': 0, 'val': 0, 'test': 0} |
| 66 | `B5_contradiction_detection` | `zero_subject_overlap` | PASS | pairwise subject intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 67 | `B5_contradiction_detection` | `subjects_exist_in_global_split` | PASS | 0 row(s) carry a subject absent from splits_subject_level.parquet |
| 68 | `B5_contradiction_detection` | `split_matches_global_split` | PASS | 0 row(s) sit in a split other than the one the frozen patient partition assigns (§4.C invariant 1) |
| 69 | `B5_contradiction_detection` | `zero_study_overlap` | PASS | pairwise study_id intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 70 | `B6_difficulty_stratified` | `split_column_matches_file` | PASS | one pointer table for all three splits (§4.B.6.5); rows are separated by the `split` column alone |
| 71 | `B6_difficulty_stratified` | `zero_subject_overlap` | PASS | pairwise subject intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 72 | `B6_difficulty_stratified` | `subjects_exist_in_global_split` | PASS | 0 row(s) carry a subject absent from splits_subject_level.parquet |
| 73 | `B6_difficulty_stratified` | `split_matches_global_split` | PASS | 0 row(s) sit in a split other than the one the frozen patient partition assigns (§4.C invariant 1) |
| 74 | `B6_difficulty_stratified` | `zero_study_overlap` | PASS | pairwise study_id intersections {'train/val': 0, 'train/test': 0, 'val/test': 0} |
| 75 | `B2_noise_robustness` | `frozen_anchors_are_test_only` | PASS | 151,551 anchor rows over 1,716 subjects, all in ['test'] |

## Reproduce

```
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/22_audit_tasks_split.py
```

The audit reads only artifacts already on disk and writes only this report, so it is safe to re-run at any time.
