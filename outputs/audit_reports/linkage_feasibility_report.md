# Linkage Feasibility Report - PASS

## Table L1 - EHR cache row counts

| Table | Rows |
|---|---:|
| `admissions` | 546,028 |
| `patients` | 364,627 |
| `diagnoses_icd` | 6,364,488 |
| `d_icd_diagnoses` | 112,107 |
| `d_labitems` | 1,650 |
| `labevents` | 158,374,764 |
| `edstays` | 425,087 |
| `ed_diagnosis` | 899,050 |
| `triage` | 425,087 |

## Table L2 - Linkage tier distribution

| Tier | Count | Percent of ECGs |
|---|---:|---:|
| L3 | 468,176 | 58.52% |
| L2 | 79,651 | 9.96% |
| L1 | 237,934 | 29.74% |
| L0 | 14,274 | 1.78% |

## Table L3 - Label availability

| Label family | Count | Percent of ECGs |
|---|---:|---:|
| ICD available on L3/L2 | 547,671 | 68.46% |
| ICD available any tier | 547,671 | 68.46% |
| Any key lab within +/-6h | 540,177 | 67.52% |
| Any key lab within +/-24h | 608,968 | 76.12% |
| Mortality observable | 494,411 | 61.80% |
| 30d mortality positive | 34,044 | 4.26% |
| 30d readmission eligible | 486,459 | 60.80% |
| 30d readmission positive | 101,276 | 12.66% |

## Table L4 - Decision threshold inputs

| Threshold input | Value |
|---|---:|
| Clean L3/L2 linkage | 547,827 (68.48%) |
| L3/L2 ICD coverage | 547,671 (68.46%) |
| Key lab within +/-24h | 608,968 (76.12%) |
| Max risk-outcome positives | 101,276 |
| Max risk-outcome prevalence | 12.66% |

## Key-lab configuration

`config/key_labs.yaml` defines: K, Na, creatinine, troponin, lactate.

## Figure L1 - Linkage tier distribution

`L3` ################################################## 468,176
`L2` ######## 79,651
`L1` ######################### 237,934
`L0` # 14,274

## Manual audit examples - successful linkages

| study_id | subject_id | ecg_time | link_tier | source | link_type | hadm_id | stay_id | offset_minutes | icd_available | any_key_lab_within_24h |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 45445758 | 12664977 | 2150-10-18 00:42:00 | L3 | ed | exact | 24010044.0 | 31218497.0 | 0.0 | True | True |
| 46311805 | 14715509 | 2168-05-12 02:15:00 | L3 | ed | exact | 20628967.0 | 36296650.0 | 0.0 | True | True |
| 43071543 | 19874138 | 2190-09-08 19:47:00 | L3 | ed | exact |  | 39210392.0 | 0.0 | True | False |
| 43921642 | 16132155 | 2139-08-31 07:22:00 | L2 | hosp | tolerance | 22468232.0 |  | -596.0 | True | True |
| 45806122 | 11443554 | 2160-09-16 20:46:00 | L3 | ed | exact |  | 31326810.0 | 0.0 | True | True |
| 40919613 | 14993194 | 2143-07-21 08:04:00 | L3 | hosp | exact | 24698228.0 |  | 0.0 | True | True |
| 47898144 | 16054794 | 2157-05-31 21:08:00 | L3 | hosp | exact | 29571686.0 |  | 0.0 | True | True |
| 47158758 | 15573574 | 2156-03-19 11:35:00 | L3 | hosp | exact | 26141124.0 |  | 0.0 | True | True |
| 49984968 | 17884254 | 2115-11-21 10:48:00 | L2 | hosp | tolerance | 23805750.0 |  | -73.0 | True | True |
| 45085838 | 19802977 | 2158-03-07 17:19:00 | L3 | ed | exact | 28575062.0 | 39902077.0 | 0.0 | True | True |
| 49815219 | 19878911 | 2118-11-18 06:22:00 | L3 | hosp | exact | 29405414.0 |  | 0.0 | True | True |
| 41542911 | 19277757 | 2131-08-23 06:09:00 | L3 | hosp | exact | 28945718.0 |  | 0.0 | True | True |
| 47958964 | 14950683 | 2180-11-26 12:51:00 | L3 | hosp | exact | 29375643.0 |  | 0.0 | True | True |
| 49459482 | 12005748 | 2141-11-07 09:53:00 | L2 | hosp | tolerance | 22557765.0 |  | -142.0 | True | True |
| 40325415 | 15676468 | 2194-11-08 00:43:00 | L3 | hosp | exact | 27399828.0 |  | 0.0 | True | True |
| 48379843 | 13777749 | 2132-03-15 03:48:00 | L3 | hosp | exact | 27550735.0 |  | 0.0 | True | True |
| 49192016 | 16918776 | 2189-08-08 19:13:00 | L3 | ed | exact |  | 36351106.0 | 0.0 | True | True |
| 46895705 | 13928953 | 2136-11-23 21:55:00 | L2 | hosp | tolerance | 29254483.0 |  | -281.0 | True | True |
| 47088044 | 11469226 | 2130-04-19 07:45:00 | L3 | ed | exact | 22445520.0 | 30484504.0 | 0.0 | True | True |
| 40654224 | 11567529 | 2166-09-05 04:31:00 | L3 | ed | exact | 25525511.0 | 38813853.0 | 0.0 | True | True |

## Manual audit examples - failed or ambiguous linkages

| study_id | subject_id | ecg_time | link_tier | source | link_type | hadm_id | stay_id | offset_minutes | icd_available | any_key_lab_within_24h |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 47034305 | 10698563 | 2126-05-02 15:21:00 | L1 |  | same_subject_no_temporal_match |  |  |  | False | False |
| 41179128 | 10081828 | 2189-02-18 12:08:00 | L1 |  | same_subject_no_temporal_match |  |  |  | False | True |
| 42845786 | 18547152 | 2145-07-04 08:14:00 | L1 | hosp | tolerance | 26382681.0 |  | -5701.0 | False | True |
| 43265885 | 14983135 | 2194-09-21 13:16:00 | L1 |  | same_subject_no_temporal_match |  |  |  | False | False |
| 47070205 | 15441487 | 2183-10-15 13:44:00 | L1 |  | same_subject_no_temporal_match |  |  |  | False | False |
| 42616335 | 19956777 | 2118-11-05 11:59:00 | L1 | ed | tolerance | 27157149.0 | 36528499.0 | -4035.0 | False | False |
| 43469733 | 18581612 | 2137-05-05 12:34:00 | L1 |  | same_subject_no_temporal_match |  |  |  | False | True |
| 47241304 | 11370993 | 2181-03-29 14:39:00 | L1 |  | same_subject_no_temporal_match |  |  |  | False | False |
| 46877871 | 18816464 | 2139-05-07 15:06:00 | L1 |  | same_subject_no_temporal_match |  |  |  | False | False |
| 44243849 | 13146966 | 2153-01-04 11:14:00 | L1 |  | same_subject_no_temporal_match |  |  |  | False | True |
| 43384330 | 16800326 | 2184-11-11 10:27:00 | L1 |  | same_subject_no_temporal_match |  |  |  | False | False |
| 49312051 | 15596257 | 2131-11-11 10:49:00 | L1 |  | same_subject_no_temporal_match |  |  |  | False | False |
| 48001789 | 10801617 | 2143-02-14 12:56:00 | L1 | ed | tolerance |  | 31876192.0 | -4556.0 | False | True |
| 40425107 | 13757352 | 2141-05-07 09:03:00 | L1 | hosp | tolerance | 29853550.0 |  | -2337.0 | False | True |
| 43773012 | 13386490 | 2157-09-27 13:19:00 | L1 |  | same_subject_no_temporal_match |  |  |  | False | True |
| 44432999 | 14505212 | 2133-11-23 07:10:00 | L1 |  | same_subject_no_temporal_match |  |  |  | False | True |
| 40440862 | 12807885 | 2179-08-19 13:47:00 | L1 |  | same_subject_no_temporal_match |  |  |  | False | True |
| 48778681 | 10775692 | 2164-01-14 14:00:00 | L1 |  | same_subject_no_temporal_match |  |  |  | False | True |
| 48109493 | 18679418 | 2151-03-30 12:34:00 | L1 |  | same_subject_no_temporal_match |  |  |  | False | True |
| 44599933 | 17936503 | 2165-04-20 12:53:00 | L1 |  | same_subject_no_temporal_match |  |  |  | False | False |
