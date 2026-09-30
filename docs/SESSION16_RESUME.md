# Resume session 16 — what is left, and exactly how to finish it

Written 2026-09-30 ~15:00 IST on the **`data-laptop`**, because the session was
stopped mid-flight to restart Claude Code. **All code and docs are committed and
pushed.** What remains is data building and uploading, and every step of it is
resumable: nothing has to be redone, only continued.

Delete this file once §1 is finished and the checks in §3 are green.

---

## 0. State of play

**Done and on `main`** (commits `9c73610` … `HEAD`): the whole code and docs
side of open questions 16 and 17. See `docs/PHASE2_PROGRESS.md` session 16.

**Built on C: and verified:**

| container | size | in R2? |
| --- | --- | --- |
| `image_scanlike_12lead__train__p8` (8 pieces) | 43.77 GB | **yes, 11/11 objects** — round trip PASSed |
| `image_scanlike_lead2__train__p8` (8 pieces) | 27.30 GB | no — **round trip PASSed** |
| `images_scanlike_12lead_valtest` | 18.84 GB | no |
| `images_scanlike_lead2_valtest` | 11.80 GB | no |

**Not built yet:** `image_clean_lead2__train__p8` and
`images_clean_lead2_valtest` — needed by campaigns 13 and 14 only.

R2 is at **267.1 GiB / 617 objects** (was 226.4 GiB / 601 before this session).

**All four scan-like containers passed `verify` at 15:06** — every sha256
matches what the builder recorded, sizes exactly as predicted:
scan-like Lead-II pieces 8 x ~3.41 GB; `images_scanlike_12lead_valtest`
val 6.31 GB / test 12.52 GB; `images_scanlike_lead2_valtest` val 3.94 /
test 7.81. Both scan-like round trips PASS.

**A background orchestrator was running when the session stopped** and had just
started the `image_clean_lead2` cut (15:06). It may or may not have survived the
Claude Code restart. **Check before re-running §1 — it is harmless either way,
because every step skips what is already done:**

```bash
tasklist | grep -i python          # or: Get-Process python
tail -20 "C:/Users/banot/AppData/Local/Temp/claude/D--Coding-MU-Tri-Modal-ECG/6ceaca24-9f54-4157-a57f-db680785cc81/scratchpad/finish.log"
ls /c/trimodal_chunks/image_clean_lead2__train__p8/
```

If it is alive, let it finish — it does the whole of §1 by itself, then prints
`FINISH DONE`. If it is gone, just run §1.

---

## 1. Finish the data — one command

Everything below is idempotent. `make_chunks` skips a piece already recorded in
`checksums.json`, `make_subsets` skips a split already recorded, and `rclone`
skips an object whose checksum matches. **Re-running after an interruption costs
only the file that was in flight.**

```bash
cd /d/Coding/MU/Tri-Modal_ECG
export TRIMODAL_UPLOAD_STAGE=/c/trimodal_chunks/_upload_stage
PY=./ecg_env/Scripts/python.exe

# --- build what is missing (clean Lead-II, for campaigns 13/14) -------------
"$PY" scripts/dgx_portability/make_chunks.py cut \
      --kinds image_clean_lead2 --split train --pieces 8
"$PY" scripts/dgx_portability/make_subsets.py build \
      --datasets images_clean_lead2_valtest

# --- verify every checksum --------------------------------------------------
"$PY" scripts/dgx_portability/make_chunks.py verify --split train --pieces 8 \
      --kinds image_scanlike_12lead image_scanlike_lead2 image_clean_lead2
"$PY" scripts/dgx_portability/make_subsets.py verify --datasets \
      images_scanlike_12lead_valtest images_scanlike_lead2_valtest \
      images_clean_lead2_valtest

# --- upload, in this order (the first is already done) ----------------------
for d in images_scanlike_12lead_valtest \
         images_scanlike_lead2_pieces images_scanlike_lead2_valtest \
         images_clean_lead2_pieces images_clean_lead2_valtest \
         signals_lead2_preprocessed signals_lead2_raw; do
    "$PY" scripts/dgx_portability/upload_data.py --dataset "$d"
done
```

`TRIMODAL_CHUNK_ROOT` and `TRIMODAL_DERIVED_BASE` are **not** needed — D: now
reaches the C: directories through junctions, so the default roots resolve.
`TRIMODAL_UPLOAD_STAGE` **is** needed: the staging tree hard-links the
containers, and a hard link cannot cross volumes.

Measured upstream on this line is **~25 MB/s**, so the ~76 GB still to push is
roughly **50 minutes** of transfer plus hashing. Do not run two uploads at once;
they share the link and the disk.

`signals_lead2_preprocessed` and `signals_lead2_raw` point at files already in
the bucket, so they transfer nothing — they only write their own per-dataset
checksum manifests, which `stage_data.sh` verifies against.

---

## 2. Two small things after the build

```bash
# 1. junction the last derived container into the D: tree, or local val/test
#    reads of clean Lead-II images will fail (trap 21).
powershell -Command "New-Item -ItemType Junction \
  -Path 'D:\Coding\MU\Tri-Modal_ECG\data\processed\derived\images_clean_lead2_valtest' \
  -Target 'C:\trimodal_derived\derived\images_clean_lead2_valtest'"

# 2. drop the scratch the round-trip check made (hard links, costs nothing,
#    but it shows up under data/processed/chunks through the junction)
rm -rf /c/trimodal_chunks/_roundtrip
```

---

## 3. Then prove it, and only then call it done

```bash
PY=./ecg_env/Scripts/python.exe

# every campaign stages what its runs actually READ  -> expect 15/15
"$PY" scripts/dgx_portability/check_campaign_data.py
"$PY" scripts/dgx_portability/check_campaign_data.py --selfcheck

# every campaign fits both phases -> expect no REFUSES and no `missing`
"$PY" scripts/dgx_portability/upload_data.py --sizes

# the clean Lead-II pieces read back byte-identical to the base shards.
# BOTH scan-like cuts already PASSed this on 2026-09-30, so only this one is left.
"$PY" scripts/dgx_portability/verify_piece_roundtrip.py \
      image_clean_lead2 C:/trimodal_chunks/image_clean_lead2__train__p8 40

# the training stack still runs
"$PY" scripts/phase2_tasks_benchmark_and_paper/_train_lib/smoke_test.py --tiers signal --skip-train
bash scripts/dgx_portability/campaigns.sh selfcheck
"$PY" scripts/phase2_tasks_benchmark_and_paper/_train_lib/chunk_cycle.py
```

The round-trip script is now in the repo (it was scratch during session 16).
It stages two real pieces as `stage_data.sh` would
(`data/processed/<base>/piece_NNN.tar`), runs
`chunk_pieces.install_overlays()`, and asserts `read_modality()` returns the
same bytes it returned from the base container, with a study outside the window
still resolving to the base. **Both scan-like cuts already PASSed** — 12-lead
and Lead-II — so only `image_clean_lead2` is outstanding, and it uses the
identical code path.

**`--sizes` rows 3, 13, 14 and 15 are lower bounds until the Lead-II containers
finish** — they will read `missing` until then. Expected finals: campaign 3 and
15 at 31.0 GB, campaigns 13 and 14 at 24.3 GB.

---

## 4. Last, update the record

- `docs/PHASE2_PROGRESS.md`: in §3 "Where the data physically lives", replace the
  R2 figure with the final `rclone size r2:trimodal-data`, and add a one-line
  R2 inventory. Add a closing line to the session 16 log saying the uploads
  finished and what the final checks reported.
- Delete this file.
- Commit on `main` and push.

---

## 5. A prompt for the next session

> Read `.machine` (this is the `data-laptop`), `git pull --ff-only origin main`,
> then read `docs/PHASE2_PROGRESS.md` (header + the session 16 log) and
> `docs/SESSION16_RESUME.md`. The previous session was stopped mid-flight to
> restart Claude Code; all code and docs are committed and pushed, and what is
> left is finishing the data build and upload.
>
> Work through `docs/SESSION16_RESUME.md` §1 to §4 autonomously and report at
> the end. Everything in it is resumable, so just run it; do not redesign
> anything. In particular **do not re-chunk, re-cut or re-plan the campaign
> table** — open questions 16 and 17 are closed, all 15 campaigns were measured
> to fit, and `check_campaign_data.py` proves each stages what it reads.
>
> Long uploads: run them in the background and monitor, do not pipe them
> through `tail` (that hides rclone's progress until the command exits).
>
> When §3's checks are all green, update `docs/PHASE2_PROGRESS.md`, delete
> `docs/SESSION16_RESUME.md`, commit on `main` and push. Then tell me: the final
> R2 size, the `--sizes` table, and anything that did not go to plan.
>
> Do not submit anything on the DGX from this machine — it cannot reach it.
> `docs/CAMPUS_LAPTOP_HANDOVER.md` is what the college laptop uses.

---

## 6. What NOT to redo

- **Do not re-cut anything at a different piece count.** Every cut in R2 is p8
  and they are aligned — `make_chunks.py plan` reports 0 of 523,945 studies
  disagreeing. A different count invalidates every uploaded cut.
- **Do not "fix" `chunk cycling OFF for this run`.** It is correct for a run
  that reads no chunked kind.
- **Do not delete `signals_12lead_L3` or `images_scanlike_test` from R2.** Both
  are unused now and both are kept deliberately; §3 of the progress doc says why.
- **Do not touch `campaigns.sh` numbers by hand.** Regenerate them with
  `upload_data.py --sizes` and paste.
