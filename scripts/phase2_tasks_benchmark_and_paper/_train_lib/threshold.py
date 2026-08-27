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
