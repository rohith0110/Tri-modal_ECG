# DGX accounts

**There are three DGX accounts as of 2026-10-30.** Accounts 1 and 2 are
student accounts (since 2026-10-14). Account 3 is a **scholar** account, added
2026-10-30, with a bigger Slurm cap and its home on `dgxb`, not `dgxa`. Each
runs as its own workflow in parallel. This file holds what does not change from
day to day: who they are, how to reach them, what each owns. **Which job is
running on which account is live state and lives in the header of
`PHASE2_PROGRESS.md`** — every job listed there is tagged with its account.

Passwords are not in this repo and never go in it. All three accounts are
reached by SSH key from the `campus-laptop`.

| | account 1 | account 2 | account 3 (scholar) |
|---|---|---|---|
| username | `se23ucse027` | `se23ucse034` | `se23pcse004` |
| SSH alias (`~/.ssh/config`) | `mudgx` | `mudgx2` | `mudgx-scholar` |
| key | `~/.ssh/mudgx` | `~/.ssh/mudgx2` | `~/.ssh/mudgx_scholar` |
| home | `/dgxa_home/se23ucse027` | `/dgxa_home/se23ucse034` | **`/dgxb_home/se23pcse004`**: local disk on dgxb, NFS on dgxa |
| project checkout | `~/se23ucse027` | `~/se23ucse027` (same folder name, its own home) | `~/se23ucse027` (same folder name, its own home) |
| Python env | `~/se23ucse027/ecg_env` | **symlink** to account 1's `ecg_env` (read-only use) | **symlink** to account 1's `ecg_env`; `bin/` (rclone) symlinked too |
| quota ceiling | 49 GiB (code default) | 49 GiB, from `.account_env` | **held at 1 GiB** in `.account_env` until storage is settled (see Storage) |
| results in R2 | `r2-results:trimodal-results/` | `r2-results:trimodal-results/acct2/`, from `.account_env` | `r2-results:trimodal-results/acct3/`, from `.account_env` |
| Slurm association | `student`, QOS `normal` | `student`, QOS `normal` | **`scholar`**, QOS `normal` |
| Slurm cap (`GrpTRES`, per user) | cpu=32, gres/gpu=1, mem=256G | cpu=32, gres/gpu=1, mem=256G | **cpu=48, gres/gpu=2, mem=384G** |
| partitions | `gpu_student` / `cpu_student` (7-day limit, priority 50) | same | **`gpu_scholar` / `cpu_scholar` (30-day limit, priority 80)**; `gpu_student` also accepts it |
| rclone remotes | `r2`, `r2-results` | same config, copied 2026-10-14 | same config, copied 2026-10-30 |
| GitHub credential | `~/.git-credentials-trimodal` (fine-grained, read-only, renewed 2026-10-27) | none — pulls from account 1's checkout | none — pulls from account 1's checkout (remote `acct1`) |

Login node for all three: `10.59.121.172`. From Windows git-bash call
`/c/WINDOWS/System32/OpenSSH/ssh.exe mudgx` (or `mudgx2`, `mudgx-scholar`), not
`/usr/bin/ssh` — the keys sit in the Windows `ssh-agent`, which git-bash's ssh
cannot reach.

## Account 3 (scholar), measured 2026-10-30

- **GPU cap tested, not only read from `sacctmgr`:** a job asking for
  `gpu:a100_1g.5gb:2` ran (29717, both devices visible). One asking for 3
  pended with `AssocGrpGRES` (29718, cancelled). So the cap is **2 GPUs at a
  time, any size**: two chain links, or one link with 2 GPUs. A `gpu_student`
  job also ran (29719).
- **End-to-end test (29720, `gpu_scholar`, dgxb):** `.account_env` +
  `campaigns.sh` resolve
  `DATA_ROOT=/dgxb_home/se23pcse004/se23ucse027/data/processed` and
  `R2_RESULTS=r2-results:trimodal-results/acct3`. Account 1's `ecg_env` runs
  torch 2.6.0+cu124 on CUDA, and `rclone lsf r2:trimodal-data` lists. The test
  scripts are in `~/acct_test`.
- **Run it on dgxb.** dgxb serves this home, so the loaders read local disk
  there and NFS on dgxa. That is the reverse of accounts 1 and 2
  (DGX_OPERATOR_HANDOVER §2 measured the NFS side at 28x slower). Pin
  `--nodelist=dgxb`. dgxb has 5 full A100s. The env symlink is read from dgxa
  over NFS, which only costs start-up time.
- **Not a clean account.** The home already holds ~124G of other work
  (`aamas` 99G, `DQUERY`, `detectron*`, ...). It is not ours: never touch it.
  The user gave the storage limit as 100 GB. That is already exceeded, so how
  much the project may use is **open** (see Storage). `QUOTA_CEILING_GB=1`
  makes every campaign fail `will_fit` until this is settled, so no chain can
  stage data by accident.
- **Before account 3 runs a campaign:** settle the ceiling.
  `merge_acct2_results.py` knows only `acct2/` and must learn `acct3/` before
  campaigns 11/14. Submit with `--partition=gpu_scholar --nodelist=dgxb`.

## How the accounts stay apart

Written for accounts 1 and 2. Account 3 follows the same rules, with `acct3/`
in place of `acct2/`; its chain claims campaigns as `se23pcse004`.

- **Campaigns are never shared, and are taken on availability** (since
  2026-10-27). A campaign belongs to one account from its first run to its last
  eval: two accounts training the same campaign would both write
  `model_runs/<task>/<tier>/seed_<n>` and the second would silently win. Which
  account owns which is no longer decided up front: both chains walk the same
  `CAMPAIGNS` list and claim a campaign in
  `r2-results:trimodal-results/claims/campaign_<n>` (one line, `<user>
  <running|done> <utc>`) before they start it. Read the claims with
  `rclone lsf` / `rclone cat` on that path. To hand a campaign over by hand,
  edit its claim file — never run one that the other account claims.
- **Folders.** Each account stages data, writes checkpoints and writes results
  in its own home. Account 2 can *read* account 1's folder (`drwxrwxr-x`, group
  of one) and cannot write it; account 1 cannot read account 2's home
  (`drwxr-x---`). That is why account 2 has its own checkout rather than
  sharing one.
- **`.account_env`.** An untracked file at the root of a checkout, sourced by
  `scripts/dgx_portability/campaigns.sh`, holding whatever differs between the
  accounts. Account 1's holds only `export R2_RESULTS=r2-results:trimodal-results`
  (added 2026-10-27: without it chain jobs pushed through the read-only `r2`
  token for a week). Account 2's is:
  ```bash
  export QUOTA_TOTAL_GB=50
  export QUOTA_CEILING_GB=49
  export R2_RESULTS=r2-results:trimodal-results/acct2
  ```
- **R2 results.** Account 2 pushes everything under `acct2/`. `results/<task>.csv`
  holds one task's rows for every tier, so two accounts evaluating different
  tiers of the same task into one path would overwrite each other's file on
  every push. Campaigns 11 and 14 stage `results` from the root, so before
  either: `ecg_env/bin/python scripts/dgx_portability/merge_acct2_results.py`
  (dry run), then again with `--apply`, from account 1's login node. It copies
  `model_runs/` (disjoint), unions the per-task CSVs and extras by arch tier
  (and stops if a tier is on both sides), and stores account 2's threshold
  audit beside account 1's as `threshold_audit.acct2.md`.
- **GPUs.** Each account may hold one GPU slice. Slurm gives each job its own
  slice, so the two never share a device; the only contention is for a free
  `a100_4g.20gb` slice (2 on dgxa, 1 on dgxb), where one of them queues.
  `campaign_chain.sbatch` pins no node for that reason.
- **Code.** Account 1's checkout gets `main` by `git pull`, or by `git bundle`
  while its token is dead. Account 2 pulls from account 1's checkout, which it
  can read: `git pull --ff-only acct1 main` (the remote `acct1` is already set).
  Update account 1 first.

## Storage

**Account 3:** the limit is 100 GB (user, 2026-10-30), but the home already
holds ~124G of other work. `/dgxb_home` is 93 % full (999G free). There is no
`quota` command, and nothing we measured enforces the limit. The ceiling stays
at 1 GiB until the user decides.

Nothing on `/dgxa_home` enforces a quota; the only gate is our own
`QUOTA_CEILING_GB`, measured with `du` over the project folder.

**Each account has 50 GB, and the two do not pool (user, 2026-10-27).** Both
gate at a 49 ceiling, in GiB — the unit `used_gb` and `du -sh` report.
`will_fit` converts the campaign table's decimal GB to GiB before comparing.

- **Account 2:** base (no staged data) about 3.0 GiB. `ecg_env` is a symlink,
  so the 5.7 GB venv is not counted there.
- **Account 1:** base about 8.6 GiB — the real venv, the HuggingFace cache and
  outputs. Every campaign fits at an empty data root; campaign 7 leaves only
  0.8 GiB, which is under the chain's 2 GB claim headroom, so account 2 takes it.
- The 99 GB ceiling on account 1 (2026-10-14 to 10-27) was the user's call when
  the plan was one shared folder; it is gone.

## Rules for all accounts

- Every job goes through Slurm to `dgxa` / `dgxb`. Nothing runs on the login node.
- The DGX pulls and never commits, whichever account is doing the pulling.
- When a job is submitted, write its account next to its job id in the progress
  doc header. A job id alone no longer says whose queue to look in:
  `squeue -u se23ucse027`, `squeue -u se23ucse034` and `squeue -u se23pcse004`
  are separate lists.
- Do not submit a campaign on one account that the header assigns to the other.
