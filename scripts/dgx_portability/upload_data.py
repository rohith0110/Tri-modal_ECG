"""Push one campaign's data to R2, in exactly the layout `stage_data.sh` reads back.

    ./ecg_env/Scripts/python.exe scripts/dgx_portability/upload_data.py --campaign 1 --dry-run
    ./ecg_env/Scripts/python.exe scripts/dgx_portability/upload_data.py --campaign 1
    ./ecg_env/Scripts/python.exe scripts/dgx_portability/upload_data.py --dataset signals_lead2
    ./ecg_env/Scripts/python.exe scripts/dgx_portability/upload_data.py --all --dry-run

`stage_data.sh` is the only reader, so it defines the layout:

    plain dataset      r2:trimodal-data/<dataset>/<path relative to data/processed>
    chunked dataset    r2:trimodal-data/chunks/<base>/piece_NNN.h5  (or .tar)
                       r2:trimodal-data/chunks/<base>/checksums.json
                       r2:trimodal-data/chunks/<base>/assignment.parquet

The paths inside a plain dataset are **relative to `data/processed`** (or to the
repo root for `code` / `configs`), because the stager unpacks a dataset into
`$DATA_ROOT`, and `_campaign_body.sh` symlinks `$DATA_ROOT` to
`$PROJECT_ROOT/data/processed` -- which is the one path `modality.py` and
`build_common.py` resolve everything under. So the int16 Lead-II copy has to
land at `signals_int16/lead2_preprocessed.h5` and not at
`signals_lead2/lead2_preprocessed.h5`, or campaign 4 fails at the first read.

**Every uploaded directory gets a `checksums_<dataset>.json`** in the format
`stage_data.sh`'s inline verifier expects -- `{"<filename>": {"sha256": ...}}`.
One file per dataset rather than a single `checksums.json`, because two datasets
can land in the same directory (`text` and `index` both write into `index/`) and
the second would otherwise overwrite the first's manifest and quietly verify
nothing.

**Resumable.** The remote layout is materialised as a tree of hard links under
`outputs/upload_stage/` (no bytes copied -- same volume), then pushed with
`rclone copy --checksum`, which skips what already matches. Re-running the same
command after an interrupted night costs one listing, not one upload. sha256
digests are cached in `outputs/upload_checksums.json` keyed by path+size+mtime,
so a resumed run does not re-hash 160 GB either.

**What may never be uploaded** is enforced, not assumed (`_refuse_forbidden`):
raw MIMIC, the EHR cache, the linkage tables and `structured_features.parquet`
are refused by path, and every task parquet is checked to carry no binary
column -- task tables ship study ids and labels, never signal or image bytes.
The bucket is private; nothing here ever enables public access or an r2.dev URL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data" / "processed"
# Hard links must land on the same volume as the data; TRIMODAL_UPLOAD_STAGE
# moves the tree when a cut lives elsewhere (TRIMODAL_CHUNK_ROOT).
STAGE_ROOT = Path(os.environ.get("TRIMODAL_UPLOAD_STAGE", REPO / "outputs" / "upload_stage"))
DIGEST_CACHE = REPO / "outputs" / "upload_checksums.json"
CAMPAIGNS_SH = Path(__file__).resolve().parent / "campaigns.sh"
REMOTE = os.environ.get("R2_DATA", "r2:trimodal-data")

# --- what each dataset name in campaigns.sh actually is ----------------------
# `root` is what the paths are relative to, and therefore where the stager must
# unpack them: DATA for anything read through data/processed, REPO for the code
# and the configs. Globs are expanded; a missing path is an error, not a skip.
DATASETS: dict[str, dict] = {
    "code": {"root": REPO, "paths": [
        "scripts/phase2_tasks_benchmark_and_paper", "scripts/dgx_portability",
        "AGENTS.md", "CLAUDE.md"]},
    "configs": {"root": REPO, "paths": ["config"]},
    "tasks": {"root": DATA, "paths": ["tasks"]},
    "index": {"root": DATA, "paths": [
        "index/ecg_metadata_clean.parquet", "index/splits.json",
        "modality_manifest.parquet", "splits_subject_level.parquet",
        "signal_metadata.parquet", "qc.parquet", "waveform_qc.parquet"]},
    # T_machine, the report text, lives in the measurements index; it is its own
    # dataset because only the text-reading campaigns need to pay for it.
    "text": {"root": DATA, "paths": ["index/ecg_metadata_clean_with_measurements.parquet"]},
    "fiducials": {"root": DATA, "paths": ["fiducials_lead2.parquet"]},
    # Lead-II: the preprocessed copy is int16 (Step 5), the raw one has no int16
    # copy, and `_resolve_h5` falls back to the float32 original when the int16
    # one is absent -- so both land where the manifest already points.
    "signals_lead2": {"root": DATA, "paths": [
        "signals_int16/lead2_preprocessed.h5", "signals/lead2_raw.h5"]},
    # The same two files, separately. Campaigns 12/13/14 read only the
    # preprocessed copy and were staging the 6.08 GB raw one for nothing; only
    # campaign 4 has `*_lead2_raw` configs. Remote keys are `<dataset>/<path>`,
    # so these are NEW prefixes: splitting them re-uploaded both files (12.6 GB,
    # 2026-09-30) and left `signals_lead2/` unused. The files live on D:, so
    # TRIMODAL_UPLOAD_STAGE must be on D: too (a hard link cannot cross volumes).
    "signals_lead2_preprocessed": {"root": DATA, "paths": [
        "signals_int16/lead2_preprocessed.h5"]},
    "signals_lead2_raw": {"root": DATA, "paths": [
        "signals/lead2_raw.h5"]},
    "signals_corrupted": {"root": DATA, "paths": ["signals_corrupted.parquet"]},
    "images_clean_12lead": {"root": DATA, "paths": ["images/clean_12lead_shard_*.tar"]},
    "images_clean_lead2": {"root": DATA, "paths": ["images/clean_lead2_shard_*.tar"]},
    # The three derived datasets (make_subsets.py): containers plus the manifest
    # overlay that tells modality.py to read them instead of the base files.
    "signals_12lead_L3": {"root": DATA, "paths": [
        "derived/signals_12lead_L3/*.h5",
        "derived/signals_12lead_L3/*__rows.parquet",
        "manifest_overlays/signals_12lead_L3.parquet"]},
    "images_clean_12lead_L3": {"root": DATA, "paths": [
        "derived/images_clean_12lead_L3/*.tar",
        "derived/images_clean_12lead_L3/*__rows.parquet",
        "manifest_overlays/images_clean_12lead_L3.parquet"]},
    "images_scanlike_test": {"root": DATA, "paths": [
        "derived/images_scanlike_test/*.tar",
        "derived/images_scanlike_test/*__rows.parquet",
        "manifest_overlays/images_scanlike_test.parquet"]},
    # val/test for the chunked campaigns 6, 8 and 9 (open question 15b). The
    # `__<split>.` in each filename is what stage_data.sh --phase filters on.
    "signals_12lead_valtest": {"root": DATA, "paths": [
        "derived/signals_12lead_valtest/*.h5",
        "derived/signals_12lead_valtest/*__rows.parquet",
        "manifest_overlays/signals_12lead_valtest.parquet"]},
    "images_clean_12lead_valtest": {"root": DATA, "paths": [
        "derived/images_clean_12lead_valtest/*.tar",
        "derived/images_clean_12lead_valtest/*__rows.parquet",
        "manifest_overlays/images_clean_12lead_valtest.parquet"]},
    "signals_raw_valtest": {"root": DATA, "paths": [
        "derived/signals_raw_valtest/*.h5",
        "derived/signals_raw_valtest/*__rows.parquet",
        "manifest_overlays/signals_raw_valtest.parquet"]},
    # val/test for the A5/B4 scan-like reads (open question 16). Per layout, so
    # a 12-lead campaign does not stage Lead-II bytes it never opens; the
    # scan-like TRAIN split is chunked, not shipped whole.
    "images_scanlike_12lead_valtest": {"root": DATA, "paths": [
        "derived/images_scanlike_12lead_valtest/*.tar",
        "derived/images_scanlike_12lead_valtest/*__rows.parquet",
        "manifest_overlays/images_scanlike_12lead_valtest.parquet"]},
    "images_scanlike_lead2_valtest": {"root": DATA, "paths": [
        "derived/images_scanlike_lead2_valtest/*.tar",
        "derived/images_scanlike_lead2_valtest/*__rows.parquet",
        "manifest_overlays/images_scanlike_lead2_valtest.parquet"]},
    # Campaigns 13/14 chunk the clean Lead-II images too: held whole it is
    # 19.15 GB, which left them 2.3 GB of margin once the scan-like pieces were
    # added. Campaigns 3 and 12 keep the whole container, because their
    # A1/A3/A6 runs must not start chunk-cycling.
    "images_clean_lead2_valtest": {"root": DATA, "paths": [
        "derived/images_clean_lead2_valtest/*.tar",
        "derived/images_clean_lead2_valtest/*__rows.parquet",
        "manifest_overlays/images_clean_lead2_valtest.parquet"]},
}

# --- chunked datasets: local cut directory -> the remote base name -----------
# campaigns.sh names these `<base>_pieces`; stage_data.sh reads them back from
# chunks/<base>/. The local directory is what make_chunks.py wrote.
CHUNK_ROOT = Path(os.environ.get("TRIMODAL_CHUNK_ROOT", DATA / "chunks"))
# Where `derived/` actually lives; see TRIMODAL_DERIVED_BASE in make_subsets.py.
DERIVED_BASE = Path(os.environ.get("TRIMODAL_DERIVED_BASE", DATA))
# A file that cannot be hard-linked into the staging tree (different volume) is
# copied instead, up to this size. Overlays and manifests are a few MB; a
# container is tens of GB and copying one would be a silent waste of a disk.
LINK_FALLBACK_MAX_BYTES = 2 * 1024**3

CHUNKS: dict[str, str] = {
    "signals_12lead": "preprocessed_12lead__train__p8",
    "images_clean_12lead": "image_clean_12lead__train__p8",
    "signals_raw": "raw_12lead__train__p8",
    # Open question 16. Cut at p8 like the three above, and `make_chunks.py plan`
    # confirms 0 studies disagree with any of them -- the assignment is
    # `blake2b(salt|study_id) % 8`, so piece k covers the same studies in every
    # kind without the cuts ever coordinating. That is what lets a fusion batch
    # read signal, clean image and scan-like image from one resident window.
    "images_scanlike_12lead": "image_scanlike_12lead__train__p8",
    "images_scanlike_lead2": "image_scanlike_lead2__train__p8",
    "images_clean_lead2": "image_clean_lead2__train__p8",
}

# --- never, under any flag ---------------------------------------------------
FORBIDDEN = (
    re.compile(r"(^|[\\/])data[\\/]raw([\\/]|$)"),
    re.compile(r"ehr_cache"),
    re.compile(r"(^|[\\/])linkage([\\/]|$)"),
    re.compile(r"structured_features\.parquet$"),
    re.compile(r"rclone\.conf$|\.env$|\.pem$|\.key$|credentials"),
)


def _refuse_forbidden(paths: list[Path]) -> None:
    """Raw MIMIC never leaves the laptop; nor do credentials or the EHR cache."""
    for path in paths:
        text = str(path)
        for pattern in FORBIDDEN:
            if pattern.search(text):
                raise SystemExit(f"REFUSING to upload {path}: matches {pattern.pattern}")


def audit_task_tables() -> list[str]:
    """Task parquets carry study ids and labels -- never signal or image bytes."""
    import pyarrow.parquet as pq

    problems = []
    for path in sorted((DATA / "tasks").rglob("*.parquet")):
        schema = pq.ParquetFile(path).schema_arrow
        for field in schema:
            if "binary" in str(field.type) or str(field.type).startswith("fixed_size_binary"):
                problems.append(f"{path.relative_to(DATA)}: column {field.name} is {field.type}")
    return problems


# --- digests -----------------------------------------------------------------
def _load_cache() -> dict:
    if DIGEST_CACHE.exists():
        return json.loads(DIGEST_CACHE.read_text(encoding="utf-8"))
    return {}


def sha256_file(path: Path, cache: dict) -> str:
    stat = path.stat()
    key = f"{path}|{stat.st_size}|{int(stat.st_mtime)}"
    if key in cache:
        return cache[key]
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    cache[key] = digest.hexdigest()
    DIGEST_CACHE.parent.mkdir(parents=True, exist_ok=True)
    DIGEST_CACHE.write_text(json.dumps(cache, indent=0), encoding="utf-8")
    return cache[key]


_BUILDER_MANIFESTS: dict[Path, dict] = {}


def _cross_check(source: Path, digest: str) -> None:
    """Refuse a file that no longer matches the digest its builder recorded.

    `make_subsets.py` and `make_chunks.py` both write a `checksums.json` beside
    what they produce, at the moment they produce it. Comparing against it here
    costs nothing (the hash is computed for the upload manifest anyway) and
    catches a truncated or half-written file -- a power cut mid-write is a
    hazard this project has already met once -- before it reaches R2 and
    becomes the thing the DGX trains on.
    """
    manifest_path = source.parent / "checksums.json"
    if manifest_path not in _BUILDER_MANIFESTS:
        _BUILDER_MANIFESTS[manifest_path] = json.loads(
            manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    recorded = _BUILDER_MANIFESTS[manifest_path].get(source.name)
    if recorded and recorded.get("sha256") and recorded["sha256"] != digest:
        raise SystemExit(
            f"REFUSING to upload {source}: sha256 {digest[:12]} does not match the "
            f"{recorded['sha256'][:12]} its builder recorded in {manifest_path}. "
            f"Rebuild that file before uploading it.")


# --- resolving a dataset to (local file, remote key) pairs -------------------
def dataset_files(dataset: str) -> list[tuple[Path, str]]:
    if dataset.endswith("_pieces"):
        base = dataset[: -len("_pieces")]
        if base not in CHUNKS:
            raise SystemExit(f"unknown chunked dataset {dataset!r}")
        directory = CHUNK_ROOT / CHUNKS[base]
        if not directory.is_dir():
            raise SystemExit(
                f"{directory} does not exist -- cut it first:\n"
                f"  make_chunks.py cut --kinds {CHUNKS[base].split('__')[0]} --pieces 8")
        # A piece counts as cut only once make_chunks.py has recorded it in
        # checksums.json, which it does after the atomic rename -- so a
        # `piece_NNN.h5.tmp` still being written by a running cut is never
        # picked up, and neither is a piece whose write died before the rename.
        recorded = json.loads((directory / "checksums.json").read_text(encoding="utf-8")) \
            if (directory / "checksums.json").exists() else {}
        pieces = sorted(p for p in directory.iterdir()
                        if p.name in recorded
                        or p.name in ("checksums.json", "assignment.parquet",
                                      "fairness.json"))
        if not any(p.name.startswith("piece_") for p in pieces):
            raise SystemExit(f"{directory} holds only the plan -- no piece files cut yet")
        return [(p, f"chunks/{base}/{p.name}") for p in pieces]

    if dataset not in DATASETS:
        raise SystemExit(f"unknown dataset {dataset!r}; known: {sorted(DATASETS)}")
    spec = DATASETS[dataset]
    root: Path = spec["root"]
    out: list[tuple[Path, str]] = []
    for pattern in spec["paths"]:
        root = DERIVED_BASE if pattern.startswith("derived/") else spec["root"]
        matches = sorted(root.glob(pattern)) if any(c in pattern for c in "*?[") \
            else [root / pattern]
        if not matches:
            raise SystemExit(f"{dataset}: nothing matches {pattern!r} under {root}")
        for match in matches:
            if match.is_dir():
                for path in sorted(match.rglob("*")):
                    if path.is_file() and "__pycache__" not in path.parts:
                        out.append((path, f"{dataset}/{path.relative_to(root).as_posix()}"))
            elif match.is_file():
                out.append((match, f"{dataset}/{match.relative_to(root).as_posix()}"))
            else:
                raise SystemExit(f"{dataset}: {match} does not exist")
    return out


def campaign_datasets(campaign: int) -> list[str]:
    """The dataset list for one campaign, read out of campaigns.sh (one source)."""
    text = CAMPAIGNS_SH.read_text(encoding="utf-8")
    match = re.search(rf'^\s*{campaign}\)\s+echo "([^"]+)"', text, re.M)
    if not match:
        raise SystemExit(f"campaigns.sh has no campaign {campaign}")
    # name|resident_gb|runs|gpu_hours|chunked|datasets|eval_gb -- field 6 by
    # index, not "the last one": a seventh field (the eval-phase size) was added
    # for open question 15b and `[-1]` silently started returning that instead.
    return match.group(1).split("|")[5].split()


# --- staging + push ----------------------------------------------------------
def stage(pairs: list[tuple[Path, str]], dataset: str, cache: dict,
          checksums: bool = True) -> Path:
    """Materialise the remote layout locally as hard links, plus its manifest."""
    root = STAGE_ROOT / dataset.replace("/", "_")
    by_directory: dict[str, dict[str, dict]] = {}
    for source, key in pairs:
        target = root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.stat().st_ino != source.stat().st_ino or \
                    target.stat().st_size != source.stat().st_size:
                target.unlink()
        if not target.exists():
            try:
                os.link(source, target)
            except OSError as error:                  # different volume, or no perm
                # One dataset can legitimately straddle two volumes: the big
                # containers were built onto C: for space while the manifest
                # overlay stayed beside the data on D:. A hard link cannot cross
                # a volume, so copy the small file rather than refusing the whole
                # dataset -- which is what silently cost images_clean_12lead_valtest
                # an upload, because the failure came after the "N files" line.
                if source.stat().st_size > LINK_FALLBACK_MAX_BYTES:
                    raise SystemExit(
                        f"cannot hard-link {source} -> {target} ({error}) and it is too "
                        f"large to copy ({source.stat().st_size / 2**30:.1f} GiB). Put the "
                        f"staging tree on the same volume as this file: "
                        f"TRIMODAL_UPLOAD_STAGE=<dir on that volume>.") from error
                shutil.copy2(source, target)
        digest = sha256_file(source, cache) if checksums else ""
        if digest:
            _cross_check(source, digest)
        remote_dir = str(Path(key).parent.as_posix())
        by_directory.setdefault(remote_dir, {})[Path(key).name] = {
            "sha256": digest,
            "bytes": source.stat().st_size,
        }

    if checksums:
        for remote_dir, entries in by_directory.items():
            # A chunked cut already ships make_chunks.py's own checksums.json in
            # exactly this format; do not shadow it with a second manifest.
            if remote_dir.startswith("chunks/"):
                continue
            (root / remote_dir).mkdir(parents=True, exist_ok=True)
            (root / remote_dir / f"checksums_{dataset}.json").write_text(
                json.dumps(entries, indent=2), encoding="utf-8")
    return root


def push(root: Path, dry_run: bool) -> int:
    """rclone copy, tuned so a single huge file can still fill the link.

    `--transfers` only parallelises across FILES, and the datasets that dominate
    this upload are one or three enormous ones (`signals_12lead_L3__train.h5` is
    30.9 GB, a scan-like tar is 20.3 GB), so it does nothing for them. What does
    is `--s3-upload-concurrency`: the number of multipart chunks of ONE file in
    flight at once. Default 4 x 5 MiB = 20 MiB outstanding, which cannot saturate
    a fast link over a long round trip; 12 x 32 MiB = 384 MiB can.

    Peak memory is roughly transfers x upload-concurrency x chunk-size (here
    ~1.5 GB worst case, against 9 GB free). Turn any of them down on a smaller
    machine -- each is an env var, and rclone reads its own `RCLONE_*` vars too.
    """
    transfers = os.environ.get("TRIMODAL_RCLONE_TRANSFERS", "4")
    concurrency = os.environ.get("TRIMODAL_RCLONE_UPLOAD_CONCURRENCY", "12")
    chunk = os.environ.get("TRIMODAL_RCLONE_CHUNK_SIZE", "32M")
    command = ["rclone", "copy", str(root), REMOTE, "--checksum",
               "--transfers", transfers,
               "--s3-upload-concurrency", concurrency,
               "--s3-chunk-size", chunk,
               # rclone logs stats at INFO, which the default NOTICE level hides,
               # so without this the log shows the command and then nothing for
               # the twenty minutes a 20 GB tar takes. `rclone size` is no
               # substitute: a multipart object does not appear in the bucket
               # until its last part lands.
               "--stats", "30s", "--stats-one-line", "--stats-log-level", "NOTICE"]
    if dry_run:
        command.append("--dry-run")
    print("+ " + " ".join(command), flush=True)
    return subprocess.call(command)


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:,.2f} {unit}"
        n /= 1024
    return ""


# --- what a campaign actually costs on the node -----------------------------
# §8.2 rule 2 keeps two pieces resident at a time. A chunked dataset therefore
# costs two pieces, not all eight -- and during the EVAL phase it costs nothing,
# because `_campaign_body.sh` runs `evict_data.sh --pieces-all` before it
# evaluates.
RESIDENT_PIECES = 2


def n_campaigns() -> int:
    """How many campaigns campaigns.sh declares -- read, never restated here."""
    match = re.search(r'^N_CAMPAIGNS=(\d+)', CAMPAIGNS_SH.read_text(encoding="utf-8"), re.M)
    if not match:
        raise SystemExit("campaigns.sh does not declare N_CAMPAIGNS")
    return int(match.group(1))

# Fixed cost on the DGX, outside any dataset: the 5.7 GB `ecg_env` venv plus the
# HuggingFace cache (pinned inside PROJECT_ROOT so `used_gb` sees it). MEASURED
# 2026-09-30 from job 24639, which reported 19.0 GB used while holding campaign
# 2's 9.4 GB of data and 2.4 GB of `c2test` outputs. Checkpoints are counted
# separately because the table is budgeted to survive them.
FIXED_GB = 7.2
CHECKPOINTS_GB = 5.0
CEILING_GB = 99.0          # campaigns.sh QUOTA_CEILING_GB; 49 -> 99 on 2026-10-14


def _keep(name: str, phase: str) -> bool:
    """Does `stage_data.sh --phase <phase>` take this file? See phase_excludes."""
    if phase == "eval":
        return not ("__train." in name or "__val." in name)
    if phase == "val":
        return not ("__train." in name or "__test." in name)
    if phase == "train_only":
        return not ("__val." in name or "__test." in name)
    return "__test." not in name                          # phase == "train"


def _recorded_sizes(dataset: str) -> dict[str, int] | None:
    """A cut's sizes from its own `checksums.json` when the pieces are not here.

    The local copy of a cut is disposable once it is in R2 -- `raw_12lead` was
    deleted on 2026-09-30 to free space on C:, after its objects were compared
    byte-for-byte against the bucket. Sizing must survive that, or the report
    silently under-counts the campaign that reads it and calls the row a lower
    bound. The manifest is 1.4 KB, so it is kept beside the empty directory.
    """
    if not dataset.endswith("_pieces"):
        return None
    base = dataset[: -len("_pieces")]
    manifest = CHUNK_ROOT / CHUNKS.get(base, "") / "checksums.json"
    if not manifest.is_file():
        return None
    recorded = json.loads(manifest.read_text(encoding="utf-8"))
    return {name: int(meta["bytes"]) for name, meta in recorded.items()
            if isinstance(meta, dict) and "bytes" in meta}


def phase_bytes(dataset: str, phase: str) -> int:
    """Bytes this dataset puts on the node in one phase, the way stage_data does.

    Mirrors `campaigns.sh::phase_excludes` and the piece rule above. Derived
    from the files rather than typed into the table, because the table has
    drifted repeatedly -- campaign 12 was listed 4.3 GB light and campaign 7
    was listed 2.8 GB light, which put it over the ceiling unnoticed.
    """
    if dataset == "results":
        return 0
    if dataset.endswith("_pieces"):
        if phase in ("eval", "val"):
            return 0               # pieces are TRAIN data; the val swap evicts them
        try:
            pairs = dataset_files(dataset)
            sizes = {p.name: p.stat().st_size for p, _ in pairs}
        except SystemExit:
            sizes = _recorded_sizes(dataset) or {}
            if not sizes:
                raise
        pieces = sorted((v for k, v in sizes.items() if k.startswith("piece_")),
                        reverse=True)
        other = sum(v for k, v in sizes.items() if not k.startswith("piece_"))
        return sum(pieces[:RESIDENT_PIECES]) + other
    return sum(path.stat().st_size for path, _key in dataset_files(dataset)
               if _keep(path.name, phase))


def campaign_val_mode(campaign: int) -> str:
    """`resident` or `on_demand`, field 8 of the campaign spec."""
    text = CAMPAIGNS_SH.read_text(encoding="utf-8")
    match = re.search(rf'^\s*{campaign}\)\s+echo "([^"]+)"', text, re.M)
    if not match:
        raise SystemExit(f"campaigns.sh has no campaign {campaign}")
    fields = match.group(1).split("|")
    return fields[7] if len(fields) > 7 else "resident"


def sizes_report(campaigns: list[int], overhead: float) -> int:
    """Measured residency per campaign and phase, and the require_fit verdict."""
    print(f"Measured residency per campaign, GB. Ceiling {CEILING_GB:.0f} GB, "
          f"non-dataset overhead {overhead:.1f} GB "
          f"(fixed {FIXED_GB:.1f} + checkpoints {CHECKPOINTS_GB:.1f}), so the "
          f"budget for data is {CEILING_GB - overhead:.1f} GB.")
    print(f"A chunked dataset counts {RESIDENT_PIECES} resident pieces while "
          f"training and nothing while validating or evaluating.")
    print("An `on_demand` campaign never holds train and val at once: its peak "
          "is max(train_only, val).\n")
    print(f"{'n':>3} {'val mode':<10} {'train':>7} {'val':>7} {'eval':>7} {'peak':>7}  "
          f"{'verdict':<26} missing")
    status = 0
    for campaign in campaigns:
        mode = campaign_val_mode(campaign)
        phases = ("train_only", "val", "eval") if mode == "on_demand" \
            else ("train", "val", "eval")
        totals, missing = {}, []
        for phase in phases:
            total = 0
            for dataset in campaign_datasets(campaign):
                try:
                    total += phase_bytes(dataset, phase)
                except SystemExit:
                    if dataset not in missing:
                        missing.append(dataset)
            totals[phase] = total / 1e9
        train = totals[phases[0]]
        # A `resident` campaign already holds val inside its train phase, so its
        # val row is informational; an `on_demand` one really does swap.
        peak = max(train, totals["eval"], totals["val"] if mode == "on_demand" else 0.0)
        headroom = CEILING_GB - overhead - peak
        verdict = (f"OK, {headroom:+.1f} GB spare" if headroom >= 0
                   else f"REFUSES, {headroom:+.1f} GB over")
        if headroom < 0:
            status = 1
        print(f"{campaign:>3} {mode:<10} {train:>7.1f} {totals['val']:>7.1f} "
              f"{totals['eval']:>7.1f} {peak:>7.1f}  {verdict:<26} "
              f"{', '.join(missing) if missing else '-'}")
    print("\nA `missing` dataset is not built on this machine and its bytes are "
          "absent from that row, so the row is a LOWER BOUND. A cut that is only "
          "in R2 is still counted, from its own checksums.json.")
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--campaign", type=int, help="upload this campaign's datasets")
    parser.add_argument("--dataset", nargs="+", help="upload these datasets by name")
    parser.add_argument("--all", action="store_true", help="every dataset, campaign order")
    parser.add_argument("--dry-run", action="store_true",
                        help="print sizes per dataset and what rclone would do")
    parser.add_argument("--skip-checksums", action="store_true",
                        help="stage without hashing (a size-only preview)")
    parser.add_argument("--sizes", action="store_true",
                        help="report measured train/eval residency per campaign "
                             "and the require_fit verdict; uploads nothing")
    parser.add_argument("--overhead", type=float, default=FIXED_GB + CHECKPOINTS_GB,
                        help="non-dataset GB to charge against the ceiling in --sizes")
    args = parser.parse_args(argv)

    if args.sizes:
        return sizes_report(list(range(1, n_campaigns() + 1)), args.overhead)

    if args.campaign:
        wanted = campaign_datasets(args.campaign)
    elif args.dataset:
        wanted = args.dataset
    elif args.all:
        seen: list[str] = []
        # range(1, 12) predated the Lead-II split (open question 14), so --all
        # silently skipped campaigns 12, 13 and 14 -- and with them, from open
        # question 16, `images_scanlike_lead2_valtest`.
        for campaign in range(1, n_campaigns() + 1):
            for dataset in campaign_datasets(campaign):
                if dataset not in seen:
                    seen.append(dataset)
        wanted = seen
    else:
        parser.error("give --campaign N, --dataset NAME..., or --all")

    problems = audit_task_tables()
    if problems:
        print("REFUSING: a task parquet carries binary data, not just ids and labels:")
        for line in problems:
            print("   " + line)
        return 1

    cache = _load_cache()
    total = 0
    status = 0
    for dataset in wanted:
        if dataset == "results":
            print(f"{dataset:26s} SKIP -- campaign 11 reads r2:trimodal-results, "
                  f"which push_results.sh fills from the DGX")
            continue
        try:
            pairs = dataset_files(dataset)
        except SystemExit as error:
            print(f"{dataset:26s} NOT READY -- {error}")
            status = 1
            continue
        _refuse_forbidden([p for p, _ in pairs])
        size = sum(p.stat().st_size for p, _ in pairs)
        total += size
        print(f"{dataset:26s} {len(pairs):5d} files  {human(size):>12s}")
        if args.dry_run and args.skip_checksums:
            continue
        root = stage(pairs, dataset, cache, checksums=not args.skip_checksums)
        status |= push(root, args.dry_run)

    print(f"{'TOTAL':26s} {human(total):>18s}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
