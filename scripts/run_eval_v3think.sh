#!/bin/bash
source /opt/hiveai-env/bin/activate
cd /opt/hiveai/project
source scripts/restore_llama_cpp.sh

GGUF="/opt/hiveai/project/models/deploy/v3-think/merged.gguf"
echo "Starting llama-server with $GGUF"
/opt/hiveai/llama-cpp-build/build/bin/llama-server -m "$GGUF" --port 11435 --ctx-size 8192 -ngl 99 --flash-attn on --cache-type-k q8_0 --cache-type-v q4_0 --threads 8 &
SERVER_PID=$!
echo "PID: $SERVER_PID"

echo "Waiting 120s for model load..."
sleep 120

echo "Warmup..."
curl -s http://localhost:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"test","messages":[{"role":"user","content":"hello"}],"max_tokens":10}' > /dev/null 2>&1
sleep 5

echo "Running regression eval..."
python scripts/regression_eval.py --model-version v3-think --server-url http://localhost:11435 2>&1 | tee logs/v3-think_07_regression.log
EVAL_EXIT=$?

kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null

if [ $EVAL_EXIT -eq 0 ]; then
    echo "PASSED - promoting v3-think"
    cp "$GGUF" /opt/hiveai/project/models/deploy/current_base.gguf
    echo "7" > /opt/hiveai/project/logs/v3-think_checkpoint
    echo "v3-think PROMOTED to current_base.gguf"
else
    echo "FAILED - not promoting"
fi
