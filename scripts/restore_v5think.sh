#!/bin/bash
# Restore canonical v5-think server
PARENT_GGUF="/opt/hiveai/project/models/deploy/current_base.gguf"
SERVER="/opt/hiveai/llama-cpp-build/build/bin/llama-server"
LOG="/tmp/v5think_server.log"

pkill -f "llama-server.*11435" 2>/dev/null
sleep 2

nohup "$SERVER" -m "$PARENT_GGUF" \
  --host 0.0.0.0 --port 11435 \
  --flash-attn auto --ctx-size 4096 -t 12 \
  > "$LOG" 2>&1 &

echo "PID: $!"

for i in $(seq 1 60); do
  sleep 2
  resp=$(curl -s http://localhost:11435/health 2>/dev/null)
  if echo "$resp" | grep -q ok; then
    echo "v5-think HEALTHY after $((i*2))s"
    exit 0
  fi
done

echo "FAILED"
tail -20 "$LOG"
exit 1
