"""Stage P2.1 script 04 -- A4: temporal / waveform event localization.

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/04_build_A4_event_localization.py [--dev]

Spec §4.A.4. Predict R-peak sample positions and QRS onset/offset spans inside
the 10-second Lead-II strip. Ground truth comes from
``data/processed/fiducials_lead2.parquet``, written by ``00_extract_fiducials.py``
-- run that first.

Cohort (§4.A.4.2). Primary is ``link_tier == 'L3'`` and
``sqi_tier in {high, medium}`` and usable ground truth; the sensitivity cohort is
the full clean cohort regardless of link tier. Both are in this one table, with
``is_primary`` marking the primary.

**No dense masks are materialised.** §4.A.4.5 lists ``r_peak_mask`` and
``qrs_mask`` as ``list<bool>`` of length 5000, but the §4.A.4.3 correction that
created this task's ground truth supersedes it: "the arrays are stored sparse
(peak positions), not as dense 5000-sample masks ... The dataloader expands to a
dense mask at batch time. Same information, no science change." Dense masks
would cost about 2.3 GB for the A4 cohort and 3.7 GB for the full clean cohort
against ~190 MB sparse. The expansion rule is fixed and recorded in the README
so every consumer builds the same mask: True within +/-5 samples of an R-peak
(the +/-10 ms tolerance at 500 Hz), and True inside any onset-offset span.

``qrs_onsets_lead2`` / ``qrs_offsets_lead2`` are aligned one-to-one with
``r_peaks_lead2`` and carry ``-1`` where delineation gave no usable boundary for
that beat, so a per-beat model never has to guess which onset belongs to which
peak.
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
SCRIPT = "04_build_A4_event_localization"
TASK = "A4_event_localization"

FIDUCIALS = bc.DATA_PROCESSED / "fiducials_lead2.parquet"
PRIMARY_SQI = ("high", "medium")
TOLERANCE_SAMPLES = 5      # +/-10 ms at 500 Hz (§4.A.4.3)
FS = 500
N_SAMPLES = 5000

SCHEMA = pa.schema([
    ("study_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("split", pa.string()),
    ("link_tier", pa.string()),
    ("sqi_tier", pa.string()),
    ("cart_id", pa.string()),
    ("r_peaks_lead2", pa.list_(pa.int32())),
    ("qrs_onsets_lead2", pa.list_(pa.int32())),
    ("qrs_offsets_lead2", pa.list_(pa.int32())),
    ("n_peaks", pa.int32()),
    ("n_qrs_spans", pa.int32()),
    ("fallback_used", pa.bool_()),
    ("delineate_ok", pa.bool_()),
    ("is_primary", pa.bool_()),
])


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

    fiducials = FIDUCIALS.with_name("fiducials_lead2_dev.parquet") if args.dev else FIDUCIALS
    bc.preflight([fiducials])

    cohort = bc.load_clean_cohort(dev=args.dev)
    fid = pd.read_parquet(fiducials)
    log.info("cohort %d studies, fiducials %d rows", len(cohort), len(fid))

    df = cohort.merge(fid, on="study_id", how="inner")
    if len(df) != len(cohort):
        missing = len(cohort) - len(df)
        raise RuntimeError(
            f"{missing} clean-cohort studies have no fiducial row -- "
            f"re-run 00_extract_fiducials.py before building A4"
        )

    df["n_qrs_spans"] = df["qrs_onsets_lead2"].map(lambda a: int((np.asarray(a) >= 0).sum()))
    df["is_primary"] = (
        (df.link_tier == "L3")
        & df.sqi_tier.isin(PRIMARY_SQI)
        & ~df.fallback_used            # "ground-truth R-peaks exist" (§4.A.4.2)
    )
    df["cart_id"] = df["cart_id"].astype("Int64").astype("string")
    df = df.sort_values("study_id", kind="mergesort").reset_index(drop=True)

    counts = bc.write_task_split_parquets(df, TASK, schema=SCHEMA)
    log.info("wrote splits: %s", counts)

    primary = df[df.is_primary]
    spans = np.concatenate([
        (np.asarray(off)[np.asarray(off) >= 0] - np.asarray(on)[np.asarray(on) >= 0])
        for on, off in zip(primary.qrs_onsets_lead2.head(50000), primary.qrs_offsets_lead2.head(50000))
    ]) if len(primary) else np.array([0])

    stats = {
        "n_rows_total": int(len(df)),
        "n_rows_primary": int(len(primary)),
        "splits_total": counts,
        "n_fallback_used_total": int(df.fallback_used.sum()),
        "pct_fallback_used_total": round(100 * float(df.fallback_used.mean()), 3),
        "pct_delineate_ok_total": round(100 * float(df.delineate_ok.mean()), 3),
        "n_peaks_mean_primary": round(float(primary.n_peaks.mean()), 2),
        "n_peaks_median_primary": int(primary.n_peaks.median()),
        "n_qrs_spans_mean_primary": round(float(primary.n_qrs_spans.mean()), 2),
        "pct_beats_with_qrs_span_primary": round(
            100 * float(primary.n_qrs_spans.sum()) / max(int(primary.n_peaks.sum()), 1), 2
        ),
        "qrs_span_ms_median": round(float(np.median(spans)) * 1000.0 / FS, 2),
        "qrs_span_ms_p05": round(float(np.percentile(spans, 5)) * 1000.0 / FS, 2),
        "qrs_span_ms_p95": round(float(np.percentile(spans, 95)) * 1000.0 / FS, 2),
        "sqi_breakdown_primary": primary.sqi_tier.value_counts().to_dict(),
        "tolerance_samples": TOLERANCE_SAMPLES,
        "dense_masks_materialised": False,
    }
    stats.update(bc.split_summary(df))
    stats.update({f"primary_{k}": v for k, v in bc.split_summary(primary).items()})
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str))

    if stats["n_rows_primary"] == 0:
        raise RuntimeError("A4 primary cohort is empty")
    if not 40 <= stats["qrs_span_ms_median"] <= 140:
        raise RuntimeError(
            f"median QRS span is {stats['qrs_span_ms_median']} ms, outside anything "
            "physiological -- the delineation output is misaligned"
        )
    bad = int(primary.r_peaks_lead2.map(
        lambda a: bool(len(a)) and (min(a) < 0 or max(a) >= N_SAMPLES)
    ).sum())
    if bad:
        raise RuntimeError(f"{bad} primary rows carry an R-peak outside [0, {N_SAMPLES})")

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2, default=str), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# A4 -- temporal / waveform event localization (R-peaks + QRS bounds)

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.A.4 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/04_build_A4_event_localization.py`.

## Reading this table

| Analysis | Filter |
| --- | --- |
| **Primary** | `is_primary` — `link_tier == 'L3' and sqi_tier in ('high','medium') and not fallback_used` |
| Full-clean-cohort sensitivity | drop the filter — the whole table |
| Per-SQI tier | `sqi_tier` |

## Ground truth

`data/processed/fiducials_lead2.parquet`, from `00_extract_fiducials.py`, which
reuses the **corrected** Phase 1 detector path verbatim: `ecg_peaks` with
`method="neurokit"` on the uncleaned preprocessed Lead II, then `ecg_delineate`
with `method="dwt"`, `check=False`. The Pan-Tompkins bug fixed during the Phase 1
regen is not reintroduced.

`qrs_onsets_lead2[i]` and `qrs_offsets_lead2[i]` belong to `r_peaks_lead2[i]`.
A value of `-1` means delineation produced no usable boundary for that beat;
`n_qrs_spans` counts the beats that do have one.

## Masks are expanded at batch time, not stored

§4.A.4.5 lists dense `r_peak_mask` and `qrs_mask` columns; the §4.A.4.3
correction supersedes that and keeps the sparse form. Every consumer must expand
the same way:

```python
r_peak_mask = np.zeros(5000, dtype=bool)
for p in r_peaks_lead2:
    r_peak_mask[max(0, p - 5):min(5000, p + 6)] = True   # +/-10 ms at 500 Hz

qrs_mask = np.zeros(5000, dtype=bool)
for on, off in zip(qrs_onsets_lead2, qrs_offsets_lead2):
    if on >= 0 and off >= 0:
        qrs_mask[on:off + 1] = True
```

Evaluation tolerance is +/-10 ms = +/-5 samples for R-peaks and for each QRS
boundary (§4.A.4.3).

## The oracle baseline uses `method="neurokit"`

§4.A.4.7 calls the algorithmic baseline "NeuroKit2 Pan-Tompkins" and says its F1
is 1.0 by construction. Those two statements are only both true if the baseline
runs the **same** detector as the ground truth, which is NeuroKit's default
(`method="neurokit"`), not `method="pantompkins"`. The Phase 1 regen switched
away from `pantompkins` precisely because it was wrong. So:

- the **oracle** row of §4.A.4.7 is `method="neurokit"`, F1 = 1.0 by construction;
- `method="pantompkins"` may be reported as an **additional, non-oracle** row —
  it measures detector disagreement, which is interesting, but it is not the
  oracle and its F1 will not be 1.0.

## Forbidden inputs

Everything except the four signal kinds (§4.A.4.4): images (a rendered ECG shows
the QRS boundaries and could be pixel-traced), `report_text`,
`machine_measurements` and `structured_features` (all carry aggregate timings
derived from the same delineation).

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
