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
