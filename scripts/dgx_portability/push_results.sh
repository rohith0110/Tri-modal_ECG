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
    # Names must match what 30_train.py writes. Until 2026-09-28 this list read
    # `threshold.json metrics.json` -- files the trainer never writes -- so
    # thresholds.json, run_summary.json and val_predictions.parquet (what the
    # thresholds and calibrators were fitted on) never left the DGX for any run.
    for artifact in test_predictions.parquet val_predictions.parquet \
                    train_log.jsonl checkpoint_best.pt train_config.yaml \
                    thresholds.json run_summary.json; do
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
            resolve_rclone && "$RCLONE" check "$staged" "$R2_RESULTS/$rel"                 --one-way >/dev/null 2>&1 || verified=0 ;;
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

# ---- the EVALUATION outputs -----------------------------------------------
# The loop above pushes per-RUN artifacts out of model_runs/. It never touched
# what 31_eval.py produces -- `outputs/results/<task>.csv` (the §7.1 table),
# `<task>_extras.json`, and the calibration figures -- so every evaluation
# result lived only on the DGX. That is the §8.0 rule ("no Phase 2 artifact may
# exist only on the DGX") broken for the one artifact the paper is actually
# made of, and it went unnoticed because "pushed N run(s), 0 failure(s)" reads
# like everything went.
#
# Nothing is deleted here: unlike a checkpoint, a results CSV is small and is
# rewritten in place by the next --arch-tier run of the same task.
if [ -d "$RESULTS_ROOT/results" ] || [ -d "$RESULTS_ROOT/figures" ]; then
    if resolve_rclone; then
        for what in results figures; do
            [ -d "$RESULTS_ROOT/$what" ] || continue
            log "pushing $what/"
            if "$RCLONE" copy --checksum --s3-no-check-bucket                     --exclude "_dev/**" --exclude ".eval_checkpoints/**"                     "$RESULTS_ROOT/$what" "$R2_RESULTS/$what"; then
                log "  $what/ pushed"
            else
                log "  PUSH FAILED for $what/"
                failed=$((failed + 1))
            fi
        done
    else
        log "cannot push $what/: rclone not resolvable"
        failed=$((failed + 1))
    fi
fi

# ---- audit reports and the eval checkpoints (backup only) -----------------
# 31_eval.py writes audit_reports/threshold_audit.md, and its resumable
# checkpoints hold days of bootstrap work per (task, tier). Both lived only on
# the DGX. The checkpoints go to their own prefix, never into results/, so a
# half-finished eval can never be mistaken for a result. A jsonl being appended
# to mid-copy is fine for a backup: resume re-runs only units it lacks.
if resolve_rclone; then
    for pair in "audit_reports:audit_reports" \
                "results/.eval_checkpoints:eval_checkpoints_backup"; do
        src="$RESULTS_ROOT/${pair%%:*}"; dst="${pair##*:}"
        [ -d "$src" ] || continue
        log "pushing ${pair%%:*}/ -> $dst/"
        if "$RCLONE" copy --checksum --s3-no-check-bucket "$src" "$R2_RESULTS/$dst"; then
            log "  $dst/ pushed"
        else
            log "  PUSH FAILED for $dst/"
            failed=$((failed + 1))
        fi
    done
fi

date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE_DIR/last_push"
log "pushed $pushed run(s), $failed failure(s). Used: $(used_gb) GB of ${QUOTA_CEILING_GB} GB."
[ "$failed" -eq 0 ] || exit 1
