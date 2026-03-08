#!/bin/bash
# HiveAI Eternal Brain v8 — Category LoRA + TIES Merge Pipeline
#
# Usage: wsl -d Ubuntu-24.04 bash /opt/hiveai/project/scripts/run_train_v8.sh
#
# Prerequisites:
#   - WSL Ubuntu-24.04 with /opt/hiveai-env/ venv
#   - v7 adapter at loras/v7/
#   - v8.jsonl at loras/training_data/v8.jsonl
#   - llama-server STOPPED (frees GPU VRAM)
#
# Pipeline:
#   1. Build replay buffer from v7 (500 pairs, diversity-sampled)
#   2. Split v8 data by category + mix replay
#   3. Train per-category LoRAs (warm-start from v7, 2 epochs each)
#   4. TIES merge all category LoRAs + v7 into unified v8
#   5. Convert to GGUF for llama-server
#
# Estimated time: ~2.5h total (4 categories × ~30-40 min + merge/convert)

set -euo pipefail

cd /opt/hiveai/project
source /opt/hiveai-env/bin/activate

echo "========================================================"
echo "  HiveAI Eternal Brain v8"
echo "  Category LoRA + TIES Merge Pipeline"
echo "========================================================"
echo "  Base:      v7 adapter (loras/v7/)"
echo "  Data:      loras/training_data/v8.jsonl"
echo "  Pairs:     $(wc -l < loras/training_data/v8.jsonl)"
echo "  Strategy:  Per-category warm-start + TIES merge"
echo "  Categories: go, cpp, rust, hive"
echo "========================================================"
echo ""

# ── Step 1: Build replay buffer ──
echo "=== STEP 1/5: Building replay buffer ==="
python scripts/build_replay_buffer.py \
    --source loras/training_data/v7.jsonl \
    --keep 500
echo ""

# ── Step 2: Split data by category ──
echo "=== STEP 2/5: Splitting data by category + mixing replay ==="
python scripts/prepare_category_data.py \
    --v8 loras/training_data/v8.jsonl
echo ""

# ── Step 3: Train per-category LoRAs ──
echo "=== STEP 3/5: Training category LoRAs ==="
CATEGORIES="go cpp rust hive"
TRAINED=""

for cat in $CATEGORIES; do
    DATA="loras/training_data/categories/${cat}_with_replay.jsonl"
    OUTPUT="loras/v8_${cat}"

    if [ ! -f "$DATA" ]; then
        echo "  SKIP: $cat (no data file at $DATA)"
        continue
    fi

    PAIR_COUNT=$(wc -l < "$DATA")
    if [ "$PAIR_COUNT" -lt 20 ]; then
        echo "  SKIP: $cat (only $PAIR_COUNT pairs — too few)"
        continue
    fi

    echo ""
    echo "--- Training $cat LoRA ($PAIR_COUNT pairs) ---"
    START_TIME=$(date +%s)

    python scripts/train_v5.py \
        --warm-start loras/v7 \
        --data "$DATA" \
        --output-dir "$OUTPUT" \
        --epochs 2 \
        --no-kl \
        2>&1 | tee "loras/v8_${cat}_training.log"

    END_TIME=$(date +%s)
    ELAPSED=$(( (END_TIME - START_TIME) / 60 ))
    echo "  $cat training complete in ${ELAPSED} minutes"
    TRAINED="$TRAINED $cat"
done

echo ""
echo "Trained adapters:$TRAINED"
echo ""

# ── Step 4: TIES merge ──
echo "=== STEP 4/5: TIES merge ==="
# Build category dir args
CAT_ARGS=""
for cat in $CATEGORIES; do
    if [ -d "loras/v8_${cat}" ] && [ -f "loras/v8_${cat}/adapter_config.json" ]; then
        CAT_ARGS="$CAT_ARGS loras/v8_${cat}"
    fi
done

if [ -z "$CAT_ARGS" ]; then
    echo "ERROR: No category adapters were trained successfully!"
    exit 1
fi

python scripts/merge_category_loras.py \
    --v7 loras/v7 \
    --categories $CAT_ARGS \
    --output loras/v8 \
    --density 0.35 \
    --v7-weight 1.4
echo ""

# ── Step 5: Convert to GGUF ──
echo "=== STEP 5/5: Converting to GGUF ==="
HF_BASE="/root/.cache/huggingface/hub/models--unsloth--Qwen2.5-Coder-14B-Instruct/snapshots/b693088367af1e4b88711d4038d269733023310d"

if [ ! -d "$HF_BASE" ]; then
    # Try to find the snapshot dir
    HF_BASE=$(find /root/.cache/huggingface/hub/models--*Qwen2.5-Coder-14B* -name "config.json" -path "*/snapshots/*" -exec dirname {} \; 2>/dev/null | head -1)
    if [ -z "$HF_BASE" ]; then
        echo "WARNING: HF base model not found for GGUF conversion."
        echo "Manual conversion needed:"
        echo "  python /tmp/llama.cpp/convert_lora_to_gguf.py --base <HF_PATH> loras/v8/ --outfile models/hiveai-v8-lora-f16.gguf"
        exit 0
    fi
fi

# Ensure llama.cpp converter is available
if [ ! -f "/tmp/llama.cpp/convert_lora_to_gguf.py" ]; then
    echo "Cloning llama.cpp for converter..."
    git clone --depth 1 https://github.com/ggerganov/llama.cpp.git /tmp/llama.cpp 2>/dev/null || true
fi

python /tmp/llama.cpp/convert_lora_to_gguf.py \
    --base "$HF_BASE" \
    loras/v8/ \
    --outfile models/hiveai-v8-lora-f16.gguf

echo ""
echo "Copying GGUF to Windows..."
cp models/hiveai-v8-lora-f16.gguf /mnt/c/Users/theyc/HiveAi/Hive-AI/models/

echo ""
echo "========================================================"
echo "  v8 TRAINING COMPLETE"
echo "========================================================"
echo "  Adapter:  loras/v8/"
echo "  GGUF:     models/hiveai-v8-lora-f16.gguf"
echo "  Copied:   /mnt/c/Users/theyc/HiveAi/Hive-AI/models/"
echo ""
echo "  Next steps:"
echo "    1. Start llama-server with v8 LoRA:"
echo "       --lora models/hiveai-v8-lora-f16.gguf"
echo "    2. Quick eval:"
echo "       python scripts/quick_eval.py --lora-only"
echo "========================================================"
