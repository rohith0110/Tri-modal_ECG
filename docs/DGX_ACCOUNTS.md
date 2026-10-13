# DGX accounts

**There are two DGX accounts as of 2026-10-14, and they run as two separate
workflows in parallel.** This file holds what does not change from day to day:
who they are, how to reach them, what each owns. **Which job is running on
which account is live state and lives in the header of `PHASE2_PROGRESS.md`** —
every job listed there is tagged with its account.

Passwords are not in this repo and never go in it. Both accounts are reached by
SSH key from the `campus-laptop`.

| | account 1 | account 2 |
|---|---|---|
| username | `se23ucse027` | `se23ucse034` |
| SSH alias (`~/.ssh/config`) | `mudgx` | `mudgx2` |
| key | `~/.ssh/mudgx` | `~/.ssh/mudgx2` |
| home | `/dgxa_home/se23ucse027` | `/dgxa_home/se23ucse034` |
| project checkout | `~/se23ucse027` | `~/se23ucse027` (same folder name, its own home) |
| Python env | `~/se23ucse027/ecg_env` | **symlink** to account 1's `ecg_env` (read-only use) |
| quota ceiling | 99 GB (see below) | 49 GB, from `.account_env` |
| results in R2 | `r2-results:trimodal-results/` | `r2-results:trimodal-results/acct2/`, from `.account_env` |
| Slurm association | `student`, QOS `normal` | `student`, QOS `normal` |
| Slurm cap (`GrpTRES`, per user) | cpu=32, gres/gpu=1, mem=256G | cpu=32, gres/gpu=1, mem=256G |
| rclone remotes | `r2`, `r2-results` | same config, copied 2026-10-14 |
| GitHub credential | `~/.git-credentials-trimodal` (empty since 10-05) | none — pulls from account 1's checkout |

Login node for both: `10.59.121.172`. From Windows git-bash call
`/c/WINDOWS/System32/OpenSSH/ssh.exe mudgx` (or `mudgx2`), not `/usr/bin/ssh` —
the keys sit in the Windows `ssh-agent`, which git-bash's ssh cannot reach.

## How the two stay apart

- **Campaigns are split, never shared.** A campaign belongs to one account from
  its first run to its last eval. The split in force is in the progress doc
  header. Two accounts training the same campaign would both write
  `model_runs/<task>/<tier>/seed_<n>` and the second would silently win.
- **Folders.** Each account stages data, writes checkpoints and writes results
  in its own home. Account 2 can *read* account 1's folder (`drwxrwxr-x`, group
  of one) and cannot write it; account 1 cannot read account 2's home
  (`drwxr-x---`). That is why account 2 has its own checkout rather than
  sharing one.
- **`.account_env`.** An untracked file at the root of a checkout, sourced by
  `scripts/dgx_portability/campaigns.sh`, holding whatever differs between the
  accounts. Account 1 has none and gets the defaults. Account 2's is:
  ```bash
  export QUOTA_TOTAL_GB=50
  export QUOTA_CEILING_GB=49
  export R2_RESULTS=r2-results:trimodal-results/acct2
  ```
- **R2 results.** Account 2 pushes everything under `acct2/`. `results/<task>.csv`
  holds one task's rows for every tier, so two accounts evaluating different
  tiers of the same task into one path would overwrite each other's file on
  every push. **Merging `acct2/` into the root is a step still to be written**
  — `model_runs/` is a plain copy (the run paths are disjoint), but the
  per-task CSVs need their rows combined, and campaigns 11 and 14 stage
  `results` from the root, so it has to happen before either of those.
- **GPUs.** Each account may hold one GPU slice. Slurm gives each job its own
  slice, so the two never share a device; the only contention is for a free
  `a100_4g.20gb` slice (2 on dgxa, 1 on dgxb), where one of them queues.
  `campaign_chain.sbatch` pins no node for that reason.
- **Code.** Account 1's checkout gets `main` by `git pull`, or by `git bundle`
  while its token is dead. Account 2 pulls from account 1's checkout, which it
  can read: `git pull --ff-only acct1 main` (the remote `acct1` is already set).
  Update account 1 first.

## Storage

Nothing on `/dgxa_home` enforces a quota; the only gate is our own
`QUOTA_CEILING_GB`, measured with `du` over the project folder.

- **Account 2: 49 GB**, its own allocation. `ecg_env` is a symlink, so the
  5.7 GB venv is not counted there.
- **Account 1: 99 GB** (user's decision, 2026-10-14, made when the plan was one
  shared folder). **Not confirmed with the admins**, and now that account 2
  stages its own data, account 1 above 50 GB plus account 2's 49 GB is more
  than the two allocations together. Campaign 2 peaks near 52 GB on account 1
  (data 40.5 + outputs and venv). If the admins object, set
  `QUOTA_CEILING_GB=49` in an `.account_env` on account 1 — campaign 2 then
  no longer fits with its test split and needs rethinking.

## Rules for both accounts

- Every job goes through Slurm to `dgxa` / `dgxb`. Nothing runs on the login node.
- The DGX pulls and never commits, whichever account is doing the pulling.
- When a job is submitted, write its account next to its job id in the progress
  doc header. A job id alone no longer says whose queue to look in:
  `squeue -u se23ucse027` and `squeue -u se23ucse034` are separate lists.
- Do not submit a campaign on one account that the header assigns to the other.
