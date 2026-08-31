"""Stage P2.1 script 06 -- A6: risk stratification (mortality + readmission, 30 d / 90 d).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/06_build_A6_risk_stratification.py [--dev]

Spec §4.A.6. Four binary heads. Index time is ``ecg_time``; no post-ECG feature
enters the table.

Mortality (§4.A.6.3)::

    death_time    = patients.dod  if not null else admissions.deathtime[hadm_id]
    mortality_30d = death_time is not null and 0 < death_time - ecg_time <= 30 d
    mortality_90d = same at 90 d

ED-only ECGs keep a mortality label -- ``patients.dod`` is observable whether or
not the patient was admitted -- but carry **null** readmission labels, per
§4.A.6.2 and Plan A/B §5.8.

Readmission (§4.A.6.3). The next admission is the earliest ``admittime``
strictly after this admission's ``dischtime`` for the same subject, a different
``hadm_id``, and "not just a transfer".

**Two readings §4.A.6.3 leaves to the builder, both recorded as data rather than
baked in silently:**

1. *"not just a transfer."* MIMIC-IV keeps intra-stay movement in the
   ``transfers`` table, where it creates no second ``hadm_id``, so the only
   candidates that are transfers rather than readmissions are hand-offs recorded
   as two admissions. This builder excludes a candidate whose
   ``admission_location`` starts with ``TRANSFER FROM`` **and** whose gap from
   the previous discharge is at most one hour -- contiguity is what makes it a
   hand-off; a transfer-in three days later is a genuine readmission. The
   candidate's ``admission_type`` and ``admission_location`` ship as provenance
   columns, so the "unplanned only" and "no transfer exclusion" variants are
   filters, not rebuilds.
2. *"Exclude rows where the censoring window cannot be observed."* §4.A.6.3
   assumes a global end-of-data cutoff. MIMIC-IV has none that is usable: every
   patient's dates are shifted into a private future window, so "how close is
   this discharge to the end of the data" is not answerable in shifted time.
   The tempting substitute -- call a row observable when the subject's own
   record extends past ``dischtime + horizon`` -- **conditions on the outcome**:
   it keeps the subjects who came back and drops the ones who did not. Measured
   on the dev sample, that lifted the 30 d rate from ~10 % to 29 %. This builder
   therefore uses the Phase 1 definition (eligible = the ECG sits inside an
   admission with a discharge time) and ships
   ``followup_days_after_discharge`` -- the subject's last recorded event minus
   this discharge -- as provenance, so a censoring-aware sensitivity analysis is
   a filter rather than a rebuild. The residual right-censoring is a stated
   limitation of the readmission heads.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402

STAGE = "P2.1"
SCRIPT = "06_build_A6_risk_stratification"
TASK = "A6_risk_stratification"

BOUNDARY_HOURS = 2
TRANSFER_GAP_HOURS = 1
ADMISSIONS_CSV = bc.DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "admissions.csv.gz"

SCHEMA = pa.schema([
    ("study_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("split", pa.string()),
    ("link_tier", pa.string()),
    ("sqi_tier", pa.string()),
    ("cart_id", pa.string()),
    ("boundary_flag", pa.bool_()),
    ("hadm_id", pa.int64()),
    ("ecg_time", pa.timestamp("ns")),
    ("mortality_30d", pa.bool_()),
    ("mortality_90d", pa.bool_()),
    ("mortality_observable", pa.bool_()),
    ("readmission_30d", pa.bool_()),          # null for ED-only
    ("readmission_90d", pa.bool_()),          # null for ED-only
    ("readmission_eligible", pa.bool_()),     # 30 d horizon
    ("readmission_eligible_90d", pa.bool_()),
    ("days_to_death", pa.float32()),
    ("days_to_readmission", pa.float32()),
    ("followup_days_after_discharge", pa.float32()),
    ("next_admission_type", pa.string()),
    ("next_admission_location", pa.string()),
    # --- Plan A/B §5.8 nested-baseline covariates. ALL strictly pre-ECG. -----
    # §5.8 requires six baseline tiers for A6 -- prevalence, demographics,
    # demographics+comorbidities, utilization, machine measurements, ECG -- and
    # Figure 5 is the nested curve across them. §7 names the failure condition
    # outright: "Only compared to random/prevalence baseline." None of these
    # columns existed, so the intermediate rungs could not be built at all.
    #
    # Every one of them is knowable at `ecg_time`: Plan §5.8's index-time rule is
    # "do not use any feature measured after ECG", and App. F lists "using future
    # covariates for risk" as a named failure mode. The builder enforces it by
    # construction -- prior counts read admissions DISCHARGED before the ECG,
    # prior diagnoses come from those admissions only, and the ED disposition is
    # taken from a stay that had already ended.
    #
    # These are BASELINE features, not model inputs: `task_input_policy.yaml`
    # still forbids them for every trained encoder, exactly as the machine
    # measurements are forbidden but permitted to the A6 Cox baseline.
    ("age_at_ecg", pa.float32()),
    ("sex_male", pa.bool_()),
    ("race", pa.string()),
    ("insurance", pa.string()),
    ("admission_type", pa.string()),          # this admission's, known at admit
    ("ed_disposition", pa.string()),          # last ED stay ENDING before the ECG
    ("n_prior_admissions", pa.int32()),
    ("n_prior_ecgs", pa.int32()),
    ("days_since_last_discharge", pa.float32()),
    ("prior_dx_atrial_fibrillation_flutter", pa.bool_()),
    ("prior_dx_heart_failure_narrow", pa.bool_()),
    ("prior_dx_acute_myocardial_infarction", pa.bool_()),
    ("prior_dx_conduction_disorder", pa.bool_()),
    ("prior_dx_ventricular_arrhythmia_or_arrest", pa.bool_()),
    ("is_primary", pa.bool_()),
])

# The comorbidity vocabulary is the LOCKED A1 map, not a new one: five cardiac
# groups, 175 codes, already validated against `d_icd_diagnoses` at Stage P2.0.
# Plan A/B §5.8 asks for "prior ICD/comorbidity flags before ECG only" without
# naming a vocabulary; reusing the locked one keeps A1 and A6 from drifting and
# means no code list is invented here.
PRIOR_DX_GROUPS = ("atrial_fibrillation_flutter", "heart_failure_narrow",
                   "acute_myocardial_infarction", "conduction_disorder",
                   "ventricular_arrhythmia_or_arrest")


def load_admissions() -> pd.DataFrame:
    """Admissions with the two columns the cached parquet dropped.

    ``data/raw/ehr_cache/admissions.parquet`` carries no ``admission_type`` or
    ``admission_location``, and both are needed to tell a hand-off from a
    readmission. The source CSV is 546 K rows -- cheap to read directly.
    """
    adm = pd.read_csv(
        ADMISSIONS_CSV,
        usecols=["subject_id", "hadm_id", "admittime", "dischtime", "deathtime",
                 "admission_type", "admission_location", "hospital_expire_flag",
                 # §5.8 demographics baseline; the cached parquet drops both.
                 "race", "insurance"],
        parse_dates=["admittime", "dischtime", "deathtime"],
        compression="gzip",
    )
    return adm.sort_values(["subject_id", "admittime"], kind="mergesort").reset_index(drop=True)


def next_admission_table(adm: pd.DataFrame) -> pd.DataFrame:
    """For every hadm_id, the first *non-transfer* later admission of that subject.

    Walks each subject's admissions in time order and, for each one, scans
    forward past any contiguous transfer hand-off to the first candidate whose
    ``admittime`` is strictly after this row's ``dischtime``.
    """
    records: list[dict] = []
    gap = pd.Timedelta(hours=TRANSFER_GAP_HOURS)
    for _, group in adm.groupby("subject_id", sort=False):
        hadm = group["hadm_id"].to_numpy()
        admit = group["admittime"].to_numpy()
        disch = group["dischtime"].to_numpy()
        atype = group["admission_type"].to_numpy()
        aloc = group["admission_location"].astype(str).to_numpy()
        n = len(group)
        for i in range(n):
            if pd.isna(disch[i]):
                continue
            discharge = pd.Timestamp(disch[i])
            for j in range(i + 1, n):
                candidate = pd.Timestamp(admit[j])
                if pd.isna(candidate) or candidate <= discharge:
                    continue
                is_transfer = (
                    aloc[j].upper().startswith("TRANSFER FROM")
                    and (candidate - discharge) <= gap
                )
                if is_transfer:
                    continue                      # a hand-off, not a readmission
                records.append({
                    "hadm_id": int(hadm[i]),
                    "next_admittime": candidate,
                    "next_admission_type": None if pd.isna(atype[j]) else str(atype[j]),
                    "next_admission_location": aloc[j],
                })
                break
    return pd.DataFrame(records)


def prior_ecg_counts(cohort: pd.DataFrame, all_ecgs: pd.DataFrame) -> pd.Series:
    """How many of the subject's ECGs precede this one, over the WHOLE index.

    Counted against every clean ECG the subject has, not just the L3/L2 ones in
    the A6 cohort. Plan A/B §5.8 wants prior ECG count as a utilization proxy --
    "controls for sick-patient ECG frequency" -- and a patient's unlinked
    outpatient ECGs are part of that frequency. Restricting the count to the A6
    cohort would make the covariate a function of linkage rather than of care.
    """
    pool = all_ecgs[all_ecgs.subject_id.isin(set(cohort.subject_id))][
        ["study_id", "subject_id", "ecg_time"]].copy()
    pool = pool.sort_values(["subject_id", "ecg_time", "study_id"], kind="mergesort")
    pool["n_prior"] = pool.groupby("subject_id").cumcount().astype("int32")
    return cohort.study_id.map(pool.set_index("study_id")["n_prior"])


def prior_history(cohort: pd.DataFrame, adm: pd.DataFrame) -> pd.DataFrame:
    """Per-ECG utilisation and comorbidity counts, using only PRE-ECG records.

    Plan A/B §5.8's utilization tier ("prior admissions, prior ECG count,
    current admission type") and its comorbidity tier ("prior ICD ... before ECG
    only"). App. F's "using future covariates for risk" is the failure mode this
    guards against, so the cut is explicit and one-sided everywhere:

    * an admission counts only if its **discharge** precedes the ECG -- an
      admission still in progress is the ECG's own encounter, not history;
    * a prior ECG counts only if its ``ecg_time`` is strictly earlier;
    * a prior diagnosis is read from those already-discharged admissions only,
      because ICD codes are assigned at discharge and the current admission's
      codes describe the very episode being predicted from.

    Returns one row per cohort study.
    """
    out = pd.DataFrame({"study_id": cohort.study_id.to_numpy(),
                        "subject_id": cohort.subject_id.to_numpy(),
                        "ecg_time": cohort.ecg_time.to_numpy()})

    discharged = adm[adm.dischtime.notna()][["subject_id", "hadm_id", "dischtime"]]
    pairs = out[["study_id", "subject_id", "ecg_time"]].merge(
        discharged, on="subject_id", how="left", validate="many_to_many")
    before = pairs[pairs.dischtime < pairs.ecg_time]

    counts = before.groupby("study_id").size()
    out["n_prior_admissions"] = out.study_id.map(counts).fillna(0).astype("int32")
    last_discharge = before.groupby("study_id")["dischtime"].max()
    out["days_since_last_discharge"] = (
        (out.ecg_time - out.study_id.map(last_discharge)).dt.total_seconds() / 86400.0
    ).astype("float32")

    # Prior diagnoses, from the already-discharged admissions only. The matcher
    # is A1's, imported rather than copied: two implementations of "does this
    # ICD code belong to this group" would eventually disagree, and then A1's
    # label and A6's comorbidity flag would mean different things.
    a1 = _import_a1()
    groups = a1.load_label_map()
    dx = pd.read_parquet(bc.EHR_CACHE / "diagnoses_icd.parquet",
                         columns=["subject_id", "hadm_id", "icd_code", "icd_version"])
    dx = dx[dx.subject_id.isin(set(out.subject_id))].copy()
    dx["icd_code"] = dx["icd_code"].astype(str).str.strip()

    distinct = dx[["icd_code", "icd_version"]].drop_duplicates()
    flags = a1.code_group_table(distinct, groups)
    prior_dx = (before[["study_id", "hadm_id"]]
                .merge(dx[["hadm_id", "icd_code", "icd_version"]], on="hadm_id", how="inner", validate="many_to_many")
                .merge(flags, on=["icd_code", "icd_version"], how="left", validate="many_to_one"))
    for group in PRIOR_DX_GROUPS:
        hits = set(prior_dx.loc[prior_dx[group].fillna(False), "study_id"])
        out[f"prior_dx_{group}"] = out.study_id.isin(hits)
    return out.drop(columns=["subject_id", "ecg_time"])


def _import_a1():
    """Load `01_build_A1_ecg_diagnosis.py` as a module (its name starts with a digit)."""
    import importlib.util

    path = Path(__file__).resolve().parent / "01_build_A1_ecg_diagnosis.py"
    spec = importlib.util.spec_from_file_location("_a1_builder", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ed_disposition_before_ecg(cohort: pd.DataFrame) -> pd.Series:
    """Disposition of the last ED stay that had ENDED before the ECG.

    Plan A/B §5.8: "ED disposition if before ECG". A stay still open at
    ``ecg_time`` has no disposition yet, and the disposition of the stay the ECG
    was taken during would be a future covariate -- so both are excluded by the
    strict ``outtime < ecg_time`` cut.
    """
    ed = pd.read_parquet(bc.EHR_CACHE / "edstays.parquet",
                         columns=["subject_id", "outtime", "disposition"])
    ed["outtime"] = pd.to_datetime(ed["outtime"], errors="coerce")
    ed = ed[ed.outtime.notna() & ed.subject_id.isin(set(cohort.subject_id))]

    pairs = cohort[["study_id", "subject_id", "ecg_time"]].merge(
        ed, on="subject_id", how="left", validate="many_to_many")
    pairs = pairs[pairs.outtime < pairs.ecg_time]
    latest = pairs.sort_values("outtime", kind="mergesort").groupby("study_id").last()
    return cohort.study_id.map(latest["disposition"]).astype("string")


def last_observed_by_subject(adm: pd.DataFrame, patients: pd.DataFrame) -> pd.Series:
    """Latest timestamp at which the record still speaks for each subject.

    Used only to decide observability, never to make a label. MIMIC-IV has no
    global end-of-data marker, so the honest proxy is the subject's own last
    recorded event.
    """
    last_adm = adm.groupby("subject_id")[["admittime", "dischtime"]].max().max(axis=1)
    dod = patients.set_index("subject_id")["dod"]
    return pd.concat([last_adm, dod], axis=1).max(axis=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    bc.add_std_args(parser)
    args = parser.parse_args()
    bc.set_dev(args.dev)

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT + ("_dev" if args.dev else ""))
    if state.done and not args.force:
        log.info("already complete (%s rows) -- pass --force to rebuild", state.data.get("n_rows"))
        return 0
    state.reset()
    started = time.time()

    bc.preflight([ADMISSIONS_CSV, bc.EHR_CACHE / "patients.parquet"])

    cohort = bc.load_clean_cohort(dev=args.dev)
    cohort = cohort[cohort.link_tier.isin(["L3", "L2"])].copy()
    log.info("L3+L2 clean cohort: %d studies", len(cohort))

    adm = load_admissions()
    patients = pd.read_parquet(bc.EHR_CACHE / "patients.parquet", columns=["subject_id", "dod"])
    patients["dod"] = pd.to_datetime(patients["dod"], errors="coerce")

    subjects = set(cohort.subject_id)
    adm_sub = adm[adm.subject_id.isin(subjects)].copy()
    log.info("admissions for cohort subjects: %d", len(adm_sub))

    nxt = next_admission_table(adm_sub)
    log.info("hadm_ids with a non-transfer next admission: %d", len(nxt))

    df = cohort.merge(
        adm[["hadm_id", "admittime", "dischtime", "deathtime"]], on="hadm_id", how="left"
    , validate="many_to_one").merge(patients, on="subject_id", how="left", validate="many_to_one")
    if len(nxt):
        df = df.merge(nxt, on="hadm_id", how="left", validate="many_to_one")
    else:
        for col in ("next_admittime", "next_admission_type", "next_admission_location"):
            df[col] = pd.NaT if col == "next_admittime" else None

    # --- boundary flag -------------------------------------------------------
    window = pd.Timedelta(hours=BOUNDARY_HOURS)
    df["boundary_flag"] = (
        ((df.ecg_time - df.admittime).abs() <= window)
        | ((df.ecg_time - df.dischtime).abs() <= window)
    ).fillna(False)

    # --- mortality (§4.A.6.3) -----------------------------------------------
    death_time = df["dod"].where(df["dod"].notna(), df["deathtime"])
    delta_death = death_time - df["ecg_time"]
    df["days_to_death"] = (delta_death.dt.total_seconds() / 86400.0).astype("float32")
    after_ecg = delta_death > pd.Timedelta(0)
    df["mortality_30d"] = (after_ecg & (delta_death <= pd.Timedelta(days=30))).fillna(False)
    df["mortality_90d"] = (after_ecg & (delta_death <= pd.Timedelta(days=90))).fillna(False)
    df["mortality_observable"] = df["mortality_observable"].fillna(False).astype(bool)

    # --- readmission (§4.A.6.3) ---------------------------------------------
    # "For an ECG during an admission with hadm_id" -- ED-only ECGs get null,
    # never False, so no head can silently score them as negatives.
    has_admission = df["hadm_id"].notna() & df["dischtime"].notna()
    gap_to_next = df["next_admittime"] - df["dischtime"]
    df["days_to_readmission"] = (gap_to_next.dt.total_seconds() / 86400.0).astype("float32")

    # Eligibility is "this ECG sits inside an admission we can be readmitted
    # from", and NOTHING else -- deliberately, see the README. Deriving it from
    # the subject's own later admissions instead conditions on the outcome: it
    # keeps exactly the subjects who came back and drops the ones who did not,
    # which was measured on the dev sample to inflate the 30 d rate from ~10 %
    # to 29 %. §4.A.6.3's "end-of-data cutoff" is not observable in MIMIC-IV,
    # whose dates are shifted per patient, so the residual right-censoring is
    # reported as a limitation rather than silently "corrected".
    df["readmission_eligible"] = has_admission.fillna(False)
    df["readmission_eligible_90d"] = has_admission.fillna(False)

    last_seen = last_observed_by_subject(adm, patients)
    df["followup_days_after_discharge"] = (
        (df["subject_id"].map(last_seen) - df["dischtime"]).dt.total_seconds() / 86400.0
    ).astype("float32")

    for horizon in (30, 90):
        positive = (gap_to_next.notna() & (gap_to_next <= pd.Timedelta(days=horizon))).fillna(False)
        df[f"readmission_{horizon}d"] = positive.where(has_admission, other=pd.NA).astype("boolean")

    # --- Plan A/B §5.8 nested-baseline covariates ---------------------------
    # Age at the ECG, not anchor age: MIMIC-IV shifts each patient's dates into
    # a private window, but the OFFSET from `anchor_year` is preserved, so
    # `anchor_age + (ecg year - anchor_year)` is valid within a patient even
    # though calendar years are not comparable across patients (§2.3 caveat).
    demo = pd.read_parquet(bc.EHR_CACHE / "patients.parquet",
                           columns=["subject_id", "gender", "anchor_age", "anchor_year"])
    df = df.merge(demo, on="subject_id", how="left", validate="many_to_one")
    df["age_at_ecg"] = (
        df["anchor_age"] + (df["ecg_time"].dt.year - df["anchor_year"])
    ).astype("float32")
    df["sex_male"] = (df["gender"].astype(str).str.upper() == "M")

    df = df.merge(adm[["hadm_id", "admission_type", "race", "insurance"]],
                  on="hadm_id", how="left", validate="many_to_one")
    df["ed_disposition"] = ed_disposition_before_ecg(df)
    df = df.merge(prior_history(df, adm), on="study_id", how="left", validate="many_to_one")
    df["n_prior_ecgs"] = prior_ecg_counts(df, bc.load_clean_cohort(dev=args.dev))
    for group in PRIOR_DX_GROUPS:
        df[f"prior_dx_{group}"] = df[f"prior_dx_{group}"].fillna(False).astype(bool)
    df["n_prior_admissions"] = df["n_prior_admissions"].fillna(0).astype("int32")
    df["n_prior_ecgs"] = df["n_prior_ecgs"].fillna(0).astype("int32")
    for column in ("race", "insurance", "admission_type", "ed_disposition"):
        df[column] = df[column].astype("string")

    # The one thing that must not slip: every covariate above is knowable at
    # `ecg_time` (Plan §5.8 index-time rule, App. F "using future covariates").
    # Assert the two that are computed from timestamps rather than fixed facts.
    lag = df["days_since_last_discharge"].dropna()
    if len(lag) and float(lag.min()) < 0:
        raise RuntimeError(
            f"{int((lag < 0).sum())} rows have a 'last discharge' AFTER the ECG -- "
            "the utilization covariates would be future information")
    if int((df["n_prior_ecgs"] < 0).sum()):
        raise RuntimeError("negative prior-ECG count")

    df["is_primary"] = df.link_tier == "L3"
    df["cart_id"] = df["cart_id"].astype("Int64").astype("string")
    df["hadm_id"] = df["hadm_id"].astype("Int64")
    df["next_admission_type"] = df["next_admission_type"].astype("string")
    df["next_admission_location"] = df["next_admission_location"].astype("string")
    df = df.sort_values("study_id", kind="mergesort").reset_index(drop=True)

    counts = bc.write_task_split_parquets(df, TASK, schema=SCHEMA)
    log.info("wrote splits: %s", counts)

    primary = df[df.is_primary]
    def rate(series: pd.Series) -> float:
        clean = series.dropna()
        return round(100 * float(clean.mean()), 4) if len(clean) else 0.0

    stats = {
        "n_rows_total": int(len(df)),
        "n_rows_primary_l3": int(len(primary)),
        "splits_total": counts,
        "n_mortality_observable_primary": int(primary.mortality_observable.sum()),
        "n_readmission_eligible_primary": int(primary.readmission_eligible.sum()),
        "n_followup_ge_30d_primary": int((primary.followup_days_after_discharge >= 30).sum()),
        "n_followup_ge_90d_primary": int((primary.followup_days_after_discharge >= 90).sum()),
        "prevalence_censoring_aware_pct": {
            "readmission_30d": rate(
                primary.loc[primary.followup_days_after_discharge >= 30, "readmission_30d"]),
            "readmission_90d": rate(
                primary.loc[primary.followup_days_after_discharge >= 90, "readmission_90d"]),
        },
        "n_ed_only_null_readmission": int(primary.readmission_30d.isna().sum()),
        "prevalence_primary_pct": {
            "mortality_30d": rate(primary.mortality_30d),
            "mortality_90d": rate(primary.mortality_90d),
            "readmission_30d": rate(primary.readmission_30d),
            "readmission_90d": rate(primary.readmission_90d),
        },
        "prevalence_primary_by_split_pct": {
            split: {
                head: rate(primary[primary.split == split][head])
                for head in ("mortality_30d", "mortality_90d", "readmission_30d", "readmission_90d")
            }
            for split in bc.SPLITS
        },
        "boundary_flag_pct_primary": round(100 * float(primary.boundary_flag.mean()), 3),
        "days_to_death_median_positive": round(
            float(primary.loc[primary.mortality_90d, "days_to_death"].median()), 2
        ) if int(primary.mortality_90d.sum()) else None,
        "days_to_readmission_median": round(
            float(primary["days_to_readmission"].median()), 2
        ) if primary["days_to_readmission"].notna().any() else None,
        "next_admission_type_top": primary["next_admission_type"].value_counts().head(6).to_dict(),
    }
    stats.update(bc.split_summary(df))
    stats.update({f"primary_{k}": v for k, v in bc.split_summary(primary).items()})
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str))

    if stats["n_rows_primary_l3"] == 0:
        raise RuntimeError("A6 primary cohort is empty")
    # A row that is not eligible must not be labelled at all (§4.A.6.3).
    leaked = int((~df.readmission_eligible & df.readmission_30d.notna()).sum())
    if leaked:
        raise RuntimeError(f"{leaked} rows carry a 30 d readmission label without being eligible")

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2, default=str), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# A6 -- risk stratification (mortality + readmission at 30 d and 90 d)

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.A.6 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/06_build_A6_risk_stratification.py`.

## Reading this table

| Analysis | Filter |
| --- | --- |
| **Primary** | `is_primary` — `link_tier == 'L3'` |
| L3 vs L3+L2 | drop the filter — the whole table |
| Mortality heads | require `mortality_observable` for the censoring-aware run |
| Readmission (both horizons) | `readmission_eligible`; rows with `readmission_30d is null` are ED-only |
| Censoring-aware readmission | add `followup_days_after_discharge >= 30` (or 90) |
| Boundary excluded | `not boundary_flag` |
| Unplanned readmission only | `next_admission_type not in ('ELECTIVE','SURGICAL SAME DAY ADMISSION')` |

Index time is `ecg_time`. Nothing in this table is measured after the ECG except
the outcome itself and its provenance (`days_to_death`, `days_to_readmission`),
which are labels, not features.

## Censoring

`readmission_30d` / `readmission_90d` are **nullable**, and are null exactly
when the ECG is ED-only — there is no admission to be readmitted from, so the
question does not apply. They are never null-by-inference.

§4.A.6.3 also asks to exclude rows whose censoring window cannot be observed,
"e.g., ECG too recent to the end-of-data cutoff". **MIMIC-IV has no usable
cutoff**: dates are shifted per patient, so proximity to the end of data is not
observable in the timeline the table is in. The obvious substitute — declare a
row observable when the subject's own record runs past `dischtime + horizon` —
conditions on the outcome, because a subject's record runs on precisely when
they were admitted again. Measured on the dev sample it moved the 30 d rate
from ~10 % to 29 %.

So this table uses the Phase 1 definition (an admission with a discharge time)
and carries `followup_days_after_discharge` as provenance. A censoring-aware
sensitivity is `followup_days_after_discharge >= horizon`, available without a
rebuild. The residual right-censoring is a stated limitation of the readmission
heads, not a silently corrected one.

## Transfers

A candidate next admission is treated as an intra-episode hand-off, and skipped,
when its `admission_location` starts with `TRANSFER FROM` **and** it begins
within one hour of the previous discharge. `next_admission_type` and
`next_admission_location` are kept so this choice can be audited or reversed
without rebuilding.

## Forbidden inputs

`machine_measurements`, `structured_features` (§4.A.6.4) — forbidden as model
input, permitted inside the algorithmic Cox baseline only (§4.A.6.7).

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
