#!/usr/bin/env python3
"""Stage 1 script 45: freeze Plan A / Hybrid / Plan B decision."""

import os
import time
from pathlib import Path

import pandas as pd
import yaml

from _stage1_common import CONFIG_DIR, LINKAGE_DIR, relative, setup_main_logger, utc_now_iso

SCRIPT_NAME = Path(__file__).stem
DECISION_FILE = CONFIG_DIR / "decision.yaml"
KEY_LABS_CONFIG = CONFIG_DIR / "key_labs.yaml"


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def main() -> None:
    t0 = time.time()
    log = setup_main_logger(SCRIPT_NAME)
    log.info("starting %s", SCRIPT_NAME)
    labels = pd.read_parquet(LINKAGE_DIR / "label_availability.parquet")
    total = len(labels)
    tier_counts = labels["link_tier"].value_counts().reindex(["L3", "L2", "L1", "L0"], fill_value=0)
    clean_linkage_count = int(labels["link_tier"].isin(["L3", "L2"]).sum())
    l3_l2_icd_count = int((labels["link_tier"].isin(["L3", "L2"]) & labels["icd_available"]).sum())
    key_lab_24h_count = int(labels["any_key_lab_within_24h"].sum())
    risk_positive_count = max(
        int(labels["in_hospital_mortality_positive"].sum()),
        int(labels["mortality_30d_positive"].sum()),
        int(labels["readmission_30d_positive"].sum()),
    )
    clean_linkage_pct = clean_linkage_count / total
    l3_l2_icd_pct = l3_l2_icd_count / total
    key_lab_24h_pct = key_lab_24h_count / total
    risk_positive_pct = risk_positive_count / total
    with KEY_LABS_CONFIG.open("r", encoding="utf-8") as f:
        key_labs = yaml.safe_load(f)["key_labs"]

    threshold_pass = {
        "clean_linkage_ge_30pct": clean_linkage_pct >= 0.30,
        "plan_a_icd_ge_40pct": l3_l2_icd_pct >= 0.40,
        "plan_a_key_lab_24h_ge_20pct": key_lab_24h_pct >= 0.20,
        "plan_a_risk_outcome_ge_1000_or_ge_1pct": risk_positive_count >= 1000 or risk_positive_pct >= 0.01,
    }
    if (
        threshold_pass["plan_a_icd_ge_40pct"]
        and threshold_pass["plan_a_key_lab_24h_ge_20pct"]
        and threshold_pass["plan_a_risk_outcome_ge_1000_or_ge_1pct"]
    ):
        chosen_path = "plan_a"
    elif clean_linkage_pct < 0.30:
        chosen_path = "plan_b"
    else:
        chosen_path = "hybrid"

    lines = [
        "# Stage 1 EHR linkage decision gate",
        f'frozen_at: "{utc_now_iso()}"',
        f'chosen_path: "{chosen_path}"',
        "threshold_pass:",
    ]
    for key, value in threshold_pass.items():
        lines.append(f"  {key}: {bool_text(value)}")
    lines.extend(
        [
            "threshold_values:",
            f"  total_ecgs: {total}",
            f"  clean_linkage_count: {clean_linkage_count}",
            f"  clean_linkage_pct: {clean_linkage_pct:.8f}",
            f"  l3_l2_icd_count: {l3_l2_icd_count}",
            f"  l3_l2_icd_pct: {l3_l2_icd_pct:.8f}",
            f"  key_lab_24h_count: {key_lab_24h_count}",
            f"  key_lab_24h_pct: {key_lab_24h_pct:.8f}",
            f"  risk_positive_count: {risk_positive_count}",
            f"  risk_positive_pct: {risk_positive_pct:.8f}",
            "linkage_distribution:",
        ]
    )
    for tier, count in tier_counts.items():
        lines.append(f"  {tier}: {int(count)}")
    lines.append("key_labs:")
    lines.append(f'  config_path: "{relative(KEY_LABS_CONFIG)}"')
    for name, spec in key_labs.items():
        itemids = ", ".join(str(int(x)) for x in spec["itemids"])
        lines.append(f"  {name}: [{itemids}]")
    tmp_path = DECISION_FILE.with_suffix(".yaml.tmp")
    tmp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp_path, DECISION_FILE)
    log.info("decision chosen_path=%s", chosen_path)
    log.info("threshold clean_linkage_pct=%.4f", clean_linkage_pct)
    log.info("threshold l3_l2_icd_pct=%.4f", l3_l2_icd_pct)
    log.info("threshold key_lab_24h_pct=%.4f", key_lab_24h_pct)
    log.info("threshold risk_positive_count=%d risk_positive_pct=%.4f", risk_positive_count, risk_positive_pct)
    log.info("wrote %s", DECISION_FILE)
    log.info("done %s elapsed_seconds=%.1f", SCRIPT_NAME, time.time() - t0)


if __name__ == "__main__":
    main()
