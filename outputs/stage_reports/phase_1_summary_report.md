# Phase 1 Dataset Generation Report

## Objective

In Phase 1, We built the local tri-modal ECG dataset from the raw MIMIC-IV-ECG files and linked it with MIMIC-IV Hosp / ED EHR data where the linkage quality was strong enough. The final goal was to create a clean, reproducible dataset that Phase 2 can use for task generation without re-checking raw files, re-making splits, or deciding leakage rules later.

The final dataset includes waveform signals, rendered ECG images, scan-like ECG images, corrupted signal variants, waveform quality metrics, structured waveform features, EHR linkage metadata, and a canonical manifest that tells us where every modality is stored and how to read it.

## Basis For The Implementation

The implementation follows `ECG_Benchmark_Neutral_Implementation_Plan_Plan_A_B.docx` and `TriModal_ECG_Truth.docx` as the main source of truth. The major choices were not arbitrary:

- Raw MIMIC files are kept local and are not part of any public artifact.
- Dataset versions, row counts, hashes, and access checks are recorded before building derived data.
- Patient-level splitting is used to prevent the same subject appearing in more than one split.
- EHR linkage is only used if the documented Plan A thresholds pass.
- Labels cannot use inputs that directly created those labels.
- Final outputs are validated through split, duplicate, missingness, leakage, and linkage audits.

Where the document did not define a small operational detail, We chose the conservative option that keeps the data auditable. For example, low SQI is kept as an analysis flag instead of being used as a hard exclusion, while hard waveform failures such as flatline, NaN/Inf, duplicate waveform, and extreme amplitude are excluded from the clean index.

## Plan A / Plan B Decision

The project had two possible directions:

- Plan A: use the EHR-linked dataset for clinically grounded tasks.
- Plan B: keep the task set signal-only and robustness-focused if EHR linkage was too weak.

I chose Plan A because the linkage decision gate passed all required thresholds in `config/decision.yaml`:

| Check                              |               Result |
| ---------------------------------- | -------------------: |
| Total ECGs                         |              800,035 |
| Clean linkage coverage             | 547,827 ECGs, 68.48% |
| L2/L3 ICD coverage                 | 547,671 ECGs, 68.46% |
| Key lab availability within 24h    | 609,402 ECGs, 76.17% |
| Risk-positive outcome availability | 101,276 ECGs, 12.66% |

This made Plan A the better main path because the dataset has enough linked EHR information for diagnosis, lab, and risk tasks. Plan B is still useful as a supplementary path for measurement-blind and robustness tasks, especially where we want signal-only evaluation.

## What Was Built

### 1. Foundation And Raw Data Checks

I first locked and checked the raw data sources:

- MIMIC-IV-ECG waveforms and metadata.
- MIMIC-IV Hosp tables.
- MIMIC-IV ED tables.
- Required CSV files such as `record_list.csv`, `machine_measurements.csv`, and `waveform_note_links.csv`.

The access check verified that required files exist, row counts are in the expected ranges, and the Hosp/ED files match the expected local setup. The final access check is recorded in `outputs/audit_reports/access_check.md` and passed.

### 2. Master ECG Index

I built the master ECG metadata index from the raw ECG metadata. This is the backbone of the dataset. It keeps one row per ECG study, with identifiers needed to connect the study to waveform files, subject information, machine measurements, text availability, EHR linkage, and later split assignment.

Final full index:

- `data/processed/index/ecg_metadata.parquet`
- Row count: 800,035 ECGs

### 3. EHR Linkage

I loaded the required Hosp and ED tables into local parquet caches, then linked ECG studies to EHR encounters. The linkage logic uses exact overlap first, then tolerance-based matching, then a tie-break rule when more than one candidate exists.

The linkage outputs include:

- `candidate_links.parquet`: candidate EHR matches.
- `linkage_final.parquet`: final selected links.
- `label_availability.parquet`: label and linkage-tier availability for every ECG.
- `config/decision.yaml`: frozen Plan A / Plan B decision.

Final linkage status:

- `candidate_links.parquet`: 602,314 rows.
- `linkage_final.parquet`: 785,761 rows.
- `label_availability.parquet`: 800,035 rows.
- Linkage tiers: L3 = 468,176, L2 = 79,651, L1 = 237,934, L0 = 14,274.
- Tie-break validation mismatches: 0.

### 4. Patient-Level Split

We created a subject-level train / validation / test split so that no patient appears in more than one split. This is important because multiple ECGs can belong to the same subject, and ECG-level splitting would leak patient-specific information.

Final clean split:

| Split      |    ECGs | Subjects |
| ---------- | ------: | -------: |
| Train      | 523,945 |  107,851 |
| Validation |  75,525 |   15,397 |
| Test       | 149,642 |   30,844 |

Subject overlap across train, validation, and test is 0.

### 5. Signal Modalities

We extracted and packed the raw ECG waveforms into HDF5 containers so the dataset can be read efficiently without scanning individual WFDB files during training. Both Lead-II and full 12-lead signals are included.

Signal outputs include:

- Raw Lead-II signal: shape `(5000,)`, float32.
- Raw 12-lead signal: shape `(5000, 12)`, float32.
- Preprocessed Lead-II signal: shape `(5000,)`, float32.
- Preprocessed 12-lead signal: shape `(5000, 12)`, float32.

The preprocessing recipe uses fixed signal-processing settings from the pipeline plan, including filtering and normalization choices intended to make the signals consistent while preserving clinically meaningful morphology.

### 6. Image Modalities

We rendered ECG images in two forms:

- Clean ECG images: controlled, readable ECG renderings.
- Scan-like ECG images: images made to look closer to scanned or real-world ECG paper.

Both image styles include Lead-II and 12-lead layouts. This gives Phase 2 both signal-first and vision-first task options. The image files are packed into tar shards and indexed through the manifest, including byte offsets and SHA256 hashes so they can be read directly and verified.

### 7. Corrupted Signal Dataset

We built corrupted Lead-II signal variants for robustness tasks. Each corrupted example keeps the corruption type, SNR level, and row locator. This is stored separately from the clean signal data so Phase 2 can create robustness tasks without changing the base waveform containers.

Final corrupted signal rows:

- 79,920 corrupted signal rows.
- 40 corruption type / SNR combinations.
- 1,998 anchor ECGs per corruption setting.

The corruption types include baseline wander, electrode motion, EMG noise, gain drift, Gaussian noise, lead dropout, powerline noise, and saturation.

### 8. Waveform QC And Structured Features

We generated waveform quality results for every ECG and then computed structured waveform features for every ECG. These files are important because they let us document signal quality, identify hard failures, and support future analysis without recomputing expensive waveform processing.

Final files:

- `data/processed/waveform_qc.parquet`: 800,035 rows.
- `data/processed/structured_features.parquet`: 800,035 rows.

The waveform QC checks include decode validity, length, lead count, lead names, NaN/Inf flags, flatline flags, extreme amplitude flags, duplicate waveform flags, SQI tier, HR consistency, and QRS consistency.

The structured features file stores derived waveform measurements and summary features. It is not allowed as an input for measurement-derived tasks because that would create label leakage.

### 9. Final Clean Index And Canonical Manifest

After all modalities and QC files existed,Webuilt the final clean index and canonical modality manifest.

The clean index keeps ECGs that pass tri-modal availability and hard waveform QC:

- Full index: 800,035 ECGs.
- Clean index: 749,112 ECGs.
- Retained percentage: 93.63%.

Main exclusion counts:

| Exclusion reason        |  Count |
| ----------------------- | -----: |
| Flatline lead flag      | 39,623 |
| NaN/Inf flag            | 10,558 |
| Duplicate waveform flag |  1,059 |
| Extreme amplitude flag  |    994 |
| Text unavailable        |      1 |

The canonical manifest stores all addressable modalities in one table. It includes study ID, modality kind, layout, container path, row or byte locator, SHA256, dataset version, and creation timestamp.

Final manifest:

- `data/processed/modality_manifest.parquet`
- Row count: 6,480,200

Manifest row breakdown:

| Modality kind       |      Rows |
| ------------------- | --------: |
| raw_lead2           |   800,035 |
| raw_12lead          |   800,035 |
| preprocessed_lead2  |   800,035 |
| preprocessed_12lead |   800,035 |
| image_clean         | 1,600,070 |
| image_scanlike      | 1,600,070 |
| signal_corrupted    |    79,920 |

The image rows are double-counted by design because each ECG has both Lead-II and 12-lead layouts for clean and scan-like images.

## Main Scripts And What They Do

| Script                              | Purpose                                                                       |
| ----------------------------------- | ----------------------------------------------------------------------------- |
| `00_lock_versions.py`               | Records dataset versions, file hashes, and library/environment information.   |
| `00b_access_check.py`               | Verifies raw data access, required files, row ranges, and source consistency. |
| `01_build_master_index.py`          | Builds the master ECG metadata index from raw ECG metadata.                   |
| `40_load_ehr_tables.py`             | Loads required Hosp and ED tables into parquet caches for linkage.            |
| `41_link_exact_overlap.py`          | Finds exact-time or direct overlap links between ECGs and EHR encounters.     |
| `42_link_tolerance.py`              | Adds tolerance-based candidate links when exact linkage is not available.     |
| `43_tie_break_link.py`              | Applies deterministic tie-breaking to select one best EHR link per ECG.       |
| `44_label_availability.py`          | Computes which ECGs have diagnosis, lab, and risk-label availability.         |
| `45_decision_gate.py`               | Applies Plan A / Plan B thresholds and writes `config/decision.yaml`.         |
| `02_create_patient_split.py`        | Creates patient-level train, validation, and test splits.                     |
| `10_extract_ecg_signals.py`         | Extracts raw ECG signals from WFDB records.                                   |
| `10b_pack_signals.py`               | Packs extracted raw signals into efficient HDF5 containers.                   |
| `14_fit_preprocessing_recipe.py`    | Defines the preprocessing recipe used for filtered/normalized signals.        |
| `20_render_clean_images.py`         | Renders clean ECG images.                                                     |
| `20b_pack_images.py`                | Packs clean images into tar shards with locators and hashes.                  |
| `21_generate_scanlike_images.py`    | Generates scan-like ECG images.                                               |
| `21b_pack_scanlike.py`              | Packs scan-like images into tar shards with locators and hashes.              |
| `30_qc.py`                          | Checks tri-modal completeness for waveform, image, and text availability.     |
| `31_waveform_qc.py`                 | Runs waveform QC and SQI checks across all leads.                             |
| `32_compute_structured_features.py` | Computes structured waveform features for every ECG.                          |
| `50_build_signals_corrupted.py`     | Builds corrupted Lead-II signal variants for robustness tasks.                |
| `15_preprocess_signals.py`          | Materializes preprocessed Lead-II and 12-lead signal containers.              |
| `03_add_measurements_to_index.py`   | Adds raw machine-measurement fields and missing flags to the ECG index.       |
| `04_cleanup_master_index.py`        | Builds the final clean index using tri-modal QC and waveform QC.              |
| `05_build_manifest_and_splits.py`   | Builds the canonical modality manifest and validates modality coverage.       |
| `33_dataset_audits.py`              | Runs final split, duplicate, missingness, leakage, and linkage audits.        |
| `modality_io.py`                    | Provides `read_modality(...)` for reading manifest-backed signals and images. |

## Final Output Inventory

| Output                                                              | What it contains                                                   | Status         |
| ------------------------------------------------------------------- | ------------------------------------------------------------------ | -------------- |
| `data/processed/index/ecg_metadata.parquet`                         | Full ECG metadata index, one row per ECG.                          | 800,035 rows   |
| `data/processed/index/ecg_metadata_with_measurements.parquet`       | Full index plus raw machine-measurement columns and missing flags. | 800,035 rows   |
| `data/processed/index/ecg_metadata_clean.parquet`                   | Final QC-filtered ECG index.                                       | 749,112 rows   |
| `data/processed/index/ecg_metadata_clean_with_measurements.parquet` | Clean index plus machine-measurement fields.                       | 749,112 rows   |
| `data/processed/waveform_qc.parquet`                                | Waveform quality and SQI results.                                  | 800,035 rows   |
| `data/processed/structured_features.parquet`                        | Structured waveform features.                                      | 800,035 rows   |
| `data/processed/modality_manifest.parquet`                          | Canonical address table for all signal/image/corrupted modalities. | 6,480,200 rows |
| `outputs/audit_reports/split_audit.md`                              | Split ratios, subject overlap, linkage and HR distribution checks. | PASS           |
| `outputs/audit_reports/duplicate_audit.md`                          | Duplicate ECG and duplicate waveform checks.                       | PASS           |
| `outputs/audit_reports/missingness_audit.md`                        | Missingness summary for required final files.                      | PASS           |
| `outputs/audit_reports/leakage_audit.md`                            | Input-policy and label-leakage checks.                             | PASS           |
| `outputs/audit_reports/linkage_audit.md`                            | Plan A linkage, provenance, and tie-break checks.                  | PASS           |
| `outputs/stage_reports/stage_10_report.md`                          | Final Stage 10 report and validation evidence.                     | PASS           |
| `outputs/stage_reports/stage_10_complete.done.json`                 | Final Phase 1 completion marker.                                   | PASS           |

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

Phase 1 is complete. Plan A is the main path because EHR linkage passed the required thresholds, and Plan B remains available for signal-only and robustness experiments.
