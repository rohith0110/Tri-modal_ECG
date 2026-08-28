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

# ---- stage ----------------------------------------------------------------
# The refusal gate lives in stage_data.sh and runs before any byte moves.
if [ "$CHUNKED" = "yes" ]; then
    FIRST_PIECES="${PIECES:-0 1}"
    "$HERE/stage_data.sh" "$CAMPAIGN" --pieces $FIRST_PIECES
else
    "$HERE/stage_data.sh" "$CAMPAIGN"
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
    log "--- train $task / $tier / seed $seed ---"
    if python3 "$TRAIN" --model-config "$config_path" --seed "$seed"; then
        # §8.1: push and free the checkpoints as each run finishes, not at the
        # end of the campaign. Three fusion checkpoints resident is the cap.
        "$HERE/push_results.sh" || status=1
    else
        log "TRAIN FAILED: $task / $tier / seed $seed (continuing)"
        status=1
    fi
    evaluated["$task|$tier"]=1
done < <(python3 "$PROJECT_ROOT/scripts/dgx_portability/campaign_runs.py" "$CAMPAIGN")

# 31_eval.py aggregates ACROSS seeds (mean +/- std over the three), so it runs
# once per (task, arch tier) after all its seeds are done -- not once per seed.
for key in "${!evaluated[@]}"; do
    task="${key%%|*}"; tier="${key##*|}"
    log "--- eval $task / $tier (all seeds) ---"
    python3 "$EVAL" --task "$task" --arch-tier "$tier" || status=1
done

# ---- final push, then leave the disk clean for the next campaign -----------
"$HERE/push_results.sh" || status=1
log "campaign $CAMPAIGN finished with status $status. Used: $(used_gb) GB."
log "evict when you are satisfied the results landed:  $HERE/evict_data.sh"
exit "$status"
