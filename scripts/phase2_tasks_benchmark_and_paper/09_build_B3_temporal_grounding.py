"""Stage P2.2 script 09 -- B3: temporal grounding (10-bin queries).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/09_build_B3_temporal_grounding.py [--dev]

Spec §4.B.3. Four physiological queries, each answered per 1-second bin of the
10-second strip. One row per (study, query); ``labels`` is 10 binary values.

Evidence comes from ``data/processed/fiducials_lead2.parquet``
(``00_extract_fiducials.py``) -- the same file A4 uses, so B3's bin labels and
A4's event labels are derived from one delineation and cannot disagree.

Query rules (§4.B.3.3)::

    HIGH_HEART_RATE  bin = 1 if any RR midpoint in the bin has instantaneous
                     HR > 100 bpm
    LOW_HEART_RATE   bin = 1 if any RR midpoint in the bin has HR < 60 bpm
    WIDE_QRS         bin = 1 if any beat whose QRS onset falls in the bin has
                     duration > 60 samples (120 ms)
    NOISY_SEGMENT    bin = 1 if that bin's SQI < the locked threshold

Instantaneous HR for the RR interval between consecutive peaks at 500 Hz is
``30000 / (p[i+1] - p[i])`` bpm, credited to the bin holding the interval's
midpoint. "Any" resolves the spec's silence about bins containing several
midpoints, and matches ``WIDE_QRS``'s own "any beat" wording.

**The NOISY_SEGMENT threshold is locked from the TRAIN split only** (§4.B.3.3:
"compute per-bin SQI distribution on train, pick the 25th percentile ... Doc
mandates threshold from train only"). This builder computes it, writes it back
into ``config/task_definitions.yaml``, and never recomputes it once the file
carries a value -- pass ``--relock-threshold`` to deliberately recompute.

Per-bin SQI is ``sqi_per_bin`` from the fiducial file, computed there on exactly
Phase 1's SQI code path (clean, re-detect, ``ecg_quality(method="averageQRS")``),
so a bin's value sits on the same scale as ``waveform_qc.sqi_aggregate``.
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

STAGE = "P2.2"
SCRIPT = "09_build_B3_temporal_grounding"
TASK = "B3_temporal_grounding"

FIDUCIALS = bc.DATA_PROCESSED / "fiducials_lead2.parquet"
QUERIES = ("HIGH_HEART_RATE", "LOW_HEART_RATE", "WIDE_QRS", "NOISY_SEGMENT")

FS = 500
N_BINS = 10
BIN_SAMPLES = 500
HIGH_HR_BPM = 100.0
LOW_HR_BPM = 60.0
WIDE_QRS_SAMPLES = 60          # 120 ms at 500 Hz
NOISY_PERCENTILE = 25

SCHEMA = pa.schema([
    ("study_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("split", pa.string()),
    ("link_tier", pa.string()),
    ("sqi_tier", pa.string()),
    ("cart_id", pa.string()),
    ("query", pa.string()),
    ("labels", pa.list_(pa.int8())),
    ("fallback_used", pa.bool_()),
    ("n_positive_bins", pa.int8()),
])


def per_study_labels(r_peaks: np.ndarray, onsets: np.ndarray, offsets: np.ndarray,
                     sqi_bins: np.ndarray, noisy_threshold: float) -> dict[str, np.ndarray]:
    """The four 10-bin label vectors for one study."""
    high = np.zeros(N_BINS, dtype="int8")
    low = np.zeros(N_BINS, dtype="int8")
    wide = np.zeros(N_BINS, dtype="int8")

    peaks = np.asarray(r_peaks, dtype="int64")
    if peaks.size >= 2:
        deltas = np.diff(peaks)
        valid = deltas > 0
        if valid.any():
            midpoints = ((peaks[:-1] + peaks[1:]) // 2)[valid]
            hr = 30000.0 / deltas[valid]
            bins = np.clip(midpoints // BIN_SAMPLES, 0, N_BINS - 1)
            high[np.unique(bins[hr > HIGH_HR_BPM])] = 1
            low[np.unique(bins[hr < LOW_HR_BPM])] = 1

    on = np.asarray(onsets, dtype="int64")
    off = np.asarray(offsets, dtype="int64")
    if on.size and off.size:
        usable = (on >= 0) & (off >= 0) & (off > on)
        if usable.any():
            duration = off[usable] - on[usable]
            onset_bin = np.clip(on[usable] // BIN_SAMPLES, 0, N_BINS - 1)
            wide[np.unique(onset_bin[duration > WIDE_QRS_SAMPLES])] = 1

    sqi = np.asarray(sqi_bins, dtype="float64")
    noisy = (sqi < noisy_threshold).astype("int8")
    return {"HIGH_HEART_RATE": high, "LOW_HEART_RATE": low,
            "WIDE_QRS": wide, "NOISY_SEGMENT": noisy}


def lock_threshold(value: float, log) -> None:
    """Write the NOISY_SEGMENT threshold back into task_definitions.yaml."""
    path = bc.CONFIG_DIR / "task_definitions.yaml"
    text = path.read_text(encoding="utf-8")
    marker = "      noisy_sqi_threshold:\n        value: "
    start = text.index(marker) + len(marker)
    end = text.index("\n", start)
    updated = text[:start] + f"{value:.6f}" + text[end:]
    updated = updated.replace(
        '        status: "TO BE LOCKED by 09_build_B3_temporal_grounding.py at Stage P2.2"',
        f'        status: "LOCKED {bc.utc_now_iso()} by 09_build_B3_temporal_grounding.py '
        f'(train split, {NOISY_PERCENTILE}th percentile)"',
    )
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(updated, encoding="utf-8")
    bc.atomic_replace(tmp, path)
    log.info("locked noisy_sqi_threshold = %.6f into config/task_definitions.yaml", value)


def read_locked_threshold() -> float | None:
    cfg = yaml.safe_load((bc.CONFIG_DIR / "task_definitions.yaml").read_text(encoding="utf-8"))
    value = cfg["tasks"]["B3_temporal_grounding"]["targets"]["noisy_sqi_threshold"]["value"]
    return None if value is None else float(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    bc.add_std_args(parser)
    parser.add_argument("--relock-threshold", action="store_true",
                        help="recompute the NOISY_SEGMENT threshold even if one is locked")
    args = parser.parse_args()
    bc.set_dev(args.dev)

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT + ("_dev" if args.dev else ""))
    if state.done and not args.force:
        log.info("already complete (%s rows) -- pass --force to rebuild", state.data.get("n_rows"))
        return 0
    state.reset()
    started = time.time()

    fiducials = FIDUCIALS.with_name("fiducials_lead2_dev.parquet") if args.dev else FIDUCIALS
    bc.preflight([fiducials, bc.CONFIG_DIR / "task_definitions.yaml"])

    cohort = bc.load_clean_cohort(dev=args.dev)
    fid = pd.read_parquet(fiducials)
    df = cohort.merge(fid, on="study_id", how="inner", validate="many_to_one")
    if len(df) != len(cohort):
        raise RuntimeError(
            f"{len(cohort) - len(df)} clean-cohort studies have no fiducial row -- "
            "re-run 00_extract_fiducials.py before building B3"
        )
    log.info("cohort: %d studies", len(df))

    # --- the NOISY_SEGMENT threshold, from TRAIN only ------------------------
    locked = read_locked_threshold()
    train_bins = np.concatenate(
        df.loc[df.split == "train", "sqi_per_bin"].map(np.asarray).to_numpy()
    )
    measured = float(np.percentile(train_bins, NOISY_PERCENTILE))
    if locked is None or args.relock_threshold:
        threshold = measured
        if not args.dev:
            lock_threshold(threshold, log)
        else:
            log.info("dev run: threshold %.6f computed but NOT locked into the config", threshold)
    else:
        threshold = locked
        log.info("using the locked threshold %.6f (train-split value now measures %.6f)",
                 threshold, measured)

    # --- labels --------------------------------------------------------------
    peaks = df.r_peaks_lead2.to_numpy()
    onsets = df.qrs_onsets_lead2.to_numpy()
    offsets = df.qrs_offsets_lead2.to_numpy()
    sqi = df.sqi_per_bin.to_numpy()
    label_lists: dict[str, list[np.ndarray]] = {q: [] for q in QUERIES}
    for i in range(len(df)):
        out = per_study_labels(peaks[i], onsets[i], offsets[i], sqi[i], threshold)
        for query in QUERIES:
            label_lists[query].append(out[query])

    base = df[["study_id", "subject_id", "split", "link_tier", "sqi_tier", "cart_id",
               "fallback_used"]].copy()
    base["cart_id"] = base["cart_id"].astype("Int64").astype("string")

    frames = []
    for query in QUERIES:
        part = base.copy()
        part["query"] = query
        part["labels"] = label_lists[query]
        part["n_positive_bins"] = np.asarray(
            [int(v.sum()) for v in label_lists[query]], dtype="int8"
        )
        frames.append(part)
    out = pd.concat(frames, ignore_index=True).sort_values(
        ["study_id", "query"], kind="mergesort"
    ).reset_index(drop=True)

    counts = bc.write_task_split_parquets(out, TASK, schema=SCHEMA)
    log.info("wrote splits: %s", counts)

    # --- validation (§9.2) ---------------------------------------------------
    per_query = {}
    for query in QUERIES:
        part = out[out["query"] == query]
        positives = np.concatenate(part.labels.map(np.asarray).to_numpy())
        per_query[query] = {
            "n_rows": int(len(part)),
            "bin_positive_rate_pct": round(100 * float(positives.mean()), 3),
            "studies_with_any_positive_pct": round(
                100 * float((part.n_positive_bins > 0).mean()), 3
            ),
            "mean_positive_bins": round(float(part.n_positive_bins.mean()), 3),
        }

    stats = {
        "n_rows_total": int(len(out)),
        "n_studies": int(out.study_id.nunique()),
        "splits_total": counts,
        "n_queries": len(QUERIES),
        "noisy_sqi_threshold": round(threshold, 6),
        "noisy_threshold_source": "train split, %dth percentile" % NOISY_PERCENTILE,
        "noisy_threshold_was_already_locked": locked is not None and not args.relock_threshold,
        "train_sqi_bin_percentiles": {
            str(p): round(float(np.percentile(train_bins, p)), 4) for p in (5, 25, 50, 75, 95)
        },
        "per_query": per_query,
        "pct_fallback_used": round(100 * float(base.fallback_used.mean()), 3),
    }
    stats.update(bc.split_summary(out))
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str))

    noisy_rate = per_query["NOISY_SEGMENT"]["bin_positive_rate_pct"]
    if not 15.0 <= noisy_rate <= 40.0:
        raise RuntimeError(
            f"NOISY_SEGMENT fires on {noisy_rate} % of bins; a {NOISY_PERCENTILE}th-percentile "
            "train threshold should put it near 25 % -- the threshold or the SQI is wrong"
        )
    if any(len(v) != N_BINS for v in out.labels.head(5000)):
        raise RuntimeError("a labels vector is not 10 bins long")

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2, default=str), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# B3 -- temporal grounding (10-bin queries)

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.B.3 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/09_build_B3_temporal_grounding.py`.

One row per (study, query); `labels` is 10 binary values, one per 1-second bin.
Four queries x the full clean cohort.

| query | bin = 1 when |
| --- | --- |
| `HIGH_HEART_RATE` | any RR midpoint in the bin has instantaneous HR > 100 bpm |
| `LOW_HEART_RATE` | any RR midpoint in the bin has HR < 60 bpm |
| `WIDE_QRS` | any beat whose QRS **onset** is in the bin lasts > 60 samples (120 ms) |
| `NOISY_SEGMENT` | that bin's SQI is below the locked threshold |

Instantaneous HR for the interval between consecutive peaks is `30000 / dRR`
bpm at 500 Hz, credited to the bin holding the interval's midpoint.

## The NOISY_SEGMENT threshold comes from train only

§4.B.3.3 requires it: the 25th percentile of the per-bin SQI distribution on the
**train split**, locked into `config/task_definitions.yaml` and never
recomputed. The value used is in the statistics below. `--relock-threshold`
recomputes it deliberately; a `--dev` run never writes it.

Per-bin SQI comes from `sqi_per_bin` in `fiducials_lead2.parquet`, computed on
exactly Phase 1's SQI code path, so a bin value is on the same scale as
`waveform_qc.sqi_aggregate`.

## Shared evidence with A4

Both tasks read the same `fiducials_lead2.parquet`, so B3's bin labels and A4's
event positions come from one delineation and cannot disagree.
`fallback_used` marks the studies where R-peak detection failed — the queries
then rest on SQI alone.

## Forbidden inputs

`machine_measurements`, `structured_features`, `report_text`, every image kind
(§4.B.3.4) — aggregate timings summarise the same quantities the bins encode.

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
