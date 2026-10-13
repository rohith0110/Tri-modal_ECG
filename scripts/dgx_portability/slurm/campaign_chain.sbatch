#!/usr/bin/env bash
#SBATCH --job-name=trimodal_chain
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=7-00:00:00
#SBATCH --requeue
#SBATCH --signal=B:TERM@300
#SBATCH --output=trimodal_chain_%j.out
#SBATCH --error=trimodal_chain_%j.err
#
# Several campaigns, one after another, in one job -- and safe to submit more
# than once. This is what runs when nobody is on campus to submit the next
# campaign by hand:
#
#   sbatch --partition=gpu_student --gres=gpu:a100_4g.20gb:1 \
#          --export=ALL,CAMPAIGNS="4 3 15" campaign_chain.sbatch
#   sbatch --dependency=afterany:<that job> ...the same line...      # link 2
#
# Each link walks CAMPAIGNS in order. A campaign whose runs are all complete is
# skipped before a byte is staged; otherwise `_campaign_body.sh` runs it, which
# itself skips finished runs and resumes an interrupted one from its checkpoint.
# So a link that starts after a 7-day TIMEOUT picks up where the last one
# stopped, and a link that starts after everything finished exits in seconds.
#
# No --partition, --gres or --nodelist here: pass them on the command line. No
# node is pinned on purpose -- two accounts run chains at once, and letting
# Slurm place each job on whichever node has a free slice is what keeps them
# from queueing behind each other.
#
# Between campaigns the finished one's data is evicted (after its results are
# pushed -- evict_data.sh refuses otherwise), because the next one is sized
# against the quota on its own.
set -uo pipefail

: "${CAMPAIGNS:?set CAMPAIGNS=\"<n> <n> ...\"}"
export PROJECT_ROOT="${TRIMODAL_HOME:-$HOME/se23ucse027}"
HERE="$PROJECT_ROOT/scripts/dgx_portability"
cd "$PROJECT_ROOT"

# shellcheck disable=SC1091
. "$PROJECT_ROOT/ecg_env/bin/activate"
# shellcheck source=../campaigns.sh
. "$HERE/campaigns.sh"
set +e                      # campaigns.sh turns -e on; one campaign failing must not end the chain

log "=== chain [$CAMPAIGNS] on $(hostname), job ${SLURM_JOB_ID:-none}, account $(id -un) ==="
overall=0
for campaign in $CAMPAIGNS; do
    if campaign_complete "$campaign"; then
        log "=== campaign $campaign: every run is complete, skipping ==="
        continue
    fi
    # Start every campaign from an empty data root. The quota gate adds the
    # campaign's residency to what is already on disk, so data left behind by
    # the previous campaign -- or by this same campaign's previous link -- is
    # counted twice and the gate refuses (session 17). Inputs are re-fetchable;
    # results are pushed first, and evict_data.sh refuses while any prediction
    # file is newer than the last successful push.
    "$HERE/push_results.sh" || log "push reported a problem before campaign $campaign"
    "$HERE/evict_data.sh" --all || log "eviction refused or failed; campaign $campaign's quota gate decides"
    # The body is written to be sourced by a one-campaign sbatch file and ends
    # in `exit`, so it gets a subshell of its own.
    ( export CAMPAIGN="$campaign"; . "$HERE/slurm/_campaign_body.sh" )
    rc=$?
    if campaign_complete "$campaign"; then
        log "=== campaign $campaign: complete (body exit $rc) ==="
    else
        log "=== campaign $campaign: NOT complete (body exit $rc) -- moving on; a later link retries it ==="
        overall=1
    fi
done
log "=== chain [$CAMPAIGNS] finished, status $overall. Used: $(used_gb) GB ==="
exit "$overall"
