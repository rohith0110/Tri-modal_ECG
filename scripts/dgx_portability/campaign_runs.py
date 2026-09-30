"""Resolve a campaign number to its `<task> <arch_tier> <seed>` run list.

    ./ecg_env/Scripts/python.exe scripts/dgx_portability/campaign_runs.py 4
    ./ecg_env/Scripts/python.exe scripts/dgx_portability/campaign_runs.py --table

One line per run as `<task> <arch_tier> <seed> <config_filename>`, ordered by
the §8.3 training-queue priority, so a campaign's sbatch file can simply read
stdin. The config filename is emitted because `30_train.py` is driven by
`--model-config <path>`, not by a task/tier pair -- resolving it here keeps the
shell free of any knowledge of the naming scheme. The run list is DERIVED from the 94 generated
model configs rather than typed out again -- a config added or removed changes
the campaigns automatically, and a typo cannot put a run in two campaigns or
none.

The campaign a config belongs to is decided by the data it reads, because that
is exactly what a campaign is (§8.2: "one group of runs that all read the same
data"). Only the modality and cohort matter, never the task.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "phase2_tasks_benchmark_and_paper"
sys.path.insert(0, str(SCRIPTS))

from _model_lib.model_configs import build_matrix, config_filename     # noqa: E402

# §8.3 locks both the task order and, within a task, the tier order.
TASK_ORDER = ["A2_measurement_blind", "A1_ecg_diagnosis", "A4_event_localization",
              "A3_lab_abnormality", "A6_risk_stratification",
              "A5_cross_modal_verification",
              "B1_measurement_blind", "B2_noise_robustness", "B3_temporal_grounding",
              "B4_cross_modal_verification", "B5_contradiction_detection",
              "B6_difficulty_stratified"]
TIER_RANK = ["algorithmic", "signal", "image", "text", "embedding", "multimodal"]
SEEDS = [42, 123, 456]

# 1-11 are the original campaigns; 12-14 are the Lead-II halves of 7, 8 and 11,
# split out at open question 14, and 15 is the Lead-II half of 10, split out at
# question 17 -- all so every campaign fits the ceiling.
N_CAMPAIGNS = 15

# The four L3 tasks use the smaller patient group and fit outright (§8.2 note,
# and the execution plan's remark on campaigns 5 and 7).
L3_TASKS = {"A1_ecg_diagnosis", "A3_lab_abnormality", "A4_event_localization",
            "A6_risk_stratification"}
FUSION_FULL_TASKS = {"A5_cross_modal_verification", "B4_cross_modal_verification",
                     "B5_contradiction_detection", "B6_difficulty_stratified"}


def campaign_of(config: dict) -> int | None:
    """Which campaign reads this config's data. None = not scheduled on the DGX."""
    tier, task = config["arch_tier"], config["task"]

    if tier.startswith("text_"):
        return 1
    if tier.startswith("image_"):
        if "scanlike" in tier:
            # SPLIT BY LEAD SUBSET 2026-09-30 (open question 17), for the same
            # reason 7/8/11 vs 12/13/14 are: this tier TRAINS (§5.3 turns
            # augmentation on "only for scan-like training", and these 30 runs
            # are part of the 312 the spec counts), so it needs scan-like
            # train+val -- 50.08 GB for 12-lead and 31.24 for Lead-II. One
            # campaign holding both is the 69 GB problem question 14 solved.
            return 10 if "12lead" in tier else 15
        return 2 if "12lead" in tier else 3
    if tier.startswith("embedding_cosine"):
        # Split by lead subset for the same reason 7 and 8 are (below).
        return 11 if "12lead" in tier else 14
    if tier.startswith("signal_"):
        if "lead2" in tier:
            return 4                                    # 4.7 GB covers every ECG
        if "raw" in tier:
            return 9                                    # raw-vs-filtered sweep
        return 5 if task in L3_TASKS else 6             # 12-lead preprocessed
    if tier.startswith("multimodal_fusion"):
        # SPLIT BY LEAD SUBSET, 2026-08-29 (open question 14). A campaign is
        # defined by the data it reads, and a fusion tier reads a whole lead
        # set: the 12-lead halves read signals_12lead_* + images_clean_12lead_*,
        # the Lead-II halves read signals_lead2 + images_clean_lead2. Keeping
        # both in one campaign meant 69 GB resident against a 45 GB ceiling, so
        # stage_data.sh refused to start it. Splitting changes no config, drops
        # no run and moves no seed -- the same 312 runs, partitioned differently.
        full = task in FUSION_FULL_TASKS
        if "12lead" in tier:
            return 8 if full else 7
        return 13 if full else 12
    return None


def sort_key(config: dict) -> tuple:
    task = config["task"]
    tier = config["arch_tier"]
    tier_rank = next((i for i, prefix in enumerate(TIER_RANK)
                      if tier.startswith(prefix)), len(TIER_RANK))
    task_rank = TASK_ORDER.index(task) if task in TASK_ORDER else len(TASK_ORDER)
    return (task_rank, tier_rank, tier)


def runs_for(campaign: int) -> list[tuple[str, str, int, str]]:
    configs = [c for c in build_matrix() if campaign_of(c) == campaign]
    out: list[tuple[str, str, int, str]] = []
    for config in sorted(configs, key=sort_key):
        for seed in SEEDS:
            out.append((config["task"], config["arch_tier"], seed,
                        config_filename(config)))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("campaign", nargs="?", type=int)
    parser.add_argument("--table", action="store_true",
                        help="summarise every campaign instead of listing one")
    # Sharding a campaign across several GPUs. A shard must own WHOLE tasks:
    # 31_eval.py aggregates across the three seeds of a (task, tier), so
    # splitting a task between jobs would leave neither able to evaluate it.
    parser.add_argument("--tasks", nargs="*", default=None, metavar="TASK",
                        help="only runs for these tasks (whole tasks only, so "
                             "all three seeds stay in one shard)")
    args = parser.parse_args()

    if args.table:
        matrix = build_matrix()
        unscheduled = [c for c in matrix if campaign_of(c) is None]
        print(f"{'campaign':>8}  {'configs':>7}  {'runs':>5}  tiers")
        total = 0
        for campaign in range(1, N_CAMPAIGNS + 1):
            configs = [c for c in matrix if campaign_of(c) == campaign]
            tiers = sorted({c["arch_tier"] for c in configs})
            runs = len(configs) * len(SEEDS)
            total += runs
            print(f"{campaign:>8}  {len(configs):>7}  {runs:>5}  {', '.join(tiers) or '-'}")
        print(f"{'total':>8}  {len(matrix) - len(unscheduled):>7}  {total:>5}")
        # Every emitted config must exist on disk, or a campaign would die at
        # submit time with a path error instead of failing loudly here.
        config_dir = Path(__file__).resolve().parents[2] / "config" / "model_configs"
        missing = sorted({config_filename(c) for c in matrix
                          if not (config_dir / config_filename(c)).exists()})
        print(f"\nconfig files: {len(matrix) - len(missing)}/{len(matrix)} present")
        for name in missing:
            print(f"  MISSING {name}")
        if unscheduled:
            print(f"\nUNSCHEDULED ({len(unscheduled)}) -- these would never run:")
            for config in unscheduled:
                print(f"  {config['task']:32s} {config['arch_tier']}")
        return 1 if (unscheduled or missing) else 0

    if args.campaign is None:
        parser.error("give a campaign number, or --table")
    runs = runs_for(args.campaign)
    if args.tasks:
        known = {task for task, _tier, _seed, _config in runs}
        unknown = sorted(set(args.tasks) - known)
        if unknown:
            parser.error(f"campaign {args.campaign} has no runs for: "
                         f"{', '.join(unknown)}. It has: {', '.join(sorted(known))}")
        runs = [r for r in runs if r[0] in set(args.tasks)]
    for task, tier, seed, config in runs:
        print(f"{task} {tier} {seed} {config}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
