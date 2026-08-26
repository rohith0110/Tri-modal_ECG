# Phase 2 — Live Progress & Handover

**This is the single file that carries state between sessions.** Any agent
starting cold reads this first, works, then updates it before the session ends.
`AGENTS.md` at the repo root enforces that loop.

- **Last updated:** 2026-08-26 (session 2)
- **Current stage:** Stage P2.0 — **COMPLETE, validation PASS 26/26**
- **Next action:** Step 2 — write the 12 task builders + `00_extract_fiducials.py`
  (Stages P2.1 / P2.2). See §6 Step Ledger.
- **Blockers:** none. Questions 9 and 11 — the two that gated the A2 and B5
  builders — were resolved 2026-08-26 (§4 Round 6, spec §12.8). Every remaining
  §5 question has a stated default and blocks nothing.
- **Branching:** never. All work lands on `main` — see §3 "Repo and git".

---

## 1. Cold-start orientation (read in this order)

| #   | Document                            | What it gives you                                                                                                                                                                                     |
| --- | ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **this file**                       | current state, what is done, what is next, decisions, open questions                                                                                                                                  |
| 2   | `docs/PHASE2_SOURCE_OF_TRUTH.md`    | **binding science spec** — 12 tasks (A1–A6, B1–B6), cohorts, labels, input policies, model architectures, training/eval protocol, audit requirements. §12 holds locked decisions; §13 the open queue. |
| 3   | `docs/PHASE2_EXECUTION_PLAN_DGX.md` | **operations** — which stage runs on DGX vs laptop, the campaign schedule, data staging, quota rules, access model                                                                                    |
| 4   | `phase_1_summary_report.md`         | what Phase 1 produced (narrative, with the numbers)                                                                                                                                                   |
| 5   | `docs/PIPELINE_SOURCE_OF_TRUTH.md`  | Phase 1 reference — executed and complete. Read for manifest schemas and artifact meanings. **Never re-run its stages.**                                                                              |

Do not open the two `.docx` source files unless the Phase 2 spec is silent on
something — every binding rule has already been transcribed into it.

**What this project is.** A tri-modal (signal + image + text) ECG benchmark
built on MIMIC-IV-ECG, ~800 K 10-second 12-lead ECGs from ~161 K patients,
linked to MIMIC-IV Hosp/ED records. Phase 1 built and audited the dataset.
Phase 2 turns it into 12 benchmark tasks with trained baselines, full
statistics, and the paper. Target: publication-grade, medical-grade rigour, no
scope compromises.

---

## 2. Where the project stands

**Phase 1: COMPLETE.** All five Phase-2 pre-flight checks pass (spec §9.0).
Stage 8 closed 2026-06-03, Stage 9 2026-06-03, Stage 10 2026-06-05, all PASS.

**Phase 2: Stage P2.0 COMPLETE** (2026-08-26, session 2). Report:
`outputs/stage_reports/stage_P2.0_report.md`. On disk now:

- `scripts/phase2_tasks_benchmark_and_paper/` — 36 pre-regen scripts moved to
  `_legacy_phase1_pre_regen/` with `git mv`; 0 `.py` left at the origin path
- `config/task_definitions.yaml` — rewritten, all 12 tasks, §4 data contract
- `config/task_input_policy.yaml` — rewritten, all 12 tasks, §4.X.4 verbatim
- `config/icd_label_map_LOCKED.yaml` · `lab_itemid_map_LOCKED.yaml` ·
  `corruption_recipes_LOCKED.yaml` · `claim_dictionary_LOCKED.yaml` — authored
- `config/decision_phase2.yaml` — authored (architecture + training + eval +
  DGX identity + Slurm partitions frozen)
- `_dataset_lib/modality.py` — canonical `read_modality()`, self-check PASS on
  all 9 modality kinds
- `_dataset_lib/schema_validators.py` — the re-runnable P2.0 gate, 26/26 PASS
- `data/processed/dev_sample/` — fixed 5,000-study sample (4,761 subjects)
- output tree + `scripts/dgx_portability/` scaffolded with placeholder READMEs
- `data/processed/tasks/` — scaffolded, still empty (Stage P2.1 fills it)

Re-run the gate any time:
`./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/schema_validators.py`

**A dataset paper was written and revised** (IEEE format, `IEEE/`) off the
Phase 1 data. It is separate from the Phase 2 benchmark paper.

### Key numbers to sanity-check against

| Quantity                        |                                              Value |
| ------------------------------- | -------------------------------------------------: |
| ECGs, full index                |                                            800,035 |
| ECGs, clean index (post-QC)     |                         749,112 (93.63 % retained) |
| Subjects                        |                                            161,352 |
| Split (ECGs)                    |          train 523,945 / val 75,525 / test 149,642 |
| Split (subjects)                |            107,851 / 15,397 / 30,844, zero overlap |
| Linkage tiers                   |    L3 468,176 · L2 79,651 · L1 237,934 · L0 14,274 |
| L3 cohort (A1/A3/A4/A6 primary) |                                       468,176 ECGs |
| Modality manifest rows          |                                          6,480,200 |
| Corrupted signal rows (B2)      |                                             79,920 |
| Decision gate                   | `chosen_path: plan_a`, frozen 2026-06-03T08:53:27Z |

### Data footprint on disk (`D:\Coding\MU\Tri-Modal_ECG\data\processed`, 355 GB)

| Artifact                                             |                        Size |
| ---------------------------------------------------- | --------------------------: |
| `signals/twelve_lead_preprocessed_shard_{00..04}.h5` |                    141.8 GB |
| `signals/twelve_lead_raw_shard_{00..04}.h5`          |                     67.5 GB |
| `signals/lead2_preprocessed.h5`                      |                    11.85 GB |
| `signals/lead2_raw.h5`                               |                     5.67 GB |
| `images/scanlike_12lead_*.tar` (18)                  |                     62.3 GB |
| `images/scanlike_lead2_*.tar` (50)                   |                     38.9 GB |
| `images/clean_lead2_*.tar` (100)                     |                     17.8 GB |
| `images/clean_12lead_*.tar` (30)                     |                     8.94 GB |
| `signals_corrupted.parquet`                          |                     0.92 GB |
| `modality_manifest.parquet`                          |                     0.49 GB |
| indexes / linkage / qc / features                    |                     ~0.4 GB |
| `data/raw/ehr_cache/`                                | 1.26 GB (labevents 1.19 GB) |

Signals are float32 + gzip-4. Measured requantisation: **int16 + per-record
scale + shuffle + gzip-4 = 0.40×** (12-lead preprocessed → 56.7 GB), max abs
error 1.1e-3 on signals reaching 70. That is finer than the source ADC
resolution, so it is a storage change, not a precision compromise — but Stage
P2.0 must still prove it empirically (see Step 5).

---

## 3. Hardware, environments, accounts

### Laptop (development only — trains nothing that reaches the paper)

- i7-12700H, 14C/20T, 32 GB RAM, **RTX 3060 Laptop 6 GB**, NVMe SSD
- Free space: D: 214 GB, C: 318 GB
- **Always use `ecg_env`**: `./ecg_env/Scripts/python.exe` — Python 3.11.9,
  torch 2.7.1+cu118, CUDA available, bf16-capable.
  The system Python 3.14 has a **CPU-only** torch. Do not use it.
- Mains power is unreliable (cuts). Every long-running local script must
  checkpoint and resume.

### MU DGX (primary compute)

- NVIDIA **DGX A100**, nodes `dgxa` / `dgxb`, login `dgx-login01` (10.59.121.172)
- **Slurm**, partitions `cpu_student` and `gpu_student`
- **50 GB** storage quota — the constraint the whole execution plan is built around
- Reachable **only inside the MU network**. Access is by remote-desktopping into
  a friend's on-campus laptop. No inbound route from outside campus, ever
  (hard constraint — do not propose tunnels, Tailscale, or reverse SSH).
- Account `se23ucse027`, **expires 2026-12-31**, data purged 10 days later.
  Ask Aman Iftekhar (HPC admin) for an extension in **November**, not December.
- Portal `http://10.59.121.175/dgx` (internal only) — queue limits documented there
- Quota check must run on a compute node, not the login node:
  `echo -e "\nCurrent utilisation: $(du -sh "$PWD" | awk '{print $1}')B\n"`

### Cloudflare R2 (staging, working as of 2026-08-26)

- Buckets: **`trimodal-data`** (uploads, DGX reads) and **`trimodal-results`**
  (DGX writes, laptop reads). Both **private** — never enable public access or
  an `r2.dev` URL; these hold MIMIC-derived data.
- rclone remote `r2:` configured on the laptop and round-trip tested both ways.
- Three scoped tokens exist: laptop read+write on both; DGX read-only on
  `trimodal-data`; DGX read+write on `trimodal-results`.
- `rclone lsd r2:` returns 403 by design — scoped tokens cannot list all
  buckets. Always name the bucket: `rclone lsd r2:trimodal-data`.
- Cost ≈ $2.20/month for ~145 GB; egress to the DGX is free.

### Repo and git

- **All work happens on `main`. Never create a branch, a worktree, or a PR.**
  Confirmed by the user 2026-08-26 (session 2). This repo is a single-track
  handover: the next cold-start session reads `docs/PHASE2_PROGRESS.md` from
  `main`, and anything parked on a side branch is invisible to it. Commit
  straight to `main`.
- Commit when the user asks, at the end of a step. Every Phase 2 commit should
  leave `docs/PHASE2_PROGRESS.md` accurate in the same commit — the doc and the
  code move together or the handover rots.
- **A markdown formatter hook reformats files under `docs/` when they are
  touched**, including files a session only *read*. On 2026-08-26 it turned a
  parenthetical into an `##` heading and a `+ …` continuation line into a bullet
  list inside `PIPELINE_SOURCE_OF_TRUTH.md`. **Run `git diff docs/` before every
  commit and `git checkout --` anything you did not intend to change.** Never
  stage a reformat of a binding spec doc.

### Credentials — never in this repo

DGX password, R2 access keys and secrets live in the user's password manager and
in `%APPDATA%\rclone\rclone.conf` only. **Never** write them into any file under
the repo, any doc, any script, or any commit. The emailed DGX password should be
rotated with `passwd` on first login.

---

## 4. Locked decisions (do not re-litigate)

Full record in spec §12. Round 5 (2026-08-26) is the current one:

1. **Fusion = end-to-end fine-tuned, everywhere.** Encoders train jointly with
   the fusion head. Frozen late fusion is a supplementary ablation only.
2. **A4/B3 fiducials = re-run NeuroKit2 at build time.** Forced: the spec
   claimed Phase 1 cached R-peak arrays; it did not. Must reuse the _corrected_
   Pan-Tompkins path from the Phase 1 regen — the detector bug fixed there must
   not be reintroduced.
3. **DGX-primary, laptop development-only.** CPU-heavy stages go to
   `cpu_student`, not the laptop.
4. **Checkpoints: best-only, evicted on completion.** Supersedes Round 4.4's
   150–200 GB budget, impossible under 50 GB.
5. **Signals staged as int16 + per-record scale.**
6. **Oversized campaigns use aligned i.i.d. chunk cycling _within_ each epoch.**
   Sequential per-chunk training is forbidden (block-local SGD, catastrophic
   forgetting, would sink the paper).
7. **Scope unchanged.** Nothing is dropped to save compute or transfer. Weeks or
   months of runtime is acceptable to the user.

Round 6 (2026-08-26, session 2 — decided during Stage P2.0):

8. **Every measurement threshold reads the MACHINE measurement.** B5's four
   families and the A2/B1/A5-masked-attribute bins all read
   `ecg_metadata_clean_with_measurements.parquet` — `machine_hr_bpm`,
   `machine_qrs_ms`, `qrs_axis`, and `qrs_onset − p_onset` for PR. Spec §4.B.5.3
   named `structured_features.parquet.pr_ms`; that column is NeuroKit-derived
   (median 120 ms, max 9468 ms) and `structured_features.qrs_ms` is
   byte-identical to `qrs_dur_ms`, not the machine `qrs_end − qrs_onset` that
   §4.A.2.3's own formula specifies. **This is a documented deviation and must be
   disclosed in the supplementary.** No builder may reach for
   `structured_features.qrs_ms` or `.pr_ms` by name.
9. **B5 injections are swaps of text that is actually present, never
   insertions.** A study is eligible only when the measurement sits in a clear
   zone *and* the report carries a matching surface form, so every
   `corrupted_span_start/end` points at real characters and the corrupted class
   is not detectable by length or phrasing style. **128,674 of 749,112 studies
   (17.2 %) are eligible.**
10. **A2's primary cohort is `sqi_tier ∈ {high, medium}`, not `high`.**
    Deviation from §4.A.2.2, which also mis-estimates the cohort at ~445 K.
    Measured: `high` is 0.56 % of the clean cohort, so a literal A2 would train
    on **3,110** ECGs; `{high, medium}` gives **275,088 L3 ECGs** (94,025
    subjects). high-only becomes one row of the §4.A.2.8 per-SQI sensitivity
    table. A4 already used `{high, medium}` and is unaffected — the two tasks
    now share one SQI rule. **Disclose in the supplementary.**
11. **B5 emits exactly one row per *eligible* study, corrupted with p = 0.5.**
    Reconciles §4.B.5.3 (which yields 12:1) with §6.4 ("balanced 50/50 by
    dataset design") — the only reading under which both are true, and the one
    §6.4 relies on when it applies no `pos_weight` to the B5 binary head.
    Cohort **128,674 rows**, 38,438 subjects. Ineligible studies contribute no
    row. Clean rows are drawn from the *same* eligible pool on purpose, so
    "the report contains a swappable claim" is not itself a signal for the
    label. **Disclose in the supplementary.**

Earlier rounds (spec §12.1–12.6) remain binding: Plan A primary + Plan B
supplementary, seeds 42/123/456, patient-level bootstrap n=10,000 BCa, AUPRC
primary for imbalanced tasks, thresholds from train+val only, 70/10/20 patient
split inherited and never re-split.

---

## 5. Open questions

**Blocking nothing right now.** Raise each at the moment it is reached.
Questions 9 and 11 are closed; the rest carry a stated default, so a builder
can proceed under it and only needs a decision if the default looks wrong once
the real numbers land.

| #   | Question                                                                             | Raise at             | Status |
| --- | ------------------------------------------------------------------------------------ | -------------------- | ------ |
| 1   | A3 lab-window join: `same_subject` only, or `same_subject AND same_hadm_id`?         | P2.1, A3 builder     | open   |
| 2   | A5 anchor pool: random or stratified over the 5 negative types?                      | P2.1, A5 builder     | open   |
| 3   | B5 span offsets: character-level or token-level?                                     | P2.2, B5 builder     | open — §4.B.5.5 declares char offsets, so character-level is the assumed default |
| 4   | Does the DGX have **outbound internet**?                                             | first friend session | open   |
| 5   | Is there **scratch space beyond the 50 GB**? Would remove chunking from 3 campaigns. | first friend session | open   |
| 6   | Slurm wall-time / GPU limits on `gpu_student`?                                       | first friend session | open   |
| 7   | Is an **NGC PyTorch container** available? Frees ~12 GB of quota.                    | first friend session | open   |
| 8   | User's home upload bandwidth (~145 GB to upload over the project)                    | anytime              | open   |
| 9   | **A2 primary cohort.** §4.A.2.2 sets it to `sqi_tier == 'high'` and predicts ~445 K ECGs. Measured: high-SQI is 4,166 of 749,112 clean studies (0.56 %), of which **3,110 are L3**. Built to the letter, A2 trains on 3,110 ECGs. | P2.1, A2 builder | **RESOLVED 2026-08-26** — `sqi ∈ {high, medium}` is primary: **275,088 L3 ECGs**, 94,025 subjects, train 192,087 / val 27,820 / test 55,181. high-only demoted to the §4.A.2.8 sensitivity table. Spec §12.8.4. |
| 10  | **B2 anchor pool is not high-SQI.** §4.B.2.2 says "test-split ECGs with `sqi_tier='high'`". Stage 8 actually took the first 2,000 test-split `raw_lead2` rows in `study_id` order, no SQI filter: 8 high / 1,119 medium / 745 low. The set is frozen and must never be regenerated. | before the B2 write-up | open — default: amend the spec text, keep the frozen anchors, describe them accurately in the paper |
| 11  | **B5 row emission.** §4.B.5.3 ("one clean row per ECG + a corrupted row with p=0.5") gives 12:1; §6.4 asserts "balanced 50/50 by dataset design". Both cannot hold. | P2.2, B5 builder | **RESOLVED 2026-08-26** — one row per **eligible** study, corrupted with p=0.5 → exact 50/50 over **128,674 rows**, 38,438 subjects, train 89,855 / val 12,944 / test 25,875. Spec §12.8.5. |
| 12  | **Regime_2 augmentation policy** is unspecified in §7.3. | P2.5, B2 regime_2 trainer | open — default recorded in `corruption_recipes_LOCKED.yaml`: p=0.5 per sample, family and SNR uniform, RNG salted `regime2\|` |
| 13  | **B6 hard tier** — add a same-HR-bucket, SAME-SUBJECT swap? (Round 3 left it RESERVED.) | P2.2, B6 builder | open — default: ship the hard tier empty |

---

## 6. Step ledger — the actual work

Marks: `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked.
**Update these marks as you go.** Details for each step are in the execution
plan; this is the index of record.

### Part 1 — Laptop, development (~2 weeks)

- [x] **Step 1 — Groundwork (Stage P2.0).** DONE 2026-08-26, validation PASS
      26/26. Report: `outputs/stage_reports/stage_P2.0_report.md`.
  - [x] Quarantine **all** pre-regen scripts in
        `scripts/phase2_tasks_benchmark_and_paper/` → `_legacy_phase1_pre_regen/`
        — 36 scripts moved with `git mv`, 0 `.py` left at the origin path. The
        collisions were wider still: 10–12, 20–24, 30–34, 40–44, 50–51, 60–66,
        70–72. `README.md` deliberately stayed put (it already carries the
        "everything here is stale" banner). `data/processed/task_jsonl/` was
        already absent, so §2.4 step 1 needed no action.
  - [x] Rewrite `config/task_definitions.yaml` — 12 task keys, per spec §4
  - [x] Rewrite `config/task_input_policy.yaml` — 12 task keys, allowed/forbidden
  - [x] Author `config/icd_label_map_LOCKED.yaml` (A1, 5 ICD groups) — all 5
        validated against `d_icd_diagnoses`: 175 codes, 275,334 assignment rows
  - [x] Author `config/lab_itemid_map_LOCKED.yaml` (A3, 7 labs) — §4.A.3.2 step-5
        coverage gate PASS (Ca 75.81 %, Mg 77.25 % ±24 h in L3, both ≥ 50 %), so
        the 7-lab universe locks. Itemids verified identical to `key_labs.yaml`.
  - [x] Author `config/corruption_recipes_LOCKED.yaml` (8 families × 5 SNRs) —
        transcribed from the Stage 8 source; a gate check re-parses that source
        and asserts the family list and SNR ladder still match.
  - [x] Author `config/claim_dictionary_LOCKED.yaml` (B5, 4 families)
  - [x] Author `config/decision_phase2.yaml` (frozen architecture/training/eval
        + DGX identity + Slurm partitions)
  - [x] Scaffold the output tree and `scripts/dgx_portability/` — 20 directories,
        9 placeholder READMEs. `.gitignore` also fixed: `/outputs/*` was
        swallowing `outputs/results/` and the figure/release provenance READMEs.
  - [x] Write `_dataset_lib/modality.py` — the canonical `read_modality()`,
        self-check PASS on all 9 kinds
  - [x] Build `data/processed/dev_sample/` — 5,000 studies / 4,761 subjects,
        deterministic (`SEED = 2026`)
  - [x] *(added)* `_dataset_lib/schema_validators.py` — the Pydantic schemas §9.1
        mandates, wrapped in a re-runnable 26-check gate
- [ ] **Step 2 — Write the 12 task builders + `00_extract_fiducials.py`** (~1 week)
      — **start here.** Resolve §5 questions 9 and 11 when the A2 and B5
      builders are reached; everything else has a stated default.
- [ ] **Step 3 — Write training + evaluation code** (~3–4 days)
- [ ] **Step 4 — Write the chunk-cutter and campaign launchers** (~2 days)
- [ ] **Step 5 — Make int16 copies + prove equivalence** (float32-vs-int16
      training comparison for the supplementary)
- [ ] **Step 6 — Staged uploads to R2** (~145 GB total, in campaign order)

### Part 2 — First DGX session (~1 hour)

- [ ] **Step 7 — Environment survey** (the 7 checks; answers → §5 questions 4–7)
- [ ] **Step 8 — Set up rclone + folders, run a 5-minute Slurm smoke job**

### Part 3 — Campaign 0, `cpu_student` (~2 days)

- [ ] **Step 9 — Run the 12 task builders + fiducial extraction at full scale**
- [ ] **Step 10 — Run the three audits (leakage / cohort / split)** — _all must
      PASS before any GPU time is spent_
- [ ] **Step 11 — Algorithmic baselines**
- [ ] **Step 12 — Pull results, review cohort report**

### Part 4 — Campaigns 1–4 (~1 week)

- [ ] **Step 13 — Text models** (21 runs) · [ ] **Step 14 — 12-lead pictures** (21)
- [ ] **Step 15 — Lead-II pictures** (21) · [ ] **Step 16 — Lead-II signals** (33)

### Part 5 — Campaigns 5–6 (~1 week)

- [ ] **Step 17 — 12-lead signals, L3 tasks** (12, fits resident)
- [ ] **Step 18 — 12-lead signals, full cohort** (18, chunked)

### Part 6 — Campaigns 7–8, the heart of the paper (~1.5 weeks)

- [ ] **Step 19 — End-to-end fusion, L3 tasks A1/A3/A6** (9, fits resident)
- [ ] **Step 20 — End-to-end fusion, full cohort A5/B4/B5/B6** (12, chunked)
- [ ] **Step 21 — Frozen-fusion ablation** (near-free by-product)

### Part 7 — Campaigns 9–11 (~1.5 weeks)

- [ ] **Step 22 — Re-training sweeps** · [ ] **Step 23 — Re-testing sweeps**
- [ ] **Step 24 — Final eval + calibration/threshold/reproducibility audits**
- [ ] **Step 25 — Tables + figures** · [ ] **Step 26 — Release package**

### Audits that must all be PASS before submission (spec §1.2)

- [ ] `leakage_audit_phase2.md` · [ ] `split_audit_phase2.md` · [ ] `cohort_audit.md`
- [ ] `threshold_audit.md` · [ ] `calibration_audit.md` · [ ] `sensitivity_audit.md`
- [ ] `reproducibility_audit.md`

---

## 7. Known traps

1. **`structured_features.parquet` has no R-peak arrays** despite what spec
   §4.A.4.3 originally said. Only `sqi_per_lead: list<float>` plus scalars.
   Worse, its `qrs_ms` and `pr_ms` are the **NeuroKit2** values, not the machine
   measurements (`qrs_ms` is byte-identical to `qrs_dur_ms`; max 9688 ms). Round
   6.8 forbids reading either column by name — see trap 8.
2. **The Pan-Tompkins detector bug** was found and fixed during the Phase 1
   regen (it had produced ~74 K false labels). Any new fiducial code must reuse
   the corrected path, not a fresh implementation.
3. **`.gitignore` ignores everything at the repo root** (`/*`) and re-includes
   subtrees explicitly. `docs/` was missing from that allowlist until
   2026-08-26 — new docs were being silently ignored. Any **new root-level
   file** needs its own `!/name` entry or it will not be committed.
4. **Never re-split.** Every task subsets `splits_subject_level.parquet`; no
   task reshuffles it.
5. **Never `open()` an HDF5 or tar directly.** Everything goes through
   `read_modality()` and the manifest.
6. **Raw MIMIC never leaves the laptop** and never enters the release package.
7. **`rclone lsd r2:` 403s by design.** Name the bucket.
8. **The machine-measurement missing sentinel is `29999`, and the `*_missing`
   flag columns are useless.** `p_onset_missing`, `qrs_onset_missing`,
   `qrs_end_missing`, `qrs_axis_missing` and `rr_interval_missing` are **all
   False for all 749,112 rows** — they mark nothing. The real encoding is the
   literal `29999` (`p_onset` 119,385 rows, `p_axis` 119,483, `qrs_axis` 1,531,
   `rr_interval` 487, `qrs_onset`/`qrs_end` 341 each). Unmasked, PR has mean
   −4600 ms; masked, mean 162.7 ms (median 160, sd 37). Every builder touching a
   machine measurement must mask it. Rule recorded in
   `claim_dictionary_LOCKED.yaml` and `task_definitions.yaml`.
9. **The manifest's tar `container_offset` points at the 512-byte member
   HEADER, not the data.** Member bytes start at `offset + 512`. `read_modality`
   handles it; nothing else should be reading tars anyway.
10. **12-lead HDF5 is sample-major, `(n, 5000, 12)`; the encoder wants
   `(12, 5000)`.** `read_modality` returns the channel-major view and exposes
   `LEAD_ORDER_12` (lead II is index **1**). A raw `h5py` read fed to `Conv1d`
   trains silently on transposed data.
11. **`sqi_tier == 'high'` is 0.56 % of the cohort**, not the majority the spec
   assumes for A2. See §5 question 9 before building A2 or A4.

---

## 8. Session log

Append a short entry per session: what changed, what to do next. Newest last.

### Session 1 — 2026-08-26

- Verified Phase 1 complete against the on-disk artifacts (all 5 pre-flight
  checks PASS); the spec's "Stages 8/9/10 pending" note was stale.
- Surveyed the real data footprint (355 GB) and benchmarked signal
  requantisation options (int16 + scale = 0.40×, error 1.1e-3).
- Found that A4/B3 fiducial ground truth does not exist — spec corrected.
- Received the MU HPCF allocation details (DGX A100, Slurm, 50 GB, expiry
  2026-12-31) and rewrote the execution plan around them: DGX-primary,
  laptop development-only, campaign-based data residency, chunk cycling.
- User locked Round 5: end-to-end fusion, no scope compromises, heavy work on
  the DGX.
- Wrote `docs/PHASE2_EXECUTION_PLAN_DGX.md`; updated the Phase 2 spec (status,
  §2.4, §4.A.4.3, §8, §8.4, §9.9, §12.7, §13.4), the Phase 1 spec status,
  `CONVERSATION_SUMMARY.md`, and both script READMEs.
- Set up Cloudflare R2: two private buckets, three scoped tokens, rclone
  configured and round-trip tested.
- Fixed `.gitignore` to include `docs/`.
- **Next:** Step 1 (Stage P2.0 groundwork).

### Session 2 — 2026-08-26

- **Stage P2.0 complete, 26/26 validation checks PASS.** Full report in
  `outputs/stage_reports/stage_P2.0_report.md`; transcript in
  `stage_P2.0_validation.log`.
- Quarantined 36 pre-regen scripts with `git mv`; the origin path is clear and
  every numeric slot the Phase 2 scripts need is free.
- Rewrote both config files to the 12-task contract; authored the four LOCKED
  YAMLs and `decision_phase2.yaml`.
- Wrote `_dataset_lib/modality.py` (canonical `read_modality()`) and
  `_dataset_lib/schema_validators.py` (the Pydantic schemas + the re-runnable
  gate). Built the 5,000-study `dev_sample`.
- **Verified against the data rather than trusting the spec**, which turned up
  five conflicts now queued as §5 questions 9–13 and traps 8–11:
  the `29999` sentinel and the dead `*_missing` flags; `structured_features`
  carrying NeuroKit rather than machine intervals (**user decided: machine
  measurements everywhere**); A2's high-SQI primary cohort being 3,110 ECGs not
  ~445 K; the frozen B2 anchors not being high-SQI; and B5's 50/50 balance being
  unreachable as §4.B.5.3 is written.
- Also confirmed the good news: the §4.A.3.2 step-5 gate PASSES (Ca 75.81 %,
  Mg 77.25 %), so the 7-lab universe locks, and all 5 ICD groups resolve
  against `d_icd_diagnoses` (175 codes, 275,334 assignment rows).
- Fixed `.gitignore` — `/outputs/*` was silently swallowing `outputs/results/`
  and the figure/release provenance READMEs. Installed `pydantic` 2.13.4 into
  `ecg_env` (the only dependency added; `transformers` is still needed for Step 3).
- Committed Stage P2.0 as `aa723cf` on `main` (61 files).
- **User confirmed the git convention: everything on `main`, never branch.**
  Recorded in §3 "Repo and git", `AGENTS.md` and `CLAUDE.md`. Also recorded the
  `docs/` formatter-hook trap there — it reformatted four binding spec docs that
  this session only read; they were reverted and kept out of the commit.
- **Questions 9 and 11 resolved** (user took both defaults). A2's primary
  cohort becomes `sqi ∈ {high, medium}` — 275,088 L3 ECGs instead of 3,110 — and
  B5 emits one row per eligible study at p = 0.5, an exact 50/50 over 128,674
  rows. Both are documented deviations from §4 and ship in the supplementary.
  Recorded in spec §12.8 (new Round 6 block) + §13.5, in
  `task_definitions.yaml`, `claim_dictionary_LOCKED.yaml` and
  `decision_phase2.yaml`, and in §4 above. Gate still 26/26.
- **Next:** Step 2 — the 12 task builders + `00_extract_fiducials.py`. Nothing
  blocks it. The remaining §5 questions (1, 2, 3, 12, 13) each have a stated
  default and are raised only if the numbers contradict it; questions 4–8 are
  for the first DGX session and touch no laptop work.
