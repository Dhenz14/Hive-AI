#!/bin/bash
# Run v8 SFT training in WSL
# Usage: wsl bash /opt/hiveai/project/scripts/run_train_v8.sh
#
# Prerequisites:
#   - WSL venv activated: source /opt/hiveai-env/bin/activate
#   - v8.jsonl exported: python scripts/prepare_v5_data.py --export
#   - llama-server STOPPED (frees GPU VRAM for training)

set -euo pipefail

cd /opt/hiveai/project

# Activate venv
source /opt/hiveai-env/bin/activate

echo "========================================"
echo "  HiveAI v8 SFT Training"
echo "========================================"
echo "  Data: loras/training_data/v8.jsonl"
echo "  Pairs: $(wc -l < loras/training_data/v8.jsonl)"
echo "  Output: loras/v8/"
echo "========================================"

# Run training with v8 data, output to v8 dir
python scripts/train_v5.py \
    --data loras/training_data/v8.jsonl \
    --output-dir loras/v8 \
    --no-kl \
    2>&1 | tee loras/v8_training.log

echo ""
echo "Training complete. Next steps:"
echo "  1. Convert to GGUF:"
echo "     python /tmp/llama.cpp/convert_lora_to_gguf.py \\"
echo "       --base /root/.cache/huggingface/hub/models--unsloth--Qwen2.5-Coder-14B-Instruct/snapshots/b693088367af1e4b88711d4038d269733023310d \\"
echo "       loras/v8/ --outfile models/hiveai-v8-lora-f16.gguf"
echo ""
echo "  2. Copy GGUF to Windows:"
echo "     cp models/hiveai-v8-lora-f16.gguf /mnt/c/Users/theyc/HiveAi/Hive-AI/models/"
echo ""
echo "  3. Quick eval:"
echo "     python scripts/quick_eval.py --lora-only"
