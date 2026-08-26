<!-- Scaffolded by Stage P2.0, 2026-08-26. See docs/PHASE2_SOURCE_OF_TRUTH.md section 3. -->

# `outputs/results/` - aggregated per-task metrics

Written by `40_aggregate_results.py` (Stage P2.9) and `41_run_sensitivity.py`
(Stage P2.10). Nothing here is hand-edited.

| File | Producer | Contents |
|---|---|---|
| `<task>.csv` | `40_aggregate_results.py` | one row per (head, group): metric mean +/- std across the 3 seeds, pooled-prediction bootstrap CI |
| `<task>_sensitivity_<sweep>.csv` | `41_run_sensitivity.py` | one file per sweep in spec section 7.2 |
| `all_tasks_summary.csv` | `40_aggregate_results.py` | `task, arch_tier, lead_subset, primary_metric_name, metric_mean, metric_std, ci_low, ci_high, n_ecg_test, n_subj_test, n_pos_test` - the data source for the main-paper headline figure |

These CSVs are the one part of `outputs/` small enough and textual enough to be
committed; `.gitignore` re-includes this directory explicitly.
