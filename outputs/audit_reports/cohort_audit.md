# Cohort audit — Phase 2 tasks (Stage P2.3)

**VERDICT: PASS** — 184 checks run, 184 passed, 0 violations.

Spec §9.4 (Stage P2.3), §1.2 audit inventory. Generated 2026-08-27T12:18:20Z by `scripts/phase2_tasks_benchmark_and_paper/21_audit_tasks_cohort.py` from the task parquets on disk — every number below is measured, none is restated from a builder's own report.

Per task: n_ECG, n_subjects, per-class counts and prevalence, missingness, linkage-tier and SQI-tier breakdowns and the cart_id top 5 — every number measured off the task parquets rather than copied from a builder's state file, so this audit can contradict Stage P2.1/P2.2 if they have drifted.

The assertions behind the verdict ask one question: **would a training run on this cohort produce a defined number?** A head needs at least two label values in every split for AUPRC to exist; a masked head needs a label wherever its mask is True; the primary cohort must obey its §4 rule; and a cohort size a §12 decision locked must still measure the same. An absent *class* is reported rather than failed — A3's `abnormal_unknown_direction` occurs once in half a million rows and troponin has no `low_abnormal`, which is MIMIC-IV, not a build defect.

## Verdict by task

| Task | Checks | Verdict |
| --- | ---: | --- |
| `A1_ecg_diagnosis` | 10 | **PASS** |
| `A2_measurement_blind` | 13 | **PASS** |
| `A3_lab_abnormality` | 75 | **PASS** |
| `A4_event_localization` | 6 | **PASS** |
| `A5_cross_modal_verification` | 15 | **PASS** |
| `A6_risk_stratification` | 13 | **PASS** |
| `B1_measurement_blind` | 11 | **PASS** |
| `B2_noise_robustness` | 12 | **PASS** |
| `B3_temporal_grounding` | 5 | **PASS** |
| `B4_cross_modal_verification` | 7 | **PASS** |
| `B5_contradiction_detection` | 10 | **PASS** |
| `B6_difficulty_stratified` | 7 | **PASS** |


## `A1_ecg_diagnosis`

Cohort rule: §4.A.1.2. Heads: 5 (binary).

| split | rows | unique `study_id` | subjects | primary rows | primary subjects |
| --- | --- | --- | --- | --- | --- |
| train | 350,090 | 350,090 | 87,220 | 262,950 | 67,024 |
| val | 50,216 | 50,216 | 12,440 | 37,914 | 9,573 |
| test | 99,971 | 99,971 | 24,887 | 75,187 | 19,168 |
| **all** | **500,277** | **500,277** | **124,547** | **376,051** |  |

| breakdown | counts over all three splits |
| --- | --- |
| `link_tier` | L3 422,009 · L2 78,268 |
| `sqi_tier` | medium 320,950 · low 175,721 · high 3,606 |
| `cart_id` | 6632385 67,674 · 6672155 29,889 · 6752764 28,721 · 6848296 27,363 · 6903271 22,704  (top 5 of 154) |


**Per-head class counts and prevalence** (`n` is the rows the head is scored on after its mask; prevalence is within that slice).

| head | split | n scored | counts | prevalence | null |
| --- | --- | --- | --- | --- | --- |
| label_atrial_fibrillation_flutter | train | 350,090 | positive 93,264 · negative 256,826 | positive 0.2664 · negative 0.7336 | 0 |
| label_atrial_fibrillation_flutter | val | 50,216 | positive 12,877 · negative 37,339 | positive 0.2564 · negative 0.7436 | 0 |
| label_atrial_fibrillation_flutter | test | 99,971 | positive 26,111 · negative 73,860 | positive 0.2612 · negative 0.7388 | 0 |
| label_heart_failure_narrow | train | 350,090 | positive 93,072 · negative 257,018 | positive 0.2659 · negative 0.7341 | 0 |
| label_heart_failure_narrow | val | 50,216 | positive 12,896 · negative 37,320 | positive 0.2568 · negative 0.7432 | 0 |
| label_heart_failure_narrow | test | 99,971 | positive 26,019 · negative 73,952 | positive 0.2603 · negative 0.7397 | 0 |
| label_acute_myocardial_infarction | train | 350,090 | positive 32,674 · negative 317,416 | positive 0.0933 · negative 0.9067 | 0 |
| label_acute_myocardial_infarction | val | 50,216 | positive 4,582 · negative 45,634 | positive 0.0912 · negative 0.9088 | 0 |
| label_acute_myocardial_infarction | test | 99,971 | positive 8,788 · negative 91,183 | positive 0.0879 · negative 0.9121 | 0 |
| label_conduction_disorder | train | 350,090 | positive 19,101 · negative 330,989 | positive 0.0546 · negative 0.9454 | 0 |
| label_conduction_disorder | val | 50,216 | positive 2,646 · negative 47,570 | positive 0.0527 · negative 0.9473 | 0 |
| label_conduction_disorder | test | 99,971 | positive 5,895 · negative 94,076 | positive 0.0590 · negative 0.9410 | 0 |
| label_ventricular_arrhythmia_or_arrest | train | 350,090 | positive 14,734 · negative 335,356 | positive 0.0421 · negative 0.9579 | 0 |
| label_ventricular_arrhythmia_or_arrest | val | 50,216 | positive 2,120 · negative 48,096 | positive 0.0422 · negative 0.9578 | 0 |
| label_ventricular_arrhythmia_or_arrest | test | 99,971 | positive 3,901 · negative 96,070 | positive 0.0390 · negative 0.9610 | 0 |


**Missingness** (columns with at least one null, over all three splits). Nulls in a label column are only legitimate where a mask column declares the row out of scope; the `mask_implies_label` checks above are what enforce that.

| column | nulls | fraction |
| --- | --- | --- |
| `hadm_id` | 47,703 | 0.0954 |


## `A2_measurement_blind`

Cohort rule: §4.A.2.2 as amended by §4 decision 10. Heads: 3 (multiclass).

| split | rows | unique `study_id` | subjects | primary rows | primary subjects |
| --- | --- | --- | --- | --- | --- |
| train | 349,871 | 349,871 | 87,244 | 192,087 | 65,852 |
| val | 50,182 | 50,182 | 12,440 | 27,820 | 9,379 |
| test | 99,964 | 99,964 | 24,900 | 55,181 | 18,794 |
| **all** | **500,017** | **500,017** | **124,584** | **275,088** |  |

| breakdown | counts over all three splits |
| --- | --- |
| `link_tier` | L3 421,755 · L2 78,262 |
| `sqi_tier` | medium 320,858 · low 175,552 · high 3,607 |
| `cart_id` | 6632385 67,693 · 6672155 29,877 · 6752764 28,718 · 6848296 27,355 · 6903271 22,697  (top 5 of 154) |


**Per-head class counts and prevalence** (`n` is the rows the head is scored on after its mask; prevalence is within that slice).

| head | split | n scored | counts | prevalence | null |
| --- | --- | --- | --- | --- | --- |
| hr_label | train | 349,871 | bradycardia 41,187 · normal 244,197 · tachycardia 64,487 | bradycardia 0.1177 · normal 0.6980 · tachycardia 0.1843 | 0 |
| hr_label | val | 50,182 | bradycardia 5,985 · normal 34,882 · tachycardia 9,315 | bradycardia 0.1193 · normal 0.6951 · tachycardia 0.1856 | 0 |
| hr_label | test | 99,964 | bradycardia 11,943 · normal 69,473 · tachycardia 18,548 | bradycardia 0.1195 · normal 0.6950 · tachycardia 0.1855 | 0 |
| qrs_label | train | 349,871 | normal 220,799 · borderline 68,538 · wide 60,534 | normal 0.6311 · borderline 0.1959 · wide 0.1730 | 0 |
| qrs_label | val | 50,182 | normal 31,901 · borderline 9,717 · wide 8,564 | normal 0.6357 · borderline 0.1936 · wide 0.1707 | 0 |
| qrs_label | test | 99,964 | normal 63,058 · borderline 19,659 · wide 17,247 | normal 0.6308 · borderline 0.1967 · wide 0.1725 | 0 |
| qtc_label | train | 349,871 | short 402 · normal 183,698 · prolonged 165,771 | short 0.0011 · normal 0.5250 · prolonged 0.4738 | 0 |
| qtc_label | val | 50,182 | short 41 · normal 26,666 · prolonged 23,475 | short 0.0008 · normal 0.5314 · prolonged 0.4678 | 0 |
| qtc_label | test | 99,964 | short 104 · normal 52,785 · prolonged 47,075 | short 0.0010 · normal 0.5280 · prolonged 0.4709 | 0 |


**Missingness** (columns with at least one null, over all three splits). Nulls in a label column are only legitimate where a mask column declares the row out of scope; the `mask_implies_label` checks above are what enforce that.

| column | nulls | fraction |
| --- | --- | --- |
| `qtc_ms_bazett` | 73,866 | 0.1477 |


## `A3_lab_abnormality`

Cohort rule: §4.A.3.2. Heads: 35 (multiclass).

| split | rows | unique `study_id` | subjects | primary rows | primary subjects |
| --- | --- | --- | --- | --- | --- |
| train | 350,203 | 350,203 | 87,255 | 295,236 | 80,431 |
| val | 50,240 | 50,240 | 12,445 | 42,563 | 11,475 |
| test | 100,028 | 100,028 | 24,902 | 84,348 | 22,953 |
| **all** | **500,471** | **500,471** | **124,602** | **422,147** |  |

| breakdown | counts over all three splits |
| --- | --- |
| `link_tier` | L3 422,147 · L2 78,324 |
| `sqi_tier` | medium 321,073 · low 175,791 · high 3,607 |
| `cart_id` | 6632385 67,713 · 6672155 29,899 · 6752764 28,731 · 6848296 27,375 · 6903271 22,710  (top 5 of 154) |


**Per-head class counts and prevalence** (`n` is the rows the head is scored on after its mask; prevalence is within that slice).

| head | split | n scored | counts | prevalence | null |
| --- | --- | --- | --- | --- | --- |
| lab_K_pm24h | train | 350,203 | missing 11,837 · low_abnormal 13,678 · high_abnormal 25,700 · abnormal_unknown_direction 0 · normal 298,988 | missing 0.0338 · low_abnormal 0.0391 · high_abnormal 0.0734 · abnormal_unknown_direction 0.0000 · normal 0.8538 | 0 |
| lab_K_pm24h | val | 50,240 | missing 1,725 · low_abnormal 1,782 · high_abnormal 3,962 · abnormal_unknown_direction 0 · normal 42,771 | missing 0.0343 · low_abnormal 0.0355 · high_abnormal 0.0789 · abnormal_unknown_direction 0.0000 · normal 0.8513 | 0 |
| lab_K_pm24h | test | 100,028 | missing 3,472 · low_abnormal 3,798 · high_abnormal 7,297 · abnormal_unknown_direction 1 · normal 85,460 | missing 0.0347 · low_abnormal 0.0380 · high_abnormal 0.0729 · abnormal_unknown_direction 0.0000 · normal 0.8544 | 0 |
| lab_K_pre_24h | train | 350,203 | missing 115,338 · low_abnormal 9,848 · high_abnormal 18,028 · abnormal_unknown_direction 0 · normal 206,989 | missing 0.3293 · low_abnormal 0.0281 · high_abnormal 0.0515 · abnormal_unknown_direction 0.0000 · normal 0.5911 | 0 |
| lab_K_pre_24h | val | 50,240 | missing 16,387 · low_abnormal 1,349 · high_abnormal 2,745 · abnormal_unknown_direction 0 · normal 29,759 | missing 0.3262 · low_abnormal 0.0269 · high_abnormal 0.0546 · abnormal_unknown_direction 0.0000 · normal 0.5923 | 0 |
| lab_K_pre_24h | test | 100,028 | missing 33,265 · low_abnormal 2,660 · high_abnormal 5,093 · abnormal_unknown_direction 1 · normal 59,009 | missing 0.3326 · low_abnormal 0.0266 · high_abnormal 0.0509 · abnormal_unknown_direction 0.0000 · normal 0.5899 | 0 |
| lab_K_post_24h | train | 350,203 | missing 62,259 · low_abnormal 12,514 · high_abnormal 21,302 · abnormal_unknown_direction 0 · normal 254,128 | missing 0.1778 · low_abnormal 0.0357 · high_abnormal 0.0608 · abnormal_unknown_direction 0.0000 · normal 0.7257 | 0 |
| lab_K_post_24h | val | 50,240 | missing 9,070 · low_abnormal 1,572 · high_abnormal 3,348 · abnormal_unknown_direction 0 · normal 36,250 | missing 0.1805 · low_abnormal 0.0313 · high_abnormal 0.0666 · abnormal_unknown_direction 0.0000 · normal 0.7215 | 0 |
| lab_K_post_24h | test | 100,028 | missing 18,093 · low_abnormal 3,584 · high_abnormal 6,000 · abnormal_unknown_direction 0 · normal 72,351 | missing 0.1809 · low_abnormal 0.0358 · high_abnormal 0.0600 · abnormal_unknown_direction 0.0000 · normal 0.7233 | 0 |
| lab_K_pm6h | train | 350,203 | missing 73,685 · low_abnormal 11,860 · high_abnormal 24,178 · abnormal_unknown_direction 0 · normal 240,480 | missing 0.2104 · low_abnormal 0.0339 · high_abnormal 0.0690 · abnormal_unknown_direction 0.0000 · normal 0.6867 | 0 |
| lab_K_pm6h | val | 50,240 | missing 10,549 · low_abnormal 1,544 · high_abnormal 3,725 · abnormal_unknown_direction 0 · normal 34,422 | missing 0.2100 · low_abnormal 0.0307 · high_abnormal 0.0741 · abnormal_unknown_direction 0.0000 · normal 0.6852 | 0 |
| lab_K_pm6h | test | 100,028 | missing 21,111 · low_abnormal 3,298 · high_abnormal 6,858 · abnormal_unknown_direction 1 · normal 68,760 | missing 0.2111 · low_abnormal 0.0330 · high_abnormal 0.0686 · abnormal_unknown_direction 0.0000 · normal 0.6874 | 0 |
| lab_K_pm12h | train | 350,203 | missing 22,539 · low_abnormal 13,412 · high_abnormal 25,478 · abnormal_unknown_direction 0 · normal 288,774 | missing 0.0644 · low_abnormal 0.0383 · high_abnormal 0.0728 · abnormal_unknown_direction 0.0000 · normal 0.8246 | 0 |
| lab_K_pm12h | val | 50,240 | missing 3,302 · low_abnormal 1,752 · high_abnormal 3,912 · abnormal_unknown_direction 0 · normal 41,274 | missing 0.0657 · low_abnormal 0.0349 · high_abnormal 0.0779 · abnormal_unknown_direction 0.0000 · normal 0.8215 | 0 |
| lab_K_pm12h | test | 100,028 | missing 6,605 · low_abnormal 3,717 · high_abnormal 7,216 · abnormal_unknown_direction 1 · normal 82,489 | missing 0.0660 · low_abnormal 0.0372 · high_abnormal 0.0721 · abnormal_unknown_direction 0.0000 · normal 0.8247 | 0 |
| lab_Na_pm24h | train | 350,203 | missing 13,661 · low_abnormal 30,190 · high_abnormal 7,458 · abnormal_unknown_direction 0 · normal 298,894 | missing 0.0390 · low_abnormal 0.0862 · high_abnormal 0.0213 · abnormal_unknown_direction 0.0000 · normal 0.8535 | 0 |
| lab_Na_pm24h | val | 50,240 | missing 1,955 · low_abnormal 4,728 · high_abnormal 1,042 · abnormal_unknown_direction 0 · normal 42,515 | missing 0.0389 · low_abnormal 0.0941 · high_abnormal 0.0207 · abnormal_unknown_direction 0.0000 · normal 0.8462 | 0 |
| lab_Na_pm24h | test | 100,028 | missing 3,993 · low_abnormal 8,667 · high_abnormal 2,304 · abnormal_unknown_direction 0 · normal 85,064 | missing 0.0399 · low_abnormal 0.0866 · high_abnormal 0.0230 · abnormal_unknown_direction 0.0000 · normal 0.8504 | 0 |
| lab_Na_pre_24h | train | 350,203 | missing 116,521 · low_abnormal 22,059 · high_abnormal 5,944 · abnormal_unknown_direction 0 · normal 205,679 | missing 0.3327 · low_abnormal 0.0630 · high_abnormal 0.0170 · abnormal_unknown_direction 0.0000 · normal 0.5873 | 0 |
| lab_Na_pre_24h | val | 50,240 | missing 16,552 · low_abnormal 3,466 · high_abnormal 844 · abnormal_unknown_direction 0 · normal 29,378 | missing 0.3295 · low_abnormal 0.0690 · high_abnormal 0.0168 · abnormal_unknown_direction 0.0000 · normal 0.5848 | 0 |
| lab_Na_pre_24h | test | 100,028 | missing 33,591 · low_abnormal 6,312 · high_abnormal 1,859 · abnormal_unknown_direction 0 · normal 58,266 | missing 0.3358 · low_abnormal 0.0631 · high_abnormal 0.0186 · abnormal_unknown_direction 0.0000 · normal 0.5825 | 0 |
| lab_Na_post_24h | train | 350,203 | missing 65,203 · low_abnormal 26,266 · high_abnormal 7,208 · abnormal_unknown_direction 0 · normal 251,526 | missing 0.1862 · low_abnormal 0.0750 · high_abnormal 0.0206 · abnormal_unknown_direction 0.0000 · normal 0.7182 | 0 |
| lab_Na_post_24h | val | 50,240 | missing 9,458 · low_abnormal 4,151 · high_abnormal 993 · abnormal_unknown_direction 0 · normal 35,638 | missing 0.1883 · low_abnormal 0.0826 · high_abnormal 0.0198 · abnormal_unknown_direction 0.0000 · normal 0.7094 | 0 |
| lab_Na_post_24h | test | 100,028 | missing 18,867 · low_abnormal 7,556 · high_abnormal 2,180 · abnormal_unknown_direction 0 · normal 71,425 | missing 0.1886 · low_abnormal 0.0755 · high_abnormal 0.0218 · abnormal_unknown_direction 0.0000 · normal 0.7141 | 0 |
| lab_Na_pm6h | train | 350,203 | missing 76,869 · low_abnormal 26,314 · high_abnormal 6,407 · abnormal_unknown_direction 0 · normal 240,613 | missing 0.2195 · low_abnormal 0.0751 · high_abnormal 0.0183 · abnormal_unknown_direction 0.0000 · normal 0.6871 | 0 |
| lab_Na_pm6h | val | 50,240 | missing 11,030 · low_abnormal 4,118 · high_abnormal 898 · abnormal_unknown_direction 0 · normal 34,194 | missing 0.2195 · low_abnormal 0.0820 · high_abnormal 0.0179 · abnormal_unknown_direction 0.0000 · normal 0.6806 | 0 |
| lab_Na_pm6h | test | 100,028 | missing 22,009 · low_abnormal 7,550 · high_abnormal 1,973 · abnormal_unknown_direction 0 · normal 68,496 | missing 0.2200 · low_abnormal 0.0755 · high_abnormal 0.0197 · abnormal_unknown_direction 0.0000 · normal 0.6848 | 0 |
| lab_Na_pm12h | train | 350,203 | missing 24,716 · low_abnormal 29,715 · high_abnormal 7,327 · abnormal_unknown_direction 0 · normal 288,445 | missing 0.0706 · low_abnormal 0.0849 · high_abnormal 0.0209 · abnormal_unknown_direction 0.0000 · normal 0.8237 | 0 |
| lab_Na_pm12h | val | 50,240 | missing 3,597 · low_abnormal 4,659 · high_abnormal 1,028 · abnormal_unknown_direction 0 · normal 40,956 | missing 0.0716 · low_abnormal 0.0927 · high_abnormal 0.0205 · abnormal_unknown_direction 0.0000 · normal 0.8152 | 0 |
| lab_Na_pm12h | test | 100,028 | missing 7,188 · low_abnormal 8,529 · high_abnormal 2,264 · abnormal_unknown_direction 0 · normal 82,047 | missing 0.0719 · low_abnormal 0.0853 · high_abnormal 0.0226 · abnormal_unknown_direction 0.0000 · normal 0.8202 | 0 |
| lab_creatinine_pm24h | train | 350,203 | missing 11,958 · low_abnormal 2,334 · high_abnormal 109,603 · abnormal_unknown_direction 12 · normal 226,296 | missing 0.0341 · low_abnormal 0.0067 · high_abnormal 0.3130 · abnormal_unknown_direction 0.0000 · normal 0.6462 | 0 |
| lab_creatinine_pm24h | val | 50,240 | missing 1,718 · low_abnormal 309 · high_abnormal 15,765 · abnormal_unknown_direction 3 · normal 32,445 | missing 0.0342 · low_abnormal 0.0062 · high_abnormal 0.3138 · abnormal_unknown_direction 0.0001 · normal 0.6458 | 0 |
| lab_creatinine_pm24h | test | 100,028 | missing 3,493 · low_abnormal 819 · high_abnormal 30,094 · abnormal_unknown_direction 0 · normal 65,622 | missing 0.0349 · low_abnormal 0.0082 · high_abnormal 0.3009 · abnormal_unknown_direction 0.0000 · normal 0.6560 | 0 |
| lab_creatinine_pre_24h | train | 350,203 | missing 115,885 · low_abnormal 1,932 · high_abnormal 80,633 · abnormal_unknown_direction 7 · normal 151,746 | missing 0.3309 · low_abnormal 0.0055 · high_abnormal 0.2302 · abnormal_unknown_direction 0.0000 · normal 0.4333 | 0 |
| lab_creatinine_pre_24h | val | 50,240 | missing 16,432 · low_abnormal 269 · high_abnormal 11,684 · abnormal_unknown_direction 3 · normal 21,852 | missing 0.3271 · low_abnormal 0.0054 · high_abnormal 0.2326 · abnormal_unknown_direction 0.0001 · normal 0.4350 | 0 |
| lab_creatinine_pre_24h | test | 100,028 | missing 33,363 · low_abnormal 710 · high_abnormal 22,132 · abnormal_unknown_direction 0 · normal 43,823 | missing 0.3335 · low_abnormal 0.0071 · high_abnormal 0.2213 · abnormal_unknown_direction 0.0000 · normal 0.4381 | 0 |
| lab_creatinine_post_24h | train | 350,203 | missing 64,511 · low_abnormal 2,404 · high_abnormal 97,373 · abnormal_unknown_direction 8 · normal 185,907 | missing 0.1842 · low_abnormal 0.0069 · high_abnormal 0.2780 · abnormal_unknown_direction 0.0000 · normal 0.5309 | 0 |
| lab_creatinine_post_24h | val | 50,240 | missing 9,385 · low_abnormal 317 · high_abnormal 13,987 · abnormal_unknown_direction 1 · normal 26,550 | missing 0.1868 · low_abnormal 0.0063 · high_abnormal 0.2784 · abnormal_unknown_direction 0.0000 · normal 0.5285 | 0 |
| lab_creatinine_post_24h | test | 100,028 | missing 18,684 · low_abnormal 805 · high_abnormal 26,745 · abnormal_unknown_direction 0 · normal 53,794 | missing 0.1868 · low_abnormal 0.0080 · high_abnormal 0.2674 · abnormal_unknown_direction 0.0000 · normal 0.5378 | 0 |
| lab_creatinine_pm6h | train | 350,203 | missing 78,231 · low_abnormal 1,696 · high_abnormal 91,665 · abnormal_unknown_direction 11 · normal 178,600 | missing 0.2234 · low_abnormal 0.0048 · high_abnormal 0.2617 · abnormal_unknown_direction 0.0000 · normal 0.5100 | 0 |
| lab_creatinine_pm6h | val | 50,240 | missing 11,233 · low_abnormal 214 · high_abnormal 13,231 · abnormal_unknown_direction 3 · normal 25,559 | missing 0.2236 · low_abnormal 0.0043 · high_abnormal 0.2634 · abnormal_unknown_direction 0.0001 · normal 0.5087 | 0 |
| lab_creatinine_pm6h | test | 100,028 | missing 22,442 · low_abnormal 555 · high_abnormal 25,223 · abnormal_unknown_direction 0 · normal 51,808 | missing 0.2244 · low_abnormal 0.0055 · high_abnormal 0.2522 · abnormal_unknown_direction 0.0000 · normal 0.5179 | 0 |
| lab_creatinine_pm12h | train | 350,203 | missing 24,980 · low_abnormal 2,250 · high_abnormal 107,004 · abnormal_unknown_direction 12 · normal 215,957 | missing 0.0713 · low_abnormal 0.0064 · high_abnormal 0.3055 · abnormal_unknown_direction 0.0000 · normal 0.6167 | 0 |
| lab_creatinine_pm12h | val | 50,240 | missing 3,628 · low_abnormal 294 · high_abnormal 15,363 · abnormal_unknown_direction 3 · normal 30,952 | missing 0.0722 · low_abnormal 0.0059 · high_abnormal 0.3058 · abnormal_unknown_direction 0.0001 · normal 0.6161 | 0 |
| lab_creatinine_pm12h | test | 100,028 | missing 7,268 · low_abnormal 781 · high_abnormal 29,412 · abnormal_unknown_direction 0 · normal 62,567 | missing 0.0727 · low_abnormal 0.0078 · high_abnormal 0.2940 · abnormal_unknown_direction 0.0000 · normal 0.6255 | 0 |
| lab_troponin_pm24h | train | 350,203 | missing 282,940 · low_abnormal 0 · high_abnormal 62,335 · abnormal_unknown_direction 0 · normal 4,928 | missing 0.8079 · low_abnormal 0.0000 · high_abnormal 0.1780 · abnormal_unknown_direction 0.0000 · normal 0.0141 | 0 |
| lab_troponin_pm24h | val | 50,240 | missing 41,033 · low_abnormal 0 · high_abnormal 8,525 · abnormal_unknown_direction 0 · normal 682 | missing 0.8167 · low_abnormal 0.0000 · high_abnormal 0.1697 · abnormal_unknown_direction 0.0000 · normal 0.0136 | 0 |
| lab_troponin_pm24h | test | 100,028 | missing 81,131 · low_abnormal 0 · high_abnormal 17,453 · abnormal_unknown_direction 0 · normal 1,444 | missing 0.8111 · low_abnormal 0.0000 · high_abnormal 0.1745 · abnormal_unknown_direction 0.0000 · normal 0.0144 | 0 |
| lab_troponin_pre_24h | train | 350,203 | missing 307,285 · low_abnormal 0 · high_abnormal 40,203 · abnormal_unknown_direction 0 · normal 2,715 | missing 0.8774 · low_abnormal 0.0000 · high_abnormal 0.1148 · abnormal_unknown_direction 0.0000 · normal 0.0078 | 0 |
| lab_troponin_pre_24h | val | 50,240 | missing 44,308 · low_abnormal 0 · high_abnormal 5,559 · abnormal_unknown_direction 0 · normal 373 | missing 0.8819 · low_abnormal 0.0000 · high_abnormal 0.1106 · abnormal_unknown_direction 0.0000 · normal 0.0074 | 0 |
| lab_troponin_pre_24h | test | 100,028 | missing 88,116 · low_abnormal 0 · high_abnormal 11,093 · abnormal_unknown_direction 0 · normal 819 | missing 0.8809 · low_abnormal 0.0000 · high_abnormal 0.1109 · abnormal_unknown_direction 0.0000 · normal 0.0082 | 0 |
| lab_troponin_post_24h | train | 350,203 | missing 297,443 · low_abnormal 0 · high_abnormal 49,185 · abnormal_unknown_direction 0 · normal 3,575 | missing 0.8493 · low_abnormal 0.0000 · high_abnormal 0.1404 · abnormal_unknown_direction 0.0000 · normal 0.0102 | 0 |
| lab_troponin_post_24h | val | 50,240 | missing 42,965 · low_abnormal 0 · high_abnormal 6,796 · abnormal_unknown_direction 0 · normal 479 | missing 0.8552 · low_abnormal 0.0000 · high_abnormal 0.1353 · abnormal_unknown_direction 0.0000 · normal 0.0095 | 0 |
| lab_troponin_post_24h | test | 100,028 | missing 85,306 · low_abnormal 0 · high_abnormal 13,706 · abnormal_unknown_direction 0 · normal 1,016 | missing 0.8528 · low_abnormal 0.0000 · high_abnormal 0.1370 · abnormal_unknown_direction 0.0000 · normal 0.0102 | 0 |
| lab_troponin_pm6h | train | 350,203 | missing 295,219 · low_abnormal 0 · high_abnormal 50,949 · abnormal_unknown_direction 0 · normal 4,035 | missing 0.8430 · low_abnormal 0.0000 · high_abnormal 0.1455 · abnormal_unknown_direction 0.0000 · normal 0.0115 | 0 |
| lab_troponin_pm6h | val | 50,240 | missing 42,776 · low_abnormal 0 · high_abnormal 6,917 · abnormal_unknown_direction 0 · normal 547 | missing 0.8514 · low_abnormal 0.0000 · high_abnormal 0.1377 · abnormal_unknown_direction 0.0000 · normal 0.0109 | 0 |
| lab_troponin_pm6h | test | 100,028 | missing 84,640 · low_abnormal 0 · high_abnormal 14,197 · abnormal_unknown_direction 0 · normal 1,191 | missing 0.8462 · low_abnormal 0.0000 · high_abnormal 0.1419 · abnormal_unknown_direction 0.0000 · normal 0.0119 | 0 |
| lab_troponin_pm12h | train | 350,203 | missing 288,713 · low_abnormal 0 · high_abnormal 57,009 · abnormal_unknown_direction 0 · normal 4,481 | missing 0.8244 · low_abnormal 0.0000 · high_abnormal 0.1628 · abnormal_unknown_direction 0.0000 · normal 0.0128 | 0 |
| lab_troponin_pm12h | val | 50,240 | missing 41,870 · low_abnormal 0 · high_abnormal 7,755 · abnormal_unknown_direction 0 · normal 615 | missing 0.8334 · low_abnormal 0.0000 · high_abnormal 0.1544 · abnormal_unknown_direction 0.0000 · normal 0.0122 | 0 |
| lab_troponin_pm12h | test | 100,028 | missing 82,824 · low_abnormal 0 · high_abnormal 15,894 · abnormal_unknown_direction 0 · normal 1,310 | missing 0.8280 · low_abnormal 0.0000 · high_abnormal 0.1589 · abnormal_unknown_direction 0.0000 · normal 0.0131 | 0 |
| lab_lactate_pm24h | train | 350,203 | missing 231,747 · low_abnormal 90 · high_abnormal 37,720 · abnormal_unknown_direction 0 · normal 80,646 | missing 0.6618 · low_abnormal 0.0003 · high_abnormal 0.1077 · abnormal_unknown_direction 0.0000 · normal 0.2303 | 0 |
| lab_lactate_pm24h | val | 50,240 | missing 33,340 · low_abnormal 17 · high_abnormal 5,435 · abnormal_unknown_direction 0 · normal 11,448 | missing 0.6636 · low_abnormal 0.0003 · high_abnormal 0.1082 · abnormal_unknown_direction 0.0000 · normal 0.2279 | 0 |
| lab_lactate_pm24h | test | 100,028 | missing 65,634 · low_abnormal 28 · high_abnormal 10,927 · abnormal_unknown_direction 0 · normal 23,439 | missing 0.6562 · low_abnormal 0.0003 · high_abnormal 0.1092 · abnormal_unknown_direction 0.0000 · normal 0.2343 | 0 |
| lab_lactate_pre_24h | train | 350,203 | missing 285,571 · low_abnormal 46 · high_abnormal 21,311 · abnormal_unknown_direction 0 · normal 43,275 | missing 0.8154 · low_abnormal 0.0001 · high_abnormal 0.0609 · abnormal_unknown_direction 0.0000 · normal 0.1236 | 0 |
| lab_lactate_pre_24h | val | 50,240 | missing 41,019 · low_abnormal 11 · high_abnormal 3,035 · abnormal_unknown_direction 0 · normal 6,175 | missing 0.8165 · low_abnormal 0.0002 · high_abnormal 0.0604 · abnormal_unknown_direction 0.0000 · normal 0.1229 | 0 |
| lab_lactate_pre_24h | test | 100,028 | missing 81,190 · low_abnormal 18 · high_abnormal 6,170 · abnormal_unknown_direction 0 · normal 12,650 | missing 0.8117 · low_abnormal 0.0002 · high_abnormal 0.0617 · abnormal_unknown_direction 0.0000 · normal 0.1265 | 0 |
| lab_lactate_post_24h | train | 350,203 | missing 270,814 · low_abnormal 65 · high_abnormal 27,247 · abnormal_unknown_direction 0 · normal 52,077 | missing 0.7733 · low_abnormal 0.0002 · high_abnormal 0.0778 · abnormal_unknown_direction 0.0000 · normal 0.1487 | 0 |
| lab_lactate_post_24h | val | 50,240 | missing 38,988 · low_abnormal 10 · high_abnormal 3,927 · abnormal_unknown_direction 0 · normal 7,315 | missing 0.7760 · low_abnormal 0.0002 · high_abnormal 0.0782 · abnormal_unknown_direction 0.0000 · normal 0.1456 | 0 |
| lab_lactate_post_24h | test | 100,028 | missing 77,088 · low_abnormal 14 · high_abnormal 7,858 · abnormal_unknown_direction 0 · normal 15,068 | missing 0.7707 · low_abnormal 0.0001 · high_abnormal 0.0786 · abnormal_unknown_direction 0.0000 · normal 0.1506 | 0 |
| lab_lactate_pm6h | train | 350,203 | missing 262,813 · low_abnormal 52 · high_abnormal 31,641 · abnormal_unknown_direction 0 · normal 55,697 | missing 0.7505 · low_abnormal 0.0001 · high_abnormal 0.0904 · abnormal_unknown_direction 0.0000 · normal 0.1590 | 0 |
| lab_lactate_pm6h | val | 50,240 | missing 37,697 · low_abnormal 12 · high_abnormal 4,564 · abnormal_unknown_direction 0 · normal 7,967 | missing 0.7503 · low_abnormal 0.0002 · high_abnormal 0.0908 · abnormal_unknown_direction 0.0000 · normal 0.1586 | 0 |
| lab_lactate_pm6h | test | 100,028 | missing 74,509 · low_abnormal 12 · high_abnormal 9,108 · abnormal_unknown_direction 0 · normal 16,399 | missing 0.7449 · low_abnormal 0.0001 · high_abnormal 0.0911 · abnormal_unknown_direction 0.0000 · normal 0.1639 | 0 |
| lab_lactate_pm12h | train | 350,203 | missing 248,599 · low_abnormal 71 · high_abnormal 34,599 · abnormal_unknown_direction 0 · normal 66,934 | missing 0.7099 · low_abnormal 0.0002 · high_abnormal 0.0988 · abnormal_unknown_direction 0.0000 · normal 0.1911 | 0 |
| lab_lactate_pm12h | val | 50,240 | missing 35,679 · low_abnormal 14 · high_abnormal 4,997 · abnormal_unknown_direction 0 · normal 9,550 | missing 0.7102 · low_abnormal 0.0003 · high_abnormal 0.0995 · abnormal_unknown_direction 0.0000 · normal 0.1901 | 0 |
| lab_lactate_pm12h | test | 100,028 | missing 70,452 · low_abnormal 23 · high_abnormal 9,986 · abnormal_unknown_direction 0 · normal 19,567 | missing 0.7043 · low_abnormal 0.0002 · high_abnormal 0.0998 · abnormal_unknown_direction 0.0000 · normal 0.1956 | 0 |
| lab_Ca_pm24h | train | 350,203 | missing 86,007 · low_abnormal 67,860 · high_abnormal 5,473 · abnormal_unknown_direction 2 · normal 190,861 | missing 0.2456 · low_abnormal 0.1938 · high_abnormal 0.0156 · abnormal_unknown_direction 0.0000 · normal 0.5450 | 0 |
| lab_Ca_pm24h | val | 50,240 | missing 12,299 · low_abnormal 9,944 · high_abnormal 700 · abnormal_unknown_direction 0 · normal 27,297 | missing 0.2448 · low_abnormal 0.1979 · high_abnormal 0.0139 · abnormal_unknown_direction 0.0000 · normal 0.5433 | 0 |
| lab_Ca_pm24h | test | 100,028 | missing 24,842 · low_abnormal 19,448 · high_abnormal 1,520 · abnormal_unknown_direction 0 · normal 54,218 | missing 0.2484 · low_abnormal 0.1944 · high_abnormal 0.0152 · abnormal_unknown_direction 0.0000 · normal 0.5420 | 0 |
| lab_Ca_pre_24h | train | 350,203 | missing 186,939 · low_abnormal 46,219 · high_abnormal 3,622 · abnormal_unknown_direction 1 · normal 113,422 | missing 0.5338 · low_abnormal 0.1320 · high_abnormal 0.0103 · abnormal_unknown_direction 0.0000 · normal 0.3239 | 0 |
| lab_Ca_pre_24h | val | 50,240 | missing 26,612 · low_abnormal 6,806 · high_abnormal 465 · abnormal_unknown_direction 0 · normal 16,357 | missing 0.5297 · low_abnormal 0.1355 · high_abnormal 0.0093 · abnormal_unknown_direction 0.0000 · normal 0.3256 | 0 |
| lab_Ca_pre_24h | test | 100,028 | missing 54,001 · low_abnormal 13,166 · high_abnormal 1,024 · abnormal_unknown_direction 0 · normal 31,837 | missing 0.5399 · low_abnormal 0.1316 · high_abnormal 0.0102 · abnormal_unknown_direction 0.0000 · normal 0.3183 | 0 |
| lab_Ca_post_24h | train | 350,203 | missing 119,726 · low_abnormal 66,591 · high_abnormal 4,125 · abnormal_unknown_direction 1 · normal 159,760 | missing 0.3419 · low_abnormal 0.1901 · high_abnormal 0.0118 · abnormal_unknown_direction 0.0000 · normal 0.4562 | 0 |
| lab_Ca_post_24h | val | 50,240 | missing 17,173 · low_abnormal 9,753 · high_abnormal 532 · abnormal_unknown_direction 0 · normal 22,782 | missing 0.3418 · low_abnormal 0.1941 · high_abnormal 0.0106 · abnormal_unknown_direction 0.0000 · normal 0.4535 | 0 |
| lab_Ca_post_24h | test | 100,028 | missing 34,482 · low_abnormal 19,012 · high_abnormal 1,161 · abnormal_unknown_direction 0 · normal 45,373 | missing 0.3447 · low_abnormal 0.1901 · high_abnormal 0.0116 · abnormal_unknown_direction 0.0000 · normal 0.4536 | 0 |
| lab_Ca_pm6h | train | 350,203 | missing 181,593 · low_abnormal 44,436 · high_abnormal 4,336 · abnormal_unknown_direction 1 · normal 119,837 | missing 0.5185 · low_abnormal 0.1269 · high_abnormal 0.0124 · abnormal_unknown_direction 0.0000 · normal 0.3422 | 0 |
| lab_Ca_pm6h | val | 50,240 | missing 25,933 · low_abnormal 6,391 · high_abnormal 557 · abnormal_unknown_direction 0 · normal 17,359 | missing 0.5162 · low_abnormal 0.1272 · high_abnormal 0.0111 · abnormal_unknown_direction 0.0000 · normal 0.3455 | 0 |
| lab_Ca_pm6h | test | 100,028 | missing 52,215 · low_abnormal 12,631 · high_abnormal 1,179 · abnormal_unknown_direction 0 · normal 34,003 | missing 0.5220 · low_abnormal 0.1263 · high_abnormal 0.0118 · abnormal_unknown_direction 0.0000 · normal 0.3399 | 0 |
| lab_Ca_pm12h | train | 350,203 | missing 125,290 · low_abnormal 59,991 · high_abnormal 5,046 · abnormal_unknown_direction 2 · normal 159,874 | missing 0.3578 · low_abnormal 0.1713 · high_abnormal 0.0144 · abnormal_unknown_direction 0.0000 · normal 0.4565 | 0 |
| lab_Ca_pm12h | val | 50,240 | missing 17,878 · low_abnormal 8,738 · high_abnormal 642 · abnormal_unknown_direction 0 · normal 22,982 | missing 0.3559 · low_abnormal 0.1739 · high_abnormal 0.0128 · abnormal_unknown_direction 0.0000 · normal 0.4574 | 0 |
| lab_Ca_pm12h | test | 100,028 | missing 36,192 · low_abnormal 17,153 · high_abnormal 1,361 · abnormal_unknown_direction 0 · normal 45,322 | missing 0.3618 · low_abnormal 0.1715 · high_abnormal 0.0136 · abnormal_unknown_direction 0.0000 · normal 0.4531 | 0 |
| lab_Mg_pm24h | train | 350,203 | missing 80,377 · low_abnormal 14,571 · high_abnormal 9,441 · abnormal_unknown_direction 1 · normal 245,813 | missing 0.2295 · low_abnormal 0.0416 · high_abnormal 0.0270 · abnormal_unknown_direction 0.0000 · normal 0.7019 | 0 |
| lab_Mg_pm24h | val | 50,240 | missing 11,525 · low_abnormal 2,099 · high_abnormal 1,355 · abnormal_unknown_direction 0 · normal 35,261 | missing 0.2294 · low_abnormal 0.0418 · high_abnormal 0.0270 · abnormal_unknown_direction 0.0000 · normal 0.7019 | 0 |
| lab_Mg_pm24h | test | 100,028 | missing 23,419 · low_abnormal 4,251 · high_abnormal 2,735 · abnormal_unknown_direction 0 · normal 69,623 | missing 0.2341 · low_abnormal 0.0425 · high_abnormal 0.0273 · abnormal_unknown_direction 0.0000 · normal 0.6960 | 0 |
| lab_Mg_pre_24h | train | 350,203 | missing 186,312 · low_abnormal 7,302 · high_abnormal 6,388 · abnormal_unknown_direction 1 · normal 150,200 | missing 0.5320 · low_abnormal 0.0209 · high_abnormal 0.0182 · abnormal_unknown_direction 0.0000 · normal 0.4289 | 0 |
| lab_Mg_pre_24h | val | 50,240 | missing 26,643 · low_abnormal 1,106 · high_abnormal 927 · abnormal_unknown_direction 0 · normal 21,564 | missing 0.5303 · low_abnormal 0.0220 · high_abnormal 0.0185 · abnormal_unknown_direction 0.0000 · normal 0.4292 | 0 |
| lab_Mg_pre_24h | test | 100,028 | missing 53,928 · low_abnormal 2,067 · high_abnormal 1,856 · abnormal_unknown_direction 0 · normal 42,177 | missing 0.5391 · low_abnormal 0.0207 · high_abnormal 0.0186 · abnormal_unknown_direction 0.0000 · normal 0.4217 | 0 |
| lab_Mg_post_24h | train | 350,203 | missing 112,777 · low_abnormal 12,402 · high_abnormal 8,781 · abnormal_unknown_direction 1 · normal 216,242 | missing 0.3220 · low_abnormal 0.0354 · high_abnormal 0.0251 · abnormal_unknown_direction 0.0000 · normal 0.6175 | 0 |
| lab_Mg_post_24h | val | 50,240 | missing 16,211 · low_abnormal 1,783 · high_abnormal 1,256 · abnormal_unknown_direction 0 · normal 30,990 | missing 0.3227 · low_abnormal 0.0355 · high_abnormal 0.0250 · abnormal_unknown_direction 0.0000 · normal 0.6168 | 0 |
| lab_Mg_post_24h | test | 100,028 | missing 32,646 · low_abnormal 3,605 · high_abnormal 2,513 · abnormal_unknown_direction 0 · normal 61,264 | missing 0.3264 · low_abnormal 0.0360 · high_abnormal 0.0251 · abnormal_unknown_direction 0.0000 · normal 0.6125 | 0 |
| lab_Mg_pm6h | train | 350,203 | missing 181,435 · low_abnormal 8,963 · high_abnormal 6,961 · abnormal_unknown_direction 1 · normal 152,843 | missing 0.5181 · low_abnormal 0.0256 · high_abnormal 0.0199 · abnormal_unknown_direction 0.0000 · normal 0.4364 | 0 |
| lab_Mg_pm6h | val | 50,240 | missing 25,956 · low_abnormal 1,280 · high_abnormal 1,032 · abnormal_unknown_direction 0 · normal 21,972 | missing 0.5166 · low_abnormal 0.0255 · high_abnormal 0.0205 · abnormal_unknown_direction 0.0000 · normal 0.4373 | 0 |
| lab_Mg_pm6h | test | 100,028 | missing 52,396 · low_abnormal 2,599 · high_abnormal 1,969 · abnormal_unknown_direction 0 · normal 43,064 | missing 0.5238 · low_abnormal 0.0260 · high_abnormal 0.0197 · abnormal_unknown_direction 0.0000 · normal 0.4305 | 0 |
| lab_Mg_pm12h | train | 350,203 | missing 120,504 · low_abnormal 12,126 · high_abnormal 8,737 · abnormal_unknown_direction 1 · normal 208,835 | missing 0.3441 · low_abnormal 0.0346 · high_abnormal 0.0249 · abnormal_unknown_direction 0.0000 · normal 0.5963 | 0 |
| lab_Mg_pm12h | val | 50,240 | missing 17,217 · low_abnormal 1,768 · high_abnormal 1,261 · abnormal_unknown_direction 0 · normal 29,994 | missing 0.3427 · low_abnormal 0.0352 · high_abnormal 0.0251 · abnormal_unknown_direction 0.0000 · normal 0.5970 | 0 |
| lab_Mg_pm12h | test | 100,028 | missing 35,019 · low_abnormal 3,506 · high_abnormal 2,521 · abnormal_unknown_direction 0 · normal 58,982 | missing 0.3501 · low_abnormal 0.0351 · high_abnormal 0.0252 · abnormal_unknown_direction 0.0000 · normal 0.5897 | 0 |


**Classes absent from the test split** (reported, not a violation — `multiclass_macro_auprc` averages over the classes present): `lab_Ca_pm12h`.abnormal_unknown_direction, `lab_Ca_pm24h`.abnormal_unknown_direction, `lab_Ca_pm6h`.abnormal_unknown_direction, `lab_Ca_post_24h`.abnormal_unknown_direction, `lab_Ca_pre_24h`.abnormal_unknown_direction, `lab_K_post_24h`.abnormal_unknown_direction, `lab_Mg_pm12h`.abnormal_unknown_direction, `lab_Mg_pm24h`.abnormal_unknown_direction, `lab_Mg_pm6h`.abnormal_unknown_direction, `lab_Mg_post_24h`.abnormal_unknown_direction, `lab_Mg_pre_24h`.abnormal_unknown_direction, `lab_Na_pm12h`.abnormal_unknown_direction, `lab_Na_pm24h`.abnormal_unknown_direction, `lab_Na_pm6h`.abnormal_unknown_direction, `lab_Na_post_24h`.abnormal_unknown_direction, `lab_Na_pre_24h`.abnormal_unknown_direction, `lab_creatinine_pm12h`.abnormal_unknown_direction, `lab_creatinine_pm24h`.abnormal_unknown_direction, `lab_creatinine_pm6h`.abnormal_unknown_direction, `lab_creatinine_post_24h`.abnormal_unknown_direction, `lab_creatinine_pre_24h`.abnormal_unknown_direction, `lab_lactate_pm12h`.abnormal_unknown_direction, `lab_lactate_pm24h`.abnormal_unknown_direction, `lab_lactate_pm6h`.abnormal_unknown_direction, `lab_lactate_post_24h`.abnormal_unknown_direction, `lab_lactate_pre_24h`.abnormal_unknown_direction, `lab_troponin_pm12h`.abnormal_unknown_direction, `lab_troponin_pm12h`.low_abnormal, `lab_troponin_pm24h`.abnormal_unknown_direction, `lab_troponin_pm24h`.low_abnormal, `lab_troponin_pm6h`.abnormal_unknown_direction, `lab_troponin_pm6h`.low_abnormal, `lab_troponin_post_24h`.abnormal_unknown_direction, `lab_troponin_post_24h`.low_abnormal, `lab_troponin_pre_24h`.abnormal_unknown_direction, `lab_troponin_pre_24h`.low_abnormal.


**Missingness** (columns with at least one null, over all three splits). Nulls in a label column are only legitimate where a mask column declares the row out of scope; the `mask_implies_label` checks above are what enforce that.

| column | nulls | fraction |
| --- | --- | --- |
| `hadm_id` | 47,723 | 0.0954 |
| `lab_K_pm24h_signed_hours_from_ecg` | 16,716 | 0.0334 |
| `lab_K_pre_24h_signed_hours_from_ecg` | 164,810 | 0.3293 |
| `lab_K_post_24h_signed_hours_from_ecg` | 89,091 | 0.1780 |
| `lab_K_pm6h_signed_hours_from_ecg` | 105,042 | 0.2099 |
| `lab_K_pm12h_signed_hours_from_ecg` | 32,130 | 0.0642 |
| `lab_Na_pm24h_signed_hours_from_ecg` | 19,565 | 0.0391 |
| `lab_Na_pre_24h_signed_hours_from_ecg` | 166,636 | 0.3330 |
| `lab_Na_post_24h_signed_hours_from_ecg` | 93,489 | 0.1868 |
| `lab_Na_pm6h_signed_hours_from_ecg` | 109,871 | 0.2195 |
| `lab_Na_pm12h_signed_hours_from_ecg` | 35,458 | 0.0708 |
| `lab_creatinine_pm24h_signed_hours_from_ecg` | 17,093 | 0.0342 |
| `lab_creatinine_pre_24h_signed_hours_from_ecg` | 165,628 | 0.3309 |
| `lab_creatinine_post_24h_signed_hours_from_ecg` | 92,515 | 0.1849 |
| `lab_creatinine_pm6h_signed_hours_from_ecg` | 111,846 | 0.2235 |
| `lab_creatinine_pm12h_signed_hours_from_ecg` | 35,803 | 0.0715 |
| `lab_troponin_pm24h_signed_hours_from_ecg` | 260,608 | 0.5207 |
| `lab_troponin_pre_24h_signed_hours_from_ecg` | 364,084 | 0.7275 |
| `lab_troponin_post_24h_signed_hours_from_ecg` | 321,028 | 0.6415 |
| `lab_troponin_pm6h_signed_hours_from_ecg` | 297,919 | 0.5953 |
| `lab_troponin_pm12h_signed_hours_from_ecg` | 278,772 | 0.5570 |
| `lab_lactate_pm24h_signed_hours_from_ecg` | 330,646 | 0.6607 |
| `lab_lactate_pre_24h_signed_hours_from_ecg` | 407,748 | 0.8147 |
| `lab_lactate_post_24h_signed_hours_from_ecg` | 386,832 | 0.7729 |
| `lab_lactate_pm6h_signed_hours_from_ecg` | 374,969 | 0.7492 |
| `lab_lactate_pm12h_signed_hours_from_ecg` | 354,669 | 0.7087 |
| `lab_Ca_pm24h_signed_hours_from_ecg` | 123,090 | 0.2459 |
| `lab_Ca_pre_24h_signed_hours_from_ecg` | 267,514 | 0.5345 |
| `lab_Ca_post_24h_signed_hours_from_ecg` | 171,336 | 0.3423 |
| `lab_Ca_pm6h_signed_hours_from_ecg` | 259,690 | 0.5189 |
| `lab_Ca_pm12h_signed_hours_from_ecg` | 179,304 | 0.3583 |
| `lab_Mg_pm24h_signed_hours_from_ecg` | 115,288 | 0.2304 |
| `lab_Mg_pre_24h_signed_hours_from_ecg` | 266,867 | 0.5332 |
| `lab_Mg_post_24h_signed_hours_from_ecg` | 161,601 | 0.3229 |
| `lab_Mg_pm6h_signed_hours_from_ecg` | 259,761 | 0.5190 |
| `lab_Mg_pm12h_signed_hours_from_ecg` | 172,709 | 0.3451 |


## `A4_event_localization`

Cohort rule: §4.A.4.2 as amended by §4 decision 10. Heads: 1 (peak_seq).

| split | rows | unique `study_id` | subjects | primary rows | primary subjects |
| --- | --- | --- | --- | --- | --- |
| train | 523,945 | 523,945 | 107,851 | 192,082 | 65,853 |
| val | 75,525 | 75,525 | 15,397 | 27,823 | 9,382 |
| test | 149,642 | 149,642 | 30,844 | 55,140 | 18,792 |
| **all** | **749,112** | **749,112** | **154,092** | **275,045** |  |

| breakdown | counts over all three splits |
| --- | --- |
| `link_tier` | L3 422,147 · L1 234,511 · L2 78,324 · L0 14,130 |
| `sqi_tier` | medium 460,963 · low 283,983 · high 4,166 |
| `cart_id` | 6632385 68,718 · 6848296 34,424 · 6672155 33,152 · 6752764 32,854 · 6097533 27,449  (top 5 of 156) |


**Per-head class counts and prevalence** (`n` is the rows the head is scored on after its mask; prevalence is within that slice).

| head | split | n scored | counts | prevalence | null |
| --- | --- | --- | --- | --- | --- |
| fiducials | train | 523,945 | peak_seq | (sequence / span target) | 0 |
| fiducials | val | 75,525 | peak_seq | (sequence / span target) | 0 |
| fiducials | test | 149,642 | peak_seq | (sequence / span target) | 0 |


**Missingness** (columns with at least one null, over all three splits). Nulls in a label column are only legitimate where a mask column declares the row out of scope; the `mask_implies_label` checks above are what enforce that.

| column | nulls | fraction |
| --- | --- | --- |
| (none) | 0 | 0.0000 |


## `A5_cross_modal_verification`

Cohort rule: §4.A.5.2 — every clean-cohort ECG, 2 positives + 5 negatives. Heads: 4 (binary, multiclass).

| split | rows | unique `anchor_study_id` | subjects | primary rows | primary subjects |
| --- | --- | --- | --- | --- | --- |
| train | 3,667,615 | 523,945 | 107,851 | 3,667,615 | 107,851 |
| val | 528,675 | 75,525 | 15,397 | 528,675 | 15,397 |
| test | 1,047,494 | 149,642 | 30,844 | 1,047,494 | 30,844 |
| **all** | **5,243,784** | **749,112** | **154,092** | **5,243,784** |  |

| breakdown | counts over all three splits |
| --- | --- |
| `link_tier` | (not in this task's schema) |
| `sqi_tier` | (not in this task's schema) |
| `cart_id` | (not in this task's schema) |


**Per-head class counts and prevalence** (`n` is the rows the head is scored on after its mask; prevalence is within that slice).

| head | split | n scored | counts | prevalence | null |
| --- | --- | --- | --- | --- | --- |
| y_match | train | 3,667,615 | positive 1,047,890 · negative 2,619,725 | positive 0.2857 · negative 0.7143 | 0 |
| y_match | val | 528,675 | positive 151,050 · negative 377,625 | positive 0.2857 · negative 0.7143 | 0 |
| y_match | test | 1,047,494 | positive 299,284 · negative 748,210 | positive 0.2857 · negative 0.7143 | 0 |
| hr_label | train | 2,093,856 | bradycardia 314,228 · normal 1,490,360 · tachycardia 289,268 | bradycardia 0.1501 · normal 0.7118 · tachycardia 0.1382 | 0 |
| hr_label | val | 301,776 | bradycardia 45,352 · normal 214,532 · tachycardia 41,892 | bradycardia 0.1503 · normal 0.7109 · tachycardia 0.1388 | 0 |
| hr_label | test | 598,184 | bradycardia 89,256 · normal 425,440 · tachycardia 83,488 | bradycardia 0.1492 · normal 0.7112 · tachycardia 0.1396 | 0 |
| qrs_label | train | 2,093,856 | normal 1,345,528 · borderline 401,324 · wide 347,004 | normal 0.6426 · borderline 0.1917 · wide 0.1657 | 0 |
| qrs_label | val | 301,776 | normal 195,208 · borderline 57,212 · wide 49,356 | normal 0.6469 · borderline 0.1896 · wide 0.1636 | 0 |
| qrs_label | test | 598,184 | normal 385,456 · borderline 114,828 · wide 97,900 | normal 0.6444 · borderline 0.1920 · wide 0.1637 | 0 |
| qtc_label | train | 2,093,856 | short 2,152 · normal 1,233,288 · prolonged 858,416 | short 0.0010 · normal 0.5890 · prolonged 0.4100 | 0 |
| qtc_label | val | 301,776 | short 204 · normal 179,676 · prolonged 121,896 | short 0.0007 · normal 0.5954 · prolonged 0.4039 | 0 |
| qtc_label | test | 598,184 | short 524 · normal 354,960 · prolonged 242,700 | short 0.0009 · normal 0.5934 · prolonged 0.4057 | 0 |


**Missingness** (columns with at least one null, over all three splits). Nulls in a label column are only legitimate where a mask column declares the row out of scope; the `mask_implies_label` checks above are what enforce that.

| column | nulls | fraction |
| --- | --- | --- |
| `neg_type` | 1,498,224 | 0.2857 |
| `hr_label` | 4,606 | 0.0009 |
| `qrs_label` | 4,606 | 0.0009 |
| `qtc_label` | 4,606 | 0.0009 |


## `A6_risk_stratification`

Cohort rule: §4.A.6.2. Heads: 4 (binary).

| split | rows | unique `study_id` | subjects | primary rows | primary subjects |
| --- | --- | --- | --- | --- | --- |
| train | 350,203 | 350,203 | 87,255 | 295,236 | 80,431 |
| val | 50,240 | 50,240 | 12,445 | 42,563 | 11,475 |
| test | 100,028 | 100,028 | 24,902 | 84,348 | 22,953 |
| **all** | **500,471** | **500,471** | **124,602** | **422,147** |  |

| breakdown | counts over all three splits |
| --- | --- |
| `link_tier` | L3 422,147 · L2 78,324 |
| `sqi_tier` | medium 321,073 · low 175,791 · high 3,607 |
| `cart_id` | 6632385 67,713 · 6672155 29,899 · 6752764 28,731 · 6848296 27,375 · 6903271 22,710  (top 5 of 154) |


**Per-head class counts and prevalence** (`n` is the rows the head is scored on after its mask; prevalence is within that slice).

| head | split | n scored | counts | prevalence | null |
| --- | --- | --- | --- | --- | --- |
| mortality_30d | train | 321,470 | positive 22,370 · negative 299,100 | positive 0.0696 · negative 0.9304 | 0 |
| mortality_30d | val | 46,041 | positive 3,250 · negative 42,791 | positive 0.0706 · negative 0.9294 | 0 |
| mortality_30d | test | 91,887 | positive 6,402 · negative 85,485 | positive 0.0697 · negative 0.9303 | 0 |
| mortality_90d | train | 321,470 | positive 37,134 · negative 284,336 | positive 0.1155 · negative 0.8845 | 0 |
| mortality_90d | val | 46,041 | positive 5,354 · negative 40,687 | positive 0.1163 · negative 0.8837 | 0 |
| mortality_90d | test | 91,887 | positive 10,604 · negative 81,283 | positive 0.1154 · negative 0.8846 | 0 |
| readmission_30d | train | 316,742 | positive 66,718 · negative 250,024 | positive 0.2106 · negative 0.7894 | 0 |
| readmission_30d | val | 45,450 | positive 9,456 · negative 35,994 | positive 0.2081 · negative 0.7919 | 0 |
| readmission_30d | test | 90,537 | positive 19,047 · negative 71,490 | positive 0.2104 · negative 0.7896 | 0 |
| readmission_90d | train | 316,742 | positive 103,406 · negative 213,336 | positive 0.3265 · negative 0.6735 | 0 |
| readmission_90d | val | 45,450 | positive 14,680 · negative 30,770 | positive 0.3230 · negative 0.6770 | 0 |
| readmission_90d | test | 90,537 | positive 29,377 · negative 61,160 | positive 0.3245 · negative 0.6755 | 0 |


**Missingness** (columns with at least one null, over all three splits). Nulls in a label column are only legitimate where a mask column declares the row out of scope; the `mask_implies_label` checks above are what enforce that.

| column | nulls | fraction |
| --- | --- | --- |
| `hadm_id` | 47,723 | 0.0954 |
| `readmission_30d` | 47,742 | 0.0954 |
| `readmission_90d` | 47,742 | 0.0954 |
| `days_to_death` | 318,379 | 0.6362 |
| `days_to_readmission` | 210,829 | 0.4213 |
| `followup_days_after_discharge` | 47,742 | 0.0954 |
| `next_admission_type` | 210,829 | 0.4213 |
| `next_admission_location` | 210,829 | 0.4213 |


## `B1_measurement_blind`

Cohort rule: §4.B.1.2 — the full clean cohort. Heads: 3 (multiclass).

| split | rows | unique `study_id` | subjects | primary rows | primary subjects |
| --- | --- | --- | --- | --- | --- |
| train | 523,464 | 523,464 | 107,841 | 523,464 | 107,841 |
| val | 75,444 | 75,444 | 15,395 | 75,444 | 15,395 |
| test | 149,546 | 149,546 | 30,843 | 149,546 | 30,843 |
| **all** | **748,454** | **748,454** | **154,079** | **748,454** |  |

| breakdown | counts over all three splits |
| --- | --- |
| `link_tier` | L3 421,755 · L1 234,311 · L2 78,262 · L0 14,126 |
| `sqi_tier` | medium 460,659 · low 283,630 · high 4,165 |
| `cart_id` | 6632385 68,698 · 6848296 34,399 · 6672155 33,130 · 6752764 32,841 · 6097533 27,439  (top 5 of 156) |


**Per-head class counts and prevalence** (`n` is the rows the head is scored on after its mask; prevalence is within that slice).

| head | split | n scored | counts | prevalence | null |
| --- | --- | --- | --- | --- | --- |
| hr_label | train | 523,464 | bradycardia 78,557 · normal 372,590 · tachycardia 72,317 | bradycardia 0.1501 · normal 0.7118 · tachycardia 0.1382 | 0 |
| hr_label | val | 75,444 | bradycardia 11,338 · normal 53,633 · tachycardia 10,473 | bradycardia 0.1503 · normal 0.7109 · tachycardia 0.1388 | 0 |
| hr_label | test | 149,546 | bradycardia 22,314 · normal 106,360 · tachycardia 20,872 | bradycardia 0.1492 · normal 0.7112 · tachycardia 0.1396 | 0 |
| qrs_label | train | 523,464 | normal 336,382 · borderline 100,331 · wide 86,751 | normal 0.6426 · borderline 0.1917 · wide 0.1657 | 0 |
| qrs_label | val | 75,444 | normal 48,802 · borderline 14,303 · wide 12,339 | normal 0.6469 · borderline 0.1896 · wide 0.1636 | 0 |
| qrs_label | test | 149,546 | normal 96,364 · borderline 28,707 · wide 24,475 | normal 0.6444 · borderline 0.1920 · wide 0.1637 | 0 |
| qtc_label | train | 523,464 | short 538 · normal 308,322 · prolonged 214,604 | short 0.0010 · normal 0.5890 · prolonged 0.4100 | 0 |
| qtc_label | val | 75,444 | short 51 · normal 44,919 · prolonged 30,474 | short 0.0007 · normal 0.5954 · prolonged 0.4039 | 0 |
| qtc_label | test | 149,546 | short 131 · normal 88,740 · prolonged 60,675 | short 0.0009 · normal 0.5934 · prolonged 0.4057 | 0 |


**Missingness** (columns with at least one null, over all three splits). Nulls in a label column are only legitimate where a mask column declares the row out of scope; the `mask_implies_label` checks above are what enforce that.

| column | nulls | fraction |
| --- | --- | --- |
| `qtc_ms_bazett` | 92,503 | 0.1236 |


## `B2_noise_robustness`

Cohort rule: §4.B.2.2 — the frozen Stage 8 corruption set. Heads: 3 (multiclass).

| split | rows | unique `study_id` | subjects | primary rows | primary subjects |
| --- | --- | --- | --- | --- | --- |
| train | 523,464 | 523,464 | 107,841 | 523,464 | 107,841 |
| val | 75,444 | 75,444 | 15,395 | 75,444 | 15,395 |
| test | 301,097 | 149,546 | 30,843 | 301,097 | 30,843 |
| **all** | **900,005** | **748,454** | **154,079** | **900,005** |  |

| breakdown | counts over all three splits |
| --- | --- |
| `link_tier` | (not in this task's schema) |
| `sqi_tier` | medium 551,298 · low 343,894 · high 4,813 |
| `cart_id` | (not in this task's schema) |


**Per-head class counts and prevalence** (`n` is the rows the head is scored on after its mask; prevalence is within that slice).

| head | split | n scored | counts | prevalence | null |
| --- | --- | --- | --- | --- | --- |
| hr_label | train | 523,464 | bradycardia 78,557 · normal 372,590 · tachycardia 72,317 | bradycardia 0.1501 · normal 0.7118 · tachycardia 0.1382 | 0 |
| hr_label | val | 75,444 | bradycardia 11,338 · normal 53,633 · tachycardia 10,473 | bradycardia 0.1503 · normal 0.7109 · tachycardia 0.1388 | 0 |
| hr_label | test | 301,097 | bradycardia 45,318 · normal 214,981 · tachycardia 40,798 | bradycardia 0.1505 · normal 0.7140 · tachycardia 0.1355 | 0 |
| qrs_label | train | 523,464 | normal 336,382 · borderline 100,331 · wide 86,751 | normal 0.6426 · borderline 0.1917 · wide 0.1657 | 0 |
| qrs_label | val | 75,444 | normal 48,802 · borderline 14,303 · wide 12,339 | normal 0.6469 · borderline 0.1896 · wide 0.1636 | 0 |
| qrs_label | test | 301,097 | normal 192,430 · borderline 60,054 · wide 48,613 | normal 0.6391 · borderline 0.1995 · wide 0.1615 | 0 |
| qtc_label | train | 523,464 | short 538 · normal 308,322 · prolonged 214,604 | short 0.0010 · normal 0.5890 · prolonged 0.4100 | 0 |
| qtc_label | val | 75,444 | short 51 · normal 44,919 · prolonged 30,474 | short 0.0007 · normal 0.5954 · prolonged 0.4039 | 0 |
| qtc_label | test | 301,097 | short 536 · normal 176,868 · prolonged 123,693 | short 0.0018 · normal 0.5874 · prolonged 0.4108 | 0 |


**Missingness** (columns with at least one null, over all three splits). Nulls in a label column are only legitimate where a mask column declares the row out of scope; the `mask_implies_label` checks above are what enforce that.

| column | nulls | fraction |
| --- | --- | --- |
| `corrupted_signal_kind` | 151,417 | 0.1682 |
| `corruption_type` | 750,325 | 0.8337 |


## `B3_temporal_grounding`

Cohort rule: §4.B.3.2 — the full clean cohort x 4 queries. Heads: 1 (bins).

| split | rows | unique `study_id` | subjects | primary rows | primary subjects |
| --- | --- | --- | --- | --- | --- |
| train | 2,095,780 | 523,945 | 107,851 | 2,095,780 | 107,851 |
| val | 302,100 | 75,525 | 15,397 | 302,100 | 15,397 |
| test | 598,568 | 149,642 | 30,844 | 598,568 | 30,844 |
| **all** | **2,996,448** | **749,112** | **154,092** | **2,996,448** |  |

| breakdown | counts over all three splits |
| --- | --- |
| `link_tier` | L3 1,688,588 · L1 938,044 · L2 313,296 · L0 56,520 |
| `sqi_tier` | medium 1,843,852 · low 1,135,932 · high 16,664 |
| `cart_id` | 6632385 274,872 · 6848296 137,696 · 6672155 132,608 · 6752764 131,416 · 6097533 109,796  (top 5 of 156) |


**Per-head class counts and prevalence** (`n` is the rows the head is scored on after its mask; prevalence is within that slice).

| head | split | n scored | counts | prevalence | null |
| --- | --- | --- | --- | --- | --- |
| bins | train | 2,095,780 | bins | (sequence / span target) | 0 |
| bins | val | 302,100 | bins | (sequence / span target) | 0 |
| bins | test | 598,568 | bins | (sequence / span target) | 0 |


**Missingness** (columns with at least one null, over all three splits). Nulls in a label column are only legitimate where a mask column declares the row out of scope; the `mask_implies_label` checks above are what enforce that.

| column | nulls | fraction |
| --- | --- | --- |
| (none) | 0 | 0.0000 |


## `B4_cross_modal_verification`

Cohort rule: §4.B.4.2 — identical rows to A5 (§4.B.4.8). Heads: 1 (binary).

| split | rows | unique `anchor_study_id` | subjects | primary rows | primary subjects |
| --- | --- | --- | --- | --- | --- |
| train | 3,667,615 | 523,945 | 107,851 | 3,667,615 | 107,851 |
| val | 528,675 | 75,525 | 15,397 | 528,675 | 15,397 |
| test | 1,047,494 | 149,642 | 30,844 | 1,047,494 | 30,844 |
| **all** | **5,243,784** | **749,112** | **154,092** | **5,243,784** |  |

| breakdown | counts over all three splits |
| --- | --- |
| `link_tier` | (not in this task's schema) |
| `sqi_tier` | (not in this task's schema) |
| `cart_id` | (not in this task's schema) |


**Per-head class counts and prevalence** (`n` is the rows the head is scored on after its mask; prevalence is within that slice).

| head | split | n scored | counts | prevalence | null |
| --- | --- | --- | --- | --- | --- |
| y_match | train | 3,667,615 | positive 1,047,890 · negative 2,619,725 | positive 0.2857 · negative 0.7143 | 0 |
| y_match | val | 528,675 | positive 151,050 · negative 377,625 | positive 0.2857 · negative 0.7143 | 0 |
| y_match | test | 1,047,494 | positive 299,284 · negative 748,210 | positive 0.2857 · negative 0.7143 | 0 |


**Missingness** (columns with at least one null, over all three splits). Nulls in a label column are only legitimate where a mask column declares the row out of scope; the `mask_implies_label` checks above are what enforce that.

| column | nulls | fraction |
| --- | --- | --- |
| `neg_type` | 1,498,224 | 0.2857 |


## `B5_contradiction_detection`

Cohort rule: §4.B.5.2 as amended by §4 decisions 11 and 17. Heads: 3 (binary, multiclass, span).

| split | rows | unique `study_id` | subjects | primary rows | primary subjects |
| --- | --- | --- | --- | --- | --- |
| train | 89,842 | 89,842 | 26,776 | 89,842 | 26,776 |
| val | 12,941 | 12,941 | 3,900 | 12,941 | 3,900 |
| test | 25,870 | 25,870 | 7,746 | 25,870 | 7,746 |
| **all** | **128,653** | **128,653** | **38,422** | **128,653** |  |

| breakdown | counts over all three splits |
| --- | --- |
| `link_tier` | L3 76,714 · L1 36,840 · L2 13,883 · L0 1,216 |
| `sqi_tier` | medium 73,196 · low 54,314 · high 1,143 |
| `cart_id` | 6632385 10,507 · 6672155 5,325 · 6848296 5,189 · 6752764 4,843 · 6734107 4,000  (top 5 of 154) |


**Per-head class counts and prevalence** (`n` is the rows the head is scored on after its mask; prevalence is within that slice).

| head | split | n scored | counts | prevalence | null |
| --- | --- | --- | --- | --- | --- |
| is_corrupted | train | 89,842 | positive 44,669 · negative 45,173 | positive 0.4972 · negative 0.5028 | 0 |
| is_corrupted | val | 12,941 | positive 6,512 · negative 6,429 | positive 0.5032 · negative 0.4968 | 0 |
| is_corrupted | test | 25,870 | positive 13,039 · negative 12,831 | positive 0.5040 · negative 0.4960 | 0 |
| label | train | 89,842 | clean 45,173 · corrupted_HR 12,359 · corrupted_QRS 14,404 · corrupted_axis 14,239 · corrupted_PR 3,667 | clean 0.5028 · corrupted_HR 0.1376 · corrupted_QRS 0.1603 · corrupted_axis 0.1585 · corrupted_PR 0.0408 | 0 |
| label | val | 12,941 | clean 6,429 · corrupted_HR 1,863 · corrupted_QRS 2,079 · corrupted_axis 1,944 · corrupted_PR 626 | clean 0.4968 · corrupted_HR 0.1440 · corrupted_QRS 0.1607 · corrupted_axis 0.1502 · corrupted_PR 0.0484 | 0 |
| label | test | 25,870 | clean 12,831 · corrupted_HR 3,644 · corrupted_QRS 4,265 · corrupted_axis 4,047 · corrupted_PR 1,083 | clean 0.4960 · corrupted_HR 0.1409 · corrupted_QRS 0.1649 · corrupted_axis 0.1564 · corrupted_PR 0.0419 | 0 |
| span | train | 44,669 | span | (sequence / span target) | 0 |
| span | val | 6,512 | span | (sequence / span target) | 0 |
| span | test | 13,039 | span | (sequence / span target) | 0 |


**Missingness** (columns with at least one null, over all three splits). Nulls in a label column are only legitimate where a mask column declares the row out of scope; the `mask_implies_label` checks above are what enforce that.

| column | nulls | fraction |
| --- | --- | --- |
| `contradiction_type` | 64,433 | 0.5008 |
| `contradiction_family` | 64,433 | 0.5008 |
| `corrupted_report_text` | 64,433 | 0.5008 |
| `corrupted_span_start` | 64,433 | 0.5008 |
| `corrupted_span_end` | 64,433 | 0.5008 |
| `source_measurement` | 64,433 | 0.5008 |


## `B6_difficulty_stratified`

Cohort rule: §4.B.6.2 — a pointer table over B4's rows. Heads: 1 (binary).

An evaluation-time stratification of `B4_cross_modal_verification` (§4.B.6.2 — a pointer table over B4's rows): the table points at rows, it does not own labels. `y_match` is read from the base task's prediction file at eval time.

| split | pointer rows | `B4_cross_modal_verification` rows | match |
| --- | --- | --- | --- |
| train | 3,667,615 | 3,667,615 | yes |
| val | 528,675 | 528,675 | yes |
| test | 1,047,494 | 1,047,494 | yes |

| difficulty_tier | neg_type | rows |
| --- | --- | --- |
| easy | IMAGE_SWAP | 749,112 |
| easy | PARTIAL_MISMATCH | 749,112 |
| easy | SIGNAL_SWAP | 749,112 |
| easy | TEXT_SWAP | 749,112 |
| medium | HARD_NEGATIVE_TEXT | 749,112 |
| positive | (positive row) | 1,498,224 |


Subjects: 154,092. Splits: train 3,667,615 · test 1,047,494 · val 528,675.


### B2 — the frozen corruption grid

§4.B.2.3 locks 8 corruption families x 5 SNR levels. The builder attaches labels to Phase 1's frozen rows and generates nothing, so a missing cell here means rows were dropped, not that a corruption was never made.

| corruption_type | snr_db | rows |
| --- | --- | --- |
| baseline_wander | 0 | 3,742 |
| baseline_wander | 5 | 3,742 |
| baseline_wander | 10 | 3,742 |
| baseline_wander | 20 | 3,742 |
| baseline_wander | 30 | 3,742 |
| electrode_motion | 0 | 3,742 |
| electrode_motion | 5 | 3,742 |
| electrode_motion | 10 | 3,742 |
| electrode_motion | 20 | 3,742 |
| electrode_motion | 30 | 3,742 |
| emg | 0 | 3,742 |
| emg | 5 | 3,742 |
| emg | 10 | 3,742 |
| emg | 20 | 3,742 |
| emg | 30 | 3,742 |
| gain_drift | 0 | 3,742 |
| gain_drift | 5 | 3,742 |
| gain_drift | 10 | 3,742 |
| gain_drift | 20 | 3,742 |
| gain_drift | 30 | 3,742 |
| gaussian | 0 | 3,742 |
| gaussian | 5 | 3,742 |
| gaussian | 10 | 3,742 |
| gaussian | 20 | 3,742 |
| gaussian | 30 | 3,742 |
| lead_dropout | 0 | 3,742 |
| lead_dropout | 5 | 3,742 |
| lead_dropout | 10 | 3,742 |
| lead_dropout | 20 | 3,742 |
| lead_dropout | 30 | 3,742 |
| powerline | 0 | 3,742 |
| powerline | 5 | 3,742 |
| powerline | 10 | 3,742 |
| powerline | 20 | 3,742 |
| powerline | 30 | 3,742 |
| saturation | 0 | 3,742 |
| saturation | 5 | 3,742 |
| saturation | 10 | 3,742 |
| saturation | 20 | 3,742 |
| saturation | 30 | 3,742 |

| regime | row_role | rows |
| --- | --- | --- |
| regime_1 | clean_reference | 1,871 |
| regime_1 | corrupted | 74,840 |
| regime_2 | augment_on_the_fly | 598,908 |
| regime_2 | corrupted | 74,840 |
| regime_3 | natural | 149,546 |


### A5 / B4 — row equality

| task | train | val | test |
| --- | --- | --- | --- |
| `A5_cross_modal_verification` | 3,667,615 | 528,675 | 1,047,494 |
| `B4_cross_modal_verification` | 3,667,615 | 528,675 | 1,047,494 |


## Every check, in the order it ran

| # | Task | Check | Verdict | Measured |
| ---: | --- | --- | --- | --- |
| 1 | `A1_ecg_diagnosis` | `all_three_splits_present` | PASS | read ['test', 'train', 'val'] |
| 2 | `A1_ecg_diagnosis` | `cohort_non_empty` | PASS | 500,277 rows over 124,547 subjects |
| 3 | `A1_ecg_diagnosis` | `row_key_unique` | PASS | key ['study_id']: 0 duplicate row(s) across the three splits |
| 4 | `A1_ecg_diagnosis` | `subgroup_columns_present` | PASS | every subgroup column `task_spec` declares is on the rows |
| 5 | `A1_ecg_diagnosis` | `primary_cohort_link_tier` | PASS | primary rows carry link_tier ['L3'], §4.A.1.2 allows ['L3'] |
| 6 | `A1_ecg_diagnosis` | `head_metric_computable[label_atrial_fibrillation_flutter]` | PASS | at least two label values present in every split |
| 7 | `A1_ecg_diagnosis` | `head_metric_computable[label_heart_failure_narrow]` | PASS | at least two label values present in every split |
| 8 | `A1_ecg_diagnosis` | `head_metric_computable[label_acute_myocardial_infarction]` | PASS | at least two label values present in every split |
| 9 | `A1_ecg_diagnosis` | `head_metric_computable[label_conduction_disorder]` | PASS | at least two label values present in every split |
| 10 | `A1_ecg_diagnosis` | `head_metric_computable[label_ventricular_arrhythmia_or_arrest]` | PASS | at least two label values present in every split |
| 11 | `A2_measurement_blind` | `all_three_splits_present` | PASS | read ['test', 'train', 'val'] |
| 12 | `A2_measurement_blind` | `cohort_non_empty` | PASS | 500,017 rows over 124,584 subjects |
| 13 | `A2_measurement_blind` | `row_key_unique` | PASS | key ['study_id']: 0 duplicate row(s) across the three splits |
| 14 | `A2_measurement_blind` | `subgroup_columns_present` | PASS | every subgroup column `task_spec` declares is on the rows |
| 15 | `A2_measurement_blind` | `primary_cohort_link_tier` | PASS | primary rows carry link_tier ['L3'], §4.A.2.2 as amended by §4 decision 10 allows ['L3'] |
| 16 | `A2_measurement_blind` | `primary_cohort_sqi_tier` | PASS | primary rows carry sqi_tier ['high', 'medium'], §4.A.2.2 as amended by §4 decision 10 allows ['high', 'medium'] |
| 17 | `A2_measurement_blind` | `locked_cohort_size` | PASS | measured 275,088 primary rows against the locked 275,088 |
| 18 | `A2_measurement_blind` | `head_metric_computable[hr_label]` | PASS | at least two label values present in every split |
| 19 | `A2_measurement_blind` | `label_vocabulary[hr_label]` | PASS | every value is one of ['bradycardia', 'normal', 'tachycardia'] |
| 20 | `A2_measurement_blind` | `head_metric_computable[qrs_label]` | PASS | at least two label values present in every split |
| 21 | `A2_measurement_blind` | `label_vocabulary[qrs_label]` | PASS | every value is one of ['normal', 'borderline', 'wide'] |
| 22 | `A2_measurement_blind` | `head_metric_computable[qtc_label]` | PASS | at least two label values present in every split |
| 23 | `A2_measurement_blind` | `label_vocabulary[qtc_label]` | PASS | every value is one of ['short', 'normal', 'prolonged'] |
| 24 | `A3_lab_abnormality` | `all_three_splits_present` | PASS | read ['test', 'train', 'val'] |
| 25 | `A3_lab_abnormality` | `cohort_non_empty` | PASS | 500,471 rows over 124,602 subjects |
| 26 | `A3_lab_abnormality` | `row_key_unique` | PASS | key ['study_id']: 0 duplicate row(s) across the three splits |
| 27 | `A3_lab_abnormality` | `subgroup_columns_present` | PASS | every subgroup column `task_spec` declares is on the rows |
| 28 | `A3_lab_abnormality` | `primary_cohort_link_tier` | PASS | primary rows carry link_tier ['L3'], §4.A.3.2 allows ['L3'] |
| 29 | `A3_lab_abnormality` | `head_metric_computable[lab_K_pm24h]` | PASS | at least two label values present in every split |
| 30 | `A3_lab_abnormality` | `label_vocabulary[lab_K_pm24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 31 | `A3_lab_abnormality` | `head_metric_computable[lab_K_pre_24h]` | PASS | at least two label values present in every split |
| 32 | `A3_lab_abnormality` | `label_vocabulary[lab_K_pre_24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 33 | `A3_lab_abnormality` | `head_metric_computable[lab_K_post_24h]` | PASS | at least two label values present in every split |
| 34 | `A3_lab_abnormality` | `label_vocabulary[lab_K_post_24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 35 | `A3_lab_abnormality` | `head_metric_computable[lab_K_pm6h]` | PASS | at least two label values present in every split |
| 36 | `A3_lab_abnormality` | `label_vocabulary[lab_K_pm6h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 37 | `A3_lab_abnormality` | `head_metric_computable[lab_K_pm12h]` | PASS | at least two label values present in every split |
| 38 | `A3_lab_abnormality` | `label_vocabulary[lab_K_pm12h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 39 | `A3_lab_abnormality` | `head_metric_computable[lab_Na_pm24h]` | PASS | at least two label values present in every split |
| 40 | `A3_lab_abnormality` | `label_vocabulary[lab_Na_pm24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 41 | `A3_lab_abnormality` | `head_metric_computable[lab_Na_pre_24h]` | PASS | at least two label values present in every split |
| 42 | `A3_lab_abnormality` | `label_vocabulary[lab_Na_pre_24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 43 | `A3_lab_abnormality` | `head_metric_computable[lab_Na_post_24h]` | PASS | at least two label values present in every split |
| 44 | `A3_lab_abnormality` | `label_vocabulary[lab_Na_post_24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 45 | `A3_lab_abnormality` | `head_metric_computable[lab_Na_pm6h]` | PASS | at least two label values present in every split |
| 46 | `A3_lab_abnormality` | `label_vocabulary[lab_Na_pm6h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 47 | `A3_lab_abnormality` | `head_metric_computable[lab_Na_pm12h]` | PASS | at least two label values present in every split |
| 48 | `A3_lab_abnormality` | `label_vocabulary[lab_Na_pm12h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 49 | `A3_lab_abnormality` | `head_metric_computable[lab_creatinine_pm24h]` | PASS | at least two label values present in every split |
| 50 | `A3_lab_abnormality` | `label_vocabulary[lab_creatinine_pm24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 51 | `A3_lab_abnormality` | `head_metric_computable[lab_creatinine_pre_24h]` | PASS | at least two label values present in every split |
| 52 | `A3_lab_abnormality` | `label_vocabulary[lab_creatinine_pre_24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 53 | `A3_lab_abnormality` | `head_metric_computable[lab_creatinine_post_24h]` | PASS | at least two label values present in every split |
| 54 | `A3_lab_abnormality` | `label_vocabulary[lab_creatinine_post_24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 55 | `A3_lab_abnormality` | `head_metric_computable[lab_creatinine_pm6h]` | PASS | at least two label values present in every split |
| 56 | `A3_lab_abnormality` | `label_vocabulary[lab_creatinine_pm6h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 57 | `A3_lab_abnormality` | `head_metric_computable[lab_creatinine_pm12h]` | PASS | at least two label values present in every split |
| 58 | `A3_lab_abnormality` | `label_vocabulary[lab_creatinine_pm12h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 59 | `A3_lab_abnormality` | `head_metric_computable[lab_troponin_pm24h]` | PASS | at least two label values present in every split |
| 60 | `A3_lab_abnormality` | `label_vocabulary[lab_troponin_pm24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 61 | `A3_lab_abnormality` | `head_metric_computable[lab_troponin_pre_24h]` | PASS | at least two label values present in every split |
| 62 | `A3_lab_abnormality` | `label_vocabulary[lab_troponin_pre_24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 63 | `A3_lab_abnormality` | `head_metric_computable[lab_troponin_post_24h]` | PASS | at least two label values present in every split |
| 64 | `A3_lab_abnormality` | `label_vocabulary[lab_troponin_post_24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 65 | `A3_lab_abnormality` | `head_metric_computable[lab_troponin_pm6h]` | PASS | at least two label values present in every split |
| 66 | `A3_lab_abnormality` | `label_vocabulary[lab_troponin_pm6h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 67 | `A3_lab_abnormality` | `head_metric_computable[lab_troponin_pm12h]` | PASS | at least two label values present in every split |
| 68 | `A3_lab_abnormality` | `label_vocabulary[lab_troponin_pm12h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 69 | `A3_lab_abnormality` | `head_metric_computable[lab_lactate_pm24h]` | PASS | at least two label values present in every split |
| 70 | `A3_lab_abnormality` | `label_vocabulary[lab_lactate_pm24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 71 | `A3_lab_abnormality` | `head_metric_computable[lab_lactate_pre_24h]` | PASS | at least two label values present in every split |
| 72 | `A3_lab_abnormality` | `label_vocabulary[lab_lactate_pre_24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 73 | `A3_lab_abnormality` | `head_metric_computable[lab_lactate_post_24h]` | PASS | at least two label values present in every split |
| 74 | `A3_lab_abnormality` | `label_vocabulary[lab_lactate_post_24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 75 | `A3_lab_abnormality` | `head_metric_computable[lab_lactate_pm6h]` | PASS | at least two label values present in every split |
| 76 | `A3_lab_abnormality` | `label_vocabulary[lab_lactate_pm6h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 77 | `A3_lab_abnormality` | `head_metric_computable[lab_lactate_pm12h]` | PASS | at least two label values present in every split |
| 78 | `A3_lab_abnormality` | `label_vocabulary[lab_lactate_pm12h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 79 | `A3_lab_abnormality` | `head_metric_computable[lab_Ca_pm24h]` | PASS | at least two label values present in every split |
| 80 | `A3_lab_abnormality` | `label_vocabulary[lab_Ca_pm24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 81 | `A3_lab_abnormality` | `head_metric_computable[lab_Ca_pre_24h]` | PASS | at least two label values present in every split |
| 82 | `A3_lab_abnormality` | `label_vocabulary[lab_Ca_pre_24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 83 | `A3_lab_abnormality` | `head_metric_computable[lab_Ca_post_24h]` | PASS | at least two label values present in every split |
| 84 | `A3_lab_abnormality` | `label_vocabulary[lab_Ca_post_24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 85 | `A3_lab_abnormality` | `head_metric_computable[lab_Ca_pm6h]` | PASS | at least two label values present in every split |
| 86 | `A3_lab_abnormality` | `label_vocabulary[lab_Ca_pm6h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 87 | `A3_lab_abnormality` | `head_metric_computable[lab_Ca_pm12h]` | PASS | at least two label values present in every split |
| 88 | `A3_lab_abnormality` | `label_vocabulary[lab_Ca_pm12h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 89 | `A3_lab_abnormality` | `head_metric_computable[lab_Mg_pm24h]` | PASS | at least two label values present in every split |
| 90 | `A3_lab_abnormality` | `label_vocabulary[lab_Mg_pm24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 91 | `A3_lab_abnormality` | `head_metric_computable[lab_Mg_pre_24h]` | PASS | at least two label values present in every split |
| 92 | `A3_lab_abnormality` | `label_vocabulary[lab_Mg_pre_24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 93 | `A3_lab_abnormality` | `head_metric_computable[lab_Mg_post_24h]` | PASS | at least two label values present in every split |
| 94 | `A3_lab_abnormality` | `label_vocabulary[lab_Mg_post_24h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 95 | `A3_lab_abnormality` | `head_metric_computable[lab_Mg_pm6h]` | PASS | at least two label values present in every split |
| 96 | `A3_lab_abnormality` | `label_vocabulary[lab_Mg_pm6h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 97 | `A3_lab_abnormality` | `head_metric_computable[lab_Mg_pm12h]` | PASS | at least two label values present in every split |
| 98 | `A3_lab_abnormality` | `label_vocabulary[lab_Mg_pm12h]` | PASS | every value is one of ['missing', 'low_abnormal', 'high_abnormal', 'abnormal_unknown_direction', 'normal'] |
| 99 | `A4_event_localization` | `all_three_splits_present` | PASS | read ['test', 'train', 'val'] |
| 100 | `A4_event_localization` | `cohort_non_empty` | PASS | 749,112 rows over 154,092 subjects |
| 101 | `A4_event_localization` | `row_key_unique` | PASS | key ['study_id']: 0 duplicate row(s) across the three splits |
| 102 | `A4_event_localization` | `subgroup_columns_present` | PASS | every subgroup column `task_spec` declares is on the rows |
| 103 | `A4_event_localization` | `primary_cohort_link_tier` | PASS | primary rows carry link_tier ['L3'], §4.A.4.2 as amended by §4 decision 10 allows ['L3'] |
| 104 | `A4_event_localization` | `primary_cohort_sqi_tier` | PASS | primary rows carry sqi_tier ['high', 'medium'], §4.A.4.2 as amended by §4 decision 10 allows ['high', 'medium'] |
| 105 | `A5_cross_modal_verification` | `all_three_splits_present` | PASS | read ['test', 'train', 'val'] |
| 106 | `A5_cross_modal_verification` | `cohort_non_empty` | PASS | 5,243,784 rows over 154,092 subjects |
| 107 | `A5_cross_modal_verification` | `row_key_unique` | PASS | key ['anchor_study_id', 'neg_type', 'image_type']: 0 duplicate row(s) across the three splits |
| 108 | `A5_cross_modal_verification` | `subgroup_columns_present` | PASS | every subgroup column `task_spec` declares is on the rows |
| 109 | `A5_cross_modal_verification` | `rows_per_anchor` | PASS | 749,112 anchors x 7 = 5,243,784, measured 5,243,784 |
| 110 | `A5_cross_modal_verification` | `head_metric_computable[y_match]` | PASS | at least two label values present in every split |
| 111 | `A5_cross_modal_verification` | `head_metric_computable[hr_label]` | PASS | at least two label values present in every split |
| 112 | `A5_cross_modal_verification` | `mask_implies_label[hr_label]` | PASS | `masked_attr_valid` is True on 0 row(s) whose `hr_label` is null |
| 113 | `A5_cross_modal_verification` | `label_vocabulary[hr_label]` | PASS | every value is one of ['bradycardia', 'normal', 'tachycardia'] |
| 114 | `A5_cross_modal_verification` | `head_metric_computable[qrs_label]` | PASS | at least two label values present in every split |
| 115 | `A5_cross_modal_verification` | `mask_implies_label[qrs_label]` | PASS | `masked_attr_valid` is True on 0 row(s) whose `qrs_label` is null |
| 116 | `A5_cross_modal_verification` | `label_vocabulary[qrs_label]` | PASS | every value is one of ['normal', 'borderline', 'wide'] |
| 117 | `A5_cross_modal_verification` | `head_metric_computable[qtc_label]` | PASS | at least two label values present in every split |
| 118 | `A5_cross_modal_verification` | `mask_implies_label[qtc_label]` | PASS | `masked_attr_valid` is True on 0 row(s) whose `qtc_label` is null |
| 119 | `A5_cross_modal_verification` | `label_vocabulary[qtc_label]` | PASS | every value is one of ['short', 'normal', 'prolonged'] |
| 120 | `A6_risk_stratification` | `all_three_splits_present` | PASS | read ['test', 'train', 'val'] |
| 121 | `A6_risk_stratification` | `cohort_non_empty` | PASS | 500,471 rows over 124,602 subjects |
| 122 | `A6_risk_stratification` | `row_key_unique` | PASS | key ['study_id']: 0 duplicate row(s) across the three splits |
| 123 | `A6_risk_stratification` | `subgroup_columns_present` | PASS | every subgroup column `task_spec` declares is on the rows |
| 124 | `A6_risk_stratification` | `primary_cohort_link_tier` | PASS | primary rows carry link_tier ['L3'], §4.A.6.2 allows ['L3'] |
| 125 | `A6_risk_stratification` | `head_metric_computable[mortality_30d]` | PASS | at least two label values present in every split |
| 126 | `A6_risk_stratification` | `mask_implies_label[mortality_30d]` | PASS | `mortality_observable` is True on 0 row(s) whose `mortality_30d` is null |
| 127 | `A6_risk_stratification` | `head_metric_computable[mortality_90d]` | PASS | at least two label values present in every split |
| 128 | `A6_risk_stratification` | `mask_implies_label[mortality_90d]` | PASS | `mortality_observable` is True on 0 row(s) whose `mortality_90d` is null |
| 129 | `A6_risk_stratification` | `head_metric_computable[readmission_30d]` | PASS | at least two label values present in every split |
| 130 | `A6_risk_stratification` | `mask_implies_label[readmission_30d]` | PASS | `readmission_eligible` is True on 0 row(s) whose `readmission_30d` is null |
| 131 | `A6_risk_stratification` | `head_metric_computable[readmission_90d]` | PASS | at least two label values present in every split |
| 132 | `A6_risk_stratification` | `mask_implies_label[readmission_90d]` | PASS | `readmission_eligible_90d` is True on 0 row(s) whose `readmission_90d` is null |
| 133 | `B1_measurement_blind` | `all_three_splits_present` | PASS | read ['test', 'train', 'val'] |
| 134 | `B1_measurement_blind` | `cohort_non_empty` | PASS | 748,454 rows over 154,079 subjects |
| 135 | `B1_measurement_blind` | `row_key_unique` | PASS | key ['study_id']: 0 duplicate row(s) across the three splits |
| 136 | `B1_measurement_blind` | `subgroup_columns_present` | PASS | every subgroup column `task_spec` declares is on the rows |
| 137 | `B1_measurement_blind` | `whole_cohort_is_primary` | PASS | 748,454 of 748,454 rows flagged primary |
| 138 | `B1_measurement_blind` | `head_metric_computable[hr_label]` | PASS | at least two label values present in every split |
| 139 | `B1_measurement_blind` | `label_vocabulary[hr_label]` | PASS | every value is one of ['bradycardia', 'normal', 'tachycardia'] |
| 140 | `B1_measurement_blind` | `head_metric_computable[qrs_label]` | PASS | at least two label values present in every split |
| 141 | `B1_measurement_blind` | `label_vocabulary[qrs_label]` | PASS | every value is one of ['normal', 'borderline', 'wide'] |
| 142 | `B1_measurement_blind` | `head_metric_computable[qtc_label]` | PASS | at least two label values present in every split |
| 143 | `B1_measurement_blind` | `label_vocabulary[qtc_label]` | PASS | every value is one of ['short', 'normal', 'prolonged'] |
| 144 | `B2_noise_robustness` | `all_three_splits_present` | PASS | read ['test', 'train', 'val'] |
| 145 | `B2_noise_robustness` | `cohort_non_empty` | PASS | 900,005 rows over 154,079 subjects |
| 146 | `B2_noise_robustness` | `row_key_unique` | PASS | key ['study_id', 'regime', 'row_role', 'corruption_type', 'snr_db']: 0 duplicate row(s) across the three splits |
| 147 | `B2_noise_robustness` | `subgroup_columns_present` | PASS | every subgroup column `task_spec` declares is on the rows |
| 148 | `B2_noise_robustness` | `head_metric_computable[hr_label]` | PASS | at least two label values present in every split |
| 149 | `B2_noise_robustness` | `label_vocabulary[hr_label]` | PASS | every value is one of ['bradycardia', 'normal', 'tachycardia'] |
| 150 | `B2_noise_robustness` | `head_metric_computable[qrs_label]` | PASS | at least two label values present in every split |
| 151 | `B2_noise_robustness` | `label_vocabulary[qrs_label]` | PASS | every value is one of ['normal', 'borderline', 'wide'] |
| 152 | `B2_noise_robustness` | `head_metric_computable[qtc_label]` | PASS | at least two label values present in every split |
| 153 | `B2_noise_robustness` | `label_vocabulary[qtc_label]` | PASS | every value is one of ['short', 'normal', 'prolonged'] |
| 154 | `B3_temporal_grounding` | `all_three_splits_present` | PASS | read ['test', 'train', 'val'] |
| 155 | `B3_temporal_grounding` | `cohort_non_empty` | PASS | 2,996,448 rows over 154,092 subjects |
| 156 | `B3_temporal_grounding` | `row_key_unique` | PASS | key ['study_id', 'query']: 0 duplicate row(s) across the three splits |
| 157 | `B3_temporal_grounding` | `subgroup_columns_present` | PASS | every subgroup column `task_spec` declares is on the rows |
| 158 | `B3_temporal_grounding` | `rows_per_study` | PASS | 749,112 studies x 4 = 2,996,448, measured 2,996,448 |
| 159 | `B4_cross_modal_verification` | `all_three_splits_present` | PASS | read ['test', 'train', 'val'] |
| 160 | `B4_cross_modal_verification` | `cohort_non_empty` | PASS | 5,243,784 rows over 154,092 subjects |
| 161 | `B4_cross_modal_verification` | `row_key_unique` | PASS | key ['anchor_study_id', 'neg_type', 'image_type']: 0 duplicate row(s) across the three splits |
| 162 | `B4_cross_modal_verification` | `subgroup_columns_present` | PASS | every subgroup column `task_spec` declares is on the rows |
| 163 | `B4_cross_modal_verification` | `rows_per_anchor` | PASS | 749,112 anchors x 7 = 5,243,784, measured 5,243,784 |
| 164 | `B4_cross_modal_verification` | `head_metric_computable[y_match]` | PASS | at least two label values present in every split |
| 165 | `B5_contradiction_detection` | `all_three_splits_present` | PASS | read ['test', 'train', 'val'] |
| 166 | `B5_contradiction_detection` | `cohort_non_empty` | PASS | 128,653 rows over 38,422 subjects |
| 167 | `B5_contradiction_detection` | `row_key_unique` | PASS | key ['study_id']: 0 duplicate row(s) across the three splits |
| 168 | `B5_contradiction_detection` | `subgroup_columns_present` | PASS | every subgroup column `task_spec` declares is on the rows |
| 169 | `B5_contradiction_detection` | `whole_cohort_is_primary` | PASS | 128,653 of 128,653 rows flagged primary |
| 170 | `B5_contradiction_detection` | `locked_cohort_size` | PASS | measured 128,653 primary rows against the locked 128,653 |
| 171 | `B5_contradiction_detection` | `head_metric_computable[is_corrupted]` | PASS | at least two label values present in every split |
| 172 | `B5_contradiction_detection` | `head_metric_computable[label]` | PASS | at least two label values present in every split |
| 173 | `B5_contradiction_detection` | `label_vocabulary[label]` | PASS | every value is one of ['clean', 'corrupted_HR', 'corrupted_QRS', 'corrupted_axis', 'corrupted_PR'] |
| 174 | `B5_contradiction_detection` | `mask_implies_label[span]` | PASS | `is_corrupted` is True on 0 row(s) whose `corrupted_span_start` is null |
| 175 | `B6_difficulty_stratified` | `all_three_splits_present` | PASS | read ['test', 'train', 'val'] |
| 176 | `B6_difficulty_stratified` | `pointer_covers_base_task_rows` | PASS | pointer rows per split [3667615, 528675, 1047494] against B4_cross_modal_verification's [3667615, 528675, 1047494] |
| 177 | `B6_difficulty_stratified` | `difficulty_tier_vocabulary` | PASS | tiers present ['easy', 'medium', 'positive']; `task_definitions.yaml` declares ['easy', 'hard', 'medium'] plus the positive rows |
| 178 | `B6_difficulty_stratified` | `tier_neg_types[easy]` | PASS | `easy` holds ['IMAGE_SWAP', 'PARTIAL_MISMATCH', 'SIGNAL_SWAP', 'TEXT_SWAP']; the config declares ['IMAGE_SWAP', 'PARTIAL_MISMATCH', 'SIGNAL_SWAP', 'TEXT_SWAP'] |
| 179 | `B6_difficulty_stratified` | `tier_neg_types[medium]` | PASS | `medium` holds ['HARD_NEGATIVE_TEXT']; the config declares ['HARD_NEGATIVE_TEXT'] |
| 180 | `B6_difficulty_stratified` | `tier_neg_types[hard]` | PASS | `hard` holds no rows; the config declares none (RESERVED, ships empty) |
| 181 | `B6_difficulty_stratified` | `rows_per_anchor` | PASS | 749,112 anchors x 7 = 5,243,784, measured 5,243,784 |
| 182 | `B2_noise_robustness` | `corruption_grid_complete` | PASS | 40 of 40 (family, SNR) cells present, smallest holds 3,742 rows |
| 183 | `B2_noise_robustness` | `frozen_anchor_count` | PASS | 1871 frozen Phase 1 anchors carry usable B1 labels (§5 question 10: 1,871 of the 1,998 that exist) |
| 184 | `B4_cross_modal_verification` | `a5_b4_row_counts_equal` | PASS | A5 and B4 carry identical per-split row counts (§4.B.4.8 compares the two, which is only meaningful on the same rows) |

## Reproduce

```
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/21_audit_tasks_cohort.py
```

The audit reads only artifacts already on disk and writes only this report, so it is safe to re-run at any time.
