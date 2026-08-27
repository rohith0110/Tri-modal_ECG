"""Stage P2.4 — run the algorithmic baselines over the test split (§5.1, §9.5).

    ./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/50_run_baselines_algorithmic.py
    ./ecg_env/Scripts/python.exe .../50_run_baselines_algorithmic.py --tasks A2_measurement_blind --dev

Writes `outputs/model_runs/<task>/algorithmic/test_predictions.parquet` in the
same §7.1 schema a trained run produces, so `31_eval.py` scores a rule baseline
and a ResNet with identical code and identical patient-level bootstrap.

These baselines have no learned parameters and no seed variability (§5.1), so a
single pass replaces the three-seed loop; the prediction file records
``seed = -1`` to make that explicit rather than implicit.

**Resumable.** The A2/B1/B2/B5 baselines re-run NeuroKit2 over ~150 K-300 K
strips, which is hours on the laptop. Every task checkpoints through
`build_common.run_chunked` into part parquets, so a mains cut costs one chunk
and re-running the same command continues (§8.2.1: "any laptop-run script must
checkpoint its progress and resume cleanly, because mains power is unreliable").

Coverage is enforced, not assumed: §11.2 makes a missing algorithmic baseline
for a doc-mandated task CRITICAL, so the run ends with an explicit per-task
table and a non-zero exit if any mandated task produced nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _dataset_lib import build_common as bc                            # noqa: E402
from _dataset_lib.task_spec import B3_QUERIES, MEASUREMENT_CLASSES, get_task  # noqa: E402
from _model_lib import algorithmic_baselines as ab                     # noqa: E402

STAGE = "P2.4"
# §5.1's table plus the two task_definitions.yaml adds (A1 logistic, B2 detector).
MANDATED = ("A1_ecg_diagnosis", "A2_measurement_blind", "A4_event_localization",
            "A6_risk_stratification", "B1_measurement_blind", "B2_noise_robustness",
            "B3_temporal_grounding", "B5_contradiction_detection")
MODEL_RUNS = bc.PROJECT_ROOT / "outputs" / "model_runs"

MEASUREMENT_SCHEMA = pa.schema([
    ("study_id", pa.int64()), ("hr_bpm", pa.float64()), ("qrs_ms", pa.float64()),
    ("qtc_ms", pa.float64()), ("rr_ms", pa.float64()),
    ("hr_label", pa.string()), ("qrs_label", pa.string()), ("qtc_label", pa.string()),
    ("n_peaks", pa.int32()), ("fallback_used", pa.bool_()), ("delineate_ok", pa.bool_()),
])


def out_dir(task: str, dev: bool) -> Path:
    root = MODEL_RUNS / "_dev" if dev else MODEL_RUNS
    path = root / task / "algorithmic"
    path.mkdir(parents=True, exist_ok=True)
    return path


def task_test_frame(task: str, dev: bool, limit: int = 0) -> pd.DataFrame:
    spec = get_task(task)
    root = bc.TASKS_DIR / "_dev" if dev else bc.TASKS_DIR
    frame = pd.read_parquet(root / task / spec.test_file)
    if "split" in frame.columns:
        frame = frame[frame["split"] == "test"]
    if spec.primary_flag_column and spec.primary_flag_column in frame.columns:
        frame = frame[frame[spec.primary_flag_column].fillna(False)]
    frame = frame.reset_index(drop=True)
    return frame.head(limit).reset_index(drop=True) if limit else frame


def write_predictions(frame: pd.DataFrame, task: str, dev: bool, log) -> Path:
    frame = frame.copy()
    frame["seed"] = -1                     # §5.1: no seed variability
    frame["arch_tier"] = "algorithmic"
    if "lead_subset" not in frame.columns:
        frame["lead_subset"] = "lead2"
    path = out_dir(task, dev) / "test_predictions.parquet"
    tmp = path.with_suffix(".parquet.tmp")
    frame.to_parquet(tmp, index=False)
    bc.atomic_replace(tmp, path)
    log.info("%s: wrote %d baseline rows -> %s", task, len(frame),
             path.relative_to(bc.PROJECT_ROOT))
    return path


# -----------------------------------------------------------------------------
# the shared NeuroKit measurement pass (A2 / B1 / B2 / B5 all need it)
# -----------------------------------------------------------------------------
_WORKER_KIND = "raw_lead2"


def _init_worker() -> None:
    bc.worker_log_init("50_run_baselines_algorithmic", STAGE)


def _measure_one(study_id: int) -> dict[str, Any]:
    return ab.measurement_baseline_row(int(study_id), _WORKER_KIND)


def measurement_pass(name: str, study_ids: list[int], state: bc.StageState, log,
                     workers: int | None = None) -> pd.DataFrame:
    """Detect + measure + bin every study, checkpointing into part parquets."""
    bc.run_chunked(name=name, units=[int(s) for s in study_ids], worker=_measure_one,
                   schema=MEASUREMENT_SCHEMA, state=state, initializer=_init_worker,
                   chunk_size=5_000, desc=name, workers=workers)
    parts = sorted(bc.part_dir(name).glob("part_*.parquet"))
    if not parts:
        return pd.DataFrame(columns=[f.name for f in MEASUREMENT_SCHEMA])
    return pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)


def align_measurements(rows: pd.DataFrame, measured: pd.DataFrame) -> pd.DataFrame:
    """One measured record per task row, in row order, joined on ``study_id``.

    Only safe where a study appears once per task row. B2 is the exception -- a
    study carries 40 corrupted variants there -- and builds its aligned frame
    positionally instead.
    """
    return rows[["study_id"]].merge(measured, on="study_id", how="left")


def attach_measurement_predictions(rows: pd.DataFrame,
                                   measured_aligned: pd.DataFrame) -> pd.DataFrame:
    """Binned rule outputs -> the §7.1 prediction columns for the three heads.

    ``measured_aligned`` must already be one row per row of ``rows``, in the same
    order. Merging inside would silently fan out on B2, where one study_id owns
    forty corrupted variants.
    """
    if len(measured_aligned) != len(rows):
        raise ValueError(f"measured frame has {len(measured_aligned)} rows, "
                         f"task frame has {len(rows)} -- they must be row-aligned")
    rows = rows.reset_index(drop=True)
    measured_aligned = measured_aligned.reset_index(drop=True)

    out = pd.DataFrame({"study_id": rows["study_id"].to_numpy(),
                        "subject_id": rows["subject_id"].to_numpy()})
    for column in ("sqi_tier", "cart_id", "link_tier", "corruption_type", "snr_db",
                   "regime", "row_role"):
        if column in rows.columns:
            out[column] = rows[column].to_numpy()

    for head, classes in MEASUREMENT_CLASSES.items():
        truth = rows[head].to_numpy()                      # the task's own label
        predicted = measured_aligned[head].to_numpy()      # what the rule said
        proba = np.stack([ab.label_to_onehot(p, classes) for p in predicted])
        for index, class_name in enumerate(classes):
            out[f"y_pred_proba_{head}__{class_name}"] = proba[:, index]
        out[f"y_true_index_{head}"] = [
            classes.index(v) if isinstance(v, str) and v in classes else -1 for v in truth]
        out[f"y_true_{head}"] = truth
        out[f"y_pred_index_{head}"] = proba.argmax(axis=1)
        out[f"y_pred_label_{head}"] = [classes[i] for i in proba.argmax(axis=1)]
        out[f"valid_{head}"] = out[f"y_true_index_{head}"].to_numpy() >= 0

    for source, target in (("fallback_used", "detector_fallback_used"),
                           ("hr_bpm", "detector_hr_bpm"), ("qrs_ms", "detector_qrs_ms"),
                           ("qtc_ms", "detector_qtc_ms")):
        if source in measured_aligned.columns:
            out[target] = measured_aligned[source].to_numpy()
    return out


# -----------------------------------------------------------------------------
# per-task baselines
# -----------------------------------------------------------------------------
def run_measurement_task(task: str, dev: bool, log, limit: int, workers: int | None) -> int:
    rows = task_test_frame(task, dev, limit)
    state = bc.StageState(STAGE, f"50_baseline_{task}{'_dev' if dev else ''}")
    name = f"baseline_{task}{'_dev' if dev else ''}"
    measured = measurement_pass(name, sorted(set(rows.study_id.tolist())), state, log, workers)
    predictions = attach_measurement_predictions(rows, align_measurements(rows, measured))
    write_predictions(predictions, task, dev, log)
    state.finish(n_rows=int(len(predictions)))
    return len(predictions)


def run_b2(dev: bool, log, limit: int, workers: int | None) -> int:
    """B2: the same detector, run on whatever signal each test row points at."""
    rows = task_test_frame("B2_noise_robustness", dev, limit)
    state = bc.StageState(STAGE, f"50_baseline_B2{'_dev' if dev else ''}")
    name = f"baseline_B2{'_dev' if dev else ''}"

    units = list(range(len(rows)))
    schema = pa.schema([("study_id", pa.int64()), ("row_ordinal", pa.int64())] +
                       [f for f in MEASUREMENT_SCHEMA if f.name != "study_id"])

    # Workers are SPAWNED on Windows and forked-then-re-imported elsewhere, so a
    # module global set in the parent does not reach them. The row table is
    # handed over as a small parquet the initializer loads once per worker.
    plan_path = bc.part_dir(name) / "_b2_rows.parquet"
    rows[["study_id", "row_role", "corruption_type", "snr_db",
          "clean_signal_kind"]].to_parquet(plan_path, index=False)
    _load_b2_rows(str(plan_path))         # the parent needs it too, for a 0-worker run

    from functools import partial

    bc.run_chunked(name=name, units=units, worker=_b2_measure_one, schema=schema,
                   state=state, initializer=partial(_init_b2_worker, str(plan_path)),
                   chunk_size=5_000, desc=name, id_column="row_ordinal", workers=workers)
    parts = sorted(bc.part_dir(name).glob("part_*.parquet"))
    measured = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True) \
        .sort_values("row_ordinal").reset_index(drop=True)

    # Positional alignment, not a join: one study_id owns 40 corrupted variants.
    rows = rows.iloc[measured["row_ordinal"].to_numpy()].reset_index(drop=True)
    measured = measured.drop(columns=["row_ordinal"]).reset_index(drop=True)
    predictions = attach_measurement_predictions(rows, measured)
    write_predictions(predictions, "B2_noise_robustness", dev, log)
    state.finish(n_rows=int(len(predictions)))
    return len(predictions)


_B2_ROWS: list[dict[str, Any]] = []


def _load_b2_rows(path: str) -> None:
    global _B2_ROWS
    _B2_ROWS = pd.read_parquet(path).to_dict("records")


def _init_b2_worker(path: str) -> None:
    bc.worker_log_init("50_run_baselines_algorithmic", STAGE)
    _load_b2_rows(path)


def _b2_measure_one(ordinal: int) -> dict[str, Any]:
    row = _B2_ROWS[int(ordinal)]
    corrupted = row["row_role"] == "corrupted"
    result = ab.measurement_baseline_row(
        int(row["study_id"]), str(row["clean_signal_kind"]),
        corruption_type=str(row["corruption_type"]) if corrupted else None,
        snr_db=int(row["snr_db"]) if corrupted else None)
    result["row_ordinal"] = int(ordinal)
    return result


def run_a4(dev: bool, log, limit: int) -> int:
    """A4's oracle: the ground-truth fiducials themselves (§4.A.4.7, F1 = 1.0)."""
    rows = task_test_frame("A4_event_localization", dev, limit)
    oracle = ab.fiducial_oracle(rows.study_id.tolist()).set_index("study_id")

    predictions = pd.DataFrame({"study_id": rows.study_id.to_numpy(),
                                "subject_id": rows.subject_id.to_numpy()})
    for column in ("sqi_tier", "cart_id", "link_tier"):
        if column in rows.columns:
            predictions[column] = rows[column].to_numpy()
    for column in ("r_peaks_lead2", "qrs_onsets_lead2", "qrs_offsets_lead2"):
        predictions[f"y_true_{column}"] = [list(map(int, v)) for v in rows[column]]
    predictions["y_pred_r_peaks"] = [
        list(map(int, oracle.loc[s, "r_peaks_lead2"])) if s in oracle.index else []
        for s in rows.study_id]
    predictions["y_pred_qrs_onsets"] = [
        list(map(int, oracle.loc[s, "qrs_onsets_lead2"])) if s in oracle.index else []
        for s in rows.study_id]
    predictions["y_pred_qrs_offsets"] = [
        list(map(int, oracle.loc[s, "qrs_offsets_lead2"])) if s in oracle.index else []
        for s in rows.study_id]
    predictions["n_pred_peaks"] = [len(v) for v in predictions["y_pred_r_peaks"]]
    write_predictions(predictions, "A4_event_localization", dev, log)
    return len(predictions)


def run_b3(dev: bool, log, limit: int) -> int:
    """B3's oracle: the §4.B.3.3 rule on the same fiducials + per-bin SQI."""
    import yaml

    rows = task_test_frame("B3_temporal_grounding", dev, limit)
    definitions = yaml.safe_load(
        (bc.CONFIG_DIR / "task_definitions.yaml").read_text(encoding="utf-8"))
    threshold = float(definitions["tasks"]["B3_temporal_grounding"]["targets"]
                      ["noisy_sqi_threshold"]["value"])
    log.info("B3 oracle: noisy_sqi_threshold = %.6f (locked from the TRAIN split)", threshold)

    oracle = ab.b3_oracle(sorted(set(rows.study_id.tolist())), threshold).set_index("study_id")
    uniform = [0] * len(B3_QUERIES[0:1] * 10)

    predictions = pd.DataFrame({"study_id": rows.study_id.to_numpy(),
                                "subject_id": rows.subject_id.to_numpy(),
                                "query": rows["query"].to_numpy()})
    for column in ("sqi_tier", "cart_id", "link_tier"):
        if column in rows.columns:
            predictions[column] = rows[column].to_numpy()
    predictions["y_true_bins"] = [list(map(int, v)) for v in rows["labels"]]
    predicted = []
    for study_id, query in zip(rows.study_id, rows["query"]):
        if study_id in oracle.index:
            predicted.append([float(v) for v in oracle.loc[study_id, query]])
        else:
            predicted.append([0.0] * 10)
    predictions["y_pred_proba_bins"] = predicted
    predictions["y_pred_label_bins"] = [[int(v >= 0.5) for v in row] for row in predicted]
    predictions["query_idx"] = [B3_QUERIES.index(q) for q in rows["query"]]
    write_predictions(predictions, "B3_temporal_grounding", dev, log)
    return len(predictions)


def run_a1(dev: bool, log, limit: int) -> int:
    """A1: logistic regression on machine-measurement summary stats (§4.A.1.7).

    BASELINE-ONLY exemption — `task_input_policy.yaml` forbids these fields as
    model input and permits them here, in this script only.
    """
    spec = get_task("A1_ecg_diagnosis")
    root = bc.TASKS_DIR / "_dev" if dev else bc.TASKS_DIR
    train = pd.read_parquet(root / "A1_ecg_diagnosis" / "train.parquet")
    train = train[train.is_primary.fillna(False)]
    test = task_test_frame("A1_ecg_diagnosis", dev, limit)

    features = ab.machine_feature_table(
        pd.concat([train.study_id, test.study_id]).unique().tolist())
    feature_columns = [c for c in features.columns if c != "study_id"]
    train = train.merge(features, on="study_id", how="inner")
    test = test.merge(features, on="study_id", how="inner")
    labels = [h.label_column for h in spec.heads]

    scored = ab.logistic_baseline(train, test, feature_columns, labels)
    predictions = pd.DataFrame({"study_id": test.study_id.to_numpy(),
                                "subject_id": test.subject_id.to_numpy()})
    for column in ("sqi_tier", "cart_id", "link_tier", "boundary_flag"):
        if column in test.columns:
            predictions[column] = test[column].to_numpy()
    for label in labels:
        proba = scored[f"y_pred_proba_{label}"].to_numpy()
        predictions[f"y_pred_proba_{label}"] = proba
        predictions[f"y_true_{label}"] = test[label].astype(float).to_numpy()
        predictions[f"y_pred_label_{label}"] = (proba >= 0.5).astype(int)
        predictions[f"valid_{label}"] = True
    write_predictions(predictions, "A1_ecg_diagnosis", dev, log)
    return len(predictions)


def run_a6(dev: bool, log, limit: int) -> int:
    """A6: Cox PH on age + sex + machine HR/QRS/QTc (§4.A.6.7, §5.1). BASELINE-ONLY."""
    spec = get_task("A6_risk_stratification")
    root = bc.TASKS_DIR / "_dev" if dev else bc.TASKS_DIR
    train = pd.read_parquet(root / "A6_risk_stratification" / "train.parquet")
    train = train[train.is_primary.fillna(False)]
    test = task_test_frame("A6_risk_stratification", dev, limit)

    demographics = ab.patient_demographics()
    features = ab.machine_feature_table(
        pd.concat([train.study_id, test.study_id]).unique().tolist())
    feature_columns = ["anchor_age", "sex_male", "hr_bpm", "qrs_ms", "qtc_ms"]
    train = train.merge(features, on="study_id").merge(demographics, on="subject_id", how="left")
    test = test.merge(features, on="study_id").merge(demographics, on="subject_id", how="left")

    predictions = pd.DataFrame({"study_id": test.study_id.to_numpy(),
                                "subject_id": test.subject_id.to_numpy()})
    for column in ("sqi_tier", "cart_id", "link_tier", "boundary_flag"):
        if column in test.columns:
            predictions[column] = test[column].to_numpy()

    info_all: dict[str, Any] = {}
    for head in spec.heads:
        mortality = head.name.startswith("mortality")
        duration = "days_to_death" if mortality else "days_to_readmission"
        censor = "followup_days_after_discharge"
        fit = train.copy()
        fit["_event"] = fit[head.label_column].fillna(False).astype(int)
        observed = fit[duration].astype("float64")
        fallback = fit[censor].astype("float64") if censor in fit.columns else pd.Series(
            np.full(len(fit), 30.0), index=fit.index)
        fit["_duration"] = observed.where(observed.notna(), fallback).fillna(1.0).clip(lower=0.5)
        if head.mask_column and head.mask_column in fit.columns:
            fit = fit[fit[head.mask_column].fillna(False)]

        score, info = ab.cox_baseline(fit, test, duration_column="_duration",
                                      event_column="_event", feature_columns=feature_columns)
        info_all[head.name] = info
        log.info("A6 Cox %s: %s (n_fit=%s, events=%s)", head.name, info.get("status"),
                 info.get("n_fit"), info.get("n_events"))

        finite = score[np.isfinite(score)]
        if finite.size:
            # Rank-normalise the partial hazard into [0, 1]: a Cox linear
            # predictor is a risk SCORE, not a probability, and AUPRC only needs
            # the ranking. A calibrated probability would be a fabrication.
            ranked = pd.Series(score).rank(pct=True, na_option="keep").to_numpy()
        else:
            ranked = np.full(len(test), np.nan)
        predictions[f"y_pred_proba_{head.name}"] = ranked
        truth = test[head.label_column]
        predictions[f"y_true_{head.name}"] = truth.fillna(False).astype(float).to_numpy()
        predictions[f"y_pred_label_{head.name}"] = (np.nan_to_num(ranked) >= 0.5).astype(int)
        valid = truth.notna().to_numpy()
        if head.mask_column and head.mask_column in test.columns:
            valid = valid & test[head.mask_column].fillna(False).to_numpy()
        predictions[f"valid_{head.name}"] = valid

    write_predictions(predictions, "A6_risk_stratification", dev, log)
    (out_dir("A6_risk_stratification", dev) / "cox_fit.json").write_text(
        json.dumps(info_all, indent=2, default=str), encoding="utf-8")
    return len(predictions)


def run_b5(dev: bool, log, limit: int, workers: int | None) -> int:
    """B5: detector-vs-report inconsistency flag (§5.1)."""
    rows = task_test_frame("B5_contradiction_detection", dev, limit)
    state = bc.StageState(STAGE, f"50_baseline_B5{'_dev' if dev else ''}")
    name = f"baseline_B5{'_dev' if dev else ''}"
    measured = measurement_pass(name, sorted(set(rows.study_id.tolist())), state, log, workers)
    measured = measured.set_index("study_id")

    dictionary = ab.load_claim_dictionary()
    audited = np.where(rows["is_corrupted"].to_numpy(dtype=bool),
                       rows["corrupted_report_text"].to_numpy(),
                       rows["original_report_text"].to_numpy())

    flags, families = [], []
    for study_id, text in zip(rows.study_id, audited):
        hr = float(measured.loc[study_id, "hr_bpm"]) if study_id in measured.index else np.nan
        qrs = float(measured.loc[study_id, "qrs_ms"]) if study_id in measured.index else np.nan
        result = ab.b5_rule_flag(str(text), hr, qrs, dictionary)
        flags.append(result["flag"])
        families.append(result["families_flagged"])

    predictions = pd.DataFrame({"study_id": rows.study_id.to_numpy(),
                                "subject_id": rows.subject_id.to_numpy()})
    for column in ("sqi_tier", "cart_id", "link_tier", "contradiction_family"):
        if column in rows.columns:
            predictions[column] = rows[column].to_numpy()
    predictions["y_pred_proba_is_corrupted"] = np.asarray(flags, dtype="float64")
    predictions["y_pred_label_is_corrupted"] = np.asarray(flags, dtype="int64")
    predictions["y_true_is_corrupted"] = rows["is_corrupted"].astype(float).to_numpy()
    predictions["valid_is_corrupted"] = True
    predictions["rule_families_flagged"] = families
    write_predictions(predictions, "B5_contradiction_detection", dev, log)
    state.finish(n_rows=int(len(predictions)))
    return len(predictions)


# -----------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--tasks", nargs="*", default=list(MANDATED))
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="cap test rows (smoke tests)")
    parser.add_argument("--workers", type=int, default=0,
                        help="process-pool size; 0 = build_common.MAX_WORKERS")
    args = parser.parse_args(argv)

    log = bc.setup_logging("50_run_baselines_algorithmic", stage=STAGE)
    bc.set_dev(args.dev)
    workers = args.workers or None
    log.info("algorithmic baselines: tasks=%s dev=%s limit=%s workers=%s",
             args.tasks, args.dev, args.limit or "all", workers or bc.MAX_WORKERS)

    runners = {
        "A1_ecg_diagnosis": lambda: run_a1(args.dev, log, args.limit),
        "A2_measurement_blind": lambda: run_measurement_task(
            "A2_measurement_blind", args.dev, log, args.limit, workers),
        "A4_event_localization": lambda: run_a4(args.dev, log, args.limit),
        "A6_risk_stratification": lambda: run_a6(args.dev, log, args.limit),
        "B1_measurement_blind": lambda: run_measurement_task(
            "B1_measurement_blind", args.dev, log, args.limit, workers),
        "B2_noise_robustness": lambda: run_b2(args.dev, log, args.limit, workers),
        "B3_temporal_grounding": lambda: run_b3(args.dev, log, args.limit),
        "B5_contradiction_detection": lambda: run_b5(args.dev, log, args.limit, workers),
    }

    results: dict[str, Any] = {}
    for task in args.tasks:
        if task not in runners:
            log.warning("%s has no algorithmic baseline in §5.1 — skipping", task)
            continue
        log.info("=== %s ===", task)
        try:
            results[task] = {"n_rows": int(runners[task]()), "status": "ok"}
        except Exception as exc:                             # keep going, report at the end
            log.exception("%s baseline FAILED: %s", task, exc)
            results[task] = {"n_rows": 0, "status": f"FAILED: {exc}"}

    missing = [t for t in MANDATED if t in args.tasks
               and results.get(t, {}).get("status") != "ok"]
    log.info("--- summary ---")
    for task, result in results.items():
        log.info("%-30s %-8s %d rows", task, result["status"][:8], result["n_rows"])
    summary_path = (MODEL_RUNS / "_dev" if args.dev else MODEL_RUNS) / \
        "algorithmic_baseline_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(
        {"results": results, "missing_mandated": missing, "dev": args.dev,
         "finished_at": bc.utc_now_iso()}, indent=2), encoding="utf-8")

    if missing:
        log.error("CRITICAL (§11.2): no algorithmic baseline produced for %s", missing)
        return 1
    log.info("all requested algorithmic baselines produced predictions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
