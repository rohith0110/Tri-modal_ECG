#!/usr/bin/env bash
# Shared body for every campaign_<n>.sbatch. Sourced, not executed.
# The per-campaign file sets CAMPAIGN (and optionally PIECES) and sources this.
#
# NOTHING HERE ASSUMES A VERIFIED DGX. Step 7 has not run, so:
#   * no `module load` is hard-coded -- the environment is detected;
#   * no container runtime is required;
#   * the GPU count comes from Slurm, never from a literal (§8.1);
#   * an absent piece-cycling loop degrades to a single-piece run.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The DGX holds two least-privilege tokens, not one all-buckets token: reading
# trimodal-data is READ-ONLY there, so no script running on the cluster can
# damage the staged data, and writing results needs a separate remote. The
# laptop keeps a single all-buckets remote, so this default only moves here --
# campaigns.sh still defaults R2_RESULTS to r2:trimodal-results for the laptop.
export R2_RESULTS="${R2_RESULTS:-r2-results:trimodal-results}"

# shellcheck source=../campaigns.sh
. "$HERE/campaigns.sh"

NAME="$(campaign_name "$CAMPAIGN")"
CHUNKED="$(campaign_chunked "$CAMPAIGN")"
log "=== campaign $CAMPAIGN ($NAME) on $(hostname) ==="
log "job=${SLURM_JOB_ID:-none} gpus=${SLURM_GPUS_ON_NODE:-unknown} cpus=${SLURM_CPUS_PER_TASK:-unknown}"

# ---- python environment, detected not assumed ------------------------------
# Order of preference: an already-active venv, a project venv, a conda env, a
# module, then bare python3. Each is checked for torch before being accepted.
activate_python() {
    local candidate
    for candidate in "${VIRTUAL_ENV:-}/bin/activate" "$PROJECT_ROOT/ecg_env/bin/activate" \
                     "$HOME/ecg_env/bin/activate"; do
        [ -n "$candidate" ] && [ -f "$candidate" ] || continue
        # shellcheck disable=SC1090
        . "$candidate"
        if python3 -c 'import torch' 2>/dev/null; then
            log "python: $candidate"
            return 0
        fi
    done
    if command -v module >/dev/null 2>&1; then
        # Never hard-code a module name -- take whatever pytorch module exists.
        local mod
        mod="$(module avail 2>&1 | tr ' ' '\n' | grep -i -m1 '^pytorch' || true)"
        if [ -n "$mod" ]; then
            module load "$mod" 2>/dev/null || true
            python3 -c 'import torch' 2>/dev/null && { log "python: module $mod"; return 0; }
        fi
    fi
    if python3 -c 'import torch' 2>/dev/null; then
        log "python: system python3"
        return 0
    fi
    echo "ERROR: no python with torch found. Checked venvs, modules and system python3." >&2
    echo "       Run the Step 7 survey and record what this node actually has." >&2
    return 1
}
activate_python

log "torch: $(python3 -c 'import torch; print(torch.__version__, torch.cuda.is_available())')"

# ---- HuggingFace: no forked parallelism, no Hub calls once cached ----------
# Campaign 1's first run (job 22336) hung dead at batch 1 of 8218: the main
# process and all four DataLoader workers sat in futex_wait with 15 seconds of
# CPU between them across ten minutes. The last thing in the log is the Hub
# being called -- transformers 5.x asks for /discussions and /commits/refs
# while resolving a model, and each forked worker then re-resolves the
# tokenizer itself.
#
# TOKENIZERS_PARALLELISM=false: the Rust tokenizer's thread pool does not
# survive a fork, and a tokenizer touched before the fork deadlocks the child.
# The DataLoader forks its workers, so this must be set before python starts.
#
# HF_HUB_OFFLINE=1, but only once the model is actually in the cache: a warm
# cache needs no network at all, and every Hub round trip inside a worker is a
# chance to hang on a box whose outbound path is not guaranteed. If the model
# is not cached yet, stay online so the first run can fetch it.
export TOKENIZERS_PARALLELISM=false
HF_MODEL_CACHE="${HF_HOME:-$HOME/.cache/huggingface}/hub/models--emilyalsentzer--Bio_ClinicalBERT"
if [ -d "$HF_MODEL_CACHE" ]; then
    export HF_HUB_OFFLINE=1
    log "huggingface: cache warm, HF_HUB_OFFLINE=1"
else
    log "huggingface: cache cold, staying online for the first fetch"
fi

# ---- stage ----------------------------------------------------------------
# The refusal gate lives in stage_data.sh and runs before any byte moves.
#
# SHARDING. TRIMODAL_TASKS splits one campaign across several GPUs, each job
# taking whole tasks (see campaign_runs.py --tasks). Concurrent shards would
# otherwise fetch the same files into the same paths at the same time, so every
# staging call takes an exclusive lock: the first shard stages and verifies,
# the rest wait a few seconds and then find their data already resident and
# checksum-clean. Nothing else in the campaign needs coordination -- runs are
# disjoint, and push_results.sh only frees a checkpoint once its run has
# predictions, so no shard can delete what another still needs.
STAGE_LOCK="$PROJECT_ROOT/.campaign_state/stage.lock"
mkdir -p "$(dirname "$STAGE_LOCK")"
stage() {
    if command -v flock >/dev/null 2>&1; then
        flock "$STAGE_LOCK" "$HERE/stage_data.sh" "$@"
    else
        "$HERE/stage_data.sh" "$@"
    fi
}
if [ -n "${TRIMODAL_TASKS:-}" ]; then
    log "shard: this job runs only tasks -- $TRIMODAL_TASKS"
fi
# `on_demand` campaigns do not hold the val split while they train -- it does
# not fit beside the training data (open question 16). The trainer stages it at
# each epoch boundary and drops it again; see TRIMODAL_VAL_ON_DEMAND below.
VAL_MODE="$(campaign_val_mode "$CAMPAIGN")"
TRAIN_PHASE=train
if [ "$VAL_MODE" = "on_demand" ]; then
    TRAIN_PHASE=train_only
    log "val mode: ON DEMAND -- the val split is staged per epoch, not held"
fi
if [ "$CHUNKED" = "yes" ]; then
    FIRST_PIECES="${PIECES:-0 1}"
    stage "$CAMPAIGN" --phase "$TRAIN_PHASE" --pieces $FIRST_PIECES
else
    stage "$CAMPAIGN" --phase "$TRAIN_PHASE"
fi
# The test split, beside the training data: 30_train.py writes test predictions
# at the end of every run (see `campaign_test_gb`). A campaign with no
# `_valtest` container adds nothing here and the call is a no-op.
# An `on_demand` campaign does not hold it either: campaign 8's test split is
# 30.1 GB on top of a 27.4 GB working set. 30_train.py stages it after training,
# once the pieces are gone, and drops it again (TRIMODAL_VAL_ON_DEMAND).
if [ "$VAL_MODE" != "on_demand" ] && [ "$(campaign_test_gb "$CAMPAIGN")" != "0" ]; then
    stage "$CAMPAIGN" --phase test
fi

# ---- point the loader at the staged data ----------------------------------
# The loader resolves everything under $PROJECT_ROOT/data/processed
# (build_common.DATA_PROCESSED). When DATA_ROOT is elsewhere -- node-local
# scratch, most usefully -- link rather than copy, so staging stays a single
# write and the loader needs no flag it does not have.
if [ "$DATA_ROOT" != "$PROJECT_ROOT/data/processed" ]; then
    mkdir -p "$PROJECT_ROOT/data"
    if [ ! -e "$PROJECT_ROOT/data/processed" ]; then
        ln -s "$DATA_ROOT" "$PROJECT_ROOT/data/processed" \
            && log "linked data/processed -> $DATA_ROOT"
    fi
fi

# §8.2 stages signals as int16 + per-record scale; modality.py rescales on read.
export TRIMODAL_SIGNAL_INT16="${TRIMODAL_SIGNAL_INT16:-1}"

# §8.2 rule 2: a chunked campaign cycles its pieces WITHIN each epoch, two
# resident at a time. The trainer drives the swaps (_train_lib/chunk_cycle.py);
# these two variables are how it learns that it should, and which campaign to
# ask stage_data.sh for. CAMPAIGN is exported because the cycling shells out.
export CAMPAIGN
# The trainer shells back out to stage_data.sh/evict_data.sh for the val swap.
if [ "$VAL_MODE" = "on_demand" ]; then
    export TRIMODAL_VAL_ON_DEMAND=1
fi
if [ "$CHUNKED" = "yes" ]; then
    export TRIMODAL_CHUNKED=1
    export TRIMODAL_CHUNK_PIECES="${TRIMODAL_CHUNK_PIECES:-8}"
    log "chunk cycling ON: ${TRIMODAL_CHUNK_PIECES} pieces, 2 resident, transport=$(transport)"
    if [ "$(transport)" = "rclone-offline" ]; then
        log "WARNING: rclone is present but this node has no outbound internet."
        log "         Mid-epoch piece fetches will fail. Export TRIMODAL_SOURCE to a"
        log "         mounted drive or campus share holding chunks/, or answer open"
        log "         question 4 first:   rclone lsd r2:trimodal-data"
    fi
fi

# ---- run ------------------------------------------------------------------
# campaign_runs.py emits `<task> <arch_tier> <seed> <config_filename>` in §8.3
# order. It resolves the config filename because 30_train.py is driven by
# --model-config <path>, not by a task/tier pair; keeping the naming scheme in
# python means this shell never has to know it.
TRAIN="$PROJECT_ROOT/scripts/phase2_tasks_benchmark_and_paper/30_train.py"
EVAL="$PROJECT_ROOT/scripts/phase2_tasks_benchmark_and_paper/31_eval.py"
CONFIG_DIR="$PROJECT_ROOT/config/model_configs"

status=0
declare -A evaluated=()
while read -r task tier seed config; do
    [ -n "${task:-}" ] || continue
    config_path="$CONFIG_DIR/$config"
    if [ ! -f "$config_path" ]; then
        log "MISSING CONFIG: $config_path -- skipping $task / $tier / seed $seed"
        status=1
        continue
    fi
    # ---- skip work that is already finished ------------------------------
    # push_results.sh deletes both checkpoints once a run's artifacts are safely
    # in R2, so `trainer.try_resume()` finds nothing and a repeat of this loop
    # retrains a finished run from scratch. That matters twice: re-submitting a
    # campaign to redo ONE tier would redo the others too, and a job requeued at
    # the wall-clock limit restarts this loop from the top -- silently redoing
    # every completed run before reaching the unfinished one.
    SUMMARY="$RESULTS_ROOT/model_runs/$task/$tier/seed_$seed/run_summary.json"
    if [ -z "${TRIMODAL_FORCE_RERUN:-}" ] && [ -f "$SUMMARY" ]        && grep -q '"status": *"complete"' "$SUMMARY" 2>/dev/null; then
        log "--- skip  $task / $tier / seed $seed (already complete) ---"
        evaluated["$task|$tier"]="${evaluated["$task|$tier"]:-skipped}"
        continue
    fi

    # The trainer decides whether to cycle from the pieces it finds on disk
    # (chunk_pieces.chunked_kinds). An on_demand run ends with every piece
    # evicted for its val/test predictions, and so can a run killed mid-swap,
    # so the next run would start un-cycled and read an unstaged shard. Put the
    # first window back before every run of a chunked campaign.
    if [ "$CHUNKED" = "yes" ] && [ -z "$(find "$DATA_ROOT" \( -name 'piece_*.h5' -o -name 'piece_*.tar' \) -print -quit 2>/dev/null)" ]; then
        log "no chunk piece on disk -- restaging pieces ${PIECES:-0 1} before this run"
        stage "$CAMPAIGN" --phase "$TRAIN_PHASE" --pieces ${PIECES:-0 1} --pieces-only || status=1
    fi
    log "--- train $task / $tier / seed $seed ---"
    if python3 "$TRAIN" --model-config "$config_path" --seed "$seed"; then
        # §8.1: push and free the checkpoints as each run finishes, not at the
        # end of the campaign. Three fusion checkpoints resident is the cap.
        "$HERE/push_results.sh" || status=1
        evaluated["$task|$tier"]=trained
    else
        log "TRAIN FAILED: $task / $tier / seed $seed (continuing)"
        status=1
        evaluated["$task|$tier"]="${evaluated["$task|$tier"]:-skipped}"
    fi
done < <(python3 "$PROJECT_ROOT/scripts/dgx_portability/campaign_runs.py"              "$CAMPAIGN" ${TRIMODAL_TASKS:+--tasks $TRIMODAL_TASKS})

# ---- swap to the EVAL phase ------------------------------------------------
# Training held train+val; evaluation needs the test split, and on a chunked
# campaign it does not need the train pieces at all. Evicting first is what
# keeps both phases under the ceiling (open question 15b).
if [ "$CHUNKED" = "yes" ]; then
    "$HERE/evict_data.sh" --pieces-all || log "piece eviction reported a problem, continuing"
fi
# A val container left over from the last epoch's swap is train-phase data the
# eval phase has no use for, and it is counted against the same ceiling.
"$HERE/evict_data.sh" --split val --force || log "val eviction reported a problem, continuing"
log "staging the eval phase (test split)"
stage "$CAMPAIGN" --phase eval || status=1

# 31_eval.py aggregates ACROSS seeds (mean +/- std over the three), so it runs
# once per (task, arch tier) after all its seeds are done -- not once per seed.
#
# IT DOES NOT RUN HERE. Evaluation is a 10,000-iteration BCa patient-level
# bootstrap: pure CPU, single-threaded, and MEASURED at over ten hours for
# A1/text_tfidf on 2026-09-01. Doing that inside this job pinned the account's
# only GPU -- `gres/gpu=1` -- while one core did statistics, and with two tiers
# per task it was costing roughly twenty GPU-hours per task, more than the
# training it was evaluating.
#
# The cap is on GPUs, not cores (`cpu=32`), so each eval goes to cpu_student
# where it runs CONCURRENTLY with the next training shard, and several evals run
# at once. Set TRIMODAL_EVAL_INLINE=1 to get the old blocking behaviour (useful
# when debugging an eval, where waiting for a queue is worse than holding a GPU).
#
# FOUR cores per eval, not twelve (2026-09-08). Twelve was sized for the eval
# alone and it deadlocked the campaign: on 2026-09-08 one training shard and
# three evals filled `cpu=32` exactly, and BOTH remaining campaign-1 training
# shards sat on `AssocGrpCpuLimit` behind their own predecessors' statistics.
# Evaluation stopped blocking training by holding the GPU and started blocking
# it by holding the cores. At 4, a training shard (8) plus six evals still fits.
# 31_eval.py sizes its pool from SLURM_CPUS_PER_TASK, so this is a real
# throughput trade -- an eval takes roughly three times as long -- but eval is
# off the critical path and training is on it. Raise TRIMODAL_EVAL_CPUS when the
# facility raises the cap, or for a lone eval with no training queued behind it.
for key in "${!evaluated[@]}"; do
    task="${key%%|*}"; tier="${key##*|}"
    # One eval per (task, tier) at a time, and none that is already done. A
    # resubmitted or chained campaign job walks its finished runs again; it
    # used to queue their evals again too, beside the ones still running, both
    # writing the same `.eval_checkpoints` file (A3 image, 2026-10-13). A tier
    # this job TRAINED is re-evaluated even if an older eval finished -- its
    # seeds have changed -- but never while one is still in the queue.
    if eval_in_flight "$task" "$tier"; then
        log "--- eval $task / $tier: one is already queued or running, not submitting another ---"
        continue
    fi
    if [ "${evaluated[$key]}" != "trained" ] && [ -f "$(eval_marker "$task" "$tier").done" ]; then
        log "--- eval $task / $tier: already done, nothing trained since ---"
        continue
    fi
    if ! ls "$RESULTS_ROOT/model_runs/$task/$tier"/seed_*/test_predictions.parquet >/dev/null 2>&1; then
        log "--- eval $task / $tier: no seed has predictions, nothing to evaluate ---"
        continue
    fi
    rm -f "$(eval_marker "$task" "$tier").done"
    if [ -n "${TRIMODAL_EVAL_INLINE:-}" ]; then
        log "--- eval $task / $tier (all seeds, inline) ---"
        python3 "$EVAL" --task "$task" --arch-tier "$tier" || status=1
        continue
    fi
    if jid=$(sbatch --parsable --export=ALL,TASK="$task",TIER="$tier"                     --cpus-per-task="${TRIMODAL_EVAL_CPUS:-4}"                     "$HERE/slurm/eval_task.sbatch" 2>&1); then
        eval_record_job "$task" "$tier" "$jid"
        log "--- eval $task / $tier queued on cpu_student as job $jid ---"
    else
        log "SUBMIT FAILED for eval $task / $tier ($jid); running it inline instead"
        python3 "$EVAL" --task "$task" --arch-tier "$tier" || status=1
    fi
done

# ---- final push, then leave the disk clean for the next campaign -----------
# The eval jobs push their own results when they finish; this push covers
# anything already complete before they do.
"$HERE/push_results.sh" || status=1
log "campaign $CAMPAIGN finished with status $status. Used: $(used_gb) GB."
log "evict when you are satisfied the results landed:  $HERE/evict_data.sh"
exit "$status"
