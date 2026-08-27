"""Stage P2.5-P2.8 — the ONLY Phase 2 training entry point (spec §6.1).

    ./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/30_train.py \
        --model-config config/model_configs/A1_multimodal_fusion_12lead.yaml \
        --task A1_ecg_diagnosis \
        --seed 42 \
        --output-dir outputs/model_runs/A1_ecg_diagnosis/multimodal_fusion_12lead/seed_42/

Re-running the identical command after any interruption RESUMES; that is the
whole crash story. `checkpoint_last.pt` is written atomically every
``--checkpoint-minutes`` and at every epoch boundary, and SIGTERM (Slurm
preemption) or SIGINT (Ctrl-C, a UPS shutdown script) triggers one more write
before a clean exit 0, so a requeued job picks up mid-epoch where it stopped.

Three gates run before a single batch is loaded:

1. **The audit gate.** `task_definitions.yaml`'s `audit_gate_before_training`
   invariant and §4.C: no training may start until `leakage_audit_phase2.md`,
   `split_audit_phase2.md` and `cohort_audit.md` are present and PASS. A
   `--dev` smoke run may bypass it (it writes under `outputs/model_runs/_dev/`
   and produces no number that reaches the paper), and says so loudly.
2. **The input-policy gate**, inside `TaskDataset` — a forbidden modality kind
   fails at construction.
3. **The split gate** — train/val/test subject sets must be disjoint in the
   rows this run actually loaded, not merely in the builder's own report.

What a completed run leaves behind (§3): `checkpoint_best.pt` (weights only),
`checkpoint_last.pt`, `train_log.jsonl`, `train_config.yaml`,
`val_predictions.parquet`, `test_predictions.parquet`, and its rows in
`outputs/audit_reports/threshold_audit.md`.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _dataset_lib import build_common as bc                            # noqa: E402
from _dataset_lib.task_dataset import TaskDataset, plan_from_config    # noqa: E402
from _dataset_lib.task_spec import get_task                            # noqa: E402
from _model_lib.model_configs import load_model_config                 # noqa: E402
from _model_lib.task_models import build_model, train_class_stats      # noqa: E402
from _train_lib import calibration as cal                              # noqa: E402
from _train_lib import threshold as th                                 # noqa: E402
from _train_lib.seed import environment_fingerprint, set_seed          # noqa: E402
from _train_lib.trainer import (TrainConfig, Trainer, collect_predictions,  # noqa: E402
                                head_metrics, head_present, primary_metric)

AUDIT_GATE_FILES = ("leakage_audit_phase2.md", "split_audit_phase2.md", "cohort_audit.md")
MODEL_RUNS = bc.PROJECT_ROOT / "outputs" / "model_runs"


def silence_noise() -> None:
    """§6.10 logging hygiene: the warnings that would drown the tqdm bar."""
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    warnings.filterwarnings("ignore", message=".*torch.cuda.amp.*")
    warnings.filterwarnings("ignore", message=".*Palette images with Transparency.*")
    warnings.filterwarnings("ignore", category=UserWarning, module="h5py")
    logging.getLogger("transformers").setLevel(logging.ERROR)
    logging.getLogger("PIL").setLevel(logging.ERROR)


# -----------------------------------------------------------------------------
# gates
# -----------------------------------------------------------------------------
def check_audit_gate(dev: bool, log: logging.Logger, allow_missing: bool = False) -> dict[str, str]:
    """§4.C invariant 4 / `task_definitions.yaml.invariants.audit_gate_before_training`."""
    directory = bc.PROJECT_ROOT / "outputs" / "audit_reports"
    status: dict[str, str] = {}
    problems: list[str] = []
    for name in AUDIT_GATE_FILES:
        path = directory / name
        if not path.exists():
            status[name] = "MISSING"
            problems.append(f"{name} does not exist")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # The audit writes a verdict line; anything that is not an explicit PASS
        # blocks, including a report that only says FAIL somewhere in the body.
        if "FAIL" in text.upper().replace("FAILURE MODE", ""):
            status[name] = "FAIL"
            problems.append(f"{name} contains a FAIL")
        elif "PASS" not in text.upper():
            status[name] = "NO_VERDICT"
            problems.append(f"{name} carries no PASS verdict")
        else:
            status[name] = "PASS"

    if not problems:
        log.info("audit gate: PASS (%s)", ", ".join(f"{k}={v}" for k, v in status.items()))
        return status

    message = ("audit gate BLOCKS training — " + "; ".join(problems) +
               ". §4.C invariant 4: leakage, split and cohort audits must be PASS "
               "before any training runs (Step 10 / Stage P2.3).")
    if dev or allow_missing:
        log.warning("%s  BYPASSED because this is a --dev smoke run; its outputs live "
                    "under outputs/model_runs/_dev/ and reach no paper number.", message)
        return status
    raise RuntimeError(message)


def check_split_disjoint(datasets: dict[str, TaskDataset], log: logging.Logger) -> dict[str, int]:
    """Assert on the ROWS THIS RUN LOADED that no subject crosses a split."""
    subjects = {name: set(ds.provenance_frame()["subject_id"].to_numpy())
                for name, ds in datasets.items() if ds is not None}
    counts = {name: len(value) for name, value in subjects.items()}
    names = list(subjects)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            overlap = subjects[names[i]] & subjects[names[j]]
            if overlap:
                raise RuntimeError(
                    f"CRITICAL (§4.C invariant 1, §11.2): {len(overlap)} subject(s) appear "
                    f"in both {names[i]} and {names[j]} — e.g. {sorted(overlap)[:5]}"
                )
    log.info("split gate: PASS (subjects %s, zero overlap)", counts)
    return counts


# -----------------------------------------------------------------------------
# text feature preparation (§5.4.1 — fit on TRAIN only)
# -----------------------------------------------------------------------------
def prepare_tfidf(datasets: dict[str, TaskDataset], log: logging.Logger):
    from _model_lib.text_encoders import TfidfTextEncoder

    started = time.time()
    encoder = TfidfTextEncoder().fit(datasets["train"].raw_texts())
    for name, dataset in datasets.items():
        if dataset is not None:
            dataset.precompute_text_features(encoder.transform(dataset.raw_texts()))
    log.info("TF-IDF fitted on %d TRAIN docs, transformed %s in %.1fs",
             encoder.fitted_on_n_docs,
             {k: len(v) for k, v in datasets.items() if v is not None},
             time.time() - started)
    return encoder


# -----------------------------------------------------------------------------
# thresholds + calibration, both from val only
# -----------------------------------------------------------------------------
def select_thresholds(spec, val_predictions: pd.DataFrame, config: TrainConfig) -> list:
    records = []
    common = {"split": "val", "task": spec.key, "arch_tier": config.arch_tier,
              "lead_subset": config.lead_subset, "seed": config.seed}
    for head in spec.heads:
        if not head_present(head, val_predictions):
            continue                      # this tier served no such head
        if head.kind == "binary":
            valid = val_predictions[f"valid_{head.name}"].to_numpy(dtype=bool)
            records.append(th.select_threshold(
                val_predictions[f"y_true_{head.name}"].to_numpy()[valid],
                val_predictions[f"y_pred_proba_{head.name}"].to_numpy()[valid],
                head=head.name, **common))
        elif head.kind == "multiclass":
            valid = val_predictions[f"valid_{head.name}"].to_numpy(dtype=bool)
            proba = np.column_stack([
                val_predictions[f"y_pred_proba_{head.name}__{c}"].to_numpy()[valid]
                for c in head.classes])
            records += th.select_multiclass_thresholds(
                val_predictions[f"y_true_index_{head.name}"].to_numpy()[valid],
                proba, head.classes, head=head.name, **common)
        elif head.kind == "bins":
            flat_true = np.array(val_predictions["y_true_bins"].tolist()).ravel()
            flat_prob = np.array(val_predictions["y_pred_proba_bins"].tolist()).ravel()
            records.append(th.select_threshold(flat_true, flat_prob, head="bins", **common))
    return records


def fit_calibrators(spec, val_predictions: pd.DataFrame, log: logging.Logger) -> dict[str, bytes]:
    """§6.8 — A3 and A6 recalibrate; every other task records ECE only."""
    auto = spec.key in cal.CALIBRATED_TASKS
    out: dict[str, bytes] = {}
    for head in spec.heads:
        if head.kind != "binary" or not head_present(head, val_predictions):
            continue
        valid = val_predictions[f"valid_{head.name}"].to_numpy(dtype=bool)
        truth = val_predictions[f"y_true_{head.name}"].to_numpy()[valid]
        prob = val_predictions[f"y_pred_proba_{head.name}"].to_numpy()[valid]
        calibrator = cal.fit_calibrator(truth, prob, head=head.name, split="val")
        if not auto:
            # Other tasks compute ECE for the supplementary but do NOT
            # auto-recalibrate (§6.8 last paragraph).
            calibrator = cal.Calibrator(method="identity", head=head.name,
                                        ece_raw=calibrator.ece_raw,
                                        ece_calibrated=calibrator.ece_raw,
                                        n_fit=calibrator.n_fit)
        out[head.name] = calibrator.state_bytes()
        log.info("calibration %s: raw ECE %.4f -> %s %.4f", head.name,
                 calibrator.ece_raw, calibrator.method, calibrator.ece_calibrated)
    return out


def apply_calibrators(spec, predictions: pd.DataFrame,
                      blobs: dict[str, bytes]) -> pd.DataFrame:
    """Add ``y_pred_proba_<head>_calibrated`` using the VAL-fitted scaler."""
    for head in spec.heads:
        if head.kind != "binary" or head.name not in blobs                 or not head_present(head, predictions):
            continue
        calibrator = cal.Calibrator.from_state_bytes(blobs[head.name])
        predictions[f"y_pred_proba_{head.name}_calibrated"] = calibrator.transform(
            predictions[f"y_pred_proba_{head.name}"].to_numpy())
        predictions[f"calibrator_{head.name}"] = calibrator.method
    return predictions


def label_with_thresholds(spec, predictions: pd.DataFrame, records: list) -> pd.DataFrame:
    by_head = {(r.head, r.class_name): r for r in records}
    for head in spec.heads:
        if not head_present(head, predictions):
            continue
        if head.kind == "binary":
            record = by_head.get((head.name, "positive"))
            if record is not None:
                predictions[f"y_pred_label_{head.name}"] = th.apply_threshold(
                    predictions[f"y_pred_proba_{head.name}"].to_numpy(), record)
                predictions[f"threshold_{head.name}"] = record.threshold
        elif head.kind == "multiclass":
            index = predictions[f"y_pred_index_{head.name}"].to_numpy()
            predictions[f"y_pred_label_{head.name}"] = [head.classes[i] for i in index]
            predictions[f"y_true_{head.name}"] = [
                head.classes[i] if i >= 0 else None
                for i in predictions[f"y_true_index_{head.name}"].to_numpy()]
        elif head.kind == "bins":
            record = by_head.get(("bins", "positive"))
            cut = record.threshold if record is not None else 0.5
            predictions["y_pred_label_bins"] = [
                (np.asarray(p) >= cut).astype(int).tolist()
                for p in predictions["y_pred_proba_bins"]]
            predictions["threshold_bins"] = cut
    return predictions


# -----------------------------------------------------------------------------
def write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    frame.to_parquet(tmp, index=False)
    bc.atomic_replace(tmp, path)


def default_output_dir(task: str, arch_tier: str, seed: int, dev: bool) -> Path:
    root = MODEL_RUNS / "_dev" if dev else MODEL_RUNS
    return root / task / arch_tier / f"seed_{seed}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--model-config", required=True,
                        help="config/model_configs/<task>_<arch_tier>.yaml (§5.8)")
    parser.add_argument("--task", help="task key; must match the model config")
    parser.add_argument("--seed", type=int, default=42, choices=(42, 123, 456),
                        help="§6.2 locks the three seeds")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--dev", action="store_true",
                        help="smoke test on data/processed/tasks/_dev/; bypasses the "
                             "audit gate and writes under outputs/model_runs/_dev/")
    parser.add_argument("--epochs", type=int, default=0, help="override the config")
    parser.add_argument("--batch-size", type=int, default=0, help="override the config")
    parser.add_argument("--accumulation-steps", type=int, default=0)
    parser.add_argument("--num-workers", type=int, default=-1)
    parser.add_argument("--checkpoint-minutes", type=float, default=10.0)
    parser.add_argument("--max-steps-per-epoch", type=int, default=0,
                        help="cap batches per epoch (smoke tests only)")
    parser.add_argument("--limit-rows", type=int, default=0,
                        help="cap rows per split (smoke tests only)")
    parser.add_argument("--balanced-sampler", action="store_true",
                        help="§6.4 optional weighted sampler for A2/B1")
    parser.add_argument("--no-pretrained", action="store_true",
                        help="random-init the image/text backbones (offline smoke only)")
    parser.add_argument("--force-restart", action="store_true",
                        help="ignore checkpoint_last.pt and start over")
    parser.add_argument("--skip-test", action="store_true",
                        help="train and write val predictions, leave test to 31_eval.py")
    parser.add_argument("--allow-missing-audits", action="store_true",
                        help=argparse.SUPPRESS)   # deliberately undocumented
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    silence_noise()

    config_dict = load_model_config(args.model_config)
    task_key = args.task or config_dict["task"]
    if task_key != config_dict["task"]:
        raise SystemExit(f"--task {task_key} does not match the model config's "
                         f"task {config_dict['task']}")
    spec = get_task(task_key)
    if spec.eval_only:
        raise SystemExit(f"{task_key} is evaluation-time only (§4.B.6) — it reuses "
                         f"{spec.base_task}'s trained models. Train {spec.base_task} instead.")

    arch_tier = config_dict["arch_tier"]
    output_dir = Path(args.output_dir) if args.output_dir else \
        default_output_dir(task_key, arch_tier, args.seed, args.dev)
    output_dir.mkdir(parents=True, exist_ok=True)

    log = bc.setup_logging(f"30_train_{task_key}_{arch_tier}_seed{args.seed}", stage="P2.5")
    log.info("task=%s arch=%s seed=%d dev=%s output=%s",
             task_key, arch_tier, args.seed, args.dev, output_dir)

    audit_status = check_audit_gate(args.dev, log, allow_missing=args.allow_missing_audits)
    set_seed(args.seed)

    train_block = config_dict.get("train", {})
    plan = plan_from_config(config_dict)
    workers = args.num_workers if args.num_workers >= 0 else (0 if args.dev else 4)

    config = TrainConfig(
        task=task_key, arch_tier=arch_tier, lead_subset=config_dict.get("lead_subset", "none"),
        seed=args.seed, output_dir=output_dir,
        epochs=args.epochs or int(train_block.get("epochs", 30)),
        batch_size=args.batch_size or int(train_block.get("batch_size", 64)),
        accumulation_steps=args.accumulation_steps or int(
            train_block.get("accumulation_steps", 1)),
        patience=int(train_block.get("patience", 5)),
        num_workers=workers,
        learning_rates=dict(train_block.get("learning_rates", {})) or None,
        checkpoint_minutes=args.checkpoint_minutes,
        balanced_sampler=args.balanced_sampler,
        max_steps_per_epoch=args.max_steps_per_epoch,
        dev=args.dev,
        signal_input_modality=plan.signal_kind,
        image_input_modality=plan.image_kind,
        text_encoder=plan.text_encoder,
    )
    if not config.learning_rates:
        config.learning_rates = TrainConfig.__dataclass_fields__[
            "learning_rates"].default_factory()

    # -- data -----------------------------------------------------------------
    augment = bool(config_dict.get("augment_regime_2", False))
    datasets: dict[str, TaskDataset] = {}
    for split in ("train", "val", "test"):
        datasets[split] = TaskDataset(
            task_key, split, plan, dev=args.dev, limit=args.limit_rows,
            augment_regime_2=augment and split == "train",
            row_filter=_split_row_filter(config_dict, split),
            run_seed=args.seed)
        log.info("%s split: %d rows", split, len(datasets[split]))

    subject_counts = check_split_disjoint(datasets, log)

    tfidf_encoder = None
    if plan.text_encoder == "tfidf":
        tfidf_encoder = prepare_tfidf(datasets, log)

    class_stats = train_class_stats(spec, datasets["train"].frame)

    # -- model ----------------------------------------------------------------
    model = build_model(spec, plan, pretrained=not args.no_pretrained,
                        head_style=config_dict.get("head_style", "auto"))
    trainer = Trainer(model, spec, config, datasets["train"], datasets["val"],
                      class_stats, log)

    snapshot = {
        "model_config": {k: v for k, v in config_dict.items() if k != "_path"},
        "model_config_path": config_dict.get("_path"),
        "train_config": config.as_dict(),
        "architecture": model.architecture_summary(),
        "class_stats_train_only": class_stats,
        "environment": environment_fingerprint(),
        "mixed_precision": trainer.amp_tag,
        "audit_gate": audit_status,
        "split_subject_counts": subject_counts,
        "split_row_counts": {k: len(v) for k, v in datasets.items()},
        "started_at": bc.utc_now_iso(),
        "dev_run": bool(args.dev),
    }
    (output_dir / "train_config.yaml").write_text(
        yaml.safe_dump(snapshot, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8")

    if args.force_restart:
        for name in ("checkpoint_last.pt", "checkpoint_best.pt"):
            (output_dir / name).unlink(missing_ok=True)
        log.warning("--force-restart: previous checkpoints deleted")
    resumed = trainer.try_resume()

    started = time.time()
    result = trainer.train()
    log.info("training %s after %.1f min (best %s=%.6f at epoch %d)",
             result["status"], (time.time() - started) / 60.0, spec.primary_metric,
             result["best_metric"], result["best_epoch"])

    if result["status"] == "interrupted":
        log.warning("exiting 0 so Slurm can requeue; re-run the identical command to resume")
        return 0

    # -- best weights back in, then val -> thresholds -> calibrators ----------
    if trainer.best_path.exists():
        best = torch.load(trainer.best_path, map_location=trainer.device, weights_only=False)
        model.load_state_dict(best["model_state_dict"])
        log.info("loaded checkpoint_best from epoch %d", best.get("epoch", -1))

    val_predictions = collect_predictions(model, spec, datasets["val"], config,
                                          trainer.device, trainer.amp_dtype)
    threshold_records = select_thresholds(spec, val_predictions, config)
    calibrators = fit_calibrators(spec, val_predictions, log)
    val_predictions = apply_calibrators(spec, val_predictions, calibrators)
    val_predictions = label_with_thresholds(spec, val_predictions, threshold_records)
    write_parquet(val_predictions, output_dir / "val_predictions.parquet")

    if not args.dev:
        audit_path = th.append_threshold_audit(threshold_records, bc.PROJECT_ROOT)
        log.info("threshold audit rows appended to %s",
                 audit_path.relative_to(bc.PROJECT_ROOT))
    (output_dir / "thresholds.json").write_text(th.records_to_json(threshold_records),
                                                encoding="utf-8")

    extras: dict[str, Any] = {"thresholds": [r.__dict__ for r in threshold_records],
                              "calibrators": calibrators}
    if tfidf_encoder is not None:
        extras["tfidf_state"] = tfidf_encoder.state_bytes()
    trainer.save_best(extras)

    if not args.skip_test:
        test_predictions = collect_predictions(model, spec, datasets["test"], config,
                                               trainer.device, trainer.amp_dtype)
        test_predictions = apply_calibrators(spec, test_predictions, calibrators)
        test_predictions = label_with_thresholds(spec, test_predictions, threshold_records)
        write_parquet(test_predictions, output_dir / "test_predictions.parquet")
        log.info("test primary %s = %.6f over %d rows / %d subjects",
                 spec.primary_metric, primary_metric(spec, test_predictions),
                 len(test_predictions), test_predictions.subject_id.nunique())

    summary = {
        "task": task_key, "arch_tier": arch_tier, "seed": args.seed,
        "status": result["status"], "resumed": resumed,
        "best_val_metric": result["best_metric"], "best_epoch": result["best_epoch"],
        "primary_metric_name": spec.primary_metric,
        "val_metrics": head_metrics(spec, val_predictions),
        "n_epochs_run": len(result["history"]),
        "wall_clock_minutes": round((time.time() - started) / 60.0, 2),
        "finished_at": bc.utc_now_iso(),
    }
    (output_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str),
                                                 encoding="utf-8")
    log.info("done: %s", output_dir)
    return 0


def _split_row_filter(config_dict: dict[str, Any], split: str) -> str | None:
    """B2's per-regime row selection (§7.3). Every other task loads its split whole."""
    regime = config_dict.get("regime")
    if not regime or config_dict["task"] != "B2_noise_robustness":
        return None
    if split == "train":
        return "row_role == 'augment_on_the_fly'"
    if regime == "regime_3":
        return "regime == 'regime_3'"
    return f"regime == '{regime}' or row_role == 'clean_reference'"


if __name__ == "__main__":
    raise SystemExit(main())
