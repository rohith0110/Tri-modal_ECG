# `scripts/` — Tri-Modal ECG Pipeline

> **Status 2026-08-26.** Phase 1 is **complete and audited** — its scripts
> produced the current 355 GB dataset and should not be re-run. Phase 2
> **has not started**: everything currently in
> `phase2_tasks_benchmark_and_paper/` is pre-regen legacy (see that
> folder's README) and gets quarantined to `_legacy_phase1_pre_regen/` in
> Stage P2.0. New Phase 2 code lands in that folder afterwards, alongside
> `_dataset_lib/`, `_model_lib/`, `_train_lib/` and
> `../dgx_portability/`.
>
> Plans: `docs/PHASE2_SOURCE_OF_TRUTH.md` (what to build) and
> `docs/PHASE2_EXECUTION_PLAN_DGX.md` (where it runs).

All pipeline code lives here, split into two phases.

```
scripts/
├── phase1_dataset_generation/        # raw MIMIC-IV ECG  ->  on-disk tri-modal dataset
└── phase2_tasks_benchmark_and_paper/ # tri-modal dataset ->  task JSONLs, audits, models,
                                      #                       benchmark figures, paper figures
```

- **[Phase 1 — Dataset Generation](phase1_dataset_generation/README.md)** —
  version lock, access checks, EHR linkage, patient split, signal extraction,
  image rendering, QC, structured features, manifest, and audits.
- **[Phase 2 — Tasks, Benchmark & Paper](phase2_tasks_benchmark_and_paper/README.md)** —
  Tasks A / B / C and Plan-B B1 / B2 / B5 dataset builders, the audit suite,
  model training and per-task baselines, evaluation utilities, benchmark and
  paper figures, and the final DOCX benchmark report.

## How to run

Follow the command blocks in each phase README and source-of-truth document.
Current Phase 1 scripts derive the repository root from `__file__`, while some
stage-report command blocks still use `scripts/` as their working directory.
Use the exact command block printed by a stage script when validating that
stage.

```powershell
cd D:\Coding\MU\Tri-Modal_ECG\scripts
python phase1_dataset_generation/01_build_master_index.py
python phase2_tasks_benchmark_and_paper/02_task_B_temporal_grounding.py
```

A handful of paper-figure helpers (`70_paper_stream_taskB.py`,
`71_post_regen_taskB.py`, `72_print_taskB_paper_numbers.py`, the `viz_*`
scripts, and `60_find_examples.py`) hard-code the absolute path
`D:/Coding/MU/Tri-Modal_ECG` and are CWD-independent.

End-to-end reproduction order: **Phase 1 → Phase 2.1 (tasks) →
Phase 2.2 (audits) → Phase 2.3 (training) → Phase 2.4 (baselines) →
Phase 2.5 (evaluation) → Phase 2.6 (benchmark figures + report) →
Phase 2.7 (paper figures).** Each phase README has the exact per-script
table and run-order block.

## Loose items in this folder

- `logs/` — runtime, audit, and regeneration logs.
- `render_errors.log`, `scanlike_errors.log`, `task_B_regen.log` — historical
  one-off run logs left in place for provenance.
- `__pycache__/` — Python bytecode cache; safe to delete.
