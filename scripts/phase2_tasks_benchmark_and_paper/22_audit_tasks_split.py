"""Stage P2.3 script 22 -- the split audit (spec §9.4, §4.C invariant 1).

    ./ecg_env/Scripts/python.exe \\
        scripts/phase2_tasks_benchmark_and_paper/22_audit_tasks_split.py

Writes `outputs/audit_reports/split_audit_phase2.md`. Exit 0 on PASS, 1 on a
violation. The third of the three files `30_train.py` reads before any
full-scale run (§4.C invariant 4).

§9.4 asks for: "for every task, verify zero subject overlap across
train/val/test". That is check 2 below. It is necessary and, on its own, not
sufficient -- a task could partition its own rows perfectly and still have
re-derived the split, which §4.C invariant 1 forbids ("the split column is
**always** populated from that join, never re-derived"). A task built off a
re-derived split would be internally consistent and still put a patient in
training who is in another task's test set, which is exactly the leak a
patient-level split exists to prevent.

So five things are checked per task:

1. **The split column matches the file.** Every row in `train.parquet` says
   `train`. A row filed under the wrong name is invisible to the overlap check.
2. **Zero subject overlap** across the three splits -- §9.4's requirement.
3. **Agreement with the frozen global split.** Every subject's split equals
   `splits_subject_level.parquet`'s, and every subject is in it. This is what
   makes the twelve tasks mutually consistent rather than each internally
   consistent.
4. **No study crosses a split**, which subject-level disjointness implies but
   which is worth measuring separately: it catches a study_id joined to the
   wrong subject.
5. **Donor containment** for the verification tasks. A5/B4 rows point at up to
   three different studies, and §4.C invariant 1 is about the BYTES a row
   loads, not just its anchor. A train row pointing at a test subject's signal
   carries test bytes into training, and no amount of anchor-level disjointness
   would show it. Every `signal_id` / `image_id` / `text_id` must resolve to a
   subject in the row's own split -- and, on a negative, to a DIFFERENT subject
   than the anchor, or the "negative" is a positive with a different label.

Nothing here re-splits anything, and this audit writes no parquet.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dataset_lib import audit_common as ac                              # noqa: E402
from _dataset_lib import build_common as bc                              # noqa: E402
from _dataset_lib.task_spec import TASK_KEYS, TaskSpec, get_task         # noqa: E402

STAGE = "P2.3"
SCRIPT = "22_audit_tasks_split"

DONOR_COLUMNS = ("signal_id", "image_id", "text_id")
# The one §6.7 rung that is same-subject BY DESIGN (Round 10, §12.9 item 4):
# level 4 swaps in a different STUDY from the SAME patient. Every other
# negative must come from a different subject.
SAME_SUBJECT_NEG_TYPES = ("HARD_NEGATIVE_L4",)


def global_split() -> pd.Series:
    """`subject_id -> split`, the frozen Phase 1 partition (trap 4)."""
    frame = pd.read_parquet(bc.DATA_PROCESSED / "splits_subject_level.parquet",
                            columns=["subject_id", "split"])
    return frame.set_index("subject_id")["split"]


def study_to_subject() -> pd.Series:
    """`study_id -> subject_id` over the clean cohort, for donor resolution."""
    cohort = bc.load_clean_cohort()
    return cohort.set_index("study_id")["subject_id"]


def split_frames(spec: TaskSpec) -> dict[str, pd.DataFrame]:
    directory = bc.TASKS_DIR / spec.key
    files = {"train": spec.train_file, "val": spec.val_file, "test": spec.test_file}
    out: dict[str, pd.DataFrame] = {}
    for split, filename in files.items():
        frame = pd.read_parquet(directory / filename)
        if "split" in frame.columns:
            frame = frame[frame["split"] == split]
        out[split] = frame.reset_index(drop=True)
    return out


def declared_split(spec: TaskSpec) -> dict[str, int]:
    """Rows whose `split` column disagrees with the file they are stored in.

    Read straight off the file, before any filtering -- `split_frames` filters
    on the split column, so by the time it has run a misfiled row is gone.
    """
    directory = bc.TASKS_DIR / spec.key
    files = {"train": spec.train_file, "val": spec.val_file, "test": spec.test_file}
    if len(set(files.values())) == 1:            # B6's one pointer table
        return {}
    wrong: dict[str, int] = {}
    for split, filename in files.items():
        column = pd.read_parquet(directory / filename, columns=["split"])["split"]
        wrong[split] = int((column != split).sum())
    return wrong


# -----------------------------------------------------------------------------
def audit_task(audit: ac.Audit, task_key: str, splits: pd.Series,
               s2s: pd.Series, log) -> None:
    spec = get_task(task_key)
    audit.heading(f"`{task_key}`", level=2)
    frames = split_frames(spec)

    # 1 -- the split column agrees with the file it is stored in
    wrong = declared_split(spec)
    if wrong:
        audit.check(task_key, "split_column_matches_file", sum(wrong.values()) == 0,
                    f"rows filed under the wrong split: {wrong}")
    else:
        audit.check(task_key, "split_column_matches_file", True,
                    "one pointer table for all three splits (§4.B.6.5); rows are "
                    "separated by the `split` column alone")

    subjects = {split: set(frame.subject_id.unique()) for split, frame in frames.items()}
    studies = {split: set(frame[spec.id_column].unique()) for split, frame in frames.items()}

    rows = []
    for split in bc.SPLITS:
        rows.append([split, f"{len(frames[split]):,}", f"{len(studies[split]):,}",
                     f"{len(subjects[split]):,}"])
    audit.table(["split", "rows", f"unique `{spec.id_column}`", "subjects"], rows)

    # 2 -- zero subject overlap, the §9.4 requirement
    pairs = [("train", "val"), ("train", "test"), ("val", "test")]
    overlaps = {f"{a}/{b}": len(subjects[a] & subjects[b]) for a, b in pairs}
    audit.check(task_key, "zero_subject_overlap", sum(overlaps.values()) == 0,
                f"pairwise subject intersections {overlaps}")

    # 3 -- agreement with the frozen global split
    all_rows = pd.concat(frames.values(), ignore_index=True)
    mapped = splits.reindex(all_rows.subject_id.to_numpy())
    unknown = int(mapped.isna().sum())
    disagree = int((mapped.to_numpy() != all_rows["split"].to_numpy()).sum()) - unknown
    audit.check(task_key, "subjects_exist_in_global_split", unknown == 0,
                f"{unknown} row(s) carry a subject absent from "
                f"splits_subject_level.parquet")
    audit.check(task_key, "split_matches_global_split", disagree == 0,
                f"{disagree} row(s) sit in a split other than the one the frozen "
                f"patient partition assigns (§4.C invariant 1)")

    # 4 -- no study crosses a split
    study_overlaps = {f"{a}/{b}": len(studies[a] & studies[b]) for a, b in pairs}
    audit.check(task_key, "zero_study_overlap", sum(study_overlaps.values()) == 0,
                f"pairwise {spec.id_column} intersections {study_overlaps}")

    # 5 -- donor containment, for the tasks whose rows point at other studies
    donors = [c for c in DONOR_COLUMNS if c in all_rows.columns]
    if donors:
        donor_rows = []
        for column in donors:
            donor_subject = s2s.reindex(all_rows[column].to_numpy())
            donor_split = splits.reindex(donor_subject.to_numpy())
            unresolved = int(donor_subject.isna().sum())
            crossing = int((donor_split.to_numpy() != all_rows["split"].to_numpy()).sum())
            audit.check(task_key, f"donor_in_same_split[{column}]",
                        unresolved == 0 and crossing == 0,
                        f"{unresolved} `{column}` value(s) resolve to no clean-cohort "
                        f"subject; {crossing} point at a subject in another split")

            negative = all_rows["y_match"].to_numpy() == 0
            swapped = all_rows[column].to_numpy() != all_rows[spec.id_column].to_numpy()
            same_subject = (donor_subject.to_numpy() == all_rows.subject_id.to_numpy())

            # Round 10 (§12.9 item 4) makes ONE rung same-subject on purpose:
            # level 4 is "a different STUDY from the SAME subject", the hardest
            # negative short of altering the anchor's own text. Excluding it
            # from this check is not a weakening -- the two assertions below
            # replace it with a stricter pair, because a same-subject row is
            # only legitimate when it is level 4 AND still a different study.
            ladder_same_subject = np.zeros(len(all_rows), dtype=bool)
            if "neg_type" in all_rows.columns:
                ladder_same_subject = all_rows["neg_type"].isin(
                    SAME_SUBJECT_NEG_TYPES).to_numpy()

            leaked = int((negative & swapped & same_subject & ~ladder_same_subject).sum())
            audit.check(task_key, f"negative_donor_is_another_subject[{column}]", leaked == 0,
                        f"{leaked} negative row(s) outside the §6.7 level-4 rung take "
                        f"`{column}` from the anchor's own subject — that row would be a "
                        f"near-positive labelled negative")

            # The level-4 rung, held to its own contract. Scoped to the rows
            # where THIS column is actually swapped: level 4 substitutes the
            # text and keeps the anchor's own signal and image, so signal_id
            # and image_id equalling the anchor is the design, not a defect.
            l4_swapped = negative & ladder_same_subject & swapped
            n_l4_swapped = int(l4_swapped.sum())
            if n_l4_swapped:
                l4_other_subject = int((l4_swapped & ~same_subject).sum())
                audit.check(task_key, f"level4_donor_is_the_same_subject[{column}]",
                            l4_other_subject == 0,
                            f"{l4_other_subject} of {n_l4_swapped:,} swapped level-4 "
                            f"`{column}` value(s) come from a different subject; that is a "
                            "level-0 negative wearing a level-4 label and would flatten "
                            "the §6.7 curve")
            donor_rows.append([f"`{column}`", f"{int(swapped.sum()):,}",
                               f"{unresolved}", f"{crossing}", f"{leaked}"])
        # A level-4 negative must actually swap SOMETHING. Checked once per row
        # rather than per column: level 4 keeps the anchor's signal and image and
        # substitutes only the text, so no single column can carry this
        # assertion, and a row that swapped nothing would be a positive wearing
        # a negative label -- the failure the whole ladder exists to avoid.
        if "neg_type" in all_rows.columns:
            is_l4 = all_rows["neg_type"].isin(SAME_SUBJECT_NEG_TYPES).to_numpy()
            if is_l4.any():
                any_swapped = np.zeros(len(all_rows), dtype=bool)
                for column in donors:
                    any_swapped |= (all_rows[column].to_numpy()
                                    != all_rows[spec.id_column].to_numpy())
                unswapped = int((is_l4 & ~any_swapped).sum())
                audit.check(task_key, "level4_swaps_at_least_one_modality",
                            unswapped == 0,
                            f"{unswapped} of {int(is_l4.sum()):,} level-4 row(s) point every "
                            "modality at the anchor itself — that row is a positive "
                            "labelled negative")

        audit.add("", "**Donor containment.** Each verification row points at up to three "
                      "studies; every one of them must belong to a subject in the row's "
                      "own split, and a swapped modality on a negative must come from a "
                      "different subject — except the §6.7 level-4 rung, which swaps in a "
                      "different STUDY from the SAME subject by design and is held to that "
                      "contract instead.", "")
        audit.table(["pointer column", "rows where it is not the anchor",
                     "unresolved", "crossing a split", "same-subject on a negative"],
                    donor_rows)

    # A5's masked-attribute sibling table is a second file per split
    if task_key == "A5_cross_modal_verification":
        sibling_bad, sibling_rows = 0, []
        for split in bc.SPLITS:
            masked = pd.read_parquet(
                bc.TASKS_DIR / task_key / f"masked_attribute_{split}.parquet",
                columns=["study_id", "subject_id", "split"])
            wrong_split = int((masked["split"] != split).sum())
            mapped = splits.reindex(masked.subject_id.to_numpy())
            wrong_global = int((mapped.to_numpy() != split).sum())
            sibling_bad += wrong_split + wrong_global
            sibling_rows.append([f"`masked_attribute_{split}.parquet`", f"{len(masked):,}",
                                 f"{masked.subject_id.nunique():,}", wrong_split,
                                 wrong_global])
        audit.table(["file", "rows", "subjects", "wrong split column",
                     "disagreeing with the global split"], sibling_rows)
        audit.check(task_key, "masked_attribute_files_respect_the_split", sibling_bad == 0,
                    f"{sibling_bad} row(s) across the three masked-attribute files sit in "
                    f"the wrong split")

    log.info("%s: %s", task_key, {s: len(f) for s, f in frames.items()})


def audit_global(audit: ac.Audit, splits: pd.Series) -> None:
    audit.heading("The frozen patient split this audit checks against")
    counts = splits.value_counts().to_dict()
    audit.add("`data/processed/splits_subject_level.parquet`, inherited from Phase 1 and "
              "never re-split (§4.C invariant 1, progress-doc trap 4). Every task is a "
              "subset of it; no task reshuffles it.", "")
    audit.table(["split", "subjects"],
                [[s, f"{counts.get(s, 0):,}"] for s in bc.SPLITS] +
                [["**all**", f"**{len(splits):,}**"]])
    audit.check("(global)", "global_split_is_a_partition",
                splits.index.is_unique and set(counts) == set(bc.SPLITS),
                f"{len(splits):,} subjects, each in exactly one of {sorted(counts)}")


def audit_b2_anchors(audit: ac.Audit) -> None:
    """The frozen B2 anchor set is a TEST-split sample (§4.B.2.2, §5 question 10)."""
    task_key = "B2_noise_robustness"
    frame = pd.concat([pd.read_parquet(bc.TASKS_DIR / task_key / f"{s}.parquet",
                                       columns=["subject_id", "split", "is_anchor"])
                       for s in bc.SPLITS], ignore_index=True)
    anchors = frame[frame.is_anchor.astype(bool)]
    seen = set(anchors.split.unique())
    audit.heading("B2 — the frozen anchor set stays in test", level=3)
    audit.add("The 1,871 anchors were frozen in Phase 1 Stage 8 and must never be "
              "regenerated. They are a test-split sample, so a train or val row flagged "
              "`is_anchor` would mean the frozen evaluation set had reached training.", "")
    audit.check(task_key, "frozen_anchors_are_test_only", seen == {"test"},
                f"{len(anchors):,} anchor rows over {anchors.subject_id.nunique():,} "
                f"subjects, all in {sorted(seen)}")


# -----------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", nargs="*", default=list(TASK_KEYS),
                        help="audit a subset (debugging only; a partial run records the "
                             "omission and therefore cannot PASS)")
    args = parser.parse_args()

    log = bc.setup_logging(SCRIPT, stage=STAGE)
    state = bc.StageState(STAGE, SCRIPT)
    state.reset()
    started = time.time()
    bc.preflight([bc.TASKS_DIR, bc.DATA_PROCESSED / "splits_subject_level.parquet"],
                 need_free_gb=0.5)

    audit = ac.Audit(
        title="Split audit — Phase 2 tasks (Stage P2.3)",
        filename="split_audit_phase2.md",
        spec="§9.4 (Stage P2.3), §4.C invariant 1",
        script=f"{SCRIPT}.py",
        intro=[
            "§9.4 asks for zero subject overlap across train/val/test for every task. "
            "That is checked, and so are the four things it does not cover on its own: "
            "that each row's `split` column matches the file it is stored in; that every "
            "subject's split equals the frozen `splits_subject_level.parquet` rather "
            "than anything re-derived (§4.C invariant 1); that no study crosses a split; "
            "and — for A5 and B4, whose rows point at up to three different studies "
            "— that every pointed-at modality belongs to a subject in the row's own "
            "split, and that a swapped modality on a negative comes from a different "
            "subject than the anchor.",
            "",
            "A task can partition its own rows perfectly and still be wrong, if it "
            "partitioned them itself. The global-agreement check is what makes the "
            "twelve tasks consistent with each other and with Phase 1.",
        ],
    )

    splits = global_split()
    s2s = study_to_subject()
    audit_global(audit, splits)

    if sorted(args.tasks) != sorted(TASK_KEYS):
        audit.check("(global)", "every_task_audited", False,
                    f"only {args.tasks} were audited; §9.4 requires all 12")

    for task_key in args.tasks:
        audit_task(audit, task_key, splits, s2s, log)
    if "B2_noise_robustness" in args.tasks:
        audit_b2_anchors(audit)

    path = audit.write(log)
    state.finish(verdict=audit.verdict, n_checks=len(audit.checks),
                 n_violations=len(audit.violations),
                 report=str(path.relative_to(bc.PROJECT_ROOT)),
                 elapsed_s=round(time.time() - started, 1))
    log.info("split audit %s — %d checks, %d violations, %.1f s",
             audit.verdict, len(audit.checks), len(audit.violations), time.time() - started)
    return audit.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
