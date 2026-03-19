#!/usr/bin/env bash
# Launch profile: campaign/probe mode (ctx-size 4096)
#
# Usage (from WSL):
#   bash scripts/start_campaign.sh
#
# This starts llama-server in a tmux session with ctx-size 4096,
# matching the campaign invariant (flash-attn auto, 12 threads).
# Flask is NOT started — campaign scripts drive inference directly.
set -euo pipefail

LLAMA_BIN="/opt/hiveai/llama-cpp-build/build/bin/llama-server"
MODEL="/opt/hiveai/project/models/deploy/current_base.gguf"
PORT=11435
CTX_SIZE=4096
THREADS=12
LOG="/opt/hiveai/project/logs/llama_server_campaign.log"
TMUX_SESSION="llama-campaign"

echo "=== HiveAI campaign/probe mode (ctx-size $CTX_SIZE) ==="

# --- Step 1: Start llama-server in tmux ---
if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    echo "[llama-server] tmux session '$TMUX_SESSION' already exists — killing it"
    tmux kill-session -t "$TMUX_SESSION"
    sleep 2
fi

# Also kill any chat-mode session to avoid port conflict
if tmux has-session -t "llama-chat" 2>/dev/null; then
    echo "[llama-server] Killing chat-mode session 'llama-chat' to free port $PORT"
    tmux kill-session -t "llama-chat"
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
echo ""
echo "=== Mode: campaign_probe | ctx: $CTX_SIZE | backend: localhost:$PORT ==="
echo "Campaign scripts (overnight_campaign_runner.py, campaign_dry_run.py) can now run."
