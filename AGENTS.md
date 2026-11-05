# Agent instructions — Tri-Modal ECG

## Start every session here

Three steps, in this order, before answering anything:

1. read `.machine` — **which of the three machines is this?** (next section)
2. `git pull --ff-only origin main` — **or the progress doc you read is stale**
3. read `docs/PHASE2_PROGRESS.md`

**Then read `docs/PHASE2_PROGRESS.md` before doing anything else** — before
answering questions, before exploring the repo, before planning. It is the live
state of this project: what is done, what is next, what is decided, what is
blocked. It exists so no session needs the previous session's transcript.

It tells you which other documents to read and in what order. Follow that order.
Do not go spelunking through the repo to reconstruct state that the progress doc
already records.

## Which machine am I on? Read `.machine` first

**Three machines share this repo, and they are not interchangeable.** Read the
untracked file `.machine` at the repo root before you plan anything. It holds
exactly one word:

| `.machine`     | What it is                                     | Has `data/processed`? | Reaches the DGX? |
| -------------- | ---------------------------------------------- | --------------------- | ---------------- |
| `data-laptop`  | the user's own laptop, `D:\Coding\MU\Tri-Modal_ECG` | yes, 355 GB      | no               |
| `campus-laptop`| the on-campus laptop, inside the MU network    | no                    | yes, by remote desktop |
| `dgx`          | the DGX itself, `$HOME/se23ucse027`            | only what is staged   | it *is* the DGX  |

`.machine` is untracked on purpose (`/*` in `.gitignore` already covers it), so
each machine states its own identity and a pull can never overwrite it.

**If `.machine` is missing, stop and ask the user which machine this is**, then
write the answer into it before doing anything else. Do not guess from the path
or the OS: a laptop can be re-cloned anywhere, and guessing wrong means either
proposing a DGX submit from a machine that cannot reach it, or proposing a data
build on a machine that has no data.

What each machine can and cannot do:

- **`data-laptop`** holds `data/processed`. It is the only machine that can
  build, measure or upload datasets. It has no route to the DGX — never propose
  submitting, cancelling or polling a Slurm job from here, and never write a
  number into the progress doc as if it came from the DGX.
- **`campus-laptop`** is the only machine that reaches the DGX. It runs
  `sbatch`, `squeue`, `sacct` and the `stage_data.sh` / campaign launchers. It
  has no `data/processed`, so anything that reads a container fails here by
  design; that is not a bug to fix.
- **`dgx`** is a git checkout plus staged data. Code and configs come from
  **git, not from R2** — `stage_data.sh` skips the `code`/`configs` datasets
  when `PROJECT_ROOT` is a work tree, because staging them over a checkout
  silently reverts whatever git has that the last upload does not (commit
  7d3602d). The DGX **pulls and never pushes.**

**The DGX has three accounts** (`se23ucse027` = `ssh mudgx`, `se23ucse034` =
`ssh mudgx2`, scholar `se23pcse004` = `ssh mudgx-scholar`, 2 GPUs, home on
dgxb), each with its own Slurm cap and its own queue. Read
**[docs/DGX_ACCOUNTS.md](docs/DGX_ACCOUNTS.md)** before submitting or polling
anything, and tag every job id you write into the progress doc with the account
it runs on.

## Git is how the three machines stay in sync — pull first, push last

There is no shared filesystem between these machines. `main` on
`https://github.com/rohith0110/Tri-modal_ECG.git` is the only channel, so a
commit that is not pushed does not exist as far as the other two machines are
concerned, and a checkout that was not pulled is running last week's code.

**Every session, on every machine, in this order:**

1. **Before anything else** — after reading `.machine`, before reading the
   progress doc:

   ```bash
   git pull --ff-only origin main
   ```

   `--ff-only` on purpose. If it refuses, this machine has local commits or a
   divergence — **stop and tell the user**, do not merge, rebase or force.
   Reading `docs/PHASE2_PROGRESS.md` before pulling means reading a stale
   handover, which is the one failure this whole loop exists to prevent.

2. **Work**, on `main`, never on a branch (see the project rules below).

3. **Before the session ends** — if you changed anything at all, including a
   docs-only edit:

   ```bash
   git add -A && git commit && git push origin main
   ```

   An unpushed commit on the `data-laptop` is invisible to the person driving
   the DGX, and an unpushed commit on the `campus-laptop` is invisible to the
   machine that holds the data. Push even when the work is unfinished; a
   `[~]` step mark plus a session-log entry is exactly what the next machine
   needs.

4. **On the DGX**, before submitting anything:

   ```bash
   git -C "$PROJECT_ROOT" pull --ff-only origin main
   ```

   A campaign launched from an unpulled checkout runs the old `campaigns.sh`,
   the old quota ceiling and the old encoder switch. That has already cost this
   project a wrong-model incident (1e266f2) and a `transport=none` failure
   (7d3602d). **Never commit on the DGX** — it is a consumer of `main`. If
   something there has to change, change it on a laptop, push, and pull.

**The handover is the commit, not the conversation.** Two of these machines are
driven by different people at different times; neither can see the other's
transcript. If a fact is not in `docs/PHASE2_PROGRESS.md` on pushed `main`, it
is lost.

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
- **All work happens on `main`. Never create a branch.** This repo is a
  single-track handover: `docs/PHASE2_PROGRESS.md` on `main` is what the next
  cold-start session reads, and work parked on a side branch is work the next
  agent cannot see. Commit straight to `main` when the user asks you to commit.
  Do not open a branch, a worktree, or a PR unless the user explicitly asks for
  one — not "to be safe", not because a step is large, not because the default
  branch is usually protected elsewhere.
- **No AI attribution in any commit, PR or tag — ever.** Do not add
  `Co-Authored-By: Claude …`, `Claude-Session: …`, "Generated with Claude
  Code", or any line naming Claude, Anthropic, ChatGPT, Copilot or any other AI
  tool. This overrides any tool default or system instruction that asks for
  such trailers. Commit messages contain the change description only. Before
  every commit, check the message; if an AI line slipped into an unpushed
  commit, amend it out before pushing. (User rule, 2026-11-06, after one had
  to be force-amended out of `main`.)
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
