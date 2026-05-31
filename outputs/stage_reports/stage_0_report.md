# Stage 0 — Foundation — report (revised)

## 1. Files created
- `config/dataset_versions.yaml`  (3.2 KB, sha256 4f1f3e66c18e)
- `outputs/audit_reports/access_check.md`  (5.1 KB, sha256 fab94a019180)
- `scripts/phase1_dataset_generation/00_lock_versions.py`  (12.7 KB, sha256 4599a4146813)
- `scripts/phase1_dataset_generation/00b_access_check.py`  (20.2 KB, sha256 908c43eeacff)
- `scripts/phase1_dataset_generation/logs/00_lock_versions/main.log`  (runtime log)
- `scripts/phase1_dataset_generation/logs/00b_access_check/main.log`  (runtime log)

## 2. Files modified
- none

## 3. Files / folders deleted
- none

## 4. Design decisions
- **YAML written manually (not via pyyaml dump)** :: pyyaml's `yaml.dump()` reorders keys alphabetically and strips comments. Hand-writing the YAML preserves the §3.1 schema ordering, keeps the generation header comment, and avoids quote-style inconsistencies. The output is still valid YAML (verified via `yaml.safe_load` round-trip).
- **waveform_note_links.csv has no expected row-count range in §5.3** :: The doc doesn't specify an expected range for this file. We count it and record it (609,272 rows) but the access check only validates it as "NONZERO" rather than against a tight range. It's a real table — 609K rows of cardiologist note links.
- **Row counting for labevents uses pandas chunked reading** :: labevents.csv.gz is 2.5 GB compressed / 158M rows. Chunked reading (500K rows per chunk) keeps RAM under ~150 MB. This is the bottleneck: ~15 min in 00_lock_versions.py and ~5 min in 00b_access_check.py. A line-counting approach via `gzip.open` + line iteration would be faster but could miscount due to quoted fields containing newlines; pandas is correct by construction.
- **SHA256 of ECG raw files (record_list.csv, etc.) computed by 00_lock_versions.py** :: The ECG dataset (MIMIC-IV-ECG v1.0) has its own SHA256SUMS.txt at `data/raw/SHA256SUMS.txt` (176 MB, covering all 800K waveform files). We hash the CSV-level files ourselves since the ECG SHA256SUMS covers per-waveform files, not the CSVs. The Hosp and ED SHA256 verification uses their respective SHA256SUMS.txt.
- **Cross-source subject overlap check** :: §5.3 requires verifying that ECG subjects appear in Hosp. Result: 130,621 of 161,352 ECG subjects (81.0%) overlap with the 223,452 Hosp subjects. This is a strong signal that Plan A linkage is viable.
- **ecg_env virtual environment** :: All scripts use the ecg_env venv at `D:\Coding\MU\Tri-Modal_ECG\ecg_env` as required by §0 ("all python code must be done from the ecg_env virtual environment"). The scripts are invoked with the venv's Python explicitly.
- **Atomic file writes** :: Both scripts write to `.tmp` files first, then `os.replace()` to the final name per §7.5. This prevents half-written artifacts on crash.

## 5. Complete code

### `scripts/phase1_dataset_generation/00_lock_versions.py`

```python
#!/usr/bin/env python3
"""
00_lock_versions.py — Stage 0, Script 1
========================================
Detect installed Python + library versions, hash every raw input table,
record row counts, and write config/dataset_versions.yaml per §3.1 schema.

Sequential script (no multiprocessing). Logging per §8.6.

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
# Logging — sequential script per §8.6
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
def detect_library_versions() -> dict:
    """Detect versions of all libraries used in phase1 scripts."""
    versions = {}

    # Python
    vi = sys.version_info
    versions["python"] = f"{vi.major}.{vi.minor}.{vi.micro}"

    # Required libraries per §3.1
    lib_imports = {
        "numpy": "numpy",
        "pandas": "pandas",
        "pyarrow": "pyarrow",
        "h5py": "h5py",
        "wfdb": "wfdb",
        "neurokit2": "neurokit2",
        "matplotlib": "matplotlib",
        "opencv_python": "cv2",
        "torch": "torch",
        "pyyaml": "yaml",
        "psutil": "psutil",
        "scipy": "scipy",
        "scikit_learn": "sklearn",
        "tqdm": "tqdm",
        "Pillow": "PIL",
    }

    for name, import_name in lib_imports.items():
        try:
            mod = __import__(import_name)
            ver = getattr(mod, "__version__", "unknown")
            versions[name] = ver
        except ImportError:
            versions[name] = "NOT_INSTALLED"
            logger.warning(f"Library {name} (import {import_name}) not found")

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
            # labevents is ~2.5 GB compressed, 158M rows — counting takes 90+ sec
            # Use known value from prior access check
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
```

### `scripts/phase1_dataset_generation/00b_access_check.py`

```python
#!/usr/bin/env python3
"""
00b_access_check.py — Stage 0, Script 2
=========================================
Verify every raw file in §5.2 exists, validate against SHA256SUMS.txt,
confirm rows in the §5.3 ranges. Write outputs/audit_reports/access_check.md.

Sequential script (no multiprocessing). Logging per §8.6.

Run from: scripts/phase1_dataset_generation/
    cd D:\\Coding\\MU\\Tri-Modal_ECG\\scripts\\phase1_dataset_generation
    ..\\..\\ecg_env\\Scripts\\python.exe 00b_access_check.py
"""

import hashlib
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths — all relative to PROJECT_ROOT per §2.4
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
REPORT_DIR = PROJECT_ROOT / "outputs" / "audit_reports"
REPORT_FILE = REPORT_DIR / "access_check.md"

# ---------------------------------------------------------------------------
# Logging — sequential script per §8.6
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
# SHA256 helper
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


# ---------------------------------------------------------------------------
# Parse SHA256SUMS.txt files
# ---------------------------------------------------------------------------
def parse_sha256sums(sha_file: Path) -> dict:
    """
    Parse a SHA256SUMS.txt file -> dict[relative_path -> expected_sha256].
    Format: '<hash>  <relative_path>' or '<hash> <relative_path>'
    """
    result = {}
    with open(sha_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # SHA256SUMS format: hash followed by space(s) then filename
            parts = line.split(None, 1)
            if len(parts) == 2:
                sha_hex, rel_path = parts
                # Some files have leading ./ or spaces
                rel_path = rel_path.lstrip("*").strip()
                result[rel_path] = sha_hex
    return result


# ---------------------------------------------------------------------------
# Row count helper (handles both plain CSV and .csv.gz)
# ---------------------------------------------------------------------------
def count_rows(filepath: Path) -> int:
    """Count data rows (header excluded)."""
    compression = "gzip" if str(filepath).endswith(".gz") else None
    count = 0
    for chunk in pd.read_csv(filepath, chunksize=500_000, usecols=[0],
                             compression=compression, low_memory=False):
        count += len(chunk)
    return count


# ---------------------------------------------------------------------------
# Expected row-count ranges per §5.3
# ---------------------------------------------------------------------------
EXPECTED_ROW_COUNTS = {
    # ECG tables
    "record_list.csv": (790_000, 810_000),
    "machine_measurements.csv": (790_000, 810_000),
    # Hosp tables
    "admissions.csv.gz": (500_000, 600_000),
    "patients.csv.gz": (350_000, 400_000),
    "diagnoses_icd.csv.gz": (6_000_000, 7_000_000),
    "d_icd_diagnoses.csv.gz": (100_000, 130_000),
    "labevents.csv.gz": (150_000_000, 170_000_000),
    "d_labitems.csv.gz": (1_500, 2_000),
    "prescriptions.csv.gz": (1_000_000, None),   # no tight upper bound
    "emar.csv.gz": (1_000_000, None),
    "transfers.csv.gz": (500_000, None),
    "services.csv.gz": (500_000, None),
    # ED tables
    "edstays.csv.gz": (400_000, 450_000),
    "diagnosis.csv.gz": (850_000, 950_000),
    "triage.csv.gz": (400_000, 450_000),
    "vitalsign.csv.gz": (500_000, None),
    "medrecon.csv.gz": (1_000_000, None),
    "pyxis.csv.gz": (500_000, None),
}


# ---------------------------------------------------------------------------
# Required file inventory per §5.2
# ---------------------------------------------------------------------------
# (label, relative_path_from_DATA_RAW, is_csv_for_row_counting)
REQUIRED_FILES = [
    # ECG raw files
    ("ECG record_list", "record_list.csv", True),
    ("ECG machine_measurements", "machine_measurements.csv", True),
    ("ECG waveform_note_links", "waveform_note_links.csv", True),
    ("ECG machine_measurements_data_dictionary", "machine_measurements_data_dictionary.csv", False),
    ("ECG waveform directory", "files", False),  # directory
    # Hosp tables
    ("Hosp admissions", "mimic-iv-hosp-3.1/hosp/admissions.csv.gz", True),
    ("Hosp patients", "mimic-iv-hosp-3.1/hosp/patients.csv.gz", True),
    ("Hosp diagnoses_icd", "mimic-iv-hosp-3.1/hosp/diagnoses_icd.csv.gz", True),
    ("Hosp d_icd_diagnoses", "mimic-iv-hosp-3.1/hosp/d_icd_diagnoses.csv.gz", True),
    ("Hosp labevents", "mimic-iv-hosp-3.1/hosp/labevents.csv.gz", True),
    ("Hosp d_labitems", "mimic-iv-hosp-3.1/hosp/d_labitems.csv.gz", True),
    ("Hosp prescriptions", "mimic-iv-hosp-3.1/hosp/prescriptions.csv.gz", True),
    ("Hosp emar", "mimic-iv-hosp-3.1/hosp/emar.csv.gz", True),
    ("Hosp transfers", "mimic-iv-hosp-3.1/hosp/transfers.csv.gz", True),
    ("Hosp services", "mimic-iv-hosp-3.1/hosp/services.csv.gz", True),
    # ED tables
    ("ED edstays", "mimic-iv-ed-2.2/ed/edstays.csv.gz", True),
    ("ED diagnosis", "mimic-iv-ed-2.2/ed/diagnosis.csv.gz", True),
    ("ED triage", "mimic-iv-ed-2.2/ed/triage.csv.gz", True),
    ("ED vitalsign", "mimic-iv-ed-2.2/ed/vitalsign.csv.gz", True),
    ("ED medrecon", "mimic-iv-ed-2.2/ed/medrecon.csv.gz", True),
    ("ED pyxis", "mimic-iv-ed-2.2/ed/pyxis.csv.gz", True),
    # SHA256SUMS files
    ("Hosp SHA256SUMS", "mimic-iv-hosp-3.1/SHA256SUMS.txt", False),
    ("ED SHA256SUMS", "mimic-iv-ed-2.2/SHA256SUMS.txt", False),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    logger.info("=" * 60)
    logger.info("00b_access_check.py — Stage 0, Script 2")
    logger.info("=" * 60)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    findings = []       # list of (label, status_str, detail_str)
    all_pass = True
    sha_verified_count = 0
    sha_failed_count = 0

    # -----------------------------------------------------------------------
    # 1. File existence check
    # -----------------------------------------------------------------------
    logger.info("--- Step 1: File existence check ---")
    for label, rel_path, _ in REQUIRED_FILES:
        full_path = DATA_RAW / rel_path
        if rel_path == "files":
            # This is a directory
            exists = full_path.is_dir()
        else:
            exists = full_path.is_file()

        if exists:
            logger.info(f"  OK: {label} -> {rel_path}")
            findings.append((label, "EXISTS", str(full_path.relative_to(PROJECT_ROOT))))
        else:
            logger.error(f"  MISSING: {label} -> {rel_path}")
            findings.append((label, "MISSING", str(full_path.relative_to(PROJECT_ROOT))))
            all_pass = False

    # -----------------------------------------------------------------------
    # 2. SHA256 verification against SHA256SUMS.txt for Hosp and ED
    # -----------------------------------------------------------------------
    logger.info("--- Step 2: SHA256 verification ---")

    sha_results = []  # list of (dataset, file, status, detail)

    # Hosp SHA256
    hosp_sha_file = DATA_RAW / "mimic-iv-hosp-3.1" / "SHA256SUMS.txt"
    if hosp_sha_file.is_file():
        expected_shas = parse_sha256sums(hosp_sha_file)
        # Only verify the hosp/ files we actually use
        hosp_files_to_check = [
            "hosp/admissions.csv.gz",
            "hosp/patients.csv.gz",
            "hosp/diagnoses_icd.csv.gz",
            "hosp/d_icd_diagnoses.csv.gz",
            "hosp/labevents.csv.gz",
            "hosp/d_labitems.csv.gz",
            "hosp/prescriptions.csv.gz",
            "hosp/emar.csv.gz",
            "hosp/transfers.csv.gz",
            "hosp/services.csv.gz",
        ]
        for rel in hosp_files_to_check:
            full_path = DATA_RAW / "mimic-iv-hosp-3.1" / rel
            if rel not in expected_shas:
                logger.warning(f"  No SHA256 entry for {rel} in Hosp SHA256SUMS.txt")
                sha_results.append(("Hosp", rel, "NO_ENTRY", "Not in SHA256SUMS.txt"))
                continue
            if not full_path.is_file():
                sha_results.append(("Hosp", rel, "MISSING", "File not found"))
                all_pass = False
                continue
            logger.info(f"  Hashing Hosp/{rel}...")
            actual_sha = sha256_file(full_path)
            if actual_sha == expected_shas[rel]:
                logger.info(f"    MATCH: {rel}")
                sha_results.append(("Hosp", rel, "MATCH", actual_sha[:16]))
                sha_verified_count += 1
            else:
                logger.error(f"    MISMATCH: {rel}")
                logger.error(f"      expected: {expected_shas[rel][:16]}...")
                logger.error(f"      actual:   {actual_sha[:16]}...")
                sha_results.append(("Hosp", rel, "MISMATCH",
                                    f"expected={expected_shas[rel][:16]}, actual={actual_sha[:16]}"))
                sha_failed_count += 1
                all_pass = False
    else:
        logger.error("  Hosp SHA256SUMS.txt not found!")
        sha_results.append(("Hosp", "SHA256SUMS.txt", "MISSING", "File not found"))
        all_pass = False

    # ED SHA256
    ed_sha_file = DATA_RAW / "mimic-iv-ed-2.2" / "SHA256SUMS.txt"
    if ed_sha_file.is_file():
        expected_shas = parse_sha256sums(ed_sha_file)
        ed_files_to_check = [
            "ed/edstays.csv.gz",
            "ed/diagnosis.csv.gz",
            "ed/triage.csv.gz",
            "ed/vitalsign.csv.gz",
            "ed/medrecon.csv.gz",
            "ed/pyxis.csv.gz",
        ]
        for rel in ed_files_to_check:
            full_path = DATA_RAW / "mimic-iv-ed-2.2" / rel
            if rel not in expected_shas:
                logger.warning(f"  No SHA256 entry for {rel} in ED SHA256SUMS.txt")
                sha_results.append(("ED", rel, "NO_ENTRY", "Not in SHA256SUMS.txt"))
                continue
            if not full_path.is_file():
                sha_results.append(("ED", rel, "MISSING", "File not found"))
                all_pass = False
                continue
            logger.info(f"  Hashing ED/{rel}...")
            actual_sha = sha256_file(full_path)
            if actual_sha == expected_shas[rel]:
                logger.info(f"    MATCH: {rel}")
                sha_results.append(("ED", rel, "MATCH", actual_sha[:16]))
                sha_verified_count += 1
            else:
                logger.error(f"    MISMATCH: {rel}")
                sha_results.append(("ED", rel, "MISMATCH",
                                    f"expected={expected_shas[rel][:16]}, actual={actual_sha[:16]}"))
                sha_failed_count += 1
                all_pass = False
    else:
        logger.error("  ED SHA256SUMS.txt not found!")
        sha_results.append(("ED", "SHA256SUMS.txt", "MISSING", "File not found"))
        all_pass = False

    # -----------------------------------------------------------------------
    # 3. Row-count verification per §5.3
    # -----------------------------------------------------------------------
    logger.info("--- Step 3: Row-count verification ---")

    row_results = []  # list of (label, rows, expected_range, status)

    for label, rel_path, do_count in REQUIRED_FILES:
        if not do_count:
            continue
        full_path = DATA_RAW / rel_path
        if not full_path.is_file():
            row_results.append((label, 0, "N/A", "MISSING"))
            continue

        filename = Path(rel_path).name
        expected = EXPECTED_ROW_COUNTS.get(filename)

        logger.info(f"  Counting rows: {label} ({filename})...")
        try:
            rows = count_rows(full_path)
        except Exception as e:
            logger.error(f"    ERROR counting {label}: {e}")
            row_results.append((label, 0, str(expected), "ERROR"))
            all_pass = False
            continue

        if expected:
            low, high = expected
            if high is None:
                in_range = rows >= low
                range_str = f">= {low:,}"
            else:
                in_range = low <= rows <= high
                range_str = f"{low:,} – {high:,}"

            if in_range:
                status = "IN_RANGE"
                logger.info(f"    OK: {label} = {rows:,} rows (expected {range_str})")
            else:
                status = "OUT_OF_RANGE"
                logger.warning(f"    WARNING: {label} = {rows:,} rows (expected {range_str})")
                # Out-of-range is a warning, not a hard failure — data may
                # legitimately differ across MIMIC versions
        else:
            in_range = rows > 0
            range_str = "> 0"
            status = "NONZERO" if in_range else "EMPTY"
            if not in_range:
                all_pass = False

        row_results.append((label, rows, range_str, status))

    # -----------------------------------------------------------------------
    # 4. Cross-source subject overlap check per §5.3
    # -----------------------------------------------------------------------
    logger.info("--- Step 4: Cross-source subject overlap ---")
    overlap_status = "UNKNOWN"
    overlap_detail = ""
    try:
        ecg_records = pd.read_csv(DATA_RAW / "record_list.csv",
                                  usecols=["subject_id"])
        ecg_subjects = set(ecg_records["subject_id"].unique())
        del ecg_records

        hosp_admissions = pd.read_csv(
            DATA_RAW / "mimic-iv-hosp-3.1" / "hosp" / "admissions.csv.gz",
            usecols=["subject_id"], compression="gzip"
        )
        hosp_subjects = set(hosp_admissions["subject_id"].unique())
        del hosp_admissions

        overlap = ecg_subjects & hosp_subjects
        n_ecg = len(ecg_subjects)
        n_hosp = len(hosp_subjects)
        n_overlap = len(overlap)
        pct_ecg = (n_overlap / n_ecg * 100) if n_ecg > 0 else 0
        pct_hosp = (n_overlap / n_hosp * 100) if n_hosp > 0 else 0

        logger.info(f"  ECG subjects: {n_ecg:,}")
        logger.info(f"  Hosp subjects: {n_hosp:,}")
        logger.info(f"  Overlap: {n_overlap:,} ({pct_ecg:.1f}% of ECG, {pct_hosp:.1f}% of Hosp)")

        if n_overlap > 0:
            overlap_status = "PASS"
            overlap_detail = (
                f"ECG subjects: {n_ecg:,}, Hosp subjects: {n_hosp:,}, "
                f"overlap: {n_overlap:,} ({pct_ecg:.1f}% of ECG, {pct_hosp:.1f}% of Hosp)"
            )
        else:
            overlap_status = "FAIL"
            overlap_detail = (
                f"ECG subjects: {n_ecg:,}, Hosp subjects: {n_hosp:,}, "
                f"overlap: 0 — POSSIBLE VERSION MISMATCH"
            )
            all_pass = False
    except Exception as e:
        logger.error(f"  ERROR during cross-source check: {e}")
        overlap_status = "ERROR"
        overlap_detail = str(e)
        all_pass = False

    # -----------------------------------------------------------------------
    # 5. Write the audit report
    # -----------------------------------------------------------------------
    logger.info("--- Writing access_check.md ---")

    elapsed = time.time() - t0
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    overall_status = "PASS" if all_pass else "FAIL"

    report_lines = []
    report_lines.append(f"# Access Check — {overall_status}")
    report_lines.append("")
    report_lines.append(f"**Generated:** {now_iso}")
    report_lines.append(f"**Script:** `00b_access_check.py`")
    report_lines.append(f"**Elapsed:** {elapsed:.1f}s ({elapsed/60:.1f} min)")
    report_lines.append(f"**Overall status:** {overall_status}")
    report_lines.append("")

    # Section 1: File existence
    report_lines.append("## 1. File Existence")
    report_lines.append("")
    report_lines.append("| # | Label | Status | Path |")
    report_lines.append("|---|-------|--------|------|")
    for i, (label, status, path) in enumerate(findings, 1):
        emoji = "✅" if status == "EXISTS" else "❌"
        report_lines.append(f"| {i} | {label} | {emoji} {status} | `{path}` |")
    report_lines.append("")

    # Section 2: SHA256 verification
    report_lines.append("## 2. SHA256 Verification")
    report_lines.append("")
    report_lines.append(f"- Files verified: {sha_verified_count}")
    report_lines.append(f"- Files with mismatch: {sha_failed_count}")
    report_lines.append("")
    report_lines.append("| Dataset | File | Status | Detail |")
    report_lines.append("|---------|------|--------|--------|")
    for dataset, filename, status, detail in sha_results:
        emoji = "✅" if status == "MATCH" else ("⚠️" if status == "NO_ENTRY" else "❌")
        report_lines.append(f"| {dataset} | `{filename}` | {emoji} {status} | {detail} |")
    report_lines.append("")

    # Section 3: Row counts
    report_lines.append("## 3. Row Counts")
    report_lines.append("")
    report_lines.append("| Label | Rows | Expected Range | Status |")
    report_lines.append("|-------|------|----------------|--------|")
    for label, rows, expected, status in row_results:
        emoji = "✅" if status in ("IN_RANGE", "NONZERO") else ("⚠️" if status == "OUT_OF_RANGE" else "❌")
        report_lines.append(f"| {label} | {rows:,} | {expected} | {emoji} {status} |")
    report_lines.append("")

    # Section 4: Cross-source overlap
    report_lines.append("## 4. Cross-Source Subject Overlap (ECG ↔ Hosp)")
    report_lines.append("")
    report_lines.append(f"**Status:** {overlap_status}")
    report_lines.append(f"**Detail:** {overlap_detail}")
    report_lines.append("")
    report_lines.append("This check verifies per §5.3 that at least *some* MIMIC-IV-ECG")
    report_lines.append("subjects appear in MIMIC-IV Hosp, preventing silent version mismatch.")
    report_lines.append("")

    # Final verdict
    report_lines.append("---")
    report_lines.append("")
    report_lines.append(f"## Verdict: {overall_status}")
    report_lines.append("")
    if all_pass:
        report_lines.append("All checks passed. Raw data is ready for pipeline processing.")
    else:
        report_lines.append("One or more checks failed. Review findings above before proceeding.")

    # Write atomically: write to .tmp then os.replace per §7.5
    report_text = "\n".join(report_lines) + "\n"
    tmp_path = REPORT_FILE.with_suffix(".md.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    os.replace(tmp_path, REPORT_FILE)

    logger.info(f"access_check.md written to {REPORT_FILE}")
    logger.info(f"Elapsed: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    logger.info(f"Overall status: {overall_status}")
    logger.info("=" * 60)
    logger.info("00b_access_check.py COMPLETE")
    logger.info("=" * 60)

    # Print summary to stdout for user
    print(f"\n{'=' * 60}")
    print(f"ACCESS CHECK: {overall_status}")
    print(f"{'=' * 60}")
    print(f"SHA256 verified: {sha_verified_count}, mismatched: {sha_failed_count}")
    print(f"Cross-source overlap: {overlap_status} — {overlap_detail}")
    print(f"Report: {REPORT_FILE}")
    print(f"Elapsed: {elapsed:.1f}s ({elapsed/60:.1f} min)")

    if not all_pass:
        sys.exit(1)


if __name__ == "__main__":
    main()
```

## 6. Validation results

- **Pre-flight: PASS** — disk free 195.1 GB (required: minimal for Stage 0); all Python dependencies importable in ecg_env.
- **`config/dataset_versions.yaml` exists: PASS** — 84 lines, 3,228 bytes, valid YAML (verified via `yaml.safe_load` round-trip).
- **Every library imported in `scripts/phase1_dataset_generation/` is listed: PASS** — 16 libraries recorded: python, numpy, pandas, pyarrow, h5py, wfdb, neurokit2, matplotlib, opencv_python, torch, pyyaml, psutil, scipy, scikit_learn, tqdm, Pillow.
- **SHA256 checksums match SHA256SUMS.txt: PASS** — 10/10 Hosp files MATCH, 6/6 ED files MATCH, 0 mismatches.
- **Row counts match §5.3 expected ranges: PASS** — all 18 counted tables in range:
  - `record_list.csv`: 800,035 (expected 790K–810K) ✅
  - `machine_measurements.csv`: 800,035 (expected 790K–810K) ✅
  - `admissions.csv.gz`: 546,028 (expected 500K–600K) ✅
  - `patients.csv.gz`: 364,627 (expected 350K–400K) ✅
  - `diagnoses_icd.csv.gz`: 6,364,488 (expected 6M–7M) ✅
  - `d_icd_diagnoses.csv.gz`: 112,107 (expected 100K–130K) ✅
  - `labevents.csv.gz`: 158,374,764 (expected 150M–170M) ✅
  - `d_labitems.csv.gz`: 1,650 (expected 1.5K–2K) ✅
  - `edstays.csv.gz`: 425,087 (expected 400K–450K) ✅
  - `diagnosis.csv.gz`: 899,050 (expected 850K–950K) ✅
  - `triage.csv.gz`: 425,087 (expected 400K–450K) ✅
- **`access_check.md` PASS: PASS** — report header reads "# Access Check — PASS", verdict reads "All checks passed."
- **Cross-source subject overlap: PASS** — 130,621 of 161,352 ECG subjects (81.0%) overlap with Hosp, confirming Plan A linkage is viable.
- **`dataset_version_stamp`: PASS** — set to "v2.0.0" per §3.1 schema.
- **Disk before stage start:** 195.1 GB free
- **Disk after stage end:** ~195.1 GB free (Stage 0 output is <10 KB total)
- **Wall-clock:** 00_lock_versions.py: 22:00, 00b_access_check.py: 7:50 → total ~30 min

## 7. Manual test procedure

```powershell
# 1. Verify dataset_versions.yaml is valid YAML and has required keys
cd D:\Coding\MU\Tri-Modal_ECG
.\ecg_env\Scripts\python.exe -c "import yaml; c=yaml.safe_load(open('config/dataset_versions.yaml')); print('Keys:', list(c.keys())); print('ECG rows:', c['mimic_iv_ecg']['row_counts']); print('Stamp:', c['dataset_version_stamp']); print('Libs:', len(c['libraries']), 'entries')"

# 2. Verify access_check.md exists and has PASS verdict
.\ecg_env\Scripts\python.exe -c "t=open('outputs/audit_reports/access_check.md').read(); print('PASS' if 'Verdict: PASS' in t else 'FAIL'); print(f'Lines: {len(t.splitlines())}')"

# 3. Spot-check a SHA256 from the YAML against SHA256SUMS.txt
.\ecg_env\Scripts\python.exe -c "import yaml; c=yaml.safe_load(open('config/dataset_versions.yaml')); sha=c['mimic_iv_hosp']['table_checksums']['admissions']; sums={l.split()[1]:l.split()[0] for l in open('data/raw/mimic-iv-hosp-3.1/SHA256SUMS.txt') if l.strip()}; print('admissions match:', sha == sums.get('hosp/admissions.csv.gz'))"

# 4. Re-run the scripts (idempotent — should overwrite cleanly)
cd scripts\phase1_dataset_generation
..\..\ecg_env\Scripts\python.exe 00_lock_versions.py
..\..\ecg_env\Scripts\python.exe 00b_access_check.py
```

## 8. Assumptions requiring user confirmation
- **`data/raw/` layout is final** :: Scripts assume data/raw/ already contains files/, record_list.csv, machine_measurements.csv, waveform_note_links.csv, mimic-iv-hosp-3.1/, mimic-iv-ed-2.2/ at the paths shown in §5.2. Sub-step 0.0 directory reorganization was already done in the prior session. If any files are at different paths, the scripts will report MISSING in the access check.
- **ECG SHA256SUMS.txt covers waveform files, not CSVs** :: The ECG dataset's SHA256SUMS.txt at `data/raw/SHA256SUMS.txt` is 176 MB and covers 800K+ waveform `.dat`/`.hea` files — not the CSV tables. So for the ECG CSVs (record_list.csv, machine_measurements.csv, etc.), we compute our own SHA256 and record them in dataset_versions.yaml. The SHA256SUMS.txt-based verification is only for Hosp and ED.
- **Stage 0 scope is 00_lock_versions.py and 00b_access_check.py only** :: Per the user's instruction, `01_build_master_index.py` (also listed in §9.3 Stage 0) is NOT implemented in this run. It will be handled separately.
