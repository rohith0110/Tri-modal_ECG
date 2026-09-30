#!/usr/bin/env bash
# Wipe the current campaign's data AFTER its results are pushed (spec §8.2).
#
#   ./evict_data.sh                  # evict the campaign named in state
#   ./evict_data.sh --pieces 0       # evict just these pieces (chunk cycling)
#   ./evict_data.sh --pieces-all     # every piece + its overlays (phase swap)
#   ./evict_data.sh --all            # everything under DATA_ROOT
#   ./evict_data.sh --force          # skip the unpushed-results guard
#
# Storage rule 2: one campaign's data at a time, wipe before loading the next.
# Storage rule 5: the DGX never holds the only copy of anything -- so this
# refuses to delete while results are still sitting locally unpushed, unless
# you override it deliberately.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=campaigns.sh
. "$HERE/campaigns.sh"

MODE="campaign"
PIECES=()
SPLIT=""
FORCE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --all) MODE="all"; shift ;;
        --force) FORCE=1; shift ;;
        --pieces) MODE="pieces"; shift
                  while [ $# -gt 0 ] && [ "${1#-}" = "$1" ]; do PIECES+=("$1"); shift; done ;;
        # Every piece of every chunked base, and the overlays that point at
        # them: what the campaign body runs between the train and eval phases.
        --pieces-all) MODE="pieces_all"; shift ;;
        # Drop one split's staged containers -- what the val swap does after it
        # has validated, so the next epoch's pieces have room to land.
        --split) MODE="split"; shift; SPLIT="${1:-}"; shift ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

# ---- guard: never evict data whose results have not left the node ---------
# Deleting inputs is cheap to undo (re-stage); deleting the only copy of a
# result is not. This checks the expensive direction.
if [ "$FORCE" -ne 1 ] && [ -d "$RESULTS_ROOT/model_runs" ]; then
    # A result is unpushed when it is NEWER than the last-push marker, i.e. it
    # was produced after the most recent successful push. With no marker at all,
    # nothing has ever been pushed, so every result counts.
    if [ -f "$STATE_DIR/last_push" ]; then
        unpushed=$(find "$RESULTS_ROOT/model_runs" -name 'test_predictions.parquet' \
                        -newer "$STATE_DIR/last_push" 2>/dev/null | wc -l || echo 0)
    else
        unpushed=$(find "$RESULTS_ROOT/model_runs" -name 'test_predictions.parquet' \
                        2>/dev/null | wc -l || echo 0)
    fi
    if [ "$unpushed" -gt 0 ]; then
        cat >&2 <<MSG
REFUSING: $unpushed prediction file(s) under $RESULTS_ROOT/model_runs have not
been pushed since the last recorded push (storage rule 5 -- the DGX never holds
the only copy of anything). Push first:
    $HERE/push_results.sh
Then re-run, or override with --force if you know they are already safe.
MSG
        exit 1
    fi
fi

before="$(used_gb)"

case "$MODE" in
    all)
        log "evicting ALL staged data under $DATA_ROOT"
        rm -rf "${DATA_ROOT:?}"/*
        rm -f "$STATE_DIR/current_campaign" "$STATE_DIR/current_pieces"
        ;;
    pieces)
        [ ${#PIECES[@]} -gt 0 ] || { echo "--pieces needs at least one index" >&2; exit 2; }
        for piece in "${PIECES[@]}"; do
            printf -v padded 'piece_%03d' "$piece"
            log "evicting $padded"
            find "$DATA_ROOT" -name "$padded.*" -delete 2>/dev/null || true
        done
        ;;
    split)
        [ -n "$SPLIT" ] || { echo "--split needs train, val or test" >&2; exit 2; }
        log "evicting every staged *__${SPLIT}.* container"
        find "$DATA_ROOT" -name "*__${SPLIT}.*" -delete 2>/dev/null || true
        ;;
    pieces_all)
        log "evicting every staged chunk piece under $DATA_ROOT"
        find "$DATA_ROOT" -name 'piece_*' -delete 2>/dev/null || true
        # A stale overlay would still name a piece that is gone, and the read
        # would fail with a missing file rather than fall back to the base
        # container -- so the pointer goes with the bytes.
        find "$DATA_ROOT/manifest_overlays" -name 'pieces_*.parquet' -delete 2>/dev/null || true
        rm -f "$STATE_DIR/current_pieces"
        ;;
    campaign)
        campaign="$(cat "$STATE_DIR/current_campaign" 2>/dev/null || true)"
        if [ -z "$campaign" ]; then
            echo "no current campaign recorded; use --all to wipe everything" >&2
            exit 1
        fi
        log "evicting campaign $campaign ($(campaign_name "$campaign"))"
        for dataset in $(campaign_datasets "$campaign"); do
            target="$DATA_ROOT/${dataset%_pieces}"
            [ -e "$target" ] || continue
            log "  rm -rf $target"
            rm -rf "$target"
        done
        rm -f "$STATE_DIR/current_campaign" "$STATE_DIR/current_pieces"
        ;;
esac

log "evicted. Used: $before GB -> $(used_gb) GB (ceiling ${QUOTA_CEILING_GB} GB)."
