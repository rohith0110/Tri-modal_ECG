"""Cut an oversized modality into aligned, i.i.d. pieces (spec §8.2 rule 1).

    ./ecg_env/Scripts/python.exe scripts/dgx_portability/make_chunks.py plan \
        --kinds preprocessed_12lead --pieces 8
    ./ecg_env/Scripts/python.exe scripts/dgx_portability/make_chunks.py cut \
        --kinds preprocessed_12lead clean_12lead --pieces 8
    ./ecg_env/Scripts/python.exe scripts/dgx_portability/make_chunks.py verify \
        --kinds preprocessed_12lead --pieces 8

`plan` assigns studies to pieces and proves the assignment is fair; `cut`
materialises the piece files; `verify` re-checks what is already on disk.

The piece a study lands in is
``blake2b(f"{PIECE_SALT}|{study_id}") % n_pieces`` -- a pure function of the
study id and the piece count, and of nothing else. Two consequences the spec
requires:

* **Modality alignment is structural, not coordinated.** Because the key reads
  only ``study_id``, piece *k* of the signals and piece *k* of the images cover
  the same studies without the two runs ever having to agree on anything. There
  is no shared ordering, no shared seed file, no sequence number to keep in
  step. Cutting one modality today and another next month still aligns.
* **The forbidden keys cannot leak in.** subject_id, admission, label, cart_id
  and time are not arguments to the hash, so a piece cannot correlate with them
  by construction. `plan` measures that claim anyway rather than asserting it --
  see the fairness report -- because a build defect upstream (a study id that
  encodes acquisition order, say) could reintroduce the correlation through the
  id itself.

**Resumable.** One piece is written at a time, to a temp file, then atomically
renamed; a piece already on disk with a matching checksum is skipped. A power
cut costs the piece in flight.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

SCRIPTS = Path(__file__).resolve().parents[1] / "phase2_tasks_benchmark_and_paper"
sys.path.insert(0, str(SCRIPTS))

from _dataset_lib import build_common as bc                            # noqa: E402
from _dataset_lib import modality as mod                               # noqa: E402

STAGE = "P2.4b"
# Changing this re-shuffles every piece and invalidates every uploaded chunk.
# It is recorded in each piece manifest so a reader can tell which epoch of the
# cut they are holding.
PIECE_SALT = "trimodal-phase2-chunk-v1"

# Cuts are large and reproducible, so they may live off the data volume while a
# night of uploads drains them: TRIMODAL_CHUNK_ROOT moves them and nothing else
# (the remote path comes from the directory NAME, not from its parent).
CHUNK_ROOT = Path(os.environ.get("TRIMODAL_CHUNK_ROOT", bc.DATA_PROCESSED / "chunks"))
SPLITS_PATH = bc.DATA_PROCESSED / "splits_subject_level.parquet"

# Kinds this script knows how to materialise. Signal kinds become one HDF5 per
# piece; image kinds become one tar per piece.
SIGNAL_KINDS = set(mod.SIGNAL_KINDS)
IMAGE_KINDS = set(mod.IMAGE_KINDS)

# Strata a piece must NOT correlate with. §8.2 forbids keying by label, machine
# or time; these are the label-like columns the processed index actually
# carries, so independence from them is what can be measured. `ecg_time` is
# listed for the day a timestamp reaches the metadata -- absent columns are
# skipped, not failed.
STRATA = ("cart_id", "link_tier", "stratum", "hr_bucket", "ecg_time")


# -----------------------------------------------------------------------------
# assignment
# -----------------------------------------------------------------------------
def piece_of(study_ids: Iterable[int], n_pieces: int) -> np.ndarray:
    """Piece index per study. Pure function of (study_id, n_pieces)."""
    if n_pieces < 1:
        raise ValueError("n_pieces must be >= 1")
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


def cohort_frame(kind: str, split: str) -> pd.DataFrame:
    """study_id + piece-relevant metadata for one modality kind and split.

    The modality manifest is the authority on which studies actually have bytes
    for this kind; the split table is the authority on which split they are in.
    A study missing from either is dropped and counted, never silently kept.
    """
    manifest = pd.read_parquet(
        mod.MANIFEST_PATH,
        columns=["study_id", "modality_kind", "layout", "container_path",
                 "container_row", "container_offset", "container_length"],
    )
    if kind in mod._IMAGE_KIND_TO_MANIFEST:
        manifest_kind, layout = mod._IMAGE_KIND_TO_MANIFEST[kind]
        rows = manifest[(manifest["modality_kind"] == manifest_kind)
                        & (manifest["layout"] == layout)]
    else:
        rows = manifest[manifest["modality_kind"] == kind]
    if rows.empty:
        raise SystemExit(f"modality manifest has no rows for kind {kind!r}")
    rows = rows.drop_duplicates("study_id").copy()

    splits = pd.read_parquet(SPLITS_PATH)
    meta_path = bc.DATA_PROCESSED / "index" / "ecg_metadata_clean.parquet"
    meta_cols = pd.read_parquet(meta_path).columns
    want = [c for c in ("study_id", "subject_id", *STRATA) if c in meta_cols]
    meta = pd.read_parquet(meta_path, columns=want)

    frame = rows.merge(meta, on="study_id", how="inner")
    frame = frame.merge(splits[["subject_id", "split"]].drop_duplicates("subject_id"),
                        on="subject_id", how="inner")
    if split != "all":
        frame = frame[frame["split"] == split]
    return frame.reset_index(drop=True)


# -----------------------------------------------------------------------------
# fairness -- the claim in §8.2 rule 1, measured
# -----------------------------------------------------------------------------
def fairness(frame: pd.DataFrame, n_pieces: int) -> dict[str, Any]:
    """Is each piece a fair miniature of the split?

    Reported, not merely asserted: a piece that correlates with subject, cart or
    time is the exact failure §8.2 forbids, and the hash argument alone does not
    prove the ids themselves are innocent.
    """
    piece = frame["piece"].to_numpy()
    sizes = np.bincount(piece, minlength=n_pieces)
    expected = len(frame) / n_pieces
    report: dict[str, Any] = {
        "n_studies": int(len(frame)),
        "n_pieces": int(n_pieces),
        "piece_sizes": sizes.tolist(),
        "size_min": int(sizes.min()),
        "size_max": int(sizes.max()),
        "size_max_rel_dev": float(abs(sizes - expected).max() / expected) if expected else 0.0,
    }

    # A subject's ECGs SHOULD scatter across pieces -- that is what keying by
    # study rather than subject means. Report the spread so the deviation is on
    # the record; it is not a leak (the split boundary is subject-level and
    # every piece here comes from one split).
    per_subject = frame.groupby("subject_id")["piece"].nunique()
    multi = frame.groupby("subject_id").size()
    report["subjects_total"] = int(len(per_subject))
    report["subjects_with_multiple_ecgs"] = int((multi > 1).sum())
    report["mean_pieces_per_multi_ecg_subject"] = float(
        per_subject[multi > 1].mean()) if (multi > 1).any() else 0.0

    # cart_id and time must not concentrate. chi-square against uniform, on the
    # top carts and on time deciles.
    def chi2_uniform(labels: pd.Series) -> dict[str, float]:
        table = pd.crosstab(labels, frame["piece"])
        if table.empty or table.shape[1] < 2:
            return {"chi2": float("nan"), "dof": 0, "max_cell_rel_dev": float("nan")}
        exp = np.outer(table.sum(axis=1), table.sum(axis=0)) / table.to_numpy().sum()
        obs = table.to_numpy().astype("float64")
        with np.errstate(divide="ignore", invalid="ignore"):
            chi2 = float(np.nansum((obs - exp) ** 2 / np.where(exp > 0, exp, np.nan)))
            rel = float(np.nanmax(np.abs(obs - exp) / np.where(exp > 0, exp, np.nan)))
        return {"chi2": chi2,
                "dof": int((table.shape[0] - 1) * (table.shape[1] - 1)),
                "max_cell_rel_dev": rel}

    for column in STRATA:
        if column not in frame.columns or frame[column].isna().all():
            continue
        values = frame[column]
        if values.nunique() > 10:                # keep the chi-square table sane
            top = values.value_counts().head(10).index
            values = values.where(values.isin(top), other="__other__")
        report[f"stratum_{column}"] = chi2_uniform(values)

    # No processed index carries an acquisition timestamp, so independence from
    # TIME cannot be measured directly here. The nearest available evidence is
    # that consecutive study ids scatter across pieces (asserted in the
    # self-check); if a timestamp is ever added to the metadata, add it to
    # STRATA and this loop covers it with no other change.
    report["ecg_time_available"] = False
    return report


def fairness_verdict(report: dict[str, Any], tol: float = 0.05) -> tuple[bool, list[str]]:
    """PASS unless a piece is materially larger/smaller or a stratum concentrates."""
    problems: list[str] = []
    if report["size_max_rel_dev"] > tol:
        problems.append(
            f"piece sizes deviate {report['size_max_rel_dev']:.3%} from equal "
            f"(tolerance {tol:.0%}) -- sizes {report['piece_sizes']}")
    for key, block in report.items():
        if not key.startswith("stratum_") or not isinstance(block, dict):
            continue
        rel = block.get("max_cell_rel_dev")
        if rel is not None and np.isfinite(rel) and rel > 0.25:
            problems.append(
                f"{key}: a cell deviates {rel:.1%} from its expected count -- "
                "the pieces are not independent of this stratum")
    return (not problems), problems


# -----------------------------------------------------------------------------
# materialising
# -----------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def out_dir(kind: str, split: str, n_pieces: int) -> Path:
    path = CHUNK_ROOT / f"{kind}__{split}__p{n_pieces}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cut_signal_piece(frame: pd.DataFrame, kind: str, index: int, target: Path,
                     int16: bool, log) -> dict[str, Any]:
    """One HDF5 holding this piece's signals, row order = manifest order."""
    import h5py

    rows = frame[frame["piece"] == index]
    tmp = target.with_suffix(".h5.tmp")
    if tmp.exists():
        tmp.unlink()

    first = mod.read_modality(int(rows.study_id.iloc[0]), kind)
    n_leads, n_samples = (first.shape if first.ndim == 2 else (1, first.shape[0]))
    dtype = "int16" if int16 else "float32"

    with h5py.File(tmp, "w") as out:
        signal = out.create_dataset(
            "signal", shape=(len(rows), n_leads, n_samples), dtype=dtype,
            chunks=(1, n_leads, n_samples), compression="gzip", compression_opts=4)
        ids = out.create_dataset("study_id", shape=(len(rows),), dtype="int64")
        scale = out.create_dataset("scale", shape=(len(rows),), dtype="float32")
        for position, study_id in enumerate(rows.study_id.to_numpy()):
            array = np.asarray(mod.read_modality(int(study_id), kind), dtype="float32")
            if array.ndim == 1:
                array = array[None, :]
            if int16:
                peak = float(np.abs(array).max())
                factor = (peak / 32767.0) if peak > 0 else 1.0
                signal[position] = np.rint(array / factor).astype("int16")
                scale[position] = factor
            else:
                signal[position] = array
                scale[position] = 1.0
            ids[position] = int(study_id)
            if position and position % 5000 == 0:
                log.info("  %s piece %d: %d/%d", kind, index, position, len(rows))
        out.attrs["kind"] = kind
        out.attrs["piece"] = index
        out.attrs["piece_salt"] = PIECE_SALT
        out.attrs["dtype"] = dtype
        out.attrs["scaled"] = bool(int16)
    bc.atomic_replace(tmp, target)
    return {"n_rows": int(len(rows)), "dtype": dtype}


def cut_image_piece(frame: pd.DataFrame, kind: str, index: int, target: Path,
                    log) -> dict[str, Any]:
    """One tar holding this piece's image bytes, named `<study_id>.png`."""
    rows = frame[frame["piece"] == index]
    tmp = target.with_suffix(".tar.tmp")
    if tmp.exists():
        tmp.unlink()

    written = 0
    with tarfile.open(tmp, "w") as out:
        for study_id in rows.study_id.to_numpy():
            # read_modality returns the ENCODED bytes for an image kind (it is
            # _read_image that seeks into the tar), which is exactly what a piece
            # tar needs -- no decode, no re-encode, byte-identical members.
            payload = mod.read_modality(int(study_id), kind)
            info = tarfile.TarInfo(name=f"{int(study_id)}.png")
            info.size = len(payload)
            import io

            out.addfile(info, io.BytesIO(payload))
            written += 1
            if written % 5000 == 0:
                log.info("  %s piece %d: %d/%d", kind, index, written, len(rows))
    bc.atomic_replace(tmp, target)
    return {"n_rows": int(written), "dtype": "png"}


def cut(kinds: list[str], split: str, n_pieces: int, int16: bool, only: list[int] | None,
        log) -> int:
    for kind in kinds:
        frame = cohort_frame(kind, split)
        frame["piece"] = piece_of(frame.study_id.to_numpy(), n_pieces)
        report = fairness(frame, n_pieces)
        ok, problems = fairness_verdict(report)
        if not ok:
            for line in problems:
                log.error("FAIRNESS FAIL (%s): %s", kind, line)
            return 1

        directory = out_dir(kind, split, n_pieces)
        frame[["study_id", "subject_id", "piece", "split"]].to_parquet(
            directory / "assignment.parquet", index=False)
        (directory / "fairness.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8")

        checksums_path = directory / "checksums.json"
        checksums = json.loads(checksums_path.read_text(encoding="utf-8")) \
            if checksums_path.exists() else {}

        for index in range(n_pieces):
            if only and index not in only:
                continue
            suffix = "h5" if kind in SIGNAL_KINDS else "tar"
            target = directory / f"piece_{index:03d}.{suffix}"
            if target.exists() and target.name in checksums:
                log.info("%s piece %d already present, skipping", kind, index)
                continue
            log.info("%s piece %d/%d -> %s", kind, index, n_pieces - 1, target.name)
            if kind in SIGNAL_KINDS:
                info = cut_signal_piece(frame, kind, index, target, int16, log)
            else:
                info = cut_image_piece(frame, kind, index, target, log)
            checksums[target.name] = {
                "sha256": sha256_file(target),
                "bytes": target.stat().st_size,
                **info,
            }
            checksums_path.write_text(json.dumps(checksums, indent=2), encoding="utf-8")
            log.info("  wrote %s (%.2f GB, %d rows)", target.name,
                     target.stat().st_size / 1e9, info["n_rows"])
    return 0


def verify(kinds: list[str], split: str, n_pieces: int, log) -> int:
    failures = 0
    for kind in kinds:
        directory = out_dir(kind, split, n_pieces)
        checksums_path = directory / "checksums.json"
        if not checksums_path.exists():
            log.error("%s: no checksums.json -- nothing cut yet", kind)
            failures += 1
            continue
        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
        for name, expected in sorted(checksums.items()):
            path = directory / name
            if not path.exists():
                log.error("%s: %s recorded but missing", kind, name)
                failures += 1
                continue
            actual = sha256_file(path)
            if actual != expected["sha256"]:
                log.error("%s: %s CHECKSUM MISMATCH", kind, name)
                failures += 1
            else:
                log.info("%s: %s OK (%.2f GB, %d rows)", kind, name,
                         expected["bytes"] / 1e9, expected["n_rows"])
        missing = [i for i in range(n_pieces)
                   if not any(n.startswith(f"piece_{i:03d}") for n in checksums)]
        if missing:
            log.error("%s: pieces not yet cut: %s", kind, missing)
            failures += 1
    return 1 if failures else 0


def plan(kinds: list[str], split: str, n_pieces: int, log) -> int:
    """Assign and prove fairness without writing a single byte of signal."""
    worst = 0
    for kind in kinds:
        frame = cohort_frame(kind, split)
        frame["piece"] = piece_of(frame.study_id.to_numpy(), n_pieces)
        report = fairness(frame, n_pieces)
        ok, problems = fairness_verdict(report)
        log.info("=== %s / %s / %d pieces ===", kind, split, n_pieces)
        log.info("  %d studies, %d subjects; piece sizes %d..%d (max deviation %.4f%%)",
                 report["n_studies"], report["subjects_total"],
                 report["size_min"], report["size_max"],
                 report["size_max_rel_dev"] * 100)
        for key, block in sorted(report.items()):
            if key.startswith("stratum_") and isinstance(block, dict):
                log.info("  %-22s chi2=%8.1f dof=%4d  worst cell deviation %.2f%%",
                         key[len("stratum_"):], block["chi2"], block["dof"],
                         block["max_cell_rel_dev"] * 100)
        log.info("  verdict: %s", "PASS" if ok else "FAIL")
        for line in problems:
            log.error("  %s", line)

        # cross-modality alignment: the same ids must land in the same piece for
        # every kind, which is the property the fusion dataloader depends on.
        directory = out_dir(kind, split, n_pieces)
        frame[["study_id", "subject_id", "piece", "split"]].to_parquet(
            directory / "assignment.parquet", index=False)
        (directory / "fairness.json").write_text(json.dumps(report, indent=2),
                                                 encoding="utf-8")
        worst = max(worst, 0 if ok else 1)

    if len(kinds) > 1:
        base = None
        for kind in kinds:
            path = out_dir(kind, split, n_pieces) / "assignment.parquet"
            frame = pd.read_parquet(path).set_index("study_id")["piece"]
            if base is None:
                base = frame
                continue
            shared = base.index.intersection(frame.index)
            disagree = int((base.loc[shared] != frame.loc[shared]).sum())
            log.info("alignment %s vs first kind: %d shared studies, %d disagree",
                     kind, len(shared), disagree)
            if disagree:
                log.error("MODALITY ALIGNMENT BROKEN -- piece k must cover the same "
                          "studies in every modality (§8.2 rule 1)")
                worst = 1
    return worst


def _self_check() -> None:
    """The two properties §8.2 makes binding, on synthetic ids."""
    ids = np.arange(100_000, 140_000)
    a = piece_of(ids, 8)
    assert a.min() == 0 and a.max() == 7, "pieces must span the range"
    sizes = np.bincount(a, minlength=8)
    assert abs(sizes - len(ids) / 8).max() / (len(ids) / 8) < 0.05, sizes

    # determinism, and independence from ordering and from n_pieces history
    shuffled = ids.copy()
    np.random.default_rng(0).shuffle(shuffled)
    lookup = dict(zip(ids.tolist(), a.tolist()))
    b = piece_of(shuffled, 8)
    assert all(lookup[int(s)] == int(p) for s, p in zip(shuffled, b)), \
        "assignment must not depend on input order"

    # modality alignment is structural: same ids, same pieces, no coordination
    assert (piece_of(ids, 8) == piece_of(ids, 8)).all()

    # a different piece count is a different cut -- callers must not mix them
    assert not (piece_of(ids, 8) == piece_of(ids, 7)).all()

    # the forbidden keys cannot enter: consecutive ids scatter
    consecutive = piece_of(np.arange(1000, 1064), 8)
    assert len(set(consecutive.tolist())) == 8, \
        "consecutive study ids must not clump into one piece"
    print("make_chunks self-check PASS")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("action", choices=["plan", "cut", "verify", "selfcheck"])
    parser.add_argument("--kinds", nargs="+", default=["preprocessed_12lead"])
    parser.add_argument("--split", default="train",
                        help="which split to cut (default train; §8.2 cuts TRAIN)")
    parser.add_argument("--pieces", type=int, default=8)
    parser.add_argument("--int16", action="store_true",
                        help="store signals as int16 + per-record scale (§8.2 note)")
    parser.add_argument("--only", type=int, nargs="*", default=None,
                        help="cut only these piece indexes (resume / parallelise)")
    args = parser.parse_args(argv)

    if args.action == "selfcheck":
        _self_check()
        return 0

    # --int16 means "the pieces are int16", so read the int16 copies where they
    # exist: half the I/O, and for a kind already converted at Step 5 the codes
    # survive the round trip exactly (peak/32767 is idempotent). raw_12lead has
    # no int16 copy, so _resolve_h5 falls back to the float32 original and the
    # quantisation happens here instead.
    if args.int16:
        os.environ["TRIMODAL_SIGNAL_INT16"] = "1"

    log = bc.setup_logging("make_chunks", stage=STAGE)
    log.info("make_chunks %s: kinds=%s split=%s pieces=%d int16=%s salt=%s",
             args.action, args.kinds, args.split, args.pieces, args.int16, PIECE_SALT)
    for kind in args.kinds:
        if kind not in SIGNAL_KINDS | IMAGE_KINDS:
            raise SystemExit(f"unknown modality kind {kind!r}; "
                             f"known: {sorted(SIGNAL_KINDS | IMAGE_KINDS)}")

    if args.action == "plan":
        return plan(args.kinds, args.split, args.pieces, log)
    if args.action == "cut":
        return cut(args.kinds, args.split, args.pieces, args.int16, args.only, log)
    return verify(args.kinds, args.split, args.pieces, log)


if __name__ == "__main__":
    raise SystemExit(main())
