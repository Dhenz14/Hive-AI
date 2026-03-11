#!/bin/bash
# Auto-shop: restore llama.cpp tools from permanent cache
CACHE=/opt/hiveai/tools
BUILD=/opt/hiveai/llama-cpp-build
if [ -d "$BUILD" ]; then
    if [ ! -e /tmp/llama.cpp ]; then
        ln -sf "$BUILD" /tmp/llama.cpp
        echo "Symlinked /tmp/llama.cpp -> $BUILD"
    fi
else
    mkdir -p /tmp/llama.cpp/build/bin
    cp "$CACHE/convert_lora_to_gguf.py" /tmp/llama.cpp/
    cp "$CACHE/convert_hf_to_gguf.py" /tmp/llama.cpp/
    cp -r "$CACHE/gguf-py" /tmp/llama.cpp/ 2>/dev/null || true
    cp "$CACHE"/llama-* /tmp/llama.cpp/build/bin/
    echo "Tools restored from $CACHE"
fi
export PATH="/tmp/llama.cpp/build/bin:$PATH"
export LD_LIBRARY_PATH="/tmp/llama.cpp/build/bin:${LD_LIBRARY_PATH:-}"
