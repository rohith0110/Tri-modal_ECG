"""Stage P2.1 script 03 -- A3: lab abnormality prediction (7 labs x 5 windows).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/03_build_A3_lab_abnormality.py [--dev]

Spec §4.A.3. Thirty-five 5-class heads: for each (lab, window) pair, the
abnormality status of the lab event nearest in time to the ECG.

**Prerequisite.** Reads ``data/raw/ehr_cache/labevents_key_labs.parquet``, built
by ``00b_rebuild_lab_cache.py``. The Phase 1 ``labevents.parquet`` dropped
``ref_range_lower``, ``ref_range_upper`` and ``flag`` -- the three columns
§4.A.3.3's rule branches on -- so it cannot be used here (spec §12.8.7, trap 7b).

Label rule (§4.A.3.3, precedence order, from ``lab_itemid_map_LOCKED.yaml``)::

    valuenum is null                          -> missing
    ref_range_lower is not null and v < lower -> low_abnormal
    ref_range_upper is not null and v > upper -> high_abnormal
    flag indicates abnormal                   -> abnormal_unknown_direction
    otherwise                                 -> normal

``missing`` is a real class and is never dropped: Plan A/B §5.5 asks for lab
availability to be modelled as a missingness process, and the class carries it.

How the nearest event is found. Two ``merge_asof`` passes per lab -- one
backward, one forward, both at the widest tolerance (24 h) -- give the nearest
prior and nearest subsequent event. Every one of the five windows is then a
bounds test on those two candidates, because "nearest" is monotone under
shrinking the window: the nearest event within +/-24 h that also lies within
+/-6 h *is* the nearest event within +/-6 h.

**Open question 1 (join policy), proceeding under the stated default.**
``config/lab_itemid_map_LOCKED.yaml`` sets the primary join to ``same_subject``
and makes ``same_subject AND same_hadm_id`` a required sensitivity sweep
(§4.A.3.8). Both are built: the 105 columns §4.A.3.5 specifies are the
same-subject join, and 35 ``..._label_same_hadm`` columns carry the restricted
join so the sweep is a filter rather than a rebuild. Restricting to the
admission removes candidates, so it can select a genuinely different event --
which is why it needs its own columns and cannot be recovered from a flag.
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
SCRIPT = "03_build_A3_lab_abnormality"
TASK = "A3_lab_abnormality"

LAB_EVENTS = bc.EHR_CACHE / "labevents_key_labs.parquet"
LABS = ["K", "Na", "creatinine", "troponin", "lactate", "Ca", "Mg"]
CLASSES = ["missing", "low_abnormal", "high_abnormal", "abnormal_unknown_direction", "normal"]
METHODS = ["no_event", "null_value", "ref_range", "flag"]
MAX_TOLERANCE_HOURS = 24

DICT_STR = pa.dictionary(pa.int32(), pa.string())


def load_windows() -> dict[str, tuple[float, float]]:
    cfg = yaml.safe_load((bc.CONFIG_DIR / "lab_itemid_map_LOCKED.yaml").read_text(encoding="utf-8"))
    return {
        name: (float(block["lower_hours"]), float(block["upper_hours"]))
        for name, block in cfg["windows"].items()
    }


def load_itemids() -> dict[str, list[int]]:
    cfg = yaml.safe_load((bc.CONFIG_DIR / "lab_itemid_map_LOCKED.yaml").read_text(encoding="utf-8"))
    return {lab: [int(i) for i in block["itemids"]] for lab, block in cfg["labs"].items()}


def build_schema(windows: list[str]) -> pa.Schema:
    fields = [
        ("study_id", pa.int64()),
        ("subject_id", pa.int64()),
        ("split", pa.string()),
        ("link_tier", pa.string()),
        ("sqi_tier", pa.string()),
        ("cart_id", pa.string()),
        ("boundary_flag", pa.bool_()),
        ("hadm_id", pa.int64()),
        ("ecg_time", pa.timestamp("ns")),
        ("is_primary", pa.bool_()),
    ]
    for lab in LABS:
        for window in windows:
            fields.append((f"lab_{lab}_{window}_label", DICT_STR))
            fields.append((f"lab_{lab}_{window}_signed_hours_from_ecg", pa.float32()))
            fields.append((f"lab_{lab}_{window}_abnormal_method", DICT_STR))
            fields.append((f"lab_{lab}_{window}_label_same_hadm", DICT_STR))
    return pa.schema(fields)


def classify(valuenum: np.ndarray, lower: np.ndarray, upper: np.ndarray,
             flag_abnormal: np.ndarray, present: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The §4.A.3.3 precedence, vectorised. Returns (label, abnormal_method)."""
    label = np.full(present.shape, "missing", dtype=object)
    method = np.full(present.shape, "no_event", dtype=object)

    has_value = present & np.isfinite(valuenum)
    null_value = present & ~np.isfinite(valuenum)
    method[null_value] = "null_value"          # label stays "missing"

    low = has_value & np.isfinite(lower) & (valuenum < lower)
    high = has_value & ~low & np.isfinite(upper) & (valuenum > upper)
    flagged = has_value & ~low & ~high & flag_abnormal
    normal = has_value & ~low & ~high & ~flagged

    label[low], method[low] = "low_abnormal", "ref_range"
    label[high], method[high] = "high_abnormal", "ref_range"
    label[flagged], method[flagged] = "abnormal_unknown_direction", "flag"
    label[normal], method[normal] = "normal", "ref_range"
    return label, method


def nearest_events(ecgs: pd.DataFrame, events: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Nearest prior and nearest subsequent lab event per ECG, within 24 h.

    ``by`` is ``['subject_id']`` for the primary join and
    ``['subject_id', 'hadm_id']`` for the same-admission sensitivity join.
    """
    tolerance = pd.Timedelta(hours=MAX_TOLERANCE_HOURS)
    value_cols = ["charttime", "valuenum", "ref_range_lower", "ref_range_upper", "flag_abnormal"]

    left = ecgs.sort_values("ecg_time", kind="mergesort")
    right = events.sort_values("charttime", kind="mergesort")
    out = left[["study_id"]].copy()

    for direction, tag in (("backward", "prev"), ("forward", "next")):
        merged = pd.merge_asof(
            left, right[by + value_cols], left_on="ecg_time", right_on="charttime",
            by=by, direction=direction, tolerance=tolerance, allow_exact_matches=True,
        )
        for col in value_cols:
            out[f"{tag}_{col}"] = merged[col].to_numpy()
    return out


def resolve_window(cand: pd.DataFrame, ecg_time: np.ndarray,
                   lower_h: float, upper_h: float) -> dict[str, np.ndarray]:
    """Pick whichever of the two candidates falls in [lower_h, upper_h] and is nearer."""
    hours = {}
    for tag in ("prev", "next"):
        delta = (cand[f"{tag}_charttime"].to_numpy() - ecg_time)
        hours[tag] = delta / np.timedelta64(1, "h")

    usable = {
        tag: np.isfinite(hours[tag]) & (hours[tag] >= lower_h) & (hours[tag] <= upper_h)
        for tag in ("prev", "next")
    }
    prev_dist = np.where(usable["prev"], np.abs(hours["prev"]), np.inf)
    next_dist = np.where(usable["next"], np.abs(hours["next"]), np.inf)
    take_prev = usable["prev"] & (prev_dist <= next_dist)
    take_next = usable["next"] & ~take_prev
    present = take_prev | take_next

    def pick(column: str, dtype: str) -> np.ndarray:
        prev = cand[f"prev_{column}"].to_numpy()
        nxt = cand[f"next_{column}"].to_numpy()
        return np.where(take_prev, prev, nxt).astype(dtype)

    signed = np.where(take_prev, hours["prev"], np.where(take_next, hours["next"], np.nan))
    label, method = classify(
        pick("valuenum", "float64"),
        pick("ref_range_lower", "float64"),
        pick("ref_range_upper", "float64"),
        pick("flag_abnormal", "float64") > 0.5,
        present,
    )
    return {"label": label, "method": method, "signed_hours": signed.astype("float32")}


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

    bc.preflight([LAB_EVENTS, bc.CONFIG_DIR / "lab_itemid_map_LOCKED.yaml"], need_free_gb=5.0)

    windows = load_windows()
    itemids = load_itemids()
    window_names = list(windows)
    log.info("windows: %s", windows)

    cohort = bc.load_clean_cohort(dev=args.dev)
    cohort = cohort[cohort.link_tier.isin(["L3", "L2"])].copy()
    cohort["is_primary"] = cohort.link_tier == "L3"
    log.info("L3+L2 clean cohort: %d studies", len(cohort))

    adm = pd.read_parquet(bc.EHR_CACHE / "admissions.parquet",
                          columns=["hadm_id", "admittime", "dischtime"])
    joined = cohort.merge(adm, on="hadm_id", how="left")
    window2h = pd.Timedelta(hours=2)
    cohort["boundary_flag"] = (
        ((joined.ecg_time - joined.admittime).abs() <= window2h)
        | ((joined.ecg_time - joined.dischtime).abs() <= window2h)
    ).fillna(False).to_numpy()

    ecgs = cohort[["study_id", "subject_id", "hadm_id", "ecg_time"]].copy()
    ecgs["hadm_id"] = ecgs["hadm_id"].astype("Int64")

    subjects = set(ecgs.subject_id)
    events = pd.read_parquet(
        LAB_EVENTS,
        columns=["subject_id", "hadm_id", "itemid", "charttime", "valuenum",
                 "ref_range_lower", "ref_range_upper", "flag"],
    )
    events = events[events.subject_id.isin(subjects) & events.charttime.notna()]
    events["flag_abnormal"] = (
        events["flag"].fillna("").astype(str).str.strip().str.lower() == "abnormal"
    ).astype("float64")
    events["hadm_id"] = events["hadm_id"].astype("Int64")
    log.info("lab events for cohort subjects: %d", len(events))

    ecg_time = cohort.sort_values("ecg_time", kind="mergesort")["ecg_time"].to_numpy()
    order = cohort.sort_values("ecg_time", kind="mergesort")["study_id"].to_numpy()
    reindex = pd.Series(np.arange(len(order)), index=order).reindex(cohort.study_id).to_numpy()

    out: dict[str, np.ndarray] = {}
    for lab in LABS:
        lab_events = events[events.itemid.isin(itemids[lab])]
        log.info("%s: %d events", lab, len(lab_events))
        cand_subject = nearest_events(ecgs, lab_events, ["subject_id"])
        cand_hadm = nearest_events(ecgs, lab_events, ["subject_id", "hadm_id"])
        for window in window_names:
            lower_h, upper_h = windows[window]
            primary = resolve_window(cand_subject, ecg_time, lower_h, upper_h)
            same_hadm = resolve_window(cand_hadm, ecg_time, lower_h, upper_h)
            out[f"lab_{lab}_{window}_label"] = primary["label"][reindex]
            out[f"lab_{lab}_{window}_signed_hours_from_ecg"] = primary["signed_hours"][reindex]
            out[f"lab_{lab}_{window}_abnormal_method"] = primary["method"][reindex]
            out[f"lab_{lab}_{window}_label_same_hadm"] = same_hadm["label"][reindex]
        del cand_subject, cand_hadm

    df = cohort[["study_id", "subject_id", "split", "link_tier", "sqi_tier", "cart_id",
                 "boundary_flag", "hadm_id", "ecg_time", "is_primary"]].copy()
    df["cart_id"] = df["cart_id"].astype("Int64").astype("string")
    df["hadm_id"] = df["hadm_id"].astype("Int64")
    for name, values in out.items():
        if name.endswith("_label") or name.endswith("_same_hadm"):
            df[name] = pd.Categorical(values, categories=CLASSES)
        elif name.endswith("_abnormal_method"):
            df[name] = pd.Categorical(values, categories=METHODS)
        else:
            df[name] = values
    del out
    df = df.sort_values("study_id", kind="mergesort").reset_index(drop=True)
    log.info("assembled table: %d rows x %d columns", len(df), len(df.columns))

    schema = build_schema(window_names)
    counts = bc.write_task_split_parquets(df, TASK, schema=schema)
    log.info("wrote splits: %s", counts)

    # --- validation (§9.2) ---------------------------------------------------
    primary = df[df.is_primary]
    coverage = {}
    distribution = {}
    for lab in LABS:
        col = f"lab_{lab}_pm24h_label"
        counts_lab = primary[col].value_counts()
        distribution[lab] = {
            cls: round(100 * float(counts_lab.get(cls, 0)) / max(len(primary), 1), 3)
            for cls in CLASSES
        }
        coverage[lab] = round(100 * float((primary[col] != "missing").mean()), 2)

    stats = {
        "n_rows_total": int(len(df)),
        "n_rows_primary_l3": int(len(primary)),
        "n_columns": int(len(df.columns)),
        "n_heads": len(LABS) * len(window_names),
        "splits_total": counts,
        "coverage_pm24h_pct_primary": coverage,
        "class_distribution_pm24h_primary_pct": distribution,
        "coverage_by_window_pct_primary": {
            window: {
                lab: round(
                    100 * float((primary[f"lab_{lab}_{window}_label"] != "missing").mean()), 2
                )
                for lab in LABS
            }
            for window in window_names
        },
        "same_hadm_coverage_pm24h_pct_primary": {
            lab: round(
                100 * float((primary[f"lab_{lab}_pm24h_label_same_hadm"] != "missing").mean()), 2
            )
            for lab in LABS
        },
        "abnormal_method_pm24h_primary": {
            lab: primary[f"lab_{lab}_pm24h_abnormal_method"].value_counts().to_dict()
            for lab in ("K", "troponin")
        },
    }
    stats.update(bc.split_summary(df))
    stats.update({f"primary_{k}": v for k, v in bc.split_summary(primary).items()})
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str))

    # The §4.A.3.2 step-5 gate was measured at P2.0 from label_availability;
    # re-assert it against the labels this builder actually produced.
    for lab, gate in (("Ca", 50.0), ("Mg", 50.0)):
        if coverage[lab] < gate:
            raise RuntimeError(
                f"{lab} pm24h coverage is {coverage[lab]} %, below the §4.A.3.2 step-5 gate of "
                f"{gate} % -- the 7-lab universe would have to downgrade to the 5-lab default"
            )
    if any(v == 0 for v in coverage.values()):
        raise RuntimeError(f"a lab has zero pm24h coverage: {coverage}")

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2, default=str), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# A3 -- lab abnormality prediction (7 labs x 5 windows)

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.A.3 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/03_build_A3_lab_abnormality.py`.

## Reading this table

| Analysis | Filter / columns |
| --- | --- |
| **Primary** | `is_primary` (`link_tier == 'L3'`), heads `lab_<lab>_pm24h_label` |
| L3 vs L3+L2 | drop the filter — the whole table |
| Window sweep (§4.A.3.8) | swap `pm24h` for `pre_24h` / `post_24h` / `pm6h` / `pm12h` |
| Same-hadm restriction | `lab_<lab>_<window>_label_same_hadm` |
| Per-SQI tier | `sqi_tier` |

35 heads = 7 labs x 5 windows, 5 classes each.

## Labels

Per (lab, window): the lab event nearest in time to the ECG inside the window,
classified by the §4.A.3.3 precedence. `..._signed_hours_from_ecg` is that
event's offset (negative = before the ECG), and `..._abnormal_method` records
which branch decided the label:

| method | meaning |
| --- | --- |
| `no_event` | no event in the window — label is `missing` |
| `null_value` | an event, but non-numeric `valuenum` — label is `missing` |
| `ref_range` | the row's own `ref_range_lower` / `ref_range_upper` decided it |
| `flag` | ref ranges said normal but the source `flag` said abnormal |

`locked_threshold`, the third value §4.A.3.5 anticipates, is never produced:
the rebuilt lab cache carries a reference range on 100 % of rows for every lab,
so no hard-coded threshold is needed. This matters most for troponin, whose
assay generations differ.

**`missing` is a real class**, never dropped (Plan A/B §5.5). Troponin and
lactate coverage is low by design, and that missingness is part of what the
task reports.

## Data source

`data/raw/ehr_cache/labevents_key_labs.parquet` (20,481,517 rows, 18 locked
itemids), built by `00b_rebuild_lab_cache.py`. The Phase 1 `labevents.parquet`
cannot be used: it dropped `ref_range_lower`, `ref_range_upper` and `flag`.

## Forbidden inputs

`machine_measurements`, `structured_features` (§4.A.3.4). Labs are EHR-derived,
so signal / image / text are all legitimate inputs.

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
