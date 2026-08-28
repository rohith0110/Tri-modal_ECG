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
