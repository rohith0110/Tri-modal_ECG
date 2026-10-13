#!/usr/bin/env bash
# Shared campaign table and helpers, sourced by every launcher (spec §8.2).
#
# NOTHING HERE ASSUMES A VERIFIED DGX. The Step 7 environment survey has not
# run, so this file must work on a node with no internet, no scratch, no module
# system and no container runtime. Every such capability is DETECTED and has a
# documented fallback; a missing capability degrades the run, it never crashes
# it silently. Credentials are never stored here (README: password manager and
# the local rclone config only).

set -euo pipefail

# ---------------------------------------------------------------------------
# per-account settings (docs/DGX_ACCOUNTS.md)
# ---------------------------------------------------------------------------
# Two DGX accounts run this code from two separate checkouts. Whatever differs
# between them -- the quota ceiling, where results are pushed -- lives in an
# UNTRACKED `.account_env` at the root of each checkout, sourced here so every
# launcher, the trainer's staging calls and the eval jobs all see the same
# values. No file: the defaults below, which are account 1's.
_ACCOUNT_ENV="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.account_env"
if [ -f "$_ACCOUNT_ENV" ]; then
    # shellcheck disable=SC1090
    . "$_ACCOUNT_ENV"
fi

# ---------------------------------------------------------------------------
# quota
# ---------------------------------------------------------------------------
# §8.0: 50 GB total. §8.1/§8.2: refuse to start above the ceiling.
# Raised 45 -> 49 on 2026-08-30: `used_gb()` sums PROJECT_ROOT, which now also
# holds the 5.7 GB `ecg_env` venv and the HuggingFace cache. Campaign 7 stages
# 37.7 GB, so the old ceiling left ~1 GB of margin on a fixed, non-staged cost.
# Raised 49 -> 99 on 2026-10-14 (user's call): a second account, se23ucse034,
# brings a second 50 GB allocation and both are spent in this one folder. Not
# confirmed with the admins that allocations pool, and nothing enforces either
# number -- see docs/DGX_ACCOUNTS.md.
QUOTA_TOTAL_GB="${QUOTA_TOTAL_GB:-100}"
QUOTA_CEILING_GB="${QUOTA_CEILING_GB:-99}"

# ---------------------------------------------------------------------------
# roots -- resolved, never assumed
# ---------------------------------------------------------------------------
# The single most valuable unknown from Step 7 is whether node-local scratch
# exists. If it does, data goes there and the 50 GB home quota only holds code,
# checkpoints and logs; if it does not, everything shares the quota. Override
# by exporting DATA_ROOT before calling.
PROJECT_FOLDER="${PROJECT_FOLDER:-se23ucse027}"

resolve_data_root() {
    if [ -n "${DATA_ROOT:-}" ]; then
        printf '%s\n' "$DATA_ROOT"
        return
    fi
    # NOT /tmp. It is writable on these nodes, so it would be picked
    # automatically, and it would hold staged data OUTSIDE the 50 GB the
    # facility allocated us: space that is not ours, that `used_gb` cannot
    # see, that differs between dgxa and dgxb, and that a reboot empties
    # mid-campaign. Project decision 2026-08-30 -- everything lives inside
    # the quota. Export DATA_ROOT to override, deliberately, per run.
    local candidate
    for candidate in "${SCRATCH:-}" "/scratch/${USER:-}" "/raid/${USER:-}" \
                     "/work/${USER:-}"; do
        [ -n "$candidate" ] || continue
        if mkdir -p "$candidate/$PROJECT_FOLDER/data/processed" 2>/dev/null \
           && [ -w "$candidate/$PROJECT_FOLDER/data/processed" ]; then
            printf '%s\n' "$candidate/$PROJECT_FOLDER/data/processed"
            return
        fi
    done
    # No writable scratch here (measured 2026-08-30), so data lives inside the
    # project folder: one roll-numbered directory holds checkout, data and
    # outputs. used_gb counts a nested root once, and _campaign_body.sh skips
    # its symlink when DATA_ROOT already IS $PROJECT_ROOT/data/processed.
    printf '%s\n' "$HOME/$PROJECT_FOLDER/data/processed"
}

# Everything this project writes goes in ONE folder named after the roll
# number. Homes sit side by side on a facility-wide filesystem, so a named
# folder keeps this project's files identifiable and keeps the account's home
# from filling with loose directories. Override PROJECT_FOLDER (or
# PROJECT_ROOT outright) for another account.
PROJECT_FOLDER="${PROJECT_FOLDER:-se23ucse027}"
PROJECT_ROOT="${PROJECT_ROOT:-$HOME/$PROJECT_FOLDER}"
DATA_ROOT="$(resolve_data_root)"
RESULTS_ROOT="${RESULTS_ROOT:-$PROJECT_ROOT/outputs}"
STATE_DIR="${STATE_DIR:-$PROJECT_ROOT/.campaign_state}"

# ---------------------------------------------------------------------------
# remote -- rclone if present, a local/mounted path if not
# ---------------------------------------------------------------------------
# R2 is the plan; the courier-a-drive fallback in the execution plan means the
# same launchers must work against a plain directory. Set TRIMODAL_SOURCE to a
# path (e.g. a mounted drive or a friend's laptop over the campus network) to
# bypass rclone entirely.
R2_DATA="${R2_DATA:-r2:trimodal-data}"
R2_RESULTS="${R2_RESULTS:-r2:trimodal-results}"
# Where the local transport writes results. Defaults beside TRIMODAL_SOURCE so
# the courier-a-drive fallback needs one variable set, not two.
TRIMODAL_RESULTS_DEST="${TRIMODAL_RESULTS_DEST:-${TRIMODAL_SOURCE:-}/../trimodal-results}"

# rclone is resolved, not assumed to be on PATH. A Slurm batch job runs a
# NON-interactive shell, which never sources ~/.bashrc -- so the `export
# PATH=$HOME/se23ucse027/bin:$PATH` that makes `rclone` work in an ssh session
# is simply absent inside a job, and `command -v rclone` fails there while
# succeeding in every interactive test. That is how campaign 1 reached
# `transport=none` on its first real submit (job 22335) after staging by hand
# had worked three times.
RCLONE="${RCLONE:-}"
resolve_rclone() {
    [ -n "$RCLONE" ] && [ -x "$RCLONE" ] && return 0
    local candidate
    for candidate in "$(command -v rclone 2>/dev/null || true)"                      "$PROJECT_ROOT/bin/rclone" "$HOME/bin/rclone"                      "$HOME/se23ucse027/bin/rclone" "/usr/local/bin/rclone"; do
        if [ -n "$candidate" ] && [ -x "$candidate" ]; then
            RCLONE="$candidate"
            export RCLONE
            return 0
        fi
    done
    return 1
}

have_rclone() { resolve_rclone; }

have_internet() {
    # Cheap, bounded, and never fatal. Used to pick a transport, not to gate.
    curl -sI --max-time 10 https://cloudflare.com >/dev/null 2>&1
}

transport() {
    if [ -n "${TRIMODAL_SOURCE:-}" ]; then
        printf 'local\n'
    elif have_rclone && have_internet; then
        printf 'rclone\n'
    elif have_rclone; then
        printf 'rclone-offline\n'
    else
        printf 'none\n'
    fi
}

# fetch <remote-relative-path> <local-dest-dir>
#
# `rel` is either a dataset PREFIX -- whose objects carry their own paths
# relative to data/processed and must keep them, so `signals_int16/x.h5` lands
# at `$DATA_ROOT/signals_int16/x.h5` where modality.py looks for it -- or a
# single chunk piece. Both copy INTO `$dest`; naming the destination after the
# object (the previous behaviour) buried a piece at `piece_000.h5/piece_000.h5`
# and put every dataset one directory too deep.
# PHASE filtering. A derived container is named `<dataset>__<split>.<ext>`, so a
# phase is two rclone excludes rather than a second copy of every dataset under
# a different name. A file with no `__<split>.` in its name -- every base
# container, every parquet, every piece -- matches neither and is always taken.
# Four phases, not two. `train_only` and `val` exist for the campaigns whose
# train+val does not fit but whose train alone does: the run holds train data
# while it trains, swaps the pieces out for the val split at the epoch boundary,
# validates, and swaps back (open question 16). A campaign that fits with val
# resident uses `train` and never pays for the swap.
phase_excludes() {
    case "${1:-train}" in
        eval)       printf '%s\n' "--exclude" "*__train.*" "--exclude" "*__val.*" ;;
        # The test containers and nothing else, ADDED to a staged train phase.
        test)       printf '%s\n' "--include" "*__test.*" ;;
        val)        printf '%s\n' "--exclude" "*__train.*" "--exclude" "*__test.*" ;;
        train_only) printf '%s\n' "--exclude" "*__val.*"   "--exclude" "*__test.*" ;;
        *)          printf '%s\n' "--exclude" "*__test.*" ;;
    esac
}

fetch() {
    local rel="$1" dest="$2" phase="${3:-train}"
    mkdir -p "$dest"
    local excludes=()
    while IFS= read -r line; do excludes+=("$line"); done < <(phase_excludes "$phase")
    case "$(transport)" in
        local)
            [ -e "$TRIMODAL_SOURCE/$rel" ] || {
                echo "ERROR: $TRIMODAL_SOURCE/$rel not found" >&2; return 1; }
            if [ -d "$TRIMODAL_SOURCE/$rel" ]; then
                # rsync is not assumed to exist on the node, so the same filter
                # is expressed with find -- the courier-a-drive fallback must
                # stage exactly what the network path would.
                ( cd "$TRIMODAL_SOURCE/$rel" && find . -type f | while IFS= read -r f; do
                      take=1
                      case "$(basename "$f")" in
                          *__test.*)
                              if [ "$phase" != "eval" ] && [ "$phase" != "test" ]; then take=0; fi ;;
                          *__train.*|*__val.*)
                              if [ "$phase" = "eval" ] || [ "$phase" = "test" ]; then take=0; fi ;;
                          *)
                              if [ "$phase" = "test" ]; then take=0; fi ;;
                      esac
                      if [ "$take" = "1" ]; then
                          mkdir -p "$dest/$(dirname "$f")" && cp "$f" "$dest/$f"
                      fi
                  done )
            else
                cp "$TRIMODAL_SOURCE/$rel" "$dest/"
            fi
            ;;
        rclone|rclone-offline)
            resolve_rclone || { echo "ERROR: rclone not resolvable" >&2; return 1; }
            "$RCLONE" copy --progress --transfers 4 --checksum "${excludes[@]}" \
                "$R2_DATA/$rel" "$dest" \
                || { echo "ERROR: rclone copy failed for $rel" >&2; return 1; }
            ;;
        none)
            cat >&2 <<'MSG'
ERROR: no transport available.
  Neither rclone nor TRIMODAL_SOURCE is usable on this node.
  Either install rclone and configure the bucket-scoped token, or export
  TRIMODAL_SOURCE=/path/to/staged/data (mounted drive, or a campus-network
  share). See scripts/dgx_portability/README.md.
MSG
            return 1
            ;;
    esac
}

# push <local-path> <remote-relative-dir>
push() {
    local src="$1" rel="$2"
    case "$(transport)" in
        local)
            mkdir -p "$TRIMODAL_RESULTS_DEST/$rel"
            cp -r "$src" "$TRIMODAL_RESULTS_DEST/$rel/"
            ;;
        rclone|rclone-offline)
            # --s3-no-check-bucket: a bucket-scoped token cannot list buckets, so
            # rclone cannot confirm the target exists and issues CreateBucket
            # first -- which the token refuses with 403, and the push then fails
            # at the END of a multi-day run with the results still only local.
            # The bucket always exists; skip the check. Set here rather than only
            # in rclone.conf so it does not depend on a config someone may
            # recreate differently later.
            resolve_rclone || { echo "ERROR: rclone not resolvable" >&2; return 1; }
            "$RCLONE" copy --progress --checksum --s3-no-check-bucket "$src" "$R2_RESULTS/$rel" \
                || { echo "ERROR: rclone push failed for $src" >&2; return 1; }
            ;;
        none)
            echo "ERROR: no transport to push results. Results kept locally at $src" >&2
            return 1
            ;;
    esac
}

# ---------------------------------------------------------------------------
# the campaign table (docs/PHASE2_EXECUTION_PLAN_DGX.md)
# ---------------------------------------------------------------------------
# campaign_spec <n> -> "name|resident_gb|runs|gpu_hours|chunked|datasets..."
# `chunked` is yes for the campaigns whose training data exceeds the quota
# (6, 8, 9) -- those stage pieces, not whole files.
#
# AFTER EDITING THIS TABLE, RUN BOTH:
#   upload_data.py --sizes            -- does every campaign still fit?
#   check_campaign_data.py            -- does every campaign stage what it READS?
# The second exists because four campaigns were wrong at once and nothing
# noticed until a job died on the DGX; it replays those four failures as its own
# self-check, so it cannot quietly stop working.
#
# REBUILT 2026-09-30 (open question 16). Every number below is MEASURED off the
# files, by `upload_data.py --sizes`, not estimated -- the hand-maintained
# version had drifted in both directions (campaign 12 was listed at 29.4 and is
# 33.7; campaign 9 was 18.5 and is 12.7). Re-run that command after any change
# to a dataset and paste the numbers back here.
#
#   campaign_spec <n> -> "name|resident_gb|runs|gpu_hours|chunked|datasets|eval_gb|val_mode"
#
# PHASES. A campaign does not need its test split while it trains, so
# `resident_gb` is the TRAIN phase and `eval_gb` the EVAL phase, and
# `stage_data.sh --phase` filters on the `__<split>.` suffix the derived
# containers carry. `val_mode` adds a third case: `on_demand` campaigns do not
# hold the val split either -- see below.
#
# THE LEAD-II SPLIT (open question 14). A fusion campaign reads a whole lead
# set, which put campaign 7 at 69 GB, so 7/8/11 are the 12-lead halves and
# 12/13/14 the Lead-II ones. `campaign_runs.py` routes to match. No config
# renamed, no run dropped: still 104 configs, 312 runs.
#
# ---------------------------------------------------------------------------
# WHAT CHANGED AT OPEN QUESTION 16, AND WHY (2026-09-30)
# ---------------------------------------------------------------------------
# A5 and B4 fix the image rendering PER ROW (`image_type_column`,
# `task_dataset.py:524-528`), so every A5/B4 config that touches images reads
# `image_scanlike_<layout>` as well as the clean container its config names.
# Nothing staged it; that is what killed jobs 24639/24640. It is not a small
# addition: there is one scan-like row per anchor and every study in the split
# is an anchor, so scan-like train+val is 599,470 of 749,112 studies --
# 50.08 GB for 12-lead, more than the whole ceiling, and 31.24 GB for Lead-II.
#
# Four consequences, all of them measured rather than assumed:
#
# 1. SCAN-LIKE TRAIN IS CHUNKED, at p8, aligned with the three existing cuts
#    (`make_chunks.py plan` reports 0 of 523,945 studies disagreeing). Val and
#    test ship as the per-layout `images_scanlike_<layout>_valtest` containers,
#    because `images_scanlike_test` holds BOTH layouts in one 20.33 GB tar and
#    a 12-lead campaign must not pay 7.81 GB for Lead-II bytes it never opens.
#
# 2. CAMPAIGNS 10 AND 11 WERE STAGING THE WRONG COHORT, found by deriving each
#    campaign's real reads from its configs instead of trusting this table.
#    Campaign 10's A5/B4 scan-like runs read the CLEAN container too, and it
#    staged none; campaign 11 trains A5/B4, which are not L3 tasks, against the
#    L3 subsets. Both would have died the same way the scan-like gap did.
#
# 3. CAMPAIGNS 5 AND 7 NOW READ THE FULL-COHORT 12-LEAD PIECES rather than
#    `signals_12lead_L3`. Measured, that subset is 35.35 GB resident, which put
#    campaign 7 at 40.5 GB and campaign 5 at 36.4 with 0.4 GB to spare. The
#    pieces are a superset, already cut and already uploaded, and cost 13.7 GB
#    for two. `signals_12lead_L3` is now UNUSED but deliberately kept in R2.
#
# 4. `signals_lead2` SPLIT IN TWO. Campaigns 12/13/14 read only the
#    preprocessed copy, and were staging the 6.08 GB raw file for nothing. The
#    two new dataset names point at files already in the bucket -- no upload.
#
# VAL ON DEMAND (`val_mode`). Campaigns 8 and 11 hold 27.4 GB of training data
# and need a further 15.1 GB of val containers; 42.5 GB against a 49 GB ceiling
# does not fit with checkpoints. They therefore stage the val split only at the
# epoch boundary: the trainer evicts the pieces, fetches `*__val.*`, validates,
# and drops it again (`_train_lib/trainer.py::_evaluate_val`). It costs one val
# fetch per epoch and buys 15 GB. Every other campaign keeps val resident and
# pays nothing.
#
# CHUNK CYCLING IS DECIDED PER RUN, NOT PER CAMPAIGN. `chunked=yes` only means
# the campaign stages pieces; `trainer.py` turns cycling on for a run only if
# that run actually reads a kind staged as pieces. Campaign 2 stages the clean
# 12-lead container WHOLE and the scan-like one as pieces, so A5/B4 cycle and
# A1/A3/A6 do not -- cycling a run that does not need it is not a slowdown, it
# is a different sampling regime, and nine runs were planned without it.
campaign_spec() {
    case "$1" in
        1)  echo "text_models|1.2|36|23|no|code configs tasks fiducials index text|1.2|resident" ;;
        2)  echo "images_12lead|27.9|15|14|yes|code configs tasks index images_clean_12lead images_scanlike_12lead_pieces images_scanlike_12lead_valtest|23.2|resident" ;;
        3)  echo "images_lead2|31.0|15|14|yes|code configs tasks index images_clean_lead2 images_scanlike_lead2_pieces images_scanlike_lead2_valtest|28.1|resident" ;;
        4)  echo "signals_lead2|15.6|78|8|no|code configs tasks index signals_lead2_preprocessed signals_lead2_raw signals_corrupted|15.6|resident" ;;
        5)  echo "signals_12lead_L3|22.7|12|6|yes|code configs tasks index signals_12lead_pieces signals_12lead_valtest|16.7|resident" ;;
        6)  echo "signals_12lead_full|22.7|18|10|yes|code configs tasks index signals_12lead_pieces signals_12lead_valtest|16.7|resident" ;;
        7)  echo "fusion_L3_12lead|26.8|18|20|yes|code configs tasks index text signals_12lead_pieces signals_12lead_valtest images_clean_12lead_L3|17.8|resident" ;;
        8)  echo "fusion_full_12lead|27.4|15|30|yes|code configs tasks index text signals_12lead_pieces images_clean_12lead_pieces images_scanlike_12lead_pieces signals_12lead_valtest images_clean_12lead_valtest images_scanlike_12lead_valtest|31.1|on_demand" ;;
        9)  echo "retrain_sweeps|12.7|30|25|yes|code configs tasks index text signals_raw_pieces signals_raw_valtest|9.6|resident" ;;
        # Campaign 10 TRAINS on scan-like images; it is not a re-testing sweep
        # (open question 17, closed 2026-09-30). §5.3 turns augmentation on
        # "only for scan-like training" and `model_configs.py` duly sets it,
        # exactly as B2's regime_2 is a trained corruption arm rather than a
        # test-time one; and these 30 runs are part of the 104 configs / 312
        # runs the spec counts. It therefore needs scan-like train+val, and is
        # SPLIT BY LAYOUT into 10 (12-lead) and 15 (Lead-II) -- one campaign
        # reading both is the 69 GB problem question 14 solved. It also reads
        # the CLEAN container, because its A5/B4 rows pick the rendering per
        # row; staging only scan-like is what question 16 fixed.
        10) echo "test_sweeps_12lead|27.9|15|6|yes|code configs tasks index images_clean_12lead images_scanlike_12lead_pieces images_scanlike_12lead_valtest|23.2|resident" ;;
        11) echo "final_eval_12lead|27.4|6|4|yes|code configs tasks index text results signals_12lead_pieces images_clean_12lead_pieces images_scanlike_12lead_pieces signals_12lead_valtest images_clean_12lead_valtest images_scanlike_12lead_valtest|31.1|on_demand" ;;
        12) echo "fusion_L3_lead2|27.7|18|20|no|code configs tasks index text signals_lead2_preprocessed images_clean_lead2|27.7|resident" ;;
        13) echo "fusion_full_lead2|24.3|15|30|yes|code configs tasks index text signals_lead2_preprocessed images_clean_lead2_pieces images_clean_lead2_valtest images_scanlike_lead2_pieces images_scanlike_lead2_valtest|20.0|resident" ;;
        14) echo "final_eval_lead2|24.3|6|4|yes|code configs tasks index text results signals_lead2_preprocessed images_clean_lead2_pieces images_clean_lead2_valtest images_scanlike_lead2_pieces images_scanlike_lead2_valtest|20.0|resident" ;;
        15) echo "test_sweeps_lead2|31.0|15|6|yes|code configs tasks index images_clean_lead2 images_scanlike_lead2_pieces images_scanlike_lead2_valtest|28.1|resident" ;;
        *)  return 1 ;;
    esac
}

N_CAMPAIGNS=15

campaign_field() { campaign_spec "$1" | cut -d'|' -f"$2"; }
campaign_name()      { campaign_field "$1" 1; }
campaign_resident()  { campaign_field "$1" 2; }
campaign_runs()      { campaign_field "$1" 3; }
campaign_hours()     { campaign_field "$1" 4; }
campaign_chunked()   { campaign_field "$1" 5; }
campaign_datasets()  { campaign_field "$1" 6; }
campaign_eval_gb()   { campaign_field "$1" 7; }
# `resident` keeps the val split staged for the whole run; `on_demand` stages it
# at each epoch boundary and drops it again. Only the campaigns that do not fit
# the other way pay the per-epoch transfer.
campaign_val_mode()  { campaign_field "$1" 8; }

# resident GB for one phase: train (train+val data) or eval (test data).
campaign_phase_gb() {
    # `resident_gb` is the PEAK of the training phase under this campaign's val
    # mode -- for an `on_demand` campaign that is the train-only working set,
    # and the val sub-phase is smaller by construction, so one number still
    # gates both.
    case "${2:-train}" in
        eval) campaign_eval_gb "$1" ;;
        test) campaign_test_gb "$1" ;;
        *)    campaign_resident "$1" ;;
    esac
}

# campaign_test_gb <n> -- what the `test` phase ADDS to a staged train phase:
# the `__test` file of each val/test container the campaign reads. MEASURED off
# R2 on 2026-10-14 (`rclone lsf -R --format ps`), in decimal GB, rounded up.
#
# WHY THIS PHASE EXISTS. `30_train.py` writes test predictions as the last step
# of every run, so the test split has to be on the node WHILE a campaign
# trains, not only afterwards. The train phase excludes `*__test.*`, and
# nothing noticed because the first campaigns read containers that hold every
# split in one file. A campaign whose test rows live in a `_valtest` container
# -- A5/B4's scan-like images in campaign 2 -- trains to convergence, some
# thirty hours a run, and then dies opening a test tar that was never fetched.
# `_campaign_body.sh` now stages this phase right after the train phase, so a
# campaign that cannot hold both is refused at its first minute instead.
campaign_test_gb() {
    local dataset total=0 gb
    for dataset in $(campaign_datasets "$1"); do
        case "$dataset" in
            images_scanlike_12lead_valtest) gb=12.6 ;;
            images_scanlike_lead2_valtest)  gb=7.9 ;;
            signals_12lead_valtest)         gb=15.7 ;;
            images_clean_12lead_valtest)    gb=1.8 ;;
            images_clean_lead2_valtest)     gb=3.6 ;;
            signals_raw_valtest)            gb=8.5 ;;
            *_valtest)
                echo "campaign_test_gb: no measured size for $dataset" >&2; return 1 ;;
            *) continue ;;
        esac
        total="$(awk -v a="$total" -v b="$gb" 'BEGIN { printf "%.1f", a + b }')"
    done
    printf '%s\n' "$total"
}

# ---------------------------------------------------------------------------
# disk accounting
# ---------------------------------------------------------------------------
# The README is explicit: measure with du on a COMPUTE node, not the login
# node, and not with `quota` (which reports the wrong thing here).
used_gb() {
    local total=0 path other resolved keep bytes
    local -a roots=()
    for path in "$PROJECT_ROOT" "$DATA_ROOT" "$RESULTS_ROOT"; do
        [ -d "$path" ] || continue
        resolved="$(cd "$path" 2>/dev/null && pwd -P)" || continue
        for other in ${roots[@]+"${roots[@]}"}; do
            [ "$other" = "$resolved" ] && { resolved=""; break; }
        done
        [ -n "$resolved" ] && roots+=("$resolved")
    done
    # Drop any root that lives INSIDE another, or du counts its bytes twice and
    # the ceiling is enforced against a number close to double the truth. That is
    # the DEFAULT layout, not a corner case: RESULTS_ROOT is $PROJECT_ROOT/outputs
    # unless overridden, and _campaign_body.sh only symlinks data/processed when
    # DATA_ROOT sits elsewhere -- so a node with no scratch, staging into
    # $PROJECT_ROOT/data/processed, measured every staged byte twice and would
    # have refused the 37.7 GB campaign against the 45 GB ceiling.
    # A DATA_ROOT reached through that symlink is NOT nested: du does not follow
    # symlinks, and `pwd -P` is what tells the two cases apart.
    for path in ${roots[@]+"${roots[@]}"}; do
        keep=1
        for other in ${roots[@]+"${roots[@]}"}; do
            [ "$path" = "$other" ] && continue
            case "$path/" in "$other"/*) keep=0; break ;; esac
        done
        [ $keep -eq 1 ] || continue
        bytes="$(du -sb "$path" 2>/dev/null | cut -f1)"
        total=$(( total + ${bytes:-0} ))
    done
    awk -v b="$total" 'BEGIN { printf "%.2f", b / 1073741824 }'
}

# One runnable check for the accounting above: nested roots counted once,
# separate roots both counted.   bash campaigns.sh selfcheck
used_gb_selfcheck() {
    local tmp; tmp="$(mktemp -d)"
    mkdir -p "$tmp/proj/outputs" "$tmp/proj/data/processed" "$tmp/elsewhere"
    head -c 10000000 /dev/zero > "$tmp/proj/outputs/a.bin"
    head -c 20000000 /dev/zero > "$tmp/proj/data/processed/b.bin"
    head -c 40000000 /dev/zero > "$tmp/elsewhere/c.bin"

    local got want rc=0
    got="$(PROJECT_ROOT="$tmp/proj" DATA_ROOT="$tmp/proj/data/processed"            RESULTS_ROOT="$tmp/proj/outputs" used_gb)"
    want="$(awk 'BEGIN { printf "%.2f", 30000000 / 1073741824 }')"
    [ "$got" = "$want" ] || {
        echo "FAIL nested: got $got want $want -- double counting is back" >&2; rc=1; }

    got="$(PROJECT_ROOT="$tmp/proj" DATA_ROOT="$tmp/elsewhere"            RESULTS_ROOT="$tmp/proj/outputs" used_gb)"
    want="$(awk 'BEGIN { printf "%.2f", 70000000 / 1073741824 }')"
    [ "$got" = "$want" ] || {
        echo "FAIL separate: got $got want $want -- a real root was dropped" >&2; rc=1; }

    rm -rf "$tmp"
    [ $rc -eq 0 ] && echo "used_gb self-check PASS"
    return $rc
}

# piece_ext <cut base> -- the file extension of a chunked cut's pieces, decided
# by name. Image cuts are tars, signal cuts are HDF5. Never infer it by trying a
# fetch: rclone exits 0 on a missing S3 key (job 25576).
piece_ext() {
    case "$1" in
        images_*)  echo tar ;;
        signals_*) echo h5 ;;
        *) echo "ERROR: no piece extension known for cut '$1'" >&2; return 1 ;;
    esac
}

# Every chunked cut any campaign stages, one per line.
chunked_bases() {
    local n dataset
    for n in $(seq 1 "$N_CAMPAIGNS"); do
        for dataset in $(campaign_datasets "$n"); do
            case "$dataset" in *_pieces) echo "${dataset%_pieces}" ;; esac
        done
    done | sort -u
}

# Every cut maps to an extension, and -- when rclone is reachable -- every
# piece key that mapping names is actually in the bucket. The second half is
# the check the `local` transport could never make.
piece_ext_selfcheck() {
    local base ext rc=0 listing n
    for base in $(chunked_bases); do
        ext="$(piece_ext "$base")" || { rc=1; continue; }
        if resolve_rclone 2>/dev/null; then
            listing="$("$RCLONE" lsf "$R2_DATA/chunks/$base/" 2>/dev/null)"
            n="$(printf '%s\n' "$listing" | grep -c "^piece_[0-9]*\.$ext\$")"
            if [ "$n" -eq 0 ]; then
                echo "FAIL $base: no piece_*.$ext under $R2_DATA/chunks/$base/" >&2; rc=1
            else
                echo "ok   $base: $n piece_*.$ext in R2"
            fi
        else
            echo "ok   $base -> .$ext (rclone not reachable; bucket not checked)"
        fi
    done
    [ $rc -eq 0 ] && echo "piece_ext self-check PASS"
    return $rc
}

# will_fit <additional_gb> -- true when used + additional stays under the ceiling
will_fit() {
    local additional="$1" used
    used="$(used_gb)"
    awk -v u="$used" -v a="$additional" -v c="$QUOTA_CEILING_GB" \
        'BEGIN { exit !(u + a <= c) }'
}

require_fit() {
    local additional="$1" label="$2" used
    used="$(used_gb)"
    if will_fit "$additional"; then
        printf 'quota OK: %.2f GB used + %s GB for %s <= %s GB ceiling\n' \
            "$used" "$additional" "$label" "$QUOTA_CEILING_GB"
        return 0
    fi
    cat >&2 <<MSG
REFUSING TO START (spec §8.1, §8.2 storage rule 6).
  $label needs about ${additional} GB.
  Currently used: ${used} GB across
      PROJECT_ROOT=$PROJECT_ROOT
      DATA_ROOT=$DATA_ROOT
      RESULTS_ROOT=$RESULTS_ROOT
  Ceiling: ${QUOTA_CEILING_GB} GB of a ${QUOTA_TOTAL_GB} GB quota.
  A refusal is always better than a job that dies at 90 %.
  Free space with:  scripts/dgx_portability/evict_data.sh --all
MSG
    return 1
}

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# ---------------------------------------------------------------------------
# eval bookkeeping -- one eval per (task, tier) at a time
# ---------------------------------------------------------------------------
# A campaign job submits an eval for every (task, tier) it touched, and a
# resubmitted or chained campaign job touches the finished ones again. Without
# a record, the second submission runs BESIDE the first and both write the same
# `.eval_checkpoints` file. `$STATE_DIR/evals/<task>__<tier>.jobs` lists the job
# ids ever queued for that eval; `.done` is written when one exits 0.
eval_marker() { printf '%s/evals/%s__%s' "$STATE_DIR" "$1" "$2"; }

# eval_in_flight <task> <tier> -- true while any recorded job is still queued
eval_in_flight() {
    local file id
    file="$(eval_marker "$1" "$2").jobs"
    [ -f "$file" ] || return 1
    while read -r id; do
        [ -n "$id" ] || continue
        if [ -n "$(squeue -h -j "$id" -o %i 2>/dev/null)" ]; then return 0; fi
    done < "$file"
    return 1
}

eval_record_job() {
    mkdir -p "$STATE_DIR/evals"
    printf '%s\n' "$3" >> "$(eval_marker "$1" "$2").jobs"
}

# campaign_complete <n> -- true when every run of the campaign has a complete
# run_summary.json. Needs a python that can import campaign_runs.py.
campaign_complete() {
    local task tier seed config summary listed=0
    while read -r task tier seed config; do
        [ -n "${task:-}" ] || continue
        listed=1
        summary="$RESULTS_ROOT/model_runs/$task/$tier/seed_$seed/run_summary.json"
        grep -q '"status": *"complete"' "$summary" 2>/dev/null || return 1
    done < <(python3 "$PROJECT_ROOT/scripts/dgx_portability/campaign_runs.py" "$1")
    [ "$listed" = "1" ]
}

# Sourced by every launcher; run directly only for the self-check.
if [ "${BASH_SOURCE[0]}" = "$0" ] && [ "${1:-}" = "selfcheck" ]; then
    used_gb_selfcheck && piece_ext_selfcheck
fi
