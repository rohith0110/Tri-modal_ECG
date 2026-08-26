<!-- Scaffolded by Stage P2.0, 2026-08-26. See docs/PHASE2_SOURCE_OF_TRUTH.md section 3. -->

# `outputs/tables/` - paper tables

`main/` holds the 5 locked main-paper tables, `supplementary/` the 15
supplementary tables (Round 4.3 decision). Written by
`60_make_paper_tables.py` (Stage P2.12).

| main/ | Contents |
|---|---|
| `table1_overview.tex` | Plan A/B section 7 evidence matrix |
| `table2_planA_results.tex` | Plan A headline results |
| `table3_planB_results.tex` | Plan B headline results |
| `table4_calibration.tex` | A3 / A6 calibration |
| `table5_robustness_AUCC.tex` | B2 area-under-corruption-curve |

Stage P2.12 validation requires every `.tex` here to compile in a smoke check.

*(Files predating Phase 2 in this directory belong to the Plan-B benchmark
report and are not Phase 2 artifacts.)*
