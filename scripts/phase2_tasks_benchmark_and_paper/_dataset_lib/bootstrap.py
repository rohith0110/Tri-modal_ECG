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
