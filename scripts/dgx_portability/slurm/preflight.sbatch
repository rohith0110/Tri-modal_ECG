#!/usr/bin/env bash
#SBATCH --job-name=trimodal_preflight
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=08:00:00
#SBATCH --output=trimodal_preflight_%j.out
#SBATCH --error=trimodal_preflight_%j.err
#
# Run every config of one campaign END TO END on a few thousand rows, before
# the campaign is left to run unattended:
#
#   sbatch --partition=gpu_student --gres=gpu:a100_4g.20gb:1 \
#          --export=ALL,CAMPAIGN=4 preflight.sbatch
#
# For each (task, tier) it trains seed 42 for EPOCHS epochs on LIMIT_ROWS rows
# per split, validates, and writes test predictions -- the whole path a real
# run takes, under the same environment `_campaign_body.sh` sets, including
# chunk cycling: on a chunked campaign every window of every epoch swaps pieces
# for real. Then one config is killed part-way and started again, to prove the
# resume a 7-day TIMEOUT depends on.
#
# Nothing here is a result. Outputs go to outputs/preflight/, which
# push_results.sh never looks at, and the checkpoints are deleted at the end.
set -uo pipefail

: "${CAMPAIGN:?set CAMPAIGN=<n>}"
LIMIT_ROWS="${LIMIT_ROWS:-4000}"
EPOCHS="${EPOCHS:-2}"
RESUME_ROWS="${RESUME_ROWS:-60000}"      # rows per split for the resume test: enough that TERM lands mid-training
KILL_AFTER="${KILL_AFTER:-150}"          # seconds before the resume test sends TERM
RESUME_ROWS="${RESUME_ROWS:-60000}"      # rows per split for the resume test: enough that TERM lands mid-training

export PROJECT_ROOT="${TRIMODAL_HOME:-$HOME/se23ucse027}"
HERE="$PROJECT_ROOT/scripts/dgx_portability"
cd "$PROJECT_ROOT"
# shellcheck disable=SC1091
. "$PROJECT_ROOT/ecg_env/bin/activate"
export R2_RESULTS="${R2_RESULTS:-r2-results:trimodal-results}"
# shellcheck source=../campaigns.sh
. "$HERE/campaigns.sh"
set +e

# ---- the environment _campaign_body.sh gives a real run ---------------------
export CAMPAIGN TOKENIZERS_PARALLELISM=false
export TRIMODAL_SIGNAL_INT16="${TRIMODAL_SIGNAL_INT16:-1}"
if [ -d "${HF_HOME:-$HOME/.cache/huggingface}/hub/models--emilyalsentzer--Bio_ClinicalBERT" ]; then
    export HF_HUB_OFFLINE=1
fi
CHUNKED="$(campaign_chunked "$CAMPAIGN")"
VAL_MODE="$(campaign_val_mode "$CAMPAIGN")"
TRAIN_PHASE=train
if [ "$VAL_MODE" = "on_demand" ]; then TRAIN_PHASE=train_only; export TRIMODAL_VAL_ON_DEMAND=1; fi

log "=== preflight campaign $CAMPAIGN ($(campaign_name "$CAMPAIGN")) on $(hostname), job ${SLURM_JOB_ID:-none}, account $(id -un) ==="
log "limit_rows=$LIMIT_ROWS epochs=$EPOCHS chunked=$CHUNKED val_mode=$VAL_MODE ceiling=${QUOTA_CEILING_GB} GB results=$R2_RESULTS"
# An empty data root first: the quota gate counts what is already on disk on
# top of this campaign.
"$HERE/evict_data.sh" --all || log "eviction refused; the quota gate decides"
if [ "$CHUNKED" = "yes" ]; then
    "$HERE/stage_data.sh" "$CAMPAIGN" --phase "$TRAIN_PHASE" --pieces 0 1 || { log "STAGING FAILED"; exit 1; }
    export TRIMODAL_CHUNKED=1 TRIMODAL_CHUNK_PIECES="${TRIMODAL_CHUNK_PIECES:-8}"
else
    "$HERE/stage_data.sh" "$CAMPAIGN" --phase "$TRAIN_PHASE" || { log "STAGING FAILED"; exit 1; }
fi
# The test split too, exactly as the body stages it.
if [ "$(campaign_test_gb "$CAMPAIGN")" != "0" ]; then
    "$HERE/stage_data.sh" "$CAMPAIGN" --phase test || { log "TEST-PHASE STAGING FAILED"; exit 1; }
fi

TRAIN="$PROJECT_ROOT/scripts/phase2_tasks_benchmark_and_paper/30_train.py"
OUT="$PROJECT_ROOT/outputs/preflight/c$CAMPAIGN"
rm -rf "$OUT"; mkdir -p "$OUT"
SUMMARY="$OUT/summary.tsv"
printf 'result\ttask\ttier\tseconds\tswaps\tpeak_gpu_gb\tnote\n' > "$SUMMARY"

# one_run <label> <config> <outdir> [extra args...] -> exit status of the trainer
one_run() {
    local config="$1" outdir="$2"; shift 2
    python3 "$TRAIN" --model-config "$PROJECT_ROOT/config/model_configs/$config" --seed 42 \
        --output-dir "$outdir" --epochs "$EPOCHS" --limit-rows "$ROWS" \
        --checkpoint-minutes 1 "$@" > "$outdir.log" 2>&1
}
verdict() {      # <task> <tier> <outdir> <seconds> <note>
    local task="$1" tier="$2" outdir="$3" seconds="$4" note="$5" result=FAIL swaps peak
    if [ -f "$outdir/test_predictions.parquet" ] \
       && grep -q '"status": *"complete"' "$outdir/run_summary.json" 2>/dev/null; then
        result=PASS
    fi
    swaps="$(grep -c 'chunk cycle: bash .*stage_data.sh' "$outdir.log" 2>/dev/null || true)"
    peak="$(grep -o '"peak_gpu_gb": *[0-9.]*' "$outdir/train_log.jsonl" 2>/dev/null | tail -1 | grep -o '[0-9.]*$' || true)"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$result" "$task" "$tier" "$seconds" "${swaps:-0}" "${peak:--}" "$note" >> "$SUMMARY"
    log "$result  $task / $tier  ${seconds}s  swaps=${swaps:-0} peak_gpu_gb=${peak:--}  $note"
    if [ "$result" = "FAIL" ]; then
        tr '\r' '\n' < "$outdir.log" | grep -v '^$' | tail -25 | sed 's/^/    | /'
        return 1
    fi
}

failures=0
ROWS="$LIMIT_ROWS"
resume_config=""; resume_task=""; resume_tier=""
while read -r task tier seed config; do
    [ "${seed:-}" = "42" ] || continue
    outdir="$OUT/$task/$tier"; mkdir -p "$(dirname "$outdir")"
    started=$SECONDS
    one_run "$config" "$outdir" --force-restart
    verdict "$task" "$tier" "$outdir" "$((SECONDS - started))" "" || failures=$((failures + 1))
    # Resume is tested on the last config that cycled, or failing that the last one.
    if [ -z "$resume_config" ] || grep -q 'chunk cycling ON' "$outdir.log" 2>/dev/null \
       || ! grep -q 'chunk cycling ON' "$OUT/$resume_task/$resume_tier.log" 2>/dev/null; then
        resume_config="$config"; resume_task="$task"; resume_tier="$tier"
    fi
    rm -f "$outdir"/checkpoint_*.pt
done < <(python3 "$HERE/campaign_runs.py" "$CAMPAIGN" ${PREFLIGHT_TASKS:+--tasks $PREFLIGHT_TASKS})

# ---- kill it part-way, start it again ---------------------------------------
if [ -n "$resume_config" ]; then
    outdir="$OUT/_resume/$resume_task/$resume_tier"; mkdir -p "$(dirname "$outdir")"
    ROWS="$RESUME_ROWS"
    log "resume test on $resume_task / $resume_tier ($ROWS rows): TERM after ${KILL_AFTER}s, then start again"
    started=$SECONDS
    timeout -s TERM -k 60 "$KILL_AFTER" python3 "$TRAIN" \
        --model-config "$PROJECT_ROOT/config/model_configs/$resume_config" --seed 42 \
        --output-dir "$outdir" --epochs "$EPOCHS" --limit-rows "$ROWS" \
        --checkpoint-minutes 1 --force-restart > "$outdir.first.log" 2>&1
    first_rc=$?
    ls "$outdir"/checkpoint_last.pt >/dev/null 2>&1 && had_checkpoint=yes || had_checkpoint=no
    one_run "$resume_config" "$outdir"
    resumed=no; grep -qi 'resum' "$outdir.log" 2>/dev/null && resumed=yes
    verdict "$resume_task" "$resume_tier" "$outdir" "$((SECONDS - started))" \
        "RESUME TEST: first exit $first_rc, checkpoint_last=$had_checkpoint, second run resumed=$resumed" \
        || failures=$((failures + 1))
    if [ "$had_checkpoint" != "yes" ] || [ "$resumed" != "yes" ]; then
        log "RESUME TEST INCONCLUSIVE: the killed run left checkpoint_last=$had_checkpoint and the second run resumed=$resumed"
        grep -i 'resum\|checkpoint\|signal' "$outdir.first.log" "$outdir.log" | tail -8 | sed 's/^/    | /'
    fi
    rm -f "$outdir"/checkpoint_*.pt
fi

log "=== preflight campaign $CAMPAIGN: $failures failure(s) ==="
column -t -s "$(printf '\t')" "$SUMMARY" 2>/dev/null || cat "$SUMMARY"
log "Used: $(used_gb) GB of ${QUOTA_CEILING_GB} GB"
[ "$failures" -eq 0 ]
