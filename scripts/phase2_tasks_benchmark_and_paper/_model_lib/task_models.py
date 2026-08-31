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
            # No default branch: an unrecognised name must fail loudly. Choosing
            # BERT for "anything that is not tfidf" is what let every tf-idf run
            # train BioClinicalBERT for a day and a half without a single sign.
            if plan.text_encoder == "tfidf":
                self.text_encoder = TfidfPassthrough()
            elif plan.text_encoder == "bioclinicalbert":
                self.text_encoder = BioClinicalBertEncoder(pretrained=pretrained)
            else:
                raise ValueError(
                    f"unknown text encoder {plan.text_encoder!r}; expected "
                    "'tfidf' or 'bioclinicalbert'. plan_from_config canonicalises "
                    "these -- if you got here, it was bypassed."
                )
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
