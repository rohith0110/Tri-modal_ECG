#!/usr/bin/env bash
# Move the running A1 shard from a dgxa MIG slice to a full A100 on dgxb.
# The account holds one GPU at a time, so the old job MUST be cancelled before
# the new one can start -- there is a short window where the card is up for
# grabs. If dgxb does not take, fall back to a dgxa slice immediately so we
# never end up holding no GPU at all.
set -uo pipefail
cd "$HOME/se23ucse027" || exit 1
OLD="${1:?usage: swap_to_dgxb.sh <jobid>}"
TASK=A1_ecg_diagnosis
SB=scripts/dgx_portability/slurm/campaign_01.sbatch

echo "cancelling $OLD"
scancel "$OLD" || { echo "scancel failed"; exit 1; }
for _ in $(seq 1 30); do
    squeue -h -j "$OLD" 2>/dev/null | grep -q . || break
    sleep 2
done

NEW=$(sbatch --parsable --partition=gpu_student --nodelist=dgxb \
             --gres=gpu:a100:1 --time=96:00:00 --job-name=b_A1 \
             --export=ALL,TRIMODAL_TASKS="$TASK" "$SB" 2>&1)
if [[ "$NEW" =~ ^[0-9]+$ ]]; then
    echo "SWAPPED: A1 resubmitted to dgxb full a100 as job $NEW"
else
    echo "dgxb submit FAILED: $NEW"
    FALLBACK=$(sbatch --parsable --partition=gpu_student --nodelist=dgxa \
                      --gres=gpu:a100_4g.20gb:1 --time=96:00:00 --job-name=c1_A1 \
                      --export=ALL,TRIMODAL_TASKS="$TASK" "$SB" 2>&1)
    echo "FELL BACK to dgxa slice as job $FALLBACK"
fi
squeue -u "$USER" -o "%.8i %.8j %.2t %R"
