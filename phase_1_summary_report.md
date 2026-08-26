# Phase 1 Dataset Generation Report

## Objective

In Phase 1, we built the local tri-modal ECG dataset from the raw MIMIC-IV-ECG files and linked it with MIMIC-IV Hosp / ED EHR data where the linkage quality was strong enough. The final goal was to create a clean, reproducible dataset that Phase 2 can use for task generation without re-checking raw files, re-making splits, or deciding leakage rules later.

The final dataset includes waveform signals, rendered ECG images, scan-like ECG images, corrupted signal variants, waveform quality metrics, structured waveform features, EHR linkage metadata, and a canonical manifest that tells us where every modality is stored and how to read it.

![Figure 1. Phase 1 architecture from raw ECG/EHR inputs to the final audited dataset.](phase_1_report_assets/phase1_pipeline_architecture.png)

*Figure 1. Phase 1 architecture from raw ECG/EHR inputs to the final audited dataset.*


## Basis For The Implementation

The implementation follows `docs/PIPELINE_SOURCE_OF_TRUTH.md` as the main source of truth. The major choices were not arbitrary:

- Raw MIMIC files are kept local and are not part of any public artifact.
- Dataset versions, row counts, hashes, and access checks are recorded before building derived data.
- Patient-level splitting is used to prevent the same subject appearing in more than one split.
- EHR linkage is only used if the documented Plan A thresholds pass.
- Labels cannot use inputs that directly created those labels.
- Final outputs are validated through split, duplicate, missingness, leakage, and linkage audits.

Where the document did not define a small operational detail, we used the conservative option that keeps the data auditable. Low SQI is kept as an analysis flag instead of being used as a hard exclusion, while hard waveform failures such as flatline, NaN/Inf, duplicate waveform, and extreme amplitude are excluded from the clean index.

## Plan A / Plan B Decision

The project had two possible directions:

- Plan A: use the EHR-linked dataset for clinically grounded tasks.
- Plan B: keep the task set signal-only and robustness-focused if EHR linkage was too weak.

We chose Plan A because the linkage decision gate passed all required thresholds in `config/decision.yaml`.

| Check | Result |
| --- | ---: |
| Total ECGs | 800,035 |
| Clean linkage coverage | 547,827 ECGs, 68.48% |
| L2/L3 ICD coverage | 547,671 ECGs, 68.46% |
| Key lab availability within 24h | 609,402 ECGs, 76.17% |
| Risk-positive outcome availability | 101,276 ECGs, 12.66% |

![Figure 2. Plan A passed every required linkage and label-availability threshold.](phase_1_report_assets/plan_a_thresholds.png)

*Figure 2. Plan A passed every required linkage and label-availability threshold.*


This made Plan A the better main path because the dataset has enough linked EHR information for diagnosis, lab, and risk tasks. Plan B is still useful as a supplementary path for measurement-blind and robustness tasks, especially where we want signal-only evaluation.

## Example ECG Outputs

The dataset contains both waveform and image forms of each ECG. The example below uses study ID `46529645` only to show what the modalities look like; the same reading pattern is validated across the final manifest.

![Figure 3. Raw and preprocessed Lead-II waveform example.](phase_1_report_assets/lead2_waveform_example.png)

*Figure 3. Raw and preprocessed Lead-II waveform example.*


![Figure 4. Raw 12-lead waveform example.](phase_1_report_assets/twelve_lead_waveform_example.png)

*Figure 4. Raw 12-lead waveform example.*


![Figure 5. Clean and scan-like ECG image examples for Lead-II and 12-lead layouts.](phase_1_report_assets/ecg_image_examples.png)

*Figure 5. Clean and scan-like ECG image examples for Lead-II and 12-lead layouts.*


## What Was Built

### Foundation And Raw Data Checks

We first locked and checked the raw data sources: MIMIC-IV-ECG waveforms and metadata, MIMIC-IV Hosp tables, MIMIC-IV ED tables, and required CSV files such as `record_list.csv`, `machine_measurements.csv`, and `waveform_note_links.csv`.

The access check verified that required files exist, row counts are in the expected ranges, and the Hosp/ED files match the expected local setup. The final access check is recorded in `outputs/audit_reports/access_check.md` and passed.

### Master ECG Index

We built the master ECG metadata index from the raw ECG metadata. This is the backbone of the dataset. It keeps one row per ECG study, with identifiers needed to connect the study to waveform files, subject information, machine measurements, text availability, EHR linkage, and later split assignment.

Final full index: `data/processed/index/ecg_metadata.parquet` with 800,035 ECGs.

### EHR Linkage

We loaded the required Hosp and ED tables into local parquet caches, then linked ECG studies to EHR encounters. The linkage logic uses exact overlap first, tolerance-based matching second, and a deterministic tie-break rule when more than one candidate exists.

Final linkage status:

- `candidate_links.parquet`: 602,314 rows.
- `linkage_final.parquet`: 785,761 rows.
- `label_availability.parquet`: 800,035 rows.
- Linkage tiers: L3 = 468,176, L2 = 79,651, L1 = 237,934, L0 = 14,274.
- Tie-break validation mismatches: 0.

![Figure 6. EHR linkage tier distribution across the full ECG set.](phase_1_report_assets/linkage_tier_distribution.png)

*Figure 6. EHR linkage tier distribution across the full ECG set.*


### Patient-Level Split

We created a subject-level train / validation / test split so that no patient appears in more than one split. This is important because multiple ECGs can belong to the same subject, and ECG-level splitting would leak patient-specific information.

Final clean split:

| Split | ECGs | Subjects |
| --- | ---: | ---: |
| Train | 523,945 | 107,851 |
| Validation | 75,525 | 15,397 |
| Test | 149,642 | 30,844 |

Subject overlap across train, validation, and test is 0.

![Figure 7. Final patient-safe clean split distribution.](phase_1_report_assets/clean_split_distribution.png)

*Figure 7. Final patient-safe clean split distribution.*


### Signals, Images, Corruptions, QC, And Features

Signals were extracted and packed into HDF5 containers so training code does not need to scan individual raw waveform files. Both raw and preprocessed Lead-II and 12-lead signals are available.

Clean ECG images and scan-like ECG images were rendered for both Lead-II and 12-lead layouts. The image files are packed into tar shards and indexed through the manifest with byte offsets and SHA256 hashes.

Corrupted Lead-II variants were created for robustness tasks. There are 79,920 corrupted rows across 40 corruption type / SNR combinations, with 1,998 anchor ECGs per setting.

Waveform QC and structured feature extraction were then run for every ECG:

- `data/processed/waveform_qc.parquet`: 800,035 rows.
- `data/processed/structured_features.parquet`: 800,035 rows.

### Final Clean Index And Manifest

The clean index keeps ECGs that pass tri-modal availability and hard waveform QC:

- Full index: 800,035 ECGs.
- Clean index: 749,112 ECGs.
- Retained percentage: 93.63%.

Main exclusion counts:

| Exclusion reason | Count |
| --- | ---: |
| Flatline lead flag | 39,623 |
| NaN / Inf flag | 10,558 |
| Duplicate waveform flag | 1,059 |
| Extreme amplitude flag | 994 |
| Text unavailable | 1 |

![Figure 8. Main reasons ECGs were excluded from the clean index.](phase_1_report_assets/qc_exclusion_counts.png)

*Figure 8. Main reasons ECGs were excluded from the clean index.*


The canonical manifest stores all addressable modalities in one table. It includes study ID, modality kind, layout, container path, row or byte locator, SHA256, dataset version, and creation timestamp.

Final manifest: `data/processed/modality_manifest.parquet` with 6,480,200 rows.

![Figure 9. Final manifest row counts by modality kind.](phase_1_report_assets/modality_manifest_counts.png)

*Figure 9. Final manifest row counts by modality kind.*


## Main Scripts And What They Do

| Script | Purpose |
| --- | --- |
| `00_lock_versions.py` | Records dataset versions, file hashes, and library/environment information. |
| `00b_access_check.py` | Verifies raw data access, required files, row ranges, and source consistency. |
| `01_build_master_index.py` | Builds the master ECG metadata index from raw ECG metadata. |
| `40_load_ehr_tables.py` | Loads required Hosp and ED tables into parquet caches for linkage. |
| `41_link_exact_overlap.py` | Finds exact-time or direct overlap links between ECGs and EHR encounters. |
| `42_link_tolerance.py` | Adds tolerance-based candidate links when exact linkage is not available. |
| `43_tie_break_link.py` | Applies deterministic tie-breaking to select one best EHR link per ECG. |
| `44_label_availability.py` | Computes diagnosis, lab, and risk-label availability. |
| `45_decision_gate.py` | Applies Plan A / Plan B thresholds and writes `config/decision.yaml`. |
| `02_create_patient_split.py` | Creates patient-level train, validation, and test splits. |
| `10_extract_ecg_signals.py` / `10b_pack_signals.py` | Extract and pack raw ECG signals. |
| `14_fit_preprocessing_recipe.py` / `15_preprocess_signals.py` | Define and materialize preprocessed signals. |
| `20_render_clean_images.py` / `20b_pack_images.py` | Render and pack clean ECG images. |
| `21_generate_scanlike_images.py` / `21b_pack_scanlike.py` | Render and pack scan-like ECG images. |
| `30_qc.py` | Checks tri-modal completeness for waveform, image, and text availability. |
| `31_waveform_qc.py` | Runs waveform QC and SQI checks across all leads. |
| `32_compute_structured_features.py` | Computes structured waveform features for every ECG. |
| `50_build_signals_corrupted.py` | Builds corrupted Lead-II signal variants for robustness tasks. |
| `03_add_measurements_to_index.py` | Adds raw machine-measurement fields and missing flags to the ECG index. |
| `04_cleanup_master_index.py` | Builds the final clean index using tri-modal QC and waveform QC. |
| `05_build_manifest_and_splits.py` | Builds the canonical modality manifest and validates modality coverage. |
| `33_dataset_audits.py` | Runs final split, duplicate, missingness, leakage, and linkage audits. |
| `modality_io.py` | Provides `read_modality(...)` for reading manifest-backed signals and images. |

## Final Output Inventory

| Output | What it contains | Status |
| --- | --- | --- |
| `data/processed/index/ecg_metadata.parquet` | Full ECG metadata index, one row per ECG. | 800,035 rows |
| `data/processed/index/ecg_metadata_with_measurements.parquet` | Full index plus raw machine-measurement columns and missing flags. | 800,035 rows |
| `data/processed/index/ecg_metadata_clean.parquet` | Final QC-filtered ECG index. | 749,112 rows |
| `data/processed/index/ecg_metadata_clean_with_measurements.parquet` | Clean index plus machine-measurement fields. | 749,112 rows |
| `data/processed/waveform_qc.parquet` | Waveform quality and SQI results. | 800,035 rows |
| `data/processed/structured_features.parquet` | Structured waveform features. | 800,035 rows |
| `data/processed/modality_manifest.parquet` | Canonical address table for all signal/image/corrupted modalities. | 6,480,200 rows |
| `outputs/audit_reports/split_audit.md` | Split ratios, subject overlap, linkage and HR distribution checks. | PASS |
| `outputs/audit_reports/duplicate_audit.md` | Duplicate ECG and duplicate waveform checks. | PASS |
| `outputs/audit_reports/missingness_audit.md` | Missingness summary for required final files. | PASS |
| `outputs/audit_reports/leakage_audit.md` | Input-policy and label-leakage checks. | PASS |
| `outputs/audit_reports/linkage_audit.md` | Plan A linkage, provenance, and tie-break checks. | PASS |

## Leakage Controls

The leakage policy is stored in `config/task_input_policy.yaml`. It defines which inputs are allowed and forbidden for the planned A and B tasks.

The main rule is that a model cannot receive the source that directly created the label. For example:

- Measurement-derived tasks cannot use machine measurements or structured waveform features.
- Report-contradiction tasks cannot use the original uncorrupted machine report text.
- Tasks that use EHR labels can use ECG signals and rendered ECG images, but not shortcut engineered features that would make the task trivial.

The final leakage audit confirmed that all required A1-A6 and B1-B6 task policies are present, allowed and forbidden inputs do not overlap, and required forbidden inputs are included.

## Validation Status

The final Stage 10 closeout passed. The validation evidence shows:

- All final audit reports start with `STATUS: PASS`.
- `read_modality(...)` passed 27 out of 27 checks across all modality types and layouts.
- The manifest has no orphan study IDs.
- The manifest has no duplicate modality keys.
- All manifest rows have required hashes, dataset version stamps, creation timestamps, and row or byte locators.
- The clean split has 0 subject overlap across train, validation, and test.
- Duplicate waveform groups are excluded from the clean index.
- Structured features exist before final closeout and have 800,035 rows.
- No stale temporary files remain after atomic publish.

## Current Status

Phase 1 is complete. The current dataset is ready for Phase 2 planning and task generation. Plan A is the main path because EHR linkage passed the required thresholds, and Plan B remains available for signal-only and robustness experiments.

The important point is that Phase 2 can now start from stable inputs: the clean index, the linked EHR metadata, the patient-safe split, the manifest-backed modalities, the waveform QC file, the structured features file, and the final leakage policy.
