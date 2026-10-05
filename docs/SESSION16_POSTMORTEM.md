# Session 16 post-mortem — what went wrong, what was fixed, what is still unproven

Written 2026-10-05 on the `data-laptop`. Sessions 15–16 (2026-09-30) plus the
addendum of 2026-10-05. **Read this once, on any machine, before submitting or
changing a campaign.** `docs/PHASE2_PROGRESS.md` stays the live state; this file
is the explanation of why the campaign table, the staging scripts and the chunk
cycling look the way they do, so that no later session re-derives it or undoes
it.

One-line version: **campaign 2's pre-flight died because a campaign staged less
data than its runs read. Looking for the cause found the same bug in three more
campaigns, a size table that was wrong in both directions, and four staging
mechanisms that would have failed later. All are fixed, all data is in R2, and
there are now checks that fail loudly if any of it regresses.**

---

## 1. The failure that started it

Session 15's campaign 2 pre-flight on the DGX died with
`FileNotFoundError: .../scanlike_12lead_shard_017.tar`.

**Cause.** Each campaign's dataset list in `campaigns.sh` was written from what
a config *names* (`input_modality`). But tasks A5 and B4 choose the image
rendering **per row** (`image_type_column`, `task_dataset.py:524-528`): six rows
per anchor are clean, one is scan-like. So every A5/B4 run that touches images
reads the scan-like container as well as the clean one its config names, and no
campaign staged scan-like train or val data. R2 held only the scan-like *test*
split.

**Why a small fix was impossible.** There is one scan-like row per anchor and
every study in a split is an anchor, so scan-like train+val is 599,470 of
749,112 studies: **50.08 GB for 12-lead**, more than the whole 49 GB quota on
its own (31.24 GB for Lead-II).

**Fix (the user's decision): chunk it.** Scan-like train was cut into 8 pieces
for both layouts; val/test ship as separate per-layout containers.

---

## 2. Everything that was found, and its fix

### 2a. Campaigns staging the wrong data (the same bug class as §1)

| # | what was wrong | fix |
| --- | --- | --- |
| 1 | Campaigns 2, 3, 8, 11, 13, 14 staged no scan-like train/val, though their A5/B4 runs read it | scan-like train chunked at p8; `images_scanlike_{12lead,lead2}_valtest` built; dataset lists corrected |
| 2 | Campaign 10 staged **no clean-image container**; its A5/B4 scan-like runs read one for their clean rows | clean container added |
| 3 | Campaign 11 trains A5/B4, which are **not** L3 tasks, against the L3-only subsets — every study outside the L3 cohort would have missed | now reads the full-cohort 12-lead pieces |
| 4 | `upload_data.py --all` looped `range(1, 12)`, so campaigns 12–14's datasets had never been uploaded by it | loops over `n_campaigns()` |
| 5 | Campaign 10 was described as "re-testing only, test split" but its 30 runs **train** on scan-like images (spec §5.3, open question 17) | split by layout into **10** (12-lead) and **15** (Lead-II). 15 campaigns; still 104 configs / 312 runs. Locked in spec §12.10 |

### 2b. Sizes that were maintained by hand, and wrong

| # | what was wrong | fix |
| --- | --- | --- |
| 6 | The residency table in `campaigns.sh` was hand-written and wrong in both directions: campaign 12 listed 29.4 GB, measured 33.7; campaign 9 listed 18.5, measured 12.7; campaign 7 listed 37.7, measured **40.5 — over the ceiling** | `upload_data.py --sizes` measures every campaign from the files; the table is pasted from its output |
| 7 | `signals_12lead_L3` is 35.35 GB resident, which is what put campaign 7 over | campaigns 5 and 7 read the full-cohort 12-lead pieces instead (13.7 GB for two pieces). `signals_12lead_L3` is now unused |
| 8 | Campaigns 12/13/14 staged a 6.08 GB raw Lead-II file they never read | `signals_lead2` split into `signals_lead2_preprocessed` and `signals_lead2_raw` |
| 9 | Campaigns 8 and 11 need 27.4 GB of training data plus 15.1 GB of validation data: 42.5 GB does not fit | **`val_mode=on_demand`**: the trainer drops the pieces at each epoch boundary, fetches the val split, validates, and drops it again |

### 2c. Staging and training mechanisms that would have failed later

| # | what was wrong | fix |
| --- | --- | --- |
| 10 | `ChunkCycle.ensure()` fetched the next pair of pieces **before** evicting the current pair — four pieces on disk where the quota is sized for two | evicts first, then fetches; the run waits with nothing resident. It also reads the disk on start, so a resumed run does not stage on top of a dead run's pieces |
| 11 | Chunk cycling was decided per campaign. Marking campaign 2 chunked would have cycled its A1/A3/A6 runs too, which changes which studies a window sees — a scientific change, not a staging detail | decided **per run**: a run cycles only if it reads a kind that is staged as pieces. `chunk cycling OFF for this run` is correct for the others |
| 12 | After a val swap evicts the pieces, the cut's `checksums.json` lists eight files that are all legitimately absent, tripping `stage_data.sh`'s "manifest lists files but none are on disk" guard. It would have killed campaigns 8 and 11 at the first epoch boundary **and the eval phase of every chunked campaign** | the cut's manifest is skipped outside the train phases |
| 13 | `max_steps_per_epoch` never capped anything (it sliced a copy of the epoch plan). No paper number is affected, but **session 15's pre-flight timings are full epochs, not 400 steps** — a full A1 epoch on an `a100_4g.20gb` slice is ~25 min with validation | `_epoch_plan` truncates the plan itself |
| 14 | `build_tiny_trainer` never fitted the TF-IDF vectoriser, so three crash-recovery checks could not run on that tier; `smoke_test.py` hard-wired the Lead-II layout, which produced session 15's 8/10 FAILs inside campaign 2 | both fixed; all six tier families pass |
| 15 | The `.sbatch` files request `--gres=gpu:a100:1`, a full 40 GB card that was three weeks out in the queue | always pass `--partition=gpu_student --gres=gpu:a100_4g.20gb:1` on the command line |

### 2d. Things that went wrong while fixing it

| # | what went wrong | what was done |
| --- | --- | --- |
| 16 | Four `*_valtest` containers had been deleted from D: after upload, leaving their overlays pointing at nothing, so local val/test reads failed (trap 21) | derived data lives on C:, reached from `data/processed/` through junctions |
| 17 | The two Lead-II signal uploads failed: their files are on D:, the upload staging tree was on C:, and a hard link cannot cross volumes | re-run with `TRIMODAL_UPLOAD_STAGE` on D: |
| 18 | Those two datasets were documented as "the same remote keys, no new upload". False: a remote key is `<dataset>/<path>`, so they landed under new prefixes and **12.6 GB was uploaded again**. The old `signals_lead2/` prefix is now unused | comment and docs corrected; both copies confirmed byte-for-byte with `rclone check` |
| 19 | The bucket's `code` / `configs` copies predated session 16. A git checkout skips them, so no run was at risk, but the `TRIMODAL_FORCE_CODE_STAGE=1` fallback would have reverted every fix above | refreshed from `main`. They go stale with every commit to `scripts/` or `config/`; **git is the source of truth** |
| 20 | The session was stopped mid-upload (Claude Code restart, then a usage limit) | the build and upload ran in a detached script that survived both; every step is idempotent |

---

## 3. The checks that now exist — run these, do not reason about it

| check | proves | runs on |
| --- | --- | --- |
| `check_campaign_data.py` (+ `--selfcheck`) | every campaign stages every (modality, split) its runs **read**, plus text and the right cohort. The self-check replays failures 1–3 and asserts each is rejected | any machine |
| `upload_data.py --sizes` | every campaign fits the quota in every phase, from measured file sizes | data laptop |
| `check_r2_complete.py` | every key, byte size and checksum manifest the stager expects is actually **in the bucket** | data laptop |
| `verify_piece_roundtrip.py` | a piece staged the way the DGX stages it reads back byte-identical to the base container | data laptop |
| `campaigns.sh selfcheck`, `chunk_cycle.py`, `make_chunks.py selfcheck` | quota accounting; the swap never holds more than two pieces; cuts are aligned | any machine |

State on 2026-10-05: all of them pass. 15/15 campaigns stage what they read,
all 15 fit (thinnest: campaigns 8 and 11 with 5.7 GB spare, 3 and 15 with 5.8),
22/22 datasets are in R2 (350.3 GiB), and all three new cuts round-trip.

---

## 4. Rules that follow — for every later session

1. **A campaign's dataset list is a claim; `check_campaign_data.py` is the
   proof.** Run it after any change to `campaigns.sh`, a config, or a task
   table. Never judge what a run reads from its config's `input_modality`.
2. **Sizes are measured, never typed.** Regenerate with `upload_data.py --sizes`
   and paste. Do not edit the numbers in `campaigns.sh` by hand.
3. **"It is already in R2" is a claim too.** After any upload, run
   `check_r2_complete.py`. A remote key is `<dataset>/<path>` — renaming or
   splitting a dataset is a new upload.
4. **Do not re-cut at a different piece count.** Every cut is p8 and they are
   aligned (0 of 523,945 studies disagree); a different count invalidates all
   six.
5. **Git is the source of truth for code.** Pull before every DGX submit. The
   DGX never commits.
6. **A guard that fires is information, not an obstacle.** A quota refusal means
   something is on the disk that should not be; a `FileNotFoundError` on a shard
   means a campaign stages less than it reads. Report the numbers; do not patch
   the caller, shrink the data or relax the gate.
7. **Nothing in R2 is deleted without the user saying so.** `signals_12lead_L3`
   (~44 GB), `signals_lead2/` (12.6 GB) and `images_scanlike_test` (18.9 GiB) are
   unused and deliberately kept.
8. **The upload staging tree must be on the same volume as the files it links.**

---

## 5. What is still UNPROVEN — the first DGX runs are the test

Everything in §3 was verified on the data laptop. These have never run on the
real machine:

| unproven | first exercised by | what to watch |
| --- | --- | --- |
| a real mid-epoch piece swap (evict two, fetch two from R2, resume) | campaign 2's **A5/B4** runs | the first swap in the log; disk use never above two pieces; the run resumes training |
| the eval phase of a chunked campaign | campaign 2's evals | `stage_data.sh` does not trip on the cut's manifest (fix 12) |
| the `val_mode=on_demand` swap | campaign 8 | each epoch boundary costs ~20 min of transfer — raise `--time` |
| GPU memory of the fusion tiers | campaigns 7, 8, 12, 13 | `peak_gpu_gb` in the first epoch row of `train_log.jsonl`; a 20 GB slice may not be enough |

**Submit campaign 2 and read its first swap before queuing anything else.** If
the swap fails, that is one bug to fix once, not fifteen campaigns to resubmit.

Separately, and not caused by any of this: **the A3 evaluation is too slow to
finish as written** (tf-idf ~34 days, BERT ~70 days remaining when measured on
2026-09-30, and decelerating). It blocks the A3 rows of the results table, not
any training. The 2,940-unit BCa bootstrap needs a redesign, not more wall
clock.
