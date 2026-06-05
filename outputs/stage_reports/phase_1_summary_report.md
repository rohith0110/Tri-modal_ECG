# Phase 1 Summary

Phase 1 built the final tri-modal ECG dataset from the local MIMIC-IV-ECG files, with EHR linkage added where it passed the project decision rules. The main goal was to end with one clean, auditable dataset that can support Phase 2 task construction without re-reading raw files or making split/leakage decisions later.

The raw ECG, Hosp, and ED inputs were first version-locked and checked for access, expected files, row ranges, and hashes. This was based on the pipeline source-of-truth document, not an ad hoc choice, because the downstream dataset has to be reproducible from the same raw inputs. The access check passed and is recorded in `outputs/audit_reports/access_check.md`.

We then built the master ECG index and linked studies to EHR data. The Plan A / Plan B decision was made from the documented thresholds in `config/decision.yaml`. Plan A was chosen because the data easily cleared the required bars: clean linkage was about 68.5%, L2/L3 ICD coverage was about 68.5%, key-lab availability was about 76.2%, and risk-positive labels were about 12.7%. Plan B remains useful as a signal-only robustness path, but Plan A is the main path because the EHR linkage is strong enough for clinically grounded tasks.

The dataset now has raw Lead-II and raw 12-lead signals, preprocessed Lead-II and 12-lead signals, clean rendered ECG images, scan-like ECG images, corrupted Lead-II variants, waveform quality results, structured waveform features, and a canonical manifest for reading all addressable modalities. We kept both Lead-II and 12-lead image layouts because they serve different model settings. We kept corrupted signals as separate manifest rows because each ECG can have multiple corruption type and SNR combinations.

Quality control is handled before the final clean index. The full index contains 800,035 ECGs. The clean index contains 749,112 ECGs after removing failed waveform/image/text rows, invalid signals, duplicate waveform groups, flatlines, extreme amplitudes, NaN/Inf cases, and the one text failure. Low SQI is retained as an analysis flag rather than a hard exclusion, because it can still be useful for robustness analysis.

The final subject-level split is patient-safe and has no subject overlap across train, validation, and test. The clean ECG split is roughly 70/10/20: 523,945 train, 75,525 validation, and 149,642 test ECGs. The split audit also records linkage-tier and heart-rate bucket distributions so Phase 2 can check that tasks are not accidentally biased by split composition.

Current final outputs:

- `data/processed/index/ecg_metadata.parquet`: 800,035 ECGs in the full index.
- `data/processed/index/ecg_metadata_with_measurements.parquet`: full index plus raw machine-measurement fields and missing flags.
- `data/processed/index/ecg_metadata_clean.parquet`: 749,112 ECGs after final QC filtering.
- `data/processed/index/ecg_metadata_clean_with_measurements.parquet`: clean index plus measurement fields.
- `data/processed/waveform_qc.parquet`: waveform QC and SQI results for 800,035 ECGs.
- `data/processed/structured_features.parquet`: structured waveform features for 800,035 ECGs.
- `data/processed/modality_manifest.parquet`: 6,480,200 rows covering raw, preprocessed, image, and corrupted-signal modalities.
- `outputs/audit_reports/split_audit.md`, `duplicate_audit.md`, `missingness_audit.md`, `leakage_audit.md`, and `linkage_audit.md`: all final audits passed.
- `outputs/stage_reports/stage_10_report.md` and `outputs/stage_reports/stage_10_complete.done.json`: final Phase 1 closeout passed.

The leakage policy is now explicit in `config/task_input_policy.yaml`. It lists the allowed and forbidden inputs for the planned A and B tasks. The main rule is simple: labels cannot be predicted from the same source that created them. For example, measurement-derived tasks cannot use machine measurements or structured features as model inputs.

Phase 1 is complete. The dataset is ready for Phase 2 planning and task generation, with Plan A as the main clinical task path and Plan B retained for measurement-blind and robustness evaluations.
