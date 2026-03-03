#!/bin/bash
# ============================================================================
# download_model.sh — Reliable Qwen3.5-9B download for WSL2
#
# The HuggingFace XET storage backend is broken (known issue: xet-core #483,
# #409, #446). This script disables XET and uses the official huggingface-cli
# with standard HTTPS fallback. If that fails, it falls back to aria2c with
# multi-connection parallel downloads.
#
# Usage:
#   # In WSL2:
#   source /opt/hiveai-env/bin/activate
#   bash scripts/download_model.sh
#
#   # From Windows (runs in tmux for persistence):
#   wsl -d Ubuntu-24.04 -- bash -c "source /opt/hiveai-env/bin/activate && \
#     cd /opt/hiveai/project && bash scripts/download_model.sh"
# ============================================================================
set -euo pipefail

REPO="Qwen/Qwen3.5-9B"
LOCAL_DIR="/opt/hiveai/project/models/qwen3.5-9b"
EXPECTED_SHARDS=4
EXPECTED_MIN_SIZE_GB=15

# Actual shard filenames (from model.safetensors.index.json)
SHARDS=(
    "model.safetensors-00001-of-00004.safetensors"
    "model.safetensors-00002-of-00004.safetensors"
    "model.safetensors-00003-of-00004.safetensors"
    "model.safetensors-00004-of-00004.safetensors"
)

echo "============================================================"
echo "  Qwen3.5-9B Download Script"
echo "============================================================"
echo "  Target: ${LOCAL_DIR}"
echo "  Time:   $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
echo ""

mkdir -p "$LOCAL_DIR"

# --- Step 1: Disable XET (the broken HuggingFace storage backend) ---
echo "[1/4] Disabling HuggingFace XET storage backend..."

if pip show hf_xet &>/dev/null 2>&1; then
    pip uninstall hf_xet -y
    echo "  Uninstalled hf_xet package"
else
    echo "  hf_xet not installed (good)"
fi

export HF_HUB_DISABLE_XET=1
export HF_HUB_DOWNLOAD_TIMEOUT=120

echo "  HF_HUB_DISABLE_XET=1 (XET disabled)"
echo ""

# --- Step 2: Verify HF authentication ---
echo "[2/4] Checking HuggingFace authentication..."

HF_TOKEN="${HF_TOKEN:-}"
if [ -z "$HF_TOKEN" ] && [ -f ~/.cache/huggingface/token ]; then
    HF_TOKEN=$(cat ~/.cache/huggingface/token)
fi

if [ -n "$HF_TOKEN" ]; then
    echo "  HF token found"
else
    echo "  WARNING: No HF token found. May fail if model is gated."
    echo "  Run: huggingface-cli login"
fi
echo ""

# --- Step 3: Try official huggingface-cli first ---
echo "[3/4] Downloading ${REPO}..."

# Find the HF CLI (could be 'huggingface-cli' or 'hf')
HF_CLI=""
if command -v huggingface-cli &>/dev/null; then
    HF_CLI="huggingface-cli"
elif command -v hf &>/dev/null; then
    HF_CLI="hf"
fi

HF_SUCCESS=false
if [ -n "$HF_CLI" ]; then
    echo "  Using official HF CLI: $HF_CLI"
    echo "  XET is disabled — downloading via standard HTTPS."
    echo "  Partial downloads resume automatically."
    echo ""

    if $HF_CLI download "$REPO" \
        --local-dir "$LOCAL_DIR" \
        --local-dir-use-symlinks False \
        --resume-download 2>&1; then
        HF_SUCCESS=true
        echo ""
        echo "  HF CLI download completed successfully."
    else
        echo ""
        echo "  HF CLI download failed. Falling back to aria2c..."
    fi
else
    echo "  HF CLI not found. Using aria2c directly."
fi

# --- Fallback: aria2c ---
if [ "$HF_SUCCESS" = false ]; then
    echo ""
    echo "  Downloading with aria2c (multi-connection, auto-resume)..."

    if ! command -v aria2c &>/dev/null; then
        echo "  Installing aria2..."
        sudo apt-get update -qq && sudo apt-get install -y -qq aria2
    fi

    BASE_URL="https://huggingface.co/${REPO}/resolve/main"

    # Build URL list for aria2c
    URL_FILE=$(mktemp)

    # Small metadata files
    for f in config.json tokenizer.json tokenizer_config.json \
             model.safetensors.index.json merges.txt vocab.json \
             chat_template.jinja preprocessor_config.json \
             video_preprocessor_config.json; do
        echo "${BASE_URL}/${f}" >> "$URL_FILE"
        if [ -n "$HF_TOKEN" ]; then
            echo "  header=Authorization: Bearer ${HF_TOKEN}" >> "$URL_FILE"
        fi
        echo "  out=${f}" >> "$URL_FILE"
        echo "  dir=${LOCAL_DIR}" >> "$URL_FILE"
    done

    # Model shard files (the big ones)
    for shard in "${SHARDS[@]}"; do
        echo "${BASE_URL}/${shard}" >> "$URL_FILE"
        if [ -n "$HF_TOKEN" ]; then
            echo "  header=Authorization: Bearer ${HF_TOKEN}" >> "$URL_FILE"
        fi
        echo "  out=${shard}" >> "$URL_FILE"
        echo "  dir=${LOCAL_DIR}" >> "$URL_FILE"
    done

    echo "  URL file generated with ${#SHARDS[@]} shards + metadata files"
    echo ""

    # aria2c flags:
    #   -c              : resume incomplete downloads
    #   -x 4            : 4 connections per file
    #   -j 2            : 2 concurrent file downloads
    #   -s 4            : split each file into 4 segments
    #   --retry-wait=10 : wait 10s between retries
    #   --max-tries=0   : retry indefinitely
    #   --timeout=120   : 120s timeout per request
    #   --file-allocation=falloc : fast pre-allocation on ext4
    aria2c \
        --continue=true \
        --max-connection-per-server=4 \
        --max-concurrent-downloads=2 \
        --split=4 \
        --retry-wait=10 \
        --max-tries=0 \
        --timeout=120 \
        --connect-timeout=30 \
        --file-allocation=falloc \
        --auto-file-renaming=false \
        --allow-overwrite=true \
        --console-log-level=notice \
        --summary-interval=30 \
        --check-certificate=true \
        -i "$URL_FILE"

    rm -f "$URL_FILE"
fi

# --- Step 4: Verify download ---
echo ""
echo "[4/4] Verifying download..."
echo ""

TOTAL_SIZE=0
SHARD_COUNT=0

for shard in "${SHARDS[@]}"; do
    f="${LOCAL_DIR}/${shard}"
    if [ -f "$f" ]; then
        SIZE=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null || echo 0)
        TOTAL_SIZE=$((TOTAL_SIZE + SIZE))
        SHARD_COUNT=$((SHARD_COUNT + 1))
        echo "  ${shard}: $(numfmt --to=iec-i --suffix=B "$SIZE" 2>/dev/null || echo "${SIZE} bytes")"
    else
        echo "  ${shard}: MISSING"
    fi
done

echo ""
echo "  Shards: ${SHARD_COUNT}/${EXPECTED_SHARDS}"

TOTAL_GB=$(echo "scale=1; $TOTAL_SIZE / 1073741824" | bc 2>/dev/null || echo "?")
echo "  Total:  ${TOTAL_GB} GB"

if [ "$SHARD_COUNT" -eq "$EXPECTED_SHARDS" ] && [ "$TOTAL_SIZE" -gt $((EXPECTED_MIN_SIZE_GB * 1073741824)) ]; then
    echo ""
    echo "============================================================"
    echo "  DOWNLOAD COMPLETE - ${TOTAL_GB} GB verified"
    echo "============================================================"

    # Check for required config files
    for f in config.json tokenizer.json model.safetensors.index.json; do
        if [ ! -f "$LOCAL_DIR/$f" ]; then
            echo "  WARNING: Missing ${f}"
        fi
    done
else
    echo ""
    echo "============================================================"
    echo "  DOWNLOAD INCOMPLETE"
    echo "  Re-run this script to resume."
    echo "============================================================"
    exit 1
fi
