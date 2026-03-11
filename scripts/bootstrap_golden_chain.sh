#!/bin/bash
# Bootstrap Golden Chain: Download bf16 HF model, merge v1-hive + v2-think, quantize, eval
# This is a ONE-TIME setup to establish the bf16 source of truth.
#
# After this completes:
#   - models/golden/v2-think-hf/ = bf16 HF checkpoint (source of truth)
#   - models/deploy/current_base.gguf = Q5_K_M GGUF for inference
#   - All future merges go through bf16 path (zero quantization drift)

set -euo pipefail

export LLAMA_CPP_DIR="/tmp/llama_cpp_build/build"
export HF_HUB_OFFLINE=0  # Need online to download bf16 model

QUANTIZE="${LLAMA_CPP_DIR}/bin/llama-quantize"
PERPLEXITY="${LLAMA_CPP_DIR}/bin/llama-perplexity"

PROJECT="/opt/hiveai/project"
GOLDEN_DIR="${PROJECT}/models/golden"
V1_LORA="${PROJECT}/loras/v1-hive"
V2_LORA="${PROJECT}/loras/v2-think"
VALIDATION="${PROJECT}/datasets/thinking_500.jsonl"

cd "$PROJECT"

echo "============================================================"
echo "  Golden Chain Bootstrap"
echo "============================================================"
echo "  Step 1: Download bf16 HF base (if needed)"
echo "  Step 2: Merge v1-hive LoRA into bf16 → v1-hive-hf"
echo "  Step 3: Merge v2-think LoRA into v1-hive-hf → v2-think-hf"
echo "  Step 4: Quantize v2-think-hf → Q5_K_M GGUF"
echo "  Step 5: Perplexity eval on Q5_K_M"
echo "  Step 6: Promote if good"
echo "============================================================"

# Activate venv
source /opt/hiveai-env/bin/activate 2>/dev/null || true

mkdir -p "$GOLDEN_DIR"

###############################################################################
# STEP 1: Download bf16 HF base (skip if permanent copy exists)
###############################################################################
ORIGINAL_BF16="${GOLDEN_DIR}/original-bf16"
if [ -f "${ORIGINAL_BF16}/config.json" ] && ls "${ORIGINAL_BF16}"/*.safetensors &>/dev/null; then
    SHARD_COUNT=$(ls "${ORIGINAL_BF16}"/*.safetensors 2>/dev/null | wc -l)
    echo ""
    echo "[Step 1/6] SKIP — permanent bf16 base already exists (${SHARD_COUNT} safetensors)"
    echo "  Path: ${ORIGINAL_BF16}"
    BASE_HF="$ORIGINAL_BF16"
    export HF_HUB_OFFLINE=1
else
echo ""
echo "[Step 1/6] Downloading bf16 HF base model..."
python3 -c "
import os, glob

model_id = 'Qwen/Qwen2.5-Coder-14B-Instruct'

# Sequential download — one file at a time to avoid connection saturation
from huggingface_hub import hf_hub_download, list_repo_files

# Get all files in the repo
files = list_repo_files(model_id)
print(f'Repo has {len(files)} files')

# Download each file sequentially (small files first, then safetensors)
safetensor_files = sorted([f for f in files if f.endswith('.safetensors')])
other_files = sorted([f for f in files if not f.endswith('.safetensors')])

for i, fname in enumerate(other_files + safetensor_files):
    print(f'  [{i+1}/{len(files)}] {fname}...', flush=True)
    hf_hub_download(model_id, fname)

# Get the snapshot path
from huggingface_hub import snapshot_download
path = snapshot_download(model_id, local_files_only=True)
print(f'Base model at: {path}')

safetensors = glob.glob(os.path.join(path, '*.safetensors'))
print(f'Found {len(safetensors)} safetensor files')
if not safetensors:
    raise RuntimeError('No safetensor files found — download may be incomplete')
print('DOWNLOAD_OK')
" 2>&1 | tee /tmp/golden_download.log

if ! grep -q "DOWNLOAD_OK" /tmp/golden_download.log; then
    echo "FATAL: bf16 model download failed"
    exit 1
fi

# Extract the base path from the log
BASE_HF=$(grep "Base model at:" /tmp/golden_download.log | sed 's/Base model at: //')
echo "  Base HF path: $BASE_HF"

# Keep a permanent copy outside HF cache so we never download again
ORIGINAL_BF16="${GOLDEN_DIR}/original-bf16"
if [ ! -f "${ORIGINAL_BF16}/config.json" ]; then
    echo "  Cloning bf16 base to permanent location: ${ORIGINAL_BF16}"
    echo "  (This way we never need to download 28GB again)"
    mkdir -p "$ORIGINAL_BF16"
    cp -a "$BASE_HF"/* "$ORIGINAL_BF16"/
    echo "  Permanent copy: $(du -sh "$ORIGINAL_BF16" | awk '{print $1}')"
else
    echo "  Permanent bf16 base already exists at ${ORIGINAL_BF16}"
fi

# Use the permanent copy as base from here on
BASE_HF="$ORIGINAL_BF16"

# Now go offline for the rest
export HF_HUB_OFFLINE=1

fi  # end of step 1 skip check

###############################################################################
# STEP 2: Merge v1-hive LoRA → bf16
###############################################################################
echo ""
echo "[Step 2/6] Merging v1-hive LoRA into bf16 base..."
V1_HF="${GOLDEN_DIR}/v1-hive-hf"

if [ -f "${V1_HF}/config.json" ]; then
    echo "  Already exists: ${V1_HF}, skipping"
else
    python3 -c "
import torch, os, json, shutil
from peft import PeftModel, PeftConfig
from transformers import AutoModelForCausalLM, AutoTokenizer

base_path = '${BASE_HF}'
lora_path = '${V1_LORA}'
output_path = '${V1_HF}'

print(f'Loading base model from {base_path}...')
model = AutoModelForCausalLM.from_pretrained(
    base_path, torch_dtype=torch.bfloat16, device_map='cpu',
    low_cpu_mem_usage=True
)
tokenizer = AutoTokenizer.from_pretrained(base_path)

# Fix adapter_config to point to correct base
config_path = os.path.join(lora_path, 'adapter_config.json')
with open(config_path) as f:
    config = json.load(f)
original_base = config.get('base_model_name_or_path', '')
config['base_model_name_or_path'] = base_path
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)

print(f'Loading v1-hive LoRA from {lora_path}...')
model = PeftModel.from_pretrained(model, lora_path)

print('Merging and unloading...')
model = model.merge_and_unload()

print(f'Saving to {output_path}...')
os.makedirs(output_path, exist_ok=True)
model.save_pretrained(output_path, safe_serialization=True)
tokenizer.save_pretrained(output_path)

# Restore original adapter config
config['base_model_name_or_path'] = original_base
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)

print('V1_MERGE_OK')
" 2>&1 | tee /tmp/golden_v1_merge.log

    if ! grep -q "V1_MERGE_OK" /tmp/golden_v1_merge.log; then
        echo "FATAL: v1-hive merge failed"
        exit 1
    fi
fi

###############################################################################
# STEP 3: Merge v2-think LoRA → v1-hive-hf
###############################################################################
echo ""
echo "[Step 3/6] Merging v2-think LoRA into v1-hive-hf..."
V2_HF="${GOLDEN_DIR}/v2-think-hf"

if [ -f "${V2_HF}/config.json" ]; then
    echo "  Already exists: ${V2_HF}, skipping"
else
    python3 -c "
import torch, os, json
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base_path = '${V1_HF}'
lora_path = '${V2_LORA}'
output_path = '${V2_HF}'

print(f'Loading v1-hive-hf from {base_path}...')
model = AutoModelForCausalLM.from_pretrained(
    base_path, torch_dtype=torch.bfloat16, device_map='cpu',
    low_cpu_mem_usage=True
)
tokenizer = AutoTokenizer.from_pretrained(base_path)

# Fix adapter_config to point to v1-hive-hf base
config_path = os.path.join(lora_path, 'adapter_config.json')
with open(config_path) as f:
    config = json.load(f)
original_base = config.get('base_model_name_or_path', '')
config['base_model_name_or_path'] = base_path
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)

print(f'Loading v2-think LoRA from {lora_path}...')
model = PeftModel.from_pretrained(model, lora_path)

print('Merging and unloading...')
model = model.merge_and_unload()

print(f'Saving to {output_path}...')
os.makedirs(output_path, exist_ok=True)
model.save_pretrained(output_path, safe_serialization=True)
tokenizer.save_pretrained(output_path)

# Restore original adapter config
config['base_model_name_or_path'] = original_base
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)

print('V2_MERGE_OK')
" 2>&1 | tee /tmp/golden_v2_merge.log

    if ! grep -q "V2_MERGE_OK" /tmp/golden_v2_merge.log; then
        echo "FATAL: v2-think merge failed"
        exit 1
    fi
fi

###############################################################################
# STEP 4: Convert HF → GGUF → Q5_K_M
###############################################################################
echo ""
echo "[Step 4/6] Converting v2-think-hf → GGUF Q5_K_M..."
V2_GGUF_F16="${GOLDEN_DIR}/v2-think-f16.gguf"
V2_GGUF_Q5="${GOLDEN_DIR}/v2-think-q5km.gguf"

if [ -f "$V2_GGUF_Q5" ]; then
    echo "  Already exists: ${V2_GGUF_Q5}, skipping"
else
    # Find convert script
    CONVERT_SCRIPT=""
    for candidate in /tmp/llama_cpp_build/convert_hf_to_gguf.py /tmp/llama.cpp/convert_hf_to_gguf.py; do
        if [ -f "$candidate" ]; then
            CONVERT_SCRIPT="$candidate"
            break
        fi
    done

    if [ -z "$CONVERT_SCRIPT" ]; then
        echo "  ERROR: convert_hf_to_gguf.py not found"
        echo "  Falling back to llama-export-lora F16 + quantize..."
        # Fallback: use existing F16 merged.gguf and just quantize it
        if [ -f "${PROJECT}/models/v2-think/merged.gguf" ]; then
            echo "  Quantizing existing F16 merged.gguf..."
            "$QUANTIZE" "${PROJECT}/models/v2-think/merged.gguf" "$V2_GGUF_Q5" Q5_K_M 2>&1 | tail -5
        else
            echo "FATAL: No F16 GGUF and no convert script"
            exit 1
        fi
    else
        echo "  Step 4a: HF → F16 GGUF..."
        python3 "$CONVERT_SCRIPT" "$V2_HF" --outfile "$V2_GGUF_F16" --outtype f16 2>&1 | tail -5
        echo "  Step 4b: F16 → Q5_K_M..."
        "$QUANTIZE" "$V2_GGUF_F16" "$V2_GGUF_Q5" Q5_K_M 2>&1 | tail -5
        # Remove F16 (huge, not needed)
        rm -f "$V2_GGUF_F16"
        echo "  Cleaned up F16 intermediate"
    fi
fi

echo "  Q5_K_M GGUF: $(ls -lh "$V2_GGUF_Q5" | awk '{print $5}')"

###############################################################################
# STEP 5: Perplexity eval
###############################################################################
echo ""
echo "[Step 5/6] Running perplexity evaluation..."

# Prepare validation text
python3 -c "
import json
texts = []
with open('${VALIDATION}') as f:
    for line in f:
        if not line.strip(): continue
        s = json.loads(line)
        text = s.get('output', s.get('text', ''))
        if text:
            texts.append(text[:500])
        if len(texts) >= 100:
            break
with open('${GOLDEN_DIR}/_validation.txt', 'w') as f:
    f.write('\n'.join(texts))
print(f'Wrote {len(texts)} samples to validation file')
"

echo "  Running llama-perplexity on Q5_K_M (should take ~5 min)..."
timeout 900 "$PERPLEXITY" \
    -m "$V2_GGUF_Q5" \
    -f "${GOLDEN_DIR}/_validation.txt" \
    --ctx-size 512 \
    -ngl 99 \
    --threads 8 2>&1 | tee /tmp/golden_perplexity.log | tail -20

# Extract perplexity value
PPL=$(grep -i "perplexity" /tmp/golden_perplexity.log | grep "=" | tail -1 | sed 's/.*= *//' | awk '{print $1}')
echo ""
echo "  Perplexity: ${PPL:-UNKNOWN}"

# Also run on current base for comparison
echo ""
echo "  Running perplexity on current base for comparison..."
timeout 900 "$PERPLEXITY" \
    -m "${PROJECT}/models/deploy/current_base.gguf" \
    -f "${GOLDEN_DIR}/_validation.txt" \
    --ctx-size 512 \
    -ngl 99 \
    --threads 8 2>&1 | tee /tmp/golden_base_perplexity.log | tail -20

BASE_PPL=$(grep -i "perplexity" /tmp/golden_base_perplexity.log | grep "=" | tail -1 | sed 's/.*= *//' | awk '{print $1}')
echo ""
echo "  Current base perplexity: ${BASE_PPL:-UNKNOWN}"
echo "  v2-think perplexity:     ${PPL:-UNKNOWN}"

###############################################################################
# STEP 6: Summary and next steps
###############################################################################
echo ""
echo "============================================================"
echo "  Golden Chain Bootstrap — COMPLETE"
echo "============================================================"
echo "  bf16 v1-hive-hf:  ${V1_HF}"
echo "  bf16 v2-think-hf: ${V2_HF}"
echo "  Q5_K_M GGUF:      ${V2_GGUF_Q5}"
echo "  Base perplexity:   ${BASE_PPL:-UNKNOWN}"
echo "  v2-think ppl:      ${PPL:-UNKNOWN}"
echo ""
echo "  To promote (if perplexity is good):"
echo "    cp ${V2_GGUF_Q5} ${PROJECT}/models/deploy/current_base.gguf"
echo ""
echo "  To run consolidation:"
echo "    python scripts/consolidation_train.py \\"
echo "      --base-model-hf ${V2_HF} \\"
echo "      --replay-data replay/sampled.jsonl \\"
echo "      --output-dir loras/v2-think-consolidation"
echo ""
echo "  To clean up old v1-hive-hf (after next merge):"
echo "    rm -rf ${V1_HF}"
echo ""
echo "  Golden chain is now established."
echo "  Future merges: train LoRA → PEFT merge into v2-think-hf → quantize → eval"
echo "============================================================"
echo "GOLDEN_CHAIN_COMPLETE"
