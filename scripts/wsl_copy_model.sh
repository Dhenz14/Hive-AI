#!/bin/bash
set -e

SRC=/mnt/c/Users/theyc/HiveAi/Hive-AI/models/qwen3.5-35b-a3b-v3.5
DST=/opt/hiveai/project/models/qwen3.5-35b-a3b-v3.5
mkdir -p "$DST"

# Copy config files
echo "Copying config/tokenizer files..."
cp "$SRC"/*.json "$DST/" 2>/dev/null || true
cp "$SRC"/*.jinja "$DST/" 2>/dev/null || true
cp "$SRC"/merges.txt "$DST/" 2>/dev/null || true
echo "Config files done."

# Copy shards with progress
echo "Copying 15 safetensors shards (~39 GB)..."
echo "This will take 15-30 minutes."
for i in $(seq 1 15); do
    PADDED=$(printf '%05d' "$i")
    SHARD="model.safetensors-${PADDED}-of-00015.safetensors"
    if [ -f "$SRC/$SHARD" ]; then
        echo -n "  [$i/15] $SHARD ... "
        cp "$SRC/$SHARD" "$DST/"
        echo "done"
    else
        echo "  [$i/15] $SHARD MISSING"
    fi
done
echo "=== All shards copied ==="
ls "$DST"/*.safetensors | wc -l
echo "safetensors files total"
