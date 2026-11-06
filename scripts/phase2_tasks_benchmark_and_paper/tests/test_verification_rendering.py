"""A5/B4 negatives must not be identifiable by their image rendering (open question 18).

Every positive pair is one clean row and one scan-like row (Truth doc §6.1), so
the negatives have to be scan-like at the same 50 % rate or "scan-like" alone
predicts a match. The original build drew every negative clean, and an
image-only model scored AUROC 0.751 on the shortcut and 0.502 on clean rows.

    python tests/test_verification_rendering.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _dataset_lib import verification_task as vt   # noqa: E402


def frame(scan_share_negative: float, n_anchors: int = 4000) -> pd.DataFrame:
    """One clean and one scan-like positive per anchor, five negatives at the given share."""
    positives = pd.DataFrame({
        "split": "train", "y_match": 1,
        "image_type": np.repeat(np.array(["clean", "scanlike"]), n_anchors),
    })
    n_negative = 5 * n_anchors
    n_scan = int(round(scan_share_negative * n_negative))
    negatives = pd.DataFrame({
        "split": "train", "y_match": 0,
        "image_type": ["scanlike"] * n_scan + ["clean"] * (n_negative - n_scan),
    })
    return pd.concat([positives, negatives], ignore_index=True)


def test_rendering_is_a_fair_deterministic_coin() -> None:
    anchors = np.arange(40_000_000, 40_200_000, dtype="int64")
    for neg_type in vt.NEG_TYPES + vt.DIFFICULTY_NEG_TYPES:
        first = vt.negative_rendering(anchors, neg_type)
        assert np.array_equal(first, vt.negative_rendering(anchors, neg_type)), neg_type
        share = float((first == "scanlike").mean())
        assert abs(share - 0.5) < 0.01, (neg_type, share)
        assert set(np.unique(first)) == {"clean", "scanlike"}, neg_type


def test_rendering_is_independent_across_negative_types() -> None:
    anchors = np.arange(200_000, dtype="int64")
    text = vt.negative_rendering(anchors, "TEXT_SWAP") == "scanlike"
    image = vt.negative_rendering(anchors, "IMAGE_SWAP") == "scanlike"
    agreement = float((text == image).mean())
    assert abs(agreement - 0.5) < 0.01, agreement


def test_balanced_frame_passes() -> None:
    vt.assert_rendering_balanced(frame(0.5))


def test_all_clean_negatives_fail() -> None:
    """The original construction: every negative clean."""
    try:
        vt.assert_rendering_balanced(frame(0.0))
    except RuntimeError as error:
        assert "rendering predicts y_match" in str(error)
    else:
        raise AssertionError("an all-clean negative set must be rejected")


def test_tolerance_boundary() -> None:
    vt.assert_rendering_balanced(frame(0.5 - vt.RENDERING_TOLERANCE + 0.005))
    try:
        vt.assert_rendering_balanced(frame(0.5 - vt.RENDERING_TOLERANCE - 0.005))
    except RuntimeError:
        return
    raise AssertionError("a gap just over the tolerance must be rejected")


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_") and callable(test):
            test()
            print(f"PASS  {name}")
