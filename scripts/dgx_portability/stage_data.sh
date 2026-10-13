#!/usr/bin/env bash
# Stage ONE campaign's data, verify checksums, refuse if it will not fit.
#
#   ./stage_data.sh 4                 # stage campaign 4
#   ./stage_data.sh 6 --pieces 0 1    # a chunked campaign: only these pieces
#   ./stage_data.sh 4 --dry-run       # decide and report, move no bytes
#   ./stage_data.sh 5 --phase eval    # the test split, after training is done
#   ./stage_data.sh 6 --pieces 2 --pieces-only   # one more piece, mid-epoch
#
# Spec §8.2 storage rule 6: check free quota BEFORE pulling anything and refuse
# if the campaign will not fit under 45 GB. A refusal beats a job that dies at
# 90 %. The check runs first, before a single byte moves.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=campaigns.sh
. "$HERE/campaigns.sh"

CAMPAIGN="${1:-}"
shift || true
PIECES=()
DRY_RUN=0
# TRAIN stages train+val data; EVAL stages the test split, after the training
# runs are done and their pieces evicted. A campaign that held both at once
# would exceed the 45 GB ceiling on paper (5, 7 and 8 did) while never actually
# needing both at the same moment.
PHASE=train
PIECES_ONLY=0
ONLY=()
while [ $# -gt 0 ]; do
    case "$1" in
        --pieces) shift; while [ $# -gt 0 ] && [ "${1#-}" = "$1" ]; do PIECES+=("$1"); shift; done ;;
        --phase) shift; PHASE="${1:-train}"; shift ;;
        # Stage only the datasets whose name is listed -- the val swap asks for
        # the val containers without re-fetching and re-verifying the whole
        # campaign, which would cost minutes at every epoch boundary.
        --only-datasets) shift
                  while [ $# -gt 0 ] && [ "${1#-}" = "$1" ]; do ONLY+=("$1"); shift; done ;;
        # Mid-epoch piece cycling (§8.2 rule 2) asks for ONE more piece while a
        # run is live. Re-staging and re-verifying every plain dataset for that
        # would cost minutes per swap, so this stages only the piece files.
        --pieces-only) PIECES_ONLY=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [ -z "$CAMPAIGN" ] || ! campaign_spec "$CAMPAIGN" >/dev/null 2>&1; then
    echo "usage: $0 <campaign 1-$N_CAMPAIGNS> [--pieces N...] [--only-datasets A B...]" \
         "[--phase train|train_only|val|eval] [--dry-run]" >&2
    exit 2
fi

NAME="$(campaign_name "$CAMPAIGN")"
RESIDENT="$(campaign_phase_gb "$CAMPAIGN" "$PHASE")"
CHUNKED="$(campaign_chunked "$CAMPAIGN")"
DATASETS="$(campaign_datasets "$CAMPAIGN")"
SKIP_CODE_VERIFY=""

log "campaign $CAMPAIGN ($NAME) phase=$PHASE: resident ~${RESIDENT} GB, chunked=$CHUNKED"
log "transport=$(transport)  DATA_ROOT=$DATA_ROOT"

# A chunked campaign never stages the whole modality -- only the resident
# pieces (two at a time per §8.2 rule 2). Staging all of them would defeat the
# entire point and blow the quota.
if [ "$CHUNKED" = "yes" ] && { [ "$PHASE" = "train" ] || [ "$PHASE" = "train_only" ]; } \
   && [ ${#PIECES[@]} -eq 0 ]; then
    cat >&2 <<MSG
REFUSING: campaign $CAMPAIGN is a CHUNKED campaign (§8.2 rule 1).
  Its training data does not fit, so it is staged piece by piece.
  Pass the pieces you want resident, at most two at a time:
      $0 $CAMPAIGN --pieces 0 1
  Chunks cycle WITHIN an epoch (§8.2 rule 2); the training loop asks for the
  next piece as it goes, it does not want them all up front.
MSG
    exit 1
fi

# ---- the refusal gate, before any transfer --------------------------------
require_fit "$RESIDENT" "campaign $CAMPAIGN ($NAME), $PHASE phase" || exit 1

if [ "$DRY_RUN" -eq 1 ]; then
    log "dry run: would stage [$DATASETS] into $DATA_ROOT"
    [ ${#PIECES[@]} -gt 0 ] && log "dry run: pieces ${PIECES[*]}"
    exit 0
fi

mkdir -p "$DATA_ROOT" "$STATE_DIR"

for dataset in $DATASETS; do
    # --only-datasets filter, applied before anything else.
    if [ ${#ONLY[@]} -gt 0 ]; then
        wanted=0
        for name in "${ONLY[@]}"; do [ "$name" = "$dataset" ] && wanted=1; done
        [ "$wanted" = "1" ] || continue
    fi
    case "$dataset" in
        *_pieces)
            # Pieces are TRAIN data: neither the eval phase nor the val swap
            # stages them, and the val swap has just evicted them to make room.
            if [ "$PHASE" = "eval" ] || [ "$PHASE" = "val" ]; then continue; fi
            base="${dataset%_pieces}"
            # The extension comes from the cut's name, never from trying one
            # and falling back on failure: `rclone copy` of a MISSING S3 key
            # exits 0 and copies nothing, so `fetch .h5 || fetch .tar` staged
            # every image piece empty (job 25576, 2026-10-05). The size check
            # below catches any other way a piece can arrive as nothing.
            ext="$(piece_ext "$base")" || exit 1
            for piece in "${PIECES[@]}"; do
                printf -v padded 'piece_%03d' "$piece"
                log "staging $base $padded.$ext"
                fetch "chunks/$base/$padded.$ext" "$DATA_ROOT/$base" || exit 1
                [ -s "$DATA_ROOT/$base/$padded.$ext" ] || {
                    echo "ERROR: $base/$padded.$ext is missing or empty after the fetch" >&2
                    echo "       (r2 key: $R2_DATA/chunks/$base/$padded.$ext)" >&2
                    exit 1; }
            done
            fetch "chunks/$base/checksums.json" "$DATA_ROOT/$base" || true
            fetch "chunks/$base/assignment.parquet" "$DATA_ROOT/$base" || true
            ;;
        code|configs)
            # No `--pieces-only` shortcut ahead of the git test below. It used
            # to `continue` here, before SKIP_CODE_VERIFY was set, so a
            # mid-epoch piece fetch went on to judge git's code against R2's
            # manifest and every swap failed with `CHECKSUM MISMATCH:
            # chunk_pieces.py` (job 27463, 2026-10-13 -- the first swap any
            # campaign ever reached).
            #
            # These are repo paths (`scripts/`, `config/`), not data paths, and
            # the loader resolves them under PROJECT_ROOT. Everything else keeps
            # its path relative to data/processed and unpacks into DATA_ROOT,
            # which _campaign_body.sh links to $PROJECT_ROOT/data/processed.
            #
            # A GIT CHECKOUT WINS OVER R2. `code`/`configs` in the bucket are the
            # fallback for when GitHub is unreachable, not the source of truth --
            # the DGX checkout is git (2026-08-30). Staging them over a checkout
            # silently reverts whatever git has that the last upload does not: on
            # 2026-08-30 job 22336 rolled back five files mid-session, including
            # the quota ceiling and the rclone resolver this very script needs,
            # and the next job then failed on the reverted copy. rclone --checksum
            # cannot save us here, because the bucket copy is genuinely different,
            # just older.
            if [ -z "${TRIMODAL_FORCE_CODE_STAGE:-}" ]                && git -C "$PROJECT_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
                log "skipping $dataset: $PROJECT_ROOT is a git checkout, and git is"
                log "  the source of truth for code. Set TRIMODAL_FORCE_CODE_STAGE=1"
                log "  to restore from R2 anyway (do that only when git is unreachable)."
                # The bucket's manifest describes the bucket's copy, so it must
                # not be used to judge git's copy -- every commit made since the
                # last upload would read as corruption.
                SKIP_CODE_VERIFY=1
                continue
            fi
            if [ "$PIECES_ONLY" = "1" ]; then continue; fi
            log "staging $dataset into $PROJECT_ROOT"
            fetch "$dataset" "$PROJECT_ROOT" "$PHASE"
            ;;
        results)
            if [ "$PIECES_ONLY" = "1" ]; then continue; fi
            log "staging $dataset from $R2_RESULTS"
            R2_DATA="$R2_RESULTS" fetch "" "$RESULTS_ROOT" "$PHASE"
            ;;
        *)
            if [ "$PIECES_ONLY" = "1" ]; then continue; fi
            log "staging $dataset"
            fetch "$dataset" "$DATA_ROOT" "$PHASE"
            ;;
    esac
done

# ---- verify what landed ---------------------------------------------------
verify_failed=0
SKIP_CODE_VERIFY="${SKIP_CODE_VERIFY:-}"
while IFS= read -r manifest; do
    case "$(basename "$manifest")" in
        checksums_code.json|checksums_configs.json)
            if [ -n "$SKIP_CODE_VERIFY" ]; then
                log "skipping $(basename "$manifest"): it describes R2's copy of the"
                log "  code, and this checkout is git's. Verified by git, not by sha."
                continue
            fi
            ;;
        # `checksums.json` is a CHUNK CUT's own manifest, and it lists all eight
        # pieces. Only the train phase stages any of them: the val swap evicts
        # them to make room for the val split, and _campaign_body.sh runs
        # `evict_data.sh --pieces-all` before the eval phase. In those phases
        # every file it names is legitimately absent, which trips the
        # "the manifest lists files but NONE of them are on disk" guard below --
        # a guard that exists to catch a fetch which silently moved nothing, and
        # which cannot tell that case apart from a deliberate eviction. So skip
        # the cut's manifest outside the train phases rather than weaken the
        # guard for everything else.
        checksums.json)
            case "$PHASE" in
                train|train_only) ;;
                *)
                    log "skipping $(basename "$(dirname "$manifest")")/checksums.json:"
                    log "  it lists chunk pieces, which the $PHASE phase does not stage."
                    continue
                    ;;
            esac
            ;;
    esac
    dir="$(dirname "$manifest")"
    log "verifying $(basename "$dir") against $(basename "$manifest")"
    python3 - "$manifest" "$dir" <<'PY' || verify_failed=1
import hashlib, json, sys
from pathlib import Path

manifest, directory = Path(sys.argv[1]), Path(sys.argv[2])
recorded = json.loads(manifest.read_text())
bad = checked = missing = 0
for name, meta in sorted(recorded.items()):
    path = directory / name
    if not path.exists():
        # Phase filtering means a manifest legitimately describes files this
        # phase did not stage (train phase does not fetch the test split), so a
        # missing file is not by itself an error. It is COUNTED, though: this
        # used to `continue` silently, which meant a staging step that fetched
        # nothing at all -- a wrong prefix, an empty listing -- still printed a
        # clean verification and the campaign trained on absent data.
        missing += 1
        continue
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    checked += 1
    if digest.hexdigest() != meta["sha256"]:
        print(f"  CHECKSUM MISMATCH: {name}", file=sys.stderr)
        bad += 1
    else:
        print(f"  ok {name}")

print(f"  verified {checked}, absent {missing} of {len(recorded)} recorded")
if recorded and checked == 0:
    print("  ERROR: the manifest lists files but NONE of them are on disk. "
          "Nothing was staged here -- this is a failed fetch, not a phase "
          "filter.", file=sys.stderr)
    sys.exit(1)
sys.exit(1 if bad else 0)
PY
    # `checksums_<dataset>.json` for a plain dataset -- two datasets can land in
    # the same directory (`text` and `index` both write into `index/`) and a
    # single shared name would let the second shadow the first, leaving the
    # first's files verified against nothing. `checksums.json` is the chunked
    # cut's own manifest, written by make_chunks.py.
done < <(find "$DATA_ROOT" "$PROJECT_ROOT" -name 'checksums*.json' 2>/dev/null | sort -u)

if [ "$verify_failed" -ne 0 ]; then
    echo "ERROR: checksum verification FAILED -- do not train on this data." >&2
    echo "       Re-stage with: $0 $CAMPAIGN ${PIECES[*]:+--pieces ${PIECES[*]}}" >&2
    exit 1
fi

printf '%s\n' "$CAMPAIGN" > "$STATE_DIR/current_campaign"
printf '%s\n' "${PIECES[*]:-}" > "$STATE_DIR/current_pieces"
printf '%s\n' "$PHASE" > "$STATE_DIR/current_phase"
log "campaign $CAMPAIGN staged. Used: $(used_gb) GB of ${QUOTA_CEILING_GB} GB ceiling."
