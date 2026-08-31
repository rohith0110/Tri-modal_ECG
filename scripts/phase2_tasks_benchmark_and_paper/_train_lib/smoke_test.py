"""End-to-end smoke test of the Step-3 training/eval stack on `dev_sample/`.

    ./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/_train_lib/smoke_test.py
    ./ecg_env/Scripts/python.exe .../smoke_test.py --tasks A2_measurement_blind --tiers signal

This is the gate §8.2.1 asks for: "the laptop authors and smoke-tests every
script against a fixed 5,000-study sample". It proves the code RUNS on real
bytes -- it proves nothing about the numbers, which come from the DGX.

What it covers:

* every trainable task x one representative arch tier of each family, trained
  for two batches and evaluated end to end;
* **crash recovery**, twice: an interrupted run resumes mid-epoch at the exact
  batch it stopped on, and a completed epoch resumes at the epoch boundary with
  optimizer, scheduler, RNG and best-metric state intact;
* **preemption**, by invoking the trainer's own SIGTERM handler and confirming
  it sets the stop flag rather than writing from inside the handler;
* the two gates that must fail loudly: a forbidden modality and a threshold
  selected on anything but `val`.

Everything writes under `outputs/model_runs/_dev/` and
`data/processed/tasks/_dev/`, so a smoke run cannot touch a real artifact.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _dataset_lib import build_common as bc                            # noqa: E402
from _dataset_lib.task_dataset import TaskDataset, plan_from_config    # noqa: E402
from _dataset_lib.task_spec import TASKS, get_task                     # noqa: E402
from _model_lib.model_configs import MODEL_CONFIG_DIR, load_model_config  # noqa: E402
from _model_lib.task_models import build_model, train_class_stats      # noqa: E402
from _train_lib.seed import set_seed                                   # noqa: E402
from _train_lib.trainer import TrainConfig, Trainer, build_batch_order  # noqa: E402

# The interpreter running this file -- the venv's own python whether that is
# `ecg_env/Scripts/python.exe` on Windows or `ecg_env/bin/python` on the DGX.
PYTHON = Path(sys.executable)
TRAIN_SCRIPT = bc.PROJECT_ROOT / "scripts" / "phase2_tasks_benchmark_and_paper" / "30_train.py"
EVAL_SCRIPT = bc.PROJECT_ROOT / "scripts" / "phase2_tasks_benchmark_and_paper" / "31_eval.py"
DEV_RUNS = bc.PROJECT_ROOT / "outputs" / "model_runs" / "_dev"

# One representative tier per family. The full 94-config matrix differs only in
# which modality kind is named, and `check_input_policy` already covers that.
TIER_PREFERENCE = {
    "signal": ["signal_resnet18_lead2_preprocessed", "signal_resnet18_lead2_raw"],
    "image": ["image_resnet50_lead2_clean", "image_resnet50_12lead_clean"],
    "text_tfidf": ["text_tfidf"],
    "text_bert": ["text_bioclinicalbert"],
    "fusion": ["multimodal_fusion_lead2"],
    # Plan A/B §5.3 ablation 6 -- the trained no-text multimodal tier. It has to
    # run on real bytes like every other tier: dropping the text encoder changes
    # the fusion input width, and a config that only *looks* right would be found
    # at campaign time on the DGX rather than here.
    "fusion_notext": ["multimodal_fusion_notext_lead2"],
}


def available_configs(task: str) -> dict[str, Path]:
    prefix = task.split("_")[0]
    return {path.stem[len(prefix) + 1:]: path
            for path in sorted(MODEL_CONFIG_DIR.glob(f"{prefix}_*.yaml"))}


def pick_configs(task: str, families: list[str]) -> list[Path]:
    configs = available_configs(task)
    picked: list[Path] = []
    for family in families:
        for tier in TIER_PREFERENCE[family]:
            if tier in configs:
                picked.append(configs[tier])
                break
    return picked


def run(command: list[str], label: str) -> tuple[bool, str]:
    started = time.time()
    result = subprocess.run([str(c) for c in command], capture_output=True, text=True)
    elapsed = time.time() - started
    ok = result.returncode == 0
    tail = (result.stderr or result.stdout).strip().splitlines()[-4:]
    print(f"  {'PASS' if ok else 'FAIL'}  {label}  ({elapsed:.1f}s)")
    if not ok:
        for line in tail:
            print(f"        {line}")
    return ok, "\n".join(tail)


# -----------------------------------------------------------------------------
# crash recovery, in-process so it is deterministic and OS-independent
# -----------------------------------------------------------------------------
# Which (task, config) the crash-recovery and determinism checks train on.
# It used to be hard-wired to a signal tier, so `--tiers text_tfidf text_bert`
# on a node staged for a TEXT campaign reported three FAILs for missing
# `signals/*.h5` -- failures that say nothing about the code under test.
# Spurious FAILs are worse than no check: they teach the reader to skim past
# FAIL lines, which is precisely the habit that lets a real one through.
RECOVERY_CHOICES = {
    "signal":     ("B1_measurement_blind", "B1_signal_resnet18_lead2_preprocessed.yaml"),
    "text_tfidf": ("A1_ecg_diagnosis",     "A1_text_tfidf.yaml"),
    "text_bert":  ("A1_ecg_diagnosis",     "A1_text_bioclinicalbert.yaml"),
    "image":      ("A1_ecg_diagnosis",     "A1_image_resnet50_lead2_clean.yaml"),
    "fusion":     ("A1_ecg_diagnosis",     "A1_multimodal_fusion_lead2.yaml"),
}
RECOVERY_TARGET: tuple[str, str] = RECOVERY_CHOICES["signal"]


def choose_recovery_target(families: list[str]) -> tuple[str, str]:
    """Run the recovery checks on a tier whose data this node actually has."""
    for family in families:
        choice = RECOVERY_CHOICES.get(family)
        if choice and (MODEL_CONFIG_DIR / choice[1]).exists():
            return choice
    return RECOVERY_CHOICES["signal"]


def build_tiny_trainer(output_dir: Path, epochs: int = 2, batch_size: int = 4,
                       steps: int = 3) -> tuple[Trainer, Any]:
    task, config_name = RECOVERY_TARGET
    spec = get_task(task)
    config_dict = load_model_config(MODEL_CONFIG_DIR / config_name)
    plan = plan_from_config(config_dict)
    set_seed(42)

    train_dataset = TaskDataset(task, "train", plan, dev=True, limit=32)
    val_dataset = TaskDataset(task, "val", plan, dev=True, limit=16)
    config = TrainConfig(task=task, arch_tier="smoke", lead_subset="lead2", seed=42,
                         output_dir=output_dir, epochs=epochs, batch_size=batch_size,
                         num_workers=0, checkpoint_minutes=1e9,
                         max_steps_per_epoch=steps, dev=True,
                         signal_input_modality=plan.signal_kind)
    model = build_model(spec, plan, pretrained=False)
    stats = train_class_stats(spec, train_dataset.frame)

    import logging

    logger = logging.getLogger("smoke")
    logger.setLevel(logging.ERROR)
    return Trainer(model, spec, config, train_dataset, val_dataset, stats, logger), spec


def test_midepoch_resume(root: Path) -> bool:
    """Interrupt after 2 of 3 batches; the resumed run must do exactly batch 3."""
    output_dir = root / "resume_midepoch"
    shutil.rmtree(output_dir, ignore_errors=True)

    trainer, _ = build_tiny_trainer(output_dir, epochs=1, steps=3)
    original_run_epoch = trainer._run_epoch

    def stop_after_two(batches, already_done, total):
        # Let two batches complete, THEN raise the flag -- that is the order a
        # SIGTERM produces: the batch in flight finishes, the loop stops after it.
        result = original_run_epoch(batches[:2], already_done, total)
        trainer.stop_requested = True
        return result

    trainer._run_epoch = stop_after_two
    result = trainer.train()
    if result["status"] != "interrupted":
        print(f"  FAIL  mid-epoch resume: expected 'interrupted', got {result['status']}")
        return False

    checkpoint = torch.load(output_dir / "checkpoint_last.pt", map_location="cpu",
                            weights_only=False)
    if checkpoint["batch_in_epoch"] != 2 or checkpoint["saved_because"] != "interrupted":
        print(f"  FAIL  mid-epoch resume: batch_in_epoch={checkpoint['batch_in_epoch']}, "
              f"saved_because={checkpoint['saved_because']}")
        return False

    # The resumed run rebuilds the same order and must skip the first two batches.
    resumed, _ = build_tiny_trainer(output_dir, epochs=1, steps=3)
    if not resumed.try_resume():
        print("  FAIL  mid-epoch resume: try_resume() found no checkpoint")
        return False
    if resumed.batch_in_epoch != 2 or resumed.global_step != checkpoint["global_step"]:
        print(f"  FAIL  mid-epoch resume: restored batch={resumed.batch_in_epoch}, "
              f"step={resumed.global_step}")
        return False

    seen: list[int] = []
    original = resumed._run_epoch

    def record(batches, already_done, total):
        seen.append(len(batches))
        return original(batches, already_done, total)

    resumed._run_epoch = record
    resumed.train()
    if seen != [1]:
        print(f"  FAIL  mid-epoch resume: resumed run did {seen} batches, expected [1]")
        return False
    print("  PASS  mid-epoch resume (stopped after 2/3 batches, resumed doing exactly 1)")
    return True


def test_epoch_boundary_resume(root: Path) -> bool:
    """A completed epoch must restore weights, optimizer, RNG and best metric."""
    output_dir = root / "resume_epoch"
    shutil.rmtree(output_dir, ignore_errors=True)

    first, _ = build_tiny_trainer(output_dir, epochs=1, steps=3)
    first.train()
    reference = {k: v.clone() for k, v in first.model.state_dict().items()}
    best_metric, global_step = first.best_metric, first.global_step

    second, _ = build_tiny_trainer(output_dir, epochs=2, steps=3)
    if not second.try_resume():
        print("  FAIL  epoch-boundary resume: no checkpoint found")
        return False
    for key, value in second.model.state_dict().items():
        if not torch.allclose(value.float(), reference[key].float()):
            print(f"  FAIL  epoch-boundary resume: weight {key} differs after restore")
            return False
    if second.epoch != 1 or second.global_step != global_step:
        print(f"  FAIL  epoch-boundary resume: epoch={second.epoch}, step={second.global_step}")
        return False
    if abs(second.best_metric - best_metric) > 1e-12:
        print(f"  FAIL  epoch-boundary resume: best {second.best_metric} != {best_metric}")
        return False
    if not second.optimizer.state_dict()["state"]:
        print("  FAIL  epoch-boundary resume: optimizer moment state is empty")
        return False
    print(f"  PASS  epoch-boundary resume (epoch {second.epoch}, step {second.global_step}, "
          f"best {second.best_metric:.6f}, optimizer state restored)")
    return True


def test_preemption_handler(root: Path) -> bool:
    """SIGTERM must set the stop flag, not write from inside the handler."""
    import signal as signal_module

    output_dir = root / "preempt"
    shutil.rmtree(output_dir, ignore_errors=True)
    trainer, _ = build_tiny_trainer(output_dir, epochs=1, steps=2)
    if trainer.stop_requested:
        print("  FAIL  preemption: stop flag set before any signal")
        return False
    handler = signal_module.getsignal(signal_module.SIGTERM)
    if not callable(handler):
        print("  FAIL  preemption: no SIGTERM handler installed")
        return False
    handler(signal_module.SIGTERM, None)
    if not (trainer.stop_requested and trainer.interrupted):
        print("  FAIL  preemption: the handler did not raise the stop flag")
        return False
    if (output_dir / "checkpoint_last.pt").exists():
        print("  FAIL  preemption: the handler wrote a checkpoint from inside itself")
        return False
    print("  PASS  preemption handler (flag raised, no write from the handler)")
    return True


def test_gates() -> bool:
    """The two failures that must be loud: forbidden input, non-val threshold."""
    from _dataset_lib.task_dataset import ModalityPlan
    from _train_lib.threshold import select_threshold

    ok = True
    try:
        # MUST be a task whose input policy forbids images -- B1 allows signals
        # only. Pointing this at the recovery target would break the gate the
        # moment that target became a task that legitimately allows images.
        TaskDataset("B1_measurement_blind", "val",
                    ModalityPlan(image_kind="image_clean_lead2"), dev=True, limit=2)
        print("  FAIL  leakage gate: B1 accepted an image input")
        ok = False
    except PermissionError:
        pass
    try:
        select_threshold([0, 1], [0.1, 0.9], split="test", task="t", arch_tier="a",
                         lead_subset="lead2", seed=42, head="h")
        print("  FAIL  threshold gate: selection on test was allowed")
        ok = False
    except ValueError:
        pass
    if ok:
        print("  PASS  gates (forbidden modality rejected, test-split threshold rejected)")
    return ok


def test_determinism(root: Path) -> bool:
    """Two runs of the same seed must produce identical weights."""
    weights = []
    for index in (0, 1):
        output_dir = root / f"determinism_{index}"
        shutil.rmtree(output_dir, ignore_errors=True)
        trainer, _ = build_tiny_trainer(output_dir, epochs=1, steps=2)
        trainer.train()
        weights.append({k: v.clone() for k, v in trainer.model.state_dict().items()})
    for key in weights[0]:
        if not torch.allclose(weights[0][key].float(), weights[1][key].float()):
            print(f"  FAIL  determinism: {key} differs between two seed-42 runs")
            return False
    print("  PASS  determinism (two seed-42 runs produce identical weights)")
    return True


# -----------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--tasks", nargs="*", default=None)
    parser.add_argument("--tiers", nargs="*", default=["signal", "image", "text_tfidf",
                                                       "text_bert", "fusion",
                                                       "fusion_notext"])
    parser.add_argument("--rows", type=int, default=48)
    parser.add_argument("--steps", type=int, default=2)
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument("--skip-recovery", action="store_true")
    args = parser.parse_args(argv)

    tasks = args.tasks or [k for k, v in TASKS.items() if not v.eval_only]

    # Bind the recovery checks to a tier this node has data for (see
    # RECOVERY_CHOICES) so a scoped smoke run does not report failures about
    # modalities it was never asked to exercise.
    global RECOVERY_TARGET
    RECOVERY_TARGET = choose_recovery_target(args.tiers)

    root = DEV_RUNS / "_smoke"
    root.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    print("=" * 78)
    print("Step 3 smoke test — dev_sample only, tiny batches, no paper numbers")
    print("=" * 78)

    if not args.skip_recovery:
        print("\n[1] crash recovery, preemption, determinism and the gates")
        for name, fn in (("mid-epoch resume", lambda: test_midepoch_resume(root)),
                         ("epoch-boundary resume", lambda: test_epoch_boundary_resume(root)),
                         ("preemption handler", lambda: test_preemption_handler(root)),
                         ("determinism", lambda: test_determinism(root)),
                         ("gates", test_gates)):
            try:
                if not fn():
                    failures.append(name)
            except Exception as exc:                          # keep going, report at the end
                print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
                failures.append(name)

    if not args.skip_train:
        print(f"\n[2] train + eval, {len(tasks)} tasks x {len(args.tiers)} tiers")
        for task in tasks:
            configs = pick_configs(task, args.tiers)
            if not configs:
                print(f"  ----  {task}: no config for tiers {args.tiers}")
                continue
            print(f"\n  {task}")
            for config_path in configs:
                ok, _ = run([PYTHON, TRAIN_SCRIPT, "--model-config", config_path,
                             "--seed", 42, "--dev", "--epochs", 1,
                             "--batch-size", 4, "--max-steps-per-epoch", args.steps,
                             "--limit-rows", args.rows, "--num-workers", 0,
                             "--no-pretrained"], f"train {config_path.stem}")
                if not ok:
                    failures.append(f"train {config_path.stem}")
                    continue
                arch_tier = load_model_config(config_path)["arch_tier"]
                ok, _ = run([PYTHON, EVAL_SCRIPT, "--task", task, "--arch-tier", arch_tier,
                             "--dev", "--bootstrap-n", 50], f"eval  {config_path.stem}")
                if not ok:
                    failures.append(f"eval {config_path.stem}")

    print("\n" + "=" * 78)
    if failures:
        print(f"SMOKE TEST FAILED — {len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("SMOKE TEST PASSED — every checked path runs on dev_sample")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
