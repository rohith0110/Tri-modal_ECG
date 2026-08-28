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
