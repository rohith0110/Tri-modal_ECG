# DGX operator handover — running the campaigns from the on-campus laptop

Written 2026-08-30 (session 11). **Read `PHASE2_PROGRESS.md` first** — this file
is the *operational* companion: which machine does what, how to drive Slurm, and
what the rules are. The science lives in the progress doc and the spec.

---

## 1. Three machines, three jobs

| machine | holds | does |
| ------- | ----- | ---- |
| **Owner's laptop** (Windows, `D:\Coding\MU\Tri-Modal_ECG`) | **all 355 GB of MIMIC-derived data**, the venv that built it, the R2 `laptop-full` token | builds datasets, uploads to R2. **Data never leaves it** except as processed artifacts. |
| **On-campus laptop** | a git clone, Claude Code, SSH access to the DGX | drives the DGX. **No data, and it does not need any.** |
| **MU DGX** (`dgx-login01`, 10.59.121.172) | `~/se23ucse027/` — the checkout, staged data, outputs | runs the training. Reachable only inside the MU network. |

**The on-campus laptop cannot rebuild datasets and should never try.** Everything
it needs is already in `r2:trimodal-data` (601 objects, 226.4 GiB). Its job is
`git pull`, `ssh`, `sbatch`, and reading logs.

### Setting it up

```bash
git clone https://github.com/rohith0110/Tri-modal_ECG.git
cd Tri-modal_ECG
ssh se23ucse027@10.59.121.172      # confirm the DGX is reachable from this machine
```

### SSH without a password — do this before starting Claude Code

The agent drives the DGX over `ssh`, so it must never need a password typed at
it. Use a key plus an alias — the same shape as a multi-account GitHub
`~/.ssh/config`. **The password is entered exactly once, by a human, in step 2.**

macOS / Linux:

```bash
# 1. a key dedicated to this cluster -- not your GitHub key
ssh-keygen -t ed25519 -f ~/.ssh/mudgx -C "mu-dgx se23ucse027"

# 2. install the PUBLIC half on the DGX. The one and only password prompt.
ssh-copy-id -i ~/.ssh/mudgx.pub se23ucse027@10.59.121.172
```

**Windows PowerShell** — `~` is NOT expanded in `ssh-keygen -f`, and `.ssh` may
not exist yet, so it fails with
`Saving key "~/.ssh/mudgx" failed: No such file or directory`. Use full paths,
and there is no `ssh-copy-id`:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh" | Out-Null
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\mudgx" -C "mu-dgx se23ucse027"

type "$env:USERPROFILE\.ssh\mudgx.pub" | ssh se23ucse027@10.59.121.172 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

With a passphrase set, load the key into the agent once per boot, or every
command prompts for it:

```powershell
Get-Service ssh-agent | Set-Service -StartupType Manual
Start-Service ssh-agent
ssh-add "$env:USERPROFILE\.ssh\mudgx"
```

**Then use the Windows ssh binary, not git-bash's.** The key lives in the
*Windows* `ssh-agent`, which is reached over a named pipe; git-bash's
`/usr/bin/ssh` speaks the MSYS socket protocol and cannot see it. With a
passphrase-protected key, git-bash therefore offers the public key, cannot sign
with it, and dies with a message that looks exactly like the key was never
installed:

```
se23ucse027@10.59.121.172: Permission denied (publickey,password).
```

`ssh -vv` shows `Offering public key: ... explicit` right before the denial —
that combination means *this* problem, not a missing `authorized_keys`. Use
`/c/WINDOWS/System32/OpenSSH/ssh.exe` (or run from PowerShell) and it works
with no prompt.

Then the alias, in `~/.ssh/config` — on Windows that is
`C:\Users\<you>\.ssh\config`. `~` inside the file IS understood, because
ssh expands it rather than the shell:

```
Host mudgx
    HostName 10.59.121.172
    User se23ucse027
    IdentityFile ~/.ssh/mudgx
    IdentitiesOnly yes
    ServerAliveInterval 60
    ServerAliveCountMax 3
    # Reuse one authenticated connection for many short commands. An agent makes
    # dozens, and this turns each into a channel on an existing socket instead
    # of a fresh TCP + auth handshake. (Not supported on Windows -- omit there.)
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 10m
```

`ControlPath` needs `~/.ssh` to exist and be private: `chmod 700 ~/.ssh`.

Verify, then it is `mudgx` everywhere:

```bash
ssh mudgx 'hostname; whoami'      # must NOT prompt for anything
```

How the agent then works:

```bash
ssh mudgx 'cd ~/se23ucse027 && git pull'
ssh mudgx 'squeue -u $USER -o "%.8i %.12P %.2t %.10M %.10L %R"'
ssh mudgx 'sbatch --partition=gpu_student ~/se23ucse027/scripts/dgx_portability/slurm/campaign_01.sbatch'
```

**Rules for the key:**

* **Never** commit a private key. `~/.ssh/` is outside the repo; keep it there.
* If the laptop is not yours, give the key a passphrase and load it into
  `ssh-agent` for the session, so a copied key file is useless on its own.
* When the work is done, revoke it and delete both halves:

  ```bash
  ssh mudgx "sed -i '/mu-dgx se23ucse027/d' ~/.ssh/authorized_keys"
  rm ~/.ssh/mudgx ~/.ssh/mudgx.pub
  ```

* The account password stays in the password manager. If a command ever prompts
  for it, something is misconfigured — fix the key, do not type it.

The repo is **private and must stay that way**: tracked reports under `outputs/`
contain row-level MIMIC identifiers (study_id, subject_id, hadm_id, charttime),
which the PhysioNet DUA forbids publishing. Making it public again requires
scrubbing those files first — a deliberate job, not a toggle.

---

## 2. Where things are on the DGX

```
~/se23ucse027/          <- PROJECT_ROOT, and a git checkout of this repo
├── bin/rclone          <- the binary (git-ignored). Config is in ~/.config/rclone/
├── scripts/ config/ docs/    <- from git; `git pull` updates them
├── data/processed/     <- DATA_ROOT, staged per campaign from R2 (git-ignored)
├── outputs/            <- RESULTS_ROOT: checkpoints, metrics, logs (runs git-ignored)
└── .campaign_state/    <- which campaign / phase / pieces are resident
```

`$HOME` is `/dgxa_home/se23ucse027` **on every node** — local ext4 on dgxa, NFS
elsewhere. One copy serves everything, and a requeued job resumes wherever it
lands.

Two R2 remotes, least privilege:

* `r2` → `dgx-read-data`, **read-only** on `trimodal-data`. A write is denied, so
  nothing running on the cluster can damage the staged 226 GB.
* `r2-results` → `dgx-write-results`, with `no_check_bucket = true` (without it
  rclone issues `CreateBucket` first and a bucket-scoped token 403s).

---

## 3. The rules, and why each exists

1. **Never run computation on `dgx-login01`.** The facility asks this directly.
   Config edits, `git pull`, `sbatch`, `squeue` are fine; staging 40 GB or `du`
   over the tree is not.
2. **Everything pins `--nodelist=dgxa`.** Measured with `dd iflag=direct`: dgxa
   2.9 GB/s on local ext4, dgxb 105 MB/s over NFS — **28x**. The loader does tens
   of thousands of ~100 KB random reads per epoch, so a run on dgxb starves the
   GPU for days without ever failing. Cost: dgxa holds 2 of the 7 full A100s.
3. **`--mem` is mandatory.** These partitions default to the *whole node's*
   1,031,800 MB, so a job without it waits for a completely empty node — which
   never happens here — and Slurm blames the nodes: *"Nodes required for job are
   DOWN, DRAINED or reserved"*. All 14 `.sbatch` files set `--mem=64G`.
4. **Always name the GPU type; never `--gres=gpu:1`.** The A100s are
   MIG-partitioned into `a100`, `a100_4g.20gb`, `a100_3g.20gb`,
   `a100_2g.10gb`, `a100_1g.5gb`. An untyped request matches any of them,
   including a **5 GB** slice that OOMs hours in. The full cards are **40 GB**,
   not 80. **But a full card is not always what a run needs** — see §3a.

   Amended 2026-08-30 (session 12). The original rule said `a100:1` always.
   That is what a *large* run needs, and asking for it unconditionally is what
   put a 5-minute smoke job three weeks deep in the queue.
5. **50 GB, and not one byte more.** `quota -s` reports *no* quota — the limit is
   policy on a 14 TB filesystem with 6.1 TB free. `used_gb()` / `require_fit()`
   is the only thing enforcing it. `/tmp` was deliberately removed from the
   `DATA_ROOT` candidate list for this reason; do not put it back.
6. **Stage inside the job.** `_campaign_body.sh` stages, trains, evicts. Do not
   pre-stage from the login node.

---

## 3a. Which GPU to ask for — measured 2026-08-30

**The full 40 GB A100s are the scarce resource on this cluster; the MIG slices
are not.** On 2026-08-30 dgxa's two full cards were both held by `gpu_faculty`
jobs with **14 and 19 days** left, and every one of dgxb's five was taken too.
Slurm's own estimate for a `--gres=gpu:a100:1 --nodelist=dgxa` request was
**three weeks out**. In the same minute, a `a100_4g.20gb` slice on dgxa
allocated in about twenty seconds.

What dgxa held free that day:

| slice | free / total |
| ----- | ------------ |
| `a100` (40 GB) | **0 / 2** |
| `a100_3g.20gb` | 0 / 2 |
| `a100_4g.20gb` | 1 / 2 |
| `a100_2g.10gb` | 5 / 5 |
| `a100_1g.5gb`  | 16 / 16 |

So the rule is **fit first, card second**:

1. **Default: a MIG slice on dgxa.** `--gres=gpu:a100_4g.20gb:1` (20 GB) or
   `a100_3g.20gb:1`. Keeps rule 2's 2.9 GB/s local ext4, which is the thing
   that actually decides whether the loader starves the GPU. Available today.
2. **If the run genuinely needs more than 20 GB: a full card on dgxb.**
   `--nodelist=dgxb --gres=gpu:a100:1`. dgxb is the *only* place a full card
   is realistically obtainable while faculty hold dgxa's two for weeks. The
   cost is real and measured — 105 MB/s NFS against dgxa's 2.9 GB/s, **28x** —
   so this is for runs that are memory-bound, not I/O-bound: small dataset,
   large model. Weigh it per campaign; a big-data campaign on dgxb starves for
   days without ever failing.
3. **Waiting for a full card on dgxa** is the third option, not the first. It
   is right only when a run needs both 40 GB and the fast disk, and then the
   queue wait is part of the cost of the run.

**How to know which one a run needs.** As of 2026-08-30 the trainer records
`peak_gpu_gb` in every epoch's row of `train_log.jsonl`, so the answer is
measured rather than guessed:

```bash
grep -o '"peak_gpu_gb": [0-9.]*' outputs/model_runs/<run>/train_log.jsonl | sort -u
```

Read it off the first campaign of each family, then size every sibling run from
it. Config batch sizes as they stand: signal resnet18_1d 256 (128 for A4/A6),
image resnet50 64 at 224x672 / 384x512, text BERT 32 at 512 tokens, fusion and
cosine 16. Precision is `bf16` on A100 (`decision_phase2.yaml` §5), and MIG
slices support bf16 exactly as the full card does. The tier to watch is
`image_resnet50` at 384x512 x 64 -- that is the one nobody should assert fits
20 GB without reading `peak_gpu_gb` first.

**`--mem` is unrelated to all of this.** That is host RAM, and rule 3 still
stands: always pass it, on every job, whatever GPU you asked for.

---

## 3b. One GPU. That is the whole budget — measured 2026-08-30

```
$ sacctmgr -n show assoc where user=$USER format=User,Account,GrpTRES
se23ucse027   student   cpu=32,gres/gpu=1,mem=256G
```

**This account may hold exactly ONE GPU at a time, of any kind.** A MIG slice
counts as `gres/gpu=1` exactly as a full A100 does. A second GPU job pends on
`AssocGrpGRES` no matter how idle the cluster is — five free slices on dgxa
made no difference. Running campaign 1 as six shards on six slices was tried on
2026-08-30 and refused by the scheduler.

What this means, and it is the single most important operational fact here:

* **Every one of the 312 runs is sequential.** The campaign schedule's parts
  cannot overlap. At ~28 min/epoch for a BioClinicalBERT run on a 20 GB slice,
  campaign 1 alone is 5–9 days.
* **Sharding is still worth doing**, just not for parallelism. `TRIMODAL_TASKS`
  splits a campaign into per-task jobs that Slurm starts back to back as the
  cap frees up: each is a smaller resumable unit, none risks a wall-clock
  timeout the way one 36-run job would, and a failure costs one task rather
  than the campaign.
* **Ask the facility to raise `gres/gpu`.** It is a one-line `sacctmgr` change
  on their side and the only thing that makes the remaining campaigns tractable
  on the planned calendar. Everything else here is working around it.

### Picking the node once you know you get one GPU

Since only one job runs at a time, the only question is which GPU that job
should sit on, and the answer is **whichever is fastest for the work at hand**:

| campaign kind | node | why |
| ------------- | ---- | --- |
| **text** (campaign 1) | **dgxb full `a100:1`** when one is free | `task_dataset.py:334` reads the text parquet ONCE into an in-memory array and tokenises from RAM. There is no per-sample disk read, so rule 2's measured 28x NFS penalty simply does not apply. A full card is ~1.75x a `4g.20gb` slice. |
| **signals / images** | **dgxa**, slice or card | tens of thousands of ~100 KB random reads per epoch. This is exactly what rule 2 is about; dgxb would starve the GPU. |

Rule 2 still stands — it was measured, and it is right about the loader. It is
about *where the bytes are read from*, so it binds only on campaigns that
actually stream bytes per sample.

---

## 3c. Nothing may depend on the operator's laptop

Slurm jobs survive everything on this end: closing Claude Code, closing the
terminal, shutting the campus laptop, leaving the network. Jobs run, queued
jobs start, and with `gres/gpu=1` each shard begins as the previous one ends,
unattended.

**Anything the agent runs locally does not.** A polling loop on the laptop that
watches a job and reacts to it dies with the session, silently. If a piece of
automation has to outlive the session, it belongs on the cluster as a batch
job.

`slurm/swap_watcher.sbatch` is the worked example. It moves the running A1
shard from a dgxa MIG slice to a full A100 on dgxb, at an epoch boundary, once
a card frees:

```bash
cd ~/se23ucse027 && sbatch scripts/dgx_portability/slurm/swap_watcher.sbatch
```

Two properties make it safe to leave running:

* **It requests no GPU** — `cpu_student`, 1 CPU, 1 GB. The account's cap is one
  GPU total, so a watcher that asked for one would compete with the training it
  is supposed to be helping.
* **It fails back.** The cap also means the old job must be cancelled before the
  new one can start, so there is a window where another user can take the card.
  `swap_to_dgxb.sh` resubmits to a dgxa slice if the dgxb submit does not take,
  so the worst case is where we started, minus one partial epoch. It never
  leaves the campaign holding no GPU.

The same shape applies to any future "watch for X then do Y": no GPU, a real
fallback, and a batch job rather than a laptop.

---

## 4. Slurm, practically

Partitions available to this account: `cpu_student`, `gpu_student` — **7-day**
limit. `*_faculty` and `*_scholar` get 30 days and outrank us; jobs of 15, 5 and
4 days were running during the survey. **Queue wait, not GPU speed, is the
binding constraint on 312 runs.**

### An interactive shell (setup and debugging)

```bash
srun --partition=cpu_student --nodelist=dgxa --time=04:00:00 \
     --ntasks=1 --cpus-per-task=4 --mem=8G --pty bash
```

Take the allocation **first**, then work inside it. `--time` is a hard kill: at
the limit you get

```
slurmstepd: error: *** STEP 22327.0 ON dgxa CANCELLED AT ... DUE TO TIME LIMIT ***
```

and you are dropped back on the login node. Nothing is corrupted — every staging
step is resumable and re-verifies checksums. Just re-allocate.

### How much time is left on the current allocation

```bash
squeue -u $USER -o "%.8i %.12P %.9j %.2t %.10M %.10L %R"
#                                         ^elapsed   ^TIME LEFT
scontrol show job <JOBID> | grep -E "RunTime|TimeLimit|StartTime|EndTime"
```

`%L` is the answer; `scontrol` also gives a wall-clock `EndTime`.

### Submitting a campaign

```bash
cd ~/se23ucse027
sbatch --partition=gpu_student scripts/dgx_portability/slurm/campaign_01.sbatch
```

Partition is passed at submit time on purpose; everything else (`--mem`,
`--gres=gpu:a100:1`, `--nodelist=dgxa`, `--time`, `--requeue`) lives in the file.
**The `--gres` in the file is the large-run default and is very often the wrong
thing to wait for** — read §3a and override it with a MIG slice unless the run
actually needs 40 GB:

```bash
sbatch --partition=gpu_student --gres=gpu:a100_4g.20gb:1        scripts/dgx_portability/slurm/campaign_01.sbatch
```

Override without editing the file:

```bash
sbatch --partition=gpu_student --gres=gpu:a100:2 --mem=128G \
       scripts/dgx_portability/slurm/campaign_07.sbatch
```

### Watching it

```bash
squeue -u $USER                    # PD = pending, R = running
squeue -u $USER --start            # estimated start time while pending
tail -f trimodal_c1_<jobid>.out
scancel <JOBID>
sacct -u $USER --format=JobID,JobName%22,State,Elapsed,MaxRSS,ExitCode
sinfo -o "%P %a %l %D %t %N %G"    # what the cluster looks like right now
```

`--requeue` with `--signal=B:TERM@300` is the resume path: the trainer gets five
minutes' warning, writes `checkpoint_last.pt`, exits 0, and Slurm requeues it.

### Storage check (compute node only, per the facility's own instruction)

```bash
du -sh ~/se23ucse027
```

---

## 5. State as of 2026-08-30, 15:00 IST (session 12)

**Step 6 DONE** — 601 objects, 226.4 GiB in `r2:trimodal-data`.
**Step 7 DONE** — environment surveyed; five launcher bugs found and fixed.
**Step 8 — venv and smoke done; campaign 1 is the next thing to submit.**

Done:

* rclone installed; both remotes verified from the DGX, including that a write to
  the read-only data token is correctly denied.
* `~/se23ucse027` is a clean git checkout **plus** staged data.
* `stage_data.sh 1` run three times, every file checksum-verified, **zero
  mismatches**: `campaign 1 staged. Used: 1.23 GB of 45 GB ceiling.` (The
  ceiling is now 49 — see rule 5 and the note below.)
* Open question 4 **ANSWERED: ONLINE** — a compute node reaches the internet, so
  §8.2 rule 2's mid-epoch piece fetch is available to campaigns 6, 8 and 9.
  Re-confirmed on 2026-08-30 when BioClinicalBERT downloaded onto dgxa mid-run.
* **The venv is built and verified** (job 22331). Python 3.10.12,
  **torch 2.6.0+cu124** against driver 550.144.03, all 17 imports resolving.
  Exact versions are in `PHASE2_PROGRESS.md`, session 12 — nothing in this repo
  pins them, so that log is the only record.
  `HF_HOME` is appended to `ecg_env/bin/activate` and points at
  `PROJECT_ROOT/.cache/huggingface`, so the model cache is counted by
  `used_gb()` instead of hiding in `$HOME`.
* **The venv costs 5.7 GB**, not the ~3 GB budgeted, and `used_gb()` counts it.
  That is why the ceiling moved **45 -> 49 GB**, in both `campaigns.sh` and
  `decision_phase2.yaml`.
* **The smoke test ran** (job 22333, on a `a100_4g.20gb` slice, 8m43s):
  **26 PASS / 30 FAIL**, and all 30 failures are `FileNotFoundError` on signal
  and image files that campaign 1 does not stage. All 12 text tiers train and
  eval; `gates` and the preemption handler pass. Scope, not breakage — see
  below.

Not done, in order:

1. **Campaign 1 for real.** It is `text_models`, and its staged data is already
   on the node.

   ```bash
   cd ~/se23ucse027
   sbatch --partition=gpu_student --gres=gpu:a100_4g.20gb:1           scripts/dgx_portability/slurm/campaign_01.sbatch
   ```

   The `--gres` override is deliberate — see §3a. The `.sbatch` still says
   `a100:1`, which is right for whichever campaigns turn out to need it, and
   wrong to wait three weeks for when a text campaign does not.
2. **Read `peak_gpu_gb`** out of `outputs/model_runs/<run>/train_log.jsonl`
   once campaign 1 has an epoch on the board, and size every later campaign of
   each family from a measured number rather than an estimate.
3. **Clean up after a smoke run.** `smoke_test.py` never calls
   `push_results.sh`, so it leaves every checkpoint it wrote on disk:
   **~20 GB under `outputs/model_runs/_dev/`** after a full-matrix run (each
   text run writes `checkpoint_best.pt` + `checkpoint_last.pt` at ~1.2 GB
   each). `used_gb()` counts all of it. Delete it once the run's PASS/FAIL
   record is in hand -- it is regenerable and, by the smoke test's own
   docstring, proves nothing about the numbers:

   ```bash
   rm -rf ~/se23ucse027/outputs/model_runs/_dev
   ```

   A real campaign does not have this problem: `_campaign_body.sh` calls
   `push_results.sh` after every run, which pushes `checkpoint_best.pt` and
   deletes both local checkpoints once the push verifies (§8.1).
4. **Smoke the other families in front of the campaign that stages their data.**
   `smoke_test.py` defaults to all six; scope it with
   `--tiers text_tfidf text_bert` for a text campaign, `--tiers signal` when
   signals are resident, and so on. Running the default on a node staged for one
   campaign will always fail the other five families on missing files.

### Two loose ends

* **8 code and 3 config files still transfer on a repeat `stage_data.sh 1`**,
  where a git checkout and R2 should be byte-identical after the LF
  normalisation. Harmless — every file verifies — but unexplained, and
  `--checksum` meaning "nothing changed" is worth being able to trust. Find out
  which they are before relying on it:

  ```bash
  cd ~/se23ucse027 && git status --short
  rclone check r2:trimodal-data/code ~/se23ucse027 --checksum --one-way 2>&1 | head -20
  ```

* **Non-finite samples in `raw_12lead`** (~1.6 % of records). The cutter refuses
  them under `--int16` and raw ships float32, but **nothing on the model path
  sanitises them** — campaign 9 will train on them as they are. Known and
  recorded, not yet decided.

---

## 6. Prompt to start a Claude Code session on the on-campus laptop

Paste this:

> I'm on the on-campus laptop that can reach the MU DGX. The Tri-Modal ECG repo
> is cloned here; **the datasets are NOT on this machine and never will be** —
> they live on the owner's laptop and in `r2:trimodal-data`. My job from here is
> to drive the DGX over SSH.
>
> Read `docs/PHASE2_PROGRESS.md` first, then `docs/DGX_OPERATOR_HANDOVER.md`.
> Run `git pull` before anything — and pull on the DGX too.
>
> We are mid-Step 8. Campaign 1 is staged and checksum-verified on the DGX at
> `~/se23ucse027`, the venv is built (torch 2.6.0+cu124, Python 3.10.12) and the
> smoke test has run. Next: submit campaign 1, then read `peak_gpu_gb` out of
> its `train_log.jsonl` to size the later campaigns.
>
> Rules that are not negotiable — all measured, all explained in the handover:
> work inside an `srun` allocation on **dgxa**, never on the login node; every
> job needs `--mem` or it pends forever; always name the GPU type, never
> `gpu:1` — and read §3a before asking for a full `a100:1`, because both of
> dgxa's are held by faculty for weeks and a MIG slice allocates in seconds;
> stay inside 50 GB even though no quota is enforced; the repo stays private
> because tracked reports carry MIMIC identifiers.
>
> SSH is key-based and aliased: `ssh mudgx '<command>'` — no password, no
> prompts. If anything asks for a password, stop and tell me rather than
> working around it. Tell me what you find before changing anything on the DGX.

**On the DGX, first thing every session:**

```bash
cd ~/se23ucse027 && git pull
```

**On the owner's laptop, whenever code changes:** re-upload so the R2 fallback
matches git, or the next stage will overwrite the checkout again.

```bash
./ecg_env/Scripts/python.exe scripts/dgx_portability/upload_data.py --dataset code configs
```
