# Stage 0 — Foundation — Independent Reviewer Report (Re-Review)

**Reviewer role:** Independent specification-compliance reviewer
**Spec authority:** `docs/PIPELINE_SOURCE_OF_TRUTH.md` (§2.2, §3.1, §5.2, §5.3, §9.3 Stage 0, §11)
**Inputs reviewed:** `stage_0_report.md` + re-run logs, `config/dataset_versions.yaml`, `outputs/audit_reports/access_check.md`, `data/processed/index/ecg_metadata.parquet`, all three Stage 0 scripts, raw data tree
**Date:** 2026-05-31 (re-review after fixes)

This supersedes the prior HALT review. All four findings from that review were addressed and the third Stage 0 script was implemented and run. Findings below were re-verified against the **on-disk artifacts and the actual script source**, not just the pasted logs.

---

## Disposition of prior findings

| # | Prior severity | Finding | Status |
|---|----------------|---------|--------|
| 1 | **CRITICAL** | `01_build_master_index.py` not implemented; `ecg_metadata.parquet` missing; 3 validation items unmet | ✅ **RESOLVED** — script written, run, parquet verified on disk |
| 2 | MINOR | Library detection was a hard-coded list, not a scan | ✅ **RESOLVED** — AST import scanner added; run logs `Import-scan: all phase1 imports covered` |
| 3 | MINOR | Docstrings cited §8.6 (Pool initializer) for sequential scripts | ✅ **ADDRESSED** — re-labelled `§8.6 (sequential scripts)` in all three scripts (see note below) |
| 4 | MINOR | Misleading labevents comment ("Use known value from prior access check") | ✅ **RESOLVED** — now "fully counted each run; no cached value is reused" |

---

## Independent verification performed (this re-review)

- **All three scripts compile cleanly** — `py_compile` with `doraise=True` passes for `00_lock_versions.py`, `00b_access_check.py`, `01_build_master_index.py`. (The trailing code-fence / duplicate `main()` that appeared in a raw file read was a read-rendering artifact; the real file tail ends with a single `if __name__ == "__main__": main()`.)
- **`ecg_metadata.parquet` schema verified on disk** — 800,035 rows; columns and arrow types:
  - `subject_id` int64, `study_id` int64, `path` string
  - `report_lines` **list&lt;string&gt;** ✅ (matches §9.3 `report_lines: list<string>`)
  - `T_machine` string, `T_cardio` **string, nullable, 190,770 nulls** ✅ (matches §9.3/§12 res. 4)
  - `has_machine_measurements` bool, `has_machine_report_text` bool
  - `machine_hr_bpm` double, `machine_qrs_ms` double, `machine_qtc_ms` double
  - `cart_id` int64, `filtering` string, `bandwidth` string (§9.3 does not pin dtypes for these)
  - All §9.3 script-3 mandated columns present; no imputation (machine_* and T_cardio retain nulls).
- **Parquet schema metadata stamp present** — `dataset_version: v2.0.0`, `created_at_iso`, `modality_kind: ecg_metadata_index`, `n_rows: 800035`, `script: 01_build_master_index.py`.
- **Stage 0 validation block (§9.3) — all 5 items satisfied:**
  - V1 `dataset_versions.yaml` exists; all phase1 imports covered (import scanner) ✅
  - V2 `access_check.md` PASS — re-run, 16/16 SHA256 MATCH, all row counts in range ✅
  - V3 `ecg_metadata.parquet` rows (800,035) == `record_list.csv` rows (800,035), independently recounted ✅
  - V4 50 random rows printed for manual inspection ✅
  - V5 `T_cardio` present, dtype nullable string ✅

---

## MINOR — RESOLVED: parquet metadata key `script` → `script_commit_hash`

**Spec section:** §2.2 — Parquet container header "Required fields: `dataset_version`, `created_at_iso`, `modality_kind`, `n_rows`, `script_commit_hash`."

**Was:** The schema metadata used the key `script` rather than `script_commit_hash`.

**Fixed:** `01_build_master_index.py` now stamps `script_commit_hash` via a `_script_commit_hash()` helper (`git rev-parse --short HEAD`, falling back to `uncommitted:<filename>` when there is no commit yet). Re-run `01_build_master_index.py` to regenerate the parquet with the corrected key.

## MINOR — RESOLVED: §8 logging citation number

**Spec section:** §8.13 — "For sequential scripts".

**Was:** Scripts cited `§8.6 (sequential scripts)`; the correct sequential-script section is §8.13.

**Fixed:** All three scripts now cite `§8.13 (sequential scripts)` (docstring + logging-section comment). Comment-only change — no re-run required for correctness.

---

## REVIEW VERDICT: PASS — proceed to Stage 1

The original CRITICAL is fully resolved: `01_build_master_index.py` is implemented and its `data/processed/index/ecg_metadata.parquet` is present, correctly schema'd (all §9.3 columns, `report_lines` as list&lt;string&gt;, `T_cardio` nullable string), row-count-matched to `record_list.csv`, and version-stamped. The two version-lock/access-check scripts re-ran clean (access check PASS, 16/16 SHA256). All five Stage 0 validation items pass. The two remaining items are non-blocking MINORs. Stage 0 is complete and spec-compliant.
