# Phase 1 — Dataset Generation

This phase turns the **raw MIMIC-IV ECG release** (WFDB records + metadata CSVs)
into the on-disk **tri-modal ECG dataset** that everything in Phase 2 consumes.
Every script in this folder is part of building the dataset itself: indexing,
splitting, signal extraction, image rendering, QC, integrity auditing, and
regeneration.

> **Where to run from:** all scripts use repo-relative paths of the form
> `../processed/...` and `../data/...`. Run them with your working directory
> set to the `scripts/` folder, e.g.:
>
> ```powershell
> cd D:\Coding\MU\Tri-Modal_ECG\scripts
> python phase1_dataset_generation/01_build_master_index.py
> ```
>
> Running from any other CWD will break the relative paths because the code
> was not modified during this reorganization.

## Inputs (under `data/`)

| File | What it provides |
|---|---|
| `data/record_list.csv` | Master list of ECG studies with `study_id`, `subject_id`, and WFDB path. |
| `data/machine_measurements.csv` | Per-study machine reports (`report_0…report_17`) and structured measurements (`rr_interval`, `qrs_onset/end`, `t_end`, `p/qrs/t_axis`, …). |
| `data/waveform_note_links.csv` | Optional links between waveforms and clinical notes. |
| `data/files/p*/p*/<study>/…` | Raw WFDB ECG waveforms (`.dat` + `.hea`). |

## Outputs (under `processed/`)

| Directory / File | Purpose |
|---|---|
| `processed/index/index.parquet` | Master index (one row per study) with merged `T_machine` text. |
| `processed/index/index_with_split.parquet` | Same as above with a patient-level `split` column added. |
| `processed/index/index_clean.parquet` | Index filtered to studies passing all QC checks. |
| `processed/index/index_clean_with_measurements.parquet` | Clean index enriched with structured measurements (HR, QRS, axis…). |
| `processed/index/splits.json` | Subject-ID lists for each split (provenance for the patient split). |
| `processed/signals_lead2/{study}.npy` | Lead-II waveform (5,000 samples @ 500 Hz). |
| `processed/signals_12lead/{study}.npy` | Full 12-lead waveform (5,000 samples × 12 leads). |
| `processed/signal_metadata/{study}.json` | Per-study extraction metadata. |
| `processed/images_clean/{study}.png` | Lossless clinical-style waveform render of Lead II. |
| `processed/images_scanlike/{study}.jpg` | Deterministically augmented scan-like JPG. |
| `processed/qc/{study}.json` | Tri-modal QC flags (`waveform_ok`, `image_ok`, `text_ok`). |
| `processed/modality_manifest.parquet` | One-row-per-study manifest of every modality file + QC + task availability. |
| `processed/splits_subject_level.parquet` | Compact subject → split table (for downstream joins). |
| `scripts/logs/…` | Log files from extraction / QC / regeneration runs. |

## Pipeline order

Scripts are prefixed by stage number. Run them in order; each stage assumes
the outputs of the previous one.

### Stage 0 — indexing (01–04)

| # | Script | Purpose |
|---|---|---|
| 01 | `01_build_master_index.py` | Builds the master parquet index by joining `record_list.csv` with the chunked-read `machine_measurements.csv` and concatenating `report_0…report_17` into the `T_machine` text field. → `processed/index/index.parquet`. |
| 02 | `02_create_patient_split.py` | Generates the 80/10/10 **patient-level** train/val/test split (numpy seed 42) and writes `index_with_split.parquet` + `splits.json`. Explicitly verifies that the three patient sets are disjoint so a single patient never crosses splits. |
| 03 | `03_add_measurements_to_index.py` | Merges structured measurements (`rr_interval`, `qrs_onset/end`, `t_end`, `p/qrs/t_axis`) onto the clean index → `index_clean_with_measurements.parquet`. *Note: this is logically run **after** the QC stage, but it lives here with the other index-builders for grouping.* |
| 04 | `04_cleanup_master_index.py` | Reads every per-study QC JSON and keeps only rows where `waveform_ok and image_ok and text_ok`. Produces `processed/index/index_clean.parquet`. |

### Stage 1 — modality manifest (05)

| # | Script | Purpose |
|---|---|---|
| 05 | `05_build_manifest_and_splits.py` | (Was `00b_build_manifest_and_splits.py`.) Builds the one-row-per-study `modality_manifest.parquet` recording the path and existence of every modality file, plus task availability, and a compact `splits_subject_level.parquet`. This is the canonical lookup table all Phase-2 scripts join against. |

### Stage 2 — signal extraction (10)

| # | Script | Purpose |
|---|---|---|
| 10 | `10_extract_ecg_signals.py` | Loads each raw WFDB record with `wfdb.rdrecord`, validates it has 12 leads, and writes `signals_lead2/{id}.npy`, `signals_12lead/{id}.npy`, and `signal_metadata/{id}.json`. Tuned for 16 GB RAM and ≤ 8 workers, with batched processing to avoid memory blow-up. |
|  | `_legacy_extract_ecg_signals_v1.py` | Earlier prototype of the extractor (kept for provenance only; do not use). |

### Stage 3 — image rendering (20–24)

| # | Script | Purpose |
|---|---|---|
| 20 | `20_render_clean_images.py` | Renders each Lead-II `.npy` to a 12 × 2.5 inch matplotlib PNG with an ECG-paper grid, normalized to the 99th-percentile absolute amplitude → `processed/images_clean/{id}.png`. |
| 21 | `21_generate_scanlike_images.py` | Reads each clean PNG and produces a deterministic scan-like JPG (rotation ±2°, perspective ±1 %, mild blur, brightness/contrast jitter, JPEG q70-95). Seed is derived from `study_id` so each study renders the same scan every time. → `processed/images_scanlike/{id}.jpg`. |
| 22 | `22_fix_clean_images.py` | Rechecks clean PNGs and regenerates any that are missing or corrupt. |
| 23 | `23_regen_clean_scanlike.py` | Multiprocessing regenerator for both clean + scan-like images from a regen list (used to recover from the ~104 K mid-run failure). |
| 24 | `24_regen_missing.py` | Sequential single-process regen of any missing clean / scan-like files (small batches). |

### Stage 4 — QC and integrity (30–32)

| # | Script | Purpose |
|---|---|---|
| 30 | `30_qc.py` | Per-study tri-modal QC. For each row in `index_with_split.parquet` checks waveform shape (= 5,000), both image files exist, and `T_machine` is non-empty. → `processed/qc/{id}.json`. |
| 31 | `31_corrupt_check.py` | Focused integrity check on clean PNGs (PIL verify + OpenCV decode + nonzero dims). Writes missing/corrupt lists to `scripts/logs/`. |
| 32 | `32_image_integrity_check.py` | Broader audit covering both clean PNGs and scan-like JPGs. Writes the structured `scripts/logs/dataset_integrity_summary.json` consumed downstream. |

### Dev helpers (not part of the pipeline)

| Script | Purpose |
|---|---|
| `_test_signal_extraction.py` | Smoke test: pulls 10 random rows from the split index, loads the WFDB record, and dumps shapes — used during development. |
| `_test_ecg_rendering.py` | Smoke test: renders 10 random Lead-II signals to a scratch directory. |

## End-to-end run order (clean reproduction)

```powershell
cd D:\Coding\MU\Tri-Modal_ECG\scripts

# Indexing
python phase1_dataset_generation/01_build_master_index.py
python phase1_dataset_generation/02_create_patient_split.py

# Signals
python phase1_dataset_generation/10_extract_ecg_signals.py

# Images
python phase1_dataset_generation/20_render_clean_images.py
python phase1_dataset_generation/21_generate_scanlike_images.py

# QC + integrity (then fix any gaps)
python phase1_dataset_generation/30_qc.py
python phase1_dataset_generation/31_corrupt_check.py
python phase1_dataset_generation/32_image_integrity_check.py
python phase1_dataset_generation/22_fix_clean_images.py        # if needed
python phase1_dataset_generation/23_regen_clean_scanlike.py    # if needed
python phase1_dataset_generation/24_regen_missing.py           # if needed

# Final clean index + measurement enrichment + manifest
python phase1_dataset_generation/04_cleanup_master_index.py
python phase1_dataset_generation/03_add_measurements_to_index.py
python phase1_dataset_generation/05_build_manifest_and_splits.py
```

## Expected counts (sanity check)

These match what the Tri-Modal ECG report records as the as-built dataset:

| Artifact | Expected count | Total size |
|---|---:|---:|
| `signals_lead2/` | 800,033 `.npy` | ≈ 15.7 GB |
| `signals_12lead/` | 800,031 `.npy` | ≈ 187.5 GB |
| `signal_metadata/` | 781,230 `.json` | ≈ 76 MB |
| `images_clean/` | 800,033 `.png` | ≈ 140.8 GB |
| `images_scanlike/` | 800,033 `.jpg` | ≈ 68.2 GB |
| `qc/` | 651,437 `.json` | ≈ 57 MB |
| `index/index.parquet` | 800,035 rows | — |
| `index/index_with_split.parquet` | 800,033 rows | — |
| `index/index_clean.parquet` | 799,706 rows | — |
| `index/index_clean_with_measurements.parquet` | 799,706 rows / 161,328 patients | — |
| Patient-level split | 80 / 10 / 10 with **zero** patient overlap | — |

The cleaned dataset removes 329 studies (out of 800,035) that failed at least
one QC gate. After regeneration the final audit reports only 2 missing files
per image modality and **0** corrupt files.
