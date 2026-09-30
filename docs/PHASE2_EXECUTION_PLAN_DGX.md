# Phase 2 — Step-by-Step Plan (DGX-first, no compromises)

**Written:** 2026-08-26 · **Read with:** `docs/PHASE2_SOURCE_OF_TRUTH.md` (the science)
**Your three rules, which this plan obeys:**
1. Full end-to-end training for the combined models. No shortcuts.
2. All heavy work on the DGX. Your laptop is unreliable for long runs (power cuts).
3. No compromises on scope. Weeks or months is fine.

---

## Amendment — 2026-08-26, after Stage P2.0 (read this first)

**All CPU-only work moved back to the laptop.** The user has approved long local
runs — hours, overnight, whatever it takes. Campaign 0 no longer exists as a DGX
campaign: the R-peak extraction, the 12 task builders, the three audits and the
rule-based baselines all run at home, at full scale.

What this buys us:

- **The DGX is now GPU-only.** Its 50 GB holds training data and nothing else. The
  EHR tables never have to go to campus at all — which also means the raw MIMIC
  extract stays on the laptop, where the data-use agreement is happiest.
- **Roughly 3 GB less to upload**, and one fewer campaign to schedule.
- **The audit gate closes before the first upload**, not after it. Leakage, cohort
  and split all say PASS at home; only then does anything move.
- **No round-trip.** Previously a failed builder meant "notice it on the DGX, fix
  it at home, re-upload, re-run" through a remote desktop into a friend's laptop.
  Now the fix and the re-run are on the same machine.

What it costs: a few days of laptop wall-clock, and the laptop must not be needed
for anything else while the long jobs run. Power cuts are handled by
checkpoint-and-resume, which every long script now has to implement — that is a
requirement, not an optimisation.

The DGX plan below is otherwise unchanged. Parts 4 through 7 — every trained
model in the paper — still run on the DGX exactly as written.

---

## What changed from the earlier draft

The earlier plan kept the big signal files on your laptop, because signal models are small
and the data is huge. Your rules change that: **everything trains on the DGX now**, so the
signals have to get there too. That is the whole difficulty, and the rest of this document is
how we solve it.

The good news is that your first rule actually makes the second one *easier*. End-to-end
training is heavy work — the model is doing a lot of maths per ECG. That means the GPU stays
busy long enough for the next batch of data to finish downloading in the background. A
"light" model would have sat idle waiting for downloads; a heavy one does not.

Your laptop's job (as amended 2026-08-26): **write the scripts, test them on a small
sample, then run every CPU-only stage here at full scale** — the R-peak extraction,
the 12 task builders, the audits and the rule-based baselines. Only the GPU work goes
to the DGX. Everything saves its progress, so a power cut costs you the current chunk,
never the job.

---

## The DGX we actually have

| Fact | What it means |
|---|---|
| NVIDIA **DGX A100**, nodes `dgxa` / `dgxb` | Roughly 10–15× your laptop's GPU for this kind of work. |
| **Slurm** queue, partitions `cpu_student` and `gpu_student` | You submit a job and log off; it keeps running. **`cpu_student` is important** — the non-GPU heavy work goes there too. |
| **50 GB** storage | The one hard limit. Everything below is choreography around it. |
| Only reachable inside MU network | You remote into your friend's laptop to submit and check. |
| Account ends **31 Dec 2026**, data wiped 10 days later | ~4 months. Enough, but ask Aman for an extension in November rather than December. |
| Portal `http://10.59.121.175/dgx` | Ask your friend to note: max hours per job, GPUs allowed at once, jobs allowed in the queue. |

Change the emailed password on first login (`passwd`). Never put it in a file in this repo or
in cloud storage.

---

## Problems found, and what we do about each

| # | Problem | What we do |
|---|---|---|
| 1 | **The R-peak data task A4 needs does not exist.** The plan document says Phase 1 saved it; it did not — I opened the file and checked. | One new script. Runs on the DGX's CPU partition, a few hours. |
| 2 | Saved models would need 150–200 GB. We have 50 GB. | Keep only what the running job needs, copy the finished model out to R2 immediately, delete it locally. Details in "Storage rules". |
| 3 | 12-lead signals are 141.8 GB — nearly 3× the whole quota | Shrink to 56.7 GB (below), then feed it to the DGX in pieces during training. |
| 4 | A4's labels would take 2.3 GB stored the obvious way | Store the peak positions instead of a full-length list. Same information, 100× smaller. |
| 5 | Two config files still describe the old Plan-B-only setup | Rewritten in Step 1. Planned work. |
| 6 | You can never connect to the DGX from home | Slurm. Submit during a session, jobs survive, check at the next session. |
| 7 | **Unknown: can the DGX download from the internet?** | First thing to test. If yes it pulls from R2 itself. If no, your friend's laptop becomes the middleman. |
| 8 | **Unknown: is there scratch space beyond the 50 GB?** | Second thing to test. **If the compute nodes have local scratch, most of this plan's difficulty disappears** — we would stage the full 56 GB per job and stop juggling pieces. |
| 9 | Installing PyTorch would eat 12 GB of the 50 | Check for a ready-made container. Usually there is one, and it costs nothing against the quota. |
| 10 | Student queues often kill and restart jobs to make room | Every training job saves its progress every few minutes and restarts where it left off. |

---

## Shrinking the signals — and why it is not a compromise

The signal files are stored as "float32", a number format with far more precision than the
data actually contains. Re-storing them as "int16 with a per-record scale" makes them 60 %
smaller. Measured on your real data: the largest error is 0.001, on signals whose values
reach 70.

This is not a quality compromise, and here is the argument for the paper: **the original
MIMIC-IV recordings are themselves int16 measurements from the ECG machine.** Storing 15 bits
of precision relative to each record's own peak is *finer* than the resolution the hardware
recorded in the first place. We are not throwing away signal, we are throwing away zeros.

To prove it rather than assert it, Step 5 trains one small model twice — once on the original
float32 and once on the int16 copy — and confirms the results match. That check goes in the
supplementary material and the objection dies there.

| Data | Now | Shrunk |
|---|---:|---:|
| 12-lead filtered signals | 141.8 GB | **56.7 GB** |
| 12-lead raw signals | 67.5 GB | ~32 GB |
| Lead-II filtered | 11.85 GB | 4.7 GB |
| Lead-II raw | 5.67 GB | ~2.5 GB |

---

## The core idea: campaigns

We never ask "how do we fit 355 GB into 50 GB". We ask **"what is the smallest set of files
that lets us finish the largest number of training runs, and how do we finish those runs
before swapping the files out?"**

A **campaign** is one group of runs that all read the same data. We load that data once, run
every job that needs it, ship the results out, wipe the disk, and load the next campaign.
The DGX therefore only ever holds one campaign's worth of data.

Here is the full schedule. "Resident" is what sits on the DGX's 50 GB during that campaign.

| # | Campaign | Data on DGX | Resident | Runs | Rough GPU time |
|---|---|---|---:|---:|---:|
| ~~0~~ | ~~Build all task files + audits + baselines~~ | **moved to the laptop 2026-08-26 — see the amendment at the top. The EHR tables never go to the DGX.** | — | — | — |
| 1 | Text models | text + task files + fiducials | ~3 GB | 21 | ~23 h |
| 2 | Picture models, 12-lead | clean 12-lead pictures | ~12 GB | 21 | ~14 h |
| 3 | Picture models, Lead-II | clean Lead-II pictures | ~21 GB | 21 | ~14 h |
| 4 | Signal models, Lead-II | Lead-II signals (4.7 GB) | ~8 GB | 33 | ~8 h |
| 5 | Signal models, 12-lead, **L3 tasks** (A1/A3/A4/A6) | 12-lead signals for the L3 group | ~27 GB | 12 | ~6 h |
| 6 | Signal models, 12-lead, **full-cohort tasks** | 12-lead signals, **in pieces** | ~30 GB | 18 | ~10 h |
| 7 | **Combined end-to-end, L3 tasks** (A1/A3/A6) | signals + pictures + text, L3 group | ~32 GB | 9 | ~20 h |
| 8 | **Combined end-to-end, full-cohort** (A5/B4/B5/B6) | signals + pictures + text, **in pieces** | ~33 GB | 12 | ~30 h |
| 9 | Re-training sweeps (raw vs filtered, TF-IDF vs BERT) | raw signals, in pieces | ~30 GB | ~30 | ~25 h |
| 10 | Testing sweeps (scan-like pictures, corrupted signals) | test-split data only | ~20 GB | — (testing only) | ~6 h |
| 11 | Final evaluation, tables, figures | results files only | ~5 GB | — | ~4 h |

**Estimated total: roughly 160 GPU-hours**, which on one GPU is about a week of queue time,
and on three or four GPUs is two or three days. Add the queue waiting and the data swapping
and I would plan for **three to five weeks on the DGX**, not counting the two weeks of script
writing before it.

Campaigns 5 and 7 are worth pointing at: the four L3 tasks use a smaller patient group
(468K ECGs instead of 749K), and **their data fits on the DGX outright with no juggling at
all.** Half the hard work has no difficulty in it.

---

## Feeding data in pieces (campaigns 6, 8, 9)

Four campaigns have more data than fits. For those, we cut the training data into equal
pieces and cycle through them.

**How the pieces are made.** Every ECG is assigned to a piece by a scrambling function on its
study ID. Never by patient, date, label, or machine — that would make each piece a biased
sample and wreck the training. Each piece is a fair miniature of the whole.

**Signals and pictures are cut the same way**, so piece 3 of the signals and piece 3 of the
pictures cover exactly the same ECGs. The combined model can then train on one piece at a
time without needing everything at once.

**How training uses them.** Each round of training walks through all the pieces in a shuffled
order. While the GPU works on piece 3, the next piece is already downloading. When piece 3 is
done it is deleted and piece 4 is ready. Two pieces on disk at a time.

**Why this is fine for the science, in one line:** the model still sees every ECG in every
round of training, in a different order each time. That is ordinary training. What would
*not* be fine is training all the way through on piece 1 and then moving to piece 2 — the
model forgets piece 1 — and we are not doing that.

**Does the GPU end up waiting?** For the combined end-to-end models, one round of training is
roughly 8 minutes of GPU work and roughly 41 GB of downloading. At a good campus connection
(1 Gbps) the download takes ~6 minutes and hides completely behind the GPU work. If the
connection turns out slower, we run three jobs side by side sharing the same pieces — one
download then serves three jobs, and the waiting disappears again. This is why the piece
system works for end-to-end training when it would have been wasteful for the small models.

---

## Storage rules on the DGX (these keep us alive)

1. **Stay under 45 GB. Always.** Check with the command from Aman's email, on a compute node,
   before every launch. Running out of space mid-job on a machine you can only reach through
   a friend costs you a day.
2. **One campaign's data at a time.** Wipe before you load the next.
3. **Finished models leave immediately.** When a run ends: copy the best model and its
   predictions to R2, delete the working files. Nothing accumulates.
4. **The in-progress save file is the only heavy thing kept**, and only for jobs that are
   actually running. For the combined models that is about 2.4 GB each, so no more than three
   combined jobs run at once.
5. **The DGX never holds the only copy of anything.** The account is wiped in January.
6. Before each campaign the launch script checks free space and **refuses to start** if the
   campaign will not fit. Better a refusal than a job that dies at 90 %.

---

# THE PLAN — in order

## PART 1 — Your laptop. Short sessions, all interruptible. (~2 weeks)

The rule here: **write and test small, run big on the DGX.** Every script is developed
against a 5,000-ECG sample so it runs in minutes on your laptop. Nothing here needs your
laptop to stay on overnight, and every long-running step saves progress and resumes.

**Step 1 — Groundwork.** (~1 day, splittable)
Move the old leftover scripts to a `_legacy` folder. Rewrite the two config files to cover
all 12 tasks instead of the 6 old ones. Write the 5 new locked config files (diagnosis code
map, lab test map, corruption list, claim dictionary, Phase-2 lock file). Create the output
folders. Write the shared helper that reads signals and pictures.

**Step 2 — Write the 12 task builders + the missing R-peak script, and RUN them.**
(~1 week of writing, plus ~1–2 days of computer time)
Six for the A tasks, six for the B tasks, plus the R-peak extractor from problem #1.

Amended 2026-08-26: each script is smoke-tested on the 5,000-ECG sample first — two
minutes, and it catches the bugs — and then **run at full scale here on the laptop**.
The R-peak extraction is the long one, roughly 5–10 hours over the 468 K-study group.
Start it, let it run, write the next builder while it works.

Every full-scale script must save its progress and resume cleanly. That is what makes
a power cut cost you twenty minutes instead of eight hours.

**One prerequisite the lab-results task needs first.** The cached lab table
(`data/raw/ehr_cache/labevents.parquet`) kept only `valuenum` — it dropped
`ref_range_lower`, `ref_range_upper` and `flag`, and the A3 abnormality rule is built
entirely on those three. They exist in the original download
(`data/raw/mimic-iv-hosp-3.1/hosp/labevents.csv.gz`, 2.6 GB compressed, 158 M rows).
Re-extract the cache for the 18 locked lab item IDs, keeping those columns, before
writing A3. This is extending a cache, not re-running Phase 1 — no Phase 1 output
changes.

**Step 3 — Write the training and evaluation code.** (~3–4 days)
The three model types, the combined end-to-end model, the trainer with save-and-resume, the
evaluation script. Test each on the sample, on your laptop's GPU, with tiny batches. You are
proving the code runs, not producing results.

**Step 4 — Write the piece-cutter and the campaign launchers.** (~2 days)
The script that cuts data into matching pieces, the download-train-upload-delete loop, and
one Slurm submission file per campaign.

**Step 5 — Make the shrunk copies and prove they are equivalent.** (~1 day of computer time,
resumable per file)
Convert the signals to int16, one file at a time so a power cut costs one file. Then train
one small model on both versions and confirm the results match — this is the evidence for the
"not a compromise" argument above.

**Step 6 — Start uploading.** (nights, over about a week)
Upload in the order the campaigns need things, so the DGX is never waiting on you:

| Upload | Size | Needed by |
|---|---:|---|
| Code, configs, **finished task files**, fiducials, indexes, Lead-II signals, corrupted signals | ~7 GB | Campaign 1 |
| Text file | 0.2 GB | Campaign 1 |
| Clean 12-lead pictures | 8.9 GB | Campaign 2 |
| Clean Lead-II pictures | 17.8 GB | Campaign 3 |
| 12-lead filtered signals, in pieces | 56.7 GB | Campaigns 5–8 |
| 12-lead raw signals, in pieces | ~32 GB | Campaign 9 |
| Scan-like pictures, 12-lead, in pieces + val/test | 62.6 GB | Campaigns 2, 8, 10, 11 |
| Scan-like pictures, Lead-II, in pieces + val/test | 39.1 GB | Campaigns 3, 13, 14, 15 |
| Clean Lead-II pictures, in pieces + val/test | 17.9 GB | Campaigns 13, 14 |

**About 262 GB in total, uploaded over the whole project, not at once.** (Was ~142 GB
before open question 16 added the scan-like train/val data — 120 GB of it — which the
A5/B4 tasks always needed and nothing had staged.)

The finished task files are small — they hold study IDs and labels, never signal or
image bytes. Storage cost is around ₹330/month, and downloading it to the DGX costs
nothing. Uploads resume after an interruption, so power cuts and dropped connections
are not a problem.

*If your home upload speed makes this painful:* an alternative is to put everything on a
256 GB portable drive and courier it to your friend. Their laptop then serves the data to the
DGX over the campus network, which is much faster than the internet. Their laptop has to be
switched on, which is why R2 is the main plan and this is only a backup.

---

## PART 2 — First session on your friend's laptop. (~1 hour)

**Step 7 — Find out what we're working with.** Save all output and send it to me.

1. `curl -sI --max-time 10 https://cloudflare.com` → **can the DGX reach the internet?**
2. `df -h $HOME; ls -d /scratch /raid /work /tmp /mnt/* 2>/dev/null; df -h /raid /tmp` →
   **is there space beyond the 50 GB?** Run it on a compute node too, not just the login node.
   **This is the single most valuable answer** — local scratch would remove the piece-cutting
   from campaigns 6, 8 and 9 entirely.
3. `sinfo` + the portal → hours per job, GPUs per student, jobs allowed in the queue.
4. `nvidia-smi` → how many GPUs, 40 GB or 80 GB, how busy.
5. `enroot version; module avail 2>&1 | head -40` → is there a PyTorch container?
6. Time a 1 GB download from R2 → tells us whether pieces can keep up with the GPU.
7. `passwd` → change the emailed password.

**Step 8 — Set up and prove it works.** Create the folders, set up the download tool with a
read-only key for data and write access only to the results folder, copy one small file both
ways, then **submit a 5-minute test job through Slurm and watch it finish while your friend is
still there.** The first real launch must never be a script's first run on that machine.

---

## PART 3 — Build everything, on your laptop. (~2 days of computer time)

**Amended 2026-08-26.** This part used to run on the DGX's `cpu_student` partition as
"Campaign 0". It runs at home now. Steps 9 to 12 keep their numbers so the ledger in
`docs/PHASE2_PROGRESS.md` still lines up, but Steps 9 and 11 have already happened by
the time you reach this point in the plan — they are done as part of Steps 2 and 3.

**Step 9 — Run the 12 task builders and the R-peak extractor at full scale, locally.**
Done during Step 2. The R-peak extraction is ~5–10 hours; the builders are shorter.
Everything checkpoints, so a power cut costs the current chunk.

The lab-results task is the memory-hungry one — it matches 7 lab tests across 5 time
windows against a 158 M-row table. On 32 GB of RAM that means reading the lab table
**filtered to the 18 locked item IDs and to the columns actually needed**, never
loading it whole. Filtered, it is about 21 M rows and fits comfortably.

**Step 10 — Run the three checking scripts.** Leakage (is any model being fed the
answer?), cohort (how many patients, how many positives, how much is missing?), split
(is any patient in two groups?). Minutes, not hours.

> **All three must say PASS. Everything downstream is built on these files.** If one
> fails, we fix it now — not after 160 GPU-hours. Because this now happens at home,
> the gate closes *before* the first upload rather than after it.

**Step 11 — Run the rule-based baselines** locally (no learning involved). These are
the reference numbers the paper needs. They are NeuroKit2 over the test split, so
budget hours, not minutes, and let them run overnight.

**Step 12 — Review the cohort report** and confirm the numbers look right. Nothing to
pull down any more; it is all already here. **This is the point where uploading
starts** — the task files are finished and audited, so Step 6's first upload can go.

---

## PART 4 — Campaigns 1 to 4: the straightforward training. (~1 week)

These four campaigns need no piece-cutting — the data fits.

**Step 13 — Campaign 1, text models.** 21 jobs. Data is 0.2 GB. If the DGX has no internet,
the Bio-ClinicalBERT files (450 MB) must be copied in by hand — that is what Step 7.1 tells
us. The simple TF-IDF version runs on the CPU partition alongside.

**Step 14 — Campaign 2, 12-lead picture models.** Load 8.9 GB, run 21 jobs, results out,
wipe.

**Step 15 — Campaign 3, Lead-II picture models.** Load 17.8 GB, 21 jobs, results out, wipe.

**Step 16 — Campaign 4, Lead-II signal models.** 4.7 GB covers every ECG. 33 jobs.

After each campaign: results in R2, disk wiped, next campaign loaded. You check in whenever
you can get to your friend's laptop; the queue does not need you.

---

## PART 5 — Campaigns 5 and 6: 12-lead signal models. (~1 week)

**Step 17 — Campaign 5, the L3 tasks (A1, A3, A4, A6).** 21.7 GB of training data fits
outright. 12 jobs, no juggling.

**Step 18 — Campaign 6, the full-cohort tasks.** 34.7 GB, so this one uses pieces. 18 jobs.
Run several side by side so one download serves several jobs.

---

## PART 6 — Campaigns 7 and 8: the combined end-to-end models. (~1.5 weeks)

This is the heart of the paper and the heaviest computing in the project.

**Step 19 — Campaign 7, combined models for A1, A3, A6.** Signals, pictures and text for the
L3 group total about 32 GB — **it fits, no juggling.** 9 jobs, roughly 2 hours each. All three
parts of the model train together, properly, end to end.

**Step 20 — Campaign 8, combined models for A5, B4, B5, B6.** The full patient group, so this
one uses matched pieces of signals and pictures. 12 jobs. At most three at a time because of
the save-file size.

**Step 21 — The free extra.** While the combined models are training we also get the
"frozen" version almost for nothing, since the pieces are already computed. That becomes a
supplementary comparison — "end-to-end vs frozen" — which strengthens the paper and answers a
question a reviewer would otherwise ask.

---

## PART 7 — Campaigns 9 to 11: sweeps, evaluation, and the paper. (~1.5 weeks)

**Step 22 — Campaign 9, the sweeps that need re-training.** Raw vs filtered signals, TF-IDF
vs BERT. Uses raw signals in pieces.

**Step 23 — Campaigns 10 and 15, the scan-like image arm.** **CORRECTED 2026-09-30
(spec §12.10, open question 17).** This step used to read "the sweeps that only need
re-testing… only the test portion needs uploading", and that was wrong. The scan-like
image tier **trains**: §5.3 turns augmentation on "when training on scan-like" and
`model_configs.py` sets it on every `*_scanlike` config and on no `*_clean` one, and
augmentation is applied only when `split == "train"`. It is the image-side analogue of
§7.3's B2 regimes, where the clean-trained and corruption-augmented arms are both
trained. Its 30 runs are part of the 104 configs / 312 runs the spec counts.

So it needs scan-like **train+val**, which is 50.08 GB for 12-lead and 31.24 GB for
Lead-II — hence the p8 cut (§8.2 rule 1) and the **split by lead subset**: campaign 10
is the 12-lead half, campaign 15 the Lead-II half, 15 runs each. It also stages the
CLEAN container, because its A5/B4 rows choose the rendering per row.

The genuinely re-testing-only sweeps — the SQI tiers, Lead-II vs 12-lead,
first-ECG-per-patient, the lab time windows — are evaluation-side slices of models
trained elsewhere and need no campaign of their own.

**Step 24 — Campaign 11, final evaluation.** Every model, every task, every seed, plus the
confidence intervals (10,000 patient-level bootstrap rounds). Then the calibration, threshold
and reproducibility checks.

**Step 25 — Tables and figures.** 5 main tables, 5 main figures, 15 supplementary tables,
8 supplementary figures. These are small and quick, so run them wherever is convenient —
your laptop is fine, and each one takes minutes.

**Step 26 — The release package.** Scripts, configs, checksums, and a README walking a
reviewer through reproducing every number. Never any raw data.

---

## Timeline

| Part | What | How long |
|---|---|---|
| 1 | Write and test everything on your laptop | ~2 weeks |
| 2 | First DGX session | 1 hour |
| 3 | Build task files, audits, baselines (**on your laptop**) | ~2 days |
| 4 | Text, picture, Lead-II signal models | ~1 week |
| 5 | 12-lead signal models | ~1 week |
| 6 | Combined end-to-end models | ~1.5 weeks |
| 7 | Sweeps, evaluation, tables, figures | ~1.5 weeks |
| | **Total** | **~7–8 weeks**, plus queue waiting |

Your account expires 31 December. That leaves comfortable margin, but **ask Aman for an
extension in November**, not in the last week.

Your laptop is needed for a few hours a day in Part 1 and occasionally after that. A power
cut costs you the current session, never the project.

---

## What I still need from you

**Nothing is blocking.** Your three rules resolved every open decision — end-to-end
everywhere, DGX for all heavy work, nothing skipped. **I can start Step 1 now.**

Two things I need *soon*, but not to start:

1. **The Step 7 answers**, especially whether there is scratch space beyond the 50 GB and
   whether the DGX can reach the internet. The first would let me delete the piece-cutting
   work from three campaigns; the second decides whether your friend's laptop has to act as
   a middleman. Neither changes Part 1.
2. **Your home upload speed** (any speed test). If it is slow, we start the big signal upload
   earlier, or switch to the portable-drive option.

One choice I made for you rather than asking, since it follows from your rules: **the sweeps
that only need re-testing (Step 23) run on the DGX too**, not on your laptop. It costs about
20 GB more uploading, and it keeps your laptop off the critical path entirely. Say the word
if you would rather save the upload and run those at home instead.
