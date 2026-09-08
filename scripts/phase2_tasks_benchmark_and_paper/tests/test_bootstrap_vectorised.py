"""The vectorised bootstrap gather must be IDENTICAL to the original loop.

`patient_bootstrap` produces every confidence interval in the paper. The
2026-09-08 rewrite replaced a per-replicate Python comprehension with a
vectorised gather for speed; speed is worthless if it moves a number, so this
asserts equality element for element, on the same RNG stream, rather than
"close enough".

    python tests/test_bootstrap_vectorised.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _dataset_lib.bootstrap import _subject_index, patient_bootstrap   # noqa: E402


def original_replicates(frame: pd.DataFrame, metric_fn, n_iter: int, seed: int) -> np.ndarray:
    """The implementation as it stood before the vectorisation."""
    _subjects, groups = _subject_index(frame["subject_id"].to_numpy())
    n_subjects = len(groups)
    rng = np.random.default_rng(seed)
    out = np.empty(n_iter, dtype="float64")
    for i in range(n_iter):
        picked = rng.integers(0, n_subjects, size=n_subjects)
        rows = np.concatenate([groups[j] for j in picked])
        out[i] = metric_fn(frame.iloc[rows])
    return out


def vectorised_replicates(frame: pd.DataFrame, metric_fn, n_iter: int, seed: int) -> np.ndarray:
    """The gather as it now stands, lifted out of patient_bootstrap."""
    _subjects, groups = _subject_index(frame["subject_id"].to_numpy())
    n_subjects = len(groups)
    counts = np.fromiter((len(g) for g in groups), dtype=np.int64, count=n_subjects)
    flat = np.concatenate(groups)
    starts = np.concatenate(([0], np.cumsum(counts)[:-1]))
    rng = np.random.default_rng(seed)
    out = np.empty(n_iter, dtype="float64")
    for i in range(n_iter):
        picked = rng.integers(0, n_subjects, size=n_subjects)
        sel_counts = counts[picked]
        total = int(sel_counts.sum())
        block_start = np.repeat(np.cumsum(sel_counts) - sel_counts, sel_counts)
        within = np.arange(total, dtype=np.int64) - block_start
        rows = flat[np.repeat(starts[picked], sel_counts) + within]
        out[i] = metric_fn(frame.take(rows))
    return out


def make_frame(rng: np.random.Generator, n_subjects: int, max_rows: int) -> pd.DataFrame:
    """Uneven rows per subject, which is the case the gather has to get right."""
    subject_ids, values, labels = [], [], []
    for subject in range(n_subjects):
        for _ in range(int(rng.integers(1, max_rows + 1))):
            subject_ids.append(subject)
            values.append(float(rng.random()))
            labels.append(int(rng.integers(0, 2)))
    return pd.DataFrame({"subject_id": subject_ids, "score": values, "label": labels})


def main() -> int:
    failures = 0
    for case, (n_subjects, max_rows, n_iter, seed) in enumerate([
            (40, 1, 200, 2026),        # one row each -- the degenerate shape
            (60, 5, 200, 7),           # uneven blocks
            (25, 12, 150, 99),         # few subjects, many rows each
    ]):
        rng = np.random.default_rng(1000 + case)
        frame = make_frame(rng, n_subjects, max_rows)
        # a metric that depends on ROW ORDER as well as content, so a gather
        # that returned the right rows in the wrong order would still fail
        def metric(f: pd.DataFrame) -> float:
            arr = f["score"].to_numpy()
            return float(np.mean(arr * np.arange(1, len(arr) + 1)))

        before = original_replicates(frame, metric, n_iter, seed)
        after = vectorised_replicates(frame, metric, n_iter, seed)
        same = np.array_equal(before, after)
        print(f"case {case}: {len(frame)} rows, {n_subjects} subjects -> "
              f"{'IDENTICAL' if same else 'DIFFERENT'}")
        if not same:
            failures += 1
            bad = np.flatnonzero(before != after)[:5]
            for i in bad:
                print(f"   replicate {i}: {before[i]!r} != {after[i]!r}")

    # and the public entry point still runs end to end
    rng = np.random.default_rng(5)
    frame = make_frame(rng, 50, 4)
    result = patient_bootstrap(frame, lambda f: float(f["score"].mean()),
                               n_iter=200, ci_method="percentile", seed=11)
    ok = np.isfinite([result.point, result.ci_low, result.ci_high]).all()
    print(f"patient_bootstrap end to end: point={result.point:.6f} "
          f"ci=({result.ci_low:.6f}, {result.ci_high:.6f}) -> {'ok' if ok else 'FAILED'}")
    failures += 0 if ok else 1

    print("PASS" if not failures else f"FAIL ({failures})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
