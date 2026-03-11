#!/bin/bash
# micro_train.sh — Simplified micro-training wrapper
#
# Usage:
#   bash scripts/micro_train.sh <batch_file> [version] [domain]
#
# Examples:
#   bash scripts/micro_train.sh datasets/thinking_batch2.jsonl v3-think thinking
#   bash scripts/micro_train.sh datasets/hive_batch1.jsonl              # auto-detect version & domain
#
# Auto-detects:
#   - Previous version from score_ledger.json (latest entry)
#   - Domain from filename (hive_*, thinking_*, rust_*, etc.)
#   - Version name from domain + timestamp

set -euo pipefail

PROJECT="/opt/hiveai/project"
cd "$PROJECT"

BATCH="${1:?Usage: micro_train.sh <batch_file> [version] [domain]}"
VERSION="${2:-}"
DOMAIN="${3:-}"

# Validate batch file exists
if [ ! -f "$BATCH" ]; then
    echo "ERROR: Batch file not found: $BATCH"
    exit 1
fi

# Count pairs
PAIR_COUNT=$(wc -l < "$BATCH" | tr -d ' ')
echo "Batch: $BATCH ($PAIR_COUNT pairs)"

# Auto-detect domain from filename
if [ -z "$DOMAIN" ]; then
    BASENAME=$(basename "$BATCH" .jsonl)
    case "$BASENAME" in
        *hive*)     DOMAIN="hive" ;;
        *think*)    DOMAIN="thinking" ;;
        *rust*)     DOMAIN="rust" ;;
        *go*)       DOMAIN="go" ;;
        *cpp*|*c++*) DOMAIN="cpp" ;;
        *js*|*javascript*|*typescript*) DOMAIN="javascript" ;;
        *python*)   DOMAIN="python" ;;
        *)          DOMAIN="general" ;;
    esac
    echo "Auto-detected domain: $DOMAIN"
fi

# Auto-detect previous version from score ledger
PREV_VERSION=""
if [ -f "$PROJECT/score_ledger.json" ]; then
    PREV_VERSION=$(python3 -c "
import json
with open('$PROJECT/score_ledger.json') as f:
    ledger = json.load(f)
versions = [k for k in ledger.keys() if k != 'timestamp']
if versions:
    print(versions[-1])
" 2>/dev/null || true)
fi

if [ -n "$PREV_VERSION" ]; then
    echo "Previous version: $PREV_VERSION (from score_ledger.json)"
else
    echo "No previous version found (first training cycle)"
fi

# Auto-generate version name
if [ -z "$VERSION" ]; then
    TIMESTAMP=$(date +%m%d)
    VERSION="${DOMAIN}-${TIMESTAMP}"
    echo "Auto-generated version: $VERSION"
fi

echo ""
echo "============================================"
echo "  Micro-Training: $VERSION"
echo "  Domain:   $DOMAIN"
echo "  Batch:    $BATCH ($PAIR_COUNT pairs)"
echo "  Previous: ${PREV_VERSION:-none}"
echo "============================================"
echo ""

# Run the full cycle
exec bash "$PROJECT/scripts/run_full_cycle.sh" "$DOMAIN" "$BATCH" "$VERSION" "$PREV_VERSION"
