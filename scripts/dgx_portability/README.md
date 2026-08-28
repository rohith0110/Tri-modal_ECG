<!-- Scaffolded by Stage P2.0, 2026-08-26. See docs/PHASE2_SOURCE_OF_TRUTH.md section 3. -->

# `scripts/dgx_portability/` - campaign staging and job submission

These are the REAL launchers, not templates (spec section 8.2). Empty until
Step 4 of `docs/PHASE2_EXECUTION_PLAN_DGX.md`.

```
stage_data.sh              # pull one campaign's data, verify checksums, refuse if it won't fit
evict_data.sh              # wipe the current campaign's data after results are pushed
push_results.sh            # best checkpoint + predictions + logs off-node, then delete local
make_chunks.py             # cut oversized modalities into aligned i.i.d. pieces
slurm/campaign_<n>.sbatch  # one submission file per campaign
```

## The two rules that bind the science, not just the operations

1. **Chunking is i.i.d. and modality-aligned.** When a campaign exceeds the
   quota, the TRAINING split is cut into equal pieces keyed by a hash of
   `study_id` - never by subject, admission, label, cart_id or time. Signal and
   image pieces use the SAME key, so piece *k* of each modality covers the same
   studies. Each piece is a fair miniature of the split.
2. **Chunks cycle WITHIN each epoch, never across epochs.** Every epoch visits
   every piece in a reshuffled order, with a shuffle buffer inside each piece;
   two pieces are resident at a time (train on *k*, prefetch *k+1*, evict
   *k-1*). Training to convergence on piece 1 and then moving to piece 2 is
   **forbidden** - that is block-local SGD and it catastrophically forgets.
   The block-shuffled sampling that IS used is recorded as a documented
   deviation in `config/decision_phase2.yaml` and disclosed in the
   supplementary.

## Quota rules

- 50 GB total, shared across env, data, checkpoints and logs.
- A launcher checks free quota **before** submitting and refuses if the
  campaign will not fit under 45 GB. A refusal beats a job that dies at 90 %.
- Check quota on a **compute** node, never the login node:
  `du -sh "$PWD"`
- Resident checkpoints <= 5 GB; at most 3 concurrent fusion jobs.

## Recovery

- A requeued job resumes from `checkpoint_last.pt`; if the file is gone it is
  re-pulled from `r2:trimodal-results`.
- No Phase 2 artifact may exist only on the DGX. The account expires
  2026-12-31 and data is purged 10 days later.
- `rclone lsd r2:` returns 403 by design - the tokens are bucket-scoped.
  Always name the bucket: `rclone lsd r2:trimodal-data`.

## Never

Credentials (DGX password, R2 keys/secrets) live in the password manager and in
the local rclone config only - never in this repo, any doc, any script or any
commit. Raw MIMIC never leaves the laptop and never enters the release package.

---

## Written at Step 4 (2026-08-28)

```
campaigns.sh          # campaign table + shared helpers (quota, transport, roots)
campaign_runs.py      # campaign number -> its <task> <arch_tier> <seed> run list
make_chunks.py        # plan / cut / verify the i.i.d. modality-aligned pieces
stage_data.sh         # refuse-then-pull one campaign, verify checksums
evict_data.sh         # wipe a campaign, a piece set, or everything
push_results.sh       # push a finished run, verify, then delete its checkpoints
slurm/_campaign_body.sh    # shared body: detect env, stage, run, push
slurm/campaign_NN.sbatch   # 11 thin per-campaign submission files
```

### Everything the DGX survey (Step 7) has not answered yet

Nothing here assumes a verified machine. Each unknown is **detected**, with a
fallback, rather than hard-coded:

| Unknown | What the scripts do |
| --- | --- |
| Outbound internet? | `transport()` picks `rclone` only if `curl` reaches the network; otherwise `rclone-offline`, or a plain directory via `TRIMODAL_SOURCE` (the courier-a-drive fallback), or a clear refusal naming both options. |
| Node-local scratch? | `resolve_data_root()` tries `$SCRATCH`, `/scratch/$USER`, `/raid/$USER`, `/work/$USER`, `/tmp/$USER`, then `$HOME`. First writable one wins. Override with `DATA_ROOT`. |
| Partition names? | **No `--partition` is written into any sbatch file** — a wrong name is a submit-time rejection. Pass it: `sbatch --partition=gpu_student campaign_04.sbatch`. |
| GPUs per job, time limits? | `--gres=gpu:1`, `--cpus-per-task=8` and a 2x-estimate wall clock are conservative floors, all overridable at submit time. |
| PyTorch module or container? | `activate_python()` tries the active venv, the project venv, `$HOME/ecg_env`, then any `module avail` entry matching `pytorch`, then system `python3` — and each candidate must actually `import torch` before it is accepted. |

### Two decisions made at Step 4

1. **The 94-config matrix is the authority on run counts, not the plan's table.**
   `campaign_runs.py --table` derives each campaign's runs from the generated
   configs, and all 94 map to exactly one campaign with none orphaned (the
   command exits non-zero if that ever stops being true). The totals differ from
   the estimates in `PHASE2_EXECUTION_PLAN_DGX.md` because that table predates
   the locked matrix — e.g. campaign 1 is 12 configs x 3 seeds = 36 runs, not
   the 21 estimated. Trust `--table`, and treat the plan's numbers as the
   sizing estimates they were.
2. **Lead-II raw signals stay in campaign 4, not the campaign-9 sweep.** A
   campaign is defined by the data it reads (§8.2), and both Lead-II encodings
   are already resident in campaign 4 at only 5.7 GB. Campaign 9 carries the
   12-lead raw set, which is the ~32 GB that actually needs pieces.

### Verified at Step 4, on this laptop

- `make_chunks.py plan --kinds preprocessed_12lead image_clean_12lead --pieces 8`:
  523,945 train studies, piece sizes 65,260-65,758 (**0.40 %** max deviation),
  and **0 of 523,945 studies disagree** between the two modalities — §8.2 rule 1's
  alignment requirement, measured rather than asserted. Independence from the
  label-like strata: cart_id chi2 46.9/dof 70, hr_bucket 12.5/14, link_tier
  15.5/21, stratum 80.6/70.
- The quota gate refuses at 44 GB used + 30 GB asked, exit 1, before any byte moves.
- A chunked campaign without `--pieces` refuses rather than staging everything.
- A failed push leaves checkpoints **untouched**; a verified push deletes them.
- The evict guard was tested in all four states (never pushed / just pushed /
  new result after push / `--force`) and behaves correctly in each.

**No acquisition timestamp exists in any processed index**, so independence of
the pieces from TIME cannot be measured directly. The nearest evidence is that
consecutive study ids scatter across all pieces (asserted in the self-check).
Add `ecg_time` to the metadata and `STRATA` in `make_chunks.py` covers it with
no other change.

---

## Written at Step 5 (2026-08-28)

```
make_int16.py                 # convert / verify the int16 + per-record-scale copies
prove_int16_equivalence.py    # the three-arm equivalence proof for the supplementary
```

`make_int16.py` writes one shard at a time to a temp file and renames it only
once its checksum is in `signals_int16/int16_manifest.json`, so a power cut
costs exactly the shard in flight. A shard already in the manifest is skipped,
so re-running the identical command resumes.

### Two numerical bugs found while writing it

Both were in the *conversion*, not the data, and both are fixed:

1. **The error was measured in float32.** At an amplitude of ~1900 the float32
   spacing is 1.2e-4, against a half-quantisation-step of 0.03 — so the
   measurement carried ~0.4 % noise on the very quantity it was bounding. The
   check now runs in float64. The *realised* float32 round-trip error is
   reported separately, because that is what training actually sees.
2. **The quotient `x / scale` was computed in float32.** Its ~6e-8 relative
   error is ~2e-3 of a code at magnitude 32767 — enough to tip `rint()` to the
   wrong neighbour and push the error just past half a step (measured 1.000266
   of a half-step on real data). Taking the quotient in float64 against the
   exact float32 scale brings it to 0.999983, so "error <= half a step" is now
   exactly true rather than nearly true.

### Reading the int16 copies

`modality.py` gained a `TRIMODAL_SIGNAL_INT16` switch. When set, `_read_signal`
resolves containers to `data/processed/signals_int16/` and multiplies by the
per-record `scale` dataset on the way out, so the trainer, the evaluator and the
baselines all receive float32 arrays exactly as before and need no change. The
campaign body exports it, because staged DGX signals are int16.

### Reconciled at Step 5: the Step 4 body called the trainer wrongly

`slurm/_campaign_body.sh` originally invoked `30_train.py --task ... --arch-tier
... --data-root ... --chunked`. None of those exist: the trainer takes
`--model-config <path>` (required) and `--seed`. Fixed by having
`campaign_runs.py` emit the config filename as a fourth field, so the shell
never needs to know the naming scheme, and `campaign_runs.py --table` now
verifies all **94/94** config files exist on disk and exits non-zero if any is
missing. Two further corrections fell out of the same read:

* **`31_eval.py` aggregates across seeds**, so it runs once per (task, arch
  tier) after all three seeds finish — not once per seed. Campaign 5's 12 train
  runs correctly collapse to 4 eval invocations.
* **The loader has no data-root flag.** It resolves everything under
  `$PROJECT_ROOT/data/processed`, so when `DATA_ROOT` is elsewhere (node-local
  scratch) the body symlinks rather than copying.

---

## Written at Step 6 (2026-08-29)

```
make_subsets.py   # build / verify the three derived datasets + their manifest overlays
upload_data.py    # push a campaign's data to R2 in the layout stage_data.sh reads back
```

### The layout, which is defined by the reader

`stage_data.sh` is the only consumer, so it decides the shape:

```
plain dataset      r2:trimodal-data/<dataset>/<path relative to data/processed>
chunked dataset    r2:trimodal-data/chunks/<base>/piece_NNN.h5   (or .tar)
                   r2:trimodal-data/chunks/<base>/checksums.json
                   r2:trimodal-data/chunks/<base>/assignment.parquet
```

The paths **inside** a dataset are relative to `data/processed`, not to the
dataset name, because `_campaign_body.sh` symlinks `DATA_ROOT` to
`$PROJECT_ROOT/data/processed` and `modality.py` resolves everything under that
one path. So `signals_lead2` ships `signals_int16/lead2_preprocessed.h5` and
`signals/lead2_raw.h5`, and each lands exactly where the modality manifest
already points. `code` and `configs` are repo paths and stage into
`PROJECT_ROOT`; `results` comes from `r2:trimodal-results`, not from here.

Chunk name mappings: `preprocessed_12lead → chunks/signals_12lead`,
`image_clean_12lead → chunks/images_clean_12lead`,
`raw_12lead → chunks/signals_raw`.

### Two read-path bugs fixed at Step 6

1. **`fetch()` named the destination after the object.** `rclone copy SRC
   "$dest/$(basename "$rel")"` put a chunk piece at
   `piece_000.h5/piece_000.h5` and every plain dataset one directory too deep.
   Both now copy *into* `$dest`.
2. **Checksum manifests are per dataset** (`checksums_<dataset>.json`). Two
   datasets can land in one directory — `text` and `index` both write into
   `index/` — and a shared `checksums.json` let the second shadow the first,
   leaving the first's files verified against nothing.

Verified by round trip, not by reading: campaign 1 was uploaded and pulled back
with the real `stage_data.sh`, 49 files checksum-verified, zero mismatches.

### Subsets and manifest overlays

A subset container (`derived/<dataset>/<dataset>__<split>.h5|.tar`) holds its own
rows in its own order, so the base `modality_manifest.parquet` no longer
describes it. Each derived dataset ships `manifest_overlays/<dataset>.parquet`
and `modality.py` lets an overlay row replace the base row for that
(study_id, kind, layout). Callers are unchanged. A study outside the subset keeps
its base-container row, and that container is not staged on a subset campaign, so
a miss is a loud missing-file error rather than silently wrong bytes.

`make_subsets.py selfcheck` builds a 40-study micro-subset, puts a live overlay
in place, asserts `read_modality()` returns bit-identical arrays and image bytes,
and deletes everything it wrote.

### Usage

```bash
PY=./ecg_env/Scripts/python.exe
$PY scripts/dgx_portability/make_subsets.py plan            # counts + byte estimates
$PY scripts/dgx_portability/make_subsets.py build --datasets signals_12lead_L3
$PY scripts/dgx_portability/make_subsets.py verify

$PY scripts/dgx_portability/upload_data.py --all --dry-run  # sizes, moves nothing
$PY scripts/dgx_portability/upload_data.py --campaign 1     # one campaign, resumable
```

`TRIMODAL_CHUNK_ROOT` moves a cut off the data volume (the remote path comes
from the directory *name*); `TRIMODAL_UPLOAD_STAGE` moves the hard-link staging
tree to follow it — hard links cannot cross volumes.

Never: `rclone lsd r2:` (403 by design — always name the bucket), public access
or an r2.dev URL on `trimodal-data`, raw MIMIC, the EHR cache, the linkage
tables, `structured_features.parquet`, or credentials in the repo. The uploader
refuses all of those by path pattern and scans every task parquet for binary
columns before it moves a byte.
