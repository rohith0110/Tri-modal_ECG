#!/usr/bin/env bash
#SBATCH --job-name=swapwatch
#SBATCH --partition=cpu_student
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=24:00:00
#SBATCH --output=swapwatch_%j.out
#SBATCH --error=swapwatch_%j.err
#
# Moves the running A1 shard from a dgxa MIG slice to a full A100 on dgxb, at
# an epoch boundary, as soon as a full card frees. Runs ON THE CLUSTER so it
# does not depend on the operator's laptop staying awake.
#
# It requests NO GPU on purpose: the account's cap is gres/gpu=1, and this job
# must never compete with the training it is watching. 1 CPU, 1 GB, polling
# squeue every five minutes -- and it is a batch job, so nothing runs on the
# login node.
set -uo pipefail
cd "$HOME/se23ucse027" || exit 1

TASK=A1_ecg_diagnosis
RUN_LOG="outputs/model_runs/$TASK/text_bioclinicalbert/seed_42/train_log.jsonl"
INTERVAL=300
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

log "watching for: an epoch boundary on $TASK AND a free full a100 on dgxb"

while true; do
    # The A1 job is the one running on dgxa with our shard name. If it is gone,
    # there is nothing left to move -- the queued dgxb shards take over by
    # themselves.
    JOB=$(squeue -u "$USER" -h -t R -o "%i %j" | awk '$2 ~ /^(c1_A1|b_A1)$/ {print $1; exit}')
    if [ -z "$JOB" ]; then
        log "no running A1 shard; nothing to swap. Exiting."
        exit 0
    fi

    NODE=$(squeue -h -j "$JOB" -o "%N")
    if [ "$NODE" = "dgxb" ]; then
        log "A1 (job $JOB) is already on dgxb. Nothing to do. Exiting."
        exit 0
    fi

    EPOCHS=0
    [ -f "$RUN_LOG" ] && EPOCHS=$(wc -l < "$RUN_LOG" 2>/dev/null || echo 0)
    BUSY=$(squeue -w dgxb -t R -h -o "%b" | grep -c "gpu:a100:1")

    log "job=$JOB node=$NODE epochs=$EPOCHS dgxb_full_cards_busy=$BUSY/5"

    if [ "$EPOCHS" -ge 1 ] && [ "$BUSY" -lt 5 ]; then
        log "conditions met -- swapping"
        bash "$HOME/se23ucse027/scripts/dgx_portability/slurm/swap_to_dgxb.sh" "$JOB"
        exit 0
    fi
    sleep "$INTERVAL"
done
