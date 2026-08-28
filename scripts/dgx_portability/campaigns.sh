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
resolve_data_root() {
    if [ -n "${DATA_ROOT:-}" ]; then
        printf '%s\n' "$DATA_ROOT"
        return
    fi
    local candidate
    for candidate in "${SCRATCH:-}" "/scratch/$USER" "/raid/$USER" "/work/$USER" \
                     "/tmp/$USER"; do
        [ -n "$candidate" ] || continue
        if mkdir -p "$candidate/trimodal-data" 2>/dev/null \
           && [ -w "$candidate/trimodal-data" ]; then
            printf '%s\n' "$candidate/trimodal-data"
            return
        fi
    done
    printf '%s\n' "$HOME/trimodal-data"
}

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/trimodal}"
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
fetch() {
    local rel="$1" dest="$2"
    mkdir -p "$dest"
    case "$(transport)" in
        local)
            [ -e "$TRIMODAL_SOURCE/$rel" ] || {
                echo "ERROR: $TRIMODAL_SOURCE/$rel not found" >&2; return 1; }
            cp -r "$TRIMODAL_SOURCE/$rel" "$dest/"
            ;;
        rclone|rclone-offline)
            rclone copy --progress --transfers 4 --checksum \
                "$R2_DATA/$rel" "$dest/$(basename "$rel")" \
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
campaign_spec() {
    case "$1" in
        1)  echo "text_models|3|21|23|no|code configs tasks fiducials index text" ;;
        2)  echo "images_12lead|12|21|14|no|code configs tasks index images_clean_12lead" ;;
        3)  echo "images_lead2|21|21|14|no|code configs tasks index images_clean_lead2" ;;
        4)  echo "signals_lead2|8|33|8|no|code configs tasks index signals_lead2 signals_corrupted" ;;
        5)  echo "signals_12lead_L3|27|12|6|no|code configs tasks index signals_12lead_L3" ;;
        6)  echo "signals_12lead_full|30|18|10|yes|code configs tasks index signals_12lead_pieces" ;;
        7)  echo "fusion_L3|32|9|20|no|code configs tasks index text signals_12lead_L3 images_clean_12lead_L3" ;;
        8)  echo "fusion_full|33|12|30|yes|code configs tasks index text signals_12lead_pieces images_clean_12lead_pieces" ;;
        9)  echo "retrain_sweeps|30|30|25|yes|code configs tasks index signals_raw_pieces text" ;;
        10) echo "test_sweeps|20|0|6|no|code configs tasks index images_scanlike_test signals_corrupted" ;;
        11) echo "final_eval|5|0|4|no|code configs results" ;;
        *)  return 1 ;;
    esac
}

campaign_field() { campaign_spec "$1" | cut -d'|' -f"$2"; }
campaign_name()      { campaign_field "$1" 1; }
campaign_resident()  { campaign_field "$1" 2; }
campaign_runs()      { campaign_field "$1" 3; }
campaign_hours()     { campaign_field "$1" 4; }
campaign_chunked()   { campaign_field "$1" 5; }
campaign_datasets()  { campaign_field "$1" 6; }

# ---------------------------------------------------------------------------
# disk accounting
# ---------------------------------------------------------------------------
# The README is explicit: measure with du on a COMPUTE node, not the login
# node, and not with `quota` (which reports the wrong thing here).
used_gb() {
    local total=0 path
    for path in "$PROJECT_ROOT" "$DATA_ROOT" "$RESULTS_ROOT"; do
        [ -d "$path" ] || continue
        total=$(( total + $(du -sb "$path" 2>/dev/null | cut -f1) ))
    done
    awk -v b="$total" 'BEGIN { printf "%.2f", b / 1073741824 }'
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
