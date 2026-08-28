# Phase 2 vs. the source plan — compliance audit

**Date:** 2026-08-28 · **Method:** cold read of the .docx, checked against the
spec, the configs, the task parquets and the campaign table.

**Source of authority:** `ECG_Benchmark_Neutral_Implementation_Plan_Plan_A_B.docx`
(repo root, 1,172 paragraphs). Every requirement below is quoted or paraphrased
from it and checked against what is actually on disk — not against what
`PHASE2_SOURCE_OF_TRUTH.md` claims about itself.

**Verdict: substantially compliant, with six gaps.** Three are cheap to close
today and expensive to close after Step 6's uploads and the first GPU campaigns.
None invalidate work already done.

---

## 1. What matches

| Plan requirement | Status |
| --- | --- |
| §1 patient-level split only, one subject in one split | PASS — `split_audit_phase2.md`, 75 checks, zero overlap |
| §1 version lock | PASS — `config/dataset_versions.yaml`, Phase 1 |
| §1 no label-to-input leakage + per-task modality allowlist | PASS — `task_input_policy.yaml` for all 12; `leakage_audit_phase2.md` proves it at the **dataloader**, not just the schema |
| §1 report missingness in every table | PASS — §1.1 statistical template, enforced in `cohort_audit.md` |
| §1 patient-level bootstrap CIs | PASS — `bootstrap.py`, BCa n=10,000, refuses a frame with no `subject_id` |
| §3 decision gate before modelling | PASS — `plan_a` frozen 2026-06-03; L3 = 468,176 / 800,035 = 58.5 %, over the 40 % Plan-A bar |
| §3.2 linkage tiers L3/L2/L1/L0 | PASS — all four present, L3 primary |
| §4.5 five modalities | PASS — raw, preprocessed, image, text, structured features all built |
| §4.7 70/10/20 subject split, subset never resplit | PASS — frozen, invariant 4.C |
| §5.2 six Plan A tasks A1–A6 | PASS — all built at full scale |
| §6.1 six Plan B tasks B1–B6 | PASS — all built at full scale |
| §5.5 / App. C lab protocol (locked itemids, ref-range → flag → threshold) | PASS — 7 labs (superset of the 4 required), 5 windows, `abnormal_method` per row |
| App. B ICD protocol (locked map, ICD-9/10 separate, narrow HF) | PASS — 5 groups, 175 codes validated against `d_icd_diagnoses` |
| §6.3 eight corruption families × {30,20,10,5,0} dB + clean | PASS — complete 8×5 grid, 900,005 rows |
| §6.3 three evaluation regimes kept separate | PASS — §7.3 regime_1/2/3, disjoint RNG streams |
| App. D deterministic corruption seeded by study_id | PASS — locked recipes, `regime2|` train prefix disjoint from the frozen test set |
| §7.2 ≥3 seeds | PASS — 42/123/456 |
| §7.2 thresholds selected on validation only | PASS — `threshold.py` refuses any other split |
| §7.1 calibration (reliability, ECE, Brier) for risk + labs | PASS — §6.8, `calibration.py`, val-fit only |
| §9.2 pre-modelling validation, all 8 items | PASS |
| §9.3 raw MIMIC never released | PASS — `.gitignore` excludes `data/`; release package is scripts + configs |
| App. F record-split leakage, lab-missing-as-normal, wrong itemids, timestamp overreach, non-reproducible noise, inconsistent cohorts | PASS — each has an explicit guard |

The three mandated pre-training audits are green: **347 checks, zero
violations** (leakage 88 / cohort 184 / split 75).

---

## 2. Gaps

Ordered by cost-of-delay, not by size.

### GAP 1 — A2/B1 have no regression head; the plan makes MAE/RMSE primary

**Plan says** (§5.4, §7.1): heart rate → "MAE, RMSE, Pearson/Spearman,
Bland-Altman"; QRS duration → "MAE/RMSE; percentage within 10 ms". §7.1 sets the
primary metric for the regression/measurement task type to "MAE and RMSE", with
"R², Spearman, Bland-Altman limits" secondary.

**We built**: three-way bins only. `A2_measurement_blind` emits `hr_label`,
`qrs_label`, `qtc_label`; §4.A.2.6 makes per-head macro-AUPRC primary. The
continuous ground truth (`hr_bpm`, `qrs_ms`, `qtc_ms`) is already in the parquet
as provenance, unused by any head.

**Why it matters.** Bland-Altman is the standard agreement plot in every ECG
measurement paper. A reviewer comparing us against the machine's own measurement
will ask for limits of agreement, and "we binned it" is not an answer. The plan
permits bins for *axis* ("Accuracy/F1 for bins; MAE if regression") but sets
MAE/RMSE as primary for HR and QRS.

**Cost to fix now: zero extra GPU runs.** Add a regression head alongside each
bin head in `task_spec.py` and the 8 A2/B1 configs. No A2 or B1 model has been
trained yet.

**Cost to fix after campaigns 4/5/9: 24 reruns** (8 configs × 3 seeds).

---

### GAP 2 — A6 has no nested clinical baselines, and the columns to build them are not in the parquet

**Plan says** (§5.8): A6 requires six baseline tiers — prevalence/intercept,
demographics-only, demographics + comorbidities (prior ICD *before* the ECG),
utilization (prior admissions, prior ECG count, admission type, ED disposition),
machine-measurement/report-only, and the ECG models. Figure 5 is the nested
curve: demographics → +comorbidities → ECG → combined, with calibration. §7 names
the failure condition outright: *"Only compared to random/prevalence baseline."*
§1.1 makes it the evidence bar for the claim **"ECG adds prognostic signal beyond
demographics."**

**We built**: one Cox model on `age + sex + machine HR/QRS/QTc` (spec §4.A.6.7),
then straight to the neural tiers. The intermediate rungs are absent.

**Worse: `A6_risk_stratification/test.parquet` has 22 columns and none of them
are age, sex, race, insurance, prior-admission count, prior-ECG count or
admission type.** The nested baselines cannot be built from the task table at
all. Everything needed sits in `patients`, `admissions` and `diagnoses_icd` on
the laptop, but recovering it means an A6 schema extension.

**Why it matters.** This is the headline Plan A claim. Without the
demographics-only and demographics+comorbidities rungs there is no way to show
the ECG adds anything, and the plan names that exact omission as a failure
condition.

**Cost to fix now: one A6 rebuild plus a re-run of the three audits. No GPU time
at all** — every added baseline is a logistic regression or a Cox fit on the
laptop.

**Cost to fix after Step 6:** the A6 parquet is part of what gets uploaded, so
the fix becomes rebuild + re-audit + re-upload.

---

### GAP 3 — "no-text multimodal" is specced as an eval-time drop, which is invalid for an end-to-end fine-tuned model

**Plan says** (§5.3 ablation 6, Figure 2, App. F): the no-text multimodal run is
the **primary leakage-controlled setting**. App. F, on report-text leakage:
*"Report text-only result honestly; include no-text multimodal as primary
leakage-controlled setting."*

**We built**: §7.2 lists "No-text ablation (drop text input)" for A1/A3/A5/A6/B4
— then says sweeps "do NOT retrain by default; [they] re-evaluate the same
trained model on the filtered cohort."

**That reasoning was written for frozen late fusion and no longer holds.**
Round 5 decision 1 made fusion **end-to-end fine-tuned** (`mode:
end_to_end_fine_tuned` in all 12 fusion configs). Feeding zeros to a jointly
trained text encoder does not produce "the same model without text" — it
produces a model outside its own training distribution. The resulting number is
not an ablation; it is a broken forward pass.

None of the 94 configs is a no-text variant, and `campaign_runs.py --table` maps
all 94 to campaigns with none left over — so nothing in the current campaign plan
trains one.

**Cost to fix: +10 configs (5 tasks × 2 lead sets) = +30 runs**, landing in
campaigns 7 and 8. Real GPU time, but it is the evidence behind the word
"leakage-audited" in the title.

Cheaper alternative if 30 runs is too many: train the fusion models with
text-branch dropout (p=0.5) so the no-text forward pass is in-distribution. That
changes the primary model, so it needs an explicit decision — it must not be
adopted silently.

---

### GAP 4 — B6's difficulty ladder has 2 rungs; the plan specifies 6

**Plan says** (§6.7): Levels 0–5 — random negative, HR-matched, HR+QRS-matched,
HR+QRS+axis+QTc-matched, same-patient-different-study, and near-duplicate with an
altered component. Figure 4 is the *curve* across those levels, and it is the
evidence for Plan B's core claim ("shortcut elimination reveals hidden
weaknesses… models plateau"). App. F names the failure mode: *"Hard negatives
accidentally easy → match more variables; same-patient negatives where
possible."*

**We built**: measured off `B6/eval_keys.parquet` —

| tier | neg_type | rows | plan level |
| --- | --- | ---: | --- |
| easy | IMAGE_SWAP / PARTIAL_MISMATCH / SIGNAL_SWAP / TEXT_SWAP | 749,112 each | Level 0 |
| medium | HARD_NEGATIVE_TEXT (same HR bucket) | 749,112 | Level 1 |
| hard | — | **0** | — |

Levels 2, 3, 4 and 5 do not exist. The "hard" tier was reserved in Round 3 and
shipped empty by the Round 7 default (open question 13). **A two-point curve is
not a difficulty curve**, and Level 4 (same patient, different study) is the rung
that tests the patient/demographic shortcut — the shortcut most likely to be real
in MIMIC, where patients carry many ECGs.

**Cost to fix.** B6 is an evaluation-time stratification of B4's rows, so the
lazy path is test-split-only: extend the B4 builder to emit levels 2–5 negatives
for the test split, regenerate the B6 pointer table, retrain nothing. If levels
2–5 are also wanted in training, that is a B4 rebuild plus retraining of
campaigns 7/8/11.

---

### GAP 5 — no structured-feature baseline for A3

**Plan says** (§5.9): the structured baseline (logistic regression / XGBoost on
machine measurements and/or NeuroKit features) is required for **A1, A3 and A6**.
Reference [R5] is CardioLab — ECG features to lab values — which makes this the
single most relevant prior-work comparison for A3.

**We built**: §4.A.3.7 says A3 is "same matrix as A1 minus the algorithmic (no
rule-based ECG → lab predictor exists)". True that no *rule* exists — but the
plan asks for a *fitted* feature model, not a rule, and that plainly does exist.

Consequence: A3 ships with no floor. A reviewer asks "does a logistic regression
on HR/QRS/QTc already predict hyperkalemia?" and we have no answer.

**Cost to fix: CPU only, hours.** One more baseline in
`50_run_baselines_algorithmic.py`.

---

### GAP 6 — the contrastive/CLIP-style family is absent and was never explicitly declined

**Plan says** (§5.9): "Contrastive multimodal — CLIP-style alignment among
signal, image, and text; then fine-tune on tasks. Tasks: A5 plus downstream
A1/A3/A6."

**We built**: Round 3 locked late-concat fusion. `A5/B4_embedding_cosine_*`
(4 configs, campaign 11) score retrieval by cosine over fusion embeddings — that
covers the §7.5 retrieval *evaluation*, not the contrastive *training* family.

The spec never mentions contrastive learning anywhere. Dropping it is defensible
— it is a whole pretraining regime, and the plan frames §5.9 as a menu of
families — but **dropping it silently is not**. It needs a recorded decision with
a reason, or a reviewer reads the omission as an oversight.

---

## 3. Deviations already taken, documented, and fine

These differ from the .docx but each was forced by the data, measured, and
recorded. No action needed beyond making sure each reaches the supplementary.

| # | Deviation | Why forced |
| --- | --- | --- |
| 6.8 / 7.14 | Measurements read the **machine** columns, not `structured_features` | `structured_features.qrs_ms` is byte-identical to the NeuroKit value; its `qtc_bazett_ms` correlates with machine QTc at r = 0.024 |
| 6.10 | A2 primary cohort is `sqi ∈ {high, medium}`, not `high` | Literal reading gives 3,110 ECGs, not the ~445 K the plan assumes |
| 6.11 | B5 emits one row per **eligible** study, p=0.5 corrupted | The only reading under which §4.B.5.3 and the plan's "50/50 by design" are both true |
| 7.16 | A5 masks **claims**, not numerals | The plan assumes reports carry numbers. Measured: 0.51 % do, all boilerplate. The literal rule masks nothing |
| 7.15 | A6 reports censoring rather than "correcting" it | MIMIC has no usable global cutoff; the obvious substitute conditions on the outcome (21.4 % → 27.5 %) |
| 8.18 | Image transform resizes, does not centre-crop | Renders are 4.8:1 and 2.02:1, not the assumed 3:1 and 1.33:1; the literal crop discards 37 % of every Lead-II strip |
| — | B2 anchors are SQI-representative, not high-SQI | Phase 1 froze the set without an SQI filter; measured 8 high / 1,119 medium / 744 low |
| — | B5 families are HR / QRS / **axis / PR**; the plan lists HR / QRS / **QTc** / axis | PR substituted for QTc. **Not yet recorded as a deviation — see action 7** |

Plus four disclosure items accepted at Step 12 sign-off: A3's structurally absent
rare classes, thin QTc-`short` in val, the ~0.7 % high-SQI tier, and A5/B4/B6
carrying no SQI/linkage columns for §7 subgrouping.

---

## 4. Progress against the plan

Phase 1 built everything §4 of the plan asks for. Phase 2 stands at:

| | |
| --- | --- |
| Tasks built at full scale | **12 / 12** |
| Mandated pre-training audits | **3 / 3 PASS** (347 checks, 0 violations) |
| Algorithmic baselines run | **8 / 8**, `missing_mandated = []`; §9.5 oracles exactly 1.000000 |
| Trained models | **0 / 282 runs** — no GPU work has started |
| Post-training audits | 0 / 4 (threshold / calibration / sensitivity / reproducibility) |
| Aggregation + paper tooling | not written — `40_aggregate_results.py`, `41_run_sensitivity.py`, `60_make_paper_tables.py`, `61_make_paper_figures.py`, `70_build_release_package.py` |

**Every gap in §2 is still free or nearly free**, because nothing has been
trained. That window closes at Step 6.

Housekeeping: `outputs/audit_reports/threshold_audit.md` is untracked and holds
**dev-sample** numbers (n_val = 2000). It occupies the path the real audit will
take. Move or delete it before it is mistaken for a result.

---

## 5. Recommended actions, in order

Actions 1, 2 and 5 should land **before Step 6's first upload**, because they
change task parquets the upload carries.

1. **Extend A6's schema** with age, sex, race/insurance, prior-admission count,
   prior-ECG count and admission type (all constrained to `charttime <=
   ecg_time`), then add the prevalence / demographics / demographics+comorbidities
   / utilization baselines. Re-run the three audits. Laptop, no GPU.
   — *closes GAP 2*
2. **Add regression heads to A2 and B1** for HR, QRS and QTc alongside the
   existing bins, with MAE / RMSE / Spearman / Bland-Altman limits in
   `metrics.py`. Free today; 24 reruns later. — *closes GAP 1*
3. **Add A3's structured-feature baseline** to
   `50_run_baselines_algorithmic.py`. Laptop, hours. — *closes GAP 5*
4. **Decide GAP 3 explicitly** — either add 10 no-text fusion configs (+30 runs
   in campaigns 7/8) or adopt text-branch dropout in the primary fusion model.
   Do not leave §7.2's eval-time drop in place; it is not a valid ablation for an
   end-to-end fine-tuned model.
5. **Decide GAP 4 explicitly** — at minimum add Levels 2–5 as test-split-only
   negatives so Figure 4 has six points and nothing needs retraining. Level 4
   (same patient, different study) matters most.
6. **Record a decision on contrastive pretraining** (GAP 6) — build it or decline
   it with a stated reason, in §12 of the spec.
7. **Record the B5 QTc → PR family substitution** as a numbered deviation. It is
   currently an undocumented divergence from plan §6.6.
8. Delete or relocate the dev-sample `threshold_audit.md`.

Actions 4 and 5 are scope decisions for the project owner. Actions 1, 2, 3, 6, 7
and 8 are unambiguous — the plan requires them and they cost no GPU time.
