"""Does every campaign stage everything its runs actually read?

    ./ecg_env/Scripts/python.exe scripts/dgx_portability/check_campaign_data.py

Exit 0 when every campaign's dataset list covers every (modality kind, split)
its configs will ask `read_modality()` for, over the cohort those configs
actually train on. Exit 1, loudly, when one does not.

**This check exists because four campaigns were wrong at once and nothing
noticed until a job died on the DGX.** All four failed the same way -- the
dataset list was derived from what a config *names*, and that is not what a run
*reads*:

* campaigns 2, 3, 8, 11, 13 and 14 staged no scan-like container, though A5 and
  B4 choose the image rendering PER ROW (`image_type_column`,
  `task_dataset.py:524-528`) and their config only fixes the layout. Jobs
  24639/24640 died on `scanlike_12lead_shard_017.tar`;
* campaign 10 staged no CLEAN container, for the mirror-image reason;
* campaign 11 trains A5 and B4, which are not L3 tasks, against the L3 subsets,
  so every study outside the L3 cohort would have missed;
* campaign 7 read a 35 GB subset it did not need, which put it over the ceiling.

A campaign's dataset list is hand-written in `campaigns.sh` and always will be --
it encodes a storage decision (whole container, subset, or pieces) that no
amount of introspection can make for us. What CAN be checked automatically is
that whatever was chosen actually covers the reads. That is this file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "phase2_tasks_benchmark_and_paper"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

from campaign_runs import L3_TASKS, campaign_of                        # noqa: E402
from upload_data import campaign_datasets, n_campaigns                 # noqa: E402
from _dataset_lib import build_common as bc                            # noqa: E402
from _dataset_lib.task_dataset import plan_from_config                 # noqa: E402
from _dataset_lib.task_spec import get_task                            # noqa: E402
from _model_lib.model_configs import build_matrix                      # noqa: E402

# Which (kind, splits, cohort) each dataset name provides. `cohort` is "all" or
# "l3": an "l3" dataset cannot serve a campaign that trains a non-L3 task.
# Pieces cover TRAIN only, by construction -- make_chunks.py cuts the train
# split and nothing else.
TRAIN, VAL, TEST = "train", "val", "test"
ALL = (TRAIN, VAL, TEST)

PROVIDES: dict[str, tuple[str, tuple[str, ...], str]] = {
    "signals_lead2":               ("preprocessed_lead2", ALL, "all"),
    "signals_lead2_preprocessed":  ("preprocessed_lead2", ALL, "all"),
    "signals_lead2_raw":           ("raw_lead2", ALL, "all"),
    "images_clean_12lead":         ("image_clean_12lead", ALL, "all"),
    "images_clean_lead2":          ("image_clean_lead2", ALL, "all"),
    "signals_12lead_L3":           ("preprocessed_12lead", ALL, "l3"),
    "images_clean_12lead_L3":      ("image_clean_12lead", ALL, "l3"),
    "signals_12lead_valtest":      ("preprocessed_12lead", (VAL, TEST), "all"),
    "images_clean_12lead_valtest": ("image_clean_12lead", (VAL, TEST), "all"),
    "images_clean_lead2_valtest":  ("image_clean_lead2", (VAL, TEST), "all"),
    "signals_raw_valtest":         ("raw_12lead", (VAL, TEST), "all"),
    "images_scanlike_12lead_valtest": ("image_scanlike_12lead", (VAL, TEST), "all"),
    "images_scanlike_lead2_valtest":  ("image_scanlike_lead2", (VAL, TEST), "all"),
    "signals_12lead_pieces":       ("preprocessed_12lead", (TRAIN,), "all"),
    "signals_raw_pieces":          ("raw_12lead", (TRAIN,), "all"),
    "images_clean_12lead_pieces":  ("image_clean_12lead", (TRAIN,), "all"),
    "images_clean_lead2_pieces":   ("image_clean_lead2", (TRAIN,), "all"),
    "images_scanlike_12lead_pieces": ("image_scanlike_12lead", (TRAIN,), "all"),
    "images_scanlike_lead2_pieces":  ("image_scanlike_lead2", (TRAIN,), "all"),
}
# `images_scanlike_test` carries BOTH layouts in one tar, so it provides two.
MULTI_PROVIDES: dict[str, tuple[tuple[str, tuple[str, ...], str], ...]] = {
    "images_scanlike_test": (("image_scanlike_12lead", (TEST,), "all"),
                             ("image_scanlike_lead2", (TEST,), "all")),
}
# Datasets that carry no modality bytes.
NO_MODALITY = {"code", "configs", "tasks", "index", "text", "fiducials",
               "signals_corrupted", "results"}

_TYPES: dict[str, list[str] | None] = {}


def image_types(task: str) -> list[str] | None:
    """The renderings this task's rows name, straight off the task table."""
    if task not in _TYPES:
        column = get_task(task).image_type_column
        if not column:
            _TYPES[task] = None
        else:
            frame = pd.read_parquet(
                bc.DATA_PROCESSED / "tasks" / task / "train.parquet", columns=[column])
            _TYPES[task] = sorted(frame[column].dropna().unique().tolist())
    return _TYPES[task]


def reads_for(campaign: int) -> tuple[set[str], set[str], bool]:
    """(modality kinds, tasks, needs_full_cohort) for one campaign's configs."""
    kinds: set[str] = set()
    tasks: set[str] = set()
    for config in build_matrix():
        if campaign_of(config) != campaign:
            continue
        tasks.add(config["task"])
        plan = plan_from_config(config)
        if getattr(plan, "signal_kind", None):
            kinds.add(plan.signal_kind)
        image_kind = getattr(plan, "image_kind", None)
        if image_kind:
            types = image_types(config["task"])
            if types:
                layout = "12lead" if image_kind.endswith("12lead") else "lead2"
                kinds |= {f"image_{t}_{layout}" for t in types}
            else:
                kinds.add(image_kind)
    return kinds, tasks, any(t not in L3_TASKS for t in tasks)


def check(campaign: int, verbose: bool) -> list[str]:
    kinds, tasks, needs_full = reads_for(campaign)
    datasets = campaign_datasets(campaign)

    # kind -> the splits this campaign's datasets cover, and whether any
    # provider is L3-only while the campaign needs the full cohort.
    covered: dict[str, set[str]] = {k: set() for k in kinds}
    # Did this campaign list a provider for the kind that we had to REJECT for
    # being L3-only? That is a different diagnosis from listing none at all.
    l3_rejected: dict[str, bool] = {k: False for k in kinds}
    for dataset in datasets:
        if dataset in NO_MODALITY:
            continue
        entries = MULTI_PROVIDES.get(dataset)
        if entries is None:
            entry = PROVIDES.get(dataset)
            if entry is None:
                return [f"dataset {dataset!r} is not in this file's PROVIDES table -- "
                        f"add it, or the check silently stops covering it"]
            entries = (entry,)
        for kind, splits, cohort in entries:
            if kind not in covered:
                continue
            if cohort == "l3" and needs_full:
                l3_rejected[kind] = True       # cannot serve a full-cohort run
                continue
            covered[kind] |= set(splits)

    problems = []
    for kind in sorted(kinds):
        want = {TRAIN, VAL, TEST}
        gaps = want - covered[kind]
        if gaps:
            why = ""
            if l3_rejected[kind]:
                non_l3 = sorted(t for t in tasks if t not in L3_TASKS)
                why = (f" -- it lists an L3-ONLY container for this kind, but the "
                       f"campaign trains {non_l3[0]}, which is not an L3 task, so "
                       f"every study outside the L3 cohort would miss")
            problems.append(
                f"reads {kind} but stages nothing for split(s) {sorted(gaps)}{why}")
    if verbose and not problems:
        print(f"  reads {sorted(kinds) or ['(text only)']}"
              f"  cohort={'full' if needs_full else 'L3'}")
    return problems


def _self_check() -> int:
    """Replay the historical failures and confirm each one is caught.

    A check that cannot fail is worth nothing, so this feeds the check the
    dataset lists those campaigns actually had on 2026-09-29 and asserts it
    rejects every one of them.
    """
    broken = {
        # the scan-like gap that killed jobs 24639/24640
        2: "code configs tasks index images_clean_12lead",
        # campaign 10 staged no clean container for its A5/B4 clean rows
        10: "code configs tasks index images_scanlike_test signals_corrupted",
        # campaign 11 trains A5/B4, which are not L3 tasks, on the L3 subsets
        11: ("code configs tasks index text results signals_12lead_L3 "
             "images_clean_12lead_L3"),
    }
    module = sys.modules[__name__]
    real = module.campaign_datasets
    failures = 0
    try:
        for campaign, listing in broken.items():
            module.campaign_datasets = lambda _c, _l=listing: _l.split()
            problems = check(campaign, verbose=False)
            if not problems:
                print(f"SELF-CHECK FAIL: campaign {campaign}'s old dataset list was "
                      f"accepted -- the check would not have caught it")
                failures += 1
            else:
                print(f"  caught campaign {campaign}: {problems[0]}")
    finally:
        module.campaign_datasets = real
    if failures:
        return 1
    print("check_campaign_data self-check PASS "
          "(every historical failure is rejected)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--selfcheck", action="store_true",
                        help="prove the check rejects the dataset lists that "
                             "actually failed on the DGX")
    args = parser.parse_args()

    if args.selfcheck:
        return _self_check()

    failures = 0
    for campaign in range(1, n_campaigns() + 1):
        problems = check(campaign, args.verbose)
        status = "FAIL" if problems else "ok  "
        print(f"{status} campaign {campaign:>2}")
        for line in problems:
            print(f"       {line}")
        failures += bool(problems)
    print(f"\n{n_campaigns() - failures}/{n_campaigns()} campaigns stage what they read")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
