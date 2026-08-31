"""Cross-modal verification rows -- shared by A5 (§4.A.5) and B4 (§4.B.4).

§4.B.4.3 says B4 uses "the same 5-negative-type construction as A5's
verification head", and §4.B.4.8 asks whether training B4 jointly with A5's
masked-attribute head helps or hurts *pure* verification. That comparison is
only meaningful if both tasks see the same verification rows, so the
construction lives here and both builders call it. It is fully deterministic --
no RNG state, only a hash of (anchor, negative type) -- so the two tasks get
byte-identical rows without either depending on the other's output.

Per anchor study (§4.A.5.3): 2 positives and 5 negatives = 7 rows.

| row | signal | image | text |
| --- | --- | --- | --- |
| positive (clean) | anchor | anchor, clean rendering | anchor |
| positive (scanlike) | anchor | anchor, scan-like rendering | anchor |
| `TEXT_SWAP` | anchor | anchor | **donor** |
| `IMAGE_SWAP` | anchor | **donor** | anchor |
| `SIGNAL_SWAP` | **donor** | anchor | anchor |
| `HARD_NEGATIVE_TEXT` | anchor | anchor | **same-HR-bucket donor** |
| `PARTIAL_MISMATCH` | anchor | **donor A** | **donor B** |

Two rules the spec does not spell out but that the split contract forces:

* **Donors come from the anchor's own split.** A train row pointing at a test
  subject's signal would put test bytes into training -- the §4.C invariant-1
  violation the whole split exists to prevent. Donor selection is therefore
  per split.
* **Negatives all use the clean rendering.** Fixing the rendering keeps the
  per-``neg_type`` F1 table (§4.A.5.8) from being confounded by how the image
  was drawn. The clean-vs-scanlike and Lead-II-vs-12-lead comparisons are done
  by resolving a different modality kind for the same ``image_id`` at load
  time, which is what ``image_type`` records.

``HARD_NEGATIVE_TEXT`` is emitted only where a same-HR-bucket, different-subject
alternative exists in the split (§4.A.5.3), so a few anchors yield 6 rows.

**Test rows carry four more negatives** -- Plan A/B §6.7's Levels 2-5, which the
original build omitted. They exist only in the test split, because they measure
generalisation to harder negatives rather than being something to train on:

| row | signal | image | text | §6.7 level |
| --- | --- | --- | --- | --- |
| `HARD_NEGATIVE_L2` | anchor | anchor | donor matched on HR + QRS bucket | 2 |
| `HARD_NEGATIVE_L3` | anchor | anchor | donor matched on HR + QRS + axis + QTc | 3 |
| `HARD_NEGATIVE_L4` | anchor | anchor | **the anchor's own subject**, another study | 4 |
| `HARD_NEGATIVE_L5` | anchor | anchor | the anchor's own report, one claim swapped | 5 |

Levels 0 and 1 are the five original negative types: the cross-subject swaps are
Level 0, ``HARD_NEGATIVE_TEXT`` is Level 1.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
import pyarrow as pa

from . import build_common as bc

NEG_TYPES = ("TEXT_SWAP", "IMAGE_SWAP", "SIGNAL_SWAP", "HARD_NEGATIVE_TEXT", "PARTIAL_MISMATCH")

# ---------------------------------------------------------------------------
# The Plan A/B §6.7 difficulty ladder, Levels 2-5. TEST SPLIT ONLY.
# ---------------------------------------------------------------------------
# §6.7 specifies six levels and §6.8's Figure 4 is the CURVE across them; the
# original build stopped at two (Level 0 = the cross-subject swaps, Level 1 =
# HARD_NEGATIVE_TEXT's same-HR-bucket swap) and shipped the third empty. Two
# points are not a curve, and Level 4 -- same patient, different study -- is the
# rung that tests the patient/demographic shortcut, which is the shortcut most
# likely to be real in MIMIC where one subject carries many ECGs.
#
# **Why test-split only.** The levels measure GENERALISATION to harder
# negatives: §6.7's expected behaviour is "most shortcut models plateau". Train
# on Level 3 negatives and the plateau is trained away, so Figure 4 would
# measure the training distribution instead of the model's shortcut reliance.
# Keeping them out of train is the methodologically correct choice, and it also
# means not one model has to be retrained to get the curve.
#
# A5 and B4 both receive them, because §4.B.4.8's A5-vs-B4 comparison is only
# controlled while the two tasks see identical rows -- the builder asserts it.
DIFFICULTY_NEG_TYPES = ("HARD_NEGATIVE_L2", "HARD_NEGATIVE_L3",
                        "HARD_NEGATIVE_L4", "HARD_NEGATIVE_L5")
# The bucket columns each level matches its text donor on. Level 4 matches on
# nothing -- it matches on the SUBJECT, which is the opposite constraint.
DIFFICULTY_MATCH_KEYS = {
    "HARD_NEGATIVE_L2": ("hr_bucket", "qrs_bucket"),
    "HARD_NEGATIVE_L3": ("hr_bucket", "qrs_bucket", "axis_bucket", "qtc_bucket"),
}
B5_TASK_DIR = "B5_contradiction_detection"

SALTS = {
    "TEXT_SWAP": 0x51ED270B,
    "IMAGE_SWAP": 0x2545F491,
    "SIGNAL_SWAP": 0x9E3779B1,
    "HARD_NEGATIVE_TEXT": 0x7FEB352D,
    "PARTIAL_MISMATCH": 0x846CA68B,
    "PARTIAL_MISMATCH_B": 0xC2B2AE35,
    "HARD_NEGATIVE_L2": 0x1B873593,
    "HARD_NEGATIVE_L3": 0xCC9E2D51,
    "HARD_NEGATIVE_L4": 0x85EBCA6B,
    "HARD_NEGATIVE_L5": 0xC2B2AE3D,
}

SCHEMA = pa.schema([
    ("anchor_study_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("signal_id", pa.int64()),
    ("image_id", pa.int64()),
    ("text_id", pa.int64()),
    ("image_type", pa.string()),
    ("y_match", pa.int8()),
    ("neg_type", pa.string()),
    ("split", pa.string()),
    # Level 5 only, null everywhere else: the anchor's OWN report with a single
    # clinical claim swapped. The loader uses this string in place of the report
    # `text_id` points at. See `_level_5_rows`.
    ("text_override", pa.string()),
])

_U64 = np.uint64


def _mix(keys: np.ndarray, salt: int) -> np.ndarray:
    """splitmix64 finaliser -- a fast, deterministic, dependency-free hash.

    Used instead of ``numpy.random`` so a row's donor depends only on that row,
    never on iteration order or on how many rows came before it. Re-running the
    builder therefore reproduces the dataset exactly (§4.C invariant 2).
    """
    # The salt is folded in as a pre-masked Python int: numpy warns on a
    # scalar uint64 multiply that wraps, and wrapping is exactly what splitmix
    # wants.
    offset = _U64((salt * 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF)
    z = (keys.astype(_U64) + offset).astype(_U64)
    z = ((z ^ (z >> _U64(30))) * _U64(0xBF58476D1CE4E5B9)).astype(_U64)
    z = ((z ^ (z >> _U64(27))) * _U64(0x94D049BB133111EB)).astype(_U64)
    return (z ^ (z >> _U64(31))).astype(_U64)


def _pick_donors(study_ids: np.ndarray, subject_ids: np.ndarray, salt: int) -> np.ndarray:
    """A different-subject donor for every row of a pool, deterministically.

    The pool is ordered by (subject_id, study_id), so a subject's studies are
    contiguous and walking forward from a collision leaves that subject after at
    most (its study count) steps.
    """
    n = len(study_ids)
    if n < 2:
        return np.full(n, -1, dtype="int64")
    offset = (_mix(study_ids, salt) % _U64(n - 1)).astype("int64") + 1
    idx = (np.arange(n) + offset) % n
    clash = np.flatnonzero(subject_ids[idx] == subject_ids)
    for pos in clash:
        j = idx[pos]
        for _ in range(n):
            j = (j + 1) % n
            if subject_ids[j] != subject_ids[pos]:
                break
        idx[pos] = j
    still = subject_ids[idx] == subject_ids
    donors = study_ids[idx]
    donors[still] = -1          # a split holding a single subject yields no donor
    return donors


def _donor_frame(pool: pd.DataFrame, salt_key: str) -> pd.Series:
    """Donor study id per row of ``pool``, indexed like ``pool``."""
    ordered = pool.sort_values(["subject_id", "study_id"], kind="mergesort")
    donors = _pick_donors(
        ordered.study_id.to_numpy(), ordered.subject_id.to_numpy(), SALTS[salt_key]
    )
    return pd.Series(donors, index=ordered.index).reindex(pool.index)


def _grouped_donor(pool: pd.DataFrame, keys: Sequence[str], salt_key: str) -> np.ndarray:
    """A different-subject donor drawn from inside the row's own bucket.

    Generalises what HARD_NEGATIVE_TEXT does for `hr_bucket` to any tuple of
    bucket columns, which is how §6.7's Levels 2 and 3 tighten the match. A row
    whose bucket holds no usable alternative gets -1 and is dropped, so a level
    never fabricates a donor by relaxing its own matching rule.
    """
    donors = np.full(len(pool), -1, dtype="int64")
    usable = pool[list(keys)].notna().all(axis=1)
    for _, group in pool[usable].groupby(list(keys), sort=False, dropna=True):
        ordered = group.sort_values(["subject_id", "study_id"], kind="mergesort")
        picked = _pick_donors(ordered.study_id.to_numpy(), ordered.subject_id.to_numpy(),
                              SALTS[salt_key])
        donors[ordered.index.to_numpy()] = picked
    return donors


def _same_subject_donor(pool: pd.DataFrame, salt_key: str) -> np.ndarray:
    """Another study of the row's OWN subject -- §6.7 Level 4.

    Every other negative type is required to cross subjects; this one is
    required NOT to. That inversion is the point: a model that has learnt
    patient identity (age, sex, lead placement, cart) rather than the report's
    content scores near-perfectly on Levels 0-3 and collapses here.

    A subject with a single ECG has no alternative and yields -1.
    """
    donors = np.full(len(pool), -1, dtype="int64")
    for _, group in pool.groupby("subject_id", sort=False):
        if len(group) < 2:
            continue
        ordered = group.sort_values("study_id", kind="mergesort")
        ids = ordered.study_id.to_numpy()
        offset = (_mix(ids, SALTS[salt_key]) % _U64(len(ids) - 1)).astype("int64") + 1
        donors[ordered.index.to_numpy()] = ids[(np.arange(len(ids)) + offset) % len(ids)]
    return donors


def _b5_corrupted_reports(dev: bool = False) -> pd.Series:
    """``study_id -> corrupted_report_text`` for the corrupted TEST rows of B5.

    §6.7 Level 5 is "a near-duplicate hard negative with an altered
    report/image/signal component". The altered report already exists, locked
    and deterministic: B5 injects exactly one contradicted clinical claim into a
    report, only where the underlying measurement sits in a clear zone, and only
    by swapping surface forms the report actually contains. Reusing it means
    Level 5 introduces no new text-generation rule of its own, and the two tasks
    cannot drift apart.

    Returns an empty Series when B5 has not been built -- Level 5 is then simply
    absent, rather than the build failing.
    """
    # `tasks_root()` already resolves _dev from the module-level flag the
    # builders set with `bc.set_dev()`; `dev` is accepted for symmetry.
    path = bc.tasks_root() / B5_TASK_DIR / "test.parquet"
    if not path.exists():
        return pd.Series(dtype="string")
    b5 = pd.read_parquet(path, columns=["study_id", "is_corrupted", "corrupted_report_text"])
    b5 = b5[b5["is_corrupted"].fillna(False).astype(bool)]
    b5 = b5.dropna(subset=["corrupted_report_text"]).drop_duplicates("study_id")
    return b5.set_index("study_id")["corrupted_report_text"].astype("string")


def _difficulty_buckets(study_ids: np.ndarray) -> pd.DataFrame:
    """`qrs_bucket` / `qtc_bucket` / `axis_bucket` for the Level 2-3 matching.

    Cohort construction, not model input: the buckets decide which studies may
    serve as each other's hard negatives and never reach an encoder. Same
    standing as `hr_bucket`, which the cohort already carries and which Level 1
    already matches on.
    """
    measurements = bc.machine_measurements()
    measurements = measurements[measurements.study_id.isin(set(int(s) for s in study_ids))]
    return pd.DataFrame({
        "study_id": measurements["study_id"].to_numpy(),
        "qrs_bucket": bc.qrs_label(measurements["qrs_ms"]).to_numpy(),
        "qtc_bucket": bc.qtc_label(measurements["qtc_ms"]).to_numpy(),
        "axis_bucket": bc.axis_label(measurements["qrs_axis"]).to_numpy(),
    })


def build_verification(dev: bool = False) -> pd.DataFrame:
    """The 7-rows-per-anchor verification table for the full clean cohort."""
    cohort = bc.load_clean_cohort(dev=dev)
    # §4.A.5.2 needs all three modalities present; Phase 1 QC says all clean
    # studies have text, a clean image and a scan-like image, but assert rather
    # than assume -- the cohort definition must not drift silently.
    usable = cohort.text_ok.fillna(False) & cohort.image_clean_ok.fillna(False) \
        & cohort.image_scanlike_ok.fillna(False)
    cohort = cohort[usable][["study_id", "subject_id", "split", "hr_bucket"]].copy()
    # Levels 2-3 match on more than heart rate, so the extra buckets are joined
    # once here rather than recomputed per split.
    cohort = cohort.merge(_difficulty_buckets(cohort.study_id.to_numpy()),
                          on="study_id", how="left", validate="many_to_one")
    corrupted_reports = _b5_corrupted_reports(dev=dev)

    frames: list[pd.DataFrame] = []
    for split in bc.SPLITS:
        pool = cohort[cohort.split == split].reset_index(drop=True)
        if pool.empty:
            continue
        anchor = pool.study_id.to_numpy()
        subject = pool.subject_id.to_numpy()

        random_donor = {
            key: _donor_frame(pool, key).to_numpy()
            for key in ("TEXT_SWAP", "IMAGE_SWAP", "SIGNAL_SWAP",
                        "PARTIAL_MISMATCH", "PARTIAL_MISMATCH_B")
        }

        # HARD_NEGATIVE_TEXT draws inside the anchor's own HR bucket.
        hard = np.full(len(pool), -1, dtype="int64")
        for bucket, group in pool.groupby("hr_bucket", sort=False):
            donors = _pick_donors(
                group.sort_values(["subject_id", "study_id"], kind="mergesort").study_id.to_numpy(),
                group.sort_values(["subject_id", "study_id"], kind="mergesort").subject_id.to_numpy(),
                SALTS["HARD_NEGATIVE_TEXT"],
            )
            order = group.sort_values(["subject_id", "study_id"], kind="mergesort").index.to_numpy()
            hard[order] = donors

        def row(signal, image, text, image_type, y, neg, text_override=None):
            return pd.DataFrame({
                "anchor_study_id": anchor,
                "subject_id": subject,
                "signal_id": signal,
                "image_id": image,
                "text_id": text,
                "image_type": image_type,
                "y_match": np.int8(y),
                "neg_type": neg,
                "split": split,
                "text_override": (pd.Series([None] * len(anchor), dtype="string")
                                  if text_override is None else text_override),
            })

        frames.append(row(anchor, anchor, anchor, "clean", 1, None))
        frames.append(row(anchor, anchor, anchor, "scanlike", 1, None))
        frames.append(row(anchor, anchor, random_donor["TEXT_SWAP"], "clean", 0, "TEXT_SWAP"))
        frames.append(row(anchor, random_donor["IMAGE_SWAP"], anchor, "clean", 0, "IMAGE_SWAP"))
        frames.append(row(random_donor["SIGNAL_SWAP"], anchor, anchor, "clean", 0, "SIGNAL_SWAP"))
        frames.append(row(anchor, anchor, hard, "clean", 0, "HARD_NEGATIVE_TEXT"))
        frames.append(row(anchor, random_donor["PARTIAL_MISMATCH"],
                          random_donor["PARTIAL_MISMATCH_B"], "clean", 0, "PARTIAL_MISMATCH"))

        # -- Plan A/B §6.7 Levels 2-5, TEST SPLIT ONLY (see DIFFICULTY_NEG_TYPES)
        if split != "test":
            continue

        for neg_type, keys in DIFFICULTY_MATCH_KEYS.items():
            frames.append(row(anchor, anchor, _grouped_donor(pool, keys, neg_type),
                              "clean", 0, neg_type))

        frames.append(row(anchor, anchor, _same_subject_donor(pool, "HARD_NEGATIVE_L4"),
                          "clean", 0, "HARD_NEGATIVE_L4"))

        # Level 5: the anchor's OWN report, one clinical claim swapped. text_id
        # stays the anchor so the row is a near-duplicate in every other respect;
        # only rows for which B5 produced a corrupted report are emitted.
        override = pd.Series(anchor, dtype="int64").map(corrupted_reports).astype("string")             if len(corrupted_reports) else pd.Series([None] * len(anchor), dtype="string")
        level5 = row(anchor, anchor, anchor, "clean", 0, "HARD_NEGATIVE_L5",
                     text_override=override.to_numpy())
        frames.append(level5[pd.notna(level5["text_override"])])

    df = pd.concat(frames, ignore_index=True)
    # A row whose donor could not be found is dropped, not emitted with a -1.
    incomplete = (df.signal_id < 0) | (df.image_id < 0) | (df.text_id < 0)
    df = df[~incomplete]
    df["neg_type"] = df["neg_type"].astype("string")
    df["text_override"] = df["text_override"].astype("string")
    return df.sort_values(["anchor_study_id", "y_match", "neg_type"],
                          kind="mergesort").reset_index(drop=True)


def verification_stats(df: pd.DataFrame) -> dict:
    """Row counts, class balance, per-negative-type counts, and the leak checks."""
    by_split = {}
    for split in bc.SPLITS:
        part = df[df.split == split]
        by_split[split] = {
            "n_rows": int(len(part)),
            "n_anchors": int(part.anchor_study_id.nunique()),
            "n_positive": int((part.y_match == 1).sum()),
            "n_negative": int((part.y_match == 0).sum()),
        }
    return {
        "n_rows": int(len(df)),
        "n_anchors": int(df.anchor_study_id.nunique()),
        "n_subjects": int(df.subject_id.nunique()),
        "positive_rate_pct": round(100 * float((df.y_match == 1).mean()), 3),
        "rows_per_neg_type": {
            ("positive" if pd.isna(k) else str(k)): int(v)
            for k, v in df.neg_type.value_counts(dropna=False).items()
        },
        "image_type_counts": df.image_type.value_counts().to_dict(),
        "by_split": by_split,
    }


def assert_no_cross_split_donor(df: pd.DataFrame, cohort: pd.DataFrame) -> None:
    """Every referenced study must sit in the same split as its anchor row.

    This is the check that makes the negatives safe: a donor from another split
    would carry that split's bytes into this one.
    """
    split_of = cohort.set_index("study_id")["split"]
    for column in ("signal_id", "image_id", "text_id"):
        referenced = df[column].map(split_of)
        bad = int((referenced != df["split"]).sum())
        if bad:
            raise RuntimeError(f"{bad} rows reference a {column} from another split")


def assert_negatives_are_mismatched(df: pd.DataFrame, cohort: pd.DataFrame) -> None:
    """A negative must actually disagree with its anchor at the SUBJECT level.

    Pointing at a different study of the same patient would make ``y_match = 0``
    a lie for a model that learns patient identity.
    """
    subject_of = cohort.set_index("study_id")["subject_id"]
    negatives = df[df.y_match == 0]
    swapped = {
        "TEXT_SWAP": "text_id", "IMAGE_SWAP": "image_id", "SIGNAL_SWAP": "signal_id",
        "HARD_NEGATIVE_TEXT": "text_id",
        "HARD_NEGATIVE_L2": "text_id", "HARD_NEGATIVE_L3": "text_id",
    }
    # Levels 4 and 5 invert this rule on purpose, so they are checked for the
    # OPPOSITE property instead of being exempted silently.
    level4 = negatives[negatives.neg_type == "HARD_NEGATIVE_L4"]
    if len(level4):
        cross = int((level4.text_id.map(subject_of).to_numpy()
                     != level4.subject_id.to_numpy()).sum())
        if cross:
            raise RuntimeError(
                f"{cross} HARD_NEGATIVE_L4 rows swap in a DIFFERENT subject. Level 4 is "
                "the same-patient rung (§6.7): a cross-subject donor there would make it "
                "a duplicate of Level 0 and hide the patient-identity shortcut.")
        same_study = int((level4.text_id.to_numpy() == level4.anchor_study_id.to_numpy()).sum())
        if same_study:
            raise RuntimeError(f"{same_study} HARD_NEGATIVE_L4 rows point at the anchor's "
                               "own study -- that is a positive, not a negative")
    level5 = negatives[negatives.neg_type == "HARD_NEGATIVE_L5"]
    if len(level5):
        # Level 5 keeps every pointer on the anchor; what makes it a negative is
        # the altered report string, so that is what must be present and changed.
        if not (level5.text_id.to_numpy() == level5.anchor_study_id.to_numpy()).all():
            raise RuntimeError("HARD_NEGATIVE_L5 must keep the anchor's own text_id")
        if level5.text_override.isna().any():
            raise RuntimeError("HARD_NEGATIVE_L5 rows must all carry a text_override")
    for neg_type, column in swapped.items():
        part = negatives[negatives.neg_type == neg_type]
        same = int((part[column].map(subject_of).to_numpy() == part.subject_id.to_numpy()).sum())
        if same:
            raise RuntimeError(f"{same} {neg_type} rows swap in the anchor's own subject")
    partial = negatives[negatives.neg_type == "PARTIAL_MISMATCH"]
    same = int(
        ((partial.image_id.map(subject_of).to_numpy() == partial.subject_id.to_numpy())
         & (partial.text_id.map(subject_of).to_numpy() == partial.subject_id.to_numpy())).sum()
    )
    if same:
        raise RuntimeError(f"{same} PARTIAL_MISMATCH rows swap in the anchor's own subject twice")
