#!/usr/bin/env bash
# Push a finished run's artifacts off-node, then delete the local checkpoints.
#
#   ./push_results.sh                          # every completed run found
#   ./push_results.sh outputs/model_runs/A2_.../signal_lead2_seed42
#   ./push_results.sh --keep-checkpoints       # push, delete nothing
#
# Spec §8.1 checkpoint retention: on run completion, push `checkpoint_best.pt`
# + `test_predictions.parquet` + `train_log.jsonl` off-node, then DELETE both
# local checkpoint files. Nothing accumulates -- 144 runs at ~2.4 GB would be
# 20x the whole quota.
#
# The deletion is deliberately ordered: verify the push landed, THEN delete.
# A failed push leaves the checkpoints exactly where they were.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=campaigns.sh
. "$HERE/campaigns.sh"

KEEP=0
TARGETS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --keep-checkpoints) KEEP=1; shift ;;
        *) TARGETS+=("$1"); shift ;;
    esac
done

# A run is "complete" when it has predictions. checkpoint_last.pt without
# predictions means the job is still going -- pushing that would race the
# trainer's next atomic write.
if [ ${#TARGETS[@]} -eq 0 ]; then
    while IFS= read -r predictions; do
        TARGETS+=("$(dirname "$predictions")")
    done < <(find "$RESULTS_ROOT/model_runs" -name 'test_predictions.parquet' 2>/dev/null)
fi

if [ ${#TARGETS[@]} -eq 0 ]; then
    log "no completed runs found under $RESULTS_ROOT/model_runs"
    exit 0
fi

log "transport=$(transport); ${#TARGETS[@]} completed run(s) to push"
mkdir -p "$STATE_DIR"

pushed=0
failed=0
for run_dir in "${TARGETS[@]}"; do
    [ -d "$run_dir" ] || { log "skip (not a directory): $run_dir"; continue; }
    rel="${run_dir#"$RESULTS_ROOT"/}"
    log "=== $rel ==="

    if [ ! -f "$run_dir/test_predictions.parquet" ]; then
        log "  skip: no test_predictions.parquet -- run is not complete"
        continue
    fi

    staged="$(mktemp -d)"
    for artifact in test_predictions.parquet train_log.jsonl checkpoint_best.pt \
                    train_config.yaml threshold.json metrics.json; do
        [ -f "$run_dir/$artifact" ] && cp "$run_dir/$artifact" "$staged/"
    done

    if ! push "$staged/." "$rel"; then
        log "  PUSH FAILED -- local files left untouched"
        rm -rf "$staged"
        failed=$((failed + 1))
        continue
    fi

    # Verify the push before deleting anything. With rclone, `check` compares
    # checksums against the remote; with a local transport, compare sizes.
    verified=1
    case "$(transport)" in
        rclone|rclone-offline)
            rclone check "$staged" "$R2_RESULTS/$rel" --one-way >/dev/null 2>&1 || verified=0 ;;
        local)
            for artifact in "$staged"/*; do
                remote="$TRIMODAL_RESULTS_DEST/$rel/$(basename "$artifact")"
                [ -f "$remote" ] && [ "$(stat -c%s "$artifact")" = "$(stat -c%s "$remote")" ] \
                    || verified=0
            done ;;
    esac
    rm -rf "$staged"

    if [ "$verified" -ne 1 ]; then
        log "  PUSH VERIFY FAILED -- local files left untouched"
        failed=$((failed + 1))
        continue
    fi
    log "  push verified"
    pushed=$((pushed + 1))

    if [ "$KEEP" -eq 1 ]; then
        log "  --keep-checkpoints: leaving local files in place"
        continue
    fi
    # §8.1: delete BOTH local checkpoints once the push is verified.
    for checkpoint in checkpoint_best.pt checkpoint_last.pt; do
        if [ -f "$run_dir/$checkpoint" ]; then
            size=$(du -h "$run_dir/$checkpoint" | cut -f1)
            rm -f "$run_dir/$checkpoint"
            log "  deleted $checkpoint ($size reclaimed)"
        fi
    done
done

date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE_DIR/last_push"
log "pushed $pushed run(s), $failed failure(s). Used: $(used_gb) GB of ${QUOTA_CEILING_GB} GB."
[ "$failed" -eq 0 ] || exit 1
