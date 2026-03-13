#!/bin/bash
set -e
source /opt/hiveai-env/bin/activate
cd /opt/hiveai/project
export HF_HUB_OFFLINE=1
export TORCH_CUDA_ARCH_LIST='8.9'
export LLAMA_CPP_DIR=/opt/hiveai/llama-cpp-build/build

echo '========================================='
echo 'RESUMING v7-think pipeline (phase 2)'
echo 'Fixes: no CURLoRA for consolidation,'
echo '  convert_hf_to_gguf.py path fixed,'
echo '  NaN detector added to quality alarm'
echo '========================================='

# Sync latest scripts from Windows (has the bug fixes)
echo 'Syncing scripts from Windows...'
for f in train_v5.py safe_merge.py consolidation_train.py; do
    cp "/mnt/c/Users/theyc/HiveAi/Hive-AI/scripts/$f" "/opt/hiveai/project/scripts/$f"
    sed -i 's/\r$//' "/opt/hiveai/project/scripts/$f"
done
echo 'Scripts synced and CRLF fixed'

# Clean up failed consolidation
rm -rf /opt/hiveai/project/loras/v7-think_consolidation

# ---- Step 1: Convert merged HF to GGUF + quantize ----
echo ''
echo '=== STEP 1/5: Convert HF to GGUF + Quantize ==='
# The HF merge succeeded (28GB model.safetensors) but GGUF convert failed
python /opt/hiveai/llama-cpp-build/convert_hf_to_gguf.py \
    /opt/hiveai/project/models/training/v7-think/hf \
    --outfile /opt/hiveai/project/models/deploy/v7-think/merged-f16.gguf \
    --outtype f16 \
    2>&1 | tee logs/v7-think_04b_convert.log

mkdir -p /opt/hiveai/project/models/deploy/v7-think
/opt/hiveai/llama-cpp-build/build/bin/llama-quantize \
    /opt/hiveai/project/models/deploy/v7-think/merged-f16.gguf \
    /opt/hiveai/project/models/deploy/v7-think/merged.gguf \
    Q5_K_M \
    2>&1 | tee -a logs/v7-think_04b_convert.log
echo 'Step 1 DONE'

# ---- Step 2: Consolidation Training (NO CURLoRA) ----
echo ''
echo '=== STEP 2/5: Consolidation Training (no CURLoRA) ==='
python scripts/consolidation_train.py \
    --base-model-hf /opt/hiveai/project/models/training/v7-think/hf \
    --replay-data replay/sampled.jsonl \
    --output-dir /opt/hiveai/project/loras/v7-think_consolidation \
    2>&1 | tee logs/v7-think_05_consolidation.log
echo 'Step 2 DONE'

# ---- Step 3: Convert Consolidation + Merge ----
echo ''
echo '=== STEP 3/5: Consolidation Merge ==='
HF_BASE_CACHE=$(find /root/.cache/huggingface/hub/models--unsloth--Qwen2.5-Coder-14B-Instruct/snapshots -maxdepth 1 -mindepth 1 -type d | head -1)

python /opt/hiveai/llama-cpp-build/convert_lora_to_gguf.py \
    --base "$HF_BASE_CACHE" \
    /opt/hiveai/project/loras/v7-think_consolidation \
    --outfile /opt/hiveai/project/models/hiveai-v7-think-consol-f16.gguf \
    2>&1 | tee logs/v7-think_05b_consol_convert.log

python scripts/safe_merge.py \
    --base-gguf models/deploy/v7-think/merged.gguf \
    --lora-gguf models/hiveai-v7-think-consol-f16.gguf \
    --output-dir models/deploy/v7-think \
    --validation-data replay/sampled.jsonl \
    --alphas 1.0 \
    --version v7-think-consolidated \
    --base-hf /opt/hiveai/project/models/training/v7-think/hf \
    --lora-hf /opt/hiveai/project/loras/v7-think_consolidation \
    --output-hf /opt/hiveai/project/models/training/v7-think/hf \
    2>&1 | tee logs/v7-think_06_consol_merge.log
echo 'Step 3 DONE'

# ---- Step 4: Regression Eval (60 probes) ----
echo ''
echo '=== STEP 4/5: Regression Eval ==='
MERGED_GGUF=models/deploy/v7-think/merged.gguf
if [ ! -f "$MERGED_GGUF" ]; then
    echo "ERROR: No merged GGUF found at $MERGED_GGUF"
    exit 1
fi

/opt/hiveai/llama-cpp-build/build/bin/llama-server \
    -m "$MERGED_GGUF" \
    --port 11435 \
    --flash-attn on \
    --cache-type-k q8_0 --cache-type-v q4_0 \
    --ctx-size 8192 -ngl 99 --threads 8 \
    > logs/v7-think_eval_server.log 2>&1 &
SERVER_PID=$!

echo "Waiting for llama-server PID=$SERVER_PID..."
for i in $(seq 1 120); do
    HEALTH=$(curl -s http://localhost:11435/health 2>/dev/null || echo '')
    if echo "$HEALTH" | grep -q '"ok"'; then
        echo "Server ready!"
        break
    fi
    sleep 3
done

timeout 3600 python -u scripts/regression_eval.py \
    --model-version v7-think \
    --server-url http://localhost:11435 \
    --threshold 0.01 \
    2>&1 | tee logs/v7-think_07_eval.log
EVAL_EXIT=$?

kill $SERVER_PID 2>/dev/null || true

if [ $EVAL_EXIT -ne 0 ]; then
    echo 'EVAL FAILED - v7-think NOT promoted'
    exit 1
fi
echo 'Step 4 DONE'

# ---- Step 5: Promote ----
echo ''
echo '=== STEP 5/5: Promote ==='
cp models/deploy/v7-think/merged.gguf models/deploy/current_base.gguf
echo 'v7-think PROMOTED as new base!'

# Cleanup intermediates
rm -f models/deploy/v7-think/merged-f16.gguf
rm -f models/hiveai-v7-think-lora-f16.gguf models/hiveai-v7-think-consol-f16.gguf
rm -rf /opt/hiveai/project/loras/v7-think_consolidation

echo ''
echo '========================================='
echo 'v7-think pipeline COMPLETE'
echo '========================================='
