#!/bin/bash
# =============================================================================
# Hive AI Continual Learning Pipeline v1.0 — Full Cycle Orchestrator
#
# Runs the complete merge-then-freeze cycle for one domain:
#   1. Build surprise replay buffer
#   2. Train domain LoRA (rank 8, LoRA+, attn-only)
#   3. Safe merge (alpha grid search)
#   4. Consolidation epoch (LR/20, 100% replay)
#   5. Merge consolidation LoRA
#   6. Regression eval
#   7. Promote (if eval passes)
#
# Usage:
#   bash scripts/run_full_cycle.sh <domain> <data_path> <version> [prev_version]
#
# Example:
#   bash scripts/run_full_cycle.sh hive datasets/hive_data.jsonl v1-hive v1.0
#   bash scripts/run_full_cycle.sh cpp datasets/cpp_data.jsonl v2-cpp v1-hive
# =============================================================================
set -euo pipefail

DOMAIN=${1:?Usage: run_full_cycle.sh <domain> <data_path> <version> [prev_version]}
DATA_PATH=${2:?Usage: run_full_cycle.sh <domain> <data_path> <version> [prev_version]}
VERSION=${3:?Usage: run_full_cycle.sh <domain> <data_path> <version> [prev_version]}
PREV_VERSION=${4:-v1.0}

# Paths
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY_DIR="$PROJECT_ROOT/models/deploy"
TRAINING_DIR="/opt/hiveai/project/models/training"
REPLAY_DIR="$PROJECT_ROOT/replay"
LORA_OUTPUT="$PROJECT_ROOT/loras/${VERSION}"
CONSOL_OUTPUT="$PROJECT_ROOT/loras/${VERSION}_consolidation"
LOG_DIR="$PROJECT_ROOT/logs"

# Previous base paths
PREV_GGUF="$DEPLOY_DIR/current_base.gguf"
PREV_HF="$TRAINING_DIR/${PREV_VERSION}/hf"

# HF cache for GGUF conversion
HF_BASE_CACHE="/root/.cache/huggingface/hub/models--unsloth--Qwen2.5-Coder-14B-Instruct/snapshots/b693088367af1e4b88711d4038d269733023310d"

echo "============================================================"
echo "  Hive AI Continual Learning — Full Cycle"
echo "============================================================"
echo "  Domain:       $DOMAIN"
echo "  Data:         $DATA_PATH"
echo "  Version:      $VERSION"
echo "  Prev version: $PREV_VERSION"
echo "  Base GGUF:    $PREV_GGUF"
echo "  Base HF:      $PREV_HF"
echo "============================================================"

# Ensure directories exist
mkdir -p "$DEPLOY_DIR" "$REPLAY_DIR" "$LOG_DIR" "$LORA_OUTPUT"

# Verify prerequisites
if [ ! -f "$PREV_GGUF" ]; then
    echo "ERROR: Base GGUF not found: $PREV_GGUF"
    echo "  Copy your base model: cp models/Qwen2.5-Coder-14B-Instruct-Q5_K_M.gguf $PREV_GGUF"
    exit 1
fi

if [ ! -f "$DATA_PATH" ]; then
    echo "ERROR: Training data not found: $DATA_PATH"
    exit 1
fi

START_TIME=$(date +%s)

# =============================================================================
# Step 1: Build surprise replay buffer
# =============================================================================
echo ""
echo "=== Step 1/7: Building SuRe replay buffer ==="
python "$PROJECT_ROOT/scripts/replay_sampler.py" \
    --replay-dir "$REPLAY_DIR" \
    --keep 500 \
    --output "$REPLAY_DIR/sampled.jsonl" \
    --fallback-diversity \
    2>&1 | tee "$LOG_DIR/${VERSION}_01_replay.log"

# =============================================================================
# Step 2: Train domain LoRA (rank 8, LoRA+, attn-only)
# =============================================================================
echo ""
echo "=== Step 2/7: Training ${DOMAIN} LoRA ==="
python "$PROJECT_ROOT/scripts/train_v5.py" \
    --base-model-hf "$PREV_HF" \
    --data "$DATA_PATH" \
    --replay-dir "$REPLAY_DIR" \
    --replay-ratio 0.25 \
    --output-dir "$LORA_OUTPUT" \
    --rank 8 \
    --lora-plus \
    --attn-only \
    --no-kl \
    --epochs 2 \
    2>&1 | tee "$LOG_DIR/${VERSION}_02_train.log"

echo "  LoRA adapter saved to: $LORA_OUTPUT"

# =============================================================================
# Step 3: Convert LoRA to GGUF for merge
# =============================================================================
echo ""
echo "=== Step 3/7: Converting LoRA to GGUF ==="
LORA_GGUF="$PROJECT_ROOT/models/hiveai-${VERSION}-lora-f16.gguf"
python /tmp/llama.cpp/convert_lora_to_gguf.py \
    --base "$HF_BASE_CACHE" \
    "$LORA_OUTPUT" \
    --outfile "$LORA_GGUF" \
    2>&1 | tee "$LOG_DIR/${VERSION}_03_convert.log"

echo "  LoRA GGUF: $LORA_GGUF"

# =============================================================================
# Step 4: Safe merge (alpha grid search)
# =============================================================================
echo ""
echo "=== Step 4/7: Safe merge with alpha grid search ==="
MERGE_OUTPUT="$DEPLOY_DIR/${VERSION}"
python "$PROJECT_ROOT/scripts/safe_merge.py" \
    --base-gguf "$PREV_GGUF" \
    --lora-gguf "$LORA_GGUF" \
    --output-dir "$MERGE_OUTPUT" \
    --validation-data "$REPLAY_DIR/sampled.jsonl" \
    --alphas "0.75,0.85,0.95,1.0" \
    --version "$VERSION" \
    --base-hf "$PREV_HF" \
    --lora-hf "$LORA_OUTPUT" \
    --output-hf "$TRAINING_DIR/${VERSION}/hf" \
    2>&1 | tee "$LOG_DIR/${VERSION}_04_merge.log"

# =============================================================================
# Step 5: Consolidation epoch
# =============================================================================
echo ""
echo "=== Step 5/7: Consolidation training ==="
python "$PROJECT_ROOT/scripts/consolidation_train.py" \
    --base-model-hf "$TRAINING_DIR/${VERSION}/hf" \
    --replay-data "$REPLAY_DIR/sampled.jsonl" \
    --output-dir "$CONSOL_OUTPUT" \
    2>&1 | tee "$LOG_DIR/${VERSION}_05_consolidation.log"

# Convert consolidation LoRA to GGUF
CONSOL_GGUF="$PROJECT_ROOT/models/hiveai-${VERSION}-consol-f16.gguf"
python /tmp/llama.cpp/convert_lora_to_gguf.py \
    --base "$HF_BASE_CACHE" \
    "$CONSOL_OUTPUT" \
    --outfile "$CONSOL_GGUF" \
    2>&1 | tee -a "$LOG_DIR/${VERSION}_05_consolidation.log"

# =============================================================================
# Step 6: Merge consolidation LoRA (alpha=1.0, no grid search)
# =============================================================================
echo ""
echo "=== Step 6/7: Merging consolidation LoRA ==="
python "$PROJECT_ROOT/scripts/safe_merge.py" \
    --base-gguf "$MERGE_OUTPUT/merged.gguf" \
    --lora-gguf "$CONSOL_GGUF" \
    --output-dir "$MERGE_OUTPUT" \
    --validation-data "$REPLAY_DIR/sampled.jsonl" \
    --alphas "1.0" \
    --version "${VERSION}-consolidated" \
    --base-hf "$TRAINING_DIR/${VERSION}/hf" \
    --lora-hf "$CONSOL_OUTPUT" \
    --output-hf "$TRAINING_DIR/${VERSION}/hf" \
    2>&1 | tee "$LOG_DIR/${VERSION}_06_consol_merge.log"

# =============================================================================
# Step 7: Regression eval
# =============================================================================
echo ""
echo "=== Step 7/7: Regression evaluation ==="
echo ""
echo "  ================================================================"
echo "  ACTION REQUIRED: Start llama-server with the new merged GGUF:"
echo ""
echo "    llama-server.exe -m $MERGE_OUTPUT/merged.gguf \\"
echo "        --port 11435 --flash-attn on \\"
echo "        --cache-type-k q8_0 --cache-type-v q4_0 \\"
echo "        --ctx-size 8192 -ngl 99"
echo ""
echo "  Then press ENTER to continue with regression eval..."
echo "  ================================================================"
read -r

python "$PROJECT_ROOT/scripts/regression_eval.py" \
    --model-version "$VERSION" \
    --threshold 0.03 \
    2>&1 | tee "$LOG_DIR/${VERSION}_07_eval.log"

EVAL_EXIT=$?

# =============================================================================
# Promote or rollback
# =============================================================================
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo "============================================================"
if [ $EVAL_EXIT -eq 0 ]; then
    echo "  CYCLE PASSED — Promoting $VERSION as new base"
    cp "$MERGE_OUTPUT/merged.gguf" "$DEPLOY_DIR/current_base.gguf"
    echo "  New base: $DEPLOY_DIR/current_base.gguf"
    echo "  Training HF: $TRAINING_DIR/${VERSION}/hf"
    echo ""
    echo "  Next domain command:"
    echo "    bash scripts/run_full_cycle.sh <next_domain> <data.jsonl> v<N+1> $VERSION"
else
    echo "  CYCLE FAILED — Regression detected!"
    echo "  NOT promoting $VERSION"
    echo "  Current base unchanged: $PREV_GGUF"
    echo ""
    echo "  Troubleshooting:"
    echo "    - Increase replay: --replay-ratio 0.35"
    echo "    - Reduce rank: --rank 4"
    echo "    - Check logs: $LOG_DIR/${VERSION}_*.log"
fi
echo ""
echo "  Total time: ${ELAPSED}s ($((ELAPSED / 3600))h $((ELAPSED % 3600 / 60))m)"
echo "============================================================"

# Cleanup intermediate files
echo ""
echo "Cleaning up intermediate files..."
rm -f "$LORA_GGUF" "$CONSOL_GGUF"
rm -rf "$CONSOL_OUTPUT"
# Keep $LORA_OUTPUT (the trained adapter) for reference
echo "  Kept: $LORA_OUTPUT (trained adapter)"
echo "  Removed: intermediate GGUF files, consolidation adapter"
echo "Done."
