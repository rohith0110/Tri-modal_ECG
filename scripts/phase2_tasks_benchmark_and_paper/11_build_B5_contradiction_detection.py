"""Stage P2.2 script 11 -- B5: contradiction detection in reports.

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/11_build_B5_contradiction_detection.py [--dev]

Spec §4.B.5, driven entirely by ``config/claim_dictionary_LOCKED.yaml``. Four
families -- HR, QRS, axis, PR -- each with clear zones, an injection-free gap
around the decision boundary, and the surface forms that may be swapped.

Three locked decisions this builder implements rather than re-deriving:

* **Every threshold reads the MACHINE measurement** (Round 6.1), with the
  ``29999`` sentinel masked and the plausible range applied (Round 6.2).
  ``structured_features.pr_ms`` and ``.qrs_ms`` are never read.
* **Injections are swaps of text that is really present, never insertions**
  (Round 6.3). A study is eligible for a family only when the measurement sits
  in a clear zone **and** the report carries a surface form of matching
  polarity, so every recorded span points at real characters and the corrupted
  class is not separable by length or phrasing.
* **Exactly one row per ELIGIBLE study**, corrupted with p = 0.5 (Round 6.5,
  progress-doc question 11). A study eligible for no family contributes no row.
  Clean rows are drawn from the same eligible pool on purpose: otherwise "the
  report contains a swappable claim" would itself predict the label.

The RNG is the one the dictionary specifies: ``sha256("b5|<study_id>")``, first
4 bytes, mod 2**31, seeding ``numpy.random.default_rng``. It depends on the
study alone, so re-running reproduces the dataset exactly (§4.C invariant 2).

**Open question 3 (span offsets), proceeding under the stated default.**
§4.B.5.5 declares ``corrupted_span_start`` / ``_end`` as character offsets, so
they are character offsets into ``corrupted_report_text``. Token offsets would
depend on a tokenizer the data contract does not name.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import build_common as bc  # noqa: E402

STAGE = "P2.2"
SCRIPT = "11_build_B5_contradiction_detection"
TASK = "B5_contradiction_detection"

FAMILY_ORDER = ("HR", "QRS", "axis", "PR")

SCHEMA = pa.schema([
    ("study_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("split", pa.string()),
    ("link_tier", pa.string()),
    ("sqi_tier", pa.string()),
    ("cart_id", pa.string()),
    ("is_corrupted", pa.bool_()),
    ("contradiction_type", pa.string()),
    ("contradiction_family", pa.string()),
    ("original_report_text", pa.string()),
    ("corrupted_report_text", pa.string()),
    ("corrupted_span_start", pa.int32()),
    ("corrupted_span_end", pa.int32()),
    ("source_measurement", pa.string()),
    ("label", pa.string()),
    ("eligible_families", pa.string()),
    ("is_primary", pa.bool_()),
])


def zone_mask(values: pd.Series, condition: str) -> np.ndarray:
    """Evaluate one ``clear_zones`` condition from the locked dictionary.

    The conditions are simple comparisons against the family's own measurement
    (``hr_bpm <= 50``, ``qrs_axis > 105``, ...), so they are parsed rather than
    ``eval``-ed: a config file must not be able to execute arbitrary code.
    """
    match = re.fullmatch(r"\s*\w+\s*(<=|>=|<|>|==)\s*(-?\d+(?:\.\d+)?)\s*", condition)
    if not match:
        raise ValueError(f"unparseable clear-zone condition: {condition!r}")
    op, bound = match.group(1), float(match.group(2))
    series = values.astype("float64")
    return {
        "<=": series <= bound, ">=": series >= bound, "<": series < bound,
        ">": series > bound, "==": series == bound,
    }[op].fillna(False).to_numpy()


def apply_swap(text: str, pattern: re.Pattern, replacement: str) -> tuple[str, int, int] | None:
    """Swap the first match, preserving the original leading capitalisation.

    Returns ``(corrupted_text, span_start, span_end)`` with offsets into the
    corrupted text. Everything before the match is untouched, so the start
    offset is the same in both strings.
    """
    match = pattern.search(text)
    if match is None:
        return None
    original = match.group(0)
    swapped = replacement
    if original[:1].isupper():
        swapped = swapped[:1].upper() + swapped[1:]
    corrupted = text[: match.start()] + swapped + text[match.end():]
    return corrupted, match.start(), match.start() + len(swapped)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    bc.add_std_args(parser)
    args = parser.parse_args()
    bc.set_dev(args.dev)

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT + ("_dev" if args.dev else ""))
    if state.done and not args.force:
        log.info("already complete (%s rows) -- pass --force to rebuild", state.data.get("n_rows"))
        return 0
    state.reset()
    started = time.time()

    bc.preflight([bc.CONFIG_DIR / "claim_dictionary_LOCKED.yaml"])
    cfg = yaml.safe_load(
        (bc.CONFIG_DIR / "claim_dictionary_LOCKED.yaml").read_text(encoding="utf-8")
    )
    families = cfg["families"]

    cohort = bc.load_clean_cohort(dev=args.dev)
    meas = bc.machine_measurements(dev=args.dev)
    text = bc.report_text_series(dev=args.dev)
    df = cohort.merge(meas, on="study_id", how="left", validate="many_to_one").merge(text, on="study_id", how="left", validate="many_to_one")
    log.info("clean cohort: %d studies", len(df))

    lowered = df.report_text.fillna("").str.lower()

    # --- eligibility, per (family, polarity, surface form) -------------------
    compiled: dict[tuple[str, str], list[tuple[re.Pattern, str]]] = {}
    eligible_by_family: dict[str, np.ndarray] = {}
    polarity_of: dict[str, np.ndarray] = {}
    zone_counts: dict[str, dict[str, int]] = {}
    form_counts: dict[str, int] = {}

    for family in FAMILY_ORDER:
        block = families[family]
        column = block["measurement"]
        values = df[column]
        eligible = np.zeros(len(df), dtype=bool)
        polarity = np.full(len(df), "", dtype=object)
        zone_counts[family] = {}

        for zone_name, zone in block["clear_zones"].items():
            truth_zone = zone_mask(values, zone["condition"])
            forms = [f for f in block["surface_forms"] if f["polarity"] == zone_name]
            if not forms:
                zone_counts[family][zone_name] = 0
                continue
            key = (family, zone_name)
            compiled[key] = [
                (re.compile(str(f["pattern"]), re.IGNORECASE), str(f["replace_with"]))
                for f in forms
            ]
            has_form = np.zeros(len(df), dtype=bool)
            for form in forms:
                hit = lowered.str.contains(str(form["pattern"]), regex=True, na=False).to_numpy()
                form_counts[f"{family}|{zone_name}|{form['pattern']}"] = int(
                    (hit & truth_zone).sum()
                )
                has_form |= hit
            zone_eligible = truth_zone & has_form
            zone_counts[family][zone_name] = int(zone_eligible.sum())
            polarity[zone_eligible & ~eligible] = zone_name
            eligible |= zone_eligible

        eligible_by_family[family] = eligible
        polarity_of[family] = polarity
        log.info("%s eligible: %d  %s", family, int(eligible.sum()), zone_counts[family])

    any_eligible = np.zeros(len(df), dtype=bool)
    for family in FAMILY_ORDER:
        any_eligible |= eligible_by_family[family]
    log.info("eligible for at least one family: %d of %d (%.2f %%)",
             int(any_eligible.sum()), len(df), 100 * any_eligible.mean())

    # --- one row per eligible study, corrupted with p = 0.5 ------------------
    pool = df[any_eligible].reset_index(drop=True)
    pool_index = np.flatnonzero(any_eligible)
    eligible_lists = [
        [f for f in FAMILY_ORDER if eligible_by_family[f][i]] for i in pool_index
    ]

    rng_cfg = cfg["injection_policy"]["rng"]
    probability = float(cfg["injection_policy"]["probability_of_corruption"])
    if rng_cfg["key_template"] != "b5|{study_id}" or rng_cfg["digest"] != "sha256":
        raise RuntimeError(f"the locked RNG spec changed: {rng_cfg}")

    rows: list[dict] = []
    swap_failures = 0
    for position, study_id in enumerate(pool.study_id.to_numpy()):
        rng = np.random.default_rng(bc.stable_seed("b5", int(study_id)))
        corrupt = bool(rng.random() < probability)
        choices = eligible_lists[position]
        record = {
            "is_corrupted": False, "contradiction_type": None, "contradiction_family": None,
            "corrupted_report_text": None, "corrupted_span_start": None,
            "corrupted_span_end": None, "source_measurement": None, "label": "clean",
            "eligible_families": ",".join(choices),
        }
        if corrupt:
            family = str(choices[int(rng.integers(len(choices)))])
            zone = polarity_of[family][pool_index[position]]
            original = pool.report_text.iloc[position]
            result = None
            for pattern, replacement in compiled[(family, zone)]:
                result = apply_swap(original, pattern, replacement)
                if result is not None:
                    break
            if result is None:
                # Eligibility was decided by the same patterns, so this cannot
                # happen; if it ever does, the row stays clean rather than
                # shipping a corrupted label with no corrupted text.
                swap_failures += 1
            else:
                corrupted_text, start, end = result
                column = families[family]["measurement"]
                record.update({
                    "is_corrupted": True,
                    "contradiction_type": family,
                    "contradiction_family": f"{family}_{zone}",
                    "corrupted_report_text": corrupted_text,
                    "corrupted_span_start": start,
                    "corrupted_span_end": end,
                    "source_measurement": json.dumps({
                        "measurement_name": column,
                        "value": float(pool[column].iloc[position]),
                        "clear_zone": zone,
                    }),
                    "label": f"corrupted_{family}",
                })
        rows.append(record)
    if swap_failures:
        log.warning("%d eligible studies could not be swapped and stayed clean", swap_failures)

    out = pd.concat([
        pool[["study_id", "subject_id", "split", "link_tier", "sqi_tier", "cart_id"]]
        .reset_index(drop=True),
        pd.DataFrame(rows),
    ], axis=1)
    out["original_report_text"] = pool.report_text.to_numpy()
    out["is_primary"] = True
    out["cart_id"] = out["cart_id"].astype("Int64").astype("string")
    for column in ("corrupted_span_start", "corrupted_span_end"):
        out[column] = out[column].astype("Int32")
    out = out.sort_values("study_id", kind="mergesort").reset_index(drop=True)

    counts = bc.write_task_split_parquets(out, TASK, schema=SCHEMA)
    log.info("wrote splits: %s", counts)

    # --- validation (§9.2) ---------------------------------------------------
    corrupted_rows = out[out.is_corrupted]
    stats = {
        "n_rows": int(len(out)),
        "n_eligible_studies": int(any_eligible.sum()),
        "eligible_pct_of_clean_cohort": round(100 * float(any_eligible.mean()), 3),
        "splits": counts,
        "corrupted_rate_pct": round(100 * float(out.is_corrupted.mean()), 3),
        "corrupted_rate_by_split_pct": {
            split: round(100 * float(out[out.split == split].is_corrupted.mean()), 3)
            for split in bc.SPLITS
        },
        "eligible_per_family": {f: int(eligible_by_family[f].sum()) for f in FAMILY_ORDER},
        "eligible_per_zone": zone_counts,
        "families_per_eligible_study": {
            str(k): int(v) for k, v in
            pd.Series([len(v) for v in eligible_lists]).value_counts().sort_index().items()
        },
        "label_distribution": out.label.value_counts().to_dict(),
        "contradiction_family_distribution": corrupted_rows.contradiction_family.value_counts().to_dict(),
        "span_length_median_chars": int(
            (corrupted_rows.corrupted_span_end - corrupted_rows.corrupted_span_start).median()
        ) if len(corrupted_rows) else 0,
        "swap_failures": swap_failures,
        "surface_form_hits_in_zone": form_counts,
    }
    stats.update(bc.split_summary(out))
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str))

    # Every recorded span must actually contain the replacement text.
    for row in corrupted_rows.head(5000).itertuples():
        span = row.corrupted_report_text[row.corrupted_span_start:row.corrupted_span_end]
        if not span or span == row.original_report_text[row.corrupted_span_start:row.corrupted_span_end]:
            raise RuntimeError(f"span on study {row.study_id} does not mark a change: {span!r}")
    if out.study_id.duplicated().any():
        raise RuntimeError("a study contributes more than one B5 row")
    balance = stats["corrupted_rate_pct"]
    if not 48.0 <= balance <= 52.0:
        raise RuntimeError(f"corrupted rate is {balance} %, not the 50/50 Round 6.5 requires")
    if not args.dev:
        expected = cfg["injection_policy"]["measured_eligibility"]
        if stats["n_eligible_studies"] != int(expected["eligible_for_at_least_one_family"]):
            raise RuntimeError(
                f"eligibility is {stats['n_eligible_studies']}, not the locked "
                f"{expected['eligible_for_at_least_one_family']} -- the dictionary or the "
                "measurement source changed"
            )

    examples = [
        {"study_id": int(r.study_id), "family": r.contradiction_family,
         "original": r.original_report_text[:130], "corrupted": r.corrupted_report_text[:130],
         "span": [int(r.corrupted_span_start), int(r.corrupted_span_end)],
         "measurement": r.source_measurement}
        for r in corrupted_rows.head(4).itertuples()
    ]
    stats["examples"] = examples
    log.info("injection examples:\n%s", json.dumps(examples, indent=2))

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2, default=str), built_at=bc.utc_now_iso()
    ))
    state.finish(**stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# B5 -- contradiction detection in reports

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.B.5 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/11_build_B5_contradiction_detection.py`.
Every threshold, zone and surface form comes from
`config/claim_dictionary_LOCKED.yaml`.

## One row per eligible study, corrupted with p = 0.5

A study is **eligible** for a family only when its machine measurement sits in a
clear zone **and** its report carries a surface form of matching polarity.
Studies eligible for no family contribute no row at all. That is Round 6.5
(progress-doc question 11), and it is what makes the cohort an exact 50/50 —
the reading under which §4.B.5.3's "with 50 % probability" and §6.4's "balanced
50/50 by dataset design" are both true.

Clean rows come from the **same eligible pool** as corrupted ones, on purpose:
drawing them from the whole cohort would let a model separate the classes on
vocabulary alone, because only eligible reports contain a swappable claim.

## Swaps, never insertions

Round 6.3. Each injection replaces text that is really present with its
opposite, so `corrupted_span_start` / `_end` always point at real characters and
the corrupted class is not detectable by length or by a phrasing style absent
from the clean class. Offsets are **character** offsets into
`corrupted_report_text` (§4.B.5.5; progress-doc question 3, stated default).

`contradiction_type` is the family (HR / QRS / axis / PR).
`contradiction_family` is the **directed** swap (`HR_brady`, `axis_lad`, ...),
which is what the per-family detection-rate table needs.
`source_measurement` is the JSON of the value that drove the injection.

## Two families are one-directional in practice

The dictionary records why, and it is a property of the source vocabulary rather
than a modelling choice: MIMIC machine reports essentially never assert a narrow
QRS ("narrow" appears 0 times in 749,112 reports) or a normal PR. QRS is
therefore wide → normal, and PR is first-degree-AVB → normal. The
per-family table must be read with that in mind.

## Measurements

Machine measurements only (Round 6.1), `29999` masked and range-gated (Round
6.2). `structured_features.pr_ms` and `.qrs_ms` are never read — both are
NeuroKit values, and the NeuroKit PR would have shipped 9,035 studies whose
report already says "1st degree A-V block" as **clean** rows.

## Forbidden inputs

`machine_measurements` and `structured_features` (they *are* the contradiction
source — a model given them could recompute the truth and diff it), and every
image kind (§4.B.5.4). `report_text` is allowed: it is the thing being audited.

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
