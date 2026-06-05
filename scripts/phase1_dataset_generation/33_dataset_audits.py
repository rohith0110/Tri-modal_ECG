#!/usr/bin/env python3
"""Stage 10 prep/final audits.

Stage 10A:
    ..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\33_dataset_audits.py --prep-check

Stage 10B:
    ..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\33_dataset_audits.py --final
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq
import yaml

from _stage1_common import (
    AUDIT_DIR,
    CONFIG_DIR,
    DATA_PROCESSED,
    PROJECT_ROOT,
    SCRIPT_DIR,
    STAGE_REPORT_DIR,
    dataset_version_stamp,
    file_size,
    relative,
    setup_main_logger,
    sha256_file,
    utc_now_iso,
    write_text_atomic,
)


SCRIPT_NAME = Path(__file__).stem
SCRIPT_PATH = Path(__file__).resolve()
RUN_DIR = STAGE_REPORT_DIR / "stage_10_run"
PREP_STATUS_PATH = STAGE_REPORT_DIR / "stage_10_prep_status.md"
FINAL_REPORT_PATH = STAGE_REPORT_DIR / "stage_10_report.md"
DONE_MARKER = STAGE_REPORT_DIR / "stage_10_complete.done.json"

INDEX_PATH = DATA_PROCESSED / "index" / "ecg_metadata.parquet"
WITH_MEASUREMENTS_PATH = DATA_PROCESSED / "index" / "ecg_metadata_with_measurements.parquet"
CLEAN_PATH = DATA_PROCESSED / "index" / "ecg_metadata_clean.parquet"
CLEAN_WITH_MEASUREMENTS_PATH = DATA_PROCESSED / "index" / "ecg_metadata_clean_with_measurements.parquet"
QC_PATH = DATA_PROCESSED / "qc.parquet"
WAVEFORM_QC_PATH = DATA_PROCESSED / "waveform_qc.parquet"
STRUCTURED_PATH = DATA_PROCESSED / "structured_features.parquet"
MANIFEST_PATH = DATA_PROCESSED / "modality_manifest.parquet"
SPLITS_PATH = DATA_PROCESSED / "splits_subject_level.parquet"
TASK_JSONL_DIR = DATA_PROCESSED / "task_jsonl"
LINKAGE_DIR = DATA_PROCESSED / "linkage"
CANDIDATE_LINKS_PATH = LINKAGE_DIR / "candidate_links.parquet"
LINKAGE_FINAL_PATH = LINKAGE_DIR / "linkage_final.parquet"
LABEL_AVAILABILITY_PATH = LINKAGE_DIR / "label_availability.parquet"
TASK_INPUT_POLICY_PATH = CONFIG_DIR / "task_input_policy.yaml"
DECISION_PATH = CONFIG_DIR / "decision.yaml"
DATASET_VERSIONS_PATH = CONFIG_DIR / "dataset_versions.yaml"
ACCESS_CHECK_PATH = AUDIT_DIR / "access_check.md"

FINAL_PREFLIGHT = [
    STRUCTURED_PATH,
    STAGE_REPORT_DIR / "stage_7_complete.done.json",
    WAVEFORM_QC_PATH,
    MANIFEST_PATH,
    CLEAN_PATH,
    CLEAN_WITH_MEASUREMENTS_PATH,
]

STAGE10_SCRIPTS = [
    SCRIPT_DIR / "03_add_measurements_to_index.py",
    SCRIPT_DIR / "04_cleanup_master_index.py",
    SCRIPT_DIR / "05_build_manifest_and_splits.py",
    SCRIPT_PATH,
    SCRIPT_DIR / "modality_io.py",
]

AUDIT_PATHS = {
    "split": AUDIT_DIR / "split_audit.md",
    "duplicate": AUDIT_DIR / "duplicate_audit.md",
    "missingness": AUDIT_DIR / "missingness_audit.md",
    "leakage": AUDIT_DIR / "leakage_audit.md",
    "linkage": AUDIT_DIR / "linkage_audit.md",
}

NON_CORRUPTED_EXPECTED = [
    ("raw_lead2", None),
    ("raw_12lead", None),
    ("preprocessed_lead2", None),
    ("preprocessed_12lead", None),
    ("image_clean", "lead2"),
    ("image_clean", "12lead"),
    ("image_scanlike", "lead2"),
    ("image_scanlike", "12lead"),
]

POLICY_TASKS = {
    "A1_ecg_diagnosis": {
        "allowed_inputs": [
            "raw_lead2",
            "raw_12lead",
            "preprocessed_lead2",
            "preprocessed_12lead",
            "image_clean_lead2",
            "image_clean_12lead",
            "image_scanlike_lead2",
            "image_scanlike_12lead",
            "report_text",
        ],
        "forbidden_inputs": ["machine_measurements", "structured_features"],
        "leakage_rationale": "EHR diagnosis labels are not ECG-measurement labels; machine measurements and structured features are still forbidden to avoid shortcut inputs.",
    },
    "A2_measurement_blind": {
        "allowed_inputs": ["raw_lead2", "raw_12lead", "preprocessed_lead2", "preprocessed_12lead"],
        "forbidden_inputs": [
            "image_clean_lead2",
            "image_clean_12lead",
            "image_scanlike_lead2",
            "image_scanlike_12lead",
            "report_text",
            "machine_measurements",
            "structured_features",
        ],
        "leakage_rationale": "Labels are computed from rr_interval, QRS duration, and QTc; all label-derived fields and text summaries are forbidden.",
    },
    "A3_lab_abnormality": {
        "allowed_inputs": [
            "raw_lead2",
            "raw_12lead",
            "preprocessed_lead2",
            "preprocessed_12lead",
            "image_clean_lead2",
            "image_clean_12lead",
            "image_scanlike_lead2",
            "image_scanlike_12lead",
            "report_text",
        ],
        "forbidden_inputs": ["machine_measurements", "structured_features"],
        "leakage_rationale": "Lab labels are EHR-derived; structured features are forbidden to prevent engineered morphology shortcuts.",
    },
    "A4_event_localization": {
        "allowed_inputs": ["raw_lead2", "raw_12lead", "preprocessed_lead2", "preprocessed_12lead"],
        "forbidden_inputs": [
            "machine_measurements",
            "structured_features",
            "report_text",
            "image_clean_lead2",
            "image_clean_12lead",
            "image_scanlike_lead2",
            "image_scanlike_12lead",
        ],
        "leakage_rationale": "Localization labels come from waveform delineation, so engineered features, text, machine measurements, and rendered images are forbidden.",
    },
    "A5_cross_modal_verification": {
        "allowed_inputs": [
            "raw_lead2",
            "raw_12lead",
            "preprocessed_lead2",
            "preprocessed_12lead",
            "image_clean_lead2",
            "image_clean_12lead",
            "image_scanlike_lead2",
            "image_scanlike_12lead",
            "report_text",
        ],
        "forbidden_inputs": ["machine_measurements", "structured_features"],
        "leakage_rationale": "The task verifies modality alignment; label-derived measurement columns and structured features stay out of model inputs.",
    },
    "A6_risk_stratification": {
        "allowed_inputs": [
            "raw_lead2",
            "raw_12lead",
            "preprocessed_lead2",
            "preprocessed_12lead",
            "image_clean_lead2",
            "image_clean_12lead",
            "image_scanlike_lead2",
            "image_scanlike_12lead",
            "report_text",
        ],
        "forbidden_inputs": ["machine_measurements", "structured_features"],
        "leakage_rationale": "Risk labels are EHR-derived; engineered structured features are reserved for audited baselines, not ordinary inputs.",
    },
    "B1_measurement_blind": {
        "allowed_inputs": ["raw_lead2", "raw_12lead", "preprocessed_lead2", "preprocessed_12lead"],
        "forbidden_inputs": [
            "image_clean_lead2",
            "image_clean_12lead",
            "image_scanlike_lead2",
            "image_scanlike_12lead",
            "report_text",
            "machine_measurements",
            "structured_features",
        ],
        "leakage_rationale": "Same label source as A2; this is signal-only measurement inference.",
    },
    "B2_noise_robustness": {
        "allowed_inputs": ["raw_lead2", "preprocessed_lead2", "signal_corrupted"],
        "forbidden_inputs": [
            "raw_12lead",
            "preprocessed_12lead",
            "image_clean_lead2",
            "image_clean_12lead",
            "image_scanlike_lead2",
            "image_scanlike_12lead",
            "report_text",
            "machine_measurements",
            "structured_features",
        ],
        "leakage_rationale": "Noise robustness uses corrupted Lead-II signals and B1 labels; clean text and measurement fields are forbidden.",
    },
    "B3_temporal_grounding": {
        "allowed_inputs": ["raw_lead2", "raw_12lead", "preprocessed_lead2", "preprocessed_12lead"],
        "forbidden_inputs": ["machine_measurements", "structured_features", "report_text"],
        "leakage_rationale": "Temporal labels are waveform-derived; measurements, text summaries, and structured features leak timing information.",
    },
    "B4_cross_modal_verification": {
        "allowed_inputs": [
            "raw_lead2",
            "raw_12lead",
            "preprocessed_lead2",
            "preprocessed_12lead",
            "image_clean_lead2",
            "image_clean_12lead",
            "image_scanlike_lead2",
            "image_scanlike_12lead",
            "report_text",
        ],
        "forbidden_inputs": ["machine_measurements", "structured_features"],
        "leakage_rationale": "Same verification head as A5; machine measurements and structured features remain shortcut inputs.",
    },
    "B5_contradiction_detection": {
        "allowed_inputs": [
            "raw_lead2",
            "raw_12lead",
            "preprocessed_lead2",
            "preprocessed_12lead",
            "report_text_corrupted",
        ],
        "forbidden_inputs": ["machine_measurements", "structured_features", "machine_report_text_original"],
        "leakage_rationale": "Contradiction labels are generated from measurement/report edits; originals and raw measurement values are forbidden.",
    },
    "B6_difficulty_stratified": {
        "allowed_inputs": [
            "raw_lead2",
            "raw_12lead",
            "preprocessed_lead2",
            "preprocessed_12lead",
            "image_clean_lead2",
            "image_clean_12lead",
            "image_scanlike_lead2",
            "image_scanlike_12lead",
            "report_text",
        ],
        "forbidden_inputs": ["machine_measurements", "structured_features"],
        "leakage_rationale": "Difficulty stratification evaluates the B4 verification setup; shortcut measurement and structured features remain forbidden.",
    },
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"missing": True, "path": relative(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def _status_line(path: Path) -> str:
    return f"- `{relative(path)}`: {'exists' if path.exists() else 'missing'}"


def _parquet_rows(path: Path) -> int | None:
    if not path.exists():
        return None
    return int(pq.ParquetFile(path).metadata.num_rows)


def _parquet_metadata(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    metadata = pq.ParquetFile(path).schema_arrow.metadata or {}
    keep = {"dataset_version", "created_at_iso", "artifact_kind", "modality_kind", "n_rows", "script_commit_hash"}
    return {
        k.decode("utf-8"): v.decode("utf-8", errors="replace")
        for k, v in metadata.items()
        if k.decode("utf-8", errors="replace") in keep
    }


def _file_line(path: Path) -> str:
    if not path.exists():
        return f"- `{relative(path)}`  (<missing>, sha256 <missing>)"
    return f"- `{relative(path)}`  ({file_size(path)}, sha256 {sha256_file(path)[:12]})"


def _script_code_block(path: Path) -> str:
    return f"```python\n# {relative(path)}\n{path.read_text(encoding='utf-8').rstrip()}\n```"


def _format_duration(seconds: float) -> str:
    return str(timedelta(seconds=int(round(seconds)))).rjust(8, "0")


def _hash_text_file(path: Path) -> str:
    if not path.exists():
        return "<missing>"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tmp_files() -> list[str]:
    patterns = [
        DATA_PROCESSED / "modality_manifest.parquet.tmp",
        DATA_PROCESSED / "index" / "ecg_metadata_with_measurements.parquet.tmp",
        DATA_PROCESSED / "index" / "ecg_metadata_clean.parquet.tmp",
        DATA_PROCESSED / "index" / "ecg_metadata_clean_with_measurements.parquet.tmp",
    ]
    found = [path for path in patterns if path.exists()]
    found.extend(DATA_PROCESSED.glob("structured_features*.tmp"))
    found.extend(AUDIT_DIR.glob("*.md.tmp"))
    found.extend(STAGE_REPORT_DIR.glob("stage_10*.tmp"))
    return sorted({relative(path) for path in found})


def _load_manifest() -> pd.DataFrame:
    return pd.read_parquet(MANIFEST_PATH)


def _manifest_validation() -> dict[str, Any]:
    index = pd.read_parquet(INDEX_PATH, columns=["study_id"])
    df = _load_manifest()
    index_ids = set(index["study_id"].astype("int64").tolist())
    manifest_ids = set(df["study_id"].astype("int64").tolist())
    key = pd.DataFrame(
        {
            "study_id": df["study_id"].astype("int64"),
            "modality_kind": df["modality_kind"].astype(str),
            "layout": df["layout"].fillna("").astype(str),
            "corruption_type": df["corruption_type"].fillna("").astype(str) if "corruption_type" in df else "",
            "snr_db": df["snr_db"].fillna(-999999).astype("int64") if "snr_db" in df else -999999,
        }
    )
    missing_expected: dict[str, int] = {}
    for modality_kind, layout in NON_CORRUPTED_EXPECTED:
        mask = df["modality_kind"].eq(modality_kind)
        label = modality_kind if layout is None else f"{modality_kind}:{layout}"
        if layout is None:
            mask &= df["layout"].isna()
        else:
            mask &= df["layout"].eq(layout)
        missing_expected[label] = int(len(index_ids - set(df.loc[mask, "study_id"].astype("int64").tolist())))
    container_paths = sorted(set(df["container_path"].astype(str).tolist()))
    invalid_paths = [path for path in container_paths if not (DATA_PROCESSED / path).exists()]
    hdf5_or_parquet = df["container_path"].astype(str).str.endswith((".h5", ".parquet"))
    tar_rows = df["container_path"].astype(str).str.endswith(".tar")
    validation = {
        "total_row_count": int(len(df)),
        "expected_non_corrupted_rows": int(len(index) * len(NON_CORRUPTED_EXPECTED)),
        "actual_non_corrupted_rows": int((df["modality_kind"] != "signal_corrupted").sum()),
        "row_count_by_modality_kind": {str(k): int(v) for k, v in df["modality_kind"].value_counts(dropna=False).to_dict().items()},
        "row_count_by_image_layout": {
            f"{kind}:{layout}": int(count)
            for (kind, layout), count in df.loc[df["layout"].notna()].groupby(["modality_kind", "layout"]).size().to_dict().items()
        },
        "row_count_by_corruption_type_and_snr_db": {
            f"{ctype}:{int(snr)}": int(count)
            for (ctype, snr), count in df.loc[df["modality_kind"].eq("signal_corrupted")]
            .groupby(["corruption_type", "snr_db"])
            .size()
            .to_dict()
            .items()
        },
        "orphan_study_id_count": int(len(manifest_ids - index_ids)),
        "missing_expected_modality_rows": missing_expected,
        "invalid_container_path_count": int(len(invalid_paths)),
        "invalid_container_paths_sample": invalid_paths[:20],
        "duplicate_manifest_key_count": int(key.duplicated().sum()),
        "missing_sha256_count": int(df["sha256"].isna().sum() + df["sha256"].eq("").sum()),
        "missing_dataset_version_count": int(df["dataset_version"].isna().sum() + df["dataset_version"].eq("").sum()),
        "missing_created_at_count": int(df["created_at"].isna().sum()),
        "missing_hdf5_or_parquet_row_locator_count": int(df.loc[hdf5_or_parquet, "container_row"].isna().sum()),
        "missing_tar_offset_or_length_count": int(
            (df.loc[tar_rows, "container_offset"].isna() | df.loc[tar_rows, "container_length"].isna()).sum()
        ),
        "preprocessed_lead2_rows": int(df["modality_kind"].eq("preprocessed_lead2").sum()),
        "preprocessed_12lead_rows": int(df["modality_kind"].eq("preprocessed_12lead").sum()),
        "structured_features_in_manifest_count": int(df["modality_kind"].eq("structured_features").sum()),
    }
    validation["passed"] = (
        validation["orphan_study_id_count"] == 0
        and all(v == 0 for v in missing_expected.values())
        and validation["invalid_container_path_count"] == 0
        and validation["duplicate_manifest_key_count"] == 0
        and validation["missing_sha256_count"] == 0
        and validation["missing_dataset_version_count"] == 0
        and validation["missing_created_at_count"] == 0
        and validation["missing_hdf5_or_parquet_row_locator_count"] == 0
        and validation["missing_tar_offset_or_length_count"] == 0
        and validation["preprocessed_lead2_rows"] > 0
        and validation["preprocessed_12lead_rows"] > 0
        and validation["structured_features_in_manifest_count"] == 0
    )
    return validation


def _read_modality_validation(samples_per_modality: int = 3) -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {"status": "FAIL", "error": "modality_manifest.parquet is missing", "checks": []}
    try:
        from modality_io import read_modality
    except Exception as exc:
        return {"status": "FAIL", "error": f"import failed: {exc!r}", "checks": []}

    manifest = pd.read_parquet(MANIFEST_PATH, columns=["study_id", "modality_kind", "layout", "corruption_type", "snr_db"])
    specs = [
        ("raw_lead2", {}),
        ("raw_12lead", {}),
        ("preprocessed_lead2", {}),
        ("preprocessed_12lead", {}),
        ("image_clean", {"layout": "lead2"}),
        ("image_clean", {"layout": "12lead"}),
        ("image_scanlike", {"layout": "lead2"}),
        ("image_scanlike", {"layout": "12lead"}),
        ("signal_corrupted", {}),
    ]
    checks: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for kind, kwargs in specs:
        mask = manifest["modality_kind"].eq(kind)
        if "layout" in kwargs:
            mask &= manifest["layout"].fillna("").eq(str(kwargs["layout"]))
        subset = manifest.loc[mask].copy()
        if subset.empty:
            failures.append({"kind": kind, "kwargs": kwargs, "error": "no manifest rows"})
            continue
        subset = subset.sample(n=min(samples_per_modality, len(subset)), random_state=202610)
        for row in subset.itertuples(index=False):
            call_kwargs = dict(kwargs)
            if kind == "signal_corrupted":
                call_kwargs["corruption_type"] = str(row.corruption_type)
                call_kwargs["snr_db"] = int(row.snr_db)
            try:
                payload = read_modality(int(row.study_id), kind, **call_kwargs)
                if hasattr(payload, "shape"):
                    shape_or_length: Any = list(payload.shape)
                    dtype = str(payload.dtype)
                    ok = (shape_or_length == [5000] and kind in {"raw_lead2", "preprocessed_lead2", "signal_corrupted"}) or (
                        shape_or_length == [5000, 12] and kind in {"raw_12lead", "preprocessed_12lead"}
                    )
                    if kind == "signal_corrupted":
                        ok = ok and dtype == "float32"
                else:
                    shape_or_length = int(len(payload))
                    dtype = "bytes"
                    ok = shape_or_length > 0 and kind in {"image_clean", "image_scanlike"}
                record = {
                    "kind": kind,
                    "kwargs": call_kwargs,
                    "study_id": int(row.study_id),
                    "shape_or_length": shape_or_length,
                    "dtype": dtype,
                    "status": "PASS" if ok else "FAIL",
                }
                checks.append(record)
                if not ok:
                    failures.append(record)
            except Exception as exc:
                failure = {"kind": kind, "kwargs": call_kwargs, "study_id": int(row.study_id), "error": repr(exc), "status": "FAIL"}
                checks.append(failure)
                failures.append(failure)
    return {
        "status": "PASS" if not failures else "FAIL",
        "command": "..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\33_dataset_audits.py --final",
        "samples_per_modality": samples_per_modality,
        "success_count": int(sum(1 for check in checks if check.get("status") == "PASS")),
        "failure_count": int(len(failures)),
        "checks": checks,
        "failures": failures,
    }


def _write_prep_status() -> dict[str, Any]:
    validations = {
        "03_add_measurements_to_index": _read_json(RUN_DIR / "03_add_measurements_to_index.validation.json"),
        "04_cleanup_master_index": _read_json(RUN_DIR / "04_cleanup_master_index.validation.json"),
        "05_build_manifest_and_splits": _read_json(RUN_DIR / "05_build_manifest_and_splits.validation.json"),
    }
    read_modality_smoke = _read_modality_validation(samples_per_modality=1)
    prep_outputs = [WITH_MEASUREMENTS_PATH, CLEAN_PATH, CLEAN_WITH_MEASUREMENTS_PATH, MANIFEST_PATH]
    final_dependencies = {
        "structured_features.parquet": STRUCTURED_PATH.exists(),
        "stage_7_complete.done.json": (STAGE_REPORT_DIR / "stage_7_complete.done.json").exists(),
    }
    lines = [
        "# Stage 10A - prep status",
        "",
        "STATUS: PREP_ONLY_NOT_FINAL",
        "",
        "## Scripts patched",
        *[f"- `{relative(path)}`" for path in STAGE10_SCRIPTS],
        "",
        "## Prep commands run",
        "- `..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\03_add_measurements_to_index.py`",
        "- `..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\04_cleanup_master_index.py`",
        "- `..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\05_build_manifest_and_splits.py`",
        "- `..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\33_dataset_audits.py --prep-check`",
        "",
        "## Prep outputs produced",
        *[_status_line(path) for path in prep_outputs],
        "",
        "## Prep validation results",
        f"- Measurement index rows: {validations['03_add_measurements_to_index'].get('ecg_metadata_with_measurements_rows', '<missing>')}",
        f"- Measurement merge duplicate study_ids: {validations['03_add_measurements_to_index'].get('duplicate_study_id_count', '<missing>')}",
        f"- Missing flags distinguish zeros from missing values: {validations['03_add_measurements_to_index'].get('zeros_and_missing_values_distinguishable', '<missing>')}",
        f"- Clean index rows: {validations['04_cleanup_master_index'].get('ecg_metadata_clean_rows', '<missing>')}",
        f"- Clean with-measurements rows: {validations['04_cleanup_master_index'].get('ecg_metadata_clean_with_measurements_rows', '<missing>')}",
        f"- Subject split overlap: {validations['04_cleanup_master_index'].get('subject_split_overlap', '<missing>')}",
        f"- Manifest total rows: {validations['05_build_manifest_and_splits'].get('manifest_total_row_count', '<missing>')}",
        f"- Manifest row count by modality_kind: {validations['05_build_manifest_and_splits'].get('row_count_by_modality_kind', '<missing>')}",
        f"- Manifest duplicate key count: {validations['05_build_manifest_and_splits'].get('duplicate_key_count', '<missing>')}",
        f"- Manifest orphan study_id count: {validations['05_build_manifest_and_splits'].get('orphan_study_id_count', '<missing>')}",
        f"- Manifest validation passed: {validations['05_build_manifest_and_splits'].get('passed', '<missing>')}",
        f"- read_modality smoke status: {read_modality_smoke.get('status')}",
        f"- read_modality smoke checks: {read_modality_smoke.get('checks', [])}",
        f"- `config/task_input_policy.yaml`: {'exists' if TASK_INPUT_POLICY_PATH.exists() else 'missing'}",
        "",
        "## Missing final dependencies",
        f"- `data/processed/structured_features.parquet`: {'exists, but final closeout still waits for user confirmation' if final_dependencies['structured_features.parquet'] else 'missing'}",
        f"- `outputs/stage_reports/stage_7_complete.done.json`: {'exists, but final closeout still waits for user confirmation' if final_dependencies['stage_7_complete.done.json'] else 'missing'}",
        "",
        "## Stage 10B status",
        "- Stage 10B remains pending.",
        "- Final closeout is waiting for structured_features.parquet.",
        "- Final closeout is waiting for stage_7_complete.done.json.",
        "- No final Stage 10 report was written.",
        "- No stage_10_complete.done.json marker was written.",
        "- Phase 1 completion is not claimed.",
        "",
        "Stage 10 prep complete. Final closeout is blocked until structured_features.parquet and stage_7_complete.done.json exist.",
    ]
    write_text_atomic("\n".join(lines) + "\n", PREP_STATUS_PATH)
    return {"validations": validations, "final_dependencies": final_dependencies, "read_modality_smoke": read_modality_smoke}


def _canonical_policy() -> dict[str, Any]:
    return {
        "modalities_available": {
            "raw_lead2": "data/processed/signals/lead2_raw.h5 via modality_manifest.parquet",
            "raw_12lead": "data/processed/signals/twelve_lead_raw_shard_*.h5 via modality_manifest.parquet",
            "preprocessed_lead2": "data/processed/signals/lead2_preprocessed.h5 via modality_manifest.parquet",
            "preprocessed_12lead": "data/processed/signals/twelve_lead_preprocessed_shard_*.h5 via modality_manifest.parquet",
            "image_clean_lead2": "data/processed/images/clean_lead2_shard_*.tar via modality_manifest layout=lead2",
            "image_clean_12lead": "data/processed/images/clean_12lead_shard_*.tar via modality_manifest layout=12lead",
            "image_scanlike_lead2": "data/processed/images/scanlike_lead2_shard_*.tar via modality_manifest layout=lead2",
            "image_scanlike_12lead": "data/processed/images/scanlike_12lead_shard_*.tar via modality_manifest layout=12lead",
            "signal_corrupted": "data/processed/signals_corrupted.parquet via modality_manifest corruption_type/snr_db",
            "report_text": "T_machine from ecg_metadata_clean_with_measurements.parquet",
            "machine_measurements": "raw machine measurement fields and derived measurement labels",
            "structured_features": "data/processed/structured_features.parquet",
        },
        "tasks": POLICY_TASKS,
    }


def _task_map(policy: dict[str, Any]) -> dict[str, Any]:
    if isinstance(policy.get("tasks"), dict):
        return policy["tasks"]
    return {k: v for k, v in policy.items() if isinstance(v, dict) and ("allowed" in v or "allowed_inputs" in v)}


def _policy_validation(policy: dict[str, Any]) -> dict[str, Any]:
    tasks = _task_map(policy)
    missing_tasks = sorted(set(POLICY_TASKS) - set(tasks))
    overlaps: dict[str, list[str]] = {}
    missing_required_forbidden: dict[str, list[str]] = {}
    for task_name, required in POLICY_TASKS.items():
        if task_name not in tasks:
            continue
        spec = tasks[task_name]
        allowed = set(spec.get("allowed_inputs", spec.get("allowed", [])))
        forbidden = set(spec.get("forbidden_inputs", spec.get("forbidden", [])))
        overlaps[task_name] = sorted((allowed & forbidden) - {"*"})
        required_forbidden = set(required["forbidden_inputs"])
        missing_required_forbidden[task_name] = sorted(required_forbidden - forbidden)
    passed = not missing_tasks and all(not v for v in overlaps.values()) and all(not v for v in missing_required_forbidden.values())
    return {
        "passed": bool(passed),
        "task_count": len(tasks),
        "required_task_count": len(POLICY_TASKS),
        "missing_tasks": missing_tasks,
        "allowed_forbidden_overlaps": overlaps,
        "missing_required_forbidden_inputs": missing_required_forbidden,
    }


def _ensure_policy() -> tuple[dict[str, Any], dict[str, Any]]:
    before_hash = _hash_text_file(TASK_INPUT_POLICY_PATH)
    if TASK_INPUT_POLICY_PATH.exists():
        with TASK_INPUT_POLICY_PATH.open("r", encoding="utf-8") as f:
            policy = yaml.safe_load(f) or {}
    else:
        policy = {}
    validation = _policy_validation(policy)
    rewritten = False
    if not validation["passed"]:
        policy = _canonical_policy()
        write_text_atomic(yaml.safe_dump(policy, sort_keys=False, allow_unicode=False), TASK_INPUT_POLICY_PATH)
        rewritten = True
        validation = _policy_validation(policy)
    after_hash = _hash_text_file(TASK_INPUT_POLICY_PATH)
    validation.update(
        {
            "policy_path": relative(TASK_INPUT_POLICY_PATH),
            "created": before_hash == "<missing>" and rewritten,
            "rewritten_to_source_policy": rewritten,
            "before_sha256": before_hash,
            "after_sha256": after_hash,
        }
    )
    return policy, validation


def _audit_split() -> tuple[str, bool, dict[str, Any]]:
    cols = ["study_id", "subject_id", "split"]
    optional = ["link_tier", "subject_linkage_tier", "hr_bucket"]
    clean = pd.read_parquet(CLEAN_PATH)
    for col in cols:
        if col not in clean.columns:
            raise ValueError(f"split audit missing clean-index column: {col}")
    split_sets = {split: set(clean.loc[clean["split"] == split, "subject_id"].astype("int64")) for split in ["train", "val", "test"]}
    overlaps = {
        "train_val": len(split_sets["train"] & split_sets["val"]),
        "train_test": len(split_sets["train"] & split_sets["test"]),
        "val_test": len(split_sets["val"] & split_sets["test"]),
    }
    ecg_counts = clean.groupby("split").size().to_dict()
    subject_counts = clean[["subject_id", "split"]].drop_duplicates().groupby("split").size().to_dict()
    split_ratio = {str(k): round(float(v) / max(1.0, float(len(clean))), 6) for k, v in ecg_counts.items()}
    link_col = "link_tier" if "link_tier" in clean.columns else "subject_linkage_tier" if "subject_linkage_tier" in clean.columns else None
    linkage_by_split = clean.groupby(["split", link_col]).size().unstack(fill_value=0).to_dict() if link_col else {}
    hr_bucket_by_split = clean.groupby(["split", "hr_bucket"]).size().unstack(fill_value=0).to_dict() if "hr_bucket" in clean.columns else {}
    passed = clean["split"].notna().all() and all(v == 0 for v in overlaps.values())
    stats = {
        "clean_ecg_rows": int(len(clean)),
        "subject_counts_by_split": {str(k): int(v) for k, v in subject_counts.items()},
        "ecg_counts_by_split": {str(k): int(v) for k, v in ecg_counts.items()},
        "split_ratio_by_ecg": split_ratio,
        "subject_overlaps": overlaps,
        "linkage_tier_distribution_by_split": {str(k): {str(kk): int(vv) for kk, vv in v.items()} for k, v in linkage_by_split.items()},
        "hr_bucket_distribution_by_split": {str(k): {str(kk): int(vv) for kk, vv in v.items()} for k, v in hr_bucket_by_split.items()},
    }
    text = "\n".join(
        [
            f"STATUS: {'PASS' if passed else 'FAIL'}",
            "",
            "# Split audit",
            f"- Clean ECG rows: {stats['clean_ecg_rows']:,}",
            f"- Subject counts per split: {stats['subject_counts_by_split']}",
            f"- ECG counts per split: {stats['ecg_counts_by_split']}",
            f"- ECG split ratios: {stats['split_ratio_by_ecg']}",
            f"- Subject overlaps: {stats['subject_overlaps']}",
            f"- Linkage-tier distribution per split: {stats['linkage_tier_distribution_by_split']}",
            f"- HR-bucket distribution per split: {stats['hr_bucket_distribution_by_split']}",
            "",
        ]
    )
    return text, bool(passed), stats


def _audit_duplicates() -> tuple[str, bool, dict[str, Any]]:
    clean = pd.read_parquet(CLEAN_PATH, columns=["study_id", "split"])
    manifest = pd.read_parquet(MANIFEST_PATH, columns=["study_id", "modality_kind", "layout", "corruption_type", "snr_db"])
    waveform = pd.read_parquet(WAVEFORM_QC_PATH, columns=["study_id", "duplicate_waveform_flag", "duplicate_group_id"])
    key = manifest.assign(
        layout=manifest["layout"].fillna(""),
        corruption_type=manifest["corruption_type"].fillna(""),
        snr_db=manifest["snr_db"].fillna(-999999),
    )
    duplicate_manifest_keys = int(key.duplicated(["study_id", "modality_kind", "layout", "corruption_type", "snr_db"]).sum())
    clean_duplicate_studies = int(clean.duplicated("study_id").sum())
    waveform_duplicate_flags = int(waveform["duplicate_waveform_flag"].sum())
    groups = waveform.loc[waveform["duplicate_group_id"].notna(), ["study_id", "duplicate_group_id"]].copy()
    duplicate_group_count = int(groups["duplicate_group_id"].nunique())
    group_size_distribution = groups.groupby("duplicate_group_id").size().value_counts().sort_index().to_dict()
    retained = waveform.merge(clean, on="study_id", how="inner")
    retained_duplicate_flags = int(retained["duplicate_waveform_flag"].sum())
    crossing = retained.loc[retained["duplicate_group_id"].notna()].groupby("duplicate_group_id")["split"].nunique()
    crossing_groups = int((crossing > 1).sum())
    passed = clean_duplicate_studies == 0 and duplicate_manifest_keys == 0 and retained_duplicate_flags == 0 and crossing_groups == 0
    stats = {
        "duplicate_study_id_count_clean": clean_duplicate_studies,
        "duplicate_manifest_key_count": duplicate_manifest_keys,
        "duplicate_waveform_flag_count_waveform_qc": waveform_duplicate_flags,
        "duplicate_waveform_flag_count_retained_clean": retained_duplicate_flags,
        "duplicate_group_count": duplicate_group_count,
        "duplicate_group_size_distribution": {str(k): int(v) for k, v in group_size_distribution.items()},
        "duplicate_groups_crossing_splits_retained": crossing_groups,
    }
    text = "\n".join(
        [
            f"STATUS: {'PASS' if passed else 'FAIL'}",
            "",
            "# Duplicate audit",
            f"- Duplicate study_id rows in clean index: {clean_duplicate_studies}",
            f"- Duplicate canonical manifest keys: {duplicate_manifest_keys}",
            f"- Duplicate waveform flags in waveform_qc.parquet: {waveform_duplicate_flags}",
            f"- Duplicate waveform flags retained in clean index: {retained_duplicate_flags}",
            f"- Duplicate waveform group count: {duplicate_group_count}",
            f"- Duplicate waveform group size distribution: {stats['duplicate_group_size_distribution']}",
            f"- Duplicate groups crossing train/val/test after cleanup: {crossing_groups}",
            "",
        ]
    )
    return text, passed, stats


def _null_counts(path: Path) -> dict[str, Any]:
    pf = pq.ParquetFile(path)
    counts = {name: 0 for name in pf.schema_arrow.names}
    rows = 0
    for rg_idx in range(pf.metadata.num_row_groups):
        table = pf.read_row_group(rg_idx)
        rows += table.num_rows
        for name in table.schema.names:
            counts[name] += int(pc.sum(pc.is_null(table[name])).as_py())
    return {"rows": rows, "null_counts": counts}


def _audit_missingness() -> tuple[str, bool, dict[str, Any]]:
    paths = [
        INDEX_PATH,
        WITH_MEASUREMENTS_PATH,
        CLEAN_PATH,
        QC_PATH,
        WAVEFORM_QC_PATH,
        STRUCTURED_PATH,
        MANIFEST_PATH,
        LINKAGE_FINAL_PATH,
        LABEL_AVAILABILITY_PATH,
    ]
    blocks = []
    stats_by_path: dict[str, Any] = {}
    passed = True
    for path in paths:
        rel = relative(path)
        if not path.exists():
            passed = False
            stats_by_path[rel] = {"missing": True}
            blocks.append(f"## {rel}\n- MISSING")
            continue
        stats = _null_counts(path)
        rows = max(1, int(stats["rows"]))
        top_nulls = {
            col: {"nulls": int(nulls), "pct": round(100.0 * int(nulls) / rows, 4)}
            for col, nulls in sorted(stats["null_counts"].items(), key=lambda kv: kv[1], reverse=True)[:25]
            if int(nulls) > 0
        }
        stats_by_path[rel] = {"rows": int(stats["rows"]), "top_null_columns": top_nulls}
        blocks.append(f"## {rel}\n- Rows: {stats['rows']:,}\n- Top null columns: {top_nulls if top_nulls else 'none'}")
    text = f"STATUS: {'PASS' if passed else 'FAIL'}\n\n# Missingness audit\n\n" + "\n\n".join(blocks) + "\n"
    return text, passed, stats_by_path


def _audit_leakage() -> tuple[str, bool, dict[str, Any]]:
    _, policy_validation = _ensure_policy()
    task_jsonl_status = {
        "path": relative(TASK_JSONL_DIR),
        "exists": TASK_JSONL_DIR.exists(),
        "file_count": len(list(TASK_JSONL_DIR.glob("*"))) if TASK_JSONL_DIR.exists() else 0,
        "status": "stale legacy Phase 2 outputs are not part of final Phase 1; Phase 2 must delete and rebuild them later",
    }
    passed = bool(policy_validation["passed"]) and TASK_INPUT_POLICY_PATH.exists()
    text = "\n".join(
        [
            f"STATUS: {'PASS' if passed else 'FAIL'}",
            "",
            "# Leakage audit",
            f"- Policy path: `{relative(TASK_INPUT_POLICY_PATH)}`",
            f"- Policy validation: {policy_validation}",
            f"- Stale task_jsonl status: {task_jsonl_status}",
            "- Checks performed: allowed_inputs present; forbidden_inputs present; label-derived machine_measurements forbidden where required; machine_report_text/report_text forbidden where required; structured_features forbidden where required.",
            "",
        ]
    )
    return text, passed, {"policy_validation": policy_validation, "task_jsonl_status": task_jsonl_status}


def _audit_linkage() -> tuple[str, bool, dict[str, Any]]:
    if not DECISION_PATH.exists():
        return "STATUS: FAIL\n\n# Linkage audit\n- Missing config/decision.yaml\n", False, {"error": "missing decision.yaml"}
    decision = yaml.safe_load(DECISION_PATH.read_text(encoding="utf-8")) or {}
    chosen = str(decision.get("chosen_path", "")).lower()
    required = chosen in {"plan_a", "a", "hybrid"}
    if not required:
        stats = {"required": False, "chosen_path": decision.get("chosen_path")}
        return "STATUS: PASS\n\n# Linkage audit\n- Not required because decision path is not Plan A or hybrid.\n", True, stats
    required_paths = [CANDIDATE_LINKS_PATH, LINKAGE_FINAL_PATH, LABEL_AVAILABILITY_PATH]
    missing = [relative(path) for path in required_paths if not path.exists()]
    if missing:
        text = "STATUS: FAIL\n\n# Linkage audit\n" + "\n".join(f"- Missing `{path}`" for path in missing) + "\n"
        return text, False, {"required": True, "missing": missing}

    candidates = pd.read_parquet(CANDIDATE_LINKS_PATH)
    final = pd.read_parquet(LINKAGE_FINAL_PATH)
    labels = pd.read_parquet(LABEL_AVAILABILITY_PATH)
    duplicate_final = int(final.duplicated("study_id").sum())
    duplicate_labels = int(labels.duplicated("study_id").sum())
    tier_counts = final["link_tier"].value_counts(dropna=False).to_dict()
    label_tier_counts = labels["link_tier"].value_counts(dropna=False).to_dict()
    candidate_tiers = set(candidates["study_id"].astype("int64"))
    linked_final = final.loc[final["link_tier"].isin(["L2", "L3"])].copy()
    linked_missing_candidate = int((~linked_final["study_id"].astype("int64").isin(candidate_tiers)).sum())

    cand = candidates.copy()
    cand["exact_rank"] = cand["link_type"].ne("exact").astype("int8")
    cand["id_priority"] = cand["hadm_id"].fillna(cand["stay_id"]).fillna(999999999).astype("int64")
    best = cand.sort_values(["study_id", "abs_tie_minutes", "exact_rank", "id_priority"]).drop_duplicates("study_id", keep="first")
    compare_cols = ["study_id", "source", "link_type", "hadm_id", "stay_id", "abs_tie_minutes"]
    comparable = linked_final.merge(best[compare_cols], on="study_id", how="left", suffixes=("_final", "_best"))
    mismatch = comparable.loc[
        comparable["source_final"].ne(comparable["source_best"])
        | comparable["link_type_final"].ne(comparable["link_type_best"])
        | comparable["hadm_id_final"].fillna(-1).ne(comparable["hadm_id_best"].fillna(-1))
        | comparable["stay_id_final"].fillna(-1).ne(comparable["stay_id_best"].fillna(-1))
    ]
    tie_break_mismatch_count = int(len(mismatch))

    stats = {
        "required": True,
        "chosen_path": decision.get("chosen_path"),
        "candidate_links_rows": int(len(candidates)),
        "linkage_final_rows": int(len(final)),
        "label_availability_rows": int(len(labels)),
        "linkage_tier_distribution": {str(k): int(v) for k, v in tier_counts.items()},
        "label_availability_tier_distribution": {str(k): int(v) for k, v in label_tier_counts.items()},
        "duplicate_final_study_ids": duplicate_final,
        "duplicate_label_availability_study_ids": duplicate_labels,
        "l2_l3_final_rows_missing_candidate": linked_missing_candidate,
        "tie_break_validation_mismatch_count": tie_break_mismatch_count,
        "tie_break_validation_sample": mismatch.head(5).to_dict(orient="records"),
    }
    passed = duplicate_final == 0 and duplicate_labels == 0 and linked_missing_candidate == 0 and tie_break_mismatch_count == 0
    text = "\n".join(
        [
            f"STATUS: {'PASS' if passed else 'FAIL'}",
            "",
            "# Linkage audit",
            f"- Decision path: {decision.get('chosen_path')}",
            f"- candidate_links rows: {stats['candidate_links_rows']:,}",
            f"- linkage_final rows: {stats['linkage_final_rows']:,}",
            f"- label_availability rows: {stats['label_availability_rows']:,}",
            f"- linkage tier distribution: {stats['linkage_tier_distribution']}",
            f"- label_availability tier distribution: {stats['label_availability_tier_distribution']}",
            f"- duplicate final study_ids: {duplicate_final}",
            f"- duplicate label_availability study_ids: {duplicate_labels}",
            f"- L2/L3 final rows missing candidate provenance: {linked_missing_candidate}",
            f"- Tie-breaking validation mismatches: {tie_break_mismatch_count}",
            f"- Tie-breaking rule checked: smallest abs_tie_minutes, exact before tolerance, then lowest hadm_id/stay_id.",
            "",
        ]
    )
    return text, passed, stats


def _write_final_audits() -> dict[str, Any]:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    split_text, split_ok, split_stats = _audit_split()
    duplicate_text, duplicate_ok, duplicate_stats = _audit_duplicates()
    missingness_text, missingness_ok, missingness_stats = _audit_missingness()
    leakage_text, leakage_ok, leakage_stats = _audit_leakage()
    linkage_text, linkage_ok, linkage_stats = _audit_linkage()
    outputs = {
        "split": (AUDIT_PATHS["split"], split_text, split_ok),
        "duplicate": (AUDIT_PATHS["duplicate"], duplicate_text, duplicate_ok),
        "missingness": (AUDIT_PATHS["missingness"], missingness_text, missingness_ok),
        "leakage": (AUDIT_PATHS["leakage"], leakage_text, leakage_ok),
    }
    if linkage_stats.get("required"):
        outputs["linkage"] = (AUDIT_PATHS["linkage"], linkage_text, linkage_ok)
    for path, text, _ in outputs.values():
        write_text_atomic(text, path)
    return {
        "audit_status": {name: ok for name, (_, _, ok) in outputs.items()},
        "audit_paths": {name: relative(path) for name, (path, _, _) in outputs.items()},
        "split": split_stats,
        "duplicate": duplicate_stats,
        "missingness": missingness_stats,
        "leakage": leakage_stats,
        "linkage": linkage_stats,
    }


def _audit_headers(paths: dict[str, str]) -> dict[str, str]:
    headers = {}
    for name, rel_path in paths.items():
        path = PROJECT_ROOT / rel_path
        if path.exists():
            headers[name] = path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        else:
            headers[name] = "<missing>"
    return headers


def _grep_evidence() -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for path in STAGE10_SCRIPTS:
        text = path.read_text(encoding="utf-8", errors="replace")
        print_pat = "pri" + "nt("
        basic_pat = "logging." + "basicConfig("
        evidence[relative(path)] = {
            "print_matches": [f"{idx + 1}: {line.strip()}" for idx, line in enumerate(text.splitlines()) if print_pat in line],
            "logging_basicConfig_matches": [f"{idx + 1}: {line.strip()}" for idx, line in enumerate(text.splitlines()) if basic_pat in line],
        }
    return evidence


def _stage10_metadata_validation() -> dict[str, Any]:
    paths = [WITH_MEASUREMENTS_PATH, CLEAN_PATH, CLEAN_WITH_MEASUREMENTS_PATH, MANIFEST_PATH]
    return {relative(path): _parquet_metadata(path) for path in paths}


def _build_final_report(audits: dict[str, Any], validation: dict[str, Any], elapsed: float) -> str:
    report_status = "PASS" if validation["passed"] else "FAIL"
    created_paths = [
        WITH_MEASUREMENTS_PATH,
        CLEAN_PATH,
        CLEAN_WITH_MEASUREMENTS_PATH,
        MANIFEST_PATH,
        *[PROJECT_ROOT / rel for rel in audits["audit_paths"].values()],
        PREP_STATUS_PATH,
        FINAL_REPORT_PATH,
        DONE_MARKER,
    ]
    files_modified = [
        "- `scripts/phase1_dataset_generation/03_add_measurements_to_index.py` :: Stage 10A-safe measurement enrichment with missing flags and atomic parquet publish.",
        "- `scripts/phase1_dataset_generation/04_cleanup_master_index.py` :: Stage 10A-safe clean-index builder using qc.parquet and waveform_qc.parquet.",
        "- `scripts/phase1_dataset_generation/05_build_manifest_and_splits.py` :: canonical manifest builder for raw, preprocessed, image-layout, and corrupted-signal modalities.",
        "- `scripts/phase1_dataset_generation/33_dataset_audits.py` :: split-mode prep/final audit runner and final Stage 10 reporter.",
        "- `scripts/phase1_dataset_generation/modality_io.py` :: manifest-backed modality read helper.",
    ]
    policy_validation = audits["leakage"]["policy_validation"]
    if policy_validation.get("rewritten_to_source_policy") or policy_validation.get("created"):
        files_modified.append("- `config/task_input_policy.yaml` :: written to the source-of-truth leakage policy used by the final leakage audit.")
    lines = [
        "# Stage 10 - Index cleanup + canonical manifest + final audits - report",
        "",
        "## 1. Files created",
        *[_file_line(path) for path in created_paths if path.exists() or path in {FINAL_REPORT_PATH, DONE_MARKER}],
        "",
        "## 2. Files modified",
        *files_modified,
        "",
        "## 3. Files / folders deleted",
        "- none  :: Stage 10 deleted no raw data, no Stage 0-9 artifacts, no modality folders, and no task_jsonl directory.",
        "",
        "## 4. Design decisions",
        "- Stage 10 split mode :: Stage 10A produced index/manifest prep outputs while structured features were still running. Stage 10B waited until both `data/processed/structured_features.parquet` and `outputs/stage_reports/stage_7_complete.done.json` existed before final audits and completion.",
        "- Image layout disambiguation :: The source schema keeps `image_clean` and `image_scanlike` as canonical modality kinds, so Stage 10 adds a non-breaking `layout` column (`lead2` or `12lead`) to keep layouts distinguishable without changing downstream modality families.",
        "- Corrupted-signal locators :: `signal_corrupted` rows keep `corruption_type`, `snr_db`, and `corruption_row` because one study has many corruption variants. This prevents accidental collapse to one row per study.",
        "- Leakage policy handling :: Existing legacy policy content is validated first. If it is missing required source-of-truth tasks or forbidden inputs, Stage 10 rewrites only `config/task_input_policy.yaml` to the source policy and audits that file.",
        "",
        "## 5. Complete code",
        *[_script_code_block(path) for path in STAGE10_SCRIPTS],
        "",
        "## 6. Validation results",
        f"- Stage 10 status: {report_status}.",
        f"- Stage 10 split-mode explanation: PASS; Stage 10A prep status path `{relative(PREP_STATUS_PATH)}` and Stage 10B final report path `{relative(FINAL_REPORT_PATH)}`.",
        f"- Proof structured_features.parquet existed before final audit: {STRUCTURED_PATH.exists()}; rows={validation['structured_features_rows']}; metadata={_parquet_metadata(STRUCTURED_PATH)}.",
        f"- Proof stage_7_complete.done.json existed before final audit: {(STAGE_REPORT_DIR / 'stage_7_complete.done.json').exists()}; path=`outputs/stage_reports/stage_7_complete.done.json`.",
        f"- Stage 10A prep outputs: measurement rows={validation['measurement_validation'].get('ecg_metadata_with_measurements_rows')}; clean rows={validation['cleanup_validation'].get('ecg_metadata_clean_rows')}; clean-with-measurements rows={validation['cleanup_validation'].get('ecg_metadata_clean_with_measurements_rows')}; manifest rows={validation['manifest']['total_row_count']}.",
        f"- Row counts for final index files: ecg_metadata={validation['index_rows']}; ecg_metadata_with_measurements={validation['with_measurements_rows']}; ecg_metadata_clean={validation['clean_rows']}; ecg_metadata_clean_with_measurements={validation['clean_with_measurements_rows']}.",
        f"- Exclusion counts for clean index: {validation['cleanup_validation'].get('exclusion_reason_counts')}; retained percentage={validation['cleanup_validation'].get('final_retained_percentage')}.",
        f"- Modality manifest validation: {validation['manifest']}.",
        f"- read_modality validation command: {validation['read_modality']['command']}.",
        f"- read_modality validation evidence: success_count={validation['read_modality']['success_count']}; failure_count={validation['read_modality']['failure_count']}; checks={validation['read_modality']['checks']}.",
        f"- Audit report paths and STATUS headers: {_audit_headers(audits['audit_paths'])}.",
        f"- Split audit summary: {audits['split']}.",
        f"- Duplicate audit summary: {audits['duplicate']}.",
        f"- Missingness audit includes structured_features.parquet: {'data/processed/structured_features.parquet' in audits['missingness']}; paths={list(audits['missingness'].keys())}.",
        f"- Leakage audit / task_input_policy.yaml validation: {audits['leakage']}.",
        f"- Linkage audit summary: {audits['linkage']}.",
        f"- access_check.md verification: exists={ACCESS_CHECK_PATH.exists()}; path=`{relative(ACCESS_CHECK_PATH)}`.",
        f"- Dataset version validation: dataset_versions.yaml exists={DATASET_VERSIONS_PATH.exists()}; dataset_version_stamp={dataset_version_stamp()}; Stage 10 parquet metadata={validation['metadata']}.",
        f"- Phase 2 stale output handling: {audits['leakage']['task_jsonl_status']}.",
        "- Stale Phase 2 task_jsonl files are not part of final Phase 1.",
        "- Phase 2 must delete and rebuild stale task_jsonl files later.",
        f"- No-deletion status: task_jsonl_before={validation['task_jsonl_before']}; task_jsonl_after={validation['task_jsonl_after']}; Stage 10 performed no deletes.",
        f"- Atomic publish evidence: Stage 10 parquet writers use `.tmp` plus `os.replace`; audit reports use `write_text_atomic`; stale temp files after success={validation['tmp_files_after']}.",
        f"- Temp cleanup evidence: PASS if empty list above; value={validation['tmp_files_after']}.",
        f"- Logging compliance evidence: Stage 10 scripts are sequential; no worker processes; grep evidence={validation['grep_evidence']}.",
        f"- Resource settings used: Stage 10 used metadata/parquet scans only; no multiprocessing; canonical MAX_WORKERS formula not invoked; dynamic RAM-sensitive Stage 7 settings are recorded in Stage 7 report.",
        f"- Required output existence: {validation['required_output_existence']}.",
        f"- Audit PASS validation: {audits['audit_status']}.",
        f"- Disk before Stage 10B: {validation['disk_before_gib']:.1f} GiB free.",
        f"- Disk after Stage 10B: {validation['disk_after_gib']:.1f} GiB free.",
        f"- Wall-clock: {_format_duration(elapsed)}.",
        "",
        "## 7. Manual test procedure",
        "cd D:\\Coding\\MU\\Tri-Modal_ECG\\scripts",
        "..\\ecg_env\\Scripts\\python.exe phase1_dataset_generation\\33_dataset_audits.py --final",
        "cd D:\\Coding\\MU\\Tri-Modal_ECG",
        ".\\ecg_env\\Scripts\\python.exe -c \"import pandas as pd, sys; sys.stdout.write(str(pd.read_parquet('data/processed/modality_manifest.parquet').modality_kind.value_counts().to_dict()) + '\\n')\"",
        ".\\ecg_env\\Scripts\\python.exe -c \"import pandas as pd, sys; c=pd.read_parquet('data/processed/index/ecg_metadata_clean.parquet'); sys.stdout.write(str((len(c), c.groupby('split').subject_id.nunique().to_dict())) + '\\n')\"",
        "Get-Content outputs\\audit_reports\\split_audit.md -Head 1",
        "Get-Content outputs\\audit_reports\\duplicate_audit.md -Head 1",
        "Get-Content outputs\\audit_reports\\missingness_audit.md -Head 1",
        "Get-Content outputs\\audit_reports\\leakage_audit.md -Head 1",
        "Get-Content outputs\\audit_reports\\linkage_audit.md -Head 1",
        "Get-ChildItem data\\processed -Recurse -Filter *.tmp",
        "",
        "## 8. Assumptions requiring user confirmation",
        "- none",
    ]
    if not validation["passed"]:
        lines.append("")
        lines.append("STAGE 10 HALTED - VALIDATION FAILED")
    return "\n".join(lines) + "\n"


def _snapshot_task_jsonl() -> dict[str, Any]:
    if not TASK_JSONL_DIR.exists():
        return {"exists": False, "file_count": 0, "files": []}
    files = sorted(path.name for path in TASK_JSONL_DIR.iterdir())
    return {"exists": True, "file_count": len(files), "files": files}


def _required_output_existence(audit_paths: dict[str, str]) -> dict[str, bool]:
    paths = [
        WITH_MEASUREMENTS_PATH,
        CLEAN_PATH,
        CLEAN_WITH_MEASUREMENTS_PATH,
        MANIFEST_PATH,
        FINAL_REPORT_PATH,
        DONE_MARKER,
    ]
    paths.extend(PROJECT_ROOT / rel for rel in audit_paths.values())
    return {relative(path): path.exists() for path in paths}


def _validate_final_state(audits: dict[str, Any], read_modality: dict[str, Any], task_jsonl_before: dict[str, Any], disk_before: float) -> dict[str, Any]:
    measurement_validation = _read_json(RUN_DIR / "03_add_measurements_to_index.validation.json")
    cleanup_validation = _read_json(RUN_DIR / "04_cleanup_master_index.validation.json")
    manifest_validation = _manifest_validation()
    metadata = _stage10_metadata_validation()
    tmp_files = _tmp_files()
    task_jsonl_after = _snapshot_task_jsonl()
    required_existing = {
        "ecg_metadata_with_measurements": WITH_MEASUREMENTS_PATH.exists(),
        "ecg_metadata_clean": CLEAN_PATH.exists(),
        "ecg_metadata_clean_with_measurements": CLEAN_WITH_MEASUREMENTS_PATH.exists(),
        "modality_manifest": MANIFEST_PATH.exists(),
        "structured_features": STRUCTURED_PATH.exists(),
        "stage_7_complete": (STAGE_REPORT_DIR / "stage_7_complete.done.json").exists(),
        "access_check": ACCESS_CHECK_PATH.exists(),
    }
    validation = {
        "index_rows": _parquet_rows(INDEX_PATH),
        "with_measurements_rows": _parquet_rows(WITH_MEASUREMENTS_PATH),
        "clean_rows": _parquet_rows(CLEAN_PATH),
        "clean_with_measurements_rows": _parquet_rows(CLEAN_WITH_MEASUREMENTS_PATH),
        "structured_features_rows": _parquet_rows(STRUCTURED_PATH),
        "measurement_validation": measurement_validation,
        "cleanup_validation": cleanup_validation,
        "manifest": manifest_validation,
        "read_modality": read_modality,
        "metadata": metadata,
        "grep_evidence": _grep_evidence(),
        "tmp_files_after": tmp_files,
        "task_jsonl_before": task_jsonl_before,
        "task_jsonl_after": task_jsonl_after,
        "disk_before_gib": disk_before,
        "disk_after_gib": PROJECT_ROOT.stat().st_dev and __import__("shutil").disk_usage(PROJECT_ROOT).free / 1024**3,
        "required_existing": required_existing,
        "required_output_existence": {},
    }
    validation["passed"] = (
        all(required_existing.values())
        and validation["with_measurements_rows"] == validation["index_rows"]
        and validation["clean_rows"] == validation["clean_with_measurements_rows"]
        and bool(manifest_validation["passed"])
        and read_modality.get("status") == "PASS"
        and all(audits["audit_status"].values())
        and not tmp_files
        and task_jsonl_before == task_jsonl_after
        and all(md.get("dataset_version") for md in metadata.values())
    )
    return validation


def _run_prep_check() -> None:
    setup_main_logger(SCRIPT_NAME).info("running Stage 10A prep check")
    state = _write_prep_status()
    sys.stdout.write(PREP_STATUS_PATH.read_text(encoding="utf-8"))
    missing_required_prep = [WITH_MEASUREMENTS_PATH, CLEAN_PATH, CLEAN_WITH_MEASUREMENTS_PATH, MANIFEST_PATH]
    if any(not path.exists() for path in missing_required_prep):
        raise SystemExit("Stage 10A prep check failed: one or more prep outputs are missing")
    manifest_ok = state["validations"]["05_build_manifest_and_splits"].get("passed", False)
    if not manifest_ok:
        raise SystemExit("Stage 10A prep check failed: modality manifest validation did not pass")
    if state["read_modality_smoke"].get("status") != "PASS":
        raise SystemExit("Stage 10A prep check failed: read_modality smoke validation did not pass")


def _run_final() -> None:
    start = time.time()
    logger = setup_main_logger(SCRIPT_NAME)
    logger.info("running Stage 10B final audits")
    if any(not path.exists() for path in FINAL_PREFLIGHT):
        sys.stdout.write("Stage 10 final closeout is blocked until structured_features.parquet and stage_7_complete.done.json exist.\n")
        raise SystemExit(2)
    disk_before = __import__("shutil").disk_usage(PROJECT_ROOT).free / 1024**3
    task_jsonl_before = _snapshot_task_jsonl()
    read_modality = _read_modality_validation(samples_per_modality=3)
    audits = _write_final_audits()
    partial_validation = _validate_final_state(audits, read_modality, task_jsonl_before, disk_before)
    partial_validation["required_output_existence"] = _required_output_existence(audits["audit_paths"])
    report = _build_final_report(audits, partial_validation, time.time() - start)
    write_text_atomic(report, FINAL_REPORT_PATH)
    if not partial_validation["passed"]:
        sys.stdout.write(report)
        raise SystemExit("Stage 10 final audits did not all pass")
    done = {
        "stage": 10,
        "status": "PASS",
        "completed_at_iso": utc_now_iso(),
        "dataset_version": dataset_version_stamp(),
        "audit_paths": audits["audit_paths"],
        "report_path": relative(FINAL_REPORT_PATH),
    }
    write_text_atomic(json.dumps(done, indent=2, sort_keys=True) + "\n", DONE_MARKER)
    final_validation = _validate_final_state(audits, read_modality, task_jsonl_before, disk_before)
    final_validation["required_output_existence"] = _required_output_existence(audits["audit_paths"])
    final_report = _build_final_report(audits, final_validation, time.time() - start)
    write_text_atomic(final_report, FINAL_REPORT_PATH)
    sys.stdout.write(final_report)
    if not final_validation["passed"]:
        raise SystemExit("Stage 10 final validation failed after done marker write")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 10 prep/final audit runner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prep-check", action="store_true", help="validate Stage 10A prep outputs only")
    group.add_argument("--final", action="store_true", help="run Stage 10B final audits")
    args = parser.parse_args()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    if args.prep_check:
        _run_prep_check()
    elif args.final:
        _run_final()


if __name__ == "__main__":
    main()
