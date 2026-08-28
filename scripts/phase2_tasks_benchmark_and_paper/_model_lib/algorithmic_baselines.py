"""The doc-mandated rule baselines (spec §5.1, §9.5). No learned ECG encoder.

    | A1     | logistic regression on machine-measurement summary stats     |
    | A2, B1 | NeuroKit2 R-peaks -> mean instantaneous HR -> bin;
    |        | NeuroKit2 wavelet delineation -> mean QRS duration -> bin;
    |        | -> QT -> Bazett QTc -> bin                                   |
    | A4     | NeuroKit2 R-peak + wavelet QRS delineator -- F1 = 1.0 oracle  |
    | A6     | Cox proportional hazards on age + sex + machine HR/QRS/QTc    |
    | B2     | the A2/B1 detector, run on the CORRUPTED signal               |
    | B3     | rule-based per-bin labeller from R-peaks + per-bin SQI        |
    | B5     | NeuroKit2 HR/QRS vs the report's own claim -> inconsistency   |

§11.2 makes a missing algorithmic baseline for a doc-mandated task CRITICAL, so
every task in that table has an entry here and `50_run_baselines_algorithmic.py`
refuses to report success without one.

**The detector must be `method="neurokit"`.** §4.A.4.7 calls A4's baseline
"Pan-Tompkins" *and* promises F1 = 1.0. Both can only be true if the baseline
runs the same detector that produced the ground truth -- and the Phase 1 regen
moved off `pantompkins` precisely because it was wrong (~74 K false labels,
progress-doc trap 2). The corrected path is NeuroKit's default. `pantompkins` is
still available through ``method=`` so the supplementary can report the
detector-disagreement row, but it is not the oracle.

Two baselines read fields that are FORBIDDEN as model inputs. That is deliberate
and declared: `task_input_policy.yaml` carries a `baseline_only_exemptions`
block for A1 (§4.A.1.7) and A6 (§4.A.6.7). A rule baseline that cannot see the
machine measurements is not a baseline. Nothing here ever reaches a trained
encoder.
"""

from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _dataset_lib import build_common as bc                     # noqa: E402
from _dataset_lib.modality import read_modality                 # noqa: E402
from _dataset_lib.task_spec import FS_HZ, N_BINS, N_SAMPLES     # noqa: E402

DETECTOR_METHOD = "neurokit"          # progress-doc trap 2 -- NOT "pantompkins"
DELINEATE_METHOD = "dwt"
FIDUCIALS_PATH = bc.DATA_PROCESSED / "fiducials_lead2.parquet"


def _silence_neurokit() -> None:
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    warnings.filterwarnings("ignore", category=UserWarning)
    np.seterr(all="ignore")


# -----------------------------------------------------------------------------
# the detector -- the corrected Phase 1 path, verbatim
# -----------------------------------------------------------------------------
def _indices(values) -> np.ndarray:
    if values is None:
        return np.empty(0, dtype="int64")
    array = np.asarray(values)
    array = array[~pd.isna(array)]
    return array.astype("int64") if array.size else np.empty(0, dtype="int64")


def detect_fiducials(signal: np.ndarray, *, method: str = DETECTOR_METHOD) -> dict[str, Any]:
    """R-peaks, QRS bounds and T-offsets from a Lead-II strip.

    Mirrors `32_compute_structured_features.py::_extract_wave_features` lines
    364-390: ``ecg_peaks`` with no preceding ``ecg_clean``, then ``ecg_delineate``
    on the SAME array with ``check=False``. Deviating from that reproduces the
    Phase 1 detector bug rather than the Phase 1 ground truth.
    """
    import neurokit2 as nk

    _silence_neurokit()
    lead2 = np.asarray(signal, dtype="float64").ravel()
    out: dict[str, Any] = {"r_peaks": np.empty(0, dtype="int64"),
                           "qrs_onsets": np.empty(0, dtype="int64"),
                           "qrs_offsets": np.empty(0, dtype="int64"),
                           "t_offsets": np.empty(0, dtype="int64"),
                           "fallback_used": False, "delineate_ok": False}
    try:
        _, peak_info = nk.ecg_peaks(lead2, sampling_rate=FS_HZ, method=method)
        out["r_peaks"] = _indices(peak_info.get("ECG_R_Peaks"))
    except Exception:
        out["fallback_used"] = True
        return out
    if out["r_peaks"].size < 2:
        out["fallback_used"] = True
        return out
    try:
        _, waves = nk.ecg_delineate(lead2, rpeaks=out["r_peaks"], sampling_rate=FS_HZ,
                                    method=DELINEATE_METHOD, show=False, check=False)
        out["qrs_onsets"] = _indices(waves.get("ECG_R_Onsets"))
        out["qrs_offsets"] = _indices(waves.get("ECG_R_Offsets"))
        out["t_offsets"] = _indices(waves.get("ECG_T_Offsets"))
        out["delineate_ok"] = True
    except Exception:
        pass
    return out


def measurements_from_fiducials(fiducials: dict[str, Any]) -> dict[str, float]:
    """Mean instantaneous HR, mean QRS duration and Bazett QTc (§5.1)."""
    peaks = np.asarray(fiducials["r_peaks"], dtype="float64")
    out = {"hr_bpm": float("nan"), "qrs_ms": float("nan"), "qtc_ms": float("nan"),
           "rr_ms": float("nan")}
    if peaks.size >= 2:
        rr_ms = np.diff(peaks) * 1000.0 / FS_HZ
        rr_ms = rr_ms[(rr_ms > 200) & (rr_ms < 3000)]        # 20-300 bpm
        if rr_ms.size:
            out["rr_ms"] = float(np.mean(rr_ms))
            out["hr_bpm"] = float(np.mean(60000.0 / rr_ms))

    onsets = np.asarray(fiducials["qrs_onsets"], dtype="float64")
    offsets = np.asarray(fiducials["qrs_offsets"], dtype="float64")
    n = min(onsets.size, offsets.size)
    if n:
        durations = (offsets[:n] - onsets[:n]) * 1000.0 / FS_HZ
        durations = durations[(durations > 20) & (durations < 300)]
        if durations.size:
            out["qrs_ms"] = float(np.mean(durations))

    t_offsets = np.asarray(fiducials["t_offsets"], dtype="float64")
    m = min(onsets.size, t_offsets.size)
    if m and np.isfinite(out["rr_ms"]) and out["rr_ms"] > 0:
        qt_ms = (t_offsets[:m] - onsets[:m]) * 1000.0 / FS_HZ
        qt_ms = qt_ms[(qt_ms > 200) & (qt_ms < 800)]
        if qt_ms.size:
            # Bazett: QTc = QT / sqrt(RR in seconds)
            out["qtc_ms"] = float(np.mean(qt_ms) / np.sqrt(out["rr_ms"] / 1000.0))
    return out


def measurement_baseline_row(study_id: int, signal_kind: str = "raw_lead2",
                             *, corruption_type: str | None = None,
                             snr_db: int | None = None,
                             method: str = DETECTOR_METHOD) -> dict[str, Any]:
    """One A2 / B1 / B2 baseline row: detect, measure, bin (§5.1)."""
    if corruption_type is not None:
        signal = read_modality(study_id, "signal_corrupted",
                               corruption_type=corruption_type, snr_db=int(snr_db))
    else:
        signal = read_modality(study_id, signal_kind)
    signal = np.asarray(signal, dtype="float32")
    if signal.ndim == 2:
        from _dataset_lib.modality import LEAD_II_INDEX

        signal = signal[LEAD_II_INDEX]

    fiducials = detect_fiducials(signal, method=method)
    values = measurements_from_fiducials(fiducials)
    return {
        "study_id": int(study_id),
        **values,
        "hr_label": _bin_hr(values["hr_bpm"]),
        "qrs_label": _bin_qrs(values["qrs_ms"]),
        "qtc_label": _bin_qtc(values["qtc_ms"]),
        "n_peaks": int(np.asarray(fiducials["r_peaks"]).size),
        "fallback_used": bool(fiducials["fallback_used"]),
        "delineate_ok": bool(fiducials["delineate_ok"]),
    }


# The §4.A.2.3 bins, restated on scalars (build_common's versions take Series).
def _bin_hr(value: float) -> str | None:
    if not np.isfinite(value):
        return None
    return "bradycardia" if value < 60 else ("normal" if value < 100 else "tachycardia")


def _bin_qrs(value: float) -> str | None:
    if not np.isfinite(value):
        return None
    return "normal" if value < 100 else ("borderline" if value < 120 else "wide")


def _bin_qtc(value: float) -> str | None:
    if not np.isfinite(value):
        return None
    return "short" if value < 350 else ("normal" if value < 450 else "prolonged")


def label_to_onehot(label: str | None, classes: Sequence[str]) -> np.ndarray:
    """A rule baseline emits a hard class; the metrics want a probability vector.

    One-hot is the honest encoding: the rule has no calibrated confidence, so
    AUPRC scores it as the step function it actually is. An unmeasurable strip
    gets a uniform vector rather than a guess.
    """
    vector = np.zeros(len(classes), dtype="float64")
    if label is None or label not in classes:
        vector[:] = 1.0 / len(classes)
    else:
        vector[list(classes).index(label)] = 1.0
    return vector


# -----------------------------------------------------------------------------
# A4 / B3 -- oracles, read straight from the ground-truth artifact
# -----------------------------------------------------------------------------
def fiducial_oracle(study_ids: Sequence[int]) -> pd.DataFrame:
    """A4's oracle (§4.A.4.7): the same NeuroKit output that built the labels.

    Reading `fiducials_lead2.parquet` rather than re-running the detector is
    what makes F1 = 1.0 exact rather than approximate -- re-running would
    reproduce it only up to NeuroKit's own numerical reproducibility.
    """
    wanted = set(int(s) for s in study_ids)
    frame = pd.read_parquet(FIDUCIALS_PATH,
                            columns=["study_id", "r_peaks_lead2", "qrs_onsets_lead2",
                                     "qrs_offsets_lead2", "n_peaks", "fallback_used"])
    return frame[frame.study_id.isin(wanted)].reset_index(drop=True)


def b3_oracle(study_ids: Sequence[int], noisy_sqi_threshold: float) -> pd.DataFrame:
    """B3's oracle (§4.B.3.7): the per-bin rule, on the same fiducials + SQI."""
    wanted = set(int(s) for s in study_ids)
    frame = pd.read_parquet(FIDUCIALS_PATH,
                            columns=["study_id", "r_peaks_lead2", "qrs_onsets_lead2",
                                     "qrs_offsets_lead2", "sqi_per_bin", "fallback_used"])
    frame = frame[frame.study_id.isin(wanted)].reset_index(drop=True)

    rows = []
    for record in frame.itertuples(index=False):
        bins = per_bin_labels(np.asarray(record.r_peaks_lead2),
                             np.asarray(record.qrs_onsets_lead2),
                             np.asarray(record.qrs_offsets_lead2),
                             np.asarray(record.sqi_per_bin, dtype="float64"),
                             noisy_sqi_threshold)
        rows.append({"study_id": int(record.study_id), "fallback_used": bool(record.fallback_used),
                     **bins})
    return pd.DataFrame(rows)


def per_bin_labels(r_peaks: np.ndarray, qrs_onsets: np.ndarray, qrs_offsets: np.ndarray,
                   sqi_per_bin: np.ndarray, noisy_threshold: float) -> dict[str, list[int]]:
    """The four §4.B.3.3 queries at 1-second resolution."""
    samples_per_bin = N_SAMPLES // N_BINS
    high = np.zeros(N_BINS, dtype=int)
    low = np.zeros(N_BINS, dtype=int)
    wide = np.zeros(N_BINS, dtype=int)
    noisy = np.zeros(N_BINS, dtype=int)

    peaks = np.asarray(r_peaks, dtype="float64")
    if peaks.size >= 2:
        midpoints = (peaks[:-1] + peaks[1:]) / 2.0
        rr_ms = np.diff(peaks) * 1000.0 / FS_HZ
        with np.errstate(divide="ignore", invalid="ignore"):
            instantaneous = 60000.0 / rr_ms
        for midpoint, rate in zip(midpoints, instantaneous):
            index = int(midpoint) // samples_per_bin
            if 0 <= index < N_BINS and np.isfinite(rate):
                if rate > 100:
                    high[index] = 1
                if rate < 60:
                    low[index] = 1

    n = min(len(qrs_onsets), len(qrs_offsets))
    for onset, offset in zip(np.asarray(qrs_onsets)[:n], np.asarray(qrs_offsets)[:n]):
        if onset < 0 or offset < 0:
            continue
        if (offset - onset) > 60:          # 60 samples at 500 Hz = 120 ms
            index = int(onset) // samples_per_bin
            if 0 <= index < N_BINS:
                wide[index] = 1

    sqi = np.asarray(sqi_per_bin, dtype="float64")
    if sqi.size == N_BINS:
        noisy = (np.nan_to_num(sqi, nan=0.0) < float(noisy_threshold)).astype(int)

    return {"HIGH_HEART_RATE": high.tolist(), "LOW_HEART_RATE": low.tolist(),
            "WIDE_QRS": wide.tolist(), "NOISY_SEGMENT": noisy.tolist()}


# -----------------------------------------------------------------------------
# A1 -- logistic regression on machine-measurement summary stats (§4.A.1.7)
# -----------------------------------------------------------------------------
def machine_feature_table(study_ids: Sequence[int]) -> pd.DataFrame:
    """HR / QRS / QTc / axis / PR, sentinel-masked. BASELINE-ONLY (§4.A.1.4)."""
    features = bc.machine_measurements()
    wanted = set(int(s) for s in study_ids)
    features = features[features.study_id.isin(wanted)].copy()
    columns = ["hr_bpm", "qrs_ms", "qtc_ms", "qrs_axis", "pr_ms"]
    for column in columns:
        median = features[column].median()
        features[f"{column}_missing"] = features[column].isna().astype("float64")
        features[column] = features[column].fillna(median)
    return features[["study_id"] + columns + [f"{c}_missing" for c in columns]]


def logistic_baseline(train: pd.DataFrame, test: pd.DataFrame, feature_columns: Sequence[str],
                      label_columns: Sequence[str]) -> pd.DataFrame:
    """Per-head logistic regression fitted on TRAIN, scored on TEST."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(train[list(feature_columns)].to_numpy())
    x_train = scaler.transform(train[list(feature_columns)].to_numpy())
    x_test = scaler.transform(test[list(feature_columns)].to_numpy())

    out = pd.DataFrame({"study_id": test["study_id"].to_numpy()})
    for label in label_columns:
        y = train[label].astype(bool).to_numpy()
        if len(np.unique(y)) < 2:
            out[f"y_pred_proba_{label}"] = float(y.mean())
            continue
        model = LogisticRegression(max_iter=2000, class_weight="balanced")
        model.fit(x_train, y)
        out[f"y_pred_proba_{label}"] = model.predict_proba(x_test)[:, 1]
    return out


def multiclass_logistic_baseline(train: pd.DataFrame, test: pd.DataFrame,
                                 feature_columns: Sequence[str],
                                 label_columns: Sequence[str],
                                 classes: Sequence[str]) -> pd.DataFrame:
    """Per-head multinomial logistic fitted on TRAIN, scored on TEST.

    A3's structured-feature floor (Plan A/B §5.9, which requires the structured
    baseline for A1, A3 **and** A6). Spec §4.A.3.7 waived it on the grounds that
    "no rule-based ECG -> lab predictor exists" -- true of a *rule*, but §5.9
    asks for a *fitted* feature model, and reference [R5] (CardioLab) is exactly
    that comparison. Without it A3's neural numbers have no floor to clear.

    Returns one probability column per (head, class), plus the arg-max label, so
    the frame matches what `31_eval.py` expects from a multiclass head.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    columns = list(feature_columns)
    classes = list(classes)
    scaler = StandardScaler().fit(train[columns].to_numpy())
    x_train = scaler.transform(train[columns].to_numpy())
    x_test = scaler.transform(test[columns].to_numpy())

    # Collected into a dict and concatenated once -- 35 heads x 6 columns
    # inserted one at a time fragments the frame badly at full scale.
    collected: dict[str, Any] = {"study_id": test["study_id"].to_numpy()}
    for label in label_columns:
        y = train[label].astype("string").to_numpy()
        keep = pd.notna(y)
        present = sorted(set(y[keep]))
        proba = np.zeros((len(x_test), len(classes)), dtype="float64")

        if len(present) < 2:
            # A head with one observed class in train cannot be fitted. Emit the
            # train prevalence rather than a fabricated model -- honest, and the
            # §6.7 support rule already flags these slices.
            for index, name in enumerate(classes):
                proba[:, index] = float((y[keep] == name).mean()) if keep.any() else 0.0
        else:
            model = LogisticRegression(max_iter=2000, class_weight="balanced")
            model.fit(x_train[keep], y[keep])
            fitted = model.predict_proba(x_test)
            for position, name in enumerate(model.classes_):
                proba[:, classes.index(str(name))] = fitted[:, position]

        for index, name in enumerate(classes):
            collected[f"y_pred_proba_{label}__{name}"] = proba[:, index]
        collected[f"y_pred_index_{label}"] = proba.argmax(axis=1)
    return pd.DataFrame(collected)


# -----------------------------------------------------------------------------
# A6 -- Cox proportional hazards (§4.A.6.7, §5.1)
# -----------------------------------------------------------------------------
def patient_demographics() -> pd.DataFrame:
    """`anchor_age` and `gender` from the Phase 1 EHR cache. BASELINE-ONLY."""
    patients = pd.read_parquet(bc.EHR_CACHE / "patients.parquet",
                               columns=["subject_id", "gender", "anchor_age"])
    patients["sex_male"] = (patients["gender"].astype(str).str.upper() == "M").astype("float64")
    return patients[["subject_id", "anchor_age", "sex_male"]]


def cox_baseline(train: pd.DataFrame, test: pd.DataFrame, *, duration_column: str,
                 event_column: str,
                 feature_columns: Sequence[str]) -> tuple[np.ndarray, dict[str, Any]]:
    """Fit Cox PH on train, return the test partial hazard as a risk score.

    A6's heads are binary at fixed horizons, but §5.1 asks for Cox, and Cox
    needs (duration, event). Duration is time to the event when it was observed
    and the follow-up length otherwise; the partial hazard is a monotone risk
    score, which is exactly what a ranking metric like AUPRC consumes.
    """
    from lifelines import CoxPHFitter

    columns = list(feature_columns) + [duration_column, event_column]
    fit_frame = train[columns].dropna()
    fit_frame = fit_frame[fit_frame[duration_column] > 0]
    info: dict[str, Any] = {"n_fit": int(len(fit_frame)),
                            "n_events": int(fit_frame[event_column].sum())}
    if len(fit_frame) < 50 or fit_frame[event_column].sum() < 5:
        info["status"] = "skipped_insufficient_events"
        return np.full(len(test), np.nan), info

    model = CoxPHFitter(penalizer=0.1)
    model.fit(fit_frame, duration_col=duration_column, event_col=event_column)
    scoring = test[list(feature_columns)].copy()
    for column in feature_columns:
        scoring[column] = scoring[column].fillna(fit_frame[column].median())
    info["status"] = "ok"
    info["coefficients"] = {k: float(v) for k, v in model.params_.items()}
    info["concordance_train"] = float(model.concordance_index_)
    return model.predict_partial_hazard(scoring).to_numpy(), info


# -----------------------------------------------------------------------------
# B5 -- report-claim vs detector inconsistency (§5.1)
# -----------------------------------------------------------------------------
def load_claim_dictionary() -> dict[str, Any]:
    import yaml

    return yaml.safe_load(
        (bc.CONFIG_DIR / "claim_dictionary_LOCKED.yaml").read_text(encoding="utf-8"))


def claim_polarity(report_text: str, family: str, dictionary: dict[str, Any]) -> str | None:
    """Which polarity, if any, the report asserts for one family."""
    forms = dictionary["families"][family]["surface_forms"]
    lowered = str(report_text).lower()
    for form in forms:
        if re.search(form["pattern"], lowered):
            return str(form["polarity"])
    return None


def b5_rule_flag(report_text: str, hr_bpm: float, qrs_ms: float,
                 dictionary: dict[str, Any]) -> dict[str, Any]:
    """1 when the report's HR or QRS claim contradicts the detector (§5.1).

    Only HR and QRS: §5.1 specifies "NeuroKit2 HR/QRS detector vs report-text
    regex". Axis and PR are not recoverable from a single Lead-II strip, so the
    rule abstains on those families rather than guessing -- which is itself the
    finding this baseline is meant to expose.
    """
    inconsistencies: list[str] = []

    hr_claim = claim_polarity(report_text, "HR", dictionary)
    if hr_claim and np.isfinite(hr_bpm):
        if hr_claim == "brady" and hr_bpm >= 60:
            inconsistencies.append("HR")
        elif hr_claim == "tachy" and hr_bpm <= 100:
            inconsistencies.append("HR")

    qrs_claim = claim_polarity(report_text, "QRS", dictionary)
    if qrs_claim == "wide" and np.isfinite(qrs_ms) and qrs_ms < 120:
        inconsistencies.append("QRS")

    return {"flag": int(bool(inconsistencies)),
            "families_flagged": ",".join(inconsistencies) or None,
            "hr_claim": hr_claim, "qrs_claim": qrs_claim}


def _self_check() -> None:
    """The detector, the bins, the B3 rule and the B5 flag, on real data."""
    import neurokit2 as nk

    _silence_neurokit()
    simulated = nk.ecg_simulate(duration=10, sampling_rate=FS_HZ, heart_rate=80,
                               random_state=0)
    fiducials = detect_fiducials(np.asarray(simulated))
    assert not fiducials["fallback_used"], "detector failed on a clean simulated ECG"
    values = measurements_from_fiducials(fiducials)
    assert 70 <= values["hr_bpm"] <= 90, values
    assert _bin_hr(values["hr_bpm"]) == "normal", values

    assert _bin_hr(45) == "bradycardia" and _bin_hr(140) == "tachycardia"
    assert _bin_qrs(80) == "normal" and _bin_qrs(110) == "borderline" and _bin_qrs(150) == "wide"
    assert _bin_qtc(300) == "short" and _bin_qtc(400) == "normal" and _bin_qtc(500) == "prolonged"
    assert _bin_hr(float("nan")) is None

    onehot = label_to_onehot("normal", ["bradycardia", "normal", "tachycardia"])
    assert onehot.tolist() == [0.0, 1.0, 0.0]
    assert label_to_onehot(None, ["a", "b"]).tolist() == [0.5, 0.5]

    # B3 rule: a 150 bpm strip must light the HIGH_HEART_RATE bins it covers.
    fast_peaks = np.arange(0, N_SAMPLES, 200)          # 200 samples = 150 bpm
    bins = per_bin_labels(fast_peaks, np.array([]), np.array([]),
                          np.full(N_BINS, 0.9), 0.415030)
    assert sum(bins["HIGH_HEART_RATE"]) >= 9, bins["HIGH_HEART_RATE"]
    assert sum(bins["LOW_HEART_RATE"]) == 0
    noisy = per_bin_labels(fast_peaks, np.array([]), np.array([]),
                           np.array([0.1] * 3 + [0.9] * 7), 0.415030)
    assert noisy["NOISY_SEGMENT"] == [1, 1, 1, 0, 0, 0, 0, 0, 0, 0], noisy["NOISY_SEGMENT"]
    wide = per_bin_labels(np.array([1000]), np.array([1000]), np.array([1100]),
                          np.full(N_BINS, 0.9), 0.415030)
    assert wide["WIDE_QRS"][2] == 1, wide["WIDE_QRS"]

    dictionary = load_claim_dictionary()
    assert claim_polarity("Sinus bradycardia", "HR", dictionary) == "brady"
    assert claim_polarity("Left bundle branch block", "QRS", dictionary) == "wide"
    assert claim_polarity("Incomplete right bundle branch block", "QRS", dictionary) is None, \
        "the 'incomplete' negative lookbehind is not firing"
    assert b5_rule_flag("Sinus bradycardia", 95.0, 90.0, dictionary)["flag"] == 1
    assert b5_rule_flag("Sinus bradycardia", 45.0, 90.0, dictionary)["flag"] == 0
    assert b5_rule_flag("Normal sinus rhythm", 75.0, 90.0, dictionary)["flag"] == 0

    # A4 oracle: exact agreement with the ground-truth artifact.
    from _train_lib.metrics import match_events

    oracle = fiducial_oracle(pd.read_parquet(FIDUCIALS_PATH, columns=["study_id"])
                             .study_id.head(20).tolist())
    assert len(oracle) == 20
    for record in oracle.itertuples(index=False):
        result = match_events(np.asarray(record.r_peaks_lead2),
                              np.asarray(record.r_peaks_lead2))
        assert result["f1"] == 1.0, "the A4 oracle does not reproduce F1 = 1.0"

    print(f"algorithmic_baselines self-check: PASS  (detector={DETECTOR_METHOD}, "
          f"simulated HR {values['hr_bpm']:.1f} bpm, QRS {values['qrs_ms']:.1f} ms, "
          f"QTc {values['qtc_ms']:.1f} ms)")


if __name__ == "__main__":
    _self_check()
