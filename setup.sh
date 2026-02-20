#!/bin/bash
set -e

echo "======================================"
echo "  HiveAI Knowledge Refinery — Setup"
echo "======================================"
echo ""

# Check Python version
python3 --version 2>/dev/null || { echo "ERROR: Python 3 is required. Install from https://python.org"; exit 1; }

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python version: $PYTHON_VERSION"

# Check PostgreSQL
if command -v psql &>/dev/null; then
    echo "PostgreSQL: $(psql --version)"
else
    echo "WARNING: PostgreSQL not found. You need a PostgreSQL database."
    echo "  Options: Local install, Neon (neon.tech), Supabase, Railway"
fi

echo ""

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Install Playwright for crawl4ai
echo ""
echo "Installing Playwright browser (for web crawling)..."
python3 -m playwright install chromium 2>/dev/null || echo "Playwright install skipped (crawl4ai will use fallback)"

# Check for .env file
if [ ! -f .env ]; then
    echo ""
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo ""
    echo "IMPORTANT: Edit .env with your settings:"
    echo "  1. Set DATABASE_URL:"
    echo "     - PostgreSQL: postgresql://user:pass@localhost:5432/hiveai"
    echo "     - SQLite (no install needed): sqlite:///hiveai.db"
    echo "  2. Set AI_INTEGRATIONS_OPENROUTER_API_KEY (or install Ollama for local LLM)"
    echo ""
    echo "  nano .env"
else
    echo ""
    echo ".env file already exists — keeping your existing config."
fi

# Download embedding model
echo ""
echo "Pre-downloading embedding model (BAAI/bge-m3)..."
python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')" 2>/dev/null || echo "Model download skipped (will download on first use)"

echo ""
echo "======================================"
echo "  Setup Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your database and API settings"
echo "  2. Run the app: python -m hiveai.app"
echo "  3. Open http://localhost:5000 in your browser"
echo ""
echo "For local LLM (no API key needed):"
echo "  1. Install Ollama: https://ollama.com"
echo "  2. Pull models: ollama pull qwen3:14b && ollama pull qwen3:8b"
echo "  3. HiveAI auto-detects Ollama — no config change needed"
echo ""
