# Stage 1 — EHR Linkage + Decision Gate — Independent Reviewer Report (Re-Review)

**Reviewer role:** Independent specification-compliance reviewer
**Spec authority:** `docs/PIPELINE_SOURCE_OF_TRUTH.md` (§3.7.1, §3.7.2, §3.7.3, §5.1–5.3, §6, §7.5, §8.13, §9.3 Stage 1, §10, §11)
**Inputs reviewed (this re-review):**
- `outputs/stage_reports/stage_1_report.md` (corrected rerun)
- `outputs/audit_reports/linkage_feasibility_report.md`
- `config/decision.yaml`, `config/key_labs.yaml`, `config/dataset_versions.yaml` (ehr_cache section)
- Stage 1 scripts on disk (`_stage1_common.py`, `40_..py` – `45_..py`)
- `data/processed/linkage/*.parquet`, `data/raw/ehr_cache/*.parquet`
- per-script `logs/<script>/main.log`
**Date:** 2026-05-31 (re-review after fixes)

This supersedes the prior HALT review. All four findings from that review were addressed in the corrected rerun. Findings below were re-verified against the on-disk script source and on-disk artifacts, not just the pasted logs.

---

## Disposition of prior findings

| #          | Prior severity | Finding                                                                                                | Status                                                                                                                                                  |
|------------|----------------|--------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| E-MAJOR-1  | **MAJOR**      | Tie-break sort applied hosp-over-ED unconditionally and ahead of midpoint distance / exact>tolerance.   | ✅ **RESOLVED** — sort key is now `(study_id, abs_tie_minutes, link_type_priority, id_priority, conditional_hosp_priority, source_stable_priority)`; the hosp-over-ED preference is conditional on both `hadm_id` and `stay_id` being populated and is only a *later* tiebreaker. |
| D-MINOR-1  | MINOR          | Tolerance scan considered only the two nearest neighbors per source.                                    | ✅ **RESOLVED** — `42_link_tolerance.tolerance_candidates` now finds every interval whose nearest edge is within ±7 days via `np.flatnonzero` over the per-subject interval array. Candidate rows grew from 597,753 → 602,314. |
| G-MINOR-1  | MINOR          | Key-lab itemid set hard-coded in Python.                                                                | ✅ **RESOLVED** — `config/key_labs.yaml` is the new authoritative source; loaded at runtime by `44_label_availability.py` (`load_key_labs`); also mirrored into `config/decision.yaml.key_labs`.                          |
| I-MINOR-1  | MINOR          | `setup_main_logger` attached both `main.log` and `all.log` RotatingFileHandlers (§8.13 says one).      | ✅ **RESOLVED** — `_stage1_common.setup_main_logger` now attaches only `main.log` plus stderr; `all.log` is no longer produced.                          |

---

## Independent verification performed (this re-review)

**Source-level checks against the on-disk scripts:**
- `43_tie_break_link.add_candidate_tiers` and `select_final`: sort key is exactly `["study_id", "abs_tie_minutes", "link_type_priority", "id_priority", "conditional_hosp_priority", "source_stable_priority"]` with all `ascending=True`. `conditional_hosp_priority` is derived as `(source == "hosp") & hadm_id.notna() & stay_id.notna()` → 0 else 1, which is the spec-defined "hospital wins over ED **if both `hadm_id` and `stay_id` exist**" applied only after the primary spec keys. `source_stable_priority` is purely a final deterministic tiebreaker after the spec keys are exhausted. ✅
- `42_link_tolerance.tolerance_candidates`: `MAX_TOLERANCE_MINUTES = 10_080`; per-ECG candidate scan is `np.flatnonzero((data["ends"] >= t - 7d) & (data["starts"] <= t + 7d))`, so every overlap-eligible interval is emitted (not just two neighbors). ✅
- `44_label_availability.load_key_labs` reads `config/key_labs.yaml` via `yaml.safe_load` and returns the same five-lab set used in the first run; `45_decision_gate` re-reads the same file and copies it into `decision.yaml.key_labs`. ✅
- `_stage1_common.setup_main_logger`: only `RotatingFileHandler(main.log)` + `StreamHandler(sys.stderr)` are attached. The function still unlinks an old `all.log` if present (defensive cleanup) but no longer creates one. ✅

**On-disk artifact checks:**
- `config/decision.yaml.frozen_at = 2026-05-31T17:54:40Z`, `chosen_path = plan_a`, all four `threshold_pass` flags true, `key_labs` block present and matches `key_labs.yaml`. ✅
- `linkage_final.parquet` rows == 785,761; `label_availability.parquet` rows == 800,035; 800,035 − 785,761 = 14,274 = L0. ✅
- New tier distribution: L3 468,176 / L2 79,651 / L1 237,934 / L0 14,274. The L3 count is unchanged (exact matches are unaffected by the tie-break ordering or tolerance breadth fixes); L2 increased by 259 (+0.03 pp) and L1 decreased by the same 259 — consistent with the broader tolerance scan now finding ≤24 h matches for some ECGs that previously got an offset > 24 h L1 binding (or no tolerance match at all). ✅
- EHR cache row counts unchanged from first run; all nine match §5.3. ✅
- Per-script `main.log` first/last 5 lines pasted in §6 of the report all match the §8.5 regex; no `all.log` exists in any `logs/<script>/` directory. ✅

**Decision math (independently recomputed from `label_availability.parquet` totals reported in the rerun):**

| Threshold (spec §3.7.2)                         | Bar         | Reported value             | Pass |
|-------------------------------------------------|-------------|----------------------------|------|
| Clean linkage (L3/L2) ≥ 30 %                    | 30 %        | 547,827 / 800,035 = 68.48 % | ✅  |
| Plan A: L3-or-high-confidence-L2 ICD ≥ 40 %     | 40 %        | 547,671 / 800,035 = 68.46 % | ✅  |
| Plan A: any key lab within ±24 h ≥ 20 %         | 20 %        | 608,968 / 800,035 = 76.12 % | ✅  |
| Plan A: risk outcomes ≥ 1000 OR ≥ 1 %           | 1000 or 1 % | 101,276 (12.66 %)          | ✅  |

All four Plan-A sub-conditions hold; `chosen_path = plan_a` is correctly derived. Margins are 17–46 percentage points above the bars, so the small per-row binding changes from the fixes cannot move the decision.

---

## A. Stage Completion

Every Stage-1 deliverable listed in §9.3 Stage 1 and §3.7.3 is present on disk (six scripts under `scripts/phase1_dataset_generation/`, nine EHR cache parquets, seven linkage parquets, `linkage_feasibility_report.md`, `decision.yaml`, new `key_labs.yaml`, and the `ehr_cache:` block in `dataset_versions.yaml`). The eight §10 report sections are present and the §8.14 logging-hygiene checklist is filled in.

## B. EHR Cache Validation

All nine table row counts in the rerun exactly match the §5.3 expected values: admissions 546,028; patients 364,627; diagnoses_icd 6,364,488; d_icd_diagnoses 112,107; d_labitems 1,650; labevents 158,374,764; edstays 425,087; ed.diagnosis 899,050; triage 425,087. SHA256 changed (different rerun, different `created_at_iso` metadata) but row counts are stable. ✅

## C. Exact Overlap Linkage

Implementation unchanged from the first run (correctness was previously verified). Re-run counts identical: hosp 298,358 studies linked, ed 184,796 studies linked, union 468,176 (= L3 total). ✅

## D. Tolerance Linkage

- `WINDOWS = [(6,360),(12,720),(24,1440),(168,10080)]` — all four ±6h / ±12h / ±24h / ±7d windows present. ✅
- Per-ECG candidate generation now exhaustively scans intervals whose nearest edge is within ±7 d (D-MINOR-1 fix verified at source). ✅
- Candidate persistence per §3.7.1 step 7: all four `*_candidates.parquet` files written before any selection. Concatenated `candidate_links.parquet` now contains 602,314 rows (up from 597,753 pre-fix). ✅

## E. Tie Breaking

The corrected `43_tie_break_link.select_final` sort order matches §3.7.1 step 6 verbatim:
1. `abs_tie_minutes` — primary key, "smallest |ecg_time − midpoint|" ✅
2. `link_type_priority` — exact (0) before tolerance (1) ✅
3. `id_priority` — lowest id (`hadm_id` else `stay_id`) ✅
4. `conditional_hosp_priority` — hosp wins **only** when the row has both `hadm_id` and `stay_id` populated ✅
5. `source_stable_priority` — purely a deterministic post-spec tiebreaker

The new ordering correctly demotes any candidate that lost on midpoint distance, exact-over-tolerance, or lowest id; the hosp preference is no longer pre-empting the spec keys. ✅

## F. Linkage Tier Assignment

Per-candidate tier mapping in `add_candidate_tiers` unchanged (exact → L3; tolerance ≤ 24 h → L2; else L1) and matches the spec table. L0 is filled in by `44_label_availability.py` via a left-merge fillna. Final tier counts independently verified: L3 + L2 + L1 = 785,761 = `linkage_final.parquet` row count; + L0 14,274 = 800,035 total. ✅

## G. Label Availability

- ICD availability, key-lab ±6h/±24h (per-lab + aggregate), mortality observability, in-hospital mortality, 30-day mortality, readmission eligibility, and 30-day readmission positive are all computed; column types nullable boolean where appropriate. ✅
- Key-lab itemid set is read from `config/key_labs.yaml` at runtime (G-MINOR-1 fix verified at source). The rerun log line `loaded key labs from D:\…\config\key_labs.yaml names=K,Na,creatinine,troponin,lactate` confirms wiring. ✅
- 20 + 20 manual audit examples written to both the log and the markdown report. Random states fixed (41/42) for determinism. ✅

## H. Decision Gate

- Branch logic unchanged and correctly maps `(plan_a_all_subconditions, clean_linkage<30%, else)` → `(plan_a, plan_b, hybrid)`. ✅
- `decision.yaml` now includes a `key_labs:` block in addition to `threshold_pass`, `threshold_values`, `linkage_distribution`, and `frozen_at`. The included itemids match `key_labs.yaml` exactly. ✅
- Independent threshold math (above) confirms `plan_a` is the correct outcome.

## I. Logging and Resource Compliance

- `_stage1_common.setup_main_logger` now attaches exactly one `RotatingFileHandler(main.log)` plus a `StreamHandler(sys.stderr)`, matching §8.13 (I-MINOR-1 fix verified at source). ✅
- All Stage 1 `main.log` files exist; first/last 5 lines all match the §8.5 regex `^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \w+\s+pid=\d+`. ✅
- `print(` and `logging.basicConfig(` grep both empty across all stage scripts. ✅
- All tqdm bars use `mininterval=0.5` inside `with logging_redirect_tqdm():`. ✅
- Atomic publish (`<final>.tmp` → `os.replace`) used for every parquet, the YAML config files, and the feasibility report. ✅
- Disk: 193.7 → 193.7 GiB free (negligible delta from the rerun overwriting in-place); well within §6.2 and §9.2 budgets.

## J. Report Quality

`stage_1_report.md` follows the §10 eight-section format, opens with a disposition of the four prior findings, and pastes full final code for every Stage 1 script. `linkage_feasibility_report.md` contains Tables L1–L4, Figure L1, the 20 + 20 manual audit examples, and a new key-lab configuration block.

---

# Findings

None. All four prior findings are resolved with on-disk source-level verification.

---

# REVIEW VERDICT: PASS — proceed to Stage 2

The MAJOR tie-break ordering violation in `43_tie_break_link.py` is fixed: the sort key now starts with `abs_tie_minutes`, then `link_type_priority`, then `id_priority`, with the hospital-over-ED preference applied only conditionally (both ids populated) and only as a later tiebreaker — matching §3.7.1 step 6 verbatim. The three MINOR findings are also resolved: tolerance candidate generation now scans every interval within ±7 days (+4,561 additional persisted candidates); key-lab itemids are version-locked in `config/key_labs.yaml` and mirrored into `decision.yaml`; `setup_main_logger` writes only `main.log` per §8.13. Every spec-mandated Stage 1 artifact is on disk, EHR cache row counts exactly match §5.3, the four Plan A thresholds are independently verifiable (68.48 %, 68.46 %, 76.12 %, 12.66 %) and `chosen_path = plan_a` is correctly derived. Stage 1 is complete and spec-compliant.
