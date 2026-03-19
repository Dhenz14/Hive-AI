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

# --- Step 2: Print Flask launch command ---
# Flask runs on Windows, so we print the command rather than executing it.
echo ""
echo "=== Flask launch command (run on Windows) ==="
echo "  cd c:\\Users\\theyc\\HiveAi\\Hive-AI"
echo "  set LLM_BACKEND=ollama"
echo "  set OLLAMA_BASE_URL=http://localhost:$PORT"
echo "  set LLM_CTX_SIZE=$CTX_SIZE"
echo "  set RUNTIME_MODE=chat_rag"
echo "  python -m hiveai.app"
echo ""
echo "Or from Git Bash / WSL:"
echo "  LLM_BACKEND=ollama OLLAMA_BASE_URL=http://localhost:$PORT LLM_CTX_SIZE=$CTX_SIZE RUNTIME_MODE=chat_rag python -m hiveai.app"
echo ""
echo "=== Mode: chat_rag | ctx: $CTX_SIZE | backend: localhost:$PORT ==="
