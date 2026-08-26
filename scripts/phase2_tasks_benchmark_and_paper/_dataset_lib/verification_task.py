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
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow as pa

from . import build_common as bc

NEG_TYPES = ("TEXT_SWAP", "IMAGE_SWAP", "SIGNAL_SWAP", "HARD_NEGATIVE_TEXT", "PARTIAL_MISMATCH")
SALTS = {
    "TEXT_SWAP": 0x51ED270B,
    "IMAGE_SWAP": 0x2545F491,
    "SIGNAL_SWAP": 0x9E3779B1,
    "HARD_NEGATIVE_TEXT": 0x7FEB352D,
    "PARTIAL_MISMATCH": 0x846CA68B,
    "PARTIAL_MISMATCH_B": 0xC2B2AE35,
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


def build_verification(dev: bool = False) -> pd.DataFrame:
    """The 7-rows-per-anchor verification table for the full clean cohort."""
    cohort = bc.load_clean_cohort(dev=dev)
    # §4.A.5.2 needs all three modalities present; Phase 1 QC says all clean
    # studies have text, a clean image and a scan-like image, but assert rather
    # than assume -- the cohort definition must not drift silently.
    usable = cohort.text_ok.fillna(False) & cohort.image_clean_ok.fillna(False) \
        & cohort.image_scanlike_ok.fillna(False)
    cohort = cohort[usable][["study_id", "subject_id", "split", "hr_bucket"]].copy()

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

        def row(signal, image, text, image_type, y, neg):
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
            })

        frames.append(row(anchor, anchor, anchor, "clean", 1, None))
        frames.append(row(anchor, anchor, anchor, "scanlike", 1, None))
        frames.append(row(anchor, anchor, random_donor["TEXT_SWAP"], "clean", 0, "TEXT_SWAP"))
        frames.append(row(anchor, random_donor["IMAGE_SWAP"], anchor, "clean", 0, "IMAGE_SWAP"))
        frames.append(row(random_donor["SIGNAL_SWAP"], anchor, anchor, "clean", 0, "SIGNAL_SWAP"))
        frames.append(row(anchor, anchor, hard, "clean", 0, "HARD_NEGATIVE_TEXT"))
        frames.append(row(anchor, random_donor["PARTIAL_MISMATCH"],
                          random_donor["PARTIAL_MISMATCH_B"], "clean", 0, "PARTIAL_MISMATCH"))

    df = pd.concat(frames, ignore_index=True)
    # A row whose donor could not be found is dropped, not emitted with a -1.
    incomplete = (df.signal_id < 0) | (df.image_id < 0) | (df.text_id < 0)
    df = df[~incomplete]
    df["neg_type"] = df["neg_type"].astype("string")
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
    }
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
