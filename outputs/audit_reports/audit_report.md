# Audit Report — 2026-05-29 12:22:58
Plan: B

## 1. Split Audit
  [PASS] Total records: 799,706
  [PASS] Unique subjects: 161,328
  [PASS] Subjects in >1 split: 0
  [PASS]   train: 641,053 ECGs, 129,061 subjects
  [PASS]   val: 80,427 ECGs, 16,133 subjects
  [PASS]   test: 78,226 ECGs, 16,134 subjects

## 2. Duplicate Audit
  [PASS] Duplicate study_ids: 0
  [PASS] Max ECGs per subject: 260
  [PASS] Subjects with >10 ECGs: 18,248
  [PASS] Subjects with >50 ECGs: 795
  [PASS] Mean ECGs per subject: 4.96

## 3. Missingness Audit
  [PASS]   index.rr_interval: 0 nulls
  [PASS]   index.qrs_onset: 0 nulls
  [PASS]   index.qrs_end: 0 nulls
  [PASS]   index.t_end: 0 nulls
  [PASS]   index.split: 0 nulls
  [PASS]   B1.hr_label: 0 nulls (in 10k sample)
  [PASS]   B1.qrs_label: 0 nulls (in 10k sample)
  [PASS]   B1.qtc_label: 0 nulls (in 10k sample)
  [PASS]   B1.hr_bpm: 0 nulls (in 10k sample)
  [PASS]   B1.qrs_dur_ms: 0 nulls (in 10k sample)
  [PASS]   B1.qtc_ms: 0 nulls (in 10k sample)

## 4. Leakage Audit
  [PASS] Checking that forbidden fields are absent from each task's JSONL keys...
  [PASS] B1: keys=['hr_bpm', 'hr_label', 'qrs_dur_ms', 'qrs_label', 'qtc_label', 'qtc_ms', 'signal_path', 'split', 'study_id', 'subject_id'], forbidden violations=none
  [PASS] B2: keys=['clean_signal_path', 'corrupted_signal_path', 'corruption_type', 'snr_db', 'split', 'study_id', 'subject_id'], forbidden violations=none
  [PASS] B3: keys=['labels', 'query', 'split', 'study_id'], forbidden violations=none
  [PASS] B4: keys=['anchor_study_id', 'image_id', 'image_type', 'neg_type', 'signal_id', 'split', 'text_id', 'y_match'], forbidden violations=none
  [PASS] B5: keys=['claim', 'label', 'split', 'study_id'], forbidden violations=none
