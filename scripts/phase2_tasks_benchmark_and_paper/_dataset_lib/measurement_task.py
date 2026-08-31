"""The A2 / B1 / B2 measurement-bin table -- one definition, three consumers.

§4.A.2.3 defines the HR / QRS / QTc bins; §4.B.1.3 says "identical to §4.A.2.3";
§4.B.2.3 says the B2 anchors inherit their B1 labels unchanged. A2 and B1 differ
only in cohort scope (A2 = L3 x {high,medium} SQI, B1 = the full clean cohort),
so the labels are computed once here and each builder filters and writes.

Every threshold reads the MACHINE measurement, sentinel-masked (spec §12.8.1-2,
Round 6.1). ``qtc_ms`` is ``machine_qtc_ms``; ``qtc_ms_bazett`` is the NeuroKit2
value, carried as provenance and as the §4.A.2.8 sensitivity row only.
"""

from __future__ import annotations

import pandas as pd
import pyarrow as pa

from . import build_common as bc

HEADS = ("hr_label", "qrs_label", "qtc_label")
CLASSES = {
    "hr_label": ["bradycardia", "normal", "tachycardia"],
    "qrs_label": ["normal", "borderline", "wide"],
    "qtc_label": ["short", "normal", "prolonged"],
}

SCHEMA = pa.schema([
    ("study_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("split", pa.string()),
    ("link_tier", pa.string()),
    ("sqi_tier", pa.string()),
    ("cart_id", pa.string()),
    ("hr_bpm", pa.float32()),
    ("qrs_ms", pa.float32()),
    ("qtc_ms", pa.float32()),
    ("qtc_ms_bazett", pa.float32()),      # provenance / sensitivity only
    ("hr_label", pa.string()),
    ("qrs_label", pa.string()),
    ("qtc_label", pa.string()),
    ("is_primary", pa.bool_()),
])


def measurement_table(dev: bool = False) -> pd.DataFrame:
    """Full clean cohort with the three bins attached and invalid rows dropped.

    A row survives only when all three measurements are valid: the task is
    "predict all three bins", and a row missing one head has no label for it.
    ``is_primary`` is left for the caller to set -- the two tasks disagree on
    what primary means.
    """
    cohort = bc.load_clean_cohort(dev=dev)
    meas = bc.machine_measurements(dev=dev)
    df = cohort.merge(meas, on="study_id", how="left", validate="many_to_one")

    valid = df.hr_bpm_valid.fillna(False) & df.qrs_ms_valid.fillna(False) & df.qtc_ms_valid.fillna(False)
    df = df[valid].copy()

    df["hr_label"] = bc.hr_label(df.hr_bpm)
    df["qrs_label"] = bc.qrs_label(df.qrs_ms)
    df["qtc_label"] = bc.qtc_label(df.qtc_ms)
    df["cart_id"] = df["cart_id"].astype("Int64").astype("string")
    for col in ("hr_bpm", "qrs_ms", "qtc_ms", "qtc_ms_bazett"):
        df[col] = df[col].astype("float32")
    return df.sort_values("study_id", kind="mergesort").reset_index(drop=True)


def label_stats(df: pd.DataFrame) -> dict:
    """Per-head class distribution, overall and per split."""
    out: dict = {}
    for head in HEADS:
        counts = df[head].value_counts()
        out[head] = {
            cls: {"n": int(counts.get(cls, 0)),
                  "pct": round(100 * float(counts.get(cls, 0)) / max(len(df), 1), 3)}
            for cls in CLASSES[head]
        }
        out[f"{head}_by_split"] = {
            split: {
                cls: round(
                    100 * float((df[df.split == split][head] == cls).mean()) if
                    len(df[df.split == split]) else 0.0, 3
                )
                for cls in CLASSES[head]
            }
            for split in bc.SPLITS
        }
    return out
