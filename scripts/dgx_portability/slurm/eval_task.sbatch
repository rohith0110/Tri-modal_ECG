#!/usr/bin/env bash
#SBATCH --job-name=trimodal_eval
#SBATCH --partition=cpu_student
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4        # NOT 12: `_campaign_body.sh` overrides this
                                  # with TRIMODAL_EVAL_CPUS, and twelve
                                  # deadlocked the campaign against `cpu=32`
                                  # on 2026-09-08 -- three evals plus one
                                  # training shard filled the cap and both
                                  # remaining shards pended on
                                  # AssocGrpCpuLimit. 31_eval.py sizes its
                                  # pool from SLURM_CPUS_PER_TASK.
#SBATCH --mem=32G
#SBATCH --time=7-00:00:00        # partition max; A3's 2,940 units
                                  # blew through a 24 h limit on 2026-09-04
                                  # (TIMEOUT, jobs 22733/22734). The
                                  # checkpoint made that survivable, but a
                                  # too-short limit still wastes a queue slot.
#SBATCH --output=trimodal_eval_%j.out
#SBATCH --error=trimodal_eval_%j.err
#
# Evaluate ONE (task, arch tier) on the CPU partition.
#
# 31_eval.py is pure CPU work -- a 10,000-iteration BCa patient-level bootstrap
# (config/eval_configs/default.yaml) over the pooled test predictions. Measured
# 2026-09-01: A1/text_tfidf took over TEN HOURS at 99.9% of a single core.
#
# Running that inside the campaign's GPU job held this account's only A100 slice
# idle for the whole of it. The account cap is `gres/gpu=1` but `cpu=32`, so an
# eval here runs CONCURRENTLY with the next training shard instead of blocking
# it -- and several evals can run at once, since each uses one core.
#
#   sbatch --export=ALL,TASK=A1_ecg_diagnosis,TIER=text_tfidf eval_task.sbatch
set -euo pipefail
PROJECT_ROOT="${TRIMODAL_HOME:-$HOME/se23ucse027}"
# push_results.sh lives in dgx_portability/, NOT in slurm/ -- the same layout
# `_campaign_body.sh` assumes when it sets HERE to the parent directory.
HERE="$PROJECT_ROOT/scripts/dgx_portability"
cd "$PROJECT_ROOT"

: "${TASK:?set TASK=<task key>}"
: "${TIER:?set TIER=<arch tier>}"

# shellcheck disable=SC1091
. "$PROJECT_ROOT/ecg_env/bin/activate"
export TOKENIZERS_PARALLELISM=false

# campaigns.sh defaults R2_RESULTS to `r2:trimodal-results` for the laptop, and
# `r2` on the DGX is the READ-ONLY data token -- a push through it fails with a
# misleading "is a file not a directory". `_campaign_body.sh` overrides this for
# campaign jobs and ~/.bashrc does it for interactive shells; a batch job that
# sources neither gets the laptop default. Both A1 evaluations finished 18 hours
# of bootstrap and then failed to push for exactly this reason.
export R2_RESULTS="${R2_RESULTS:-r2-results:trimodal-results}"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] eval $TASK / $TIER on $(hostname) job ${SLURM_JOB_ID:-none}"

# ---- continuation, queued up front -----------------------------------------
# The big evals outlive the 7-day partition limit (A3 is 2,940 units), and a
# TIMEOUT with nothing behind it sits idle until someone on campus notices. So
# each eval queues its own successor before it starts work: `afternotok` runs
# it only if this job times out or fails, it resumes from `.eval_checkpoints`,
# and this job cancels it on success. EVAL_CHAIN bounds the chain, so an eval
# that fails in its first seconds respawns that many times and then stops.
# shellcheck source=../campaigns.sh
. "$HERE/campaigns.sh"
# Second line of defence against two evals of one (task, tier) running side by
# side: whoever submitted this job, stand down if another recorded job for the
# same eval is RUNNING right now. (A predecessor in this job's own chain has
# finished by the time this one starts; its successor is only pending.)
if [ -n "${SLURM_JOB_ID:-}" ] && [ -f "$(eval_marker "$TASK" "$TIER").jobs" ]; then
    while read -r other; do
        [ -n "$other" ] && [ "$other" != "$SLURM_JOB_ID" ] || continue
        if [ "$(squeue -h -j "$other" -o %T 2>/dev/null)" = "RUNNING" ]; then
            echo "eval $TASK / $TIER is already running as job $other -- this job stands down"
            exit 0
        fi
    done < "$(eval_marker "$TASK" "$TIER").jobs"
fi
if [ -n "${SLURM_JOB_ID:-}" ]; then eval_record_job "$TASK" "$TIER" "$SLURM_JOB_ID"; fi

chain_left="${EVAL_CHAIN:-2}"
next_job=""
if [ -n "${SLURM_JOB_ID:-}" ] && [ "$chain_left" -gt 0 ]; then
    if next_job=$(sbatch --parsable --dependency="afternotok:$SLURM_JOB_ID" \
            --cpus-per-task="${SLURM_CPUS_PER_TASK:-4}" \
            ${SLURM_MEM_PER_NODE:+--mem="${SLURM_MEM_PER_NODE}M"} \
            --export=ALL,TASK="$TASK",TIER="$TIER",EVAL_CHAIN="$((chain_left - 1))" \
            "$HERE/slurm/eval_task.sbatch" 2>&1); then
        eval_record_job "$TASK" "$TIER" "$next_job"
        echo "continuation queued as job $next_job (EVAL_CHAIN left: $((chain_left - 1)))"
    else
        echo "WARNING: could not queue a continuation: $next_job"
        next_job=""
    fi
fi

# `&& ... ||`, not a bare call: under `set -e` a failing eval used to end the
# script on that line, before the push below and before the status was read.
python3 "$PROJECT_ROOT/scripts/phase2_tasks_benchmark_and_paper/31_eval.py" \
        --task "$TASK" --arch-tier "$TIER" && status=0 || status=$?
if [ "$status" -eq 0 ]; then
    mkdir -p "$STATE_DIR/evals"
    date -u +%Y-%m-%dT%H:%M:%SZ > "$(eval_marker "$TASK" "$TIER").done"
    if [ -n "$next_job" ]; then scancel "$next_job" 2>/dev/null || true; fi
fi

# Push whatever this eval completed. push_results only frees a run's
# checkpoints once its artifacts verify in R2, so an eval that failed leaves
# everything where it was.
"$HERE/push_results.sh" || status=1
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] eval $TASK / $TIER finished, status=$status"
exit $status
