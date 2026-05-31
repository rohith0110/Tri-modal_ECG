# Tri-Modal ECG — Session Handoff Summary

**Purpose.** Self-contained context for a fresh Claude Opus 4.7 instance.
Read this first; you will then have enough background to pick up the
work without needing the prior session's transcript.

The **authoritative spec for what to do next** is
[`docs/PIPELINE_SOURCE_OF_TRUTH.md`](PIPELINE_SOURCE_OF_TRUTH.md). This
file is just the orientation document that gets you there.

---

## 1. What this project is

**Tri-Modal ECG Benchmark** built on **MIMIC-IV-ECG** (~800,033 10-second
12-lead ECGs at 500 Hz, ~161 K patients). The goal is a publishable
multimodal benchmark where each ECG study has three aligned modalities
(signal + image + text) used for cross-modal verification, temporal
grounding, and physiological-contradiction detection.

Repo root: `D:\Coding\MU\Tri-Modal_ECG` (Windows, PowerShell + Git Bash).

Two binding source-of-truth documents from the user's professor:
- `TriModal_ECG_Truth.docx` — defines the tri-modal benchmark scope
  (Tasks A / B / C) and names file-path conventions.
- `ECG_Benchmark_Neutral_Implementation_Plan_Plan_A_B.docx` — the
  broader implementation rules (non-negotiables, modality definitions,
  linkage protocol, supplementary requirements, reproducibility).

**Authority hierarchy.** Where the two disagree, **Plan A/B wins.** All
relevant binding content has been quoted into
`docs/PIPELINE_SOURCE_OF_TRUTH.md`; the agent does not need to re-read
the docx files for Phase 1.

---

## 2. What's been done so far (this session)

The session started with an already-built tri-modal dataset at
`data/processed/` (~406 GB, ~4 million per-study files) that was built
with a Plan-B-only mindset before the Plan A/B docx was available. After
reviewing both docs, the user decided to **rebuild Phase 1 from scratch**
to:

1. **Consolidate storage** — kill the 4 million tiny files; pack into
   parquet / HDF5 / tar shards. (~170 files total at end state.)
2. **Achieve Plan A/B compliance** — the existing pipeline is missing
   several mandated artifacts (rich QC, NeuroKit2 structured features,
   version lock, EHR linkage analysis, preprocessed-signal modality,
   the 12-lead grid image layout, the four required audit reports,
   `task_input_policy.yaml`, etc.).
3. **Fix one known bug** — `05_task_B2_noise_robustness.py` uses Python
   built-in `hash()` which is non-deterministic across processes; must
   replace with `hashlib.sha256`.

Concrete artifacts produced **this session**:

- **`scripts/` reorganized** into two phases (`phase1_dataset_generation/`
  and `phase2_tasks_benchmark_and_paper/`) with per-phase READMEs. Code
  was not modified — only files moved + renamed.
- **MIMIC-IV Hosp v3.1 + ED v2.2 downloaded** to `data/mimic-iv-hosp-3.1/`
  and `data/mimic-iv-ed-2.2/`. ED via wget (116 MB), Hosp via the user's
  AWS account (9.9 GB) since wget was extremely slow. Both verified
  against SHA256SUMS.txt and row counts via pandas (see
  `data/.wget_logs/access_check.json`).
- **`docs/PIPELINE_SOURCE_OF_TRUTH.md` authored** — the canonical
  agent-facing spec for Phase 1 regeneration. Locked storage decisions,
  10-stage migration plan, agent output format, reviewer checklist.
- **`scripts/STORAGE_PLAN_GENERATOR_AWARE.md`,
  `SPEC_VS_STORAGE_PLAN_AUDIT.md`,
  `docs/STORAGE_CONSOLIDATION_PLAN.md`** — three earlier iteration
  documents that were superseded and **deleted**.

---

## 3. Locked decisions you need to know

Folder-by-folder storage decisions (full table in `PIPELINE_SOURCE_OF_TRUTH.md` §2):

| Old per-study folder       | Decision                                                                                                          |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `qc/` 651 K JSON           | → single `qc.parquet` (delete JSONs)                                                                              |
| `signal_metadata/` 781 K   | → single `signal_metadata.parquet` (delete JSONs)                                                                 |
| `signals_lead2/` 800 K NPY | → `signals/lead2_raw.h5` chunked HDF5 (delete `.npy`)                                                             |
| `signals_12lead/` 800 K NPY| → `signals/twelve_lead_raw_shard_{00..04}.h5` 5-way sharded HDF5 (delete `.npy`)                                  |
| `signals_corrupted/` 80 K  | → `signals_corrupted.parquet` (delete .npy + fix hash() non-determinism)                                          |
| `images_clean/` 800 K PNG  | → 100 × `images/clean_lead2_shard_*.tar` (Lead-II strip) + 30 × `clean_12lead_shard_*.tar` (3×4 grid, low DPI)    |
| `images_scanlike/` 800 K JPG | → 50 × `images/scanlike_lead2_shard_*.tar` + 18 × `scanlike_12lead_shard_*.tar`                                 |

All consolidated artifacts use a `modality_manifest.parquet` lookup keyed
on `(study_id, modality_kind)` with SHA256 per blob, `dataset_version`
stamp, and `created_at` timestamp. Consumers read via a single
`read_modality(study_id, kind)` helper.

**Resolved minor decisions** (§12):
1. Powerline notch = **60 Hz** (US recording).
2. Both image layouts (Lead-II strip + 12-lead grid) shipped; 12-lead
   uses low DPI / high compression.
3. `signals_corrupted` anchor size = 2 000 (× 8 corruptions × 5 SNRs).
4. `T_cardio` ingested as nullable column in `ecg_metadata.parquet`.

**Migration policy:** **delete-as-you-go per stage**, NOT
archive-and-keep. The raw WFDB waveforms at `data/raw/files/` are the
only true source of truth; everything else is regenerable from them via
the version-locked scripts. The user's D: drive (1 TB total, ~195 GB
free at session end) cannot hold both old and new layouts
simultaneously, so each stage builds the new artifact, validates it
against a SHA256 spot-check of the old, then deletes the old folder
immediately.

**One unresolved decision** (§12.5, blocks Stage 9 only):
- **Preprocessed-signal modality — materialize or on-the-fly?** Both
  satisfy Plan A/B §4.4. Materialize = +75 GB; on-the-fly via locked
  recipe = ~0 GB. Stages 0–8 don't block on this.

---

## 4. Current disk state (as of session end)

| | Size                |
| -- | ------------------ |
| D: total / free       | 1,050 GB / 195 GB |
| `data/processed/` (old per-study) | 406 GB |
| `data/raw/` (after Hosp+ED added) | 100 GB |

Final state after Phase 1 regen will be ~310 GB in `data/processed/`
(without materializing preprocessed signals). The 10 stages all fit
within disk budget thanks to delete-as-you-go — peak free space hits
~46 GB during Stage 3 packing, then climbs back to >200 GB free for the
remaining stages.

---

## 5. What the agent should do next

The user wants their AGENT (separate from the reviewer) to start
implementing Phase 1 stage-by-stage. The flow is:

1. **Agent reads `docs/PIPELINE_SOURCE_OF_TRUTH.md`** and starts with
   Stage 0 from §9. Implements the scripts listed there, runs them,
   validates per the stage's validation block.
2. **Agent emits the §10 8-section stage report** to
   `outputs/stage_reports/stage_0_report.md` and prints it to stdout.
3. **User pastes the report to the reviewer (the role you're playing
   in a fresh session).** Reviewer runs through the §11 checklist,
   classifies findings as CRITICAL / MAJOR / MINOR, quotes spec
   sections, gives fix directives — **does not rewrite code**.
4. **Reviewer issues `PASS` or `HALT`** verdict at the end.
5. If PASS: agent proceeds to Stage 1.
6. If HALT: agent applies fixes, re-runs validation, re-emits the
   report.

Repeat for all 10 stages.

The first stage to implement is **Stage 0 (Foundation):**
- Sub-step 0.0: directory reorganization (if not already done) — move
  raw data under `data/raw/`, processed under `data/processed/`.
- `00_lock_versions.py` (new) — writes `config/dataset_versions.yaml`.
- `00b_access_check.py` (new) — verifies raw data integrity.
- `01_build_master_index.py` (modify existing) — adds new columns to
  `ecg_metadata.parquet` including the `T_cardio` nullable column.

---

## 6. Important context not in the spec doc

### 6.1 Logging hygiene is a hard rule

The user explicitly called out that multi-process workers writing
directly to stdout produces garbled interleaved output. The spec doc §8
makes workers communicate only by return value; each worker logs to its
own `scripts/logs/<script_name>/worker_<pid>.log`; the main process owns
the single `tqdm` bar and the only `print` statements. Any stage report
that shows worker `print` calls is a MAJOR finding.

### 6.2 Resource policy

`MAX_WORKERS = max(1, math.floor(os.cpu_count() * 0.75))`. `MAX_RAM_GB`
is computed dynamically as `psutil.virtual_memory().total / 1024**3 − 8`
(leave 8 GB for OS + other apps). The existing
`10_extract_ecg_signals.py` hardcodes 16 GB — flag that as MAJOR if not
fixed during regen.

### 6.3 PowerShell quirks the agent will hit

- Windows MAX_PATH = 260 chars unless long-path support is on. Deeply
  nested `partial/lead2_worker_{wid}.h5` paths are fine.
- `wget` is NOT installed by default. The user installed
  `JernejSimoncic.Wget` via winget; it lives at
  `$env:LOCALAPPDATA\Microsoft\WinGet\Packages\JernejSimoncic.Wget_*\wget.exe`.
- Bash tool (Git Bash) is available, but POSIX paths translate to
  Windows: `cd /d/Coding/MU/Tri-Modal_ECG` works for read-only commands.
- The `data/.wget_logs/` folder holds the historical download logs and
  `access_check.json` (machine-readable row counts).

### 6.4 What's intentionally outside Phase 1

The 37 scripts in `scripts/phase2_tasks_benchmark_and_paper/` are
**Phase 2**. They include the Task A/B/C/B1/B2/B5 builders, model
training, benchmark eval, and paper figures. After Phase 1 regen,
**Phase 2 needs a separate pass**: every script that opens
`data/processed/signals_lead2/{id}.npy` etc. directly becomes one-line
edit to `read_modality(study_id, kind)`. The stale `task_jsonl/` files
already on disk are wrong post-regen and must be deleted before Phase 2
re-runs.

### 6.5 The user is on a slow PhysioNet connection

The MIMIC-IV Hosp download via wget was ~63 KB/s; the user switched to
AWS (their own credential) for that one. If a future stage needs to
re-fetch raw data, expect this constraint. The current `data/raw/`
contents are fully present — nothing to re-download for Phase 1.

---

## 7. The minimum the agent needs to read

If the agent only reads two files, make them:

1. **`docs/PIPELINE_SOURCE_OF_TRUTH.md`** — the actual spec, ~75 KB.
2. This file (`docs/CONVERSATION_SUMMARY.md`) — context for *why*
   the spec is what it is.

If the agent reads a third, make it **`scripts/README.md`** — explains
the current Phase 1 / Phase 2 script layout.

The agent does NOT need to read `TriModal_ECG_Truth.docx` or
`ECG_Benchmark_Neutral_Implementation_Plan_Plan_A_B.docx` directly for
Phase 1 work; every binding clause has been quoted into the source-of-
truth doc.

---

## 8. Glossary

| Term                        | Meaning                                                                                                                  |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Phase 1                     | Dataset generation: raw MIMIC-IV-ECG → on-disk tri-modal dataset. Scope of this regen.                                  |
| Phase 2                     | Tasks / benchmark / paper figures. Out of scope here; touched only by `read_modality(...)` switch later.                |
| Pattern A                   | Multiprocessing layout: workers return dicts; main process writes one parquet with chunked flush. For small-row tables. |
| Pattern B                   | Multiprocessing layout: each worker writes its own private shard; a single-process packer streams-merges into the canonical artifact. For big-payload modalities. |
| Modality manifest           | `data/processed/modality_manifest.parquet` — single lookup `(study_id, modality_kind) → (container, locator, sha256, …)`. |
| Linkage tier (L0/L1/L2/L3)  | EHR linkage strength per ECG. L3 = exact temporal overlap; L0 = no usable EHR link. Determined in Stage 1.              |
| Plan A vs Plan B            | EHR-grounded benchmark (Plan A) vs no-EHR-linkage robustness benchmark (Plan B). Decision is auto-computed in Stage 1.  |
| Stage report                | The 8-section markdown summary the agent emits after each stage (§10 of source-of-truth doc).                            |
| Review verdict              | The reviewer's PASS / HALT after walking the §11 checklist on a stage report.                                            |
