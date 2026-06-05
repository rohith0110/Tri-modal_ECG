STATUS: PASS

# Missingness audit

## data/processed/index/ecg_metadata.parquet
- Rows: 800,035
- Top null columns: {'T_cardio': {'nulls': 190770, 'pct': 23.8452}, 'machine_hr_bpm': {'nulls': 188, 'pct': 0.0235}, 'machine_qtc_ms': {'nulls': 188, 'pct': 0.0235}}

## data/processed/index/ecg_metadata_with_measurements.parquet
- Rows: 800,035
- Top null columns: {'T_cardio': {'nulls': 190770, 'pct': 23.8452}, 'machine_hr_bpm': {'nulls': 188, 'pct': 0.0235}, 'machine_qtc_ms': {'nulls': 188, 'pct': 0.0235}}

## data/processed/index/ecg_metadata_clean.parquet
- Rows: 749,112
- Top null columns: {'T_cardio': {'nulls': 171692, 'pct': 22.9194}}

## data/processed/qc.parquet
- Rows: 800,035
- Top null columns: none

## data/processed/waveform_qc.parquet
- Rows: 800,035
- Top null columns: {'duplicate_group_id': {'nulls': 798976, 'pct': 99.8676}, 'waveform_qrs_ms': {'nulls': 26911, 'pct': 3.3637}, 'waveform_hr_bpm': {'nulls': 12344, 'pct': 1.5429}, 'machine_hr_bpm': {'nulls': 188, 'pct': 0.0235}}

## data/processed/structured_features.parquet
- Rows: 800,035
- Top null columns: {'lf_hf': {'nulls': 800035, 'pct': 100.0}, 'sdnn_index': {'nulls': 800035, 'pct': 100.0}, 'p_dur_ms': {'nulls': 246683, 'pct': 30.834}, 'pr_ms': {'nulls': 238502, 'pct': 29.8114}, 'qrs_dur_ms': {'nulls': 29656, 'pct': 3.7068}, 'qrs_ms': {'nulls': 29656, 'pct': 3.7068}, 'qt_ms': {'nulls': 28841, 'pct': 3.605}, 'qtc_bazett_ms': {'nulls': 28841, 'pct': 3.605}, 'qtc_fridericia_ms': {'nulls': 28841, 'pct': 3.605}, 't_dur_ms': {'nulls': 21614, 'pct': 2.7016}, 't_amp': {'nulls': 6116, 'pct': 0.7645}, 'p_amp': {'nulls': 2852, 'pct': 0.3565}, 'rmssd': {'nulls': 2059, 'pct': 0.2574}, 'sdnn': {'nulls': 2059, 'pct': 0.2574}, 'pnn50': {'nulls': 2059, 'pct': 0.2574}, 'mean_nn': {'nulls': 1391, 'pct': 0.1739}, 'qrs_amp': {'nulls': 915, 'pct': 0.1144}}

## data/processed/modality_manifest.parquet
- Rows: 6,480,200
- Top null columns: {'corruption_type': {'nulls': 6400280, 'pct': 98.7667}, 'snr_db': {'nulls': 6400280, 'pct': 98.7667}, 'corruption_row': {'nulls': 6400280, 'pct': 98.7667}, 'layout': {'nulls': 3280060, 'pct': 50.6166}, 'container_offset': {'nulls': 3280060, 'pct': 50.6166}, 'container_length': {'nulls': 3280060, 'pct': 50.6166}, 'container_row': {'nulls': 3200140, 'pct': 49.3834}}

## data/processed/linkage/linkage_final.parquet
- Rows: 785,761
- Top null columns: {'tolerance_window_hours': {'nulls': 684338, 'pct': 87.0924}, 'stay_id': {'nulls': 595480, 'pct': 75.7839}, 'hadm_id': {'nulls': 279717, 'pct': 35.5982}, 'source': {'nulls': 216162, 'pct': 27.5099}, 'interval_start': {'nulls': 216162, 'pct': 27.5099}, 'interval_end': {'nulls': 216162, 'pct': 27.5099}, 'offset_minutes': {'nulls': 216162, 'pct': 27.5099}, 'midpoint_offset_minutes': {'nulls': 216162, 'pct': 27.5099}, 'abs_tie_minutes': {'nulls': 216162, 'pct': 27.5099}}

## data/processed/linkage/label_availability.parquet
- Rows: 800,035
- Top null columns: {'stay_id': {'nulls': 609754, 'pct': 76.2159}, 'hadm_id': {'nulls': 293991, 'pct': 36.7473}, 'source': {'nulls': 230436, 'pct': 28.8032}, 'offset_minutes': {'nulls': 230436, 'pct': 28.8032}, 'link_type': {'nulls': 14274, 'pct': 1.7842}}
