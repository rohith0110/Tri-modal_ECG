#!/usr/bin/env bash
# Stage ONE campaign's data, verify checksums, refuse if it will not fit.
#
#   ./stage_data.sh 4                 # stage campaign 4
#   ./stage_data.sh 6 --pieces 0 1    # a chunked campaign: only these pieces
#   ./stage_data.sh 4 --dry-run       # decide and report, move no bytes
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
while [ $# -gt 0 ]; do
    case "$1" in
        --pieces) shift; while [ $# -gt 0 ] && [ "${1#-}" = "$1" ]; do PIECES+=("$1"); shift; done ;;
        --dry-run) DRY_RUN=1; shift ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [ -z "$CAMPAIGN" ] || ! campaign_spec "$CAMPAIGN" >/dev/null 2>&1; then
    echo "usage: $0 <campaign 1-11> [--pieces N...] [--dry-run]" >&2
    exit 2
fi

NAME="$(campaign_name "$CAMPAIGN")"
RESIDENT="$(campaign_resident "$CAMPAIGN")"
CHUNKED="$(campaign_chunked "$CAMPAIGN")"
DATASETS="$(campaign_datasets "$CAMPAIGN")"

log "campaign $CAMPAIGN ($NAME): resident ~${RESIDENT} GB, chunked=$CHUNKED"
log "transport=$(transport)  DATA_ROOT=$DATA_ROOT"

# A chunked campaign never stages the whole modality -- only the resident
# pieces (two at a time per §8.2 rule 2). Staging all of them would defeat the
# entire point and blow the quota.
if [ "$CHUNKED" = "yes" ] && [ ${#PIECES[@]} -eq 0 ]; then
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
require_fit "$RESIDENT" "campaign $CAMPAIGN ($NAME)" || exit 1

if [ "$DRY_RUN" -eq 1 ]; then
    log "dry run: would stage [$DATASETS] into $DATA_ROOT"
    [ ${#PIECES[@]} -gt 0 ] && log "dry run: pieces ${PIECES[*]}"
    exit 0
fi

mkdir -p "$DATA_ROOT" "$STATE_DIR"

for dataset in $DATASETS; do
    case "$dataset" in
        *_pieces)
            base="${dataset%_pieces}"
            for piece in "${PIECES[@]}"; do
                printf -v padded 'piece_%03d' "$piece"
                log "staging $base $padded"
                fetch "chunks/$base/$padded.h5" "$DATA_ROOT/$base" \
                    || fetch "chunks/$base/$padded.tar" "$DATA_ROOT/$base"
            done
            fetch "chunks/$base/checksums.json" "$DATA_ROOT/$base" || true
            fetch "chunks/$base/assignment.parquet" "$DATA_ROOT/$base" || true
            ;;
        code|configs)
            # These are repo paths (`scripts/`, `config/`), not data paths, and
            # the loader resolves them under PROJECT_ROOT. Everything else keeps
            # its path relative to data/processed and unpacks into DATA_ROOT,
            # which _campaign_body.sh links to $PROJECT_ROOT/data/processed.
            log "staging $dataset into $PROJECT_ROOT"
            fetch "$dataset" "$PROJECT_ROOT"
            ;;
        results)
            log "staging $dataset from $R2_RESULTS"
            R2_DATA="$R2_RESULTS" fetch "" "$RESULTS_ROOT"
            ;;
        *)
            log "staging $dataset"
            fetch "$dataset" "$DATA_ROOT"
            ;;
    esac
done

# ---- verify what landed ---------------------------------------------------
verify_failed=0
while IFS= read -r manifest; do
    dir="$(dirname "$manifest")"
    log "verifying $(basename "$dir") against $(basename "$manifest")"
    python3 - "$manifest" "$dir" <<'PY' || verify_failed=1
import hashlib, json, sys
from pathlib import Path

manifest, directory = Path(sys.argv[1]), Path(sys.argv[2])
recorded = json.loads(manifest.read_text())
bad = 0
for name, meta in sorted(recorded.items()):
    path = directory / name
    if not path.exists():
        continue                      # not staged this time; not an error here
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != meta["sha256"]:
        print(f"  CHECKSUM MISMATCH: {name}", file=sys.stderr)
        bad += 1
    else:
        print(f"  ok {name}")
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
log "campaign $CAMPAIGN staged. Used: $(used_gb) GB of ${QUOTA_CEILING_GB} GB ceiling."
