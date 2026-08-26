"""Stage P2.1 script 05 -- A5: cross-modal verification + masked attribute prediction.

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/05_build_A5_cross_modal_verification.py [--dev]

Spec §4.A.5. Two heads on one tri-encoder:

1. **Verification** -- does this (signal, image, text) triple belong to one
   study? Rows come from ``_dataset_lib/verification_task.py``, shared with B4.
   Written to ``{train,val,test}.parquet``.
2. **Masked attribute** -- given signal + image, predict the binned HR / QRS /
   QTc that an attribute-masked report no longer states. Written to
   ``masked_attribute_{train,val,test}.parquet`` (§4.A.5.5).

------------------------------------------------------------------------------
DOCUMENTED DEVIATION -- the masked-attribute head masks CLAIMS, not NUMERALS
------------------------------------------------------------------------------
§4.A.5.3 says to build the masked text by replacing "numeric mentions of HR,
QRS, QT, QTc, axis, and intervals" with ``[MASK]``. **MIMIC-IV-ECG machine
reports contain no numeric measurements at all.** Measured over the 749,112
clean reports:

* 12.5 % contain any digit whatsoever;
* after removing lead names (``V1``-``V6``), ordinals (``1st degree``) and
  ratios (``2:1``), **0.51 %** contain a digit -- and every one of those is the
  boilerplate "Age not entered, assumed to be 50 years old for purpose of ECG
  interpretation". That is an age, not an ECG measurement.

Implemented literally, ``report_text_masked`` would be byte-identical to
``report_text`` for 99.5 % of studies, ``masked_positions`` would be empty, and
the "masked" head would be the unmasked head under another name -- while the
report still says "Sinus bradycardia" in plain words, making the HR head a
lookup rather than a prediction.

What these reports state instead is the **qualitative claim**: "Sinus
bradycardia", "Leftward axis", "Left bundle branch block", "Prolonged QT".
44.3 % of reports carry at least one such claim across the four attribute
families. Masking those is what §4.A.5.3 is actually asking for in this
vocabulary, and it is the same finding, in the same direction, as Round 6.3 --
which restricted B5 to swapping surface forms that are really present because
the numerics the spec assumed are not there either. The HR / QRS / axis surface
forms are reused verbatim from ``config/claim_dictionary_LOCKED.yaml`` so B5 and
A5 cannot drift apart; QT/QTc forms are added here because B5 has no QT family.

Numerals are masked too, on the same pass, so the rule is a superset of the
literal one and the boilerplate age cannot be used as a shortcut.

**Disclose in the supplementary.**

------------------------------------------------------------------------------
Open question 2 (anchor pool) dissolves rather than needing a decision. It asks
whether the anchor pool is random or stratified over the 5 negative types.
§4.A.5.2 makes the cohort *all* clean-cohort ECGs and §4.A.5.3 gives *every*
anchor all five negative types, so no anchor is ever sampled and there is
nothing to stratify. What is drawn is each negative's donor, and that is
deterministic per (anchor, negative type).
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
from _dataset_lib import measurement_task as mt  # noqa: E402
from _dataset_lib import verification_task as vt  # noqa: E402

STAGE = "P2.1"
SCRIPT = "05_build_A5_cross_modal_verification"
TASK = "A5_cross_modal_verification"

MASK_TOKEN = "[MASK]"

MASKED_SCHEMA = pa.schema([
    ("study_id", pa.int64()),
    ("subject_id", pa.int64()),
    ("split", pa.string()),
    ("report_text_masked", pa.string()),
    ("hr_label", pa.string()),
    ("qrs_label", pa.string()),
    ("qtc_label", pa.string()),
    ("masked_positions", pa.list_(pa.int32())),
    ("n_masked_spans", pa.int32()),
    ("masked_families", pa.string()),
])

# QT / QTc forms. B5 has no QT family, so these are defined here; the HR, QRS
# and axis forms come from claim_dictionary_LOCKED.yaml instead of being
# retyped, so the two tasks cannot drift apart.
QT_FORMS = [
    r"prolonged q-?t(?:c)?(?: interval)?",
    r"long q-?t(?:c)?(?: syndrome| interval)?",
    r"short q-?t(?:c)?(?: interval)?",
    r"q-?t(?:c)? (?:interval )?(?:is )?prolong\w*",
    r"borderline prolonged q-?t(?:c)?",
    r"q-?t(?:c)? interval",
]
# Any numeral that is not a lead name, an ordinal or a ratio -- the literal
# §4.A.5.3 rule, kept so the masking is a strict superset of it.
NUMERIC_FORM = r"(?<![vV])(?<!\d:)\b\d+(?!:\d)(?!(?:st|nd|rd|th)\b)\b"


def load_claim_forms() -> dict[str, list[str]]:
    """HR / QRS / axis surface forms, straight from the B5 claim dictionary."""
    cfg = yaml.safe_load(
        (bc.CONFIG_DIR / "claim_dictionary_LOCKED.yaml").read_text(encoding="utf-8")
    )
    families: dict[str, list[str]] = {}
    for family, block in cfg["families"].items():
        if family == "PR":
            continue          # PR is an interval claim, not an HR/QRS/QTc bin
        # The dictionary stores STEMS ("bradycardi"), because B5 swaps a stem
        # and keeps the inflection. A5 must remove the whole word instead:
        # masking the stem alone leaves "Sinus [MASK]a", which advertises both
        # that something was removed and how long it was. \w* eats the
        # inflection so [MASK] stands in for a complete token.
        families[family] = [str(form["pattern"]) + r"\w*" for form in block["surface_forms"]]
    families["QT"] = QT_FORMS
    families["numeric"] = [NUMERIC_FORM]
    return families


def build_masker(families: dict[str, list[str]]) -> list[tuple[str, re.Pattern]]:
    """One compiled, case-insensitive pattern per family, longest-first.

    Longest-first inside a family stops "qt interval" from eating the first half
    of "prolonged qt interval" and leaving a fragment behind.
    """
    compiled = []
    for family, patterns in families.items():
        ordered = sorted(patterns, key=len, reverse=True)
        compiled.append((family, re.compile("|".join(f"(?:{p})" for p in ordered), re.IGNORECASE)))
    return compiled


def mask_report(text: str, masker: list[tuple[str, re.Pattern]]) -> tuple[str, list[int], str]:
    """Replace every attribute-bearing claim with ``[MASK]``.

    Returns the masked text, the character offsets of each ``[MASK]`` **in the
    masked text**, and the families that fired. Offsets point into the masked
    text because that is the string a model is given; ``report_text`` in the
    verification table still holds the original.
    """
    spans: list[tuple[int, int, str]] = []
    for family, pattern in masker:
        for match in pattern.finditer(text):
            spans.append((match.start(), match.end(), family))
    if not spans:
        return text, [], ""

    spans.sort(key=lambda s: (s[0], -s[1]))
    merged: list[tuple[int, int, set[str]]] = []
    for start, end, family in spans:
        if merged and start < merged[-1][1]:
            previous = merged[-1]
            merged[-1] = (previous[0], max(previous[1], end), previous[2] | {family})
        else:
            merged.append((start, end, {family}))

    pieces: list[str] = []
    positions: list[int] = []
    cursor = 0
    out_len = 0
    fired: set[str] = set()
    for start, end, fams in merged:
        pieces.append(text[cursor:start])
        out_len += start - cursor
        positions.append(out_len)
        pieces.append(MASK_TOKEN)
        out_len += len(MASK_TOKEN)
        cursor = end
        fired |= fams
    pieces.append(text[cursor:])
    return "".join(pieces), positions, ",".join(sorted(fired))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    bc.add_std_args(parser)
    args = parser.parse_args()

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT + ("_dev" if args.dev else ""))
    if state.done and not args.force:
        log.info("already complete (%s rows) -- pass --force to rebuild", state.data.get("n_rows"))
        return 0
    state.reset()
    started = time.time()

    bc.preflight([bc.CONFIG_DIR / "claim_dictionary_LOCKED.yaml"])

    # --- head 1: verification ------------------------------------------------
    cohort = bc.load_clean_cohort(dev=args.dev)
    verification = vt.build_verification(dev=args.dev)
    vt.assert_no_cross_split_donor(verification, cohort)
    vt.assert_negatives_are_mismatched(verification, cohort)
    counts = bc.write_task_split_parquets(verification, TASK, schema=vt.SCHEMA)
    log.info("verification rows: %d, splits %s", len(verification), counts)

    # --- head 2: masked attribute -------------------------------------------
    masker = build_masker(load_claim_forms())
    labels = mt.measurement_table(dev=args.dev)
    text = bc.report_text_series(dev=args.dev)
    masked = labels[["study_id", "subject_id", "split", "hr_label", "qrs_label", "qtc_label"]].merge(
        text, on="study_id", how="inner"
    )
    log.info("masked-attribute rows (all three measurements valid): %d", len(masked))

    results = [mask_report(t, masker) for t in masked.report_text.tolist()]
    masked["report_text_masked"] = [r[0] for r in results]
    masked["masked_positions"] = [np.asarray(r[1], dtype="int32") for r in results]
    masked["n_masked_spans"] = np.asarray([len(r[1]) for r in results], dtype="int32")
    masked["masked_families"] = [r[2] for r in results]

    masked_counts = bc.write_task_split_parquets(
        masked, TASK, schema=MASKED_SCHEMA, prefix="masked_attribute_"
    )
    log.info("masked-attribute splits: %s", masked_counts)

    # --- validation (§9.2) ---------------------------------------------------
    changed = masked.report_text_masked.to_numpy() != masked.report_text.to_numpy()
    family_hits: dict[str, int] = {}
    for family in ("HR", "QRS", "axis", "QT", "numeric"):
        family_hits[family] = int(
            masked.masked_families.str.contains(rf"\b{family}\b", regex=True).sum()
        )

    stats = {
        "verification": vt.verification_stats(verification),
        "verification_splits": counts,
        "masked_attribute": {
            "n_rows": int(len(masked)),
            "splits": masked_counts,
            "n_reports_changed": int(changed.sum()),
            "pct_reports_changed": round(100 * float(changed.mean()), 3),
            "mean_masked_spans": round(float(masked.n_masked_spans.mean()), 3),
            "max_masked_spans": int(masked.n_masked_spans.max()),
            "reports_by_family": family_hits,
            "labels": mt.label_stats(masked),
        },
    }
    stats.update(bc.split_summary(verification))
    log.info("validation:\n%s", json.dumps(stats, indent=2, default=str)[:4000])

    if stats["verification"]["n_rows"] == 0:
        raise RuntimeError("A5 verification table is empty")
    balance = stats["verification"]["positive_rate_pct"]
    if not 26.0 <= balance <= 30.0:
        raise RuntimeError(
            f"positive rate is {balance} %, not the ~2-in-7 (28.6 %) the "
            "§4.A.5.3 construction gives -- rows were lost or duplicated"
        )
    if stats["masked_attribute"]["pct_reports_changed"] < 30.0:
        raise RuntimeError(
            f"only {stats['masked_attribute']['pct_reports_changed']} % of reports were masked; "
            "the measured claim-bearing share of the corpus is 44.3 % -- the vocabulary is wrong"
        )
    for row in masked.head(2000).itertuples():
        for pos in row.masked_positions:
            if row.report_text_masked[pos:pos + len(MASK_TOKEN)] != MASK_TOKEN:
                raise RuntimeError(f"masked_positions is misaligned on study {row.study_id}")

    examples = [
        {"study_id": int(r.study_id), "original": r.report_text[:160],
         "masked": r.report_text_masked[:160], "families": r.masked_families}
        for r in masked[changed].head(5).itertuples()
    ]
    stats["masked_attribute"]["examples"] = examples
    log.info("masking examples:\n%s", json.dumps(examples, indent=2))

    bc.write_task_readme(TASK, README.format(
        stats=json.dumps(stats, indent=2, default=str), built_at=bc.utc_now_iso()
    ))
    state.finish(n_verification_rows=int(len(verification)), **stats)
    log.info("DONE in %.1f s", time.time() - started)
    return 0


README = """# A5 -- cross-modal verification + masked attribute prediction

Spec: `docs/PHASE2_SOURCE_OF_TRUTH.md` §4.A.5 · built {built_at} by
`scripts/phase2_tasks_benchmark_and_paper/05_build_A5_cross_modal_verification.py`.

## Two tables

| File | Head | Row |
| --- | --- | --- |
| `{{train,val,test}}.parquet` | verification | one (signal, image, text) triple |
| `masked_attribute_{{train,val,test}}.parquet` | masked attribute | one study |

## Verification rows

Seven per anchor: 2 positives (clean and scan-like rendering of the anchor's own
image) and 5 negatives, one per `neg_type`. `signal_id` / `image_id` / `text_id`
name the study each modality is resolved from — always through
`read_modality()`, never by opening a container.

Two rules the split contract forces, both asserted at build time:

* **donors are drawn from the anchor's own split** — a train row pointing at a
  test subject would put test bytes into training;
* **every negative disagrees with its anchor at the subject level**, so
  `y_match = 0` is not a lie for a model that has learned patient identity.

Negatives all use `image_type == 'clean'` so the per-`neg_type` F1 table is not
confounded by rendering. The clean-vs-scanlike and Lead-II-vs-12-lead
comparisons are made by resolving a different modality kind for the same
`image_id` at load time.

`HARD_NEGATIVE_TEXT` needs a same-HR-bucket, different-subject donor in the same
split; the few anchors without one yield 6 rows instead of 7 (§4.A.5.3).

## Masked attribute — a documented deviation

§4.A.5.3 asks for numeric mentions of HR / QRS / QT / QTc / axis / intervals to
be replaced with `[MASK]`. **These reports have no numeric measurements.**
Measured across all 749,112: 12.5 % contain any digit, and only **0.51 %**
contain one that is not a lead name, an ordinal or a ratio — every one of those
being the boilerplate "Age not entered, assumed to be 50 years old".

Taken literally the rule masks nothing, `report_text_masked` equals
`report_text`, and the report still says "Sinus bradycardia" — so the HR head
becomes a lookup. This table therefore masks the **qualitative claims** that
carry the attribute in this vocabulary, which 44.3 % of reports contain, and
masks bare numerals as well so the rule stays a strict superset of the literal
one.

HR, QRS and axis surface forms are read from
`config/claim_dictionary_LOCKED.yaml`, so A5 and B5 cannot drift apart; QT/QTc
forms are defined in the builder because B5 has no QT family.

`masked_positions` holds the character offset of each `[MASK]` **in
`report_text_masked`**, and `masked_families` records which families fired.

**Disclosed in the supplementary.**

## Forbidden inputs

`machine_measurements`, `structured_features` (§4.A.5.4). `report_text_masked`
is allowed precisely because its attribute content has been removed.

## Build statistics

```json
{stats}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
