<!-- Scaffolded by Stage P2.0, 2026-08-26. See docs/PHASE2_SOURCE_OF_TRUTH.md section 3. -->

# `config/eval_configs/` - evaluation settings

Consumed by `31_eval.py` and `41_run_sensitivity.py`. Empty until Stage P2.9.

| File | Adds |
|---|---|
| `default.yaml` | bootstrap n / CI method / subgroup keys shared by every task |
| `A4_fiducial.yaml` | +/-10 ms peak matcher, event-count distribution buckets (spec section 7.4) |
| `A6_risk.yaml` | calibration block: reliability bins, ECE, Brier, decision-curve thresholds (spec section 7.6) |
| `B2_robustness.yaml` | regime-1/2/3 split, AUCC, collapse threshold (spec section 7.3) |
| `cross_modal.yaml` | A5/B4/B6 verification + 100-candidate retrieval pool (spec section 7.5) |

Defaults live in `config/decision_phase2.yaml` under `evaluation:`; these files
only add the per-task extras.
