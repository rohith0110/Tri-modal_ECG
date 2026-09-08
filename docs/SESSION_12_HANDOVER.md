# Session 12 handover — driving campaign 1 from the on-campus laptop

**Written 2026-09-08.** This is a narrative companion to the two canonical
documents, not a replacement for either:

| read | for |
| ---- | --- |
| `docs/PHASE2_PROGRESS.md` | **the live state.** Always first, every session. |
| `docs/DGX_OPERATOR_HANDOVER.md` | **the operating rules** — machines, Slurm, §3a–§3d. |
| this file | what session 12 did, what it learned the hard way, and why the code looks the way it does. |

Session 12 ran from 2026-08-30 to 2026-09-08. It took the project from "the
venv does not exist" to "campaign 1's first task is finished, published and
audited", and it found **eleven defects** on the way, one of which had already
produced a day and a half of confidently wrong results.

---

## 1. Where things stand (2026-09-08 09:50 UTC)

```
22737 c1_B4          gpu_student  R   training B4
22838 trimodal_eval  cpu_student  R   A6 / text_bioclinicalbert    45 units done
22839 trimodal_eval  cpu_student  R   A6 / text_tfidf              46 units done
22854 trimodal_eval  cpu_student  R   A3 / text_tfidf             312/2940 units
22853 c1_A5          gpu_student  PD  resumes seed 456
22738 c1_B5          gpu_student  PD
```

| task | training | results CSV |
| ---- | -------- | ----------- |
| **A1_ecg_diagnosis** | 6/6 complete | **YES — published to R2** |
| A3_lab_abnormality | 6/6 complete | eval running (2,940 units/tier) |
| A6_risk_stratification | 6/6 complete | eval running |
| A5_cross_modal_verification | 2/6 complete | seed 456 resumes from checkpoint |
| B4_cross_modal_verification | 0/6 — training now | — |
| B5_contradiction_detection | 0/6 — queued | — |

Disk 12 GB of the 49 GB ceiling. 36 commits, `f13be9a`..`HEAD`, all pushed.

---

## 2. The one that matters: every tf-idf run trained BioClinicalBERT

**This is the most important thing in this document.** For a day and a half,
`text_tfidf` runs trained BioClinicalBERT and wrote their results under
`text_tfidf/`.

```python
# the configs name encoder CLASSES
encoder: TfidfTextEncoder
# plan_from_config lower-cased that
plan.text_encoder = "tfidftextencoder"
# and the model builder defaulted anything unrecognised to BERT
TfidfPassthrough() if plan.text_encoder == "tfidf" else BioClinicalBertEncoder(...)
```

`BioClinicalBert`.lower() happens to equal `"bioclinicalbert"`, so **the BERT
tier was correct by luck**; only tf-idf fell through. Nothing raised. Checksums
passed, the audits passed, the smoke test passed, and every run wrote a
`train_config.yaml` faithfully saying `encoder: TfidfTextEncoder`.

**What caught it:** the two tiers returned identical `macro_AUPRC` to four
decimals, identical epoch counts and an identical 7.814 GB peak. Nothing else
would have.

Fixed in `1e266f2` (canonical aliases; both switch points raise on unknown) and
`04ff100` (the plan must match the `arch_tier` name). After the fix tf-idf runs
at **148 it/s against BERT's 4.9** — it had never executed once.

**The lesson, and the reason for three of the guards below:** a silent fallback
in a dispatch table is indistinguishable from success. Prefer raising.

---

## 3. Every defect found, in order

| # | defect | commit |
| - | ------ | ------ |
| 1 | `smoke_test.py` spawned a hard-coded `ecg_env/Scripts/python.exe` — a Windows path, absent on Linux | `f13be9a` |
| 2 | Quota ceiling 45 GB counted the 5.7 GB venv; campaign 7 had ~1 GB margin. Raised to 49 in **both** places it is written | `f13be9a`, `859cd8a` |
| 3 | Every tracked `*.sh` was mode `100644`; `core.fileMode=false` on Windows hid it. `stage_data.sh` died with exit 126 | `23ceade` |
| 4 | rclone lives at `$PROJECT_ROOT/bin` and reaches PATH via `.bashrc`, which a **Slurm batch shell never sources** → `transport=none` | `6f15ca3` |
| 5 | HuggingFace fork/Hub deadlock: main in `futex_wait`, four workers at 0 CPU, 15 s of CPU across 10 minutes. transformers 5.x re-resolves the model per forked worker | `74f2a8b` |
| 6 | Staging `code` from R2 **silently reverted five tracked files mid-session**, including the fix the same script needed. Caught only by a `45 GB ceiling` line in a log | `7d3602d` |
| 7 | **The tf-idf/BERT collision** (§2 above) | `1e266f2` |
| 8 | `stage_data.sh` verified *nothing* when nothing was staged — absent files counted as neither ok nor bad | `b61af7e` |
| 9 | `smoke_test.py`'s recovery checks were pinned to a signal tier, so a scoped text run reported FAILs about a missing `.h5` | `b61af7e` |
| 10 | Three bugs in the new CPU-eval route: wrong `eval_task.sbatch` path (evals silently fell back **onto the GPU**), wrong `push_results.sh` path, and the **read-only** `r2` remote inherited from the laptop default | `012d576`, `a059d94` |
| 11 | `push_results.sh` pushed only `model_runs/` — **the results CSVs and figures were never published at all** | `32796ac` |

Several were introduced while fixing the others, and the identical-tier gate was
itself inert at first (`0e8ca7d`). The pattern is consistent: **every one was
silent.** None crashed.

---

## 4. Guards now in place (all verified, not merely written)

1. **`plan_from_config` asserts the plan matches the `arch_tier` name** — a
   tfidf tier must produce tfidf, a `notext` tier no text, a `signal_`/`image_`
   tier that modality. Policy-aware (B5 legitimately has no image block).
   **Validated: 104/104 configs accepted, and re-injecting the original bug is
   caught.**
2. **`31_eval.py` refuses to write when two arch tiers give bit-identical
   metrics** (`--allow-identical-tiers` overrides). It compares against the
   accumulated per-task CSV, because the campaign runs one tier per process —
   the first version could never have fired (`0e8ca7d`).
3. **Skip-if-complete** in `_campaign_body.sh` — which also closes a latent bug
   where a wall-clock requeue silently retrained every finished run.
4. **`validate=` on all 42 merges**, classified per right-hand table
   (39 `many_to_one`, 3 `many_to_many` for deliberate fan-outs).
5. **Empty staging now fails** instead of verifying vacuously.
6. **Checkpoint stamping** — eval checkpoints record their bootstrap settings, so
   a `--bootstrap-n 200` debug run can never be adopted as a 10,000-iteration CI.

---

## 5. Measured facts about this cluster (do not re-derive)

* **`gres/gpu=1`.** One GPU at a time, of any kind — a MIG slice counts as a
  whole GPU. Six shards on six free slices were refused with `AssocGrpGRES`.
  **All 312 runs are sequential.** Raising this with the facility is the single
  highest-leverage action available to the project.
* **`cpu=32`, shared.** Evaluation on CPU runs *concurrently* with GPU training —
  but three 8-core evals plus a shard fill the cap exactly, and then **a training
  job pends on CPUs with a GPU sitting free.** Keep eval cores at 24 or below.
* **dgxa's two full A100s were held by faculty for 14–19 days**, and dgxb's five
  churn straight back to faculty. Slurm quoted **three weeks** for a full card;
  a `4g.20gb` slice allocated in about twenty seconds. **Do not wait for a full
  card.**
* **`peak_gpu_gb` = 7.814** for a BioClinicalBERT run — fits a 10 GB
  `a100_2g.10gb` slice, does not fit 5 GB.
* **Throughput:** BERT ~4.9 it/s on a 20 GB slice; tf-idf ~148 it/s. Early
  stopping fires at 9–13 of the 20 allowed epochs.
* **Task sizes are wildly unequal.** A1 is 8,218 batches/epoch; A5 is **101,409**.
* **Evaluation cost:** ~29 core-minutes per unit. A1 had 300 units, A6 1,470,
  A3 **2,940**. The bootstrap is **82 % sklearn metric, 18 % resampling** —
  vectorising the gather (`b825f34`) bought only ~1.2x. The real levers are the
  metric or `n_iter`, and §6.7 locks `n_iter: 10000`.
* **The facility cancelled four queued jobs** on 2026-09-02 (`CANCELLED by 0`,
  uid 0 = an administrator), none of them started. **Nobody has asked why yet.**

---

## 6. Results so far — A1_ecg_diagnosis

75,187 test rows, 19,168 subjects, three seeds pooled, patient-level BCa CIs.

| label | positives | BioClinicalBERT AUPRC | tf-idf AUPRC |
| ----- | --------- | --------------------- | ------------ |
| atrial fibrillation / flutter | 22,338 | 0.7143 [0.7002–0.7273] | **0.7194** [0.7058–0.7322] |
| heart failure (narrow) | 22,608 | 0.5728 [0.5548–0.5896] | **0.5900** [0.5723–0.6070] |
| acute myocardial infarction | 8,003 | 0.2671 [0.2488–0.2857] | 0.2669 [0.2487–0.2854] |
| conduction disorder | 5,281 | 0.2441 [0.2233–0.2695] | 0.2428 [0.2231–0.2664] |
| ventricular arrhythmia / arrest | 3,563 | 0.1101 [0.0956–0.1272] | 0.1150 [0.0996–0.1327] |

**tf-idf matches or beats BioClinicalBERT on every head**, decisively on heart
failure. AUROC spans 0.706–0.827. Calibration is poor for both (**ECE ~0.23**);
the reliability plots are in `r2-results/figures/main/`.

Two caveats for whoever writes this up. A1's label comes from ICD codes on the
same encounter as the report, so a text-only tier is largely reading a
clinician's own description — this is a text-to-code task, not ECG
interpretation. And the rare labels (ventricular arrhythmia, 3,563 positives)
sit near the prevalence floor: unlearned from text alone.

---

## 7. Traps that will bite the next agent

* **Use `/c/WINDOWS/System32/OpenSSH/ssh.exe`, not git-bash's `ssh`.** The key
  lives in the *Windows* ssh-agent; git-bash cannot reach it and fails with a
  `Permission denied (publickey,password)` that looks exactly like a missing
  `authorized_keys`.
* **Killing an `ssh` does not cancel the `srun` it started.** `scancel` it.
* **A Slurm batch shell sources neither `.bashrc` nor the campaign body**, so a
  standalone job inherits `campaigns.sh`'s laptop defaults — including
  `R2_RESULTS=r2:...`, which on the DGX is the **read-only** token.
* **Anything the agent runs locally dies with the session.** Automation that must
  outlive it belongs in a `cpu_student` batch job, holding no GPU, with a real
  fallback — `slurm/swap_watcher.sbatch` is the worked example.
* **`--requeue` does not requeue on TIMEOUT.** A5 was killed at its 96 h limit
  and marked FAILED; only the SIGTERM handler's `checkpoint_last.pt` saved it.
  Long tasks need the 7-day limit (partition max) and a manual resubmit.
* **Evals and training share the CPU cap.** Check before submitting another:
  `squeue -u $USER -h -t R -o "%C" | paste -sd+ | bc`
* **Verify a push by listing the bucket**, never by trusting
  `pushed N run(s), 0 failure(s)` — that line counts *runs*, and it was true for
  a week while every results CSV sat on the DGX alone.

---

## 8. Open items

1. **Ask the facility about the `CANCELLED by 0` jobs**, and ask to raise
   `gres/gpu` above 1. Everything else here is a workaround for that cap.
2. **A5 must be resubmitted after each 7-day window** until seed 456 and the
   three tf-idf seeds finish. It resumes from `checkpoint_last.pt`.
3. **A3 and A6 evals are long** (2,940 and 1,470 units). They are checkpointed
   and resumable; keep them fed and under the core cap.
4. **B5's `multimodal_fusion` tier is two modalities** where every other task's
   is three, because its input policy forbids images. Correct, but cross-task
   fusion comparisons are not like-for-like — the paper should say so.
5. **`n_iter: 10000` is the project's dominant compute cost.** If the schedule
   matters more than CI width, that is a spec decision (§6.7) for the owner.
6. Campaigns 2–14 have not started. Campaign 1 is **Step 13 of 26**.

---

## 9. Prompt for the next session

Paste this into Claude Code on the on-campus laptop:

> I'm on the on-campus laptop that can reach the MU DGX. The Tri-Modal ECG repo
> is cloned here; the datasets are NOT on this machine and never will be — they
> live on the owner's laptop and in `r2:trimodal-data`. My job is to drive the
> DGX over SSH.
>
> Read `docs/PHASE2_PROGRESS.md` first, then `docs/DGX_OPERATOR_HANDOVER.md`
> (especially §3a–§3d), then `docs/SESSION_12_HANDOVER.md` for how we got here.
> Run `git pull` locally and on the DGX before anything.
>
> **Use `/c/WINDOWS/System32/OpenSSH/ssh.exe mudgx '<command>'`** — git-bash's
> own `ssh` cannot reach the Windows ssh-agent and its failure looks exactly
> like a broken key. No password should ever be requested; if one is, stop and
> tell me rather than working around it.
>
> We are mid-campaign 1 (Step 13 of 26): A1 is finished and published; A3 and A6
> are trained with evaluations running; A5 is part-trained and resumes from a
> checkpoint; B4 is training; B5 is queued. Evaluations run as separate
> `cpu_student` jobs and are checkpointed and resumable.
>
> Start by checking `squeue -u $USER`, the per-task run counts under
> `outputs/model_runs/`, and the eval checkpoint line counts — then tell me what
> state things are in before changing anything on the DGX.
>
> Non-negotiables, all measured: the account holds **one GPU at a time**, so
> never expect concurrency from training; **`cpu=32` is shared** with the eval
> jobs, so keep eval cores at 24 or below or a training shard will pend with a
> GPU free; ask for a **MIG slice on dgxa** (`a100_4g.20gb`, or `a100_2g.10gb` —
> a BERT run peaks at 7.8 GB), never wait for a full A100; every job needs
> `--mem`; stay inside the 49 GB ceiling; the repo stays private because tracked
> reports carry MIMIC identifiers.
>
> And the habit this project was built on: **verify by measuring, not by reading
> a success line.** A day and a half of runs once trained the wrong model while
> every log said they had succeeded.
