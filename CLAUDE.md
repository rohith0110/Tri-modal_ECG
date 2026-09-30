# Tri-Modal ECG

See **[AGENTS.md](AGENTS.md)** — it is the full instruction set for this repo.

Short version, so it is never missed:

1. **Read `.machine` first.** Three machines share this repo: `data-laptop`
   (has `data/processed`, no DGX), `campus-laptop` (reaches the DGX, no data),
   `dgx` (git checkout + staged data). It is untracked, one word. If it is
   missing, ask the user which machine this is and write it.
2. **`git pull --ff-only origin main` before you read anything else** — no
   shared filesystem, so `main` is the only channel between the three machines
   and an unpulled checkout is last week's code. If it refuses, stop and say so.
3. **Read `docs/PHASE2_PROGRESS.md`, every session.** It holds the live
   project state and tells you which documents to read next.
4. **Update `docs/PHASE2_PROGRESS.md` before the session ends** — step marks,
   decisions, open questions, the header block, and a session-log entry — then
   **commit and push `main`.** An unpushed commit does not exist to the other
   two machines. The DGX pulls and never commits.
5. **Use `./ecg_env/Scripts/python.exe`**, never the system Python.
6. **Work on `main`.** Never branch — the progress doc on `main` is the
   handover, and a side branch hides the work from the next session.
