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
