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
}

# --- chunked datasets: local cut directory -> the remote base name -----------
# campaigns.sh names these `<base>_pieces`; stage_data.sh reads them back from
# chunks/<base>/. The local directory is what make_chunks.py wrote.
CHUNK_ROOT = Path(os.environ.get("TRIMODAL_CHUNK_ROOT", DATA / "chunks"))

CHUNKS: dict[str, str] = {
    "signals_12lead": "preprocessed_12lead__train__p8",
    "images_clean_12lead": "image_clean_12lead__train__p8",
    "signals_raw": "raw_12lead__train__p8",
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
        pieces = sorted(p for p in directory.iterdir()
                        if p.name.startswith("piece_")
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
    return match.group(1).split("|")[-1].split()


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
                raise SystemExit(
                    f"cannot hard-link {source} -> {target} ({error}). The staging tree "
                    f"must sit on the same volume as the data; set STAGE_ROOT or move "
                    f"outputs/ onto the data volume.") from error
        remote_dir = str(Path(key).parent.as_posix())
        by_directory.setdefault(remote_dir, {})[Path(key).name] = {
            "sha256": sha256_file(source, cache) if checksums else "",
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
    command = ["rclone", "copy", str(root), REMOTE, "--checksum",
               "--transfers", "4", "--stats", "30s", "--stats-one-line"]
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--campaign", type=int, help="upload this campaign's datasets")
    parser.add_argument("--dataset", nargs="+", help="upload these datasets by name")
    parser.add_argument("--all", action="store_true", help="every dataset, campaign order")
    parser.add_argument("--dry-run", action="store_true",
                        help="print sizes per dataset and what rclone would do")
    parser.add_argument("--skip-checksums", action="store_true",
                        help="stage without hashing (a size-only preview)")
    args = parser.parse_args(argv)

    if args.campaign:
        wanted = campaign_datasets(args.campaign)
    elif args.dataset:
        wanted = args.dataset
    elif args.all:
        seen: list[str] = []
        for campaign in range(1, 12):
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
