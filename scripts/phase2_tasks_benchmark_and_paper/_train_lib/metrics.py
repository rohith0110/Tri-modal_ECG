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
    print("metrics self-check: PASS")


if __name__ == "__main__":
    _self_check()
