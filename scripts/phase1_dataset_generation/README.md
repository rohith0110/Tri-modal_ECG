# Phase 1 - Dataset Generation

This folder contains the active Phase 1 scripts for regenerating the
tri-modal ECG dataset from raw MIMIC-IV-ECG inputs.

The binding specification is
`docs/PIPELINE_SOURCE_OF_TRUTH.md`. This README lists only the scripts that
are part of the current Phase 1 flow, plus local helper modules imported by
those scripts.

## Active scripts

| Stage | Scripts |
| --- | --- |
| 0 - Foundation | `00_lock_versions.py`, `00b_access_check.py`, `01_build_master_index.py` |
| 1 - EHR linkage chain + decision gate | `40_load_ehr_tables.py`, `41_link_exact_overlap.py`, `42_link_tolerance.py`, `43_tie_break_link.py`, `44_label_availability.py`, `45_decision_gate.py` |
| 2 - Patient split | `02_create_patient_split.py` |
| 3 - Signal extraction + pack | `10_extract_ecg_signals.py`, `10b_pack_signals.py`, `14_fit_preprocessing_recipe.py` |
| 4 - Clean image rendering | `20_render_clean_images.py`, `20b_pack_images.py` |
| 5 - Scanlike image rendering | `21_generate_scanlike_images.py`, `21b_pack_scanlike.py` |
| 6 - Tri-modal QC | `30_qc.py` |
| 7 - Waveform QC + structured features | `31_waveform_qc.py`, `32_compute_structured_features.py` |
| 8 - Corrupted signal dataset | `50_build_signals_corrupted.py` |
| 9 - Preprocessed signals | `15_preprocess_signals.py` |
| 10 - Final index, manifest, audits | `03_add_measurements_to_index.py`, `04_cleanup_master_index.py`, `05_build_manifest_and_splits.py`, `33_dataset_audits.py` |

## Local helpers

| Helper | Used by |
| --- | --- |
| `_stage1_common.py` | Shared paths, logging, atomic writes, version stamps, and reporting helpers used across the active stage scripts. |
| `modality_io.py` | Canonical modality reader used by `33_dataset_audits.py` for final manifest smoke checks. |

## Run order

Follow section 9 of `docs/PIPELINE_SOURCE_OF_TRUTH.md` for the exact
preconditions, validation checks, and delete-after-validation rules.

```powershell
cd D:\Coding\MU\Tri-Modal_ECG

.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\00_lock_versions.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\00b_access_check.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\01_build_master_index.py

.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\40_load_ehr_tables.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\41_link_exact_overlap.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\42_link_tolerance.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\43_tie_break_link.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\44_label_availability.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\45_decision_gate.py

.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\02_create_patient_split.py

.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\10_extract_ecg_signals.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\10b_pack_signals.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\14_fit_preprocessing_recipe.py

.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\20_render_clean_images.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\20b_pack_images.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\21_generate_scanlike_images.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\21b_pack_scanlike.py

.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\30_qc.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\31_waveform_qc.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\32_compute_structured_features.py

.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\50_build_signals_corrupted.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\15_preprocess_signals.py

.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\03_add_measurements_to_index.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\04_cleanup_master_index.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\05_build_manifest_and_splits.py
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\33_dataset_audits.py --prep-check
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\33_dataset_audits.py --final
```

Some stage scripts still emit their own report commands with `scripts/` as
the working directory. When running a full stage, prefer the command block
printed by that script and the validation block in the source-of-truth doc.
