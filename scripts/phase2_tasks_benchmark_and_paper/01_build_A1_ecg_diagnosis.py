"""Stage P2.1 script 01 -- A1: EHR diagnosis prediction (multi-label ICD).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/01_build_A1_ecg_diagnosis.py [--dev]

Spec §4.A.1. Five multi-label ICD-group heads over the hospital admission the
ECG overlaps with. The label is **encounter-associated, not prospective** -- the
ICD code is assigned at the end of the admission, after the ECG (§4.A.1.3).

Cohort (§4.A.1.2). ``link_tier == 'L3'`` with ``icd_available`` is primary;
``link_tier in {L3, L2}`` is the sensitivity cohort. Both live in ONE table,
distinguished by ``link_tier`` and by the added ``is_primary`` flag -- the
§4.A.1.5 schema already carries ``link_tier`` with the comment "L3 in primary;
L2 in sensitivity", so a single table with the filter columns present is what
that schema describes. Same for the label source: hospital ICD rows are
primary, and ED-linked rows carry ``label_source == 'ed'`` and
``is_primary == False`` so they are never pooled by accident (§4.A.1.2, Plan
A/B §5.3 "Do not mix hospital and ED labels without a provenance column").

Labels come from ``config/icd_label_map_LOCKED.yaml`` and nothing else. Its
matching contract is binding: strip the code, match ``icd_version`` exactly,
``*_prefix`` is ``startswith``, ``*_exact*`` is equality, groups are
independent. ``cohort_manifest.parquet`` carries the resolved ``long_title``
for every code that fired, per Appendix B.

Machine measurements and structured features are forbidden inputs (§4.A.1.4)
and no column here is derived from them; ``sqi_tier`` and ``cart_id`` are
subgroup keys, not features.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402

STAGE = "P2.1"
SCRIPT = "01_build_A1_ecg_diagnosis"
TASK = "A1_ecg_diagnosis"

GROUPS = [
    "atrial_fibrillation_flutter",
    "heart_failure_narrow",
    "acute_myocardial_infarction",
    "conduction_disorder",
    "ventricular_arrhythmia_or_arrest",
]
BOUNDARY_HOURS = 2  # §4.A.1.5: within +/-2 h of admittime or dischtime

SCHEMA = pa.schema(
    [
        ("study_id", pa.int64()),
        ("subject_id", pa.int64()),
        ("split", pa.string()),
        ("hadm_id", pa.int64()),
        ("ecg_time", pa.timestamp("ns")),
        ("link_tier", pa.string()),
        ("boundary_flag", pa.bool_()),
    ]
    + [(f"label_{g}", pa.bool_()) for g in GROUPS]
    + [
        ("label_source", pa.string()),
        ("n_icd_codes_on_admission", pa.int32()),
        ("icd_codes_matched", pa.list_(pa.string())),
        ("sqi_tier", pa.string()),
        ("cart_id", pa.string()),
        ("is_primary", pa.bool_()),
    ]
)


def load_label_map() -> dict:
    return yaml.safe_load(
        (bc.CONFIG_DIR / "icd_label_map_LOCKED.yaml").read_text(encoding="utf-8")
    )["groups"]


def code_group_table(codes: pd.DataFrame, groups: dict) -> pd.DataFrame:
    """One row per distinct (icd_version, icd_code) with a boolean per group.

    ``codes`` must carry ``icd_code`` (already stripped) and ``icd_version``.
    """
    out = codes.copy()
    for group in GROUPS:
        rules = groups[group]
        hit = np.zeros(len(out), dtype=bool)
        for version, prefix_key, exact_keys in (
            (10, "icd10_prefix", ("icd10_exact", "icd10_exact_optional")),
            (9, "icd9_prefix", ("icd9_exact", "icd9_exact_optional")),
        ):
            same_version = (out["icd_version"] == version).to_numpy()
            for prefix in rules.get(prefix_key, []) or []:
                hit |= same_version & out["icd_code"].str.startswith(str(prefix)).to_numpy()
            for exact_key in exact_keys:
                exact = set(str(c) for c in (rules.get(exact_key, []) or []))
                if exact:
                    hit |= same_version & out["icd_code"].isin(exact).to_numpy()
        out[group] = hit
    return out


def aggregate_by_encounter(assign: pd.DataFrame, key: str, code_groups: pd.DataFrame) -> pd.DataFrame:
    """Roll per-code group flags up to one row per encounter (`hadm_id` / `stay_id`)."""
    merged = assign.merge(code_groups, on=["icd_code", "icd_version"], how="left")
    for group in GROUPS:
        merged[group] = merged[group].fillna(False)
    merged["any_group"] = merged[GROUPS].any(axis=1)

    agg = merged.groupby(key, sort=False).agg(
        **{g: (g, "any") for g in GROUPS},
        n_icd_codes_on_admission=("icd_code", "size"),
    )
    matched = (
        merged[merged["any_group"]]
        .sort_values([key, "icd_code"], kind="mergesort")
        .groupby(key, sort=False)["icd_code"]
        .apply(list)
        .rename("icd_codes_matched")
    )
    agg = agg.join(matched)
    agg["icd_codes_matched"] = agg["icd_codes_matched"].apply(
        lambda v: v if isinstance(v, list) else []
    )
    return agg.reset_index()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    bc.add_std_args(parser)
    args = parser.parse_args()

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT + ("_dev" if args.dev else ""))
    if state.done and not args.force:
        log.info("already complete (%s rows) -- pass --force to rebuild", state.data.get("n_rows"))
        return 0
    state.reset()
    started = time.time()

    bc.preflight([
        bc.EHR_CACHE / "diagnoses_icd.parquet",
        bc.EHR_CACHE / "d_icd_diagnoses.parquet",
        bc.EHR_CACHE / "ed_diagnosis.parquet",
        bc.EHR_CACHE / "admissions.parquet",
        bc.CONFIG_DIR / "icd_label_map_LOCKED.yaml",
    ])

    groups = load_label_map()
    cohort = bc.load_clean_cohort(dev=args.dev)
    cohort = cohort[cohort.link_tier.isin(["L3", "L2"])].copy()
    log.info("L3+L2 clean cohort: %d studies", len(cohort))

    # --- hospital ICD --------------------------------------------------------
    diag = pd.read_parquet(
        bc.EHR_CACHE / "diagnoses_icd.parquet",
        columns=["subject_id", "hadm_id", "icd_code", "icd_version"],
    )
    diag["icd_code"] = diag["icd_code"].astype(str).str.strip()
    needed_hadm = set(cohort.hadm_id.dropna().astype("int64"))
    diag = diag[diag.hadm_id.isin(needed_hadm)]
    log.info("diagnoses_icd rows on cohort admissions: %d", len(diag))

    distinct = diag[["icd_code", "icd_version"]].drop_duplicates()
    code_groups = code_group_table(distinct, groups)
    log.info("distinct codes on cohort admissions: %d, firing: %d",
             len(code_groups), int(code_groups[GROUPS].any(axis=1).sum()))
    hosp = aggregate_by_encounter(diag, "hadm_id", code_groups)

    # --- ED ICD (secondary, provenance-tagged, never pooled) -----------------
    ed = pd.read_parquet(
        bc.EHR_CACHE / "ed_diagnosis.parquet",
        columns=["subject_id", "stay_id", "icd_code", "icd_version"],
    )
    ed["icd_code"] = ed["icd_code"].astype(str).str.strip()
    needed_stay = set(cohort.stay_id.dropna().astype("int64"))
    ed = ed[ed.stay_id.isin(needed_stay)]
    ed_codes = code_group_table(ed[["icd_code", "icd_version"]].drop_duplicates(), groups)
    ed_agg = aggregate_by_encounter(ed, "stay_id", ed_codes) if len(ed) else None
    log.info("ed_diagnosis rows on cohort stays: %d", len(ed))

    # --- boundary flag -------------------------------------------------------
    adm = pd.read_parquet(
        bc.EHR_CACHE / "admissions.parquet", columns=["hadm_id", "admittime", "dischtime"]
    )
    cohort = cohort.merge(adm, on="hadm_id", how="left")
    window = pd.Timedelta(hours=BOUNDARY_HOURS)
    near_admit = (cohort.ecg_time - cohort.admittime).abs() <= window
    near_disch = (cohort.ecg_time - cohort.dischtime).abs() <= window
    cohort["boundary_flag"] = (near_admit | near_disch).fillna(False)

    # --- assemble ------------------------------------------------------------
    hosp_rows = cohort[cohort.hadm_id.notna() & cohort.icd_available.fillna(False)].merge(
        hosp, on="hadm_id", how="inner"
    )
    hosp_rows["label_source"] = "hosp"
    log.info("hospital-ICD rows: %d", len(hosp_rows))

    if ed_agg is not None and len(ed_agg):
        ed_rows = cohort[cohort.stay_id.notna() & cohort.hadm_id.isna()].merge(
            ed_agg, on="stay_id", how="inner"
        )
        ed_rows["label_source"] = "ed"
    else:
        ed_rows = hosp_rows.iloc[0:0].copy()
    log.info("ED-ICD rows (secondary only): %d", len(ed_rows))

    df = pd.concat([hosp_rows, ed_rows], ignore_index=True)
    for group in GROUPS:
        df[f"label_{group}"] = df[group].astype(bool)
    df["is_primary"] = (df.link_tier == "L3") & (df.label_source == "hosp")
    df["cart_id"] = df["cart_id"].astype("Int64").astype("string")
    df["hadm_id"] = df["hadm_id"].astype("Int64")
    df["n_icd_codes_on_admission"] = df["n_icd_codes_on_admission"].astype("int32")
    df = df.sort_values("study_id", kind="mergesort").reset_index(drop=True)

    counts = bc.write_task_split_parquets(df, TASK, schema=SCHEMA)
    log.info("wrote splits: %s", counts)

    # --- cohort manifest: the Appendix B long_title evidence -----------------
    dictionary = pd.read_parquet(
        bc.EHR_CACHE / "d_icd_diagnoses.parquet",
        columns=["icd_code", "icd_version", "long_title"],
    )
    dictionary["icd_code"] = dictionary["icd_code"].astype(str).str.strip()
    firing = code_groups[code_groups[GROUPS].any(axis=1)].merge(
        dictionary, on=["icd_code", "icd_version"], how="left"
    )
    occurrences = diag.groupby(["icd_code", "icd_version"]).size().rename("n_rows_in_cohort")
    firing = firing.merge(occurrences, on=["icd_code", "icd_version"], how="left")
    firing["n_rows_in_cohort"] = firing["n_rows_in_cohort"].fillna(0).astype("int64")
    manifest = firing.melt(
        id_vars=["icd_code", "icd_version", "long_title", "n_rows_in_cohort"],
        value_vars=GROUPS, var_name="icd_group", value_name="matched",
    )
    manifest = manifest[manifest.matched].drop(columns=["matched"]).sort_values(
        ["icd_group", "icd_version", "icd_code"], kind="mergesort"
    )
    bc.write_cohort_manifest(manifest, TASK)
    log.info("cohort_manifest: %d (group, code) rows", len(manifest))

    # --- validation (§9.2) ---------------------------------------------------
    primary = df[df.is_primary]
    stats = {
        "n_rows_total": int(len(df)),
        "n_rows_primary_l3_hosp": int(len(primary)),
        "n_rows_sensitivity_l2": int((df.link_tier == "L2").sum()),
        "n_rows_ed_secondary": int((df.label_source == "ed").sum()),
        "splits": counts,
        "boundary_flag_pct": round(100 * float(df.boundary_flag.mean()), 3),
        "boundary_flag_pct_primary": round(100 * float(primary.boundary_flag.mean()), 3),
        "n_manifest_codes": int(len(manifest)),
        "prevalence_primary": {
            g: round(100 * float(primary[f"label_{g}"].mean()), 3) for g in GROUPS
        },
        "prevalence_primary_by_split": {
            s: {g: round(100 * float(primary[primary.split == s][f"label_{g}"].mean()), 3)
                for g in GROUPS}
            for s in bc.SPLITS
        },
        "n_any_label_primary": int(primary[[f"label_{g}" for g in GROUPS]].any(axis=1).sum()),
    }
    stats.update(bc.split_summary(df))
    stats.update({f"primary_{k}": v for k, v in bc.split_summary(primary).items()})
    log.info("validation:\n%s", json.dumps(stats, indent=2))

    if stats["n_rows_primary_l3_hosp"] == 0:
        raise RuntimeError("A1 primary cohort is empty")
    if stats["n_any_label_primary"] == 0:
        raise RuntimeError("no primary row carries any ICD group label")

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# A1 -- EHR diagnosis prediction (multi-label ICD)

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.A.1 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/01_build_A1_ecg_diagnosis.py`.

## Reading this table

`train.parquet` / `val.parquet` / `test.parquet` hold the **union** of the
primary and sensitivity cohorts. Filter before use:

| Analysis | Filter |
| --- | --- |
| **Primary** (§4.A.1.2) | `is_primary` — equivalently `link_tier == 'L3' and label_source == 'hosp'` |
| L3+L2 sensitivity | `link_tier in ('L3','L2') and label_source == 'hosp'` |
| Hospital+ED secondary | drop the `label_source` filter; never pool without reporting it |
| Boundary-excluded sensitivity | `not boundary_flag` |

The split column is joined from `splits_subject_level.parquet` and is never
re-derived (§4.C invariant 1).

## Labels

Five independent binary heads from `config/icd_label_map_LOCKED.yaml`. A head is
True when **any** ICD row on the linked encounter matches **any** pattern in that
group. `icd_codes_matched` lists the codes that fired;
`cohort_manifest.parquet` resolves every one of them to its `long_title`
(Plan A/B Appendix B).

Label timing: **encounter-associated, not prospective.** The ICD code is
assigned at the end of the admission, after the ECG.

## Forbidden inputs

`machine_measurements`, `structured_features` (§4.A.1.4). `sqi_tier` and
`cart_id` are present as subgroup keys for the §4.A.1.8 tables, not as model
features.

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
