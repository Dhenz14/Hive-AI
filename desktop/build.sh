#!/bin/bash
set -e

echo "======================================"
echo "  HiveAI Desktop — Build"
echo "======================================"
echo ""

# Check prerequisites
command -v python3 >/dev/null 2>&1 || { echo "ERROR: Python 3 required"; exit 1; }
command -v pip >/dev/null 2>&1 || { echo "ERROR: pip required"; exit 1; }

# Install PyInstaller if not present
pip install pyinstaller 2>/dev/null

echo "Building standalone executable..."
echo ""

# Run PyInstaller from the desktop directory
cd "$(dirname "$0")"
pyinstaller --clean --noconfirm hiveai.spec

echo ""
echo "======================================"
echo "  Build Complete!"
echo "======================================"
echo ""
echo "Output: desktop/dist/hiveai/"
echo ""
echo "To run:"
echo "  cd dist/hiveai"
echo "  ./hiveai"
echo ""
echo "Note: You still need:"
echo "  - PostgreSQL database (set DATABASE_URL in .env)"
echo "  - Ollama (optional, for local LLM) or OpenRouter API key"
echo "  - The embedding model will download on first run (~1.5 GB)"
echo ""
