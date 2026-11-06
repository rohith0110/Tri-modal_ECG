# Phase 2 Pilot Results — 2026-11-06

A small test run before trusting the full DGX campaigns. **Do the models
actually learn?** Mostly yes. **Is anything broken?** Yes, one data problem:
A5/B4 had a shortcut. It is now fixed (see the end).

## How the pilot was run

| Setting | Value |
|---|---|
| Machine | `data-laptop`, RTX 3060 Laptop GPU (6 GB) |
| Data | The real task files, capped at **17,500 rows per split** (~5 % of A1's training set) |
| Image run | 20,000 rows, 3 epochs (slower model) |
| Epochs | 5 |
| Seed | 42 |
| Scored on | Validation split only (no test numbers) |
| Model | Signal ResNet-18 on Lead II, one per task; plus TF-IDF text on A1 and ResNet-50 image on A5 |
| Time | ~3.5 h, 13 runs, all finished without errors |

**These are not paper numbers.** 5 % of the data and 5 epochs only show whether
learning happens, not how good the final models are.

## How to read the scores

- **AUROC**: 0.5 = coin flip, 1.0 = perfect.
- **AUPRC**: compare with the **prevalence** (share of positives). A score
  equal to the prevalence means the model learned nothing.
- **"Epoch 1 → 5"**: if the number climbs, the model is learning.

## Results at a glance

| Task | What it predicts | Score, epoch 1 → 5 | Learns? |
|---|---|---|---|
| A1 | Diagnosis from ECG (5 conditions) | macro AUPRC 0.298 → **0.381** | ✅ Yes |
| A1 (text) | Same, from report text | 0.376 → **0.382** | ✅ Yes |
| A2 | HR / QRS / QTc from signal | 0.763 → **0.813** | ✅ Yes |
| B1 | Same as A2 (Plan B version) | 0.750 → **0.817** | ✅ Yes |
| B2 | Same, robustness setup | 0.771 → **0.817** | ✅ Yes |
| A4 | Find R-peaks in time | F1 0.573 → **0.721** | ✅ Yes |
| B3 | Find where evidence is (1-second bins) | mIoU 0.565 → **0.670** | ✅ Yes |
| A6 | 30/90-day death and readmission | 0.224 → **0.247** | ⚠️ Death yes, readmission barely |
| A3 | Abnormal lab values | 0.297 → **0.321** | ⚠️ Barely (only troponin) |
| A5 / B4 / B5 | Does the text match the ECG? | flat ~0.50 AUROC | ➖ Expected — the signal model cannot see the text |
| A5 (image) | Same, from the image | AUROC **0.751** | ❌ Shortcut, not learning |

## Details per task

### A1 — Diagnosis (signal model)

| Condition | AUROC | AUPRC | Prevalence |
|---|---|---|---|
| Atrial fibrillation / flutter | 0.83 | 0.72 | 0.29 |
| Heart failure | 0.77 | 0.58 | 0.30 |
| Acute MI | 0.72 | 0.25 | 0.11 |
| Conduction disorder | 0.78 | 0.23 | 0.07 |
| Ventricular arrhythmia / arrest | 0.73 | 0.14 | 0.05 |

Every condition is well above chance. The text model (TF-IDF) lands at almost
the same place (macro AUPRC 0.382), but stops improving after epoch 3.

### A2 / B1 — Measurements (signal model)

| Measurement | Average error | Correlation | Within tolerance |
|---|---|---|---|
| Heart rate | 1.6–1.8 bpm | 0.99 | ~95 % within 5 bpm |
| QRS duration | 7.0–7.1 ms | 0.89–0.90 | ~78 % within 10 ms |
| QTc | 11.5–13.0 ms | 0.79–0.85 | 81–84 % within 20 ms |

Heart rate is nearly perfect, QRS is good, QTc is the hardest.

### A4 — Event localization (signal model)

| Event | F1 | Avg timing error |
|---|---|---|
| R-peak | **0.72** | 4.0 ms |
| QRS onset | 0.11 | 5.5 ms |
| QRS offset | 0.11 | 5.4 ms |

R-peaks are found well. QRS start/end are weak this early — watch them in the
full runs.

### B3 — Temporal grounding (signal model)

mIoU **0.67**, 74 % of queries found at IoU ≥ 0.3, "no evidence" answered
correctly 98 % of the time.

### A6 — Risk (signal model)

| Outcome | AUROC | AUPRC | Prevalence |
|---|---|---|---|
| Death within 30 days | **0.72** | 0.17 | 0.08 |
| Death within 90 days | **0.70** | 0.24 | 0.12 |
| Readmission within 30 days | 0.54 | 0.23 | 0.21 |
| Readmission within 90 days | 0.54 | 0.35 | 0.33 |

Mortality is predictable from the ECG; **readmission is close to a coin flip**.
That may simply be true (readmission depends on much more than one ECG), but
expect weak readmission numbers in the paper.

### A3 — Lab abnormality (signal model)

Each lab is a 3-way choice (low / normal / high), so ~0.33 macro AUPRC is
roughly chance.

| Lab | Macro AUPRC (best window) |
|---|---|
| Troponin | **0.40** |
| Calcium | 0.34 |
| Creatinine | 0.33 |
| Magnesium | 0.33 |
| Lactate | 0.31 |
| Sodium | 0.30 |
| Potassium | 0.30 |

Only troponin is clearly above chance. Lab values may be hard to read from Lead
II alone — the 12-lead and fusion runs are where this should improve.

### A5 / B4 / B5 — Text vs ECG tasks (signal model)

All flat at chance (AUROC 0.50). **This is expected**: these tasks ask whether
the report text matches the ECG, and a signal-only model never sees the text.
They are control runs, not failures.

## ❌ The problem found: A5/B4 image shortcut

Each ECG in A5/B4 gets **two positive rows** (clean image + scan-like image)
and **five negative rows**. The original build drew **every negative with a
clean image**. So:

| Image style | Share that are positives (train) |
|---|---|
| Clean | 16.7 % |
| Scan-like | **100 %** |

A model that only checks "does this look scanned?" gets it right without
reading anything.

| Check | AUROC |
|---|---|
| Rule: "scan-like ⇒ match", no model at all | **0.750** |
| Pilot image model, all rows | **0.751** |
| Pilot image model, clean rows only | **0.502** (coin flip) |
| DGX image models (A5/B4, full runs) | ~0.75 |

The image model learned nothing except the shortcut — it scored 0.999 on every
scan-like image. The DGX A5/B4 image and fusion scores are therefore not real.

### The fix

Negatives are now drawn clean or scan-like **50/50** (deterministic, per row),
so a scan-like image says nothing about the answer. Positives are unchanged.
Recorded as spec §12.12 and open question 18 in `PHASE2_PROGRESS.md`.

### Proof the fix works

Same A5 image model, same 20,000 validation rows, rebuilt data (1 epoch — the
laptop GPU ran out of memory in epoch 2, so the epoch-1 weights were scored):

| Check | Old data | Fixed data |
|---|---|---|
| Rule "scan-like ⇒ match" | 0.750 | **0.500** |
| Image model, all rows (AUROC) | 0.751 | **0.498** |
| Image model, clean rows | 0.502 | **0.497** |
| Image model, scan-like rows | (all positive) | **0.499** |
| Image model, AUPRC vs prevalence 0.286 | 0.714 | **0.285** |

The image model is now at chance everywhere, which is correct: an image alone
cannot tell whether the text belongs to it. Any skill a fusion model shows on
A5/B4 now has to come from actually comparing the modalities.

## What to do next

1. Upload the rebuilt A5/B4/B6 task files to R2 (waiting on approval) and
   retrain the A5/B4 image, fusion and embedding-cosine runs on the DGX.
2. Watch A3 and A6-readmission in the full runs — likely weak results, not bugs.
3. Check B5 fusion's validation AUPRC of 1.000 on all 3 seeds (still unexplained).
