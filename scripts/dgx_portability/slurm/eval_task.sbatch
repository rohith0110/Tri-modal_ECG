#!/usr/bin/env bash
#SBATCH --job-name=trimodal_eval
#SBATCH --partition=cpu_student
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --time=24:00:00
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
HERE="$PROJECT_ROOT/scripts/dgx_portability/slurm"
cd "$PROJECT_ROOT"

: "${TASK:?set TASK=<task key>}"
: "${TIER:?set TIER=<arch tier>}"

# shellcheck disable=SC1091
. "$PROJECT_ROOT/ecg_env/bin/activate"
export TOKENIZERS_PARALLELISM=false

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] eval $TASK / $TIER on $(hostname) job ${SLURM_JOB_ID:-none}"
python3 "$PROJECT_ROOT/scripts/phase2_tasks_benchmark_and_paper/31_eval.py" \
        --task "$TASK" --arch-tier "$TIER"
status=$?

# Push whatever this eval completed. push_results only frees a run's
# checkpoints once its artifacts verify in R2, so an eval that failed leaves
# everything where it was.
"$HERE/push_results.sh" || status=1
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] eval $TASK / $TIER finished, status=$status"
exit $status
