# Step 6 — Staged uploads to R2 — report

Written 2026-08-29 (session 8). Operations step, not a science stage: it moves
processed artifacts to `r2:trimodal-data` in the layout `stage_data.sh` reads
back, and builds the datasets that layout names but nothing produced.

**Gate before starting, checked not assumed.** Step 10R is DONE (leakage 88/88,
cohort 199/199, split 79/79 — 366 checks, 0 violations) and Step 5's int16
conversion is complete (six files in `data/processed/signals_int16/`, all in
`int16_manifest.json`). `rclone size r2:trimodal-data` was **0 objects** before
the first push, so nothing pre-existing was overwritten.

---

## 1. What was built, and why it did not exist

### 1.1 The three derived datasets — `make_subsets.py` (new)

`campaigns.sh` named `signals_12lead_L3`, `images_clean_12lead_L3` and
`images_scanlike_test`; no script produced them.

**The study list comes from the task parquets**, as instructed — not from
re-derived linkage. It is the union of the `is_primary` rows of A1, A3, A4 and
A6, which is exactly the row set `TaskDataset(primary_only=True)` (the default)
will ask for on campaigns 5 and 7:

| split | studies | int16 12-lead | clean 12-lead images |
| ----- | ------: | ------------: | -------------------: |
| train | 295,236 |     30.72 GB  |              3.57 GB |
| val   |  42,563 |      4.43 GB  |              0.51 GB |
| test  |  84,348 |      8.78 GB  |              1.02 GB |
| **total** | **422,147** | **43.93 GB** | **5.10 GB** |

`images_scanlike_test` is the test split (149,642 studies) of **both** scan-like
layouts, 12-lead and Lead-II, because campaign 10's configs read both:
~20.40 GB, which is what the plan's "~20 GB resident" was sized against.

**One file per split**, because campaign 5 holds train+val while training and
swaps in test to evaluate.

**How a subset is read back — the one new mechanism.** A subset container holds
its own rows in its own order, so the base `modality_manifest.parquet` no longer
describes it. Each dataset therefore ships
`manifest_overlays/<dataset>.parquet` — the manifest schema, its studies only —
and `modality.py` now lets an overlay row **replace** the base row for that
(study_id, kind, layout). Nothing else changed: the trainer, the evaluator and
the baselines still call `read_modality()` and receive float32 exactly as
before. A study *outside* the subset keeps its base-container row, and the base
container is not staged on a subset campaign, so a miss fails loudly with a
missing-file error rather than silently returning the wrong bytes.

`make_subsets.py selfcheck` builds a 40-study micro-subset, puts a live overlay
in place and asserts `read_modality()` returns **bit-identical** arrays and
image bytes through it, then deletes everything it wrote. **PASS.**
`modality.py`'s own self-check (9/9 kinds) and the P2.0 gate (**26/26**) both
still pass with the overlay code in.

The signal subset **copies int16 codes**, it does not requantise, so the Step 5
equivalence proof still covers the data campaigns 5 and 7 train on.

### 1.2 The chunk cuts — `make_chunks.py cut`

`data/processed/chunks/` held only plans (`assignment.parquet`,
`fairness.json`); campaigns 6, 8 and 9 cannot stage without piece files. Three
cuts are running, all TRAIN split, 8 pieces, `--int16` for the signal kinds:

    make_chunks.py cut --kinds image_clean_12lead  --pieces 8
    make_chunks.py cut --kinds preprocessed_12lead --int16 --pieces 8
    make_chunks.py cut --kinds raw_12lead --int16  --pieces 8

Two fixes were needed before the first one could run:

* **`cut_image_piece` called `modality.read_modality_bytes()`, which does not
  exist** — the cut would have exited at the first image piece. `read_modality`
  already returns the *encoded* bytes for an image kind (it is `_read_image`
  that seeks into the tar), so the piece tars are byte-identical members with no
  decode/re-encode round trip.
* **`--int16` now sets `TRIMODAL_SIGNAL_INT16=1`**, so a signal cut reads the
  int16 copies where they exist: half the I/O, and for `preprocessed_12lead`
  the codes survive exactly (`peak/32767` is idempotent). `raw_12lead` has no
  int16 copy, `_resolve_h5` falls back to the float32 original, and the
  quantisation happens in the cut instead.

`TRIMODAL_CHUNK_ROOT` was added because the laptop has 86 GB free on D: and the
three cuts are ~84 GB; they are being written to C: and the remote path is
derived from the directory *name*, so nothing downstream changes.

### 1.3 The uploader — `upload_data.py` (new)

`stage_data.sh` only ever pulled; nothing pushed. The new script writes exactly
what the stager reads:

    plain dataset      r2:trimodal-data/<dataset>/<path relative to data/processed>
    chunked dataset    r2:trimodal-data/chunks/<base>/piece_NNN.h5   (or .tar)
                       r2:trimodal-data/chunks/<base>/checksums.json
                       r2:trimodal-data/chunks/<base>/assignment.parquet

with the three name mappings the stager expects
(`preprocessed_12lead → chunks/signals_12lead`,
`image_clean_12lead → chunks/images_clean_12lead`,
`raw_12lead → chunks/signals_raw`).

* **A piece counts as uploadable only once `make_chunks.py` has recorded it in
  `checksums.json`** — which happens after the atomic rename. The first version
  globbed `piece_*` and a dry-run caught it about to push a live cut's
  `piece_001.h5.tmp`: a half-written file that, being listed in no manifest,
  the stager's verifier would then have skipped. Every file is also cross-checked
  against the digest its builder recorded before it is pushed; the hash is
  computed for the upload manifest anyway, so the check costs nothing and catches
  a truncated artifact before the DGX trains on it.
* **Resumable**: the remote layout is materialised as a tree of *hard links*
  under `outputs/upload_stage/` (no bytes copied — same volume) and pushed with
  `rclone copy --checksum`, which skips what already matches. sha256 digests are
  cached in `outputs/upload_checksums.json` keyed by path+size+mtime, so a
  resumed night does not re-hash 160 GB.
* **`--dry-run`** prints files and bytes per dataset, per campaign, before
  anything moves; `--campaign N`, `--dataset NAME...` and `--all` select.
* Every uploaded directory gets a `checksums_<dataset>.json` in the format the
  stager's inline verifier expects, `{"<file>": {"sha256": ...}}`.

---

## 2. The read-path check — the thing most likely to be quietly wrong

**It was wrong, in two ways, and both are fixed.**

1. **`fetch()` named the destination after the object.**
   `rclone copy "$R2_DATA/$rel" "$dest/$(basename "$rel")"` buried a chunk piece
   at `piece_000.h5/piece_000.h5` and put every plain dataset one directory too
   deep. Both now copy *into* `$dest`.
2. **`modality.py` resolves everything under `$PROJECT_ROOT/data/processed`**
   (`_campaign_body.sh` symlinks `DATA_ROOT` there), so a dataset's objects have
   to carry their paths **relative to `data/processed`** — the int16 Lead-II copy
   must land at `signals_int16/lead2_preprocessed.h5`, not at
   `signals_lead2/lead2_preprocessed.h5`. The uploader now writes those paths,
   and `stage_data.sh` routes `code`/`configs` to `PROJECT_ROOT` (they are repo
   paths, `scripts/` and `config/`) and `results` to `$R2_RESULTS`.

**int16 specifically.** `TRIMODAL_SIGNAL_INT16` defaults to 1 in
`_campaign_body.sh`; `_resolve_h5` prefers `signals_int16/<name>` and falls back
to the base path **if the int16 file is absent**. `lead2_raw.h5` has no int16
copy, so campaign 4 reads it from `signals/lead2_raw.h5` — both files are
uploaded at exactly those two paths, so campaign 4 resolves both encodings.

**Verified end to end, not reasoned about.** Campaign 1 was uploaded, then
pulled back with the real `stage_data.sh` into a scratch `PROJECT_ROOT`:
`code → proj/scripts/`, `configs → proj/config/`, data → `proj/data/processed/`
with `index/`, `tasks/`, `modality_manifest.parquet` at their manifest paths,
and **49 files checksum-verified, zero mismatches**.

**`checksums_<dataset>.json`, not `checksums.json`.** Two datasets can land in
one directory (`text` and `index` both write into `index/`); a shared name let
the second shadow the first and leave the first's files verified against
nothing. The stager's `find` now matches `checksums*.json`.

---

## 3. Upload status

| # | campaign | datasets | bytes | state |
| - | -------- | -------- | ----: | ----- |
| 1 | text_models | code, configs, tasks, fiducials, index, text | 1.10 GB | **UPLOADED, round-trip verified** |
| 2 | images_12lead | + images_clean_12lead | 8.94 GB | **UPLOADED** |
| 3 | images_lead2 | + images_clean_lead2 | 17.84 GB | **UPLOADED** |
| 4 | signals_lead2 | + signals_lead2 (12.57 GB), signals_corrupted | 13.50 GB | **UPLOADED** |
| 5 | signals_12lead_L3 | + signals_12lead_L3 | 43.93 GB | train + val built; test building |
| 6 | signals_12lead_full | chunks/signals_12lead ×8 | ~54.5 GB | cutting, 1 of 8 pieces |
| 7 | fusion_L3 | + images_clean_12lead_L3 | 5.02 GB | **BUILT + verified, uploading** |
| 8 | fusion_full | chunks/images_clean_12lead ×8 | 5.82 GB | **CUT 8/8, uploading** |
| 9 | retrain_sweeps | chunks/signals_raw ×8 | ~23.6 GB | queued behind campaign 6's cut |
| 10 | test_sweeps | + images_scanlike_test | 20.33 GB | **BUILT, uploading** |
| 11 | final_eval | results | — | reads `r2:trimodal-results`, filled by `push_results.sh` |

**41.36 GiB was in the bucket after campaigns 1–4** (524 objects), measured with
`rclone size r2:trimodal-data`.

**Project upload total ≈ 195 GB**, not the ~142 GB the plan assumed — Step 5's
measured int16 ratio (77.5 GiB of 12-lead, not 56.7) plus the chunk cuts, which
duplicate the training split in piece form.

Uploads are deliberately paced across nights and are one command each:

    ./ecg_env/Scripts/python.exe scripts/dgx_portability/upload_data.py --campaign N
    ./ecg_env/Scripts/python.exe scripts/dgx_portability/upload_data.py --all --dry-run

---

## 4. Privacy and access, checked before the first push

* **Raw MIMIC never left the laptop.** The uploader refuses by path pattern:
  `data/raw/`, `ehr_cache`, `linkage/`, `structured_features.parquet`, and
  anything that looks like a credential (`rclone.conf`, `.env`, `.pem`, `.key`).
  Refusal is an exception, not a skip.
* **Task parquets carry ids and labels, never bytes.** Every task parquet's
  arrow schema is scanned before any upload and the run refuses if a `binary` /
  `fixed_size_binary` column appears. All 101 files: clean.
* **The bucket stays private.** No public-access or `r2.dev` setting was touched
  or requested. `rclone lsd r2:` 403s by design; every command names the bucket.
* **Credentials** stayed in `%APPDATA%\rclone\rclone.conf` and the password
  manager. Nothing was written to the repo, a script, a doc or a commit.

---

## 5. Findings that outlive this step

1. **A4 is not an L3-only table.** Its built parquets carry the full clean
   cohort (749,112 studies) with `is_primary` marking the L3 subset, exactly as
   §4.A.4.2 specifies (primary L3, sensitivity full). The L3 subsets are
   therefore built from `is_primary`, which is what the loader reads by default.
   Had they been built from the raw row set they would have been the whole
   cohort and campaign 5 would not fit.
2. **Campaigns 7, 8 and 11 read the Lead-II streams too** — their configs
   include `multimodal_fusion_lead2` and `embedding_cosine_lead2` — and
   `campaigns.sh` did not list those datasets, so those runs would have died at
   the first read. The lists are now correct, which makes 7 (69 GB) and 8
   (48 GB) exceed the 45 GB ceiling: `require_fit` will now **refuse** them.
   **The fix is to split each campaign by lead subset** (a 12-lead half and a
   Lead-II half), which needs `campaign_runs.py` to route by lead subset as well
   as tier. Refusing loudly beats dying at the first missing file, so this is
   left refusing until that decision is made.
3. **The chunked campaigns are not runnable on pieces yet, for two reasons
   beyond Step 6.** (a) No dataloader reads `piece_NNN.h5`; the pieces are
   self-describing (`signal`, `study_id`, `scale`) but nothing consumes them
   yet. (b) Pieces are cut from **train** only, by design, so campaigns 6, 8 and
   9 have no val split resident for early stopping and no test split for
   evaluation. Both belong to Step 7/8 planning.
4. **Resident sizes were re-derived from disk** and written into `campaigns.sh`.
   Campaign 4 is 15 GB, not 8 (Lead-II raw is 6.08 GB of float32 and the int16
   preprocessed copy is 7.42 GB — the README's "5.7 GB" predates Step 5's
   measurements). Campaign 5 is 34 GB, not 27.
5. **The run counts are 104 configs / 312 runs**, per
   `campaign_runs.py --table`, not the 94/282 recorded before Round 10 added the
   regression heads.
6. **Campaign 11's `results` dataset lives in `r2:trimodal-results`**, which
   `push_results.sh` fills from the DGX. The uploader skips it by name and says
   so rather than failing.
