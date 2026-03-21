#!/usr/bin/env bash
# Launch profile: chat/RAG mode (ctx-size 8192)
#
# Usage (from WSL):
#   bash scripts/start_chat_rag.sh
#
# This starts llama-server in a tmux session with ctx-size 8192,
# then starts Flask with the correct backend routing.
# No .env editing required — overrides are process-local.
set -euo pipefail

LLAMA_BIN="/opt/hiveai/llama-cpp-build/build/bin/llama-server"
MODEL="/opt/hiveai/project/models/deploy/current_base.gguf"
PORT=11435
CTX_SIZE=8192
THREADS=12
LOG="/opt/hiveai/project/logs/llama_server_chat.log"
TMUX_SESSION="llama-chat"

echo "=== HiveAI chat/RAG mode (ctx-size $CTX_SIZE) ==="

# --- Step 1: Start llama-server in tmux ---
if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    echo "[llama-server] tmux session '$TMUX_SESSION' already exists — killing it"
    tmux kill-session -t "$TMUX_SESSION"
    sleep 2
fi

echo "[llama-server] Starting in tmux session '$TMUX_SESSION' (ctx-size $CTX_SIZE)..."
tmux new-session -d -s "$TMUX_SESSION" \
    "exec $LLAMA_BIN -m $MODEL --host 0.0.0.0 --port $PORT --flash-attn auto --ctx-size $CTX_SIZE -t $THREADS 2>&1 | tee $LOG"

# Wait for health
echo -n "[llama-server] Waiting for health"
for i in $(seq 1 120); do
    if curl -sf http://localhost:$PORT/health > /dev/null 2>&1; then
        echo " OK (${i}s)"
        break
    fi
    echo -n "."
    sleep 1
    if [ "$i" -eq 120 ]; then
        echo " TIMEOUT"
        echo "ERROR: llama-server did not become healthy within 120s"
        exit 1
    fi
done

echo "[llama-server] Healthy on port $PORT, ctx-size $CTX_SIZE"

# --- Step 2: Sync code from Windows git repo ---
echo "[sync] Syncing latest code from Windows git repo..."
cp -ru /mnt/c/Users/theyc/HiveAi/Hive-AI/hiveai/ /opt/hiveai/project/hiveai/ 2>/dev/null || true
cp -ru /mnt/c/Users/theyc/HiveAi/Hive-AI/scripts/*.py /opt/hiveai/project/scripts/ 2>/dev/null || true
cp -ru /mnt/c/Users/theyc/HiveAi/Hive-AI/skills/ /opt/hiveai/project/skills/ 2>/dev/null || true
find /opt/hiveai/project/hiveai -name '*.py' -exec sed -i 's/\r$//' {} + 2>/dev/null
find /opt/hiveai/project/scripts -name '*.py' -exec sed -i 's/\r$//' {} + 2>/dev/null
echo "[sync] Done"

# --- Step 3: Start Flask in tmux (IN WSL — not Windows) ---
FLASK_SESSION="flask"
if tmux has-session -t "$FLASK_SESSION" 2>/dev/null; then
    echo "[flask] tmux session '$FLASK_SESSION' already exists — killing it"
    tmux kill-session -t "$FLASK_SESSION"
    sleep 1
fi

echo "[flask] Starting in tmux session '$FLASK_SESSION'..."
tmux new-session -d -s "$FLASK_SESSION" \
    "cd /opt/hiveai/project && \
     HIVEAI_ALLOW_WINDOWS=1 \
     LLM_BACKEND=llama-server \
     OLLAMA_BASE_URL=http://localhost:$PORT \
     LLM_CTX_SIZE=$CTX_SIZE \
     RUNTIME_MODE=chat_rag \
     python3 -m flask --app hiveai.app run --host 0.0.0.0 --port 5001 2>&1 | tee /opt/hiveai/project/logs/flask_chat.log"

# Wait for Flask health
echo -n "[flask] Waiting for health"
for i in $(seq 1 30); do
    if curl -sf http://localhost:5001/ready > /dev/null 2>&1; then
        echo " OK (${i}s)"
        break
    fi
    echo -n "."
    sleep 2
    if [ "$i" -eq 30 ]; then
        echo " TIMEOUT"
        echo "WARNING: Flask did not become healthy within 60s"
    fi
done

# --- Status ---
echo ""
echo "════════════════════════════════════════════════════════"
echo "  HiveAI running ENTIRELY in WSL"
echo "  Chat:     http://localhost:5001"
echo "  LLM:      http://localhost:$PORT (ctx-size $CTX_SIZE)"
echo "  Database: /opt/hiveai/project/hiveai.db (ONE database)"
echo ""
echo "  tmux sessions: $TMUX_SESSION, $FLASK_SESSION"
echo "  Attach: tmux attach -t flask"
echo "  Windows = backup only. NEVER run Flask on Windows."
echo "════════════════════════════════════════════════════════"
