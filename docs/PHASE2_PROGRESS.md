# Phase 2 — Live Progress & Handover

**This is the single file that carries state between sessions.** Any agent
starting cold reads this first, works, then updates it before the session ends.
`AGENTS.md` at the repo root enforces that loop.

- **Last updated:** 2026-10-27 (session 20, `campus-laptop`)
- **Last checked:** 2026-10-27 08:40 UTC (session 20, `campus-laptop`)
- **LIVE STATE AFTER SESSION 20 (2026-10-27 ~09:30 UTC; supersedes everything
  below). Both DGX checkouts at `792c652`.**
  - **Campaigns are taken ON AVAILABILITY now, not assigned (user, 10-27).**
    Both accounts' chains walk `CAMPAIGNS="10 4 3 15 5 6 7 9 12 13 8"` and claim
    a campaign in `r2-results:trimodal-results/claims/campaign_<n>` (`<user>
    <running|done> <utc>`) before running it; an account skips what the other
    has claimed and anything that does not fit its own ceiling + 2 GB. Seeded:
    1, 2 done (acct 1); 10 running (acct 1); 4 running (acct 2). **3 and 15 were
    released to the pool** (they had been account 2's; nothing of them ran).
    **11 and 14 are NOT in the list** — submit by hand once every other
    campaign's evals are in and `merge_acct2_results.py --apply` has run.
  - **Both accounts: 50 GB each, no pooling (user, 10-27). Ceiling 49 GiB.**
    `will_fit` now converts the table's decimal GB to GiB (it was overstating
    every campaign 7 %). Every campaign fits both accounts at an empty data
    root (account 1 base 8.6 GiB, account 2 base 3.0); campaign 7 on account 1
    has 0.8 GiB spare, under the 2 GB claim headroom, so account 2 takes it.
  - **Account 1 GPU:** 27480 (campaign 10, 6/15 trained, A6 seed 42 training)
    ends ~20:45 UTC 10-27, then **29172 -> 29173 -> 29174 -> 29175** (new
    script, `afterany`). **CPU:** A5 image eval 28594 (cont. 28596); **A3 image
    eval resubmitted at 16 CPU / 96G as 29167** (cont. 29168), resumed `1107 of
    2940 units already done`, 1833 to go — about 10 days.
  - **Account 2 GPU:** 27475 (campaign 4, 64/78 trained, B3 raw seed 123
    training; left: B3 raw 456, B4 x6, B5 x6) ends ~22:55 UTC 10-27, then
    **29176 -> 29177 -> 29178 -> 29179**.
  - **Campaigns 8/11 (`on_demand`) code is in, never run:** val phase gated on
    the val split only, test not held beside training, `30_train.py` stages
    val/test for the end-of-run predictions, the body restages the first
    window before any chunked run with no piece on disk. **Watch the first run
    of 8** (it is last in the list).
  - **Merge step written:** `scripts/dgx_portability/merge_acct2_results.py`
    (dry run by default). Dry run 10-27: 448 model_runs files to copy, no
    acct2 CSVs yet, only clash `figures/README.md`.
  - **DGX GitHub token WORKS again (10-27):** fine-grained, `rohith0110`'s,
    Tri-modal_ECG only, Contents read-only. Account 1 does `git pull --ff-only
    origin main`; no more bundles. **Before testing a token, copy
    `~/.git-credentials-trimodal` aside** — git's `store` helper empties the
    file on any rejection (it wiped the first attempt, a 94-char paste with a
    stray character; a good token is 93).
- **SESSION 20 CHECK (2026-10-27, first read; details, superseded above):**
  - **🔴 Account 1 cannot push to R2 since ~10-20 20:43 UTC.**
    `campaign_chain.sbatch` never sets `R2_RESULTS`, so chain jobs (27480,
    27481) and every eval they submit (28594, 28595, 28596) push through `r2:`
    — the read-only data token — and fail with "is a file not a directory"
    (trap from `eval_task.sbatch:48`). Nothing is lost: push_results leaves
    local files untouched. **FIXED same session (user approved):** account 1
    now has an `.account_env` with
    `export R2_RESULTS=r2-results:trimodal-results` (campaigns.sh sources it on
    every call, so 27480/28594 pick it up mid-run); `campaign_chain.sbatch`
    defaults to `r2-results:` too (`e9dce96`, bundled to account 1, account 2
    pulled). The backlog was pushed by hand from the login node with
    `push_results.sh --keep-checkpoints` (log `push_backlog_20261027.log`), so
    checkpoints stay until the chain's next push deletes them. 27457 cancelled.
  - **Account 1:** campaign 2 TRAINING DONE (27465 timed out in B4 seed 123;
    27480 resumed it and finished B4 on 10-22). Campaign 2 evals: A1, A6 done
    earlier; **B4 image eval finished locally (CSV 10-25) but 28595 FAILED on
    the push**; A5 image eval 28594 RUNNING 120/240 units (continuation 28596
    `afternotok`). **Campaign 10** started in 27480 on 10-22: A1 and A3
    scanlike x3 seeds trained, A6 seed 42 training. 27480 ends ~10-27 20:45
    UTC, 27481 (`afterany`) continues. **A3 evals: tf-idf DONE (27456, 10-24),
    BERT DONE (27459, 10-26), both pushed.** A3 image 27461 at 190/2025 units
    (~2 units/h, about 38 days left) and it is the last link of that chain.
    27457 is `DependencyNeverSatisfied` (its parent completed) — harmless,
    cancel it. 45 GB used.
  - **Account 2:** healthy, pushing. Campaign 4 on chain link 27475 (27474
    timed out 10-21 and handed over): A2-A6, B1, **B2 incl. both regime_1 tiers
    trained** (known issue (1) closed), B3 preprocessed x3 done, B3 raw seed
    123 training. 27475 ends ~10-27 22:55 UTC; 27476 continues. 18 GB used.
- **TWO DGX ACCOUNTS NOW: `se23ucse027` (`ssh mudgx`) and `se23ucse034`
  (`ssh mudgx2`). Read `docs/DGX_ACCOUNTS.md`.** Every job below is tagged with
  its account. They run as two separate workflows: account 2 has its own
  checkout, a 49 GB ceiling and its own results prefix in R2. Account 1's
  ceiling is 99 GB (user's call; not confirmed with the admins).
- **UNATTENDED RUN, 2026-10-14 to about 10-24: the user is off campus and the
  DGX cannot be reached from outside. Everything below was queued on 10-13
  ~23:30 UTC; both DGX checkouts are at `59e7832`.**
  - **Campaign split: account 1 owns campaigns 2 and 10; account 2 owns 4, 3
    and 15.** Do not run one account's campaign on the other.
  - **Account 1 (`ssh mudgx`, `se23ucse027`), GPU:** campaign 2 job **27465
    RUNNING** (A5 seed 42, cycling on, three piece windows done, ~4.7 h per
    epoch), then chain links **27480 -> 27481** (`campaign_chain.sbatch`,
    `CAMPAIGNS="2 10"`, `afterany`, 7 d each). 27465 times out ~10-20 20:48
    UTC; 27480 resumes campaign 2 from checkpoint. **CPU:** A3 evals 24635
    (tf-idf), 24638 (BERT), 27050 (image) RUNNING, continuations 27456 -> 27457,
    27458 -> 27459, 27460 -> 27461.
  - **Account 2 (`ssh mudgx2`, `se23ucse034`), GPU:** chain links **27474
    RUNNING -> 27475 -> 27476**, `CAMPAIGNS="4 3 15"`. Campaign 4 is on its
    first run at ~4 min per epoch; 78 runs, so roughly a week. Its evals queue
    on account 2's `cpu_student` as the tiers finish. Results go to
    `r2-results:trimodal-results/acct2/` (`docs/DGX_ACCOUNTS.md`).
  - **FIRST THING ON RETURN, per account:** `squeue -u $USER`, then
    `grep -- "--- \|===\|FAILED" trimodal_chain_*.out trimodal_c2_27465.out`
    for which runs trained, were skipped or failed, and `sacct -u $USER -S
    2026-10-13 -X -o JobID,JobName%20,State,Elapsed` for timeouts. If a chain's
    last link has ended and work remains, submit another link (the line is in
    `campaign_chain.sbatch`'s header).
  - **Known going in:** (1) B2 `regime_1` was failing on an empty val split;
    patched in `e39d4a0` to validate on the clean val rows (user's decision) —
    dataset construction checked, **a full regime_1 run has not been seen**.
    (2) Account 1's ceiling is 99 GB and campaign 2 peaks near 52 GB there
    while account 2 uses up to 49 GB of its own; the user accepted going over
    the two allocations for this run. (3) Account 2's results must be merged
    from `acct2/` before campaigns 11 or 14 — not written yet. (4) First
    production use, unobserved when this was written: a chain link switching
    campaigns, the eval de-duplication and self-continuation, chunk cycling
    through a resume on GPU. (5) Campaigns 8 and 11 (`val_mode=on_demand`) are
    NOT ready: their val swap is gated on the full residency and they may start
    a run un-cycled — session 19 log.
- **Earlier in session 19 (superseded by the block above): campaign 2 resubmitted as job 27465**
  (account 1, dgxa, `gpu_student`, `a100_4g.20gb`, 7 d, submitted 2026-10-13
  20:48 UTC, DGX checkout `3e090e7`). It skipped the 9 finished runs and is on
  **A5 seed 42 with chunk cycling ON**; the first piece swap (evict 1, fetch 2)
  worked and batches are moving at ~3 it/s, 49,902 per epoch, **~4.7 h per
  epoch**. Two things nobody has seen yet: **a swap at a window boundary inside
  an epoch** (first one ~22:05 UTC on 10-13) and **the end-of-epoch validation
  with pieces resident**. **NEXT ACTION: check 27465's `.err` for the second
  window and the first `epoch 1/30` line.** 6 runs x at least 6 epochs is more
  than 7 days, so this job will TIMEOUT part-way and must be resubmitted (it
  resumes from checkpoint).
  - 26896 (the 10-09 submission) failed at A5 because cycling never turned on
    for A5/B4; 27463 then failed at the first swap on a staging bug. Both fixed
    (`e3a2538`, `6da9bf8`, `3e090e7`) — session 19 log.
  - **A3 evals, account 1:** 24635 (tf-idf, dgxa), 24638 (BERT, dgxb), 27050
    (image, dgxb) RUNNING; none finishes inside its 7 days, so continuations
    are chained `afternotok`: **27456 -> 27457** (tf-idf), **27458 -> 27459**
    (BERT), **27460 -> 27461** (image). The image eval is ~52 days of work at
    4 CPU — still open whether to rerun it bigger on account 2.
  - **The DGX still cannot `git pull`**: `~/.git-credentials-trimodal` is empty
    (git erased the rejected token). The user is putting in a new fine-grained
    token; until then code moves by `git bundle` (session 17 recipe).
  - A5/B4 image evals 27049/27051 failed for want of predictions; the campaign
    body resubmits them when the runs finish.
- **SESSION 17 (superseded by session 19 above): campaign 2 resubmitted as job 26896** (2026-10-09
  ~08:13 UTC, dgxa, `gpu_student`, `a100_4g.20gb`, `--time=7-00:00:00`, DGX
  checkout `f190193`). The first attempt 25576 died at staging — image pieces
  fetched empty over rclone — fixed in **f190193** (`piece_ext`, a non-empty
  check, and an R2 key check in `campaigns.sh selfcheck`: 6 cuts x 8 pieces
  PASS). Then the quota gate refused (25.68 used + 27.9 > 49) because campaign
  2's own leftovers were counted on top of its residency; **user approved
  `evict_data.sh --all`** -> 9.76 GB used, gate OK. Run order A1, A3, A6 (no
  cycling) then A5, B4 (cycling): **first piece swap ~2-4 days out. NEXT ACTION:
  watch 26896's first A5 swap** (post-mortem §5). **Do not queue campaign 3 or
  anything else until the user has seen it.**
- **SESSION 18 (2026-10-06, `data-laptop`): 186.7 GB deleted from D: — 147.7 GB
  of DGX-prep intermediates and 39.0 GB of dev-sample checkpoints. Nothing in R2
  and nothing of Phase 1 touched.** Gone: the five
  whole int16 12-lead shards (83.2 GB — they exist as the p8 pieces plus
  `signals_12lead_valtest`), the two derived containers no campaign stages
  (`signals_12lead_L3` 44.2 GB, `images_scanlike_test` 20.3 GB, both
  hash-checked against R2 first) with their overlays, both hard-link upload
  staging trees, two dead junctions, and every `checkpoint_*.pt` under
  `outputs/model_runs/_dev`. D: went 14.9 -> **188.8 GiB free**. **The chunk
  pieces on C: stay** — the user's rule is to delete only what will never have
  to be rebuilt.
  `check_r2_complete.py`, `--sizes` and `check_campaign_data.py` print the same
  output before and after; every kind still reads through `read_modality()` in
  every split. **A rebuild of anything int16 12-lead now starts with
  `make_int16.py` (~6 h).** Storage map: §3. Rules for the next cleanup: trap 22.
  - **🔴 The DGX cannot `git pull`: its GitHub token in
    `~/.git-credentials-trimodal` is rejected** ("Invalid username or token").
    Session 17 moved `main` over as a `git bundle` (same commits, fast-forward
    to 71bde63). The user must put a fresh read-only token there before the next
    pull; until then use the bundle recipe in the session 17 log.
  - **Campaign 1 evals: B4 DONE** (24760 tf-idf 09-30, 24761 BERT 10-01;
    `B4_cross_modal_verification.csv` written). **A3 still running** on dgxb as
    continuations 24634 (tf-idf, 1,512/2,940 units) and 24637 (BERT,
    1,071/2,940), last continuations 24635/24638 queued. dgxa NODE_FAILed
    2026-10-04 20:07 and killed the first pair.
- **SESSION 15 (2026-09-30): campaign 1 training is DONE (36/36; `c1_B4` 24622
  COMPLETED 09-29). Campaign 2 pre-flight ran and found a DATA GAP — A5/B4
  image runs cannot train.** R2 holds only `images_scanlike_test`; A5/B4 read
  `image_scanlike_12lead` for train/val rows (`task_dataset.py:524-528`), and
  no campaign stages it. `c2_images12` 24641 is HELD. A3 evals are far slower
  than planned (tf-idf ~34 d, BERT ~70 d left at the current rate). See the
  session 15 log.
- **✅ SESSION 16 (2026-09-30, `data-laptop`): OPEN QUESTION 16 IS CLOSED, END
  TO END. The A5/B4 scan-like gap is fixed, the campaign table was rebuilt from
  MEASURED sizes, and three further latent staging bugs were found and closed.
  The data laptop should not be needed again** — see
  `docs/CAMPUS_LAPTOP_HANDOVER.md`, which is the operating manual for the
  campus laptop and the DGX.
  - **The gap.** A5/B4 fix the image rendering per ROW (`image_type_column`,
    `task_dataset.py:524-528`), so every A5/B4 config that touches images reads
    `image_scanlike_<layout>` too. A subset could not fix it: one scan-like row
    per anchor and every study is an anchor, so train+val is **599,470 of
    749,112 studies** — **50.08 GB** for 12-lead, more than the whole ceiling.
  - **The fix (user's call, 2026-09-30): chunk it.** Scan-like TRAIN is cut at
    **p8 for both layouts**, aligned with the three existing cuts (`plan`
    reports **0 of 523,945** studies disagreeing, and a real round trip proves
    the pieces byte-identical to the base shards). Val/test ship as **per-layout**
    `images_scanlike_<layout>_valtest`, because `images_scanlike_test` holds
    both layouts in one 20.33 GB tar.
  - **Three more bugs of the same shape**, found by deriving each campaign's
    real reads from its configs instead of trusting the table: **campaign 10**
    staged no clean-image container though its A5/B4 runs read one;
    **campaign 11** trains A5/B4, which are not L3 tasks, against the L3
    subsets; and `--all` in `upload_data.py` skipped campaigns 12-14.
  - **The size table is now measured, not maintained.** `upload_data.py
    --sizes` derives every campaign's residency from the files. The old table
    was wrong in both directions — campaign 12 was listed 29.4 and is 33.7,
    campaign 9 was 18.5 and is 12.7, campaign 7 was 37.7 and is 40.5.
  - **Two new mechanisms.** A piece swap now **evicts before it fetches** (it
    held four pieces where the quota is sized for two), and campaigns 8 and 11
    run **`val_mode=on_demand`**: they do not hold the val split while training,
    fetching it at each epoch boundary and dropping it again. That is worth
    15 GB and is what makes them fit.
  - **Chunk cycling is now decided PER RUN**, not per campaign: a run cycles
    only if it reads a kind actually staged as pieces. Campaign 2 stages clean
    12-lead whole and scan-like as pieces, so A5/B4 cycle and A1/A3/A6 do not —
    without this, nine already-planned runs would have silently changed
    sampling regime.
  - **`max_steps_per_epoch` never capped anything** (it was sliced off a
    flattened *copy* of the epoch plan while the loop iterated the original).
    No paper number is affected — no campaign script passes it. But **session
    15's pre-flight timings are one FULL EPOCH, not 400 steps**: a full A1
    epoch on an `a100_4g.20gb` slice is **~25 min including validation**.
    Separately, `build_tiny_trainer` never fitted the TF-IDF vectoriser, so
    three crash-recovery checks could not run at all on the one tier whose
    encoder was silently wrong once already (1e266f2). All six tier families
    now PASS.
  - **Campaign 10 trains on scan-like images; it is not a re-testing sweep**
    (question 17). §5.3 turns augmentation on "when *training on* scan-like",
    the generated configs set it, and its 30 runs are part of the spec's 312.
    So it was **split by lead subset into 10 (12-lead) and 15 (Lead-II)**, as
    7/8/11 were into 12/13/14 — **15 campaigns now**, still 104 configs and 312
    runs. The execution plan's "test split only" description was wrong and is
    corrected; spec §12.10 records it. No new data: it reads the containers
    question 16 already built.
  - **The three machines now say which they are**: an untracked one-word
    `.machine` (`data-laptop` / `campus-laptop` / `dgx`), a section in
    `AGENTS.md` on what each may do, and a git contract — pull `--ff-only`
    before reading this doc, push before the session ends, the DGX never
    commits.
- **RIGHT NOW: campaign 1 restarted after 12 idle days.** 32/36 runs and 8/12
  evals done (A1, A5, A6, B5). Running since 2026-09-28 ~10:06 UTC:
  - **`c1_B4` 24622** (dgxa slice, 7 d) — resumed B4 BERT seed 456 at epoch 3
    batch 79,997; then 3 tf-idf runs; its body then submits B4's 2 evals.
    ETA training ~2026-09-29 07:00 UTC, B4 evals ~2026-10-01/02.
  - **A3 evals 24625 (tfidf, dgxa) / 24626 (bert, dgxb)** at 12 CPU / 96G,
    resumed at 903 and 571 of 2,940 units. **32G OOM-killed a 12-worker eval**
    (24623/24624) — MaxRSS measured ~33-35 GB. Continuations chained with
    `afternotok` (24627/24628 tfidf, 24629/24630 bert) so a 7-day TIMEOUT no
    longer stalls them. ETA roughly 2-3 weeks per tier; re-measure the rate.
  - **Cloudflare backfilled**: `push_results.sh` artifact-name bug fixed
    (7128da3) — 96 missing run files pushed; `audit_reports/` and eval
    checkpoints (`eval_checkpoints_backup/`) now pushed on every run.
  - Account now at cap: cpu 32/32, mem 256/256G. **All jobs go to dgxa/dgxb
    via Slurm, never the login node.**
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
- **The venv on dgxa is BUILT and verified (2026-08-30, session 12).** Python
  **3.10.12**, **torch 2.6.0+cu124** against driver **550.144.03**, all 17
  third-party imports resolving, `torch.cuda.is_available()` True on a real
  allocation. The dependency list was read off the imports of `30_train.py`,
  `_dataset_lib`, `_model_lib` and `_train_lib` — there is no
  `requirements.txt` in this repo — and the resolved versions are recorded in
  session 12 below. `HF_HOME` is pinned inside `PROJECT_ROOT` so the
  HuggingFace cache is counted by `used_gb()` rather than hiding in `$HOME`.
- **THE FULL 40 GB A100s ARE THE BINDING CONSTRAINT, not the queue in general
  (2026-08-30).** dgxa has exactly two, and on this date both were held by
  `gpu_faculty` jobs with **14 and 19 days** left; all five of dgxb's were also
  taken. Slurm's estimate for `--gres=gpu:a100:1 --nodelist=dgxa` was **three
  weeks out**. A `a100_4g.20gb` MIG slice on dgxa allocated in ~20 seconds.
  **Rule 4 is amended: fit first, card second** — a slice on dgxa by default, a
  full card on dgxb when a run truly needs >20 GB (paying the measured 28x I/O
  penalty), and waiting for a full dgxa card only when a run needs both 40 GB
  and the fast disk. See `DGX_OPERATOR_HANDOVER.md` §3a. To make that decision
  measurable rather than guessed, `trainer.py` now records **`peak_gpu_gb`** in
  every epoch row of `train_log.jsonl`; nothing recorded GPU memory before.
- **The quota ceiling is 45 -> 49 GB.** `used_gb()` sums `du` over
  `PROJECT_ROOT`, which now also holds the 5.7 GB venv and the HF cache — fixed
  costs, not staged data. Campaign 7 stages 37.7 GB, which left ~1 GB of margin
  under the old ceiling. Changed in both places it is written:
  `campaigns.sh` and `decision_phase2.yaml`.
- **🔴 STOP-THE-LINE (2026-08-31): every `text_tfidf` run was silently training
  BioClinicalBERT.** Campaign 1's tf-idf and BERT runs came back with identical
  `macro_AUPRC` to four decimals (0.3931 / 0.3923 / 0.3932 across seeds 42 /
  123 / 456), identical epoch counts, ~29 min/epoch and an identical
  **7.814 GB** peak. A TF-IDF model cannot do any of that. Cause: the emitted
  configs name encoder CLASSES (`encoder: TfidfTextEncoder`), `plan_from_config`
  lower-cased that to `"tfidftextencoder"`, and `task_models.py` read
  `TfidfPassthrough() if plan.text_encoder == "tfidf" else
  BioClinicalBertEncoder(...)` — so the mismatch fell through to BERT.
  `task_dataset.py:529` compared the same way, so the loader fed tokenised text
  instead of `text_vec` and **nothing ever raised**. `BioClinicalBert` lowers to
  `"bioclinicalbert"`, which matched, so **the BERT tier is correct**; only
  tf-idf was wrong. Fixed in **1e266f2**: names canonicalise in one place
  (`_TEXT_ENCODER_ALIASES`) and both switch points now raise on anything
  unknown rather than defaulting.
  **RESOLVED 2026-09-01:** the fix is proven on the machine. The scoped smoke
  test (`--tiers text_tfidf text_bert`, job 22484) passed all 24 text
  train/eval checks with tf-idf now visibly a different model
  (`train A1_text_tfidf 8.4s` vs `text_bioclinicalbert 13.9s`), and the live
  re-run trains at **148.84 it/s against BERT's 4.9** — ~55 s per epoch instead
  of 29 minutes. The tf-idf path had never executed once before this.
  **Consequences, now handled:**
  - **6 configs / 18 runs affected** (one tf-idf config per text task x 3 seeds).
  - A1's three tf-idf runs are **invalid, and already pushed to `r2-results`**
    with their checkpoints deleted locally. They must be re-run and the pushed
    copies removed.
  - The five queued shards were **cancelled** (22345–22349) before they could
    burn ~75 GPU-hours producing more of the same. Nothing else was lost — they
    had not started.
  - **The A1 BERT results stand** and do not need re-running.
  - **DONE:** the three invalid runs were purged from `r2-results` and locally;
    campaign 1 was resubmitted as six per-task shards on dgxa `a100_4g.20gb`
    (jobs 22485–22490), and the A1 shard correctly **skipped the three finished
    BERT runs** and re-ran only tf-idf.

- **🟠 EVALUATION MUST NOT RUN ON THE GPU (measured 2026-09-01). This applies
  to every remaining campaign, not just campaign 1.** `31_eval.py` is a
  10,000-iteration BCa patient-level bootstrap — pure CPU, single-threaded — and
  A1/text_tfidf took **over ten hours at 99.9 % of one core** while the A100
  slice beside it sat idle. At two tiers per task that is ~20 GPU-hours per
  task, **more than the training it evaluates**, and with `gres/gpu=1` every one
  of those hours is on the critical path.
  **The account cap is on GPUs, not cores (`cpu=32`),** so evaluation belongs on
  `cpu_student`, where it runs *concurrently with the next training shard* and
  concurrently with other evals (one core each, 24 spare — a campaign's twelve
  evaluations can all be in flight at once). `_campaign_body.sh` now submits
  `slurm/eval_task.sbatch` per (task, tier); `TRIMODAL_EVAL_INLINE=1` restores
  the old blocking behaviour for debugging. Handover §3d has the rule:
  **before putting a step in the GPU job, ask whether it uses the GPU.**
- **✅ A1_ecg_diagnosis IS COMPLETE (2026-09-02) — campaign 1's first finished
  task.** `outputs/results/A1_ecg_diagnosis.csv`, 600 rows, both tiers, pushed
  to `r2-results` (12 runs, 0 failures). **The identical-tier tripwire passed
  its first real test**: overall AUPRC now differs between the tiers at every
  head (AF 0.7172 BERT vs 0.7199 tf-idf; HF 0.5754 vs 0.5907), which is what two
  genuinely different encoders look like — and nothing like the bit-identical
  collision of 2026-08-31.
- **🔴 THE FACILITY CANCELLED FOUR QUEUED JOBS (2026-09-02 ~10:17 IST).**
  `sacct` reports `CANCELLED by 0` — uid 0, an administrator — for 22487/22488/
  22489/22490 (A5, A6, B4, B5), none of which had started. We did not cancel
  them. **Someone should ask the facility why**: a queue-depth policy, a
  maintenance window, or something about our submissions. If it repeats, the
  campaign cannot be left unattended. They were resubmitted 2026-09-03 as
  22735–22738.
- **Three more bugs in the CPU-eval path, all now fixed (2026-09-03).** They
  cost no science, but two of them silently undid the point of the change:
  1. `_campaign_body.sh` submitted `$HERE/eval_task.sbatch`, but `HERE` is
     `dgx_portability/` and the file is in `slurm/`. Every eval **fell back to
     running inline on the GPU** — the exact thing the change existed to stop.
     The fallback logged loudly and still evaluated, which is why it was
     visible at all (commit 012d576).
  2. `eval_task.sbatch` set its own `HERE` to `slurm/` and called
     `$HERE/push_results.sh`, which is one level up. Both A1 evaluations ran
     their full 18 h, wrote the results CSV, then **exited 1 without pushing** —
     results existing only on the DGX, which §8.1 forbids (012d576).
  3. `eval_task.sbatch` inherited `campaigns.sh`'s laptop default
     `R2_RESULTS=r2:trimodal-results`, and on the DGX `r2` is the **read-only**
     data token. rclone failed with a misleading "is a file not a directory".
     `_campaign_body.sh` overrides this and `~/.bashrc` covers interactive
     shells; a batch job that sources neither got the wrong remote (a059d94).
- **A3's evaluation has 2,940 units against A1's 300** — an order of magnitude
  more, because A3 carries far more subgroup values. At A1's measured rate this
  is the cost to watch; it is the reason eval belongs on CPU where several can
  run at once, and the reason the checkpoint exists.
- **Measured evaluation cost (2026-09-02), now that it is parallel and off the
  GPU.** A1, 8 workers, both tiers running at once on `cpu_student`:
  **178 of 300 units in 11.1 h**. The rate decelerates hard — units 10→30 took
  16 minutes, units 160→170 took 83 — because `as_completed` returns the cheap
  subgroup slices first and the expensive `overall` slices over all 225,561
  pooled rows finish last. Extrapolating the tail: **~27 h per (task, tier)**,
  with the two tiers of a task running concurrently, so ~27 h per task.
  An earlier guess of "~4 days per tier" from a short `--bootstrap-n 200` probe
  was **wrong and too pessimistic**; the real figure comes from the checkpoint
  counter, which only exists because the eval is now resumable.
  **The important part: this no longer sits on the critical path.** Training a
  task takes ~28 h (A3: seed 42 took 8.8 h over 13 epochs, 9,227 batches/epoch),
  and its evals run beside the *next* task's training. With `cpu=32` and
  training holding 8, three evals fit alongside.
- **Guards added after the tf-idf collision (2026-09-01).** All three are
  proven, not just written:
  1. **`plan_from_config` asserts the plan matches the `arch_tier` name.** A
     tfidf tier must produce the tfidf encoder, a `notext` tier no text, a
     `text_`/`signal_`/`image_` tier that modality; a declared block that
     produced nothing (misspelt inner key) and a modality-ish top-level key the
     function does not read (misspelt outer key) both raise. Deliberately
     policy-aware — B5 forbids images, so its `multimodal_fusion` configs
     legitimately have no image block. **Validated against all 104 configs:
     104 accepted, 0 rejected**, and re-injecting the original bug is caught.
  2. **`31_eval.py` refuses to write results when two arch tiers produce
     bit-identical headline metrics** (`--allow-identical-tiers` to override).
     That comparison was the only thing that caught this bug.
  3. **`_campaign_body.sh` skips runs whose `run_summary.json` says
     `complete`.** push_results deletes both checkpoints once a run is in R2, so
     `try_resume()` found nothing and the loop retrained finished work — which
     also meant **every wall-clock requeue silently retrained every completed
     run** before reaching the unfinished one. `TRIMODAL_FORCE_RERUN=1`
     overrides.

- **Audit sweep for the same failure shape (2026-09-01).** Two more found and
  fixed:
  - **`stage_data.sh` verified nothing when nothing was staged.** A manifest
    entry absent from disk was skipped as neither ok nor bad, so a fetch that
    pulled *zero* files still printed a clean verification. It now counts
    absences, prints `verified N, absent M of T`, and fails when a manifest
    lists files and none are present.
  - **`smoke_test.py`'s recovery checks were hard-wired to a signal tier**, so a
    scoped text run reported three FAILs about missing `signals/*.h5`. Spurious
    FAILs teach you to skim past FAIL lines. The recovery target now follows
    `--tiers`; `test_gates` stays pinned to B1 because it needs a task whose
    policy genuinely forbids images.
  - **Audited and sound:** `delineate_ok` is carried as a real column into the
    parquet and stage stats, so a NeuroKit failure is recorded not silent; the
    other four swallowed exceptions are a read-only cache write, handle
    teardown, stdout reconfiguration, and an expected-exception gate. No bare
    `except:` anywhere outside `_legacy_phase1_pre_regen/`.
- **The 12 task builders were audited too (2026-09-01) — no bugs found.**
  Checked against their own staged outputs rather than argued from the code:
  - **zero duplicate `study_id`** in every one-row-per-study task and split
    (A1, A2, A3, A4, A6, B1, B5), so none of the **39 merges that carry no
    `validate=`** has multiplied rows;
  - **zero null label columns** anywhere, in any task or split;
  - the tasks that do repeat `study_id` do so by design and the numbers
    reconcile — B3 is exactly 4 rows per study (temporal bins, uniform), and B2
    is one natural row for each of 149,546 studies plus a full corruption sweep
    (`corruption_type` x `snr_db`, ~41 per regime) for 1,871 anchors,
    distinguished by `row_role` / `is_anchor`.
  - **A6's `errors="coerce"` is safe**: NaT rows are dropped explicitly for ED
    disposition, and mortality falls back `dod -> admissions.deathtime` with
    **`mortality_observable` carried as its own column** — "known alive" stays
    distinguishable from "unobservable". Same discipline as `delineate_ok`.
    Every other `fillna(False)`/`fillna(0)` is a flag or count where absence
    genuinely means False or zero.
  - **One tripwire added** (`01_build_A1`): `aggregate_by_encounter` merges rows
    against a group table built from those same rows' codes, so its
    `fillna(False)` is a no-op — it now asserts that, because an unmatched ICD
    code would become a confidently NEGATIVE label rather than a missing one.
    `validate="many_to_one"` guards the other direction.
  - **DONE 2026-09-01 — `validate=` is now on all 42 merge calls** (verified by
    AST walk, not grep: 42 calls, 0 without). Each was classified from its
    right-hand table, not blanket-applied: **`many_to_one` on 39** where the
    right side is unique on the join key (per-study metadata, per-hadm
    admissions, per-subject patients, group tables built from the same rows'
    distinct codes, groupby/drop_duplicates results), and **`many_to_many` on
    3** — A6's `prior_history` and `ed_disposition_before_ecg`, where a
    subject's studies are deliberately crossed with that subject's admissions
    and filtered by time straight after. That performs no check; it records
    that the fan-out is intended, beside the ones where it is not.
    **Tested before it reached the queued shards:** constructing every
    campaign-1 task x split on the staged data exercises the live data-path
    merges — **18/18 ok, 0 fail**. Not exercised by that test, and therefore
    unproven until their next run: the 12 builders' own merges (they need raw
    MIMIC, which is on the owner's laptop only), `50_run_baselines`,
    `31_eval.attach_b6_tiers` (B6 only), and `chunk_pieces` (chunked campaigns
    only). A wrong classification there fails loudly on the next run rather
    than corrupting anything.
  - **Noted, not a bug:** B5's `multimodal_fusion` tier is two modalities
    (signal+text) where every other task's is three, because B5's input policy
    forbids images. Correct, but it means cross-task fusion comparisons are not
    like-for-like — worth a line in the paper.
- **Next action — the scoped smoke test, then campaign 1.**
  `smoke_test.py` defaults to all six families, but campaign 1 is `text_models`
  and stages `code configs tasks fiducials index text` — no signals, no images.
  The signal/image/fusion tiers therefore cannot smoke until their data is
  staged, and they should smoke in front of the campaign that needs them.
  Exact commands in Step 8 below and in **`docs/DGX_OPERATOR_HANDOVER.md`**,
  which is the operational companion to this file: which machine does what, the
  Slurm cheat-sheet, the rules (now with §3a on GPU selection), and the prompt
  for starting a session on the on-campus laptop that drives the DGX.
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
| 0   | **`docs/SESSION_12_HANDOVER.md`**   | **the narrative of sessions 12's nine days** — the eleven defects found (one of which produced a day and a half of wrong results), the measured cluster constraints, A1's numbers, the traps, and a ready-made prompt to resume. Read it once; this file stays the live state. |
| 0b  | **`docs/SESSION16_POSTMORTEM.md`**  | **what went wrong in sessions 15–16, what was fixed, the checks that now guard it, the rules that follow, and what is still unproven on the DGX.** Read it before submitting or changing any campaign. |
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

Added by Steps 5 and 6, **as it stands after the 2026-10-06 cleanup** (decimal
GB, measured; the Phase 1 table above is in GiB — `data/processed` is 396.9 GB
on D: now, of which Phase 1 is ~384):

| Artifact                                                    |     Size | Where |
| ----------------------------------------------------------- | -------: | ----- |
| `signals_int16/lead2_preprocessed.h5` + `int16_manifest.json` |  7.42 GB | D:    |
| `derived/images_clean_12lead_L3/` (3 splits, campaign 7)    |  5.03 GB | D:    |
| `derived/*_valtest/` — six val/test containers              | 74.92 GB | C:    |
| `chunks/` — five cuts × 8 train pieces (raw 12-lead: plan only) | 144.56 GB | C: |

**Deleted 2026-10-06, rebuildable:** `signals_int16/twelve_lead_preprocessed_shard_{00..04}.h5`
(83.24 GB, `make_int16.py`), `derived/signals_12lead_L3/` (44.17 GB) and
`derived/images_scanlike_test/` (20.33 GB) (`make_subsets.py`; both still in R2).

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
- Free space **(re-measured 2026-10-06, after the session 18 cleanup): D:
  188.8 GiB.** C: was 107.3 GiB and the cleanup freed nothing there; other work
  on this machine is using it, so measure before building onto it. D: has room
  again, so a rebuilt int16 shard set
  (83 GB) fits where `make_int16.py` writes it. `TRIMODAL_DERIVED_BASE` still
  moves a derived container to C: when it does not.
- **Always use `ecg_env`**: `./ecg_env/Scripts/python.exe` — Python 3.11.9,
  torch 2.7.1+cu118, CUDA available, bf16-capable.
  The system Python 3.14 has a **CPU-only** torch. Do not use it.
- Mains power is unreliable (cuts). Every long-running local script must
  checkpoint and resume.

### Where the data physically lives (2026-10-06)

**One rule: D: holds what Phase 1 produced, C: holds everything derived from
it, and R2 holds what the DGX reads.** Two derived leftovers sit on D: because
their upload links needed the same volume: `signals_int16/lead2_preprocessed.h5`
and `derived/images_clean_12lead_L3/`.

| path | what | size |
| --- | --- | --- |
| `D:\Coding\MU\Tri-Modal_ECG\data\processed` | the base containers Phase 1 built -- image shards, signal HDF5s, `tasks/`, `index/`, `modality_manifest.parquet` -- plus `manifest_overlays/` (7) and the two leftovers above. **Never uploaded wholesale.** | 396.9 GB |
| `C:\trimodal_chunks\<kind>__train__p8` | the chunk cuts, one directory per kind; `raw_12lead` holds its plan files only | 144.56 GB |
| `C:\trimodal_derived\derived\<dataset>` | the six derived val/test containers, junctioned into `data/processed/derived/`. **Do not delete: their overlays are live locally (trap 21).** | 74.92 GB |
| `outputs/upload_stage`, `C:\trimodal_chunks\_upload_stage` | hard-link staging the uploader builds. **Disposable** -- it shares inodes with the originals and costs no space; `upload_data.py` recreates it. Both removed 2026-10-06. **A file deleted while its staging link survives frees nothing.** | 0 |
| `r2:trimodal-data` | what the DGX stages from. The authority for anything staged. | **350.3 GiB, 672 objects** (`rclone size`, 2026-10-05) |
| `r2:trimodal-results` | what the DGX writes back; `push_results.sh` fills it | grows |

**The C: directories are reached from D: through junctions** under
`data/processed/derived/` and `data/processed/chunks/`, because `modality.py`
resolves every overlay path relative to `DATA_PROCESSED`. Without the junction a
val/test read fails on the laptop while being correct on the DGX -- see trap 21.

**Deleted on purpose:** the local copy of `raw_12lead__train__p8` (28 GB). Its
11 objects were compared name-for-name and byte-for-byte against
`r2:trimodal-data/chunks/signals_raw` first. R2 is the authority for staged
data (storage rule 5), and the cut is reproducible from the base containers.
**And on 2026-10-06 (session 18):** the whole int16 12-lead shards (83.24 GB;
every byte a campaign reads from them is in `signals_12lead_pieces` +
`signals_12lead_valtest`), and the local `signals_12lead_L3` (44.17 GB) and
`images_scanlike_test` (20.33 GB) — no campaign stages either, and
`rclone check` matched both hash-for-hash against R2 (9 and 5 files, 0
differences) before they went. Their two overlays went with them, so those
studies read from the base containers or the `*_valtest` ones again.

**R2 inventory (2026-09-30):** `chunks/` {images_clean_12lead, images_clean_lead2,
images_scanlike_12lead, images_scanlike_lead2, signals_12lead, signals_raw} (all p8, aligned);
`code configs tasks index text fiducials`; `images_clean_12lead[_L3|_valtest]`,
`images_clean_lead2[_valtest]`, `images_scanlike_{12lead,lead2}_valtest`,
`images_scanlike_test`; `signals_12lead_L3`, `signals_12lead_valtest`, `signals_raw_valtest`,
`signals_corrupted`, `signals_lead2`, `signals_lead2_preprocessed`, `signals_lead2_raw`.

**Retained but UNUSED:** `signals_lead2/` in R2 (12.6 GB) since campaign 4 moved to
`signals_lead2_preprocessed` + `_raw`, which hold the same two files under new keys.
`signals_12lead_L3` in R2 (~44 GB). Campaigns 5 and 7
moved to the full-cohort 12-lead pieces when the L3 subset measured 35.35 GB
resident. It is kept rather than deleted because it cost a night to upload and
storage is about $0.53/month; nothing reads it. Delete it only deliberately.

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
- **Two accounts since 2026-10-14** (`se23ucse027`, `se23ucse034`) — usernames,
  aliases, caps, what each can write and the account 2 setup list are in
  `docs/DGX_ACCOUNTS.md`. **The ceiling is now 99 GB**, in account 1's folder;
  every "49 GB" below this line is history.
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
- **Claude Code is NOT installed on the DGX, deliberately (decided 2026-08-30).**
  It runs on the on-campus laptop that already holds the owner's authenticated
  session and can reach the cluster over SSH. That keeps the auth token off the
  facility, and keeps ~300 MB of Node and CLI out of the 50 GB. Node is not
  installed on the DGX and does not need to be.
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

### The three machines, and `.machine`

**This repo lives on three machines and they are not interchangeable.** Each
one carries an untracked one-word file `.machine` at the repo root
(`/*` in `.gitignore` already ignores it, so a pull can never overwrite it):

| `.machine`      | What it is                                       | `data/processed`?   | Reaches the DGX?       |
| --------------- | ------------------------------------------------ | ------------------- | ---------------------- |
| `data-laptop`   | the user's laptop, `D:\Coding\MU\Tri-Modal_ECG`  | yes, 355 GB         | no                     |
| `campus-laptop` | the on-campus laptop, inside the MU network      | no                  | yes, by remote desktop |
| `dgx`           | the DGX itself, `$HOME/se23ucse027`              | only what is staged | it *is* the DGX        |

Added 2026-09-30 (session 16) because two sessions had to be told which machine
they were on. **If `.machine` is absent, ask the user and write it** — do not
infer it from the path or the OS. Consequences that actually bite:

- Only `data-laptop` can build, measure or upload a dataset. It cannot submit,
  cancel or poll a Slurm job, and must never record a DGX number as if it had
  observed one.
- Only `campus-laptop` can reach the DGX. It has no containers, so anything
  that calls `read_modality()` fails there **by design** — not a bug to fix.
- `dgx` **pulls and never commits.** Code and configs come from git, not R2
  (`stage_data.sh` skips those two datasets over a work tree — commit 7d3602d).

### Git is the only channel between them — pull first, push last

There is no shared filesystem. `main` on
`https://github.com/rohith0110/Tri-modal_ECG.git` is it, so **an unpushed
commit does not exist** to the other two machines and an unpulled checkout is
running last week's code. Every session, every machine:

1. `git pull --ff-only origin main` **before reading the progress doc** —
   reading it first means reading a stale handover, which is the one failure
   this loop exists to prevent. If `--ff-only` refuses, stop and tell the user;
   never merge, rebase or force.
2. work on `main`;
3. `git add -A && git commit && git push origin main` if anything changed at
   all, including a docs-only edit, and even if the work is unfinished — a
   `[~]` mark plus a session-log entry is exactly what the next machine needs;
4. on the DGX, `git -C "$PROJECT_ROOT" pull --ff-only origin main` **before
   every submit**. An unpulled checkout has already cost this project the
   wrong-model incident (1e266f2) and a `transport=none` failure (7d3602d).

The contract is written out in `AGENTS.md`; `CLAUDE.md` carries the short form
so it is injected every session.

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

**Nothing is open that blocks work.** Questions 16 and 17 closed in session 16,
questions 9 and 11 in session 2.
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
| 16  | **The A5/B4 scan-like train/val images do not fit, and no subset makes them fit.** `image_type_column` (`task_dataset.py:524-528`) makes A5/B4 pick the rendering per row, so their scan-like rows need `image_scanlike_{12lead,lead2}` for TRAIN and VAL. R2 had only `images_scanlike_test`. | was holding campaigns 2, 3, 8, 10, 11, 13, 14 | **✅ CLOSED 2026-09-30 (session 16). CHUNKED, on the user's decision.** The measurement first: there is exactly one scan-like row per anchor and every study in the split is an anchor, so train+val is **599,470 of 749,112 studies (80.0 %)** — **`images_scanlike_12lead` 50.08 GB** (train 43.77 + val 6.31) and **`images_scanlike_lead2` 31.24 GB** (27.30 + 3.94), the first of which exceeds the entire 49 GB ceiling on its own. Scan-like is JPEG RGB at the same pixel size as clean PNG, so it costs **80.8 KiB/study against 10.8**. The method cross-checks: 12.52 + 7.81 GB of test = **18.93 GiB**, which is exactly the `images_scanlike_test` container already in R2. **What was built:** scan-like TRAIN cut at **p8 for both layouts** (`make_chunks.py`, fairness PASS, piece sizes within 0.40 %, and **0 of 523,945 studies disagree** with the `preprocessed_12lead` / `image_clean_12lead` / `raw_12lead` cuts, so one resident window serves every modality); **per-layout** `images_scanlike_<layout>_valtest` for val and test; **`images_clean_lead2` chunked at p8** plus its valtest, for campaigns 13/14 only; and `signals_lead2` split into `_preprocessed` / `_raw` (12/13/14 were staging a 6.08 GB raw file they never read — new remote prefixes, so both files were re-uploaded, 12.6 GB). **Verified by round trip:** two real pieces staged the way `stage_data.sh` stages them, `install_overlays()` run, and `read_modality()` returns **byte-identical** payloads to the base shards, with studies outside the window still resolving to the base container. **Two mechanisms were needed:** `ChunkCycle.ensure()` now **evicts before it fetches** (it used to hold the outgoing and incoming pairs at once — four pieces against a quota sized for two), and campaigns 8 and 11 use **`val_mode=on_demand`**, staging the val split only at the epoch boundary. **All 14 campaigns now pass `require_fit` in both phases**, the thinnest being campaign 12 at 27.7 GB against a 36.8 GB budget. |
| 17  | **Does campaign 10 TRAIN on scan-like images, or only re-test on them?** `campaign_runs.py 10` emitted 30 training runs and `_campaign_body.sh` trains them, but the campaign staged the test split only and the execution plan called it "the sweeps that only need re-testing… test split only". | Step 23 | **✅ CLOSED 2026-09-30 (session 16) — IT TRAINS.** Settled against the binding documents, not by preference. **§5.3 turns image augmentation on "when *training on* scan-like or mixed clean+scanlike" and off for clean-only training**, and `model_configs.py:145` emits exactly that: `augmentation: true` on every `*_scanlike` config, `false` on every `*_clean` one. `build_image_transform` applies augmentation **only when `split == "train"`**, so the setting is meaningless unless the tier trains. It is the image-side analogue of §7.3's B2 regimes, where regime_1 (clean-trained) and regime_2 (corruption-augmented) are **both** trained arms. And its 30 runs are part of the **104 configs / 312 runs** the spec counts — treating the tier as evaluation-only would silently drop them. The Truth doc agrees on the data side: §6.1 makes the scan-like image **"Positive type 2"** of the verification task, i.e. training data, which is exactly what `image_type_column` implements. **The execution plan was wrong and has been corrected** (its Step 23 and its upload table). **Consequence:** the tier needs scan-like train+val for both layouts, so campaign 10 is **split by lead subset** exactly as 7/8/11 were into 12/13/14 — **10 is the 12-lead half, 15 the Lead-II half**, 5 configs and 15 runs each, and `--table` still reports 104 / 312. Both stage the CLEAN container too, because their A5/B4 rows pick the rendering per row. **No new data was needed** — the scan-like pieces and val/test containers built for question 16 are exactly what it reads. Measured: campaign 10 27.9 GB train / 23.2 eval, campaign 15 31.0 / 28.1. Recorded in spec §12.10. |

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
  - [x] **`stage_data.sh 1` ran for real on dgxa, 2026-08-30.** Six datasets,
        ~1.12 GB pulled at 22-41 MiB/s, and **every staged file verified against
        its `checksums_<dataset>.json`** — 124 code files, 128 configs, the 12
        task directories, index, fiducials and text, all `ok`, zero mismatches.
        Finished: *"campaign 1 staged. Used: 1.18 GB of 45 GB ceiling."*
        The round trip proved on the laptop in session 8 now holds on the real
        machine, with `code`/`configs` landing in `$PROJECT_ROOT` and everything
        else at its manifest path under `data/processed/`.
  - [x] **The DGX checkout is git, not rclone (2026-08-30).** `~/se23ucse027` is
        a clone of the private repo; `git pull` updates code and `stage_data.sh`
        only pulls data. R2's `code`/`configs` datasets are now the fallback for
        when GitHub is unreachable. This forced a second line-ending fix:
        `upload_data.py` ships the *working tree*, and with `core.autocrlf` on
        Windows 197 tracked text files were CRLF locally and LF in git, so
        staging over a fresh clone overwrote 66 of git's files. `*.py`, `*.yaml`,
        `*.yml`, `*.json`, `*.md` are now pinned `eol=lf`.
  - [x] **The venv is BUILT (2026-08-30, session 12).** No `module`, no conda, no
        container runtime, so plain `python3 -m venv` against **Python 3.10.12**
        (the laptop is 3.11), inside an `srun` allocation on dgxa — job 22331,
        `cpu_student`, granted in ~4 s. `nvidia-smi` from that allocation gave
        **550.144.03 / 6x A100-SXM4-40GB**, so the **cu124** wheel.
        Result: **torch 2.6.0+cu124**, torchvision 0.21.0+cu124, and all 17
        third-party imports resolving with `FAILED: none`. The list came from
        the imports of `30_train.py`, `_dataset_lib`, `_model_lib` and
        `_train_lib` — there is no `requirements.txt` in this repo — and is
        recorded in session 12 below. `HF_HOME` is appended to
        `ecg_env/bin/activate`, which `activate_python()` sources, so the
        HuggingFace cache lands in `PROJECT_ROOT/.cache/huggingface` and
        `used_gb()` counts it. The venv costs **5.7 GB**, not the ~3 GB budgeted,
        which is why the ceiling moved to 49.
  - [x] **The smoke job RAN on a MIG slice, 2026-08-30 — 26 PASS / 30 FAIL, and
        every one of the 30 is missing data, not broken code.** Job 22333,
        `--gres=gpu:a100_4g.20gb:1` on dgxa, 8m43s.
        `torch.cuda.is_available()` True on `A100-SXM4-40GB MIG 4g.20gb`.
        **PASS:** all 12 text tiers train and eval (`text_tfidf` and
        `text_bioclinicalbert` across A1/A3/A5/A6/B4/B5 — BioClinicalBERT
        downloaded through `HF_HOME` on the node, which re-confirms open
        question 4's ONLINE), plus `gates` and the preemption handler.
        **FAIL:** all 30 signal / image / fusion tiers, every one of them
        `FileNotFoundError` — 25 on `signals/lead2_preprocessed.h5`, 5 on image
        files. **No other error type appears in the log.**
        The cause is scope, not a bug: `smoke_test.py` defaults to all six
        families, while campaign 1 is `text_models` and stages
        `code configs tasks fiducials index text` (`campaigns.sh:233`) — no
        signals, no images. `--tiers` scopes it. The signal/image/fusion tiers
        smoke in front of the campaign that stages their data, not before.
  - [x] **Two code fixes the DGX forced (commits f13be9a, 859cd8a).**
        (1) `smoke_test.py` spawned `30_train.py` / `31_eval.py` through a
        hard-coded `ecg_env/Scripts/python.exe`, which does not exist on Linux;
        it is now `Path(sys.executable)`. It was the only live occurrence — the
        other `Scripts/python.exe` hits in the tree are usage docstrings.
        (2) `trainer.py` now records **`peak_gpu_gb`** per epoch in
        `train_log.jsonl`. Nothing measured GPU memory before, and on this
        cluster that number decides between a slice available now and a full
        card three weeks out.
  - [x] **Campaign 1 IS RUNNING (2026-08-30, session 12) — Step 13 has started.**
        Four more DGX-only bugs had to be fixed to get there, each of which
        stopped a submit dead (commits 23ceade, 6f15ca3, 74f2a8b, 7d3602d):
        1. **Every tracked `*.sh` was mode 100644.** `_campaign_body.sh` invokes
           `stage_data.sh`, `push_results.sh` and `evict_data.sh` directly, so
           the first submit died with `Permission denied` (exit 126).
           `core.fileMode=false` on the Windows checkout is why nobody saw it.
           All five are 100755 in git now.
        2. **`transport=none`.** rclone lives at `$PROJECT_ROOT/bin/rclone` and
           reaches PATH through `.bashrc`, which a Slurm batch shell never
           sources. `resolve_rclone()` searches real paths and exports `RCLONE`.
        3. **A hard hang at batch 1 of 8218.** Main process in
           `futex_wait_queue_me`, four DataLoader workers alive at 0 CPU, 15 s
           of CPU across 10 minutes of wall clock. transformers 5.x resolves a
           model against the Hub (`/discussions`, `/commits/refs%2Fpr%2F16`) and
           each forked worker then re-resolved the tokenizer. Fixed by exporting
           `TOKENIZERS_PARALLELISM=false` always and `HF_HUB_OFFLINE=1` when the
           model is cached. It would have burned the whole allocation silently.
        4. **Staging `code` from R2 reverted five tracked files mid-session** —
           the ceiling fix, the rclone resolver, `peak_gpu_gb` and the smoke-test
           interpreter fix all rolled back, and the next job then failed on the
           reverted copy (its log said `45 GB ceiling`, which is what exposed
           it). `stage_data.sh` now skips `code`/`configs` when `PROJECT_ROOT`
           is a git checkout, and skips their manifests with them, since those
           describe R2's copy. `TRIMODAL_FORCE_CODE_STAGE=1` is the override.
  - [x] **THE ACCOUNT MAY HOLD ONE GPU AT A TIME.**
        `sacctmgr show assoc` gives `cpu=32,gres/gpu=1,mem=256G` for
        `se23ucse027`, and a MIG slice counts as `gres/gpu=1` exactly as a full
        A100 does. Campaign 1 was submitted as six per-task shards across six
        free slices; five pended on `AssocGrpGRES` and would have waited
        forever. **All 312 runs are therefore strictly sequential**, which the
        campaign schedule in Part 4–7 does not assume. Asking the facility to
        raise `gres/gpu` is the highest-leverage action available to this
        project. Sharding was kept anyway: with the cap, Slurm starts the next
        shard automatically, each is a smaller resumable unit, and none risks
        the wall-clock timeout a single 36-run job would.
  - [x] **A1's six runs finished (2026-08-30 → 08-31), job 22339 on a dgxa
        `a100_4g.20gb` slice.** Measured, per run:

        | tier | seed | epochs | best macro_AUPRC | hours | peak_gpu_gb |
        | ---- | ---- | ------ | ---------------- | ----- | ----------- |
        | text_bioclinicalbert | 42  | 10 | 0.3931 | 4.84 | 7.814 |
        | text_bioclinicalbert | 123 |  9 | 0.3923 | 4.35 | 7.814 |
        | text_bioclinicalbert | 456 | 11 | 0.3932 | 5.33 | 7.814 |
        | text_tfidf (INVALID) | 42  | 10 | 0.3931 | 4.84 | 7.814 |
        | text_tfidf (INVALID) | 123 |  9 | 0.3923 | 4.35 | 7.814 |
        | text_tfidf (INVALID) | 456 | 11 | 0.3932 | 5.32 | 7.814 |

        Early stopping fired at 9–11 epochs of the allowed 20 (patience 5), so a
        BERT run is **~4.3–5.3 h** on a 20 GB slice, not the 9.7 h a full 20
        epochs would cost. Training was healthy: loss 4.963 → 4.785 over the
        first four epochs, `amp: bf16`, `improved: true` every epoch until the
        plateau. All six pushed to `r2-results`, 0 failures, checkpoints freed
        (1.3 GB + 419 MB per run); `Used: 7.65 GB of 49 GB`.
        **The three tf-idf rows are the wrong model — see the stop-the-line
        note in the header.**
  - [x] **`peak_gpu_gb` = 7.814 for a BioClinicalBERT run** — the first
        measurement the field was added for. It fits an **`a100_2g.10gb`** slice
        (10 GB) with ~2.2 GB spare, and does NOT fit `a100_1g.5gb`. The 10 GB
        slices are the most plentiful thing on dgxa, so memory was never the
        obstacle to fanning out — `gres/gpu=1` was.
  - [x] **The dgxb swap never happened, and should not be relied on.**
        `swap_watcher.sbatch` (job 22350) polled for 24 h and logged
        `dgxb_full_cards_busy=5/5` on every single check before hitting its
        TIMEOUT. Jobs 22033/22034 did end — and `gpu_faculty` immediately took
        the cards again as 22308/22309. **dgxb's full A100s churn straight back
        to faculty; a student job should not wait for one.** The mechanism
        worked exactly as designed (no GPU held, clean exit); the assumption
        behind it did not.
  - [ ] Read `peak_gpu_gb` from the first completed epoch's `train_log.jsonl`
        and size every later campaign of each family from it.

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

- [~] **Step 13 — Text models** (36 runs: 6 tasks x 2 tiers x 3 seeds, as
      `campaign_runs.py 1` derives them; the older "21" predates Round 10)
      — **IN PROGRESS 2026-09-28: 32/36 runs pushed** (A1, A3, A5, A6, B5
      complete; B4 2/6, shard died on wall clock, not resubmitted).
      **Evaluation: 8 of 12 (task, tier) pairs done** — A1, A5, A6, B5; A3's
      two timed out at 7 days, B4's not started. See session 14.
- [ ] **Step 14 — 12-lead pictures** (15 runs, `campaign_runs.py 2`)
      — **UNBLOCKED 2026-09-30.** Campaign 2 is 27.9 GB train / 23.2 eval and
      stages `images_scanlike_12lead_pieces` + `_valtest`. A5/B4 chunk-cycle,
      A1/A3/A6 do not. **Job 24641 is held and was submitted against the OLD
      table — cancel it and submit fresh.**
- [ ] **Step 15 — Lead-II pictures** (15 runs, `campaign_runs.py 3`)
      — **UNBLOCKED 2026-09-30.** Campaign 3 is 31.0 / 28.1 GB.
      · [ ] **Step 16 — Lead-II signals** (33)

### Part 5 — Campaigns 5–6 (~1 week)

- [ ] **Step 17 — 12-lead signals, L3 tasks** (12) — **now chunked.** Campaign 5
      reads the FULL-cohort 12-lead pieces, not `signals_12lead_L3`: measured,
      that subset is 35.35 GB resident and left 0.4 GB of margin. 22.7 GB now.
- [ ] **Step 18 — 12-lead signals, full cohort** (18, chunked) — 22.7 GB

### Part 6 — Campaigns 7–8 and 12–13, the heart of the paper (~1.5 weeks)

Round 10.5 added the trained no-text tier here. **SPLIT BY LEAD SUBSET
2026-08-29 (open question 14)**: a fusion campaign reads a whole lead set, and
holding both put campaign 7 at 69 GB against a 45 GB ceiling. 7 and 8 are now
the 12-lead halves, 12 and 13 the Lead-II ones. Project total is unchanged —
**104 configs, 312 runs**; `campaign_runs.py --table` is the authority.

- [ ] **Step 19 — End-to-end fusion, L3 tasks A1/A3/A6**
      — campaign 7 (12-lead, 18 runs) + campaign 12 (Lead-II, 18 runs)
- [ ] **Step 20 — End-to-end fusion, full cohort A5/B4/B5/B6**
      — campaign 8 (12-lead, 15 runs) + campaign 13 (Lead-II, 15 runs)
      — **UNBLOCKED 2026-09-30.** Campaign 8 is the first `val_mode=on_demand`
      campaign: 27.4 GB train, and it fetches the 15.1 GB val split at each
      epoch boundary rather than holding it. Campaign 13 is 24.3 GB and chunks
      the clean Lead-II images as well as the scan-like ones.
- [ ] **Step 21 — Frozen-fusion ablation** (near-free by-product)

### Part 7 — Campaigns 9–11 and 14 (~1.5 weeks)

- [ ] **Step 22 — Re-training sweeps** (campaign 9, 12.7 GB)
- [ ] **Step 23 — The scan-like image arm** — campaign 10 (12-lead, 15 runs,
      27.9 GB) + **campaign 15** (Lead-II, 15 runs, 31.0 GB). **This tier
      TRAINS** (open question 17, spec §12.10); the execution plan's
      "re-testing only" description was wrong and is corrected. Campaign 10 was
      split by lead subset for the same reason 7/8/11 were. It had also staged
      **no clean-image container at all**, though its A5/B4 rows read one.
- [ ] **Step 24 — Final eval + calibration/threshold/reproducibility audits**
      — campaign 11 (12-lead, 6 runs) + campaign 14 (Lead-II, 6 runs)
      — **UNBLOCKED 2026-09-30.** Both are A5/B4 only and both DO train
      (20 epochs). Campaign 11 also had the wrong cohort: it staged the L3
      subsets although A5/B4 are not L3 tasks. It now reads the full-cohort
      12-lead pieces and is `val_mode=on_demand` (27.4 GB). Campaign 14 is
      24.3 GB.
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


20. **A5 and B4 read a modality their model config never names.** Both specs
    set `image_type_column="image_type"`, and `task_dataset.py:524-528` then
    builds the kind from the ROW: `image_{row.image_type}_{layout}`. The config
    only decides the layout. So **any** A5/B4 config that touches images — the
    image tier, `multimodal_fusion*`, `embedding_cosine` — reads
    `image_scanlike_<layout>` as well as `image_clean_<layout>`, and a campaign
    dataset list derived from `input_modality` alone will be short one dataset
    and die at the first scan-like row. That is exactly how jobs 24639/24640
    failed. **Derive an A5/B4 campaign's image datasets from the task table, not
    from the config.**

21. **A derived container can live on C: while its overlay lives on D:, and a
    junction is what makes that work.** `data/processed` is on D:, which has
    25 GB free; the cuts and the derived val/test containers are on C: and are
    reached through directory junctions under `data/processed/derived/`.
    `modality.py` resolves an overlay path relative to `DATA_PROCESSED`, so
    **without the junction a val/test read fails locally with
    `FileNotFoundError` while being perfectly correct on the DGX** -- which is
    what happened between 2026-08-29 and 2026-09-30, when the three `*_valtest`
    sets were uploaded and then deleted from D: to free space. All four are
    junctioned now and every val read works; see the storage map in §3. **If you
    add a derived dataset, add its junction**, or the next session will chase a
    missing file that is not missing.

22. **Freeing disk on the data laptop: three things that look deletable and
    are not, and one that looks done and is not.** (Session 18.)
    - **Every parquet in `manifest_overlays/` is live on the laptop** —
      `_manifest_with_overlays()` applies all of them, whatever the comment at
      `modality.py:35` says. Deleting a derived container without its overlay
      breaks every local read of those studies (trap 21 is this, by accident).
      Delete the pair or neither.
    - **The upload staging trees are hard links.** `du` and Explorer count
      their bytes twice (333 GB of phantom on 2026-10-06), and a file whose
      staging link survives frees nothing when deleted. Remove the tree first.
    - **Keep each cut's `checksums.json`, `assignment.parquet` and
      `fairness.json`** when its pieces go: `--sizes` and
      `check_r2_complete.py` fall back to them, and report a non-chunk dataset
      with no local copy as `missing` instead.
    - **`signals_int16/lead2_preprocessed.h5` is a dataset source, not an
      intermediate** — campaigns 4 and 12–14 upload that exact file.
    Measure with something that does not cross a junction or it counts C: under
    D:. Run the three checks before and after and diff the output.

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
4. **One roll-numbered folder.** All work lives in
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
denied, so no script running on the cluster can damage the 226 GB. `r2-results` =
`dgx-write-results`, round-tripped a file and deleted it. `laptop-full` stays on
the laptop.

**`code` was re-uploaded twice**, because the first DGX dry run proved the
bucket copy was stale — it still resolved `DATA_ROOT=/tmp/...`. Re-pulled, and
the dry run then gave the right roots and `quota OK: 0.08 GB used + 1.1 GB`.

**Next:** `stage_data.sh 1` for real, then the venv (plain `python3 -m venv`,
**Python 3.10.12**, no conda/module/container — `venv` verified working; pick
the torch CUDA wheel against dgxa's driver), then the 5-minute smoke job.

### Session 12 — 2026-08-30 — the venv on dgxa, and the GPU that is not there

Driven from the **on-campus laptop** over `ssh mudgx`, per
`DGX_OPERATOR_HANDOVER.md`. No data on that machine and none needed.

**SSH, first.** Key auth failed from git-bash with
`Permission denied (publickey,password)` even though the key was offered. The
key was fine and `authorized_keys` on the DGX was fine: the key carries a
passphrase and lives in the **Windows** `ssh-agent`, which git-bash's
`/usr/bin/ssh` cannot reach (named pipe vs MSYS socket). Calling
`/c/WINDOWS/System32/OpenSSH/ssh.exe` uses the agent and never prompts. If a
future session sees that error, check *which* ssh binary is running before
touching the key.

**Cancelling an `ssh` does not cancel the `srun` it started.** A killed
`nvidia-smi` allocation was still sitting in the queue minutes later as job
22330. `scancel` it — a pending job holds a scheduling slot.

**The venv** (job 22331, `cpu_student --nodelist=dgxa --mem=8G`, allocated in
~4 s). Python 3.10.12, driver 550.144.03, 6x A100-SXM4-40GB, so cu124:

```
torch==2.6.0+cu124  torchvision==0.21.0+cu124  numpy==2.2.6  pandas==2.3.3
pyarrow==25.0.1  scipy==1.15.3  scikit-learn==1.7.2  transformers==5.16.1
tokenizers==0.23.1  huggingface_hub==1.29.0  h5py==3.16.0  pydantic==2.13.5
psutil==7.2.2  pillow==12.3.0  matplotlib==3.10.9  tqdm==4.70.0  PyYAML==6.0.3
neurokit2==0.2.13  lifelines==0.30.0
```

Nothing is pinned anywhere in this repo, so these are what pip resolved on this
date and they are recorded here because nothing else records them. Note
**transformers 5.x**, a major version ahead of what the code was written
against; the usage is core (`AutoModel` / `AutoConfig` / `AutoTokenizer`,
`.from_pretrained`, `bert.embeddings.parameters()`) and all 12 text tiers
smoke-passed on it. The venv is **5.7 GB**, against the ~3 GB budgeted.

**The finding that matters: the full 40 GB A100s are the scarce resource.**
A `--gres=gpu:a100:1 --nodelist=dgxa` smoke job pended on `Priority` with
`StartTime=2026-09-21` — three weeks. dgxa has two full cards and both were
held by `gpu_faculty` jobs with 14 d 04 h and 19 d 02 h left; all five of
dgxb's were taken as well, and `gpu_student` job 22313 was already pending
ahead of us for the first one to free. Free on dgxa the same minute:
one `a100_4g.20gb`, five `a100_2g.10gb`, sixteen `a100_1g.5gb`.

The slice allocated in about twenty seconds. **Rule 4 is amended to "fit first,
card second"** — `DGX_OPERATOR_HANDOVER.md` §3a. dgxb becomes the real answer
when a run needs more than 20 GB, accepting the measured 28x NFS penalty, which
is a per-campaign judgement: memory-bound runs yes, I/O-bound runs no. And
because that judgement had no measured basis at all, `trainer.py` now writes
`peak_gpu_gb` into each epoch row of `train_log.jsonl`.

**The smoke test** (job 22333, `a100_4g.20gb`, 8m43s): **26 PASS, 30 FAIL, and
all 30 failures are `FileNotFoundError`** — 25 on `signals/lead2_preprocessed.h5`
and 5 on image files. No other error type in the log. All 12 text tiers train
and eval; `gates` and the preemption handler pass. BioClinicalBERT downloaded
onto the node through `HF_HOME`, which re-confirms question 4's ONLINE.

The failures are scope, not breakage: the smoke test defaults to all six
families while campaign 1 (`text_models`) stages only
`code configs tasks fiducials index text`. `--tiers text_tfidf text_bert` is
the honest run for campaign 1's scope; the other families smoke in front of the
campaign that stages their data.

**Two fixes** (f13be9a, 859cd8a): `smoke_test.py`'s hard-coded
`ecg_env/Scripts/python.exe` became `Path(sys.executable)` — it does not exist
on Linux and was the only live occurrence; and the ceiling moved 45 -> 49 GB in
**both** places it is written, `campaigns.sh` and `decision_phase2.yaml`,
because `used_gb()` now also counts the 5.7 GB venv and the HF cache against a
campaign that stages 37.7 GB.

**Campaign 1 is running — Step 13 has started.** Four more DGX-only bugs had to
be fixed first, each fatal to a submit: shell scripts tracked as 100644 (exit
126 on `stage_data.sh`), rclone unreachable because a batch shell never sources
`.bashrc`, a HuggingFace fork/Hub deadlock that hung the trainer at batch 1 of
8218 with 15 seconds of CPU in ten minutes, and — the worst of them — staging
`code` from R2 silently reverting five tracked files mid-session, including the
rclone resolver that the same script needs to run. All four are fixed in
23ceade, 6f15ca3, 74f2a8b and 7d3602d.

**The account may hold ONE GPU at a time** (`gres/gpu=1`), and a MIG slice
counts the same as a full A100. Six per-task shards were submitted across six
idle slices; five pended on `AssocGrpGRES`. All 312 runs are sequential, which
Parts 4-7 of the schedule do not assume. The sharding was kept anyway because
Slurm then starts each task's job back to back with no babysitting.

Measured: **4.88 it/s, ~28 min/epoch** for BioClinicalBERT on a `4g.20gb`
slice; 20 epochs with patience 5 puts campaign 1 at **5-9 days**. The remaining
five tasks are queued on a dgxb full card, which is the right node for text
because `task_dataset.py:334` reads the parquet once into memory -- rule 2's
28x NFS penalty is a per-sample-read problem and text has no per-sample reads.

**Next:** `peak_gpu_gb` off the first finished epoch, then campaign 2.

### Session 12 (continued) — 2026-08-31 — campaign 1's first task, and a wrong model

**A1 finished all six runs** on a dgxa `a100_4g.20gb` slice (job 22339, 1 d 09 h
wall). Numbers are in Step 8 above. The useful measurements:

* **`peak_gpu_gb` = 7.814** for BioClinicalBERT, constant across every epoch of
  every run. It fits a 10 GB `a100_2g.10gb` slice; it does not fit a 5 GB one.
* **Early stopping fires at 9–11 epochs**, not 20, so a BERT run costs
  **~4.3–5.3 h** on a 20 GB slice rather than the ~9.7 h a full schedule would.
* Epoch time was *dead* steady: 1746.7 / 1745.3 / 1748.3 / 1747.3 seconds.

**The dgxb plan failed, and the reason matters more than the plan.** The swap
watcher ran its full 24 h and saw `dgxb_full_cards_busy=5/5` on every check.
The two faculty jobs we were waiting on did finish — and the same faculty user
immediately took both cards again (22308/22309). **dgxb's full A100s churn back
to faculty; waiting for one as a student is not a strategy.** The watcher
itself behaved correctly: no GPU held, honest logging, clean TIMEOUT, and the
training was never disturbed.

**Then the tf-idf finding.** The six runs came back like this:

```
text_bioclinicalbert seed_42  epochs=10 best_macro_AUPRC=0.3931 hours=4.84 peak=7.814
text_tfidf           seed_42  epochs=10 best_macro_AUPRC=0.3931 hours=4.84 peak=7.814
```

Identical to four decimals, in a model that should be orders of magnitude
cheaper. The logs are genuinely different files written a day apart, so these
were two real runs — of the same model. Cause and fix are in the header's
stop-the-line note and in commit 1e266f2. The short version: configs name
encoder classes, the plan lower-cased the class name, and the model builder
treated "not exactly tfidf" as "use BERT".

**What that costs:** 18 runs across 6 configs. Three are done, invalid, and
already in `r2-results`. The five queued shards were cancelled before they
could add 15 more.

**What it does not cost:** the BERT tier. `BioClinicalBert`.lower() happens to
equal the expected token, so those runs used the right model and their numbers
stand.

**Lesson worth keeping:** the bug was invisible from every angle the pipeline
checks — no crash, no warning, checksums fine, audits fine, and each run wrote
a `train_config.yaml` that faithfully said `encoder: TfidfTextEncoder`. What
caught it was two tiers agreeing to four decimal places. **Cross-tier
comparisons are a correctness check, not just a result.** Consider asserting in
`31_eval.py` that two different arch tiers never produce bit-identical metrics.

**Open, for the next session:**

1. Decide the re-run scope for the tf-idf tier (18 runs, ~2–3 h each once it is
   actually a TF-IDF model, so far cheaper than the BERT runs).
2. Remove the three invalid `text_tfidf` run directories from `r2-results`.
3. Re-submit campaign 1's remaining five tasks (A3, A5, A6, B4, B5). Use a dgxa
   slice — `a100_4g.20gb` if free, `a100_2g.10gb` otherwise, since 7.814 GB
   fits. Do not wait for dgxb.
4. Ask the facility to raise `gres/gpu` above 1.

### Session 13 — 2026-09-08 — a status read of the DGX after five unattended days

Nothing was trained by this session; it read the machine, found two stalls, and
restarted one of them. The gap since 2026-09-03 was unattended, and the campaign
survived it — but not intact, and the reasons are worth recording.

**Campaign 1 stands at 20 of 36 runs pushed to `r2-results`.** A1, A3 and A6 are
complete at six runs each (both tiers, three seeds); A5 has two; B4 and B5 have
none.

| Task | Training                                             | Evaluation                                   |
| ---- | ---------------------------------------------------- | -------------------------------------------- |
| A1   | 6/6                                                  | **DONE**, CSV + extras in `r2-results/results` |
| A3   | 6/6                                                  | tfidf 312/2,940 units (22854); bert 90/2,940 |
| A6   | 6/6 (job 22736, 13 h 34 m, finished 07:42 UTC today) | bert 46, tfidf 56 (22838/22839)              |
| A5   | 2/6                                                  | not started                                  |
| B4   | in flight (22737)                                    | not started                                  |
| B5   | 0/6, pending                                         | not started                                  |

**Stall 1 — `c1_A5` (22735) died on the wall clock, not on an error.**
`sacct` says `FAILED` after `3-23:54:51` against a `4-00:00:00` limit. The log's
last line is `--- train A5_cross_modal_verification / text_bioclinicalbert /
seed 456 ---`, so the shard had pushed A1's and A3's fourteen runs and was four
runs from done. The skip-completed guard means the resubmission (22853) will
re-enter at that seed rather than retraining the twenty finished runs — the
guard added on 2026-09-01 is what makes this cheap instead of catastrophic.

**Stall 2 — A3's BioClinicalBERT evaluation had no job at all.** Its checkpoint
was last written 2026-09-04 23:36 at 90 units and nothing has touched it since;
jobs 22733/22734 TIMEOUT'd at their 24 h limit that night and only the tf-idf
half was ever resubmitted. **Resubmitted this session as 22859** (`cpu_student`,
12 cores, 7-day limit), pending on `AssocGrpCpuLimit`. It will resume at unit 90.

**🔴 THE CPU CAP IS NOW THE BINDING CONSTRAINT, and evaluation is what is
holding it.** The account is `cpu=32,gres/gpu=1,mem=256G`. Four jobs at 8 cores
each — one training (22737) and three evaluations (22838, 22839, 22854) — sit
at exactly 32, so **`c1_A5` (22853) and `c1_B5` (22738) are both pending on
`AssocGrpCpuLimit`, and so is the eval just submitted.** This is the inverse of
the problem the 2026-09-01 move to `cpu_student` solved: evaluation no longer
blocks training by holding the GPU, it blocks it by holding the cores. The move
was still right — the GPU was idle for the whole of those hours — but the new
sizing (12 cores per eval, commit ddfdd7e) makes a training shard and three
evals mutually exclusive on a 32-core cap. **Ask the facility to raise `cpu`
before `gres/gpu`.** Until then, `TRIMODAL_EVAL_CPUS` is the throttle: at 4
cores an eval and a training shard coexist comfortably.

**A6's two evaluations will TIMEOUT in ~21 hours.** 22838/22839 carry a
`1-00:00:00` limit — they were submitted at 07:42 UTC by the campaign body as it
stood *before* ddfdd7e reached the DGX checkout, which is also why they show 8
cores and not 12. The checkpoint makes that survivable; they need resubmitting
afterwards, and nothing resubmits them automatically.

**A3's evaluation is the schedule risk, and it is now measured rather than
feared.** 2,940 units against A1's 300. The tf-idf half did ~312 units in about
24.5 h of wall clock, and the rate decelerates by construction (`as_completed`
returns cheap subgroup slices first and the pooled `overall` slices last).
Straight-lining the *early* rate gives ~10 days per tier and the true figure is
worse. Two tiers of A3 alone can cost more than all of campaign 1's training.

**Scale check on what remains.** `campaign_runs.py --table` is unchanged at
**104 configs / 312 runs**; 20 are done. Campaign 1 owes 16 runs and 10 of its
12 (task, tier) evaluations. **Campaigns 2–14 are 276 runs and have not
started** — and campaign 1 is the *cheapest* family, with no per-sample reads
and a 7.8 GB peak. Parts 4–7 of the schedule below read "~1 week" per part;
nothing measured on this machine supports that under `gres/gpu=1`.

**Unchanged and still open from session 12:** open question 15a (the mid-epoch
piece fetch is implemented but has never run, and campaigns 6, 8 and 9 need it);
the signal/image/fusion smoke tests, which smoke in front of the campaign that
stages their data; and the four remaining audits — `threshold_audit.md`,
`calibration_audit.md`, `sensitivity_audit.md`, `reproducibility_audit.md`.
The facility's `CANCELLED by 0` of four queued jobs on 2026-09-02 has still not
been explained by anyone.

**Actions taken this session, and what they corrected.** The eval sizing was
changed and the four stalled/mis-sized evaluations were put back on the machine:

* **`TRIMODAL_EVAL_CPUS` defaults to 4, not 12** (commit c01d5ba), in both
  places it is written — `_campaign_body.sh`'s override, which is the path a
  campaign uses, and `eval_task.sbatch`'s own header, which is what a
  hand-submitted eval gets. `31_eval.py` sizes its pool from
  `SLURM_CPUS_PER_TASK`, so **an eval now takes roughly three times as long**.
  That is the right side to lose on: evaluation runs beside the next task's
  training and is off the critical path. Raise it for a lone eval with nothing
  queued behind it.
* **All four campaign-1 evaluations now run at 4 cores with a 7-day limit**:
  22860 (A6/bert, resumed at unit 54), 22861 (A6/tfidf, 59), 22862 (A3/bert,
  90), beside 22854 (A3/tfidf, still 8 cores from its pre-change submit).
  Checkpoint line counts were compared before and after every cancel and were
  identical — a cancelled eval loses only the units in flight.
* **`scontrol update jobid=... NumCPUs=4` on a PENDING job does not survive
  dispatch.** It reported success, `scontrol show job` read back `NumCPUs=4`,
  and the job then started holding **12**. Only a fresh `sbatch` picks up a new
  size. That is why 22859 was cancelled and resubmitted as 22862.
* **`stage_data.sh` needed no R2 re-upload for this change**: a git checkout
  wins over the bucket's `code` copy (2026-08-30), so the next campaign's
  staging will not revert it.

**A correction to the CPU-cap diagnosis above.** Freeing cores does **not**
release `c1_A5` (22853) or `c1_B5` (22738). Both also need the account's single
GPU, which `c1_B4` (22737) holds for up to another four days — `gres/gpu=1` is
the real limit and `AssocGrpCpuLimit` was merely the first one Slurm named.
**A5 starts when B4 ends, not when cores free.** So the evaluations were not, at
that moment, blocking anything that could otherwise have run. The 4-core change
still matters for every campaign after this one, where the body submits its
evals while the *next* training shard is genuinely runnable — and it removes a
deadlock that would have bitten as soon as the GPU cap is raised.

### Session 14 — 2026-09-28 — a read-only check after twenty unattended days

Nothing was changed on the DGX or in R2. The machine had been **idle since
2026-09-16**: the GPU since `c1_A5` (22853) finished 2026-09-13, the CPU since
the A5 evals (23093/23094) finished 2026-09-16. Nothing resubmits a job that
dies, so every stall below sat for about two weeks.

**What finished between 09-08 and 09-16.** `c1_B5` (22738, 6 h 22 m) and
`c1_A5` (22853, 25 h, re-entered at seed 456 as designed). Evals: A6 both tiers
(22860/22861), B5 both (23087/23088, ~3 h each), A5 both (23093/23094, ~2.3 d).
`31_eval.py` also wrote `audit_reports/threshold_audit.md` (1,157 lines, every
threshold `selected_on_split = val`) — untracked on the DGX, not in R2.

**What died.** `c1_B4` (22737) hit `3-23:54:55` of 4 days mid-seed-456 BERT
(epoch 3, batch ~80k/101k); `checkpoint_last.pt` is present, so a resubmit
resumes. A3's evals hit the 7-day wall: tfidf 903/2,940 units, bert 571/2,940.
At 4 cores that is ~480 units per 7 days on the decelerating curve, so **A3
needs several more 7-day evals per tier**; with nothing else on the CPU they can
run at 12 cores each (8 + 12 + 12 = 32 with B4 training).

**Verified.**
- 32 `run_summary.json` all `complete`, 3 seeds each; DGX checkout at 7845778,
  same as `main`.
- Result CSVs A1/A5/A6/B5: `rclone check` against `r2-results` — **9 of 9
  identical**. Every row `n_seeds=3`; every pooled point inside its CI; all
  blank CIs (A5 80, B5 122) are single-class slices where AUROC/AUPRC are
  undefined, none a failure.
- 96 per-run files (test predictions, logs, configs, `checkpoint_best.pt`)
  match R2.

**🔴 Found: `push_results.sh` artifact list is wrong.** It copies
`threshold.json` and `metrics.json`; the trainer writes `thresholds.json`,
`run_summary.json` and `val_predictions.parquet`. **None of the three has ever
reached R2 for any run** (`rclone check --one-way`: 99 missing, 96 of them
these). The checkpoints are already deleted locally, so the DGX copy is the only
copy of the val predictions the thresholds and calibrators were fitted on — the
calibration, threshold and reproducibility audits need them. Fix: correct the
list at `push_results.sh:59-60`, then re-run `push_results.sh` (additive) to
backfill. `.eval_checkpoints/` (weeks of bootstrap work, 1.2 MB) is also
excluded from every push and should be backed up somewhere.

**Noted, not bugs.**
- **A5/B4 text tiers are at chance by construction** (A5 test AUROC 0.5000
  BERT, 0.4998 tf-idf). The label is "does this report belong to *that* ECG",
  and a text-only model never sees the ECG. BERT collapsed to a constant
  (val AUPRC = 2/7, AUROC = 0.5 exactly, best epoch 0 on every seed); tf-idf
  is noisy chance. It is the unimodal floor the fusion tiers are measured
  against — say so in the paper.
- **B4 BERT reproduces A5 BERT loss-for-loss** (same rows, seeds, config — the
  verification head is the only head a text tier has). Each is ~36 h of GPU.
  Scope rule keeps both; worth knowing when estimating.
- `run_summary.n_epochs_run` counts only post-resume epochs (A5 seed 456 says
  3; its log has 6). Cosmetic.
- ECE is high on A1/A6 (0.14–0.32), as expected from pos-weighted BCE; §6's
  calibrators should be reported beside it.

**Actions later the same day (owner approved).** `push_results.sh` fixed and
pulled on the DGX (7128da3); backfill pushed 32 runs, 0 failures — `rclone
check` now 192 matching, only the placeholder `model_runs/README.md` differs.
Resubmitted `c1_B4` (24622, resumed mid-epoch as designed) and both A3 evals.
The first A3 pair (24623/24624, 12 CPU, `eval_task.sbatch`'s default 32G) was
**OOM-killed** — 12 workers need ~35 GB — and was resubmitted at `--mem=96G`
(24625/24626) with checkpoints unchanged (903 / 571 lines). Two `afternotok`
continuations per tier are queued so a TIMEOUT resumes on its own.
**Trap:** raising `--cpus-per-task` on an eval without raising `--mem` OOMs it.

### Session 15 — 2026-09-30 — reading back the campaign 2 pre-flight

Read-only: nothing submitted, cancelled or pushed. Git on the DGX is at 7128da3
(docs-only behind `main`).

**Campaign 1.** `c1_B4` 24622 COMPLETED 2026-09-29 14:56 (23 h 20 m): **36/36
runs done.** Its body submitted the B4 evals at 4 CPU / 32G: tf-idf 24760 at
50/60 units (hours left), BERT 24761 at 10/60 (~3-4 d). The A3 evals were
re-submitted a third time after session 14 at **8 CPU / 64G** (24633 tf-idf,
24636 BERT; 24625/24626 cancelled), continuations 24634/24635, 24637/24638
chained `afternotok`. Units restarted counting at 2,037 / 2,369 remaining.
After 39 h: tf-idf 170, BERT 100 — and decelerating (last 10 units took 4.3 h
and 7.5 h). **Extrapolated: tf-idf ~34 days, BERT ~70 days.** That is 5-10
more 7-day continuations per tier than are queued; the eval method for A3
(2,940 bootstrap units) needs rethinking, not more wall clock.

**Campaign 2 pre-flight (`~/c2test/`, outside the repo; outputs under
`outputs/model_runs/_dev/c2test*`, 2.4 GB).**
- 24639 `c2_test_cpu` (8 CPU, 52 min, COMPLETED): stage `2 --phase train` and
  `--phase eval` both PASS, 19.0 -> 20.2 GB of 49. Real-data 20-step runs:
  **A1/A3/A6 exit 0**, A1 test predictions written; **A5/B4 exit 1**.
  `smoke_test.py --tiers image` failed 8/10 — only because the smoke harness
  uses **lead2** image configs and campaign 2 stages only 12-lead
  (`clean_lead2_shard_000.tar` missing). Not a code bug; the smoke test cannot
  be run inside a single-layout campaign's staging.
- 24640 `c2_test_gpu` (a100_4g.20gb slice on dgxa, 1 h 38 m, FAILED on A5/B4):
  400 steps each, bf16. **A1/A3/A6 peak_gpu_gb 10.82** — fits the 20 GB slice
  with room. ~3.0 it/s. Epoch = 4,109 (A1) / 4,614 (A3, A6) steps; 400 steps +
  full val took 25 / 33 / 28 min.
- **🔴 A5/B4 image tier: `FileNotFoundError ... images/scanlike_12lead_shard_017.tar`.**
  Verification tasks pick the rendering per row (`image_type_column`,
  `task_dataset.py:524-528`), so the scan-like positive rows need
  `image_scanlike_12lead` for train and val. R2 has only
  `images_scanlike_test` (18.9 GiB, test split, both layouts). Full
  `scanlike_12lead` is 62.3 GB — over the 49 GB ceiling alone. Affects
  campaign 2 and 3 (A5/B4 image, 6 runs each) and every fusion campaign that
  trains A5/B4 with images (7, 8, 12, 13). Fix needs the data machine: a
  derived `images_scanlike_{12lead,lead2}_trainval` subset of only the A5/B4
  anchors (like `make_subsets.py` did for L3), uploaded and added to those
  campaigns' dataset lists in `campaigns.sh`.
- `c2_images12` 24641 (`gpu_student`, 4g.20gb slice, dgxa, 7 d) is **held**
  (`--hold`), dependency on 24640 already satisfied.
  `campaign_runs.py` takes `--tasks`, so campaign 2 can run A1/A3/A6 (9 runs)
  now and A5/B4 later.

### Session 16 — 2026-09-30 — open question 16, closed end to end

On the **`data-laptop`** (`.machine`, new this session). Nothing was submitted,
cancelled or polled on the DGX. The session ran in two halves: measure and stop,
then — once the user chose chunking — build, upload, verify and rewire.

**1. The measurement that killed the original plan.** The task was to cut an
`images_scanlike_{12lead,lead2}_trainval` subset the way `make_subsets.py` cut
the L3 sets. It is not a subset:

- A5 and B4 carry the **same** row table, and `image_type == 'scanlike'` is
  exactly **one row per anchor**, always `y_match == 1`; the other six rows per
  anchor are `clean` (one positive + five negatives).
- Every study in the split is an anchor, so the scan-like study set **is the
  split**: train 523,945, val 75,525, test 149,642 — **599,470 of 749,112
  studies (80.0 %)** for train+val.

| kind                   | KiB/study | train    | val     | **trainval** | test     |
| ---------------------- | --------- | -------- | ------- | ------------ | -------- |
| `image_scanlike_12lead`| 80.8      | 43.77 GB | 6.31 GB | **50.08 GB** | 12.52 GB |
| `image_scanlike_lead2` | 50.1      | 27.30 GB | 3.94 GB | **31.24 GB** | 7.81 GB  |
| `image_clean_12lead`   | 10.8      | —        | —       | —            | —        |
| `image_clean_lead2`    | 22.5      | —        | —       | —            | —        |

The method cross-checks: 12.52 + 7.81 = 20.33 GB = **18.93 GiB**, which is the
18.9 GiB `images_scanlike_test` measured in R2 after it was independently built.
The size is a format difference — scan-like is **JPEG RGB** at the same pixel
size as clean (1016x504 / 1600x333) while clean is PNG, so 12-lead scan-like
costs **7.5x** per study. The 12-lead train+val container alone is larger than
the entire 49 GB ceiling, so nothing was built and the numbers went to the user.

**2. The user chose chunking**, with the instruction to let the run wait while
old pieces are deleted and new ones come down from R2.

**3. Deriving what each campaign REALLY reads, instead of trusting the table.**
This is the check that should have existed before any of this: for every
campaign, the union of `modality_kinds_read()` over its configs — which reads
the ROW's `image_type`, not the config's `input_modality`. It found the
scan-like gap in **2, 3, 8, 11, 13, 14** and **three more bugs of the same
shape**:

- **campaign 10** staged no clean-image container at all, though its A5/B4
  scan-like runs read one for their clean rows;
- **campaign 11** trains A5 and B4, which are **not** L3 tasks, against
  `signals_12lead_L3` / `images_clean_12lead_L3`;
- `upload_data.py --all` looped `range(1, 12)` — a leftover from before the
  Lead-II split — so it had never uploaded campaigns 12-14's datasets.

`TaskDataset.modality_kinds_read()` now exists as the single place that answers
the question, and the chunk-cycling decision uses it too.

**4. The size table is measured now, not maintained.** `upload_data.py --sizes`
reports every campaign's train/eval residency from the files on disk, applying
the same phase filter `stage_data.sh` applies and counting two resident pieces
for a chunked dataset. The hand-maintained numbers were wrong in **both**
directions: campaign 12 listed 29.4, measured **33.7**; campaign 9 listed 18.5,
measured **12.7**; campaign 7 listed 37.7, measured **40.5** — over the ceiling,
which nobody knew.

**5. What was built.** All at p8, all aligned:

| dataset | bytes | for |
| --- | --- | --- |
| `images_scanlike_12lead_pieces` | 43.77 GB | 2, 8, 11 |
| `images_scanlike_12lead_valtest` | 18.84 GB | 2, 8, 11 |
| `images_scanlike_lead2_pieces` | 27.30 GB | 3, 13, 14 |
| `images_scanlike_lead2_valtest` | 11.80 GB | 3, 13, 14 |
| `images_clean_lead2_pieces` | 12.53 GB | 13, 14 |
| `images_clean_lead2_valtest` | 5.32 GB | 10, 13, 14 |
| `signals_lead2_preprocessed` / `_raw` | 12.6 GB (re-upload, see below) | 4, 12, 13, 14 |

`make_chunks.py plan` reports fairness PASS with piece sizes within **0.40 %**,
and **0 of 523,945 studies disagree** with the `preprocessed_12lead`,
`image_clean_12lead` and `raw_12lead` cuts — the assignment is
`blake2b(salt|study_id) % 8`, so piece *k* covers the same studies in every
modality without the cutters ever coordinating. That is what lets one resident
window serve a fusion batch.

`signals_lead2_preprocessed` / `_raw` are the same two files under separate
dataset names: campaigns 12/13/14 read only the preprocessed copy and had been
staging the 6.08 GB raw one for nothing. **They were expected to cost no upload
and did not**: a remote key is `<dataset>/<path>`, so each landed under a new
prefix and both files were pushed again (12.6 GB). `signals_lead2/` is now
unused, and was kept for the same reason as `signals_12lead_L3`.

**6. Proved by round trip, not asserted.** Two real pieces were staged exactly
as `stage_data.sh` stages them (`<DATA_ROOT>/<base>/piece_NNN.tar`),
`install_overlays()` was run, and `read_modality()` returned payloads
**byte-identical** to the base shards for every sampled study, while studies
outside the resident window still resolved to the base container.

**7. Two mechanisms had to change.**

- **`ChunkCycle.ensure()` evicted AFTER it fetched.** `windows()` hands out
  disjoint pairs, so a swap held the outgoing pair and the incoming pair at
  once — **four** pieces where the campaign is sized for two, 21.9 GB instead
  of 10.9 on the 12-lead scan-like cut. It now evicts first and waits with
  nothing resident while the next pair comes down. It also seeds its idea of
  what is resident from the **disk**, so a run resuming after a crash does not
  stage on top of the dead run's pieces.
- **`val_mode=on_demand`** for campaigns 8 and 11. They hold 27.4 GB of
  training data and need a further 15.1 GB of val containers; 42.5 GB does not
  fit. The trainer now evicts the pieces at the epoch boundary, stages
  `*__val.*`, validates, and drops it again (`trainer.py::_evaluate_val`,
  `campaigns.sh` phases `train_only` and `val`, `evict_data.sh --split`). One
  val fetch per epoch buys 15 GB. Every other campaign keeps val resident.

**8. Chunk cycling is decided PER RUN.** `chunked=yes` only means the campaign
stages pieces; a run cycles only if it reads a kind actually staged as pieces
(`chunk_pieces.chunked_kinds()` against `modality_kinds_read()`). Campaign 2
stages clean 12-lead **whole** and scan-like as **pieces**, so A5/B4 cycle and
A1/A3/A6 do not. Without this, marking campaign 2 chunked would have silently
changed the sampling regime of nine already-planned runs — each window sees 2 of
8 pieces — which is a scientific change, not a staging detail.

**9. Campaigns 5 and 7 switched to the full-cohort 12-lead pieces.** Measured,
`signals_12lead_L3` is **35.35 GB** resident, which put campaign 7 at 40.5 GB
and campaign 5 at 36.4 with 0.4 GB to spare. The full-cohort pieces are a
superset, already cut and already uploaded, and cost 13.7 GB for two.
**`signals_12lead_L3` is now unused.** It is deliberately KEPT in R2 rather than
deleted — it cost a night to upload, it is ~$0.53/month, and deleting data while
unattended is not a call to make on my own. It is listed in the R2 inventory
below as retained-but-unused.

**10. Two other fixes, found while verifying.** `max_steps_per_epoch` was
applied to a **flattened copy** of the epoch plan while `_run_windows` iterated
the original, so the cap only moved the progress-bar total; `_epoch_plan` now
truncates the plan itself. **No paper number is affected** — the flag defaults
to 0 and no campaign script passes it — but **session 15's pre-flight timings
are one full epoch, not 400 steps**: a full A1 epoch on an `a100_4g.20gb` slice
is **~25 min including validation**. And `build_tiny_trainer` never fitted the
TF-IDF vectoriser, so three crash-recovery checks could not run at all on the
one tier whose encoder was silently wrong once already (1e266f2).
`smoke_test.py` also follows the staged image layout now instead of hard-wiring
Lead-II, which is what produced session 15's 8/10 FAILs inside campaign 2.

**11. The three machines.** An untracked one-word `.machine` at the repo root
(`data-laptop` / `campus-laptop` / `dgx`), already covered by `.gitignore`'s
`/*` so a pull cannot overwrite it; an `AGENTS.md` section on what each machine
may and may not do; and an explicit git contract — **pull `--ff-only` before
reading this doc, push before the session ends, the DGX pulls and never
commits.** `CLAUDE.md` carries the short form so it is injected every session.
`docs/CAMPUS_LAPTOP_HANDOVER.md` is the operating manual for the other two
machines and carries a ready-to-paste prompt.

**12. Then the same question was asked of every campaign, and four more
answers came back wrong.** The scan-like gap was not a one-off: a campaign's
dataset list was written from what a config *names* (`input_modality`), and
that is not what a run *reads*. Deriving the reads properly — resolving A5/B4's
per-row `image_type`, and asking which cohort each campaign's tasks actually
train on — found:

- **campaign 10 staged no CLEAN container**, the mirror image of the original
  bug: its A5/B4 scan-like runs read a clean image for their clean rows;
- **campaign 11 trains A5 and B4, which are not L3 tasks**, against
  `signals_12lead_L3` / `images_clean_12lead_L3`, so every study outside the L3
  cohort would have missed;
- **campaign 7 was over the ceiling at 40.5 GB** on measured sizes while the
  table claimed 37.7, because `signals_12lead_L3` is 35.35 GB resident;
- **`upload_data.py --all` looped `range(1, 12)`**, a leftover from before the
  Lead-II split, so it had never uploaded campaigns 12-14's datasets.

Campaigns 5 and 7 now read the full-cohort 12-lead pieces instead of the L3
subset — a superset, already cut and already uploaded, 13.7 GB for two resident
pieces against 35.35 GB whole. `signals_12lead_L3` is consequently unused.

**13. `check_campaign_data.py` is the guard so this class of bug cannot come
back.** For each campaign it derives the (modality kind, split) pairs its
configs will actually ask `read_modality()` for, plus whether any run reads
text and whether the cohort is L3 or full, and checks the hand-written dataset
list covers all of it. The dataset list stays hand-written — it encodes a
storage decision (whole container, subset, or pieces) that no introspection can
make — but whether that choice covers the reads is now checked. **Its
`--selfcheck` replays the three historical failures and asserts each is
rejected**, so a check that quietly stops working fails loudly instead.
**15/15 campaigns pass.**

**14. Open question 17: the scan-like image tier TRAINS.** `campaign_runs.py 10`
emits 30 training runs and the body trains them, but the campaign staged the
test split only and the execution plan called it "the sweeps that only need
re-testing". Settled against the binding documents:

- **§5.3** turns image augmentation on "when **training on** scan-like or mixed
  clean+scanlike" and off for clean-only training, and `model_configs.py:145`
  emits exactly that — `augmentation: true` on every `*_scanlike` config and
  `false` on every `*_clean` one. `build_image_transform` applies augmentation
  **only when `split == "train"`**, so the setting is meaningless otherwise.
- It is the image-side analogue of **§7.3's B2 regimes**, where regime_1
  (clean-trained) and regime_2 (corruption-augmented) are **both** trained arms.
- Its 30 runs are part of the **104 configs / 312 runs** the spec counts.
- The **Truth doc §6.1** makes the scan-like image **"Positive type 2"** of the
  verification task — training data — which is exactly what `image_type_column`
  implements.

So the execution plan was wrong and is corrected (its Step 23 and its upload
table). Campaign 10 is **split by lead subset** exactly as 7/8/11 were into
12/13/14: **10 is the 12-lead half, 15 the Lead-II half**, 5 configs and 15 runs
each. `--table` still reports **104 configs and 312 runs**. Both stage the clean
container too. **No new data was needed** — they read what question 16 built.
Locked in spec **§12.10**.

**15. Storage on this laptop is now unambiguous.** D: holds what Phase 1 built;
C: holds everything derived from it; R2 holds what the DGX reads. The C:
directories are reached from D: through **junctions**, so the default roots
resolve to the real data and `TRIMODAL_CHUNK_ROOT` / `TRIMODAL_DERIVED_BASE` are
no longer needed to run anything locally. That also closed trap 21: four
`*_valtest` containers had been uploaded and then deleted from D: to free space,
leaving their overlays pointing at files that were not there, so every local
val/test read of 12-lead clean images, 12-lead int16 signals and raw 12-lead
signals failed. All three read correctly again. `data/processed/chunks` held
four stale plan files duplicating C:, now a junction to the real cuts. The local
copy of `raw_12lead__train__p8` (28 GB) was deleted after comparing its objects
name-for-name and byte-for-byte against R2; its 1.4 KB `checksums.json` was kept
so `--sizes` can still measure campaign 9 from the manifest.

**Everything run on this laptop, all green:**

| check | result |
| --- | --- |
| `campaigns.sh selfcheck` | PASS |
| `chunk_cycle.py` self-check | PASS, including the new peak-residency property — a swap never holds more than two pieces |
| `make_chunks.py plan` (both scan-like kinds, clean Lead-II) | fairness PASS, piece sizes within 0.40 %, **0 of 523,945 studies disagree** with the three existing cuts |
| piece round trip | PASS — `read_modality()` byte-identical to the base shards, studies outside the window still on the base container |
| `check_campaign_data.py` | **15/15 campaigns stage what they read** |
| `check_campaign_data.py --selfcheck` | PASS — all three historical failures rejected |
| `upload_data.py --sizes` | every campaign fits both phases; thinnest is campaign 8/11 at +5.7 GB |
| `smoke_test.py` block [1] | green for all six tier families |
| the four staging phases | `train`, `train_only`, `val`, `eval` all filter correctly against a fake DATA_ROOT |

**One bug was caught by re-reading rather than by a test, and it would have
been fatal:** after the val swap evicts the pieces, a chunk cut's
`checksums.json` lists eight files that are all legitimately absent, which
tripped `stage_data.sh`'s "the manifest lists files but NONE of them are on
disk" guard — a guard that exists to catch a fetch which silently moved
nothing. It would have failed the val swap at the first epoch boundary on
campaigns 8 and 11, **and the eval phase of every chunked campaign**, which has
never run. The cut's manifest is now skipped outside the train phases.

**Closing (17:40 IST): every upload finished and every check is green.** The
background orchestrator cut and verified `image_clean_lead2` p8 and
`images_clean_lead2_valtest`, both Lead-II round trips PASSed, and all five
image datasets uploaded. **Off plan:** `signals_lead2_preprocessed` / `_raw`
FAILED first time — their files are on D: and the resume recipe put
`TRIMODAL_UPLOAD_STAGE` on C:, and a hard link cannot cross volumes. Re-run with
the stage on D:. They were also meant to cost no upload but landed under new
prefixes (remote key is `<dataset>/<path>`), so 12.6 GB went up again and
`signals_lead2/` is now unused; `rclone check` confirms both copies byte-for-byte.
One attempt died on a DNS failure and resumed cleanly. **R2 is 350.3 GiB / 664
objects.** Final checks: `check_campaign_data.py` 15/15 and `--selfcheck` PASS;
`--sizes` all 15 OK with nothing `missing` (peaks 1.2–31.1 GB, thinnest 8/11 at
+5.7 GB, 3/15 at +5.8); `verify_piece_roundtrip.py image_clean_lead2` PASS;
`smoke_test.py --tiers signal --skip-train` PASSED; `campaigns.sh selfcheck` and
`chunk_cycle.py` PASS. `docs/SESSION16_RESUME.md` deleted.

**Addendum, 2026-10-05 — R2 audited against what every campaign stages.**
`--sizes` and `check_campaign_data.py` both read LOCAL files, so neither proves
the bucket. One listing of `r2:trimodal-data` was compared against
`dataset_files()` for every dataset of all 15 campaigns: each expected key
present, each byte size equal to the local file, and each directory's checksum
manifest present. **All 20 data datasets PASS** (`signals_raw_pieces` has no
local copy any more and was checked by presence: 11 objects, 29.20 GB). The only
differences were `code` and `configs`, whose bucket copies predated session 16.
A git checkout skips them (`stage_data.sh`), so no run was at risk, but the
`TRIMODAL_FORCE_CODE_STAGE=1` fallback would have reverted every staging fix of
this session. Both were re-uploaded from `5b1a2e0` (1.7 MB) and the audit
re-run: **PASS, 22/22**. They go stale again with the next commit that touches
`scripts/` or `config/`, which is why git stays the source of truth.
**Nothing is left to do on the data laptop.** Next action is on the campus
laptop: `docs/CAMPUS_LAPTOP_HANDOVER.md` §0, then cancel held job 24641 and
submit campaign 2 fresh.

**Addendum 2, 2026-10-05 — the record for the other machines.**
`docs/SESSION16_POSTMORTEM.md` is new: the 20 things that went wrong across
sessions 15–16, each with its fix, the checks that now guard them, eight rules
for later sessions, and the four things still unproven on the DGX. The R2 audit
is now a script, `scripts/dgx_portability/check_r2_complete.py`.
`docs/CAMPUS_LAPTOP_HANDOVER.md` was corrected (six cuts not five, the thinnest
campaign, a broken line continuation in the sharded `sbatch` example) and its
§6 prompt now stops after campaign 2's first piece swap instead of running down
the queue.

### Session 17 — 2026-10-05 — `campus-laptop`: campaign 2 submitted for real

Ran the CAMPUS_LAPTOP_HANDOVER §6 prompt. Local pull to `71bde63`, `.machine`
= `campus-laptop` (already set).

**1. DGX state (11:11 UTC).**
- `c1_B4` 24622 COMPLETED 09-29. B4 evals **done**: 24760 tf-idf COMPLETED
  09-30 14:32 (23 h 37 m), 24761 BERT COMPLETED 10-01 20:36 (2 d 5 h 41 m).
  `outputs/results/B4_cross_modal_verification.csv` written; y_match AUPRC
  ~0.1997-0.1998 for both text tiers (chance floor, as expected for A5/B4 text).
- A3 evals: **24633/24636 NODE_FAIL** at 2026-10-04 20:07 after 6 d 4 h
  (dgxa node failure). Slurm requeued both onto dgxb; the requeued attempt ran
  14 h and ended FAILED (exit 0:53) at 10-05 10:10, which fired the
  `afternotok` continuations **24634 (tf-idf) and 24637 (BERT), now running on
  dgxb** (8 CPU / 64G). Resumed at **tf-idf 1,512 / 2,940** and **BERT 1,071 /
  2,940** units. Rate 09-30 -> 10-05: ~86 and ~80 units/day, so roughly
  **~17 d (tf-idf) and ~23 d (BERT)** left — better than session 15's
  extrapolation, but more than the two 7-day continuations each that remain
  (24634+24635, 24637+24638). Expect one more resubmit per tier. A3 rethink
  (post-mortem §5) still open.
- dgxa back up (`mixed`).

**2. DGX pull — the token is dead.** `git pull --ff-only origin main` on the
DGX: `remote: Invalid username or token. Password authentication is not
supported`. The credential helper is `store --file ~/.git-credentials-trimodal`
(in `~/.gitconfig`). Not touched. Workaround used, which keeps git the source of
truth (same commit hashes, fast-forward only):

```bash
# campus laptop
git bundle create "$TEMP/claude/main.bundle" <dgx HEAD>..main
scp.exe <that file> mudgx:/dgxa_home/se23ucse027/main.bundle
# DGX
cd ~/se23ucse027 && git bundle verify ~/main.bundle &&   git pull --ff-only ~/main.bundle main && rm ~/main.bundle
```

DGX went 7128da3 -> **71bde63**; no tracked changes on the DGX. `.machine`
was missing there and is now `dgx` (ignored by `.gitignore:12`).
**User action: put a fresh GitHub token (read-only, this repo) in
`~/.git-credentials-trimodal` on the DGX.**

**Checks on dgxa (srun job 25574, cpu_student):** `campaigns.sh selfcheck`
PASS; `chunk_cycle.py` PASS; `check_campaign_data.py` **15/15** campaigns stage
what they read; `--selfcheck` PASS (replays campaigns 2/10/11's failures).

**3. Dry run (job 25575):** `stage_data.sh 2 --pieces 0 1 --dry-run` ->
`quota OK: 19.79 GB used + 27.9 GB for campaign 2 (images_12lead), train phase
<= 49 GB ceiling` (47.7 GB, 1.3 GB margin). Would stage `code configs tasks
index images_clean_12lead images_scanlike_12lead_pieces
images_scanlike_12lead_valtest`, pieces 0 1. On disk: project 20 GB — venv
5.7, `data/processed/images` 9.0 (clean 12-lead from session 15),
`outputs/model_runs` 3.1 (includes session 15's 2.4 GB `_dev/c2test*`;
not deleted — ask the user).

**4. Submitted.** `scancel 24641` (CANCELLED). Then from `~/se23ucse027`:

```bash
sbatch --parsable --partition=gpu_student --gres=gpu:a100_4g.20gb:1        --time=7-00:00:00 scripts/dgx_portability/slurm/campaign_02.sbatch
```

-> **25576**, RUNNING on dgxa within seconds. `--time` raised from the file's
28 h because 15 runs (incl. B4-sized image epochs) cannot fit 28 h; 7 d is the
`gpu_student` max and what campaign 1 and session 15 used. The job has
`--requeue` and resumes from checkpoints. Logs: `~/se23ucse027/trimodal_c2_25576.{out,err}`.
At 11:14 it was staging `images_scanlike_12lead_valtest` (5.9 GiB val tar at
~48 MiB/s).

**Run order** (`campaign_runs.py 2`): A1 x3, A3 x3, A6 x3, A5 x3, B4 x3
(seeds 42/123/456). Only A5/B4 cycle, so the **first swap comes after the nine
A1/A3/A6 runs**, ~2-4 days at ~25-33 min/epoch. Watching it is the next action.

**How to check from a new session** (Windows: use
`/c/WINDOWS/System32/OpenSSH/ssh.exe mudgx`, not git-bash `ssh` — session 12 trap):

```bash
squeue -u $USER; sacct -j 25576 -X -o JobID,State,Elapsed
cd ~/se23ucse027
grep -v "Transferr\|Elapsed time\|Checks:" trimodal_c2_25576.out | tail -40
ls outputs/model_runs/*/ ; grep -h peak_gpu_gb outputs/model_runs/*/*/train_log.jsonl | tail
grep -n -i "chunk\|piece\|evict\|swap\|quota" trimodal_c2_25576.err | tail -30   # the swap
```

**5. 25576 FAILED at staging (11:15:32 UTC, exit 1, 1 m 43 s).** Everything
else staged and verified (clean 12-lead 30/30, scan-like valtest, tasks,
index), but `[11:14:02] staging images_scanlike_12lead piece_000` and
`piece_001` each moved `0 B / 0 B` in 0.2 s, then
`verifying images_scanlike_12lead against checksums.json — verified 0, absent
8 of 8 recorded` -> `ERROR: the manifest lists files but NONE of them are on
disk ... checksum verification FAILED -- do not train on this data.` The guard
did its job.

Cause, verified on the login node with `--dry-run` (nothing moved):
`rclone copy r2:trimodal-data/chunks/images_scanlike_12lead/piece_000.h5 <dir>`
-> **EXIT=0**, nothing listed; the same for `piece_000.tar` -> `size 5.086Gi`.
`stage_data.sh:106-107` is

```bash
fetch "chunks/$base/$padded.h5" "$DATA_ROOT/$base"     || fetch "chunks/$base/$padded.tar" "$DATA_ROOT/$base"
```

and rclone treats a missing S3 key as an empty prefix, so the `||` never fires.
Signal pieces (`.h5`) are unaffected; image pieces (`.tar`) always stage empty.
All six cuts are in R2 (`rclone lsf r2:trimodal-data/chunks/` lists
`images_clean_12lead images_clean_lead2 images_scanlike_12lead
images_scanlike_lead2 signals_12lead signals_raw`; scan-like 12-lead has
`piece_000..007.tar`, `assignment.parquet`, `checksums.json`,
`fairness.json`). Not a data gap.

Disk after the failure: `data/processed/derived` 5.9 GB (scan-like valtest),
`images` 9.0 GB, `images_scanlike_12lead/` 4.1 MB (assignment + checksums
only). Nothing deleted. Not patched — per the session rules, reported to the
user first. Proposed fix: pick the extension from what exists rather than from
the exit code (e.g. `images_*` -> `.tar`, `signals_*` -> `.h5`, or an
`rclone lsf` probe), plus a regression case in a selfcheck that runs the
rclone path, then pull (bundle) and resubmit with the same command.

**6. Fix and resubmit (user approved).** `f190193`: `piece_ext()` in
`campaigns.sh` (`images_*` -> tar, `signals_*` -> h5, else error);
`stage_data.sh` fetches `piece_NNN.<ext>` and exits if the file is missing or
empty afterwards; `campaigns.sh selfcheck` now also runs `piece_ext_selfcheck`,
which lists every staged cut's `piece_*.<ext>` in R2 when rclone resolves. On
dgxa (srun 25604): all six cuts `8 piece_*.<ext> in R2`, PASS. Bundled to the
DGX (71bde63 -> f190193; token still dead).

Dry run then REFUSED: `Currently used: 25.68 GB` + 27.9 > 49. The extra was
campaign 2's own data already on disk (clean 12-lead 9.0 GB from session 15,
scan-like valtest 5.9 GB from 25576), which the gate adds again on top of the
full residency. Gate not relaxed. **User approved `evict_data.sh --all`**
(2026-10-09; checked first that the running A3 evals read only
`outputs/model_runs` — `31_eval.py` touches `data/processed` only for B6). srun
26895: `Used: 25.69 GB -> 9.76 GB`, guard passed without `--force`; dry run
`quota OK: 9.76 GB used + 27.9 GB`. Resubmitted with the same command ->
**26896**. Session 15's `_dev/c2test*` (2.4 GB) still kept.
**Lesson:** evict between attempts of the same campaign as well as between
campaigns — leftovers of a failed stage count twice at the gate.

**A3 evals at 2026-10-09 08:12:** 24634 tf-idf 1,743/2,940 (230 of 1,428 in
this job), 24637 BERT 1,260/2,940 (180 of 1,869), both ~4 d 3 h into 7 d. Rate
fell again: ~58 and ~47 units/day -> **~21 d and ~36 d left**. Each has one
continuation queued (24635, 24638); both tiers will need more. Raise the A3
redesign with the user.


### Session 18 — 2026-10-06 — `data-laptop`: a disk cleanup, nothing else

The user asked for an audit of every file belonging to this dataset on both
drives and for the DGX-prep leftovers that are no longer needed to go — Phase 1
outputs excluded. D: had 14.9 GB free. **No code changed, nothing in R2 was
touched, and no DGX fact in this file was re-observed** (this machine cannot
reach it; `f190193`'s staging fix arrived by pull and is not this session's).

**What was on disk, measured without crossing a junction** (decimal GB):

| where | what | real bytes |
| --- | --- | ---: |
| D: `data/processed` | Phase 1 containers, tasks, index | ~384 |
| D: `signals_int16/` | 5 whole int16 12-lead shards + Lead-II | 90.66 |
| D: `derived/` | `signals_12lead_L3`, `images_scanlike_test`, `images_clean_12lead_L3` | 69.53 |
| D: `outputs/upload_stage` | hard links to the above and to Phase 1 files | 0 (114 apparent) |
| D: `outputs/model_runs/_dev` | 80 dev-sample and smoke-test checkpoints | 38.98 |
| C: `trimodal_chunks/*__train__p8` | five cuts' pieces | 144.56 |
| C: `trimodal_derived/derived` | six `*_valtest` containers | 74.92 |
| C: `trimodal_chunks/_upload_stage` | hard links to both of the above | 0 (219 apparent) |

A scan of both whole drives for data-shaped files over 300 MB found no copy of
anything outside these trees and `data/raw`.

**Deleted (186.72 GB real, all on D:):**

1. `signals_int16/twelve_lead_preprocessed_shard_{00..04}.h5` — 83.24 GB. No
   dataset uploads them; what a campaign reads of them is the p8 pieces and
   `signals_12lead_valtest`, both in R2 and both still on C:.
   `int16_manifest.json` and `lead2_preprocessed.h5` stay.
2. `derived/signals_12lead_L3/` (44.17 GB) and `derived/images_scanlike_test/`
   (20.33 GB), with `manifest_overlays/{signals_12lead_L3,images_scanlike_test}.parquet`.
   No campaign has staged either since session 16. `rclone check` against R2
   first: 9 and 5 files, 0 differences. **The R2 copies are untouched**
   (post-mortem rule 7).
3. Both upload staging trees. Audited first: no reparse points, and the only
   files not linked elsewhere were code/config snapshots (git), checksum
   manifests (R2) and six cross-volume overlay copies (originals on D:).
4. Two dead junctions in `data/processed`: `derived$d` (an unexpanded shell
   variable) and `signals_raw` (into a scratchpad from 2026-08-30 that no
   longer exists).
5. The 80 `checkpoint_*.pt` files under `outputs/model_runs/_dev` — 38.98 GB of
   `--dev` runs from 2026-08-27/28 and `smoke_test.py` leftovers. They reach no
   paper number, `31_eval.py` reads predictions rather than checkpoints, and a
   finished run's checkpoints are deleted by design (§8.1). Every
   `run_summary.json`, log, config and predictions file stays (239 files, 8 MB).

**Kept, deliberately:** the six `*_valtest` containers (their overlays are
live locally — trap 21), `images_clean_12lead_L3` (campaign 7 stages it), the
Lead-II int16 file (a dataset source), and **the chunk pieces (144.56 GB on
C:)**. Asked whether the pieces should go too, the user's answer was: *delete
only what we do not need and will not have to rebuild.* A cut is re-cuttable,
but that is a rebuild, so the pieces stay — the signal pieces above all, now
that their int16 source is gone.

**Verified after:**

| check | result |
| --- | --- |
| `check_r2_complete.py` | PASS, output byte-identical to the run before the cleanup (673 objects, 350.331 GiB) |
| `upload_data.py --sizes` | identical; all 15 fit, nothing `missing` |
| `check_campaign_data.py` | identical; 15/15 |
| `read_modality()`, 8 kinds x 3 splits x L3/non-L3, 3 studies each | all read, with and without `TRIMODAL_SIGNAL_INT16=1` (12-lead falls back to float32) |
| Phase 1 trees | `signals/` 243.81 GB / 14 files and `images/` 137.76 GB / 202 files, unchanged |
| free space | D: 14.87 -> 152.48 GiB after items 1–4, **188.76 GiB** after item 5; C: untouched by any of it |

**What this costs later:** rebuilding any int16 12-lead container starts with
`make_int16.py` (resumable; ~6 h, read off the deleted shards' 2026-08-28 timestamps). The pieces and val/test
containers already built do not need it.

**Next action is unchanged and is not on this machine** — see the header.

### Session 19 — 2026-10-14 — `campus-laptop`: a read-only check; campaign 2 died at A5

Read-only over `ssh mudgx` (`squeue`, `sacct`, log reads). Nothing submitted,
cancelled, evicted or patched. DGX checkout is still `f190193`. Checked
2026-10-13 20:30 UTC. `sacct` prints IST; the campaign `.out` prints UTC.

**1. Campaign 2 (26896): FAILED, exit 1, after 1 d 10 h 29 m.**

| runs | state |
|---|---|
| A1, A3, A6 x seeds 42/123/456 (`image_resnet50_12lead_clean`) | DONE — `run_summary.json`, val/test predictions, thresholds; ~3.5-4.7 h each; `push verified` for all nine |
| A5, B4 x seeds 42/123/456 | FAILED at batch 0 of epoch 0, each within ~20 s; only `train_config.yaml` in the run directory |

The six failures are one error:

```
FileNotFoundError: .../data/processed/images/scanlike_12lead_shard_013.tar   (also _016, _017)
  task_dataset.py:556 _read_image -> modality.py:396 _read_image -> modality.py:244 _tar
```

preceded in every one of them by

```
chunk cycling OFF for this run: it reads ['image_clean_12lead', 'image_scanlike_12lead'],
and what is staged as pieces here is ['image_scanlike_12lead'] -- nothing in common
```

The two lists do have a kind in common, so `needs_cycle` was True. The branch
was lost on the other condition at `trainer.py:236`:
`"study_id" in train_dataset.frame.columns`. A5 and B4 are the two specs with
`id_column="anchor_study_id"` and `image_id_column="image_id"`
(`task_spec.py:264-266`, `320-322`). With cycling off, no manifest overlay
points the scan-like rows at the pieces, and the read goes to the base shard
path. **Read off the code and the log; the frame's columns were not inspected
on the DGX.** Staging itself worked this time: `piece_000.tar` and
`piece_001.tar` fetched at 5.086 GiB each and verified `ok`.

A fix is more than deleting the column test: `ChunkCycle` is handed
`frame["study_id"]` to build its windows, and for A5/B4 the id that decides
which piece a row needs is `image_id` (mismatched pairs read another study's
image), and only for rows whose `image_type` is scan-like. `selfcheck` and the
dry run passed because neither builds an A5/B4 trainer with pieces staged.

**2. After the failure** the body evicted the pieces and the `__val`
containers (36.31 -> 20.23 GB), pushed 46 runs with 0 failures, and submitted
the five image evals. Quota now 31.89 of 49 GB; `data/processed` 22 GB (clean
12-lead shards 9.0 GB, `derived` 12 GB).

**3. Evals.**

| job | task / tier | state | progress | rate | finishes inside the limit? |
|---|---|---|---|---|---|
| 27048 | A1 / image 12-lead clean | COMPLETED 21 h 40 m | | | |
| 27047 | A6 / image 12-lead clean | COMPLETED 22 h 10 m | | | |
| 27049, 27051 | A5, B4 / image | FAILED in 8 s / 5 s | no `test_predictions.parquet` | | consequence of item 1 |
| 27050 | A3 / image, 4 CPU / 32G, dgxb | RUNNING 2 d 23 h | 160 / 2,940 units | ~2.2 units/h | no — ~52 days of work left, times out ~2026-10-17 20:48 UTC |
| 24635 | A3 / tf-idf, 8 CPU / 64G, dgxa | RUNNING 1 d 15 h | 150 / 1,088 left | ~3.8 units/h | no — ~10 days left, times out 2026-10-19 04:41 UTC |
| 24638 | A3 / BERT, 8 CPU / 64G, dgxb | RUNNING 1 d 15 h | 230 / 1,519 left | ~5.8 units/h | no — ~9 days left, times out 2026-10-19 04:41 UTC |

24634 and 24637 TIMEOUT at 7 d on 2026-10-12 as planned and handed over to
24635/24638, which are the last links of both chains. **Nothing is queued
behind any of the three.** The rates are two readings of a 10-unit log step
each, so they are rough.

**Open, for the user:**

1. How to fix the cycling gate for A5/B4 (item 1), then resubmit campaign 2
   for the six missing runs — the nine finished ones are skipped on resume.
2. Whether to chain continuations behind 24635, 24638 and 27050 before they
   time out, and whether 27050 at 4 CPU is worth running at ~52 days.
3. Still open from session 17: the DGX's GitHub token is rejected, so a fix
   reaches it by `git bundle`.

**Session 19, continued — the user's four decisions, and what was done.**
(1) fix cycling by keying it on `image_id`; (2) chain A3 continuations now;
(3) one folder, raise the ceiling now; (4) accounts in a new file with a
pointer from the header.

**4. Continuations (account 1).** Six `afternotok` jobs, each a copy of its
parent's submit line: 27456 -> 27457 behind 24635, 27458 -> 27459 behind 24638,
27460 -> 27461 behind 27050.

**5. The cycling fix — `e3a2538`.** `TaskDataset.chunk_key_ids()` returns, per
chunked read, the id each row asks for (`-1` where the row does not make that
read); `chunk_cycle.row_key_ids()` folds those into one id per row, falls back
to the row's own id for rows that read nothing chunked, and refuses a row whose
two chunked reads sit in different pieces. `trainer.py` no longer tests for a
column called `study_id`. A task keyed on `study_id` gets the identical
assignment it had before. Checked on dgxa (srun 27462) against the real tables:

| | A5 | B4 |
|---|---|---|
| train rows | 3,667,615 | 3,667,615 |
| `study_id` column in the frame | **no** (the cause, now seen directly) | **no** |
| rows that read a scan-like image | 523,945 | 523,945 |
| ... whose `image_id` is in the cut, in the piece the hash gives | 523,945 | 523,945 |
| epoch 0 covers every row once; rows per window | 915,523 / 917,084 / 917,203 / 917,805 | same |

A1 reports zero chunked reads, so it stays un-cycled. `chunk_cycle.py`
self-check PASS (case 7 is new), `campaigns.sh selfcheck` PASS.
`python chunk_pieces.py` fails on its relative import — it did before this
session too, and was not touched.

**6. Ceiling 49 -> 99 GB** in `campaigns.sh` and `upload_data.py`. First gate
under it: `quota OK: 31.89 GB used + 27.9 GB ... <= 99 GB ceiling`.

**7. 27463 (first resubmission) failed at the first swap — a second bug,
`6da9bf8`.** Cycling came ON, the trainer evicted and fetched, and
`stage_data.sh 2 --pieces 6 --pieces-only` exited with `CHECKSUM MISMATCH:
chunk_pieces.py`, `chunk_cycle.py`. With `--pieces-only` the `code|configs` case
hit `continue` before the git test that sets `SKIP_CODE_VERIFY`, so the verify
pass judged git's code against R2's `checksums_code.json`. Any file committed
since the last code upload trips it, so this would have stopped every chunked
campaign at its first swap; 27463 was the first job to reach one. Cancelled
after two runs had failed the same way.

**8. `3e090e7`:** the cancel left `piece_002.tar.<hash>.partial`, and
`chunk_pieces.resident()` counted it as piece 2, which would have made the next
run skip the fetch. `resident()` now counts only `.h5` / `.tar`; the stale
partial was removed by hand.

**9. 27465 is the live job** — header. Seen so far: `chunk cycle: pieces
already on disk: [0, 1]`, `chunk cycling ON`, `epoch 0: 8 pieces in 4 windows,
3193572 rows covered`, evict 1 / fetch 2, `resident=[0, 2], 130789 studies
readable`, then 409 batches in 2 m 32 s.

**Open after this session:**

1. Not yet observed in 27465: a mid-epoch window swap, validation with pieces
   resident, a resume after TIMEOUT.
2. **Possible repeat of the 26896 failure in campaigns 8 and 11**
   (`val_mode=on_demand`): `ChunkCycle.release()` evicts every piece for the val
   swap, and the next run's trainer decides whether to cycle from
   `chunk_pieces.chunked_kinds()`, which reads what is on disk. If a run ends
   with nothing resident, the next one would start un-cycled. Read off the code
   only; check before either campaign is queued.
3. Account 2: the user installs the key (`docs/DGX_ACCOUNTS.md`), then decide
   what it runs and where it writes.
4. Whether the admins accept 99 GB in one account's folder.
5. The A3 image eval's ~52 days.

**Session 19, part 3 — preparing 1.5 weeks of unattended running on two accounts.**
The user installed account 2's key and is leaving campus for about ten days.
Commit `c7b95fc`. What the audit found, beyond the three fixes above:

- **The test split was never on the node while a campaign trained.**
  `30_train.py:431-436` writes test predictions as the last step of every run;
  the train phase excludes `*__test.*`. A1/A3/A6 never noticed because the
  clean image container holds every split in one file. A5/B4's scan-like test
  rows live in `images_scanlike_12lead_valtest__test.tar` (12.5 GB), so each of
  those runs would have trained ~30 h and died at the end. Account 1 is safe by
  accident: 26896's eval phase left that tar on disk. Fix: a `test` staging
  phase (`campaign_test_gb`, sizes measured off R2), staged by the body right
  after the train phase and gated against the quota at the first minute.
  **Campaigns 8 and 11 need 30.1 GB of test data beside 27.4 GB of training
  data — they fit only under the 99 GB ceiling.**
- **`SKIP_CODE_VERIFY` is now decided once, before the dataset loop**, so no
  early `continue` can bring back the 27463 failure.
- **Evals:** the body resubmitted every eval on every resubmission, beside the
  ones still running. `.campaign_state/evals/<task>__<tier>.jobs|.done` now
  records them (seeded by hand on account 1 for the three A3 chains and the
  finished A1/A6 image evals). `eval_task.sbatch` queues its own `afternotok`
  continuation, bounded by `EVAL_CHAIN` (default 2), cancels it on success, and
  no longer exits under `set -e` before its push when the eval fails.
- **`campaign_chain.sbatch`** runs a list of campaigns in one job, skips a
  finished campaign before staging, pushes and evicts before each one (the
  quota gate double-counts leftovers), and is safe to submit as `afterany`
  links. **`preflight.sbatch`** trains every config of a campaign end to end on
  a few thousand rows and then kills and resumes one.
- **Untested as of this entry:** a chain link in production (27474 is the
  first), the eval de-duplication, the eval self-continuation, chunk cycling
  through validation and through a resume.

**How to finish account 1** (not done — see header):

```bash
# campus laptop
git bundle create "$TEMP/claude/main.bundle" 3e090e7..main
scp.exe <that file> mudgx:/dgxa_home/se23ucse027/main.bundle
# account 1
cd ~/se23ucse027 && git pull --ff-only ~/main.bundle main && rm ~/main.bundle
export CAMPAIGNS="2 10"
a=$(sbatch --parsable --partition=gpu_student --gres=gpu:a100_4g.20gb:1 \
      --dependency=afterany:27465 scripts/dgx_portability/slurm/campaign_chain.sbatch)
sbatch --partition=gpu_student --gres=gpu:a100_4g.20gb:1 --dependency=afterany:$a \
      scripts/dgx_portability/slurm/campaign_chain.sbatch
```

The pull changes `stage_data.sh` under the live job 27465, whose next piece
swap will run the new version. Its train and test paths passed on account 2;
its `--pieces-only` path is what pre-flight 27468 exercises.

**Session 19, part 4 — what the pre-flights found, and what was queued.**

| pre-flight | account | result |
|---|---|---|
| 27467, campaign 4, GPU, 4,000 rows x 2 epochs | 2 | 24 of 26 configs PASS end to end (train, val, thresholds, test predictions, `status: complete`); peak GPU 1.1-2.0 GB; kill-and-resume PASS (`checkpoint_last=yes`, `resumed=yes`). Both B2 `regime_1` configs FAIL: `val is empty after filtering` |
| 27468, campaign 3, GPU | 2 | train phase + new test phase staged, 37.1 of 49 GB. A1, A3, A6 PASS (peak GPU 8.4 GB). **A5, B4 FAIL at the first swap: the quota gate refused it** |
| 27479, campaign 3 A5 only, CPU, scratch checkout `~/pf` | 2 | after the gate fix: epoch 0's four windows all swapped (`resident=[0,2]`, `[1,7]`, `[3,4]`, `[5,6]`). Validation, test and the resume test still running when this was written — `~/pf/trimodal_preflight_27479.out` |

- **B2 regime_1 (`e39d4a0`, user's decision).** `_split_row_filter` sent val
  through the regime filter; regime_1's rows are test-only. Train and val now
  share `row_role == 'augment_on_the_fly'` for every regime. regime_2's val
  rows are the same set as before. Checked: both regimes now build train, val
  and test datasets (600 rows each); the run itself could not be tried because
  campaign 4's data had just been evicted for the campaign 3 pre-flight.
- **Piece-fetch gate (`6608528`).** `stage_data.sh --pieces-only` weighed the
  campaign's whole residency on top of a disk already holding it (33.93 + 31.0
  > 49). It now weighs the pieces asked for (`campaign_pieces_gb`, largest
  piece per cut measured off R2). Account 1 never saw this because of its
  ceiling.
- **`92c21e1`:** an eval job stands down if another recorded job for the same
  (task, tier) is RUNNING — for evals queued by 27465, whose body was loaded
  before the de-duplication existed.
- **Account 1 updated under the live job.** Pulled to `8364ff8` then `92c21e1`
  between piece swaps; 27465 went on into its third window
  (`resident=[3, 4]`) afterwards.
- **Not fixed, campaigns 8 and 11:** `stage_val` calls
  `stage_data.sh --phase val`, which is still gated on the full residency, and
  the "starts un-cycled when nothing is resident" question from part 1 is still
  open. Neither campaign is queued.
- **Scratch to delete on return:** `~/pf` on account 2 (a second checkout with
  ~36 GB of campaign 3 data, used only by 27479) and `outputs/preflight/` in
  account 2's main checkout.

**Session 19, part 5 — the resume path, tested and fixed (`59e7832`).**

- **27479 finished: the cycled A5 config PASSES end to end** on the 49 GB
  account — 2 epochs, 15 piece fetches, validation with pieces resident
  (`epoch 1/2 ... val_AUPRC_y_match`), test predictions, `status: complete`.
- **Its kill-and-resume test FAILED**, and this is the path a 7-day TIMEOUT
  takes: the second run resumed (`skipping 3 of 6 batches`) and died on
  `images_scanlike_lead2/piece_007.tar` — a piece the overlay still listed and
  the disk no longer held. `ChunkCycle.ensure()` returned early when the wanted
  pieces were already resident, trusting an overlay an earlier process wrote.
  It now installs the overlay at least once per process.
- **Re-test 27489 (`RESUME_ONLY=1`, CPU, `~/pf`):** TERM landed mid-swap,
  leaving only piece 3 on disk. The second run logged `pieces already on disk:
  [3]`, `resumed from checkpoint_last.pt: epoch 0, batch 3`, fetched piece 4,
  `resident=[3, 4]`, trained that window and moved on to the next. Its final
  PASS line had not printed when this was written.
- Both accounts pulled `59e7832`. 27465 (account 1) loaded the old
  `chunk_cycle.py` and keeps it until it ends; **27480, which resumes campaign
  2 after the timeout, starts with the fix.**

### Session 20 — 2026-10-27 — `campus-laptop`: back on campus, a read-only check of both accounts

- Read `squeue`/`sacct` and the chain/eval logs on both accounts. Status and
  job IDs are in the header block. Note: `sacct` prints IST; the job logs print
  UTC (5 h 30 apart). Do not take that as two jobs overlapping.
- **Account 1 push failure, root cause:** `push_results.sh` pushes to
  `$R2_RESULTS`, which defaults to `r2:trimodal-results` in `campaigns.sh:97`.
  On the DGX, `r2` is the read-only data token. `eval_task.sbatch` and
  `preflight.sbatch` default it to `r2-results:`; `campaign_chain.sbatch` does
  not, and evals submitted from a chain inherit the `r2:` value. 27465
  (`campaign_images` launcher) pushed fine up to 10-19, and every account 1 push
  since 27480 started has failed. The A3 text evals 27456/27459 pushed fine
  because they were queued from an interactive shell (`~/.bashrc`).
  `rclone lsd r2-results:trimodal-results/` works; `r2:` gets 403.
- Changed nothing on the DGX; the fix is waiting on the user (header).
- **Later in the session, with the user's go-ahead:** wrote account 1's
  `.account_env` (R2_RESULTS only; no quota lines, so the 99 GB default
  stands), committed the `campaign_chain.sbatch` default (`e9dce96`), moved
  `main` to account 1 by bundle (the GitHub token is still dead: `could not
  read Username`), pulled account 2 from `acct1`, cancelled 27457, and ran the
  backlog push on the login node. It finished: `pushed 58 run(s), 0 failure(s)`, 49.60 GB used.

**Session 20, part 2 — the user's eight answers, acted on.**

1. **Chain links queued**, 4 per account, on the new claim-based chain (above).
   The old pending links 27481 and 27476 ran the old script (sbatch copies the
   script at submit), so they were cancelled and replaced.
2. **A3 image eval: continue, bigger.** 27461 cancelled and resubmitted as
   29167 with 16 CPUs, 96G, `EVAL_CHAIN=2`. 31_eval.py checkpoints per unit, so
   nothing was redone (`resuming — 1107 of 2940 units already done`). Kept on
   account 1: moving it would mean moving its predictions and checkpoint file.
   CPU on account 1: 8 (chain) + 4 (A5 eval) + 16 = 28 of 32.
3. **Campaigns on availability**: R2 claims, `campaign_chain.sbatch`. Tested on
   account 2's login node with `CAMPAIGNS="1 2 10"`: skipped all three
   (done/done/claimed by se23ucse027) in seconds.
4. **Campaigns 8/11 fixed in code** (`c94a838`): `campaign_val_gb` (val sizes
   measured off R2), body skips the test phase for on_demand, `30_train.py`
   stages val then test around the end-of-run predictions, and a chunked run
   that finds no piece on disk gets pieces 0 1 back first (the "un-cycled"
   question from session 19). Not run on a node yet.
5. **Merge** written and dry-run (above). `--apply` uploads.
6. Token: the user is making one (instructions given in chat: fine-grained,
   this repo only, Contents read-only; placed with `read -s` so it never shows).
7. **Ceiling 99 -> 49 on account 1** (code default; `.account_env` holds only
   R2_RESULTS). To fit campaign 10's restart: `push_results.sh` freed pushed
   checkpoints, `_dev` September preflight checkpoints deleted (2.4 GB),
   A3 text `test_predictions.parquet` deleted locally after `rclone check`
   against R2 (their evals are done), 112 finished-job logs gzipped. Account
   1 base 12.2 -> 8.6 GiB. **Also found:** the gate added decimal-GB table
   sizes to GiB usage; fixed in `will_fit` (`gb_to_gib`).
8. **Account 2 scratch deleted**: `~/pf` (144 MB — its campaign 3 data was
   already gone; `ecg_env` there was a symlink) and `outputs/preflight`.
- **Rough Phase 2 ETA (10-27, low confidence).** Per-run times seen: 12-lead
  image A1/A3/A6 10-25 h, A5/B4 (cycled) ~35 h; Lead-II signals ~5 h average
  (campaign 4: 64 runs in 13 days). Fusion and 12-lead signal campaigns have
  never run; guessed at 10-35 h/run. That puts the remaining training at
  ~145 GPU-days (10: 10, 4: 8, 3: 14, 15: 14, 5: 5, 6: 8, 7: 15, 8: 22, 9: 10,
  12: 11, 13: 19), so **~75 days on two slices: training done ~early January
  2027**, then 11/14 and the CPU eval tail: **Phase 2 complete ~late January
  to February 2027.** The queued links run out ~11-24; add more before then.
