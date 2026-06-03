#!/usr/bin/env python3
"""Stage 1 script 44: label availability and linkage feasibility report."""

import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import yaml
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from _stage1_common import (
    AUDIT_DIR,
    CONFIG_DIR,
    DATA_PROCESSED,
    DATA_RAW,
    EHR_CACHE,
    LINKAGE_DIR,
    setup_main_logger,
    write_parquet_atomic,
    write_text_atomic,
)

SCRIPT_NAME = Path(__file__).stem
KEY_LABS_CONFIG = CONFIG_DIR / "key_labs.yaml"
NS_PER_HOUR = 3_600_000_000_000


def load_key_labs() -> dict[str, set[int]]:
    with KEY_LABS_CONFIG.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return {name: set(int(x) for x in spec["itemids"]) for name, spec in config["key_labs"].items()}


def load_ecg_universe() -> pd.DataFrame:
    index = pd.read_parquet(DATA_PROCESSED / "index" / "ecg_metadata.parquet", columns=["study_id", "subject_id"])
    times = pd.read_csv(DATA_RAW / "record_list.csv", usecols=["study_id", "ecg_time"])
    ecg = index.merge(times, on="study_id", how="left", validate="one_to_one")
    ecg["ecg_time"] = pd.to_datetime(ecg["ecg_time"], errors="coerce")
    return ecg.sort_values("study_id").reset_index(drop=True)


def build_subject_time_lookup(labels: pd.DataFrame) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    lookup: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for subject_id, group in labels.groupby("subject_id", sort=False):
        ordered = group.sort_values("ecg_time")
        times = ordered["ecg_time"].astype("int64").to_numpy()
        row_indices = ordered.index.to_numpy()
        lookup[int(subject_id)] = (times, row_indices)
    return lookup


def mark_key_labs(labels: pd.DataFrame, key_labs: dict[str, set[int]], log) -> pd.DataFrame:
    item_to_lab = {item: lab for lab, items in key_labs.items() for item in items}
    key_itemids = set(item_to_lab)
    lookup = build_subject_time_lookup(labels)
    lab_arrays: dict[str, dict[str, np.ndarray]] = {}
    for lab in key_labs:
        lab_arrays[lab] = {
            "6h": np.zeros(len(labels), dtype=bool),
            "24h": np.zeros(len(labels), dtype=bool),
        }
    any_6h = np.zeros(len(labels), dtype=bool)
    any_24h = np.zeros(len(labels), dtype=bool)
    parquet_file = pq.ParquetFile(EHR_CACHE / "labevents.parquet")
    total_key_events = 0
    with logging_redirect_tqdm():
        for row_group in tqdm(
            range(parquet_file.num_row_groups),
            total=parquet_file.num_row_groups,
            file=None,
            dynamic_ncols=True,
            mininterval=0.5,
            desc="label-labs",
        ):
            table = parquet_file.read_row_group(row_group, columns=["subject_id", "itemid", "charttime"])
            chunk = table.to_pandas()
            chunk = chunk[chunk["itemid"].isin(key_itemids)]
            if chunk.empty:
                continue
            chunk["charttime"] = pd.to_datetime(chunk["charttime"], errors="coerce")
            chunk = chunk.dropna(subset=["charttime"])
            total_key_events += len(chunk)
            for event in chunk.itertuples(index=False):
                data = lookup.get(int(event.subject_id))
                if data is None:
                    continue
                times, row_indices = data
                t_ns = int(pd.Timestamp(event.charttime).value)
                lo24 = int(np.searchsorted(times, t_ns - 24 * NS_PER_HOUR, side="left"))
                hi24 = int(np.searchsorted(times, t_ns + 24 * NS_PER_HOUR, side="right"))
                if hi24 <= lo24:
                    continue
                lab = item_to_lab[int(event.itemid)]
                idx24 = row_indices[lo24:hi24]
                lab_arrays[lab]["24h"][idx24] = True
                any_24h[idx24] = True
                lo6 = int(np.searchsorted(times, t_ns - 6 * NS_PER_HOUR, side="left"))
                hi6 = int(np.searchsorted(times, t_ns + 6 * NS_PER_HOUR, side="right"))
                if hi6 > lo6:
                    idx6 = row_indices[lo6:hi6]
                    lab_arrays[lab]["6h"][idx6] = True
                    any_6h[idx6] = True
    for lab, windows in lab_arrays.items():
        labels[f"lab_{lab}_within_6h"] = windows["6h"]
        labels[f"lab_{lab}_within_24h"] = windows["24h"]
    labels["any_key_lab_within_6h"] = any_6h
    labels["any_key_lab_within_24h"] = any_24h
    log.info("scanned key lab events rows=%d", total_key_events)
    return labels


def attach_icd_and_risk(labels: pd.DataFrame) -> pd.DataFrame:
    hosp_diag = pd.read_parquet(EHR_CACHE / "diagnoses_icd.parquet", columns=["hadm_id"])
    ed_diag = pd.read_parquet(EHR_CACHE / "ed_diagnosis.parquet", columns=["stay_id"])
    hadm_with_icd = set(int(x) for x in hosp_diag["hadm_id"].dropna().unique())
    stay_with_icd = set(int(x) for x in ed_diag["stay_id"].dropna().unique())
    defensible = labels["link_tier"].isin(["L3", "L2"])
    labels["icd_available"] = defensible & (
        labels["hadm_id"].isin(hadm_with_icd) | labels["stay_id"].isin(stay_with_icd)
    )

    admissions = pd.read_parquet(
        EHR_CACHE / "admissions.parquet",
        columns=["subject_id", "hadm_id", "admittime", "dischtime", "deathtime", "hospital_expire_flag"],
    )
    admissions["hadm_id"] = admissions["hadm_id"].astype("Int64")
    adm = admissions.set_index("hadm_id")
    labels = labels.merge(
        adm[["admittime", "dischtime", "deathtime", "hospital_expire_flag"]],
        left_on="hadm_id",
        right_index=True,
        how="left",
    )
    patients = pd.read_parquet(EHR_CACHE / "patients.parquet", columns=["subject_id", "dod"])
    patients["dod"] = pd.to_datetime(patients["dod"], errors="coerce")
    labels = labels.merge(patients, on="subject_id", how="left")

    defensible = labels["link_tier"].isin(["L3", "L2"])
    labels["mortality_observable"] = defensible & (labels["hadm_id"].notna() | labels["dod"].notna())
    labels["in_hospital_mortality_positive"] = defensible & (
        labels["hospital_expire_flag"].fillna(0).astype(int).eq(1) | labels["deathtime"].notna()
    )
    labels["mortality_30d_positive"] = defensible & labels["dod"].notna() & (
        labels["dod"] >= labels["ecg_time"]
    ) & (labels["dod"] <= labels["ecg_time"] + pd.Timedelta(days=30))

    next_admit_by_hadm: dict[int, pd.Timestamp] = {}
    for _, group in admissions.sort_values(["subject_id", "admittime"]).groupby("subject_id", sort=False):
        hadms = group["hadm_id"].to_numpy()
        starts = group["admittime"].to_numpy()
        for i in range(len(group) - 1):
            if pd.notna(hadms[i]):
                next_admit_by_hadm[int(hadms[i])] = pd.Timestamp(starts[i + 1])
    labels["readmission_eligible"] = defensible & labels["hadm_id"].notna() & labels["dischtime"].notna()
    next_admit = labels["hadm_id"].map(lambda x: next_admit_by_hadm.get(int(x)) if pd.notna(x) else pd.NaT)
    labels["readmission_30d_positive"] = labels["readmission_eligible"] & next_admit.notna() & (
        next_admit > labels["dischtime"]
    ) & (next_admit <= labels["dischtime"] + pd.Timedelta(days=30))
    return labels


def format_pct(count: int, denom: int) -> str:
    return f"{count:,} ({(count / denom * 100 if denom else 0):.2f}%)"


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "| none |\n|---|"
    display = df.copy()
    for col in display.columns:
        display[col] = display[col].map(lambda x: "" if pd.isna(x) else str(x))
    lines = []
    headers = list(display.columns)
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in display.itertuples(index=False):
        values = [str(x).replace("|", "\\|") for x in row]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def manual_examples(labels: pd.DataFrame, log) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = [
        "study_id",
        "subject_id",
        "ecg_time",
        "link_tier",
        "source",
        "link_type",
        "hadm_id",
        "stay_id",
        "offset_minutes",
        "icd_available",
        "any_key_lab_within_24h",
    ]
    successful = labels[labels["link_tier"].isin(["L3", "L2"])].sample(
        n=min(20, int(labels["link_tier"].isin(["L3", "L2"]).sum())),
        random_state=41,
    )[cols]
    failed = labels[labels["link_tier"].isin(["L1", "L0"])].sample(
        n=min(20, int(labels["link_tier"].isin(["L1", "L0"]).sum())),
        random_state=42,
    )[cols]
    log.info("manual audit successful linkages follows")
    for row in successful.itertuples(index=False):
        log.info("manual_success study_id=%s tier=%s source=%s offset=%s", row.study_id, row.link_tier, row.source, row.offset_minutes)
    log.info("manual audit failed_or_ambiguous linkages follows")
    for row in failed.itertuples(index=False):
        log.info("manual_failed_or_ambiguous study_id=%s tier=%s source=%s offset=%s", row.study_id, row.link_tier, row.source, row.offset_minutes)
    return successful, failed


def make_report(
    labels: pd.DataFrame,
    successful: pd.DataFrame,
    failed: pd.DataFrame,
    key_labs: dict[str, set[int]],
) -> str:
    total = len(labels)
    tier_counts = labels["link_tier"].value_counts().reindex(["L3", "L2", "L1", "L0"], fill_value=0)
    icd_count = int(labels["icd_available"].sum())
    l3_l2_icd = int((labels["link_tier"].isin(["L3", "L2"]) & labels["icd_available"]).sum())
    lab24 = int(labels["any_key_lab_within_24h"].sum())
    mortality_positive = int(labels["mortality_30d_positive"].sum())
    readmit_positive = int(labels["readmission_30d_positive"].sum())
    risk_positive = max(mortality_positive, readmit_positive, int(labels["in_hospital_mortality_positive"].sum()))
    clean_linkage = int(labels["link_tier"].isin(["L3", "L2"]).sum())
    lines = [
        "# Linkage Feasibility Report - PASS",
        "",
        "## Table L1 - EHR cache row counts",
        "",
        "| Table | Rows |",
        "|---|---:|",
    ]
    for name in [
        "admissions",
        "patients",
        "diagnoses_icd",
        "d_icd_diagnoses",
        "d_labitems",
        "labevents",
        "edstays",
        "ed_diagnosis",
        "triage",
    ]:
        rows = pq.ParquetFile(EHR_CACHE / f"{name}.parquet").metadata.num_rows
        lines.append(f"| `{name}` | {rows:,} |")
    lines.extend(
        [
            "",
            "## Table L2 - Linkage tier distribution",
            "",
            "| Tier | Count | Percent of ECGs |",
            "|---|---:|---:|",
        ]
    )
    for tier, count in tier_counts.items():
        lines.append(f"| {tier} | {int(count):,} | {(int(count) / total * 100):.2f}% |")
    lines.extend(
        [
            "",
            "## Table L3 - Label availability",
            "",
            "| Label family | Count | Percent of ECGs |",
            "|---|---:|---:|",
            f"| ICD available on L3/L2 | {l3_l2_icd:,} | {l3_l2_icd / total * 100:.2f}% |",
            f"| ICD available any tier | {icd_count:,} | {icd_count / total * 100:.2f}% |",
            f"| Any key lab within +/-6h | {int(labels['any_key_lab_within_6h'].sum()):,} | {labels['any_key_lab_within_6h'].mean() * 100:.2f}% |",
            f"| Any key lab within +/-24h | {lab24:,} | {lab24 / total * 100:.2f}% |",
            f"| Mortality observable | {int(labels['mortality_observable'].sum()):,} | {labels['mortality_observable'].mean() * 100:.2f}% |",
            f"| 30d mortality positive | {mortality_positive:,} | {mortality_positive / total * 100:.2f}% |",
            f"| 30d readmission eligible | {int(labels['readmission_eligible'].sum()):,} | {labels['readmission_eligible'].mean() * 100:.2f}% |",
            f"| 30d readmission positive | {readmit_positive:,} | {readmit_positive / total * 100:.2f}% |",
            "",
            "## Table L4 - Decision threshold inputs",
            "",
            "| Threshold input | Value |",
            "|---|---:|",
            f"| Clean L3/L2 linkage | {format_pct(clean_linkage, total)} |",
            f"| L3/L2 ICD coverage | {format_pct(l3_l2_icd, total)} |",
            f"| Key lab within +/-24h | {format_pct(lab24, total)} |",
            f"| Max risk-outcome positives | {risk_positive:,} |",
            f"| Max risk-outcome prevalence | {risk_positive / total * 100:.2f}% |",
            "",
            "## Key-lab configuration",
            "",
            f"`config/key_labs.yaml` defines: {', '.join(key_labs.keys())}.",
            "",
            "## Figure L1 - Linkage tier distribution",
            "",
        ]
    )
    max_count = max(int(tier_counts.max()), 1)
    for tier, count in tier_counts.items():
        bar = "#" * max(1, int(int(count) / max_count * 50)) if count else ""
        lines.append(f"`{tier}` {bar} {int(count):,}")
    lines.extend(["", "## Manual audit examples - successful linkages", ""])
    lines.append(markdown_table(successful))
    lines.extend(["", "## Manual audit examples - failed or ambiguous linkages", ""])
    lines.append(markdown_table(failed))
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    t0 = time.time()
    log = setup_main_logger(SCRIPT_NAME)
    log.info("starting %s", SCRIPT_NAME)
    key_labs = load_key_labs()
    log.info("loaded key labs from %s names=%s", KEY_LABS_CONFIG, ",".join(key_labs.keys()))
    ecg = load_ecg_universe()
    final = pd.read_parquet(LINKAGE_DIR / "linkage_final.parquet")
    labels = ecg.merge(final.drop(columns=["subject_id", "ecg_time"]), on="study_id", how="left")
    labels["link_tier"] = labels["link_tier"].fillna("L0")
    labels = attach_icd_and_risk(labels)
    labels = mark_key_labs(labels, key_labs, log)
    successful, failed = manual_examples(labels, log)
    output_cols = [
        "study_id",
        "subject_id",
        "ecg_time",
        "link_tier",
        "source",
        "link_type",
        "hadm_id",
        "stay_id",
        "offset_minutes",
        "icd_available",
    ]
    for lab in key_labs:
        output_cols.extend(
            [
                f"lab_{lab}_within_6h",
                f"lab_{lab}_within_24h",
            ]
        )
    output_cols.extend(
        [
            "any_key_lab_within_6h",
            "any_key_lab_within_24h",
            "mortality_observable",
            "in_hospital_mortality_positive",
            "mortality_30d_positive",
            "readmission_eligible",
            "readmission_30d_positive",
        ]
    )
    labels_out = labels[output_cols].copy()
    write_parquet_atomic(labels_out, LINKAGE_DIR / "label_availability.parquet", "linkage_label_availability")
    report = make_report(labels_out, successful, failed, key_labs)
    write_text_atomic(report, AUDIT_DIR / "linkage_feasibility_report.md")
    log.info("wrote label_availability rows=%d", len(labels_out))
    log.info("wrote linkage feasibility report")
    log.info("done %s elapsed_seconds=%.1f", SCRIPT_NAME, time.time() - t0)


if __name__ == "__main__":
    main()
