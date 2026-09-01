"""Stage P2.9 — the unified evaluation entry point (spec §7).

    ./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/31_eval.py \
        --task A1_ecg_diagnosis --arch-tier multimodal_fusion_12lead

Reads the per-seed `test_predictions.parquet` files a run left behind, and for
every (head, group) emits the §1.1 row: the metric's mean +/- std across the
three seeds, the pooled-prediction patient-level bootstrap CI, and the
per-subgroup breakdown. Output is `outputs/results/<task>.csv`.

Two rules are enforced here rather than assumed:

* **The bootstrap resamples subjects.** `_dataset_lib/bootstrap.py` refuses a
  frame with no `subject_id`; an ECG-level interval is CRITICAL under §11.2.
* **Thresholds are not re-tuned.** This script never calls `select_threshold`.
  It reads `y_pred_label_<head>` and `threshold_<head>`, both written by
  `30_train.py` from the VALIDATION split, and records the threshold it used in
  every row so a reviewer can diff it against `threshold_audit.md`.

The §7.3-§7.6 regimes ride on the same machinery: a regime, an SQI tier, a
corruption cell, a difficulty tier and a negative type are all just group keys.
§7.4's fiducial matcher, §7.6's calibration block and §7.5's retrieval check are
the three that need more than a group-by, and each has its own function below.

Idempotent (§8.6): re-running overwrites `outputs/results/<task>.csv` from the
prediction files, which it never modifies.
"""

from __future__ import annotations

import argparse
import json
import os
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _dataset_lib import build_common as bc                            # noqa: E402
from _dataset_lib.bootstrap import patient_bootstrap, pooled_across_seeds  # noqa: E402
from _dataset_lib.task_spec import B3_QUERIES, get_task                # noqa: E402
from _train_lib import calibration as cal                              # noqa: E402
from _train_lib import metrics as M                                    # noqa: E402
from _train_lib.trainer import head_present                            # noqa: E402

MODEL_RUNS = bc.PROJECT_ROOT / "outputs" / "model_runs"
RESULTS_DIR = bc.PROJECT_ROOT / "outputs" / "results"
EVAL_CONFIG_DIR = bc.CONFIG_DIR / "eval_configs"
FIGURES_DIR = bc.PROJECT_ROOT / "outputs" / "figures"

RESULT_COLUMNS = [
    "task", "arch_tier", "lead_subset", "head", "metric", "group_key", "group_value",
    "n_rows", "n_subjects", "n_positive", "value_mean", "value_std", "pooled_point",
    "ci_low", "ci_high", "ci_method", "n_jackknife_groups", "n_seeds", "seeds",
    "threshold", "signal_input_modality", "image_input_modality", "text_encoder",
]

TASK_EVAL_CONFIG = {
    "A3_lab_abnormality": "A6_risk.yaml",
    "A4_event_localization": "A4_fiducial.yaml",
    "A5_cross_modal_verification": "cross_modal.yaml",
    "A6_risk_stratification": "A6_risk.yaml",
    "B2_noise_robustness": "B2_robustness.yaml",
    "B4_cross_modal_verification": "cross_modal.yaml",
    "B6_difficulty_stratified": "cross_modal.yaml",
}


# -----------------------------------------------------------------------------
# discovery
# -----------------------------------------------------------------------------
def run_root(dev: bool) -> Path:
    return MODEL_RUNS / "_dev" if dev else MODEL_RUNS


def find_seed_predictions(task: str, arch_tier: str, dev: bool,
                          seeds: Iterable[int] | None = None) -> dict[int, Path]:
    base = run_root(dev) / task / arch_tier
    found: dict[int, Path] = {}
    if not base.is_dir():
        return found
    # The algorithmic tier has no seeds (§5.1: "run once on test set, no seed
    # variability"), so it writes its prediction file at the tier root and
    # records seed = -1.
    flat = base / "test_predictions.parquet"
    if flat.exists():
        return {-1: flat}
    for directory in sorted(base.glob("seed_*")):
        try:
            seed = int(directory.name.split("_")[1])
        except (IndexError, ValueError):
            continue
        if seeds and seed not in set(seeds):
            continue
        path = directory / "test_predictions.parquet"
        if path.exists():
            found[seed] = path
    return found


def discover_arch_tiers(task: str, dev: bool) -> list[str]:
    base = run_root(dev) / task
    if not base.is_dir():
        return []
    return sorted(d.name for d in base.iterdir()
                  if d.is_dir() and (any(d.glob("seed_*/test_predictions.parquet"))
                                     or (d / "test_predictions.parquet").exists()))


def load_eval_config(task: str) -> dict[str, Any]:
    config = yaml.safe_load((EVAL_CONFIG_DIR / "default.yaml").read_text(encoding="utf-8"))
    extra = TASK_EVAL_CONFIG.get(task)
    if extra:
        config["task_specific"] = yaml.safe_load(
            (EVAL_CONFIG_DIR / extra).read_text(encoding="utf-8"))
        config["task_specific_file"] = extra
    return config


# -----------------------------------------------------------------------------
# metric callables over a prediction frame
# -----------------------------------------------------------------------------
def head_metric_fns(spec, head) -> dict[str, Callable[[pd.DataFrame], float]]:
    """The metric functions for one head, keyed by the name that lands in the CSV."""
    name = head.name

    if head.kind == "binary":
        def _valid(frame: pd.DataFrame) -> pd.DataFrame:
            return frame[frame[f"valid_{name}"].to_numpy(dtype=bool)]

        fns = {
            "auprc": lambda f: M.auprc(_valid(f)[f"y_true_{name}"], _valid(f)[f"y_pred_proba_{name}"]),
            "auroc": lambda f: M.auroc(_valid(f)[f"y_true_{name}"], _valid(f)[f"y_pred_proba_{name}"]),
        }
        def _f1(frame: pd.DataFrame) -> float:
            part = _valid(frame)
            if f"y_pred_label_{name}" not in part.columns or part.empty:
                return float("nan")
            from sklearn.metrics import f1_score

            truth = part[f"y_true_{name}"].to_numpy()
            if len(np.unique(truth)) < 2:
                return float("nan")
            return float(f1_score(truth, part[f"y_pred_label_{name}"].to_numpy(),
                                  zero_division=0))

        fns["f1_at_val_threshold"] = _f1

        def _ece(frame: pd.DataFrame) -> float:
            part = _valid(frame)
            return M.expected_calibration_error(part[f"y_true_{name}"],
                                                part[f"y_pred_proba_{name}"])

        def _brier(frame: pd.DataFrame) -> float:
            part = _valid(frame)
            return M.brier(part[f"y_true_{name}"], part[f"y_pred_proba_{name}"])

        fns["ece"] = _ece
        fns["brier"] = _brier
        return fns

    if head.kind == "multiclass":
        classes = list(head.classes)

        def _proba(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
            part = frame[frame[f"valid_{name}"].to_numpy(dtype=bool)]
            truth = part[f"y_true_index_{name}"].to_numpy()
            proba = np.column_stack([part[f"y_pred_proba_{name}__{c}"].to_numpy()
                                     for c in classes]) if len(part) else np.zeros((0, len(classes)))
            return truth, proba

        def _macro(frame: pd.DataFrame) -> float:
            truth, proba = _proba(frame)
            return M.multiclass_macro_auprc(truth, proba, len(classes))

        def _accuracy(frame: pd.DataFrame) -> float:
            truth, proba = _proba(frame)
            return float((proba.argmax(axis=1) == truth).mean()) if truth.size else float("nan")

        fns = {"macro_auprc": _macro, "accuracy": _accuracy}
        for index, class_name in enumerate(classes):
            def _class_auprc(frame: pd.DataFrame, i=index) -> float:
                truth, proba = _proba(frame)
                return M.auprc((truth == i).astype("int64"), proba[:, i]) if truth.size \
                    else float("nan")
            fns[f"auprc__{class_name}"] = _class_auprc
        return fns

    if head.kind == "regression":
        # Plan A/B §5.4 / §7.1. Every value is in real units (bpm / ms) -- the
        # trainer inverted the standardisation before writing the frame.
        def _pair(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
            part = frame[frame[f"valid_{name}"].to_numpy(dtype=bool)]
            return (part[f"y_true_{name}"].to_numpy(dtype="float64"),
                    part[f"y_pred_{name}"].to_numpy(dtype="float64"))

        def _metric(key: str):
            def _fn(frame: pd.DataFrame) -> float:
                stats = M.regression_metrics(*_pair(frame), tolerance=head.tolerance,
                                             units=head.units)
                return float(stats.get(key, float("nan")))
            return _fn

        keys = ["mae", "rmse", "r2", "pearson_r", "spearman_r",
                "bias", "sd_diff", "loa_lower", "loa_upper"]
        if head.tolerance is not None:
            keys.append(f"pct_within_{head.tolerance:g}")
        return {key: _metric(key) for key in keys}

    if head.kind == "peak_seq":
        def _matches(frame: pd.DataFrame, true_col: str, pred_col: str) -> dict[str, float]:
            return M.aggregate_event_matches([
                M.match_events(np.asarray(t), np.asarray(p))
                for t, p in zip(frame[true_col], frame[pred_col])])

        return {
            "r_peak_f1": lambda f: _matches(f, "y_true_r_peaks_lead2", "y_pred_r_peaks")["f1"],
            "r_peak_precision": lambda f: _matches(f, "y_true_r_peaks_lead2",
                                                   "y_pred_r_peaks")["precision"],
            "r_peak_recall": lambda f: _matches(f, "y_true_r_peaks_lead2",
                                                "y_pred_r_peaks")["recall"],
            "r_peak_mean_abs_error_ms": lambda f: _matches(
                f, "y_true_r_peaks_lead2", "y_pred_r_peaks")["mean_abs_error_ms"],
            "qrs_onset_f1": lambda f: _matches(f, "y_true_qrs_onsets_lead2",
                                               "y_pred_qrs_onsets")["f1"],
            "qrs_offset_f1": lambda f: _matches(f, "y_true_qrs_offsets_lead2",
                                                "y_pred_qrs_offsets")["f1"],
        }

    if head.kind == "bins":
        def _arrays(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
            truth = np.array(frame["y_true_bins"].tolist(), dtype="float64")
            predicted = np.array(frame["y_pred_label_bins"].tolist(), dtype="float64") \
                if "y_pred_label_bins" in frame.columns else \
                (np.array(frame["y_pred_proba_bins"].tolist(), dtype="float64") >= 0.5).astype(float)
            return truth, predicted

        return {
            "mIoU": lambda f: M.miou(*_arrays(f)),
            "recall_at_iou_0.3": lambda f: M.recall_at_iou(*_arrays(f), 0.3),
            "recall_at_iou_0.5": lambda f: M.recall_at_iou(*_arrays(f), 0.5),
            "no_evidence_accuracy": lambda f: M.no_evidence_accuracy(*_arrays(f)),
            "bin_auprc": lambda f: M.auprc(
                np.array(f["y_true_bins"].tolist()).ravel(),
                np.array(f["y_pred_proba_bins"].tolist()).ravel()),
        }

    if head.kind == "span":
        def _iou(frame: pd.DataFrame) -> float:
            part = frame[frame[f"valid_{name}"].to_numpy(dtype=bool)]
            values = [M.char_iou((ts, te), (ps, pe)) for ts, te, ps, pe in zip(
                part["y_true_span_start_norm"], part["y_true_span_end_norm"],
                part["y_pred_span_start_norm"], part["y_pred_span_end_norm"])]
            finite = [v for v in values if np.isfinite(v)]
            return float(np.mean(finite)) if finite else float("nan")

        return {"mean_char_iou": _iou}

    raise ValueError(f"no metric set for head kind {head.kind!r}")      # pragma: no cover


def n_positive_for(head, frame: pd.DataFrame) -> int:
    if head.kind == "binary" and f"y_true_{head.name}" in frame.columns:
        valid = frame[f"valid_{head.name}"].to_numpy(dtype=bool)
        return int((frame[f"y_true_{head.name}"].to_numpy()[valid] > 0).sum())
    if head.kind == "multiclass" and f"y_true_index_{head.name}" in frame.columns:
        valid = frame[f"valid_{head.name}"].to_numpy(dtype=bool)
        return int((frame[f"y_true_index_{head.name}"].to_numpy()[valid] >= 0).sum())
    if head.kind == "regression" and f"valid_{head.name}" in frame.columns:
        # A regression head has no "positives"; §1.1 wants the scored n.
        return int(frame[f"valid_{head.name}"].to_numpy(dtype=bool).sum())
    return int(len(frame))


# -----------------------------------------------------------------------------
# the §1.1 row builder
# -----------------------------------------------------------------------------
def evaluate_group(spec, head, metric_name: str, metric_fn, per_seed: dict[int, pd.DataFrame],
                   pooled: pd.DataFrame, group_key: str, group_value: Any,
                   settings: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    values = [metric_fn(frame) for frame in per_seed.values()]
    finite = [v for v in values if np.isfinite(v)]
    n_positive = n_positive_for(head, pooled)

    boot = patient_bootstrap(
        pooled, metric_fn,
        n_iter=int(settings["n_iter"]), ci_method=settings["method"],
        seed=int(settings["seed"]), level=float(settings["level"]),
        n_positive=n_positive,
        n_jackknife_groups=int(settings.get("delete_d_groups", 200)))

    return {
        "task": spec.key, "arch_tier": meta["arch_tier"], "lead_subset": meta["lead_subset"],
        "head": head.name, "metric": metric_name,
        "group_key": group_key, "group_value": group_value,
        "n_rows": int(len(pooled) / max(len(per_seed), 1)),
        "n_subjects": int(pooled["subject_id"].nunique()),
        "n_positive": int(n_positive / max(len(per_seed), 1)),
        "value_mean": float(np.mean(finite)) if finite else float("nan"),
        "value_std": float(np.std(finite, ddof=1)) if len(finite) > 1 else 0.0,
        "pooled_point": boot["point"], "ci_low": boot["ci_low"], "ci_high": boot["ci_high"],
        "ci_method": boot["method_used"], "n_jackknife_groups": boot["n_jackknife_groups"],
        "n_seeds": len(per_seed), "seeds": ",".join(str(s) for s in sorted(per_seed)),
        "threshold": meta["thresholds"].get(head.name),
        "signal_input_modality": meta["signal_input_modality"],
        "image_input_modality": meta["image_input_modality"],
        "text_encoder": meta["text_encoder"],
    }


def subgroup_values(spec, pooled: pd.DataFrame, settings: dict[str, Any]) -> list[tuple[str, Any]]:
    """(group_key, group_value) pairs for the §7.1 subgroup breakdown."""
    pairs: list[tuple[str, Any]] = [("overall", "all")]
    for key in settings["keys"]:
        if key not in pooled.columns:
            continue
        counts = pooled[key].value_counts(dropna=True)
        if key == "cart_id":
            counts = counts.head(int(settings.get("cart_id_top_n", 5)))
        for value, count in counts.items():
            if count >= int(settings.get("min_rows_per_group", 50)):
                pairs.append((key, value))
    for key in spec.subgroup_columns:
        if key in pooled.columns and key not in settings["keys"]:
            for value, count in pooled[key].value_counts(dropna=True).items():
                if count >= int(settings.get("min_rows_per_group", 50)):
                    pairs.append((key, value))
    seen, unique = set(), []
    for pair in pairs:
        if pair not in seen:
            seen.add(pair)
            unique.append(pair)
    return unique


def resolve_jobs(requested: int) -> int:
    """Workers to use: what was asked, else the cores Slurm allocated.

    `os.cpu_count()` reports the whole 256-core node, not this job's share, so
    using it would oversubscribe the allocation and slow every other job on the
    box. SLURM_CPUS_PER_TASK is the honest number.
    """
    if requested and requested > 0:
        return requested
    allocated = os.environ.get("SLURM_CPUS_PER_TASK") or os.environ.get("SLURM_CPUS_ON_NODE")
    try:
        return max(1, int(allocated))
    except (TypeError, ValueError):
        return 1


# Set by evaluate_arch immediately before the pool is created; the workers
# inherit it through fork rather than receiving it as pickled arguments.
_UNIT_CTX: dict[str, Any] = {}


def _compute_unit(index: int) -> dict[str, Any]:
    ctx = _UNIT_CTX
    head, metric_name, metric_fn, group_key, group_value = ctx["units"][index]
    sliced_seeds = {s: _slice(f, group_key, group_value)
                    for s, f in ctx["per_seed"].items()}
    sliced_pooled = _slice(ctx["pooled"], group_key, group_value)
    return evaluate_group(ctx["spec"], head, metric_name, metric_fn,
                          sliced_seeds, sliced_pooled, group_key, group_value,
                          ctx["settings"], ctx["meta"])


def checkpoint_path(task: str, arch_tier: str, dev: bool) -> Path:
    directory = (RESULTS_DIR / "_dev" if dev else RESULTS_DIR) / ".eval_checkpoints"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{task}__{arch_tier}.jsonl"


def load_checkpoint(task: str, arch_tier: str, dev: bool,
                    settings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Units already computed for this (task, tier) UNDER THE SAME SETTINGS.

    An evaluation is hours of work and used to be all-or-nothing: it wrote
    nothing until the very end, so a cancelled or preempted job threw away
    everything.

    The settings stamp is not optional. A debug run with `--bootstrap-n 200`
    leaves a checkpoint behind, and without the stamp a later full run would
    happily adopt those 200-iteration CIs as though they were the 10,000 the
    spec locks -- reported numbers, quietly wrong, with nothing to show it. Any
    record whose bootstrap settings differ from the current ones is ignored and
    the unit is recomputed. A truncated final line (killed mid-write) is
    skipped for the same reason: cheaper to redo one unit than to trust it.
    """
    path = checkpoint_path(task, arch_tier, dev)
    if not path.exists():
        return {}
    stamp = checkpoint_stamp(settings)
    done: dict[str, dict[str, Any]] = {}
    stale = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue                    # half-written last line
            if record.get("stamp") != stamp:
                stale += 1
                continue
            done[record["unit"]] = record["row"]
    if stale:
        print(f"  ignoring {stale} checkpointed unit(s) computed under different "
              f"bootstrap settings", file=sys.stderr)
    return done


def checkpoint_stamp(settings: dict[str, Any]) -> str:
    """The settings a checkpointed number depends on."""
    keys = ("n_iter", "method", "seed", "level", "unit", "fallback")
    return json.dumps({k: settings.get(k) for k in keys}, sort_keys=True, default=str)


def append_checkpoint(task: str, arch_tier: str, dev: bool, unit: str,
                      row: dict[str, Any], stamp: str) -> None:
    """Append one finished unit. Written by the parent, so it stays serialised."""
    with checkpoint_path(task, arch_tier, dev).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"unit": unit, "row": row, "stamp": stamp},
                                default=str) + chr(10))
        handle.flush()
        os.fsync(handle.fileno())


def clear_checkpoint(task: str, arch_tier: str, dev: bool) -> None:
    checkpoint_path(task, arch_tier, dev).unlink(missing_ok=True)


def evaluate_arch(task: str, arch_tier: str, dev: bool, seeds: Iterable[int] | None,
                  eval_config: dict[str, Any], log: logging.Logger,
                  bootstrap_override: int | None = None,
                  jobs: int = 1) -> list[dict[str, Any]]:
    spec = get_task(task)
    prediction_paths = find_seed_predictions(task, arch_tier, dev, seeds)
    if not prediction_paths:
        log.warning("%s/%s: no test_predictions.parquet found — nothing to evaluate",
                    task, arch_tier)
        return []

    per_seed = {seed: pd.read_parquet(path) for seed, path in prediction_paths.items()}
    if task == "B6_difficulty_stratified":
        per_seed = {s: attach_b6_tiers(f, dev) for s, f in per_seed.items()}
    pooled = pooled_across_seeds(list(per_seed.values()))

    first = next(iter(per_seed.values()))
    meta = {
        "arch_tier": arch_tier,
        "lead_subset": str(first["lead_subset"].iloc[0]) if "lead_subset" in first else "none",
        "signal_input_modality": _first_or_none(first, "signal_input_modality"),
        "image_input_modality": _first_or_none(first, "image_input_modality"),
        "text_encoder": _first_or_none(first, "text_encoder"),
        "thresholds": {h.name: _first_or_none(first, f"threshold_{h.name}")
                       for h in spec.heads},
    }

    settings = dict(eval_config["bootstrap"])
    settings.update(eval_config["bootstrap"].get("jackknife", {}))
    if bootstrap_override:
        settings["n_iter"] = bootstrap_override
    subgroup_settings = eval_config["subgroups"]

    rows: list[dict[str, Any]] = []
    groups = subgroup_values(spec, pooled, subgroup_settings)
    log.info("%s/%s: %d seeds, %d pooled rows, %d groups",
             task, arch_tier, len(per_seed), len(pooled), len(groups))

    # ---- plan the work ----------------------------------------------------
    # One unit = (head, subgroup, metric). Units are independent: each calls
    # patient_bootstrap, which seeds its own RNG from the fixed spec seed, so a
    # unit's numbers do not depend on how many other units ran or in what order.
    # That is what makes both the parallelism below and the resume safe.
    units: list[tuple[Any, str, str, Any, Any]] = []
    for head in spec.heads:
        if not head_present(head, pooled):
            # This tier could not serve the head (e.g. A5 text-only has no
            # signal/image for the masked-attribute head), so it wrote no
            # columns for it. Scoring it would invent numbers.
            log.info("%s/%s: head %s absent from the prediction file — skipped",
                     task, arch_tier, head.name)
            continue
        fns = head_metric_fns(spec, head)
        for group_key, group_value in groups:
            if _slice(pooled, group_key, group_value).empty:
                continue
            for metric_name, metric_fn in fns.items():
                units.append((head, metric_name, metric_fn, group_key, group_value))

    def unit_key(head, metric_name, group_key, group_value) -> str:
        return f"{head.name}|{metric_name}|{group_key}|{group_value}"

    # The worker must be importable at module level: ProcessPoolExecutor pickles
    # the CALLABLE, and a nested function cannot be pickled. Only the unit index
    # crosses the process boundary -- the frames, the metric closures and the
    # spec are inherited through fork, which is also what keeps the ~10^5-row
    # pooled frame from being copied per task.
    _UNIT_CTX.update(units=units, per_seed=per_seed, pooled=pooled,
                     spec=spec, settings=settings, meta=meta)
    compute = _compute_unit

    # ---- resume ------------------------------------------------------------
    stamp = checkpoint_stamp(settings)
    done = load_checkpoint(task, arch_tier, dev, settings)
    rows = [None] * len(units)                       # keep deterministic order
    todo = []
    for index, (head, metric_name, _fn, group_key, group_value) in enumerate(units):
        key = unit_key(head, metric_name, group_key, group_value)
        if key in done:
            rows[index] = done[key]
        else:
            todo.append(index)
    if done:
        log.info("%s/%s: resuming — %d of %d units already done",
                 task, arch_tier, len(units) - len(todo), len(units))

    # ---- run ---------------------------------------------------------------
    # A 10,000-iteration BCa bootstrap per unit is hours of single-core work.
    # fork lets the children share `pooled`/`per_seed` copy-on-write instead of
    # pickling them per task, which matters when the pooled frame is ~10^5 rows.
    if jobs > 1 and len(todo) > 1 and hasattr(os, "fork"):
        import concurrent.futures as cf
        import multiprocessing as mp
        context = mp.get_context("fork")
        log.info("%s/%s: %d units to compute across %d workers",
                 task, arch_tier, len(todo), jobs)
        with cf.ProcessPoolExecutor(max_workers=jobs, mp_context=context) as pool:
            futures = {pool.submit(compute, index): index for index in todo}
            for finished, future in enumerate(cf.as_completed(futures), start=1):
                index = futures[future]
                row = future.result()
                rows[index] = row
                head, metric_name, _fn, group_key, group_value = units[index]
                append_checkpoint(task, arch_tier, dev,
                                  unit_key(head, metric_name, group_key, group_value),
                                  row, stamp)
                if finished % 10 == 0 or finished == len(todo):
                    log.info("%s/%s: %d/%d units", task, arch_tier, finished, len(todo))
    else:
        for finished, index in enumerate(todo, start=1):
            rows[index] = compute(index)
            head, metric_name, _fn, group_key, group_value = units[index]
            append_checkpoint(task, arch_tier, dev,
                              unit_key(head, metric_name, group_key, group_value),
                              rows[index], stamp)
            if finished % 10 == 0 or finished == len(todo):
                log.info("%s/%s: %d/%d units", task, arch_tier, finished, len(todo))

    return [r for r in rows if r is not None]


def _first_or_none(frame: pd.DataFrame, column: str):
    if column not in frame.columns or frame.empty:
        return None
    value = frame[column].iloc[0]
    return None if pd.isna(value) else value


def _slice(frame: pd.DataFrame, group_key: str, group_value: Any) -> pd.DataFrame:
    if group_key == "overall":
        return frame
    return frame[frame[group_key] == group_value]


def attach_b6_tiers(frame: pd.DataFrame, dev: bool) -> pd.DataFrame:
    """B6 is a slice of B4's prediction file (§4.B.6, §7.5) -- join the tier table."""
    root = bc.TASKS_DIR / "_dev" if dev else bc.TASKS_DIR
    keys = pd.read_parquet(root / "B6_difficulty_stratified" / "eval_keys.parquet")
    keys = keys.rename(columns={"study_id": "study_id", "neg_type": "neg_type"})
    merged = frame.merge(keys[["study_id", "neg_type", "difficulty_tier"]].drop_duplicates(),
                         on=["study_id", "neg_type"], how="left", validate="many_to_one")
    merged["difficulty_tier"] = merged["difficulty_tier"].fillna("positive")
    return merged


# -----------------------------------------------------------------------------
# §7.6 calibration report + §7.4 event-count distribution
# -----------------------------------------------------------------------------
def calibration_block(task: str, arch_tier: str, per_seed: dict[int, pd.DataFrame],
                      output_dir: Path) -> dict[str, Any]:
    spec = get_task(task)
    report: dict[str, Any] = {}
    pooled = pooled_across_seeds(list(per_seed.values()))
    for head in spec.heads:
        if head.kind != "binary" or not head_present(head, pooled):
            continue
        valid = pooled[f"valid_{head.name}"].to_numpy(dtype=bool)
        truth = pooled[f"y_true_{head.name}"].to_numpy()[valid]
        raw = pooled[f"y_pred_proba_{head.name}"].to_numpy()[valid]
        entry = {"raw": cal.calibration_report(truth, raw, head=head.name)}
        calibrated_column = f"y_pred_proba_{head.name}_calibrated"
        if calibrated_column in pooled.columns:
            entry["calibrated"] = cal.calibration_report(
                truth, pooled[calibrated_column].to_numpy()[valid], head=head.name)
            entry["calibrator"] = _first_or_none(pooled, f"calibrator_{head.name}")
        for threshold in (0.05, 0.10, 0.20):
            entry.setdefault("net_benefit", {})[str(threshold)] = M.net_benefit(
                truth, raw, threshold)
        cal.save_reliability_diagram(
            entry["raw"], output_dir / f"reliability_{task}_{arch_tier}_{head.name}.png",
            f"{task} / {arch_tier} / {head.name}")
        report[head.name] = entry
    return report


def event_count_distribution(per_seed: dict[int, pd.DataFrame],
                             buckets: list[int]) -> dict[str, int]:
    pooled = pooled_across_seeds(list(per_seed.values()))
    deltas = pooled["n_pred_peaks"].to_numpy() - np.array(
        [len(v) for v in pooled["y_true_r_peaks_lead2"]])
    out: dict[str, int] = {}
    edges = sorted(buckets)
    out[f"<={edges[0]}"] = int((deltas <= edges[0]).sum())
    for lo, hi in zip(edges, edges[1:]):
        out[f"({lo},{hi}]"] = int(((deltas > lo) & (deltas <= hi)).sum())
    out[f">{edges[-1]}"] = int((deltas > edges[-1]).sum())
    return out


# -----------------------------------------------------------------------------
# §7.3 B2 -- corruption curve, AUCC, collapse threshold
# -----------------------------------------------------------------------------
def b2_corruption_grid(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """The 8 x 5 grid, AUCC per family and the collapse threshold (§7.3)."""
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    cells = frame[(frame.metric == "macro_auprc") &
                  (frame.group_key.isin(["corruption_type", "snr_db", "overall"]))]
    return cells.reset_index(drop=True)


def b2_summary(per_seed: dict[int, pd.DataFrame], spec) -> list[dict[str, Any]]:
    """Per-(family, SNR) AUPRC plus AUCC and collapse threshold, per head."""
    pooled = pooled_across_seeds(list(per_seed.values()))
    if "corruption_type" not in pooled.columns:
        return []
    clean = pooled[pooled.get("row_role", pd.Series(dtype=str)) == "clean_reference"] \
        if "row_role" in pooled.columns else pooled.iloc[0:0]

    out: list[dict[str, Any]] = []
    for head in spec.heads:
        fns = head_metric_fns(spec, head)
        clean_value = fns["macro_auprc"](clean) if len(clean) else float("nan")
        corrupted = pooled[pooled["corruption_type"].notna()]
        for family, family_rows in corrupted.groupby("corruption_type"):
            per_snr: dict[int, float] = {}
            for snr, snr_rows in family_rows.groupby("snr_db"):
                per_snr[int(snr)] = fns["macro_auprc"](snr_rows)
            values = [v for v in per_snr.values() if np.isfinite(v)]
            collapse = None
            if np.isfinite(clean_value):
                for snr in sorted(per_snr, reverse=True):
                    if np.isfinite(per_snr[snr]) and per_snr[snr] < 0.5 * clean_value:
                        collapse = snr
                        break
            out.append({
                "head": head.name, "corruption_type": family,
                "clean_macro_auprc": clean_value,
                "per_snr": {str(k): per_snr[k] for k in sorted(per_snr, reverse=True)},
                "area_under_corruption_curve": float(np.mean(values)) if values else float("nan"),
                "collapse_threshold_snr_db": collapse,
            })
    return out


# -----------------------------------------------------------------------------
# §7.5 retrieval (secondary check)
# -----------------------------------------------------------------------------
def retrieval_eval(task: str, arch_tier: str, dev: bool, seed: int,
                   log: logging.Logger, pool_size: int = 100,
                   max_anchors: int = 500) -> dict[str, Any]:
    """Recall@1 / Recall@5 / MRR over a deterministic 100-candidate pool (§7.5).

    **Cross-modal by construction.** §7.5 asks, "given an anchor study_id and a
    modality, rank the 100-candidate pool of other-subject studies by embedding
    similarity". The query and the candidates must come from DIFFERENT
    modalities -- ranking a study's signal embedding against its own signal
    embedding scores 1.0 for every anchor and measures nothing. The query is the
    anchor's text (or image) embedding; the candidates are signal (or image)
    embeddings. A single-modality run has no retrieval to do and is skipped with
    a recorded reason.

    Pool composition: 50 same-HR-bucket + 50 different-HR-bucket non-anchor
    subjects, drawn with ``seed = 2026 + anchor_id`` so all three training seeds
    are scored on the same candidates.
    """
    import torch

    from _dataset_lib.task_dataset import TaskDataset, plan_from_config
    from _model_lib.task_models import build_model
    from _train_lib.trainer import TrainConfig

    directory = run_root(dev) / task / arch_tier / f"seed_{seed}"
    checkpoint_path = directory / "checkpoint_best.pt"
    if not checkpoint_path.exists():
        return {"status": "skipped", "reason": f"{checkpoint_path} not found"}

    snapshot = yaml.safe_load((directory / "train_config.yaml").read_text(encoding="utf-8"))
    config_dict = snapshot["model_config"]
    plan = plan_from_config(config_dict)
    spec = get_task(task)

    # query modality -> candidate modality; both must exist for this run.
    if plan.uses_text and plan.uses_signal:
        query_modality, candidate_modality = "text", "signal"
    elif plan.uses_text and plan.uses_image:
        query_modality, candidate_modality = "text", "image"
    elif plan.uses_image and plan.uses_signal:
        query_modality, candidate_modality = "image", "signal"
    else:
        return {"status": "skipped",
                "reason": "retrieval is cross-modal; this tier reads one modality only"}

    dataset = TaskDataset(task, "test", plan, dev=dev, primary_only=False)
    frame = dataset.frame
    anchors = frame[frame["y_match"] == 1].drop_duplicates("anchor_study_id").head(max_anchors)
    if anchors.empty:
        return {"status": "skipped", "reason": "no positive anchors in the test split"}

    cohort = bc.load_clean_cohort(dev=dev)[["study_id", "subject_id", "hr_bucket"]]
    bucket = dict(zip(cohort.study_id.to_numpy(), cohort.hr_bucket.to_numpy()))
    subject_of = dict(zip(cohort.study_id.to_numpy(), cohort.subject_id.to_numpy()))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(spec, plan, pretrained=False,
                        head_style=config_dict.get("head_style", "auto"))
    payload = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model.load_state_dict(payload["model_state_dict"])
    model.to(device).eval()

    tfidf = None
    if plan.text_encoder == "tfidf":
        from _model_lib.text_encoders import TfidfTextEncoder

        blob = payload.get("tfidf_state")
        if blob is None:
            return {"status": "skipped", "reason": "checkpoint carries no fitted TF-IDF state"}
        tfidf = TfidfTextEncoder().load_state_bytes(blob)

    candidates_all = list(dict.fromkeys(frame[spec.image_id_column].tolist()))
    log.info("retrieval %s->%s: %d anchors against %d candidate studies",
             query_modality, candidate_modality, len(anchors), len(candidates_all))

    config = TrainConfig(task=task, arch_tier=arch_tier, lead_subset="none", seed=seed,
                         output_dir=directory, batch_size=32, num_workers=0, dev=dev)
    candidate_vectors = _embed_studies(model, candidate_modality, candidates_all, plan,
                                       device, config, tfidf)
    query_vectors = _embed_studies(model, query_modality,
                                   anchors["anchor_study_id"].tolist(), plan, device,
                                   config, tfidf)

    rng_base = 2026
    ranks: list[int] = []
    for raw_anchor in anchors["anchor_study_id"].to_numpy():
        anchor_id = int(raw_anchor)
        if anchor_id not in query_vectors or anchor_id not in candidate_vectors:
            continue
        anchor_subject = subject_of.get(anchor_id)
        anchor_bucket = bucket.get(anchor_id)
        others = [int(s) for s in candidates_all
                  if subject_of.get(int(s)) != anchor_subject and int(s) != anchor_id
                  and int(s) in candidate_vectors]
        same = [s for s in others if bucket.get(s) == anchor_bucket]
        different = [s for s in others if bucket.get(s) != anchor_bucket]
        rng = np.random.default_rng(rng_base + anchor_id)
        half = pool_size // 2
        picked = list(rng.choice(same, size=min(half, len(same)), replace=False))
        picked += list(rng.choice(different, size=min(pool_size - half, len(different)),
                                  replace=False))
        if not picked:
            continue
        pool = [anchor_id] + [int(p) for p in picked]
        matrix = np.stack([candidate_vectors[c] for c in pool])
        query = query_vectors[anchor_id]
        norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query) + 1e-9
        similarity = matrix @ query / norms
        ranks.append(int((similarity[1:] >= similarity[0]).sum()) + 1)

    if not ranks:
        return {"status": "skipped", "reason": "no anchor produced a usable pool"}
    ranks_array = np.array(ranks)
    return {
        "status": "ok", "query_modality": query_modality,
        "candidate_modality": candidate_modality,
        "n_anchors": int(ranks_array.size), "pool_size": pool_size,
        "recall_at_1": float((ranks_array == 1).mean()),
        "recall_at_5": float((ranks_array <= 5).mean()),
        "mrr": float((1.0 / ranks_array).mean()),
    }


def _embed_studies(model, modality: str, study_ids, plan, device, config,
                   tfidf) -> dict[int, np.ndarray]:
    """Embed each study once with the run's own encoder for ``modality``."""
    import torch

    from _dataset_lib.modality import read_modality
    from _dataset_lib.task_dataset import _decode_image, build_image_transform

    out: dict[int, np.ndarray] = {}
    unique = list(dict.fromkeys(int(s) for s in study_ids))
    transform = (build_image_transform(plan.image_h, plan.image_w, False)
                 if modality == "image" else None)

    texts: dict[int, str] = {}
    tokenizer = None
    if modality == "text":
        table = bc.report_text_series(dev=bool(getattr(config, "dev", False)))
        table = table[table.study_id.isin(unique)]
        texts = dict(zip(table.study_id.to_numpy(),
                         table.report_text.fillna("").astype(str)))
        if tfidf is None:
            from transformers import AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(model.text_encoder.hf_id)

    def flush(chunk: list[int]) -> None:
        if not chunk:
            return
        with torch.no_grad():
            if modality == "signal":
                arrays = []
                for study_id in chunk:
                    array = np.asarray(read_modality(study_id, plan.signal_kind),
                                       dtype="float32")
                    arrays.append(array[None, :] if array.ndim == 1 else array)
                tensor = torch.from_numpy(np.stack(arrays)).to(device)
                vectors = model.signal_encoder(tensor).float().cpu().numpy()
            elif modality == "image":
                tensor = torch.stack([
                    transform(_decode_image(read_modality(s, plan.image_kind)))
                    for s in chunk]).to(device)
                vectors = model.image_encoder(tensor).float().cpu().numpy()
            else:
                batch_texts = [texts.get(s, "") for s in chunk]
                if tfidf is not None:
                    vectors = tfidf.transform(batch_texts)
                else:
                    encoded = tokenizer(batch_texts, max_length=plan.text_max_length,
                                        truncation=True, padding="max_length",
                                        return_tensors="pt")
                    vectors = model.text_encoder(
                        encoded["input_ids"].to(device),
                        encoded["attention_mask"].to(device)).float().cpu().numpy()
        for study_id, vector in zip(chunk, vectors):
            out[int(study_id)] = np.asarray(vector, dtype="float64")

    batch: list[int] = []
    for study_id in unique:
        batch.append(study_id)
        if len(batch) >= config.batch_size:
            flush(batch)
            batch = []
    flush(batch)
    return out


# -----------------------------------------------------------------------------
def write_results(task: str, rows: list[dict[str, Any]], dev: bool,
                  log: logging.Logger) -> Path:
    directory = RESULTS_DIR / "_dev" if dev else RESULTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{task}.csv"
    frame = pd.DataFrame(rows)
    for column in RESULT_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    frame = frame[RESULT_COLUMNS]

    # A targeted --arch-tier run must not delete the tiers it did not evaluate.
    # Rows for the tiers just evaluated are replaced; everything else survives,
    # so the per-task CSV accumulates the full §7.1 table across invocations and
    # stays idempotent (§8.6).
    if path.exists():
        previous = pd.read_csv(path)
        if "arch_tier" in previous.columns:
            refreshed = set(frame["arch_tier"].unique())
            previous = previous[~previous["arch_tier"].isin(refreshed)]
            frame = pd.concat([previous.reindex(columns=RESULT_COLUMNS), frame],
                              ignore_index=True)
    frame = frame.sort_values(["arch_tier", "head", "metric", "group_key", "group_value"],
                              kind="mergesort").reset_index(drop=True)
    tmp = path.with_suffix(".csv.tmp")
    frame.to_csv(tmp, index=False)
    bc.atomic_replace(tmp, path)
    log.info("wrote %d rows -> %s", len(frame), path.relative_to(bc.PROJECT_ROOT))
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--task", required=True)
    parser.add_argument("--arch-tier", default=None,
                        help="default: every arch tier with predictions on disk")
    parser.add_argument("--seeds", type=int, nargs="*", default=None)
    parser.add_argument("-j", "--jobs", type=int, default=0,
                        help="worker processes for the per-unit bootstrap "
                             "(0 = use the cores Slurm actually gave this job)")
    parser.add_argument("--allow-identical-tiers", action="store_true",
                        help="write results even when two arch tiers produce "
                             "bit-identical metrics (normally a wiring bug)")
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--bootstrap-n", type=int, default=0,
                        help="override n_iter (smoke tests only; §6.7 locks 10,000)")
    parser.add_argument("--retrieval", action="store_true",
                        help="also run the §7.5 retrieval check (needs checkpoint_best)")
    parser.add_argument("--no-calibration", action="store_true")
    return parser.parse_args(argv)


def previously_written_rows(task: str, dev: bool,
                           exclude_tiers: set[str]) -> list[dict[str, Any]]:
    """Headline rows for OTHER tiers of this task, from the accumulated CSV.

    Returns [] when the file is absent or unreadable -- a missing history must
    never block an evaluation, it just means there is nothing to compare with
    yet.
    """
    path = (RESULTS_DIR / "_dev" if dev else RESULTS_DIR) / f"{task}.csv"
    if not path.exists():
        return []
    try:
        frame = pd.read_csv(path)
    except Exception:
        return []
    if "arch_tier" not in frame.columns:
        return []
    frame = frame[~frame["arch_tier"].isin(exclude_tiers)]
    return frame.to_dict("records")


def identical_tier_check(rows: list[dict[str, Any]], log) -> list[tuple[str, str]]:
    """Refuse to believe that two different architectures scored identically.

    On 2026-08-31 every `text_tfidf` run in campaign 1 turned out to have
    trained BioClinicalBERT: the configs name encoder classes
    (`TfidfTextEncoder`), the modality plan lower-cased that to
    `"tfidftextencoder"`, and the model builder read "anything that is not
    exactly 'tfidf'" as "use BERT". Nothing raised. Checksums passed, the audits
    passed, the smoke test passed, and each run wrote a `train_config.yaml` that
    said `encoder: TfidfTextEncoder`. A day and a half of GPU time produced a
    duplicate of the BERT arm labelled as the baseline it was supposed to be
    compared against.

    The ONLY thing that gave it away was two tiers agreeing to four decimals.
    So that comparison is now a gate rather than an observation: two distinct
    arch tiers producing bit-identical metrics across every head and metric is
    not a result, it is a wiring bug. `--allow-identical-tiers` exists for the
    genuinely degenerate case (a task where two tiers really are the same
    computation), and it has to be typed deliberately.
    """
    by_tier: dict[str, dict[tuple, float]] = {}
    for row in rows:
        if row.get("group_key") not in (None, "", "overall"):
            continue                       # compare headline numbers, not subgroups
        key = (row["head"], row["metric"])
        value = row.get("value_mean")
        if value is None:
            continue
        by_tier.setdefault(row["arch_tier"], {})[key] = float(value)

    collisions: list[tuple[str, str]] = []
    tiers = sorted(by_tier)
    for i, left in enumerate(tiers):
        for right in tiers[i + 1:]:
            shared = set(by_tier[left]) & set(by_tier[right])
            if len(shared) < 2:
                continue                   # too little overlap to mean anything
            if all(by_tier[left][k] == by_tier[right][k] for k in shared):
                collisions.append((left, right))
                log.error(
                    "IDENTICAL METRICS: arch tiers %r and %r agree exactly on all "
                    "%d headline metrics. Two different architectures do not do "
                    "that. Check that each tier builds the encoder its config "
                    "names -- this is exactly how the 2026-08-31 tf-idf/BERT "
                    "collision looked. Override with --allow-identical-tiers "
                    "only if they are genuinely the same computation.",
                    left, right, len(shared))
    return collisions


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    spec = get_task(args.task)
    log = bc.setup_logging(f"31_eval_{args.task}", stage="P2.9")

    eval_config = load_eval_config(args.task)
    log.info("eval config: default.yaml + %s", eval_config.get("task_specific_file", "(none)"))

    tiers = [args.arch_tier] if args.arch_tier else discover_arch_tiers(args.task, args.dev)
    if not tiers:
        log.error("no arch tier with test predictions under %s",
                  run_root(args.dev) / args.task)
        return 1

    rows: list[dict[str, Any]] = []
    extras: dict[str, Any] = {}
    for arch_tier in tiers:
        rows += evaluate_arch(args.task, arch_tier, args.dev, args.seeds, eval_config, log,
                              bootstrap_override=args.bootstrap_n or None,
                              jobs=resolve_jobs(args.jobs))

        prediction_paths = find_seed_predictions(args.task, arch_tier, args.dev, args.seeds)
        per_seed = {s: pd.read_parquet(p) for s, p in prediction_paths.items()}
        if not per_seed:
            continue
        output_dir = FIGURES_DIR / ("supplementary" if args.dev else "main")

        if not args.no_calibration and any(h.kind == "binary" for h in spec.heads):
            extras.setdefault("calibration", {})[arch_tier] = calibration_block(
                args.task, arch_tier, per_seed, output_dir)
        if args.task == "A4_event_localization":
            buckets = eval_config["task_specific"]["event_count_distribution"]["buckets"]
            extras.setdefault("event_count_distribution", {})[arch_tier] = \
                event_count_distribution(per_seed, buckets)
        if args.task == "B2_noise_robustness":
            extras.setdefault("b2_corruption", {})[arch_tier] = b2_summary(per_seed, spec)
        if args.retrieval and args.task in ("A5_cross_modal_verification",
                                            "B4_cross_modal_verification"):
            for seed in sorted(per_seed):
                extras.setdefault("retrieval", {}).setdefault(arch_tier, {})[str(seed)] = \
                    retrieval_eval(args.task, arch_tier, args.dev, seed, log)

    if not rows:
        log.error("no results produced")
        return 1

    # The campaign runs `31_eval.py --task X --arch-tier Y`, one tier per
    # process, so `rows` holds a SINGLE tier and a cross-tier comparison inside
    # it can never fire -- which would have made this gate useless exactly where
    # it is needed. `write_results` accumulates the per-task CSV across
    # invocations, so the previously evaluated tiers are on disk: compare
    # against those too.
    identical = identical_tier_check(rows + previously_written_rows(args.task, args.dev,
                                                                    {r["arch_tier"] for r in rows}),
                                     log)
    if identical and not args.allow_identical_tiers:
        log.error("refusing to write results -- see the tier collision above")
        return 1

    write_results(args.task, rows, args.dev, log)
    for arch_tier in tiers:
        clear_checkpoint(args.task, arch_tier, args.dev)

    if extras:
        directory = RESULTS_DIR / "_dev" if args.dev else RESULTS_DIR
        path = directory / f"{args.task}_extras.json"
        path.write_text(json.dumps(extras, indent=2, default=str), encoding="utf-8")
        log.info("wrote %s", path.relative_to(bc.PROJECT_ROOT))

    headline = [r for r in rows if r["group_key"] == "overall"
                and r["metric"] in ("auprc", "macro_auprc", "r_peak_f1", "mIoU")]
    for row in headline[:12]:
        log.info("%-28s %-12s %-22s %s=%.4f +/- %.4f  CI[%.4f, %.4f] (%s)",
                 row["arch_tier"], row["head"][:12], row["metric"], "value",
                 row["value_mean"], row["value_std"], row["ci_low"], row["ci_high"],
                 row["ci_method"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
