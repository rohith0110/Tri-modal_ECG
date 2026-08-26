<!-- Scaffolded by Stage P2.0, 2026-08-26. See docs/PHASE2_SOURCE_OF_TRUTH.md section 3. -->

# `outputs/model_runs/` - per-run training artifacts

One tree per task x arch tier x seed:

```
<task>/<arch_tier>[_<lead_subset>]/seed_<n>/
    checkpoint_best.pt        # weights only (~0.6 GB for fusion)
    checkpoint_last.pt        # weights + optimizer + scheduler + RNG, for resume
    train_log.jsonl           # canonical machine-readable log, one row per epoch
    train_config.yaml         # snapshot of the resolved config for this run
    val_predictions.parquet
    test_predictions.parquet
```

**Retention (Round 5.4).** On the DGX the 50 GB quota caps resident checkpoints
at 5 GB. When a run completes, `checkpoint_best.pt`, `test_predictions.parquet`
and `train_log.jsonl` are pushed off-node and BOTH local checkpoints are
deleted. Nothing accumulates. At most 3 concurrent end-to-end fusion jobs.

Nothing in this directory is tracked in git.

*(Files predating Phase 2 here belong to the Plan-B benchmark and are not
Phase 2 artifacts.)*
