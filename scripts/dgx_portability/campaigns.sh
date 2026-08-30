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
# quota
# ---------------------------------------------------------------------------
# §8.0: 50 GB total. §8.1/§8.2: refuse to start above 45 GB.
QUOTA_TOTAL_GB="${QUOTA_TOTAL_GB:-50}"
QUOTA_CEILING_GB="${QUOTA_CEILING_GB:-45}"

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

# The DGX account is shared, so everything this project writes goes in ONE
# folder named after the roll number -- nobody has to guess whose files these
# are. Override PROJECT_FOLDER (or PROJECT_ROOT outright) for another account.
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

have_rclone() { command -v rclone >/dev/null 2>&1; }

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
phase_excludes() {
    if [ "${1:-train}" = "eval" ]; then
        printf '%s\n' "--exclude" "*__train.*" "--exclude" "*__val.*"
    else
        printf '%s\n' "--exclude" "*__test.*"
    fi
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
                              if [ "$phase" != "eval" ]; then take=0; fi ;;
                          *__train.*|*__val.*)
                              if [ "$phase" = "eval" ]; then take=0; fi ;;
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
            rclone copy --progress --transfers 4 --checksum "${excludes[@]}" \
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
            rclone copy --progress --checksum "$src" "$R2_RESULTS/$rel" \
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
# AMENDED 2026-08-29 (Step 6, then open questions 14 and 15b). Every number
# below is measured off the files on disk, not estimated, and every dataset list
# is what that campaign's model configs actually read.
#
#   campaign_spec <n> -> "name|resident_gb|runs|gpu_hours|chunked|datasets|eval_gb"
#
# TWO PHASES, because a campaign does not need its test split while it trains.
# `resident_gb` is the TRAIN phase (train + val data); `eval_gb` is the EVAL
# phase (test data), staged after the training runs finish and the train pieces
# are evicted. stage_data.sh --phase picks one, and filters by the `__<split>.`
# suffix the derived containers carry, so no dataset had to be split in two.
# Without this campaigns 5, 7 and 8 exceed the 45 GB ceiling on paper while
# never actually needing that much at once.
#
# THE LEAD-II SPLIT (open question 14). Campaigns 7, 8 and 11 read a whole lead
# set each, and their configs cover both, which put campaign 7 at 69 GB. They
# are now split by lead subset: 7/8/11 are the 12-lead halves, 12/13/14 the
# Lead-II ones. campaign_runs.py routes by lead subset to match. No config was
# renamed, no run dropped, no seed dropped -- --table still reports 104 configs
# and 312 runs.
#
# VAL/TEST FOR THE CHUNKED CAMPAIGNS (open question 15b). Pieces are cut from
# TRAIN only, so 6, 8 and 9 had no val split to early-stop on and no test split
# to evaluate. MEASURED: 12-lead int16 is 101.6 KiB/study (val 7.3 GiB, test
# 14.5 GiB), clean 12-lead images 11.7 KiB/study (0.84 / 1.67 GiB), raw 12-lead
# float32 88.5 KiB/study (6.4 / 12.6 GiB). All of that fits alongside two
# resident pieces, so val and test are staged as PLAIN datasets and NOTHING
# extra is chunked.
campaign_spec() {
    case "$1" in
        1)  echo "text_models|1.1|36|23|no|code configs tasks fiducials index text|1.1" ;;
        2)  echo "images_12lead|9.4|15|14|no|code configs tasks index images_clean_12lead|9.4" ;;
        3)  echo "images_lead2|17.6|15|14|no|code configs tasks index images_clean_lead2|17.6" ;;
        4)  echo "signals_lead2|13.6|78|8|no|code configs tasks index signals_lead2 signals_corrupted|13.6" ;;
        5)  echo "signals_12lead_L3|33.9|12|6|no|code configs tasks index signals_12lead_L3|9.2" ;;
        6)  echo "signals_12lead_full|21.0|18|10|yes|code configs tasks index signals_12lead_pieces signals_12lead_valtest|15.5" ;;
        7)  echo "fusion_L3_12lead|37.7|18|20|no|code configs tasks index text signals_12lead_L3 images_clean_12lead_L3|10.2" ;;
        8)  echo "fusion_full_12lead|23.4|15|30|yes|code configs tasks index text signals_12lead_pieces images_clean_12lead_pieces signals_12lead_valtest images_clean_12lead_valtest|17.2" ;;
        9)  echo "retrain_sweeps|18.5|30|25|yes|code configs tasks index text signals_raw_pieces signals_raw_valtest|13.7" ;;
        10) echo "test_sweeps|20.8|30|6|no|code configs tasks index images_scanlike_test signals_corrupted|20.8" ;;
        11) echo "final_eval_12lead|12.2|6|4|no|code configs tasks index text results signals_12lead_L3 images_clean_12lead_L3|12.2" ;;
        12) echo "fusion_L3_lead2|29.4|18|20|no|code configs tasks index text signals_lead2 images_clean_lead2|29.4" ;;
        13) echo "fusion_full_lead2|29.4|15|30|no|code configs tasks index text signals_lead2 images_clean_lead2|29.4" ;;
        14) echo "final_eval_lead2|31.4|6|4|no|code configs tasks index text results signals_lead2 images_clean_lead2|31.4" ;;
        *)  return 1 ;;
    esac
}

N_CAMPAIGNS=14

campaign_field() { campaign_spec "$1" | cut -d'|' -f"$2"; }
campaign_name()      { campaign_field "$1" 1; }
campaign_resident()  { campaign_field "$1" 2; }
campaign_runs()      { campaign_field "$1" 3; }
campaign_hours()     { campaign_field "$1" 4; }
campaign_chunked()   { campaign_field "$1" 5; }
campaign_datasets()  { campaign_field "$1" 6; }
campaign_eval_gb()   { campaign_field "$1" 7; }

# resident GB for one phase: train (train+val data) or eval (test data).
campaign_phase_gb() {
    if [ "${2:-train}" = "eval" ]; then campaign_eval_gb "$1"; else campaign_resident "$1"; fi
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

# Sourced by every launcher; run directly only for the self-check.
if [ "${BASH_SOURCE[0]}" = "$0" ] && [ "${1:-}" = "selfcheck" ]; then
    used_gb_selfcheck
fi
