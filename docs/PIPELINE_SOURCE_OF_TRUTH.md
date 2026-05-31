# Tri-Modal ECG Pipeline — Source of Truth (Phase 1)

**Status:** Plan only. No code yet. This document is the single source of
truth for **regenerating the Phase 1 dataset** (raw MIMIC-IV-ECG → on-disk
tri-modal dataset). An agent following this document should not need to
open `ECG_Benchmark_Neutral_Implementation_Plan_Plan_A_B.docx` or
`TriModal_ECG_Truth.docx` while working on Phase 1; every binding rule
that affects dataset construction has been quoted or summarized here.

Phase 2 (model training, benchmark suite, paper figures) is **out of
scope** for this document. When work moves to Phase 2, the agent should
read the Plan A/B doc §5 (Plan A tasks), §6 (Plan B tasks), §7 (paper
evidence) for that work.

**Authority hierarchy.** Where the two source docs disagree, **Plan A/B
wins.** Truth-doc–only constraints are preserved when they don't conflict.
Decisions in this document override both source docs (the user has
explicitly resolved several clashes — see §2).

---

## 0. Quick orientation

The agent is rebuilding the dataset from scratch because the original
build:

1. Used per-study small files everywhere → 4 million files in
   `data/processed/` (previously root-level `processed/`), painful to operate on / transfer.
2. Was completed before the Plan A/B spec landed → missing several
   required artifacts (preprocessed-signal modality, comprehensive QC
   flags, version lock, EHR labels, etc.).
3. Used the wrong split ratio (80/10/10 per Truth doc rather than
   70/10/20 per Plan A/B).
4. Was generated assuming Plan B (no EHR linkage) because the EHR
   datasets weren't downloaded. They are now (see §5).
5. All teh python code and everything must be done from the ecg_env virtual environment in the root of the repo

The regeneration consolidates the storage layout **and** brings the
pipeline to Plan A/B compliance in one pass. The work plan in §11
orders these changes so the heaviest re-computations happen only once.

---

## 1. Non-negotiable rules (from Plan A/B §1)

These rules apply to every step below. If a downstream design choice
would violate one of these, the choice is wrong, not the rule.

| Rule                           | Implementation requirement                                                                                                                                              |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Patient-level split only**   | Split by `subject_id` before any modeling. A subject appears in exactly one of train/val/test. Verify zero overlap.                                                     |
| **Version lock**               | Record exact versions of MIMIC-IV-ECG, MIMIC-IV Hosp, MIMIC-IV-ED, WFDB, NeuroKit2, plotting code, and every Python lib used. Stored in `config/dataset_versions.yaml`. |
| **No label-to-input leakage**  | Every task has a modality allowlist. Fields that the label is derived from are forbidden as inputs. Recorded in `config/task_input_policy.yaml`.                        |
| **Timing rules before labels** | For any label, define whether it's retrospective association or prospective prediction _before_ extracting it.                                                          |
| **Report missingness**         | Every cohort table records `n_subjects`, `n_ECGs`, positive count, prevalence, missingness.                                                                             |
| **Confidence intervals**       | Report 95 % CIs with **patient-level** bootstrap for primary metrics. (Phase 2.)                                                                                        |
| **Do not overclaim novelty**   | The paper claim is "EHR-grounded, leakage-audited multimodal ECG benchmark." Never "first multimodal ECG benchmark." (Phase 2.)                                         |
| **Raw MIMIC never published**  | No raw MIMIC data in any public repo or release artifact. Scripts and configs only.                                                                                     |

---

## 2. Locked storage decisions

The user has chosen one option per clash. The matrix below is the **final
state** — no alternatives. **Migration policy:** delete-as-you-go per
stage; the old per-study folder for each modality is deleted immediately
after the new consolidated artifact for that modality is built and
validated. No `archive/` directory is kept on disk. The full per-stage
procedure (which artifact is built when, which old folder is deleted
when, peak disk usage) is in **§9 — Stage-by-stage migration plan**.
Rollback story is "regenerate from `data/raw/files/` via the
version-locked extractor scripts" — the raw WFDB waveforms are the only
true source of truth and are never touched.

| Folder today                             | Decision                                                 | Final on-disk artifact                                                                                            | Notes                                                                                                                                                              |
| ---------------------------------------- | -------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `qc/` 651 K × JSON                       | **A-2** parquet only; delete JSONs                       | `data/processed/qc.parquet`                                                                                       | Truth-doc literal §5.5 path violated; content preserved.                                                                                                           |
| `signal_metadata/` 781 K × JSON          | **B-1** parquet only                                     | `data/processed/signal_metadata.parquet`                                                                          | Truth doc doesn't pin a path here.                                                                                                                                 |
| `signals_lead2/` 800 K × NPY (15.7 GB)   | **C-2** HDF5 only; delete `.npy` folder after validation | `data/processed/signals/lead2_raw.h5` + (Stage 9 optional) `lead2_preprocessed.h5`                                | One file per modality kind.                                                                                                                                        |
| `signals_12lead/` 800 K × NPY (187.5 GB) | **C-2** HDF5 only; delete `.npy` folder after validation | `data/processed/signals/twelve_lead_raw_shard_{00..04}.h5` (~5 shards × ~40 GB) + manifest                        | Sharded for transfer; preprocessed twin added in Stage 9 if materialized.                                                                                          |
| `signals_corrupted/` 80 K × NPY (1.5 GB) | **D-3** single parquet                                   | `data/processed/signals_corrupted.parquet` (columns: `study_id, corruption_type, snr_db, signal[5000] float32`)   | Keep persisted (not regenerate on the fly). 2 K anchors × 8 corruptions × 5 SNRs ≈ 80 K rows ≈ 1.6 GB. Plan A/B is silent on N; 2 K anchors is resolved.           |
| `images_clean/` 800 K × PNG (140.8 GB)   | **E-1 / fewer shards** — **both layouts**                | `data/processed/images/clean_lead2_shard_{000..099}.tar` (~100 shards × ~1.4 GB) + `images/clean_lead2_manifest.parquet` **AND** `clean_12lead_shard_{000..029}.tar` (low-DPI/quality) + `images/clean_12lead_manifest.parquet` | Per §12 resolution: render both Lead-II strip AND 12-lead 3×4 grid; minimize 12-lead size with low DPI and high JPEG/PNG compression. |
| `images_scanlike/` 800 K × JPG (68.2 GB) | **F-1 / fewer shards** — **both layouts**                | `data/processed/images/scanlike_lead2_shard_{000..049}.tar` + `scanlike_lead2_manifest.parquet` **AND** `scanlike_12lead_shard_{000..017}.tar` + `scanlike_12lead_manifest.parquet` | Always shipped (Truth doc §5.4 D2 mandates and `30_qc.py` reads it). Same shape as clean; both layouts. |

### 2.1 Cross-cutting manifest schema

A single `data/processed/modality_manifest.parquet` is the canonical lookup.
One row per `(study_id, modality_kind)`:

```txt
study_id           int64        -- ECG study identifier
subject_id         int64        -- patient identifier
modality_kind      str          -- one of {raw_lead2, raw_12lead,
                                --         preprocessed_lead2, preprocessed_12lead,
                                --         image_clean, image_scanlike,
                                --         signal_corrupted}
container_path     str          -- relative path to .h5/.tar/.parquet (inside data/processed/)
container_row      int64?       -- row index inside HDF5 / parquet (null for tar)
container_offset   int64?       -- byte offset inside tar (null for h5/parquet)
container_length   int64?       -- payload length in bytes (null for h5/parquet)
sha256             str          -- hex digest of the modality payload bytes
dataset_version    str          -- e.g. "v2.0.0" — stamped by writer
created_at         timestamp_ns -- UTC writer timestamp
```

The manifest is the **only** thing downstream code reads to find a study's
modality bytes. Consumers go through a single helper:

```txt
read_modality(study_id, kind) -> bytes-or-array
```

This isolates the consumer code from the container format and gives a
single chokepoint for migrations or rollbacks.

### 2.2 Per-shard / per-container header metadata

Every consolidated container also embeds its own self-describing header:

| Container | Where the header lives                                       | Required fields                                                                                                       |
| --------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| HDF5      | root group attributes                                        | `dataset_version`, `created_at_iso`, `modality_kind`, `n_studies`, `chunk_shape`, `compression`, `script_commit_hash` |
| Tar       | first member of the tar named `MANIFEST.json`                | `dataset_version`, `created_at_iso`, `modality_kind`, `studies` list with `(study_id, offset, length, sha256)`        |
| Parquet   | parquet schema metadata (`pa.schema().with_metadata({...})`) | `dataset_version`, `created_at_iso`, `modality_kind`, `n_rows`, `script_commit_hash`                                  |

Self-description means: even if `modality_manifest.parquet` is lost, any
container alone can be inspected and re-indexed. Defense in depth.

### 2.3 Final on-disk tree (post-migration)

```plaintext
data/
├── processed/
│   ├── index/                                          # already consolidated
│   │   ├── ecg_metadata.parquet                        # § renamed; was index.parquet
│   │   ├── ecg_metadata_with_split.parquet
│   │   ├── ecg_metadata_clean.parquet
│   │   └── ecg_metadata_clean_with_measurements.parquet
│   ├── qc.parquet                                      # was qc/   (651K → 1)
│   ├── waveform_qc.parquet                             # NEW — per Plan A/B §9.1
│   ├── signal_metadata.parquet                         # was signal_metadata/   (781K → 1)
│   ├── signals/
│   │   ├── lead2_raw.h5                                # was signals_lead2/   (800K → 1)
│   │   ├── lead2_preprocessed.h5                       # NEW — Plan A/B §4.4
│   │   ├── twelve_lead_raw_shard_{00..04}.h5           # was signals_12lead/  (800K → 5)
│   │   ├── twelve_lead_preprocessed_shard_{00..04}.h5  # NEW
│   │   └── signals_manifest.parquet                    # study_id -> (file, row)
│   ├── signals_corrupted.parquet                       # was signals_corrupted/ (80K → 1)
│   ├── images/                                         # both layouts per §12 resolution
│   │   ├── clean_lead2_shard_{000..099}.tar            # was images_clean/    (800K → 100), Lead-II strip
│   │   ├── clean_lead2_manifest.parquet
│   │   ├── clean_12lead_shard_{000..029}.tar           # NEW — 3×4 grid + rhythm strip, low DPI/quality
│   │   ├── clean_12lead_manifest.parquet
│   │   ├── scanlike_lead2_shard_{000..049}.tar         # was images_scanlike/ (800K → 50), Lead-II strip
│   │   ├── scanlike_lead2_manifest.parquet
│   │   ├── scanlike_12lead_shard_{000..017}.tar        # NEW — scanlike of 12-lead grid
│   │   └── scanlike_12lead_manifest.parquet
│   ├── structured_features.parquet                     # NEW — Plan A/B §4.5
│   ├── splits_subject_level.parquet
│   ├── modality_manifest.parquet                       # canonical lookup
│   └── task_jsonl/                                     # Phase 2 outputs (unchanged)
│       ├── taskA_verification.jsonl
│       ├── taskB_temporal_grounding.jsonl
│       ├── taskC_plausibility.jsonl
│       ├── taskB1_measurement_blind.jsonl
│       ├── taskB2_noise_robustness.jsonl
│       └── taskB5_contradiction_detection.jsonl
└── raw/                                                # Raw datasets (previously directly under data/)
    ├── files/                                          # MIMIC-IV-ECG waveforms
    ├── record_list.csv
    ├── machine_measurements.csv
    ├── waveform_note_links.csv
    ├── machine_measurements_data_dictionary.csv
    ├── mimic-iv-hosp-3.1/
    │   └── hosp/
    │       ├── admissions.csv.gz
    │       ├── patients.csv.gz
    │       ├── diagnoses_icd.csv.gz
    │       ├── d_icd_diagnoses.csv.gz
    │       ├── labevents.csv.gz
    │       ├── d_labitems.csv.gz
    │       ├── prescriptions.csv.gz
    │       ├── emar.csv.gz
    │       ├── transfers.csv.gz
    │       └── services.csv.gz
    ├── mimic-iv-ed-2.2/
    │   └── ed/
    │       ├── edstays.csv.gz
    │       ├── diagnosis.csv.gz
    │       ├── triage.csv.gz
    │       ├── vitalsign.csv.gz
    │       ├── medrecon.csv.gz
    │       └── pyxis.csv.gz
    └── ehr_cache/                                      # cached Parquet tables
```

**Net file count change:** 4,000,000+ files → **~170 files** (100 image
shards + 50 scanlike shards + 5 12-lead HDF5 shards + ~15 parquet/h5
artifacts). Total size unchanged (~414 GB) or smaller with HDF5 chunk
compression.

### 2.4 Dataset Reorganization (De-fragmentation)

To reduce fragmentation of the dataset, raw data and processed artifacts are consolidated under a single unified `data/` folder at the project root. This reorganization resolves the split across root-level `data/` and `processed/` folders.

- **Previous location of raw data:** `data/` (root-level)
- **Current location of raw data:** `data/raw/` (e.g., raw MIMIC files are now in `data/raw/files/`, etc.)
- **Previous location of processed output:** `processed/` (root-level)
- **Current location of processed output:** `data/processed/`

All scripts and configuration files must refer to these new nested paths. This keeps raw inputs cleanly separated from pipeline-generated outputs while containing all data artifacts within a single top-level directory.

---

## 3. Plan A/B gaps in the current pipeline

These are things the **Plan A/B spec mandates** but the current Phase 1
pipeline doesn't do. All of them must be added during the regeneration.

### 3.1 Missing: `config/dataset_versions.yaml` (Plan A/B Rule "Version lock")

Required artifact. Must list, for every external dataset and every
pinned library:

```yaml
mimic_iv_ecg:
  version: "1.0"
  source_path: "data/raw/files/"
  row_counts:
    record_list_csv: 800035
    machine_measurements_csv: 800035
  date_accessed: "2026-XX-XX"
  sha256_of_record_list: "..."
mimic_iv_hosp:
  version: "3.1"
  source_path: "data/raw/mimic-iv-hosp-3.1/"
  date_accessed: "2026-05-30"
  table_row_counts:
    admissions: 546028
    patients: 364627
    diagnoses_icd: 6364488
    d_icd_diagnoses: 112107
    labevents: 158374764
    d_labitems: 1650
mimic_iv_ed:
  version: "2.2"
  source_path: "data/raw/mimic-iv-ed-2.2/"
  date_accessed: "2026-05-30"
  table_row_counts:
    edstays: <fill>
    diagnosis: <fill>
    triage: <fill>
    vitalsign: <fill>
    medrecon: <fill>
    pyxis: <fill>
libraries:
  python: "3.11.X"
  numpy: "X.Y.Z"
  pandas: "X.Y.Z"
  pyarrow: "X.Y.Z"
  h5py: "X.Y.Z"
  wfdb: "X.Y.Z"
  neurokit2: "X.Y.Z"
  matplotlib: "X.Y.Z"
  opencv_python: "X.Y.Z"
  torch: "X.Y.Z"
dataset_version_stamp: "v2.0.0" # incremented when regenerating
```

This file is read by every consolidated-artifact writer and its
`dataset_version_stamp` is what lands in container header metadata
(§2.2).

### 3.2 Missing: rich waveform QC + cross-source consistency (Plan A/B §4.3 + §4.6)

Current pipeline writes a `qc/{id}.json` with three booleans:
`waveform_ok / image_ok / text_ok`. Spec requires more. The new
`data/processed/waveform_qc.parquet` schema:

| Column                    | Source / rule                                                                                 |
| ------------------------- | --------------------------------------------------------------------------------------------- |
| `study_id`, `subject_id`  | identifiers                                                                                   |
| `decode_ok`               | `wfdb.rdrecord` succeeded and signal array is non-null                                        |
| `length_ok`               | sample count corresponds to 10 s ± tolerance @ 500 Hz                                         |
| `lead_count_ok`           | exactly 12 leads present                                                                      |
| `lead_names_ok`           | matches `{I, II, III, aVR, aVL, aVF, V1..V6}` after mapping                                   |
| `nan_inf_flag`            | any NaN or Inf anywhere in the signal                                                         |
| `flatline_lead_flag`      | per-lead variance below threshold for > 90 % of record                                        |
| `flatline_leads`          | list of lead names that flatlined                                                             |
| `extreme_amplitude_flag`  | amplitude outside physiologically plausible range                                             |
| `duplicate_waveform_flag` | same/near-identical signal across multiple `study_id`s (detect via SHA256 of `lead_II[::10]`) |
| `duplicate_group_id`      | id of the duplicate group (or null)                                                           |
| `sqi_per_lead`            | list of 12 floats — SQI per lead (NeuroKit2 `ecg_quality` average)                            |
| `sqi_aggregate`           | mean of `sqi_per_lead`                                                                        |
| `sqi_tier`                | `high (≥0.8) / medium (0.6–0.8) / low (<0.6)`                                                 |
| `waveform_hr_bpm`         | HR derived from waveform R-peaks (NeuroKit2)                                                  |
| `machine_hr_bpm`          | HR derived from `60000 / rr_interval`                                                         |
| `hr_consistency_flag`     | true if `abs(waveform - machine) > 10 bpm` AND relative diff > 15 %                           |
| `waveform_qrs_ms`         | derived QRS duration (NeuroKit2 wavelet)                                                      |
| `machine_qrs_ms`          | `qrs_end - qrs_onset` from machine measurements                                               |
| `qrs_consistency_flag`    | abs diff > 20 ms                                                                              |
| `report_consistency_flag` | text says tachy/brady/AF while measurements strongly disagree                                 |

Plus the original tri-modal QC flags retained:

| Column              | Source / rule                       |
| ------------------- | ----------------------------------- |
| `image_clean_ok`    | image_clean blob exists and decodes |
| `image_scanlike_ok` | scanlike blob exists and decodes    |
| `text_ok`           | `T_machine` non-empty               |
| `notes`             | free-text                           |

**Plan A/B §4.3 mandate:** _"Do not drop low-quality records yet. Create
flags and quality tiers so analyses can include/exclude intentionally."_
So even severe failures land in `data/processed/waveform_qc.parquet`; downstream `_clean`
index filters them at the index-cleanup stage.

### 3.3 Missing: preprocessed-signal modality (Plan A/B §4.4)

> _"Store raw and preprocessed signal as separate modalities. Never
> overwrite raw data."_

A second signal modality must exist with the recommended filter chain:

| Operation               | Default                                                                | Stored metadata in HDF5 attrs                           |
| ----------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------- |
| Baseline-wander removal | zero-phase high-pass ~0.5 Hz                                           | `hp_cutoff_hz`, `hp_order`, `filter_lib_version`        |
| Powerline notch         | 60 Hz per user resolution (configurable 50/60 Hz default 60 Hz)        | `notch_freq_hz`, `notch_q_factor`                       |
| Low-pass                | ~100–150 Hz                                                            | `lp_cutoff_hz`, `lp_order`                              |
| Resampling              | none (keep 500 Hz)                                                     | `original_fs`, `target_fs`                              |
| Normalization           | per-lead z-score, scaler fit on **train split only**                   | `scaler_type=zscore_per_lead`, `scaler_fit_split=train` |

Output containers: `data/processed/signals/lead2_preprocessed.h5` and
`data/processed/signals/twelve_lead_preprocessed_shard_{00..04}.h5`. Same schema as the
raw twins. Manifest gets new rows with `modality_kind=preprocessed_*`.

### 3.4 Missing: structured features (Plan A/B §4.5)

> _"Structured features … NeuroKit2/FeatureDB-like HRV, morphology,
> intervals, SQI, plus machine measurements if explicitly allowed."_

New artifact: `data/processed/structured_features.parquet`, one row per study,
columns include at minimum:

- HRV: `rmssd, sdnn, pnn50, lf_hf, mean_nn, sdnn_index`
- Morphology: `p_amp, qrs_amp, t_amp, p_dur_ms, qrs_dur_ms, t_dur_ms`
- Intervals: `pr_ms, qrs_ms, qt_ms, qtc_bazett_ms, qtc_fridericia_ms`
- SQI: `sqi_high / sqi_med / sqi_low` (per-lead and aggregate)
- Machine measurements: `machine_rr_ms, machine_qrs_onset, machine_qrs_end, machine_p_axis, machine_qrs_axis, machine_t_axis, cart_id, filtering, bandwidth`

This is computed from the preprocessed signal. Heavy compute (NeuroKit2
is ~1–3 s per ECG). Parallelize per §8.

### 3.5 Missing: split ratio is wrong (Plan A/B §4.7 vs Truth doc §5.2)

| Source         | Split                                                    |
| -------------- | -------------------------------------------------------- |
| Truth doc §5.2 | 80 / 10 / 10                                             |
| Plan A/B §4.7  | **70 / 10 / 20**, stratified by key labels when possible |

**Plan A/B wins.** New split: 70 train / 10 val / 20 test. Re-do
`02_create_patient_split.py` with the new ratio and **stratify** by HR
bucket and presence of EHR linkage tier so each split has a comparable
mix.

### 3.6 Missing: 12-lead clinical-layout image (Plan A/B §4.5)

Current image render is **Lead II only**, single horizontal strip. Plan
A/B §4.5 requires:

> _"Render 3×4 12-lead grid plus rhythm strip if implemented. Standard
> paper speed 25 mm/s and amplitude 10 mm/mV. Store exact plotting code."_

Two image modalities going forward:

| Modality                      | Layout                                        | Used for                                            |
| ----------------------------- | --------------------------------------------- | --------------------------------------------------- |
| `image_clean_lead2` (current) | single Lead II strip, 12×2.5 in               | Truth-doc Track 1 / MVP tasks A, B, C               |
| `image_clean_12lead` (NEW)    | 3×4 grid + rhythm strip, paper-speed-grounded | Plan A/B Track 2 + cross-modal verification (B4/B6) |

Same idea for `image_scanlike_*`. Store both. The image manifest gets a
`layout` column.

**Size Optimization Resolution:** To address critical storage constraints, ensure both image modalities are stored with the smallest possible footprint. Implement this by minimizing dimensions, using low DPI/resolution, and applying optimized/maximum compression settings before writing them to the tar shards.

### 3.7 Missing: EHR linkage (Plan A/B §3)

The original pipeline chose Plan B because EHR data wasn't available.
That is no longer true (§5). Plan A/B says (§3):

> _"Do not choose Plan A because it is more exciting. Choose Plan A only
> if the linkage produces enough clean, temporally defensible labels for
> multiple clinically meaningful tasks. If linkage is weak or ambiguous,
> Plan B is safer and more honest."_

The decision can only be made _after_ running the linkage feasibility
report. So Phase 1 must produce that report and persist its outputs even
if Plan B remains the chosen path. This is a new sub-stage of Phase 1.

#### 3.7.1 Linkage feasibility procedure (Plan A/B §3.1)

1. Build the ECG metadata universe (already exists as
   `ecg_metadata.parquet`).
2. **Exact overlap linkage** — for each ECG, find:
   - hospital admissions where `admittime ≤ ecg_time ≤ dischtime`
   - ED stays where `intime ≤ ecg_time ≤ outtime`
3. **Tolerance linkage** — for ECGs with no exact overlap, find the
   nearest admission / ED stay within ±6 h, ±12 h, ±24 h, ±7 days.
4. **Attach label availability** — for each candidate linked ECG, count:
   ICD labels, key labs within ±6 h / ±24 h, mortality observable,
   readmission eligible.
5. **Compute linkage tiers**:

| Tier   | Definition                                                   | Allowed use           |
| ------ | ------------------------------------------------------------ | --------------------- |
| **L3** | ECG inside admission/ED window; direct `hadm_id`/`stay_id`   | Primary Plan A labels |
| **L2** | Within tolerance window ≤ 24 h                               | Sensitivity analyses  |
| **L1** | Same subject has admissions but no defensible temporal match | Descriptive only      |
| **L0** | No usable EHR link                                           | Plan B tasks          |

1. **Tie-breaking** (§3.4): hospital wins over ED if both `hadm_id` and
   `stay_id` exist. Multiple overlaps → smallest `|ecg_time − midpoint|`,
   then exact > tolerance, then lowest id.
2. **Persist** all candidate links before selecting (don't overwrite).

#### 3.7.2 Decision gate thresholds (§3.3)

| Path           | Hard criteria                                                                                                             |
| -------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Plan A**     | ≥ 40 % L3-or-high-confidence-L2 ICD; ≥ 20 % key lab within ±24 h; risk outcomes with ≥ 1000 positives or ≥ 1 % prevalence |
| **Hybrid A+B** | 30–40 % clean linkage, or only some tasks have adequate coverage                                                          |
| **Plan B**     | < 30 % clean linkage                                                                                                      |

The agent **runs the analysis and reports the numbers**; the chosen path
is then frozen in `config/decision.yaml` along with the linkage
distribution. No skipping.

#### 3.7.3 Required artifacts of the linkage stage

| File                                                       | Content                                                                                                      |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | --- | --------------------------------------------- |
| `data/processed/linkage/candidate_links.parquet`           | every candidate `(study_id, hadm_id, stay_id, link_type, offset_minutes)`                                    |
| `data/processed/linkage/linkage_final.parquet`             | one row per study after tie-breaking with `link_tier, hadm_id, stay_id, offset_minutes`                      |
| `data/processed/linkage/label_availability.parquet`        | per study: `icd_available, lab_K_within_6h, lab_K_within_24h, …, mortality_observable, readmission_eligible` |
| `outputs/audit_reports/linkage_feasibility_report.md` | Tables L1–L4 + Figure L1 + 20 manual-audit examples                                                          |
| `config/decision.yaml`                                | `{chosen_path: A                                                                                             | B   | hybrid, threshold_pass: {…}, frozen_at: ISO}` |

### 3.8 Missing: required audits (Plan A/B §1.2)

The Plan A/B doc requires four audit logs as final artifacts:

| Audit                  | What it contains                                              | Output                                       |
| ---------------------- | ------------------------------------------------------------- | -------------------------------------------- |
| `split_audit.md`       | proof of zero subject overlap across train/val/test           | `outputs/audit_reports/split_audit.md`       |
| `duplicate_audit.md`   | duplicate `study_id`, near-identical waveforms across studies | `outputs/audit_reports/duplicate_audit.md`   |
| `missingness_audit.md` | null rates per field per modality                             | `outputs/audit_reports/missingness_audit.md` |
| `leakage_audit.md`     | each task's allowed/forbidden field list + verification       | `outputs/audit_reports/leakage_audit.md`     |
| `linkage_audit.md`     | Plan A only — provenance of every EHR linkage                 | `outputs/audit_reports/linkage_audit.md`     |
| `access_check.md`      | every required raw table exists with expected row count       | `outputs/audit_reports/access_check.md`      |

These are mandatory before Phase 2 starts.

### 3.9 Missing: per-task `task_input_policy.yaml`

Plan A/B Rule "No label-to-input leakage" requires a machine-readable
policy per task. New file `config/task_input_policy.yaml`:

```yaml
B1_measurement_blind:
  allowed_inputs: [signal_lead2_raw, signal_lead2_preprocessed, signal_12lead_raw]
  forbidden_inputs: [machine_measurements, machine_report_text, structured_features]
B2_noise_robustness:
  allowed_inputs: [signal_lead2_raw, signal_lead2_preprocessed]
  forbidden_inputs: [machine_measurements, machine_report_text, structured_features]
B3_temporal_grounding:
  allowed_inputs: [signal_lead2_raw, signal_lead2_preprocessed]
  forbidden_inputs: [machine_measurements]
B4_cross_modal:
  allowed_inputs: [*]
  forbidden_inputs: []
B5_contradiction:
  allowed_inputs: [signal_lead2_raw, signal_lead2_preprocessed, machine_report_text_corrupted]
  forbidden_inputs: [machine_measurements, machine_report_text_original]
B6_difficulty_verification:
  allowed_inputs: [*]
  forbidden_inputs: []
# (and Plan A tasks A1..A6 if Plan A is chosen)
```

Phase 2's `10_run_audits.py` already exists; it's the leakage audit
consumer. Phase 1 needs to produce this policy file.

### 3.10 Missing: B5 contradiction must keep originals (Plan A/B §6.6)

Current `06_task_B5_contradiction_detection.py` already does this
correctly (`original_report_text` + `corrupted_report_text` etc.). No
change. Listed here for completeness of the audit.

### 3.11 Pre-existing bug: `hash()` non-determinism

`05_task_B2_noise_robustness.py` line:

```python
seed_key = abs(hash((int(row.study_id), corruption, snr_db))) % (2**31)
```

Python's built-in `hash()` is **non-deterministic across processes**
unless `PYTHONHASHSEED` is set at interpreter startup. This was hidden by
the fact that the corrupted files were persisted and not regenerated.
Once `signals_corrupted.parquet` is rebuilt per decision D-3, fix at
source:

```python
import hashlib
def _seed(study_id: int, corruption: str, snr_db: int) -> int:
    key = f"{study_id}|{corruption}|{snr_db}".encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:4], "big") % (2**31)
```

Stable across processes, machines, and Python versions.

---

## 4. Pipeline modification roadmap (per phase, per script)

Numbered prefixes refer to the current scripts under
`scripts/phase1_dataset_generation/`. "**Modify**" = change the existing
script; "**New**" = author a new script.

### Phase 0 — config and access check (NEW stage)

| #   | Script                | Status | Purpose                                                                                                                 |
| --- | --------------------- | ------ | ----------------------------------------------------------------------------------------------------------------------- |
| 00  | `00_lock_versions.py` | New    | Detect installed library versions, hash every raw input table, record row counts, write `config/dataset_versions.yaml`. |
| 00b | `00b_access_check.py` | New    | Verify every table required by §5.1 exists with expected schema. Write `outputs/audit_reports/access_check.md`.         |

### Phase 1 — index building

| #   | Script                            | Status | Changes                                                                                                                                                                                                                                                                                                                                                                                                                          |
| --- | --------------------------------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 01  | `01_build_master_index.py`        | Modify | Output renamed to `data/processed/index/ecg_metadata.parquet`. Add columns: `has_machine_measurements`, `has_machine_report_text`, `machine_hr_bpm`, `machine_qrs_ms`, `machine_qtc_ms`, `cart_id`, `filtering`, `bandwidth`. Ingest cardiologist `T_cardio` from `waveform_note_links.csv` (nullable) but do not gate tasks on it. Keep original report lines as list column `report_lines` alongside `T_machine`. |
| 02  | `02_create_patient_split.py`      | Modify | Ratio **70 / 10 / 20** (was 80/10/10). Stratify by HR bucket _and_ EHR linkage tier (after §3.7 runs). Write `data/processed/splits_subject_level.parquet` plus `splits.json`. Hard check zero subject overlap.                                                                                                                                                                                                                  |
| 03  | `03_add_measurements_to_index.py` | Modify | Run after QC stage. Add missing-flag columns per measurement so downstream consumers can tell "0" from "missing".                                                                                                                                                                                                                                                                                                                |
| 04  | `04_cleanup_master_index.py`      | Modify | Reads from `data/processed/waveform_qc.parquet` and `data/processed/qc.parquet` (not per-study JSON). Filter rule unchanged.                                                                                                                                                                                                                                                                                                     |
| 05  | `05_build_manifest_and_splits.py` | Modify | Builds the new canonical `data/processed/modality_manifest.parquet` with the §2.1 schema.                                                                                                                                                                                                                                                                                                                                        |

### Phase 2 — signal extraction (NEW: emit HDF5 directly)

| #   | Script                      | Status | Changes                                                                                                                                                                                                                                                                                                                                                |
| --- | --------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 10  | `10_extract_ecg_signals.py` | Modify | Pattern B writer (see §7.2). Each ProcessPoolExecutor worker writes a private partial HDF5 (`data/processed/partial/lead2_worker_{wid}.h5` and `data/processed/partial/twelve_lead_worker_{wid}.h5`). Worker also returns a `signal_metadata` dict to the main process.                                                                                |
| 10b | `10b_pack_signals.py`       | New    | Offline packer. Consumes the `data/processed/partial/*.h5` files and writes the canonical `data/processed/signals/lead2_raw.h5` plus `data/processed/signals/twelve_lead_raw_shard_{00..04}.h5` (5 shards). Builds `data/processed/signals/signals_manifest.parquet` and stamps HDF5 with §2.2 attrs. Deletes `partial/` on success.                    |

### Phase 3 — preprocessed signals (NEW stage)

| #   | Script                     | Status | Changes                                                                                                                                                                                                                                                                                                                                                                            |
| --- | -------------------------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 15  | `15_preprocess_signals.py` | New    | Read raw HDF5, apply baseline-wander HP, 60 Hz notch, low-pass, per-lead z-score (scaler fit on **train split only**, persisted to `config/scalers/lead2_zscore_train.npz`). Write `data/processed/signals/lead2_preprocessed.h5` and `data/processed/signals/twelve_lead_preprocessed_shard_{00..04}.h5`. Pattern B; record filter params in HDF5 attrs (§3.3). |

### Phase 4 — image rendering

| #     | Script                           | Status | Changes                                                                                                                                                                                                                                                                                                                                                                          |
| ----- | -------------------------------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 20    | `20_render_clean_images.py`      | Modify | Pattern B writer. Each worker writes its own `data/processed/partial/clean_worker_{wid}.tar` of raw PNGs. Produces a second modality: **12-lead 3×4 grid + rhythm strip** at 25 mm/s × 10 mm/mV — written into a parallel tar set `data/processed/partial/clean_12lead_worker_{wid}.tar`. Minimize image footprint per user resolution.                                           |
| 20b   | `20b_pack_images.py`             | New    | Offline packer. Re-shards partial tars into 100 canonical `data/processed/images/clean_shard_{000..099}.tar` and 50 canonical `data/processed/images/clean_12lead_shard_{000..049}.tar`. Builds `data/processed/images/clean_manifest.parquet` and `data/processed/images/clean_12lead_manifest.parquet` with per-blob SHA256, offset, length.                                  |
| 21    | `21_generate_scanlike_images.py` | Modify | Pattern B writer. Worker reads from the canonical `clean_shard_*.tar` (so the renderer's output is decoupled), writes `data/processed/partial/scanlike_worker_{wid}.tar`.                                                                                                                                                                                                        |
| 21b   | `21b_pack_scanlike.py`           | New    | Offline packer → 50 × `data/processed/images/scanlike_shard_{000..049}.tar` + `data/processed/images/scanlike_manifest.parquet`.                                                                                                                                                                                                                                                 |
| 22–24 | regen helpers                    | Modify | Update path expectations to read from / write to the tar shards.                                                                                                                                                                                                                                                                                                                 |

### Phase 5 — QC + integrity (Pattern A)

| #   | Script                              | Status | Changes                                                                                                                                                                                                                                                                                                                                                             |
| --- | ----------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 30  | `30_qc.py`                          | Modify | Pattern A: workers return dicts (no per-study JSON). Main process accumulates with `FLUSH_EVERY=100_000` and writes `data/processed/qc.parquet`. Schema is the lighter §3.2 tri-modal triple.                                                                                                                                                                            |
| 31  | `31_waveform_qc.py`                 | New    | Computes every column in §3.2 `data/processed/waveform_qc.parquet` table: decode, length, lead names, NaN/Inf, flatline, extreme amplitude, duplicate, SQI per lead, SQI tier, HR consistency, QRS consistency, report consistency. Reads from raw HDF5 (not per-study NPY). Pattern A writer.                                                                     |
| 32  | `32_compute_structured_features.py` | New    | NeuroKit2 HRV + morphology + intervals + machine-measurement passthrough → `data/processed/structured_features.parquet`. CPU-heavy; Pattern A writer with chunked flush (`FLUSH_EVERY=10_000` due to bigger rows).                                                                                                                                                 |
| 33  | `33_dataset_audits.py`              | New    | Produces the four audit reports (`split_audit.md`, `duplicate_audit.md`, `missingness_audit.md`, `leakage_audit.md`) from the consolidated parquet artifacts.                                                                                                                                                                                                       |

### Phase 6 — EHR linkage (NEW stage; gated on §5 downloads)

| #   | Script                     | Status | Changes                                                                                                                                                                                                                                                                                                                                                                               |
| --- | -------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 40  | `40_load_ehr_tables.py`    | New    | Read MIMIC-IV Hosp + ED CSVs into parquet locally for fast joins: `data/raw/ehr_cache/admissions.parquet`, `patients.parquet`, `diagnoses_icd.parquet`, `d_icd_diagnoses.parquet`, `labevents.parquet`, `d_labitems.parquet`, `edstays.parquet`, `ed_diagnosis.parquet`, `triage.parquet`. Row-count + sha256 stamped into `config/dataset_versions.yaml`.                           |
| 41  | `41_link_exact_overlap.py` | New    | §3.7.1 step 2. Output `data/processed/linkage/exact_hosp_candidates.parquet` + `exact_ed_candidates.parquet`.                                                                                                                                                                                                                                                                         |
| 42  | `42_link_tolerance.py`     | New    | §3.7.1 step 3. Output `data/processed/linkage/tolerance_hosp_candidates.parquet` + `data/processed/linkage/tolerance_ed_candidates.parquet` for ±6 h / ±12 h / ±24 h / ±7 d.                                                                                                                                                                                                          |
| 43  | `43_tie_break_link.py`     | New    | §3.7.1 step 6. Output `data/processed/linkage/linkage_final.parquet` + `candidate_links.parquet`.                                                                                                                                                                                                                                                                                     |
| 44  | `44_label_availability.py` | New    | §3.7.1 step 4. Output `data/processed/linkage/label_availability.parquet` and the linkage feasibility report.                                                                                                                                                                                                                                                                         |
| 45  | `45_decision_gate.py`      | New    | §3.7.2. Apply hard thresholds, write `config/decision.yaml`. Print a clear "Plan A / Hybrid / Plan B" determination.                                                                                                                                                                                                                                                                  |

### Aux

| Script                                                 | Status    | Note                  |
| ------------------------------------------------------ | --------- | --------------------- |
| `_legacy_extract_ecg_signals_v1.py`                    | Unchanged | Stays in `_legacy_`.  |
| `_test_signal_extraction.py`, `_test_ecg_rendering.py` | Unchanged | Stays as smoke tests. |

---

## 5. EHR datasets — download, layout, validation

### 5.1 What was downloaded

The following datasets were downloaded and stored locally:

| Dataset            | Source                  | Destination                   |
| ------------------ | ----------------------- | ----------------------------- |
| MIMIC-IV Hosp v3.1 | `s3://mimiciv/3.1/`     | `data/raw/mimic-iv-hosp-3.1/` |
| MIMIC-IV-ED v2.2   | `s3://mimic-iv-ed/2.2/` | `data/raw/mimic-iv-ed-2.2/`   |

The downloaded files were placed directly into the corresponding destination directories and were subsequently used for preprocessing and data generation.

### 5.2 Expected final layout

```plaintext
data/
└── raw/                                      # Unified raw data folder
    ├── files/                                # existing — MIMIC-IV-ECG waveforms
    ├── record_list.csv                       # existing
    ├── machine_measurements.csv              # existing
    ├── waveform_note_links.csv               # existing
    ├── machine_measurements_data_dictionary.csv
    ├── mimic-iv-hosp-3.1/
    │   ├── hosp/
    │   │   ├── admissions.csv.gz
    │   │   ├── patients.csv.gz
    │   │   ├── diagnoses_icd.csv.gz
    │   │   ├── d_icd_diagnoses.csv.gz
    │   │   ├── labevents.csv.gz                 # big (~5 GB)
    │   │   ├── d_labitems.csv.gz
    │   │   ├── prescriptions.csv.gz
    │   │   ├── emar.csv.gz
    │   │   ├── transfers.csv.gz
    │   │   └── services.csv.gz
    │   ├── icu/                                  # ICU module — present in MIMIC-IV 3.1 but optional for this project
    │   ├── CHANGELOG.txt
    │   ├── LICENSE.txt
    │   └── SHA256SUMS.txt
    ├── mimic-iv-ed-2.2/
    │   ├── ed/
    │   │   ├── edstays.csv.gz
    │   │   ├── diagnosis.csv.gz
    │   │   ├── triage.csv.gz
    │   │   ├── vitalsign.csv.gz
    │   │   ├── medrecon.csv.gz
    │   │   └── pyxis.csv.gz
    │   ├── LICENSE.txt
    │   └── SHA256SUMS.txt
    └── ehr_cache/                                # NEW — produced by 40_load_ehr_tables.py
        ├── admissions.parquet
        ├── patients.parquet
        ├── diagnoses_icd.parquet
        ├── d_icd_diagnoses.parquet
        ├── labevents.parquet
        ├── d_labitems.parquet
        ├── edstays.parquet
        ├── ed_diagnosis.parquet
        └── triage.parquet
```

### 5.3 Validation after download completes

`00b_access_check.py` must confirm:

- Every file in `SHA256SUMS.txt` of each dataset hashes correctly.
- The 9 tables in §5.2 exist and have non-zero rows.
- `record_list.csv` (ECG side) and `admissions.subject_id` (Hosp side)
  intersect — i.e. at least _some_ MIMIC-IV-ECG subjects appear in Hosp;
  otherwise the version mismatch is silent and Plan A is doomed.

Expected row-count ranges (sanity, not exact):

| Table             | Observed rows (v3.1 / v2.2) |
| ----------------- | --------------------------- |
| `admissions`      | 546,028                     |
| `patients`        | 364,627                     |
| `diagnoses_icd`   | 6,364,488                   |
| `d_icd_diagnoses` | 112,107                     |
| `d_labitems`      | 1,650                       |
| `labevents`       | **158,374,764** (big)       |
| `edstays`         | 425,087                     |
| `ed.diagnosis`    | 899,050                     |
| `triage`          | 425,087                     |

(Counts measured 2026-05-30 from the locally extracted release; v3.1
Hosp and v2.2 ED. The exact numbers above replace the earlier rough
estimates and are saved as machine-readable JSON at
`data/raw/.wget_logs/access_check.json`.)

---

## 6. Resource policy

The pipeline runs on the user's local Windows workstation. Use the
machine, don't undershoot — but leave headroom so the OS / other apps
don't thrash. Make all the scripts resumable and crash-tolerant so if the machine reboots or a runaway process causes OOM, we can just restart the script and it picks up where it left off.

### 6.1 CPU

| Knob                                          | Value                                       | Reason                                                                                                     |
| --------------------------------------------- | ------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `MAX_WORKERS` for CPU-bound multiprocessing   | `max(1, math.floor(os.cpu_count() * 0.75))` | At least 75 % of logical cores. Floor (not ceiling) so we never schedule more workers than cores.          |
| `BATCH_SIZE` per worker (ProcessPoolExecutor) | 32 (current value is fine)                  | Amortises IPC and process-pool overhead. Don't go above 128; large batches reduce parallelism granularity. |
| Worker affinity                               | Leave default                               | Windows scheduler does fine; manual affinity tends to hurt on multi-NUMA boxes we don't have here.         |

Implementation pattern every new/modified parallel script should follow:

```python
import math, os
MAX_WORKERS = max(1, math.floor(os.cpu_count() * 0.75))
# Documented at the top of every script that uses multiprocessing.
```

### 6.2 RAM

| Knob                                         | Value                                                                                                                                 | Reason                                                                                                     |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `MAX_RAM_GB` soft cap for extractor / packer | `psutil.virtual_memory().total / 1024**3 − 8` (leave 8 GB for OS + other apps)                                                        | Current `10_extract_ecg_signals.py` hardcodes 16 GB — change to compute dynamically.                       |
| Cooperative throttle                         | Every worker checks `psutil.Process().memory_info().rss` after each batch; if > `MAX_RAM_GB / MAX_WORKERS × 1.5`, sleep 2 s and retry | Stops a runaway worker from OOM-killing the whole pool.                                                    |
| HDF5 chunk size                              | `(64, 5000)` for `(N_chunk, samples)` per dataset                                                                                     | 64 studies × 5000 samples × 4 bytes = 1.25 MB per chunk — fits in L2 cache, big enough for I/O coalescing. |
| Pattern-A flush threshold                    | `FLUSH_EVERY = 100_000` rows (10 K for big-row tables like `structured_features.parquet`)                                             | Caps main-process buffer at ≤ ~50 MB even at much larger study counts.                                     |
| Pre-loaded data                              | Never load all signals into RAM. Loaders stream from HDF5 by chunk.                                                                   | Avoids 15 GB+ heap spikes.                                                                                 |

### 6.3 VRAM (GPU)

Phase 1 generation has no GPU-heavy step today. The only place it would
help is `15_preprocess_signals.py` (filters) or `21_generate_scanlike_images.py`
(OpenCV) — but neither benefits enough to justify CUDA setup overhead.

Policy: **Phase 1 does not use the GPU.** Phase 2 (training) gets the
full VRAM less a 1 GB margin (CUDA context + driver overhead).

### 6.4 Disk

The pipeline is disk heavy and the current disk does not have much space so if you hit space constraints during any step of the phase 1 pipeline please free up space and restart the script. The scripts are all designed to be resumable and crash-tolerant so you won't lose progress. When you are freeing up disk space, please prioritize deleting products/all the images and npy files of the old pipeline first and do not touch anything the new pipeline has produced because the current pipeline is more important than the files created from the old one.

| Knob                                  | Value                                                                                        |
| ------------------------------------- | -------------------------------------------------------------------------------------------- |
| Working directory during packing      | Same drive as `data/processed/` (no cross-drive copies)                                           |
| Free-space check before packer        | Refuse to run if free < (artifact size × 2) — we always need source + dest live during merge |
| Cleanup of `data/processed/partial/` dirs | Only after the packer has verified row counts and SHA256-stamped the canonical artifact      |
| Intermediate `.npy` / `.json` folders | Retained until §11.6 validation passes; then moved to cold storage (e.g., `data/archive/<timestamp>/`), not deleted blindly |

---

## 7. Parallel-write safety for consolidated formats

The reason the storage plan is "Pattern A" or "Pattern B" rather than
"have N workers write to one file" is that **parquet, HDF5, and tar are
not safe for concurrent writes from multiple processes**. The patterns
below are the only acceptable concurrency models in this pipeline.

### 7.1 Pattern A — small payload (qc, signal_metadata, structured_features)

```plaintext
ProcessPool workers ──▶ each worker returns (study_id, dict-of-fields)
                              │
                              ▼
            Main process accumulates into a buffer
                              │
              When buffer hits FLUSH_EVERY rows:
                              │
                              ▼
                pq.write_table(buffer → data/processed/part_{NNNN}.parquet)
                clear buffer
                              │
                              ▼
            At end of pool, pa.dataset(data/processed/part_dir).to_table()
            → single canonical parquet write + delete parts
```

Concurrency invariants:

- Exactly **one process writes to disk** (the main process).
- Workers are pure functions: input → dict.
- Crash safety: a partial run leaves `part_*.parquet` files; restarting
  picks up where the last successful flush ended (workers check the
  union of completed `study_id`s before processing).

### 7.2 Pattern B — large payload (signals, images)

```plaintext
ProcessPool workers ──▶ each worker writes its OWN file
                              ├─ data/processed/partial/lead2_worker_{wid}.h5
                              ├─ data/processed/partial/clean_worker_{wid}.tar
                              └─ data/processed/partial/scanlike_worker_{wid}.tar
                              (workers NEVER touch each other's files,
                              NEVER write offsets — see §7.3)
                              │
                              ▼
            Pool finishes
                              │
                              ▼
            Offline packer (single process) reads every partial,
            writes the canonical sharded output, builds the
            manifest INLINE as it writes:
                for member in incoming_studies_for_this_shard():
                    offset = out_container.tell()
                    out_container.write(member.bytes)
                    manifest.append((study_id, shard, offset,
                                     len(member.bytes), sha256))
                              │
                              ▼
            Verify per-shard row counts match expected total,
            then delete data/processed/partial/ tree
```

Concurrency invariants:

- Each worker owns its own file; no shared write target during the
  parallel phase.
- The packer is single-process; no contention at merge.
- **Manifest authority lives only in the packer** — see §7.3.

### 7.3 Manifest is the packer's job — not the worker's

Workers must NOT record their own offsets. The byte offset of each blob
inside the canonical shard is only knowable at the moment the packer
writes it. If a worker records its position inside its private partial
tar, that number becomes wrong as soon as the packer relocates the blob
to a different shard or position.

Packer skeleton (don't deviate from this contract):

```python
# in 20b_pack_images.py — one shard
out_tar = tarfile.open(shard_path, "w")
manifest_rows = []
for member, src_fileobj in studies_assigned_to_this_shard():
    offset = out_tar.fileobj.tell()              # BEFORE addfile
    out_tar.addfile(member, src_fileobj)
    manifest_rows.append({
        "study_id": int(member.name.split(".")[0]),
        "shard":    shard_idx,
        "offset":   offset,
        "length":   member.size,
        "sha256":   hashlib.sha256(blob_bytes).hexdigest(),
    })
out_tar.close()
```

### 7.4 HDF5-specific safety

| Constraint                                 | Rule                                                                                                                                             |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Concurrent writers on one `.h5`            | **Forbidden.** Use per-worker shards + offline merge (Pattern B).                                                                                |
| SWMR mode                                  | Don't use it. SWMR is for one writer + many _readers_; not multi-writer.                                                                         |
| MPI-HDF5 / `h5py.File(..., driver="mpio")` | Don't use it. Setup cost is not worth it for this project.                                                                                       |
| Virtual datasets                           | Optional optimization in the packer: stitch per-worker shards into a single logical dataset without copying bytes. Cheaper than a full re-write. |
| Dataset chunk shape                        | `(64, 5000)` for `(N, samples_per_lead)`. Compression: `gzip` level 4 (good ratio, fast decode) — set in HDF5 attrs.                             |

### 7.5 Parquet-specific safety

| Constraint                         | Rule                                                                                                                                                       |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Single `ParquetWriter` per process | Always. Sharing a writer across processes via pickling does not work.                                                                                      |
| Schema evolution                   | Never mutate a parquet file in place. Rewrite.                                                                                                             |
| Atomic publish                     | Write canonical artifact to `data/processed/qc.parquet.tmp` first; `os.replace(...)` to its final name once finished. Prevents half-written artifacts on crash. |

### 7.6 Tar-specific safety

| Constraint                     | Rule                                                                                                                                           |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Concurrent appends             | **Forbidden.** Central directory corruption. Per-worker partial tars only.                                                                     |
| Streaming reads                | Safe and lock-free; many readers can stream the same tar simultaneously.                                                                       |
| Member ordering inside a shard | Order by `study_id` ascending so the manifest's `offset` column is monotonically increasing per shard — makes consumer-side seeks predictable. |

---

## 8. Logging hygiene for multiprocessing

The default behavior of `multiprocessing.Pool` workers is for each child
process to inherit the parent's stdout / stderr handle. When many workers
call `print(...)` or `logging.info(...)` at the same time, their lines
get **interleaved character-by-character** on the terminal. This is the
"garbled mess" the user wants prevented.

This section is **binding for every script in this pipeline**. Two
worker-logging transports are allowed (§8.3 per-PID files, §8.4 queue
listener); pick one per script and stick to it. The other rules
(§8.1, §8.2, §8.5 – §8.11) apply unconditionally.

### 8.1 The terminal has exactly one speaker: the main process

Workers may not call `print(...)`, `logging.info(...)`, `tqdm.write(...)`,
or anything that writes to stdout/stderr.

The main process is the only thing that may touch the terminal. It
renders:

- A **single `tqdm` progress bar** driven from the pool's
  `imap_unordered(...)` iterator. The bar lives on `sys.stderr`. Only the
  main process iterates the pool, so the bar is updated from exactly one
  thread and never breaks.
- A **periodic status line** (every N studies) with cumulative counts,
  throughput, RAM usage — emitted via `tqdm.write(...)` (see §8.7), never
  raw `print`.
- A **final summary** when the pool drains: OK / skipped / errored,
  elapsed, output size.

### 8.2 Worker output goes to files, never to the parent's stdout/stderr

Workers communicate **results** by return value — success/failure status,
counts, per-study error info — back to the main process via the pool.

Workers communicate **detail logs** (exception tracebacks, per-study
reasons) via one of the two transports in §8.3 or §8.4. Choose:

| Transport | Use when | Trade-off |
|--|--|--|
| §8.3 Per-PID files | Default. Stages 3–8 of §9. High-throughput pipelines where workers produce few log lines per study, mostly warnings/errors. | Zero IPC overhead; aggregation is a single `cat` pass at the end. Lines from different workers are not globally time-ordered (they are time-ordered within a PID). |
| §8.4 QueueHandler + QueueListener | When you need a single time-ordered log and worker volume is modest. Stages 1, 2, 10 (orchestration-heavy, low fan-out). | One unified log file; globally ordered. Adds an IPC hop per log record (≈ a few µs). Listener thread is a single point of failure — must be supervised. |

Both transports forbid every worker process from writing to the parent's
stdout/stderr.

### 8.3 Transport A — per-PID log files (default)

Each worker writes to its own file:

```plaintext
scripts/logs/<script_name>/worker_{pid}.log
```

- Append-only, line-buffered, one file per process.
- **No locking needed** because no two processes write to the same file.
- File handle is opened in the **pool initializer** (§8.6), not lazily
  inside the task — opening a new `FileHandler` on every task adds I/O
  overhead and races during shutdown.
- After the pool drains, the main process concatenates worker logs in
  PID order into `scripts/logs/<script_name>/aggregate.log`, then moves
  the per-PID files into `scripts/logs/<script_name>/archive_<ts>/`.

### 8.4 Transport B — QueueHandler / QueueListener (when one ordered log is required)

Pattern (uses `logging.handlers.QueueHandler` + `logging.handlers.QueueListener`):

```python
# Main process
import logging, logging.handlers, multiprocessing as mp
log_queue = mp.Manager().Queue(-1)   # -1 = unbounded; safe because listener drains fast
file_handler = logging.FileHandler(LOG_DIR / "all.log")
file_handler.setFormatter(LOG_FORMATTER)         # §8.5
listener = logging.handlers.QueueListener(
    log_queue, file_handler, respect_handler_level=True
)
listener.start()

with mp.Pool(N, initializer=_init_worker_queue, initargs=(log_queue,)) as pool:
    for result in tqdm(pool.imap_unordered(worker, tasks), total=len(tasks)):
        ...

listener.stop()
file_handler.close()
```

Worker initializer:

```python
def _init_worker_queue(log_queue):
    import logging
    from logging.handlers import QueueHandler
    root = logging.getLogger()
    root.handlers.clear()                # remove inherited StreamHandlers!
    root.addHandler(QueueHandler(log_queue))
    root.setLevel(logging.WARNING)       # workers only emit WARNING+
```

Hard rules for Transport B:

- The queue **must** be created via `multiprocessing.Manager().Queue()`
  (or `multiprocessing.Queue()`). Standard library `queue.Queue` is
  in-process only and will silently lose worker records.
- The listener **must** be `.stop()`-ed before the script exits, or the
  tail of the log is lost.
- Workers must **not** add a `StreamHandler` — the inherited root logger
  may already have one from the parent and must be cleared first
  (`root.handlers.clear()`), otherwise warnings still escape to the
  terminal.
- On Windows (this project's platform), `multiprocessing` uses *spawn*,
  so each worker re-imports the script. The initializer runs **once per
  worker process** even with spawn, which is exactly what we want.

### 8.5 Standard log line format (binding for both transports)

Every log record in this pipeline — main, worker, listener — uses one
formatter:

```python
LOG_FORMATTER = logging.Formatter(
    fmt="%(asctime)s %(levelname)-7s pid=%(process)-6d %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
```

When logging anything study-specific, **always include the study_id in
the message** so post-mortem `grep` works:

```python
log.warning("study_id=%s wfdb decode failed: %s", sid, exc)
```

Do not use f-strings inside `log.<level>(...)` calls — they format
eagerly even when the level is suppressed, wasting CPU under high
throughput.

### 8.6 Worker setup goes in the Pool initializer, not the task

Setting up handlers inside the task function (`if not wl.handlers: ...`)
works but rebuilds state on every call. Use the Pool initializer:

```python
def _init_worker_pidfile(log_dir):
    import logging, os
    from pathlib import Path
    log_path = Path(log_dir) / f"worker_{os.getpid()}.log"
    root = logging.getLogger()
    root.handlers.clear()                            # critical — see §8.4
    fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    fh.setFormatter(LOG_FORMATTER)
    root.addHandler(fh)
    root.setLevel(logging.WARNING)
    _silence_noisy_libs()                            # §8.9

with mp.Pool(N, initializer=_init_worker_pidfile, initargs=(LOG_DIR,)) as pool:
    ...
```

### 8.7 tqdm and logging must coexist — use `logging_redirect_tqdm`

If the main process writes to `stderr` via a `StreamHandler` while a
`tqdm` bar is live on the same `stderr`, the bar gets shredded. Two
acceptable fixes — use **both** in the main process:

1. Wrap the main loop in `tqdm.contrib.logging.logging_redirect_tqdm()`,
   which routes every `logging` call through `tqdm.write()` for the
   duration of the bar:

   ```python
   from tqdm.contrib.logging import logging_redirect_tqdm
   from tqdm import tqdm

   with logging_redirect_tqdm():
       for result in tqdm(pool.imap_unordered(worker, tasks),
                          total=len(tasks), file=sys.stderr,
                          dynamic_ncols=True, mininterval=0.5):
           ...
   ```

2. When emitting status lines from the main process during the bar, use
   `tqdm.write("...")` — never raw `print(...)`.

`mininterval=0.5` caps redraw rate so the bar doesn't dominate the
terminal under high task throughput.

### 8.8 Capture accidental library stdout/stderr inside workers

Some libraries we use bypass `logging` and write directly to
stdout/stderr from C code (NeuroKit2 warnings, h5py debug, matplotlib
font warnings, libpng warnings during PNG render). Inherited file
descriptors from the parent point at the user's terminal, so even with
all rules above these can still leak.

Inside the worker initializer, redirect the worker's own stdout/stderr
to the worker's log file at the file-descriptor level:

```python
def _init_worker_pidfile(log_dir):
    import os, sys, logging
    from pathlib import Path
    log_path = Path(log_dir) / f"worker_{os.getpid()}.log"
    # redirect fd 1 (stdout) and fd 2 (stderr) into the log file
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)
    sys.stdout = os.fdopen(1, "w", buffering=1)      # line-buffered
    sys.stderr = os.fdopen(2, "w", buffering=1)
    # … then attach python logging as in §8.6
```

After this, `print(...)`, `sys.stderr.write(...)`, and native-code
writes from inside the worker all land in the worker's log file. The
terminal stays clean even if a dependency misbehaves.

For Transport B (queue), do the same redirect — the queue handles
Python `logging`; the fd redirect handles native library noise.

### 8.9 Silence noisy third-party loggers

In the main process, before launching the pool:

```python
def _silence_noisy_libs():
    import logging
    for name in ("matplotlib", "PIL", "PIL.PngImagePlugin",
                 "h5py", "fontTools", "urllib3", "neurokit2"):
        logging.getLogger(name).setLevel(logging.WARNING)
```

Call `_silence_noisy_libs()` in both the main process and the pool
initializer.

### 8.10 Log file size / rotation

Per-PID worker logs are bounded by job duration; no rotation needed.
Main-process logs (`main.log`) for long stages (Stage 3, Stage 4 each
multi-hour) should use `RotatingFileHandler(maxBytes=50_000_000,
backupCount=3)` so a single stage cannot fill the disk with logs.

### 8.11 Concrete skeleton — copy this into every parallel script

```python
import logging, logging.handlers, multiprocessing as mp, os, sys
from pathlib import Path
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

SCRIPT_NAME = Path(__file__).stem
LOG_DIR = Path(f"logs/{SCRIPT_NAME}"); LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FORMATTER = logging.Formatter(
    fmt="%(asctime)s %(levelname)-7s pid=%(process)-6d %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

def _silence_noisy_libs():
    for name in ("matplotlib", "PIL", "PIL.PngImagePlugin", "h5py",
                 "fontTools", "urllib3", "neurokit2"):
        logging.getLogger(name).setLevel(logging.WARNING)

def _init_worker(log_dir):
    log_path = Path(log_dir) / f"worker_{os.getpid()}.log"
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(fd, 1); os.dup2(fd, 2); os.close(fd)
    sys.stdout = os.fdopen(1, "w", buffering=1)
    sys.stderr = os.fdopen(2, "w", buffering=1)
    root = logging.getLogger()
    root.handlers.clear()
    fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    fh.setFormatter(LOG_FORMATTER)
    root.addHandler(fh)
    root.setLevel(logging.WARNING)
    _silence_noisy_libs()

def worker(args):
    log = logging.getLogger("worker")
    sid = args["study_id"]
    try:
        ...
        return {"study_id": sid, "ok": True}
    except Exception as exc:
        log.exception("study_id=%s failed", sid)
        return {"study_id": sid, "ok": False, "error": str(exc)}

def setup_main_logger():
    main_log = logging.getLogger("main")
    main_log.setLevel(logging.INFO)
    fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / "main.log", maxBytes=50_000_000, backupCount=3, encoding="utf-8"
    )
    sh = logging.StreamHandler(sys.stderr)
    fh.setFormatter(LOG_FORMATTER); sh.setFormatter(LOG_FORMATTER)
    main_log.addHandler(fh); main_log.addHandler(sh)
    _silence_noisy_libs()
    return main_log

def aggregate_worker_logs():
    out = LOG_DIR / "aggregate.log"
    pid_files = sorted(LOG_DIR.glob("worker_*.log"))
    with out.open("ab") as dst:
        for p in pid_files:
            dst.write(f"\n# === {p.name} ===\n".encode())
            dst.write(p.read_bytes())
    archive = LOG_DIR / f"archive_{int(__import__('time').time())}"
    archive.mkdir(exist_ok=True)
    for p in pid_files:
        p.replace(archive / p.name)

def main(tasks):
    main_log = setup_main_logger()
    main_log.info("starting %s with %d tasks", SCRIPT_NAME, len(tasks))
    with mp.Pool(N_WORKERS, initializer=_init_worker, initargs=(LOG_DIR,)) as pool:
        with logging_redirect_tqdm():
            with tqdm(total=len(tasks), file=sys.stderr,
                      dynamic_ncols=True, mininterval=0.5) as bar:
                ok = err = 0
                for r in pool.imap_unordered(worker, tasks, chunksize=8):
                    if r["ok"]: ok += 1
                    else:       err += 1
                    bar.update(1)
                    if (ok + err) % 5000 == 0:
                        main_log.info("progress ok=%d err=%d", ok, err)
    aggregate_worker_logs()
    main_log.info("done ok=%d err=%d", ok, err)
```

### 8.12 Anti-patterns — explicitly forbidden

| Anti-pattern | Why it breaks |
|--|--|
| Worker calls `print(...)` or `tqdm.write(...)` | Interleaves with other workers and shreds the main bar. |
| Worker calls `logging.basicConfig(...)` | Reconfigures the root logger inherited from the parent → log lines escape to terminal. |
| Two processes append to one log file | Partial-line interleaving on Windows; lock-free POSIX append works only on full lines smaller than `PIPE_BUF`, which we cannot guarantee. |
| `queue.Queue` instead of `mp.Manager().Queue()` for Transport B | In-process only; worker records silently dropped. |
| `StreamHandler(sys.stderr)` left active in worker | Inherited from parent → escapes to terminal even if no explicit `print`. |
| f-strings inside `log.info(f"...")` | Formats eagerly under suppressed levels. Use `%`-style. |
| `tqdm` bar with default `mininterval=0.1` under 50k+ tasks/min | Bar redraws faster than terminal can flush → tearing. Use `mininterval=0.5`. |
| Forgetting `listener.stop()` (Transport B) | Tail of the log lost on script exit. |
| Not redirecting fd 1/2 in worker | C-extension noise (libpng, h5py debug) still escapes to terminal. |

### 8.13 For sequential scripts

Sequential scripts use one `main.log` via `RotatingFileHandler` plus a
`StreamHandler(sys.stderr)`. Wrap any `tqdm` use in
`logging_redirect_tqdm()`. No per-PID files, no queue, no fd redirect
needed. `_silence_noisy_libs()` still applies.

### 8.14 Stage-report logging-validation checklist (reviewer-enforced)

Every stage's §10 report must demonstrate, in its "Validation results"
section, that the script ran without garbled output. The reviewer
(§11) will reject any stage that fails any of these checks:

- [ ] Terminal output during the run shows exactly one `tqdm` bar; no
      duplicated, stuttering, or character-interleaved lines.
- [ ] `scripts/logs/<script>/aggregate.log` (Transport A) or
      `scripts/logs/<script>/all.log` (Transport B) exists, is
      non-empty, and every line matches the §8.5 format regex
      `^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \w+\s+pid=\d+`.
- [ ] No `print(` calls exist in any function the pool calls. Verify via
      `grep -n "print(" <script>.py` in the report.
- [ ] No `logging.basicConfig(` calls inside worker functions. Verify
      same way.
- [ ] `worker_<pid>.log` files were archived (not left at the
      script-log root) after the run completed.
- [ ] If Transport B: report shows `listener.stop()` was called in the
      `finally` block of `main()`.
- [ ] If the script used `tqdm`: report confirms `mininterval >= 0.5`
      and `logging_redirect_tqdm()` was active.

---

## 9. Stage-by-stage migration plan (the agent's actual playbook)

Phase 1 is split into **10 stages**. Each stage is a self-contained
chunk: scripts to build/modify, inputs read, outputs produced, **old
per-study folder(s) deleted after validation**, expected disk delta, and
a per-stage validation checklist.

After every stage the agent halts, emits the §10 output summary, and
waits for the reviewer (§11) to sign off before starting the next
stage.

### 9.1 Dependency rules (why the order is what it is)

- Patient split (Stage 2) depends on linkage tier (Stage 1) because
  Plan A/B §4.7 requires stratification by linkage tier.
- Image rendering (Stages 4–5) depends on raw signals (Stage 3) because
  rendering reads from `signals/lead2_raw.h5`.
- Scanlike images (Stage 5) depend on clean images (Stage 4) because
  scanlike is a deterministic OpenCV transform of the clean PNG.
- QC (Stage 6) depends on raw signals **and** both image modalities
  because it joins all three to flag tri-modal completeness.
- Rich waveform-QC and structured features (Stage 7) depend on raw
  signals (NeuroKit2 reads `lead2_raw.h5`).
- Signals-corrupted (Stage 8) depends on raw signals and the patient
  split (test split is the anchor subset).
- Final audits (Stage 10) need every prior artifact to be in place.

### 9.2 Wall-clock and disk budget (running totals)

Starting state: `data/processed/` ≈ 406 GB, D: free ≈ 195 GB.

| Stage | What happens                                          | Wall-clock  | Delta `data/processed/` | Free after |
| ----- | ----------------------------------------------------- | ----------- | ----------------------- | ---------- |
| 0     | Foundation (version lock, access check, ECG metadata) | 30–60 min   | +0.5 GB                 | ≈ 194 GB   |
| 1     | EHR linkage chain + decision gate                     | 30–90 min   | +13 GB (ehr_cache)      | ≈ 181 GB   |
| 2     | Patient split (stratified)                            | 5 min       | ≈ +0                    | ≈ 181 GB   |
| 3     | Signal extraction + pack (BIG)                        | 6–12 h      | +75 new −204 old        | ≈ 310 GB   |
| 4     | Clean image rendering (both layouts)                  | 8–16 h      | +201 new −141 old       | ≈ 250 GB   |
| 5     | Scanlike image rendering (both layouts)               | 4–8 h       | +104 new −68 old        | ≈ 214 GB   |
| 6     | Tri-modal QC (parquet)                                | 30–60 min   | +0.05 −0.06             | ≈ 214 GB   |
| 7     | Rich waveform-QC + structured features                | 4–8 h       | +10 GB                  | ≈ 204 GB   |
| 8     | Signals-corrupted parquet                             | 1–2 h       | +1.5 −1.5               | ≈ 204 GB   |
| 9     | Preprocessed signals (DEFERRED — see §12 open)        | (optional)  | +75 GB if materialized  | ≈ 129 GB   |
| 10    | Index cleanup + canonical manifest + final audits     | 30–60 min   | +0.05                   | ≈ 204 GB   |

Peak transient usage during Stage 3 (extractor partials + new HDF5 +
old NPY all live for a few minutes during the streaming-merge): leaves
~46 GB free at the very worst moment. The packer streams (read one
partial → append to canonical → delete that partial → next) to keep
this safe.

### 9.3 Per-stage detail

> **Common rules** that apply to every stage below — do not restate
> per stage:
> - Run scripts with CWD = `scripts/`.
> - Every script lands its work behind a `try / except` that returns a
>   structured result; on uncaught exception the worker logs to
>   `scripts/logs/<script_name>/worker_<pid>.log` and the main process
>   continues. See §8.
> - Every script reads `config/dataset_versions.yaml` and stamps
>   `dataset_version` into every artifact it produces (HDF5 attr / tar
>   `MANIFEST.json` / parquet schema metadata) per §2.2.
> - Every consolidated artifact is written to `<final>.tmp` and
>   `os.replace`-d to its final name once finished (atomic publish per
>   §7.5).
> - **Deletion happens only after the stage's validation block passes.**
>   If validation fails, the agent halts and the old folder stays.

---

#### Stage 0 — Foundation

**Purpose.** Lock dataset versions, verify raw data integrity, build the
master ECG metadata index. Pre-condition for everything else.

**Sub-step 0.0 — Directory reorganization (one-time).**
If `data/files/` exists at root level (pre-§2.4 layout), move
`data/files/`, `data/record_list.csv`, `data/machine_measurements.csv`,
`data/waveform_note_links.csv`,
`data/machine_measurements_data_dictionary.csv`,
`data/mimic-iv-hosp-3.1/`, `data/mimic-iv-ed-2.2/` into `data/raw/`.
Move `processed/` (root) into `data/processed/`. Verify nothing broke
with a quick `Get-ChildItem` listing each new location. This is a
filesystem rename only — no data is copied.

**Scripts to author / modify (this stage):**

| # | Script                       | Status | What it does                                                                                                                                          |
| - | ---------------------------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | `00_lock_versions.py`        | New    | Detect installed Python+lib versions; hash + count rows for every raw table; write `config/dataset_versions.yaml` per §3.1 schema.                    |
| 2 | `00b_access_check.py`        | New    | Verify every raw file in §5.2 exists, validates against SHA256SUMS.txt, has rows in the §5.3 ranges. Write `outputs/audit_reports/access_check.md`.   |
| 3 | `01_build_master_index.py`   | Modify | Output `data/processed/index/ecg_metadata.parquet`. Add columns: `report_lines: list<string>`, `T_machine`, `T_cardio` (nullable per §12 res. 4), `has_machine_measurements`, `has_machine_report_text`, `machine_hr_bpm`, `machine_qrs_ms`, `machine_qtc_ms`, `cart_id`, `filtering`, `bandwidth`. No imputation. |

**Inputs:** `data/raw/files/`, `data/raw/record_list.csv`,
`data/raw/machine_measurements.csv`, `data/raw/waveform_note_links.csv`,
`data/raw/mimic-iv-hosp-3.1/SHA256SUMS.txt`,
`data/raw/mimic-iv-ed-2.2/SHA256SUMS.txt`.

**Outputs:** `config/dataset_versions.yaml`,
`outputs/audit_reports/access_check.md`,
`data/processed/index/ecg_metadata.parquet`.

**Deletes (after validation):** none. Sub-step 0.0 is a filesystem move,
not a delete.

**Disk delta:** +0.5 GB (the metadata parquet).

**Validation:**
- `config/dataset_versions.yaml` exists; every library imported anywhere
  in `scripts/phase1_dataset_generation/` is listed.
- `access_check.md` PASS: every required file present, SHA256 verified,
  row counts in range.
- `ecg_metadata.parquet` row count == row count of
  `data/raw/record_list.csv` ± 0.
- 50 random rows from `ecg_metadata.parquet` printed in the output
  summary for manual sanity check (Truth doc §5.1 mandates this manual
  inspection).
- `T_cardio` column present, dtype nullable string.

---

#### Stage 1 — EHR linkage chain + decision gate

**Purpose.** Determine whether Plan A (EHR-grounded) is viable on this
release. Produces the linkage tier per study and the auto-chosen path.

**Scripts to author (all new):**

| # | Script                       | What it does                                                                                                                  |
| - | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 1 | `40_load_ehr_tables.py`      | Read `data/raw/mimic-iv-hosp-3.1/hosp/*.csv.gz` and `data/raw/mimic-iv-ed-2.2/ed/*.csv.gz` into `data/raw/ehr_cache/*.parquet` for fast joins. Stamp row counts into `dataset_versions.yaml`. |
| 2 | `41_link_exact_overlap.py`   | Plan A/B §3.1 step 2 — `data/processed/linkage/exact_hosp_candidates.parquet`, `exact_ed_candidates.parquet`.                  |
| 3 | `42_link_tolerance.py`       | §3.1 step 3 — `tolerance_*_candidates.parquet` for ±6 h / ±12 h / ±24 h / ±7 d.                                                |
| 4 | `43_tie_break_link.py`       | §3.1 step 6 — `data/processed/linkage/linkage_final.parquet` + `candidate_links.parquet`.                                      |
| 5 | `44_label_availability.py`   | §3.1 step 4 — `data/processed/linkage/label_availability.parquet` + `outputs/audit_reports/linkage_feasibility_report.md`.     |
| 6 | `45_decision_gate.py`        | §3.7.2 — apply hard thresholds, write `config/decision.yaml` with chosen path.                                                 |

**Inputs:** `data/processed/index/ecg_metadata.parquet`,
`data/raw/mimic-iv-hosp-3.1/`, `data/raw/mimic-iv-ed-2.2/`.

**Outputs:** `data/raw/ehr_cache/*.parquet`,
`data/processed/linkage/*.parquet`, `config/decision.yaml`,
`outputs/audit_reports/linkage_feasibility_report.md`.

**Deletes:** none.

**Disk delta:** +13 GB (EHR cache parquets are ~30 % the size of the
gzip CSVs they replace).

**Validation:**
- `linkage_final.parquet` row count == ECGs with at least L1 linkage.
- Linkage tier distribution printed (counts of L3 / L2 / L1 / L0).
- `decision.yaml` written with one of `{plan_a, hybrid, plan_b}`,
  `threshold_pass` block, and `frozen_at` ISO timestamp.
- Tables L1–L4 of the feasibility report exist and are populated.
- 20 random successful linkages + 20 random failed/ambiguous linkages
  printed in the output summary for manual audit (Plan A/B Appendix A
  step A10).

---

#### Stage 2 — Patient split (stratified)

**Purpose.** Produce the subject-level 70/10/20 split, stratified on HR
bucket and linkage tier so each split has a comparable mix.

**Scripts to modify:**

| # | Script                          | Status | What changes                                                                                                                                                                                  |
| - | ------------------------------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | `02_create_patient_split.py`    | Modify | Ratio 70/10/20 (was 80/10/10). Stratify by `(hr_bucket, linkage_tier)`. Output `data/processed/splits_subject_level.parquet` + `data/processed/index/splits.json`. Hard-check zero subject overlap. |

**Inputs:** `ecg_metadata.parquet`, `linkage_final.parquet`.

**Outputs:** `data/processed/splits_subject_level.parquet`,
`data/processed/index/splits.json`.

**Deletes:** none.

**Disk delta:** ≈ 0.

**Validation:**
- Three patient sets disjoint: `len(set(train) ∩ set(val)) == 0`, etc.
- Stratification table printed: per-stratum counts in each split.
- Split ratio reported and within ±1 % of 70/10/20.

---

#### Stage 3 — Signal extraction + pack (THE BIG ONE — frees 204 GB)

**Purpose.** Read raw WFDB, write consolidated HDF5, delete the 800 K
per-study `.npy` files.

**Scripts to author / modify:**

| # | Script                            | Status | What it does                                                                                                                                                                                  |
| - | --------------------------------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | `10_extract_ecg_signals.py`       | Modify | Pattern B writer per §7.2. Each `ProcessPoolExecutor` worker writes its own `data/processed/partial/lead2_worker_{wid}.h5` and `partial/twelve_lead_worker_{wid}.h5`. Workers also return `signal_metadata` dicts to the main process. |
| 2 | `10b_pack_signals.py`             | New    | **Streaming-merge** packer: for each worker partial, append its rows to the canonical HDF5 then `os.unlink` the partial. Output `signals/lead2_raw.h5` (1 file) + `signals/twelve_lead_raw_shard_{00..04}.h5` (5 shards by `study_id % 5`). Build per-row SHA256 in `signals/signals_manifest.parquet`. Stamp HDF5 attrs per §2.2. Same script materializes `data/processed/signal_metadata.parquet` from the workers' returned dicts. |

**Inputs:** `data/raw/files/`, `data/processed/index/ecg_metadata.parquet`.

**Outputs:** `data/processed/signals/lead2_raw.h5`,
`data/processed/signals/twelve_lead_raw_shard_{00..04}.h5`,
`data/processed/signals/signals_manifest.parquet`,
`data/processed/signal_metadata.parquet`.

**Deletes (after validation):**
- `data/processed/signals_lead2/` (~16 GB)
- `data/processed/signals_12lead/` (~187 GB)
- `data/processed/signal_metadata/` (~76 MB)
- `data/processed/partial/` (transient, deleted by packer itself)

**Disk delta:** +75 GB new −204 GB old = **−129 GB net**.

**Validation:**
- `lead2_raw.h5` row count == `ecg_metadata.parquet` row count minus
  records with `decode_ok=False`.
- `twelve_lead_raw_shard_{00..04}.h5` row counts sum to the same number.
- HDF5 root attrs include `dataset_version`, `created_at_iso`,
  `modality_kind`, `n_studies`, `chunk_shape=(64, 5000)`, `compression`,
  `script_commit_hash`.
- **Spot check:** SHA256 of 100 random rows from `lead2_raw.h5` matches
  the SHA256 of the corresponding `data/processed/signals_lead2/{id}.npy`
  (which still exists pre-delete).
- `signal_metadata.parquet` row count == row count of HDF5.
- `data/processed/partial/` directory is empty after packing.

---

#### Stage 4 — Clean image rendering (BOTH layouts — frees 141 GB)

**Purpose.** Render Lead-II strip **and** 12-lead 3×4 grid per §12
resolution 2. 12-lead grid uses low DPI / high compression to minimize
size.

**Scripts to author / modify:**

| # | Script                              | Status | What it does                                                                                                                                                                                                                                                                                                                                       |
| - | ----------------------------------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | `20_render_clean_images.py`         | Modify | Pattern B. Each worker writes two private tars: `partial/clean_lead2_worker_{wid}.tar` (existing 12×2.5 in PNG @ 300 DPI) and `partial/clean_12lead_worker_{wid}.tar` (new 3×4 grid + rhythm strip @ 25 mm/s × 10 mm/mV; **low DPI (~100) + PNG `optimize=True, compress_level=9`** to hit ≤80 KB/image target).                                  |
| 2 | `20b_pack_images.py`                | New    | Streaming-merge packer per §7.3. For each layout: write canonical `images/clean_{layout}_shard_{NNN}.tar` ordered by `study_id`; embed `MANIFEST.json` as first tar member; capture `offset` via `tar.fileobj.tell()` BEFORE `addfile`; produce `images/clean_{layout}_manifest.parquet` with per-blob `sha256`. Delete partials. |

**Inputs:** `data/processed/signals/lead2_raw.h5`,
`data/processed/signals/twelve_lead_raw_shard_*.h5`,
`data/processed/index/ecg_metadata.parquet`.

**Outputs:** `data/processed/images/clean_lead2_shard_{000..099}.tar`,
`data/processed/images/clean_lead2_manifest.parquet`,
`data/processed/images/clean_12lead_shard_{000..029}.tar`,
`data/processed/images/clean_12lead_manifest.parquet`.

**Deletes (after validation):** `data/processed/images_clean/` (~141 GB).

**Disk delta:** +201 GB new − 141 GB old = **+60 GB net**.

**Validation:**
- For both layouts: per-shard `MANIFEST.json` round-trips and equals
  the parquet manifest for that shard.
- Every manifest row has non-null `offset, length, sha256`; `offset`
  monotonically increasing within each shard.
- **Spot check (Lead-II only):** 100 random PNG byte-strings extracted
  from new tar shards match SHA256 of corresponding old
  `data/processed/images_clean/{id}.png`.
- 12-lead grid: render 8 example studies and embed them in the output
  summary so the reviewer can eyeball clinical correctness
  (3×4 layout, rhythm strip, paper-speed grid visible, no patient ID
  printed per Truth doc §5.4 D1).
- Total shard count: 100 (lead2) + ≤ 30 (12-lead).

---

#### Stage 5 — Scanlike image rendering (BOTH layouts — frees 68 GB)

**Purpose.** Apply the deterministic OpenCV scan-like augmentation to
both clean image layouts.

**Scripts to author / modify:**

| # | Script                              | Status | What it does                                                                                                                                                                                                       |
| - | ----------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1 | `21_generate_scanlike_images.py`    | Modify | Read clean tar shards (Stage 4 output) via `tarfile.open(...).extractfile(name)`. Pattern B writer: per-worker `partial/scanlike_{layout}_worker_{wid}.tar`. Seed `cv2.RNG` deterministically from `study_id`.       |
| 2 | `21b_pack_scanlike.py`              | New    | Same streaming-merge packer skeleton as `20b_`. Output `images/scanlike_lead2_shard_{000..049}.tar` + `images/scanlike_12lead_shard_{000..017}.tar` + their manifests with per-blob sha256.                          |

**Inputs:** `data/processed/images/clean_lead2_*` and
`clean_12lead_*` tars + manifests.

**Outputs:** `data/processed/images/scanlike_lead2_shard_{000..049}.tar`,
`data/processed/images/scanlike_lead2_manifest.parquet`,
`data/processed/images/scanlike_12lead_shard_{000..017}.tar`,
`data/processed/images/scanlike_12lead_manifest.parquet`.

**Deletes (after validation):** `data/processed/images_scanlike/`
(~68 GB).

**Disk delta:** +104 GB new − 68 GB old = **+36 GB net**.

**Validation:**
- Determinism check: pick 10 study_ids; for each, re-run the scanlike
  transform from scratch on the same clean PNG and verify byte-identical
  output (catches any non-determinism introduced by NumPy/OpenCV
  upgrades).
- **Spot check (Lead-II only):** 100 random JPG byte-strings from new
  tar match SHA256 of corresponding old
  `data/processed/images_scanlike/{id}.jpg`.
- Manifest invariants same as Stage 4.

---

#### Stage 6 — Tri-modal QC (frees old `qc/`)

**Purpose.** Replace 651 K per-study `qc/{id}.json` with one
`qc.parquet` containing the existing 4-field schema (this stage stays
narrow; the rich waveform-QC happens in Stage 7).

**Scripts to author / modify:**

| # | Script               | Status | What it does                                                                                                                                                                                                                                                                                                                  |
| - | -------------------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | `30_qc.py`           | Modify | Pattern A per §7.1. Workers read `lead2_raw.h5[study_id]` + check both image-tar manifests + read `T_machine` from `ecg_metadata.parquet`. Workers return dicts; main process accumulates with `FLUSH_EVERY=100_000` to `qc.part_{NNNN}.parquet`, then concatenates to `data/processed/qc.parquet`. |

**Inputs:** `ecg_metadata.parquet`, `signals/lead2_raw.h5`,
`images/clean_lead2_manifest.parquet`,
`images/scanlike_lead2_manifest.parquet`,
`images/clean_12lead_manifest.parquet`,
`images/scanlike_12lead_manifest.parquet`.

**Outputs:** `data/processed/qc.parquet`.

**Deletes (after validation):** `data/processed/qc/` (~60 MB).

**Disk delta:** ≈ 0.

**Validation:**
- `qc.parquet` row count == `ecg_metadata.parquet` row count exactly.
- For 100 random rows: each field matches the corresponding old
  `qc/{id}.json` file (which still exists pre-delete).
- Parquet schema metadata includes `dataset_version`, `created_at_iso`,
  `script_commit_hash`.
- `qc.part_*.parquet` cleanup verified.

---

#### Stage 7 — Rich waveform QC + structured features

**Purpose.** Build the Plan A/B–mandated `waveform_qc.parquet` (rich
QC + cross-source consistency, §3.2) and `structured_features.parquet`
(NeuroKit2 HRV + morphology + intervals, §3.4).

**Scripts to author (all new):**

| # | Script                                | What it does                                                                                                                                                                                                                                                                                                                                |
| - | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | `31_waveform_qc.py`                   | Pattern A. Read `lead2_raw.h5[i]` + `twelve_lead_raw_shard_*.h5` + machine measurements; compute every column in §3.2 (per-lead SQI via NeuroKit2 `ecg_quality`, HR consistency, QRS consistency, flatline, extreme amplitude, duplicate detection via SHA256 of `lead_II[::10]`); workers return dicts; main writes `waveform_qc.parquet`. |
| 2 | `32_compute_structured_features.py`   | Pattern A with smaller `FLUSH_EVERY=10_000` (bigger rows). Read raw signal, run NeuroKit2 HRV / morphology / intervals, passthrough machine measurements; write `structured_features.parquet`.                                                                                                                                              |

**Inputs:** `signals/lead2_raw.h5`, `signals/twelve_lead_raw_shard_*.h5`,
`ecg_metadata.parquet`.

**Outputs:** `data/processed/waveform_qc.parquet` (~0.5 GB),
`data/processed/structured_features.parquet` (~5–10 GB).

**Deletes:** none (no old equivalent existed).

**Disk delta:** +10 GB.

**Validation:**
- `waveform_qc.parquet` row count == `ecg_metadata.parquet` row count.
- SQI tier distribution printed (`high / medium / low` counts).
- HR-consistency mismatch count printed (expected ≤ 5 % of records).
- Duplicate-waveform groups: count and size distribution printed.
- `structured_features.parquet` row count == row count of HDF5 rows
  with `decode_ok=True`.

---

#### Stage 8 — Signals-corrupted parquet (frees 1.5 GB)

**Purpose.** Replace the 80 K per-corruption `.npy` files with one
parquet. Fix the `hash()` non-determinism bug (§3.11) in the same pass.

**Scripts to modify:**

| # | Script                                                              | Status | What changes                                                                                                                                                                                                                                                                                                                                                                                                  |
| - | ------------------------------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | `phase2_tasks_benchmark_and_paper/05_task_B2_noise_robustness.py`   | Modify | Output target → `data/processed/signals_corrupted.parquet` (columns per §2). 2 K anchors (per §12 res. 3) × 8 corruptions × 5 SNRs = 80 K rows. **Replace `hash(...)` with `hashlib.sha256(...).digest()[:4]` per §3.11.** Pattern A writer with `FLUSH_EVERY=10_000`. |

**Inputs:** `signals/lead2_raw.h5`, `splits_subject_level.parquet`
(test split is the anchor pool).

**Outputs:** `data/processed/signals_corrupted.parquet` (~1.5 GB).

**Deletes (after validation):** `data/processed/signals_corrupted/`
(~1.5 GB).

**Disk delta:** ≈ 0.

**Validation:**
- Row count: 80,000 ± small slack (some anchors may fail length check).
- Re-run determinism: pick 10 `(study_id, corruption, snr_db)` triples
  and regenerate from `lead2_raw.h5`; assert byte-identical with
  parquet row (proves the SHA256-seed fix worked).

---

#### Stage 9 — Preprocessed signals (DEFERRED — see §12 open decision)

**Purpose.** Plan A/B §4.4 mandates "raw and preprocessed signal as
separate modalities." Two ways to satisfy this:

- **9.A — Materialize:** build `signals/lead2_preprocessed.h5` +
  `signals/twelve_lead_preprocessed_shard_{00..04}.h5` with the filter
  chain in §3.3 (60 Hz notch per §12 res. 1, baseline-wander HP at
  0.5 Hz, low-pass at 100 Hz, per-lead z-score with scaler fit on
  **training split only**). Disk +75 GB.
- **9.B — On-the-fly via locked recipe:** write only
  `config/preprocessing_recipe.yaml` (KB) + `config/scalers/lead2_zscore_train.npz`
  (KB). The consumer's `read_modality(study_id, "preprocessed_lead2")`
  reads raw and applies the recipe at read time. Disk ≈ 0.
  Either way the recipe must be saved.

**This is an open decision (§12.5).** Do not run Stage 9 until the
user picks 9.A or 9.B.

---

#### Stage 10 — Index cleanup + canonical manifest + final audits

**Purpose.** Close out Phase 1: produce the cleaned index, the master
modality manifest, and the four required audit reports.

**Scripts to modify / author:**

| # | Script                              | Status | What changes                                                                                                                                                          |
| - | ----------------------------------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | `03_add_measurements_to_index.py`   | Modify | Read `ecg_metadata.parquet` + machine measurements; add missing-flag columns per measurement. Output `data/processed/index/ecg_metadata_with_measurements.parquet`.   |
| 2 | `04_cleanup_master_index.py`        | Modify | Read `qc.parquet` and `waveform_qc.parquet`; apply tri-modal pass filter; output `data/processed/index/ecg_metadata_clean.parquet` + `ecg_metadata_clean_with_measurements.parquet`. |
| 3 | `05_build_manifest_and_splits.py`   | Modify | Build canonical `data/processed/modality_manifest.parquet` per §2.1 schema (one row per `(study_id, modality_kind)` for every modality container).                    |
| 4 | `33_dataset_audits.py`              | New    | Produce all four audit reports per §3.8: `split_audit.md`, `duplicate_audit.md`, `missingness_audit.md`, `leakage_audit.md` (the last reads `config/task_input_policy.yaml`). |

**Inputs:** every Phase-1 artifact built so far.

**Outputs:** `data/processed/index/ecg_metadata_with_measurements.parquet`,
`data/processed/index/ecg_metadata_clean.parquet`,
`data/processed/index/ecg_metadata_clean_with_measurements.parquet`,
`data/processed/modality_manifest.parquet`,
`outputs/audit_reports/{split,duplicate,missingness,leakage}_audit.md`.

**Deletes:** none new (existing `processed/index/` files are rewritten
in place; old Phase-2 `task_jsonl/` files are left untouched — they'll
be regenerated when Phase 2 builders run against the new artifacts).

**Disk delta:** ≈ 0.

**Validation (also the final "Phase 1 done" check):**
- All four audit reports written; every report has a `STATUS: PASS`
  header line.
- `modality_manifest.parquet` row count == `n_studies × n_modality_kinds`
  with **zero** orphan studies (every studio_id in `ecg_metadata.parquet`
  has rows for every modality_kind it is expected to have).
- Three random calls to `read_modality(study_id, kind)` per modality
  succeed and return the expected shape / bytes.
- `ecg_metadata_clean.parquet` row count documented; difference vs
  `ecg_metadata.parquet` explained by `waveform_qc.parquet` exclusions.
- `dataset_versions.yaml` final `dataset_version_stamp` recorded.

---

## 10. Per-stage agent output format (the report the agent must produce after every stage)

After completing a stage, the agent halts and emits one
`stage_<N>_report.md` file in `outputs/stage_reports/` and ALSO prints
the same content to stdout in a single block so the user can copy-paste
it to the reviewer. The report contains **exactly these eight numbered
sections** in this order:

```
# Stage <N> — <stage name> — report

## 1. Files created
- <relative path>  (<size>, sha256 <hex prefix 12>)
- <relative path>  (<size>, sha256 <hex prefix 12>)
...

## 2. Files modified
- <relative path>  ::  <one-line summary of what changed>
- <relative path>  ::  <one-line summary>
...

## 3. Files / folders deleted
- <relative path>  ::  <file count, total bytes freed>
- <relative path>  ::  <file count, total bytes freed>
(or: "none")

## 4. Design decisions
- <decision 1>  ::  <one-paragraph reasoning>
- <decision 2>  ::  <reasoning>
...
(small, non-obvious choices the agent made that aren't already specified
in the source-of-truth doc — chunk sizes, parallel-worker counts,
fallback behaviors when an edge case wasn't covered, etc.)

## 5. Complete code
For every script in §2 (Files modified) or §1 (Files created) under
`scripts/`, paste the full final file contents in a fenced code block
labeled with the file's path. No "..." elisions.

## 6. Validation results
- Pre-flight: <PASS/FAIL with the disk-free + dependency checks>
- Per-validation-bullet from §9.X for this stage: <PASS/FAIL with numbers>
- Logging-hygiene checklist (every bullet from §8.14):
  - [ ] Terminal showed one tqdm bar, no interleaving (state evidence: e.g. "captured stderr to terminal.log; first 50 lines pasted below")
  - [ ] aggregate.log / all.log exists, first + last 5 lines pasted, all match §8.5 regex
  - [ ] `grep -n "print(" <script>.py` output pasted (must be empty inside worker())
  - [ ] `grep -n "logging.basicConfig" <script>.py` output pasted (must be empty inside worker())
  - [ ] worker_<pid>.log files moved into archive_<ts>/ (paste `ls` of archive dir)
  - [ ] If Transport B: paste the `finally: listener.stop()` line from the script
  - [ ] If tqdm used: paste the `tqdm(..., mininterval=…)` call and the `with logging_redirect_tqdm():` line
- Disk before stage start: <GB free>
- Disk after stage end: <GB free>
- Wall-clock: <hh:mm:ss>

## 7. Manual test procedure
Specific commands the user can run to independently re-verify the
stage's outputs. Each command on its own line, no shell pipelines
spanning multiple lines.

## 8. Assumptions requiring user confirmation
- <assumption>  ::  <why it matters / what changes if it's wrong>
(or: "none")
```

If any §6 validation bullet is FAIL, the agent **does not delete** the
old per-study folder for this stage and halts with an explicit
`STAGE <N> HALTED — VALIDATION FAILED` line at the bottom of the
report.

---

## 11. Reviewer checklist (what the reviewing model does with §10 output)

The reviewer reads the stage report and verifies it against this doc.
The reviewer's job is **review only — not rewrite the code**.

### 11.1 Coverage areas

For every stage report, check:

| Area                          | Specifically look for                                                                                                                              |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Missing requirements          | Every script listed in §9.X for this stage is present in §1 or §2 of the report. Every output file in §9.X is in §1 of the report.                  |
| Spec violations               | Output schemas match §2.1 / §3.2 / §3.4 column lists. HDF5 chunk shape matches §6.2. Compression matches §7.4. Stamps match §2.2.                  |
| Race conditions               | Multi-process code follows §7.1 (Pattern A) or §7.2 (Pattern B); workers do not share write targets; manifest offsets recorded only by packer.     |
| Resume / recovery violations  | `<final>.tmp` + `os.replace` atomic publish per §7.5. Pattern A `part_*.parquet` cleanup. Idempotent re-run: re-running a stage on existing output is a no-op or safely overwrites. |
| Logging violations            | Full §8.14 checklist (terminal not garbled, one tqdm bar, log format regex matches, no `print(` / `basicConfig(` in worker code, worker logs archived, listener stopped for Transport B, `logging_redirect_tqdm()` used, `mininterval >= 0.5`, fd 1/2 redirected in worker initializer). Transport A vs B choice documented per §8.2. |
| Incorrect schemas             | Column types match this doc (int64 vs string, nullable vs required). `modality_kind` values are from the closed enum in §2.1.                       |
| Missing audit outputs         | If §9.X promises an audit report, it's in §1 of the report and has a PASS/FAIL header.                                                              |
| Path mismatches               | All paths are `data/raw/...` or `data/processed/...` per §2.4 — no leftover `processed/` root-level paths, no leftover `data/files/` root-level.   |
| Windows compatibility issues  | No POSIX-only constructs (`os.symlink`, fork-only multiprocessing patterns, max-path-260-character risks for deeply nested partials).               |
| Resource policy violations    | `MAX_WORKERS` formula matches §6.1. `MAX_RAM_GB` is computed dynamically per §6.2 (not hardcoded 16). `FLUSH_EVERY` matches §6.2.                  |

### 11.2 Severity classification

Every finding the reviewer raises is labelled with one of:

- **CRITICAL** — blocks Phase 1 completion or compromises data integrity
  (e.g., manifest offsets wrong; worker shared-write race; missing
  spec-mandated artifact; hash non-determinism; old folder deleted
  before validation passed).
- **MAJOR** — spec violation that lets the stage proceed but creates
  downstream risk (e.g., HDF5 chunk shape wrong; missing column in
  schema; wrong dtype; missing `dataset_version` stamp; logging
  hygiene violation that garbles terminal output).
- **MINOR** — cosmetic / style / pre-existing issue (e.g., docstring
  outdated; variable name; tqdm bar disable not respected by CI).

### 11.3 Finding format (one per issue, in this exact shape)

```
## <SEVERITY>: <one-line title>

**Spec section:** <quote the exact source-of-truth section, e.g. "§7.3 — Manifest is the packer's job, not the worker's">

**Violation:** <one-paragraph description of what the agent did wrong>

**Fix:** <specific instructions on what change to make. Do NOT paste rewritten code; describe the change as a directive>
```

### 11.4 Rules for the reviewer

- **Do not rewrite code.** The fix instructions describe *what to
  change*, not *here is the new code*.
- **Only review.** Don't add new requirements that aren't in the source
  of truth. If a missing thing is genuinely needed, flag it as a
  proposal in a separate section, not as a finding against the stage.
- **Quote, don't paraphrase.** Every finding cites a specific section
  (§N.M) and quotes the binding sentence.
- **Be decisive.** A finding is either CRITICAL, MAJOR, or MINOR. Don't
  hedge.
- **If everything is clean, say so.** The review concludes with either
  `## REVIEW VERDICT: PASS — proceed to Stage <N+1>` or
  `## REVIEW VERDICT: HALT — <count CRITICAL> CRITICAL, <count MAJOR> MAJOR findings; address before re-submitting Stage <N>`.

---

## 12. Resolved decisions + one new open question

### 12.1 Resolved

1. **Powerline notch frequency:** Locked to 60 Hz (MIMIC-IV-ECG is US-recorded). Applied in Stage 9 if/when preprocessed signals are materialized.
2. **Image rendering layouts:** Keep BOTH Lead-II strip and 12-lead 3×4 grid + rhythm strip. 12-lead grid must use low DPI (~100) and high PNG `compress_level=9` / low JPEG quality to minimize on-disk footprint. Applied in Stages 4–5.
3. **`signals_corrupted` anchor size:** Keep 2 000 anchors × 8 corruptions × 5 SNRs ≈ 80 000 rows. Applied in Stage 8.
4. **Cardiologist `T_cardio` text:** Ingest from `data/raw/waveform_note_links.csv`, store as nullable `T_cardio` column in `ecg_metadata.parquet`. Do not gate any main-paper task on it. Applied in Stage 0.

### 12.2 New open question (blocks Stage 9 only)

5. **Preprocessed-signal modality — materialize or on-the-fly?** Plan A/B §4.4 mandates "raw and preprocessed signal as separate modalities, never overwrite raw." Two ways to satisfy:

   - **5.A — Materialize:** build `signals/lead2_preprocessed.h5` + 5 × `twelve_lead_preprocessed_shard_*.h5` with the §3.3 filter chain. **Disk cost: +75 GB** on top of the ~204 GB Phase-1 end state.
   - **5.B — Locked recipe + on-the-fly:** save `config/preprocessing_recipe.yaml` + `config/scalers/lead2_zscore_train.npz` (kilobytes). Consumer's `read_modality(study_id, "preprocessed_lead2")` reads raw and applies the recipe at read time. Disk cost: ~0; ~few-ms read overhead per signal. Same logical separation, same Plan A/B §4.4 compliance.

   Stages 0–8 do not block on this. Stage 9 does. Decide before running Stage 9.

---

## 13. What this leaves for Phase 2

Out of scope for this document, but tracked so it's not forgotten:

- All Plan A/B §5 tasks (Plan A: A1–A6) and §6 tasks (Plan B: B1–B6) builders need rewriting to consume the new consolidated artifacts via the §2.1 manifest. The existing scripts under `scripts/phase2_tasks_benchmark_and_paper/` are mostly file-system readers (open `data/processed/signals_lead2/{id}.npy`); each needs a one-line switch to `read_modality(study_id, 'raw_lead2')`.
- §7 paper evidence matrix (figures, tables, ablations) — unchanged from current state.
- §8 supplement materials — unchanged.
- §9 reproducibility deliverables — Phase-1 share is fully covered by this document; the Phase-2 share is added when Phase 2 runs.
- Stale Phase-2 outputs already present in `data/processed/task_jsonl/` (e.g. `taskA_verification.jsonl`, `taskB_temporal_grounding.jsonl`, …) were generated from the old per-study modalities and are wrong after the Phase-1 regen. Phase 2's first action should be: delete the stale JSONLs, then re-run the task builders against the new manifest.
