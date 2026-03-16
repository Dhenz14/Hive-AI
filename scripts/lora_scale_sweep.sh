#!/usr/bin/env bash
# LoRA Scale Sweep — test adapter at multiple scaling factors
# Usage: bash scripts/lora_scale_sweep.sh
set -uo pipefail
# Don't set -e: regression_eval.py returns non-zero on "regressions" vs stale ledger

BASE_GGUF="/opt/hiveai/project/models/deploy/current_base.gguf"
ADAPTER_GGUF="/opt/hiveai/project/loras/domains/ts-generics/adapter.gguf"
SERVER_BIN="/opt/hiveai/llama-cpp-build/build/bin/llama-server"
PORT=11435
SCALES="0.20 0.35 0.50 0.70 1.00"
RESULTS_DIR="/opt/hiveai/project/loras/domains/ts-generics/scale_sweep"
EVAL_SCRIPT="/opt/hiveai/project/scripts/regression_eval.py"

mkdir -p "$RESULTS_DIR"

echo "============================================================"
echo "  LoRA Scale Sweep — ts-generics adapter"
echo "  Scales: $SCALES"
echo "  Base: $BASE_GGUF"
echo "  Adapter: $ADAPTER_GGUF"
echo "============================================================"

# Baseline already captured — skip to scale sweep
# Run each scale
for SCALE in $SCALES; do
  echo ""
  echo ">>> SCALE = $SCALE <<<"
  pkill -f llama-server 2>/dev/null || true
  sleep 2

  $SERVER_BIN \
    -m "$BASE_GGUF" \
    --lora-scaled "${ADAPTER_GGUF}:${SCALE}" \
    --port $PORT -ngl 99 --ctx-size 4096 --flash-attn on -t 12 \
    > "$RESULTS_DIR/server_scale_${SCALE}.log" 2>&1 &
  SERVER_PID=$!

  echo "  Waiting for server (PID $SERVER_PID)..."
  for i in $(seq 1 60); do
    if curl -s http://localhost:$PORT/health | grep -q '"status":"ok"'; then
      echo "  Server ready after ${i}s"
      break
    fi
    sleep 1
    if [ $i -eq 60 ]; then
      echo "  ERROR: Server failed to start at scale $SCALE"
      kill $SERVER_PID 2>/dev/null
      continue 2
    fi
  done

  python3 "$EVAL_SCRIPT" \
    --model-version "ts-generics-scale-${SCALE}" \
    --server-url "http://localhost:$PORT" \
    --quick \
    2>&1 | tee "$RESULTS_DIR/eval_scale_${SCALE}.txt"

  kill $SERVER_PID 2>/dev/null || true
  sleep 2
done

echo ""
echo "============================================================"
echo "  SWEEP COMPLETE — Results in $RESULTS_DIR/"
echo "============================================================"

# Summary table
echo ""
echo "SUMMARY:"
echo "Scale     | cpp    | go     | hive   | js     | python | rust   | OVERALL"
echo "----------|--------|--------|--------|--------|--------|--------|--------"
for f in "$RESULTS_DIR"/eval_*.txt; do
  label=$(basename "$f" .txt | sed 's/eval_//')
  # Extract the score lines
  scores=$(grep -E '^\s+(cpp|go|hive|js|python|rust|OVERALL)' "$f" 2>/dev/null | \
    awk '{printf "%s ", $3}')
  printf "%-9s | %s\n" "$label" "$scores"
done
