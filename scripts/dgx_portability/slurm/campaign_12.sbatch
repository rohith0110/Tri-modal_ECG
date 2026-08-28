#!/usr/bin/env bash
#SBATCH --job-name=trimodal_c12_fusion_L3_lead2
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --time=40:00:00
#SBATCH --requeue
#SBATCH --signal=B:TERM@300
#SBATCH --output=trimodal_c12_%j.out
#SBATCH --error=trimodal_c12_%j.err
#
# Campaign 12 -- fusion_L3_lead2. The Lead-II half of the campaign that used to be
# one job; split at open question 14 so it fits the 45 GB ceiling.
#   resident data ~29.4 GB (measured) | ~20 GPU-hours | chunked: no
#   wall clock requested is 2x the estimate for queue and I/O, capped at 48 h.
#
# UNVERIFIED ENVIRONMENT -- Step 7's survey has not run. Consequences:
#   * No --partition is set, because the partition names are unconfirmed beyond
#     `gpu_student` in the spec and a wrong name is a submit-time rejection.
#     Pass it at submit time:  sbatch --partition=gpu_student campaign_12.sbatch
#   * --gres=gpu:1 and --cpus-per-task=8 are conservative floors. Override the
#     same way rather than editing this file:
#         sbatch --partition=gpu_student --gres=gpu:2 campaign_12.sbatch
#   * --requeue with --signal=B:TERM@300 is what makes the §6.9/§8.1 resume
#     path real: the trainer gets 5 minutes' warning, writes checkpoint_last.pt
#     and exits 0, so Slurm requeues it and it continues mid-epoch.
#
# TRIMODAL_HOME defaults to ~/trimodal; set it if the checkout lives elsewhere.

set -euo pipefail
export CAMPAIGN=12
export PROJECT_ROOT="${TRIMODAL_HOME:-$HOME/trimodal}"

. "$PROJECT_ROOT/scripts/dgx_portability/slurm/_campaign_body.sh"
