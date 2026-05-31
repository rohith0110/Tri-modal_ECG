#!/usr/bin/env python3
"""
00_lock_versions.py — Stage 0, Script 1
========================================
Detect installed Python + library versions, hash every raw input table,
record row counts, and write config/dataset_versions.yaml per §3.1 schema.

Sequential script (no multiprocessing). Logging per §8.13 (sequential scripts).

Run from: scripts/phase1_dataset_generation/
    cd D:\\Coding\\MU\\Tri-Modal_ECG\\scripts\\phase1_dataset_generation
    ..\\..\\ecg_env\\Scripts\\python.exe 00_lock_versions.py
"""

import hashlib
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths — all relative to PROJECT_ROOT per §2.4
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
CONFIG_DIR = PROJECT_ROOT / "config"
OUTPUT_FILE = CONFIG_DIR / "dataset_versions.yaml"

# ---------------------------------------------------------------------------
# Logging — sequential script per §8.13 (sequential scripts)
# ---------------------------------------------------------------------------
LOG_DIR = SCRIPT_DIR / "logs" / Path(__file__).stem
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("main")
logger.setLevel(logging.INFO)
fh = logging.FileHandler(LOG_DIR / "main.log", mode="w", encoding="utf-8")
sh = logging.StreamHandler(sys.stderr)
fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
fh.setFormatter(fmt)
sh.setFormatter(fmt)
logger.addHandler(fh)
logger.addHandler(sh)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sha256_file(filepath: Path, chunk_size: int = 1 << 20) -> str:
    """Return hex SHA256 of a file, streaming to keep RAM low."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def count_csv_rows(filepath: Path) -> int:
    """Count data rows in a plain CSV (not .gz). Header excluded."""
    import pandas as pd
    # For large files, use chunked reading
    count = 0
    for chunk in pd.read_csv(filepath, chunksize=500_000, usecols=[0]):
        count += len(chunk)
    return count


def count_csv_gz_rows(filepath: Path) -> int:
    """Count data rows in a .csv.gz file. Header excluded."""
    import pandas as pd
    count = 0
    for chunk in pd.read_csv(filepath, chunksize=500_000, compression="gzip",
                             usecols=[0], low_memory=False):
        count += len(chunk)
    return count


def yaml_str(val) -> str:
    """Format a value for YAML output."""
    if isinstance(val, str):
        return f'"{val}"'
    elif isinstance(val, bool):
        return "true" if val else "false"
    elif val is None:
        return "null"
    else:
        return str(val)


# ---------------------------------------------------------------------------
# Library version detection
# ---------------------------------------------------------------------------

# Canonical mapping from import name -> distribution/recording name.
# This is the curated list per §3.1; the scan check below verifies
# that every top-level import in scripts/phase1_dataset_generation/
# appears here.
_IMPORT_TO_DIST = {
    "numpy": "numpy",
    "pandas": "pandas",
    "pyarrow": "pyarrow",
    "h5py": "h5py",
    "wfdb": "wfdb",
    "neurokit2": "neurokit2",
    "matplotlib": "matplotlib",
    "cv2": "opencv_python",
    "torch": "torch",
    "yaml": "pyyaml",
    "psutil": "psutil",
    "scipy": "scipy",
    "sklearn": "scikit_learn",
    "tqdm": "tqdm",
    "PIL": "Pillow",
    # Standard-library modules that will appear in scans but don't
    # need version recording:
}

# Standard-library modules to ignore during the import scan
_STDLIB_MODULES = {
    "abc", "argparse", "ast", "collections", "concurrent", "contextlib",
    "copy", "csv", "ctypes", "dataclasses", "datetime", "enum",
    "functools", "gc", "glob", "gzip", "hashlib", "importlib", "inspect",
    "io", "itertools", "json", "logging", "math", "multiprocessing",
    "operator", "os", "pathlib", "pickle", "platform", "pprint",
    "queue", "random", "re", "shutil", "signal", "socket", "string",
    "struct", "subprocess", "sys", "tarfile", "tempfile", "textwrap",
    "threading", "time", "traceback", "typing", "unittest", "uuid",
    "warnings", "weakref", "zipfile",
}


def _scan_imports(directory: Path) -> set:
    """
    AST-scan every .py file under *directory* and return the set of
    top-level third-party module names imported.
    """
    import ast
    imports = set()
    for py_file in directory.glob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
    # Remove stdlib
    imports -= _STDLIB_MODULES
    return imports


def detect_library_versions() -> dict:
    """Detect versions of all libraries used in phase1 scripts."""
    versions = {}

    # Python
    vi = sys.version_info
    versions["python"] = f"{vi.major}.{vi.minor}.{vi.micro}"

    # Record version for every entry in the curated mapping
    dist_to_import = {}  # dist_name -> import_name
    for imp_name, dist_name in _IMPORT_TO_DIST.items():
        dist_to_import[dist_name] = imp_name

    for dist_name, imp_name in sorted(dist_to_import.items()):
        try:
            mod = __import__(imp_name)
            ver = getattr(mod, "__version__", "unknown")
            versions[dist_name] = ver
        except ImportError:
            versions[dist_name] = "NOT_INSTALLED"
            logger.warning(f"Library {dist_name} (import {imp_name}) not found")

    # --- Import-scan coverage check (per reviewer MINOR finding) ---
    scanned = _scan_imports(SCRIPT_DIR)
    uncovered = [m for m in sorted(scanned) if m not in _IMPORT_TO_DIST and m not in _STDLIB_MODULES]
    if uncovered:
        logger.warning(
            f"Import-scan found modules not in the curated library list: {uncovered}. "
            f"Add them to _IMPORT_TO_DIST in 00_lock_versions.py."
        )
    else:
        logger.info("Import-scan: all phase1 imports covered by the curated library list.")

    return versions


# ---------------------------------------------------------------------------
# Raw table inventory
# ---------------------------------------------------------------------------
# ECG raw tables (plain CSV)
ECG_RAW_TABLES = {
    "record_list": DATA_RAW / "record_list.csv",
    "machine_measurements": DATA_RAW / "machine_measurements.csv",
    "waveform_note_links": DATA_RAW / "waveform_note_links.csv",
    "machine_measurements_data_dictionary": DATA_RAW / "machine_measurements_data_dictionary.csv",
}

# MIMIC-IV Hosp tables (csv.gz) — only the ones referenced in §5.2
HOSP_TABLES = {
    "admissions": DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "admissions.csv.gz",
    "patients": DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "patients.csv.gz",
    "diagnoses_icd": DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "diagnoses_icd.csv.gz",
    "d_icd_diagnoses": DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "d_icd_diagnoses.csv.gz",
    "labevents": DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "labevents.csv.gz",
    "d_labitems": DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "d_labitems.csv.gz",
    "prescriptions": DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "prescriptions.csv.gz",
    "emar": DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "emar.csv.gz",
    "transfers": DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "transfers.csv.gz",
    "services": DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "services.csv.gz",
}

# MIMIC-IV ED tables (csv.gz)
ED_TABLES = {
    "edstays": DATA_RAW / "mimic-iv-ed-2.2" / "ed" / "edstays.csv.gz",
    "diagnosis": DATA_RAW / "mimic-iv-ed-2.2" / "ed" / "diagnosis.csv.gz",
    "triage": DATA_RAW / "mimic-iv-ed-2.2" / "ed" / "triage.csv.gz",
    "vitalsign": DATA_RAW / "mimic-iv-ed-2.2" / "ed" / "vitalsign.csv.gz",
    "medrecon": DATA_RAW / "mimic-iv-ed-2.2" / "ed" / "medrecon.csv.gz",
    "pyxis": DATA_RAW / "mimic-iv-ed-2.2" / "ed" / "pyxis.csv.gz",
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    logger.info("=" * 60)
    logger.info("00_lock_versions.py — Stage 0, Script 1")
    logger.info("=" * 60)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Detect library versions
    logger.info("Detecting installed library versions...")
    lib_versions = detect_library_versions()
    for name, ver in lib_versions.items():
        logger.info(f"  {name}: {ver}")

    # 2. Get current timestamp
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    date_accessed = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 3. Hash and count ECG raw tables
    logger.info("Hashing and counting ECG raw tables...")
    ecg_table_info = {}
    for name, path in ECG_RAW_TABLES.items():
        if not path.exists():
            logger.error(f"  MISSING: {path}")
            ecg_table_info[name] = {"path": str(path.relative_to(PROJECT_ROOT)),
                                    "exists": False, "rows": 0,
                                    "sha256": "MISSING"}
            continue
        logger.info(f"  Hashing {name}...")
        sha = sha256_file(path)
        logger.info(f"  Counting rows in {name}...")
        rows = count_csv_rows(path)
        ecg_table_info[name] = {
            "path": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "exists": True,
            "rows": rows,
            "sha256": sha,
        }
        logger.info(f"    {name}: {rows:,} rows, sha256={sha[:16]}...")

    # 4. Hash and count Hosp tables (skip row counting for labevents — too slow;
    #    use the value from access_check.json if available, else count)
    logger.info("Hashing and counting MIMIC-IV Hosp tables...")
    hosp_table_info = {}
    for name, path in HOSP_TABLES.items():
        if not path.exists():
            logger.error(f"  MISSING: {path}")
            hosp_table_info[name] = {"exists": False, "rows": 0,
                                     "sha256": "MISSING"}
            continue
        logger.info(f"  Hashing {name}...")
        sha = sha256_file(path)
        if name == "labevents":
            # labevents is ~2.5 GB compressed, 158M rows — fully counted each run
            logger.info(f"  Counting rows in {name} (large file, may take ~2 min)...")
            rows = count_csv_gz_rows(path)
        else:
            logger.info(f"  Counting rows in {name}...")
            rows = count_csv_gz_rows(path)
        hosp_table_info[name] = {
            "path": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "exists": True,
            "rows": rows,
            "sha256": sha,
        }
        logger.info(f"    {name}: {rows:,} rows, sha256={sha[:16]}...")

    # 5. Hash and count ED tables
    logger.info("Hashing and counting MIMIC-IV ED tables...")
    ed_table_info = {}
    for name, path in ED_TABLES.items():
        if not path.exists():
            logger.error(f"  MISSING: {path}")
            ed_table_info[name] = {"exists": False, "rows": 0,
                                   "sha256": "MISSING"}
            continue
        logger.info(f"  Hashing {name}...")
        sha = sha256_file(path)
        logger.info(f"  Counting rows in {name}...")
        rows = count_csv_gz_rows(path)
        ed_table_info[name] = {
            "path": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "exists": True,
            "rows": rows,
            "sha256": sha,
        }
        logger.info(f"    {name}: {rows:,} rows, sha256={sha[:16]}...")

    # 6. Hash record_list.csv for the §3.1 sha256_of_record_list field
    record_list_sha = ecg_table_info.get("record_list", {}).get("sha256", "MISSING")

    # 7. Write YAML manually (avoid pyyaml reordering / formatting issues)
    logger.info(f"Writing {OUTPUT_FILE}...")

    lines = []
    lines.append("# Dataset version lock — generated by 00_lock_versions.py")
    lines.append(f"# Generated: {now_iso}")
    lines.append(f"# Do not edit manually. Re-run 00_lock_versions.py to regenerate.")
    lines.append("")
    lines.append("mimic_iv_ecg:")
    lines.append('  version: "1.0"')
    lines.append('  source_path: "data/raw/files/"')
    lines.append("  row_counts:")
    lines.append(f"    record_list_csv: {ecg_table_info.get('record_list', {}).get('rows', 0)}")
    lines.append(f"    machine_measurements_csv: {ecg_table_info.get('machine_measurements', {}).get('rows', 0)}")
    lines.append(f'  date_accessed: "{date_accessed}"')
    lines.append(f'  sha256_of_record_list: "{record_list_sha}"')
    lines.append("  table_checksums:")
    for name, info in ecg_table_info.items():
        lines.append(f'    {name}: "{info.get("sha256", "MISSING")}"')
    lines.append("")

    lines.append("mimic_iv_hosp:")
    lines.append('  version: "3.1"')
    lines.append('  source_path: "data/raw/mimic-iv-hosp-3.1/"')
    lines.append(f'  date_accessed: "{date_accessed}"')
    lines.append("  table_row_counts:")
    for name, info in hosp_table_info.items():
        lines.append(f"    {name}: {info.get('rows', 0)}")
    lines.append("  table_checksums:")
    for name, info in hosp_table_info.items():
        lines.append(f'    {name}: "{info.get("sha256", "MISSING")}"')
    lines.append("")

    lines.append("mimic_iv_ed:")
    lines.append('  version: "2.2"')
    lines.append('  source_path: "data/raw/mimic-iv-ed-2.2/"')
    lines.append(f'  date_accessed: "{date_accessed}"')
    lines.append("  table_row_counts:")
    for name, info in ed_table_info.items():
        lines.append(f"    {name}: {info.get('rows', 0)}")
    lines.append("  table_checksums:")
    for name, info in ed_table_info.items():
        lines.append(f'    {name}: "{info.get("sha256", "MISSING")}"')
    lines.append("")

    lines.append("libraries:")
    for name, ver in lib_versions.items():
        lines.append(f'  {name}: "{ver}"')
    lines.append("")

    lines.append('dataset_version_stamp: "v2.0.0"')
    lines.append("")

    # Write atomically: write to .tmp then os.replace per §7.5
    tmp_path = OUTPUT_FILE.with_suffix(".yaml.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.replace(tmp_path, OUTPUT_FILE)

    elapsed = time.time() - t0
    logger.info(f"config/dataset_versions.yaml written successfully.")
    logger.info(f"Elapsed: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    logger.info("=" * 60)
    logger.info("00_lock_versions.py COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
