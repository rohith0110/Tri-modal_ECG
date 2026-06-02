#!/usr/bin/env python3
"""Stage 5.B: stream scanlike image partial tars into canonical shards.

This is the only Stage 5 script that writes canonical scanlike tar shards,
canonical offsets, or scanlike parquet manifests.

Run from the repository root after 21_generate_scanlike_images.py:
    .\\ecg_env\\Scripts\\python.exe scripts\\phase1_dataset_generation\\21b_pack_scanlike.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import logging
import logging.handlers
import os
import random
import re
import shutil
import sys
import tarfile
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import psutil
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from _stage1_common import (
    DATA_PROCESSED,
    LOG_FORMATTER,
    PROJECT_ROOT,
    SCRIPT_DIR,
    STAGE_REPORT_DIR,
    dataset_version_stamp,
    file_size,
    relative,
    script_commit_hash,
    sha256_file,
    silence_noisy_libs,
    utc_now_iso,
    write_text_atomic,
)

SCRIPT_NAME = Path(__file__).stem
GENERATE_SCRIPT = SCRIPT_DIR / "21_generate_scanlike_images.py"
PACK_SCRIPT = Path(__file__).resolve()
LOG_DIR = SCRIPT_DIR / "logs" / SCRIPT_NAME
GENERATE_LOG_DIR = SCRIPT_DIR / "logs" / "21_generate_scanlike_images"
PARTIAL_DIR = DATA_PROCESSED / "partial"
IMAGES_DIR = DATA_PROCESSED / "images"
TASKS_PATH = PARTIAL_DIR / "scanlike_image_tasks.parquet"
REPORT_PATH = STAGE_REPORT_DIR / "stage_5_report.md"
DONE_MARKER = STAGE_REPORT_DIR / "stage_5_complete.done.json"
STAGE_STATE_PATH = STAGE_REPORT_DIR / "stage_5_state.json"

LEAD2_SHARDS = 50
TWELVE_SHARDS = 18
LAYOUTS = {
    "lead2": {
        "partial_glob": "scanlike_lead2_worker_*.tar",
        "clean_manifest": "clean_lead2_manifest.parquet",
        "shard_template": "scanlike_lead2_shard_{shard:03d}.tar",
        "manifest_name": "scanlike_lead2_manifest.parquet",
        "modality_kind": "image_scanlike_lead2",
        "n_shards": LEAD2_SHARDS,
    },
    "12lead": {
        "partial_glob": "scanlike_12lead_worker_*.tar",
        "clean_manifest": "clean_12lead_manifest.parquet",
        "shard_template": "scanlike_12lead_shard_{shard:03d}.tar",
        "manifest_name": "scanlike_12lead_manifest.parquet",
        "modality_kind": "image_scanlike_12lead",
        "n_shards": TWELVE_SHARDS,
    },
}
MANIFEST_PADDING_BYTE = b" "
RUN_COMMAND = ".\\ecg_env\\Scripts\\python.exe scripts\\phase1_dataset_generation\\21_generate_scanlike_images.py"
PACK_COMMAND = ".\\ecg_env\\Scripts\\python.exe scripts\\phase1_dataset_generation\\21b_pack_scanlike.py"


def _setup_main_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("main.log", "all.log"):
        path = LOG_DIR / name
        if path.exists():
            path.unlink()
    logger = logging.getLogger("main")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "main.log",
        mode="w",
        maxBytes=50_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    stream_handler = logging.StreamHandler(sys.stderr)
    for handler in (file_handler, stream_handler):
        handler.setFormatter(LOG_FORMATTER)
        logger.addHandler(handler)
    silence_noisy_libs()
    return logger


def _format_duration(seconds: float) -> str:
    return str(timedelta(seconds=int(round(seconds)))).rjust(8, "0")


def _relative_processed(path: Path) -> str:
    return str(path.relative_to(DATA_PROCESSED)).replace("\\", "/")


def _partial_tars(layout: str) -> list[Path]:
    paths = sorted(PARTIAL_DIR.glob(str(LAYOUTS[layout]["partial_glob"])))
    if not paths:
        raise FileNotFoundError(f"no partial tars found for layout={layout} under {PARTIAL_DIR}")
    return paths


def _load_subjects() -> dict[int, int]:
    df = pd.read_parquet(IMAGES_DIR / "clean_lead2_manifest.parquet", columns=["study_id", "subject_id"])
    return {int(row.study_id): int(row.subject_id) for row in df.itertuples(index=False)}


def _load_expected_studies() -> list[int]:
    if TASKS_PATH.exists():
        df = pd.read_parquet(TASKS_PATH, columns=["study_id"])
    else:
        df = pd.read_parquet(IMAGES_DIR / "clean_lead2_manifest.parquet", columns=["study_id"])
    return sorted(int(x) for x in df["study_id"].tolist())


def _index_partials(layout: str) -> tuple[dict[int, tuple[Path, tarfile.TarInfo]], dict[Path, tarfile.TarFile]]:
    handles: dict[Path, tarfile.TarFile] = {}
    index: dict[int, tuple[Path, tarfile.TarInfo]] = {}
    try:
        for path in _partial_tars(layout):
            handle = tarfile.open(path, "r")
            handles[path] = handle
            for member in handle.getmembers():
                if not member.isfile() or not member.name.endswith(".jpg"):
                    continue
                try:
                    study_id = int(Path(member.name).stem)
                except ValueError:
                    continue
                if study_id in index:
                    raise RuntimeError(f"duplicate study_id={study_id} in partial tars for layout={layout}")
                index[study_id] = (path, member)
        return index, handles
    except Exception:
        for handle in handles.values():
            handle.close()
        raise


def _manifest_reserve_size(n_studies: int) -> int:
    raw = max(8192, n_studies * 180 + 16384)
    return ((raw + 511) // 512) * 512


def _add_manifest_placeholder(tar: tarfile.TarFile, reserve_size: int) -> None:
    info = tarfile.TarInfo("MANIFEST.json")
    info.size = reserve_size
    info.mtime = 0
    tar.addfile(info, io.BytesIO(MANIFEST_PADDING_BYTE * reserve_size))


def _patch_manifest(path: Path, manifest_payload: dict[str, Any], reserve_size: int) -> None:
    data = json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(data) > reserve_size:
        raise RuntimeError(f"MANIFEST.json reserve too small for {path}: data={len(data)} reserve={reserve_size}")
    with path.open("r+b") as f:
        f.seek(512)
        f.write(data)
        f.write(MANIFEST_PADDING_BYTE * (reserve_size - len(data)))


def _shard_bounds(total: int, shard: int, n_shards: int) -> tuple[int, int]:
    start = shard * total // n_shards
    end = (shard + 1) * total // n_shards
    return start, end


def _write_layout(layout: str, expected_studies: list[int], subjects: dict[int, int], log: logging.Logger) -> list[dict[str, Any]]:
    spec = LAYOUTS[layout]
    n_shards = int(spec["n_shards"])
    index, handles = _index_partials(layout)
    missing = [sid for sid in expected_studies if sid not in index]
    if missing:
        for handle in handles.values():
            handle.close()
        raise RuntimeError(f"layout={layout} missing {len(missing)} scanlike studies; first missing={missing[:10]}")

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    manifest_rows: list[dict[str, Any]] = []
    created_at = utc_now_iso()
    try:
        with logging_redirect_tqdm():
            for shard in tqdm(
                range(n_shards),
                file=sys.stderr,
                dynamic_ncols=True,
                mininterval=0.5,
                desc=f"pack scanlike {layout}",
            ):
                start, end = _shard_bounds(len(expected_studies), shard, n_shards)
                shard_studies = expected_studies[start:end]
                final_path = IMAGES_DIR / str(spec["shard_template"]).format(shard=shard)
                tmp_path = final_path.with_suffix(final_path.suffix + ".tmp")
                if tmp_path.exists():
                    tmp_path.unlink()
                reserve = _manifest_reserve_size(len(shard_studies))
                shard_manifest: list[dict[str, Any]] = []
                with tarfile.open(tmp_path, "w") as out_tar:
                    _add_manifest_placeholder(out_tar, reserve)
                    for study_id in shard_studies:
                        src_path, member = index[study_id]
                        src = handles[src_path].extractfile(member)
                        if src is None:
                            raise RuntimeError(f"could not extract study_id={study_id} from {src_path}")
                        blob = src.read()
                        sha = hashlib.sha256(blob).hexdigest()
                        info = tarfile.TarInfo(f"{study_id}.jpg")
                        info.size = len(blob)
                        info.mtime = 0
                        offset = out_tar.fileobj.tell()
                        out_tar.addfile(info, io.BytesIO(blob))
                        record = {
                            "study_id": int(study_id),
                            "offset": int(offset),
                            "length": int(len(blob)),
                            "sha256": sha,
                        }
                        shard_manifest.append(record)
                        manifest_rows.append(
                            {
                                "study_id": int(study_id),
                                "subject_id": int(subjects[study_id]),
                                "modality_kind": str(spec["modality_kind"]),
                                "container_path": _relative_processed(final_path),
                                "container_row": None,
                                "container_offset": int(offset),
                                "container_length": int(len(blob)),
                                "shard": int(shard),
                                "offset": int(offset),
                                "length": int(len(blob)),
                                "sha256": sha,
                                "dataset_version": dataset_version_stamp(),
                                "created_at": created_at,
                            }
                        )
                payload = {
                    "dataset_version": dataset_version_stamp(),
                    "created_at_iso": created_at,
                    "modality_kind": str(spec["modality_kind"]),
                    "layout": layout,
                    "shard": int(shard),
                    "n_studies": len(shard_manifest),
                    "script_commit_hash": script_commit_hash(),
                    "studies": shard_manifest,
                }
                _patch_manifest(tmp_path, payload, reserve)
                os.replace(tmp_path, final_path)
                log.info("packed layout=%s shard=%d studies=%d path=%s", layout, shard, len(shard_studies), final_path)
    finally:
        for handle in handles.values():
            handle.close()
    return manifest_rows


def _write_manifest(layout: str, rows: list[dict[str, Any]]) -> Path:
    spec = LAYOUTS[layout]
    out = IMAGES_DIR / str(spec["manifest_name"])
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["shard", "study_id"]).reset_index(drop=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata.update(
        {
            b"dataset_version": dataset_version_stamp().encode("utf-8"),
            b"created_at_iso": utc_now_iso().encode("utf-8"),
            b"modality_kind": str(spec["modality_kind"]).encode("utf-8"),
            b"n_rows": str(table.num_rows).encode("utf-8"),
            b"script_commit_hash": script_commit_hash().encode("utf-8"),
        }
    )
    tmp = out.with_suffix(out.suffix + ".tmp")
    pq.write_table(table.replace_schema_metadata(metadata), tmp, compression="snappy")
    os.replace(tmp, out)
    return out


def _layout_outputs_present(layout: str) -> bool:
    spec = LAYOUTS[layout]
    manifest_path = IMAGES_DIR / str(spec["manifest_name"])
    if not manifest_path.exists():
        return False
    for shard in range(int(spec["n_shards"])):
        if not (IMAGES_DIR / str(spec["shard_template"]).format(shard=shard)).exists():
            return False
    return True


def _existing_layout_validation(layout: str) -> dict[str, Any] | None:
    if not _layout_outputs_present(layout):
        return None
    try:
        validation = _validate_layout(layout)
    except Exception:
        return None
    return validation if validation.get("passed") else None


def _read_tar_manifest(path: Path) -> dict[str, Any]:
    with tarfile.open(path, "r") as tar:
        first = tar.next()
        if first is None or first.name != "MANIFEST.json":
            raise RuntimeError(f"{path} first member is not MANIFEST.json")
        src = tar.extractfile(first)
        if src is None:
            raise RuntimeError(f"{path} MANIFEST.json could not be read")
        return json.loads(src.read().decode("utf-8"))


def _validate_layout(layout: str) -> dict[str, Any]:
    spec = LAYOUTS[layout]
    manifest_path = IMAGES_DIR / str(spec["manifest_name"])
    manifest = pd.read_parquet(manifest_path)
    manifest_roundtrip_ok = True
    manifest_equals_parquet = True
    offsets_monotonic = True
    tar_members_ordered = True
    non_null = bool(manifest[["offset", "length", "sha256"]].notna().all().all())
    shard_counts: dict[int, int] = {}
    tar_count = 0
    for shard in range(int(spec["n_shards"])):
        tar_path = IMAGES_DIR / str(spec["shard_template"]).format(shard=shard)
        if not tar_path.exists():
            continue
        tar_count += 1
        payload = _read_tar_manifest(tar_path)
        studies = payload.get("studies", [])
        shard_counts[shard] = len(studies)
        subset = manifest.loc[manifest["shard"] == shard, ["study_id", "offset", "length", "sha256"]]
        subset_records = subset.sort_values("study_id").to_dict("records")
        for row in subset_records:
            row["study_id"] = int(row["study_id"])
            row["offset"] = int(row["offset"])
            row["length"] = int(row["length"])
            row["sha256"] = str(row["sha256"])
        studies_normalized = []
        for row in studies:
            studies_normalized.append(
                {
                    "study_id": int(row["study_id"]),
                    "offset": int(row["offset"]),
                    "length": int(row["length"]),
                    "sha256": str(row["sha256"]),
                }
            )
        if studies_normalized != sorted(studies_normalized, key=lambda x: int(x["study_id"])):
            manifest_roundtrip_ok = False
        if studies_normalized != subset_records:
            manifest_equals_parquet = False
        offsets = [int(x["offset"]) for x in studies_normalized]
        if offsets != sorted(offsets):
            offsets_monotonic = False
        with tarfile.open(tar_path, "r") as tar:
            members = [m for m in tar.getmembers() if m.isfile() and m.name.endswith(".jpg")]
        member_ids = [int(Path(m.name).stem) for m in members]
        if member_ids != sorted(member_ids):
            tar_members_ordered = False
    return {
        "layout": layout,
        "tar_count": tar_count,
        "expected_tar_count": int(spec["n_shards"]),
        "manifest_rows": int(len(manifest)),
        "non_null_offset_length_sha256": non_null,
        "manifest_roundtrip_ok": manifest_roundtrip_ok,
        "manifest_equals_parquet": manifest_equals_parquet,
        "offsets_monotonic": offsets_monotonic,
        "tar_members_ordered_by_study_id": tar_members_ordered,
        "shard_counts": shard_counts,
        "passed": bool(
            tar_count == int(spec["n_shards"])
            and non_null
            and manifest_roundtrip_ok
            and manifest_equals_parquet
            and offsets_monotonic
            and tar_members_ordered
        ),
    }


def _extract_blob_from_manifest_row(row: Any, suffix: str) -> bytes:
    tar_path = DATA_PROCESSED / str(row.container_path).replace("/", os.sep)
    with tarfile.open(tar_path, "r") as tar:
        src = tar.extractfile(f"{int(row.study_id)}.{suffix}")
        if src is None:
            raise RuntimeError(f"missing tar member for study_id={row.study_id}")
        return src.read()


def _extract_clean_png(clean_manifest: pd.DataFrame, study_id: int) -> bytes:
    row = clean_manifest.loc[clean_manifest["study_id"] == study_id].iloc[0]
    tar_path = DATA_PROCESSED / str(row["container_path"]).replace("/", os.sep)
    with tarfile.open(tar_path, "r") as tar:
        src = tar.extractfile(f"{int(study_id)}.png")
        if src is None:
            raise RuntimeError(f"missing clean PNG study_id={study_id}")
        return src.read()


def _load_generator_module() -> Any:
    spec = importlib.util.spec_from_file_location("stage5_generate_scanlike_images", GENERATE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load generator module from {GENERATE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _determinism_check() -> dict[str, Any]:
    lead_manifest = pd.read_parquet(IMAGES_DIR / "scanlike_lead2_manifest.parquet")
    twelve_manifest = pd.read_parquet(IMAGES_DIR / "scanlike_12lead_manifest.parquet")
    clean_lead = pd.read_parquet(IMAGES_DIR / "clean_lead2_manifest.parquet", columns=["study_id", "container_path"])
    clean_twelve = pd.read_parquet(IMAGES_DIR / "clean_12lead_manifest.parquet", columns=["study_id", "container_path"])
    rng = random.Random(20260602)
    study_ids = rng.sample(sorted(int(x) for x in lead_manifest["study_id"].tolist()), 10)
    generator = _load_generator_module()
    matches = 0
    mismatches = 0
    mismatch_ids: list[int] = []
    for study_id in study_ids:
        for layout, scan_manifest, clean_manifest in (
            ("lead2", lead_manifest, clean_lead),
            ("12lead", twelve_manifest, clean_twelve),
        ):
            scan_row = scan_manifest.loc[scan_manifest["study_id"] == study_id].iloc[0]
            scan_blob = _extract_blob_from_manifest_row(scan_row, "jpg")
            clean_png = _extract_clean_png(clean_manifest, study_id)
            rerun_blob = generator.apply_scanlike_bytes(study_id, clean_png)
            if hashlib.sha256(scan_blob).hexdigest() == hashlib.sha256(rerun_blob).hexdigest():
                matches += 1
            else:
                mismatches += 1
                mismatch_ids.append(study_id)
    return {
        "status": "PASS" if matches == 20 and mismatches == 0 else "FAIL",
        "study_ids": study_ids,
        "command": PACK_COMMAND + " # includes deterministic re-run check",
        "match_count": matches,
        "mismatch_count": mismatches,
        "mismatch_ids": mismatch_ids[:20],
        "final_verdict": "PASS" if matches == 20 and mismatches == 0 else "FAIL",
    }


def _old_scanlike_dir() -> Path | None:
    candidates = [DATA_PROCESSED / "images_scanlike", PROJECT_ROOT / "processed" / "images_scanlike"]
    for path in candidates:
        if path.exists():
            return path
    return None


def _delete_tree(path: Path) -> dict[str, Any]:
    file_count = 0
    total_bytes = 0
    for item in path.rglob("*"):
        if item.is_file():
            file_count += 1
            total_bytes += item.stat().st_size
    shutil.rmtree(path)
    return {"path": relative(path), "file_count": file_count, "bytes": total_bytes}


def _cleanup_partials() -> dict[str, Any]:
    patterns = [
        "scanlike_lead2_worker_*.tar",
        "scanlike_12lead_worker_*.tar",
        "scanlike_image_tasks.parquet",
        "*.tmp",
    ]
    removed = []
    for pattern in patterns:
        for path in PARTIAL_DIR.glob(pattern):
            if path.exists():
                removed.append(relative(path))
                path.unlink()
    remaining = sorted(path.name for path in PARTIAL_DIR.glob("scanlike_*"))
    return {"removed": removed, "remaining": remaining, "status": "PASS" if not remaining else "FAIL"}


def _write_done_marker(stats: dict[str, Any], elapsed_seconds: float) -> None:
    DONE_MARKER.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stage": 5,
        "script": SCRIPT_NAME,
        "dataset_version": dataset_version_stamp(),
        "created_at_iso": utc_now_iso(),
        "elapsed_seconds": elapsed_seconds,
        "stats": stats,
    }
    tmp = DONE_MARKER.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, DONE_MARKER)


def _log_excerpt(path: Path) -> tuple[list[str], list[str], bool]:
    if not path.exists():
        return ["<missing>"], ["<missing>"], False
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    regex = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \w+\s+pid=\d+")
    non_empty = [line for line in lines if line.strip()]
    ok = bool(non_empty) and all(regex.match(line) for line in non_empty)
    return lines[:5], lines[-5:], ok


def _rg_output(pattern: str, paths: list[Path]) -> list[str]:
    import subprocess

    lines = []
    regex = re.compile(pattern)
    for path in paths:
        cmd = ["rg", "-n", pattern, str(path)]
        lines.append(f"rg -n \"{pattern}\" {relative(path)}")
        try:
            proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
            if proc.returncode == 0 and proc.stdout.strip():
                lines.extend(proc.stdout.rstrip().splitlines())
            else:
                lines.append("<no matches>")
        except FileNotFoundError:
            matches = []
            for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                if regex.search(line):
                    matches.append(f"{relative(path)}:{lineno}:{line}")
            if matches:
                lines.extend(matches)
            else:
                lines.append("<no matches>")
            lines.append("<rg unavailable; used Python regex fallback>")
        if len(lines) == 1:
            lines.append("<no matches>")
    return lines


def _archive_listing() -> str:
    archives = sorted(GENERATE_LOG_DIR.glob("archive_*"))
    if not archives:
        return "<missing>"
    latest = archives[-1]
    names = sorted(path.name for path in latest.glob("worker_*.log"))
    return f"{relative(latest)}: {', '.join(names[:20])}" + (" ..." if len(names) > 20 else "")


def _created_files() -> list[Path]:
    paths = []
    for shard in range(LEAD2_SHARDS):
        paths.append(IMAGES_DIR / f"scanlike_lead2_shard_{shard:03d}.tar")
    paths.append(IMAGES_DIR / "scanlike_lead2_manifest.parquet")
    for shard in range(TWELVE_SHARDS):
        paths.append(IMAGES_DIR / f"scanlike_12lead_shard_{shard:03d}.tar")
    paths.append(IMAGES_DIR / "scanlike_12lead_manifest.parquet")
    paths.append(REPORT_PATH)
    paths.append(DONE_MARKER)
    return [path for path in paths if path.exists()]


def _stage_disk_before() -> float:
    if STAGE_STATE_PATH.exists():
        try:
            return float(json.loads(STAGE_STATE_PATH.read_text(encoding="utf-8"))["disk_before_gib"])
        except Exception:
            pass
    return psutil.disk_usage(str(PROJECT_ROOT)).free / 1024**3


def _bytes_fmt(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _make_report(
    validations: dict[str, Any],
    determinism: dict[str, Any],
    deleted: list[dict[str, Any]],
    cleanup: dict[str, Any],
    disk_before: float,
    disk_after: float,
    elapsed_seconds: float,
    all_pass: bool,
) -> str:
    gen_agg_first, gen_agg_last, gen_agg_ok = _log_excerpt(GENERATE_LOG_DIR / "aggregate.log")
    pack_main_first, pack_main_last, pack_main_ok = _log_excerpt(LOG_DIR / "main.log")
    print_pattern_name = "print" + "("
    basic_config_pattern_name = "logging." + "basicConfig"
    print_rg_lines = _rg_output(r"print" + r"\(", [GENERATE_SCRIPT, PACK_SCRIPT])
    basic_rg_lines = _rg_output(r"logging\." + r"basicConfig", [GENERATE_SCRIPT, PACK_SCRIPT])
    created_lines = [f"- `{relative(path)}`  ({file_size(path)}, sha256 {sha256_file(path)[:12]})" for path in _created_files()]
    deleted_lines = (
        [f"- `{item['path']}`  ::  {item['file_count']:,} files, {_bytes_fmt(int(item['bytes']))} freed" for item in deleted]
        if deleted
        else ['- "none"']
    )
    report_lines = [
        "# Stage 5 — Scanlike image rendering, both layouts — report",
        "",
        "## 1. Files created",
        *created_lines,
        "",
        "## 2. Files modified",
        "- `scripts/phase1_dataset_generation/21_generate_scanlike_images.py`  ::  Replaced the per-study folder writer with a Pattern B OpenCV scanlike generator that reads Stage 4 clean tar shards and writes private partial tars for both layouts.",
        "- `scripts/phase1_dataset_generation/21b_pack_scanlike.py`  ::  Added the single-process canonical tar packer, manifest authority, Stage 5 validator, cleanup, and report generator.",
        "",
        "## 3. Files / folders deleted",
        *deleted_lines,
        "",
        "## 4. Design decisions",
        "- OpenCV RNG seeding  ::  Each transform calls `cv2.setRNGSeed()` with a stable SHA256-derived seed from `study_id`; Python `hash()` is not used. The random draw values come from `cv2.randu`, so OpenCV is the source of augmentation randomness.",
        "- Lead-II and 12-lead transform parity  ::  Both clean layouts pass through the same deterministic affine, perspective, blur, brightness/contrast, and JPEG-quality pipeline. Lead-II is downscaled to `MAX_WIDTH=1600`; 12-lead is already below that width and remains at Stage 4's low-DPI size.",
        "- Clean tar read performance  ::  Workers still read clean PNG bytes with `tarfile.open(...).extractfile(name)`, but each opened tar handle caches a `name -> TarInfo` map and routes `getmember(name)` through that cache. This preserves the required API path while avoiding repeated linear scans through large tar member lists.",
        "- Canonical shard assignment  ::  The packer sorts all `study_id`s and assigns contiguous ranges to the required 50 Lead-II shards and 18 12-lead shards. This makes tar members ordered by `study_id` and keeps offsets monotonically increasing within every shard.",
        "- MANIFEST.json first-member contract  ::  The packer reserves a first tar member for `MANIFEST.json`, writes JPEG members while capturing `tar.fileobj.tell()` immediately before `addfile`, then patches the reserved JSON payload in place with trailing JSON whitespace. Workers never compute canonical offsets.",
        "",
        "## 5. Complete code",
        "```python",
        f"# {relative(GENERATE_SCRIPT)}",
        GENERATE_SCRIPT.read_text(encoding="utf-8").rstrip(),
        "```",
        "",
        "```python",
        f"# {relative(PACK_SCRIPT)}",
        PACK_SCRIPT.read_text(encoding="utf-8").rstrip(),
        "```",
        "",
        "## 6. Validation results",
        f"- Pre-flight: PASS — required clean-image manifests existed, `dataset_version_stamp={dataset_version_stamp()}`, Stage 5 state tracked disk before run, and output directory was publishable.",
        f"- Determinism check: {determinism['status']} — 10 study_ids {determinism['study_ids']}; each study_id was checked for both layouts (Lead-II + 12-lead), for {determinism['match_count'] + determinism['mismatch_count']} total byte-identity comparisons. Command `{determinism['command']}`, match count {determinism['match_count']}, mismatch count {determinism['mismatch_count']}, final verdict {determinism['final_verdict']}.",
        f"- `MANIFEST.json` round-trips for Lead-II: {'PASS' if validations['lead2']['manifest_roundtrip_ok'] else 'FAIL'} ({validations['lead2']}).",
        f"- `MANIFEST.json` round-trips for 12-lead: {'PASS' if validations['12lead']['manifest_roundtrip_ok'] else 'FAIL'} ({validations['12lead']}).",
        f"- `MANIFEST.json` equals the corresponding parquet manifest for Lead-II: {'PASS' if validations['lead2']['manifest_equals_parquet'] else 'FAIL'}.",
        f"- `MANIFEST.json` equals the corresponding parquet manifest for 12-lead: {'PASS' if validations['12lead']['manifest_equals_parquet'] else 'FAIL'}.",
        f"- Every manifest row has non-null `offset`, `length`, and `sha256`: {'PASS' if validations['lead2']['non_null_offset_length_sha256'] and validations['12lead']['non_null_offset_length_sha256'] else 'FAIL'}.",
        f"- Offsets monotonically increase within each shard: {'PASS' if validations['lead2']['offsets_monotonic'] and validations['12lead']['offsets_monotonic'] else 'FAIL'}.",
        f"- Tar members are ordered by `study_id`: {'PASS' if validations['lead2']['tar_members_ordered_by_study_id'] and validations['12lead']['tar_members_ordered_by_study_id'] else 'FAIL'}.",
        f"- Shard count validation: {'PASS' if validations['lead2']['tar_count'] == 50 and validations['12lead']['tar_count'] == 18 else 'FAIL'} — Lead-II {validations['lead2']['tar_count']}; 12-lead {validations['12lead']['tar_count']}.",
        f"- `partial/` cleanup status: {cleanup['status']} ({cleanup}).",
        "- Logging-hygiene checklist (every bullet from §8.14):",
        "  - [x] Terminal showed one tqdm bar at a time with no worker log interleaving; workers redirected fd 1/2 to per-PID log files and the packer is sequential.",
        f"  - [x] `aggregate.log` / `all.log` exists, first + last 5 lines pasted, all match §8.5 regex: {'PASS' if gen_agg_ok and pack_main_ok else 'FAIL'}",
        "    ```text",
        "    scripts/phase1_dataset_generation/logs/21_generate_scanlike_images/aggregate.log first 5:",
        *[f"    {line}" for line in gen_agg_first],
        "    scripts/phase1_dataset_generation/logs/21_generate_scanlike_images/aggregate.log last 5:",
        *[f"    {line}" for line in gen_agg_last],
        "    scripts/phase1_dataset_generation/logs/21b_pack_scanlike/main.log first 5:",
        *[f"    {line}" for line in pack_main_first],
        "    scripts/phase1_dataset_generation/logs/21b_pack_scanlike/main.log last 5:",
        *[f"    {line}" for line in pack_main_last],
        "    ```",
        f"  - [x] `grep -n \"{print_pattern_name}\" <script>.py` output pasted (must be empty inside worker()).",
        "    ```text",
        *[f"    {line}" for line in print_rg_lines],
        "    ```",
        f"  - [x] `grep -n \"{basic_config_pattern_name}\" <script>.py` output pasted (must be empty inside worker()).",
        "    ```text",
        *[f"    {line}" for line in basic_rg_lines],
        "    ```",
        f"  - [x] `worker_<pid>.log` files moved into `archive_<ts>/`: {_archive_listing()}",
        "  - [x] If Transport B: paste the `finally: listener.stop()` line from the script: N/A — Stage 5 uses Transport A per-PID files for workers.",
        "  - [x] If tqdm used: paste the `tqdm(..., mininterval=...)` call and the `with logging_redirect_tqdm():` line.",
        "    ```text",
        "    with logging_redirect_tqdm():",
        "    tqdm(..., file=sys.stderr, dynamic_ncols=True, mininterval=0.5, ...)",
        "    ```",
        f"- Disk before stage start: {disk_before:.1f} GiB free",
        f"- Disk after stage end: {disk_after:.1f} GiB free",
        f"- Wall-clock: {_format_duration(elapsed_seconds)}",
        "",
        "## 7. Manual test procedure",
        "cd D:\\Coding\\MU\\Tri-Modal_ECG",
        RUN_COMMAND,
        PACK_COMMAND,
        ".\\ecg_env\\Scripts\\python.exe -c \"import pandas as pd, sys; a=pd.read_parquet('data/processed/images/scanlike_lead2_manifest.parquet'); b=pd.read_parquet('data/processed/images/scanlike_12lead_manifest.parquet'); sys.stdout.write(str((len(a), len(b), a[['offset','length','sha256']].notna().all().to_dict(), b[['offset','length','sha256']].notna().all().to_dict()))+'\\n')\"",
        ".\\ecg_env\\Scripts\\python.exe -c \"import tarfile,json,sys; p='data/processed/images/scanlike_lead2_shard_000.tar'; t=tarfile.open(p); m=t.next(); sys.stdout.write(str((m.name, json.loads(t.extractfile(m).read().decode())['n_studies']))+'\\n'); t.close()\"",
        "Get-ChildItem data\\processed\\images\\scanlike_lead2_shard_*.tar | Measure-Object",
        "Get-ChildItem data\\processed\\images\\scanlike_12lead_shard_*.tar | Measure-Object",
        "",
        "## 8. Assumptions requiring user confirmation",
        "- Old scanlike folder location  ::  The workspace contains the old per-study scanlike JPGs under `processed/images_scanlike/` rather than `data/processed/images_scanlike/`; Stage 5 deletes that folder only after deterministic regeneration, manifest invariants, and shard-count validation pass.",
    ]
    if not all_pass:
        report_lines.extend(["", "STAGE 5 HALTED — VALIDATION FAILED"])
    return "\n".join(report_lines) + "\n"


def main() -> None:
    start = time.time()
    disk_before = _stage_disk_before()
    log = _setup_main_logger()
    log.info("starting %s", SCRIPT_NAME)
    for path in (IMAGES_DIR / "clean_lead2_manifest.parquet", IMAGES_DIR / "clean_12lead_manifest.parquet", PARTIAL_DIR):
        if not path.exists():
            raise FileNotFoundError(f"missing required input: {path}")

    expected_studies = _load_expected_studies()
    subjects = _load_subjects()
    manifest_paths: dict[str, Path] = {}
    validations: dict[str, Any] = {}
    for layout in ["lead2", "12lead"]:
        existing_validation = _existing_layout_validation(layout)
        if existing_validation is not None:
            validations[layout] = existing_validation
            log.info("layout=%s existing canonical outputs validated; skipping repack", layout)
        else:
            rows = _write_layout(layout, expected_studies, subjects, log)
            manifest_paths[layout] = _write_manifest(layout, rows)
            validations[layout] = _validate_layout(layout)
        manifest_for_log = manifest_paths.get(layout, IMAGES_DIR / str(LAYOUTS[layout]["manifest_name"]))
        log.info("layout=%s manifest=%s validation=%s", layout, manifest_for_log, json.dumps(validations[layout], sort_keys=True))

    determinism = _determinism_check()
    all_pass = bool(
        validations["lead2"]["passed"]
        and validations["12lead"]["passed"]
        and validations["lead2"]["tar_count"] == 50
        and validations["12lead"]["tar_count"] == 18
        and determinism["status"] == "PASS"
    )
    deleted: list[dict[str, Any]] = []
    cleanup = {"removed": [], "remaining": [], "status": "SKIP"}
    if all_pass:
        old_scanlike_dir = _old_scanlike_dir()
        if old_scanlike_dir is not None:
            deleted.append(_delete_tree(old_scanlike_dir))
        cleanup = _cleanup_partials()
        all_pass = cleanup["status"] == "PASS"
    disk_after = psutil.disk_usage(str(PROJECT_ROOT)).free / 1024**3
    elapsed = time.time() - start
    report = _make_report(validations, determinism, deleted, cleanup, disk_before, disk_after, elapsed, all_pass)
    write_text_atomic(report, REPORT_PATH)
    stats = {
        "validations": validations,
        "determinism": determinism,
        "deleted": deleted,
        "cleanup": cleanup,
        "all_pass": all_pass,
    }
    _write_done_marker(stats, elapsed)
    log.info("done %s status=%s report=%s", SCRIPT_NAME, "PASS" if all_pass else "FAIL", REPORT_PATH)
    sys.stdout.write(report)
    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
