# Agent instructions — Tri-Modal ECG

## Start every session here

**Read `docs/PHASE2_PROGRESS.md` before doing anything else** — before
answering questions, before exploring the repo, before planning. It is the live
state of this project: what is done, what is next, what is decided, what is
blocked. It exists so no session needs the previous session's transcript.

It tells you which other documents to read and in what order. Follow that order.
Do not go spelunking through the repo to reconstruct state that the progress doc
already records.

## Update it before every session ends

`docs/PHASE2_PROGRESS.md` is not a read-only briefing — **you maintain it.**
Without being asked, update it whenever any of these happen:

- a step in the §6 ledger starts, finishes, or becomes blocked → change its mark
  (`[ ]` → `[~]` → `[x]`, or `[!]` with the reason)
- a decision gets made → add it to §4 and to the spec's §12 decision record
- a question gets answered or a new one appears → update §5
- a number, path, or environment fact changes → update §2 or §3
- you discover something that would trip up the next agent → add it to §7 traps
- **any session that changed anything** → append an entry to the §8 session log,
  and refresh the header block at the top (last updated, current stage, next
  action, blockers)

Keep the header block accurate above all else. If a future agent reads only the
first fifteen lines, they should still know exactly where to pick up.

Prefer updating the existing text over appending new sections — a progress doc
that grows by accretion stops being readable, and an unreadable handover is the
same as no handover.

## Project rules

- **Use `./ecg_env/Scripts/python.exe` for all Python.** The system Python 3.14
  has a CPU-only torch and will silently not use the GPU.
- **`docs/PHASE2_SOURCE_OF_TRUTH.md` is binding.** It is a medical-grade
  benchmark spec. Where it defines a cohort, a metric, an input policy, or a
  statistical procedure, follow it exactly. If an implementation would violate
  it, the implementation is wrong, not the spec. If the spec is genuinely
  ambiguous or you believe it is wrong, **halt and ask** — record the answer in
  its §12 and in the progress doc. "I picked a sensible default" is never
  acceptable here.
- **Never re-run Phase 1.** It is complete and audited. Its outputs are
  read-only ground truth.
- **Never re-split patients.** Tasks subset `splits_subject_level.parquet`;
  nothing reshuffles it.
- **Never read an HDF5 or tar directly.** Go through `read_modality()` and the
  modality manifest.
- **Never commit credentials.** The DGX password and R2 keys live in the user's
  password manager and `%APPDATA%\rclone\rclone.conf`, never in this repo.
- **Never commit data.** `data/` and `ecg_env/` are permanently excluded. Raw
  MIMIC never leaves the laptop and never enters a release package.
- **`.gitignore` ignores the repo root by default** (`/*`) and re-includes
  subtrees explicitly. A **new root-level file needs its own `!/name` entry** or
  it will be silently untracked. Check `git status` after adding one.
- **The DGX is reachable only from inside the MU network**, via remote desktop
  to an on-campus laptop. This is a hard constraint from the user — do not
  propose tunnels, Tailscale, reverse SSH, or any other inbound route.
- **The laptop's mains power is unreliable.** Anything long-running that runs
  locally must checkpoint and resume cleanly.
- **Scope is not negotiable.** The user has stated that no task, seed, sweep, or
  evaluation is dropped to save compute or time. Weeks or months of runtime is
  acceptable; a quietly reduced experiment is not. If something looks
  infeasible, say so and propose how to do it anyway — do not silently shrink it.

## Working style

Verify against the repo rather than trusting the docs on factual claims — the
docs have been wrong before (the spec claimed Phase 1 had cached R-peak arrays
that do not exist). When a doc and the filesystem disagree, the filesystem wins
and the doc gets corrected.
