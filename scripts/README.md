# `scripts/` — Tri-Modal ECG Pipeline

All pipeline code lives here, split into two phases.

```
scripts/
├── phase1_dataset_generation/        # raw MIMIC-IV ECG  ->  on-disk tri-modal dataset
└── phase2_tasks_benchmark_and_paper/ # tri-modal dataset ->  task JSONLs, audits, models,
                                      #                       benchmark figures, paper figures
```

- **[Phase 1 — Dataset Generation](phase1_dataset_generation/README.md)** —
  master index, patient split, signal extraction, image rendering, QC and
  integrity, dataset cleanup.
- **[Phase 2 — Tasks, Benchmark & Paper](phase2_tasks_benchmark_and_paper/README.md)** —
  Tasks A / B / C and Plan-B B1 / B2 / B5 dataset builders, the audit suite,
  model training and per-task baselines, evaluation utilities, benchmark and
  paper figures, and the final DOCX benchmark report.

## How to run

**Always run scripts with your working directory set to `scripts/`** — every
script uses repo-relative paths (`../processed/...`, `../data/...`,
`../outputs/...`). The reorganization did not modify any code, so paths
continue to resolve correctly only when CWD is `scripts/`.

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
table (purpose, inputs, outputs) and the run-order block to copy-paste.

## Loose items in this folder

- `logs/` — runtime / audit / regen logs (read by Phase 1 integrity scripts).
- `render_errors.log`, `scanlike_errors.log`, `task_B_regen.log` — historical
  one-off run logs left in place for provenance.
- `__pycache__/` — Python bytecode cache; safe to delete.
