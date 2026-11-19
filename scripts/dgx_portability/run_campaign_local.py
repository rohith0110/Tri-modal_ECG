#!/usr/bin/env python3
"""Run whole campaigns on the data-laptop's own GPU (decision 26).

    ./ecg_env/Scripts/python.exe scripts/dgx_portability/run_campaign_local.py 5 6 9
    ./ecg_env/Scripts/python.exe scripts/dgx_portability/run_campaign_local.py 5 --tasks A1_ecg_diagnosis
    ./ecg_env/Scripts/python.exe scripts/dgx_portability/run_campaign_local.py --check 5 6 9

The Windows counterpart of `slurm/_campaign_body.sh` for the campaigns this
machine claimed in R2 (`claims/campaign_<n>` = `data-laptop ...`). Same configs,
seeds and run order (`campaign_runs.py`), same int16 pieces from R2, and the same
block-shuffled windows: every piece is kept on disk and `chunk_cycle.py` replays
the DGX's window order without staging (TRIMODAL_CHUNK_ALL_RESIDENT).

Each finished run is pushed to `r2:trimodal-results/data-laptop/model_runs/...`
and verified; each (task, tier) is then evaluated on this machine's CPUs while
the next run trains, and its CSV pushed to `data-laptop/results/`. Fold it into the
root with `merge_acct2_results.py --prefix data-laptop --apply`.

Re-running is the resume path: finished runs are skipped, an interrupted one
resumes from its own checkpoint_last.pt (mains power here is unreliable).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
SCRIPTS = PROJECT_ROOT / "scripts" / "phase2_tasks_benchmark_and_paper"
TRAIN = SCRIPTS / "30_train.py"
EVAL = SCRIPTS / "31_eval.py"
CAMPAIGN_RUNS = PROJECT_ROOT / "scripts" / "dgx_portability" / "campaign_runs.py"
CONFIG_DIR = PROJECT_ROOT / "config" / "model_configs"
DATA = PROJECT_ROOT / "data" / "processed"
OUTPUTS = PROJECT_ROOT / "outputs"
LOG_DIR = OUTPUTS / "local_campaigns"

ME = (PROJECT_ROOT / ".machine").read_text(encoding="utf-8").strip()    # data-laptop
R2_RESULTS = os.environ.get("R2_RESULTS", "r2:trimodal-results")
REMOTE = f"{R2_RESULTS}/{ME}"
N_PIECES = 8
EVAL_CPUS = 12          # ponytail: half the 24 cores; training's loader keeps the rest

# The chunked bases each claimed campaign reads (campaigns.sh, field 6).
CAMPAIGN_PIECES: dict[int, tuple[str, ...]] = {
    5: ("signals_12lead",),
    6: ("signals_12lead",),
    9: ("signals_raw",),
}
RUN_ARTIFACTS = ("test_predictions.parquet", "val_predictions.parquet", "train_log.jsonl",
                 "checkpoint_best.pt", "train_config.yaml", "thresholds.json",
                 "run_summary.json")


@dataclass(frozen=True)
class Run:
    task: str
    tier: str
    seed: int
    config: str

    @property
    def directory(self) -> Path:
        return OUTPUTS / "model_runs" / self.task / self.tier / f"seed_{self.seed}"


def log(message: str) -> None:
    line = f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {message}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "runner.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def rclone(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["rclone", *args], capture_output=True, text=True)


def campaign_runs(campaign: int, tasks: list[str]) -> list[Run]:
    command = [PYTHON, str(CAMPAIGN_RUNS), str(campaign)] + (["--tasks", *tasks] if tasks else [])
    output = subprocess.run(command, capture_output=True, text=True, check=True).stdout
    runs = []
    for line in output.splitlines():
        if line.strip():
            task, tier, seed, config = line.split()
            runs.append(Run(task, tier, int(seed), config))
    return runs


def missing_pieces(campaign: int) -> list[str]:
    missing = []
    for base in CAMPAIGN_PIECES[campaign]:
        for piece in range(N_PIECES):
            if not (DATA / base / f"piece_{piece:03d}.h5").is_file():
                missing.append(f"{base}/piece_{piece:03d}.h5")
        if not (DATA / base / "assignment.parquet").is_file():
            missing.append(f"{base}/assignment.parquet")
    return missing


def claim_owner(campaign: int) -> str:
    result = rclone("cat", f"{R2_RESULTS}/claims/campaign_{campaign}")
    return result.stdout.split()[0] if result.returncode == 0 and result.stdout.strip() else ""


def write_claim(campaign: int, state: str) -> None:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    subprocess.run(["rclone", "rcat", f"{R2_RESULTS}/claims/campaign_{campaign}"],
                   input=f"{ME} {state} {stamp}\n", text=True, check=True)


def is_complete(run: Run) -> bool:
    summary = run.directory / "run_summary.json"
    if not summary.is_file():
        return False
    return json.loads(summary.read_text(encoding="utf-8")).get("status") == "complete"


def train_env(campaign: int) -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "CAMPAIGN": str(campaign),
        "TRIMODAL_SIGNAL_INT16": "1",
        "TRIMODAL_CHUNKED": "1",
        "TRIMODAL_CHUNK_PIECES": str(N_PIECES),
        "TRIMODAL_CHUNK_ALL_RESIDENT": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "PYTHONUNBUFFERED": "1",
    })
    return env


def push_run(run: Run) -> bool:
    """Copy the run's artifacts to R2, verify by checksum. Nothing is deleted."""
    relative = run.directory.relative_to(OUTPUTS).as_posix()
    present = [name for name in RUN_ARTIFACTS if (run.directory / name).is_file()]
    include = [arg for name in present for arg in ("--include", name)]
    target = f"{REMOTE}/{relative}"
    copied = rclone("copy", "--checksum", "--s3-no-check-bucket", *include,
                    str(run.directory), target)
    checked = rclone("check", "--one-way", *include, str(run.directory), target)
    if copied.returncode or checked.returncode:
        log(f"PUSH FAILED {relative}: {(copied.stderr + checked.stderr)[-500:]}")
        return False
    log(f"pushed + verified {relative} ({len(present)} files)")
    return True


def push_eval(task: str, since: float) -> bool:
    """The task's CSV/extras, plus any figure or audit file this eval wrote."""
    ok = True
    results = OUTPUTS / "results"
    for name in (f"{task}.csv", f"{task}_extras.json"):
        if (results / name).is_file():
            ok &= rclone("copyto", "--checksum", "--s3-no-check-bucket",
                         str(results / name), f"{REMOTE}/results/{name}").returncode == 0
    for folder in ("figures", "audit_reports"):
        root = OUTPUTS / folder
        for path in root.rglob("*") if root.is_dir() else []:
            if path.is_file() and path.stat().st_mtime >= since:
                remote = f"{REMOTE}/{folder}/{path.relative_to(root).as_posix()}"
                ok &= rclone("copyto", "--checksum", "--s3-no-check-bucket",
                             str(path), remote).returncode == 0
    log(f"eval push {task}: {'ok' if ok else 'FAILED'}")
    return ok


class EvalLane:
    """One background eval at a time, so training keeps its loader cores."""

    def __init__(self) -> None:
        self.queue: list[tuple[str, str]] = []
        self.current: tuple[str, str, subprocess.Popen[bytes], float] | None = None
        self.failed = 0

    def submit(self, task: str, tier: str) -> None:
        if (task, tier) not in self.queue:
            self.queue.append((task, tier))
        self.poll()

    def poll(self) -> None:
        if self.current is not None:
            task, tier, process, started = self.current
            if process.poll() is None:
                return
            if process.returncode == 0:
                log(f"eval done {task} / {tier}")
                self.failed += 0 if push_eval(task, started) else 1
            else:
                log(f"EVAL FAILED {task} / {tier} (exit {process.returncode})")
                self.failed += 1
            self.current = None
        if self.queue:
            task, tier = self.queue.pop(0)
            env = dict(os.environ, SLURM_CPUS_PER_TASK=str(EVAL_CPUS), PYTHONUNBUFFERED="1")
            handle = (LOG_DIR / f"eval_{task}_{tier}.log").open("ab")
            process = subprocess.Popen([PYTHON, str(EVAL), "--task", task, "--arch-tier", tier],
                                       cwd=PROJECT_ROOT, env=env, stdout=handle,
                                       stderr=subprocess.STDOUT)
            self.current = (task, tier, process, time.time())
            log(f"eval started {task} / {tier} ({EVAL_CPUS} CPUs)")

    def drain(self) -> None:
        while self.current is not None or self.queue:
            self.poll()
            time.sleep(30)


def run_campaign(campaign: int, tasks: list[str], evals: EvalLane) -> int:
    missing = missing_pieces(campaign)
    if missing:
        log(f"campaign {campaign}: {len(missing)} piece file(s) missing, e.g. {missing[0]} -- "
            f"rclone copy r2:trimodal-data/chunks/<base> data/processed/<base> first")
        return 1
    owner = claim_owner(campaign)
    if owner != ME:
        log(f"campaign {campaign}: claimed by '{owner}', not {ME} -- refusing")
        return 1
    runs = campaign_runs(campaign, tasks)
    log(f"=== campaign {campaign}: {len(runs)} run(s) ===")
    status = 0
    for run in runs:
        name = f"{run.task} / {run.tier} / seed {run.seed}"
        if is_complete(run):
            log(f"skip {name} (complete)")
        else:
            log(f"train {name}")
            handle = (LOG_DIR / f"c{campaign}_{run.task}_{run.tier}_{run.seed}.log").open("ab")
            code = subprocess.run([PYTHON, str(TRAIN), "--model-config",
                                   str(CONFIG_DIR / run.config), "--seed", str(run.seed)],
                                  cwd=PROJECT_ROOT, env=train_env(campaign),
                                  stdout=handle, stderr=subprocess.STDOUT).returncode
            handle.close()
            if code != 0 or not is_complete(run):
                log(f"TRAIN FAILED {name} (exit {code}), continuing")
                status = 1
                evals.poll()
                continue
        if not push_run(run):
            status = 1
        seeds = [r for r in runs if (r.task, r.tier) == (run.task, run.tier)]
        if run is seeds[-1] and all(is_complete(r) for r in seeds):
            evals.submit(run.task, run.tier)
        evals.poll()
    if status == 0 and all(is_complete(r) for r in campaign_runs(campaign, [])):
        write_claim(campaign, "done")
        log(f"campaign {campaign}: every run complete, claim set to done")
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("campaigns", type=int, nargs="+", choices=sorted(CAMPAIGN_PIECES))
    parser.add_argument("--tasks", nargs="*", default=[], help="only these tasks")
    parser.add_argument("--check", action="store_true",
                        help="report pieces, claim and run counts; train nothing")
    args = parser.parse_args()
    os.chdir(PROJECT_ROOT)

    if args.check:
        for campaign in args.campaigns:
            runs = campaign_runs(campaign, args.tasks)
            done = sum(is_complete(r) for r in runs)
            print(f"campaign {campaign}: claim={claim_owner(campaign)!r} "
                  f"missing pieces={len(missing_pieces(campaign))} runs={done}/{len(runs)} complete")
        return 0

    evals = EvalLane()
    status = 0
    for campaign in args.campaigns:
        status |= run_campaign(campaign, args.tasks, evals)
    log("training finished; waiting for evals")
    evals.drain()
    return 1 if status or evals.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
