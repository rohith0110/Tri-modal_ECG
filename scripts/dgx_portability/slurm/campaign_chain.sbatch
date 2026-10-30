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
#          --export=ALL,CAMPAIGNS="10 4 13 8 7 3 15 12 9 6 5" campaign_chain.sbatch
#   sbatch --dependency=afterany:<that job> ...the same line...      # link 2
#
# Order is longest first (user, 2026-10-30): with only two GPUs, a 20-day
# campaign left for last runs on one account while the other sits idle.
# Campaigns already running go first so their owner resumes them before
# claiming anything new.
#
# BOTH accounts submit the same CAMPAIGNS list: each campaign is claimed in R2
# by whichever account reaches it first with room for it (see "claims" below).
# 11 and 14 (final evals) are left out on purpose -- they need every other
# campaign's evals finished and account 2's results merged into the root
# first (merge_acct2_results.py), so they are submitted by hand.
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
# campaigns.sh defaults R2_RESULTS to `r2:trimodal-results`, and `r2` on the DGX
# is the READ-ONLY data token: every push fails with "is a file not a directory",
# and the evals this chain submits inherit the same value. Chain 27480 pushed
# nothing for a week this way. An `.account_env` still wins (campaigns.sh
# sources it after this line).
export R2_RESULTS="${R2_RESULTS:-r2-results:trimodal-results}"
# shellcheck source=../campaigns.sh
. "$HERE/campaigns.sh"
set +e                      # campaigns.sh turns -e on; one campaign failing must not end the chain

# ---- claims: which account runs which campaign -----------------------------
# Campaigns are taken on availability, not assigned up front (user, 2026-10-27).
# Both accounts' chains walk the SAME list; before starting a campaign a chain
# claims it with a small file in R2, and the other account skips anything the
# first has claimed. A claim is for the campaign's whole life -- two accounts
# training one campaign would both write model_runs/<task>/<tier>/seed_<n>.
# Claims sit at one fixed path, NOT under an account's own R2_RESULTS prefix,
# so both accounts read the same files. Line format: `<user> <state> <utc>`,
# state `running` or `done`. Unreadable claims (R2 down) mean: run only what
# this account already owned, never take something new.
# CLAIM_OWNER (from an `.account_env`) names a claimant other than the user: an
# account with 2 GPUs runs two chains from two checkouts, and under one name
# both would treat the other's campaign as their own and train it twice.
CLAIMS="${R2_CLAIMS:-r2-results:trimodal-results/claims}"
ME="${CLAIM_OWNER:-$(id -un)}"
resolve_rclone || { log "no rclone: cannot read claims"; exit 1; }
claim_read() {          # prints "<user> <state>" or nothing; exit 1 if R2 unreadable
    local listing
    listing="$("$RCLONE" lsf "$CLAIMS/" 2>/dev/null)" || return 1
    printf '%s\n' "$listing" | grep -qx "campaign_$1" || return 0
    "$RCLONE" cat "$CLAIMS/campaign_$1" 2>/dev/null | awk 'NR==1 { print $1, $2 }'
}
claim_write() {         # claim_write <n> <state>
    printf '%s %s %s\n' "$ME" "$2" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        | "$RCLONE" rcat --s3-no-check-bucket "$CLAIMS/campaign_$1"
}
# True when any run of the campaign has a run directory on this account.
campaign_started_here() {
    local task tier seed config
    while read -r task tier seed config; do
        [ -n "${task:-}" ] || continue
        [ -d "$RESULTS_ROOT/model_runs/$task/$tier/seed_$seed" ] && return 0
    done < <(python3 "$PROJECT_ROOT/scripts/dgx_portability/campaign_runs.py" "$1")
    return 1
}
# Data a campaign must hold at once: the train phase plus, unless it is
# on_demand, the test split staged beside it (see _campaign_body.sh).
campaign_peak_gb() {
    local train test=0
    train="$(campaign_phase_gb "$1" "$(
        [ "$(campaign_val_mode "$1")" = "on_demand" ] && echo train_only || echo train)")"
    [ "$(campaign_val_mode "$1")" = "on_demand" ] || test="$(campaign_test_gb "$1")"
    awk -v a="$train" -v b="$test" 'BEGIN { printf "%.1f", a + b }'
}

log "=== chain [$CAMPAIGNS] on $(hostname), job ${SLURM_JOB_ID:-none}, account $ME ==="
overall=0
for campaign in $CAMPAIGNS; do
    if ! claim="$(claim_read "$campaign")"; then
        claim="unknown unknown"
        log "claims unreadable in $CLAIMS -- campaign $campaign only if this account already has runs of it"
    fi
    owner="${claim%% *}"; state="${claim##* }"
    # A `hold` claim parks a campaign away from chain links still running the
    # OLD walk order (sbatch keeps the script and CAMPAIGNS it was submitted
    # with). Links on this script treat it as unclaimed and overwrite it.
    if [ "$owner" = "hold" ]; then owner=""; state=""; fi
    if [ "$state" = "done" ]; then
        log "=== campaign $campaign: done (claim by $owner), skipping ==="
        continue
    fi
    if [ -n "$owner" ] && [ "$owner" != "$ME" ] && [ "$owner" != "unknown" ]; then
        log "=== campaign $campaign: claimed by $owner, skipping ==="
        continue
    fi
    if campaign_complete "$campaign"; then
        log "=== campaign $campaign: every run is complete, skipping ==="
        [ "$owner" = "$ME" ] && claim_write "$campaign" done
        continue
    fi
    if [ "$owner" = "unknown" ]; then
        if ! campaign_started_here "$campaign"; then
            log "=== campaign $campaign: claims unreadable and no run of it here, skipping ==="
            continue
        fi
        owner="$ME"           # ours already; carry on without touching the claim
    fi
    # Start every campaign from an empty data root. The quota gate adds the
    # campaign's residency to what is already on disk, so data left behind by
    # the previous campaign -- or by this same campaign's previous link -- is
    # counted twice and the gate refuses (session 17). Inputs are re-fetchable;
    # results are pushed first, and evict_data.sh refuses while any prediction
    # file is newer than the last successful push.
    "$HERE/push_results.sh" || log "push reported a problem before campaign $campaign"
    "$HERE/evict_data.sh" --all || log "eviction refused or failed; campaign $campaign's quota gate decides"
    # Take a new campaign only if it fits THIS account's ceiling with the disk
    # as it is now (base: venv, cache, outputs). A claim on something that
    # cannot stage would hold it away from the account that could run it.
    # CLAIM_HEADROOM_GB is room for the run's own checkpoints and logs on top of
    # the staged data: campaign 7 fits account 1's gate with 0.8 GiB to spare,
    # less than two fusion checkpoints.
    if [ "$owner" != "$ME" ]; then
        peak="$(awk -v p="$(campaign_peak_gb "$campaign")" -v h="${CLAIM_HEADROOM_GB:-2}" \
                'BEGIN { printf "%.1f", p + h }')"
        if ! will_fit "$peak"; then
            log "=== campaign $campaign: needs ${peak} GB, does not fit here ($(used_gb) GiB used, ceiling ${QUOTA_CEILING_GB}), leaving it ==="
            continue
        fi
        claim_write "$campaign" running || { log "could not write claim for $campaign, skipping"; continue; }
        # Two chains reaching the same free campaign within seconds: the later
        # write wins, and the earlier one sees that and stands down.
        sleep 20
        if [ "$(claim_read "$campaign" | cut -d' ' -f1)" != "$ME" ]; then
            log "=== campaign $campaign: lost the claim race, skipping ==="
            continue
        fi
        log "=== campaign $campaign: claimed by $ME ==="
    fi
    # The body is written to be sourced by a one-campaign sbatch file and ends
    # in `exit`, so it gets a subshell of its own.
    ( export CAMPAIGN="$campaign"; . "$HERE/slurm/_campaign_body.sh" )
    rc=$?
    if campaign_complete "$campaign"; then
        log "=== campaign $campaign: complete (body exit $rc) ==="
        claim_write "$campaign" done || log "could not mark campaign $campaign done in $CLAIMS"
    else
        log "=== campaign $campaign: NOT complete (body exit $rc) -- moving on; a later link retries it ==="
        overall=1
    fi
done
log "=== chain [$CAMPAIGNS] finished, status $overall. Used: $(used_gb) GB ==="
exit "$overall"
