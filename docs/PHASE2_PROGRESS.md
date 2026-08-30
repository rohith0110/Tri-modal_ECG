# Phase 2 — Live Progress & Handover

**This is the single file that carries state between sessions.** Any agent
starting cold reads this first, works, then updates it before the session ends.
`AGENTS.md` at the repo root enforces that loop.

- **Last updated:** 2026-08-30 (session 11)
- **Current stage:** Stages P2.1–P2.4 were complete at full scale. **Round 10 —
  the Plan A/B compliance audit — then reopened four of them on purpose.**
  A cold re-read of `ECG_Benchmark_Neutral_Implementation_Plan_Plan_A_B.docx`
  against what is on disk found six gaps; all six are now closed in code and
  spec (spec §12.9, `docs/PLAN_DOCX_COMPLIANCE_AUDIT.md`). Five cost no GPU
  time; one costs +30 runs. **Nothing had been trained**, which is why they were
  cheap — and why they had to be done before Step 6's first upload.
- **✅ THE AUDIT GATE IS GREEN — Step 10R is DONE (2026-08-28).** All four
  Round 10 tables were rebuilt at full scale and all three audits re-run:
  leakage **PASS 88/88**, cohort **PASS 199/199**, split **PASS 79/79** —
  **366 checks, zero violations**. `30_train.py` will now start.
- **Step 6 — DONE 2026-08-30 (sessions 8–10). Every byte the DGX needs is in
  `r2:trimodal-data`: 601 objects, 226.4 GiB.** Report:
  `outputs/stage_reports/step6_staging_report.md`. All 14 campaigns' datasets
  are uploaded; campaign 11–14's `results` come from `r2:trimodal-results`,
  which `push_results.sh` fills from the DGX.
  New tooling: `make_subsets.py` (six derived datasets — the three L3/scan-like
  ones from the task parquets' `is_primary` rows, 422,147 studies, plus the
  three `*_valtest` sets the chunked campaigns evaluate on) and `upload_data.py`
  (resumable, `--dry-run`, per-dataset checksum manifests, refuses raw MIMIC and
  credential-shaped paths by pattern). `modality.py` gained **manifest overlays**
  so a subset container or a chunk piece is read with no caller changed.
  **The read path was proved by round trip, twice.** Campaign 1: 49 files pulled
  back with the real `stage_data.sh`, checksum-verified, every path where
  `modality.py` looks for it. Campaign 9 (session 10): a raw piece pulled from
  R2, `install_overlays()` installed, and `read_modality()` returned arrays
  **bit-identical** to the base container for sampled studies — the chunked
  read path, which nothing had exercised end to end before.
  **Four bugs were found and fixed before a campaign could hit them:** `fetch()`
  named the destination after the object; datasets must carry paths *relative to
  `data/processed`*; a cross-volume hard link made an upload report success
  while pushing nothing; and `used_gb()` counted nested roots twice (below).
- **Open questions 14 and 15 are CLOSED (2026-08-29), except 15a's validation.**
  There are now **14 campaigns**: 7/8/11 are the 12-lead halves of the fusion
  and final-eval campaigns and 12/13/14 the Lead-II ones, because a fusion
  campaign reads a whole lead set and holding both put campaign 7 at 69 GB.
  Staging also gained a **train phase and an eval phase**, so no campaign holds
  its test split while it trains. **All 14 now pass `require_fit` in both
  phases** with 5 GB of checkpoints resident; the largest is campaign 7 at
  37.7 GB. The chunked campaigns got their val/test data (measured, plain
  datasets, nothing extra chunked) and a piece reader plus in-epoch cycling —
  **15a is implemented but not validated: a mid-epoch fetch needs outbound
  internet on the DGX, which is open question 4.**
- **Step 7 is DONE and Step 8 is half done (2026-08-30, session 11). The DGX
  account is live and reaches R2.** `rclone lsd r2:trimodal-data` lists all 17
  directories from the DGX; `stage_data.sh 1 --dry-run` resolves the right roots
  and passes the quota check on the real machine.
  **Open question 4 is ANSWERED: ONLINE** — a `cpu_student` compute node reaches
  the internet, so §8.2 rule 2's mid-epoch piece fetch is available to campaigns
  6, 8 and 9. The fetch itself still has to run once before 15a is called
  validated.
- **Next action — `stage_data.sh 1` for real on dgxa, then the venv, then the
  smoke job.** Exact commands and state in Step 8 below.
- **Two DGX-only bugs were caught on the laptop in session 10 and fixed.**
  (1) `used_gb()` summed `du` over `PROJECT_ROOT`, `DATA_ROOT` and
  `RESULTS_ROOT` without noticing that **`RESULTS_ROOT` defaults to
  `$PROJECT_ROOT/outputs`** — so every staged byte under a nested root was
  counted twice and the 45 GB ceiling was enforced against roughly double the
  truth. On a node with no scratch (`DATA_ROOT=$PROJECT_ROOT/data/processed`,
  the case `_campaign_body.sh` explicitly contemplates) **campaign 7 at 37.7 GB
  would have measured ~75 GB and refused to stage.** Nested roots are now
  dropped before `du`; `bash campaigns.sh selfcheck` is the runnable proof.
  (2) Ten of the shell scripts had **CRLF line endings** in the working tree,
  and `upload_data.py` ships `scripts/` straight from that tree to a Linux box,
  where `bash` fails a CRLF script at the shebang. `.gitattributes` now pins
  `*.sh` and `*.sbatch` to `eol=lf`, all ten are normalised, and `code` was
  re-uploaded.
- **Step 12 — SIGNED OFF 2026-08-28 by the project owner. The first upload is
  released.** `cohort_audit.md` PASS, 184 checks, 0 violations; four disclosure
  items accepted for the paper's limitations (A3's structurally-absent rare
  classes, QTc `short` thin in val, the ~0.7 % high-SQI tier, and A5/B4/B6
  carrying no SQI/linkage columns for §7 subgrouping). See Step 12 below.
- **Step 11 — DONE 2026-08-27 at full scale.** 8/8 doc-mandated §5.1 baselines
  wrote `test_predictions.parquet`; `missing_mandated = []`. **The §9.5 oracle
  gate passed exactly:** A4 `r_peak_f1` / `qrs_onset_f1` / `qrs_offset_f1` all
  `1.000000` over 55,140 rows with mean |offset| 0.0000 ms, and B3 `mIoU`
  `1.000000` over 598,568 rows with every row bin-for-bin exact. The baselines
  therefore read exactly the fiducials the builders wrote.
- **Audit gate (Step 10 / Stage P2.3) — PASSED 2026-08-27, INVALIDATED by
  Round 10 on 2026-08-28.** The 2026-08-27 run was PASS on all three
  (88 / 184 / 75 = 347 checks, zero violations) and the method stands: every
  number is measured off the task parquets rather than restated from a builder's
  state file. But four task tables are being rebuilt, so those numbers no longer
  describe the data. **Re-running the three audits is how the gate re-opens** —
  they read only artifacts already on disk and write only their own report.
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

Added by Steps 5 and 6:

| Artifact                                             |                        Size |
| ---------------------------------------------------- | --------------------------: |
| `signals_int16/` (6 files, Step 5)                   |                     90.7 GB |
| `derived/signals_12lead_L3/` (3 splits, Step 6)      |                     43.9 GB |
| `derived/images_clean_12lead_L3/` (3 splits)         |                      5.1 GB |
| `derived/images_scanlike_test/` (test, both layouts) |                     20.4 GB |
| `chunks/` — 3 cuts × 8 train pieces (on C:, Step 6)  |                     ~84 GB |

**CORRECTED 2026-08-28 (Step 5), measured.** The requantisation ratio above was
an estimate and it was wrong: int16 + per-record scale + gzip-4 measures
**0.55×**, not 0.40×, because the float32 source is *already* gzip-4 compressed.
12-lead preprocessed is **83.24 GB (77.5 GiB)**, not 56.7 GB; the whole
conversion was 164.98 → 90.66 GB. The "max abs error 1.1e-3 against amplitude
70" also does not describe this data — the preprocessed signals are z-scored per
lead and reach 1,923. What was proved instead (Step 5, four arms): the int16
encoding moves every metric **0.42× as much as changing the training seed does**.

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

- NVIDIA **DGX A100**, nodes `dgxa` / `dgxb`, login `dgx-login01` (10.59.121.172),
  Ubuntu 22.04.5. **Surveyed 2026-08-30 (Step 7) — the numbers below are measured.**
- **Slurm**, partitions `cpu_student` / `gpu_student` (**MaxTime 7 days**);
  `*_faculty` and `*_scholar` exist at **30 days** and outrank us. Jobs of 15, 5
  and 4 days were running during the survey — **queue wait, not GPU speed, sets
  throughput for the 312 runs.**
- **GPUs are MIG-partitioned and the cards are 40 GB, not 80.** Full cards:
  `gpu:a100` ×2 on dgxa, ×5 on dgxb — **7 in total, campus-wide**. The rest are
  slices: `a100_4g.20gb`, `a100_3g.20gb`, `a100_2g.10gb`, `a100_1g.5gb` (24 of
  the smallest). **An untyped `--gres=gpu:1` matches any of them, including a
  5 GB slice**, so every `.sbatch` now says `--gres=gpu:a100:1`. The slices are
  far less contended and worth costing once peak memory per campaign is known.
- **`--mem` is mandatory.** These partitions default to the whole node's memory
  (1,031,800 MB), so a job without `--mem` waits for a completely empty node —
  forever, on a shared box — and Slurm reports it as *"Nodes required for job
  are DOWN, DRAINED or reserved"*, blaming the nodes rather than the request.
  All 14 `.sbatch` files now carry `--mem=64G`.
- **50 GB storage quota** — the constraint the whole execution plan is built
  around. `/home` shows 238 GB in `df`; that is the filesystem, not the quota,
  and there is no `quota` command, so **`du` is the only measure** — which is
  what `used_gb()` does.
- **No writable scratch.** `/scratch`, `/raid`, `/work` exist but are not
  writable; only `/tmp/$USER` is. `resolve_data_root()` used to fall through to
  `/tmp`, which would have staged 30 GB outside the quota — node-local, invisible
  to `used_gb`, different on dgxa and dgxb, emptied by a reboot. **Project
  decision 2026-08-30: everything lives inside the 50 GB.** `/tmp` was removed
  from the candidate list, so `DATA_ROOT` resolves to `$HOME/trimodal-data`,
  a sibling of `$PROJECT_ROOT` and therefore counted once.
- **One home, seen from every node, but only fast on one.**
  `$HOME=/dgxa_home/se23ucse027` everywhere — local ext4 on dgxa, NFS from dgxa
  on dgxb, and the login node resolves there too (`/home/se23ucse027` does not
  exist). So a single staged copy serves both nodes and the `--requeue` resume
  path survives landing on either. **But measured 2026-08-30 with
  `dd iflag=direct`: dgxa 2.9 GB/s, dgxb 105 MB/s — 28x.** The loader does tens
  of thousands of ~100 KB random reads per epoch, so a run on dgxb does not
  fail, it starves the GPU for days. **All 14 campaigns are pinned
  `--nodelist=dgxa`**, which costs GPUs: dgxa holds 2 of the 7 full A100s. The
  20 GB MIG slices on dgxa (`a100_3g.20gb`, `a100_4g.20gb`) are the way to buy
  concurrency back without leaving the fast disk — worth costing once peak
  memory per campaign is measured.
- **The 50 GB is not enforced.** `quota -s` reports `none`; the filesystem is
  14 TB with 6.1 TB free, and nothing would stop a run at 60 GB. The ceiling is
  policy, so `used_gb()` / `require_fit` is the only thing holding it — which is
  why the /tmp fallback removal above matters more, not less.
- **Python 3.10.12**, system, no `module`, no conda, no container runtime —
  plain venv + pip. (The laptop's env is 3.11.)
- A `cpu_student` allocation still **sees all 6 local GPUs** via `nvidia-smi`,
  so staging jobs can run there without consuming a contended `gpu:a100`.
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

Round 8 (2026-08-27, session 4 — forced by the data while writing Step 3):

18. **The image transform resizes the whole render; it does not centre-crop.**
    §5.3 specifies `Resize(short_side) → CenterCrop(target_h, target_w)` and
    justifies 224×672 and 384×512 as preserving the render aspect ratios.
    Measured, the Phase 1 renders are **3600×750** (Lead-II clean, 4.8:1) and
    **1016×504** (12-lead, 2.02:1) — not 3:1 and 1.33:1. Applied literally, the
    centre crop discards **37 % of every Lead-II strip** (the first and last
    ~2 s of a 10-second ECG) and the outer lead columns of the 12-lead grid.
    The stated intent — the whole ECG at the locked target size — is honoured by
    resizing the full image into the target box. Target sizes, and therefore the
    §6.6 VRAM budgets, are unchanged. The augmented variant keeps §5.3's
    translation jitter by resizing 5 % larger and random-cropping back; colour
    jitter and the ±2° rotation are unchanged and horizontal flip stays off.
    Recorded as `decision_phase2.yaml → architecture.image_encoder.transform_deviation`;
    implemented in `_dataset_lib/task_dataset.py::build_image_transform`.
    **Disclose in the supplementary.**

Round 9 (2026-08-27, session 5 — forced by the audits in Step 10):

19. **A declared-provenance column is not a leak; an unreachable one is proven,
    not asserted.** §9.4 says to flag any forbidden column in a task parquet,
    and §11.2 calls that CRITICAL — but §4.A.2.5 lists `hr_bpm`, `qrs_ms` and
    `qtc_ms` under the comment `# provenance`, and §4.B.5.5 lists
    `source_measurement`. Read literally the two rules contradict each other and
    A2, B1 and B5 would permanently violate a spec that mandated their own
    schemas. `20_audit_tasks_leakage.py` therefore names every such column with
    the §4 section that mandates it (`PROVENANCE`), treats an unlisted one as a
    violation, treats an **unclassified** column as a violation too, and proves
    unreachability by constructing the real `TaskDataset` for every (task,
    arch-tier family) the policy allows and checking the tensor keys it hands
    the model. A column list alone would have been both too weak — the leakage
    surface is the dataloader, not the schema — and too strong.

20. **The audit gate parses a verdict LINE.** `30_train.py::check_audit_gate`
    used to scan the whole report for the substring `FAIL`. The leakage audit
    lists every column of every task and A1's heads are named
    `label_heart_failure_narrow`, so a clean report was read as a blocked one.
    `_dataset_lib/audit_common.report_verdict` is now the single parser of
    `**VERDICT: PASS|FAIL**` and `30_train.py` imports it; every audit parses its
    own rendered report with it before the file lands, so an audit cannot emit a
    report the gate would misread. See trap 20.

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
| 14  | **Campaigns 7, 8 and 11 read the Lead-II streams too, and did not fit.** Their configs include `multimodal_fusion_lead2` / `embedding_cosine_lead2`, so they needed both lead sets resident: campaign 7 measured **69 GB** against a 45 GB ceiling. | before campaign 7 | **CLOSED 2026-08-29. Split by lead subset.** `campaign_runs.py` now routes fusion and embedding tiers by lead subset as well as by tier: **7/8/11 are the 12-lead halves, 12/13/14 the Lead-II ones**, with `campaign_12/13/14.sbatch` written to match. `--table` still reports **104 configs and 312 runs** — no config renamed, no run dropped, no seed dropped. Residency was then re-derived from the files on disk rather than estimated, and a second lever was needed: a campaign does not hold its test split while it trains, so the table carries a train-phase and an eval-phase size and `stage_data.sh --phase` picks one (it filters on the `__<split>.` suffix the derived containers already carry, so no dataset had to be duplicated). **ACCEPTANCE MET: all 14 campaigns pass `require_fit` in both phases with 5 GB of checkpoints resident** — the largest is campaign 7 at 37.7 GB. |
| 15  | **The chunked campaigns (6, 8, 9) could not run on pieces:** nothing read `piece_NNN.h5`, and pieces are cut from TRAIN only, so there was no val split to early-stop on and no test split to evaluate. | Step 7/8 planning | **15b CLOSED 2026-08-29, no chunking needed — the preferred outcome. MEASURED** off the containers: 12-lead int16 **101.6 KiB/study** (val 7.9 GB, test 15.6 GB), clean 12-lead images **11.7 KiB/study** (0.9 / 1.8 GB), raw 12-lead float32 **88.5 KiB/study** (6.8 / 13.6 GB). All of that fits beside two resident pieces, so val and test ship as PLAIN datasets (`signals_12lead_valtest`, `images_clean_12lead_valtest`, `signals_raw_valtest`) and nothing extra is cut. Campaign 6 is 21.0 GB training / 15.5 GB evaluating. **15a IMPLEMENTED 2026-08-29, VALIDATION BLOCKED ON QUESTION 4.** The read side is `_dataset_lib/chunk_pieces.py`: a piece already carries `study_id` per row, so it needs no new reader — an overlay makes `read_modality()` resolve it, and `modality.py` learned that a piece is stored channel-major (it carries the cutter's `piece_salt`) so it is not transposed twice. The cycling is `_train_lib/chunk_cycle.py` **in the training loop, not the Dataset**: staging is a transport call, and `stage_data.sh:51` is explicit that the loop asks for the next piece as it goes. Every piece appears once per epoch in a reshuffled order, two resident, rows shuffled inside the window; the sampling deviation and the transport are stamped into the run metadata. Both self-checks pass. **What is blocked:** fetching piece k+1 mid-epoch needs outbound internet (question 4). Written against `transport()`, so `rclone` (online) and `rclone-offline` + `TRIMODAL_SOURCE` (a mounted drive) are both expressible and the body warns on the offline one — but no mid-epoch fetch has been exercised on a real node. |

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
- [x] **Step 3 — Write training + evaluation code** — **DONE 2026-08-27
      (session 4).** Report: `outputs/stage_reports/stage_P2.4_report.md`.
      Every module carries a runnable `_self_check()`; the whole stack is
      smoke-tested on `dev_sample/` and nothing here has produced a paper number.
  - [x] `_dataset_lib/task_spec.py` — the 12 tasks × 64 heads declared once
        (head kind, label column, mask column, primary metric), cross-checked
        against `task_definitions.yaml` and `task_input_policy.yaml` at import
  - [x] `_dataset_lib/task_dataset.py` — one `Dataset` for all 12 tasks; resolves
        every modality through `read_modality()` and **refuses a forbidden input
        at construction** (`check_input_policy`)
  - [x] `_dataset_lib/bootstrap.py` — patient-level BCa, n=10,000. Refuses a
        frame with no `subject_id`. Self-check proves the patient-level interval
        is >1.5× wider than the ECG-level one on correlated data
  - [x] `_dataset_lib/corruption.py` — B2 regime_2 augmenter; **imports** the
        Phase 1 Stage 8 corruption functions instead of reimplementing them, with
        the locked `regime2|` seed prefix keeping the train stream disjoint
  - [x] `_model_lib/` — `signal_encoders.py` (1D ResNet-18, 9.0 M params, §5.2),
        `image_encoders.py` (ResNet-50 IMAGENET1K_V2, §5.3),
        `text_encoders.py` (Bio-ClinicalBERT rev `d5892b39a4ad` + TF-IDF/SVD,
        §5.4), `fusion_heads.py` (LateFusionMLP, concat_dim 1539, §5.5),
        `task_models.py` (per-task assembly + the §6.4 losses)
  - [x] `_model_lib/model_configs.py` — **94 generated YAMLs**, one per
        (task, arch tier, lead subset), derived from `task_input_policy.yaml` so
        a config cannot name a forbidden modality
  - [x] `_train_lib/` — `seed.py` (§6.2 + RNG capture), `metrics.py` (every §4/§7
        metric), `threshold.py` (**val-only**, refuses any other split and
        refuses to apply a threshold not selected on val), `calibration.py`
        (§6.8 identity → Platt → isotonic, fitted on val only), `trainer.py`
  - [x] `30_train.py` — §6 training infrastructure with three gates: the audit
        gate (§4.C invariant 4), the input-policy gate, and a split gate that
        re-checks subject disjointness **on the rows the run loaded**
  - [x] `31_eval.py` — §7 regimes: per-seed mean ± std, pooled patient-level
        bootstrap CI, subgroup breakdowns, §7.3 B2 AUCC/collapse threshold,
        §7.4 fiducial matcher, §7.5 retrieval, §7.6 calibration + decision curves
  - [x] `config/eval_configs/` — `default.yaml`, `A4_fiducial.yaml`,
        `A6_risk.yaml`, `B2_robustness.yaml`, `cross_modal.yaml`
  - [x] **Checkpoint/resume proven, not asserted** (`_train_lib/smoke_test.py`):
        an interrupted run stops after 2 of 3 batches and the resumed run does
        **exactly the remaining 1**; an epoch-boundary resume restores weights,
        optimizer moments, scheduler, RNG and best-metric; the SIGTERM handler
        raises the stop flag without writing from inside itself; two seed-42 runs
        produce byte-identical weights
  - [x] **Smoke matrix: 34 (task, arch tier) combinations — 11 trainable tasks
        × every tier each task's input policy allows — 34 trains + 34 evals,
        68/68 PASS**, plus the 5 recovery/determinism/gate checks: **73 PASS,
        0 FAIL** on `dev_sample/` with tiny batches. Log:
        `outputs/stage_reports/stage_P2.4_smoke_test.log`
- [x] **Step 4 — Write the chunk-cutter and campaign launchers. DONE
      2026-08-28.** `scripts/dgx_portability/` now holds real launchers:
      `campaigns.sh` (campaign table, quota, transport, root resolution),
      `campaign_runs.py` (campaign -> its `<task> <arch_tier> <seed>` list),
      `make_chunks.py` (plan / cut / verify), `stage_data.sh`, `evict_data.sh`,
      `push_results.sh`, `slurm/_campaign_body.sh` and 11 thin
      `slurm/campaign_NN.sbatch` files.
      **§8.2 rule 1 measured, not asserted:** on the real 12-lead train split,
      523,945 studies into 8 pieces gives sizes 65,260-65,758 (**0.40 %** max
      deviation) and **0 of 523,945 studies disagree** between
      `preprocessed_12lead` and `image_clean_12lead` — the piece key is a pure
      function of `study_id`, so modality alignment is structural and needs no
      coordination between cuts. Independence from the label-like strata:
      cart_id chi2 46.9/dof 70, hr_bucket 12.5/14, link_tier 15.5/21, stratum
      80.6/70. **No acquisition timestamp exists in any processed index**, so
      independence from TIME cannot be measured; the proxy is that consecutive
      study ids scatter across all 8 pieces.
      **Guards tested on this laptop:** the quota gate refuses 44 GB used +
      30 GB asked (exit 1) before any byte moves; a chunked campaign without
      `--pieces` refuses rather than staging everything; a failed push leaves
      checkpoints untouched while a verified push deletes them; the evict guard
      was exercised in all four states (never pushed / just pushed / new result
      after push / `--force`). **One real bug was found and fixed in testing** —
      the evict guard's `find ! -newer` was inverted and counted already-pushed
      results as unpushed.
      **Nothing assumes a verified DGX** (Step 7 has not run): transport falls
      back rclone -> offline rclone -> a plain directory (`TRIMODAL_SOURCE`, the
      courier-a-drive path) -> a refusal naming both options; `DATA_ROOT` probes
      `$SCRATCH`, `/scratch`, `/raid`, `/work`, `/tmp` then `$HOME`; **no
      `--partition` is written into any sbatch file** because a wrong name is a
      submit-time rejection; and the python environment is detected by actually
      importing torch, never by a hard-coded module name.
      **Two decisions taken** (recorded in the README): the 94-config matrix is
      the authority on run counts, not the plan's older estimate table
      (`campaign_runs.py --table` maps all 94 configs to exactly one campaign,
      none orphaned, and exits non-zero if that breaks — campaign 1 is 36 runs,
      not the estimated 21); and Lead-II raw signals stay in campaign 4 rather
      than the campaign-9 sweep, because a campaign is defined by the data it
      reads and both Lead-II encodings are already resident there at 5.7 GB.
- [x] **Step 5 — Make int16 copies + prove equivalence. DONE 2026-08-28.**
      All six files converted and verified (sha256 + 64 spot rows each). Tools: `make_int16.py` (convert / verify, one shard at a
      time, atomic rename only after the checksum is in
      `signals_int16/int16_manifest.json`, so a power cut costs the shard in
      flight and re-running resumes) and `prove_int16_equivalence.py`.
      Report: `outputs/stage_reports/int16_equivalence.md` — supplementary-ready.
      **The proof needed FOUR arms, not two.** A = float32; B = an identical
      repeat; C = int16; D = float32 at seed 123. B came back **bit-identical to
      A on all 9 heads**, which proves training here is deterministic and so
      pins every difference in C on the encoding with no confound — but it also
      makes B's floor exactly 0, a bar nothing perturbed can clear. **D is the
      real yardstick**: it measures how far the metric moves under variation the
      paper already reports as ±std over three seeds.
      **Result — int16 moves the metrics 0.42x as much as changing the seed
      does:** largest int16 metric effect **2.90e-03** against a seed effect of
      **6.90e-03**, and the int16 effect is ≤ the seed effect on *every one* of
      the six metrics. Row-level divergence tells the same story (int16 0.441 vs
      seed 0.893 max delta).
      **A first, stricter version of this test failed**, and the failure was in
      the test: it compared raw per-row probabilities between separately trained
      models. A 1.5e-05 relative input change perturbs the SGD trajectory, the
      runs settle at different points in weight space, and boundary rows swing
      hard while the aggregate barely moves. §8.2 asks whether the *metrics*
      agree, so the verdict is now computed on metrics against the seed
      yardstick; the row comparison is kept as a labelled diagnostic.
      **Two real numerical bugs were found and fixed in the converter:** the
      error was being measured in float32 (at amplitude ~1900 the float32
      spacing is 1.2e-4 against a half-step of 0.03, so the measurement was
      noisier than the quantity it bounded — now float64), and the quotient
      `x / scale` was computed in float32, whose ~6e-8 relative error is ~2e-3
      of a code at magnitude 32767, enough to tip `rint()` to the wrong
      neighbour and push the error past half a step (measured 1.000266). With
      the quotient in float64 the ratio is **0.999983**, so "error ≤ half a
      step" is exactly true rather than nearly true.
      `modality.py` gained a `TRIMODAL_SIGNAL_INT16` switch: `_read_signal`
      resolves to `signals_int16/` and multiplies by the per-record `scale`, so
      trainer, evaluator and baselines all still receive float32 and need no
      change. Verified round-trip relative error **1.53e-05**.
      **`lead2_preprocessed.h5`: 12.73 GB -> 7.42 GB (58.3 %)**, half-step ratio
      1.000000, `verify` re-checks sha256 + 64 spot rows and passes.
      **`outputs/audit_reports/threshold_audit.md` now EXISTS, and every row in
      it is from the equivalence arms, not a paper run.** The four arms are real
      full-scale-path runs (the §4.C gate passes, thresholds are val-selected),
      but they trained A2 on `--limit-rows 10000` for 2 epochs purely to compare
      encodings. A provenance banner at the top of the file says so. Delete the
      banner and supersede those rows once the campaigns append their own —
      otherwise a 10,000-row smoke threshold could reach a results table.
      **SIZE FINDING — §8.2's "56.7 GB" is wrong, MEASURED.** All five 12-lead
      shards convert at a consistent **54.7 %** of source, not the ~40 % the
      estimate assumed, because the float32 source is *already* gzip-4
      compressed and int16 does not compress as much further. Measured:
      12-lead **152.25 GB -> 83.24 GB** (141.8 GiB -> **77.5 GiB**), lead2
      **12.73 -> 7.42 GB**, whole conversion **164.98 GB -> 90.66 GB (55.0 %,
      74.32 GB saved)**. So the figure to use is **77.5 GiB, not 56.7**, and the
      upload budget rises from ~142 GB to **~163 GB**. **This does not break the
      campaign model:** 77.5 GiB over 8 pieces is ~10 GiB each and two resident
      is ~20 GiB, well under the 45 GB ceiling. **§8.2 amended in place** with a
      dated Round-10-style note; the execution plan's upload table still says
      56.7 and should be corrected when it is next touched.
      Two of §8.2's other numbers were also wrong and are corrected in the same
      note: the "max abs error 1.1e-3 against amplitude 70" does not describe
      this data (the preprocessed signals are z-scored per lead and reach
      **1923**), and the validation belongs to Stage P2.5, not P2.0.
- [x] **Step 6 — Staged uploads to R2. DONE 2026-08-30.** 601 objects,
      **226.4 GiB** in `r2:trimodal-data`. Report:
      `outputs/stage_reports/step6_staging_report.md`. **~195 GB** total, revised
      up again: Step 5's measured int16 ratio plus the chunk cuts, which
      duplicate the training split in piece form.
  - [x] **Job 1 — the three derived datasets.** New `make_subsets.py`.
        The study list is read off the task parquets, as the plan requires, not
        re-derived: the union of the `is_primary` rows of A1/A3/A4/A6 —
        **422,147 studies, train 295,236 / val 42,563 / test 84,348**, which is
        exactly what `TaskDataset(primary_only=True)` asks for.
        `signals_12lead_L3` **43.93 GB** (int16 codes copied, not requantised, so
        Step 5's equivalence proof still covers it), `images_clean_12lead_L3`
        **5.10 GB**, `images_scanlike_test` **20.40 GB** (both layouts, test
        split, which is what campaign 10's configs read). One file per split,
        because campaign 5 trains on train+val and swaps in test to evaluate.
        **A4 is not an L3-only table** — its parquets carry the full clean
        cohort with `is_primary` marking L3, per §4.A.4.2. Building the subset
        from the row set instead of the flag would have produced the entire
        cohort and campaign 5 would not have fitted.
  - [x] **The overlay mechanism, which is what makes a subset readable.** A
        subset container holds its own rows in its own order, so the base
        `modality_manifest.parquet` no longer describes it. Each dataset ships
        `manifest_overlays/<dataset>.parquet` and `modality.py` lets an overlay
        row replace the base row for that (study_id, kind, layout). **No caller
        changed.** A study outside the subset keeps its base row, whose container
        is not staged, so a miss is a loud missing-file error, never silently
        wrong bytes. `make_subsets.py selfcheck` proves a live overlay returns
        **bit-identical** signal arrays and image bytes for 40 studies; the P2.0
        gate is still **26/26** and `modality.py`'s own self-check still 9/9.
  - [x] **Job 2 — cut the chunks. 24/24 pieces, all verified.**
        `chunks/signals_12lead` 8×6.8 GB (50.94 GB), `chunks/images_clean_12lead`
        8 tars (5.82 GB), `chunks/signals_raw` 8×3.65 GB (27.20 GB).
        **`raw_12lead` ships float32, NOT int16**: 8 of 512 sampled raw records
        carry non-finite samples, which `--int16` would have cast to plausible
        integers with nothing on the model path to catch it. `make_chunks` now
        refuses a non-finite record under `--int16`. *The non-finite samples
        themselves are still unhandled on the model path — campaign 9's problem,
        recorded in §7.*
        **The cut was single-threaded on a 20-core box** (measured: 98.5 % of one
        core, both volumes on one NVMe). `--only` already selected pieces; what
        blocked parallel workers was shared state — `assignment.parquet` and
        `fairness.json` rewritten on every run, and `checksums.json` read once
        and written back whole, dropping any sibling's entry. Both fixed; four
        workers then cut pieces 4–7 in **1h45m instead of 4h32m**.
        Three cuts, TRAIN split, 8 pieces, `--int16` for `preprocessed_12lead`,
        running into
        `TRIMODAL_CHUNK_ROOT` on C: (D: has 84 GB free and the cuts are ~84 GB).
        **Two bugs fixed first:** `cut_image_piece` called a
        `modality.read_modality_bytes()` that does not exist (`read_modality`
        already returns encoded bytes for an image kind), and `--int16` now
        exports `TRIMODAL_SIGNAL_INT16=1` so a signal cut reads the int16 copies
        — half the I/O, and for `preprocessed_12lead` the codes survive exactly.
  - [x] **Job 3 — the uploader.** New `upload_data.py`: hard-link staging tree +
        `rclone copy --checksum` (resumable), sha256 cache, `--dry-run` sizes per
        campaign, `checksums_<dataset>.json` per uploaded directory in the format
        the stager's verifier expects, and the three chunk name mappings
        (`preprocessed_12lead → chunks/signals_12lead`, `image_clean_12lead →
        chunks/images_clean_12lead`, `raw_12lead → chunks/signals_raw`).
        **The layout was verified by round trip, not by reading**: campaign 1 was
        uploaded and pulled back with the real `stage_data.sh` — 49 files
        checksum-verified, `code → scripts/`, `configs → config/`, data at its
        manifest paths under `data/processed/`.
  - [x] **The read-path check the plan called the most likely thing to be
        quietly wrong — it WAS wrong, twice, and both are fixed.** `fetch()`
        named its destination after the object, so a chunk piece landed at
        `piece_000.h5/piece_000.h5` and every plain dataset went one directory
        too deep; and a dataset's objects must carry their paths **relative to
        `data/processed`** (the int16 Lead-II copy has to land at
        `signals_int16/lead2_preprocessed.h5`), with `code`/`configs` routed to
        `PROJECT_ROOT` instead. On int16 specifically: `lead2_raw.h5` has no
        int16 copy, `_resolve_h5` falls back to the float32 original when the
        int16 file is absent, and both files are uploaded at exactly the two
        paths the manifest names — so campaign 4 resolves both encodings.
  - [x] **Job 4 — upload, in campaign order. COMPLETE.** 601 objects,
        226.4 GiB. Uploads were paced across nights and overlapped with the
        cuts once it was clear the two contend for nothing: the cut is CPU-bound
        on one core, the link runs at 24 MiB/s. Historical detail below.
        **Campaigns 1–4 UPLOADED**
        (1.10 + 8.94 + 17.84 + 13.50 GB; `rclone size` = 41.4 GiB, 524 objects),
        campaign 1 round-trip verified. `images_clean_12lead_L3`,
        `images_scanlike_test` and `chunks/images_clean_12lead` uploading. The
        rest are one command each: `upload_data.py --campaign N`.
        **A chunked dataset is only uploaded when its cut is complete** — a
        `checksums.json` listing 1 of 8 pieces would let a stager pull piece 1
        and fail on piece 2.
        Privacy checked before the first push: raw MIMIC, the EHR cache, the
        linkage tables, `structured_features.parquet` and anything
        credential-shaped are refused **by path pattern**, every task parquet's
        schema is scanned for binary columns (101 files, all clean), the bucket
        stays private, and no `rclone lsd r2:` is ever issued.

### Part 2 — First DGX session (~1 hour)

- [x] **Step 7 — Environment survey. DONE 2026-08-30.** Findings and the five
      launcher fixes they forced are in §3 (MU DGX) and session 11 below.
  - [x] **Question 4 — ANSWERED 2026-08-30: ONLINE.** A `cpu_student` compute
        node (dgxa) reached `https://downloads.rclone.org/` with **HTTP 200**,
        so the chunked campaigns can fetch piece k+1 mid-epoch, which is what
        §8.2 rule 2's cycling does. **15a's design is validated in principle;
        the mid-epoch fetch itself still has to run once against R2.**
        Original wording:
        `rclone lsd r2:trimodal-data && echo ONLINE || echo OFFLINE`.
        ONLINE means the chunked campaigns (6, 8, 9) can fetch piece k+1
        mid-epoch, which is what §8.2 rule 2's cycling does. OFFLINE means they
        cannot, and the piece set has to be on the node before the run starts —
        `export TRIMODAL_SOURCE=/path/to/staged/data` (mounted drive or campus
        share); `_campaign_body.sh` already warns when it sees
        `transport() = rclone-offline`. Nothing else in the design changes.
- [ ] **Step 8 — Set up rclone + folders, run a 5-minute Slurm smoke job.**
      IN PROGRESS 2026-08-30.
  - [x] rclone v1.75.0 installed at `~/se23ucse027/bin/rclone`, on PATH via
        `.bashrc`. Two remotes, least privilege: **`r2`** = `dgx-read-data`
        (read-only on `trimodal-data`, verified: a write is correctly denied) and
        **`r2-results`** = `dgx-write-results`, with `no_check_bucket = true`.
  - [x] `rclone lsd r2:trimodal-data` lists all **17** directories from the DGX,
        and a 43-byte round trip to `r2-results` succeeded and was deleted.
  - [x] Folder layout built: everything under `~/se23ucse027/` (see §3).
  - [x] `stage_data.sh 1 --dry-run` on dgxa resolves
        `DATA_ROOT=/dgxa_home/se23ucse027/se23ucse027/data/processed`,
        `quota OK: 0.08 GB used + 1.1 GB` — the nested-root accounting fix
        confirmed on the real machine.
  - [ ] **NEXT: `stage_data.sh 1` for real** (1.1 GB, six datasets, every file
        checksum-verified on arrival).
  - [ ] **Then the venv.** No `module`, no conda, no container runtime, so it is
        plain `python3 -m venv` against **Python 3.10.12** (the laptop is 3.11).
        `python3 -m venv` works — verified. Torch build must match the driver on
        dgxa; check `nvidia-smi` there before choosing the CUDA wheel.
  - [ ] Then the 5-minute Slurm smoke job.

### Part 3 — Full-scale build + audits, **on the laptop** (~2 days of compute)


Amended 2026-08-26 (Round 6.12). This was Campaign 0 on `cpu_student`. Step
numbers are kept so the plan and this ledger stay aligned, but Steps 9 and 11
now happen inside Steps 2 and 3 rather than after Step 8.

- [x] **Step 9 — Run the 12 task builders + fiducial extraction at full scale,
      locally** (folded into Step 2) — DONE 2026-08-27
- [x] **Step 10 — Run the three audits (leakage / cohort / split)** —
      **DONE 2026-08-27, all three PASS, 347 checks, 0 violations.** Report:
      `outputs/stage_reports/stage_P2.3_report.md`. Every number is measured off
      the task parquets, so an audit can contradict a builder's own state file.
  - [x] `_dataset_lib/audit_common.py` — the report writer plus
        `report_verdict()`, the single parser of the `**VERDICT:**` line that
        `30_train.py` now imports (§4 decision 20, trap 20)
  - [x] `20_audit_tasks_leakage.py` — **PASS, 88 checks.** Six gates: the §9.4
        column inventory (every column of all 12 tasks classified; a forbidden
        reference outside §4's declared provenance, or an unclassified column,
        blocks); all 94 model configs resolved to modality kinds and pushed
        through `check_input_policy`; a real `TaskDataset` built for each of the
        30 (task, arch-tier family) pairs with its tensor keys checked against
        the allowlist; B5 proven to be fed exactly one report per row; A5's
        masked-attribute head proven text-independent **by forward pass**
        (change `text_vec`, the three attribute heads stay bit-identical while
        `y_match` moves); and a source-tree scan showing no module on the model
        path reads `structured_features.parquet` or a machine measurement
  - [x] `21_audit_tasks_cohort.py` — **PASS, 184 checks.** n_ECG, n_subjects,
        per-class counts and prevalence, missingness, linkage-tier and SQI-tier
        breakdowns, cart_id top-5 — plus the assertions: every head has ≥2 label
        values in every split (or its AUPRC is NaN), a masked head has a label
        wherever its mask is True, the primary cohort obeys its §4 rule, and a
        §12-locked cohort size still measures the same (A2 275,088; B5 128,653)
  - [x] `22_audit_tasks_split.py` — **PASS, 75 checks.** Zero subject overlap
        (§9.4's requirement) plus the four things it does not cover: the split
        column matches the file it is stored in; every subject's split equals
        the frozen `splits_subject_level.parquet`; no study crosses a split; and
        **donor containment** — every A5/B4 `signal_id`/`image_id`/`text_id`
        resolves to a subject in the row's own split, and a swapped modality on
        a negative comes from a different subject than the anchor
- [x] **Step 11 — Algorithmic baselines, locally** (folded into Step 3).
      **DONE at full scale 2026-08-27 (session 6).** `_model_lib/
      algorithmic_baselines.py` + `50_run_baselines_algorithmic.py` cover all
      eight doc-mandated tasks — A1 (logistic regression on machine
      measurements), A2/B1/B2 (NeuroKit2 detector → HR/QRS/QTc bins), A4 and B3
      (oracles), A6 (Cox PH on age + sex + machine HR/QRS/QTc, `lifelines`
      0.30.3), B5 (detector vs report-claim inconsistency). Two baseline-only
      exemptions are used and declared: A1 and A6 read machine measurements,
      which are forbidden as MODEL input (§5.1 permits them here).
      **Full test-split results, 8/8 `status = ok`, `missing_mandated = []`:**
      A1 75,187 · A2 55,181 · A4 55,140 · A6 84,348 · B1 149,546 · B2 301,097 ·
      B3 598,568 · B5 25,870 rows. **§9.5 oracle gate PASS, exactly:** A4's
      three F1s all `1.000000` (precision = recall = 1.000000, mean |offset|
      0.0000 ms), B3 `mIoU = 1.000000` with 598,568/598,568 rows bin-for-bin
      exact and all four queries individually 1.000000.
      Resumability was exercised for real: the run was killed one minute into
      B2 and the identical command replayed B5/A2/B1 from their part parquets in
      six seconds before continuing. Wall clock ≈ 2 h 45 m at 15 workers.
- [x] **Step 10R — Round 10 rebuild + re-audit. DONE 2026-08-28.**
      All four tables rebuilt at full scale and all three audits PASS:
      **leakage 88/88, cohort 199/199, split 79/79 — 366 checks, 0 violations.**
      Reports regenerated: `stage_P2.1/P2.2/P2.3/P2.4_report.md`.
      Far faster than budgeted — A5 53.6 s, B4 29.7 s, B6 5.7 s, A6 31.2 s, not
      the estimated few hours, because the verification rows are built from
      cached part files rather than re-derived.
      **What the rebuild produced, measured not assumed:**
      - **A5/B4 row equality PASS at 5,693,989 rows** (up from 5,243,784); the
        B4 builder asserts it and refuses to finish otherwise.
      - **Levels 2–5 are strictly test-only.** Train and val carry only the
        original five negative types; test adds `HARD_NEGATIVE_L2` 149,549,
        `L3` 149,036, `L4` 138,581, `L5` 13,039. Train/val row counts are
        unchanged, so no model needs retraining to produce the §6.7 curve.
      - **All six B6 levels have test rows** — 598,568 / 149,642 / 149,549 /
        149,036 / 138,581 / 13,039 — and the builder reports
        `levels_2_to_5_are_test_only: true`. The old empty "hard" tier is closed.
      - **A6 carries the fifteen pre-ECG covariates**, including `age_at_ecg`,
        which replaced `anchor_age` in the Cox feature list.
      **Three stale expectations had to be fixed — Round 10 changed the data but
      left two files behind. None was a data defect:**
      1. `task_definitions.yaml` still declared B6's tiers as `easy/medium/hard`
         with `hard` RESERVED and empty. Replaced with the six Level 0–5 tiers,
         each carrying its `neg_types` and the splits it may appear in.
      2. `21_audit_tasks_cohort.py`'s `rows_per_anchor` hard-coded
         `anchors x 7` across all three splits — a uniformity the ladder
         deliberately breaks. Replaced with a **stricter** split-aware pair: the
         base rows are exactly 7 per anchor *in every split*, and the ladder rows
         are asserted to be test-only. Check count rose 184 → 199.
      3. `22_audit_tasks_split.py` failed 138,581 rows on
         `negative_donor_is_another_subject[text_id]` — exactly the L4 count.
         Level 4 is *defined* as a different study from the **same** subject, so
         the rule was right for every rung but the new one. It now exempts L4 and
         replaces the exemption with three tighter assertions: a swapped L4 donor
         must be the same subject, L4 must swap at least one modality (else it is
         a positive wearing a negative label), and every other negative still
         must come from a different subject. L4 keeps the anchor's own signal and
         image and substitutes only the text, so the check is scoped to the
         column actually swapped.
      **Baselines (§5.1) re-run: A3 structured 84,348 rows / 35 heads, the four
      A6 nested rungs 337,392 rows, A6 Cox 84,348 rows, all `status = ok`.**
      - **The nested ladder is monotone on all four heads and prevalence sits at
        exactly AUROC 0.5000**, as §5.8 requires by construction:
        mortality_30d 0.5000 → 0.6716 → 0.6758 → **0.7302**; mortality_90d
        0.5000 → 0.6618 → 0.6699 → **0.7217**; readmission_30d 0.5000 → 0.5568
        → 0.5792 → **0.6321**; readmission_90d 0.5000 → 0.5681 → 0.6034 →
        **0.6574**.
      - **⚠ FINDING FOR THE PAPER — the §5.1 Cox does NOT beat rung 4.** The Cox
        on `age + sex + machine HR/QRS/QTc` scores 0.7156 / 0.7061 / 0.5340 /
        0.5291, *below* the +utilization rung on every head and dramatically so
        for readmission (−0.098, −0.128). It is not a fifth rung — it is a
        different, smaller feature set that omits comorbidities and utilisation,
        so the ladder is rungs 1–4 and the Cox is a sibling. **Consequence:**
        §1.1's "ECG adds prognostic signal beyond demographics" claim cannot be
        carried by machine measurements; it must be carried by the trained
        neural models, benchmarked against rung 4 at 0.730 — a materially harder
        bar than the 0.5 prevalence baseline. Plan §7 names "only compared to
        random/prevalence baseline" as a failure condition, and this ladder is
        exactly what avoids it.
- [ ] ~~**Step 10R — Round 10 rebuild + re-audit (THE CURRENT BLOCKER).**~~
      Closing the six Plan A/B compliance gaps changed four task schemas, so the
      affected tables and every audit that reads them must be regenerated at
      full scale. Laptop only, no GPU. Run **after** Step 5's int16 job
      finishes — both are CPU-heavy and would fight each other on 14 cores.

      Order matters (B6 reads B4; the audits read everything):

      1. `05_build_A5_cross_modal_verification.py --force` — gains the §6.7
         level 2–5 test negatives and the `text_override` column
      2. `10_build_B4_cross_modal_verification.py --force` — same rows; the
         builder asserts A5/B4 equality and refuses to finish if they disagree
      3. `12_build_B6_difficulty_stratified.py --force` — six tiers; it now
         **fails if any of the six levels has no test rows**
      4. `06_build_A6_risk_stratification.py --force` — gains the fifteen
         pre-ECG §5.8 covariates
      5. `20_audit_tasks_leakage.py`, `21_audit_tasks_cohort.py`,
         `22_audit_tasks_split.py` — all three must be PASS before anything trains
      6. `50_run_baselines_algorithmic.py --tasks A3_lab_abnormality
         A6_nested_baselines A6_risk_stratification` — the new A3 structured
         baseline, the four new A6 rungs, and the A6 Cox (its feature list
         changed from `anchor_age` to `age_at_ecg`)

      Expect a few hours. A5/B4 are ~5.8 M rows each; the rest are minutes.
      Every one of these scripts is resumable and `--force` is idempotent.
      **Do not re-run steps 1–4 of Stage P2.1/P2.2 for the other eight tasks** —
      their schemas did not change.
- [x] **Step 12 — Review the cohort report. SIGNED OFF 2026-08-28 by the
      project owner.** `outputs/audit_reports/cohort_audit.md` (PASS, 184 checks,
      0 violations) was read head by head. **Step 6's first upload is released.**
      Both §12-locked cohort sizes still measure correctly (A2 primary 275,088;
      B5 128,653 — 21 below the originally locked 128,674, which is decision 17).
      Split balance is tight: the largest train-vs-test prevalence gap across all
      64 heads is 0.0121. A5/B4 `y_match` positives are 28.57 % = 2/7 exactly, and
      B5 `is_corrupted` is 50.40 %, both matching their constructions.
      **Four disclosure items were accepted, none a build defect** — they belong
      in the paper's limitations, not in a rebuild:
      1. **A3's rare classes** — 45 test slices fall under §6.7's 100-positive
         threshold and 36 are empty, all in A3. They are clinically correct
         absences, not under-sampling: `abnormal_unknown_direction` is a MIMIC
         reference-range artifact (0-1 rows), troponin `low_abnormal` does not
         exist as a clinical entity, and lactate `low_abnormal` is 10-28 rows.
         State them as structurally absent.
      2. **QTc `short` is thin in VAL, where thresholds are selected** — test is
         fine (A2 104, B1 131, B2 536, all >= 100) but val is 41 / 51 / 51. This
         is the one place a §6.7 fallback touches threshold *selection* rather
         than only the CI.
      3. **The high-SQI tier is ~0.7 % of every cohort** (3,606-16,664 rows; about
         700 test rows for the A-series). The low-vs-medium contrast has power;
         low-vs-high does not. Do not headline a high-SQI number.
      4. **A5, B4 and B6 carry no `sqi_tier` / `link_tier` / `cart_id` columns**,
         but `eval_configs/default.yaml` lists them as subgroup keys — so §7's
         subgroup breakdown comes back EMPTY for the three largest tasks. B6
         substitutes `difficulty_tier`. If SQI-stratified verification numbers
         are wanted in the paper, that needs a schema change, not a re-run.
      A4's 36.7 % and A2's 55.0 % "primary kept" figures are not shrinkage — both
      apply the same §4 decision-10 primary rule and their primary counts are
      nearly identical (192,082 vs 192,087 train); A4 simply has a wider
      denominator because it needs no EHR linkage.

### Part 4 — Campaigns 1–4 (~1 week)

- [ ] **Step 13 — Text models** (21 runs) · [ ] **Step 14 — 12-lead pictures** (21)
- [ ] **Step 15 — Lead-II pictures** (21) · [ ] **Step 16 — Lead-II signals** (33)

### Part 5 — Campaigns 5–6 (~1 week)

- [ ] **Step 17 — 12-lead signals, L3 tasks** (12, fits resident)
- [ ] **Step 18 — 12-lead signals, full cohort** (18, chunked)

### Part 6 — Campaigns 7–8 and 12–13, the heart of the paper (~1.5 weeks)

Round 10.5 added the trained no-text tier here. **SPLIT BY LEAD SUBSET
2026-08-29 (open question 14)**: a fusion campaign reads a whole lead set, and
holding both put campaign 7 at 69 GB against a 45 GB ceiling. 7 and 8 are now
the 12-lead halves, 12 and 13 the Lead-II ones. Project total is unchanged —
**104 configs, 312 runs**; `campaign_runs.py --table` is the authority.

- [ ] **Step 19 — End-to-end fusion, L3 tasks A1/A3/A6**
      — campaign 7 (12-lead, 18 runs) + campaign 12 (Lead-II, 18 runs)
- [ ] **Step 20 — End-to-end fusion, full cohort A5/B4/B5/B6**
      — campaign 8 (12-lead, 15 runs, chunked) + campaign 13 (Lead-II, 15 runs)
- [ ] **Step 21 — Frozen-fusion ablation** (near-free by-product)

### Part 7 — Campaigns 9–11 and 14 (~1.5 weeks)

- [ ] **Step 22 — Re-training sweeps** · [ ] **Step 23 — Re-testing sweeps**
- [ ] **Step 24 — Final eval + calibration/threshold/reproducibility audits**
      — campaign 11 (12-lead, 6 runs) + campaign 14 (Lead-II, 6 runs)
- [ ] **Step 25 — Tables + figures** · [ ] **Step 26 — Release package**

### Audits that must all be PASS before submission (spec §1.2)

- [ ] `leakage_audit_phase2.md` · [ ] `split_audit_phase2.md` · [ ] `cohort_audit.md`
      — all three were PASS 2026-08-27 (88 / 75 / 184 checks) and were
      **invalidated by the Round 10 rebuild**. Re-run them in Step 10R; a stale
      PASS is worse than no PASS, which is why the leakage report is left
      reading FAIL rather than reverted to its last green copy.
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
16. **The rendered images are NOT the aspect ratios §5.3 assumes, and the
   spec's centre crop would throw away a third of every strip.** Measured:
   Lead-II clean is 3600×750 (4.8:1) and scan-like 1600×333 (4.8:1); both
   12-lead kinds are 1016×504 (2.02:1). §5.3's targets (224×672 = 3:1,
   384×512 = 1.33:1) were chosen believing the renders matched. `Resize(short
   side) → CenterCrop(target)` therefore keeps only 672 of 1075 px of a
   short-side-resized Lead-II strip — the middle ~6 s of a 10 s ECG — and only
   512 of 774 px of the 12-lead grid, cutting the outer lead columns. **Never
   restore the centre crop.** `build_image_transform` resizes the full render
   into the target box; §4 decision 18.

17. **A5's masked-attribute head must not see the fused embedding.**
   `task_input_policy.yaml` says the unmasked `report_text` must never reach
   that head, and on an A5 *positive* row the text IS the unmasked anchor
   report. The head therefore reads `cat(signal_emb, image_emb)` only, while the
   encoders stay shared with the verification head (§5.6). A future refactor
   that "simplifies" it onto the shared fusion vector reintroduces the leak.
   The same rule makes an A5 text-only tier verification-only: with no signal
   and no image the head is undefined, and `TaskModel.active_head_names` drops
   it rather than fabricating one.

18. **`torch.__version__` is a `TorchVersion`, not a `str`, and
   `yaml.safe_dump` refuses it.** It killed the first `train_config.yaml` write.
   `seed.environment_fingerprint()` now coerces every value with `str()`. Any
   new field added to a YAML snapshot needs the same treatment.

20. **The audit gate reads a verdict LINE; do not go back to scanning the body
   for `FAIL`.** `30_train.py::check_audit_gate` originally blocked whenever the
   substring appeared anywhere in an audit report. The leakage audit's whole job
   is to list every column of every task, and A1's heads are named
   `label_heart_failure_narrow` / `label_ventricular_arrhythmia_or_arrest` — so
   a clean, 88-check, zero-violation report was read as a violation and blocked
   all training. The parser is now
   `_dataset_lib/audit_common.report_verdict()`, matching
   `**VERDICT: PASS|FAIL**` on its own line, and it is the ONLY reader: the
   audits parse their own rendered report with it before writing, and
   `30_train.py` imports it. A second copy of that logic anywhere is how the two
   drift apart. §4 decision 20.

21. **A5's HR/QRS/QTc labels are not in `A5_.../{train,val,test}.parquet`.**
   They live in `masked_attribute_<split>.parquet` and reach a row through
   `task_dataset.join_masked_attributes()`, which also computes
   `masked_attr_valid` — True only where the signal AND the image are still the
   anchor's own. Anything that reads the verification parquet alone (an audit, a
   table script, a figure) will conclude that three of A5's four heads have no
   label column. Call the join function; do not re-implement it. Note that
   `PARTIAL_MISMATCH` swaps the image as well as the text (§4.A.5.3: "replace
   two modalities"), so those rows are correctly `masked_attr_valid = False` and
   the head is scored on 4 of the 7 rows per anchor, not 5.

19. **A checkpoint loaded with `map_location="cuda"` brings its RNG tensors back
   on the GPU, and `torch.set_rng_state` demands a CPU `ByteTensor`.** Resume
   raised `TypeError: RNG state must be a torch.ByteTensor` until
   `seed._byte_tensor()` moved them back. Caught by the resume smoke test, which
   is the only reason it was not discovered on the DGX after a preemption.


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

### Session 4 — 2026-08-27

- **Step 3 is done, and Step 11's code with it.** Twenty new modules plus the
  two entry points `30_train.py` and `31_eval.py`, the baseline runner
  `50_run_baselines_algorithmic.py`, 94 generated model configs and the five
  eval configs. Report: `outputs/stage_reports/stage_P2.4_report.md`.
- **Every module carries a runnable self-check**, and each one passes:
  `bootstrap` (patient-level CI >1.5× the ECG-level width on correlated data,
  and `n_positive < 100` falls back to percentile), `task_spec` (12 tasks /
  64 heads, cross-checked against both config files), `corruption` (the five
  additive families realise their requested SNR to <0.5 dB, the train stream
  cannot collide with the frozen test stream), `task_dataset`,
  `signal_encoders` (the trap-10 transposed-input guard fires),
  `image_encoders`, `text_encoders`, `fusion_heads`, `task_models` (all 11
  trainable tasks forward + backward with a finite loss), `metrics` (a 6-sample
  = 12 ms shift correctly scores F1 = 0, double-firing is charged as false
  positives), `threshold` (selection on test and application of a test-selected
  threshold both raise), `calibration` (a squashed input goes ECE 0.2587 → Platt
  0.0234; an already-calibrated one is left as `identity`),
  `algorithmic_baselines`, `model_configs`, `trainer`.
- **The three non-optional requirements were built as tests, not claims.**
  1. *Checkpoint-and-resume.* `checkpoint_last.pt` is written atomically every
     N minutes and at every epoch boundary and carries `batch_in_epoch` beside
     the RNG states; the epoch's batch order is a pure function of
     `(seed, epoch)`. The smoke test interrupts after 2 of 3 batches and the
     resumed run does **exactly the remaining 1**; an epoch-boundary resume
     restores weights, optimizer moments, scheduler, RNG and best-metric; the
     SIGTERM handler raises a flag and lets the loop write, so no checkpoint is
     ever produced from inside a signal handler. Interrupted runs exit 0 so
     Slurm requeues.
  2. *Smoke-test everything first.* 34 (task, arch tier) combinations — every
     tier each task's input policy allows — give 34 trains + 34 evals, and all
     68 pass on `dev_sample/` with tiny batches. With the five recovery and
     gate checks that is **73 PASS, 0 FAIL**. No number in this session is a
     paper number.
  3. *Thresholds val-only, bootstrap patient-level.* `select_threshold` refuses
     any split but `val`; `apply_threshold` refuses a record not stamped `val`;
     `patient_bootstrap` refuses a frame with no `subject_id`. All three are
     asserted in the smoke test's gate check.
- **`30_train.py` now enforces the §4.C audit gate.** A full-scale run halts
  until `leakage_audit_phase2.md`, `split_audit_phase2.md` and
  `cohort_audit.md` exist and are PASS. `--dev` bypasses it with a logged
  warning and writes under `outputs/model_runs/_dev/`.
- **Algorithmic baselines (Step 11) are written and proven on the dev sample.**
  All eight doc-mandated tasks produce prediction parquets in the §7.1 schema,
  so `31_eval.py` scores a rule baseline and a ResNet with identical code. Both
  oracles hit their §9.5 target exactly: **A4 `r_peak_F1 = 1.0000`, B3
  `mIoU = 1.0000`**. The full test-split pass is queued behind Step 10.
- **Four things the data or the platform forced:**
  1. **§4 decision 18** — the §5.3 centre crop would discard 37 % of every
     Lead-II strip, because the renders are 4.8:1 and 2.02:1, not the 3:1 and
     1.33:1 §5.3 assumes. The whole render is resized into the locked target
     box instead. Traps 16.
  2. A5's masked-attribute head reads signal + image only; the fused embedding
     would hand it back the unmasked report on positive rows. A5 text-only
     therefore trains verification alone. Trap 17.
  3. `torch.__version__` is not a `str` and broke the first `train_config.yaml`
     write. Trap 18.
  4. A checkpoint loaded onto CUDA returns GPU RNG tensors, which
     `set_rng_state` rejects — a bug that would have surfaced only after a real
     Slurm preemption. Trap 19.
- **BCa acceleration above 2,000 subjects uses a delete-one-group jackknife**
  (200 groups); the bias correction z0 stays exact and every results row records
  `n_jackknife_groups`. An exact jackknife over 30,844 test subjects is roughly
  an hour per head per metric.
- Dependencies added to `ecg_env`: `transformers` 4.57.6 and `lifelines` 0.30.3
  (the A6 Cox baseline). Bio-ClinicalBERT revision
  `d5892b39a4adaed74b92212a44081509db72f87b` recorded in `decision_phase2.yaml`
  for the release package. **P2.0 gate re-run after the config edits: 26/26.**
- **Next:** Step 10 / Stage P2.3 — the leakage, cohort and split audits
  (`20_audit_tasks_leakage.py`, `21_audit_tasks_cohort.py`,
  `22_audit_tasks_split.py`). They now gate three things, not one: the first
  upload, the full-scale algorithmic-baseline pass, and every `30_train.py` run.
  After that, Step 4 (chunk-cutter + campaign launchers).


### Session 5 — 2026-08-27

- **Step 10 / Stage P2.3 is DONE. All three audits PASS: 347 checks, zero
  violations.** Report: `outputs/stage_reports/stage_P2.3_report.md`. The
  §4.C invariant-4 gate is open — `30_train.py::check_audit_gate` was run
  against the three files on disk and returns PASS for each, so a full-scale
  training run, the full-scale algorithmic-baseline pass and the first upload
  are all unblocked.
- **`20_audit_tasks_leakage.py` — PASS, 88 checks.** §9.4 asks for a column
  inventory cross-checked against `task_input_policy.yaml`. That alone would
  have been wrong in both directions, so the audit runs six gates:
  1. the column inventory — every column of all 12 tasks classified, with an
     **unclassified** column counting as a violation;
  2. all 94 model configs resolved to modality kinds and pushed through the same
     `check_input_policy` a run calls;
  3. a real `TaskDataset` constructed on the **test** split for each of the 30
     (task, arch-tier family) pairs, and its tensor keys checked against an
     allowlist — this is what proves the provenance columns are unreachable;
  4. B5 fed exactly one report per row, measured on the whole test split
     (13,039 corrupted rows show `corrupted_report_text`, 12,831 clean rows show
     `original_report_text`, and the resolver drops both source columns);
  5. A5's masked-attribute head proven **text-independent by forward pass** —
     change `text_vec`, the three attribute heads stay bit-identical while
     `y_match` moves (the control that proves the change reached the model);
  6. a source-tree scan: no module on the model path reads
     `structured_features.parquet` or a machine measurement. The single reader
     is `algorithmic_baselines.py`, under the A1/A6 exemptions the policy file
     declares.
- **`21_audit_tasks_cohort.py` — PASS, 184 checks.** Every §9.4 description
  (n_ECG, n_subjects, per-class counts and prevalence, missingness, linkage and
  SQI tiers, cart_id top-5) plus the assertions that decide the verdict: ≥2
  label values per head per split, a label wherever a mask is True, the §4
  primary-cohort rule per task, and the §12-locked sizes still measuring the
  same (**A2 275,088**, **B5 128,653**, A5 rows == B4 rows, B2's 8x5 grid
  complete with 1,871 frozen anchors, B3 4 queries per study, A5/B4 7 rows per
  anchor).
- **`22_audit_tasks_split.py` — PASS, 75 checks.** Zero subject overlap in every
  task, and the four things that requirement does not cover on its own: the
  split column matching its file, agreement with the frozen
  `splits_subject_level.parquet` (§4.C invariant 1 — a task can partition its
  own rows perfectly and still have re-derived them), no study crossing a split,
  and **donor containment** — all 5,243,784 A5 rows and all 5,243,784 B4 rows
  have every `signal_id`/`image_id`/`text_id` resolving to a subject in the
  row's own split, and no negative takes its swapped modality from the anchor's
  own subject.
- **One real defect found and fixed, in the gate rather than in an audit.**
  `30_train.py` blocked on the substring `FAIL` appearing anywhere in a report;
  the leakage audit lists every column of every task and A1's heads are named
  `label_heart_failure_narrow`, so a clean report read as blocked. The verdict
  is now a parsed line (`audit_common.report_verdict`), with one parser shared
  by the audits and the trainer. §4 decisions 19–20, traps 20–21.
- **No builder needed a fix.** Every task cohort, split and column set is as
  Stages P2.1/P2.2 left it; the only source changes outside the new audit
  scripts are the gate parser, `task_dataset.join_masked_attributes` lifted to
  module level so the cohort audit joins A5's labels through the same function
  the loader uses, and the P2.3 entry in `stage_report.py`.
- Regression-checked after those edits: `task_dataset`, `task_spec` and
  `audit_common` self-checks PASS, and a `--dev` A5 multimodal run trained,
  passed both gates, selected val-only thresholds and wrote
  `val_predictions.parquet` with the masked-attribute heads correctly masked on
  `IMAGE_SWAP` rows.
- **Next:** Step 11's full-scale algorithmic-baseline pass (resumable, hours of
  NeuroKit2 over the test split) and Step 4 (chunk-cutter + campaign launchers),
  then Step 5 and the Step 6 uploads. Re-run all three audits after any task
  rebuild — a stale PASS is worse than no PASS.


### Session 6 — 2026-08-27

- **Step 11 is DONE at full scale. 8/8 §5.1 baselines, `missing_mandated = []`.**
  Report: `outputs/stage_reports/stage_P2.4_report.md`. Row counts: A1 75,187 ·
  A2 55,181 · A4 55,140 · A6 84,348 · B1 149,546 · B2 301,097 · B3 598,568 ·
  B5 25,870. Wall clock ≈ 2 h 45 m at 15 workers, ~530 K NeuroKit2 detections.
- **The §9.5 oracle gate passed exactly, which was the check that could have
  failed.** A4 `r_peak_f1` = `qrs_onset_f1` = `qrs_offset_f1` = **1.000000**
  over 55,140 rows, precision = recall = 1.000000, mean |offset| 0.0000 ms, zero
  empty predictions. B3 **`mIoU` = 1.000000** over 598,568 rows, every row
  bin-for-bin exact, all four queries individually 1.000000. The baselines read
  the same fiducials the builders wrote; no drift.
- **Resumability was exercised for real, not asserted.** The run was killed one
  minute into B2, before its first 5,000-unit flush. Re-running the identical
  command replayed B5 / A2 / B1 from their part parquets in **six seconds** and
  continued into B2 from zero. Nothing was lost and nothing was recomputed twice.
- **Non-oracle baselines behave the way the physics says they should:**
  - **B2 is the strongest validation in the step.** HR accuracy is strictly
    monotonic in SNR — 0 dB 0.5483 · 5 dB 0.6125 · 10 dB 0.8011 · 20 dB 0.9307 ·
    30 dB 0.9343 — and 30 dB converges back onto the clean reference (0.9353).
    Detector fallback tracks it inversely, 0.374 → 0.002. Family ordering is
    physiologically correct: broadband families destroy QRS detection (powerline
    0.578, EMG 0.583, gaussian 0.599) while low-frequency `baseline_wander` is
    almost harmless (0.936). The 8 × 5 grid is complete, 18,710 rows per family.
  - **A2 / B1 agree with each other and with Phase 1.** A2 hr_label acc 0.9424 /
    macro-AUPRC 0.8482; B1 0.9347 / 0.8575 — two independently built cohorts,
    same detector, same answer, and both land on Phase 1's NeuroKit2 figure of
    94.7 %. B1's HR accuracy by SQI tier orders correctly: high 0.9454 > medium
    0.9443 > low 0.9187.
  - **A6's Cox fits all converged** (4/4 `status = ok`): mortality_30d AUROC
    0.7189, mortality_90d 0.7072, readmission_30d 0.5375, readmission_90d
    0.5343; train concordance 0.6997 / 0.6867 / 0.5515 / 0.5492. The `anchor_age`
    coefficient is **negative** for both readmission heads and positive for both
    mortality heads — the expected competing-risk signature (older patients die
    rather than being readmitted), not a sign error.
  - **A1's logistic baseline** separates rhythm but not infarct, as it must from
    HR/QRS/QTc summary stats alone: AF AUPRC 0.6246 (prevalence 0.2971),
    conduction 0.2123 (0.0702), but AMI 0.1359 (0.1064) — barely above its own
    base rate.
- **Investigated and dismissed: B5's QRS_wide recall of 0.031 is not a bug.**
  B5 overall F1 0.4633 / AUPRC 0.5132, with per-family recall splitting sharply —
  HR_brady 0.9868 and HR_tachy 0.9770 against QRS_wide 0.0307, axis_lad 0.3781,
  axis_rad 0.3189, PR_first_degree_avb 0.1764. Cause: `b5_rule_flag` fires only
  when a report *claims* wide and the detector measures narrow, but B5's
  QRS_wide family corrupts in the opposite direction — it strips the wide claim
  out (`"Right bundle branch block"` → `"Normal QRS duration"`), so the rule
  abstains. **Making the rule symmetric would make it worse:** measured QRS
  ≥ 120 ms occurs on 21.06 % of QRS_wide-corrupted rows against 21.58 % of clean
  rows, so the Lead-II NeuroKit QRS duration carries *no* signal for that family
  and the reverse check would add false positives, not recall. Detector health is
  fine (fallback 0.0092, delineate_ok 0.9796). **Left unchanged**, and recorded
  as a §11 open question. The paper finding: NeuroKit's Lead-II QRS duration does
  not separate RBBB reports from normal ones in this cohort (median 93.1 ms vs
  90.1 ms population) — which is precisely why B5 needs a learned model.
- **A2/B1's weak QRS and QTc heads are recorded biases, not new defects.** A2
  qrs acc 0.5776 (true `wide` → predicted `normal` 5,698 / 8,248) is the same
  Lead-II QRS blindness as above; A2 qtc acc 0.4160, with true `prolonged`
  splitting almost evenly into `normal` (10,610) and `short` (10,963), is
  session 1's logged "machine QTc > NeuroKit QTc" validation showing at scale.
  A2's labels come from machine measurements, so both heads measure
  detector-vs-machine disagreement by construction.
- **`stage_report.py` changed** so the report measures rather than restates: a
  new `_oracle_check_lines()` recomputes A4's three F1s and B3's mIoU directly
  from the prediction parquets instead of reading a dev results CSV; the §9.5
  block reports full-scale first and `dev_sample` second; both summary JSONs are
  rendered. Three stale P2.4 open questions were replaced — the audit gate is
  open now, the baselines are no longer "not yet run at scale", and the B5
  detector-blindness measurement is recorded with its numbers.
- **Deliberately NOT done: the baselines' patient-level bootstrap CIs.** §6.7's
  10,000 BCa replicates re-evaluate the metric on a resampled frame each
  iteration, which on A4's 55 K event-matched rows or B3's 598 K bin rows is a
  campaign-scale job, not a report-generation one. §9.5 asks for the point
  estimate on the test split and that is what was produced; the intervals come
  from `31_eval.py` alongside the trained arms, so a baseline and a ResNet are
  scored by identical code.
- **Next:** Step 4 (chunk-cutter + campaign launchers), Step 5 (int16 + the
  equivalence proof), then Step 6's first upload — which also wants Step 12's
  human sign-off on `cohort_audit.md`.

### Session 7 — 2026-08-28

No narrative entry was written at the time. What it did is recorded in full in
the step ledger: **Step 5** (the int16 copies and the four-arm equivalence
proof), the **Round 10** compliance closure, and **Step 10R** (all four tables
rebuilt, all three audits re-run — 366 checks, 0 violations).

### Session 8 — 2026-08-29 — Step 6, the staged uploads

**Started only after checking the gate rather than trusting it:** Step 10R DONE
(366/366), Step 5's six int16 files present and in `int16_manifest.json`, and
`rclone size r2:trimodal-data` = **0 objects**, so nothing was overwritten.

- **Built the three derived datasets nothing produced** — new `make_subsets.py`.
  Study list read off the task parquets (`is_primary` of A1/A3/A4/A6):
  **422,147 studies**, train 295,236 / val 42,563 / test 84,348.
  `signals_12lead_L3` 43.93 GB, `images_clean_12lead_L3` 5.10 GB,
  `images_scanlike_test` 20.40 GB.
- **Gave `modality.py` manifest overlays** so those subsets are readable with no
  caller changed, and proved it: a 40-study micro-subset with a live overlay
  returns bit-identical arrays and image bytes. P2.0 gate still 26/26.
- **Wrote `upload_data.py`** and proved the layout by round trip — campaign 1
  uploaded, then pulled back with the real `stage_data.sh`: **49 files
  checksum-verified, zero mismatches.**
- **Fixed the read path, which was broken in two ways.** `fetch()` named the
  destination after the object (`piece_000.h5/piece_000.h5`, and every dataset a
  directory too deep); and dataset objects must carry paths relative to
  `data/processed`, with `code`/`configs` routed to `PROJECT_ROOT`. Also
  `checksums_<dataset>.json`, because `text` and `index` share a directory and a
  single name let the second shadow the first.
- **Fixed two bugs in `make_chunks.py`** before the first cut: the image path
  called a `read_modality_bytes()` that does not exist, and `--int16` now reads
  the int16 copies instead of re-quantising the float32 originals.
- **Corrected `campaigns.sh`** — resident sizes measured off disk, dataset lists
  matched to what each campaign's configs actually read, run counts from
  `campaign_runs.py --table` (104 configs, 312 runs).
- **Raised two open questions the step uncovered and did not fix** — §5 #14
  (campaigns 7/8/11 read Lead-II too and no longer fit; split them by lead
  subset) and #15 (nothing reads chunk pieces yet, and pieces are train-only).
- **Left running:** campaigns 2–4 uploading, the L3 subsets and the three chunk
  cuts building. Report: `outputs/stage_reports/step6_staging_report.md`.
- **Next:** finish the uploads, one campaign per night
  (`upload_data.py --campaign N`), then Step 7, the DGX environment survey.

### Session 9 — 2026-08-29 — closing open questions 14 and 15

No bytes were uploaded in this session; the transfers already in flight were
left alone (`upload_data.py` never calls `require_fit`, so none of this touches
them).

**Question 15b was measured before anything was built, and the measurement
deleted the work.** The question was whether val/test need chunking too. Per
study, off the containers: 12-lead int16 **101.6 KiB**, clean 12-lead images
**11.7 KiB**, raw 12-lead float32 **88.5 KiB** — so val is 7.9 / 0.9 / 6.8 GB
and test is 15.6 / 1.8 / 13.6 GB. That fits beside two resident pieces, so
**val and test ship as plain datasets and nothing beyond the training split is
ever chunked** — three new entries in `make_subsets.py`, no new machinery.

**Two defects found while measuring.**
- `raw_12lead` carries **non-finite samples in ~1.6 % of records** (8 of 512
  sampled; the preprocessed copies carry none, the filtering interpolates them
  out). `--int16` would have turned every one into a plausible-looking integer
  with no error, because casting NaN to int16 is undefined. The cutter now
  refuses; raw pieces and `signals_raw_valtest` are float32. **This is a live
  problem beyond chunking** — nothing on the model path sanitises a non-finite
  sample, so campaign 9 would train on them either way.
- `make_subsets.py plan` was overstating 12-lead by 53 % (155.5 KiB/study
  against the true 101.6): it divided a whole shard's size by a partial row
  count, which the L3 overlay made wrong the moment it existed.

**Question 15a is implemented, and honestly not validated.** The read side is
`_dataset_lib/chunk_pieces.py` — a piece already carries `study_id` per row, so
the overlay mechanism covers it and no new reader was needed; `modality.py`
learned that a piece is stored channel-major so it is not transposed twice. The
cycling is `_train_lib/chunk_cycle.py`, **in the training loop, not the
Dataset**, because staging is a transport call. Every piece appears once per
epoch in a reshuffled order, two resident, rows shuffled inside the window, and
the deviation plus the transport are stamped into the run metadata. What is not
validated is a real mid-epoch fetch: that needs outbound internet on the DGX
(question 4), so both the online and the offline path are written against
`transport()` and the campaign body warns when it sees `rclone-offline`.

**Question 14 closed by splitting the campaigns by lead subset**, plus a
train/eval phase split so no campaign holds its test data while it trains.
`campaign_runs.py --table` still reports 104 configs and 312 runs.

**Next:** build the three `*_valtest` datasets, finish the uploads, then Step 7
— and answer question 4 first, because 15a's validation waits on it.

### Session 10 — 2026-08-29/30 — Step 6 finished, and two DGX bugs caught early

The laptop shut down mid-cut. Nothing was lost but one piece: pieces 0–5 of the
12-lead cut survived, `piece_006.h5.tmp` was redone. The system clock came back
12h41m behind, which R2 warns about and tolerates; it resynced itself. Log
timestamps between 03:07 and 15:53 are that jump, not elapsed time.

**An upload had reported success while pushing nothing.** The staging tree is
hard links, and a hard link cannot cross volumes: the containers were on C: and
their overlay parquet on D:, so `images_clean_12lead_valtest` was refused while
the wrapper still echoed UPLOADED. A file that cannot be linked is now copied
instead, up to 2 GiB — above that it still refuses rather than silently
duplicating 30 GB. The dataset was re-pushed and verified in the bucket.

**Everything left was serial for no reason.** The cut is CPU-bound on a single
core (98.5 % of one of 20, both volumes on one NVMe), so the queue was split
into a disk queue and a network queue, and then the raw cut itself into four
`--only` workers. Pieces 4–7 took **1h45m instead of 4h32m**; the two `*_valtest`
builds ran alongside them. Making that safe needed two fixes in `make_chunks.py`
(nested under Step 6, job 2): `assignment.parquet` / `fairness.json` are written
only when absent, and `checksums.json` merges instead of overwriting. The proof
it held: eight entries in one `checksums.json`, written by four processes,
verified 8/8.

**Step 6 is DONE — 601 objects, 226.4 GiB.** Final pieces: `signals_12lead`
50.94 GB, `signals_raw` 27.20 GB, `images_clean_12lead` 5.82 GB;
`signals_12lead_valtest` 21.93 GB, `signals_raw_valtest` 11.84 GB,
`images_clean_12lead_valtest` 2.50 GB.

**The chunked read path was round-tripped for the first time.** Campaign 9's
piece 0 was pulled from R2 with the real `stage_data.sh`, checksum-verified,
junctioned where the loader looks, and read through `install_overlays()`:
all 65,309 rows hash to piece 0, and `read_modality()` returned arrays
**bit-identical** to the base container for five sampled studies. This is what
campaigns 6, 8 and 9 depend on and nothing had exercised it end to end.

**Two bugs that would only have appeared on the DGX, found on the laptop.**
- **`used_gb()` double-counted nested roots.** It summed `du` over
  `PROJECT_ROOT`, `DATA_ROOT` and `RESULTS_ROOT`, and `RESULTS_ROOT` defaults to
  `$PROJECT_ROOT/outputs`. The round-trip made it visible: a 3.63 GB piece was
  reported as **6.78 GB used**. On a node with no scratch, where `DATA_ROOT` is
  `$PROJECT_ROOT/data/processed`, every staged byte counts twice and **campaign
  7's 37.7 GB measures ~75 GB against a 45 GB ceiling — a refusal to stage, on
  the first real campaign.** Nested roots are dropped before `du`; a root
  reached through `_campaign_body.sh`'s symlink is correctly *not* nested,
  because `du` does not follow symlinks and `pwd -P` distinguishes the cases.
  `bash campaigns.sh selfcheck` asserts both directions. A bare `$USER` under
  `set -u` was guarded in the same function.
- **Ten shell scripts had CRLF line endings.** `upload_data.py` ships `scripts/`
  straight from the working tree, and Linux `bash` fails a CRLF script at the
  shebang. `.gitattributes` now pins `*.sh` / `*.sbatch` to `eol=lf`, all ten
  are normalised, and `code` was re-uploaded. The copy already in the bucket was
  LF, so nothing staged before this was broken.

All 14 campaigns still pass `require_fit` in both phases under the corrected
accounting (chunked ones with `--pieces`, which is the by-design refusal without
them).

**Next:** Step 7, the first DGX session. Answer question 4 on a compute node
before anything else — 15a's validation waits on it.

### Session 11 — 2026-08-30 — the DGX account arrived; Step 7 done, Step 8 half

Credentials landed by email and the account works. **Everything below was
measured on the machine, not assumed**, and five launcher bugs came out of it —
each of which would have failed a real submit, most of them silently.

**Connecting.** `ssh se23ucse027@10.59.121.172` from a machine on the MU
network. Storage is 50 GB, account expires 2026-12-31, portal at
`http://10.59.121.175/dgx`. Login node is a PowerEdge R760xs and holds no GPUs.

**The five fixes** (all in §3 and in commits 501d9b7, 430f621, 2ecf0aa,
5ad6515):

1. **`--mem` is mandatory.** These partitions default to the *whole node's*
   memory, 1,031,800 MB, so a job without `--mem` waits for a completely empty
   node — which never happens here — and Slurm blames the nodes:
   *"Nodes required for job are DOWN, DRAINED or reserved"*. A 1-CPU test job
   pended on exactly this. All 14 campaigns now set `--mem=64G`.
2. **`--gres=gpu:1` could have grabbed a 5 GB MIG slice.** The A100s are
   partitioned into `a100`, `a100_4g.20gb`, `a100_3g.20gb`, `a100_2g.10gb` and
   `a100_1g.5gb`; an untyped request matches any of them. Now
   `--gres=gpu:a100:1`. **Only 7 full cards exist campus-wide, and they are
   40 GB, not 80.**
3. **`resolve_data_root()` would have staged outside the quota.** Its candidate
   list ended in `/tmp/$USER` — the one path that IS writable on these nodes.
   Project decision, from the owner: *everything lives inside the 50 GB*. `/tmp`
   is no longer a candidate.
4. **One roll-numbered folder.** The account is shared, so all work lives in
   `~/se23ucse027/` — checkout, data, outputs — via `PROJECT_FOLDER`.
5. **The results push tried to create the bucket.** A bucket-scoped token cannot
   list buckets, so rclone issues `CreateBucket` before the first object and the
   token refuses it with 403. Reproduced with a 43-byte file. **That would have
   surfaced at the end of a multi-day campaign, with the only copy of the results
   on a node whose account expires.** `--s3-no-check-bucket` is now on the push
   path itself, not just in `rclone.conf`.

**One home, one fast node.** `$HOME=/dgxa_home/se23ucse027` on *every* node —
local ext4 on dgxa, NFS on dgxb, and the login node resolves there too. So one
staged copy serves both nodes and `--requeue` resume survives either. But
`dd iflag=direct` measured **dgxa 2.9 GB/s against dgxb 105 MB/s — 28x**. The
loader does tens of thousands of ~100 KB random reads per epoch, so a run on
dgxb starves the GPU for days without failing. **All 14 campaigns are pinned
`--nodelist=dgxa`, which costs GPUs: dgxa has 2 of the 7 full A100s.** The
20 GB MIG slices on dgxa are how to buy concurrency back without leaving the
fast disk — cost them once peak memory per campaign is known.

**The 50 GB is not enforced.** `quota -s` returns `none` on a 14 TB filesystem
with 6.1 TB free. `used_gb()` / `require_fit` is the only thing holding the
line, which is why fix 3 matters more, not less.

**Two least-privilege R2 tokens, both verified from the DGX.** `r2` =
`dgx-read-data`, read-only on `trimodal-data` — a write to it is correctly
denied, so nothing on a shared account can damage the 226 GB. `r2-results` =
`dgx-write-results`, round-tripped a file and deleted it. `laptop-full` stays on
the laptop.

**`code` was re-uploaded twice**, because the first DGX dry run proved the
bucket copy was stale — it still resolved `DATA_ROOT=/tmp/...`. Re-pulled, and
the dry run then gave the right roots and `quota OK: 0.08 GB used + 1.1 GB`.

**Next:** `stage_data.sh 1` for real, then the venv (plain `python3 -m venv`,
**Python 3.10.12**, no conda/module/container — `venv` verified working; pick
the torch CUDA wheel against dgxa's driver), then the 5-minute smoke job.

