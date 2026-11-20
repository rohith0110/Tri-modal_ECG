"""An eval checkpoint must not outlive the predictions it scored (open question 18).

`31_eval.py` resumes from `.eval_checkpoints/<task>__<tier>.jsonl`. Its stamp
used to cover the bootstrap settings only, so after the A5/B4 image tiers were
retrained on the §12.12 rows, a leftover checkpoint from the shortcut-trained
seeds would have been adopted unit for unit. Records now carry a content hash
of the prediction files. Also covers `<task>_extras.json`, which used to be
rewritten from the one tier just evaluated and lost every other tier's block.

    python tests/test_eval_checkpoint_predictions.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
_spec = importlib.util.spec_from_file_location("eval31", HERE / "31_eval.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)

SETTINGS = {"n_iter": 10000, "method": "bca", "seed": 20260826, "level": 0.95,
            "unit": "subject_id", "fallback": "percentile"}


def _write(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def test_fingerprint_follows_content_not_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "a").mkdir(); (tmp / "b").mkdir()
        for d in ("a", "b"):
            (tmp / d / "p42.parquet").write_bytes(b"seed42-bytes")
            (tmp / d / "p123.parquet").write_bytes(b"seed123-bytes")
        fa = ev.predictions_fingerprint({42: tmp / "a/p42.parquet", 123: tmp / "a/p123.parquet"})
        fb = ev.predictions_fingerprint({123: tmp / "b/p123.parquet", 42: tmp / "b/p42.parquet"})
        assert fa == fb, "same bytes in another home must hash the same (--extra-checkpoint)"
        (tmp / "b/p42.parquet").write_bytes(b"retrained-seed42")
        fc = ev.predictions_fingerprint({42: tmp / "b/p42.parquet", 123: tmp / "b/p123.parquet"})
        assert fc != fa, "a retrained seed must change the fingerprint"


def test_checkpoint_from_other_predictions_is_ignored() -> None:
    stamp = ev.checkpoint_stamp(SETTINGS)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "A5__tier.jsonl"
        _write(path, [
            {"unit": "u_old", "row": {"v": 0.75}, "stamp": stamp, "predictions": "OLD"},
            {"unit": "u_new", "row": {"v": 0.50}, "stamp": stamp, "predictions": "NEW"},
            {"unit": "u_legacy", "row": {"v": 0.60}, "stamp": stamp},
            {"unit": "u_bootstrap", "row": {"v": 0.1}, "stamp": "other", "predictions": "NEW"},
        ])
        done = ev.load_checkpoint("A5", "tier", False, SETTINGS, path=path, predictions="NEW")
        assert set(done) == {"u_new", "u_legacy"}, done
        assert done["u_new"] == {"v": 0.50}


def test_append_records_fingerprint() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        original = ev.RESULTS_DIR
        ev.RESULTS_DIR = Path(tmp)
        try:
            (Path(tmp) / ".eval_checkpoints").mkdir()
            ev.append_checkpoint("T", "tier", False, "u1", {"v": 1}, "s", "FP")
            line = ev.checkpoint_path("T", "tier", False).read_text(encoding="utf-8")
            assert json.loads(line)["predictions"] == "FP"
        finally:
            ev.RESULTS_DIR = original


def test_extras_merge_keeps_other_tiers() -> None:
    previous = {"calibration": {"image_clean": {"ece": 0.1}, "text_tfidf": {"ece": 0.2}},
                "retrieval": {"image_clean": {"42": 0.3}}}
    new = {"calibration": {"image_clean": {"ece": 0.05}, "fusion": {"ece": 0.07}}}
    merged = ev.merge_extras(previous, new)
    assert merged["calibration"] == {"image_clean": {"ece": 0.05},
                                     "text_tfidf": {"ece": 0.2},
                                     "fusion": {"ece": 0.07}}
    assert merged["retrieval"] == previous["retrieval"]
    assert previous["calibration"]["image_clean"] == {"ece": 0.1}, "input mutated"


def test_stored_event_matches_equal_rematching() -> None:
    """A4 metrics read per-row matches stored once; a resample must score the
    same as re-matching it, including duplicated rows and empty predictions."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(0)
    truth = [np.sort(rng.choice(5000, 8, replace=False)) for _ in range(40)]
    pred = [np.sort(t + rng.integers(-8, 9, t.size)) for t in truth]
    pred[3] = np.array([], dtype="int64")
    frame = pd.DataFrame({"y_true_r_peaks_lead2": truth, "y_pred_r_peaks": pred})
    stored = ev.add_event_match_columns(frame, "y_true_r_peaks_lead2", "y_pred_r_peaks")
    rows = rng.integers(0, len(frame), 60)                       # duplicates on purpose
    head = type("Head", (), {"kind": "peak_seq", "name": "fiducials"})()
    fns = ev.head_metric_fns(None, head)
    rematched = ev.M.aggregate_event_matches([
        ev.M.match_events(np.asarray(t), np.asarray(p))
        for t, p in zip(frame.take(rows)["y_true_r_peaks_lead2"],
                        frame.take(rows)["y_pred_r_peaks"])])
    for metric, key in (("r_peak_f1", "f1"), ("r_peak_precision", "precision"),
                        ("r_peak_recall", "recall"),
                        ("r_peak_mean_abs_error_ms", "mean_abs_error_ms")):
        assert fns[metric](stored.take(rows)) == rematched[key], metric
        assert fns[metric](frame.take(rows)) == rematched[key], f"{metric} (no stored columns)"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} PASS")
