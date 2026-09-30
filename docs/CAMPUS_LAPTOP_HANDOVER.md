# Campus laptop + DGX — how to pick Phase 2 back up

Written 2026-09-30 on the `data-laptop` at the end of session 16, after open
question 16 (the A5/B4 scan-like gap) was closed end to end. **Everything the
DGX needs is in R2. The data laptop is not needed again** — no re-chunking, no
re-upload, no rebuild. If you find yourself wanting it, something has gone
wrong and the last section says what to check first.

Read `docs/PHASE2_PROGRESS.md` for the full state; this file is the operating
manual for the two machines that are not the data laptop.

---

## 0. First five minutes on the campus laptop

```bash
cd <repo>
git pull --ff-only origin main
printf 'campus-laptop\n' > .machine     # untracked; each machine states its own
cat docs/PHASE2_PROGRESS.md | head -60
```

`.machine` is how a Claude session knows which machine it is on and therefore
what it may do. `campus-laptop` means: **you drive the DGX, you have no
`data/processed`**. Anything that calls `read_modality()` fails here by design —
that is not a bug to fix.

Then, on the DGX (through the remote desktop, as `se23ucse027`):

```bash
cd ~/se23ucse027
git pull --ff-only origin main
printf 'dgx\n' > .machine
bash scripts/dgx_portability/campaigns.sh selfcheck      # expect: used_gb self-check PASS
```

**The DGX pulls and never commits.** Code and configs come from git, not R2 —
`stage_data.sh` skips those two datasets over a work tree on purpose
(commit 7d3602d). Pull before every submit; an unpulled checkout has already
cost this project two incidents.

---

## 1. What changed while you were away, in one page

The campaign 2 pre-flight died on `scanlike_12lead_shard_017.tar`. Root cause:
**A5 and B4 choose the image rendering per ROW**, not per config
(`image_type_column`, `task_dataset.py:524-528`), so every A5/B4 run that
touches images reads `image_scanlike_<layout>` as well as the clean container
its config names. Nothing staged it.

It could not be fixed with a small subset: there is exactly one scan-like row
per anchor and every study in the split is an anchor, so scan-like train+val is
**599,470 of 749,112 studies** — 50.08 GB for 12-lead, which is more than the
entire 49 GB ceiling on its own.

So, measured and rebuilt:

| what | now |
| --- | --- |
| scan-like TRAIN, both layouts | **chunked at p8**, aligned with the three existing cuts (0 of 523,945 studies disagree) |
| scan-like VAL/TEST | `images_scanlike_<layout>_valtest`, **per layout** — the old `images_scanlike_test` held both layouts in one 20.3 GB tar |
| clean Lead-II TRAIN | chunked at p8 as well, for campaigns 13/14 only |
| `signals_lead2` | split into `..._preprocessed` and `..._raw`; 12/13/14 were staging a 6.08 GB raw file they never read |
| campaigns 5 and 7 | now read the **full-cohort** 12-lead pieces instead of `signals_12lead_L3` (35.35 GB resident, which put campaign 7 at 40.5) |
| campaigns 8 and 11 | **val on demand** — they do not hold the val split while training |
| the whole size table | **measured**, by `upload_data.py --sizes`, not hand-maintained |

Three latent failures were found and fixed on the way, all the same shape as
the original — a campaign staging less than its runs actually read:

- **campaign 10** staged no clean-image container, but its A5/B4 scan-like runs
  read one for their clean rows;
- **campaign 11** trains A5/B4, which are *not* L3 tasks, against the L3 subsets;
- **`max_steps_per_epoch` never capped anything** (it was sliced off a copy of
  the epoch plan), so the session-15 pre-flight timings are one full epoch, not
  400 steps. A full A1 epoch on an `a100_4g.20gb` slice is ~25 min with
  validation. No paper number is affected — no campaign script passes the flag.

### Two behaviours worth knowing before you read a log

**Chunk cycling is decided per RUN, not per campaign.** `chunked=yes` only
means the campaign stages pieces. A run cycles only if it reads a kind that is
actually staged as pieces. In campaign 2 the clean 12-lead container is staged
whole and the scan-like one as pieces, so **A5/B4 cycle and A1/A3/A6 do not** —
you will see `chunk cycling OFF for this run` in nine of campaign 2's logs and
that is correct. Cycling a run that does not need it is not a slowdown, it is a
different sampling regime.

**A piece swap evicts before it fetches.** It used to stage the incoming pair
then drop the outgoing one, which held four pieces where the quota is sized for
two. The loop now waits with nothing resident while the next pair comes down
from R2. Slower per swap; the only version that fits.

---

## 2. The order to run things

Campaign 1 is **done** (36/36 runs). Its B4 evals were still finishing on
2026-09-29; check them first.

```bash
squeue -u $USER
sacct -u $USER --starttime 2026-09-28 --format=JobID,JobName%22,State,Elapsed,End
```

Then, in this order:

Every `sbatch` below wants `--partition=gpu_student --gres=gpu:a100_4g.20gb:1`
on the command line — see campaign 2.

| step | campaign | runs | notes |
| --- | --- | --- | --- |
| 14 | **2** `images_12lead` | 15 | job **24641 is held** — see below |
| 15 | **3** `images_lead2` | 15 | |
| 16 | 4 `signals_lead2` | 78 | |
| 17/18 | 5, 6 | 12 + 18 | both now read the full-cohort 12-lead pieces |
| 19 | 7, 12 | 18 + 18 | |
| 20 | 8, 13 | 15 + 15 | 8 is the first `val_mode=on_demand` campaign |
| 22/23 | 9, 10 | 30 + 30 | |
| 24 | 11, 14 | 6 + 6 | 11 is `on_demand` too |

### Campaign 2 specifically

Job `24641` (`c2_images12`) is held from session 15 and was submitted against
the **old** campaign table. Do not release it. Cancel it and submit fresh, so
it picks up the new dataset list:

```bash
scancel 24641
cd ~/se23ucse027
git pull --ff-only origin main
bash scripts/dgx_portability/stage_data.sh 2 --pieces 0 1 --dry-run   # expect: quota OK
sbatch --partition=gpu_student --gres=gpu:a100_4g.20gb:1 \
       scripts/dgx_portability/slurm/campaign_02.sbatch
```

**Always override `--gres` on the command line.** The `.sbatch` files say
`--gres=gpu:a100:1`, which is a FULL 40 GB card, and on 2026-08-30 Slurm's
estimate for one of those was **three weeks out** — dgxa has exactly two and
they were held by `gpu_faculty` jobs. A `a100_4g.20gb` slice allocated in
~20 seconds. Rule 4 in `DGX_OPERATOR_HANDOVER.md` §3a is "fit first, card
second": take a slice on dgxa by default, a full card on dgxb only when a run
truly needs more than 20 GB, and wait for a full dgxa card only when it needs
both 40 GB and the fast disk.

Measured: A1/A3/A6 peak at **10.82 GB**, so they fit a 20 GB slice with room.
The fusion tiers (campaigns 7, 8, 12, 13) have never been measured — every
epoch row in `train_log.jsonl` carries `peak_gpu_gb`, so read it off the first
one rather than guessing, and move to a dgxb full card if it OOMs.

`campaign_runs.py` takes `--tasks`, so campaign 2 can be sharded if you want
A1/A3/A6 (9 runs, no cycling) separate from A5/B4 (6 runs, cycling):

```bash
TRIMODAL_TASKS="A1_ecg_diagnosis A3_lab_abnormality A6_risk_stratification" \
  sbatch --partition=gpu_student --gres=gpu:a100_4g.20gb:1 \n         --export=ALL scripts/dgx_portability/slurm/campaign_02.sbatch
```

### Before every campaign

```bash
bash scripts/dgx_portability/stage_data.sh <n> --dry-run            # unchunked
bash scripts/dgx_portability/stage_data.sh <n> --pieces 0 1 --dry-run   # chunked
```

A dry run resolves the roots, prints the transport and runs the quota gate
without moving a byte. **If it refuses, stop and read the number** — every
campaign was measured to fit, so a refusal means something else is on the disk
(old checkpoints, a previous campaign's data, the `c2test` outputs from session
15's pre-flight, which were 2.4 GB under `outputs/model_runs/_dev/`).

```bash
bash scripts/dgx_portability/evict_data.sh --all       # between campaigns
du -sh ~/se23ucse027/*                                 # what is actually using the quota
```

---

## 3. Which campaigns need what

Measured residency, GB, against the 49 GB ceiling with ~7.2 GB of fixed cost
(venv + HF cache) and 5 GB of checkpoints. Regenerate this any time with
`./ecg_env/Scripts/python.exe scripts/dgx_portability/upload_data.py --sizes`
on the data laptop, or read it off `campaigns.sh`.

| n | name | train | eval | chunked | val mode |
| --- | --- | --- | --- | --- | --- |
| 1 | text_models | 1.2 | 1.2 | no | resident |
| 2 | images_12lead | 27.9 | 23.2 | yes | resident |
| 3 | images_lead2 | 31.0 | 28.1 | yes | resident |
| 4 | signals_lead2 | 15.6 | 15.6 | no | resident |
| 5 | signals_12lead_L3 | 22.7 | 16.7 | yes | resident |
| 6 | signals_12lead_full | 22.7 | 16.7 | yes | resident |
| 7 | fusion_L3_12lead | 26.8 | 17.8 | yes | resident |
| 8 | fusion_full_12lead | 27.4 | 31.1 | yes | **on_demand** |
| 9 | retrain_sweeps | 12.7 | 9.6 | yes | resident |
| 10 | test_sweeps | 27.8 | 27.8 | no | resident |
| 11 | final_eval_12lead | 27.4 | 31.1 | yes | **on_demand** |
| 12 | fusion_L3_lead2 | 27.7 | 27.7 | no | resident |
| 13 | fusion_full_lead2 | 24.3 | 20.0 | yes | resident |
| 14 | final_eval_lead2 | 24.3 | 20.0 | yes | resident |

**`val_mode=on_demand`** (campaigns 8 and 11) means the run does not hold the
val split while it trains: at each epoch boundary the trainer evicts the
pieces, fetches `*__val.*`, validates, and drops it again. It buys 15 GB, which
is what makes them fit at all.

Two things follow. **Give those two campaigns more wall clock** — the `.sbatch`
files were timed without a per-epoch 15 GB transfer; at the 27 MB/s measured
from the data laptop that is ~10 minutes each way, so budget an extra ~20 min
per epoch and raise `--time` accordingly (`MaxTime` on `gpu_student` is 7 days).
And **they depend on the network at every epoch boundary**: a chunked campaign
already fetches mid-epoch, so the dependency is not new, but a run that dies
with `chunk staging failed` or `staging failed` is an R2/network failure, not a
data bug. It resumes from the last epoch-boundary checkpoint.

---

## 4. Two things that are still genuinely unresolved

### 4a. Campaign 10: does it train on scan-like images, or only re-test?

**Settle this before Step 23; as configured it will fail either way.**
`campaign_runs.py 10` emits **30 training runs** and the body trains them, but
the campaign stages the **test split only** and the execution plan budgets
6 GPU-hours for all 30 — which is an evaluation, not training. Meanwhile spec
§5.3 says augmentation is "on when **training on** scan-like", and the
`*_scanlike.yaml` configs set `augmentation: true`, which only means anything
while training.

Either way the data is ready: the re-testing reading measures 27.8 GB and works
now (its clean test containers were missing from the dataset list until
2026-09-30), and the training reading needs the scan-like pieces, which are
already in R2. **It is a `campaigns.sh` change, not a data change** — the data
laptop is not needed. If it does train, campaign 10 must also be split by lead
subset, the way 7/8/11 and 12/13/14 were, because one campaign reading both
layouts is the 69 GB problem open question 14 solved.

See open question 17 in `docs/PHASE2_PROGRESS.md` for the full evidence.

### 4b. The A3 evaluation is too slow to finish as written

Measured over 39 hours
in session 15: tf-idf ~34 days remaining, BERT ~70 days, and *decelerating* —
the last ten units took 4.3 h and 7.5 h. That is 5–10 more seven-day
continuations per tier. The 2,940-unit BCa bootstrap needs rethinking, not more
wall clock. Nothing in this session touched it.

This blocks the A3 rows of the results table, not any training. Raise it
explicitly rather than letting continuations pile up.

---

## 5. If something looks wrong

Run the checks before concluding anything:

```bash
# the read path, chunk cycling and the quota accounting
bash scripts/dgx_portability/campaigns.sh selfcheck
python3 scripts/phase2_tasks_benchmark_and_paper/_train_lib/chunk_cycle.py
python3 scripts/dgx_portability/make_chunks.py selfcheck

# what the pieces and overlays on this node actually are
ls ~/se23ucse027/data/processed/*/piece_*
ls ~/se23ucse027/data/processed/manifest_overlays/
```

| symptom | what it means |
| --- | --- |
| `FileNotFoundError: .../shard_NNN.tar` | a campaign is staging less than its runs read. **This is the bug class that caused all of session 16.** Do not patch the caller; compare the campaign's dataset list against what its configs read. |
| `REFUSING TO START (spec §8.1…)` | the quota gate, working. Read the used-GB number; something is on the disk that should not be. |
| `chunk cycling OFF for this run` | correct for a run that reads no chunked kind (all of campaign 2's A1/A3/A6). |
| `chunk pieces are not modality-aligned` | a cut was made with a different `--pieces` count. Every cut in R2 is p8. |
| a `*_pieces` dataset is missing from R2 | it is not; `rclone lsd r2:trimodal-data/chunks` lists all five. |
| `transport=none` inside a job | rclone is not on PATH in a non-interactive shell. `resolve_rclone()` handles it; if it still fails, check `~/se23ucse027/bin/rclone`. |

**You should not need the data laptop.** The only reasons that would change:
a cut has to be made at a different piece count, or a modality has to be
re-rendered. Neither is expected — every campaign was measured to fit at p8
with margin, the thinnest being campaign 12 at 27.7 GB against a 36.8 GB
budget.

---

## 6. A prompt to start a Claude session on the campus laptop

Paste this as the first message:

> Read `.machine` first, then `git pull --ff-only origin main`, then read
> `docs/PHASE2_PROGRESS.md` (header plus the session 16 log) and
> `docs/CAMPUS_LAPTOP_HANDOVER.md`. Per `AGENTS.md` this is the `campus-laptop`:
> it drives the DGX and has no `data/processed`, so anything that reads a
> container fails here by design.
>
> Context: session 16 on the data laptop closed open question 16 — the A5/B4
> scan-like data gap that killed the campaign 2 pre-flight. Scan-like train is
> now chunked at p8 for both layouts, val/test ship as per-layout containers,
> the campaign table was rebuilt from measured sizes, and three more
> staging/cohort bugs were fixed. All of it is in R2 and on `main`.
>
> What I want:
> 1. Check the DGX state — `squeue`, and `sacct` since 2026-09-28 — and tell me
>    where campaign 1's B4 evals and the A3 evals actually got to.
> 2. Pull on the DGX, confirm `campaigns.sh selfcheck` passes, and dry-run
>    `stage_data.sh 2 --pieces 0 1`. Report the quota numbers before staging.
> 3. Job 24641 is held and was submitted against the old campaign table —
>    cancel it and submit campaign 2 fresh.
> 4. Then work down the queue in `docs/CAMPUS_LAPTOP_HANDOVER.md` §2.
>
> Rules: work on `main`, never branch. Pull before every DGX submit; the DGX
> never commits. Update `docs/PHASE2_PROGRESS.md` and push before the session
> ends — the data laptop and I can only see what is on `main`. Do not propose
> re-chunking or re-uploading data: that was finished on the data laptop and
> every campaign was measured to fit. If a campaign refuses at the quota gate,
> report the numbers rather than shrinking anything.

Swap step 3 for whatever is actually true when you get there — `squeue` is the
authority, not this file.
