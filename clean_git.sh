#!/bin/bash
# Clean Git History Script
# Creates a fresh git history with only current HiveAI files
# Run this from the Shell tab in Replit

set -e

echo "=== Creating clean Git history for HiveAI ==="
echo ""

# Save the remote URL
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")

# Remove old .github and .gitattributes (ArcHive leftovers)
rm -rf .github .gitattributes 2>/dev/null || true

# Remove old git history
rm -rf .git

# Initialize fresh repo
git init
git branch -M main

# Add all current files
git add -A

# Commit
git commit -m "Initial release: HiveAI Knowledge Refinery v1.0.0

AI-powered research system with:
- Automated URL discovery and web crawling
- LLM-powered knowledge extraction (triple extraction)
- Knowledge graph with community detection
- Golden Book prose generation
- Hive blockchain publishing
- AI chat with multi-hop semantic RAG
- Dual database support (PostgreSQL + SQLite)
- Local-first deployment (Ollama + SQLite)
- Windows quick start (setup.bat + run.bat)"

# Re-add remote
if [ -n "$REMOTE_URL" ]; then
    git remote add origin "$REMOTE_URL"
    echo ""
    echo "Remote set to: $REMOTE_URL"
fi

echo ""
echo "=== Done! Clean git history created ==="
echo ""
echo "Now push with:"
echo "  git push origin main --force"
echo ""
echo "This will replace the old bloated history with a clean single commit."
