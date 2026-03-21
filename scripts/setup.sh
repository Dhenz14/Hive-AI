#!/bin/bash
# =============================================================================
# HiveAI — First-Run Setup
# =============================================================================
# Run this once before 'docker compose up'. Checks prerequisites, creates
# config, and tells you if anything is missing.
#
# Usage: bash scripts/setup.sh
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }

echo ""
echo "════════════════════════════════════════════════════════"
echo "  HiveAI Knowledge Refinery — Setup"
echo "════════════════════════════════════════════════════════"
echo ""

ERRORS=0

# ── Check Docker ────────────────────────────────────────
echo "[1/5] Docker..."
if command -v docker &>/dev/null; then
    DOCKER_VER=$(docker --version | head -1)
    ok "Docker installed: $DOCKER_VER"
else
    fail "Docker not installed. Get it at https://docker.com"
    ERRORS=$((ERRORS + 1))
fi

if command -v docker &>/dev/null && docker compose version &>/dev/null; then
    ok "Docker Compose available"
else
    fail "Docker Compose not available (need Docker Desktop or docker-compose-plugin)"
    ERRORS=$((ERRORS + 1))
fi

# ── Check NVIDIA GPU ────────────────────────────────────
echo "[2/5] GPU..."
if command -v nvidia-smi &>/dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    GPU_VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)
    ok "GPU: $GPU_NAME (${GPU_VRAM}MB VRAM)"
else
    warn "nvidia-smi not found. GPU acceleration won't work."
    warn "Install NVIDIA drivers + Container Toolkit:"
    warn "  https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/"
fi

# Check NVIDIA Container Toolkit
if docker info 2>/dev/null | grep -qi "nvidia\|cuda"; then
    ok "NVIDIA Container Toolkit detected"
elif command -v nvidia-container-cli &>/dev/null; then
    ok "NVIDIA Container CLI found"
else
    warn "NVIDIA Container Toolkit not detected in Docker"
    warn "GPU may not be available inside containers"
    warn "Install: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/"
fi

# ── Create .env ─────────────────────────────────────────
echo "[3/5] Config..."
if [ -f .env ]; then
    ok ".env exists"
else
    if [ -f .env.example ]; then
        cp .env.example .env
        ok ".env created from template"
    else
        fail ".env.example not found — are you in the HiveAI directory?"
        ERRORS=$((ERRORS + 1))
    fi
fi

# ── Check model ─────────────────────────────────────────
echo "[4/5] Model..."
mkdir -p models

if [ -f models/current_base.gguf ]; then
    MODEL_SIZE=$(du -h models/current_base.gguf | cut -f1)
    ok "Model found: models/current_base.gguf ($MODEL_SIZE)"
else
    warn "Model not found at models/current_base.gguf"
    echo ""
    echo "    Download it (pick one):"
    echo ""
    echo "    Option A — HuggingFace CLI:"
    echo "      pip install huggingface-hub"
    echo "      huggingface-cli download Dhenz14/hiveai-v5-think --local-dir ./models"
    echo ""
    echo "    Option B — Direct download:"
    echo "      Copy your GGUF file to ./models/current_base.gguf"
    echo ""
fi

# ── Summary ─────────────────────────────────────────────
echo "[5/5] Summary..."
echo ""

if [ $ERRORS -eq 0 ] && [ -f models/current_base.gguf ]; then
    echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Ready! Run: docker compose up${NC}"
    echo -e "${GREEN}  Then open: http://localhost:5001${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}  Almost ready! Just need the model file.${NC}"
    echo -e "${YELLOW}  See instructions above, then: docker compose up${NC}"
    echo -e "${YELLOW}════════════════════════════════════════════════════════${NC}"
else
    echo -e "${RED}════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}  $ERRORS issue(s) found. Fix them, then re-run:${NC}"
    echo -e "${RED}    bash scripts/setup.sh${NC}"
    echo -e "${RED}════════════════════════════════════════════════════════${NC}"
fi
echo ""
