# Phase 2 — Tasks, Benchmark Suite & Paper

This phase consumes the dataset built in
[Phase 1](../phase1_dataset_generation/README.md) and produces:

1. The **downstream task datasets** — the original Tasks A / B / C from the
   "TriModal ECG Truth" rule book, plus the spec-compliant B1 / B2 / B5
   variants for the Plan-B benchmark (`§6` of the
   `ECG_Benchmark_Neutral_Implementation_Plan_Plan_A_B.docx` spec).
2. The **audit suite** that verifies the dataset and the benchmark against
   the spec (split / duplicate / missingness / leakage + spec compliance).
3. **Model training** (1D ResNet baselines, signal-bank / RAM / fast variants;
   noise-augmented regime-2 model).
4. **Per-task baselines** (NeuroKit2 algorithmic B1, ResNet B3 temporal, B5
   contradiction, B4/B6 cross-modal verification).
5. **Evaluation utilities** (multi-seed aggregation, B2 corruption curves,
   derived AUC-CC / collapse metrics, SQI-stratified evaluation).
6. **Figures** for the benchmark and the paper, and the final **DOCX
   benchmark report** plus the markdown/HTML technical report.

> **Where to run from:** like Phase 1, every script uses repo-relative
> paths (`../processed/...`, `../outputs/...`, `../data/...`,
> `../report_assets/...`, `../paper/...`). Run them with your working
> directory set to `scripts/`:
>
> ```powershell
> cd D:\Coding\MU\Tri-Modal_ECG\scripts
> python phase2_tasks_benchmark_and_paper/01_task_A_verification.py
> ```
>
> A handful of scripts (`70_paper_stream_taskB.py`, `71_post_regen_taskB.py`,
> `72_print_taskB_paper_numbers.py`, the `viz_*` figure scripts, and
> `60_find_examples.py`) hard-code the absolute repo path
> `D:/Coding/MU/Tri-Modal_ECG` and so are CWD-independent.

## Output layout

| Directory | What lands here |
|---|---|
| `processed/taskA_verification.jsonl` | Task A dataset (rule-book version). |
| `processed/taskB_temporal_grounding.jsonl` | Task B dataset (per-second labels). |
| `processed/taskC_plausibility.jsonl` | Task C dataset (claim ↔ measurement labels). |
| `processed/taskB1_measurement_blind.jsonl` | Plan-B Task B1 (measurement-blind targets). |
| `processed/taskB2_noise_robustness.jsonl` + `signals_corrupted/` | Plan-B Task B2 (corruption curriculum). |
| `processed/taskB5_contradiction_detection.jsonl` | Plan-B Task B5 (text contradiction). |
| `outputs/audit_reports/` | Audit JSONs and the spec-compliance markdown report. |
| `outputs/model_runs/B1/`, `B2_regime2/`, `B3/` | Trained model weights + per-seed metrics. |
| `outputs/tables/` | Aggregated metric JSONs / CSVs for every benchmark. |
| `outputs/figures/` | Benchmark figures (corruption curves, training curves, etc.). |
| `outputs/ECG_Benchmark_Plan_B_Report.docx` | Final human-voice benchmark report. |
| `report_assets/` | Figures + intermediate stats for the markdown/HTML technical report. |
| `paper/figures/` | Polished figures for the LaTeX paper. |

## Script groups

Scripts are prefixed by stage; within a stage they run in numeric order.

### 01–06 · Task datasets

| # | Script | Purpose |
|---|---|---|
| 01 | `01_task_A_verification.py` | (Was `task_A.py`.) Generates the cross-modal verification dataset: 2 positives (clean + scan-like) and 4–5 negatives per study (`TEXT_SWAP`, `IMAGE_SWAP`, `SIGNAL_SWAP`, `PARTIAL_MISMATCH`, `HARD_NEGATIVE_TEXT` within same HR bucket). Writes `processed/taskA_verification.jsonl` + `taskA_stats.json`. Expected ≈ 5.6 M rows. |
| 02 | `02_task_B_temporal_grounding.py` | (Was `task_B.py`.) Per-second temporal grounding labels for three queries (`HIGH_HEART_RATE`, `LOW_HEART_RATE`, `WIDE_QRS`). Uses NeuroKit2 R-peak detection + wavelet QRS delineation; falls back to global rules only if peak detection fails. 10 bins / study, 3 queries → ≈ 2.4 M rows. Replaced the earlier buggy global-stamp version (see `taskb.md`). |
| 03 | `03_task_C_plausibility.py` | (Was `task_C.py`.) Physiological-plausibility claims (tachycardia, bradycardia, normal HR, wide QRS, normal QRS, left/right/normal axis) labelled `SUPPORTED` / `CONTRADICTED` / `UNCERTAIN` from structured measurements. ≈ 4.7 M rows. |
| 04 | `04_task_B1_measurement_blind.py` | (Was `task_B1.py`.) Plan-B B1 dataset: pairs Lead-II waveform with three binned targets (`hr_label`, `qrs_label`, `qtc_label` — Bazett). Sentinel-filters MIMIC null markers (`rr_interval=65535`, fiducial `29999`). Models must predict from signal only — text and structured features are forbidden inputs. |
| 05 | `05_task_B2_noise_robustness.py` | (Was `task_B2.py`.) Picks a clean anchor subset (test split, `waveform_ok=True`) and writes corrupted signals (8 corruption families × 5 SNR levels) to `processed/signals_corrupted/` and the matching JSONL. |
| 06 | `06_task_B5_contradiction_detection.py` | (Was `task_B5_rebuild.py`.) Spec-compliant Plan-B B5: 50 % clean / 50 % corrupted report-text pairs with safe injection rules (`HR≤50 ⇢ tachy flip`, `HR≥120 ⇢ brady flip`, no injection when `58<HR<105`). Emits all keys required by spec §6.6. |

### 10–12 · Audits

| # | Script | Purpose |
|---|---|---|
| 10 | `10_run_audits.py` | (Was `00_run_audits.py`.) Pre-modeling audit suite required by spec §1.2 / §9.2: split audit (no subject crosses), duplicate audit, missingness audit, leakage audit (forbidden fields absent from each task JSONL). |
| 11 | `11_audit_against_spec.py` | (Was `20_audit_against_spec.py`.) Machine-readable spec compliance check against `ECG_Benchmark_Neutral_Implementation_Plan_Plan_A_B.docx` (§6–§9). Walks every requirement and reports `PASS / PARTIAL / MISSING` to `outputs/audit_reports/spec_compliance_audit.md`. |
| 12 | `12_fill_audit_gaps.py` | (Was `21_fill_audit_gaps.py`.) Fills the 5 `MISSING` items uncovered by 11: cart-ID stratification, B3 event-count distribution, B3 success/failure examples, B1 failure cases figure, and visual QC sample. |

### 20–24 · Training

| # | Script | Purpose |
|---|---|---|
| 20 | `20_train_B1_bank.py` | (Was `08_train_bank.py`.) **Canonical** B1 trainer. Loads signals from a pre-built signal bank (`processed/signal_bank/`) so epochs run pure-GPU. ResNet-1D, 25 epochs, AdamW. Three seeds → bootstrap CIs. |
| 21 | `21_train_B1_baselines.py` | (Was `08_train_baselines.py`.) Original streaming variant of the B1 ResNet trainer (`argparse --task --seed`). Useful as a sanity check or when `signal_bank/` is not available. |
| 22 | `22_train_B1_baselines_fast.py` | (Was `08_train_baselines_fast.py`.) Windows-friendly fast variant (`num_workers=0`, 80 K samples / epoch) for fast iteration. |
| 23 | `23_train_B1_ram.py` | (Was `08_train_ram.py`.) RAM-preloaded variant (10 K / 2 K / 2 K subset by default; flip `FULL_DATASET=True` to use all signals in RAM, ~4.8 GB). Bypasses Windows small-file I/O bottleneck. |
| 24 | `24_train_B2_regime2.py` | (Was `12_train_regime2.py`.) Regime-2 ResNet — same architecture as B1 but trained with noise augmentation that matches the B2 corruption families. Saves to `outputs/model_runs/B2_regime2/` so `42_eval_B2_regime2.py` can replay the corruption curve. |

### 30–34 · Per-task baselines

| # | Script | Purpose |
|---|---|---|
| 30 | `30_neurokit2_baseline_B1.py` | (Was `08_neurokit2_baseline_B1.py`.) Pure-algorithmic B1 baseline — NeuroKit2 R-peak detection on the raw signal, no training. Reports accuracy / F1 / AUPRC per class against the measurement-blind labels. |
| 31 | `31_baseline_B3_temporal.py` | (Was `13_baseline_B3.py`.) B3 temporal event-localization baseline: ResNet-1D encoder with a 10-way sigmoid head, trained separately per query type (`HIGH_HEART_RATE`, `LOW_HEART_RATE`, `WIDE_QRS`). |
| 32 | `32_baseline_B5_contradiction.py` | (Was `14_baseline_B5.py`.) B5 contradiction-detection baselines: text-only (TF-IDF + Logistic Regression) and signal+text multimodal (frozen B1 ResNet embedding + TF-IDF → MLP). |
| 33 | `33_baseline_B4_cross_modal.py` | (Was `15_baseline_B4.py`.) B4 / B6 cross-modal verification baseline: frozen ResNet signal embedding (512-d) + TF-IDF text embedding → cosine similarity + LR. Sampled to 4 K records / split for the demo. |
| 34 | `34_baseline_B6_difficulty.py` | (Was `17_baseline_B6.py`.) Difficulty-stratified verification across 6 negative-mining levels (random → same patient → nearest signal-embedding neighbor). Emits the verification difficulty curve. |

### 40–44 · Evaluation utilities

| # | Script | Purpose |
|---|---|---|
| 40 | `40_aggregate_seeds.py` | (Was `09_evaluate.py`.) Aggregates per-seed result JSONs into mean ± std and combined bootstrap CIs → `outputs/tables/{task}_final_results.{json,csv}`. |
| 41 | `41_eval_B2_regime1.py` | (Was `11_eval_B2_regime1.py`.) Runs the B2 corruption curve for **Regime 1** (clean-trained B1 model). 8 corruption types × 5 SNR levels, computed in-memory on 2 K anchor signals to avoid 80 K small-file reads. |
| 42 | `42_eval_B2_regime2.py` | (Was `11b_eval_B2_regime2.py`.) Re-runs the same curve for the **Regime 2** (noise-augmented) model — thin wrapper that imports `41_eval_B2_regime1.py` and points it at the regime-2 weights. |
| 43 | `43_b2_auc_metrics.py` | (Was `18_b2_auc_metrics.py`.) Derives the headline robustness scalars from the regime-1/2 curves: AUC-CC (trapezoidal area under accuracy vs SNR), relative drop at 0 dB, and the collapse threshold (first SNR where accuracy < 0.80). |
| 44 | `44_b1_sqi_stratified.py` | (Was `19_b1_sqi_stratified.py`.) Stratified B1 evaluation by signal-quality tier (kurtosis-based SQI, `high≥0.8 / medium 0.6–0.8 / low<0.6`). |

### 50–51 · Benchmark figures & report

| # | Script | Purpose |
|---|---|---|
| 50 | `50_benchmark_figures.py` | (Was `16_figures.py`.) Generates the supplementary figures for the benchmark report: B2 corruption curves (regime 1 vs 2), B1 training curves (3 seeds), per-class AUPRC bar chart, B6 verification difficulty curve, B1 SQI-stratified bar chart, B2 AUC-CC summary. |
| 51 | `51_write_benchmark_report.py` | (Was `10_write_report.py`.) Builds the final `outputs/ECG_Benchmark_Plan_B_Report.docx` from every result JSON and figure produced above. |

### 60–66 · Technical-report figures (`report_assets/` & `paper/figures/`)

These produce the figures used by `TRI_MODAL_ECG_UNDERSTANDING_SYSTEM_REPORT.md`
and by the LaTeX paper. They expect the example study list at
`report_assets/examples.json` — produced by `60_find_examples.py`.

| # | Script | Purpose |
|---|---|---|
| 60 | `60_find_examples.py` | Picks a small representative study per clinical bucket (brady, normal_low / normal_high, tachy, wide QRS, left / right / normal axis) and writes `report_assets/examples.json`. Run this first. |
| 61 | `61_viz_overview.py` | Dataset-level overview figures (HR distribution, QRS / axis histograms, split distribution, ECGs-per-patient, modality coverage). |
| 62 | `62_viz_12lead_only.py` | Standalone 12-lead montage figure for the raw-data section. |
| 63 | `63_viz_examples.py` | Per-condition multimodal evidence figures (Lead II + 12-lead + clean PNG + scan-like JPG + `T_machine` snippet) and clean-vs-scan before/after. |
| 64 | `64_viz_extras.py` | Supporting figures: amplitude normalization, scan-like augmentation pipeline, storage comparison, pipeline runtime, hard-negative HR-bucket diagram. |
| 65 | `65_viz_tasks_bc.py` | Task B and Task C visualizations (label distributions, claim × label heatmap, per-condition Task C examples). |
| 66 | `66_viz_paper.py` | Paper-only figures into `paper/figures/`: feature matrix (MEETI vs Tri-Modal), Task B before/after, Task B examples grid, two-row pipeline diagram, four-modality data card. |

### 70–72 · Task B paper-stats helpers

| # | Script | Purpose |
|---|---|---|
| 70 | `70_paper_stream_taskB.py` | Streams `processed/taskB_temporal_grounding.jsonl` once and writes `report_assets/taskB_stats.json` (per-query positive rates, mixed-label counts, per-bin distributions) — single source of truth for figure scripts and paper text. |
| 71 | `71_post_regen_taskB.py` | Post-regeneration driver. After `02_task_B_temporal_grounding.py` finishes: sanity-checks the row count (= 2,399,118), re-runs `70`, then re-runs `65` and `66`. |
| 72 | `72_print_taskB_paper_numbers.py` | Prints the exact numbers (per query: any_pos count + %, mixed/any_pos %) that need to land in the Technical Validation section of `paper/main.tex`. |

### Dev helper

| Script | Purpose |
|---|---|
| `_dev_check_linkage_feasibility.py` | (Was `check_linkage_feasibility.py`.) Quick feasibility probe of how many ECG records have `ecg_time` and could be linked to ED/hospital encounters in the future. Not part of any pipeline. |

## End-to-end run order (clean reproduction)

```powershell
cd D:\Coding\MU\Tri-Modal_ECG\scripts

# Phase 2.1 — task datasets (depends on Phase 1 outputs)
python phase2_tasks_benchmark_and_paper/01_task_A_verification.py
python phase2_tasks_benchmark_and_paper/02_task_B_temporal_grounding.py
python phase2_tasks_benchmark_and_paper/03_task_C_plausibility.py
python phase2_tasks_benchmark_and_paper/04_task_B1_measurement_blind.py
python phase2_tasks_benchmark_and_paper/05_task_B2_noise_robustness.py
python phase2_tasks_benchmark_and_paper/06_task_B5_contradiction_detection.py

# Phase 2.2 — audits
python phase2_tasks_benchmark_and_paper/10_run_audits.py
python phase2_tasks_benchmark_and_paper/11_audit_against_spec.py
python phase2_tasks_benchmark_and_paper/12_fill_audit_gaps.py

# Phase 2.3 — training (pick one B1 trainer; multi-seed for variance)
python phase2_tasks_benchmark_and_paper/20_train_B1_bank.py --seed 42
python phase2_tasks_benchmark_and_paper/20_train_B1_bank.py --seed 123
python phase2_tasks_benchmark_and_paper/20_train_B1_bank.py --seed 456
python phase2_tasks_benchmark_and_paper/24_train_B2_regime2.py --seed 42

# Phase 2.4 — per-task baselines
python phase2_tasks_benchmark_and_paper/30_neurokit2_baseline_B1.py
python phase2_tasks_benchmark_and_paper/31_baseline_B3_temporal.py
python phase2_tasks_benchmark_and_paper/32_baseline_B5_contradiction.py
python phase2_tasks_benchmark_and_paper/33_baseline_B4_cross_modal.py
python phase2_tasks_benchmark_and_paper/34_baseline_B6_difficulty.py

# Phase 2.5 — evaluation
python phase2_tasks_benchmark_and_paper/40_aggregate_seeds.py
python phase2_tasks_benchmark_and_paper/41_eval_B2_regime1.py
python phase2_tasks_benchmark_and_paper/42_eval_B2_regime2.py
python phase2_tasks_benchmark_and_paper/43_b2_auc_metrics.py
python phase2_tasks_benchmark_and_paper/44_b1_sqi_stratified.py

# Phase 2.6 — benchmark figures + DOCX report
python phase2_tasks_benchmark_and_paper/50_benchmark_figures.py
python phase2_tasks_benchmark_and_paper/51_write_benchmark_report.py

# Phase 2.7 — technical-report / paper figures
python phase2_tasks_benchmark_and_paper/60_find_examples.py
python phase2_tasks_benchmark_and_paper/61_viz_overview.py
python phase2_tasks_benchmark_and_paper/62_viz_12lead_only.py
python phase2_tasks_benchmark_and_paper/63_viz_examples.py
python phase2_tasks_benchmark_and_paper/64_viz_extras.py
python phase2_tasks_benchmark_and_paper/65_viz_tasks_bc.py
python phase2_tasks_benchmark_and_paper/66_viz_paper.py
python phase2_tasks_benchmark_and_paper/70_paper_stream_taskB.py
python phase2_tasks_benchmark_and_paper/72_print_taskB_paper_numbers.py
```

## Expected counts & key metrics (sanity check)

| Artifact | Expected |
|---|---:|
| `processed/taskA_verification.jsonl` | 5,597,755 rows / 799,706 studies |
| `processed/taskB_temporal_grounding.jsonl` | 2,399,118 rows (3 queries × 799,706 studies) |
| `processed/taskC_plausibility.jsonl` | 4,726,480 rows |
| `processed/taskB1_measurement_blind.jsonl` | ≈ 190 MB |
| `processed/taskB2_noise_robustness.jsonl` | ≈ 21 MB |
| `processed/taskB5_contradiction_detection.jsonl` | ≈ 38 MB |
| Task B `LOW_HEART_RATE` global positive rate | ≈ 33 % (matches dataset bradycardia fraction) |
| Task C `UNCERTAIN` rows | 374 (= 2 × 187 invalid-RR studies) |
| Patient-level split | 80/10/10 — every audit must report **zero** subject overlap |

If the row counts above match, the cleaned dataset and downstream tasks are
internally consistent with the report.
