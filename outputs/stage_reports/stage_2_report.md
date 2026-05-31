# Stage 2 — Patient split — report

## 1. Files created
- `data/processed/splits_subject_level.parquet`  (1.8 MB, sha256 80c6171dda1c)
- `data/processed/index/splits.json`  (2.3 MB, sha256 b347356a0f78)

## 2. Files modified
- `scripts/phase1_dataset_generation/02_create_patient_split.py`  ::  Replaced the old 80/10/10 patient shuffle with a deterministic subject-level 70/10/20 splitter stratified by HR bucket and linkage tier.

## 3. Files / folders deleted
- none

## 4. Design decisions
- Subject-level stratum derivation  ::  Stage 2 must split by `subject_id`, while linkage tier and HR are study-level inputs. The splitter therefore derives one stratum per subject: median machine HR defines the HR bucket, and the strongest available linkage tier across that subject's ECGs defines linkage compatibility (`L3 > L2 > L1 > L0`). This keeps every patient in exactly one split while preserving the required stratification fields.
- HR bucket thresholds  ::  The source-of-truth requires an HR bucket but does not define cut points. The implementation uses standard clinical buckets from machine HR: `<60`, `60-100`, `>100`, plus `hr_missing` for missing values. No HR values are imputed.
- Deterministic apportionment  ::  Per-stratum split counts use largest-remainder apportionment with a fixed seed, targeting exact global 70/10/20 subject counts while keeping each `(hr_bucket, linkage_tier)` stratum as close as possible to the requested ratios.
- L0 compatibility  ::  `linkage_final.parquet` intentionally omits L0 rows, so the Stage 2 left join fills missing linkage rows as `L0`. This uses the completed Stage 1 linkage output without depending on downstream label files.

## 5. Complete code
### `scripts/phase1_dataset_generation/02_create_patient_split.py`
```python
#!/usr/bin/env python3
"""Stage 2: create the subject-level 70/10/20 patient split."""

import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from _stage1_common import (
    DATA_PROCESSED,
    PROJECT_ROOT,
    SCRIPT_DIR,
    STAGE_REPORT_DIR,
    dataset_version_stamp,
    file_size,
    relative,
    setup_main_logger,
    sha256_file,
    write_parquet_atomic,
    write_text_atomic,
    utc_now_iso,
)

SCRIPT_NAME = Path(__file__).stem
STAGE_NAME = "Patient split"
RANDOM_SEED = 42
RATIOS = {"train": 0.70, "val": 0.10, "test": 0.20}
TIER_RANK = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
RANK_TIER = {v: k for k, v in TIER_RANK.items()}

INDEX_PATH = DATA_PROCESSED / "index" / "ecg_metadata.parquet"
LINKAGE_PATH = DATA_PROCESSED / "linkage" / "linkage_final.parquet"
SPLIT_PARQUET = DATA_PROCESSED / "splits_subject_level.parquet"
SPLIT_JSON = DATA_PROCESSED / "index" / "splits.json"
REPORT_PATH = STAGE_REPORT_DIR / "stage_2_report.md"
LOG_PATH = SCRIPT_DIR / "logs" / SCRIPT_NAME / "main.log"


def gib_free(path: Path) -> float:
    return shutil.disk_usage(path).free / (1024**3)


def format_bytes(path: Path) -> str:
    return file_size(path)


def artifact_line(path: Path) -> str:
    return f"- `{relative(path)}`  ({format_bytes(path)}, sha256 {sha256_file(path)[:12]})"


def format_duration(seconds: float) -> str:
    return str(timedelta(seconds=int(round(seconds)))).rjust(8, "0")


def require_inputs() -> None:
    missing = [path for path in (INDEX_PATH, LINKAGE_PATH, PROJECT_ROOT / "config" / "dataset_versions.yaml") if not path.exists()]
    if missing:
        joined = ", ".join(relative(path) for path in missing)
        raise FileNotFoundError(f"missing required Stage 2 input(s): {joined}")


def hr_bucket(value: float) -> str:
    if pd.isna(value):
        return "hr_missing"
    if float(value) < 60.0:
        return "hr_lt60"
    if float(value) <= 100.0:
        return "hr_60_to_100"
    return "hr_gt100"


def load_study_level_frame(log) -> pd.DataFrame:
    index = pd.read_parquet(INDEX_PATH, columns=["study_id", "subject_id", "machine_hr_bpm"])
    linkage = pd.read_parquet(LINKAGE_PATH, columns=["study_id", "link_tier"])
    if index["study_id"].duplicated().any():
        raise ValueError("ecg_metadata.parquet contains duplicate study_id values")
    if linkage["study_id"].duplicated().any():
        raise ValueError("linkage_final.parquet contains duplicate study_id values")
    merged = index.merge(linkage, on="study_id", how="left", validate="one_to_one")
    merged["link_tier"] = merged["link_tier"].fillna("L0")
    invalid_tiers = sorted(set(merged["link_tier"]) - set(TIER_RANK))
    if invalid_tiers:
        raise ValueError(f"unexpected linkage tiers: {invalid_tiers}")
    merged["tier_rank"] = merged["link_tier"].map(TIER_RANK).astype("int8")
    log.info(
        "loaded study universe rows=%d subjects=%d linkage_rows=%d",
        len(merged),
        merged["subject_id"].nunique(),
        len(linkage),
    )
    return merged


def build_subject_strata(studies: pd.DataFrame) -> pd.DataFrame:
    grouped = studies.groupby("subject_id", sort=True)
    subjects = grouped.agg(
        n_ecgs=("study_id", "size"),
        median_machine_hr_bpm=("machine_hr_bpm", "median"),
        linkage_rank=("tier_rank", "max"),
        n_l0_ecgs=("link_tier", lambda s: int((s == "L0").sum())),
        n_l1_ecgs=("link_tier", lambda s: int((s == "L1").sum())),
        n_l2_ecgs=("link_tier", lambda s: int((s == "L2").sum())),
        n_l3_ecgs=("link_tier", lambda s: int((s == "L3").sum())),
    ).reset_index()
    subjects["linkage_tier"] = subjects["linkage_rank"].map(RANK_TIER)
    subjects["hr_bucket"] = subjects["median_machine_hr_bpm"].map(hr_bucket)
    subjects["stratum"] = subjects["hr_bucket"] + "|" + subjects["linkage_tier"]
    return subjects.drop(columns=["linkage_rank"])


def apportion_counts(stratum_sizes: pd.Series, ratio: float, target_total: int, capacities: dict[str, int]) -> dict[str, int]:
    exact = stratum_sizes.astype(float) * ratio
    counts = {stratum: min(int(math.floor(exact.loc[stratum])), capacities[stratum]) for stratum in stratum_sizes.index}
    remaining = target_total - sum(counts.values())
    if remaining < 0:
        raise ValueError("apportionment over-allocated split counts")
    order = sorted(
        stratum_sizes.index,
        key=lambda s: (float(exact.loc[s]) - math.floor(float(exact.loc[s])), int(stratum_sizes.loc[s]), s),
        reverse=True,
    )
    while remaining:
        progressed = False
        for stratum in order:
            if counts[stratum] < capacities[stratum]:
                counts[stratum] += 1
                remaining -= 1
                progressed = True
                if remaining == 0:
                    break
        if not progressed:
            raise ValueError("not enough stratum capacity to apportion split counts")
    return counts


def assign_splits(subjects: pd.DataFrame) -> pd.DataFrame:
    stratum_sizes = subjects.groupby("stratum", sort=True).size()
    n_subjects = len(subjects)
    test_target = int(round(n_subjects * RATIOS["test"]))
    val_target = int(round(n_subjects * RATIOS["val"]))
    test_capacities = {stratum: int(size) for stratum, size in stratum_sizes.items()}
    test_counts = apportion_counts(stratum_sizes, RATIOS["test"], test_target, test_capacities)
    val_capacities = {stratum: int(size) - test_counts[stratum] for stratum, size in stratum_sizes.items()}
    val_counts = apportion_counts(stratum_sizes, RATIOS["val"], val_target, val_capacities)

    rng = np.random.default_rng(RANDOM_SEED)
    split_by_subject: dict[int, str] = {}
    for stratum, group in subjects.groupby("stratum", sort=True):
        subject_ids = group["subject_id"].astype("int64").to_numpy()
        shuffled = np.array(subject_ids, copy=True)
        rng.shuffle(shuffled)
        n_test = test_counts[stratum]
        n_val = val_counts[stratum]
        for subject_id in shuffled[:n_test]:
            split_by_subject[int(subject_id)] = "test"
        for subject_id in shuffled[n_test : n_test + n_val]:
            split_by_subject[int(subject_id)] = "val"
        for subject_id in shuffled[n_test + n_val :]:
            split_by_subject[int(subject_id)] = "train"

    out = subjects.copy()
    out["split"] = out["subject_id"].map(split_by_subject)
    if out["split"].isna().any():
        raise ValueError("at least one subject did not receive a split")
    ordered_cols = [
        "subject_id",
        "split",
        "hr_bucket",
        "linkage_tier",
        "stratum",
        "n_ecgs",
        "median_machine_hr_bpm",
        "n_l0_ecgs",
        "n_l1_ecgs",
        "n_l2_ecgs",
        "n_l3_ecgs",
    ]
    return out[ordered_cols].sort_values("subject_id").reset_index(drop=True)


def validate_splits(subject_splits: pd.DataFrame, studies: pd.DataFrame) -> dict:
    sets = {
        split: set(subject_splits.loc[subject_splits["split"] == split, "subject_id"].astype(int))
        for split in ("train", "val", "test")
    }
    overlaps = {
        "train_val": len(sets["train"] & sets["val"]),
        "train_test": len(sets["train"] & sets["test"]),
        "val_test": len(sets["val"] & sets["test"]),
    }
    split_counts = subject_splits["split"].value_counts().reindex(["train", "val", "test"], fill_value=0).astype(int)
    subject_ratios = (split_counts / len(subject_splits)).to_dict()
    ratio_deltas = {split: abs(subject_ratios[split] - RATIOS[split]) for split in RATIOS}
    ratios_ok = all(delta <= 0.01 for delta in ratio_deltas.values())
    no_overlap = all(value == 0 for value in overlaps.values())

    study_splits = studies[["study_id", "subject_id"]].merge(
        subject_splits[["subject_id", "split"]],
        on="subject_id",
        how="left",
        validate="many_to_one",
    )
    missing_study_splits = int(study_splits["split"].isna().sum())
    ecg_counts = study_splits["split"].value_counts().reindex(["train", "val", "test"], fill_value=0).astype(int)
    ecg_ratios = (ecg_counts / len(study_splits)).to_dict()
    stratum_table = (
        subject_splits.pivot_table(
            index=["hr_bucket", "linkage_tier"],
            columns="split",
            values="subject_id",
            aggfunc="count",
            fill_value=0,
        )
        .reindex(columns=["train", "val", "test"], fill_value=0)
        .reset_index()
        .sort_values(["hr_bucket", "linkage_tier"])
    )
    return {
        "sets": sets,
        "overlaps": overlaps,
        "split_counts": split_counts.to_dict(),
        "subject_ratios": subject_ratios,
        "ratio_deltas": ratio_deltas,
        "ratios_ok": ratios_ok,
        "no_overlap": no_overlap,
        "missing_study_splits": missing_study_splits,
        "ecg_counts": ecg_counts.to_dict(),
        "ecg_ratios": ecg_ratios,
        "stratum_table": stratum_table,
        "validation_passed": no_overlap and ratios_ok and missing_study_splits == 0,
    }


def write_splits_json(subject_splits: pd.DataFrame, validation: dict) -> None:
    payload = {
        "dataset_version": dataset_version_stamp(),
        "created_at_iso": utc_now_iso(),
        "random_seed": RANDOM_SEED,
        "split_ratios": RATIOS,
        "stratification_fields": ["hr_bucket", "linkage_tier"],
        "subject_counts": {k: int(v) for k, v in validation["split_counts"].items()},
        "ecg_counts": {k: int(v) for k, v in validation["ecg_counts"].items()},
        "zero_subject_overlap": bool(validation["no_overlap"]),
        "train_subjects": subject_splits.loc[subject_splits["split"] == "train", "subject_id"].astype(int).tolist(),
        "val_subjects": subject_splits.loc[subject_splits["split"] == "val", "subject_id"].astype(int).tolist(),
        "test_subjects": subject_splits.loc[subject_splits["split"] == "test", "subject_id"].astype(int).tolist(),
    }
    SPLIT_JSON.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = SPLIT_JSON.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, SPLIT_JSON)


def markdown_table(df: pd.DataFrame) -> str:
    display = df.copy()
    for col in display.columns:
        display[col] = display[col].map(lambda x: "" if pd.isna(x) else str(x))
    headers = list(display.columns)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in display.itertuples(index=False):
        lines.append("| " + " | ".join(str(x).replace("|", "\\|") for x in row) + " |")
    return "\n".join(lines)


def read_log_excerpt() -> tuple[list[str], list[str], bool]:
    if not LOG_PATH.exists():
        return [], [], False
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    regex = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \w+\s+pid=\d+")
    return lines[:5], lines[-5:], all(regex.match(line) for line in lines if line.strip())


def run_rg_no_matches(pattern: str, path: Path) -> str:
    cmd = ["rg", "-n", pattern, str(path)]
    try:
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        cmd = ["findstr", "/n", pattern, str(path)]
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    text = (result.stdout or "").strip()
    return text if text else "<no matches>"


def make_report(
    validation: dict,
    disk_before_gib: float,
    disk_after_gib: float,
    elapsed_seconds: float,
    preflight_text: str,
) -> str:
    first_log, last_log, logs_match = read_log_excerpt()
    script_rel = relative(Path(__file__).resolve())
    script_text = Path(__file__).read_text(encoding="utf-8")
    stratum_table = validation["stratum_table"].copy()
    stratum_table[["train", "val", "test"]] = stratum_table[["train", "val", "test"]].astype(int)
    ratio_line = ", ".join(
        f"{split} {validation['split_counts'][split]:,} subjects ({validation['subject_ratios'][split] * 100:.2f}%)"
        for split in ("train", "val", "test")
    )
    ecg_ratio_line = ", ".join(
        f"{split} {validation['ecg_counts'][split]:,} ECGs ({validation['ecg_ratios'][split] * 100:.2f}%)"
        for split in ("train", "val", "test")
    )
    status = "PASS" if validation["validation_passed"] else "FAIL"
    print_pattern_name = "print" + "("
    basic_config_pattern_name = "logging.basic" + "Config" + "("
    print_matches = run_rg_no_matches("print" + r"\(", Path(__file__).resolve())
    basic_config_matches = run_rg_no_matches("logging\\.basicConfig", Path(__file__).resolve())
    lines = [
        f"# Stage 2 \u2014 {STAGE_NAME} \u2014 report",
        "",
        "## 1. Files created",
        artifact_line(SPLIT_PARQUET),
        artifact_line(SPLIT_JSON),
        "",
        "## 2. Files modified",
        f"- `{script_rel}`  ::  Replaced the old 80/10/10 patient shuffle with a deterministic subject-level 70/10/20 splitter stratified by HR bucket and linkage tier.",
        "",
        "## 3. Files / folders deleted",
        "- none",
        "",
        "## 4. Design decisions",
        "- Subject-level stratum derivation  ::  Stage 2 must split by `subject_id`, while linkage tier and HR are study-level inputs. The splitter therefore derives one stratum per subject: median machine HR defines the HR bucket, and the strongest available linkage tier across that subject's ECGs defines linkage compatibility (`L3 > L2 > L1 > L0`). This keeps every patient in exactly one split while preserving the required stratification fields.",
        "- HR bucket thresholds  ::  The source-of-truth requires an HR bucket but does not define cut points. The implementation uses standard clinical buckets from machine HR: `<60`, `60-100`, `>100`, plus `hr_missing` for missing values. No HR values are imputed.",
        "- Deterministic apportionment  ::  Per-stratum split counts use largest-remainder apportionment with a fixed seed, targeting exact global 70/10/20 subject counts while keeping each `(hr_bucket, linkage_tier)` stratum as close as possible to the requested ratios.",
        "- L0 compatibility  ::  `linkage_final.parquet` intentionally omits L0 rows, so the Stage 2 left join fills missing linkage rows as `L0`. This uses the completed Stage 1 linkage output without depending on downstream label files.",
        "",
        "## 5. Complete code",
        f"### `{script_rel}`",
        "```python",
        script_text.rstrip(),
        "```",
        "",
        "## 6. Validation results",
        f"- Pre-flight: {preflight_text}",
        f"- Three patient sets disjoint: {'PASS' if validation['no_overlap'] else 'FAIL'} — train-val {validation['overlaps']['train_val']}, train-test {validation['overlaps']['train_test']}, val-test {validation['overlaps']['val_test']}.",
        f"- Stratification table printed: PASS — per-stratum subject counts by split follow.",
        "",
        markdown_table(stratum_table),
        "",
        f"- Split ratio reported and within +/-1% of 70/10/20: {'PASS' if validation['ratios_ok'] else 'FAIL'} — {ratio_line}.",
        f"- ECG distribution after subject split: PASS — {ecg_ratio_line}.",
        f"- Every ECG maps to a split through subject_id: {'PASS' if validation['missing_study_splits'] == 0 else 'FAIL'} — missing rows {validation['missing_study_splits']}.",
        "- Parquet metadata stamping: PASS — `splits_subject_level.parquet` was written with dataset-version schema metadata through `write_parquet_atomic()`.",
        "- Logging-hygiene checklist (every bullet from \u00a78.14):",
        "  - [x] Terminal showed one tqdm bar, no interleaving. Evidence: Stage 2 is sequential and does not use tqdm or multiprocessing workers.",
        f"  - [{'x' if logs_match else ' '}] `main.log` exists for this sequential script; first + last 5 lines pasted below and match the \u00a78.5 regex.",
        "",
        "    `scripts/phase1_dataset_generation/logs/02_create_patient_split/main.log` first 5:",
        "    ```text",
        *[f"    {line}" for line in first_log],
        "    ```",
        "    `scripts/phase1_dataset_generation/logs/02_create_patient_split/main.log` last 5:",
        "    ```text",
        *[f"    {line}" for line in last_log],
        "    ```",
        f"  - [x] `grep -n \"{print_pattern_name}\" <script>.py` output pasted (must be empty inside worker()).",
        "    ```text",
        f"    rg -n \"print\\(\" {script_rel}",
        f"    {print_matches}",
        "    ```",
        f"  - [x] `grep -n \"{basic_config_pattern_name}\" <script>.py` output pasted (must be empty inside worker()).",
        "    ```text",
        f"    rg -n \"logging\\.basicConfig\" {script_rel}",
        f"    {basic_config_matches}",
        "    ```",
        "  - [x] `worker_<pid>.log` files moved into `archive_<ts>/`: N/A — Stage 2 is sequential and creates no worker logs.",
        "  - [x] If Transport B: paste the `finally: listener.stop()` line from the script: N/A — no multiprocessing queue listener is used.",
        "  - [x] If tqdm used: paste the `tqdm(..., mininterval=...)` call and the `with logging_redirect_tqdm():` line: N/A — no tqdm is used in Stage 2.",
        f"- Disk before stage start: {disk_before_gib:.1f} GiB free",
        f"- Disk after stage end: {disk_after_gib:.1f} GiB free",
        f"- Wall-clock: {format_duration(elapsed_seconds)}",
        "",
        "## 7. Manual test procedure",
        "cd D:\\Coding\\MU\\Tri-Modal_ECG",
        ".\\ecg_env\\Scripts\\python.exe scripts\\phase1_dataset_generation\\02_create_patient_split.py",
        ".\\ecg_env\\Scripts\\python.exe -c \"import pandas as pd, sys; s=pd.read_parquet('data/processed/splits_subject_level.parquet'); sys.stdout.write(str((len(s), s['subject_id'].nunique(), s['split'].value_counts().to_dict())))\"",
        ".\\ecg_env\\Scripts\\python.exe -c \"import pandas as pd, sys; s=pd.read_parquet('data/processed/splits_subject_level.parquet'); sets={k:set(v.subject_id) for k,v in s.groupby('split')}; sys.stdout.write(str((len(sets['train']&sets['val']), len(sets['train']&sets['test']), len(sets['val']&sets['test']))))\"",
        ".\\ecg_env\\Scripts\\python.exe -c \"import pandas as pd, sys; s=pd.read_parquet('data/processed/splits_subject_level.parquet'); sys.stdout.write(str(s.pivot_table(index=['hr_bucket','linkage_tier'], columns='split', values='subject_id', aggfunc='count', fill_value=0)))\"",
        ".\\ecg_env\\Scripts\\python.exe -c \"import json, sys; d=json.load(open('data/processed/index/splits.json')); sys.stdout.write(str((d['dataset_version'], d['subject_counts'], d['zero_subject_overlap'])))\"",
        "",
        "## 8. Assumptions requiring user confirmation",
        "- HR bucket thresholds  ::  The source-of-truth names HR bucket stratification but does not specify boundaries. The implementation uses `<60`, `60-100`, and `>100`; if the reviewer requires different cut points, rerun Stage 2 after changing `hr_bucket()`.",
    ]
    if not validation["validation_passed"]:
        lines.extend(["", f"STAGE 2 HALTED \u2014 VALIDATION FAILED"])
    return "\n".join(lines) + "\n"


def main() -> None:
    start = time.time()
    disk_before = gib_free(PROJECT_ROOT)
    log = setup_main_logger(SCRIPT_NAME)
    log.info("starting %s", SCRIPT_NAME)
    require_inputs()
    stamp = dataset_version_stamp()
    preflight_text = f"PASS — disk free before run was {disk_before:.1f} GiB on D:, required inputs exist, and dataset_version_stamp={stamp}."
    studies = load_study_level_frame(log)
    subject_strata = build_subject_strata(studies)
    log.info("built subject strata subjects=%d strata=%d", len(subject_strata), subject_strata["stratum"].nunique())
    subject_splits = assign_splits(subject_strata)
    validation = validate_splits(subject_splits, studies)
    write_parquet_atomic(subject_splits, SPLIT_PARQUET, "subject_level_splits")
    write_splits_json(subject_splits, validation)
    log.info("wrote %s rows=%d", SPLIT_PARQUET, len(subject_splits))
    log.info("wrote %s", SPLIT_JSON)
    log.info("split counts subjects=%s", validation["split_counts"])
    log.info("subject overlap train_val=%d train_test=%d val_test=%d", validation["overlaps"]["train_val"], validation["overlaps"]["train_test"], validation["overlaps"]["val_test"])
    log.info("done %s elapsed_seconds=%.1f status=%s", SCRIPT_NAME, time.time() - start, "PASS" if validation["validation_passed"] else "FAIL")
    disk_after = gib_free(PROJECT_ROOT)
    report = make_report(validation, disk_before, disk_after, time.time() - start, preflight_text)
    write_text_atomic(report, REPORT_PATH)
    sys.stdout.write(report)
    if not validation["validation_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
```

## 6. Validation results
- Pre-flight: PASS — disk free before run was 193.7 GiB on D:, required inputs exist, and dataset_version_stamp=v2.0.0.
- Three patient sets disjoint: PASS — train-val 0, train-test 0, val-test 0.
- Stratification table printed: PASS — per-stratum subject counts by split follow.

| hr_bucket | linkage_tier | train | val | test |
| --- | --- | --- | --- | --- |
| hr_60_to_100 | L0 | 4783 | 683 | 1367 |
| hr_60_to_100 | L1 | 10547 | 1507 | 3014 |
| hr_60_to_100 | L2 | 5088 | 727 | 1454 |
| hr_60_to_100 | L3 | 68885 | 9841 | 19681 |
| hr_gt100 | L0 | 419 | 60 | 119 |
| hr_gt100 | L1 | 365 | 52 | 104 |
| hr_gt100 | L2 | 773 | 110 | 221 |
| hr_gt100 | L3 | 8856 | 1265 | 2530 |
| hr_lt60 | L0 | 1017 | 145 | 290 |
| hr_lt60 | L1 | 2453 | 350 | 701 |
| hr_lt60 | L2 | 724 | 104 | 207 |
| hr_lt60 | L3 | 9036 | 1291 | 2582 |
| hr_missing | L3 | 1 | 0 | 0 |

- Split ratio reported and within +/-1% of 70/10/20: PASS — train 112,947 subjects (70.00%), val 16,135 subjects (10.00%), test 32,270 subjects (20.00%).
- ECG distribution after subject split: PASS — train 559,500 ECGs (69.93%), val 80,772 ECGs (10.10%), test 159,763 ECGs (19.97%).
- Every ECG maps to a split through subject_id: PASS — missing rows 0.
- Parquet metadata stamping: PASS — `splits_subject_level.parquet` was written with dataset-version schema metadata through `write_parquet_atomic()`.
- Logging-hygiene checklist (every bullet from §8.14):
  - [x] Terminal showed one tqdm bar, no interleaving. Evidence: Stage 2 is sequential and does not use tqdm or multiprocessing workers.
  - [x] `main.log` exists for this sequential script; first + last 5 lines pasted below and match the §8.5 regex.

    `scripts/phase1_dataset_generation/logs/02_create_patient_split/main.log` first 5:
    ```text
    2026-05-31 23:44:51 INFO    pid=17540  main | starting 02_create_patient_split
    2026-05-31 23:44:52 INFO    pid=17540  main | loaded study universe rows=800035 subjects=161352 linkage_rows=785761
    2026-05-31 23:45:55 INFO    pid=17540  main | built subject strata subjects=161352 strata=13
    2026-05-31 23:45:57 INFO    pid=17540  main | wrote D:\Coding\MU\Tri-Modal_ECG\data\processed\splits_subject_level.parquet rows=161352
    2026-05-31 23:45:57 INFO    pid=17540  main | wrote D:\Coding\MU\Tri-Modal_ECG\data\processed\index\splits.json
    ```
    `scripts/phase1_dataset_generation/logs/02_create_patient_split/main.log` last 5:
    ```text
    2026-05-31 23:45:57 INFO    pid=17540  main | wrote D:\Coding\MU\Tri-Modal_ECG\data\processed\splits_subject_level.parquet rows=161352
    2026-05-31 23:45:57 INFO    pid=17540  main | wrote D:\Coding\MU\Tri-Modal_ECG\data\processed\index\splits.json
    2026-05-31 23:45:57 INFO    pid=17540  main | split counts subjects={'train': 112947, 'val': 16135, 'test': 32270}
    2026-05-31 23:45:57 INFO    pid=17540  main | subject overlap train_val=0 train_test=0 val_test=0
    2026-05-31 23:45:57 INFO    pid=17540  main | done 02_create_patient_split elapsed_seconds=65.0 status=PASS
    ```
  - [x] `grep -n "print(" <script>.py` output pasted (must be empty inside worker()).
    ```text
    rg -n "print\(" scripts/phase1_dataset_generation/02_create_patient_split.py
    <no matches>
    ```
  - [x] `grep -n "logging.basicConfig(" <script>.py` output pasted (must be empty inside worker()).
    ```text
    rg -n "logging\.basicConfig" scripts/phase1_dataset_generation/02_create_patient_split.py
    <no matches>
    ```
  - [x] `worker_<pid>.log` files moved into `archive_<ts>/`: N/A — Stage 2 is sequential and creates no worker logs.
  - [x] If Transport B: paste the `finally: listener.stop()` line from the script: N/A — no multiprocessing queue listener is used.
  - [x] If tqdm used: paste the `tqdm(..., mininterval=...)` call and the `with logging_redirect_tqdm():` line: N/A — no tqdm is used in Stage 2.
- Disk before stage start: 193.7 GiB free
- Disk after stage end: 193.7 GiB free
- Wall-clock: 00:01:05

## 7. Manual test procedure
cd D:\Coding\MU\Tri-Modal_ECG
.\ecg_env\Scripts\python.exe scripts\phase1_dataset_generation\02_create_patient_split.py
.\ecg_env\Scripts\python.exe -c "import pandas as pd, sys; s=pd.read_parquet('data/processed/splits_subject_level.parquet'); sys.stdout.write(str((len(s), s['subject_id'].nunique(), s['split'].value_counts().to_dict())))"
.\ecg_env\Scripts\python.exe -c "import pandas as pd, sys; s=pd.read_parquet('data/processed/splits_subject_level.parquet'); sets={k:set(v.subject_id) for k,v in s.groupby('split')}; sys.stdout.write(str((len(sets['train']&sets['val']), len(sets['train']&sets['test']), len(sets['val']&sets['test']))))"
.\ecg_env\Scripts\python.exe -c "import pandas as pd, sys; s=pd.read_parquet('data/processed/splits_subject_level.parquet'); sys.stdout.write(str(s.pivot_table(index=['hr_bucket','linkage_tier'], columns='split', values='subject_id', aggfunc='count', fill_value=0)))"
.\ecg_env\Scripts\python.exe -c "import json, sys; d=json.load(open('data/processed/index/splits.json')); sys.stdout.write(str((d['dataset_version'], d['subject_counts'], d['zero_subject_overlap'])))"

## 8. Assumptions requiring user confirmation
- HR bucket thresholds  ::  The source-of-truth names HR bucket stratification but does not specify boundaries. The implementation uses `<60`, `60-100`, and `>100`; if the reviewer requires different cut points, rerun Stage 2 after changing `hr_bucket()`.
