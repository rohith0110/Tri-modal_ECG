# TriECG-Truth — progress review deck: outline

Draft for the B.Tech 4-1 progress review (Dr. Neeraj Choudhary, 15 min).
Guide asked for: problem statement, work completed, results, next steps.
Numbers come from R2 `trimodal-results` pulled 2026-11-06 (root, `acct2/`,
`acct3b/`); test-set numbers are from `results/<task>.csv`, `group_key = overall`,
mean of 3 seeds. No timelines or ETAs anywhere in the deck (user's call).

Deck: `TriECG_Progress_Review.pptx` (built by `build_deck.js`).

| # | Slide | One message | Content |
|---|-------|-------------|---------|
| 1 | Title | — | TriECG-Truth, tri-modal ECG benchmark; team; guide; Mahindra University |
| 2 | Problem statement | One ECG has three views, but models use one | Signal / image / report cards; gap: no benchmark tests all three on the same patients or checks they agree; our goal |
| 3 | Dataset (Phase 1, done) | We built and audited the dataset | 800,035 ECGs · 161,352 patients · 749,112 pass QC (93.6 %) · 3 views each; patient-level 70/10/20 split, no overlap; all audits pass |
| 4 | 12 tasks | Two tracks of six tasks | Track A uses hospital records (A1–A6), Track B uses the ECG alone (B1–B6), one plain line each |
| 5 | Method | Every model is tested the same, fair way | Model families (signal ResNet-18, image ResNet-50, text TF-IDF + BioClinicalBERT, fusion); 3 seeds; unseen test patients; 95 % CIs; 104 setups × 3 seeds = 312 runs; DGX A100s, 3 accounts |
| 6 | Progress | 159 of 312 runs done | Stacked bar by model group (done / to do); ~1,300 GPU-hours; test scores in for 6 of 12 tasks |
| 7 | Engineering | Problems we hit and solved | Storage limit (data split into pieces), half-size signals proven safe, 7-day job limit (auto-resume chains), bugs caught before results |
| 8 | Result: A1 diagnosis | ECG models beat the written report on all 5 conditions | AUROC per condition: signal (Lead II), image (12-lead), report (BioClinicalBERT) |
| 9 | Result: A6 risk | ECG predicts death risk, not readmission | AUROC for 30/90-day mortality and readmission, image vs report |
| 10 | More results | Three other test-set findings | B5 altered reports AUROC 0.98; A3 labs hard (macro AUPRC ~0.32); A5/B4 report alone = 0.50, the floor fusion must beat |
| 11 | Early signs (validation) | Signal models learn measurements and hold up under noise | A2 0.87, B1 0.91, B2 under noise 0.91, A4 F1 0.83, B3 mIoU 0.82 — validation, not final |
| 12 | Next steps | What is left | Finish remaining runs (mostly fusion), test-set eval for all 12, classical baselines + statistical tests, final audits, paper — no dates |
| 13 | Thank you | — | Questions; GitHub repo link |

## Things to check before presenting

1. **A5/B4 image score (AUROC ~0.75) is probably a shortcut, not real skill.**
   In the test set every scan-like image row is a match (`n_positive == n_rows`
   for `image_type = scanlike`), so an image model can score by spotting
   "scan-like" alone. Kept off the slides; mentioned in slide 10 notes.
2. **B5 fusion validation AUPRC = 1.000** (3 seeds). Too perfect; not shown.
   Worth a look before it reaches the paper.
3. Team list taken from the meeting email (Anshika Mishra, Banoth Rohith Rathod,
   Aditya Goyal). Subrahmanyam B H not listed — confirm.
4. Slide 11 numbers are **validation**, best epoch, mean of 3 seeds. Test-set
   numbers for those tasks are not computed yet.
