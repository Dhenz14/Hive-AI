#!/bin/bash
set -euo pipefail

DEST=/opt/hiveai/project/models/golden/original-bf16
HF_TOKEN=$(cat ~/.cache/huggingface/token)
MODEL=Qwen/Qwen2.5-Coder-14B-Instruct
BASE_URL="https://huggingface.co/${MODEL}/resolve/main"

mkdir -p "$DEST"

FILES="config.json generation_config.json model.safetensors.index.json tokenizer.json tokenizer_config.json merges.txt vocab.json model-00001-of-00006.safetensors model-00002-of-00006.safetensors model-00003-of-00006.safetensors model-00004-of-00006.safetensors model-00005-of-00006.safetensors model-00006-of-00006.safetensors"

for f in $FILES; do
    if [ -f "$DEST/$f" ]; then
        SIZE=$(du -h "$DEST/$f" | cut -f1)
        echo "SKIP (exists, ${SIZE}): $f"
        continue
    fi
    echo ""
    echo "=== Downloading: $f ==="
    aria2c -x 16 -s 16 -k 1M --continue=true \
        --header="Authorization: Bearer $HF_TOKEN" \
        --dir="$DEST" --out="$f" \
        --file-allocation=none \
        --timeout=120 --max-tries=5 --retry-wait=10 \
        --summary-interval=10 \
        "${BASE_URL}/$f"
    echo "DONE: $f"
done

echo ""
echo "All files downloaded. Verifying..."
COUNT=$(ls "$DEST"/*.safetensors 2>/dev/null | wc -l)
echo "Found $COUNT safetensor files"
du -sh "$DEST"
if [ "$COUNT" -eq 6 ]; then
    echo "DOWNLOAD_COMPLETE"
else
    echo "FATAL: Expected 6 safetensors, got $COUNT"
    exit 1
fi
