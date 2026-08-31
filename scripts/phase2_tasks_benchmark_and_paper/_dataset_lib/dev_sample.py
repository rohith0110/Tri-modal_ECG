"""Build the fixed 5,000-study development sample (spec §8.2.1).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/dev_sample.py

The laptop authors and smoke-tests every Phase 2 script against this sample so a
builder runs in minutes instead of hours; it trains nothing that reaches the
paper. The sample is a **pointer table only** -- study ids plus the cohort flags
a builder filters on. Modality bytes still resolve through
``read_modality``, so a script exercised on the sample takes the exact code path
it will take at full scale on the DGX.

Determinism: the row set is a pure function of the Phase 1 artifacts and
``SEED``. Re-running overwrites the file with identical content.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
OUT_DIR = DATA_PROCESSED / "dev_sample"
OUT_PATH = OUT_DIR / "dev_sample_studies.parquet"

SEED = 2026
N_STUDIES = 5_000
N_B2_ANCHORS = 100     # force-included so B2 has corrupted variants to smoke-test
N_SQI_HIGH_FLOOR = 300  # force-included so A2/A4 have a workable high-SQI cohort

# Why the floor: sqi_tier == "high" is only 0.56 % of the clean cohort (4,166 of
# 749,112 studies), so proportional sampling yields ~28 high-SQI rows -- too few
# to exercise A2's primary cohort (sqi high) or A4's (sqi high+medium) at all.
# The boosted rows carry `is_sqi_high_boost = True`. THE SAMPLE IS THEREFORE NOT
# A PREVALENCE ESTIMATE: drop the boosted and anchor rows before reading any
# class balance off it. Real prevalence lands in cohort_audit.md at Stage P2.3.


def build() -> pd.DataFrame:
    meta = pd.read_parquet(
        DATA_PROCESSED / "index" / "ecg_metadata_clean_with_measurements.parquet",
        columns=["study_id", "subject_id", "split", "link_tier", "cart_id", "hr_bucket"],
    )
    qc = pd.read_parquet(
        DATA_PROCESSED / "waveform_qc.parquet",
        columns=["study_id", "sqi_tier", "decode_ok", "length_ok", "text_ok",
                 "image_clean_ok", "image_scanlike_ok"],
    )
    avail = pd.read_parquet(
        DATA_PROCESSED / "linkage" / "label_availability.parquet",
        columns=["study_id", "hadm_id", "icd_available", "any_key_lab_within_24h",
                 "mortality_observable", "readmission_eligible"],
    )

    df = meta.merge(qc, on="study_id", how="left", validate="many_to_one").merge(avail, on="study_id", how="left", validate="many_to_one")
    df = df[df.decode_ok.fillna(False) & df.length_ok.fillna(False)]

    # Stratify on (split, link_tier, sqi_tier) so the sample is a fair miniature
    # of the clean cohort: the 70/10/20 ratio, the linkage mix that decides which
    # tasks are exercisable, and the SQI mix the sensitivity tables slice on.
    df["stratum"] = (
        df.split.astype(str) + "|" + df.link_tier.astype(str) + "|" + df.sqi_tier.astype(str)
    )

    corrupted_anchors = pd.read_parquet(
        DATA_PROCESSED / "signals_corrupted.parquet", columns=["study_id"]
    ).study_id.drop_duplicates()
    anchors = (
        df[df.study_id.isin(corrupted_anchors)]
        .sort_values("study_id", kind="mergesort")
        .head(N_B2_ANCHORS)
    )

    boost = (
        df[(df.sqi_tier == "high") & ~df.study_id.isin(anchors.study_id)]
        .sort_values("study_id", kind="mergesort")
        .head(N_SQI_HIGH_FLOOR)
    )

    forced = pd.concat([anchors, boost], ignore_index=True)
    remaining = N_STUDIES - len(forced)
    pool = df[~df.study_id.isin(forced.study_id)]

    rng = np.random.default_rng(SEED)
    sizes = pool.stratum.value_counts()
    quota = (sizes / sizes.sum() * remaining).round().astype(int)
    # Largest-remainder correction so the quotas sum to exactly `remaining`.
    while quota.sum() != remaining:
        step = 1 if quota.sum() < remaining else -1
        for key in sizes.index:
            if quota.sum() == remaining:
                break
            if step == -1 and quota[key] <= 0:
                continue
            quota[key] += step

    picks = []
    for stratum, n in quota.items():
        if n <= 0:
            continue
        group = pool[pool.stratum == stratum].sort_values("study_id", kind="mergesort")
        take = min(n, len(group))
        idx = rng.choice(len(group), size=take, replace=False)
        picks.append(group.iloc[np.sort(idx)])

    sample = pd.concat([forced, *picks], ignore_index=True)
    sample["is_b2_anchor"] = sample.study_id.isin(anchors.study_id)
    sample["is_sqi_high_boost"] = sample.study_id.isin(boost.study_id)
    sample = sample.sort_values("study_id", kind="mergesort").reset_index(drop=True)
    return sample.drop(columns=["stratum"])


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sample = build()

    assert len(sample) == N_STUDIES, f"built {len(sample)} rows, expected {N_STUDIES}"
    assert sample.study_id.is_unique, "duplicate study_id"
    assert set(sample.split) == {"train", "val", "test"}, sorted(set(sample.split))
    assert sample.is_b2_anchor.sum() == N_B2_ANCHORS, "B2 anchors missing"
    assert sample.is_sqi_high_boost.sum() == N_SQI_HIGH_FLOOR, "high-SQI floor missing"
    assert not (sample.is_b2_anchor & sample.is_sqi_high_boost).any(), "forced sets overlap"
    # A subject must never appear under two splits -- the sample inherits the
    # global split and never re-derives it (§4.C invariant 1).
    per_subject = sample.groupby("subject_id").split.nunique()
    assert per_subject.max() == 1, "a subject appears under more than one split"

    tmp = OUT_PATH.with_suffix(".parquet.tmp")
    sample.to_parquet(tmp, index=False)
    tmp.replace(OUT_PATH)

    print(f"wrote {OUT_PATH.relative_to(PROJECT_ROOT)}  ({len(sample):,} studies)")
    print(f"  subjects            {sample.subject_id.nunique():,}")
    print(f"  split               {sample.split.value_counts().to_dict()}")
    print(f"  link_tier           {sample.link_tier.value_counts().to_dict()}")
    print(f"  sqi_tier            {sample.sqi_tier.value_counts().to_dict()}")
    print(f"  B2 anchors          {int(sample.is_b2_anchor.sum())}")
    print(f"  high-SQI boost      {int(sample.is_sqi_high_boost.sum())}"
          f"  (sample is enriched; not a prevalence estimate)")
    print(f"  icd_available       {int(sample.icd_available.fillna(False).sum()):,}")
    print(f"  key lab +/-24 h     {int(sample.any_key_lab_within_24h.fillna(False).sum()):,}")
    print(f"  mortality_observable {int(sample.mortality_observable.fillna(False).sum()):,}")
    print(f"  text_ok             {int(sample.text_ok.fillna(False).sum()):,}")


if __name__ == "__main__":
    main()
