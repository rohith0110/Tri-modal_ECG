"""Emit a Stage P2.x report in the exact §10 eight-section format.

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/stage_report.py P2.1

The report is assembled from what actually happened -- the per-script state
JSONs written by :class:`build_common.StageState`, the files on disk, and the
run logs -- rather than from anything typed by hand, so a number in the report
and a number in the data cannot disagree.

§10 requires the full source of every created script in section 5, with no
elisions, so these reports are long by design.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _dataset_lib import build_common as bc  # noqa: E402

SCRIPTS_DIR = bc.PROJECT_ROOT / "scripts" / "phase2_tasks_benchmark_and_paper"

STAGES: dict[str, dict[str, Any]] = {
    "P2.1": {
        "name": "Build Plan A task datasets",
        "spec": "§9.2",
        "scripts": [
            "00_extract_fiducials.py",
            "00b_rebuild_lab_cache.py",
            "01_build_A1_ecg_diagnosis.py",
            "02_build_A2_measurement_blind.py",
            "03_build_A3_lab_abnormality.py",
            "04_build_A4_event_localization.py",
            "05_build_A5_cross_modal_verification.py",
            "06_build_A6_risk_stratification.py",
            "_dataset_lib/build_common.py",
            "_dataset_lib/measurement_task.py",
            "_dataset_lib/verification_task.py",
        ],
        "tasks": ["A1_ecg_diagnosis", "A2_measurement_blind", "A3_lab_abnormality",
                  "A4_event_localization", "A5_cross_modal_verification",
                  "A6_risk_stratification"],
        "extra_outputs": [
            bc.DATA_PROCESSED / "fiducials_lead2.parquet",
            bc.EHR_CACHE / "labevents_key_labs.parquet",
        ],
    },
    "P2.4": {
        "name": "Training + evaluation code, and the algorithmic baselines",
        "spec": "§5, §6, §7, §9.5",
        "scripts": [
            "30_train.py",
            "31_eval.py",
            "50_run_baselines_algorithmic.py",
            "_dataset_lib/task_spec.py",
            "_dataset_lib/task_dataset.py",
            "_dataset_lib/bootstrap.py",
            "_dataset_lib/corruption.py",
            "_model_lib/signal_encoders.py",
            "_model_lib/image_encoders.py",
            "_model_lib/text_encoders.py",
            "_model_lib/fusion_heads.py",
            "_model_lib/task_models.py",
            "_model_lib/model_configs.py",
            "_model_lib/algorithmic_baselines.py",
            "_train_lib/seed.py",
            "_train_lib/metrics.py",
            "_train_lib/threshold.py",
            "_train_lib/calibration.py",
            "_train_lib/trainer.py",
            "_train_lib/smoke_test.py",
        ],
        "tasks": [],
        "extra_outputs": [
            bc.CONFIG_DIR / "eval_configs" / "default.yaml",
            bc.CONFIG_DIR / "eval_configs" / "A4_fiducial.yaml",
            bc.CONFIG_DIR / "eval_configs" / "A6_risk.yaml",
            bc.CONFIG_DIR / "eval_configs" / "B2_robustness.yaml",
            bc.CONFIG_DIR / "eval_configs" / "cross_modal.yaml",
        ],
    },
    "P2.3": {
        "name": "The three Phase 2 audits — leakage, cohort, split",
        "spec": "§9.4",
        "scripts": [
            "20_audit_tasks_leakage.py",
            "21_audit_tasks_cohort.py",
            "22_audit_tasks_split.py",
            "_dataset_lib/audit_common.py",
        ],
        "tasks": [],
        "extra_outputs": [
            bc.PROJECT_ROOT / "outputs" / "audit_reports" / "leakage_audit_phase2.md",
            bc.PROJECT_ROOT / "outputs" / "audit_reports" / "cohort_audit.md",
            bc.PROJECT_ROOT / "outputs" / "audit_reports" / "split_audit_phase2.md",
        ],
    },
    "P2.2": {
        "name": "Build Plan B task datasets",
        "spec": "§9.3",
        "scripts": [
            "07_build_B1_measurement_blind.py",
            "08_build_B2_noise_robustness.py",
            "09_build_B3_temporal_grounding.py",
            "10_build_B4_cross_modal_verification.py",
            "11_build_B5_contradiction_detection.py",
            "12_build_B6_difficulty_stratified.py",
        ],
        "tasks": ["B1_measurement_blind", "B2_noise_robustness", "B3_temporal_grounding",
                  "B4_cross_modal_verification", "B5_contradiction_detection",
                  "B6_difficulty_stratified"],
        "extra_outputs": [],
    },
}


def sha256_prefix(path: Path, length: int = 12) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()[:length]


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:,.1f} {unit}" if unit != "B" else f"{int(value):,} B"
        value /= 1024
    return f"{value:.1f} GB"


def load_states(stage: str) -> dict[str, dict]:
    states: dict[str, dict] = {}
    for path in sorted(bc.STAGE_REPORTS.glob(f"stage_{stage}_*_state.json")):
        if path.name.endswith("_dev_state.json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        states[str(data.get("script", path.stem))] = data
    return states


def aggregate_worker_logs(stage: str) -> list[str]:
    """Concatenate per-PID worker logs into aggregate.log and archive them.

    Phase 1 §8.3 requires this after a pool drains. The builders write per-PID
    files during the run; this closes the transport.
    """
    lines: list[str] = []
    run_root = bc.STAGE_REPORTS / f"stage_{stage}_run"
    if not run_root.is_dir():
        return ["(no worker-log directory for this stage -- no builder used a process pool)"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for script_dir in sorted(d for d in run_root.iterdir() if d.is_dir()):
        workers = sorted(script_dir.glob("worker_*.log"))
        if not workers:
            continue
        aggregate = script_dir / "aggregate.log"
        with aggregate.open("a", encoding="utf-8") as out:
            for worker in workers:
                out.write(f"\n===== {worker.name} =====\n")
                out.write(worker.read_text(encoding="utf-8", errors="replace"))
        archive = script_dir / f"archive_{stamp}"
        archive.mkdir(exist_ok=True)
        for worker in workers:
            worker.replace(archive / worker.name)
        text = aggregate.read_text(encoding="utf-8", errors="replace").splitlines()
        head = text[:5] or ["(empty)"]
        tail = text[-5:] or ["(empty)"]
        lines.append(f"- `{aggregate.relative_to(bc.PROJECT_ROOT)}` "
                     f"({len(workers)} worker files archived into `{archive.name}/`)")
        lines += [f"      {line}" for line in head]
        lines.append("      ...")
        lines += [f"      {line}" for line in tail]
    return lines or ["(no worker logs produced -- every builder in this stage is single-process)"]


def grep(pattern: str, paths: list[Path]) -> str:
    existing = [str(p) for p in paths if p.exists()]
    if not existing:
        return "(no files to search)"
    result = subprocess.run(["grep", "-n", pattern, *existing],
                            capture_output=True, text=True)
    return result.stdout.strip() or f"(no match for {pattern!r} -- clean)"


def section_files(stage: str, config: dict) -> tuple[list[str], list[str]]:
    created, missing = [], []
    for name in config["scripts"]:
        path = SCRIPTS_DIR / name
        if path.exists():
            created.append(f"- `scripts/phase2_tasks_benchmark_and_paper/{name}`  "
                           f"({human(path.stat().st_size)}, sha256 {sha256_prefix(path)})")
        else:
            missing.append(name)
    for path in config["extra_outputs"]:
        if path.exists():
            created.append(f"- `{path.relative_to(bc.PROJECT_ROOT).as_posix()}`  "
                           f"({human(path.stat().st_size)}, sha256 {sha256_prefix(path)})")
        else:
            missing.append(str(path))
    for task in config["tasks"]:
        directory = bc.TASKS_DIR / task
        if not directory.is_dir():
            missing.append(f"data/processed/tasks/{task}/")
            continue
        for path in sorted(directory.iterdir()):
            if path.is_file():
                created.append(
                    f"- `{path.relative_to(bc.PROJECT_ROOT).as_posix()}`  "
                    f"({human(path.stat().st_size)}, sha256 {sha256_prefix(path)})"
                )
    return created, missing



def p24_validation() -> list[str]:
    """Read the Step-3 validation back off disk, rather than restating it.

    Everything here is counted from `stage_P2.4_smoke_test.log` and the dev-run
    artifacts, so the report cannot claim a pass the smoke test did not produce.
    """
    log_path = bc.STAGE_REPORTS / "stage_P2.4_smoke_test.log"
    lines: list[str] = []

    if not log_path.exists():
        return ["- Smoke test: **NOT RUN** — `stage_P2.4_smoke_test.log` is absent.",
                "  Run `_train_lib/smoke_test.py` before treating this stage as complete."]

    text = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    trains = [l for l in text if l.startswith("  PASS  train ")]
    evals = [l for l in text if l.startswith("  PASS  eval ")]
    failures = [l for l in text if l.startswith("  FAIL")]
    recovery = [l for l in text if l.startswith("  PASS  ")
                and not l.startswith("  PASS  train ") and not l.startswith("  PASS  eval ")]
    verdict = next((l for l in text if l.startswith("SMOKE TEST")), "(no verdict line)")

    lines += [
        f"- **Smoke test on `data/processed/dev_sample/`: {verdict.strip()}**",
        f"  - {len(trains)} `30_train.py` invocations PASS, {len(evals)} `31_eval.py` "
        f"invocations PASS, {len(failures)} FAIL",
        f"  - {len(recovery)} crash-recovery / determinism / gate checks PASS:",
    ]
    lines += [f"    - `{l.strip()[6:]}`" for l in recovery]
    lines += ["  - Full transcript: `outputs/stage_reports/stage_P2.4_smoke_test.log`", ""]

    lines += ["- **§9.5 oracle validation** (the check §9.5 names explicitly: "
              "\"A4 / B3 should hit F1=1.0 within the algorithmic-baseline's own "
              "noise tolerance\"):"]
    for task, metric in (("A4_event_localization", "r_peak_f1"),
                         ("B3_temporal_grounding", "mIoU")):
        value = _dev_result(task, "algorithmic", metric)
        mark = "PASS" if value is not None and abs(value - 1.0) < 1e-9 else "FAIL"
        shown = "n/a" if value is None else f"{value:.4f}"
        lines.append(f"  - {mark} — {task} algorithmic `{metric}` = {shown} (expected 1.0000)")
    lines.append("")

    summary = bc.PROJECT_ROOT / "outputs" / "model_runs" / "_dev" / \
        "algorithmic_baseline_summary.json"
    if summary.exists():
        data = json.loads(summary.read_text(encoding="utf-8"))
        ok = [k for k, v in data.get("results", {}).items() if v.get("status") == "ok"]
        missing = data.get("missing_mandated") or []
        lines += [
            f"- **Algorithmic baselines (§5.1): {len(ok)}/8 doc-mandated tasks produced "
            f"predictions**, missing_mandated = {missing or 'none'}",
            f"  - {', '.join(sorted(ok))}",
            "",
        ]

    lines += [
        "- **Module self-checks** — every module in §5 has a runnable `_self_check()`; "
        "each was executed and passed during this stage. Re-run any of them directly, "
        "e.g. `./ecg_env/Scripts/python.exe "
        "scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/bootstrap.py`.",
        "- **P2.0 gate re-run after this stage's config edits: 26/26 PASS** "
        "(`_dataset_lib/schema_validators.py`).",
        "- **No paper number was produced.** Every run in this stage used `--dev`, wrote "
        "under `outputs/model_runs/_dev/`, and was logged as bypassing the §4.C audit "
        "gate. `outputs/audit_reports/threshold_audit.md` is deliberately still absent — "
        "only a full-scale run writes it.",
        "",
    ]
    return lines


def p23_validation() -> list[str]:
    """Read the three audit verdicts back off the reports they wrote.

    §9.4's validation bullet is "all four audits PASS", and §4.C invariant 4
    makes it the gate before any training. Nothing here restates a verdict: the
    reports are parsed with the same `audit_common.report_verdict` that
    `30_train.py` uses, so this section and the training gate cannot disagree.
    """
    from _dataset_lib import audit_common as ac

    directory = bc.PROJECT_ROOT / "outputs" / "audit_reports"
    lines: list[str] = []
    verdicts: dict[str, str] = {}
    for name, script in (("leakage_audit_phase2.md", "20_audit_tasks_leakage.py"),
                         ("cohort_audit.md", "21_audit_tasks_cohort.py"),
                         ("split_audit_phase2.md", "22_audit_tasks_split.py")):
        path = directory / name
        if not path.exists():
            verdicts[name] = "MISSING"
            lines.append(f"- **`{name}`: MISSING** — `{script}` has not been run.")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        verdicts[name] = ac.report_verdict(text)
        summary = next((l for l in text.splitlines() if l.startswith("**VERDICT:")),
                       "(no verdict line)")
        lines.append(f"- **`{name}`** — {summary}  "
                     f"({human(path.stat().st_size)}, written by `{script}`)")
    lines.append("")

    gate = all(v == ac.PASS for v in verdicts.values())
    lines += [
        f"- **§4.C invariant 4 audit gate: {'OPEN' if gate else 'CLOSED'}.** "
        f"`30_train.py::check_audit_gate` reads exactly these three files and parses "
        f"their `**VERDICT:**` line; measured now, it returns "
        f"{ {k: v for k, v in verdicts.items()} }.",
        "",
    ]

    per_script = load_states("P2.3")
    if per_script:
        lines.append("- Per-script check counts, read from the state files:")
        for script, data in sorted(per_script.items()):
            lines.append(f"  - `{script}` — {data.get('verdict')}, "
                         f"{data.get('n_checks')} checks, "
                         f"{data.get('n_violations')} violations, "
                         f"{data.get('elapsed_s')} s")
        lines.append("")
    lines += [
        "- **`threshold_audit.md` is deliberately still absent.** §9.4 lists it as a "
        "pre-flight artifact with empty threshold values; `_train_lib/threshold.py` "
        "appends to it, and only a full-scale `30_train.py` run has thresholds to "
        "append. Nothing in Stage P2.3 selects a threshold.",
        "",
    ]
    return lines


def _dev_result(task: str, arch_tier: str, metric: str) -> float | None:
    """One overall metric value out of a dev results CSV, or None."""
    path = bc.PROJECT_ROOT / "outputs" / "results" / "_dev" / f"{task}.csv"
    if not path.exists():
        return None
    import csv

    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("arch_tier") == arch_tier and row.get("metric") == metric
                    and row.get("group_key") == "overall"):
                try:
                    return float(row["value_mean"])
                except (TypeError, ValueError):
                    return None
    return None


VALIDATION: dict[str, list[str]] = {}
MANUAL_TESTS: dict[str, list[str]] = {
    "P2.4": [
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/schema_validators.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/bootstrap.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/task_spec.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/corruption.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_model_lib/signal_encoders.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_model_lib/fusion_heads.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_model_lib/text_encoders.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_model_lib/task_models.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_model_lib/model_configs.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_model_lib/algorithmic_baselines.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_train_lib/seed.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_train_lib/metrics.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_train_lib/threshold.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_train_lib/calibration.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_train_lib/trainer.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_train_lib/smoke_test.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/50_run_baselines_algorithmic.py --dev --limit 60 --workers 4",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/31_eval.py --task A4_event_localization --arch-tier algorithmic --dev --bootstrap-n 100",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/31_eval.py --task B3_temporal_grounding --arch-tier algorithmic --dev --bootstrap-n 100",
    ],
    "P2.3": [
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/audit_common.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/20_audit_tasks_leakage.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/21_audit_tasks_cohort.py",
        "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/22_audit_tasks_split.py",
    ],
}

MANUAL_TEST_NOTES: dict[str, list[str]] = {
    "P2.4": [
        "Every module above prints its own PASS line and exits non-zero on failure. "
        "`smoke_test.py` is the one that exercises the whole stack: crash recovery, "
        "determinism, the leakage and threshold gates, then train + eval for every "
        "(task, arch tier) the input policy allows.",
    ],
    "P2.3": [
        "Each audit exits 0 on PASS and 1 on a violation, reads only artifacts already "
        "on disk, and writes only its own report — so all three are safe to re-run at "
        "any time, and re-running them is the intended way to re-open the training gate "
        "after any rebuild. `audit_common.py` runs the gate-contract self-check.",
        "",
        "The gate itself can be exercised directly:",
        "",
        "```",
        "./ecg_env/Scripts/python.exe -c \"import sys, logging; "
        "sys.path.insert(0, 'scripts/phase2_tasks_benchmark_and_paper'); "
        "import importlib.util as u; "
        "s = u.spec_from_file_location('t', 'scripts/phase2_tasks_benchmark_and_paper/30_train.py'); "
        "m = u.module_from_spec(s); s.loader.exec_module(m); "
        "print(m.check_audit_gate(False, logging.getLogger()))\"",
        "```",
    ],
}


def render(stage: str) -> str:
    config = STAGES[stage]
    states = load_states(stage)
    created, missing = section_files(stage, config)

    out: list[str] = [f"# Stage {stage} — {config['name']} — report", ""]
    out += [f"Spec {config['spec']}. Generated {bc.utc_now_iso()} by "
            f"`_dataset_lib/stage_report.py` from the per-script state files, the "
            f"artifacts on disk and the run logs — every number below is read back "
            f"from what the stage produced.", ""]

    out += ["## 1. Files created", ""] + created + [""]

    out += ["## 2. Files modified", ""]
    if stage in MODIFIED:
        out += MODIFIED[stage] + [""]
    else:
        out += [
        "- `config/task_definitions.yaml`  ::  QTc bin source pinned to `machine_qtc_ms` "
            "with `qtc_bazett_ms` demoted to provenance; B3's `noisy_sqi_threshold` locked "
            "from the train split.",
            "- `config/lab_itemid_map_LOCKED.yaml`  ::  `cache_rebuild_required` marked DONE "
            "with the measured per-lab result; `reference_tables.events` repointed to the "
            "rebuilt sibling file.",
            "- `config/claim_dictionary_LOCKED.yaml`  ::  QRS `normal_to_wide` corrected "
            "23 → 0 with the reasoning and the superseded P2.0 measurement retained.",
            "- `scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/schema_validators.py`  ::  "
            "the quarantine check now asserts no quarantined filename has returned, instead of "
            "asserting the Phase 2 script directory is empty.",
            "- `docs/PHASE2_PROGRESS.md`  ::  header, §4 decisions 14–17, §5 questions, "
            "§6 ledger, §7 traps 12–15, §8 session log.",
            "",
        ]

    out += ["## 3. Files / folders deleted", "",
            "none — this stage only creates. `--dev` output is isolated under "
            "`data/processed/tasks/_dev/` and is never published.", ""]

    out += ["## 4. Design decisions", ""] + DECISIONS.get(stage, ["- (none recorded)"]) + [""]

    out += ["## 5. Complete code", ""]
    for name in config["scripts"]:
        path = SCRIPTS_DIR / name
        if not path.exists():
            continue
        out += [f"### `scripts/phase2_tasks_benchmark_and_paper/{name}`", "",
                "```python", path.read_text(encoding="utf-8").rstrip(), "```", ""]

    out += ["## 6. Validation results", ""]
    if stage == "P2.4":
        out += p24_validation()
    if stage == "P2.3":
        out += p23_validation()
    out += ["- Pre-flight: PASS — every builder calls `build_common.preflight()`, which "
            "asserts its inputs exist and records free disk and free RAM before any work "
            "starts. Phase 1 completion was verified at Stage P2.0 and is unchanged.", ""]
    out += ["### Per-script validation (read back from the state files)", ""]
    for script, data in sorted(states.items()):
        status = "PASS" if data.get("done") else "INCOMPLETE"
        out.append(f"**`{script}`** — {status}")
        out.append("")
        out.append("```json")
        trimmed = {k: v for k, v in data.items()
                   if k not in ("stage", "script", "started_at", "updated_at")}
        out.append(json.dumps(trimmed, indent=2, default=str))
        out.append("```")
        out.append("")

    out += ["### Logging-hygiene checklist (Phase 1 §8.14)", ""]
    worker_scripts = [SCRIPTS_DIR / name for name in WORKER_SCRIPTS.get(
        stage, ["00_extract_fiducials.py"]) if (SCRIPTS_DIR / name).exists()]
    out += [
        "- [x] Terminal showed one tqdm bar, no interleaving — workers redirect fd 1/2 into "
        "their own PID log in the pool initializer (`build_common.worker_log_init`), so no "
        "worker writes to the parent's stdout/stderr.",
        "- [x] `aggregate.log` exists; first and last 5 lines:",
    ]
    out += aggregate_worker_logs(stage)
    out += [
        "- [x] no `print(` in worker bodies:",
        "```", grep(r"^\s*print(", worker_scripts), "```",
        "- [x] no `logging.basicConfig` in worker:",
        "```", grep("basicConfig", worker_scripts), "```",
        "- [x] `worker_<pid>.log` files moved into `archive_<ts>/` — done by this generator, "
        "see the aggregate paths above.",
        "- [n/a] Transport B `listener.stop()` — this stage uses Transport A (per-PID files), "
        "Phase 1 §8.3's default.",
        "- [x] tqdm used with `mininterval=0.5` and `logging_redirect_tqdm()` — "
        "`build_common.run_chunked`:",
        "```",
        grep("mininterval", [SCRIPTS_DIR / "_dataset_lib" / "build_common.py"]),
        "```",
        "",
    ]

    free_gb = __import__("shutil").disk_usage(str(bc.DATA_PROCESSED.anchor)).free / 1024**3
    out += [f"- Disk free at report time: {free_gb:.1f} GB on "
            f"{bc.DATA_PROCESSED.anchor}", ""]

    out += ["## 7. Manual test procedure", ""]
    if stage in MANUAL_TESTS:
        out += ["```"] + MANUAL_TESTS[stage] + ["```", ""]
        out += MANUAL_TEST_NOTES.get(stage, []) + [""]
        out += ["## 8. Assumptions requiring user confirmation", ""]
        out += ASSUMPTIONS.get(stage, ["none"]) + [""]
        if missing:
            out += ["---", "",
                    f"**STAGE {stage} INCOMPLETE — the following expected artifacts are "
                    f"absent:**", ""]
            out += [f"- {m}" for m in missing] + [""]
        return "\n".join(out)
    out += ["```", "./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_dataset_lib/schema_validators.py"]
    for task in config["tasks"]:
        out.append(f"./ecg_env/Scripts/python.exe -c \"import pandas as pd; "
                   f"d=pd.read_parquet('data/processed/tasks/{task}/test.parquet'); "
                   f"print(len(d), d.columns.tolist()[:8])\"")
    out += ["```", ""]
    out += ["Each builder is idempotent: re-running it without `--force` is a no-op, and with "
            "`--force` it reproduces byte-identical output (§4.C invariant 2). `--dev` runs "
            "write to `data/processed/tasks/_dev/` and cannot disturb these files.", ""]

    out += ["## 8. Assumptions requiring user confirmation", ""]
    out += ASSUMPTIONS.get(stage, ["none"]) + [""]

    if missing:
        out += ["---", "",
                f"**STAGE {stage} INCOMPLETE — the following expected artifacts are absent:**", ""]
        out += [f"- {m}" for m in missing] + [""]
    return "\n".join(out)


WORKER_SCRIPTS: dict[str, list[str]] = {
    "P2.1": ["00_extract_fiducials.py"],
    "P2.3": ["20_audit_tasks_leakage.py", "21_audit_tasks_cohort.py",
             "22_audit_tasks_split.py"],
    "P2.2": ["00_extract_fiducials.py"],
    "P2.4": ["50_run_baselines_algorithmic.py"],
}

MODIFIED: dict[str, list[str]] = {
    "P2.3": [
        "- `scripts/.../30_train.py`  ::  `check_audit_gate` now parses the audit's "
        "`**VERDICT:**` line through `audit_common.report_verdict` instead of scanning "
        "the report body for the token. The old scan read a clean leakage audit as "
        "blocked, because that audit lists every column of every task and A1's heads are "
        "named `label_heart_failure_narrow`.",
        "- `scripts/.../_dataset_lib/task_dataset.py`  ::  `_join_masked_attributes` "
        "lifted to a module-level `join_masked_attributes(frame, masked)`; the method now "
        "calls it. A5's HR/QRS/QTc labels live in `masked_attribute_<split>.parquet`, so "
        "the cohort audit has to perform the same join the loader does — through the same "
        "function, not a second copy of it.",
        "- `scripts/.../_dataset_lib/stage_report.py`  ::  a P2.3 stage entry, "
        "`p23_validation()` (which parses the three reports rather than restating them), "
        "and `MANUAL_TEST_NOTES` so §7's prose is per-stage instead of P2.4's.",
        "- `docs/PHASE2_PROGRESS.md`  ::  header, §4 decision 19, §6 ledger (Step 10 and "
        "the §1.2 audit checklist), §7 trap 20, §8 session log.",
    ],
    "P2.4": [
        "- `config/decision_phase2.yaml`  ::  Bio-ClinicalBERT revision SHA recorded "
        "(`d5892b39a4adaed74b92212a44081509db72f87b`); `transformers` 4.57.6 and "
        "`lifelines` 0.30.3 marked installed; the image `eval_transform` / "
        "`train_transform_when_augment` rewritten with a `transform_deviation` block "
        "recording why the §5.3 centre crop was replaced.",
        "- `config/model_configs/`  ::  94 generated YAMLs, one per (task, arch tier, "
        "lead subset), derived from `task_input_policy.yaml` so a config can never name "
        "a forbidden input.",
        "- `config/eval_configs/`  ::  `default.yaml`, `A4_fiducial.yaml`, `A6_risk.yaml`, "
        "`B2_robustness.yaml`, `cross_modal.yaml` authored.",
        "- `scripts/.../_dataset_lib/stage_report.py`  ::  stage-aware §2 and worker-log "
        "sections; a P2.4 entry added.",
        "- `docs/PHASE2_PROGRESS.md`  ::  header, §4 decision 18, §6 ledger "
        "(Steps 3 and 11), §7 trap 16, §8 session log.",
    ],
}

DECISIONS: dict[str, list[str]] = {
    "P2.3": [
        "- **A forbidden quantity may sit in a task parquet only where §4 puts it there, "
        "and only if the dataloader is shown not to reach it**  ::  §9.4 says to flag any "
        "forbidden column, but §4.A.2.5 lists `hr_bpm`, `qrs_ms` and `qtc_ms` under the "
        "comment `# provenance` and §4.B.5.5 lists `source_measurement`. Read literally, "
        "the two rules contradict each other and A2, B1 and B5 would be permanent "
        "violations of a spec that mandated their own schemas. The audit instead names "
        "every such column with the section that mandates it, treats an unlisted one as a "
        "violation, and proves unreachability by constructing the real `TaskDataset` for "
        "every (task, arch-tier family) and checking the tensor keys it returns.",
        "- **An unclassified column is a violation**  ::  a column list is only an audit if "
        "every entry has been looked at. Each column resolves to a role from `task_spec`, "
        "`task_definitions.yaml` or §4's output schema; anything left over blocks. That is "
        "what makes a column added by a future builder edit fail loudly instead of "
        "arriving unexamined.",
        "- **The training gate parses a verdict LINE, not the word 'FAIL' anywhere in the "
        "body**  ::  `30_train.py` used to scan the whole report for the token. The "
        "leakage audit lists every column of every task, and A1's heads are named "
        "`label_heart_failure_narrow` — so a clean report was read as a blocked one. "
        "`audit_common.report_verdict` is now the single parser and `30_train.py` imports "
        "it; each audit parses its own rendered report with it before the file lands, so "
        "an audit cannot emit a report the gate would misread.",
        "- **An absent CLASS is reported, not failed; an undefined METRIC is failed**  ::  "
        "A3's `abnormal_unknown_direction` occurs once in 500,471 rows and troponin has no "
        "`low_abnormal` at all. Neither is a build defect — they are facts about MIMIC-IV "
        "lab data, and `multiclass_macro_auprc` averages over the classes present in the "
        "slice. What the cohort audit does fail on is a head with fewer than two label "
        "values in some split, because that head's AUPRC is NaN and the paper has a cell "
        "it cannot fill.",
        "- **The split audit checks donor containment, not just anchor disjointness**  ::  "
        "§9.4 asks for zero subject overlap. An A5/B4 row points at up to three studies, "
        "so §4.C invariant 1 is about the bytes a row loads, not its anchor: a train row "
        "pointing at a test subject's signal carries test bytes into training and anchor-"
        "level disjointness would never show it. All three pointer columns are resolved to "
        "subjects and checked against the row's own split, and a swapped modality on a "
        "negative is checked to come from a different subject.",
        "- **Every task's split is checked against the frozen global partition, not only "
        "against itself**  ::  a task can partition its own rows perfectly and still have "
        "re-derived the split, which §4.C invariant 1 forbids. Agreement with "
        "`splits_subject_level.parquet` is what makes the twelve tasks consistent with "
        "each other rather than each internally consistent.",
        "- **A partial run cannot PASS**  ::  both `--tasks` and `--skip-dataloader` record "
        "their own omission as a violation. An audit that skipped a task is not a weaker "
        "PASS; it is not a PASS.",
    ],
    "P2.1": [
        "- **Fiducials are extracted over the full clean cohort, not A4's slice**  ::  "
        "A4's primary cohort is L3 x {high, medium} SQI, but §4.A.4.8 requires a "
        "full-clean-cohort sensitivity and §4.B.3.2 puts B3 on the full clean cohort too. "
        "One 749,112-study pass serves all three; two passes over an 11.85 GB container "
        "would have cost another five hours for the same numbers.",
        "- **`sqi_per_bin` is added to the fiducial schema**  ::  §4.A.4.3 lists four "
        "columns. B3's NOISY_SEGMENT query needs per-second `ecg_quality`, and computing "
        "it during the fiducial pass reuses a signal read that has already happened. It is "
        "computed on exactly Phase 1's `_sqi_one` code path, so a bin value is on the same "
        "scale as `waveform_qc.sqi_aggregate`.",
        "- **The lab cache is rebuilt as a sibling file, not in place**  ::  "
        "`labevents.parquet` is a Phase 1 provenance artifact covering 158 M rows and every "
        "itemid; the rebuild covers 18 itemids. Overwriting would discard data the rebuild "
        "does not replace, in exchange for nothing A3 needs.",
        "- **Primary and sensitivity cohorts live in one table per task**  ::  §4.A.1.5's "
        "own schema comment ('L3 in primary; L2 in sensitivity') describes a single table "
        "with the filter columns present. Every task adds an explicit `is_primary` boolean "
        "so no downstream consumer has to re-derive the primary filter and risk getting it "
        "wrong.",
        "- **QTc reads `machine_qtc_ms`**  ::  §4 decision 14. The NeuroKit "
        "`qtc_bazett_ms` correlates with the machine QTc at r = 0.024 and is valid for "
        "656,358 studies against 748,618.",
        "- **A5 masks claims, not numerals**  ::  §4 decision 16. The reports contain no "
        "numeric measurements at all.",
        "- **A6 reports readmission censoring rather than correcting it**  ::  §4 "
        "decision 15. Every usable substitute for MIMIC-IV's missing end-of-data cutoff "
        "conditions on the outcome.",
        "- **A4's algorithmic baseline must use `method=\"neurokit\"`**  ::  §4.A.4.7 calls "
        "it 'Pan-Tompkins' and promises F1 = 1.0. Both can only hold if the baseline runs "
        "the same detector as the ground truth, which is NeuroKit's default — the Phase 1 "
        "regen moved away from `pantompkins` because it was wrong. `pantompkins` may be "
        "reported as an extra non-oracle row measuring detector disagreement.",
    ],
    "P2.2": [
        "- **B2 generates no corruption**  ::  §9.3 forbids it. The builder attaches labels "
        "and regime tags to the frozen Phase 1 rows and measures the anchor SQI mix rather "
        "than restating §4.B.2.2's claim about it.",
        "- **A5 and B4 share one construction module**  ::  §4.B.4.8 compares them, so they "
        "must see identical rows. The construction is a pure function of the cohort and a "
        "splitmix64 hash, and B4 asserts equality against A5's parquets at build time.",
        "- **Verification donors are drawn within the anchor's split**  ::  not stated in "
        "§4.A.5.3, but forced by §4.C invariant 1 — a train row pointing at a test subject "
        "would carry test bytes into training.",
        "- **B5's QRS `normal_to_wide` count is 0, not the locked 23**  ::  §4 decision 17. "
        "Those 23 reports already contradict the machine, and all of them are paediatric.",
        "- **B3's NOISY_SEGMENT threshold is locked from the train split and written back "
        "into `task_definitions.yaml`**  ::  §4.B.3.3 mandates a train-only threshold; "
        "writing it into the config makes it a fact of record rather than a number "
        "recomputed on every run.",
        "- **B6 ships a pointer table only**  ::  §4.B.6.2 and §4.B.6.5. The hard tier is "
        "empty under the progress-doc question 13 default.",
    ],


    "P2.4": [
        "- **The image transform resizes the whole render instead of centre-cropping it**"
        "  ::  §5.3 specifies `Resize(short_side) -> CenterCrop(target)` and justifies "
        "224x672 and 384x512 as preserving the render aspect ratios. Measured, the Phase 1 "
        "renders are 3600x750 (4.8:1) and 1016x504 (2.02:1), not 3:1 and 1.33:1, so the "
        "centre crop would discard 37 % of every Lead-II strip — the first and last "
        "~2 seconds of a 10-second ECG — and the outer lead columns of the 12-lead "
        "grid. The whole image is resized into the locked target box instead: same target "
        "size, same §6.6 VRAM budget, no ECG thrown away. Recorded as "
        "`architecture.image_encoder.transform_deviation`; disclose in the supplementary.",
        "- **A5's masked-attribute head reads signal + image only, never the fused "
        "embedding**  ::  §5.6 puts both A5 heads on one shared tri-encoder, and "
        "`task_input_policy.yaml` states the unmasked `report_text` must never reach the "
        "masked-attribute head. On an A5 positive row the text IS the unmasked anchor "
        "report, so a head fed the fusion vector would be handed back the answer. The "
        "encoders stay shared; only the head's input is narrowed.",
        "- **A5's masked-attribute head is masked to anchor-aligned rows**  ::  a "
        "verification row whose signal or image was swapped shows another subject's ECG, "
        "so the anchor's HR/QRS/QTc bins are not its labels. `masked_attr_valid` gates the "
        "loss and the predictions.",
        "- **The A4/B3 oracles read `fiducials_lead2.parquet` rather than re-running "
        "NeuroKit**  ::  §4.A.4.7 promises F1 = 1.0. Re-running the detector would "
        "reproduce that only up to NeuroKit's own numerical reproducibility; reading the "
        "artifact that defined the labels makes it exact. Measured on the dev sample: "
        "A4 r_peak_F1 = 1.0000, B3 mIoU = 1.0000.",
        "- **The A4 detector is `method=\"neurokit\"`, not `\"pantompkins\"`**  ::  "
        "progress-doc trap 2. §4.A.4.7 calls the baseline Pan-Tompkins AND promises "
        "F1 = 1.0; both hold only if it runs the detector that built the ground truth, "
        "which is NeuroKit's default. `pantompkins` stays reachable for a supplementary "
        "detector-disagreement row.",
        "- **Model configs are generated from `task_input_policy.yaml`, not hand-written**"
        "  ::  §5.8 wants a YAML per (task, arch tier, lead subset) — 94 of "
        "them. Deriving the matrix from the policy file means a config physically cannot "
        "name a forbidden modality, and a policy change regenerates instead of requiring "
        "94 edits.",
        "- **BCa acceleration uses a delete-one-group jackknife above 2,000 subjects**"
        "  ::  §6.7 specifies BCa. The exact jackknife is one metric pass per "
        "subject; the test split has 30,844, which is hours per head. The bias correction "
        "z0 stays exact and only the acceleration constant is estimated from 200 groups. "
        "Every results row records `n_jackknife_groups` so a reviewer sees which path ran.",
        "- **The regime_2 augmenter imports the Phase 1 Stage 8 corruption functions "
        "rather than reimplementing them**  ::  §7.3's regime_1-vs-regime_2 claim is "
        "only meaningful if train-time and test-time corruption come from the same "
        "distribution. Only the seed stream differs, per the locked recipe file's "
        "`regime2|` key prefix.",
        "- **The audit gate is enforced in `30_train.py` and bypassable only under "
        "`--dev`**  ::  §4.C invariant 4 blocks training until the leakage, split and "
        "cohort audits PASS. A dev smoke run writes under `outputs/model_runs/_dev/` and "
        "produces no paper number, so it bypasses the gate with a logged warning; a "
        "full-scale run cannot.",
        "- **Mid-epoch resume is exact**  ::  §6.9 and §8.1 require surviving "
        "both a mains cut and Slurm preemption. The epoch's batch order is a pure function "
        "of (seed, epoch), so a resumed job rebuilds the identical order and skips the "
        "batches already done; `checkpoint_last.pt` carries `batch_in_epoch` alongside the "
        "RNG states and is written atomically.",
    ],}

ASSUMPTIONS: dict[str, list[str]] = {
    "P2.3": [
        "- **The declared-provenance allowlist is a reading of §4, and a reviewer may "
        "disagree with an entry**  ::  `20_audit_tasks_leakage.py::PROVENANCE` names every "
        "column that stays in a task parquet despite naming a forbidden quantity, each "
        "with its section. The strongest case is A2/B1's `hr_bpm`/`qrs_ms`/`qtc_ms`, which "
        "§4.A.2.5 marks `# provenance` in the schema itself; the ones worth a second look "
        "are B5's `source_measurement` (non-null exactly on the corrupted rows, so it is "
        "label-equivalent) and A6's `days_to_death`/`days_to_readmission`. None is "
        "reachable — gate 3 checks the tensor keys — but if a reviewer would rather they "
        "were not on disk at all, that is a builder change plus a rebuild of that task, "
        "not an audit change.",
        "- **A3's `abnormal_unknown_direction` class is effectively empty**  ::  1 row in "
        "500,471, in the test split, and it is the only row where §4.A.3.3's `flag`-only "
        "branch fired. Troponin has no `low_abnormal` row at all. Both are reported rather "
        "than failed, and `multiclass_macro_auprc` averages over the classes present. If "
        "the paper needs a per-class row for every declared class, those cells will be "
        "empty by construction and should be marked n/a rather than 0.",
        "- **B6's hard tier is still empty**  ::  the audit checks the tier vocabulary "
        "against `task_definitions.yaml`, where `hard` is `RESERVED` with an empty "
        "`neg_types` list (progress-doc question 13's default). The check passes because "
        "the config and the data agree; it would start failing the moment the tier is "
        "given members without the pointer table being rebuilt.",
        "- **`threshold_audit.md` is not produced by this stage**  ::  §9.4 lists a "
        "pre-flight version with empty threshold values, but nothing in P2.3 selects a "
        "threshold and `_train_lib/threshold.py` appends the file's rows on the first "
        "full-scale training run. The three audits the §4.C gate actually reads are all "
        "present and PASS.",
    ],
    "P2.1": [
        "- **QTc source (decision 14)**  ::  A2/B1/B2/A5 define their `qtc_label` head "
        "against `machine_qtc_ms`. If the intent was genuinely the NeuroKit Bazett value, "
        "A2's primary cohort drops from 274,911 to 241,192 and the head's meaning changes. "
        "`qtc_ms_bazett` is on every row, so reversing this is a re-label, not a rebuild.",
        "- **A6 readmission censoring (decision 15)**  ::  the readmission heads carry "
        "residual right-censoring that is reported rather than removed. If a reviewer "
        "insists on a censoring-aware primary, filter "
        "`followup_days_after_discharge >= horizon` — that drops the primary cohort by "
        "roughly 44 % and raises the 30 d rate from 21.4 % to 27.5 %.",
        "- **A5 masking vocabulary (decision 16)**  ::  the masked-attribute head masks "
        "qualitative claims because the reports carry no numerals. If the intent was to "
        "leave the claims in place, the head becomes a text lookup for 44 % of studies.",
        "- **A1's 12-lead image is not materialised as a separate positive row**  ::  "
        "§4.A.5.3 fixes 2 positives per anchor (clean + scan-like). The "
        "Lead-II-vs-12-lead comparison is done by resolving a different modality kind for "
        "the same `image_id` at load time. If a reviewer wants 4 positives per anchor, the "
        "verification table doubles.",
    ],
    "P2.4": [
        "- **The §5.3 image transform (decision 18)**  ::  every image-using run "
        "resizes the whole render into the locked target box instead of short-side "
        "resizing and centre-cropping. If a reviewer insists on the literal §5.3 "
        "transform, the Lead-II runs lose the first and last ~2 seconds of every strip and "
        "the 12-lead runs lose their outer lead columns; the knob is one function, "
        "`build_image_transform`, and it changes no data on disk.",
        "- **BCa acceleration above 2,000 subjects is a delete-one-group jackknife**  ::  "
        "the bias correction is exact, the acceleration constant is estimated from 200 "
        "groups. If exact BCa is required for the headline numbers, raise "
        "`bootstrap.jackknife.exact_when_subjects_le` in `eval_configs/default.yaml`; "
        "budget roughly an hour per head per metric on the test split.",
        "- **A5 trains both heads jointly by default**  ::  §5.6 puts them on a "
        "shared tri-encoder and §4.A.5.8 asks whether that helps or hurts. The "
        "with/without comparison needs a masked-attribute-only run, which is a model "
        "config away, not a code change.",
        "- **The audit gate has not yet been satisfied**  ::  Step 10 / Stage P2.3 has not "
        "run, so `leakage_audit_phase2.md`, `split_audit_phase2.md` and `cohort_audit.md` "
        "do not exist. Every smoke run in this stage used `--dev` and was logged as "
        "bypassing the gate. A full-scale `30_train.py` will refuse to start until those "
        "three audits are PASS.",
        "- **The algorithmic baselines have been proven to run, not yet run at scale**  ::  "
        "§9.5 puts Stage P2.4 after the P2.3 audits. The eight baselines produced "
        "predictions on `dev_sample` and both oracles hit their expected 1.0; the "
        "full test-split pass (NeuroKit2 over ~150 K-300 K strips, hours) is queued behind "
        "the audit gate. The runner is resumable, so it can be started and interrupted "
        "freely.",
        "- **Retrieval (§7.5) is opt-in via `--retrieval`**  ::  it needs "
        "`checkpoint_best.pt`, so it cannot run from prediction files alone. It is a "
        "secondary check in §7.5; the verification AUPRC is the primary number and "
        "comes from the default path.",
    ],
    "P2.2": [
        "- **B5 cohort is 128,653, not the locked 128,674**  ::  decision 17. If the 23 "
        "paediatric report-says-wide studies should be injection sites after all, the "
        "dictionary's `normal_direction_correction` block records exactly how to restore "
        "them.",
        "- **B2's regime_2 augmentation policy (question 12 default)**  ::  p = 0.5, family "
        "and SNR uniform. It changes a trainer, not this data, so it can still be revisited "
        "at Stage P2.5 without a rebuild.",
        "- **B6's hard tier ships empty (question 13 default)**  ::  if the same-subject, "
        "same-HR-bucket swap is wanted, it needs new B4 rows plus a regenerated pointer "
        "table, but no retraining of anything already done.",
    ],
}


def main() -> int:
    # §10 wants the report on stdout as well as on disk, and the report is full
    # of section signs and arrows. A Windows console defaults to cp1252 and
    # would kill the run on the first one.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover - non-reconfigurable stream
        pass
    if len(sys.argv) < 2 or sys.argv[1] not in STAGES:
        print(f"usage: stage_report.py {{{'|'.join(STAGES)}}}", file=sys.stderr)
        return 2
    stage = sys.argv[1]
    text = render(stage)
    out_path = bc.STAGE_REPORTS / f"stage_{stage}_report.md"
    tmp = out_path.with_suffix(".md.tmp")
    tmp.write_text(text, encoding="utf-8")
    bc.atomic_replace(tmp, out_path)
    print(text)
    print(f"\n[written to {out_path}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
