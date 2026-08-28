<!-- Scaffolded by Stage P2.0, 2026-08-26. See docs/PHASE2_SOURCE_OF_TRUTH.md section 3. -->

# `scripts/dgx_portability/` - campaign staging and job submission

These are the REAL launchers, not templates (spec section 8.2). Empty until
Step 4 of `docs/PHASE2_EXECUTION_PLAN_DGX.md`.

```
stage_data.sh              # pull one campaign's data, verify checksums, refuse if it won't fit
evict_data.sh              # wipe the current campaign's data after results are pushed
push_results.sh            # best checkpoint + predictions + logs off-node, then delete local
make_chunks.py             # cut oversized modalities into aligned i.i.d. pieces
slurm/campaign_<n>.sbatch  # one submission file per campaign
```

## The two rules that bind the science, not just the operations

1. **Chunking is i.i.d. and modality-aligned.** When a campaign exceeds the
   quota, the TRAINING split is cut into equal pieces keyed by a hash of
   `study_id` - never by subject, admission, label, cart_id or time. Signal and
   image pieces use the SAME key, so piece *k* of each modality covers the same
   studies. Each piece is a fair miniature of the split.
2. **Chunks cycle WITHIN each epoch, never across epochs.** Every epoch visits
   every piece in a reshuffled order, with a shuffle buffer inside each piece;
   two pieces are resident at a time (train on *k*, prefetch *k+1*, evict
   *k-1*). Training to convergence on piece 1 and then moving to piece 2 is
   **forbidden** - that is block-local SGD and it catastrophically forgets.
   The block-shuffled sampling that IS used is recorded as a documented
   deviation in `config/decision_phase2.yaml` and disclosed in the
   supplementary.

## Quota rules

- 50 GB total, shared across env, data, checkpoints and logs.
- A launcher checks free quota **before** submitting and refuses if the
  campaign will not fit under 45 GB. A refusal beats a job that dies at 90 %.
- Check quota on a **compute** node, never the login node:
  `du -sh "$PWD"`
- Resident checkpoints <= 5 GB; at most 3 concurrent fusion jobs.

## Recovery

- A requeued job resumes from `checkpoint_last.pt`; if the file is gone it is
  re-pulled from `r2:trimodal-results`.
- No Phase 2 artifact may exist only on the DGX. The account expires
  2026-12-31 and data is purged 10 days later.
- `rclone lsd r2:` returns 403 by design - the tokens are bucket-scoped.
  Always name the bucket: `rclone lsd r2:trimodal-data`.

## Never

Credentials (DGX password, R2 keys/secrets) live in the password manager and in
the local rclone config only - never in this repo, any doc, any script or any
commit. Raw MIMIC never leaves the laptop and never enters the release package.

---

## Written at Step 4 (2026-08-28)

```
campaigns.sh          # campaign table + shared helpers (quota, transport, roots)
campaign_runs.py      # campaign number -> its <task> <arch_tier> <seed> run list
make_chunks.py        # plan / cut / verify the i.i.d. modality-aligned pieces
stage_data.sh         # refuse-then-pull one campaign, verify checksums
evict_data.sh         # wipe a campaign, a piece set, or everything
push_results.sh       # push a finished run, verify, then delete its checkpoints
slurm/_campaign_body.sh    # shared body: detect env, stage, run, push
slurm/campaign_NN.sbatch   # 11 thin per-campaign submission files
```

### Everything the DGX survey (Step 7) has not answered yet

Nothing here assumes a verified machine. Each unknown is **detected**, with a
fallback, rather than hard-coded:

| Unknown | What the scripts do |
| --- | --- |
| Outbound internet? | `transport()` picks `rclone` only if `curl` reaches the network; otherwise `rclone-offline`, or a plain directory via `TRIMODAL_SOURCE` (the courier-a-drive fallback), or a clear refusal naming both options. |
| Node-local scratch? | `resolve_data_root()` tries `$SCRATCH`, `/scratch/$USER`, `/raid/$USER`, `/work/$USER`, `/tmp/$USER`, then `$HOME`. First writable one wins. Override with `DATA_ROOT`. |
| Partition names? | **No `--partition` is written into any sbatch file** — a wrong name is a submit-time rejection. Pass it: `sbatch --partition=gpu_student campaign_04.sbatch`. |
| GPUs per job, time limits? | `--gres=gpu:1`, `--cpus-per-task=8` and a 2x-estimate wall clock are conservative floors, all overridable at submit time. |
| PyTorch module or container? | `activate_python()` tries the active venv, the project venv, `$HOME/ecg_env`, then any `module avail` entry matching `pytorch`, then system `python3` — and each candidate must actually `import torch` before it is accepted. |

### Two decisions made at Step 4

1. **The 94-config matrix is the authority on run counts, not the plan's table.**
   `campaign_runs.py --table` derives each campaign's runs from the generated
   configs, and all 94 map to exactly one campaign with none orphaned (the
   command exits non-zero if that ever stops being true). The totals differ from
   the estimates in `PHASE2_EXECUTION_PLAN_DGX.md` because that table predates
   the locked matrix — e.g. campaign 1 is 12 configs x 3 seeds = 36 runs, not
   the 21 estimated. Trust `--table`, and treat the plan's numbers as the
   sizing estimates they were.
2. **Lead-II raw signals stay in campaign 4, not the campaign-9 sweep.** A
   campaign is defined by the data it reads (§8.2), and both Lead-II encodings
   are already resident in campaign 4 at only 5.7 GB. Campaign 9 carries the
   12-lead raw set, which is the ~32 GB that actually needs pieces.

### Verified at Step 4, on this laptop

- `make_chunks.py plan --kinds preprocessed_12lead image_clean_12lead --pieces 8`:
  523,945 train studies, piece sizes 65,260-65,758 (**0.40 %** max deviation),
  and **0 of 523,945 studies disagree** between the two modalities — §8.2 rule 1's
  alignment requirement, measured rather than asserted. Independence from the
  label-like strata: cart_id chi2 46.9/dof 70, hr_bucket 12.5/14, link_tier
  15.5/21, stratum 80.6/70.
- The quota gate refuses at 44 GB used + 30 GB asked, exit 1, before any byte moves.
- A chunked campaign without `--pieces` refuses rather than staging everything.
- A failed push leaves checkpoints **untouched**; a verified push deletes them.
- The evict guard was tested in all four states (never pushed / just pushed /
  new result after push / `--force`) and behaves correctly in each.

**No acquisition timestamp exists in any processed index**, so independence of
the pieces from TIME cannot be measured directly. The nearest evidence is that
consecutive study ids scatter across all pieces (asserted in the self-check).
Add `ecg_time` to the metadata and `STRATA` in `make_chunks.py` covers it with
no other change.
