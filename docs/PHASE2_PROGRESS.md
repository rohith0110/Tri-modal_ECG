# Phase 2 — Live Progress & Handover

**This is the single file that carries state between sessions.** Any agent
starting cold reads this first, works, then updates it before the session ends.
`AGENTS.md` at the repo root enforces that loop.

- **Last updated:** 2026-08-27 (session 3)
- **Current stage:** Stages P2.1 and P2.2 — **COMPLETE.** All 13 Step-2 scripts
  written and run at full scale on the laptop. Reports:
  `outputs/stage_reports/stage_P2.1_report.md`, `stage_P2.2_report.md`.
- **Next action:** Step 10 / Stage P2.3 — the three audits (leakage, cohort,
  split), which §4.C invariant 4 makes the gate before any training and, since
  the Round 6.12 amendment, before the first upload too. Then Step 3.
- **Blockers:** none. The A3 lab-cache prerequisite is **DONE** (§4 decision 13).
  Every §5 question is now resolved, dissolved, or proceeding under its stated
  default — see §5.
- **Compute:** amended 2026-08-26 — **all CPU-only stages run on the laptop at
  full scale**, not on `cpu_student`. The DGX stays primary for every trained
  model. See §4 decision 12.
- **The A3 lab-cache prerequisite is done.**
  `data/raw/ehr_cache/labevents_key_labs.parquet` — 20,481,517 rows, 18 locked
  itemids, `ref_range_lower` / `ref_range_upper` / `flag` recovered on 100 % of
  rows. The Phase 1 `labevents.parquet` was left untouched (§4 decision 13).
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
3. **DGX-primary for every TRAINED model.** ~~CPU-heavy stages go to
   `cpu_student`, not the laptop.~~ **Amended 2026-08-26 (Round 6.6): all
   CPU-only stages run on the laptop at full scale** — `00_extract_fiducials.py`,
   the 12 task builders, the P2.3 audits, the P2.4 algorithmic baselines. The
   user approved long local runs. The GPU half of the plan is unchanged.
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
12. **CPU-only stages run at home, at full scale.** Amends decision 3 above and
    spec §12.7.3. Buys: the EHR cache never leaves the laptop, ~3 GB less to
    upload, one fewer campaign, and the audit gate closes *before* the first
    upload instead of after it. Costs: a couple of days of laptop wall-clock,
    and **every long local script must checkpoint and resume** — that is a
    requirement, not an optimisation. Spec §12.8.6.
13. **The lab cache must be re-extracted before A3.**
    `data/raw/ehr_cache/labevents.parquet` kept only `valuenum` and dropped
    `ref_range_lower`, `ref_range_upper` and `flag` — the three columns
    §4.A.3.3's rule branches on. They exist in
    `data/raw/mimic-iv-hosp-3.1/hosp/labevents.csv.gz`. Re-extract, filtered to
    the 18 locked itemids, streaming the gz. Extends a cache; re-runs no Phase 1
    stage. Spec §12.8.7, `config/lab_itemid_map_LOCKED.yaml`.

Round 7 (2026-08-27, session 3 — forced by the data while building Step 2):

14. **QTc reads `machine_qtc_ms`, not `structured_features.qtc_bazett_ms`.**
    Extends Round 6.1 to the third measurement bin. §4.A.2.3 names the NeuroKit
    column; measured, it correlates with the machine QTc at **r = 0.024** and is
    valid for 656,358 studies against the machine column's 748,618. It belongs
    to the same defective family as `structured_features.qrs_ms` and `.pr_ms`,
    which Round 6.8 already forbids by name. Using it would have cut A2's primary
    cohort from 274,911 to 241,192 and defined the `qtc` head against a quantity
    uncorrelated with the vendor's own QTc. `qtc_bazett_ms` survives as the
    provenance column `qtc_ms_bazett` and supplies one §4.A.2.8 sensitivity row.
    **Disclose in the supplementary.**
15. **A6 readmission keeps Phase 1's eligibility rule; censoring is reported, not
    "corrected".** §4.A.6.3 asks to exclude rows whose censoring window cannot be
    observed, assuming a global end-of-data cutoff. MIMIC-IV has none that is
    usable — dates are shifted per patient. The obvious substitute (call a row
    observable when the subject's own record runs past `dischtime + horizon`)
    **conditions on the outcome**, because a record runs on precisely when the
    patient came back: measured, it lifts readmission_30d from 21.4 % to 27.5 %.
    A6 therefore ships `followup_days_after_discharge` as provenance, so a
    censoring-aware sensitivity is a filter, and the residual right-censoring is
    a stated limitation of the readmission heads.
16. **A5's masked-attribute head masks CLAIMS, not numerals.** §4.A.5.3 says to
    replace "numeric mentions of HR, QRS, QT, QTc, axis, and intervals" with
    `[MASK]`. **These reports contain no numeric measurements.** Measured over
    all 749,112: 12.5 % contain any digit, and after removing lead names
    (`V1`–`V6`), ordinals (`1st degree`) and ratios (`2:1`), **0.51 %** remain —
    every one the boilerplate "Age not entered, assumed to be 50 years old".
    Taken literally the rule masks nothing, `report_text_masked` equals
    `report_text`, and the report still says "Sinus bradycardia", so the HR head
    becomes a lookup. The head masks the qualitative claims that carry the
    attribute in this vocabulary (44.3 % of reports) **and** bare numerals, so
    the rule is a strict superset of the literal one. HR/QRS/axis surface forms
    are read from `claim_dictionary_LOCKED.yaml` so A5 and B5 cannot drift.
    Same finding, same direction, as Round 6.3. **Disclose in the supplementary.**
17. **B5's QRS `normal_to_wide` count drops from 23 to 0.** Those 23 studies are
    not injection sites: they are the `qrs_ms <= 90` studies whose report ALREADY
    asserts a wide QRS, so swapping one produces text that *agrees* with the
    measurement under the label "corrupted". Inspected, all 23 are
    "--- Pediatric criteria used ---" reports, where 86–90 ms genuinely **is** an
    intraventricular conduction defect — the adult 120 ms threshold does not
    apply, so the report is right and the adult clear zone misfires. Cohort:
    128,674 → **128,653** (0.016 %). `claim_dictionary_LOCKED.yaml` carries the
    correction, the superseded P2.0 measurement and the reasoning; the builder
    re-asserts the union every run.

Earlier rounds (spec §12.1–12.6) remain binding: Plan A primary + Plan B
supplementary, seeds 42/123/456, patient-level bootstrap n=10,000 BCa, AUPRC
primary for imbalanced tasks, thresholds from train+val only, 70/10/20 patient
split inherited and never re-split.

---

## 5. Open questions

**Nothing is open that blocks work.** Questions 9 and 11 closed in session 2.
Session 3 built all thirteen Step-2 scripts, and in doing so resolved 1 and 3
under their stated defaults, dissolved 2, confirmed 10 against the data, and
applied the stated defaults for 12 and 13. Questions 4–8 are for the first DGX
session and touch no laptop work.

| #   | Question                                                                             | Raise at             | Status |
| --- | ------------------------------------------------------------------------------------ | -------------------- | ------ |
| 1   | A3 lab-window join: `same_subject` only, or `same_subject AND same_hadm_id`?         | P2.1, A3 builder     | open   |
| 2   | A5 anchor pool: random or stratified over the 5 negative types?                      | P2.1, A5 builder     | **DISSOLVED 2026-08-27** — the question presumes anchors are sampled. §4.A.5.2 makes the cohort *every* clean-cohort ECG and §4.A.5.3 gives *every* anchor all five negative types, so no anchor is ever drawn and there is nothing to stratify. What IS drawn is each negative's donor, and that is deterministic per (anchor, neg_type) via a splitmix64 hash, constrained to the anchor's own split and to a different subject. |
| 3   | B5 span offsets: character-level or token-level?                                     | P2.2, B5 builder     | **RESOLVED 2026-08-27** — character offsets into `corrupted_report_text`, the §4.B.5.5 default. Token offsets would depend on a tokenizer the data contract never names. Every span is asserted at build time to mark a real change; median span 19 characters. |
| 4   | Does the DGX have **outbound internet**?                                             | first friend session | open   |
| 5   | Is there **scratch space beyond the 50 GB**? Would remove chunking from 3 campaigns. | first friend session | open   |
| 6   | Slurm wall-time / GPU limits on `gpu_student`?                                       | first friend session | open   |
| 7   | Is an **NGC PyTorch container** available? Frees ~12 GB of quota.                    | first friend session | open   |
| 8   | User's home upload bandwidth (~145 GB to upload over the project)                    | anytime              | open   |
| 9   | **A2 primary cohort.** §4.A.2.2 sets it to `sqi_tier == 'high'` and predicts ~445 K ECGs. Measured: high-SQI is 4,166 of 749,112 clean studies (0.56 %), of which **3,110 are L3**. Built to the letter, A2 trains on 3,110 ECGs. | P2.1, A2 builder | **RESOLVED 2026-08-26** — `sqi ∈ {high, medium}` is primary: **275,088 L3 ECGs**, 94,025 subjects, train 192,087 / val 27,820 / test 55,181. high-only demoted to the §4.A.2.8 sensitivity table. Spec §12.8.4. |
| 10  | **B2 anchor pool is not high-SQI.** §4.B.2.2 says "test-split ECGs with `sqi_tier='high'`". Stage 8 actually took the first 2,000 test-split `raw_lead2` rows in `study_id` order, no SQI filter. The set is frozen and must never be regenerated. | before the B2 write-up | **CONFIRMED 2026-08-27, default applied.** The B2 builder measures the mix rather than restating the spec: **8 high / 1,119 medium / 744 low** among the 1,871 anchors that carry usable B1 labels (1,998 anchors exist; 127 lack valid machine measurements). The frozen set is untouched, the builder records the real mix in the task README, and the paper must describe B2 anchors as an SQI-representative test-split sample. The §4.B.2.2 sentence is what needs amending. |
| 11  | **B5 row emission.** §4.B.5.3 ("one clean row per ECG + a corrupted row with p=0.5") gives 12:1; §6.4 asserts "balanced 50/50 by dataset design". Both cannot hold. | P2.2, B5 builder | **RESOLVED 2026-08-26** — one row per **eligible** study, corrupted with p=0.5 → exact 50/50 over **128,674 rows**, 38,438 subjects, train 89,855 / val 12,944 / test 25,875. Spec §12.8.5. |
| 12  | **Regime_2 augmentation policy** is unspecified in §7.3. | P2.5, B2 regime_2 trainer | **DEFAULT APPLIED 2026-08-27** — `corruption_recipes_LOCKED.yaml` `regimes.regime_2.augmentation_policy`: p = 0.5 per sample, family uniform over all 8, SNR uniform over {30,20,10,5,0}, a train_augmentation RNG stream distinct from the frozen test set. The B2 builder stamps the policy into the task README so the trainer reads it from one place. Still revisitable at P2.5 — it changes a trainer, not the data. |
| 13  | **B6 hard tier** — add a same-HR-bucket, SAME-SUBJECT swap? (Round 3 left it RESERVED.) | P2.2, B6 builder | **DEFAULT APPLIED 2026-08-27** — the hard tier ships empty. The tier name stays in `eval_keys.parquet`'s vocabulary, so adding it later rebuilds one small pointer table plus the matching B4 rows, and no trained model. |

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
- [x] **Step 2 — Write AND RUN the 12 task builders + `00_extract_fiducials.py`**
      — **DONE 2026-08-27, all 13 at full scale.** Every script smoke-tests on
      `dev_sample/` first, then runs for real; all of them checkpoint and resume,
      and `--dev` writes to `data/processed/tasks/_dev/` so a smoke test can
      never overwrite a real table. Reports: `stage_P2.1_report.md`,
      `stage_P2.2_report.md`.
  - [x] **Prerequisite for A3 — DONE.** `00b_rebuild_lab_cache.py` streamed
        `labevents.csv.gz` (158,374,764 rows) in 4 M-row chunks and wrote
        `data/raw/ehr_cache/labevents_key_labs.parquet`: 20,481,517 rows over
        the 18 locked itemids, with `ref_range_lower` / `ref_range_upper` /
        `flag` recovered on **100 %** of rows in every lab. 9.0 min. The Phase 1
        `labevents.parquet` was NOT overwritten — it is a provenance artifact
        covering every itemid, and the rebuild covers 18.
  - [x] `00_extract_fiducials.py` — **749,112 studies in 223.5 min** on 15
        workers (~56/s at the end). The full clean cohort, so A4's primary,
        A4's full-cohort sensitivity and B3 are all served by one pass.
        0.10 % fallback, 99.29 % delineation, R-peak rate vs machine HR
        **r = 0.9206** — the corrected Phase 1 detector path reproduces.
        `sqi_per_bin` mean 0.6178 against Phase 1's `sqi_aggregate` median
        0.617, so B3's per-bin SQI is on the right scale and needs no second
        pass over 11.85 GB. Output 79.6 MB sparse.
  - [x] `01_build_A1_ecg_diagnosis.py` — 376,051 primary rows / 95,765 subjects
  - [x] `02_build_A2_measurement_blind.py` — 275,088 / 94,025, **exactly** the
        locked Round 6.4 cohort and split
  - [x] `03_build_A3_lab_abnormality.py` — 422,147 primary rows, 150 columns
  - [x] `04_build_A4_event_localization.py` — 275,045 primary rows / 94,027
        subjects; 90.8 % of beats carry a usable QRS span, median span 86 ms
        (p05 50, p95 160)
  - [x] `05_build_A5_cross_modal_verification.py` — 5,243,784 verification rows
        + 748,454 masked-attribute rows
  - [x] `06_build_A6_risk_stratification.py` — 422,147 primary rows / 114,859 subjects
  - [x] `07_build_B1_measurement_blind.py` — 748,454 rows
  - [x] `08_build_B2_noise_robustness.py` — 900,005 rows, complete 8 x 5 grid
  - [x] `09_build_B3_temporal_grounding.py` — 2,996,448 rows (749,112 x 4
        queries); `noisy_sqi_threshold` **locked at 0.415030** from the train
        split and written into `task_definitions.yaml`
  - [x] `10_build_B4_cross_modal_verification.py` — 5,243,784 rows, **A5/B4 row
        equality PASSES** at full scale
  - [x] `11_build_B5_contradiction_detection.py` — 128,653 rows, 49.92 % corrupted
  - [x] `12_build_B6_difficulty_stratified.py` — pointer table, hard tier empty
  - [x] Emitted `stage_P2.1_report.md` (4,393 lines) and `stage_P2.2_report.md`
        (2,183 lines) in the §10 eight-section format, generated from the state
        files and the artifacts rather than written by hand
- [ ] **Step 3 — Write training + evaluation code** (~3–4 days)
- [ ] **Step 4 — Write the chunk-cutter and campaign launchers** (~2 days)
- [ ] **Step 5 — Make int16 copies + prove equivalence** (float32-vs-int16
      training comparison for the supplementary)
- [ ] **Step 6 — Staged uploads to R2** (~145 GB total, in campaign order)

### Part 2 — First DGX session (~1 hour)

- [ ] **Step 7 — Environment survey** (the 7 checks; answers → §5 questions 4–7)
- [ ] **Step 8 — Set up rclone + folders, run a 5-minute Slurm smoke job**

### Part 3 — Full-scale build + audits, **on the laptop** (~2 days of compute)


Amended 2026-08-26 (Round 6.12). This was Campaign 0 on `cpu_student`. Step
numbers are kept so the plan and this ledger stay aligned, but Steps 9 and 11
now happen inside Steps 2 and 3 rather than after Step 8.

- [x] **Step 9 — Run the 12 task builders + fiducial extraction at full scale,
      locally** (folded into Step 2) — DONE 2026-08-27
- [ ] **Step 10 — Run the three audits (leakage / cohort / split)** — *all must
      PASS before any GPU time is spent, and now before the first upload too*
- [ ] **Step 11 — Algorithmic baselines, locally** (folded into Step 3).
      NeuroKit2 over the test split — budget hours, run overnight.
- [ ] **Step 12 — Review the cohort report.** Nothing to pull down; it is all
      already here. **This is the gate that releases Step 6's first upload.**

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
   the corrected path, not a fresh implementation. **The corrected path is
   `scripts/phase1_dataset_generation/32_compute_structured_features.py::_extract_wave_features`
   (lines 364–390), mirrored in `31_waveform_qc.py:272–283`:**

   ```python
   _, peak_info = nk.ecg_peaks(lead2, sampling_rate=500, method="neurokit")
   rpeaks = _indices(peak_info.get("ECG_R_Peaks"))
   _, waves = nk.ecg_delineate(lead2, rpeaks=rpeaks, sampling_rate=500,
                               method="dwt", show=False, check=False)
   ```

   Three things to carry over exactly, or `00_extract_fiducials.py` will not
   reproduce Phase 1's fiducials:
   - `method="neurokit"`, **not** `"pantompkins"`. The corrected detector is
     NeuroKit's default. Note that spec §4.A.4.7 and §5.1 describe the A4
     algorithmic baseline as "NeuroKit2 Pan-Tompkins" — if the oracle baseline
     is built with `pantompkins` while the ground truth uses `neurokit`, its F1
     will **not** be the 1.0 §4.A.4.7 promises. Resolve when writing A4.
   - The input is `preprocessed[:, 1]` — lead II of the **preprocessed**
     12-lead signal — and it is fed to `ecg_peaks` **without** a further
     `ecg_clean` call. (`_sqi_one` does clean first; the fiducial path does
     not. Do not "fix" this.)
   - `ecg_delineate` runs on the same array as `ecg_peaks`, with
     `check=False`.
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
7b. **`data/raw/ehr_cache/labevents.parquet` is missing `ref_range_lower`,
   `ref_range_upper` and `flag`** — the three columns A3's label rule needs. It
   kept only `labevent_id, subject_id, hadm_id, itemid, charttime, valuenum,
   valueuom` across 158,374,764 rows. The originals are in
   `data/raw/mimic-iv-hosp-3.1/hosp/labevents.csv.gz` (16 columns). Re-extract
   before A3; see §4 decision 13. Also: **never load that table whole** on a
   32 GB laptop — filter to the 18 locked itemids at read time (~21 M rows).
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
12. **The machine reports carry NO numbers.** 12.5 % of the 749,112 clean reports
   contain a digit; after lead names (`V1`–`V6`), ordinals (`1st degree`) and
   ratios (`2:1`), **0.51 %** remain, and every one is the boilerplate "Age not
   entered, assumed to be 50 years old". Any spec sentence about "numeric
   mentions" in the report text (§4.A.5.3 was one) is describing a corpus this
   is not. What the reports state is the qualitative claim — "Sinus
   bradycardia", "Left axis deviation", "RBBB". §4 decision 16.
13. **`--dev` used to overwrite the real task parquets.** Both modes wrote to
   `data/processed/tasks/<task>/`, so a two-minute smoke test silently replaced
   a full-scale table with 5,000 dev rows and nothing downstream could tell.
   Fixed 2026-08-27: `build_common.set_dev()` routes dev output to
   `data/processed/tasks/_dev/`, and every builder calls it right after parsing
   args. **A new builder that forgets `bc.set_dev(args.dev)` reintroduces the
   bug.**
14. **The cohort contains paediatric ECGs and adult thresholds misfire on them.**
   659 of 749,112 clean reports (0.088 %, 654 subjects) say
   "--- Pediatric criteria used ---". Their median HR (74 bpm) and QRS (94 ms)
   are within a beat and a millisecond of the adult medians, so the A2/B1 bins
   are not materially affected — but every one of B5's 23 spurious
   report-says-wide / measurement-says-narrow QRS pairs was paediatric, where
   86–90 ms genuinely IS a conduction defect. §4 decision 17.
15. **The `n_ecg_expected_*` numbers in §4 and `task_definitions.yaml` are
   pre-QC.** They were computed on the 800,035-row full index; every builder
   works on the 749,112-row post-QC clean cohort (93.6 %). So A1's "expected
   468,176" lands at 422,147 L3 rows and A6's "416,440 mortality-observable"
   lands at 382,572. Nothing is wrong — the two are counting different
   populations. Compare against the clean cohort, not the spec's estimate.

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
- **Compute placement amended (Round 6.12):** the user approved long local runs,
  so every CPU-only stage — fiducial extraction, the 12 builders, the audits, the
  algorithmic baselines — moves off `cpu_student` and onto the laptop, at full
  scale. Updated `PHASE2_EXECUTION_PLAN_DGX.md` (amendment block, campaign table,
  Steps 2/6/9–12, upload table, timeline), spec §12.8.6, `decision_phase2.yaml`,
  and §4/§6 here. The DGX half of the plan is untouched.
- **Found an A3 blocker while checking the plan:**
  `data/raw/ehr_cache/labevents.parquet` (158,374,764 rows) kept only
  `valuenum` — it dropped `ref_range_lower`, `ref_range_upper` and `flag`, which
  are exactly what §4.A.3.3's rule branches on. The columns exist in
  `data/raw/mimic-iv-hosp-3.1/hosp/labevents.csv.gz`. Recorded as spec §12.8.7,
  §4 decision 13, trap 7b, and a `cache_rebuild_required` block in
  `lab_itemid_map_LOCKED.yaml`. Re-extraction is a Step 2 prerequisite for A3.
- **Next:** Step 2 — the 12 task builders + `00_extract_fiducials.py`, written
  AND run at full scale locally. Nothing blocks it. The remaining §5 questions (1, 2, 3, 12, 13) each have a stated
  default and are raised only if the numbers contradict it; questions 4–8 are
  for the first DGX session and touch no laptop work.

### Session 3 — 2026-08-27

- **Step 2 is 11/13 done at full scale, on the laptop, per the Round 6.12
  compute amendment.** Every builder was smoke-tested on `dev_sample/` first and
  then run for real; the numbers below are the real ones.
- **Lab cache rebuilt** (`00b_rebuild_lab_cache.py`): 158,374,764 source rows
  streamed in 4 M-row chunks → 20,481,517 rows over the 18 locked itemids, with
  `ref_range_lower` / `ref_range_upper` / `flag` recovered on 100 % of rows in
  every lab, in 9.0 min. Written as a **sibling** file; the Phase 1
  `labevents.parquet` is untouched. The A3 blocker is closed.
- **`00_extract_fiducials.py` runs over the full clean cohort** (749,112), not
  just A4's L3 slice, because A4's sensitivity cohort and B3's cohort are both
  the full clean cohort — one pass serves three needs. It reuses the corrected
  Phase 1 detector path verbatim, and the dev sample confirms it reproduces:
  R-peak rate vs machine HR **r = 0.931**, 0.14 % fallback, 99.24 % delineation.
  It also emits `sqi_per_bin` (10 × 1 s) so B3 needs no second 11.85 GB pass.
- **Full-scale results.** A1 376,051 primary / 95,765 subjects · A2 275,088 /
  94,025 (exactly the locked Round 6.4 numbers, split included) · A3 422,147 /
  114,859 over 150 columns · A5 5,243,784 verification rows (28.571 % positive =
  exactly 2-in-7) + 748,454 masked rows · A6 422,147 / 114,859 · B1 748,454 ·
  B2 900,005 with a complete 8 × 5 grid · B4 5,243,784 with the **A5/B4 equality
  assertion passing** · B5 128,653 at 49.92 % corrupted · B6 pointer table.
  Zero subject overlap on every table.
- **Five things the data forced**, all recorded in §4 as decisions 14–17 and in
  §7 as traps 12–15:
  1. QTc must read `machine_qtc_ms` — the NeuroKit `qtc_bazett_ms` correlates
     with it at r = 0.024.
  2. A6's readmission censoring cannot be "corrected" in MIMIC-IV without
     conditioning on the outcome (21.4 % → 27.5 % if you try).
  3. The machine reports contain no numerals, so A5's masked-attribute head
     masks claims instead — and 44.3 % of reports carry one.
  4. B5's 23 `normal_to_wide` QRS studies are not injection sites; all 23 are
     paediatric reports where the adult threshold misfires. 128,674 → 128,653.
  5. `--dev` was overwriting full-scale task parquets. Fixed.
- **Every §5 question is now closed or running under its stated default.**
  1 resolved (both joins built), 2 dissolved, 3 resolved, 10 confirmed against
  the data, 12 and 13 defaults applied. 4–8 remain for the first DGX session.
- Config changes: `task_definitions.yaml` (QTc source, B3 threshold slot),
  `lab_itemid_map_LOCKED.yaml` (rebuild done + result), `claim_dictionary_LOCKED.yaml`
  (QRS correction + superseded measurement). **P2.0 gate re-run after each: 26/26.**
  The gate's quarantine check was also fixed — it asserted the Phase 2 script
  directory holds zero `.py`, true at P2.0 and wrong the moment Step 2 began.
- Commits on `main`: `bd32b9c`, `e336238`, `0ae04b7`, `7fd076b`, `13f0f9d`.
- **Stages P2.1 and P2.2 closed at 03:56.** The fiducial run finished in
  223.5 min (749,112 studies, r = 0.9206 vs machine HR, 0.10 % fallback);
  `04_build_A4...` then produced 275,045 primary rows and `09_build_B3...`
  2,996,448 rows with `noisy_sqi_threshold` locked at **0.415030** from the
  train split. Both stage reports were emitted in the §10 format, generated
  from the state files and the artifacts on disk.
- **Independent verification** (re-derived from the raw sources, not from
  builder code): A1's five ICD heads on 400 admissions → MATCH; A3's K/pm24h
  label, method and signed hours on 300 rows → MATCH; A6's mortality_30d and
  _90d on 4,000 rows → MATCH; A5's 40,000 negatives → 0 cross-split references
  and 0 same-subject swaps, HARD_NEGATIVE_TEXT donors 100 % same-HR-bucket
  against TEXT_SWAP's 70 %; B5's 20,000 spans all mark a real change with a
  median length delta of 0 (a swap, not an insertion); B2's grid 40/40 cells at
  1,871 anchors each with regime_1 and regime_2 on the identical set; B3's four
  queries re-derived on 4,000 studies → MATCH. Every task table's `split`
  column equals the frozen subject-level split and no subject crosses splits.
- **Next:** Step 10 / Stage P2.3 — the leakage, cohort and split audits. §4.C
  invariant 4 makes them the gate before any training, and the Round 6.12
  amendment makes them the gate before the first upload as well.
