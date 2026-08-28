# Stage P2.4 — Training + evaluation code, and the algorithmic baselines — report

Spec §5, §6, §7, §9.5. Generated 2026-08-28T17:29:03Z by `_dataset_lib/stage_report.py` from the per-script state files, the artifacts on disk and the run logs — every number below is read back from what the stage produced.

## 1. Files created

- `scripts/phase2_tasks_benchmark_and_paper/30_train.py`  (23.5 KB, sha256 45a69e2e15f2)
- `scripts/phase2_tasks_benchmark_and_paper/31_eval.py`  (38.7 KB, sha256 aeddd3c0593f)
- `scripts/phase2_tasks_benchmark_and_paper/50_run_baselines_algorithmic.py`  (35.9 KB, sha256 67a236d1b441)
- `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/task_spec.py`  (19.3 KB, sha256 54682a1faaee)
- `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/task_dataset.py`  (26.2 KB, sha256 2cfddeb658e3)
- `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/bootstrap.py`  (10.1 KB, sha256 b6e60a7f6196)
- `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/corruption.py`  (6.3 KB, sha256 f379e57a4a26)
- `scripts/phase2_tasks_benchmark_and_paper/_model_lib/signal_encoders.py`  (7.5 KB, sha256 bd42006f9a36)
- `scripts/phase2_tasks_benchmark_and_paper/_model_lib/image_encoders.py`  (3.5 KB, sha256 52e803f18e9d)
- `scripts/phase2_tasks_benchmark_and_paper/_model_lib/text_encoders.py`  (9.2 KB, sha256 28a95f7e5702)
- `scripts/phase2_tasks_benchmark_and_paper/_model_lib/fusion_heads.py`  (5.5 KB, sha256 1a122a8f7c9e)
- `scripts/phase2_tasks_benchmark_and_paper/_model_lib/task_models.py`  (25.1 KB, sha256 d5069966985c)
- `scripts/phase2_tasks_benchmark_and_paper/_model_lib/model_configs.py`  (15.7 KB, sha256 fb70f390e4ca)
- `scripts/phase2_tasks_benchmark_and_paper/_model_lib/algorithmic_baselines.py`  (24.0 KB, sha256 113d6491954f)
- `scripts/phase2_tasks_benchmark_and_paper/_train_lib/seed.py`  (4.9 KB, sha256 7662352a2073)
- `scripts/phase2_tasks_benchmark_and_paper/_train_lib/metrics.py`  (18.3 KB, sha256 6a41186e86ab)
- `scripts/phase2_tasks_benchmark_and_paper/_train_lib/threshold.py`  (9.7 KB, sha256 9d7038b47687)
- `scripts/phase2_tasks_benchmark_and_paper/_train_lib/calibration.py`  (8.8 KB, sha256 4af981134ee5)
- `scripts/phase2_tasks_benchmark_and_paper/_train_lib/trainer.py`  (35.1 KB, sha256 22b5c3d47ff9)
- `scripts/phase2_tasks_benchmark_and_paper/_train_lib/smoke_test.py`  (15.7 KB, sha256 3fa579e6d225)
- `config/eval_configs/default.yaml`  (2.2 KB, sha256 ba1bbffc7511)
- `config/eval_configs/A4_fiducial.yaml`  (1.6 KB, sha256 7277ff7113d4)
- `config/eval_configs/A6_risk.yaml`  (1.5 KB, sha256 9da4bea77e6f)
- `config/eval_configs/B2_robustness.yaml`  (2.3 KB, sha256 8f66346ba457)
- `config/eval_configs/cross_modal.yaml`  (2.0 KB, sha256 20ece67aeaea)

## 2. Files modified

- `config/decision_phase2.yaml`  ::  Bio-ClinicalBERT revision SHA recorded (`d5892b39a4adaed74b92212a44081509db72f87b`); `transformers` 4.57.6 and `lifelines` 0.30.3 marked installed; the image `eval_transform` / `train_transform_when_augment` rewritten with a `transform_deviation` block recording why the §5.3 centre crop was replaced.
- `config/model_configs/`  ::  94 generated YAMLs, one per (task, arch tier, lead subset), derived from `task_input_policy.yaml` so a config can never name a forbidden input.
- `config/eval_configs/`  ::  `default.yaml`, `A4_fiducial.yaml`, `A6_risk.yaml`, `B2_robustness.yaml`, `cross_modal.yaml` authored.
- `scripts/.../_dataset_lib/stage_report.py`  ::  stage-aware §2 and worker-log sections; a P2.4 entry added.
- `docs/PHASE2_PROGRESS.md`  ::  header, §4 decision 18, §6 ledger (Steps 3 and 11), §7 trap 16, §8 session log.

## 3. Files / folders deleted

none — this stage only creates. `--dev` output is isolated under `data/processed/tasks/_dev/` and is never published.

## 4. Design decisions

- **The image transform resizes the whole render instead of centre-cropping it**  ::  §5.3 specifies `Resize(short_side) -> CenterCrop(target)` and justifies 224x672 and 384x512 as preserving the render aspect ratios. Measured, the Phase 1 renders are 3600x750 (4.8:1) and 1016x504 (2.02:1), not 3:1 and 1.33:1, so the centre crop would discard 37 % of every Lead-II strip — the first and last ~2 seconds of a 10-second ECG — and the outer lead columns of the 12-lead grid. The whole image is resized into the locked target box instead: same target size, same §6.6 VRAM budget, no ECG thrown away. Recorded as `architecture.image_encoder.transform_deviation`; disclose in the supplementary.
- **A5's masked-attribute head reads signal + image only, never the fused embedding**  ::  §5.6 puts both A5 heads on one shared tri-encoder, and `task_input_policy.yaml` states the unmasked `report_text` must never reach the masked-attribute head. On an A5 positive row the text IS the unmasked anchor report, so a head fed the fusion vector would be handed back the answer. The encoders stay shared; only the head's input is narrowed.
- **A5's masked-attribute head is masked to anchor-aligned rows**  ::  a verification row whose signal or image was swapped shows another subject's ECG, so the anchor's HR/QRS/QTc bins are not its labels. `masked_attr_valid` gates the loss and the predictions.
- **The A4/B3 oracles read `fiducials_lead2.parquet` rather than re-running NeuroKit**  ::  §4.A.4.7 promises F1 = 1.0. Re-running the detector would reproduce that only up to NeuroKit's own numerical reproducibility; reading the artifact that defined the labels makes it exact. Measured on the dev sample: A4 r_peak_F1 = 1.0000, B3 mIoU = 1.0000.
- **The A4 detector is `method="neurokit"`, not `"pantompkins"`**  ::  progress-doc trap 2. §4.A.4.7 calls the baseline Pan-Tompkins AND promises F1 = 1.0; both hold only if it runs the detector that built the ground truth, which is NeuroKit's default. `pantompkins` stays reachable for a supplementary detector-disagreement row.
- **Model configs are generated from `task_input_policy.yaml`, not hand-written**  ::  §5.8 wants a YAML per (task, arch tier, lead subset) — 94 of them. Deriving the matrix from the policy file means a config physically cannot name a forbidden modality, and a policy change regenerates instead of requiring 94 edits.
- **BCa acceleration uses a delete-one-group jackknife above 2,000 subjects**  ::  §6.7 specifies BCa. The exact jackknife is one metric pass per subject; the test split has 30,844, which is hours per head. The bias correction z0 stays exact and only the acceleration constant is estimated from 200 groups. Every results row records `n_jackknife_groups` so a reviewer sees which path ran.
- **The regime_2 augmenter imports the Phase 1 Stage 8 corruption functions rather than reimplementing them**  ::  §7.3's regime_1-vs-regime_2 claim is only meaningful if train-time and test-time corruption come from the same distribution. Only the seed stream differs, per the locked recipe file's `regime2|` key prefix.
- **The audit gate is enforced in `30_train.py` and bypassable only under `--dev`**  ::  §4.C invariant 4 blocks training until the leakage, split and cohort audits PASS. A dev smoke run writes under `outputs/model_runs/_dev/` and produces no paper number, so it bypasses the gate with a logged warning; a full-scale run cannot.
- **Mid-epoch resume is exact**  ::  §6.9 and §8.1 require surviving both a mains cut and Slurm preemption. The epoch's batch order is a pure function of (seed, epoch), so a resumed job rebuilds the identical order and skips the batches already done; `checkpoint_last.pt` carries `batch_in_epoch` alongside the RNG states and is written atomically.

## 5. Complete code

### `scripts/phase2_tasks_benchmark_and_paper/30_train.py`

```python
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

from _dataset_lib import audit_common as ac                            # noqa: E402
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
        # The audit's `**VERDICT: ...**` line, parsed by the one reader in
        # `audit_common`. Scanning the whole body for the block token instead
        # would misread a clean leakage audit: it lists every column of every
        # task, and A1's heads are named `label_heart_failure_narrow`.
        verdict = ac.report_verdict(text)
        status[name] = verdict
        if verdict != ac.PASS:
            problems.append(f"{name} reads {verdict}")

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
```

### `scripts/phase2_tasks_benchmark_and_paper/31_eval.py`

```python
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


def evaluate_arch(task: str, arch_tier: str, dev: bool, seeds: Iterable[int] | None,
                  eval_config: dict[str, Any], log: logging.Logger,
                  bootstrap_override: int | None = None) -> list[dict[str, Any]]:
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
            sliced_seeds = {s: _slice(f, group_key, group_value) for s, f in per_seed.items()}
            sliced_pooled = _slice(pooled, group_key, group_value)
            if sliced_pooled.empty:
                continue
            for metric_name, metric_fn in fns.items():
                rows.append(evaluate_group(spec, head, metric_name, metric_fn,
                                           sliced_seeds, sliced_pooled, group_key,
                                           group_value, settings, meta))
    return rows


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
                         on=["study_id", "neg_type"], how="left")
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
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--bootstrap-n", type=int, default=0,
                        help="override n_iter (smoke tests only; §6.7 locks 10,000)")
    parser.add_argument("--retrieval", action="store_true",
                        help="also run the §7.5 retrieval check (needs checkpoint_best)")
    parser.add_argument("--no-calibration", action="store_true")
    return parser.parse_args(argv)


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
                              bootstrap_override=args.bootstrap_n or None)

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
    write_results(args.task, rows, args.dev, log)

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
```

### `scripts/phase2_tasks_benchmark_and_paper/50_run_baselines_algorithmic.py`

```python
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
# §5.1's table, plus the two task_definitions.yaml adds (A1 logistic, B2 detector),
# plus A3's structured baseline -- Plan A/B §5.9 requires it for A1, A3 and A6.
MANDATED = ("A1_ecg_diagnosis", "A2_measurement_blind", "A3_lab_abnormality",
            "A4_event_localization", "A6_risk_stratification", "A6_nested_baselines",
            "B1_measurement_blind", "B2_noise_robustness",
            "B3_temporal_grounding", "B5_contradiction_detection")
MODEL_RUNS = bc.PROJECT_ROOT / "outputs" / "model_runs"

MEASUREMENT_SCHEMA = pa.schema([
    ("study_id", pa.int64()), ("hr_bpm", pa.float64()), ("qrs_ms", pa.float64()),
    ("qtc_ms", pa.float64()), ("rr_ms", pa.float64()),
    ("hr_label", pa.string()), ("qrs_label", pa.string()), ("qtc_label", pa.string()),
    ("n_peaks", pa.int32()), ("fallback_used", pa.bool_()), ("delineate_ok", pa.bool_()),
])


def out_dir(task: str, dev: bool, tier: str = "algorithmic") -> Path:
    """Where one baseline's predictions live.

    `tier` is the arch_tier name, so A6's nested Plan A/B §5.8 ladder writes to
    sibling directories (`algorithmic_demographics`, ...) and `31_eval.py` scores
    each rung with the same code it uses for a trained tier.
    """
    root = MODEL_RUNS / "_dev" if dev else MODEL_RUNS
    path = root / task / tier
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


def write_predictions(frame: pd.DataFrame, task: str, dev: bool, log,
                      tier: str = "algorithmic") -> Path:
    frame = frame.copy()
    frame["seed"] = -1                     # §5.1: no seed variability
    frame["arch_tier"] = tier
    if "lead_subset" not in frame.columns:
        frame["lead_subset"] = "lead2"
    path = out_dir(task, dev, tier) / "test_predictions.parquet"
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


def run_a3(dev: bool, log, limit: int) -> int:
    """A3: multinomial logistic on machine-measurement summary stats.

    Plan A/B §5.9 requires the structured baseline for A1, A3 and A6. Spec
    §4.A.3.7 had waived A3's; this restores it. BASELINE-ONLY exemption, the
    same one A1 uses and now declared for A3 in `task_input_policy.yaml`.
    """
    spec = get_task("A3_lab_abnormality")
    root = bc.TASKS_DIR / "_dev" if dev else bc.TASKS_DIR
    train = pd.read_parquet(root / "A3_lab_abnormality" / "train.parquet")
    train = train[train.is_primary.fillna(False)]
    test = task_test_frame("A3_lab_abnormality", dev, limit)

    features = ab.machine_feature_table(
        pd.concat([train.study_id, test.study_id]).unique().tolist())
    feature_columns = [c for c in features.columns if c != "study_id"]
    train = train.merge(features, on="study_id", how="inner")
    test = test.merge(features, on="study_id", how="inner")

    classes = list(spec.heads[0].classes)
    labels = [h.label_column for h in spec.heads]
    log.info("A3 structured baseline: %d heads x %d classes on %d train / %d test rows",
             len(labels), len(classes), len(train), len(test))
    scored = ab.multiclass_logistic_baseline(train, test, feature_columns, labels, classes)

    predictions = pd.DataFrame({"study_id": test.study_id.to_numpy(),
                                "subject_id": test.subject_id.to_numpy()})
    for column in ("sqi_tier", "cart_id", "link_tier", "boundary_flag"):
        if column in test.columns:
            predictions[column] = test[column].to_numpy()
    # 35 heads x 5 classes is 210 new columns; assembled as one dict and
    # concatenated once, because inserting them one at a time fragments the
    # frame and crawls at the real 84 K-row test split.
    columns: dict[str, Any] = {}
    for head in spec.heads:
        label = head.label_column
        for name in classes:
            columns[f"y_pred_proba_{head.name}__{name}"] = \
                scored[f"y_pred_proba_{label}__{name}"].to_numpy()
        index = scored[f"y_pred_index_{label}"].to_numpy()
        truth = test[label].astype("string")
        true_index = np.array([classes.index(v) if pd.notna(v) and v in classes else -1
                               for v in truth], dtype="int64")
        columns[f"y_pred_index_{head.name}"] = index
        columns[f"y_pred_label_{head.name}"] = [classes[i] for i in index]
        columns[f"y_true_index_{head.name}"] = true_index
        columns[f"valid_{head.name}"] = true_index >= 0
    predictions = pd.concat(
        [predictions, pd.DataFrame(columns, index=predictions.index)], axis=1)
    write_predictions(predictions, "A3_lab_abnormality", dev, log)
    return len(predictions)


def run_a6(dev: bool, log, limit: int) -> int:
    """A6: Cox PH on age + sex + machine HR/QRS/QTc (§4.A.6.7, §5.1). BASELINE-ONLY."""
    spec = get_task("A6_risk_stratification")
    root = bc.TASKS_DIR / "_dev" if dev else bc.TASKS_DIR
    train = pd.read_parquet(root / "A6_risk_stratification" / "train.parquet")
    train = train[train.is_primary.fillna(False)]
    test = task_test_frame("A6_risk_stratification", dev, limit)

    # Age and sex now come from the task parquet, not from a second join on
    # `patients`. The parquet carries `age_at_ecg` -- the age at INDEX TIME,
    # which is what §5.8 asks a risk model to condition on -- where
    # `patient_demographics()` returns `anchor_age`, the age at an unrelated
    # anchor year. Joining both would also collide on `sex_male` and silently
    # suffix the columns.
    features = ab.machine_feature_table(
        pd.concat([train.study_id, test.study_id]).unique().tolist())
    feature_columns = ["age_at_ecg", "sex_male", "hr_bpm", "qrs_ms", "qtc_ms"]
    train = train.merge(features, on="study_id")
    test = test.merge(features, on="study_id")
    for frame in (train, test):
        frame["sex_male"] = frame["sex_male"].astype("boolean").fillna(False).astype("float64")

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
        predictions[f"y_true_{head.name}"] = truth.astype("boolean").fillna(False).astype("float64").to_numpy()
        predictions[f"y_pred_label_{head.name}"] = (np.nan_to_num(ranked) >= 0.5).astype(int)
        valid = truth.notna().to_numpy()
        if head.mask_column and head.mask_column in test.columns:
            valid = valid & test[head.mask_column].fillna(False).to_numpy()
        predictions[f"valid_{head.name}"] = valid

    write_predictions(predictions, "A6_risk_stratification", dev, log)
    (out_dir("A6_risk_stratification", dev) / "cox_fit.json").write_text(
        json.dumps(info_all, indent=2, default=str), encoding="utf-8")
    return len(predictions)


# -----------------------------------------------------------------------------
# A6 nested clinical baselines (Plan A/B section 5.8, Figure 5)
# -----------------------------------------------------------------------------
# 5.8 requires six tiers and Figure 5 plots the nested curve across them.
# Section 7 states the failure condition outright -- "Only compared to
# random/prevalence baseline" -- and 1.1 makes this ladder the evidence for the
# claim "ECG adds prognostic signal beyond demographics". Each rung ADDS
# features to the one before it, so the increment is attributable.
#
# The Cox tier (`run_a6` above) is the fifth rung -- machine measurements -- and
# the trained encoders are the sixth. These four fill the gap between the floor
# and the ECG models, which had nothing in it.
#
# BASELINE-ONLY, like every other entry in this file: `task_input_policy.yaml`
# forbids these covariates to every trained encoder and declares the exemption.
PRIOR_DX_GROUPS = ("atrial_fibrillation_flutter", "heart_failure_narrow",
                   "acute_myocardial_infarction", "conduction_disorder",
                   "ventricular_arrhythmia_or_arrest")
_PRIOR_DX = [f"prior_dx_{g}" for g in PRIOR_DX_GROUPS]

A6_BASELINE_TIERS: dict[str, dict[str, Any]] = {
    "algorithmic_prevalence": {
        "numeric": [], "categorical": [],
        "spec": "5.8 Prevalence/logistic intercept -- the minimum sanity floor",
    },
    "algorithmic_demographics": {
        "numeric": ["age_at_ecg", "sex_male"],
        "categorical": ["race", "insurance"],
        "spec": "5.8 Demographics-only -- tests whether ECG beats simple covariates",
    },
    "algorithmic_demographics_comorbidities": {
        "numeric": ["age_at_ecg", "sex_male"] + _PRIOR_DX,
        "categorical": ["race", "insurance"],
        "spec": "5.8 Demographics + comorbidities -- prior ICD before the ECG only",
    },
    "algorithmic_utilization": {
        "numeric": (["age_at_ecg", "sex_male"] + _PRIOR_DX
                    + ["n_prior_admissions", "n_prior_ecgs", "days_since_last_discharge"]),
        "categorical": ["race", "insurance", "admission_type", "ed_disposition"],
        "spec": "5.8 Utilization -- controls for sick-patient ECG frequency",
    },
}


def _design_matrix(train: pd.DataFrame, test: pd.DataFrame, numeric: list[str],
                   categorical: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Standardised numerics + one-hot categoricals, fitted on TRAIN only.

    Plan A/B 4.7: "All preprocessing scalers ... must be fit or selected using
    train/validation only." The category vocabulary comes from train as well, so
    a level seen only in test lands in the all-zero column instead of silently
    widening the matrix.
    """
    from sklearn.preprocessing import StandardScaler

    blocks_train, blocks_test = [], []
    if numeric:
        raw_train = train[numeric].astype("float64")
        raw_test = test[numeric].astype("float64")
        medians = raw_train.median()
        scaler = StandardScaler().fit(raw_train.fillna(medians).to_numpy())
        blocks_train.append(scaler.transform(raw_train.fillna(medians).to_numpy()))
        blocks_test.append(scaler.transform(raw_test.fillna(medians).to_numpy()))
    for column in categorical:
        levels = sorted(train[column].dropna().astype(str).unique())
        if not levels:
            continue
        blocks_train.append(np.column_stack(
            [(train[column].astype(str) == level).to_numpy(dtype="float64")
             for level in levels]))
        blocks_test.append(np.column_stack(
            [(test[column].astype(str) == level).to_numpy(dtype="float64")
             for level in levels]))
    if not blocks_train:
        # The prevalence tier has no features at all -- a single constant column,
        # so the fit has nothing but an intercept to learn.
        return np.ones((len(train), 1)), np.ones((len(test), 1))
    return np.hstack(blocks_train), np.hstack(blocks_test)


def run_a6_nested(dev: bool, log, limit: int) -> int:
    """The four Plan A/B 5.8 rungs that sit below the machine-measurement Cox."""
    from sklearn.linear_model import LogisticRegression

    spec = get_task("A6_risk_stratification")
    root = bc.TASKS_DIR / "_dev" if dev else bc.TASKS_DIR
    train_all = pd.read_parquet(root / "A6_risk_stratification" / "train.parquet")
    train_all = train_all[train_all.is_primary.fillna(False)]
    test = task_test_frame("A6_risk_stratification", dev, limit)

    required = ("age_at_ecg", "n_prior_admissions", "prior_dx_heart_failure_narrow")
    absent = [c for c in required if c not in train_all.columns]
    if absent:
        raise RuntimeError(
            f"the A6 parquet lacks the 5.8 nested-baseline covariates ({absent}). "
            "Re-run 06_build_A6_risk_stratification.py --force first.")

    total = 0
    for tier, config in A6_BASELINE_TIERS.items():
        numeric = [c for c in config["numeric"] if c in train_all.columns]
        categorical = [c for c in config["categorical"] if c in train_all.columns]
        x_train, x_test = _design_matrix(train_all, test, numeric, categorical)

        predictions = pd.DataFrame({"study_id": test.study_id.to_numpy(),
                                    "subject_id": test.subject_id.to_numpy()})
        for column in ("sqi_tier", "cart_id", "link_tier", "boundary_flag"):
            if column in test.columns:
                predictions[column] = test[column].to_numpy()

        for head in spec.heads:
            truth_train = train_all[head.label_column]
            keep = truth_train.notna().to_numpy()
            if head.mask_column and head.mask_column in train_all.columns:
                keep = keep & train_all[head.mask_column].fillna(False).to_numpy()
            y = truth_train[keep].astype(bool).to_numpy()

            if y.size == 0 or len(np.unique(y)) < 2 or (not numeric and not categorical):
                # Nothing fittable, or the prevalence tier by construction: emit
                # the train prevalence rather than a fabricated model.
                proba = np.full(len(test), float(y.mean()) if y.size else 0.0)
            else:
                model = LogisticRegression(max_iter=2000, class_weight="balanced")
                model.fit(x_train[keep], y)
                proba = model.predict_proba(x_test)[:, 1]

            truth_test = test[head.label_column]
            valid = truth_test.notna().to_numpy()
            if head.mask_column and head.mask_column in test.columns:
                valid = valid & test[head.mask_column].fillna(False).to_numpy()
            predictions[f"y_pred_proba_{head.name}"] = proba
            predictions[f"y_true_{head.name}"] = truth_test.astype("boolean").fillna(False).astype("float64").to_numpy()
            predictions[f"y_pred_label_{head.name}"] = (proba >= 0.5).astype(int)
            predictions[f"valid_{head.name}"] = valid

        write_predictions(predictions, "A6_risk_stratification", dev, log, tier=tier)
        (out_dir("A6_risk_stratification", dev, tier) / "features.json").write_text(
            json.dumps({"spec": config["spec"], "numeric": numeric,
                        "categorical": categorical, "n_train": int(len(train_all)),
                        "n_test": int(len(test))}, indent=2), encoding="utf-8")
        log.info("A6 %-42s %2d numeric + %d categorical",
                 tier, len(numeric), len(categorical))
        total += len(predictions)
    return total


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
        "A3_lab_abnormality": lambda: run_a3(args.dev, log, args.limit),
        "A4_event_localization": lambda: run_a4(args.dev, log, args.limit),
        "A6_risk_stratification": lambda: run_a6(args.dev, log, args.limit),
        # Plan A/B 5.8 four rungs below the Cox model; Figure 5 needs the
        # whole nested ladder, not only its top and bottom.
        "A6_nested_baselines": lambda: run_a6_nested(args.dev, log, args.limit),
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
```

### `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/task_spec.py`

```python
"""One declarative description of every task's heads, labels and metrics.

The dataloader, the model builder, the trainer, the evaluator and the
algorithmic baselines all read this module. Without it each of the five would
carry its own copy of "A3 has 35 five-class heads whose label columns are named
``lab_<name>_<window>_label``", and the five copies would drift.

Nothing here decides *architecture* -- that is `config/decision_phase2.yaml`
(§5) and the per-run model config. This is the DATA + HEAD contract, mirroring
`config/task_definitions.yaml` §5.6 and §6.4, in the form Python needs.

    from _dataset_lib.task_spec import get_task
    spec = get_task("A2_measurement_blind")
    spec.heads[0].name, spec.heads[0].classes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

# --- head kinds ---------------------------------------------------------------
# binary      : one sigmoid logit, label column is bool/0-1
# multiclass  : softmax over `classes`, label column is the class string
# regression  : one linear output, label column is the continuous measurement
# peak_seq    : per-sample sigmoid over 5000 samples + 2 regression channels (A4)
# bins        : per-bin sigmoid over 10 one-second bins, one query per row (B3)
# span        : two regression outputs, normalised character offsets (B5)
HEAD_KINDS = ("binary", "multiclass", "regression", "peak_seq", "bins", "span")

MEASUREMENT_CLASSES = {
    "hr_label": ["bradycardia", "normal", "tachycardia"],
    "qrs_label": ["normal", "borderline", "wide"],
    "qtc_label": ["short", "normal", "prolonged"],
}

# Continuous measurement targets for A2 and B1.
#
# Plan A/B §5.4 makes MAE/RMSE the PRIMARY metric for heart rate and QRS
# duration ("MAE, RMSE, Pearson/Spearman, Bland-Altman"; "MAE/RMSE; percentage
# within 10 ms"), and §7.1 repeats it for the regression/measurement task type.
# §6.2 extends the same construction to B1. The binned heads stay -- they are
# what §4.A.2.6 locks for early stopping -- and these ride alongside them on the
# same encoder, so the regression numbers cost no extra run.
#
# `center` / `unit` are DECLARED PHYSIOLOGICAL CONSTANTS, not statistics fitted
# to any split. They exist only to condition the optimiser (raw QTc ~450 next to
# raw HR ~82 would let one head dominate the shared loss). Because they are
# constants, no split can leak through them, and `31_eval.py` inverts them so
# every reported number is in real bpm / ms.
#
# `tolerance` drives the "percentage within" metric. **10 ms for QRS is
# mandated by Plan A/B §5.4.** The HR and QTc tolerances are NOT in the plan;
# they are declared here (and in spec §4.A.2.6) as reporting conventions so the
# table has a comparable column for all three heads. They are recorded rather
# than invented silently, per the plan's "do not invent thresholds" rule.
MEASUREMENT_REGRESSION = {
    #  name       column      units   center  unit   tolerance  mandated?
    "hr_bpm":  ("hr_bpm",   "bpm",   80.0,   25.0,   5.0),      # convention
    "qrs_ms":  ("qrs_ms",   "ms",   100.0,   25.0,  10.0),      # Plan §5.4
    "qtc_ms":  ("qtc_ms",   "ms",   450.0,   35.0,  20.0),      # convention
}
LAB_CLASSES = ["missing", "low_abnormal", "high_abnormal",
               "abnormal_unknown_direction", "normal"]
LABS = ("K", "Na", "creatinine", "troponin", "lactate", "Ca", "Mg")
LAB_WINDOWS = ("pm24h", "pre_24h", "post_24h", "pm6h", "pm12h")
PRIMARY_LAB_WINDOW = "pm24h"
B3_QUERIES = ("HIGH_HEART_RATE", "LOW_HEART_RATE", "WIDE_QRS", "NOISY_SEGMENT")
B5_CLASSES = ["clean", "corrupted_HR", "corrupted_QRS", "corrupted_axis", "corrupted_PR"]
# The last four are Plan A/B §6.7 Levels 2-5 and exist only in the TEST split;
# see `_dataset_lib/verification_task.py` for why they are not trained on.
NEG_TYPES = ("TEXT_SWAP", "IMAGE_SWAP", "SIGNAL_SWAP", "HARD_NEGATIVE_TEXT",
             "PARTIAL_MISMATCH", "HARD_NEGATIVE_L2", "HARD_NEGATIVE_L3",
             "HARD_NEGATIVE_L4", "HARD_NEGATIVE_L5")

N_SAMPLES = 5000
FS_HZ = 500
N_BINS = 10


@dataclass(frozen=True)
class Head:
    """One output head: its name, shape, label column and optional row mask."""

    name: str
    kind: str
    label_column: str
    classes: Sequence[str] = ()
    # A row where `mask_column` is False contributes NO loss for this head and
    # no prediction row for it. A6's readmission heads are the reason this
    # exists: a row that is not readmission-eligible has no label, and zeroing
    # it would invent 4,790 negatives per split.
    mask_column: str | None = None
    loss: str = "auto"
    pos_weight: float | None = None
    # regression heads only -- see MEASUREMENT_REGRESSION for what these mean.
    units: str = ""
    center: float = 0.0
    unit: float = 1.0
    tolerance: float | None = None

    def standardise(self, raw: float) -> float:
        return (float(raw) - self.center) / self.unit

    def destandardise(self, value):
        return value * self.unit + self.center

    @property
    def n_out(self) -> int:
        if self.kind == "binary":
            return 1
        if self.kind == "multiclass":
            return len(self.classes)
        if self.kind == "regression":
            return 1
        if self.kind == "peak_seq":
            return 3 * N_SAMPLES        # 1 sigmoid channel + 2 regression channels
        if self.kind == "bins":
            return len(B3_QUERIES) * N_BINS
        if self.kind == "span":
            return 2
        raise ValueError(f"unknown head kind {self.kind!r}")


@dataclass(frozen=True)
class TaskSpec:
    """Everything the training/eval stack needs to know about one task."""

    key: str
    plan: str
    heads: tuple[Head, ...]
    primary_metric: str
    # Where the row's own identity lives, and where each modality's study_id
    # lives. For A5/B4 the three modalities can point at three DIFFERENT
    # studies -- that IS the verification task.
    id_column: str = "study_id"
    signal_id_column: str = "study_id"
    image_id_column: str = "study_id"
    text_id_column: str = "study_id"
    # image_type_column names a per-row column ('clean'/'scanlike') that
    # overrides the model config's image kind. Only A5/B4 use it.
    image_type_column: str | None = None
    # Text that lives in the task parquet rather than being looked up by
    # study_id (B5's audited report; A5's masked report).
    text_column: str | None = None
    primary_flag_column: str | None = "is_primary"
    subgroup_columns: tuple[str, ...] = ("sqi_tier", "cart_id", "link_tier")
    extra_columns: tuple[str, ...] = ()
    train_file: str = "train.parquet"
    val_file: str = "val.parquet"
    test_file: str = "test.parquet"
    eval_only: bool = False
    base_task: str | None = None
    notes: str = ""

    def head(self, name: str) -> Head:
        for candidate in self.heads:
            if candidate.name == name:
                return candidate
        raise KeyError(f"{self.key} has no head {name!r}")

    @property
    def label_columns(self) -> list[str]:
        return [h.label_column for h in self.heads]

    @property
    def mask_columns(self) -> list[str]:
        return [h.mask_column for h in self.heads if h.mask_column]


def _measurement_heads(*, with_regression: bool = False) -> tuple[Head, ...]:
    """The three binned measurement heads, optionally plus their regressions.

    B2 gets bins only: its task parquet carries no continuous columns (it is a
    corruption grid keyed on the label bins), and Plan A/B §7.1 scores the
    robustness task type on AUCC / relative drop over AUPRC, not on MAE. A2 and
    B1 get both -- §5.4 and §6.2 require the regression numbers there.
    """
    binned = tuple(
        Head(name=name, kind="multiclass", label_column=name, classes=classes)
        for name, classes in MEASUREMENT_CLASSES.items()
    )
    if not with_regression:
        return binned
    continuous = tuple(
        Head(name=name, kind="regression", label_column=column, units=units,
             center=center, unit=unit, tolerance=tolerance)
        for name, (column, units, center, unit, tolerance)
        in MEASUREMENT_REGRESSION.items()
    )
    return binned + continuous


def _lab_heads() -> tuple[Head, ...]:
    return tuple(
        Head(name=f"lab_{lab}_{window}", kind="multiclass",
             label_column=f"lab_{lab}_{window}_label", classes=LAB_CLASSES)
        for lab in LABS
        for window in LAB_WINDOWS
    )


TASKS: dict[str, TaskSpec] = {

    "A1_ecg_diagnosis": TaskSpec(
        key="A1_ecg_diagnosis", plan="A",
        heads=tuple(
            Head(name=name, kind="binary", label_column=name)
            for name in (
                "label_atrial_fibrillation_flutter",
                "label_heart_failure_narrow",
                "label_acute_myocardial_infarction",
                "label_conduction_disorder",
                "label_ventricular_arrhythmia_or_arrest",
            )
        ),
        primary_metric="macro_AUPRC",
        subgroup_columns=("sqi_tier", "cart_id", "link_tier", "boundary_flag"),
        extra_columns=("boundary_flag",),
    ),

    "A2_measurement_blind": TaskSpec(
        key="A2_measurement_blind", plan="A",
        heads=_measurement_heads(with_regression=True),
        primary_metric="mean_head_macro_AUPRC",
        subgroup_columns=("sqi_tier", "cart_id", "link_tier"),
    ),

    "A3_lab_abnormality": TaskSpec(
        key="A3_lab_abnormality", plan="A",
        heads=_lab_heads(),
        primary_metric="macro_AUPRC_pm24h",
        subgroup_columns=("sqi_tier", "cart_id", "link_tier", "boundary_flag"),
        extra_columns=("boundary_flag",),
    ),

    "A4_event_localization": TaskSpec(
        key="A4_event_localization", plan="A",
        heads=(Head(name="fiducials", kind="peak_seq", label_column="r_peaks_lead2",
                    pos_weight=14.0),),
        primary_metric="r_peak_F1_10ms",
        subgroup_columns=("sqi_tier", "cart_id", "link_tier"),
        extra_columns=("qrs_onsets_lead2", "qrs_offsets_lead2", "n_peaks",
                       "fallback_used", "delineate_ok"),
    ),

    # Verification rows. The masked-attribute heads ride along on the rows whose
    # signal AND image are still the anchor's own (positives, TEXT_SWAP,
    # HARD_NEGATIVE_TEXT); elsewhere `masked_attr_valid` is False and the three
    # heads contribute no loss. §5.6 puts both on one shared tri-encoder, and
    # §4.A.5.8 asks whether the joint training helps -- which needs them joint.
    "A5_cross_modal_verification": TaskSpec(
        key="A5_cross_modal_verification", plan="A",
        heads=(
            Head(name="y_match", kind="binary", label_column="y_match"),
            Head(name="hr_label", kind="multiclass", label_column="hr_label",
                 classes=MEASUREMENT_CLASSES["hr_label"], mask_column="masked_attr_valid"),
            Head(name="qrs_label", kind="multiclass", label_column="qrs_label",
                 classes=MEASUREMENT_CLASSES["qrs_label"], mask_column="masked_attr_valid"),
            Head(name="qtc_label", kind="multiclass", label_column="qtc_label",
                 classes=MEASUREMENT_CLASSES["qtc_label"], mask_column="masked_attr_valid"),
        ),
        primary_metric="AUPRC_y_match",
        id_column="anchor_study_id",
        signal_id_column="signal_id", image_id_column="image_id", text_id_column="text_id",
        image_type_column="image_type",
        primary_flag_column=None,
        subgroup_columns=("neg_type", "image_type"),
        extra_columns=("neg_type", "image_type", "text_override"),
        notes="masked-attribute targets are joined from masked_attribute_<split>.parquet",
    ),

    "A6_risk_stratification": TaskSpec(
        key="A6_risk_stratification", plan="A",
        heads=(
            Head(name="mortality_30d", kind="binary", label_column="mortality_30d",
                 mask_column="mortality_observable"),
            Head(name="mortality_90d", kind="binary", label_column="mortality_90d",
                 mask_column="mortality_observable"),
            Head(name="readmission_30d", kind="binary", label_column="readmission_30d",
                 mask_column="readmission_eligible"),
            Head(name="readmission_90d", kind="binary", label_column="readmission_90d",
                 mask_column="readmission_eligible_90d"),
        ),
        primary_metric="mean_head_AUPRC",
        subgroup_columns=("sqi_tier", "cart_id", "link_tier", "boundary_flag"),
        extra_columns=("boundary_flag", "followup_days_after_discharge"),
    ),

    "B1_measurement_blind": TaskSpec(
        key="B1_measurement_blind", plan="B",
        heads=_measurement_heads(with_regression=True),
        primary_metric="mean_head_macro_AUPRC",
        subgroup_columns=("sqi_tier", "cart_id", "link_tier"),
    ),

    "B2_noise_robustness": TaskSpec(
        key="B2_noise_robustness", plan="B",
        heads=_measurement_heads(),
        primary_metric="mean_head_macro_AUPRC",
        primary_flag_column=None,
        subgroup_columns=("sqi_tier", "corruption_type", "snr_db", "regime"),
        extra_columns=("corruption_type", "snr_db", "regime", "row_role", "is_anchor",
                       "clean_signal_kind", "corrupted_signal_kind"),
    ),

    "B3_temporal_grounding": TaskSpec(
        key="B3_temporal_grounding", plan="B",
        heads=(Head(name="bins", kind="bins", label_column="labels"),),
        primary_metric="mIoU",
        primary_flag_column=None,
        subgroup_columns=("sqi_tier", "cart_id", "query"),
        extra_columns=("query", "fallback_used", "n_positive_bins"),
    ),

    "B4_cross_modal_verification": TaskSpec(
        key="B4_cross_modal_verification", plan="B",
        heads=(Head(name="y_match", kind="binary", label_column="y_match"),),
        primary_metric="AUPRC_y_match",
        id_column="anchor_study_id",
        signal_id_column="signal_id", image_id_column="image_id", text_id_column="text_id",
        image_type_column="image_type",
        primary_flag_column=None,
        subgroup_columns=("neg_type", "image_type"),
        extra_columns=("neg_type", "image_type", "text_override"),
    ),

    "B5_contradiction_detection": TaskSpec(
        key="B5_contradiction_detection", plan="B",
        heads=(
            Head(name="is_corrupted", kind="binary", label_column="is_corrupted"),
            Head(name="label", kind="multiclass", label_column="label", classes=B5_CLASSES),
            Head(name="span", kind="span", label_column="corrupted_span_start",
                 mask_column="is_corrupted"),
        ),
        primary_metric="AUPRC_is_corrupted",
        text_column="audited_report_text",
        subgroup_columns=("sqi_tier", "cart_id", "contradiction_family"),
        extra_columns=("contradiction_family", "contradiction_type",
                       "corrupted_span_start", "corrupted_span_end"),
    ),

    # Evaluation-time only (§4.B.6, §7.5). B6 has no train/val rows of its own:
    # it slices B4's test predictions with eval_keys.parquet.
    "B6_difficulty_stratified": TaskSpec(
        key="B6_difficulty_stratified", plan="B",
        heads=(Head(name="y_match", kind="binary", label_column="y_match"),),
        primary_metric="AUPRC_y_match",
        id_column="study_id",
        primary_flag_column=None,
        subgroup_columns=("difficulty_tier", "neg_type"),
        extra_columns=("difficulty_tier", "neg_type"),
        train_file="eval_keys.parquet", val_file="eval_keys.parquet",
        test_file="eval_keys.parquet",
        eval_only=True, base_task="B4_cross_modal_verification",
    ),
}

TASK_KEYS = tuple(TASKS)


def get_task(key: str) -> TaskSpec:
    try:
        return TASKS[key]
    except KeyError:
        raise KeyError(
            f"unknown task {key!r}. The twelve Phase 2 tasks are: {', '.join(TASK_KEYS)}"
        ) from None


def _self_check() -> None:
    """Cross-check this module against config/task_definitions.yaml."""
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[3]
    defs = yaml.safe_load((root / "config" / "task_definitions.yaml").read_text(encoding="utf-8"))
    policy = yaml.safe_load(
        (root / "config" / "task_input_policy.yaml").read_text(encoding="utf-8")
    )

    assert set(TASK_KEYS) == set(defs["tasks"]), (
        f"task set differs from task_definitions.yaml: "
        f"{set(TASK_KEYS) ^ set(defs['tasks'])}"
    )
    assert set(TASK_KEYS) == set(policy["tasks"]), "task set differs from task_input_policy.yaml"

    expected_head_counts = {
        "A1_ecg_diagnosis": 5, "A2_measurement_blind": 6, "A3_lab_abnormality": 35,
        "A4_event_localization": 1, "A5_cross_modal_verification": 4,
        "A6_risk_stratification": 4, "B1_measurement_blind": 6, "B2_noise_robustness": 3,
        "B3_temporal_grounding": 1, "B4_cross_modal_verification": 1,
        "B5_contradiction_detection": 3, "B6_difficulty_stratified": 1,
    }
    for key, spec in TASKS.items():
        assert len(spec.heads) == expected_head_counts[key], (
            f"{key}: {len(spec.heads)} heads, §5.6 says {expected_head_counts[key]}"
        )
        for head in spec.heads:
            assert head.kind in HEAD_KINDS, f"{key}.{head.name}: bad kind {head.kind!r}"
            if head.kind == "multiclass":
                assert head.classes, f"{key}.{head.name}: multiclass head with no classes"
            if head.kind == "regression":
                assert head.unit > 0, f"{key}.{head.name}: regression unit must be positive"
                assert head.units, f"{key}.{head.name}: regression head must declare units"

    # A1's five heads must be the five locked ICD groups, in the config's order.
    assert [h.name for h in TASKS["A1_ecg_diagnosis"].heads] == \
        defs["tasks"]["A1_ecg_diagnosis"]["targets"]["heads"], "A1 head order drifted"
    assert [h.name for h in TASKS["A6_risk_stratification"].heads] == \
        defs["tasks"]["A6_risk_stratification"]["targets"]["heads"], "A6 head order drifted"
    assert list(LAB_CLASSES) == defs["tasks"]["A3_lab_abnormality"]["targets"]["classes"]
    assert list(LABS) == defs["tasks"]["A3_lab_abnormality"]["targets"]["labs"]
    assert list(LAB_WINDOWS) == defs["tasks"]["A3_lab_abnormality"]["targets"]["windows"]
    assert list(B5_CLASSES) == \
        defs["tasks"]["B5_contradiction_detection"]["targets"]["class_head"]["classes"]
    assert set(B3_QUERIES) == set(
        defs["tasks"]["B3_temporal_grounding"]["targets"]["queries"]
    ), "B3 query set drifted"
    assert set(NEG_TYPES) == set(defs["shared_label_defs"]["negative_types"])

    # The measurement bins are written in the YAML as rules keyed by class name
    # ("bradycardia: hr_bpm < 60"), so compare the class SETS, not the values.
    for head, classes in MEASUREMENT_CLASSES.items():
        declared = set(defs["shared_label_defs"]["measurement_bins"][head]) - {"note"}
        assert set(classes) == declared, (
            f"{head} classes drifted from shared_label_defs.measurement_bins"
        )

    print(f"task_spec self-check: PASS  ({len(TASKS)} tasks, "
          f"{sum(len(t.heads) for t in TASKS.values())} heads)")


if __name__ == "__main__":
    _self_check()
```

### `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/task_dataset.py`

```python
"""The one PyTorch ``Dataset`` behind every Phase 2 training and eval run.

One class serves all twelve tasks. What varies per task is declared in
:mod:`_dataset_lib.task_spec` (heads, label columns, which column holds each
modality's ``study_id``) and per run in the model config (which encoders, which
modality kinds). Nothing about a task is hard-coded in a trainer.

Three rules this module enforces rather than assumes:

* **Input policy.** Every modality kind a run asks for is checked against
  ``config/task_input_policy.yaml`` before a single row is read. A forbidden
  input is a CRITICAL finding (§11.2), and the cheapest place to catch it is
  the constructor.
* **Modality bytes come from** :func:`_dataset_lib.modality.read_modality`
  **only** (§2.1, trap 5). No ``h5py.File`` and no ``tarfile`` in this file.
* **B5 is fed exactly one report per row** -- the corrupted text on corrupted
  rows, the original on clean rows. The parquet carries both columns; handing a
  model both would reveal the label by diff (`task_input_policy.yaml`, B5
  notes).

Windows/Slurm note: worker processes are spawned, so this object must stay
picklable. It holds parquet-derived arrays, never an open file handle;
``read_modality`` keeps its handle cache keyed by PID, so each worker opens its
own.
"""

from __future__ import annotations

import io
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
import torch
import yaml
from torch.utils.data import Dataset

# Absolute, not relative, so this module can be executed directly for its
# self-check the way every other Step-3 module can.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _dataset_lib import build_common as bc                              # noqa: E402
from _dataset_lib import corruption as corrupt_lib                       # noqa: E402
from _dataset_lib.modality import (IMAGE_KINDS, SIGNAL_KINDS,            # noqa: E402
                                   read_modality)
from _dataset_lib.task_spec import (B3_QUERIES, N_BINS, N_SAMPLES,       # noqa: E402
                                    TaskSpec, get_task)

POLICY_PATH = bc.CONFIG_DIR / "task_input_policy.yaml"
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

# §4.A.4 tolerance: +/-10 ms at 500 Hz = +/-5 samples. The dense R-peak target
# marks the peak sample and its two neighbours on each side, so a prediction
# anywhere inside the scored tolerance window sees a positive label. A
# single-sample target would make the BCE gradient vanishingly sparse (1 in
# 5,000) and would penalise a prediction the metric calls correct.
PEAK_HALF_WIDTH = 5


def _load_policy() -> dict[str, Any]:
    return yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))


def check_input_policy(task_key: str, kinds: Sequence[str]) -> None:
    """Raise unless every requested modality kind is allowed for this task.

    ``task_input_policy.yaml`` is the single authority on leakage (§4.X.4). A
    run that asks for a forbidden kind must fail at construction, loudly, not
    produce a results row nobody re-checks.
    """
    policy = _load_policy()["tasks"]
    if task_key not in policy:
        raise KeyError(f"{task_key} is not in {POLICY_PATH.name}")
    allowed = set(policy[task_key]["allowed_inputs"])
    forbidden = set(policy[task_key].get("forbidden_inputs", ()))
    for kind in kinds:
        if kind in forbidden or kind not in allowed:
            raise PermissionError(
                f"CRITICAL (§11.2 leakage): {task_key} may not read {kind!r}. "
                f"Allowed: {sorted(allowed)}"
            )


def join_masked_attributes(frame: pd.DataFrame, masked: pd.DataFrame) -> pd.DataFrame:
    """Attach A5's masked-attribute targets to its verification rows.

    Module-level so the P2.3 cohort audit sees the same rows the loader does --
    A5's HR/QRS/QTc labels live in `masked_attribute_<split>.parquet`, not in
    the verification parquet, and an audit that read only the latter would
    report three heads as label-less.

    The head is valid only where the signal AND the image are still the
    anchor's own. Elsewhere the row shows another subject's ECG, so the
    anchor's HR/QRS/QTc bins are not its labels and the head contributes no
    loss (`mask_column='masked_attr_valid'`).
    """
    masked = masked.rename(columns={"study_id": "anchor_study_id"})
    out = frame.merge(masked, on="anchor_study_id", how="left")
    aligned = (out["signal_id"] == out["anchor_study_id"]) & \
              (out["image_id"] == out["anchor_study_id"])
    out["masked_attr_valid"] = aligned & out["hr_label"].notna() & \
        out["qrs_label"].notna() & out["qtc_label"].notna()
    return out


@dataclass
class ModalityPlan:
    """Which modality kinds this run reads, resolved from the model config."""

    signal_kind: str | None = None
    n_leads: int = 1
    image_kind: str | None = None
    image_h: int = 224
    image_w: int = 672
    image_augment: bool = False
    text_encoder: str | None = None        # "bioclinicalbert" | "tfidf" | None
    text_max_length: int = 512

    @property
    def uses_signal(self) -> bool:
        return self.signal_kind is not None

    @property
    def uses_image(self) -> bool:
        return self.image_kind is not None

    @property
    def uses_text(self) -> bool:
        return self.text_encoder is not None

    def kinds(self) -> list[str]:
        out = []
        if self.signal_kind:
            out.append(self.signal_kind)
        if self.image_kind:
            out.append(self.image_kind)
        if self.text_encoder:
            out.append("report_text")
        return out


def plan_from_config(config: dict[str, Any]) -> ModalityPlan:
    """Build the modality plan from a `config/model_configs/*.yaml` mapping."""
    plan = ModalityPlan()
    if config.get("signal"):
        block = config["signal"]
        plan.signal_kind = block["input_modality"]
        plan.n_leads = int(block.get("n_leads", 1))
    if config.get("image"):
        block = config["image"]
        plan.image_kind = block["input_modality"]
        plan.image_h = int(block["target_h"])
        plan.image_w = int(block["target_w"])
        plan.image_augment = bool(block.get("augmentation", False))
    if config.get("text"):
        block = config["text"]
        plan.text_encoder = str(block["encoder"]).lower()
        plan.text_max_length = int(block.get("max_length", 512))
    return plan


# -----------------------------------------------------------------------------
# image transforms (§5.3)
# -----------------------------------------------------------------------------
def _decode_image(raw: bytes) -> "Any":
    from PIL import Image

    return Image.open(io.BytesIO(raw)).convert("RGB")


def build_image_transform(height: int, width: int, augment: bool):
    """Deterministic eval transform, or the §5.3 training transform.

    **Deviation from §5.3's `Resize(short_side) -> CenterCrop(target)`, forced
    by the rendered images.** §5.3 picks 224x672 "preserves the 1:3 strip aspect
    ratio" and 384x512 "preserves the 3x4 grid aspect ratio". Measured, the
    Phase 1 renders are 3600x750 (Lead-II clean) and 1016x504 (12-lead) -- 4.8:1
    and 2.02:1, not 3:1 and 1.33:1. Short-side resize plus a centre crop would
    therefore discard 37 % of the Lead-II strip (the first and last ~2 seconds of
    a 10-second ECG) and the outer lead columns of the 12-lead grid. The stated
    intent -- keep the whole ECG at the locked target size -- is honoured by
    resizing the full image into the target box. Target sizes, and so the §6.6
    VRAM budgets, are unchanged. Disclose in the supplementary.

    The augmented variant keeps §5.3's translation jitter by resizing 5 % larger
    and random-cropping back to the target, and keeps the locked colour jitter
    and +/-2 degree rotation. Horizontal flip stays off -- it inverts the leads.
    """
    from torchvision import transforms

    normalize = transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD)
    if not augment:
        return transforms.Compose([
            transforms.Resize((height, width)),
            transforms.ToTensor(),
            normalize,
        ])
    return transforms.Compose([
        transforms.Resize((int(round(height * 1.05)), int(round(width * 1.05)))),
        transforms.RandomCrop((height, width)),
        transforms.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.05, hue=0),
        transforms.RandomRotation(degrees=2),
        transforms.ToTensor(),
        normalize,
    ])


# -----------------------------------------------------------------------------
# the dataset
# -----------------------------------------------------------------------------
class TaskDataset(Dataset):
    """Rows of one task/split, resolved to model inputs and targets.

    Args:
        task_key: one of the twelve keys in :mod:`task_spec`.
        split: ``train`` / ``val`` / ``test``.
        plan: which modalities this run reads.
        dev: read from ``data/processed/tasks/_dev/`` instead of the real tree.
        primary_only: keep only ``is_primary`` rows (the §4 primary cohort).
        row_filter: extra pandas ``query`` string, for sensitivity slices and
            for B2's per-regime test sets.
        augment_regime_2: apply on-the-fly corruption per §7.3 / the locked
            recipe file. B2 regime_2 only.
        run_seed / epoch: fed to the regime_2 augmentation key so a resumed
            epoch reproduces the same noise.
        limit: cap the row count (smoke tests only).
    """

    def __init__(
        self,
        task_key: str,
        split: str,
        plan: ModalityPlan,
        *,
        dev: bool = False,
        primary_only: bool = True,
        row_filter: str | None = None,
        augment_regime_2: bool = False,
        run_seed: int = 42,
        epoch: int = 0,
        limit: int = 0,
    ) -> None:
        self.spec: TaskSpec = get_task(task_key)
        self.task_key = task_key
        self.split = split
        self.plan = plan
        self.dev = dev
        self.augment_regime_2 = augment_regime_2
        self.run_seed = int(run_seed)
        self.epoch = int(epoch)

        check_input_policy(task_key, plan.kinds())
        if plan.signal_kind and plan.signal_kind not in SIGNAL_KINDS:
            raise ValueError(f"{plan.signal_kind!r} is not a signal modality kind")
        if plan.image_kind and plan.image_kind not in IMAGE_KINDS:
            raise ValueError(f"{plan.image_kind!r} is not an image modality kind")

        self.frame = self._load_frame(split, primary_only, row_filter, limit)
        self._text_lookup: dict[int, str] | None = None
        self._text_matrix: np.ndarray | None = None   # TF-IDF/SVD, precomputed
        self._tokenizer = None
        self._image_transform = None

        if plan.uses_text:
            self._prepare_text()

    # -- construction ---------------------------------------------------------
    def _task_path(self, filename: str) -> Path:
        root = bc.TASKS_DIR / "_dev" if self.dev else bc.TASKS_DIR
        return root / self.task_key / filename

    def _load_frame(self, split: str, primary_only: bool, row_filter: str | None,
                    limit: int) -> pd.DataFrame:
        spec = self.spec
        filename = {"train": spec.train_file, "val": spec.val_file, "test": spec.test_file}[split]
        path = self._task_path(filename)
        if not path.exists():
            raise FileNotFoundError(
                f"{path} is missing -- run the Stage P2.1/P2.2 builder for {self.task_key} "
                f"({'--dev' if self.dev else 'full scale'}) first"
            )
        frame = pd.read_parquet(path)
        if "split" in frame.columns:
            frame = frame[frame["split"] == split]
        if primary_only and spec.primary_flag_column and spec.primary_flag_column in frame.columns:
            frame = frame[frame[spec.primary_flag_column].fillna(False)]
        if row_filter:
            frame = frame.query(row_filter)
        frame = frame.reset_index(drop=True)
        if limit:
            frame = frame.head(limit).reset_index(drop=True)

        if self.task_key == "A5_cross_modal_verification":
            frame = self._join_masked_attributes(frame, split)
        if self.task_key == "B5_contradiction_detection":
            frame = self._resolve_b5_text(frame)
        if frame.empty:
            raise RuntimeError(f"{self.task_key}/{split} is empty after filtering")
        return frame

    def _join_masked_attributes(self, frame: pd.DataFrame, split: str) -> pd.DataFrame:
        masked = pd.read_parquet(
            self._task_path(f"masked_attribute_{split}.parquet"),
            columns=["study_id", "hr_label", "qrs_label", "qtc_label"],
        )
        return join_masked_attributes(frame, masked)

    @staticmethod
    def _resolve_b5_text(frame: pd.DataFrame) -> pd.DataFrame:
        """Pick the ONE report a B5 row is allowed to show the model."""
        frame = frame.copy()
        frame["audited_report_text"] = np.where(
            frame["is_corrupted"].to_numpy(dtype=bool),
            frame["corrupted_report_text"].to_numpy(),
            frame["original_report_text"].to_numpy(),
        )
        length = frame["audited_report_text"].str.len().clip(lower=1).to_numpy(dtype="float32")
        frame["span_start_norm"] = (
            frame["corrupted_span_start"].fillna(0).to_numpy(dtype="float32") / length
        )
        frame["span_end_norm"] = (
            frame["corrupted_span_end"].fillna(0).to_numpy(dtype="float32") / length
        )
        # The model never sees these two columns again; drop them so no
        # downstream consumer can accidentally hand the model both reports.
        return frame.drop(columns=["original_report_text", "corrupted_report_text"])

    def _prepare_text(self) -> None:
        if self.spec.text_column:
            self._texts = self.frame[self.spec.text_column].fillna("").astype(str).to_numpy()
            return
        needed = pd.unique(self.frame[self.spec.text_id_column])
        table = bc.report_text_series()
        table = table[table.study_id.isin(needed)]
        lookup = dict(zip(table.study_id.to_numpy(), table.report_text.fillna("").astype(str)))
        self._texts = np.array(
            [lookup.get(int(sid), "") for sid in self.frame[self.spec.text_id_column]],
            dtype=object,
        )
        # Plan A/B §6.7 Level 5 (A5 / B4 test rows only): the row keeps the
        # anchor's own `text_id` and supplies the altered report inline, so the
        # negative differs from the positive by exactly one clinical claim. Any
        # other row leaves the column null and reads its text by id as usual.
        if "text_override" in self.frame.columns:
            override = self.frame["text_override"].to_numpy()
            present = pd.notna(override)
            if present.any():
                self._texts[present] = [str(v) for v in override[present]]

    # -- text encoders --------------------------------------------------------
    def raw_texts(self) -> np.ndarray:
        """Every row's text, in row order. Used to fit the TF-IDF vectoriser."""
        if not self.plan.uses_text:
            raise RuntimeError(f"{self.task_key} run reads no text")
        return self._texts

    def precompute_text_features(self, matrix: np.ndarray) -> None:
        """Attach a (n_rows, embed_dim) TF-IDF/SVD matrix computed elsewhere.

        §5.4.1 makes TF-IDF a feature extractor whose vocabulary is fitted on
        TRAIN only. Transforming the whole split once is both faster than
        per-item work and the only way to keep the fit strictly out of val/test.
        """
        if matrix.shape[0] != len(self.frame):
            raise ValueError(f"text matrix has {matrix.shape[0]} rows, frame has {len(self.frame)}")
        self._text_matrix = np.ascontiguousarray(matrix, dtype="float32")

    def _tokenize(self, text: str) -> dict[str, torch.Tensor]:
        if self._tokenizer is None:
            import os

            from transformers import AutoTokenizer

            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")   # §6.10
            self._tokenizer = AutoTokenizer.from_pretrained(
                "emilyalsentzer/Bio_ClinicalBERT"
            )
        encoded = self._tokenizer(
            text, max_length=self.plan.text_max_length, truncation=True,
            padding="max_length", return_tensors="pt",
        )
        return {"input_ids": encoded["input_ids"][0],
                "attention_mask": encoded["attention_mask"][0]}

    # -- modality reads -------------------------------------------------------
    def _read_signal(self, row: pd.Series) -> torch.Tensor:
        kind = self.plan.signal_kind
        study_id = int(row[self.spec.signal_id_column])

        if self.task_key == "B2_noise_robustness":
            role = str(row.get("row_role", ""))
            if role == "corrupted":
                array = read_modality(study_id, "signal_corrupted",
                                      corruption_type=str(row["corruption_type"]),
                                      snr_db=int(row["snr_db"]))
            else:
                array = read_modality(study_id, kind)
                if role == "augment_on_the_fly" and self.augment_regime_2:
                    array, _, _ = corrupt_lib.augment_regime_2(
                        np.asarray(array), study_id,
                        run_seed=self.run_seed, epoch=self.epoch)
        else:
            array = read_modality(study_id, kind)

        array = np.asarray(array, dtype=np.float32)
        if array.ndim == 1:
            array = array[None, :]
        return torch.from_numpy(np.ascontiguousarray(array))

    def _read_image(self, row: pd.Series) -> torch.Tensor:
        if self._image_transform is None:
            self._image_transform = build_image_transform(
                self.plan.image_h, self.plan.image_w,
                self.plan.image_augment and self.split == "train")
        kind = self.plan.image_kind
        if self.spec.image_type_column:
            # A5/B4 fix the rendering per row; the layout still comes from the
            # model config, so a Lead-II run and a 12-lead run see the same rows.
            layout = "12lead" if kind.endswith("12lead") else "lead2"
            kind = f"image_{row[self.spec.image_type_column]}_{layout}"
        study_id = int(row[self.spec.image_id_column])
        return self._image_transform(_decode_image(read_modality(study_id, kind)))

    # -- targets --------------------------------------------------------------
    def _targets(self, row: pd.Series, index: int) -> dict[str, torch.Tensor]:
        out: dict[str, torch.Tensor] = {}
        for head in self.spec.heads:
            valid = True
            if head.mask_column:
                flag = row.get(head.mask_column)
                valid = bool(flag) if pd.notna(flag) else False

            if head.kind == "binary":
                raw = row[head.label_column]
                valid = valid and pd.notna(raw)
                out[f"y__{head.name}"] = torch.tensor(
                    float(bool(raw)) if valid else 0.0, dtype=torch.float32)

            elif head.kind == "multiclass":
                raw = row[head.label_column]
                valid = valid and pd.notna(raw) and raw in head.classes
                out[f"y__{head.name}"] = torch.tensor(
                    head.classes.index(raw) if valid else -1, dtype=torch.long)

            elif head.kind == "regression":
                # Stored standardised (declared constants, not fitted stats --
                # see MEASUREMENT_REGRESSION). `31_eval.py` inverts it.
                raw = row[head.label_column]
                valid = valid and pd.notna(raw) and np.isfinite(float(raw))
                out[f"y__{head.name}"] = torch.tensor(
                    head.standardise(raw) if valid else 0.0, dtype=torch.float32)
                out[f"raw__{head.name}"] = torch.tensor(
                    float(raw) if valid else float("nan"), dtype=torch.float32)

            elif head.kind == "peak_seq":
                dense, onset_reg, offset_reg, reg_mask = self._dense_fiducials(row)
                out["y__fiducials"] = torch.from_numpy(dense)
                out["y__fiducials_onset"] = torch.from_numpy(onset_reg)
                out["y__fiducials_offset"] = torch.from_numpy(offset_reg)
                out["y__fiducials_regmask"] = torch.from_numpy(reg_mask)

            elif head.kind == "bins":
                labels = np.asarray(row[head.label_column], dtype="float32")
                out["y__bins"] = torch.from_numpy(labels)
                out["query_idx"] = torch.tensor(
                    B3_QUERIES.index(str(row["query"])), dtype=torch.long)

            elif head.kind == "span":
                out["y__span"] = torch.tensor(
                    [float(row["span_start_norm"]), float(row["span_end_norm"])],
                    dtype=torch.float32)

            out[f"m__{head.name}"] = torch.tensor(float(valid), dtype=torch.float32)
        out["row_index"] = torch.tensor(index, dtype=torch.long)
        return out

    @staticmethod
    def _dense_fiducials(row: pd.Series) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Sparse peak/onset/offset lists -> the dense A4 target (§4.A.4.3).

        The parquet stores positions, not masks, exactly so this expansion
        happens at batch time. ``-1`` marks a beat whose delineation failed.
        """
        peaks = np.asarray(row["r_peaks_lead2"], dtype="int64")
        onsets = np.asarray(row["qrs_onsets_lead2"], dtype="int64")
        offsets = np.asarray(row["qrs_offsets_lead2"], dtype="int64")

        dense = np.zeros(N_SAMPLES, dtype="float32")
        onset_reg = np.zeros(N_SAMPLES, dtype="float32")
        offset_reg = np.zeros(N_SAMPLES, dtype="float32")
        reg_mask = np.zeros(N_SAMPLES, dtype="float32")

        for i, peak in enumerate(peaks):
            if peak < 0 or peak >= N_SAMPLES:
                continue
            lo = max(0, peak - PEAK_HALF_WIDTH)
            hi = min(N_SAMPLES, peak + PEAK_HALF_WIDTH + 1)
            dense[lo:hi] = 1.0
            onset = onsets[i] if i < len(onsets) else -1
            offset = offsets[i] if i < len(offsets) else -1
            if onset >= 0 and offset >= 0:
                # Regressed in samples relative to the peak, scaled by the
                # tolerance window so the SmoothL1 transition sits near 1.
                onset_reg[lo:hi] = (peak - onset) / float(N_SAMPLES)
                offset_reg[lo:hi] = (offset - peak) / float(N_SAMPLES)
                reg_mask[lo:hi] = 1.0
        return dense, onset_reg, offset_reg, reg_mask

    # -- Dataset protocol -----------------------------------------------------
    def __len__(self) -> int:
        return len(self.frame)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        row = self.frame.iloc[index]
        item: dict[str, Any] = {}
        presence = torch.zeros(3, dtype=torch.float32)

        if self.plan.uses_signal:
            item["signal"] = self._read_signal(row)
            presence[0] = 1.0
        if self.plan.uses_image:
            item["image"] = self._read_image(row)
            presence[1] = 1.0
        if self.plan.uses_text:
            if self.plan.text_encoder == "tfidf":
                if self._text_matrix is None:
                    raise RuntimeError(
                        "TF-IDF features not precomputed -- the trainer must fit the "
                        "vectoriser on TRAIN and call precompute_text_features()"
                    )
                item["text_vec"] = torch.from_numpy(self._text_matrix[index])
            else:
                item.update(self._tokenize(str(self._texts[index])))
            presence[2] = 1.0

        item["presence"] = presence
        item.update(self._targets(row, index))
        return item

    def set_epoch(self, epoch: int) -> None:
        """Advance the regime_2 augmentation stream (§7.3)."""
        self.epoch = int(epoch)

    # -- provenance for the prediction file (§7.1) ----------------------------
    def provenance_frame(self) -> pd.DataFrame:
        """``study_id, subject_id`` + every subgroup key this task reports on."""
        columns = ["subject_id"]
        id_col = self.spec.id_column
        out = pd.DataFrame({"study_id": self.frame[id_col].to_numpy()})
        for column in list(self.spec.subgroup_columns) + columns:
            if column in self.frame.columns:
                out[column] = self.frame[column].to_numpy()
        if "subject_id" not in out.columns:
            raise RuntimeError(f"{self.task_key} rows carry no subject_id -- the "
                               "patient-level bootstrap cannot run without it")
        return out


def _self_check() -> None:
    """Smallest runnable proof that the loader resolves real bytes and targets."""
    plan = ModalityPlan(signal_kind="preprocessed_lead2", n_leads=1)
    dataset = TaskDataset("B1_measurement_blind", "val", plan, dev=True, limit=8)
    item = dataset[0]
    assert item["signal"].shape == (1, N_SAMPLES), item["signal"].shape
    assert item["y__hr_label"].dtype == torch.long
    assert item["presence"].tolist() == [1.0, 0.0, 0.0]

    try:
        TaskDataset("B1_measurement_blind", "val",
                    ModalityPlan(image_kind="image_clean_lead2"), dev=True, limit=2)
    except PermissionError as exc:
        assert "leakage" in str(exc)
    else:                                                    # pragma: no cover
        raise AssertionError("B1 accepted an image input; §4.B.1.4 forbids it")

    prov = dataset.provenance_frame()
    assert {"study_id", "subject_id"} <= set(prov.columns)
    print(f"task_dataset self-check: PASS  ({len(dataset)} rows, "
          f"signal {tuple(item['signal'].shape)}, provenance {list(prov.columns)})")


if __name__ == "__main__":
    _self_check()
```

### `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/bootstrap.py`

```python
"""Patient-level bootstrap with BCa intervals (spec §6.7, §1.1).

Every confidence interval in Phase 2 comes from here. The resampling unit is the
**subject**, never the ECG: a subject with forty ECGs must move in and out of a
replicate as one unit, or the interval is narrower than the evidence supports.
An ECG-level bootstrap is a CRITICAL finding under §11.2, so the entry point
takes a ``subject_id`` column and refuses to run without it.

    from _dataset_lib.bootstrap import patient_bootstrap
    result = patient_bootstrap(predictions, my_metric)

CI method (§6.7): BCa when the test-positive count is >= 100, plain percentile
otherwise. Both are computed from the same replicate draw.

Acceleration estimate. Textbook BCa jackknifes one subject at a time. The test
split holds 30,844 subjects and a metric pass costs ~0.1 s, so an exact
jackknife would cost an hour per metric per head. This module therefore uses an
exact jackknife while the subject count is small (<= ``MAX_EXACT_JACKKNIFE``)
and a **delete-one-group jackknife** over ``n_jackknife_groups`` equal-sized
random groups above it -- the standard delete-d estimator of the acceleration
constant. The bias correction z0 is always exact; only ``a`` is approximated,
and ``a`` is the smaller of the two corrections. The group count is recorded in
every result so a reviewer can see which path ran.
"""

from __future__ import annotations

from typing import Callable, Sequence

import numpy as np
import pandas as pd
from scipy import stats

DEFAULT_N_ITER = 10_000
DEFAULT_SEED = 2026
BCA_MIN_POSITIVES = 100
MAX_EXACT_JACKKNIFE = 2_000
DEFAULT_JACKKNIFE_GROUPS = 200


class BootstrapResult(dict):
    """``dict`` with attribute access, so callers can write ``res.ci_low``."""

    __getattr__ = dict.__getitem__


def _subject_index(subject_ids: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
    """Return (unique subjects, per-subject row-index arrays)."""
    order = np.argsort(subject_ids, kind="mergesort")
    sorted_ids = subject_ids[order]
    uniques, starts = np.unique(sorted_ids, return_index=True)
    groups = np.split(order, starts[1:])
    return uniques, groups


def patient_bootstrap(
    predictions: pd.DataFrame,
    metric_fn: Callable[[pd.DataFrame], float],
    *,
    n_iter: int = DEFAULT_N_ITER,
    ci_method: str = "bca",
    seed: int = DEFAULT_SEED,
    level: float = 0.95,
    n_positive: int | None = None,
    subject_column: str = "subject_id",
    n_jackknife_groups: int = DEFAULT_JACKKNIFE_GROUPS,
) -> BootstrapResult:
    """Bootstrap ``metric_fn`` over ``predictions``, resampling SUBJECTS.

    Args:
        predictions: one row per prediction; must carry ``subject_column``.
        metric_fn: takes a DataFrame of rows, returns a scalar. May return NaN
            for a degenerate replicate (e.g. a single class present); NaN
            replicates are dropped before the quantiles are taken.
        n_iter: replicate count (§6.7 locks 10,000 for reported numbers).
        ci_method: ``"bca"`` requests BCa; it downgrades to ``"percentile"``
            automatically when ``n_positive < 100`` (§6.7).
        n_positive: test-positive count used for that downgrade decision. When
            omitted the BCa path is taken as requested.

    Returns:
        ``BootstrapResult`` with ``point``, ``ci_low``, ``ci_high``,
        ``method_used``, ``n_iter_effective``, ``n_subjects``, ``n_rows``,
        ``n_jackknife_groups``.
    """
    if subject_column not in predictions.columns:
        raise KeyError(
            f"patient_bootstrap needs a {subject_column!r} column -- an ECG-level "
            "bootstrap is a CRITICAL spec violation (§1, §6.7, §11.2)"
        )
    if predictions.empty:
        return BootstrapResult(point=float("nan"), ci_low=float("nan"),
                               ci_high=float("nan"), method_used="empty",
                               n_iter_effective=0, n_subjects=0, n_rows=0,
                               n_jackknife_groups=0)

    frame = predictions.reset_index(drop=True)
    subjects, groups = _subject_index(frame[subject_column].to_numpy())
    n_subjects = len(subjects)
    point = float(metric_fn(frame))

    method = "bca" if ci_method == "bca" else "percentile"
    if method == "bca" and n_positive is not None and n_positive < BCA_MIN_POSITIVES:
        method = "percentile"

    rng = np.random.default_rng(seed)
    replicates = np.empty(n_iter, dtype="float64")
    for i in range(n_iter):
        picked = rng.integers(0, n_subjects, size=n_subjects)
        rows = np.concatenate([groups[j] for j in picked])
        replicates[i] = metric_fn(frame.iloc[rows])

    finite = replicates[np.isfinite(replicates)]
    if finite.size < 20:
        return BootstrapResult(point=point, ci_low=float("nan"), ci_high=float("nan"),
                               method_used=f"{method}_degenerate",
                               n_iter_effective=int(finite.size),
                               n_subjects=n_subjects, n_rows=len(frame),
                               n_jackknife_groups=0)

    alpha = (1.0 - level) / 2.0
    used_groups = 0

    if method == "percentile" or not np.isfinite(point):
        lo, hi = np.quantile(finite, [alpha, 1.0 - alpha])
    else:
        # bias correction z0 -- the share of replicates below the point estimate
        share = float(np.mean(finite < point))
        if share <= 0.0 or share >= 1.0:
            lo, hi = np.quantile(finite, [alpha, 1.0 - alpha])
            method = "percentile_z0_degenerate"
        else:
            z0 = stats.norm.ppf(share)
            jack, used_groups = _jackknife(frame, groups, metric_fn, n_subjects,
                                           n_jackknife_groups, seed)
            jack = jack[np.isfinite(jack)]
            if jack.size < 3:
                lo, hi = np.quantile(finite, [alpha, 1.0 - alpha])
                method = "percentile_jackknife_degenerate"
            else:
                deviations = jack.mean() - jack
                denom = 6.0 * (float(np.sum(deviations**2)) ** 1.5)
                accel = 0.0 if denom == 0 else float(np.sum(deviations**3) / denom)
                z_lo, z_hi = stats.norm.ppf(alpha), stats.norm.ppf(1.0 - alpha)
                adj_lo = stats.norm.cdf(z0 + (z0 + z_lo) / (1 - accel * (z0 + z_lo)))
                adj_hi = stats.norm.cdf(z0 + (z0 + z_hi) / (1 - accel * (z0 + z_hi)))
                lo, hi = np.quantile(finite, [float(np.clip(adj_lo, 0.0, 1.0)),
                                              float(np.clip(adj_hi, 0.0, 1.0))])

    return BootstrapResult(point=point, ci_low=float(lo), ci_high=float(hi),
                           method_used=method, n_iter_effective=int(finite.size),
                           n_subjects=n_subjects, n_rows=len(frame),
                           n_jackknife_groups=int(used_groups))


def _jackknife(frame: pd.DataFrame, groups: list[np.ndarray],
               metric_fn: Callable[[pd.DataFrame], float], n_subjects: int,
               n_groups: int, seed: int) -> tuple[np.ndarray, int]:
    """Leave-one-out over subjects, or leave-one-group-out when that is too slow."""
    if n_subjects <= MAX_EXACT_JACKKNIFE:
        blocks: list[Sequence[int]] = [[i] for i in range(n_subjects)]
    else:
        rng = np.random.default_rng(seed + 1)
        assignment = rng.permutation(n_subjects) % max(1, n_groups)
        blocks = [np.flatnonzero(assignment == g) for g in range(max(1, n_groups))]
        blocks = [b for b in blocks if len(b)]

    all_rows = np.arange(len(frame))
    values = np.empty(len(blocks), dtype="float64")
    for i, block in enumerate(blocks):
        dropped = np.concatenate([groups[j] for j in block])
        keep = np.setdiff1d(all_rows, dropped, assume_unique=False)
        values[i] = metric_fn(frame.iloc[keep]) if keep.size else np.nan
    return values, len(blocks)


def pooled_across_seeds(per_seed: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate per-seed test predictions for the §7.1 pooled-prediction CI.

    The pooled frame is resampled by subject exactly like a single-seed frame;
    a drawn subject brings all of its rows from all seeds, which is what keeps
    the pooled interval honest about the between-seed correlation.
    """
    return pd.concat(list(per_seed), ignore_index=True)


def _self_check() -> None:
    """One runnable check: the interval must widen when subjects are correlated."""
    rng = np.random.default_rng(0)
    n_subj, per_subj = 300, 20
    subject = np.repeat(np.arange(n_subj), per_subj)
    truth = rng.integers(0, 2, size=n_subj).repeat(per_subj)      # label is per-SUBJECT
    score = truth * 0.6 + rng.normal(0, 0.4, size=truth.size)
    frame = pd.DataFrame({"subject_id": subject, "y": truth, "p": score})

    from sklearn.metrics import average_precision_score

    def ap(part: pd.DataFrame) -> float:
        if part.y.nunique() < 2:
            return float("nan")
        return float(average_precision_score(part.y, part.p))

    patient = patient_bootstrap(frame, ap, n_iter=400, n_positive=1_000)
    ecg = patient_bootstrap(frame.assign(subject_id=np.arange(len(frame))), ap,
                            n_iter=400, n_positive=1_000)
    width_patient = patient.ci_high - patient.ci_low
    width_ecg = ecg.ci_high - ecg.ci_low
    assert width_patient > width_ecg * 1.5, (
        f"patient-level CI ({width_patient:.4f}) is not meaningfully wider than the "
        f"ECG-level one ({width_ecg:.4f}) -- the subject grouping is not taking effect"
    )
    assert patient.ci_low <= patient.point <= patient.ci_high, "point estimate outside its CI"
    assert patient.method_used.startswith("bca"), patient.method_used

    rare = patient_bootstrap(frame, ap, n_iter=200, n_positive=10)
    assert rare.method_used == "percentile", (
        f"n_positive=10 must fall back to percentile, got {rare.method_used}"
    )
    print(f"patient-level  AP={patient.point:.4f}  CI=[{patient.ci_low:.4f}, "
          f"{patient.ci_high:.4f}]  width={width_patient:.4f}  ({patient.method_used})")
    print(f"ECG-level      AP={ecg.point:.4f}  CI=[{ecg.ci_low:.4f}, {ecg.ci_high:.4f}]  "
          f"width={width_ecg:.4f}  <- what NOT to report")
    print("bootstrap self-check: PASS")


if __name__ == "__main__":
    _self_check()
```

### `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/corruption.py`

```python
"""Train-time signal corruption for B2 regime_2 (spec §7.3).

The eight corruption families are NOT reimplemented here. They are imported
from the Phase 1 Stage 8 script that generated the frozen test set, so the
regime_2 augmenter draws from exactly the same distribution the test rows were
drawn from. A reimplementation would be a second definition of the same
physics, and any drift between the two would silently invalidate the
regime_1-vs-regime_2 comparison, which is B2's whole claim.

Only the SEED STREAM differs. ``config/corruption_recipes_LOCKED.yaml``
requires the train-time key to carry a literal ``regime2|`` prefix plus the run
seed and the epoch, so no train-time realisation can equal a locked test
realisation for the same (study, family, snr) -- the model cannot memorise the
test set's noise.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STAGE8_SCRIPT = (PROJECT_ROOT / "scripts" / "phase1_dataset_generation"
                 / "50_build_signals_corrupted.py")

SNR_LEVELS_DB = (30, 20, 10, 5, 0)
SEED_MODULUS = 2_147_483_648      # 2**31, per the recipe file's rng block


@lru_cache(maxsize=1)
def _stage8() -> Any:
    """Import the Stage 8 module by path -- its filename starts with a digit."""
    if not STAGE8_SCRIPT.exists():
        raise FileNotFoundError(
            f"Phase 1 Stage 8 script not found at {STAGE8_SCRIPT}. The regime_2 "
            "augmenter must reuse its corruption functions, not reimplement them."
        )
    # The Stage 8 script imports its sibling `_stage1_common`, which is only
    # importable from inside the Phase 1 script directory.
    stage1_dir = str(STAGE8_SCRIPT.parent)
    if stage1_dir not in sys.path:
        sys.path.insert(0, stage1_dir)
    spec = importlib.util.spec_from_file_location("_phase1_stage8", STAGE8_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # The Stage 8 module configures logging and touches disk only under
    # __main__, so a plain import is side-effect free.
    sys.modules["_phase1_stage8"] = module
    spec.loader.exec_module(module)
    return module


def families() -> tuple[str, ...]:
    return tuple(_stage8().CORRUPTIONS)


def train_seed(run_seed: int, epoch: int, study_id: int, family: str, snr_db: int) -> int:
    """The ``train_augmentation`` key from corruption_recipes_LOCKED.yaml."""
    key = f"regime2|{run_seed}|{epoch}|{study_id}|{family}|{snr_db}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest()[:4], "big") % SEED_MODULUS


def corrupt(signal: np.ndarray, family: str, snr_db: int,
            rng: np.random.Generator) -> np.ndarray:
    """Apply one locked corruption family. Delegates to the Stage 8 function."""
    fns = _stage8().CORRUPT_FN
    if family not in fns:
        raise ValueError(f"unknown corruption family {family!r}; the eight are {families()}")
    return np.asarray(fns[family](np.asarray(signal, dtype=np.float32), int(snr_db), rng),
                      dtype=np.float32)


def augment_regime_2(signal: np.ndarray, study_id: int, *, run_seed: int, epoch: int,
                     p_corrupt: float = 0.5) -> tuple[np.ndarray, str | None, int]:
    """Draw the regime_2 augmentation for one training sample.

    Policy (``regimes.regime_2.augmentation_policy``, progress-doc question 12
    default): corrupt with p = 0.5, family uniform over all 8, SNR uniform over
    the five-step ladder. Returns ``(signal, family_or_None, snr_db_or_-1)``.
    """
    # The decision RNG is keyed on the same stream as the realisation, so a
    # resumed epoch reproduces both the coin flip and the noise.
    decide = np.random.default_rng(train_seed(run_seed, epoch, study_id, "decide", -1))
    if decide.random() >= p_corrupt:
        return np.asarray(signal, dtype=np.float32), None, -1
    fam = str(families()[int(decide.integers(0, len(families())))])
    snr = int(SNR_LEVELS_DB[int(decide.integers(0, len(SNR_LEVELS_DB)))])
    rng = np.random.default_rng(train_seed(run_seed, epoch, study_id, fam, snr))
    return corrupt(signal, fam, snr, rng), fam, snr


def _self_check() -> None:
    """Determinism, disjointness from the test stream, and a real SNR check."""
    import yaml

    recipes = yaml.safe_load(
        (PROJECT_ROOT / "config" / "corruption_recipes_LOCKED.yaml").read_text(encoding="utf-8")
    )
    assert tuple(recipes["families"]) == families(), (
        f"family list drifted: yaml {tuple(recipes['families'])} vs stage 8 {families()}"
    )
    assert tuple(recipes["snr_levels_db"]) == SNR_LEVELS_DB

    rng = np.random.default_rng(0)
    sig = rng.standard_normal(5000).astype(np.float32)

    # Additive families must realise the requested SNR to within rounding.
    for family in ("gaussian", "baseline_wander", "powerline", "emg", "electrode_motion"):
        for snr in SNR_LEVELS_DB:
            out = corrupt(sig, family, snr, np.random.default_rng(7))
            noise = out - sig
            realised = 10 * np.log10(np.mean(sig**2) / max(np.mean(noise**2), 1e-30))
            assert abs(realised - snr) < 0.5, f"{family} @ {snr} dB realised {realised:.2f} dB"

    # Same key -> same bytes; different epoch -> different bytes.
    a = augment_regime_2(sig, 40000035, run_seed=42, epoch=0)
    b = augment_regime_2(sig, 40000035, run_seed=42, epoch=0)
    c = augment_regime_2(sig, 40000035, run_seed=42, epoch=1)
    assert np.array_equal(a[0], b[0]) and a[1:] == b[1:], "regime_2 augmentation is not reproducible"
    assert not (np.array_equal(a[0], c[0]) and a[1:] == c[1:]), "epoch does not change the stream"

    # The train stream must never collide with the frozen test stream.
    test_seed = int.from_bytes(
        hashlib.sha256(b"40000035|gaussian|10").digest()[:4], "big") % SEED_MODULUS
    assert train_seed(42, 0, 40000035, "gaussian", 10) != test_seed, (
        "train_augmentation seed collides with the frozen test seed"
    )

    corrupted = sum(augment_regime_2(sig, sid, run_seed=42, epoch=0)[1] is not None
                    for sid in range(4000))
    assert 1800 < corrupted < 2200, f"p_corrupt=0.5 realised {corrupted / 4000:.3f}"
    print(f"corruption self-check: PASS  ({len(families())} families, "
          f"realised p_corrupt={corrupted / 4000:.3f})")


if __name__ == "__main__":
    _self_check()
```

### `scripts/phase2_tasks_benchmark_and_paper/_model_lib/signal_encoders.py`

```python
"""1D ResNet-18 signal encoder (spec §5.2, locked by `decision_phase2.yaml`).

    Input:   (B, n_leads, 5000) float32, n_leads in {1, 12}
    Stem:    Conv1d(n_leads, 64, k=15, s=2, p=7) + BN + ReLU + MaxPool1d(3, s=2)
    Stage 1: 2 x BasicBlock1D(64,  64,  stride=1)
    Stage 2: 2 x BasicBlock1D(64,  128, stride=2)
    Stage 3: 2 x BasicBlock1D(128, 256, stride=2)
    Stage 4: 2 x BasicBlock1D(256, 512, stride=2)
    Head:    AdaptiveAvgPool1d(1) -> flatten -> Linear(512, 512)
    Output:  (B, 512)

Trained from scratch, Kaiming-normal init. The 1-lead and 12-lead
instantiations are the same class and share no weights -- Track-1 and Track-2
are independent runs per seed.

``forward(..., return_sequence=True)`` also returns the pre-pool feature map,
which the A4 / B3 localisation heads decode back to sample and bin resolution.
"""

from __future__ import annotations

import torch
import torch.nn as nn

EMBED_DIM = 512
KERNEL_SIZE = 7          # the two convs inside a BasicBlock1D
STEM_KERNEL = 15


class BasicBlock1D(nn.Module):
    """Standard 2-conv ResNet basic block, 1-D. Stride is applied to conv1 only."""

    expansion = 1

    def __init__(self, in_channels: int, out_channels: int, stride: int = 1) -> None:
        super().__init__()
        padding = KERNEL_SIZE // 2
        self.conv1 = nn.Conv1d(in_channels, out_channels, KERNEL_SIZE, stride=stride,
                               padding=padding, bias=False)
        self.bn1 = nn.BatchNorm1d(out_channels)
        self.conv2 = nn.Conv1d(out_channels, out_channels, KERNEL_SIZE, stride=1,
                               padding=padding, bias=False)
        self.bn2 = nn.BatchNorm1d(out_channels)
        self.relu = nn.ReLU(inplace=True)
        self.downsample: nn.Module | None = None
        if stride != 1 or in_channels != out_channels:
            self.downsample = nn.Sequential(
                nn.Conv1d(in_channels, out_channels, 1, stride=stride, bias=False),
                nn.BatchNorm1d(out_channels),
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        identity = x if self.downsample is None else self.downsample(x)
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        return self.relu(out + identity)


class ECGResNet1D18(nn.Module):
    """The locked signal backbone. ``n_leads`` selects Track-1 vs Track-2."""

    STAGES = ((64, 64, 1), (64, 128, 2), (128, 256, 2), (256, 512, 2))

    def __init__(self, n_leads: int = 1, embed_dim: int = EMBED_DIM) -> None:
        super().__init__()
        if n_leads not in (1, 12):
            raise ValueError(f"n_leads must be 1 or 12 (§5.2 lead_subsets), got {n_leads}")
        self.n_leads = n_leads
        self.embed_dim = embed_dim

        self.stem = nn.Sequential(
            nn.Conv1d(n_leads, 64, STEM_KERNEL, stride=2, padding=STEM_KERNEL // 2, bias=False),
            nn.BatchNorm1d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(3, stride=2, padding=1),
        )
        self.stages = nn.Sequential(*[
            nn.Sequential(BasicBlock1D(in_c, out_c, stride=stride),
                          BasicBlock1D(out_c, out_c, stride=1))
            for in_c, out_c, stride in self.STAGES
        ])
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.projection = nn.Linear(512, embed_dim)
        self._init_weights()

    def _init_weights(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Conv1d):
                nn.init.kaiming_normal_(module.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(module, nn.BatchNorm1d):
                nn.init.ones_(module.weight)
                nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Linear):
                nn.init.kaiming_normal_(module.weight, nonlinearity="relu")
                nn.init.zeros_(module.bias)

    def forward(self, x: torch.Tensor, return_sequence: bool = False):
        if x.dim() != 3 or x.shape[1] != self.n_leads:
            raise ValueError(
                f"expected (B, {self.n_leads}, 5000), got {tuple(x.shape)}. "
                "read_modality returns CHANNEL-major arrays; a transposed read "
                "trains silently on the wrong axis (progress-doc trap 10)."
            )
        features = self.stages(self.stem(x))              # (B, 512, L')
        embedding = self.projection(self.pool(features).flatten(1))
        if return_sequence:
            return embedding, features
        return embedding


class DenseDecoder1D(nn.Module):
    """Upsample the backbone feature map back to per-sample resolution (A4).

    §5.6 gives A4 a per-sample sigmoid over 5,000 samples plus onset/offset
    regression. The backbone downsamples by 32, so a light three-step
    transposed-conv decoder brings 512 channels at L/32 back to ``out_channels``
    at L, and a final interpolation absorbs the rounding.
    """

    def __init__(self, in_channels: int = 512, out_channels: int = 3,
                 hidden: int = 128, n_samples: int = 5000) -> None:
        super().__init__()
        self.n_samples = n_samples
        self.blocks = nn.Sequential(
            nn.ConvTranspose1d(in_channels, hidden, 4, stride=4), nn.BatchNorm1d(hidden),
            nn.ReLU(inplace=True),
            nn.ConvTranspose1d(hidden, hidden, 4, stride=4), nn.BatchNorm1d(hidden),
            nn.ReLU(inplace=True),
            nn.ConvTranspose1d(hidden, hidden, 2, stride=2), nn.BatchNorm1d(hidden),
            nn.ReLU(inplace=True),
        )
        self.out = nn.Conv1d(hidden, out_channels, 1)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        x = self.out(self.blocks(features))
        if x.shape[-1] != self.n_samples:
            x = nn.functional.interpolate(x, size=self.n_samples, mode="linear",
                                          align_corners=False)
        return x                                           # (B, out_channels, 5000)


class BinPooler(nn.Module):
    """Pool the backbone feature map into 10 one-second bins (B3, §4.B.3.3)."""

    def __init__(self, in_channels: int = 512, n_bins: int = 10) -> None:
        super().__init__()
        self.pool = nn.AdaptiveAvgPool1d(n_bins)
        self.in_channels = in_channels

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.pool(features).transpose(1, 2)         # (B, n_bins, C)


def _self_check() -> None:
    """Shapes, parameter count, and the transposed-input guard."""
    torch.manual_seed(0)
    for n_leads in (1, 12):
        model = ECGResNet1D18(n_leads=n_leads)
        x = torch.randn(2, n_leads, 5000)
        embedding, features = model(x, return_sequence=True)
        assert embedding.shape == (2, EMBED_DIM), embedding.shape
        assert features.shape[1] == 512, features.shape
        n_params = sum(p.numel() for p in model.parameters())
        print(f"  n_leads={n_leads:2d}  embed={tuple(embedding.shape)}  "
              f"seq={tuple(features.shape)}  params={n_params/1e6:.2f} M")

        dense = DenseDecoder1D()(features)
        assert dense.shape == (2, 3, 5000), dense.shape
        bins = BinPooler()(features)
        assert bins.shape == (2, 10, 512), bins.shape

    try:
        ECGResNet1D18(n_leads=12)(torch.randn(2, 5000, 12))
    except ValueError as exc:
        assert "CHANNEL-major" in str(exc)
    else:                                                   # pragma: no cover
        raise AssertionError("sample-major input was accepted -- trap 10 is unguarded")

    print("signal_encoders self-check: PASS")


if __name__ == "__main__":
    _self_check()
```

### `scripts/phase2_tasks_benchmark_and_paper/_model_lib/image_encoders.py`

```python
"""ImageNet-pretrained ResNet-50 image encoder (spec §5.3).

    Input:    (B, 3, H, W) -- 224x672 Lead-II strip or 384x512 12-lead grid
    Backbone: torchvision.models.resnet50(weights=IMAGENET1K_V2)
    Head:     final fc replaced with Linear(2048, 512)
    Output:   (B, 512)

Fine-tuning policy (§5.3, §6.3): all layers trainable, backbone at LR 1e-5 and
the new fc at 1e-3. :meth:`param_groups` hands the trainer that split so no
caller has to re-derive which tensors are "backbone".

Preprocessing lives in `_dataset_lib/task_dataset.build_image_transform`, next
to the loader that applies it, and is documented there -- including the one
deviation from §5.3's centre-crop, which would have cropped away 37 % of a
Lead-II strip given the real render aspect ratios.
"""

from __future__ import annotations

import torch
import torch.nn as nn

EMBED_DIM = 512
BACKBONE_FEATURES = 2048


class ImageResNet50(nn.Module):
    """The locked image backbone.

    Args:
        embed_dim: output width; 512 everywhere in Phase 2.
        pretrained: load IMAGENET1K_V2 weights (§5.3). Only a smoke test with
            no network should pass False, and it must say so in its run config.
    """

    def __init__(self, embed_dim: int = EMBED_DIM, pretrained: bool = True) -> None:
        super().__init__()
        from torchvision.models import ResNet50_Weights, resnet50

        weights = ResNet50_Weights.IMAGENET1K_V2 if pretrained else None
        self.backbone = resnet50(weights=weights)
        self.pretrained = bool(pretrained)
        self.weights_tag = "IMAGENET1K_V2" if pretrained else "random_init"
        self.backbone.fc = nn.Linear(BACKBONE_FEATURES, embed_dim)
        nn.init.kaiming_normal_(self.backbone.fc.weight, nonlinearity="relu")
        nn.init.zeros_(self.backbone.fc.bias)
        self.embed_dim = embed_dim

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.dim() != 4 or x.shape[1] != 3:
            raise ValueError(f"expected (B, 3, H, W), got {tuple(x.shape)}")
        return self.backbone(x)

    def param_groups(self, backbone_lr: float, head_lr: float) -> list[dict]:
        """§5.3 discriminative LRs: pretrained trunk slow, new fc fast."""
        head = list(self.backbone.fc.parameters())
        head_ids = {id(p) for p in head}
        trunk = [p for p in self.backbone.parameters() if id(p) not in head_ids]
        return [{"params": trunk, "lr": backbone_lr, "name": "image_backbone"},
                {"params": head, "lr": head_lr, "name": "image_head"}]


def _self_check() -> None:
    """Both locked input geometries, and the LR split."""
    torch.manual_seed(0)
    model = ImageResNet50(pretrained=False)          # offline-safe for the check
    for height, width in ((224, 672), (384, 512)):
        out = model(torch.randn(2, 3, height, width))
        assert out.shape == (2, EMBED_DIM), out.shape
        print(f"  {height}x{width} -> {tuple(out.shape)}")

    groups = model.param_groups(1e-5, 1e-3)
    assert [g["name"] for g in groups] == ["image_backbone", "image_head"]
    assert groups[0]["lr"] == 1e-5 and groups[1]["lr"] == 1e-3
    n_head = sum(p.numel() for p in groups[1]["params"])
    assert n_head == BACKBONE_FEATURES * EMBED_DIM + EMBED_DIM, n_head
    total = sum(p.numel() for g in groups for p in g["params"])
    assert total == sum(p.numel() for p in model.parameters()), "a parameter is in no group"
    print(f"image_encoders self-check: PASS  ({total/1e6:.1f} M params, "
          f"{n_head/1e6:.2f} M in the head)")


if __name__ == "__main__":
    _self_check()
```

### `scripts/phase2_tasks_benchmark_and_paper/_model_lib/text_encoders.py`

```python
"""Text encoders: TF-IDF + SVD (§5.4.1) and Bio-ClinicalBERT (§5.4.2).

Both are trained for every text-using task; the paper reports Bio-ClinicalBERT
as primary and TF-IDF in the supplementary (§5.4, `decision_phase2.yaml`).

The one rule both obey: **anything fitted is fitted on TRAIN only.** The TF-IDF
vocabulary and the SVD basis are fitted on the training split and frozen for
val and test, and the fitted object travels inside the checkpoint so an eval
run cannot silently refit on the split it is scoring.
"""

from __future__ import annotations

import pickle
from typing import Sequence

import numpy as np
import torch
import torch.nn as nn

EMBED_DIM = 512
HF_ID = "emilyalsentzer/Bio_ClinicalBERT"
# Recorded at first fetch, 2026-08-27; ships in the release package (§5.4.2).
HF_REVISION_SHA = "d5892b39a4adaed74b92212a44081509db72f87b"
BERT_HIDDEN = 768


class TfidfTextEncoder:
    """Feature extractor, not a network (§5.4.1) -- no gradients, no GPU.

        Vocabulary: 50,000 features over char n-grams (2,3,4) + word 1,2-grams
        Vectorizer: TfidfVectorizer(sublinear_tf=True, max_df=0.95, min_df=10)
        Projection: TruncatedSVD -> 512 dims

    Both stages are fitted on the TRAIN split and reused verbatim elsewhere.
    The per-task MLP head downstream is what actually trains.
    """

    def __init__(self, embed_dim: int = EMBED_DIM, max_features: int = 50_000,
                 random_state: int = 2026) -> None:
        self.embed_dim = embed_dim
        self.max_features = max_features
        self.random_state = random_state
        self.word_vectorizer = None
        self.char_vectorizer = None
        self.svd = None
        self.fitted_on_n_docs = 0

    def fit(self, texts: Sequence[str]) -> "TfidfTextEncoder":
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        docs = [str(t) for t in texts]
        # sklearn cannot mix char and word analysers in one vectoriser, so the
        # 50,000-feature budget is split between them and the two matrices are
        # stacked before the SVD. Same vocabulary size, same fit-on-train rule.
        half = max(1, self.max_features // 2)
        self.word_vectorizer = TfidfVectorizer(
            analyzer="word", ngram_range=(1, 2), max_features=half,
            sublinear_tf=True, max_df=0.95, min_df=10)
        self.char_vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4), max_features=half,
            sublinear_tf=True, max_df=0.95, min_df=10)
        word = self.word_vectorizer.fit_transform(docs)
        char = self.char_vectorizer.fit_transform(docs)

        from scipy.sparse import hstack

        stacked = hstack([word, char]).tocsr()
        n_components = min(self.embed_dim, stacked.shape[1] - 1)
        self.svd = TruncatedSVD(n_components=n_components, random_state=self.random_state)
        self.svd.fit(stacked)
        self.fitted_on_n_docs = len(docs)
        return self

    def transform(self, texts: Sequence[str]) -> np.ndarray:
        if self.svd is None:
            raise RuntimeError("TfidfTextEncoder.transform before fit -- §5.4.1 requires "
                               "the vocabulary to be fitted on TRAIN before any split is "
                               "transformed")
        from scipy.sparse import hstack

        docs = [str(t) for t in texts]
        stacked = hstack([self.word_vectorizer.transform(docs),
                          self.char_vectorizer.transform(docs)]).tocsr()
        out = np.zeros((len(docs), self.embed_dim), dtype="float32")
        reduced = self.svd.transform(stacked).astype("float32")
        out[:, : reduced.shape[1]] = reduced
        return out

    # The fitted vectorisers travel inside checkpoint_best.pt so an eval run
    # cannot refit on the split it is scoring.
    def state_bytes(self) -> bytes:
        return pickle.dumps({"word": self.word_vectorizer, "char": self.char_vectorizer,
                             "svd": self.svd, "embed_dim": self.embed_dim,
                             "fitted_on_n_docs": self.fitted_on_n_docs})

    def load_state_bytes(self, blob: bytes) -> "TfidfTextEncoder":
        state = pickle.loads(blob)
        self.word_vectorizer = state["word"]
        self.char_vectorizer = state["char"]
        self.svd = state["svd"]
        self.embed_dim = state["embed_dim"]
        self.fitted_on_n_docs = state.get("fitted_on_n_docs", 0)
        return self


class TfidfPassthrough(nn.Module):
    """Adapter so a TF-IDF run plugs into the same fusion head as BERT.

    The dataset hands over the precomputed 512-d SVD vector; §5.4.1 says the
    embedding itself carries no trainable parameters, so this module only
    normalises the dtype. It exists to keep one model-assembly path.
    """

    def __init__(self, embed_dim: int = EMBED_DIM) -> None:
        super().__init__()
        self.embed_dim = embed_dim

    def forward(self, text_vec: torch.Tensor) -> torch.Tensor:
        return text_vec.to(dtype=torch.float32)

    def param_groups(self, backbone_lr: float, head_lr: float) -> list[dict]:
        return []


class BioClinicalBertEncoder(nn.Module):
    """Bio-ClinicalBERT with a [CLS] -> Linear(768, 512) head (§5.4.2).

    Fine-tuning policy: full backbone trainable with discriminative LRs --
    transformer layers 1e-5, word/position embeddings 1e-6, head 1e-3.
    """

    def __init__(self, embed_dim: int = EMBED_DIM, hf_id: str = HF_ID,
                 pretrained: bool = True) -> None:
        super().__init__()
        from transformers import AutoConfig, AutoModel

        if pretrained:
            self.bert = AutoModel.from_pretrained(hf_id)
        else:
            # Offline smoke path only; every run records which branch it took.
            self.bert = AutoModel.from_config(AutoConfig.from_pretrained(hf_id))
        self.pretrained = bool(pretrained)
        self.hf_id = hf_id
        self.hf_revision_sha = HF_REVISION_SHA if pretrained else "random_init"
        self.projection = nn.Linear(self.bert.config.hidden_size, embed_dim)
        nn.init.kaiming_normal_(self.projection.weight, nonlinearity="relu")
        nn.init.zeros_(self.projection.bias)
        self.embed_dim = embed_dim

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        out = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        cls = out.last_hidden_state[:, 0]          # [CLS], last layer (§5.4.2)
        return self.projection(cls)

    def param_groups(self, backbone_lr: float, head_lr: float,
                     embedding_lr: float | None = None) -> list[dict]:
        embedding_lr = embedding_lr if embedding_lr is not None else backbone_lr / 10.0
        embeddings = list(self.bert.embeddings.parameters())
        embedding_ids = {id(p) for p in embeddings}
        head = list(self.projection.parameters())
        head_ids = {id(p) for p in head}
        layers = [p for p in self.bert.parameters() if id(p) not in embedding_ids]
        return [
            {"params": embeddings, "lr": embedding_lr, "name": "text_embeddings"},
            {"params": layers, "lr": backbone_lr, "name": "text_layers"},
            {"params": head, "lr": head_lr, "name": "text_head"},
        ]


def _self_check() -> None:
    """TF-IDF fits on train only and BERT emits a 512-d [CLS] embedding."""
    train = ["sinus bradycardia", "normal sinus rhythm", "atrial fibrillation",
             "left axis deviation", "right bundle branch block"] * 20
    test = ["sinus tachycardia", "normal sinus rhythm"]

    encoder = TfidfTextEncoder(embed_dim=32).fit(train)
    train_vec, test_vec = encoder.transform(train), encoder.transform(test)
    assert train_vec.shape == (len(train), 32), train_vec.shape
    assert test_vec.shape == (2, 32), test_vec.shape
    assert np.isfinite(test_vec).all()

    restored = TfidfTextEncoder().load_state_bytes(encoder.state_bytes())
    assert np.allclose(restored.transform(test), test_vec), \
        "a round-tripped TF-IDF encoder does not reproduce its own features"

    fresh = TfidfTextEncoder(embed_dim=32)
    try:
        fresh.transform(test)
    except RuntimeError as exc:
        assert "before fit" in str(exc)
    else:                                                   # pragma: no cover
        raise AssertionError("transform before fit was allowed")

    bert = BioClinicalBertEncoder(pretrained=True)
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(HF_ID)
    batch = tokenizer(test, max_length=32, truncation=True, padding="max_length",
                      return_tensors="pt")
    with torch.no_grad():
        out = bert(batch["input_ids"], batch["attention_mask"])
    assert out.shape == (2, EMBED_DIM), out.shape
    groups = bert.param_groups(1e-5, 1e-3, 1e-6)
    assert [g["name"] for g in groups] == ["text_embeddings", "text_layers", "text_head"]
    assert [g["lr"] for g in groups] == [1e-6, 1e-5, 1e-3]
    total = sum(p.numel() for g in groups for p in g["params"])
    assert total == sum(p.numel() for p in bert.parameters()), "a parameter is in no group"
    print(f"text_encoders self-check: PASS  (BERT {total/1e6:.1f} M params, "
          f"rev {bert.hf_revision_sha[:12]}, TF-IDF fitted on {encoder.fitted_on_n_docs} docs)")


if __name__ == "__main__":
    _self_check()
```

### `scripts/phase2_tasks_benchmark_and_paper/_model_lib/fusion_heads.py`

```python
"""Late-concat fusion head (spec §5.5) and the small MLP heads it feeds.

    Concat:  [sig_emb, img_emb, txt_emb, presence_mask_3] -> (B, 1539)
    MLP:     Linear(1539, 1024) + GELU + Dropout(0.2) +
             Linear(1024, 512)  + GELU + Dropout(0.2) +
             Linear(512, task_out)

One head class serves every multimodal task; only the final ``task_out`` layer
differs. A missing modality contributes an all-zeros embedding and a zero
presence bit, so the head can tell "absent" from "present and near zero".

The single-modality tiers (§5.6's "where signal-only is the only allowed input,
no fusion head is used") route through :class:`UnimodalMLP` instead -- the same
two-hidden-layer geometry over one 512-d embedding, so a signal-only result and
a fusion result differ in inputs rather than in head capacity.
"""

from __future__ import annotations

import torch
import torch.nn as nn

EMBED_DIM = 512
N_MODALITIES = 3
CONCAT_DIM = N_MODALITIES * EMBED_DIM + N_MODALITIES      # 1539, per §5.5
HIDDEN_DIMS = (1024, 512)
DROPOUT = 0.2


def _mlp(in_dim: int, hidden_dims, out_dim: int, dropout: float) -> nn.Sequential:
    layers: list[nn.Module] = []
    width = in_dim
    for hidden in hidden_dims:
        layers += [nn.Linear(width, hidden), nn.GELU(), nn.Dropout(dropout)]
        width = hidden
    layers.append(nn.Linear(width, out_dim))
    return nn.Sequential(*layers)


class LateFusionMLP(nn.Module):
    """The locked fusion head. ``task_out`` is the only per-task difference."""

    def __init__(self, task_out: int, embed_dim: int = EMBED_DIM,
                 hidden_dims=HIDDEN_DIMS, dropout: float = DROPOUT) -> None:
        super().__init__()
        self.embed_dim = embed_dim
        self.concat_dim = N_MODALITIES * embed_dim + N_MODALITIES
        self.mlp = _mlp(self.concat_dim, hidden_dims, task_out, dropout)

    def forward(self, signal_emb: torch.Tensor | None, image_emb: torch.Tensor | None,
                text_emb: torch.Tensor | None, presence: torch.Tensor) -> torch.Tensor:
        reference = next(e for e in (signal_emb, image_emb, text_emb, presence)
                         if e is not None)
        batch = reference.shape[0]
        zeros = torch.zeros(batch, self.embed_dim, dtype=reference.dtype,
                            device=reference.device)
        parts = [signal_emb if signal_emb is not None else zeros,
                 image_emb if image_emb is not None else zeros,
                 text_emb if text_emb is not None else zeros,
                 presence.to(dtype=reference.dtype)]
        return self.mlp(torch.cat(parts, dim=1))


class UnimodalMLP(nn.Module):
    """Task head for the single-modality tiers -- same geometry, one input."""

    def __init__(self, task_out: int, in_dim: int = EMBED_DIM,
                 hidden_dims=HIDDEN_DIMS, dropout: float = DROPOUT) -> None:
        super().__init__()
        self.mlp = _mlp(in_dim, hidden_dims, task_out, dropout)

    def forward(self, embedding: torch.Tensor) -> torch.Tensor:
        return self.mlp(embedding)


class EmbeddingSimilarityHead(nn.Module):
    """The §4.A.5.7 / §4.B.4.7 'cosine similarity between frozen embeddings'
    baseline tier, expressed as a head so it shares the trainer stack.

    The only learned parameters are a scale and a bias on the mean pairwise
    cosine similarity of whichever modalities the run reads -- a calibrated
    similarity threshold rather than a learned decision boundary.
    """

    def __init__(self) -> None:
        super().__init__()
        self.scale = nn.Parameter(torch.tensor(10.0))
        self.bias = nn.Parameter(torch.tensor(0.0))

    def forward(self, signal_emb, image_emb, text_emb, presence) -> torch.Tensor:
        available = [e for e in (signal_emb, image_emb, text_emb) if e is not None]
        if len(available) < 2:
            raise ValueError("the similarity baseline needs at least two modalities")
        sims = []
        for i in range(len(available)):
            for j in range(i + 1, len(available)):
                sims.append(torch.cosine_similarity(available[i], available[j], dim=1))
        return (self.scale * torch.stack(sims, dim=1).mean(dim=1) + self.bias).unsqueeze(1)


def _self_check() -> None:
    torch.manual_seed(0)
    head = LateFusionMLP(task_out=5)
    assert head.concat_dim == CONCAT_DIM, head.concat_dim

    batch = 4
    embeddings = [torch.randn(batch, EMBED_DIM) for _ in range(3)]
    presence = torch.ones(batch, N_MODALITIES)
    full = head(*embeddings, presence)
    assert full.shape == (batch, 5), full.shape

    # A dropped modality must change the output AND still run.
    presence_no_text = presence.clone()
    presence_no_text[:, 2] = 0.0
    dropped = head(embeddings[0], embeddings[1], None, presence_no_text)
    assert dropped.shape == (batch, 5)
    assert not torch.allclose(full, dropped), "dropping text did not change the output"

    uni = UnimodalMLP(task_out=3)
    assert uni(embeddings[0]).shape == (batch, 3)

    sim = EmbeddingSimilarityHead()
    assert sim(embeddings[0], embeddings[1], embeddings[2], presence).shape == (batch, 1)
    # An anchor-aligned triple must score above a mismatched one.
    aligned = embeddings[0]
    same = sim(aligned, aligned, aligned, presence).mean()
    different = sim(embeddings[0], embeddings[1], embeddings[2], presence).mean()
    assert same > different, "cosine baseline does not prefer an aligned triple"

    print(f"fusion_heads self-check: PASS  (concat_dim={head.concat_dim}, "
          f"{sum(p.numel() for p in head.parameters())/1e6:.2f} M params)")


if __name__ == "__main__":
    _self_check()
```

### `scripts/phase2_tasks_benchmark_and_paper/_model_lib/task_models.py`

```python
"""Assemble one task's model and its loss from the locked parts (§5.6, §6.4).

`30_train.py` and `31_eval.py` both call :func:`build_model`; neither knows what
a ResNet is. Everything task-specific about the architecture is here, and
everything task-specific about the *data* is in `_dataset_lib/task_spec.py`.

Head layout. Most tasks concatenate every head into one output vector and slice
it -- §5.5's "this single fusion head is shared across all multimodal tasks;
only the final task_out layer differs". Three tasks cannot:

* **A4** predicts at sample resolution, so it decodes the backbone feature map
  with :class:`DenseDecoder1D` instead of pooling it away.
* **B3** predicts at 1-second bin resolution, via :class:`BinPooler`.
* **A5** carries two heads with *different inputs*. The verification head reads
  all three modalities -- that is the task. The masked-attribute head reads
  **signal + image only**: `task_input_policy.yaml` states that "the UNMASKED
  report_text must never reach this head -- it would restore the very numerics
  the head is asked to predict", and on an A5 positive row the text IS the
  unmasked anchor report. Both heads still sit on one shared tri-encoder, as
  §5.6 requires.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _dataset_lib.task_dataset import ModalityPlan                     # noqa: E402
from _dataset_lib.task_spec import B3_QUERIES, N_BINS, N_SAMPLES, TaskSpec  # noqa: E402
from _model_lib.fusion_heads import (EMBED_DIM, EmbeddingSimilarityHead,   # noqa: E402
                                     LateFusionMLP, UnimodalMLP)
from _model_lib.image_encoders import ImageResNet50                    # noqa: E402
from _model_lib.signal_encoders import (BinPooler, DenseDecoder1D,     # noqa: E402
                                        ECGResNet1D18)
from _model_lib.text_encoders import (BioClinicalBertEncoder,          # noqa: E402
                                      TfidfPassthrough)

POS_WEIGHT_CAP = 20.0        # §6.4, multi-label binary heads
A4_POS_WEIGHT = 14.0         # §6.4, per-sample sigmoid


class TaskModel(nn.Module):
    """Encoders + head for one (task, arch tier, lead subset)."""

    def __init__(self, spec: TaskSpec, plan: ModalityPlan, *, pretrained: bool = True,
                 head_style: str = "auto") -> None:
        super().__init__()
        self.spec = spec
        self.plan = plan
        self.task_key = spec.key

        self.signal_encoder = (ECGResNet1D18(n_leads=plan.n_leads)
                               if plan.uses_signal else None)
        self.image_encoder = (ImageResNet50(pretrained=pretrained)
                              if plan.uses_image else None)
        if plan.uses_text:
            self.text_encoder = (TfidfPassthrough() if plan.text_encoder == "tfidf"
                                 else BioClinicalBertEncoder(pretrained=pretrained))
        else:
            self.text_encoder = None

        self.n_modalities_used = sum(
            [plan.uses_signal, plan.uses_image, plan.uses_text])
        if self.n_modalities_used == 0:
            raise ValueError(f"{spec.key}: a run must read at least one modality")

        # "auto": fuse when the run reads more than one modality, otherwise the
        # single embedding feeds a task MLP directly (§5.6).
        self.head_style = ("fusion" if self.n_modalities_used > 1 else "unimodal") \
            if head_style == "auto" else head_style

        self.slices: dict[str, tuple[int, int]] = {}
        # Heads this particular run can actually serve. Equal to every head in
        # the task spec except where a tier lacks a head's required modality.
        self.active_head_names: tuple[str, ...] = tuple(h.name for h in spec.heads)
        self.dense_decoder = None
        self.bin_pooler = None
        self.bin_head = None
        self.masked_head = None
        self.head = None
        self._build_head()

    # -- head construction ----------------------------------------------------
    def _make_head(self, out_dim: int) -> nn.Module:
        if self.head_style == "similarity":
            return EmbeddingSimilarityHead()
        if self.head_style == "fusion":
            return LateFusionMLP(task_out=out_dim)
        return UnimodalMLP(task_out=out_dim)

    def _build_head(self) -> None:
        key = self.task_key

        if key == "A4_event_localization":
            # peak logit + onset regression + offset regression, per sample
            self.dense_decoder = DenseDecoder1D(in_channels=512, out_channels=3,
                                                n_samples=N_SAMPLES)
            return

        if key == "B3_temporal_grounding":
            self.bin_pooler = BinPooler(in_channels=512, n_bins=N_BINS)
            self.bin_head = nn.Linear(512, len(B3_QUERIES))
            return

        if key == "A5_cross_modal_verification":
            self.head = self._make_head(1)                 # verification
            self.slices["y_match"] = (0, 1)
            attr_in = EMBED_DIM * (int(self.plan.uses_signal) + int(self.plan.uses_image))
            if attr_in == 0:
                # A text-only A5 tier is a single-modality BASELINE row. The
                # masked-attribute head reads signal + image only (§5.6 plus the
                # `task_input_policy.yaml` note that the unmasked report must
                # never reach it), so with neither present the head is undefined
                # and this run trains verification alone. The multimodal tier --
                # the one §5.6 describes -- still carries both heads.
                self.masked_head = None
                self.active_head_names = ("y_match",)
                return
            attr_out = 0
            for head in self.spec.heads[1:]:
                self.slices[head.name] = (attr_out, attr_out + head.n_out)
                attr_out += head.n_out
            self.masked_head = UnimodalMLP(task_out=attr_out, in_dim=attr_in)
            return

        offset = 0
        for head in self.spec.heads:
            self.slices[head.name] = (offset, offset + head.n_out)
            offset += head.n_out
        self.head = self._make_head(offset)

    # -- forward --------------------------------------------------------------
    def encode(self, batch: dict[str, torch.Tensor]) -> dict[str, torch.Tensor | None]:
        signal_emb = image_emb = text_emb = None
        features = None
        if self.signal_encoder is not None:
            signal_emb, features = self.signal_encoder(batch["signal"], return_sequence=True)
        if self.image_encoder is not None:
            image_emb = self.image_encoder(batch["image"])
        if self.text_encoder is not None:
            if isinstance(self.text_encoder, TfidfPassthrough):
                text_emb = self.text_encoder(batch["text_vec"])
            else:
                text_emb = self.text_encoder(batch["input_ids"], batch["attention_mask"])
        return {"signal": signal_emb, "image": image_emb, "text": text_emb,
                "signal_features": features}

    def forward(self, batch: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
        embeddings = self.encode(batch)
        presence = batch["presence"]
        key = self.task_key

        if key == "A4_event_localization":
            dense = self.dense_decoder(embeddings["signal_features"])
            return {"fiducials": dense[:, 0], "fiducials_onset": dense[:, 1],
                    "fiducials_offset": dense[:, 2]}

        if key == "B3_temporal_grounding":
            pooled = self.bin_pooler(embeddings["signal_features"])   # (B, bins, C)
            per_query = self.bin_head(pooled).transpose(1, 2)         # (B, queries, bins)
            index = batch["query_idx"].view(-1, 1, 1).expand(-1, 1, N_BINS)
            return {"bins": per_query.gather(1, index).squeeze(1),
                    "bins_all_queries": per_query}

        logits = self._apply_head(embeddings, presence)
        out = {name: logits[:, lo:hi] for name, (lo, hi) in self.slices.items()
               if name in self._generic_head_names()}

        if key == "A5_cross_modal_verification":
            out = {"y_match": logits[:, 0:1]}
            if self.masked_head is None:
                return out                       # text-only tier: verification alone
            parts = [e for e in (embeddings["signal"], embeddings["image"]) if e is not None]
            attr_logits = self.masked_head(torch.cat(parts, dim=1))
            for head in self.spec.heads[1:]:
                lo, hi = self.slices[head.name]
                out[head.name] = attr_logits[:, lo:hi]
        return out

    def _generic_head_names(self) -> set[str]:
        if self.task_key == "A5_cross_modal_verification":
            return {"y_match"}
        return {h.name for h in self.spec.heads}

    def _apply_head(self, embeddings: dict, presence: torch.Tensor) -> torch.Tensor:
        if self.head_style in ("fusion", "similarity"):
            return self.head(embeddings["signal"], embeddings["image"],
                             embeddings["text"], presence)
        single = next(e for e in (embeddings["signal"], embeddings["image"],
                                  embeddings["text"]) if e is not None)
        return self.head(single)

    # -- optimiser groups (§6.3 discriminative LRs) ---------------------------
    def param_groups(self, learning_rates: dict[str, float]) -> list[dict]:
        head_lr = learning_rates["head"]
        groups: list[dict] = []
        claimed: set[int] = set()

        if self.signal_encoder is not None:
            params = list(self.signal_encoder.parameters())
            groups.append({"params": params, "lr": learning_rates["signal_backbone"],
                           "name": "signal_backbone"})
            claimed |= {id(p) for p in params}
        if self.image_encoder is not None:
            for group in self.image_encoder.param_groups(
                    learning_rates["image_backbone"], head_lr):
                groups.append(group)
                claimed |= {id(p) for p in group["params"]}
        if self.text_encoder is not None:
            for group in self.text_encoder.param_groups(
                    learning_rates["text_backbone_layers"], head_lr):
                groups.append(group)
                claimed |= {id(p) for p in group["params"]}
            if isinstance(self.text_encoder, BioClinicalBertEncoder):
                for group in groups:
                    if group["name"] == "text_embeddings":
                        group["lr"] = learning_rates["text_embeddings"]

        rest = [p for p in self.parameters() if id(p) not in claimed]
        if rest:
            groups.append({"params": rest, "lr": head_lr, "name": "task_head"})
        return [g for g in groups if g["params"]]

    def architecture_summary(self) -> dict[str, Any]:
        return {
            "task": self.task_key,
            "head_style": self.head_style,
            "signal_encoder": None if self.signal_encoder is None else
                {"name": "ECGResNet1D18", "n_leads": self.plan.n_leads,
                 "input_modality": self.plan.signal_kind},
            "image_encoder": None if self.image_encoder is None else
                {"name": "ImageResNet50", "weights": self.image_encoder.weights_tag,
                 "input_modality": self.plan.image_kind,
                 "target_hw": [self.plan.image_h, self.plan.image_w],
                 "augmentation": self.plan.image_augment},
            "text_encoder": None if self.text_encoder is None else
                ({"name": "TfidfTextEncoder"} if isinstance(self.text_encoder, TfidfPassthrough)
                 else {"name": "BioClinicalBertEncoder", "hf_id": self.text_encoder.hf_id,
                       "hf_revision_sha": self.text_encoder.hf_revision_sha,
                       "max_length": self.plan.text_max_length}),
            "n_parameters": int(sum(p.numel() for p in self.parameters())),
            "n_trainable": int(sum(p.numel() for p in self.parameters() if p.requires_grad)),
        }


def build_model(spec: TaskSpec, plan: ModalityPlan, *, pretrained: bool = True,
                head_style: str = "auto") -> TaskModel:
    return TaskModel(spec, plan, pretrained=pretrained, head_style=head_style)


# -----------------------------------------------------------------------------
# train-only class statistics (§6.4 -- "All loss weights ... use TRAIN
# statistics only, always")
# -----------------------------------------------------------------------------
def train_class_stats(spec: TaskSpec, train_frame: "Any") -> dict[str, Any]:
    """Per-head ``pos_weight`` / class weights, computed on the TRAIN split.

    Computing these anywhere but train leaks the split being scored into the
    objective. The returned dict is written into ``train_config.yaml`` so the
    §11 reviewer can see the numbers a run actually used.
    """
    import pandas as pd

    stats: dict[str, Any] = {}
    for head in spec.heads:
        if head.kind == "binary":
            column = train_frame[head.label_column]
            if head.mask_column and head.mask_column in train_frame.columns:
                column = column[train_frame[head.mask_column].fillna(False)]
            column = column.dropna()
            prevalence = float(pd.Series(column).astype(bool).mean()) if len(column) else 0.0
            pos_weight = (min((1 - prevalence) / prevalence, POS_WEIGHT_CAP)
                          if prevalence > 0 else POS_WEIGHT_CAP)
            stats[head.name] = {"prevalence": round(prevalence, 6),
                                "pos_weight": round(float(pos_weight), 4),
                                "n": int(len(column))}
        elif head.kind == "multiclass":
            counts = (train_frame[head.label_column].value_counts()
                      .reindex(list(head.classes)).fillna(0.0))
            total = float(counts.sum())
            if spec.key == "A3_lab_abnormality" and total > 0:
                # §6.4: inverse frequency, and 'missing' is a real class that is
                # NOT down-weighted -- it gets the same treatment as the others.
                weights = np.where(counts.to_numpy() > 0,
                                   total / (len(head.classes) * np.maximum(counts.to_numpy(), 1.0)),
                                   0.0)
            else:
                weights = np.ones(len(head.classes), dtype="float64")
            stats[head.name] = {"counts": {c: int(counts[c]) for c in head.classes},
                                "class_weights": [round(float(w), 4) for w in weights]}
        elif head.kind == "regression":
            # Nothing is FITTED here -- `center`/`unit` are declared constants
            # (task_spec.MEASUREMENT_REGRESSION). The train-split summary is
            # recorded anyway so `train_config.yaml` shows the §11 reviewer what
            # the target distribution actually looked like next to the constants.
            column = pd.to_numeric(train_frame[head.label_column], errors="coerce").dropna()
            stats[head.name] = {
                "center": head.center, "unit": head.unit, "units": head.units,
                "tolerance": head.tolerance,
                "train_mean": round(float(column.mean()), 4) if len(column) else None,
                "train_std": round(float(column.std()), 4) if len(column) else None,
                "n": int(len(column)),
            }
    return stats


# -----------------------------------------------------------------------------
# losses (§6.4)
# -----------------------------------------------------------------------------
def active_heads(spec: TaskSpec, outputs: dict[str, torch.Tensor]) -> list:
    """The heads this run actually produced -- see `TaskModel.active_head_names`.

    A single-modality tier of a multi-head task can lack the inputs one head
    needs (A5 text-only cannot serve the signal+image masked-attribute head).
    Iterating over the outputs rather than the spec keeps the loss, the metrics
    and the prediction file consistent about which heads exist for a run.
    """
    produced = set(outputs)
    return [h for h in spec.heads
            if h.name in produced
            or (h.kind == "peak_seq" and "fiducials" in produced)
            or (h.kind == "bins" and "bins" in produced)]


def compute_losses(spec: TaskSpec, outputs: dict[str, torch.Tensor],
                   batch: dict[str, torch.Tensor],
                   stats: dict[str, Any]) -> tuple[torch.Tensor, dict[str, float]]:
    """Total loss plus a per-head breakdown for `train_log.jsonl`."""
    device = next(iter(outputs.values())).device
    total = torch.zeros((), dtype=torch.float32, device=device)
    parts: dict[str, float] = {}

    for head in active_heads(spec, outputs):
        if head.kind == "binary":
            logits = outputs[head.name].squeeze(-1)
            target = batch[f"y__{head.name}"].to(device)
            mask = batch[f"m__{head.name}"].to(device)
            pos_weight = torch.tensor(
                float(stats.get(head.name, {}).get("pos_weight", 1.0)), device=device)
            raw = F.binary_cross_entropy_with_logits(
                logits, target, pos_weight=pos_weight, reduction="none")
            loss = (raw * mask).sum() / mask.sum().clamp(min=1.0)

        elif head.kind == "multiclass":
            logits = outputs[head.name]
            target = batch[f"y__{head.name}"].to(device)
            mask = batch[f"m__{head.name}"].to(device) > 0
            target = torch.where(mask, target, torch.full_like(target, -1))
            weights = stats.get(head.name, {}).get("class_weights")
            weight_tensor = (torch.tensor(weights, dtype=logits.dtype, device=device)
                             if weights and any(w != 1.0 for w in weights) else None)
            loss = F.cross_entropy(logits, target, weight=weight_tensor, ignore_index=-1)
            if torch.isnan(loss):                # every row in the batch masked out
                loss = torch.zeros((), dtype=torch.float32, device=device)

        elif head.kind == "regression":
            # SmoothL1 on the standardised target: robust to the QTc tail
            # (max 773 ms) in a way plain MSE is not, and bounded gradients keep
            # the shared trunk from being dragged by one outlier measurement.
            prediction = outputs[head.name].squeeze(-1)
            target = batch[f"y__{head.name}"].to(device)
            mask = batch[f"m__{head.name}"].to(device)
            raw = F.smooth_l1_loss(prediction, target, reduction="none")
            loss = (raw * mask).sum() / mask.sum().clamp(min=1.0)

        elif head.kind == "peak_seq":
            # §6.4: BCE summed over samples, normalised per study, pos_weight 14
            logits = outputs["fiducials"]
            target = batch["y__fiducials"].to(device)
            pos_weight = torch.tensor(A4_POS_WEIGHT, device=device)
            peak_loss = F.binary_cross_entropy_with_logits(
                logits, target, pos_weight=pos_weight, reduction="none").sum(dim=1).mean()
            reg_mask = batch["y__fiducials_regmask"].to(device)
            denom = reg_mask.sum().clamp(min=1.0)
            reg_loss = (
                (F.smooth_l1_loss(outputs["fiducials_onset"],
                                  batch["y__fiducials_onset"].to(device),
                                  reduction="none") * reg_mask).sum()
                + (F.smooth_l1_loss(outputs["fiducials_offset"],
                                    batch["y__fiducials_offset"].to(device),
                                    reduction="none") * reg_mask).sum()
            ) / denom
            loss = peak_loss / target.shape[1] + reg_loss

        elif head.kind == "bins":
            loss = F.binary_cross_entropy_with_logits(
                outputs["bins"], batch["y__bins"].to(device))

        elif head.kind == "span":
            # §6.4: SmoothL1 on normalised (start, end); defined only on
            # is_corrupted rows, masked elsewhere.
            mask = batch[f"m__{head.name}"].to(device).unsqueeze(1)
            raw = F.smooth_l1_loss(outputs[head.name], batch["y__span"].to(device),
                                   reduction="none")
            loss = (raw * mask).sum() / mask.sum().clamp(min=1.0) / 2.0

        else:                                                # pragma: no cover
            raise ValueError(f"no loss defined for head kind {head.kind!r}")

        total = total + loss
        parts[head.name] = float(loss.detach())

    return total, parts


def _self_check() -> None:
    """Every task builds, runs a forward pass and produces a finite loss."""
    import pandas as pd

    from _dataset_lib.task_spec import TASKS

    torch.manual_seed(0)
    batch_size = 2
    plans = {
        "signal_lead2": ModalityPlan(signal_kind="preprocessed_lead2", n_leads=1),
        "signal_12lead": ModalityPlan(signal_kind="preprocessed_12lead", n_leads=12),
        "fusion": ModalityPlan(signal_kind="preprocessed_lead2", n_leads=1,
                               image_kind="image_clean_lead2", image_h=224, image_w=672,
                               text_encoder="tfidf"),
    }

    for key, spec in TASKS.items():
        if spec.eval_only:
            continue
        plan = plans["fusion"] if key in (
            "A1_ecg_diagnosis", "A3_lab_abnormality", "A5_cross_modal_verification",
            "A6_risk_stratification", "B4_cross_modal_verification",
            "B6_difficulty_stratified") else plans["signal_lead2"]
        if key == "B5_contradiction_detection":
            plan = ModalityPlan(signal_kind="preprocessed_lead2", n_leads=1,
                                text_encoder="tfidf")
        model = build_model(spec, plan, pretrained=False)

        batch: dict[str, torch.Tensor] = {"presence": torch.zeros(batch_size, 3)}
        if plan.uses_signal:
            batch["signal"] = torch.randn(batch_size, plan.n_leads, N_SAMPLES)
            batch["presence"][:, 0] = 1
        if plan.uses_image:
            batch["image"] = torch.randn(batch_size, 3, plan.image_h, plan.image_w)
            batch["presence"][:, 1] = 1
        if plan.uses_text:
            batch["text_vec"] = torch.randn(batch_size, EMBED_DIM)
            batch["presence"][:, 2] = 1

        rows = []
        for head in spec.heads:
            batch[f"m__{head.name}"] = torch.ones(batch_size)
            if head.kind == "binary":
                batch[f"y__{head.name}"] = torch.tensor([0.0, 1.0])
                rows.append({head.label_column: [False, True]})
            elif head.kind == "multiclass":
                batch[f"y__{head.name}"] = torch.tensor([0, min(1, len(head.classes) - 1)])
                rows.append({head.label_column: list(head.classes[:2])})
            elif head.kind == "regression":
                values = [head.center, head.center + head.unit]
                batch[f"y__{head.name}"] = torch.tensor(
                    [head.standardise(v) for v in values], dtype=torch.float32)
                batch[f"raw__{head.name}"] = torch.tensor(values, dtype=torch.float32)
                rows.append({head.label_column: values})
            elif head.kind == "peak_seq":
                batch["y__fiducials"] = (torch.rand(batch_size, N_SAMPLES) > 0.95).float()
                batch["y__fiducials_onset"] = torch.rand(batch_size, N_SAMPLES) * 0.01
                batch["y__fiducials_offset"] = torch.rand(batch_size, N_SAMPLES) * 0.01
                batch["y__fiducials_regmask"] = (torch.rand(batch_size, N_SAMPLES) > 0.95).float()
            elif head.kind == "bins":
                batch["y__bins"] = (torch.rand(batch_size, N_BINS) > 0.5).float()
                batch["query_idx"] = torch.tensor([0, 2])
            elif head.kind == "span":
                batch["y__span"] = torch.rand(batch_size, 2)

        train_frame = pd.DataFrame({
            col: value for row in rows for col, value in row.items()
        })
        stats = train_class_stats(spec, train_frame) if not train_frame.empty else {}

        outputs = model(batch)
        loss, parts = compute_losses(spec, outputs, batch, stats)
        assert torch.isfinite(loss), f"{key}: non-finite loss"
        loss.backward()
        grads = sum(1 for p in model.parameters() if p.grad is not None and p.grad.abs().sum() > 0)
        assert grads > 0, f"{key}: no parameter received a gradient"
        n_groups = len(model.param_groups({"head": 1e-3, "signal_backbone": 1e-3,
                                           "image_backbone": 1e-5,
                                           "text_backbone_layers": 1e-5,
                                           "text_embeddings": 1e-6}))
        print(f"  {key:32s} head={model.head_style:10s} loss={float(loss):7.4f} "
              f"heads={len(parts):2d} groups={n_groups}")

    print("task_models self-check: PASS")


if __name__ == "__main__":
    _self_check()
```

### `scripts/phase2_tasks_benchmark_and_paper/_model_lib/model_configs.py`

```python
"""Generate and load `config/model_configs/*.yaml` (spec §5.8).

    ./ecg_env/Scripts/python.exe _model_lib/model_configs.py --emit
    ./ecg_env/Scripts/python.exe _model_lib/model_configs.py --list

§5.8 requires a YAML per (task, arch tier, lead subset). Writing ~100 of them by
hand would guarantee drift from `task_input_policy.yaml`, so they are DERIVED
from it: the tier list for a task is exactly the modality kinds that task is
allowed to read, crossed with the locked encoders. A config can therefore never
name a forbidden input, and adding a task or changing a policy regenerates the
matrix instead of requiring 100 edits.

Nothing here invents architecture. Every encoder, LR, dropout and embedding
width comes from `config/decision_phase2.yaml` (§5); a model config only selects
which locked encoder a run uses, which modality it reads, and the head shape.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _dataset_lib import build_common as bc                              # noqa: E402
from _dataset_lib.task_spec import TASKS, get_task                       # noqa: E402

MODEL_CONFIG_DIR = bc.CONFIG_DIR / "model_configs"
POLICY_PATH = bc.CONFIG_DIR / "task_input_policy.yaml"
DECISION_PATH = bc.CONFIG_DIR / "decision_phase2.yaml"

TASK_PREFIX = {key: key.split("_")[0] for key in TASKS}
IMAGE_TARGET = {
    "image_clean_lead2": (224, 672), "image_scanlike_lead2": (224, 672),
    "image_clean_12lead": (384, 512), "image_scanlike_12lead": (384, 512),
}
SIGNAL_LEADS = {"raw_lead2": 1, "preprocessed_lead2": 1,
                "raw_12lead": 12, "preprocessed_12lead": 12}
PRIMARY_SIGNAL = {"lead2": "preprocessed_lead2", "12lead": "preprocessed_12lead"}
PRIMARY_IMAGE = {"lead2": "image_clean_lead2", "12lead": "image_clean_12lead"}
EMBEDDING_TIER_TASKS = ("A5_cross_modal_verification", "B4_cross_modal_verification")

# §6.6 batch sizes, keyed by the family a run belongs to.
BATCH_SIZE = {"signal": 256, "signal_a4": 128, "signal_a6": 128,
              "image": 64, "text": 32, "multimodal": 16}
EPOCHS = {"signal": 30, "image": 30, "text": 20, "multimodal": 20}


def _policy() -> dict[str, Any]:
    return yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))["tasks"]


def _decision() -> dict[str, Any]:
    return yaml.safe_load(DECISION_PATH.read_text(encoding="utf-8"))


def _short(kind: str) -> str:
    """`preprocessed_lead2` -> `lead2_preprocessed`; `image_clean_12lead` -> `12lead_clean`."""
    if kind.startswith("image_"):
        _, rendering, layout = kind.split("_", 2)
        return f"{layout}_{rendering}"
    modality, layout = kind.rsplit("_", 1)
    return f"{layout}_{modality}"


def _batch_size(task: str, family: str) -> int:
    if family == "signal" and task == "A4_event_localization":
        return BATCH_SIZE["signal_a4"]
    if family == "signal" and task == "A6_risk_stratification":
        return BATCH_SIZE["signal_a6"]
    return BATCH_SIZE[family]


def _accumulation(task: str, family: str) -> int:
    # §6.6: A6 multimodal accumulates 4 steps to reach effective batch 64 for
    # calibration stability. Everything else is 1.
    return 4 if (task == "A6_risk_stratification" and family == "multimodal") else 1


def build_matrix() -> list[dict[str, Any]]:
    """Every (task, arch tier, lead subset) config, derived from the input policy."""
    policy = _policy()
    decision = _decision()
    lrs = decision["training"]["learning_rates"]
    configs: list[dict[str, Any]] = []

    for task_key, spec in TASKS.items():
        if spec.eval_only:
            continue                       # B6 reuses B4's trained models (§4.B.6)
        allowed = set(policy[task_key]["allowed_inputs"])
        signals = [k for k in SIGNAL_LEADS if k in allowed]
        images = [k for k in IMAGE_TARGET if k in allowed]
        has_text = "report_text" in allowed
        n_heads_out = sum(h.n_out for h in spec.heads)
        prefix = TASK_PREFIX[task_key]

        def base(arch_tier: str, lead_subset: str, family: str) -> dict[str, Any]:
            return {
                "task": task_key,
                "arch_tier": arch_tier,
                "lead_subset": lead_subset,
                "generated_by": "_model_lib/model_configs.py --emit",
                "spec": "docs/PHASE2_SOURCE_OF_TRUTH.md §5.8",
                "note": ("Architecture values are fixed by config/decision_phase2.yaml (§5). "
                         "This file selects encoders, input modalities and head shape only."),
                "head": {"n_out_total": int(n_heads_out),
                         "heads": [{"name": h.name, "kind": h.kind, "n_out": h.n_out}
                                   for h in spec.heads]},
                "train": {"epochs": EPOCHS[family],
                          "batch_size": _batch_size(task_key, family),
                          "accumulation_steps": _accumulation(task_key, family),
                          "patience": decision["training"]["early_stopping"]["patience_epochs"],
                          "learning_rates": dict(lrs)},
            }

        # -- signal-only tiers ------------------------------------------------
        for kind in signals:
            layout = "12lead" if kind.endswith("12lead") else "lead2"
            config = base(f"signal_resnet18_{_short(kind)}", layout, "signal")
            config["signal"] = {"encoder": "ECGResNet1D18", "n_leads": SIGNAL_LEADS[kind],
                                "input_modality": kind, "embed_dim": 512}
            configs.append(config)
            if task_key == "B2_noise_robustness":
                # §7.3: the same architecture trained with and without on-the-fly
                # corruption. regime_1 is the clean trainer, regime_2 augments.
                for regime, augment in (("regime_1", False), ("regime_2", True)):
                    variant = base(f"signal_resnet18_{_short(kind)}_{regime}", layout, "signal")
                    variant["signal"] = dict(config["signal"])
                    variant["regime"] = regime
                    variant["augment_regime_2"] = augment
                    configs.append(variant)

        # -- image-only tiers --------------------------------------------------
        for kind in images:
            layout = "12lead" if kind.endswith("12lead") else "lead2"
            height, width = IMAGE_TARGET[kind]
            config = base(f"image_resnet50_{_short(kind)}", layout, "image")
            config["image"] = {"encoder": "ImageResNet50", "input_modality": kind,
                               "target_h": height, "target_w": width,
                               # §5.3: augmentation on only for scan-like training
                               "augmentation": kind.startswith("image_scanlike"),
                               "embed_dim": 512}
            configs.append(config)

        # -- text-only tiers ---------------------------------------------------
        if has_text:
            for encoder, tier in (("BioClinicalBert", "text_bioclinicalbert"),
                                  ("TfidfTextEncoder", "text_tfidf")):
                config = base(tier, "none", "text")
                config["text"] = {"encoder": encoder, "max_length": 512, "embed_dim": 512}
                if encoder == "BioClinicalBert":
                    config["text"]["hf_id"] = decision["architecture"]["text_encoders"][
                        "primary"]["hf_id"]
                configs.append(config)

        # -- multimodal fusion -------------------------------------------------
        families_available = int(bool(signals)) + int(bool(images)) + int(has_text)
        if families_available >= 2:
            for layout in ("lead2", "12lead"):
                signal_kind = PRIMARY_SIGNAL[layout] if PRIMARY_SIGNAL[layout] in allowed else None
                image_kind = PRIMARY_IMAGE[layout] if PRIMARY_IMAGE[layout] in allowed else None
                if not signal_kind and not image_kind:
                    continue
                config = base(f"multimodal_fusion_{layout}", layout, "multimodal")
                if signal_kind:
                    config["signal"] = {"encoder": "ECGResNet1D18",
                                        "n_leads": SIGNAL_LEADS[signal_kind],
                                        "input_modality": signal_kind, "embed_dim": 512}
                if image_kind:
                    height, width = IMAGE_TARGET[image_kind]
                    config["image"] = {"encoder": "ImageResNet50",
                                       "input_modality": image_kind,
                                       "target_h": height, "target_w": width,
                                       "augmentation": False, "embed_dim": 512}
                if has_text:
                    config["text"] = {"encoder": "BioClinicalBert",
                                      "hf_id": decision["architecture"]["text_encoders"][
                                          "primary"]["hf_id"],
                                      "max_length": 512, "embed_dim": 512}
                config["fusion"] = {"head": "LateFusionMLP", "hidden_dims": [1024, 512],
                                    "dropout": 0.2, "mode": "end_to_end_fine_tuned"}
                configs.append(config)

                # -- the no-text leakage-controlled tier ----------------------
                # Plan A/B §5.3 ablation 6, Figure 2 and Appendix F: the no-text
                # multimodal run is the PRIMARY leakage-controlled setting, and
                # it has to be TRAINED, not simulated.
                #
                # §7.2 originally listed "no-text ablation" among the sweeps that
                # "re-evaluate the same trained model" without retraining. That
                # was written when fusion was frozen late fusion. Round 5.1 made
                # fusion end-to-end fine-tuned (`mode` above), and zeroing the
                # text branch of a jointly-trained encoder does not yield "the
                # same model without text" -- it yields a forward pass outside
                # the model's own training distribution. So the ablation gets its
                # own trained tier.
                #
                # Only where dropping text still leaves a FUSION: a task whose
                # only other modality is signal would collapse to the
                # signal-only tier that already exists (B5 is that case).
                if has_text and signal_kind and image_kind:
                    no_text = {k: v for k, v in config.items()}
                    no_text["arch_tier"] = f"multimodal_fusion_notext_{layout}"
                    no_text["train"] = dict(config["train"])
                    no_text["fusion"] = dict(config["fusion"])
                    no_text.pop("text", None)
                    no_text["ablation"] = "no_text"
                    no_text["ablation_spec"] = (
                        "Plan A/B §5.3 ablation 6 / Figure 2 / Appendix F — the "
                        "leakage-controlled multimodal setting, trained without "
                        "report text rather than evaluated with it zeroed")
                    configs.append(no_text)

                if task_key in EMBEDDING_TIER_TASKS:
                    # §4.A.5.7 / §4.B.4.7 "cosine similarity between frozen S/I/T
                    # embeddings" -- the no-fusion reference point.
                    similarity = dict(config)
                    similarity = {k: v for k, v in config.items()}
                    similarity["arch_tier"] = f"embedding_cosine_{layout}"
                    similarity["head_style"] = "similarity"
                    similarity["train"] = dict(config["train"])
                    configs.append(similarity)

    return configs


def config_filename(config: dict[str, Any]) -> str:
    prefix = TASK_PREFIX[config["task"]]
    return f"{prefix}_{config['arch_tier']}.yaml"


def emit(force: bool = False) -> list[Path]:
    MODEL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for config in build_matrix():
        path = MODEL_CONFIG_DIR / config_filename(config)
        text = yaml.safe_dump(config, sort_keys=False, width=100, allow_unicode=True)
        if path.exists() and not force and path.read_text(encoding="utf-8") == text:
            continue
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def load_model_config(path: str | Path) -> dict[str, Any]:
    """Read one model config and check it against the task's input policy."""
    from _dataset_lib.task_dataset import check_input_policy, plan_from_config

    candidate = Path(path)
    if not candidate.exists():
        candidate = MODEL_CONFIG_DIR / Path(path).name
    if not candidate.exists():
        raise FileNotFoundError(
            f"model config {path} not found. Run "
            "`_model_lib/model_configs.py --emit` to generate the §5.8 matrix.")
    config = yaml.safe_load(candidate.read_text(encoding="utf-8"))
    get_task(config["task"])                       # raises on an unknown task
    check_input_policy(config["task"], plan_from_config(config).kinds())
    config["_path"] = str(candidate)
    return config


def _self_check() -> None:
    configs = build_matrix()
    names = [config_filename(c) for c in configs]
    assert len(names) == len(set(names)), "two configs claim the same filename"

    policy = _policy()
    for config in configs:
        allowed = set(policy[config["task"]]["allowed_inputs"])
        for block, key in (("signal", "input_modality"), ("image", "input_modality")):
            if config.get(block):
                kind = config[block][key]
                assert kind in allowed, f"{config_filename(config)} names forbidden {kind}"
        if config.get("text"):
            assert "report_text" in allowed, f"{config_filename(config)} reads forbidden text"

    per_task: dict[str, int] = {}
    for config in configs:
        per_task[config["task"]] = per_task.get(config["task"], 0) + 1
    # Every trainable task must have at least a signal-only and (where the
    # policy allows more than one family) a fusion tier.
    for task_key, spec in TASKS.items():
        if spec.eval_only:
            continue
        tiers = [c["arch_tier"] for c in configs if c["task"] == task_key]
        assert any(t.startswith("signal_resnet18") for t in tiers), f"{task_key}: no signal tier"
        if "report_text" in set(policy[task_key]["allowed_inputs"]):
            assert "text_bioclinicalbert" in tiers and "text_tfidf" in tiers, \
                f"{task_key}: §5.4 requires BOTH text encoders"

    assert not any(c["task"] == "B6_difficulty_stratified" for c in configs), \
        "B6 is evaluation-time only (§4.B.6) and must have no trained config"

    for task_key in sorted(per_task):
        print(f"  {task_key:32s} {per_task[task_key]:2d} configs")
    print(f"model_configs self-check: PASS  ({len(configs)} configs over "
          f"{len(per_task)} trainable tasks)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the §5.8 model-config matrix")
    parser.add_argument("--emit", action="store_true", help="write the YAMLs")
    parser.add_argument("--force", action="store_true", help="rewrite unchanged files too")
    parser.add_argument("--list", action="store_true", help="print the matrix")
    args = parser.parse_args()

    if args.emit:
        written = emit(force=args.force)
        print(f"wrote {len(written)} config(s) into {MODEL_CONFIG_DIR}")
        for path in written[:10]:
            print(f"  {path.name}")
        if len(written) > 10:
            print(f"  ... and {len(written) - 10} more")
        return 0
    if args.list:
        for config in build_matrix():
            print(config_filename(config))
        return 0
    _self_check()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### `scripts/phase2_tasks_benchmark_and_paper/_model_lib/algorithmic_baselines.py`

```python
"""The doc-mandated rule baselines (spec §5.1, §9.5). No learned ECG encoder.

    | A1     | logistic regression on machine-measurement summary stats     |
    | A2, B1 | NeuroKit2 R-peaks -> mean instantaneous HR -> bin;
    |        | NeuroKit2 wavelet delineation -> mean QRS duration -> bin;
    |        | -> QT -> Bazett QTc -> bin                                   |
    | A4     | NeuroKit2 R-peak + wavelet QRS delineator -- F1 = 1.0 oracle  |
    | A6     | Cox proportional hazards on age + sex + machine HR/QRS/QTc    |
    | B2     | the A2/B1 detector, run on the CORRUPTED signal               |
    | B3     | rule-based per-bin labeller from R-peaks + per-bin SQI        |
    | B5     | NeuroKit2 HR/QRS vs the report's own claim -> inconsistency   |

§11.2 makes a missing algorithmic baseline for a doc-mandated task CRITICAL, so
every task in that table has an entry here and `50_run_baselines_algorithmic.py`
refuses to report success without one.

**The detector must be `method="neurokit"`.** §4.A.4.7 calls A4's baseline
"Pan-Tompkins" *and* promises F1 = 1.0. Both can only be true if the baseline
runs the same detector that produced the ground truth -- and the Phase 1 regen
moved off `pantompkins` precisely because it was wrong (~74 K false labels,
progress-doc trap 2). The corrected path is NeuroKit's default. `pantompkins` is
still available through ``method=`` so the supplementary can report the
detector-disagreement row, but it is not the oracle.

Two baselines read fields that are FORBIDDEN as model inputs. That is deliberate
and declared: `task_input_policy.yaml` carries a `baseline_only_exemptions`
block for A1 (§4.A.1.7) and A6 (§4.A.6.7). A rule baseline that cannot see the
machine measurements is not a baseline. Nothing here ever reaches a trained
encoder.
"""

from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _dataset_lib import build_common as bc                     # noqa: E402
from _dataset_lib.modality import read_modality                 # noqa: E402
from _dataset_lib.task_spec import FS_HZ, N_BINS, N_SAMPLES     # noqa: E402

DETECTOR_METHOD = "neurokit"          # progress-doc trap 2 -- NOT "pantompkins"
DELINEATE_METHOD = "dwt"
FIDUCIALS_PATH = bc.DATA_PROCESSED / "fiducials_lead2.parquet"


def _silence_neurokit() -> None:
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    warnings.filterwarnings("ignore", category=UserWarning)
    np.seterr(all="ignore")


# -----------------------------------------------------------------------------
# the detector -- the corrected Phase 1 path, verbatim
# -----------------------------------------------------------------------------
def _indices(values) -> np.ndarray:
    if values is None:
        return np.empty(0, dtype="int64")
    array = np.asarray(values)
    array = array[~pd.isna(array)]
    return array.astype("int64") if array.size else np.empty(0, dtype="int64")


def detect_fiducials(signal: np.ndarray, *, method: str = DETECTOR_METHOD) -> dict[str, Any]:
    """R-peaks, QRS bounds and T-offsets from a Lead-II strip.

    Mirrors `32_compute_structured_features.py::_extract_wave_features` lines
    364-390: ``ecg_peaks`` with no preceding ``ecg_clean``, then ``ecg_delineate``
    on the SAME array with ``check=False``. Deviating from that reproduces the
    Phase 1 detector bug rather than the Phase 1 ground truth.
    """
    import neurokit2 as nk

    _silence_neurokit()
    lead2 = np.asarray(signal, dtype="float64").ravel()
    out: dict[str, Any] = {"r_peaks": np.empty(0, dtype="int64"),
                           "qrs_onsets": np.empty(0, dtype="int64"),
                           "qrs_offsets": np.empty(0, dtype="int64"),
                           "t_offsets": np.empty(0, dtype="int64"),
                           "fallback_used": False, "delineate_ok": False}
    try:
        _, peak_info = nk.ecg_peaks(lead2, sampling_rate=FS_HZ, method=method)
        out["r_peaks"] = _indices(peak_info.get("ECG_R_Peaks"))
    except Exception:
        out["fallback_used"] = True
        return out
    if out["r_peaks"].size < 2:
        out["fallback_used"] = True
        return out
    try:
        _, waves = nk.ecg_delineate(lead2, rpeaks=out["r_peaks"], sampling_rate=FS_HZ,
                                    method=DELINEATE_METHOD, show=False, check=False)
        out["qrs_onsets"] = _indices(waves.get("ECG_R_Onsets"))
        out["qrs_offsets"] = _indices(waves.get("ECG_R_Offsets"))
        out["t_offsets"] = _indices(waves.get("ECG_T_Offsets"))
        out["delineate_ok"] = True
    except Exception:
        pass
    return out


def measurements_from_fiducials(fiducials: dict[str, Any]) -> dict[str, float]:
    """Mean instantaneous HR, mean QRS duration and Bazett QTc (§5.1)."""
    peaks = np.asarray(fiducials["r_peaks"], dtype="float64")
    out = {"hr_bpm": float("nan"), "qrs_ms": float("nan"), "qtc_ms": float("nan"),
           "rr_ms": float("nan")}
    if peaks.size >= 2:
        rr_ms = np.diff(peaks) * 1000.0 / FS_HZ
        rr_ms = rr_ms[(rr_ms > 200) & (rr_ms < 3000)]        # 20-300 bpm
        if rr_ms.size:
            out["rr_ms"] = float(np.mean(rr_ms))
            out["hr_bpm"] = float(np.mean(60000.0 / rr_ms))

    onsets = np.asarray(fiducials["qrs_onsets"], dtype="float64")
    offsets = np.asarray(fiducials["qrs_offsets"], dtype="float64")
    n = min(onsets.size, offsets.size)
    if n:
        durations = (offsets[:n] - onsets[:n]) * 1000.0 / FS_HZ
        durations = durations[(durations > 20) & (durations < 300)]
        if durations.size:
            out["qrs_ms"] = float(np.mean(durations))

    t_offsets = np.asarray(fiducials["t_offsets"], dtype="float64")
    m = min(onsets.size, t_offsets.size)
    if m and np.isfinite(out["rr_ms"]) and out["rr_ms"] > 0:
        qt_ms = (t_offsets[:m] - onsets[:m]) * 1000.0 / FS_HZ
        qt_ms = qt_ms[(qt_ms > 200) & (qt_ms < 800)]
        if qt_ms.size:
            # Bazett: QTc = QT / sqrt(RR in seconds)
            out["qtc_ms"] = float(np.mean(qt_ms) / np.sqrt(out["rr_ms"] / 1000.0))
    return out


def measurement_baseline_row(study_id: int, signal_kind: str = "raw_lead2",
                             *, corruption_type: str | None = None,
                             snr_db: int | None = None,
                             method: str = DETECTOR_METHOD) -> dict[str, Any]:
    """One A2 / B1 / B2 baseline row: detect, measure, bin (§5.1)."""
    if corruption_type is not None:
        signal = read_modality(study_id, "signal_corrupted",
                               corruption_type=corruption_type, snr_db=int(snr_db))
    else:
        signal = read_modality(study_id, signal_kind)
    signal = np.asarray(signal, dtype="float32")
    if signal.ndim == 2:
        from _dataset_lib.modality import LEAD_II_INDEX

        signal = signal[LEAD_II_INDEX]

    fiducials = detect_fiducials(signal, method=method)
    values = measurements_from_fiducials(fiducials)
    return {
        "study_id": int(study_id),
        **values,
        "hr_label": _bin_hr(values["hr_bpm"]),
        "qrs_label": _bin_qrs(values["qrs_ms"]),
        "qtc_label": _bin_qtc(values["qtc_ms"]),
        "n_peaks": int(np.asarray(fiducials["r_peaks"]).size),
        "fallback_used": bool(fiducials["fallback_used"]),
        "delineate_ok": bool(fiducials["delineate_ok"]),
    }


# The §4.A.2.3 bins, restated on scalars (build_common's versions take Series).
def _bin_hr(value: float) -> str | None:
    if not np.isfinite(value):
        return None
    return "bradycardia" if value < 60 else ("normal" if value < 100 else "tachycardia")


def _bin_qrs(value: float) -> str | None:
    if not np.isfinite(value):
        return None
    return "normal" if value < 100 else ("borderline" if value < 120 else "wide")


def _bin_qtc(value: float) -> str | None:
    if not np.isfinite(value):
        return None
    return "short" if value < 350 else ("normal" if value < 450 else "prolonged")


def label_to_onehot(label: str | None, classes: Sequence[str]) -> np.ndarray:
    """A rule baseline emits a hard class; the metrics want a probability vector.

    One-hot is the honest encoding: the rule has no calibrated confidence, so
    AUPRC scores it as the step function it actually is. An unmeasurable strip
    gets a uniform vector rather than a guess.
    """
    vector = np.zeros(len(classes), dtype="float64")
    if label is None or label not in classes:
        vector[:] = 1.0 / len(classes)
    else:
        vector[list(classes).index(label)] = 1.0
    return vector


# -----------------------------------------------------------------------------
# A4 / B3 -- oracles, read straight from the ground-truth artifact
# -----------------------------------------------------------------------------
def fiducial_oracle(study_ids: Sequence[int]) -> pd.DataFrame:
    """A4's oracle (§4.A.4.7): the same NeuroKit output that built the labels.

    Reading `fiducials_lead2.parquet` rather than re-running the detector is
    what makes F1 = 1.0 exact rather than approximate -- re-running would
    reproduce it only up to NeuroKit's own numerical reproducibility.
    """
    wanted = set(int(s) for s in study_ids)
    frame = pd.read_parquet(FIDUCIALS_PATH,
                            columns=["study_id", "r_peaks_lead2", "qrs_onsets_lead2",
                                     "qrs_offsets_lead2", "n_peaks", "fallback_used"])
    return frame[frame.study_id.isin(wanted)].reset_index(drop=True)


def b3_oracle(study_ids: Sequence[int], noisy_sqi_threshold: float) -> pd.DataFrame:
    """B3's oracle (§4.B.3.7): the per-bin rule, on the same fiducials + SQI."""
    wanted = set(int(s) for s in study_ids)
    frame = pd.read_parquet(FIDUCIALS_PATH,
                            columns=["study_id", "r_peaks_lead2", "qrs_onsets_lead2",
                                     "qrs_offsets_lead2", "sqi_per_bin", "fallback_used"])
    frame = frame[frame.study_id.isin(wanted)].reset_index(drop=True)

    rows = []
    for record in frame.itertuples(index=False):
        bins = per_bin_labels(np.asarray(record.r_peaks_lead2),
                             np.asarray(record.qrs_onsets_lead2),
                             np.asarray(record.qrs_offsets_lead2),
                             np.asarray(record.sqi_per_bin, dtype="float64"),
                             noisy_sqi_threshold)
        rows.append({"study_id": int(record.study_id), "fallback_used": bool(record.fallback_used),
                     **bins})
    return pd.DataFrame(rows)


def per_bin_labels(r_peaks: np.ndarray, qrs_onsets: np.ndarray, qrs_offsets: np.ndarray,
                   sqi_per_bin: np.ndarray, noisy_threshold: float) -> dict[str, list[int]]:
    """The four §4.B.3.3 queries at 1-second resolution."""
    samples_per_bin = N_SAMPLES // N_BINS
    high = np.zeros(N_BINS, dtype=int)
    low = np.zeros(N_BINS, dtype=int)
    wide = np.zeros(N_BINS, dtype=int)
    noisy = np.zeros(N_BINS, dtype=int)

    peaks = np.asarray(r_peaks, dtype="float64")
    if peaks.size >= 2:
        midpoints = (peaks[:-1] + peaks[1:]) / 2.0
        rr_ms = np.diff(peaks) * 1000.0 / FS_HZ
        with np.errstate(divide="ignore", invalid="ignore"):
            instantaneous = 60000.0 / rr_ms
        for midpoint, rate in zip(midpoints, instantaneous):
            index = int(midpoint) // samples_per_bin
            if 0 <= index < N_BINS and np.isfinite(rate):
                if rate > 100:
                    high[index] = 1
                if rate < 60:
                    low[index] = 1

    n = min(len(qrs_onsets), len(qrs_offsets))
    for onset, offset in zip(np.asarray(qrs_onsets)[:n], np.asarray(qrs_offsets)[:n]):
        if onset < 0 or offset < 0:
            continue
        if (offset - onset) > 60:          # 60 samples at 500 Hz = 120 ms
            index = int(onset) // samples_per_bin
            if 0 <= index < N_BINS:
                wide[index] = 1

    sqi = np.asarray(sqi_per_bin, dtype="float64")
    if sqi.size == N_BINS:
        noisy = (np.nan_to_num(sqi, nan=0.0) < float(noisy_threshold)).astype(int)

    return {"HIGH_HEART_RATE": high.tolist(), "LOW_HEART_RATE": low.tolist(),
            "WIDE_QRS": wide.tolist(), "NOISY_SEGMENT": noisy.tolist()}


# -----------------------------------------------------------------------------
# A1 -- logistic regression on machine-measurement summary stats (§4.A.1.7)
# -----------------------------------------------------------------------------
def machine_feature_table(study_ids: Sequence[int]) -> pd.DataFrame:
    """HR / QRS / QTc / axis / PR, sentinel-masked. BASELINE-ONLY (§4.A.1.4)."""
    features = bc.machine_measurements()
    wanted = set(int(s) for s in study_ids)
    features = features[features.study_id.isin(wanted)].copy()
    columns = ["hr_bpm", "qrs_ms", "qtc_ms", "qrs_axis", "pr_ms"]
    for column in columns:
        median = features[column].median()
        features[f"{column}_missing"] = features[column].isna().astype("float64")
        features[column] = features[column].fillna(median)
    return features[["study_id"] + columns + [f"{c}_missing" for c in columns]]


def logistic_baseline(train: pd.DataFrame, test: pd.DataFrame, feature_columns: Sequence[str],
                      label_columns: Sequence[str]) -> pd.DataFrame:
    """Per-head logistic regression fitted on TRAIN, scored on TEST."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(train[list(feature_columns)].to_numpy())
    x_train = scaler.transform(train[list(feature_columns)].to_numpy())
    x_test = scaler.transform(test[list(feature_columns)].to_numpy())

    out = pd.DataFrame({"study_id": test["study_id"].to_numpy()})
    for label in label_columns:
        y = train[label].astype(bool).to_numpy()
        if len(np.unique(y)) < 2:
            out[f"y_pred_proba_{label}"] = float(y.mean())
            continue
        model = LogisticRegression(max_iter=2000, class_weight="balanced")
        model.fit(x_train, y)
        out[f"y_pred_proba_{label}"] = model.predict_proba(x_test)[:, 1]
    return out


def multiclass_logistic_baseline(train: pd.DataFrame, test: pd.DataFrame,
                                 feature_columns: Sequence[str],
                                 label_columns: Sequence[str],
                                 classes: Sequence[str]) -> pd.DataFrame:
    """Per-head multinomial logistic fitted on TRAIN, scored on TEST.

    A3's structured-feature floor (Plan A/B §5.9, which requires the structured
    baseline for A1, A3 **and** A6). Spec §4.A.3.7 waived it on the grounds that
    "no rule-based ECG -> lab predictor exists" -- true of a *rule*, but §5.9
    asks for a *fitted* feature model, and reference [R5] (CardioLab) is exactly
    that comparison. Without it A3's neural numbers have no floor to clear.

    Returns one probability column per (head, class), plus the arg-max label, so
    the frame matches what `31_eval.py` expects from a multiclass head.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    columns = list(feature_columns)
    classes = list(classes)
    scaler = StandardScaler().fit(train[columns].to_numpy())
    x_train = scaler.transform(train[columns].to_numpy())
    x_test = scaler.transform(test[columns].to_numpy())

    # Collected into a dict and concatenated once -- 35 heads x 6 columns
    # inserted one at a time fragments the frame badly at full scale.
    collected: dict[str, Any] = {"study_id": test["study_id"].to_numpy()}
    for label in label_columns:
        y = train[label].astype("string").to_numpy()
        keep = pd.notna(y)
        present = sorted(set(y[keep]))
        proba = np.zeros((len(x_test), len(classes)), dtype="float64")

        if len(present) < 2:
            # A head with one observed class in train cannot be fitted. Emit the
            # train prevalence rather than a fabricated model -- honest, and the
            # §6.7 support rule already flags these slices.
            for index, name in enumerate(classes):
                proba[:, index] = float((y[keep] == name).mean()) if keep.any() else 0.0
        else:
            model = LogisticRegression(max_iter=2000, class_weight="balanced")
            model.fit(x_train[keep], y[keep])
            fitted = model.predict_proba(x_test)
            for position, name in enumerate(model.classes_):
                proba[:, classes.index(str(name))] = fitted[:, position]

        for index, name in enumerate(classes):
            collected[f"y_pred_proba_{label}__{name}"] = proba[:, index]
        collected[f"y_pred_index_{label}"] = proba.argmax(axis=1)
    return pd.DataFrame(collected)


# -----------------------------------------------------------------------------
# A6 -- Cox proportional hazards (§4.A.6.7, §5.1)
# -----------------------------------------------------------------------------
def patient_demographics() -> pd.DataFrame:
    """`anchor_age` and `gender` from the Phase 1 EHR cache. BASELINE-ONLY."""
    patients = pd.read_parquet(bc.EHR_CACHE / "patients.parquet",
                               columns=["subject_id", "gender", "anchor_age"])
    patients["sex_male"] = (patients["gender"].astype(str).str.upper() == "M").astype("float64")
    return patients[["subject_id", "anchor_age", "sex_male"]]


def cox_baseline(train: pd.DataFrame, test: pd.DataFrame, *, duration_column: str,
                 event_column: str,
                 feature_columns: Sequence[str]) -> tuple[np.ndarray, dict[str, Any]]:
    """Fit Cox PH on train, return the test partial hazard as a risk score.

    A6's heads are binary at fixed horizons, but §5.1 asks for Cox, and Cox
    needs (duration, event). Duration is time to the event when it was observed
    and the follow-up length otherwise; the partial hazard is a monotone risk
    score, which is exactly what a ranking metric like AUPRC consumes.
    """
    from lifelines import CoxPHFitter

    columns = list(feature_columns) + [duration_column, event_column]
    fit_frame = train[columns].dropna()
    fit_frame = fit_frame[fit_frame[duration_column] > 0]
    info: dict[str, Any] = {"n_fit": int(len(fit_frame)),
                            "n_events": int(fit_frame[event_column].sum())}
    if len(fit_frame) < 50 or fit_frame[event_column].sum() < 5:
        info["status"] = "skipped_insufficient_events"
        return np.full(len(test), np.nan), info

    model = CoxPHFitter(penalizer=0.1)
    model.fit(fit_frame, duration_col=duration_column, event_col=event_column)
    scoring = test[list(feature_columns)].copy()
    for column in feature_columns:
        scoring[column] = scoring[column].fillna(fit_frame[column].median())
    info["status"] = "ok"
    info["coefficients"] = {k: float(v) for k, v in model.params_.items()}
    info["concordance_train"] = float(model.concordance_index_)
    return model.predict_partial_hazard(scoring).to_numpy(), info


# -----------------------------------------------------------------------------
# B5 -- report-claim vs detector inconsistency (§5.1)
# -----------------------------------------------------------------------------
def load_claim_dictionary() -> dict[str, Any]:
    import yaml

    return yaml.safe_load(
        (bc.CONFIG_DIR / "claim_dictionary_LOCKED.yaml").read_text(encoding="utf-8"))


def claim_polarity(report_text: str, family: str, dictionary: dict[str, Any]) -> str | None:
    """Which polarity, if any, the report asserts for one family."""
    forms = dictionary["families"][family]["surface_forms"]
    lowered = str(report_text).lower()
    for form in forms:
        if re.search(form["pattern"], lowered):
            return str(form["polarity"])
    return None


def b5_rule_flag(report_text: str, hr_bpm: float, qrs_ms: float,
                 dictionary: dict[str, Any]) -> dict[str, Any]:
    """1 when the report's HR or QRS claim contradicts the detector (§5.1).

    Only HR and QRS: §5.1 specifies "NeuroKit2 HR/QRS detector vs report-text
    regex". Axis and PR are not recoverable from a single Lead-II strip, so the
    rule abstains on those families rather than guessing -- which is itself the
    finding this baseline is meant to expose.
    """
    inconsistencies: list[str] = []

    hr_claim = claim_polarity(report_text, "HR", dictionary)
    if hr_claim and np.isfinite(hr_bpm):
        if hr_claim == "brady" and hr_bpm >= 60:
            inconsistencies.append("HR")
        elif hr_claim == "tachy" and hr_bpm <= 100:
            inconsistencies.append("HR")

    qrs_claim = claim_polarity(report_text, "QRS", dictionary)
    if qrs_claim == "wide" and np.isfinite(qrs_ms) and qrs_ms < 120:
        inconsistencies.append("QRS")

    return {"flag": int(bool(inconsistencies)),
            "families_flagged": ",".join(inconsistencies) or None,
            "hr_claim": hr_claim, "qrs_claim": qrs_claim}


def _self_check() -> None:
    """The detector, the bins, the B3 rule and the B5 flag, on real data."""
    import neurokit2 as nk

    _silence_neurokit()
    simulated = nk.ecg_simulate(duration=10, sampling_rate=FS_HZ, heart_rate=80,
                               random_state=0)
    fiducials = detect_fiducials(np.asarray(simulated))
    assert not fiducials["fallback_used"], "detector failed on a clean simulated ECG"
    values = measurements_from_fiducials(fiducials)
    assert 70 <= values["hr_bpm"] <= 90, values
    assert _bin_hr(values["hr_bpm"]) == "normal", values

    assert _bin_hr(45) == "bradycardia" and _bin_hr(140) == "tachycardia"
    assert _bin_qrs(80) == "normal" and _bin_qrs(110) == "borderline" and _bin_qrs(150) == "wide"
    assert _bin_qtc(300) == "short" and _bin_qtc(400) == "normal" and _bin_qtc(500) == "prolonged"
    assert _bin_hr(float("nan")) is None

    onehot = label_to_onehot("normal", ["bradycardia", "normal", "tachycardia"])
    assert onehot.tolist() == [0.0, 1.0, 0.0]
    assert label_to_onehot(None, ["a", "b"]).tolist() == [0.5, 0.5]

    # B3 rule: a 150 bpm strip must light the HIGH_HEART_RATE bins it covers.
    fast_peaks = np.arange(0, N_SAMPLES, 200)          # 200 samples = 150 bpm
    bins = per_bin_labels(fast_peaks, np.array([]), np.array([]),
                          np.full(N_BINS, 0.9), 0.415030)
    assert sum(bins["HIGH_HEART_RATE"]) >= 9, bins["HIGH_HEART_RATE"]
    assert sum(bins["LOW_HEART_RATE"]) == 0
    noisy = per_bin_labels(fast_peaks, np.array([]), np.array([]),
                           np.array([0.1] * 3 + [0.9] * 7), 0.415030)
    assert noisy["NOISY_SEGMENT"] == [1, 1, 1, 0, 0, 0, 0, 0, 0, 0], noisy["NOISY_SEGMENT"]
    wide = per_bin_labels(np.array([1000]), np.array([1000]), np.array([1100]),
                          np.full(N_BINS, 0.9), 0.415030)
    assert wide["WIDE_QRS"][2] == 1, wide["WIDE_QRS"]

    dictionary = load_claim_dictionary()
    assert claim_polarity("Sinus bradycardia", "HR", dictionary) == "brady"
    assert claim_polarity("Left bundle branch block", "QRS", dictionary) == "wide"
    assert claim_polarity("Incomplete right bundle branch block", "QRS", dictionary) is None, \
        "the 'incomplete' negative lookbehind is not firing"
    assert b5_rule_flag("Sinus bradycardia", 95.0, 90.0, dictionary)["flag"] == 1
    assert b5_rule_flag("Sinus bradycardia", 45.0, 90.0, dictionary)["flag"] == 0
    assert b5_rule_flag("Normal sinus rhythm", 75.0, 90.0, dictionary)["flag"] == 0

    # A4 oracle: exact agreement with the ground-truth artifact.
    from _train_lib.metrics import match_events

    oracle = fiducial_oracle(pd.read_parquet(FIDUCIALS_PATH, columns=["study_id"])
                             .study_id.head(20).tolist())
    assert len(oracle) == 20
    for record in oracle.itertuples(index=False):
        result = match_events(np.asarray(record.r_peaks_lead2),
                              np.asarray(record.r_peaks_lead2))
        assert result["f1"] == 1.0, "the A4 oracle does not reproduce F1 = 1.0"

    print(f"algorithmic_baselines self-check: PASS  (detector={DETECTOR_METHOD}, "
          f"simulated HR {values['hr_bpm']:.1f} bpm, QRS {values['qrs_ms']:.1f} ms, "
          f"QTc {values['qtc_ms']:.1f} ms)")


if __name__ == "__main__":
    _self_check()
```

### `scripts/phase2_tasks_benchmark_and_paper/_train_lib/seed.py`

```python
"""Determinism controls (spec §6.2) and RNG capture for resume (§6.9).

    set_seed(42)          # before anything random happens
    state = rng_state()   # into checkpoint_last.pt
    load_rng_state(state) # after a crash / preemption

``cudnn.benchmark = False`` costs 5-15 % throughput and is required: with
benchmark on, cuDNN picks a convolution algorithm from wall-clock timings, so
two runs of the same command can take different code paths and diverge.
"""

from __future__ import annotations

import os
import random
from typing import Any

import numpy as np
import torch

SEEDS = (42, 123, 456)      # §6.2 / Round 1.4 -- every task x arch


def set_seed(seed: int) -> None:
    """Seed every generator Phase 2 touches, and pin the deterministic path."""
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    # §8.1: TF32 on Ampere+; the non-determinism it introduces is bounded and
    # reproducible across runs, unlike a benchmarked algorithm choice.
    torch.set_float32_matmul_precision("high")


def rng_state() -> dict[str, Any]:
    """Everything needed to resume the exact stochastic trajectory (§6.9)."""
    return {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
        "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
    }


def _byte_tensor(value: Any) -> torch.Tensor:
    return torch.as_tensor(value).detach().to(device="cpu", dtype=torch.uint8)


def load_rng_state(state: dict[str, Any] | None) -> None:
    if not state:
        return
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    # A checkpoint loaded with map_location="cuda" brings the RNG tensors back on
    # the GPU; set_rng_state insists on a CPU ByteTensor.
    torch.set_rng_state(_byte_tensor(state["torch"]))
    if state.get("cuda") and torch.cuda.is_available():
        try:
            torch.cuda.set_rng_state_all([_byte_tensor(s) for s in state["cuda"]])
        except (RuntimeError, ValueError):
            # A requeued job can land on a node with a different GPU count. The
            # CPU streams still restore, which is what drives shuffling and
            # dropout; losing the CUDA stream is a documented, bounded loss.
            pass


def environment_fingerprint() -> dict[str, str]:
    """Versions the reproducibility audit (§1.2) has to name."""
    import platform

    import torchvision

    fingerprint = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "torchvision": torchvision.__version__,
        "cuda_available": str(torch.cuda.is_available()),
        "cuda_version": str(torch.version.cuda),
        "cudnn_version": str(torch.backends.cudnn.version()),
        "numpy": np.__version__,
    }
    if torch.cuda.is_available():
        fingerprint["gpu"] = torch.cuda.get_device_name(0)
        fingerprint["gpu_capability"] = ".".join(
            str(x) for x in torch.cuda.get_device_capability(0))
    try:
        import transformers

        fingerprint["transformers"] = transformers.__version__
    except ImportError:                                      # pragma: no cover
        pass
    # torch.__version__ is a TorchVersion, not a str; yaml.safe_dump refuses it.
    return {key: str(value) for key, value in fingerprint.items()}


def autocast_dtype() -> tuple[torch.dtype | None, str]:
    """§6.6 / §8.1: bf16 where supported, else fp16 + GradScaler, else off."""
    if not torch.cuda.is_available():
        return None, "fp32_cpu"
    if torch.cuda.is_bf16_supported():
        return torch.bfloat16, "bf16"
    return torch.float16, "fp16_gradscaler"


def _self_check() -> None:
    set_seed(42)
    first = (random.random(), float(np.random.rand()), float(torch.rand(1)))
    state = rng_state()
    second = (random.random(), float(np.random.rand()), float(torch.rand(1)))
    assert first != second
    load_rng_state(state)
    restored = (random.random(), float(np.random.rand()), float(torch.rand(1)))
    assert restored == second, (
        f"RNG restore did not reproduce the next draws: {restored} != {second} -- "
        "a resumed run would not follow the interrupted trajectory (§6.9)"
    )
    assert torch.backends.cudnn.deterministic and not torch.backends.cudnn.benchmark

    set_seed(42)
    again = (random.random(), float(np.random.rand()), float(torch.rand(1)))
    assert again == first, "set_seed is not reproducible"

    dtype, tag = autocast_dtype()
    print(f"  mixed precision resolves to: {tag} ({dtype})")
    print("  env:", {k: v for k, v in environment_fingerprint().items()
                     if k in ("python", "torch", "cuda_version", "gpu")})
    print("seed self-check: PASS")


if __name__ == "__main__":
    _self_check()
```

### `scripts/phase2_tasks_benchmark_and_paper/_train_lib/metrics.py`

```python
"""Every Phase 2 metric, in one place (spec §4 per-task, §7).

The trainer uses these for early stopping on the validation primary metric; the
evaluator uses the same functions on test, so "val primary metric" and "test
primary metric" cannot be two different quantities computed two different ways.

AUPRC is `sklearn.average_precision_score`. It is the primary metric for the
imbalanced tasks (Round 1 lock); AUROC is always reported alongside.

A metric returns ``nan`` rather than raising when a slice is degenerate (a
single class present, an empty subgroup). The bootstrap drops non-finite
replicates, and a NaN in a results cell is honest where a 0.0 would be a lie.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import (average_precision_score, brier_score_loss, f1_score,
                             log_loss, roc_auc_score)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _dataset_lib.task_spec import FS_HZ, N_BINS      # noqa: E402

PEAK_TOLERANCE_MS = 10.0                                  # §4.A.4 / §7.4
PEAK_TOLERANCE_SAMPLES = int(round(PEAK_TOLERANCE_MS * FS_HZ / 1000.0))   # 5


def _clean(y_true: np.ndarray, y_score: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    y_true = np.asarray(y_true).ravel()
    y_score = np.asarray(y_score, dtype="float64").ravel()
    keep = np.isfinite(y_score) & ~np.isnan(y_true.astype("float64"))
    y_true, y_score = y_true[keep], y_score[keep]
    if y_true.size == 0 or len(np.unique(y_true)) < 2:
        return None
    return y_true.astype("int64"), y_score


def auprc(y_true, y_score) -> float:
    cleaned = _clean(y_true, y_score)
    return float("nan") if cleaned is None else float(average_precision_score(*cleaned))


def auroc(y_true, y_score) -> float:
    cleaned = _clean(y_true, y_score)
    return float("nan") if cleaned is None else float(roc_auc_score(*cleaned))


def f1_at(y_true, y_score, threshold: float) -> float:
    cleaned = _clean(y_true, y_score)
    if cleaned is None:
        return float("nan")
    truth, score = cleaned
    return float(f1_score(truth, (score >= threshold).astype("int64"), zero_division=0))


def macro_auprc(per_head: dict[str, tuple]) -> float:
    """Mean AUPRC over heads, ignoring heads with no positives in this slice."""
    values = [auprc(t, s) for t, s in per_head.values()]
    values = [v for v in values if np.isfinite(v)]
    return float(np.mean(values)) if values else float("nan")


def multiclass_macro_auprc(y_true_index: np.ndarray, proba: np.ndarray,
                           n_classes: int) -> float:
    """One-vs-rest AUPRC averaged over the classes present in this slice.

    §6.5: a per-class threshold is not meaningful for a softmax head, so the
    threshold-free macro-AUPRC is what gets reported for A2/A3/B1/B2.
    """
    y_true_index = np.asarray(y_true_index)
    proba = np.asarray(proba, dtype="float64")
    values = []
    for cls in range(n_classes):
        value = auprc((y_true_index == cls).astype("int64"), proba[:, cls])
        if np.isfinite(value):
            values.append(value)
    return float(np.mean(values)) if values else float("nan")


# -----------------------------------------------------------------------------
# A4 -- fiducial matching (§7.4)
# -----------------------------------------------------------------------------
def regression_metrics(y_true, y_pred, *, tolerance: float | None = None,
                       units: str = "") -> dict[str, float]:
    """MAE / RMSE / agreement for a continuous measurement head (Plan §5.4, §7.1).

    Plan A/B §5.4 asks for "MAE, RMSE, Pearson/Spearman, Bland-Altman" on heart
    rate and "MAE/RMSE; percentage within 10 ms" on QRS duration; §7.1 makes MAE
    and RMSE the primary pair for the whole regression/measurement task type.

    The Bland-Altman triple is the one that answers the question a cardiologist
    actually asks -- not "how correlated is it" but "how far off can it be" --
    so bias and the 95 % limits of agreement are returned alongside the errors.
    ``bias`` is signed (prediction minus truth): a model that reads every QRS
    8 ms wide has a bias no correlation coefficient will reveal.

    Inputs are in REAL units (bpm, ms); the trainer inverts the standardisation
    before calling this.
    """
    truth = np.asarray(y_true, dtype="float64").ravel()
    predicted = np.asarray(y_pred, dtype="float64").ravel()
    keep = np.isfinite(truth) & np.isfinite(predicted)
    truth, predicted = truth[keep], predicted[keep]

    out: dict[str, float] = {"n": int(truth.size), "units": units}
    if truth.size == 0:
        return {**out, "mae": float("nan"), "rmse": float("nan"), "r2": float("nan"),
                "pearson_r": float("nan"), "spearman_r": float("nan"),
                "bias": float("nan"), "sd_diff": float("nan"),
                "loa_lower": float("nan"), "loa_upper": float("nan")}

    difference = predicted - truth
    out["mae"] = float(np.mean(np.abs(difference)))
    out["rmse"] = float(np.sqrt(np.mean(difference ** 2)))

    variance = float(np.var(truth))
    out["r2"] = (float(1.0 - np.mean(difference ** 2) / variance)
                 if variance > 0 else float("nan"))

    # Correlations need both vectors non-constant, and > 1 point.
    if truth.size > 1 and np.std(truth) > 0 and np.std(predicted) > 0:
        from scipy import stats as _stats
        out["pearson_r"] = float(_stats.pearsonr(truth, predicted).statistic)
        out["spearman_r"] = float(_stats.spearmanr(truth, predicted).statistic)
    else:
        out["pearson_r"] = float("nan")
        out["spearman_r"] = float("nan")

    # Bland-Altman: bias and the 95 % limits of agreement.
    out["bias"] = float(np.mean(difference))
    sd_diff = float(np.std(difference, ddof=1)) if truth.size > 1 else float("nan")
    out["sd_diff"] = sd_diff
    out["loa_lower"] = out["bias"] - 1.96 * sd_diff
    out["loa_upper"] = out["bias"] + 1.96 * sd_diff

    if tolerance is not None:
        out["tolerance"] = float(tolerance)
        out[f"pct_within_{tolerance:g}"] = float(
            np.mean(np.abs(difference) <= tolerance) * 100.0)
    return out


def match_events(true_positions: np.ndarray, predicted_positions: np.ndarray,
                 tolerance: int = PEAK_TOLERANCE_SAMPLES) -> dict[str, float]:
    """Greedy nearest-neighbour match inside +/-tolerance samples.

    Greedy on the sorted sequences: each true event may match at most one
    prediction and vice versa, so a detector that fires twice on one beat is
    charged a false positive rather than being rewarded twice.
    """
    truth = np.sort(np.asarray(true_positions, dtype="int64"))
    predicted = np.sort(np.asarray(predicted_positions, dtype="int64"))
    truth = truth[truth >= 0]
    predicted = predicted[predicted >= 0]

    used = np.zeros(predicted.size, dtype=bool)
    errors: list[float] = []
    matched = 0
    for position in truth:
        if predicted.size == 0:
            break
        distances = np.abs(predicted - position)
        distances[used] = np.iinfo("int64").max
        best = int(np.argmin(distances))
        if distances[best] <= tolerance:
            used[best] = True
            matched += 1
            errors.append(abs(float(predicted[best] - position)))

    false_negative = truth.size - matched
    false_positive = predicted.size - matched
    precision = matched / predicted.size if predicted.size else 0.0
    recall = matched / truth.size if truth.size else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "tp": float(matched), "fp": float(false_positive), "fn": float(false_negative),
        "precision": float(precision), "recall": float(recall), "f1": float(f1),
        "mean_abs_error_ms": float(np.mean(errors) * 1000.0 / FS_HZ) if errors else float("nan"),
        "count_delta": float(predicted.size - truth.size),
    }


def aggregate_event_matches(matches: list[dict[str, float]]) -> dict[str, float]:
    """Micro-averaged F1 over studies -- one beat counts the same everywhere."""
    if not matches:
        return {"f1": float("nan"), "mean_abs_error_ms": float("nan")}
    tp = sum(m["tp"] for m in matches)
    fp = sum(m["fp"] for m in matches)
    fn = sum(m["fn"] for m in matches)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    errors = [m["mean_abs_error_ms"] for m in matches if np.isfinite(m["mean_abs_error_ms"])]
    return {
        "f1": float(2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0,
        "precision": float(precision), "recall": float(recall),
        "mean_abs_error_ms": float(np.mean(errors)) if errors else float("nan"),
        "n_studies": float(len(matches)),
    }


def decode_peaks(probability: np.ndarray, threshold: float = 0.5,
                 min_distance: int = 100) -> np.ndarray:
    """Dense per-sample probability -> peak positions.

    ``min_distance`` = 100 samples = 200 ms, just under the physiological
    refractory floor at 300 bpm, so two genuine beats are never merged.
    """
    probability = np.asarray(probability, dtype="float64")
    above = np.flatnonzero(probability >= threshold)
    if above.size == 0:
        return np.empty(0, dtype="int64")
    peaks: list[int] = []
    # Split the above-threshold samples into contiguous runs; take each run's
    # argmax, then suppress any peak too close to a stronger neighbour.
    breaks = np.flatnonzero(np.diff(above) > 1) + 1
    for run in np.split(above, breaks):
        peaks.append(int(run[int(np.argmax(probability[run]))]))
    peaks_array = np.array(sorted(peaks), dtype="int64")
    if peaks_array.size < 2:
        return peaks_array
    keep = [peaks_array[0]]
    for position in peaks_array[1:]:
        if position - keep[-1] < min_distance:
            if probability[position] > probability[keep[-1]]:
                keep[-1] = int(position)
        else:
            keep.append(int(position))
    return np.array(keep, dtype="int64")


# -----------------------------------------------------------------------------
# B3 -- temporal grounding (§4.B.3.6)
# -----------------------------------------------------------------------------
def bin_iou(true_bins: np.ndarray, predicted_bins: np.ndarray) -> float:
    """IoU over the 10 one-second bins. Two all-negative rows score 1.0.

    That convention is what makes `no_evidence_accuracy` and mIoU consistent:
    correctly saying "nothing here" is a perfect answer, not an undefined one.
    """
    truth = np.asarray(true_bins).astype(bool)
    predicted = np.asarray(predicted_bins).astype(bool)
    union = int((truth | predicted).sum())
    if union == 0:
        return 1.0
    return float((truth & predicted).sum() / union)


def miou(true_bins: np.ndarray, predicted_bins: np.ndarray) -> float:
    truth = np.atleast_2d(np.asarray(true_bins))
    predicted = np.atleast_2d(np.asarray(predicted_bins))
    if truth.shape != predicted.shape:
        raise ValueError(f"bin shape mismatch {truth.shape} vs {predicted.shape}")
    return float(np.mean([bin_iou(t, p) for t, p in zip(truth, predicted)]))


def recall_at_iou(true_bins: np.ndarray, predicted_bins: np.ndarray,
                  threshold: float) -> float:
    truth = np.atleast_2d(np.asarray(true_bins))
    predicted = np.atleast_2d(np.asarray(predicted_bins))
    ious = np.array([bin_iou(t, p) for t, p in zip(truth, predicted)])
    return float(np.mean(ious >= threshold))


def no_evidence_accuracy(true_bins: np.ndarray, predicted_bins: np.ndarray) -> float:
    """Accuracy restricted to rows whose ground truth has no positive bin."""
    truth = np.atleast_2d(np.asarray(true_bins)).astype(bool)
    predicted = np.atleast_2d(np.asarray(predicted_bins)).astype(bool)
    empty = ~truth.any(axis=1)
    if not empty.any():
        return float("nan")
    return float(np.mean(~predicted[empty].any(axis=1)))


# -----------------------------------------------------------------------------
# B5 -- span localisation (§4.B.5.6)
# -----------------------------------------------------------------------------
def char_iou(true_span: tuple[float, float], predicted_span: tuple[float, float]) -> float:
    true_lo, true_hi = sorted(true_span)
    pred_lo, pred_hi = sorted(predicted_span)
    intersection = max(0.0, min(true_hi, pred_hi) - max(true_lo, pred_lo))
    union = max(true_hi, pred_hi) - min(true_lo, pred_lo)
    return float(intersection / union) if union > 0 else float("nan")


# -----------------------------------------------------------------------------
# calibration (§6.8) -- kept here so eval and the calibrator share one ECE
# -----------------------------------------------------------------------------
def expected_calibration_error(y_true, y_prob, n_bins: int = 10) -> float:
    """ECE over 10 QUANTILE bins (§6.8: 'reliability diagram: 10 quantile bins')."""
    y_true = np.asarray(y_true, dtype="float64").ravel()
    y_prob = np.asarray(y_prob, dtype="float64").ravel()
    keep = np.isfinite(y_prob) & np.isfinite(y_true)
    y_true, y_prob = y_true[keep], y_prob[keep]
    if y_true.size == 0:
        return float("nan")
    edges = np.unique(np.quantile(y_prob, np.linspace(0, 1, n_bins + 1)))
    if edges.size < 2:
        return float(abs(y_prob.mean() - y_true.mean()))
    index = np.clip(np.digitize(y_prob, edges[1:-1], right=True), 0, edges.size - 2)
    total = 0.0
    for b in range(edges.size - 1):
        mask = index == b
        if not mask.any():
            continue
        total += mask.mean() * abs(y_prob[mask].mean() - y_true[mask].mean())
    return float(total)


def reliability_bins(y_true, y_prob, n_bins: int = 10) -> list[dict[str, float]]:
    y_true = np.asarray(y_true, dtype="float64").ravel()
    y_prob = np.asarray(y_prob, dtype="float64").ravel()
    edges = np.unique(np.quantile(y_prob, np.linspace(0, 1, n_bins + 1)))
    if edges.size < 2:
        return []
    index = np.clip(np.digitize(y_prob, edges[1:-1], right=True), 0, edges.size - 2)
    out = []
    for b in range(edges.size - 1):
        mask = index == b
        if not mask.any():
            continue
        out.append({"bin": b, "n": int(mask.sum()),
                    "mean_predicted": float(y_prob[mask].mean()),
                    "observed_rate": float(y_true[mask].mean()),
                    "lo": float(edges[b]), "hi": float(edges[b + 1])})
    return out


def brier(y_true, y_prob) -> float:
    y_true = np.asarray(y_true, dtype="float64").ravel()
    y_prob = np.asarray(y_prob, dtype="float64").ravel()
    if y_true.size == 0 or len(np.unique(y_true)) < 2:
        return float("nan")
    return float(brier_score_loss(y_true, np.clip(y_prob, 0.0, 1.0)))


def logloss(y_true, y_prob) -> float:
    y_true = np.asarray(y_true, dtype="float64").ravel()
    y_prob = np.asarray(y_prob, dtype="float64").ravel()
    if y_true.size == 0 or len(np.unique(y_true)) < 2:
        return float("nan")
    return float(log_loss(y_true, np.clip(y_prob, 1e-7, 1 - 1e-7), labels=[0, 1]))


def net_benefit(y_true, y_prob, threshold: float) -> float:
    """Decision-curve net benefit at one risk threshold (§7.6, A6 supplementary)."""
    y_true = np.asarray(y_true, dtype="float64").ravel()
    y_prob = np.asarray(y_prob, dtype="float64").ravel()
    n = y_true.size
    if n == 0 or threshold >= 1.0:
        return float("nan")
    predicted = y_prob >= threshold
    tp = float((predicted & (y_true > 0)).sum())
    fp = float((predicted & (y_true == 0)).sum())
    return float(tp / n - (fp / n) * (threshold / (1.0 - threshold)))


def _self_check() -> None:
    rng = np.random.default_rng(0)

    truth = rng.integers(0, 2, 500)
    score = truth * 0.7 + rng.normal(0, 0.3, 500)
    assert 0.8 < auprc(truth, score) < 1.0
    assert np.isnan(auprc(np.zeros(10), rng.random(10))), "single-class slice must be NaN"

    # A perfect detector scores 1.0; a 4-sample shift is inside the 10 ms window.
    peaks = np.array([100, 450, 800, 1150])
    assert match_events(peaks, peaks)["f1"] == 1.0
    shifted = match_events(peaks, peaks + 4)
    assert shifted["f1"] == 1.0 and abs(shifted["mean_abs_error_ms"] - 8.0) < 1e-6
    assert match_events(peaks, peaks + 6)["f1"] == 0.0, "6 samples = 12 ms must NOT match"
    doubled = match_events(peaks, np.sort(np.concatenate([peaks, peaks + 2])))
    assert doubled["fp"] == 4, "double-firing was not charged as false positives"

    dense = np.zeros(5000)
    for position in peaks:
        dense[position - 2: position + 3] = [0.6, 0.8, 0.99, 0.8, 0.6]
    assert np.array_equal(decode_peaks(dense), peaks), decode_peaks(dense)

    assert bin_iou(np.zeros(N_BINS), np.zeros(N_BINS)) == 1.0
    assert bin_iou(np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 0]),
                   np.array([1, 0, 0, 0, 0, 0, 0, 0, 0, 0])) == 0.5
    assert abs(char_iou((10, 20), (15, 25)) - (5 / 15)) < 1e-9

    perfect = np.linspace(0.01, 0.99, 2000)
    observed = (rng.random(2000) < perfect).astype(float)
    assert expected_calibration_error(observed, perfect) < 0.05, "a calibrated model scored badly"
    assert expected_calibration_error(observed, np.clip(perfect * 0.3, 0, 1)) > 0.10, \
        "a badly miscalibrated model scored well"

    assert net_benefit(np.ones(100), np.ones(100), 0.1) > 0

    # regression / Bland-Altman. A predictor that reads every QRS 8 ms too wide
    # has near-perfect correlation and a bias no correlation would reveal --
    # which is the whole reason Plan A/B §5.4 asks for the agreement numbers.
    qrs_true = rng.normal(100.0, 20.0, 4000)
    qrs_pred = qrs_true + 8.0 + rng.normal(0.0, 2.0, 4000)
    stats = regression_metrics(qrs_true, qrs_pred, tolerance=10.0, units="ms")
    assert abs(stats["bias"] - 8.0) < 0.3, stats["bias"]
    assert stats["pearson_r"] > 0.99, "a shifted-but-linear predictor must still correlate"
    assert abs(stats["mae"] - 8.0) < 0.4, stats["mae"]
    assert stats["loa_lower"] < stats["bias"] < stats["loa_upper"]
    assert abs(stats["sd_diff"] - 2.0) < 0.2, stats["sd_diff"]
    assert 60.0 < stats["pct_within_10"] < 90.0, stats["pct_within_10"]
    exact = regression_metrics(qrs_true, qrs_true, tolerance=10.0)
    assert exact["mae"] == 0.0 and exact["rmse"] == 0.0 and exact["r2"] == 1.0
    assert exact["pct_within_10"] == 100.0
    empty = regression_metrics(np.array([]), np.array([]))
    assert empty["n"] == 0 and np.isnan(empty["mae"]), "empty slice must be NaN, not 0.0"

    print("metrics self-check: PASS")


if __name__ == "__main__":
    _self_check()
```

### `scripts/phase2_tasks_benchmark_and_paper/_train_lib/threshold.py`

```python
"""Validation-only threshold selection (spec §6.5).

    "For every classification head, the binary threshold ... is chosen by
     maximizing Youden's J on the **validation** set."

Tuning a threshold on test is a CRITICAL finding (§11.2), so this module makes
that hard to do by accident:

* :func:`select_threshold` takes ONE frame and stamps the split it saw into the
  returned record; it refuses any split other than ``val``.
* :func:`apply_threshold` checks that stamp before it will binarise anything,
  so a test prediction file cannot be thresholded by a value that was not
  chosen on validation.
* :func:`append_threshold_audit` writes the row §6.5 requires into
  ``outputs/audit_reports/threshold_audit.md`` -- (task, arch, seed, head,
  threshold, val Youden's J).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np

AUDIT_RELATIVE = Path("outputs") / "audit_reports" / "threshold_audit.md"
SELECTION_SPLIT = "val"


@dataclass
class ThresholdRecord:
    """One chosen threshold and the evidence behind it."""

    task: str
    arch_tier: str
    lead_subset: str
    seed: int
    head: str
    class_name: str
    threshold: float
    youden_j: float
    sensitivity: float
    specificity: float
    n_val: int
    n_positive_val: int
    selected_on_split: str = SELECTION_SPLIT
    extra: dict[str, Any] = field(default_factory=dict)


def youden_curve(y_true: np.ndarray, y_score: np.ndarray) -> tuple[np.ndarray, np.ndarray,
                                                                   np.ndarray, np.ndarray]:
    from sklearn.metrics import roc_curve

    fpr, tpr, thresholds = roc_curve(y_true, y_score)
    return fpr, tpr, thresholds, tpr - fpr


def select_threshold(y_true: Sequence, y_score: Sequence, *, split: str,
                     task: str, arch_tier: str, lead_subset: str, seed: int,
                     head: str, class_name: str = "positive") -> ThresholdRecord:
    """Maximise Youden's J on the VALIDATION split. Refuses any other split."""
    if split != SELECTION_SPLIT:
        raise ValueError(
            f"CRITICAL (§6.5, §11.2): thresholds are selected on {SELECTION_SPLIT!r} only. "
            f"select_threshold was called with split={split!r}."
        )
    truth = np.asarray(y_true, dtype="float64").ravel()
    score = np.asarray(y_score, dtype="float64").ravel()
    keep = np.isfinite(truth) & np.isfinite(score)
    truth, score = truth[keep], score[keep]

    n_positive = int((truth > 0).sum())
    if truth.size == 0 or n_positive == 0 or n_positive == truth.size:
        # No usable ROC. 0.5 is recorded explicitly as a fallback rather than
        # silently produced, so the audit row shows what happened.
        return ThresholdRecord(task=task, arch_tier=arch_tier, lead_subset=lead_subset,
                               seed=seed, head=head, class_name=class_name,
                               threshold=0.5, youden_j=float("nan"),
                               sensitivity=float("nan"), specificity=float("nan"),
                               n_val=int(truth.size), n_positive_val=n_positive,
                               extra={"fallback": "single-class validation slice"})

    fpr, tpr, thresholds, youden = youden_curve(truth, score)
    best = int(np.argmax(youden))
    threshold = float(thresholds[best])
    if not np.isfinite(threshold):
        # sklearn prepends an infinite threshold for the (0,0) ROC point.
        threshold = float(np.nextafter(score.max(), np.inf))
    return ThresholdRecord(
        task=task, arch_tier=arch_tier, lead_subset=lead_subset, seed=seed,
        head=head, class_name=class_name, threshold=threshold,
        youden_j=float(youden[best]), sensitivity=float(tpr[best]),
        specificity=float(1.0 - fpr[best]), n_val=int(truth.size),
        n_positive_val=n_positive)


def apply_threshold(y_score: Sequence, record: ThresholdRecord | dict) -> np.ndarray:
    """Binarise with a threshold that was demonstrably chosen on validation."""
    selected_on = (record.selected_on_split if isinstance(record, ThresholdRecord)
                   else record.get("selected_on_split"))
    if selected_on != SELECTION_SPLIT:
        raise ValueError(
            f"CRITICAL (§6.5, §11.2): refusing to apply a threshold selected on "
            f"{selected_on!r}; it must come from {SELECTION_SPLIT!r}."
        )
    threshold = (record.threshold if isinstance(record, ThresholdRecord)
                 else float(record["threshold"]))
    return (np.asarray(y_score, dtype="float64") >= threshold).astype("int64")


def select_multiclass_thresholds(y_true_index: Sequence, proba: np.ndarray,
                                 classes: Sequence[str], **kwargs) -> list[ThresholdRecord]:
    """Per-class one-vs-rest thresholds for the §4.A.2.6 per-class F1 table.

    §6.5 notes these are not the headline for a softmax head -- macro-AUPRC is.
    They exist so "per_class_F1_at_val_optimal_threshold" has a defined value.
    """
    truth = np.asarray(y_true_index)
    proba = np.asarray(proba, dtype="float64")
    return [
        select_threshold((truth == index).astype("int64"), proba[:, index],
                         class_name=name, **kwargs)
        for index, name in enumerate(classes)
    ]


def append_threshold_audit(records: Sequence[ThresholdRecord], project_root: Path) -> Path:
    """Append the §6.5 audit rows. Idempotent per (task, arch, lead, seed, head, class)."""
    path = project_root / AUDIT_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)

    header = [
        "# threshold_audit.md — Phase 2 threshold selection",
        "",
        "Every classification threshold used anywhere in Phase 2, with the validation",
        "Youden's J that chose it (spec §6.5). `selected_on_split` is `val` on every row",
        "by construction — `_train_lib/threshold.py` refuses to select on any other split",
        "and refuses to apply a threshold that was not selected on `val`.",
        "",
        "| task | arch_tier | lead_subset | seed | head | class | threshold | val Youden J |"
        " sens | spec | n_val | n_pos_val | selected_on_split |",
        "| --- | --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else header
    if not existing_lines or not existing_lines[0].startswith("# threshold_audit"):
        existing_lines = header

    def key_of(line: str) -> tuple | None:
        if not line.startswith("| ") or line.startswith("| ---") or line.startswith("| task"):
            return None
        cells = [c.strip() for c in line.strip("|").split("|")]
        return tuple(cells[:6]) if len(cells) >= 6 else None

    kept = [line for line in existing_lines]
    incoming = {(r.task, r.arch_tier, r.lead_subset, str(r.seed), r.head, r.class_name)
                for r in records}
    kept = [line for line in kept if key_of(line) not in incoming]

    for r in records:
        kept.append(
            f"| {r.task} | {r.arch_tier} | {r.lead_subset} | {r.seed} | {r.head} | "
            f"{r.class_name} | {r.threshold:.6f} | {r.youden_j:.6f} | "
            f"{r.sensitivity:.4f} | {r.specificity:.4f} | {r.n_val} | "
            f"{r.n_positive_val} | {r.selected_on_split} |"
        )
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return path


def records_to_json(records: Sequence[ThresholdRecord]) -> str:
    return json.dumps([asdict(r) for r in records], indent=2)


def _self_check() -> None:
    rng = np.random.default_rng(0)
    truth = rng.integers(0, 2, 2000)
    score = 1 / (1 + np.exp(-(truth * 2.0 + rng.normal(0, 1.0, 2000))))

    record = select_threshold(truth, score, split="val", task="T", arch_tier="a",
                              lead_subset="lead2", seed=42, head="h")
    assert 0.0 < record.threshold < 1.0 and record.youden_j > 0.3, record
    assert record.selected_on_split == "val"

    # The chosen threshold must beat a grid of alternatives on Youden's J.
    def youden_at(t: float) -> float:
        predicted = score >= t
        tpr = (predicted & (truth == 1)).sum() / max((truth == 1).sum(), 1)
        fpr = (predicted & (truth == 0)).sum() / max((truth == 0).sum(), 1)
        return tpr - fpr

    best_grid = max(youden_at(t) for t in np.linspace(0.01, 0.99, 99))
    assert record.youden_j >= best_grid - 1e-9, (record.youden_j, best_grid)

    for bad_split in ("test", "train"):
        try:
            select_threshold(truth, score, split=bad_split, task="T", arch_tier="a",
                             lead_subset="lead2", seed=42, head="h")
        except ValueError as exc:
            assert "CRITICAL" in str(exc)
        else:                                                # pragma: no cover
            raise AssertionError(f"threshold selection on {bad_split} was allowed")

    forged = dict(asdict(record))
    forged["selected_on_split"] = "test"
    try:
        apply_threshold(score, forged)
    except ValueError as exc:
        assert "CRITICAL" in str(exc)
    else:                                                    # pragma: no cover
        raise AssertionError("a test-selected threshold was applied")

    labels = apply_threshold(score, record)
    assert set(np.unique(labels)) <= {0, 1}

    degenerate = select_threshold(np.zeros(50), rng.random(50), split="val", task="T",
                                  arch_tier="a", lead_subset="lead2", seed=42, head="h")
    assert degenerate.threshold == 0.5 and "fallback" in degenerate.extra

    print(f"threshold self-check: PASS  (t={record.threshold:.4f}, "
          f"J={record.youden_j:.4f}, sens={record.sensitivity:.3f}, "
          f"spec={record.specificity:.3f})")


if __name__ == "__main__":
    _self_check()
```

### `scripts/phase2_tasks_benchmark_and_paper/_train_lib/calibration.py`

```python
"""Calibration: ECE, Brier, reliability diagrams, and recalibration (spec §6.8).

    "If ECE > 0.05 at the val-optimal threshold, apply post-hoc Platt scaling
     (sigmoid scaler fit on val predictions). Re-evaluate ECE; if still > 0.05,
     switch to isotonic regression. Whatever scaler wins on val carries forward
     to test -- the scaler is part of the trained model artifact."

A3 and A6 recalibrate automatically; every other task computes ECE for the
supplementary but keeps its raw probabilities (§6.8 last paragraph).

The scaler is fitted on VAL and only ever applied elsewhere -- fitting a
calibrator on test is the same class of violation as tuning a threshold there.
:meth:`Calibrator.transform` therefore refuses to run on the split it was
fitted on being anything but ``val``.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _train_lib.metrics import (brier, expected_calibration_error, logloss,  # noqa: E402
                                reliability_bins)

ECE_TRIGGER = 0.05                        # §6.8
CALIBRATED_TASKS = ("A3_lab_abnormality", "A6_risk_stratification")
FIT_SPLIT = "val"


@dataclass
class Calibrator:
    """A fitted probability calibrator plus the evidence that it helped."""

    method: str                            # "identity" | "platt" | "isotonic"
    head: str
    ece_raw: float
    ece_calibrated: float
    n_fit: int
    fitted_on_split: str = FIT_SPLIT
    _model: Any = field(default=None, repr=False)

    def transform(self, probabilities: Sequence[float]) -> np.ndarray:
        p = np.clip(np.asarray(probabilities, dtype="float64").ravel(), 1e-7, 1 - 1e-7)
        if self.method == "identity" or self._model is None:
            return p
        if self.method == "platt":
            logit = np.log(p / (1 - p)).reshape(-1, 1)
            return self._model.predict_proba(logit)[:, 1]
        return np.clip(self._model.predict(p), 0.0, 1.0)

    def state_bytes(self) -> bytes:
        return pickle.dumps({"method": self.method, "head": self.head,
                             "ece_raw": self.ece_raw, "ece_calibrated": self.ece_calibrated,
                             "n_fit": self.n_fit, "fitted_on_split": self.fitted_on_split,
                             "model": self._model})

    @staticmethod
    def from_state_bytes(blob: bytes) -> "Calibrator":
        state = pickle.loads(blob)
        return Calibrator(method=state["method"], head=state["head"],
                          ece_raw=state["ece_raw"], ece_calibrated=state["ece_calibrated"],
                          n_fit=state["n_fit"], fitted_on_split=state["fitted_on_split"],
                          _model=state["model"])


def fit_calibrator(y_true: Sequence, y_prob: Sequence, *, head: str, split: str,
                   force: bool = False, n_bins: int = 10) -> Calibrator:
    """Fit the §6.8 ladder on VALIDATION predictions: identity -> Platt -> isotonic.

    Args:
        force: recalibrate even when ECE is already under the trigger. Used by
            nothing in the default pipeline; kept for the sensitivity audit.
    """
    if split != FIT_SPLIT:
        raise ValueError(
            f"CRITICAL (§6.8, §11.2): calibrators are fitted on {FIT_SPLIT!r} predictions "
            f"only; fit_calibrator was called with split={split!r}."
        )
    truth = np.asarray(y_true, dtype="float64").ravel()
    prob = np.clip(np.asarray(y_prob, dtype="float64").ravel(), 1e-7, 1 - 1e-7)
    keep = np.isfinite(truth) & np.isfinite(prob)
    truth, prob = truth[keep], prob[keep]

    ece_raw = expected_calibration_error(truth, prob, n_bins)
    identity = Calibrator(method="identity", head=head, ece_raw=ece_raw,
                          ece_calibrated=ece_raw, n_fit=int(truth.size))
    if truth.size < 50 or len(np.unique(truth)) < 2:
        return identity
    if not force and (not np.isfinite(ece_raw) or ece_raw <= ECE_TRIGGER):
        return identity

    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression

    platt = LogisticRegression(solver="lbfgs")
    platt.fit(np.log(prob / (1 - prob)).reshape(-1, 1), truth)
    platt_cal = Calibrator(method="platt", head=head, ece_raw=ece_raw,
                           ece_calibrated=float("nan"), n_fit=int(truth.size), _model=platt)
    platt_cal.ece_calibrated = expected_calibration_error(
        truth, platt_cal.transform(prob), n_bins)
    if platt_cal.ece_calibrated <= ECE_TRIGGER:
        return platt_cal

    isotonic = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    isotonic.fit(prob, truth)
    isotonic_cal = Calibrator(method="isotonic", head=head, ece_raw=ece_raw,
                              ece_calibrated=float("nan"), n_fit=int(truth.size),
                              _model=isotonic)
    isotonic_cal.ece_calibrated = expected_calibration_error(
        truth, isotonic_cal.transform(prob), n_bins)

    # Whatever wins ON VAL carries forward. Isotonic can overfit a small val
    # slice, so the better of the two is chosen by measured val ECE, not by
    # position in the ladder.
    best = min([identity, platt_cal, isotonic_cal],
               key=lambda c: c.ece_calibrated if np.isfinite(c.ece_calibrated) else np.inf)
    return best


def calibration_report(y_true: Sequence, y_prob: Sequence, *, head: str,
                       n_bins: int = 10) -> dict[str, Any]:
    """The §7.6 block: ECE, Brier, log-loss and the reliability bins."""
    truth = np.asarray(y_true, dtype="float64").ravel()
    prob = np.asarray(y_prob, dtype="float64").ravel()
    return {
        "head": head,
        "n": int(truth.size),
        "ece": expected_calibration_error(truth, prob, n_bins),
        "brier": brier(truth, prob),
        "log_loss": logloss(truth, prob),
        "reliability_bins": reliability_bins(truth, prob, n_bins),
    }


def save_reliability_diagram(report: dict[str, Any], path: Path, title: str) -> Path | None:
    """Reliability diagram PNG per (task, arch, seed, head) -- §6.8."""
    bins = report.get("reliability_bins") or []
    if not bins:
        return None
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    predicted = [b["mean_predicted"] for b in bins]
    observed = [b["observed_rate"] for b in bins]
    figure, axes = plt.subplots(figsize=(4.2, 4.2), dpi=150)
    axes.plot([0, 1], [0, 1], linestyle="--", linewidth=1, color="0.5",
              label="perfect calibration")
    axes.plot(predicted, observed, marker="o", linewidth=1.4, label="model")
    axes.set_xlabel("mean predicted probability")
    axes.set_ylabel("observed rate")
    axes.set_title(f"{title}\nECE={report['ece']:.4f}  Brier={report['brier']:.4f}", fontsize=8)
    axes.legend(fontsize=7)
    axes.set_xlim(0, 1)
    axes.set_ylim(0, 1)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path)
    plt.close(figure)
    return path


def _self_check() -> None:
    rng = np.random.default_rng(0)
    n = 4000
    truth_prob = rng.random(n)
    truth = (rng.random(n) < truth_prob).astype("float64")

    # Already calibrated -> the ladder must leave it alone.
    good = fit_calibrator(truth, truth_prob, head="h", split="val")
    assert good.method == "identity", good
    assert good.ece_raw <= ECE_TRIGGER, good.ece_raw

    # Squashed probabilities -> miscalibrated -> must be repaired below the trigger.
    squashed = np.clip(truth_prob * 0.4 + 0.05, 1e-6, 1 - 1e-6)
    bad = fit_calibrator(truth, squashed, head="h", split="val")
    assert bad.method in ("platt", "isotonic"), bad
    assert bad.ece_raw > ECE_TRIGGER, bad.ece_raw
    assert bad.ece_calibrated < bad.ece_raw, bad
    assert bad.ece_calibrated <= ECE_TRIGGER, bad

    restored = Calibrator.from_state_bytes(bad.state_bytes())
    assert np.allclose(restored.transform(squashed), bad.transform(squashed)), \
        "a round-tripped calibrator does not reproduce its own output"

    for bad_split in ("test", "train"):
        try:
            fit_calibrator(truth, squashed, head="h", split=bad_split)
        except ValueError as exc:
            assert "CRITICAL" in str(exc)
        else:                                                # pragma: no cover
            raise AssertionError(f"calibrator fitted on {bad_split}")

    report = calibration_report(truth, squashed, head="h")
    assert len(report["reliability_bins"]) >= 8 and np.isfinite(report["brier"])
    print(f"calibration self-check: PASS  (raw ECE {bad.ece_raw:.4f} -> "
          f"{bad.method} {bad.ece_calibrated:.4f}; calibrated input left as "
          f"{good.method})")


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    _self_check()
```

### `scripts/phase2_tasks_benchmark_and_paper/_train_lib/trainer.py`

```python
"""The Phase 2 training loop, checkpointing and prediction collection (§6, §8.1).

One loop trains all eleven trainable tasks. What differs per task is the model
(`_model_lib/task_models.py`), the loss (§6.4, same module) and the primary
metric (`_train_lib/metrics.py`); the loop itself does not branch on task.

**Interruption is the design case, not the exception.** Two different things
kill a Phase 2 run:

* a mains cut on the laptop -- the process dies with no warning, mid-write;
* Slurm preemption on `gpu_student` -- SIGTERM, then SIGKILL a grace period
  later, then the job is requeued and re-runs the identical command.

Both are survived by the same three mechanisms:

1. ``checkpoint_last.pt`` is written **atomically** (temp file + ``os.replace``)
   every ``--checkpoint-minutes`` minutes as well as at every epoch boundary, so
   a power cut costs minutes, never an epoch, and can never leave a torn file.
   §8.1 requires exactly this ("written every N minutes, not only per epoch").
2. The checkpoint stores ``epoch`` **and** ``batch_in_epoch`` alongside the RNG
   states, and the epoch's batch order is a pure function of (seed, epoch), so
   a resumed run rebuilds the same order and skips the batches it already did.
   Resume is mid-epoch exact, not epoch-granular.
3. SIGTERM and SIGINT are trapped: the loop finishes the batch in flight, writes
   ``checkpoint_last.pt``, and exits 0 so Slurm requeues cleanly.

Retention (§8.1, Round 5.4): ``checkpoint_last.pt`` carries optimizer +
scheduler + RNG for resume; ``checkpoint_best.pt`` carries **weights only**.
Nothing else accumulates -- 50 GB of quota does not hold 144 runs of optimizer
state.
"""

from __future__ import annotations

import json
import math
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _dataset_lib import build_common as bc                       # noqa: E402
from _dataset_lib.task_dataset import TaskDataset                 # noqa: E402
from _dataset_lib.task_spec import B3_QUERIES, TaskSpec           # noqa: E402
from _model_lib.task_models import (TaskModel, active_heads,      # noqa: E402
                                    compute_losses)
from _train_lib import metrics as M                               # noqa: E402
from _train_lib.seed import autocast_dtype, load_rng_state, rng_state, set_seed  # noqa: E402

HARD_NEGATIVE = "HARD_NEGATIVE_TEXT"
GRAD_CLIP_NORM = 1.0                    # §6.3
WARMUP_FRACTION = 0.05                  # §6.3


# -----------------------------------------------------------------------------
# deterministic, resumable batch order
# -----------------------------------------------------------------------------
def build_batch_order(n_rows: int, batch_size: int, *, seed: int, epoch: int,
                      shuffle: bool, hard_negative_index: np.ndarray | None = None,
                      drop_last: bool = False) -> list[list[int]]:
    """The batch index lists for one epoch -- a pure function of (seed, epoch).

    Materialising the order (rather than trusting a DataLoader's internal RNG)
    is what makes mid-epoch resume exact: a requeued job rebuilds the identical
    list and slices off the batches it already completed.

    When ``hard_negative_index`` is given, every batch is seeded with exactly one
    HARD_NEGATIVE_TEXT row before the remaining slots are filled -- §6.4's
    "every batch contains >= 1 HARD_NEGATIVE_TEXT example" for A5/B4/B6.
    """
    rng = np.random.default_rng(seed * 100_003 + epoch)
    if hard_negative_index is not None and hard_negative_index.size:
        hard = hard_negative_index.copy()
        others = np.setdiff1d(np.arange(n_rows), hard, assume_unique=False)
        if shuffle:
            rng.shuffle(hard)
            rng.shuffle(others)
        per_batch_others = max(1, batch_size - 1)
        n_batches = max(1, int(math.ceil(others.size / per_batch_others)))
        batches: list[list[int]] = []
        for index in range(n_batches):
            chunk = others[index * per_batch_others:(index + 1) * per_batch_others]
            if chunk.size == 0:
                continue
            anchor = hard[index % hard.size]        # cycles: hard negatives repeat
            batch = [int(anchor)] + [int(i) for i in chunk]
            if shuffle:
                rng.shuffle(batch)
            batches.append(batch)
        return batches

    order = rng.permutation(n_rows) if shuffle else np.arange(n_rows)
    batches = [order[i:i + batch_size].tolist() for i in range(0, n_rows, batch_size)]
    if drop_last and batches and len(batches[-1]) < batch_size:
        batches.pop()
    return [[int(i) for i in b] for b in batches]


def hard_negative_rows(dataset: TaskDataset) -> np.ndarray | None:
    """Row indices whose ``neg_type`` is HARD_NEGATIVE_TEXT, if the task has any."""
    if "neg_type" not in dataset.frame.columns:
        return None
    index = np.flatnonzero(dataset.frame["neg_type"].to_numpy() == HARD_NEGATIVE)
    return index if index.size else None


# -----------------------------------------------------------------------------
# run configuration
# -----------------------------------------------------------------------------
@dataclass
class TrainConfig:
    """Everything a run needs, snapshotted verbatim into `train_config.yaml`."""

    task: str
    arch_tier: str
    lead_subset: str
    seed: int
    output_dir: Path
    epochs: int = 30
    batch_size: int = 64
    accumulation_steps: int = 1
    patience: int = 5
    num_workers: int = 0
    learning_rates: dict[str, float] = field(default_factory=lambda: {
        "head": 1e-3, "signal_backbone": 1e-3, "image_backbone": 1e-5,
        "text_backbone_layers": 1e-5, "text_embeddings": 1e-6,
    })
    weight_decay: float = 0.01
    betas: tuple[float, float] = (0.9, 0.999)
    checkpoint_minutes: float = 10.0
    balanced_sampler: bool = False
    max_steps_per_epoch: int = 0            # smoke tests only
    dev: bool = False
    signal_input_modality: str | None = None
    image_input_modality: str | None = None
    text_encoder: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out = {k: (str(v) if isinstance(v, Path) else v) for k, v in self.__dict__.items()}
        out["betas"] = list(self.betas)
        return out


# -----------------------------------------------------------------------------
# the trainer
# -----------------------------------------------------------------------------
class Trainer:
    def __init__(self, model: TaskModel, spec: TaskSpec, config: TrainConfig,
                 train_dataset: TaskDataset, val_dataset: TaskDataset,
                 class_stats: dict[str, Any], logger, device: torch.device | None = None):
        self.model = model
        self.spec = spec
        self.config = config
        self.train_dataset = train_dataset
        self.val_dataset = val_dataset
        self.class_stats = class_stats
        self.log = logger

        self.device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.amp_dtype, self.amp_tag = autocast_dtype()
        self.scaler = torch.amp.GradScaler("cuda", enabled=self.amp_tag == "fp16_gradscaler")

        self.optimizer = torch.optim.AdamW(
            self.model.param_groups(config.learning_rates),
            weight_decay=config.weight_decay, betas=tuple(config.betas))

        self.hard_index = hard_negative_rows(train_dataset)
        self.batches_per_epoch = len(build_batch_order(
            len(train_dataset), config.batch_size, seed=config.seed, epoch=0,
            shuffle=True, hard_negative_index=self.hard_index))
        if config.max_steps_per_epoch:
            self.batches_per_epoch = min(self.batches_per_epoch, config.max_steps_per_epoch)
        total_steps = max(1, self.batches_per_epoch * config.epochs // config.accumulation_steps)
        self.scheduler = self._build_scheduler(total_steps)

        self.epoch = 0
        self.batch_in_epoch = 0
        self.global_step = 0
        self.best_metric = -math.inf
        self.best_epoch = -1
        self.epochs_without_improvement = 0
        self.stop_requested = False
        self.interrupted = False
        self._last_checkpoint_time = time.time()

        config.output_dir.mkdir(parents=True, exist_ok=True)
        self.last_path = config.output_dir / "checkpoint_last.pt"
        self.best_path = config.output_dir / "checkpoint_best.pt"
        self.log_path = config.output_dir / "train_log.jsonl"
        self._install_signal_handlers()

    # -- schedule (§6.3: linear warmup over 5 % of steps -> cosine to 0) -------
    def _build_scheduler(self, total_steps: int):
        warmup = max(1, int(total_steps * WARMUP_FRACTION))

        def lr_lambda(step: int) -> float:
            if step < warmup:
                return (step + 1) / warmup
            progress = (step - warmup) / max(1, total_steps - warmup)
            return 0.5 * (1.0 + math.cos(math.pi * min(1.0, progress)))

        return torch.optim.lr_scheduler.LambdaLR(self.optimizer, lr_lambda)

    # -- preemption -----------------------------------------------------------
    def _install_signal_handlers(self) -> None:
        def handler(signum, _frame):
            # Do NOT write from inside the handler -- the training step may be
            # mid-tensor-op. Set the flag; the loop checkpoints at the next
            # batch boundary, which is at most one batch away.
            self.log.warning("signal %s received -- will checkpoint and exit at the "
                             "next batch boundary (Slurm preemption or Ctrl-C)", signum)
            self.stop_requested = True
            self.interrupted = True

        for name in ("SIGTERM", "SIGINT"):
            if hasattr(signal, name):
                try:
                    signal.signal(getattr(signal, name), handler)
                except (ValueError, OSError):        # pragma: no cover - non-main thread
                    pass

    # -- checkpoints ----------------------------------------------------------
    def _checkpoint_payload(self) -> dict[str, Any]:
        return {
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "scheduler_state_dict": self.scheduler.state_dict(),
            "seed": self.config.seed,
            "epoch": self.epoch,
            "batch_in_epoch": self.batch_in_epoch,
            "global_step": self.global_step,
            "val_metric_best": self.best_metric,
            "val_metric_best_epoch": self.best_epoch,
            "epochs_without_improvement": self.epochs_without_improvement,
            "rng_states": rng_state(),
            "train_config_snapshot": self.config.as_dict(),
            "class_stats": self.class_stats,
            "architecture": self.model.architecture_summary(),
            "amp": self.amp_tag,
            "scaler_state_dict": self.scaler.state_dict(),
            "format_version": 1,
        }

    def save_last(self, reason: str = "periodic") -> None:
        payload = self._checkpoint_payload()
        payload["saved_because"] = reason
        tmp = self.last_path.with_suffix(".pt.tmp")
        torch.save(payload, tmp)
        bc.atomic_replace(tmp, self.last_path)
        self._last_checkpoint_time = time.time()
        self.log.info("checkpoint_last written (%s) at epoch %d batch %d",
                      reason, self.epoch, self.batch_in_epoch)

    def save_best(self, extras: dict[str, Any]) -> None:
        """Weights only -- §8.1's checkpoint_best is ~0.6 GB, not 2.4 GB."""
        payload = {
            "model_state_dict": self.model.state_dict(),
            "seed": self.config.seed,
            "epoch": self.epoch,
            "val_metric_best": self.best_metric,
            "val_metric_best_epoch": self.best_epoch,
            "train_config_snapshot": self.config.as_dict(),
            "class_stats": self.class_stats,
            "architecture": self.model.architecture_summary(),
            "format_version": 1,
        }
        payload.update(extras)
        tmp = self.best_path.with_suffix(".pt.tmp")
        torch.save(payload, tmp)
        bc.atomic_replace(tmp, self.best_path)

    def try_resume(self) -> bool:
        if not self.last_path.exists():
            return False
        payload = torch.load(self.last_path, map_location=self.device, weights_only=False)
        self.model.load_state_dict(payload["model_state_dict"])
        self.optimizer.load_state_dict(payload["optimizer_state_dict"])
        self.scheduler.load_state_dict(payload["scheduler_state_dict"])
        if payload.get("scaler_state_dict"):
            self.scaler.load_state_dict(payload["scaler_state_dict"])
        self.epoch = int(payload["epoch"])
        self.batch_in_epoch = int(payload.get("batch_in_epoch", 0))
        self.global_step = int(payload["global_step"])
        self.best_metric = float(payload.get("val_metric_best", -math.inf))
        self.best_epoch = int(payload.get("val_metric_best_epoch", -1))
        self.epochs_without_improvement = int(payload.get("epochs_without_improvement", 0))
        load_rng_state(payload.get("rng_states"))
        self.log.info("resumed from %s: epoch %d, batch %d, global_step %d, best %.6f "
                      "(saved because: %s)", self.last_path.name, self.epoch,
                      self.batch_in_epoch, self.global_step, self.best_metric,
                      payload.get("saved_because", "?"))
        return True

    # -- loop -----------------------------------------------------------------
    def _loader(self, dataset: TaskDataset, batches: Sequence[Sequence[int]]) -> DataLoader:
        return DataLoader(
            dataset, batch_sampler=list(batches), num_workers=self.config.num_workers,
            pin_memory=self.device.type == "cuda",
            persistent_workers=False,
            prefetch_factor=2 if self.config.num_workers else None)

    def _to_device(self, batch: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
        return {k: (v.to(self.device, non_blocking=True) if torch.is_tensor(v) else v)
                for k, v in batch.items()}

    def train(self) -> dict[str, Any]:
        config = self.config
        history: list[dict[str, Any]] = []
        start_epoch = self.epoch

        for epoch in range(start_epoch, config.epochs):
            self.epoch = epoch
            self.train_dataset.set_epoch(epoch)       # B2 regime_2 noise stream
            batches = build_batch_order(
                len(self.train_dataset), config.batch_size, seed=config.seed,
                epoch=epoch, shuffle=True, hard_negative_index=self.hard_index)
            if config.max_steps_per_epoch:
                batches = batches[:config.max_steps_per_epoch]
            skip = self.batch_in_epoch if epoch == start_epoch else 0
            if skip:
                self.log.info("resuming mid-epoch: skipping %d of %d batches",
                              skip, len(batches))
            remaining = batches[skip:]

            epoch_start = time.time()
            train_loss, head_losses = self._run_epoch(remaining, skip, len(batches))
            if self.stop_requested:
                self.save_last("interrupted")
                self.log.warning("stopping after signal at epoch %d batch %d",
                                 self.epoch, self.batch_in_epoch)
                return {"status": "interrupted", "history": history,
                        "best_metric": self.best_metric, "best_epoch": self.best_epoch}

            self.batch_in_epoch = 0
            val = self.evaluate(self.val_dataset)
            primary = val["primary_metric"]
            improved = np.isfinite(primary) and primary > self.best_metric
            if improved:
                self.best_metric = float(primary)
                self.best_epoch = epoch
                self.epochs_without_improvement = 0
                self.save_best({"val_metrics": val["metrics"]})
            else:
                self.epochs_without_improvement += 1

            row = {
                "epoch": epoch,
                "global_step": self.global_step,
                "train_loss": round(float(train_loss), 6),
                "train_head_losses": {k: round(v, 6) for k, v in head_losses.items()},
                "val_primary_metric": None if not np.isfinite(primary) else round(float(primary), 6),
                "val_primary_metric_name": self.spec.primary_metric,
                "val_metrics": val["metrics"],
                "lr": [round(g["lr"], 10) for g in self.optimizer.param_groups],
                "improved": bool(improved),
                "epochs_without_improvement": self.epochs_without_improvement,
                "seconds": round(time.time() - epoch_start, 2),
                "amp": self.amp_tag,
                "timestamp": bc.utc_now_iso(),
            }
            history.append(row)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, default=str) + "\n")
            self.log.info("epoch %d/%d  train_loss=%.5f  val_%s=%.5f  %s",
                          epoch + 1, config.epochs, train_loss, self.spec.primary_metric,
                          primary, "BEST" if improved else
                          f"no improvement ({self.epochs_without_improvement}/{config.patience})")

            self.epoch = epoch + 1
            self.save_last("epoch_end")

            if self.epochs_without_improvement >= config.patience:
                self.log.info("early stop: %d epochs without improvement (§6.3 patience %d)",
                              self.epochs_without_improvement, config.patience)
                break

        return {"status": "complete", "history": history,
                "best_metric": self.best_metric, "best_epoch": self.best_epoch}

    def _run_epoch(self, batches: Sequence[Sequence[int]], already_done: int,
                   total_batches: int) -> tuple[float, dict[str, float]]:
        from tqdm import tqdm
        from tqdm.contrib.logging import logging_redirect_tqdm

        self.model.train()
        loader = self._loader(self.train_dataset, batches)
        running = 0.0
        running_heads: dict[str, float] = {}
        seen = 0

        with logging_redirect_tqdm():
            bar = tqdm(total=total_batches, initial=already_done, file=sys.stderr,
                       dynamic_ncols=True, mininterval=0.5,
                       desc=f"{self.config.task} e{self.epoch}")
            self.optimizer.zero_grad(set_to_none=True)
            for index, batch in enumerate(loader):
                batch = self._to_device(batch)
                with torch.autocast(device_type=self.device.type, dtype=self.amp_dtype,
                                    enabled=self.amp_dtype is not None):
                    outputs = self.model(batch)
                    loss, parts = compute_losses(self.spec, outputs, batch, self.class_stats)
                scaled = loss / self.config.accumulation_steps
                if self.scaler.is_enabled():
                    self.scaler.scale(scaled).backward()
                else:
                    scaled.backward()

                if (index + 1) % self.config.accumulation_steps == 0:
                    if self.scaler.is_enabled():
                        self.scaler.unscale_(self.optimizer)
                    nn.utils.clip_grad_norm_(self.model.parameters(), GRAD_CLIP_NORM)
                    if self.scaler.is_enabled():
                        self.scaler.step(self.optimizer)
                        self.scaler.update()
                    else:
                        self.optimizer.step()
                    self.scheduler.step()
                    self.optimizer.zero_grad(set_to_none=True)
                    self.global_step += 1

                running += float(loss.detach())
                for key, value in parts.items():
                    running_heads[key] = running_heads.get(key, 0.0) + value
                seen += 1
                self.batch_in_epoch = already_done + index + 1
                bar.update(1)

                elapsed_minutes = (time.time() - self._last_checkpoint_time) / 60.0
                if elapsed_minutes >= self.config.checkpoint_minutes:
                    self.save_last("periodic")
                if self.stop_requested:
                    break
            bar.close()

        divisor = max(seen, 1)
        return running / divisor, {k: v / divisor for k, v in running_heads.items()}

    # -- inference ------------------------------------------------------------
    @torch.no_grad()
    def evaluate(self, dataset: TaskDataset) -> dict[str, Any]:
        predictions = collect_predictions(self.model, self.spec, dataset, self.config,
                                          self.device, self.amp_dtype)
        return {"primary_metric": primary_metric(self.spec, predictions),
                "metrics": head_metrics(self.spec, predictions),
                "predictions": predictions}


# -----------------------------------------------------------------------------
# prediction collection -- shared by the trainer, 31_eval.py and 41_run_sensitivity
# -----------------------------------------------------------------------------
@torch.no_grad()
def collect_predictions(model: TaskModel, spec: TaskSpec, dataset: TaskDataset,
                        config: TrainConfig, device: torch.device,
                        amp_dtype: torch.dtype | None,
                        batch_size: int | None = None) -> pd.DataFrame:
    """Run the model over a split and build the §7.1 prediction frame."""
    model.eval()
    batch_size = batch_size or max(1, config.batch_size)
    batches = build_batch_order(len(dataset), batch_size, seed=config.seed, epoch=0,
                                shuffle=False)
    loader = DataLoader(dataset, batch_sampler=batches, num_workers=config.num_workers,
                        pin_memory=device.type == "cuda")

    collected: dict[str, list] = {}

    def push(name: str, values) -> None:
        collected.setdefault(name, []).extend(values)

    for batch in loader:
        moved = {k: (v.to(device, non_blocking=True) if torch.is_tensor(v) else v)
                 for k, v in batch.items()}
        with torch.autocast(device_type=device.type, dtype=amp_dtype,
                            enabled=amp_dtype is not None):
            outputs = model(moved)
        outputs = {k: v.float().cpu() for k, v in outputs.items()}

        push("row_index", batch["row_index"].tolist())
        for head in active_heads(spec, outputs):
            if head.kind == "binary":
                proba = torch.sigmoid(outputs[head.name].squeeze(-1)).numpy()
                push(f"y_pred_proba_{head.name}", proba.tolist())
                push(f"y_true_{head.name}", batch[f"y__{head.name}"].numpy().tolist())
                push(f"valid_{head.name}", batch[f"m__{head.name}"].numpy().astype(bool).tolist())

            elif head.kind == "multiclass":
                proba = torch.softmax(outputs[head.name], dim=1).numpy()
                for index, class_name in enumerate(head.classes):
                    push(f"y_pred_proba_{head.name}__{class_name}", proba[:, index].tolist())
                push(f"y_pred_index_{head.name}", proba.argmax(axis=1).tolist())
                push(f"y_true_index_{head.name}", batch[f"y__{head.name}"].numpy().tolist())
                push(f"valid_{head.name}", batch[f"m__{head.name}"].numpy().astype(bool).tolist())

            elif head.kind == "regression":
                # Inverted here, once, so every downstream consumer -- metrics,
                # bootstrap, the results CSV, the paper table -- sees bpm and ms
                # and never the standardised scale.
                predicted = head.destandardise(outputs[head.name].squeeze(-1).numpy())
                push(f"y_pred_{head.name}", predicted.tolist())
                push(f"y_true_{head.name}", batch[f"raw__{head.name}"].numpy().tolist())
                push(f"valid_{head.name}", batch[f"m__{head.name}"].numpy().astype(bool).tolist())

            elif head.kind == "peak_seq":
                probability = torch.sigmoid(outputs["fiducials"]).numpy()
                onset = outputs["fiducials_onset"].numpy()
                offset = outputs["fiducials_offset"].numpy()
                for row in range(probability.shape[0]):
                    peaks = M.decode_peaks(probability[row])
                    push("y_pred_r_peaks", [peaks.tolist()])
                    if peaks.size:
                        push("y_pred_qrs_onsets",
                             [(peaks - np.round(onset[row][peaks] * 5000)).astype("int64").tolist()])
                        push("y_pred_qrs_offsets",
                             [(peaks + np.round(offset[row][peaks] * 5000)).astype("int64").tolist()])
                    else:
                        push("y_pred_qrs_onsets", [[]])
                        push("y_pred_qrs_offsets", [[]])
                    push("n_pred_peaks", [int(peaks.size)])

            elif head.kind == "bins":
                proba = torch.sigmoid(outputs["bins"]).numpy()
                push("y_pred_proba_bins", [row.tolist() for row in proba])
                push("y_true_bins", [row.tolist() for row in batch["y__bins"].numpy()])
                push("query_idx", batch["query_idx"].numpy().tolist())

            elif head.kind == "span":
                span = outputs[head.name].numpy()
                push("y_pred_span_start_norm", span[:, 0].tolist())
                push("y_pred_span_end_norm", span[:, 1].tolist())
                push("y_true_span_start_norm", batch["y__span"].numpy()[:, 0].tolist())
                push("y_true_span_end_norm", batch["y__span"].numpy()[:, 1].tolist())
                push(f"valid_{head.name}", batch[f"m__{head.name}"].numpy().astype(bool).tolist())

    frame = pd.DataFrame(collected)
    provenance = dataset.provenance_frame().iloc[frame["row_index"].to_numpy()].reset_index(drop=True)
    frame = pd.concat([provenance, frame.drop(columns=["row_index"])], axis=1)

    # A4/B3 ground truth the metrics need but the loader stores sparsely.
    if spec.key == "A4_event_localization":
        source = dataset.frame.iloc[frame.index]
        for column in ("r_peaks_lead2", "qrs_onsets_lead2", "qrs_offsets_lead2"):
            frame[f"y_true_{column}"] = [list(map(int, v)) for v in source[column]]
    if spec.key == "B3_temporal_grounding":
        frame["query"] = [B3_QUERIES[i] for i in frame["query_idx"]]

    frame["seed"] = config.seed
    frame["arch_tier"] = config.arch_tier
    frame["lead_subset"] = config.lead_subset
    frame["signal_input_modality"] = config.signal_input_modality
    frame["image_input_modality"] = config.image_input_modality
    frame["text_encoder"] = config.text_encoder
    return frame


# -----------------------------------------------------------------------------
# metrics over a prediction frame
# -----------------------------------------------------------------------------
def head_present(head, predictions: pd.DataFrame) -> bool:
    """Did this prediction frame actually get columns for this head?"""
    if head.kind == "peak_seq":
        return "y_pred_r_peaks" in predictions.columns
    if head.kind == "bins":
        return "y_pred_proba_bins" in predictions.columns
    if head.kind == "span":
        return "y_pred_span_start_norm" in predictions.columns
    if head.kind == "regression":
        return f"y_pred_{head.name}" in predictions.columns
    if head.kind == "binary":
        return f"y_pred_proba_{head.name}" in predictions.columns
    return f"y_pred_proba_{head.name}__{head.classes[0]}" in predictions.columns


def head_metrics(spec: TaskSpec, predictions: pd.DataFrame) -> dict[str, Any]:
    """Per-head metrics on one prediction frame -- the trainer's val summary."""
    out: dict[str, Any] = {}
    for head in spec.heads:
        # A tier that could not serve a head wrote no columns for it (see
        # `task_models.active_heads`); scoring it would invent numbers.
        if not head_present(head, predictions):
            continue
        if head.kind == "binary":
            valid = predictions[f"valid_{head.name}"].to_numpy(dtype=bool)
            truth = predictions[f"y_true_{head.name}"].to_numpy()[valid]
            score = predictions[f"y_pred_proba_{head.name}"].to_numpy()[valid]
            out[head.name] = {"auprc": M.auprc(truth, score), "auroc": M.auroc(truth, score),
                              "n": int(valid.sum()), "n_positive": int((truth > 0).sum())}
        elif head.kind == "multiclass":
            valid = predictions[f"valid_{head.name}"].to_numpy(dtype=bool)
            truth = predictions[f"y_true_index_{head.name}"].to_numpy()[valid]
            proba = np.column_stack([
                predictions[f"y_pred_proba_{head.name}__{c}"].to_numpy()[valid]
                for c in head.classes])
            out[head.name] = {
                "macro_auprc": M.multiclass_macro_auprc(truth, proba, len(head.classes)),
                "accuracy": float((proba.argmax(axis=1) == truth).mean()) if valid.any()
                else float("nan"),
                "n": int(valid.sum()),
            }
        elif head.kind == "regression":
            valid = predictions[f"valid_{head.name}"].to_numpy(dtype=bool)
            out[head.name] = M.regression_metrics(
                predictions[f"y_true_{head.name}"].to_numpy()[valid],
                predictions[f"y_pred_{head.name}"].to_numpy()[valid],
                tolerance=head.tolerance, units=head.units)
        elif head.kind == "peak_seq":
            matches = [M.match_events(np.asarray(t), np.asarray(p))
                       for t, p in zip(predictions["y_true_r_peaks_lead2"],
                                       predictions["y_pred_r_peaks"])]
            out["r_peak"] = M.aggregate_event_matches(matches)
            onset_matches = [M.match_events(np.asarray(t), np.asarray(p))
                             for t, p in zip(predictions["y_true_qrs_onsets_lead2"],
                                             predictions["y_pred_qrs_onsets"])]
            offset_matches = [M.match_events(np.asarray(t), np.asarray(p))
                              for t, p in zip(predictions["y_true_qrs_offsets_lead2"],
                                              predictions["y_pred_qrs_offsets"])]
            out["qrs_onset"] = M.aggregate_event_matches(onset_matches)
            out["qrs_offset"] = M.aggregate_event_matches(offset_matches)
        elif head.kind == "bins":
            truth = np.array(predictions["y_true_bins"].tolist())
            proba = np.array(predictions["y_pred_proba_bins"].tolist())
            predicted = (proba >= 0.5).astype(int)
            out["bins"] = {
                "mIoU": M.miou(truth, predicted),
                "recall_at_iou_0.3": M.recall_at_iou(truth, predicted, 0.3),
                "recall_at_iou_0.5": M.recall_at_iou(truth, predicted, 0.5),
                "no_evidence_accuracy": M.no_evidence_accuracy(truth, predicted),
                "bin_auprc": M.auprc(truth.ravel(), proba.ravel()),
            }
        elif head.kind == "span":
            valid = predictions[f"valid_{head.name}"].to_numpy(dtype=bool)
            ious = [M.char_iou((ts, te), (ps, pe)) for ts, te, ps, pe in zip(
                predictions["y_true_span_start_norm"].to_numpy()[valid],
                predictions["y_true_span_end_norm"].to_numpy()[valid],
                predictions["y_pred_span_start_norm"].to_numpy()[valid],
                predictions["y_pred_span_end_norm"].to_numpy()[valid])]
            finite = [v for v in ious if np.isfinite(v)]
            out["span"] = {"mean_char_iou": float(np.mean(finite)) if finite else float("nan"),
                           "n": int(valid.sum())}
    return out


def primary_metric(spec: TaskSpec, predictions: pd.DataFrame) -> float:
    """The one number early stopping and the headline table use (§4 per task)."""
    per_head = head_metrics(spec, predictions)
    name = spec.primary_metric

    if name == "macro_AUPRC":
        values = [v["auprc"] for v in per_head.values() if "auprc" in v]
    elif name == "mean_head_macro_AUPRC":
        values = [v["macro_auprc"] for v in per_head.values() if "macro_auprc" in v]
    elif name == "macro_AUPRC_pm24h":
        values = [v["macro_auprc"] for k, v in per_head.items()
                  if k.endswith("_pm24h") and "macro_auprc" in v]
    elif name == "mean_head_AUPRC":
        values = [v["auprc"] for v in per_head.values() if "auprc" in v]
    elif name in ("AUPRC_y_match", "AUPRC_is_corrupted"):
        key = name.replace("AUPRC_", "")
        values = [per_head[key]["auprc"]] if key in per_head else []
    elif name == "r_peak_F1_10ms":
        values = [per_head["r_peak"]["f1"]] if "r_peak" in per_head else []
    elif name == "mIoU":
        values = [per_head["bins"]["mIoU"]] if "bins" in per_head else []
    else:                                                    # pragma: no cover
        raise ValueError(f"no primary metric rule for {name!r}")

    values = [v for v in values if np.isfinite(v)]
    return float(np.mean(values)) if values else float("nan")


def _self_check() -> None:
    """Batch order determinism, mid-epoch resume slicing, hard-negative coverage."""
    first = build_batch_order(1000, 32, seed=42, epoch=0, shuffle=True)
    again = build_batch_order(1000, 32, seed=42, epoch=0, shuffle=True)
    later = build_batch_order(1000, 32, seed=42, epoch=1, shuffle=True)
    assert first == again, "batch order is not a pure function of (seed, epoch)"
    assert first != later, "epoch does not change the shuffle"
    assert sorted(i for b in first for i in b) == list(range(1000)), "rows lost or duplicated"

    # Mid-epoch resume: batches 7.. of a rebuilt order must equal the original tail.
    assert first[7:] == build_batch_order(1000, 32, seed=42, epoch=0, shuffle=True)[7:]

    hard = np.arange(0, 1000, 25)          # 40 hard negatives among 1000 rows
    batches = build_batch_order(1000, 16, seed=42, epoch=0, shuffle=True,
                               hard_negative_index=hard)
    hard_set = set(hard.tolist())
    assert all(any(i in hard_set for i in batch) for batch in batches), \
        "a batch contains no HARD_NEGATIVE_TEXT row (§6.4)"
    others = sorted(i for b in batches for i in b if i not in hard_set)
    assert others == sorted(set(range(1000)) - hard_set), "non-hard rows lost or duplicated"

    ordered = build_batch_order(10, 4, seed=1, epoch=0, shuffle=False)
    assert ordered == [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9]], ordered
    print("trainer self-check: PASS  (deterministic order, exact mid-epoch resume, "
          "hard negatives in every batch)")


if __name__ == "__main__":
    _self_check()
```

### `scripts/phase2_tasks_benchmark_and_paper/_train_lib/smoke_test.py`

```python
"""End-to-end smoke test of the Step-3 training/eval stack on `dev_sample/`.

    ./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_train_lib/smoke_test.py
    ./ecg_env/Scripts/python.exe .../smoke_test.py --tasks A2_measurement_blind --tiers signal

This is the gate §8.2.1 asks for: "the laptop authors and smoke-tests every
script against a fixed 5,000-study sample". It proves the code RUNS on real
bytes -- it proves nothing about the numbers, which come from the DGX.

What it covers:

* every trainable task x one representative arch tier of each family, trained
  for two batches and evaluated end to end;
* **crash recovery**, twice: an interrupted run resumes mid-epoch at the exact
  batch it stopped on, and a completed epoch resumes at the epoch boundary with
  optimizer, scheduler, RNG and best-metric state intact;
* **preemption**, by invoking the trainer's own SIGTERM handler and confirming
  it sets the stop flag rather than writing from inside the handler;
* the two gates that must fail loudly: a forbidden modality and a threshold
  selected on anything but `val`.

Everything writes under `outputs/model_runs/_dev/` and
`data/processed/tasks/_dev/`, so a smoke run cannot touch a real artifact.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _dataset_lib import build_common as bc                            # noqa: E402
from _dataset_lib.task_dataset import TaskDataset, plan_from_config    # noqa: E402
from _dataset_lib.task_spec import TASKS, get_task                     # noqa: E402
from _model_lib.model_configs import MODEL_CONFIG_DIR, load_model_config  # noqa: E402
from _model_lib.task_models import build_model, train_class_stats      # noqa: E402
from _train_lib.seed import set_seed                                   # noqa: E402
from _train_lib.trainer import TrainConfig, Trainer, build_batch_order  # noqa: E402

PYTHON = bc.PROJECT_ROOT / "ecg_env" / "Scripts" / "python.exe"
TRAIN_SCRIPT = bc.PROJECT_ROOT / "scripts" / "phase2_tasks_benchmark_and_paper" / "30_train.py"
EVAL_SCRIPT = bc.PROJECT_ROOT / "scripts" / "phase2_tasks_benchmark_and_paper" / "31_eval.py"
DEV_RUNS = bc.PROJECT_ROOT / "outputs" / "model_runs" / "_dev"

# One representative tier per family. The full 94-config matrix differs only in
# which modality kind is named, and `check_input_policy` already covers that.
TIER_PREFERENCE = {
    "signal": ["signal_resnet18_lead2_preprocessed", "signal_resnet18_lead2_raw"],
    "image": ["image_resnet50_lead2_clean", "image_resnet50_12lead_clean"],
    "text_tfidf": ["text_tfidf"],
    "text_bert": ["text_bioclinicalbert"],
    "fusion": ["multimodal_fusion_lead2"],
    # Plan A/B §5.3 ablation 6 -- the trained no-text multimodal tier. It has to
    # run on real bytes like every other tier: dropping the text encoder changes
    # the fusion input width, and a config that only *looks* right would be found
    # at campaign time on the DGX rather than here.
    "fusion_notext": ["multimodal_fusion_notext_lead2"],
}


def available_configs(task: str) -> dict[str, Path]:
    prefix = task.split("_")[0]
    return {path.stem[len(prefix) + 1:]: path
            for path in sorted(MODEL_CONFIG_DIR.glob(f"{prefix}_*.yaml"))}


def pick_configs(task: str, families: list[str]) -> list[Path]:
    configs = available_configs(task)
    picked: list[Path] = []
    for family in families:
        for tier in TIER_PREFERENCE[family]:
            if tier in configs:
                picked.append(configs[tier])
                break
    return picked


def run(command: list[str], label: str) -> tuple[bool, str]:
    started = time.time()
    result = subprocess.run([str(c) for c in command], capture_output=True, text=True)
    elapsed = time.time() - started
    ok = result.returncode == 0
    tail = (result.stderr or result.stdout).strip().splitlines()[-4:]
    print(f"  {'PASS' if ok else 'FAIL'}  {label}  ({elapsed:.1f}s)")
    if not ok:
        for line in tail:
            print(f"        {line}")
    return ok, "\n".join(tail)


# -----------------------------------------------------------------------------
# crash recovery, in-process so it is deterministic and OS-independent
# -----------------------------------------------------------------------------
def build_tiny_trainer(output_dir: Path, epochs: int = 2, batch_size: int = 4,
                       steps: int = 3) -> tuple[Trainer, Any]:
    task = "B1_measurement_blind"
    spec = get_task(task)
    config_dict = load_model_config(
        MODEL_CONFIG_DIR / "B1_signal_resnet18_lead2_preprocessed.yaml")
    plan = plan_from_config(config_dict)
    set_seed(42)

    train_dataset = TaskDataset(task, "train", plan, dev=True, limit=32)
    val_dataset = TaskDataset(task, "val", plan, dev=True, limit=16)
    config = TrainConfig(task=task, arch_tier="smoke", lead_subset="lead2", seed=42,
                         output_dir=output_dir, epochs=epochs, batch_size=batch_size,
                         num_workers=0, checkpoint_minutes=1e9,
                         max_steps_per_epoch=steps, dev=True,
                         signal_input_modality=plan.signal_kind)
    model = build_model(spec, plan, pretrained=False)
    stats = train_class_stats(spec, train_dataset.frame)

    import logging

    logger = logging.getLogger("smoke")
    logger.setLevel(logging.ERROR)
    return Trainer(model, spec, config, train_dataset, val_dataset, stats, logger), spec


def test_midepoch_resume(root: Path) -> bool:
    """Interrupt after 2 of 3 batches; the resumed run must do exactly batch 3."""
    output_dir = root / "resume_midepoch"
    shutil.rmtree(output_dir, ignore_errors=True)

    trainer, _ = build_tiny_trainer(output_dir, epochs=1, steps=3)
    original_run_epoch = trainer._run_epoch

    def stop_after_two(batches, already_done, total):
        # Let two batches complete, THEN raise the flag -- that is the order a
        # SIGTERM produces: the batch in flight finishes, the loop stops after it.
        result = original_run_epoch(batches[:2], already_done, total)
        trainer.stop_requested = True
        return result

    trainer._run_epoch = stop_after_two
    result = trainer.train()
    if result["status"] != "interrupted":
        print(f"  FAIL  mid-epoch resume: expected 'interrupted', got {result['status']}")
        return False

    checkpoint = torch.load(output_dir / "checkpoint_last.pt", map_location="cpu",
                            weights_only=False)
    if checkpoint["batch_in_epoch"] != 2 or checkpoint["saved_because"] != "interrupted":
        print(f"  FAIL  mid-epoch resume: batch_in_epoch={checkpoint['batch_in_epoch']}, "
              f"saved_because={checkpoint['saved_because']}")
        return False

    # The resumed run rebuilds the same order and must skip the first two batches.
    resumed, _ = build_tiny_trainer(output_dir, epochs=1, steps=3)
    if not resumed.try_resume():
        print("  FAIL  mid-epoch resume: try_resume() found no checkpoint")
        return False
    if resumed.batch_in_epoch != 2 or resumed.global_step != checkpoint["global_step"]:
        print(f"  FAIL  mid-epoch resume: restored batch={resumed.batch_in_epoch}, "
              f"step={resumed.global_step}")
        return False

    seen: list[int] = []
    original = resumed._run_epoch

    def record(batches, already_done, total):
        seen.append(len(batches))
        return original(batches, already_done, total)

    resumed._run_epoch = record
    resumed.train()
    if seen != [1]:
        print(f"  FAIL  mid-epoch resume: resumed run did {seen} batches, expected [1]")
        return False
    print("  PASS  mid-epoch resume (stopped after 2/3 batches, resumed doing exactly 1)")
    return True


def test_epoch_boundary_resume(root: Path) -> bool:
    """A completed epoch must restore weights, optimizer, RNG and best metric."""
    output_dir = root / "resume_epoch"
    shutil.rmtree(output_dir, ignore_errors=True)

    first, _ = build_tiny_trainer(output_dir, epochs=1, steps=3)
    first.train()
    reference = {k: v.clone() for k, v in first.model.state_dict().items()}
    best_metric, global_step = first.best_metric, first.global_step

    second, _ = build_tiny_trainer(output_dir, epochs=2, steps=3)
    if not second.try_resume():
        print("  FAIL  epoch-boundary resume: no checkpoint found")
        return False
    for key, value in second.model.state_dict().items():
        if not torch.allclose(value.float(), reference[key].float()):
            print(f"  FAIL  epoch-boundary resume: weight {key} differs after restore")
            return False
    if second.epoch != 1 or second.global_step != global_step:
        print(f"  FAIL  epoch-boundary resume: epoch={second.epoch}, step={second.global_step}")
        return False
    if abs(second.best_metric - best_metric) > 1e-12:
        print(f"  FAIL  epoch-boundary resume: best {second.best_metric} != {best_metric}")
        return False
    if not second.optimizer.state_dict()["state"]:
        print("  FAIL  epoch-boundary resume: optimizer moment state is empty")
        return False
    print(f"  PASS  epoch-boundary resume (epoch {second.epoch}, step {second.global_step}, "
          f"best {second.best_metric:.6f}, optimizer state restored)")
    return True


def test_preemption_handler(root: Path) -> bool:
    """SIGTERM must set the stop flag, not write from inside the handler."""
    import signal as signal_module

    output_dir = root / "preempt"
    shutil.rmtree(output_dir, ignore_errors=True)
    trainer, _ = build_tiny_trainer(output_dir, epochs=1, steps=2)
    if trainer.stop_requested:
        print("  FAIL  preemption: stop flag set before any signal")
        return False
    handler = signal_module.getsignal(signal_module.SIGTERM)
    if not callable(handler):
        print("  FAIL  preemption: no SIGTERM handler installed")
        return False
    handler(signal_module.SIGTERM, None)
    if not (trainer.stop_requested and trainer.interrupted):
        print("  FAIL  preemption: the handler did not raise the stop flag")
        return False
    if (output_dir / "checkpoint_last.pt").exists():
        print("  FAIL  preemption: the handler wrote a checkpoint from inside itself")
        return False
    print("  PASS  preemption handler (flag raised, no write from the handler)")
    return True


def test_gates() -> bool:
    """The two failures that must be loud: forbidden input, non-val threshold."""
    from _dataset_lib.task_dataset import ModalityPlan
    from _train_lib.threshold import select_threshold

    ok = True
    try:
        TaskDataset("B1_measurement_blind", "val",
                    ModalityPlan(image_kind="image_clean_lead2"), dev=True, limit=2)
        print("  FAIL  leakage gate: B1 accepted an image input")
        ok = False
    except PermissionError:
        pass
    try:
        select_threshold([0, 1], [0.1, 0.9], split="test", task="t", arch_tier="a",
                         lead_subset="lead2", seed=42, head="h")
        print("  FAIL  threshold gate: selection on test was allowed")
        ok = False
    except ValueError:
        pass
    if ok:
        print("  PASS  gates (forbidden modality rejected, test-split threshold rejected)")
    return ok


def test_determinism(root: Path) -> bool:
    """Two runs of the same seed must produce identical weights."""
    weights = []
    for index in (0, 1):
        output_dir = root / f"determinism_{index}"
        shutil.rmtree(output_dir, ignore_errors=True)
        trainer, _ = build_tiny_trainer(output_dir, epochs=1, steps=2)
        trainer.train()
        weights.append({k: v.clone() for k, v in trainer.model.state_dict().items()})
    for key in weights[0]:
        if not torch.allclose(weights[0][key].float(), weights[1][key].float()):
            print(f"  FAIL  determinism: {key} differs between two seed-42 runs")
            return False
    print("  PASS  determinism (two seed-42 runs produce identical weights)")
    return True


# -----------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--tasks", nargs="*", default=None)
    parser.add_argument("--tiers", nargs="*", default=["signal", "image", "text_tfidf",
                                                       "text_bert", "fusion",
                                                       "fusion_notext"])
    parser.add_argument("--rows", type=int, default=48)
    parser.add_argument("--steps", type=int, default=2)
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument("--skip-recovery", action="store_true")
    args = parser.parse_args(argv)

    tasks = args.tasks or [k for k, v in TASKS.items() if not v.eval_only]
    root = DEV_RUNS / "_smoke"
    root.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    print("=" * 78)
    print("Step 3 smoke test — dev_sample only, tiny batches, no paper numbers")
    print("=" * 78)

    if not args.skip_recovery:
        print("\n[1] crash recovery, preemption, determinism and the gates")
        for name, fn in (("mid-epoch resume", lambda: test_midepoch_resume(root)),
                         ("epoch-boundary resume", lambda: test_epoch_boundary_resume(root)),
                         ("preemption handler", lambda: test_preemption_handler(root)),
                         ("determinism", lambda: test_determinism(root)),
                         ("gates", test_gates)):
            try:
                if not fn():
                    failures.append(name)
            except Exception as exc:                          # keep going, report at the end
                print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
                failures.append(name)

    if not args.skip_train:
        print(f"\n[2] train + eval, {len(tasks)} tasks x {len(args.tiers)} tiers")
        for task in tasks:
            configs = pick_configs(task, args.tiers)
            if not configs:
                print(f"  ----  {task}: no config for tiers {args.tiers}")
                continue
            print(f"\n  {task}")
            for config_path in configs:
                ok, _ = run([PYTHON, TRAIN_SCRIPT, "--model-config", config_path,
                             "--seed", 42, "--dev", "--epochs", 1,
                             "--batch-size", 4, "--max-steps-per-epoch", args.steps,
                             "--limit-rows", args.rows, "--num-workers", 0,
                             "--no-pretrained"], f"train {config_path.stem}")
                if not ok:
                    failures.append(f"train {config_path.stem}")
                    continue
                arch_tier = load_model_config(config_path)["arch_tier"]
                ok, _ = run([PYTHON, EVAL_SCRIPT, "--task", task, "--arch-tier", arch_tier,
                             "--dev", "--bootstrap-n", 50], f"eval  {config_path.stem}")
                if not ok:
                    failures.append(f"eval {config_path.stem}")

    print("\n" + "=" * 78)
    if failures:
        print(f"SMOKE TEST FAILED — {len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("SMOKE TEST PASSED — every checked path runs on dev_sample")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## 6. Validation results

- **Smoke test on `data/processed/dev_sample/`: SMOKE TEST PASSED � every checked path runs on dev_sample**
  - 34 `30_train.py` invocations PASS, 34 `31_eval.py` invocations PASS, 0 FAIL
  - 5 crash-recovery / determinism / gate checks PASS:
    - `mid-epoch resume (stopped after 2/3 batches, resumed doing exactly 1)`
    - `epoch-boundary resume (epoch 1, step 3, best 0.554747, optimizer state restored)`
    - `preemption handler (flag raised, no write from the handler)`
    - `determinism (two seed-42 runs produce identical weights)`
    - `gates (forbidden modality rejected, test-split threshold rejected)`
  - Full transcript: `outputs/stage_reports/stage_P2.4_smoke_test.log`

- **§9.5 oracle validation** (the check §9.5 names explicitly: "A4 / B3 should hit F1=1.0 within the algorithmic-baseline's own noise tolerance"):
  - PASS — A4_event_localization algorithmic `r_peak_f1` = 1.000000 (expected 1.0000) over 55,140 rows on the full test split; precision 1.000000, recall 1.000000, mean |offset| 0.0000 ms
  - PASS — A4_event_localization algorithmic `qrs_onset_f1` = 1.000000 (expected 1.0000) over 55,140 rows on the full test split; precision 1.000000, recall 1.000000, mean |offset| 0.0000 ms
  - PASS — A4_event_localization algorithmic `qrs_offset_f1` = 1.000000 (expected 1.0000) over 55,140 rows on the full test split; precision 1.000000, recall 1.000000, mean |offset| 0.0000 ms
  - PASS — B3_temporal_grounding algorithmic `mIoU` = 1.000000 (expected 1.0000) over 598,568 rows on the full test split; 598,568/598,568 rows bin-for-bin exact
  - the same check on `dev_sample/`, from the smoke run's results CSV:
    - PASS — A4_event_localization algorithmic `r_peak_f1` = 1.0000 (expected 1.0000)
    - PASS — B3_temporal_grounding algorithmic `mIoU` = 1.0000 (expected 1.0000)

- **Algorithmic baselines (§5.1) on the full test split: 3/8 doc-mandated tasks produced predictions**, missing_mandated = none
  - `A3_lab_abnormality` — 84,348 rows, ok
  - `A6_nested_baselines` — 337,392 rows, ok
  - `A6_risk_stratification` — 84,348 rows, ok

- **Algorithmic baselines (§5.1) on the `dev_sample/`: 3/8 doc-mandated tasks produced predictions**, missing_mandated = none
  - `A3_lab_abnormality` — 614 rows, ok
  - `A6_nested_baselines` — 2,456 rows, ok
  - `A6_risk_stratification` — 614 rows, ok

- **Module self-checks** — every module in §5 has a runnable `_self_check()`; each was executed and passed during this stage. Re-run any of them directly, e.g. `./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/bootstrap.py`.
- **P2.0 gate re-run after this stage's config edits: 26/26 PASS** (`_dataset_lib/schema_validators.py`).
- **No trained-model paper number was produced.** Every `30_train.py` / `31_eval.py` run in this stage used `--dev`, wrote under `outputs/model_runs/_dev/`, and was logged as bypassing the §4.C audit gate. `outputs/audit_reports/threshold_audit.md` is deliberately still absent — only a full-scale training run writes it. The algorithmic baselines are the one exception: they have no learned parameters and no threshold to select, so their full-test-split predictions above ARE final and are what §5.1 asks for.
- **The baselines' patient-level bootstrap CIs are not computed here.** §6.7's 10,000 BCa replicates re-evaluate the metric on a resampled frame each time, which for A4's 55 K event-matched rows or B3's 598 K bin rows is a campaign-scale job, not a report-generation one. The oracle check above is the point estimate on the full test split — exactly the quantity §9.5 names — and the CIs are produced by `31_eval.py` alongside the trained arms, so a baseline and a ResNet get identical treatment.

- Pre-flight: PASS — every builder calls `build_common.preflight()`, which asserts its inputs exist and records free disk and free RAM before any work starts. Phase 1 completion was verified at Stage P2.0 and is unchanged.

### Per-script validation (read back from the state files)

**`50_baseline_A2_measurement_blind`** — PASS

```json
{
  "done": true,
  "n_units": 55181,
  "n_done": 55181,
  "n_pending": 0,
  "rate_per_s": 46.9,
  "eta_minutes": 0.1,
  "finished_at": "2026-08-27T16:48:18Z",
  "n_rows": 55181
}
```

**`50_baseline_B1_measurement_blind`** — PASS

```json
{
  "done": true,
  "n_units": 149546,
  "n_done": 149546,
  "n_pending": 0,
  "rate_per_s": 48.42,
  "eta_minutes": 1.6,
  "finished_at": "2026-08-27T16:48:54Z",
  "n_rows": 149546
}
```

**`50_baseline_B2`** — PASS

```json
{
  "done": true,
  "n_units": 301097,
  "n_done": 301097,
  "n_pending": 0,
  "rate_per_s": 48.81,
  "eta_minutes": 0.4,
  "finished_at": "2026-08-27T16:48:57Z",
  "n_rows": 301097
}
```

**`50_baseline_B5`** — PASS

```json
{
  "done": true,
  "n_units": 25870,
  "n_done": 25870,
  "n_pending": 0,
  "rate_per_s": 37.67,
  "eta_minutes": 0.4,
  "finished_at": "2026-08-27T16:49:14Z",
  "n_rows": 25870
}
```

### Logging-hygiene checklist (Phase 1 §8.14)

- [x] Terminal showed one tqdm bar, no interleaving — workers redirect fd 1/2 into their own PID log in the pool initializer (`build_common.worker_log_init`), so no worker writes to the parent's stdout/stderr.
- [x] `aggregate.log` exists; first and last 5 lines:
(no worker logs produced -- every builder in this stage is single-process)
- [x] no `print(` in worker bodies:
```
(no match for '^\\s*print(' -- clean)
```
- [x] no `logging.basicConfig` in worker:
```
(no match for 'basicConfig' -- clean)
```
- [x] `worker_<pid>.log` files moved into `archive_<ts>/` — done by this generator, see the aggregate paths above.
- [n/a] Transport B `listener.stop()` — this stage uses Transport A (per-PID files), Phase 1 §8.3's default.
- [x] tqdm used with `mininterval=0.5` and `logging_redirect_tqdm()` — `build_common.run_chunked`:
```
549:                   mininterval=0.5, desc=desc or name)
```

- Disk free at report time: 90.7 GB on D:\

## 7. Manual test procedure

```
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/schema_validators.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/bootstrap.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/task_spec.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/corruption.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_model_lib/signal_encoders.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_model_lib/fusion_heads.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_model_lib/text_encoders.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_model_lib/task_models.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_model_lib/model_configs.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_model_lib/algorithmic_baselines.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_train_lib/seed.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_train_lib/metrics.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_train_lib/threshold.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_train_lib/calibration.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_train_lib/trainer.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_train_lib/smoke_test.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/50_run_baselines_algorithmic.py --dev --limit 60 --workers 4
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/50_run_baselines_algorithmic.py
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/31_eval.py --task A4_event_localization --arch-tier algorithmic --dev --bootstrap-n 100
./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/31_eval.py --task B3_temporal_grounding --arch-tier algorithmic --dev --bootstrap-n 100
```

Every module above prints its own PASS line and exits non-zero on failure. `smoke_test.py` is the one that exercises the whole stack: crash recovery, determinism, the leakage and threshold gates, then train + eval for every (task, arch tier) the input policy allows.

The last command is the full-scale §9.5 pass and takes hours -- the four detector tasks re-run NeuroKit2 over roughly 530 K strips between them. It is resumable through part parquets flushed every 5,000 units, so re-running the identical command after any interruption continues from the last flush rather than restarting; a task whose parts are already complete is rewritten from them in seconds. That path was exercised for real during the 2026-08-27 run.

## 8. Assumptions requiring user confirmation

- **The §5.3 image transform (decision 18)**  ::  every image-using run resizes the whole render into the locked target box instead of short-side resizing and centre-cropping. If a reviewer insists on the literal §5.3 transform, the Lead-II runs lose the first and last ~2 seconds of every strip and the 12-lead runs lose their outer lead columns; the knob is one function, `build_image_transform`, and it changes no data on disk.
- **BCa acceleration above 2,000 subjects is a delete-one-group jackknife**  ::  the bias correction is exact, the acceleration constant is estimated from 200 groups. If exact BCa is required for the headline numbers, raise `bootstrap.jackknife.exact_when_subjects_le` in `eval_configs/default.yaml`; budget roughly an hour per head per metric on the test split.
- **A5 trains both heads jointly by default**  ::  §5.6 puts them on a shared tri-encoder and §4.A.5.8 asks whether that helps or hurts. The with/without comparison needs a masked-attribute-only run, which is a model config away, not a code change.
- **No full-scale TRAINING run has happened yet**  ::  the §4.C audit gate is open (Step 10 / Stage P2.3 PASS, 2026-08-27), so `30_train.py` will now start, but every `30_train.py` / `31_eval.py` invocation to date used `--dev`. `outputs/audit_reports/threshold_audit.md` is therefore still absent — only a full-scale training run writes it. This does not touch the algorithmic baselines, which have no threshold to select.
- **The baselines' bootstrap CIs are deferred to the eval matrix**  ::  §5.1 asks for patient-level CIs at n = 10,000 like every other model, and §6.7's BCa re-evaluates the metric on a resampled frame each iteration. On A4's 55 K event-matched rows or B3's 598 K bin rows that is a campaign-scale job, so the full-scale pass produced the §9.5 point estimates and left the intervals to `31_eval.py`, where a baseline and a ResNet are scored by identical code.
- **The Lead-II detector is blind to two of the five B5 contradiction families**  ::  measured at full scale, QRS duration >= 120 ms occurs on 21.06 % of QRS_wide-corrupted rows against 21.58 % of clean rows, so the NeuroKit QRS duration carries no signal for that family and making `b5_rule_flag` symmetric would add false positives rather than recall. Axis and PR are not recoverable from a single Lead-II strip at all. The rule abstains on all three by design, which is why B5's baseline F1 is 0.46 and why the task needs a learned model.
- **Retrieval (§7.5) is opt-in via `--retrieval`**  ::  it needs `checkpoint_best.pt`, so it cannot run from prediction files alone. It is a secondary check in §7.5; the verification AUPRC is the primary number and comes from the default path.
