"""Read the chunk pieces `make_chunks.py` cuts, and say which studies are resident.

Spec §8.2 rule 1 cuts an oversized TRAIN split into 8 aligned i.i.d. pieces;
rule 2 says the training loop cycles through them **within** each epoch, two
resident at a time. This module is the read half. The loop half -- when a piece
arrives and when it leaves -- lives in `_train_lib/trainer.py`, because that is
where the epoch is, and staging is a transport call, not a dataset concern.

Nothing here changes a non-chunked run: with no piece directories staged,
`resident()` returns an empty plan and every caller behaves exactly as before.

**A piece needs no new reader.** It already carries `study_id` per row, so the
manifest-overlay mechanism `modality.py` grew for the derived subsets covers it
too: `install_overlays()` writes one overlay parquet per staged piece set and
`read_modality()` then resolves those studies to the piece file. The rest of the
pipeline -- trainer, evaluator, baselines -- is untouched.

**Alignment is checked, not assumed.** Campaign 8 chunks signals *and* images,
and a batch whose signal is in piece 3 but whose image is in piece 5 would stall
on a modality that is not staged. `piece_of()` is a pure function of study_id,
so the two cutters agree by construction; `check_alignment()` measures it anyway
against the assignment tables actually on disk, because a cut made with a
different `--pieces` count would silently break the property.
"""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from . import modality as mod

DATA_PROCESSED = mod.DATA_PROCESSED
OVERLAY_DIR = mod.OVERLAY_DIR

# Must match make_chunks.PIECE_SALT. Changing either invalidates every cut.
PIECE_SALT = "trimodal-phase2-chunk-v1"

# stage_data.sh unpacks chunks/<base>/piece_NNN.* into $DATA_ROOT/<base>/, and
# these are the three bases the campaign table names.
BASE_TO_KIND = {
    "signals_12lead": "preprocessed_12lead",
    "images_clean_12lead": "image_clean_12lead",
    "signals_raw": "raw_12lead",
}


def piece_of(study_ids: Iterable[int], n_pieces: int) -> np.ndarray:
    """Piece index per study -- the same pure function `make_chunks.py` cuts by."""
    return np.array(
        [
            int.from_bytes(
                hashlib.blake2b(f"{PIECE_SALT}|{int(s)}".encode(), digest_size=8).digest(),
                "big",
            )
            % n_pieces
            for s in study_ids
        ],
        dtype="int32",
    )


def enabled() -> bool:
    """Chunk cycling is on when the campaign body says so (§8.2 rule 2)."""
    return os.environ.get("TRIMODAL_CHUNKED", "") not in ("", "0", "false", "False")


def n_pieces() -> int:
    return int(os.environ.get("TRIMODAL_CHUNK_PIECES", "8"))


def staged_bases() -> dict[str, Path]:
    """The piece directories actually present under data/processed, by base name."""
    found: dict[str, Path] = {}
    for base in BASE_TO_KIND:
        directory = DATA_PROCESSED / base
        if directory.is_dir() and any(directory.glob("piece_*")):
            found[base] = directory
    return found


def resident(base: str) -> list[int]:
    """Which piece indexes of one base are on disk right now."""
    directory = DATA_PROCESSED / base
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("piece_*")):
        stem = path.name.split(".")[0]                 # piece_003.h5 -> piece_003
        try:
            out.append(int(stem.split("_")[1]))
        except (IndexError, ValueError):
            continue
    return sorted(set(out))


# -----------------------------------------------------------------------------
# making a piece readable -- one overlay per staged piece set
# -----------------------------------------------------------------------------
def _signal_piece_rows(path: Path, base: str) -> pd.DataFrame:
    import h5py

    with h5py.File(path, "r") as handle:
        study_ids = np.asarray(handle["study_id"][:], dtype="int64")
    return pd.DataFrame({
        "study_id": study_ids,
        "container_path": f"{base}/{path.name}",
        "container_row": np.arange(len(study_ids), dtype="int64"),
        "container_offset": 0,
        "container_length": 0,
    })


def _image_piece_rows(path: Path, base: str) -> pd.DataFrame:
    """Index a piece tar by scanning its headers once.

    The cutter writes members named `<study_id>.png` but records no offsets, and
    a tar is a linked list of headers -- one pass reads only the headers, not the
    payloads, so this costs a seek per member rather than the file's bytes. The
    result is cached beside the piece so the next worker does not repeat it.
    """
    cache = path.with_suffix(".index.parquet")
    if cache.exists():
        return pd.read_parquet(cache)
    rows = []
    with tarfile.open(path, "r") as archive:
        for member in archive:
            if not member.isfile():
                continue
            stem = Path(member.name).stem
            if not stem.isdigit():
                continue
            rows.append((int(stem), int(member.offset), int(member.size)))
    frame = pd.DataFrame(rows, columns=["study_id", "container_offset", "container_length"])
    frame["container_path"] = f"{base}/{path.name}"
    frame["container_row"] = 0
    try:
        frame.to_parquet(cache, index=False)
    except OSError:                                    # read-only staging dir
        pass
    return frame


def install_overlays(log=None) -> dict[str, list[int]]:
    """Point `read_modality()` at every staged piece. Returns base -> resident pieces."""
    plan: dict[str, list[int]] = {}
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    subjects = pd.read_parquet(DATA_PROCESSED / "index" / "ecg_metadata_clean.parquet",
                               columns=["study_id", "subject_id"])
    for base, directory in staged_bases().items():
        kind = BASE_TO_KIND[base]
        manifest_kind, layout = mod._IMAGE_KIND_TO_MANIFEST.get(kind, (kind, None))
        frames = []
        for path in sorted(directory.glob("piece_*")):
            if path.suffix == ".h5":
                frames.append(_signal_piece_rows(path, base))
            elif path.suffix == ".tar":
                frames.append(_image_piece_rows(path, base))
        if not frames:
            continue
        overlay = pd.concat(frames, ignore_index=True)
        overlay["modality_kind"] = manifest_kind
        overlay["layout"] = layout
        overlay = overlay.merge(subjects, on="study_id", how="left")
        overlay = overlay[["study_id", "subject_id", "modality_kind", "layout",
                           "container_path", "container_row",
                           "container_offset", "container_length"]]
        overlay.to_parquet(OVERLAY_DIR / f"pieces_{base}.parquet", index=False)
        plan[base] = resident(base)
        if log:
            log.info("chunk pieces: %s resident=%s, %d studies readable",
                     base, plan[base], len(overlay))
    mod._INDEX.clear()                 # the overlay changed; drop cached indexes
    mod.close_handles()
    return plan


def drop_overlay(base: str) -> None:
    """Forget a piece set that has been evicted, so a stale row cannot be read."""
    path = OVERLAY_DIR / f"pieces_{base}.parquet"
    path.unlink(missing_ok=True)
    mod._INDEX.clear()
    mod.close_handles()


# -----------------------------------------------------------------------------
# alignment -- §8.2 rule 1's cross-modality guarantee, measured
# -----------------------------------------------------------------------------
def check_alignment(bases: Iterable[str] | None = None) -> tuple[bool, str]:
    """Does every shared study land in the same piece index in every base?"""
    bases = list(bases or staged_bases())
    tables = {}
    for base in bases:
        path = DATA_PROCESSED / base / "assignment.parquet"
        if path.exists():
            tables[base] = pd.read_parquet(path).set_index("study_id")["piece"]
    if len(tables) < 2:
        return True, f"only {len(tables)} assignment table(s) staged -- nothing to compare"
    names = list(tables)
    first = tables[names[0]]
    for other in names[1:]:
        shared = first.index.intersection(tables[other].index)
        disagree = int((first.loc[shared] != tables[other].loc[shared]).sum())
        if disagree:
            return False, (f"{names[0]} vs {other}: {disagree} of {len(shared)} shared studies "
                           f"land in different pieces -- the cuts are NOT aligned (§8.2 rule 1)")
    return True, f"{len(names)} bases aligned over {len(first)} studies"


def rows_for_pieces(study_ids: np.ndarray, pieces: Iterable[int],
                    total_pieces: int | None = None) -> np.ndarray:
    """Row positions whose study belongs to one of these piece indexes."""
    assignment = piece_of(study_ids, total_pieces or n_pieces())
    wanted = np.asarray(sorted(set(int(p) for p in pieces)), dtype="int32")
    return np.flatnonzero(np.isin(assignment, wanted))


def _self_check() -> None:
    """The two properties the cycling depends on, on synthetic ids."""
    ids = np.arange(200_000, 240_000)

    # 1. every study belongs to exactly one piece, and the pieces are even
    assignment = piece_of(ids, 8)
    sizes = np.bincount(assignment, minlength=8)
    assert sizes.sum() == len(ids)
    assert abs(sizes - len(ids) / 8).max() / (len(ids) / 8) < 0.05, sizes

    # 2. alignment is structural: the same ids, cut for a different modality with
    #    no coordination, land in the same pieces
    assert (piece_of(ids, 8) == piece_of(ids, 8)).all()

    # 3. rows_for_pieces selects exactly the resident studies, and a full sweep
    #    over all pieces visits every row exactly once
    seen = np.concatenate([rows_for_pieces(ids, [p], 8) for p in range(8)])
    assert np.array_equal(np.sort(seen), np.arange(len(ids))), \
        "a sweep over every piece must visit every row exactly once"
    window = rows_for_pieces(ids, [2, 5], 8)
    assert set(assignment[window].tolist()) == {2, 5}
    print("chunk_pieces self-check PASS")


if __name__ == "__main__":
    _self_check()
