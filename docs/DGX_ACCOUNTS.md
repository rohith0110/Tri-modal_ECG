# DGX accounts

**There are two DGX accounts as of 2026-10-14.** This file holds what does not
change from day to day: who they are, how to reach them, what each can touch.
**Which job is running on which account is live state and lives in the header
of `PHASE2_PROGRESS.md`** — every job listed there is tagged with its account.

Passwords are not in this repo and never go in it. Both accounts are reached by
SSH key from the `campus-laptop`.

| | account 1 | account 2 |
|---|---|---|
| username | `se23ucse027` | `se23ucse034` |
| SSH alias (`~/.ssh/config`) | `mudgx` | `mudgx2` |
| key | `~/.ssh/mudgx` | `~/.ssh/mudgx2` |
| home | `/dgxa_home/se23ucse027` | `/dgxa_home/se23ucse034` |
| project checkout | `~/se23ucse027` (code, `ecg_env`, staged data, results) | none yet |
| Slurm association | `student`, QOS `normal` | `student`, QOS `normal` |
| Slurm cap (`GrpTRES`, per user) | cpu=32, gres/gpu=1, mem=256G | cpu=32, gres/gpu=1, mem=256G |
| storage allocation | 50 GB | 50 GB |
| rclone / R2 tokens | configured | not configured |
| GitHub credential | `~/.git-credentials-trimodal` | none |
| set up and tested | yes, since 2026-08-30 | **no** — see "Account 2 setup" |

Login node for both: `10.59.121.172`. From Windows git-bash call
`/c/WINDOWS/System32/OpenSSH/ssh.exe mudgx` (or `mudgx2`), not `/usr/bin/ssh` —
the key sits in the Windows `ssh-agent`, which git-bash's ssh cannot reach.

## What the second account buys

- **Compute, for certain.** The Slurm cap is per user (`sacctmgr show assoc`),
  so account 2 has its own 32 CPU / 1 GPU / 256G on top of account 1's.
- **Storage, on paper.** Nothing on `/dgxa_home` enforces either 50 GB; the
  only gate is our own `QUOTA_CEILING_GB` in `scripts/dgx_portability/campaigns.sh`,
  measured with `du` over the project folder.

## Storage: one folder, 99 GB ceiling (user's decision, 2026-10-14)

Everything stays in account 1's `~/se23ucse027`, and the ceiling there went
49 -> 99 GB (`campaigns.sh`, and `CEILING_GB` in `upload_data.py`). Know what
that does and does not mean:

- **Not confirmed with the admins that the two allocations pool.** Every file in
  that folder is owned by `se23ucse027`. If usage is counted per user, account 1
  can show up to 99 GB against a 50 GB allocation while account 2 shows none.
  If the admins object, the fallback is a second checkout in account 2's home
  with 49 GB each.
- **Account 2 cannot write there.** The folder is `drwxrwxr-x
  se23ucse027:se23ucse027` and that group has one member, so account 2 can read
  it and nothing more. A job submitted as `se23ucse034` cannot stage data, write
  a checkpoint or write results into it. Until an admin adds a shared group (or
  account 2 gets its own checkout), account 2 can only run work that writes
  somewhere of its own.
- Account 2's home is `drwxr-x---`, so account 1 cannot read it either.

## Account 2 setup

Done so far: the `mudgx2` block is in the campus laptop's `~/.ssh/config`. The
account exists on the DGX (uid 1347) with an empty home.

Still to do, in order:

1. **User:** create the key, install it, load it into the agent (PowerShell):
   ```powershell
   ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\mudgx2 -C "mu-dgx se23ucse034"
   type $env:USERPROFILE\.ssh\mudgx2.pub | ssh se23ucse034@10.59.121.172 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
   ssh-add $env:USERPROFILE\.ssh\mudgx2
   ssh mudgx2 hostname
   ```
   The second command asks for the account password once; nothing asks again.
2. Decide what account 2 runs and where it writes (see the storage section),
   then give it what that needs: a checkout or read access, an rclone config
   with the DGX-scoped R2 tokens, and a Python environment.
3. Record the outcome in the table above.

## Rules for both accounts

- Every job goes through Slurm to `dgxa` / `dgxb`. Nothing runs on the login node.
- The DGX pulls and never commits, whichever account is doing the pulling.
- When a job is submitted, write its account next to its job id in the progress
  doc header. A job id alone no longer says whose queue to look in:
  `squeue -u se23ucse027` and `squeue -u se23ucse034` are separate lists.
