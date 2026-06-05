# Stage 10A - prep status

STATUS: PREP_ONLY_NOT_FINAL

## Scripts patched
- `scripts/phase1_dataset_generation/03_add_measurements_to_index.py`
- `scripts/phase1_dataset_generation/04_cleanup_master_index.py`
- `scripts/phase1_dataset_generation/05_build_manifest_and_splits.py`
- `scripts/phase1_dataset_generation/33_dataset_audits.py`
- `scripts/phase1_dataset_generation/modality_io.py`

## Prep commands run
- `..\ecg_env\Scripts\python.exe phase1_dataset_generation\03_add_measurements_to_index.py`
- `..\ecg_env\Scripts\python.exe phase1_dataset_generation\04_cleanup_master_index.py`
- `..\ecg_env\Scripts\python.exe phase1_dataset_generation\05_build_manifest_and_splits.py`
- `..\ecg_env\Scripts\python.exe phase1_dataset_generation\33_dataset_audits.py --prep-check`

## Prep outputs produced
- `data/processed/index/ecg_metadata_with_measurements.parquet`: exists
- `data/processed/index/ecg_metadata_clean.parquet`: exists
- `data/processed/index/ecg_metadata_clean_with_measurements.parquet`: exists
- `data/processed/modality_manifest.parquet`: exists

## Prep validation results
- Measurement index rows: 800035
- Measurement merge duplicate study_ids: 0
- Missing flags distinguish zeros from missing values: True
- Clean index rows: 749112
- Clean with-measurements rows: 749112
- Subject split overlap: {'overlaps': {'train_test': 0, 'train_val': 0, 'val_test': 0}, 'status': 'PASS'}
- Manifest total rows: 6480200
- Manifest row count by modality_kind: {'image_clean': 1600070, 'image_scanlike': 1600070, 'preprocessed_12lead': 800035, 'preprocessed_lead2': 800035, 'raw_12lead': 800035, 'raw_lead2': 800035, 'signal_corrupted': 79920}
- Manifest duplicate key count: 0
- Manifest orphan study_id count: 0
- Manifest validation passed: True
- read_modality smoke status: PASS
- read_modality smoke checks: [{'kind': 'raw_lead2', 'kwargs': {}, 'study_id': 47950833, 'shape_or_length': [5000], 'dtype': 'float32', 'status': 'PASS'}, {'kind': 'raw_12lead', 'kwargs': {}, 'study_id': 48499748, 'shape_or_length': [5000, 12], 'dtype': 'float32', 'status': 'PASS'}, {'kind': 'preprocessed_lead2', 'kwargs': {}, 'study_id': 47950833, 'shape_or_length': [5000], 'dtype': 'float32', 'status': 'PASS'}, {'kind': 'preprocessed_12lead', 'kwargs': {}, 'study_id': 48499748, 'shape_or_length': [5000, 12], 'dtype': 'float32', 'status': 'PASS'}, {'kind': 'image_clean', 'kwargs': {'layout': 'lead2'}, 'study_id': 46529645, 'shape_or_length': 28671, 'dtype': 'bytes', 'status': 'PASS'}, {'kind': 'image_clean', 'kwargs': {'layout': '12lead'}, 'study_id': 46529645, 'shape_or_length': 15484, 'dtype': 'bytes', 'status': 'PASS'}, {'kind': 'image_scanlike', 'kwargs': {'layout': 'lead2'}, 'study_id': 46529645, 'shape_or_length': 66326, 'dtype': 'bytes', 'status': 'PASS'}, {'kind': 'image_scanlike', 'kwargs': {'layout': '12lead'}, 'study_id': 46529645, 'shape_or_length': 91634, 'dtype': 'bytes', 'status': 'PASS'}, {'kind': 'signal_corrupted', 'kwargs': {'corruption_type': 'baseline_wander', 'snr_db': 30}, 'study_id': 40078138, 'shape_or_length': [5000], 'dtype': 'float32', 'status': 'PASS'}]
- `config/task_input_policy.yaml`: exists

## Missing final dependencies
- `data/processed/structured_features.parquet`: missing
- `outputs/stage_reports/stage_7_complete.done.json`: missing

## Stage 10B status
- Stage 10B remains pending.
- Final closeout is waiting for structured_features.parquet.
- Final closeout is waiting for stage_7_complete.done.json.
- No final Stage 10 report was written.
- No stage_10_complete.done.json marker was written.
- Phase 1 completion is not claimed.

Stage 10 prep complete. Final closeout is blocked until structured_features.parquet and stage_7_complete.done.json exist.
