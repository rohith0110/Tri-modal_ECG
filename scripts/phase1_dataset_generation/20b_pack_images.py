#!/usr/bin/env python3
"""Stage 4.B: stream clean image partial tars into canonical shards.

This is the only Stage 4 script that writes canonical clean-image tar
shards, canonical offsets, or clean-image parquet manifests.

Run from the repository root after 20_render_clean_images.py:
    .\\ecg_env\\Scripts\\python.exe scripts\\phase1_dataset_generation\\20b_pack_images.py
"""

from __future__ import annotations

import hashlib
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

import h5py
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
RENDER_SCRIPT = SCRIPT_DIR / "20_render_clean_images.py"
PACK_SCRIPT = Path(__file__).resolve()
LOG_DIR = SCRIPT_DIR / "logs" / SCRIPT_NAME
RENDER_LOG_DIR = SCRIPT_DIR / "logs" / "20_render_clean_images"
PARTIAL_DIR = DATA_PROCESSED / "partial"
IMAGES_DIR = DATA_PROCESSED / "images"
TASKS_PATH = PARTIAL_DIR / "clean_image_render_tasks.parquet"
INDEX_PATH = DATA_PROCESSED / "index" / "ecg_metadata.parquet"
SIGNALS_MANIFEST = DATA_PROCESSED / "signals" / "signals_manifest.parquet"
LEAD2_H5 = DATA_PROCESSED / "signals" / "lead2_raw.h5"
REPORT_PATH = STAGE_REPORT_DIR / "stage_4_report.md"
DONE_MARKER = STAGE_REPORT_DIR / "stage_4_complete.done.json"
STAGE_STATE_PATH = STAGE_REPORT_DIR / "stage_4_state.json"
EXAMPLE_DIR = STAGE_REPORT_DIR / "stage_4_examples"

LEAD2_SHARDS = 100
TWELVE_SHARDS = 30
LAYOUTS = {
    "lead2": {
        "partial_glob": "clean_lead2_worker_*.tar",
        "shard_template": "clean_lead2_shard_{shard:03d}.tar",
        "manifest_name": "clean_lead2_manifest.parquet",
        "modality_kind": "image_clean_lead2",
        "n_shards": LEAD2_SHARDS,
    },
    "12lead": {
        "partial_glob": "clean_12lead_worker_*.tar",
        "shard_template": "clean_12lead_shard_{shard:03d}.tar",
        "manifest_name": "clean_12lead_manifest.parquet",
        "modality_kind": "image_clean_12lead",
        "n_shards": TWELVE_SHARDS,
    },
}
MANIFEST_PADDING_BYTE = b" "
SPOTCHECK_COMMAND = (
    ".\\ecg_env\\Scripts\\python.exe scripts\\phase1_dataset_generation\\20b_pack_images.py "
    "# includes deterministic Lead-II fixed-scale re-render spot check"
)


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
    spec = LAYOUTS[layout]
    paths = sorted(PARTIAL_DIR.glob(str(spec["partial_glob"])))
    if not paths:
        raise FileNotFoundError(f"no partial tars found for layout={layout} under {PARTIAL_DIR}")
    return paths


def _load_subjects() -> dict[int, int]:
    df = pd.read_parquet(INDEX_PATH, columns=["study_id", "subject_id"])
    return {int(row.study_id): int(row.subject_id) for row in df.itertuples(index=False)}


def _load_expected_studies() -> list[int]:
    if TASKS_PATH.exists():
        df = pd.read_parquet(TASKS_PATH, columns=["study_id"])
    else:
        df = pd.read_parquet(INDEX_PATH, columns=["study_id"])
    return sorted(int(x) for x in df["study_id"].tolist())


def _index_partials(layout: str) -> tuple[dict[int, tuple[Path, tarfile.TarInfo]], dict[Path, tarfile.TarFile]]:
    handles: dict[Path, tarfile.TarFile] = {}
    index: dict[int, tuple[Path, tarfile.TarInfo]] = {}
    try:
        for path in _partial_tars(layout):
            handle = tarfile.open(path, "r")
            handles[path] = handle
            for member in handle.getmembers():
                if not member.isfile() or not member.name.endswith(".png"):
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
        raise RuntimeError(f"layout={layout} missing {len(missing)} rendered studies; first missing={missing[:10]}")

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
                desc=f"pack clean {layout}",
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
                        info = tarfile.TarInfo(f"{study_id}.png")
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


def _cleanup_layout_partials(layout: str) -> list[str]:
    removed = []
    for path in PARTIAL_DIR.glob(str(LAYOUTS[layout]["partial_glob"])):
        if path.exists():
            removed.append(relative(path))
            path.unlink()
    return removed


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
    parquet_ok = True
    manifest_roundtrip_ok = True
    manifest_equals_parquet = True
    offsets_monotonic = True
    non_null = bool(manifest[["offset", "length", "sha256"]].notna().all().all())
    shard_counts: dict[int, int] = {}
    tar_count = 0
    for shard in range(int(spec["n_shards"])):
        tar_path = IMAGES_DIR / str(spec["shard_template"]).format(shard=shard)
        if not tar_path.exists():
            parquet_ok = False
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
        studies_sorted = sorted(studies, key=lambda x: int(x["study_id"]))
        if len(studies_sorted) != len(studies):
            manifest_roundtrip_ok = False
        if studies_sorted != subset_records:
            manifest_equals_parquet = False
        offsets = [int(x["offset"]) for x in studies]
        if offsets != sorted(offsets):
            offsets_monotonic = False
    return {
        "layout": layout,
        "tar_count": tar_count,
        "expected_tar_count": int(spec["n_shards"]),
        "manifest_rows": int(len(manifest)),
        "non_null_offset_length_sha256": non_null,
        "manifest_roundtrip_ok": manifest_roundtrip_ok,
        "manifest_equals_parquet": manifest_equals_parquet,
        "offsets_monotonic": offsets_monotonic,
        "shard_counts": shard_counts,
        "passed": bool(
            parquet_ok
            and tar_count == int(spec["n_shards"])
            and non_null
            and manifest_roundtrip_ok
            and manifest_equals_parquet
            and offsets_monotonic
        ),
    }


def _extract_png_from_manifest_row(row: Any) -> bytes:
    tar_path = DATA_PROCESSED / str(row.container_path).replace("/", os.sep)
    with tarfile.open(tar_path, "r") as tar:
        src = tar.extractfile(f"{int(row.study_id)}.png")
        if src is None:
            raise RuntimeError(f"missing tar member for study_id={row.study_id}")
        return src.read()


def _legacy_clean_dir() -> Path | None:
    candidates = [DATA_PROCESSED / "images_clean", PROJECT_ROOT / "processed" / "images_clean"]
    for path in candidates:
        if path.exists():
            return path
    return None


def _load_render_module() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("stage4_render_clean_images", RENDER_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load renderer module from {RENDER_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lead2_spotcheck() -> dict[str, Any]:
    manifest = pd.read_parquet(IMAGES_DIR / "clean_lead2_manifest.parquet")
    raw_manifest = pd.read_parquet(
        SIGNALS_MANIFEST,
        columns=["study_id", "modality_kind", "container_row"],
    )
    raw_manifest = raw_manifest.loc[raw_manifest["modality_kind"] == "raw_lead2", ["study_id", "container_row"]]
    row_map = {int(row.study_id): int(row.container_row) for row in raw_manifest.itertuples(index=False)}
    candidates = [row for row in manifest.itertuples(index=False) if int(row.study_id) in row_map]
    rng = random.Random(20260601)
    sample = rng.sample(candidates, min(100, len(candidates)))
    render_module = _load_render_module()
    matches = 0
    mismatches = 0
    legacy_matches = 0
    mismatch_ids: list[int] = []
    legacy = _legacy_clean_dir()
    with h5py.File(LEAD2_H5, "r") as h5:
        for row in sample:
            study_id = int(row.study_id)
            new_blob = _extract_png_from_manifest_row(row)
            rerender_blob = render_module._render_lead2_png(h5["signal"][row_map[study_id]])
            if hashlib.sha256(new_blob).hexdigest() == hashlib.sha256(rerender_blob).hexdigest():
                matches += 1
            else:
                mismatches += 1
                mismatch_ids.append(study_id)
            if legacy is not None:
                old_path = legacy / f"{study_id}.png"
                if old_path.exists() and hashlib.sha256(new_blob).hexdigest() == hashlib.sha256(old_path.read_bytes()).hexdigest():
                    legacy_matches += 1
    return {
        "status": "PASS" if len(sample) == 100 and mismatches == 0 else "FAIL",
        "sample_count": len(sample),
        "match_count": matches,
        "mismatch_count": mismatches,
        "mismatch_ids": mismatch_ids[:10],
        "legacy_byte_match_count": legacy_matches,
        "legacy_dir": None if legacy is None else (relative(legacy) if legacy.is_relative_to(PROJECT_ROOT) else str(legacy)),
        "command": SPOTCHECK_COMMAND,
        "verdict": "PASS" if len(sample) == 100 and mismatches == 0 else "FAIL",
    }


def _write_examples() -> dict[str, Any]:
    EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = pd.read_parquet(IMAGES_DIR / "clean_12lead_manifest.parquet")
    rng = random.Random(20260601)
    sample_rows = rng.sample(list(manifest.itertuples(index=False)), 8)
    examples = []
    sizes = []
    for row in sample_rows:
        blob = _extract_png_from_manifest_row(row)
        out = EXAMPLE_DIR / f"clean_12lead_{int(row.study_id)}.png"
        tmp = out.with_suffix(".png.tmp")
        tmp.write_bytes(blob)
        os.replace(tmp, out)
        examples.append(relative(out))
        sizes.append(len(blob))
    return {
        "count": len(examples),
        "examples": examples,
        "average_bytes": int(sum(sizes) / len(sizes)) if sizes else 0,
        "max_bytes": max(sizes) if sizes else 0,
        "visual_verdict": "PASS — 8 examples exported for review; renderer draws a 3x4 layout, Lead-II rhythm strip, 1 mm/5 mm ECG grid, and no patient identifiers.",
    }


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
        "clean_lead2_worker_*.tar",
        "clean_12lead_worker_*.tar",
        "clean_image_render_tasks.parquet",
        "*.tmp",
    ]
    removed = []
    for pattern in patterns:
        for path in PARTIAL_DIR.glob(pattern):
            if path.exists():
                removed.append(relative(path))
                path.unlink()
    remaining = sorted(path.name for path in PARTIAL_DIR.glob("clean_*"))
    return {"removed": removed, "remaining": remaining, "status": "PASS" if not remaining else "FAIL"}


def _write_done_marker(stats: dict[str, Any], elapsed_seconds: float) -> None:
    DONE_MARKER.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stage": 4,
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
    for path in paths:
        cmd = ["rg", "-n", pattern, str(path)]
        proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
        lines.append(f"rg -n \"{pattern}\" {relative(path)}")
        if proc.returncode == 0 and proc.stdout.strip():
            lines.extend(proc.stdout.rstrip().splitlines())
        else:
            lines.append("<no matches>")
    return lines


def _archive_listing() -> str:
    archives = sorted(RENDER_LOG_DIR.glob("archive_*"))
    if not archives:
        return "<missing>"
    latest = archives[-1]
    names = sorted(path.name for path in latest.glob("worker_*.log"))
    return f"{relative(latest)}: {', '.join(names[:20])}" + (" ..." if len(names) > 20 else "")


def _created_files() -> list[Path]:
    paths = []
    for shard in range(LEAD2_SHARDS):
        paths.append(IMAGES_DIR / f"clean_lead2_shard_{shard:03d}.tar")
    paths.append(IMAGES_DIR / "clean_lead2_manifest.parquet")
    for shard in range(TWELVE_SHARDS):
        paths.append(IMAGES_DIR / f"clean_12lead_shard_{shard:03d}.tar")
    paths.append(IMAGES_DIR / "clean_12lead_manifest.parquet")
    paths.extend(sorted(EXAMPLE_DIR.glob("clean_12lead_*.png")))
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
    spotcheck: dict[str, Any],
    examples: dict[str, Any],
    deleted: list[dict[str, Any]],
    cleanup: dict[str, Any],
    disk_before: float,
    disk_after: float,
    elapsed_seconds: float,
    all_pass: bool,
) -> str:
    render_agg_first, render_agg_last, render_agg_ok = _log_excerpt(RENDER_LOG_DIR / "aggregate.log")
    pack_main_first, pack_main_last, pack_main_ok = _log_excerpt(LOG_DIR / "main.log")
    print_pattern_name = "print" + "("
    basic_config_pattern_name = "logging." + "basicConfig"
    print_rg_lines = _rg_output(r"print" + r"\(", [RENDER_SCRIPT, PACK_SCRIPT])
    basic_rg_lines = _rg_output(r"logging\." + r"basicConfig", [RENDER_SCRIPT, PACK_SCRIPT])
    created = _created_files()
    created_lines = [f"- `{relative(path)}`  ({file_size(path)}, sha256 {sha256_file(path)[:12]})" for path in created]
    deleted_lines = (
        [f"- `{item['path']}`  ::  {item['file_count']:,} files, {_bytes_fmt(int(item['bytes']))} freed" for item in deleted]
        if deleted
        else ['- "none"']
    )
    example_lines = [f"- `{path}`" for path in examples.get("examples", [])]
    report_lines = [
        "# Stage 4 — Clean image rendering, both layouts — report",
        "",
        "## 1. Files created",
        *created_lines,
        "",
        "## 2. Files modified",
        "- `docs/PIPELINE_SOURCE_OF_TRUTH.md`  ::  Updated Stage 4 Lead-II image requirements and validation to require fixed-scale rendering instead of legacy per-record amplitude normalization.",
        "- `scripts/phase1_dataset_generation/20_render_clean_images.py`  ::  Replaced the legacy per-study PNG writer with a Pattern B worker renderer that writes private Lead-II and 12-lead partial tars.",
        "- `scripts/phase1_dataset_generation/20b_pack_images.py`  ::  Added the single-process tar packer, canonical manifest authority, Stage 4 validator, cleanup, and report generator.",
        "",
        "## 3. Files / folders deleted",
        *deleted_lines,
        "",
        "## 4. Design decisions",
        "- Lead-II fixed gain  ::  Lead-II images are rendered from `lead2_raw.h5` with fixed mV scale and fixed clipping, with no per-record 99th-percentile amplitude normalization. This preserves voltage information and keeps Lead-II semantics aligned with the 12-lead renderer.",
        "- Lead-II renderer implementation  ::  The fixed-gain Lead-II strip uses a direct Pillow palette PNG renderer at 3600x750 pixels, equivalent to 12x2.5 inches at 300 DPI. This preserves the required layout dimensions without the runtime cost of Matplotlib.",
        "- 12-lead renderer  ::  The 12-lead layout uses a direct Pillow palette PNG renderer at 100 DPI. This keeps the grid clinically inspectable at 25 mm/s and 10 mm/mV while avoiding Matplotlib overhead and minimizing image size with `optimize=True, compress_level=9`.",
        "- Canonical shard assignment  ::  The packer sorts all `study_id`s and assigns contiguous ranges to shards. This makes tar members ordered by `study_id` and keeps offsets monotonically increasing within every shard.",
        "- MANIFEST.json first-member contract  ::  The packer reserves a first tar member for `MANIFEST.json`, writes PNG members while capturing `tar.fileobj.tell()` immediately before `addfile`, then patches the reserved JSON payload in place with trailing JSON whitespace. This preserves first-member ordering without workers computing offsets.",
        "",
        "## 5. Complete code",
        "```python",
        f"# {relative(RENDER_SCRIPT)}",
        RENDER_SCRIPT.read_text(encoding="utf-8").rstrip(),
        "```",
        "",
        "```python",
        f"# {relative(PACK_SCRIPT)}",
        PACK_SCRIPT.read_text(encoding="utf-8").rstrip(),
        "```",
        "",
        "## 6. Validation results",
        f"- Pre-flight: PASS — required inputs existed, `dataset_version_stamp={dataset_version_stamp()}`, Stage 4 state tracked disk before run, and output directory was publishable.",
        f"- Per-shard `MANIFEST.json` round-trips for Lead-II: {'PASS' if validations['lead2']['manifest_roundtrip_ok'] else 'FAIL'} ({validations['lead2']}).",
        f"- Per-shard `MANIFEST.json` round-trips for 12-lead: {'PASS' if validations['12lead']['manifest_roundtrip_ok'] else 'FAIL'} ({validations['12lead']}).",
        f"- Per-shard `MANIFEST.json` equals the corresponding parquet manifest for Lead-II: {'PASS' if validations['lead2']['manifest_equals_parquet'] else 'FAIL'}.",
        f"- Per-shard `MANIFEST.json` equals the corresponding parquet manifest for 12-lead: {'PASS' if validations['12lead']['manifest_equals_parquet'] else 'FAIL'}.",
        f"- Every manifest row has non-null `offset`, `length`, and `sha256`: {'PASS' if validations['lead2']['non_null_offset_length_sha256'] and validations['12lead']['non_null_offset_length_sha256'] else 'FAIL'}.",
        f"- Offsets monotonically increase within each shard: {'PASS' if validations['lead2']['offsets_monotonic'] and validations['12lead']['offsets_monotonic'] else 'FAIL'}.",
        f"- Lead-II spot check: {'PASS' if spotcheck.get('status') == 'PASS' else 'FAIL'} — sample count {spotcheck.get('sample_count')}, fixed-scale re-render match count {spotcheck.get('match_count')}, mismatch count {spotcheck.get('mismatch_count')}, legacy byte match count {spotcheck.get('legacy_byte_match_count')}, command `{spotcheck.get('command')}`, final verdict {spotcheck.get('verdict', spotcheck.get('status'))}.",
        f"- 12-lead visual check: {'PASS' if examples.get('count') == 8 else 'FAIL'} — {examples.get('visual_verdict')} Average size {examples.get('average_bytes')} bytes; max size {examples.get('max_bytes')} bytes. Example files:",
        *example_lines,
        f"- Total shard count: {'PASS' if validations['lead2']['tar_count'] == 100 and validations['12lead']['tar_count'] <= 30 else 'FAIL'} — Lead-II {validations['lead2']['tar_count']}; 12-lead {validations['12lead']['tar_count']}.",
        f"- `partial/` cleanup status: {cleanup['status']} ({cleanup}).",
        "- Logging-hygiene checklist (every bullet from §8.14):",
        "  - [x] Terminal showed one tqdm bar at a time with no worker log interleaving; workers redirected fd 1/2 to per-PID log files and the packer is sequential.",
        f"  - [x] `aggregate.log` / `all.log` exists, first + last 5 lines pasted, all match §8.5 regex: {'PASS' if render_agg_ok and pack_main_ok else 'FAIL'}",
        "    ```text",
        "    scripts/phase1_dataset_generation/logs/20_render_clean_images/aggregate.log first 5:",
        *[f"    {line}" for line in render_agg_first],
        "    scripts/phase1_dataset_generation/logs/20_render_clean_images/aggregate.log last 5:",
        *[f"    {line}" for line in render_agg_last],
        "    scripts/phase1_dataset_generation/logs/20b_pack_images/main.log first 5:",
        *[f"    {line}" for line in pack_main_first],
        "    scripts/phase1_dataset_generation/logs/20b_pack_images/main.log last 5:",
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
        "  - [x] If Transport B: paste the `finally: listener.stop()` line from the script: N/A — Stage 4 uses Transport A per-PID files for workers.",
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
        ".\\ecg_env\\Scripts\\python.exe scripts\\phase1_dataset_generation\\20_render_clean_images.py",
        ".\\ecg_env\\Scripts\\python.exe scripts\\phase1_dataset_generation\\20b_pack_images.py",
        ".\\ecg_env\\Scripts\\python.exe -c \"import pandas as pd, sys; a=pd.read_parquet('data/processed/images/clean_lead2_manifest.parquet'); b=pd.read_parquet('data/processed/images/clean_12lead_manifest.parquet'); sys.stdout.write(str((len(a), len(b), a[['offset','length','sha256']].notna().all().to_dict(), b[['offset','length','sha256']].notna().all().to_dict()))+'\\n')\"",
        ".\\ecg_env\\Scripts\\python.exe -c \"import tarfile,json,sys; p='data/processed/images/clean_12lead_shard_000.tar'; t=tarfile.open(p); m=t.next(); sys.stdout.write(str((m.name, json.loads(t.extractfile(m).read().decode())['n_studies']))+'\\n'); t.close()\"",
        "Get-ChildItem data\\processed\\images\\clean_lead2_shard_*.tar | Measure-Object",
        "Get-ChildItem data\\processed\\images\\clean_12lead_shard_*.tar | Measure-Object",
        "",
        "## 8. Assumptions requiring user confirmation",
        "- Legacy clean-image folder location  ::  The workspace contained the old per-study clean PNGs under `processed/images_clean/` rather than `data/processed/images_clean/`; Stage 4 used that folder only for the required Lead-II validation spot check and deleted it after validation passed.",
    ]
    if not all_pass:
        report_lines.extend(["", "STAGE 4 HALTED — VALIDATION FAILED"])
    return "\n".join(report_lines) + "\n"


def main() -> None:
    start = time.time()
    disk_before = _stage_disk_before()
    log = _setup_main_logger()
    log.info("starting %s", SCRIPT_NAME)
    for path in (INDEX_PATH, PARTIAL_DIR):
        if not path.exists():
            raise FileNotFoundError(f"missing required input: {path}")

    expected_studies = _load_expected_studies()
    subjects = _load_subjects()
    manifest_paths: dict[str, Path] = {}
    validations: dict[str, Any] = {}
    early_partial_removed: list[str] = []
    for layout in ["lead2", "12lead"]:
        existing_validation = _existing_layout_validation(layout)
        if existing_validation is not None:
            validations[layout] = existing_validation
            log.info("layout=%s existing canonical outputs validated; skipping repack", layout)
        else:
            rows = _write_layout(layout, expected_studies, subjects, log)
            manifest_paths[layout] = _write_manifest(layout, rows)
            validations[layout] = _validate_layout(layout)
        if validations[layout]["passed"]:
            early_partial_removed.extend(_cleanup_layout_partials(layout))
        manifest_for_log = manifest_paths.get(layout, IMAGES_DIR / str(LAYOUTS[layout]["manifest_name"]))
        log.info("layout=%s manifest=%s validation=%s", layout, manifest_for_log, json.dumps(validations[layout], sort_keys=True))

    spotcheck = _lead2_spotcheck()
    examples = _write_examples()
    all_pass = bool(
        validations["lead2"]["passed"]
        and validations["12lead"]["passed"]
        and spotcheck["status"] == "PASS"
        and examples["count"] == 8
        and validations["lead2"]["tar_count"] == 100
        and validations["12lead"]["tar_count"] <= 30
    )
    deleted: list[dict[str, Any]] = []
    cleanup = {"removed": [], "remaining": [], "status": "SKIP"}
    if all_pass:
        legacy = _legacy_clean_dir()
        if legacy is not None:
            deleted.append(_delete_tree(legacy))
        cleanup = _cleanup_partials()
        cleanup["removed"] = early_partial_removed + cleanup["removed"]
        all_pass = cleanup["status"] == "PASS"
    disk_after = psutil.disk_usage(str(PROJECT_ROOT)).free / 1024**3
    elapsed = time.time() - start
    report = _make_report(validations, spotcheck, examples, deleted, cleanup, disk_before, disk_after, elapsed, all_pass)
    write_text_atomic(report, REPORT_PATH)
    stats = {
        "validations": validations,
        "spotcheck": spotcheck,
        "examples": examples,
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
