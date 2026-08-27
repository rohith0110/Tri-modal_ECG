"""Shared plumbing for the three Stage P2.3 audits (spec §9.4).

`20_audit_tasks_leakage.py`, `21_audit_tasks_cohort.py` and
`22_audit_tasks_split.py` each produce one markdown report under
`outputs/audit_reports/`, and `30_train.py::check_audit_gate` reads all three
back before a single batch is loaded (§4.C invariant 4). That gate is a text
match, so the report format is a machine contract, not decoration:

* every report carries exactly one verdict line, `**VERDICT: PASS**` or
  `**VERDICT: FAIL**`, as its first non-heading line;
* :func:`report_verdict` is the ONE parser for that line, and `30_train.py`
  imports it rather than carrying a second copy.

The parser exists because the obvious implementation -- scan the whole report
for the substring "FAIL" -- is wrong on this dataset. A1's heads are named
`label_heart_failure_narrow` and friends, so a leakage audit that does its job
and lists every column emits the token inside a column name and a substring
scan reads a clean report as a blocked one. The verdict is a line, not a word
somewhere in the prose.

:meth:`Audit.write` parses its own rendered report back with
:func:`report_verdict` before the file lands, so an audit cannot emit a report
the gate would misread.

Nothing here decides what a check *is*; the three scripts do that. This module
owns the bookkeeping, the markdown, and the contract with the gate.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _dataset_lib import build_common as bc  # noqa: E402

AUDIT_DIR = bc.PROJECT_ROOT / "outputs" / "audit_reports"

# The verdict tokens `30_train.py::check_audit_gate` reads.
PASS = "PASS"
BLOCK = "FAIL"
NO_VERDICT = "NO_VERDICT"

VERDICT_LINE = re.compile(r"^\*\*VERDICT:\s*(PASS|FAIL)\*\*", re.MULTILINE)


def report_verdict(text: str) -> str:
    """`PASS`, `FAIL` or `NO_VERDICT` for one audit report's text.

    The single reader of the audit-gate contract (§4.C invariant 4). A report
    with no verdict line, or with two that disagree, is `NO_VERDICT` and blocks
    -- an audit that cannot state its own outcome has not run.
    """
    found = VERDICT_LINE.findall(text)
    if not found or len(set(found)) != 1:
        return NO_VERDICT
    return found[0]


@dataclass
class Check:
    """One assertion, its subject, and what it measured."""

    task: str
    check_id: str
    ok: bool
    detail: str

    @property
    def verdict(self) -> str:
        return PASS if self.ok else BLOCK


@dataclass
class Audit:
    """Collects checks and markdown blocks, then renders one audit report."""

    title: str
    filename: str
    spec: str
    script: str
    intro: Sequence[str] = ()
    checks: list[Check] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)

    # -- recording -------------------------------------------------------------
    def check(self, task: str, check_id: str, ok: bool, detail: str) -> bool:
        self.checks.append(Check(task, check_id, bool(ok), detail))
        return bool(ok)

    def add(self, *lines: str) -> None:
        self.blocks.extend(lines)

    def heading(self, text: str, level: int = 2) -> None:
        self.blocks += ["", "#" * level + " " + text, ""]

    def table(self, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
        self.blocks.append("| " + " | ".join(str(h) for h in header) + " |")
        self.blocks.append("| " + " | ".join("---" for _ in header) + " |")
        for row in rows:
            self.blocks.append("| " + " | ".join(_cell(v) for v in row) + " |")
        self.blocks.append("")

    # -- outcome ---------------------------------------------------------------
    @property
    def violations(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    @property
    def verdict(self) -> str:
        return BLOCK if self.violations else PASS

    def tasks(self) -> list[str]:
        seen: list[str] = []
        for check in self.checks:
            if check.task not in seen:
                seen.append(check.task)
        return seen

    def task_verdict(self, task: str) -> str:
        bad = [c for c in self.checks if c.task == task and not c.ok]
        return BLOCK if bad else PASS

    # -- rendering -------------------------------------------------------------
    def render(self) -> str:
        n_ok = len(self.checks) - len(self.violations)
        out: list[str] = [
            f"# {self.title}",
            "",
            f"**VERDICT: {self.verdict}** — {len(self.checks)} checks run, "
            f"{n_ok} passed, {len(self.violations)} violations.",
            "",
            f"Spec {self.spec}. Generated {bc.utc_now_iso()} by "
            f"`scripts/phase2_tasks_benchmark_and_paper/{self.script}` from the task "
            f"parquets on disk — every number below is measured, none is restated from "
            f"a builder's own report.",
            "",
        ]
        out += list(self.intro)
        out += ["", "## Verdict by task", ""]
        out.append("| Task | Checks | Verdict |")
        out.append("| --- | ---: | --- |")
        for task in self.tasks():
            n = sum(1 for c in self.checks if c.task == task)
            out.append(f"| `{task}` | {n} | **{self.task_verdict(task)}** |")
        out.append("")

        if self.violations:
            out += ["## Violations", "",
                    "Each of these is CRITICAL under §11.2 and blocks every training "
                    "stage. The fix belongs in the builder that produced the artifact, "
                    "not in this audit.", ""]
            out.append("| Task | Check | Detail |")
            out.append("| --- | --- | --- |")
            for check in self.violations:
                out.append(f"| `{check.task}` | `{check.check_id}` | {_cell(check.detail)} |")
            out.append("")

        out += self.blocks

        out += ["", "## Every check, in the order it ran", ""]
        out.append("| # | Task | Check | Verdict | Measured |")
        out.append("| ---: | --- | --- | --- | --- |")
        for i, check in enumerate(self.checks, 1):
            out.append(f"| {i} | `{check.task}` | `{check.check_id}` | {check.verdict} | "
                       f"{_cell(check.detail)} |")
        out += ["",
                "## Reproduce",
                "",
                "```",
                f"./ecg_env/Scripts/python.exe scripts/phase2_tasks_benchmark_and_paper/"
                f"{self.script}",
                "```",
                "",
                "The audit reads only artifacts already on disk and writes only this "
                "report, so it is safe to re-run at any time.",
                ""]
        return "\n".join(out)

    def write(self, log: Any = None) -> Path:
        """Render, enforce the gate contract, then land the file atomically."""
        text = self.render()
        parsed = report_verdict(text)
        if parsed != self.verdict:
            raise RuntimeError(
                f"{self.filename} would be read by the training gate as {parsed!r} "
                f"while this audit's own verdict is {self.verdict!r}. The report is "
                f"not written; fix the renderer before anything reads it."
            )
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        path = AUDIT_DIR / self.filename
        tmp = path.with_suffix(".md.tmp")
        tmp.write_text(text, encoding="utf-8")
        bc.atomic_replace(tmp, path)
        if log is not None:
            log.info("%s — %s (%d checks, %d violations) -> %s",
                     self.title, self.verdict, len(self.checks), len(self.violations),
                     path.relative_to(bc.PROJECT_ROOT))
        return path

    def exit_code(self) -> int:
        return 0 if self.verdict == PASS else 1


def _cell(value: Any) -> str:
    """Markdown-table-safe one-line rendering of a value."""
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= 300 else text[:297] + "..."


def fmt_counts(counts: dict[Any, int], top: int | None = None) -> str:
    """`a 3 · b 1` — deterministic, compact, and safe inside a table cell."""
    items = sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))
    if top:
        items = items[:top]
    return " · ".join(f"{k} {v:,}" for k, v in items) or "(none)"


def _self_check() -> None:
    """The gate contract is the only thing here worth a test."""
    good = Audit(title="t", filename="_selfcheck.md", spec="§9.4", script="audit_common.py")
    good.check("A1", "c1", True, "0 violations")
    assert good.verdict == PASS
    assert report_verdict(good.render()) == PASS

    bad = Audit(title="t", filename="_selfcheck.md", spec="§9.4", script="audit_common.py")
    bad.check("A1", "c1", False, "1 forbidden column")
    assert bad.verdict == BLOCK and report_verdict(bad.render()) == BLOCK
    assert bad.exit_code() == 1

    # The reason the parser exists: A1's head names carry the block token, and a
    # substring scan would read this clean report as a blocked one.
    collides = Audit(title="t", filename="_selfcheck.md", spec="§9.4",
                     script="audit_common.py")
    collides.check("A1_ecg_diagnosis", "c1", True, "head `label_heart_failure_narrow` ok")
    assert collides.verdict == PASS
    assert BLOCK in collides.render().upper(), "this fixture is pointless if it does not collide"
    assert report_verdict(collides.render()) == PASS, \
        "a column name containing the token must not flip the verdict"

    assert report_verdict("no verdict line here") == NO_VERDICT
    assert report_verdict("**VERDICT: PASS**\n**VERDICT: FAIL**") == NO_VERDICT

    assert fmt_counts({"b": 1, "a": 3}) == "a 3 · b 1"
    print("audit_common self-check: PASS  (verdict parser holds, and survives a "
          "column name that contains the token)")


if __name__ == "__main__":
    _self_check()
