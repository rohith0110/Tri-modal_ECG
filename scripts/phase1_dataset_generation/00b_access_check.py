#!/usr/bin/env python3
"""
00b_access_check.py — Stage 0, Script 2
=========================================
Verify every raw file in §5.2 exists, validate against SHA256SUMS.txt,
confirm rows in the §5.3 ranges. Write outputs/audit_reports/access_check.md.

Sequential script (no multiprocessing). Logging per §8.13 (sequential scripts).

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
    Parse a SHA256SUMS.txt file → dict[relative_path → expected_sha256].
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
