@echo off
REM Launch Flask in chat/RAG mode (ctx-size 8192)
REM Requires: llama-server already running on port 11435 with ctx-size 8192
REM   (start it first: wsl -d Ubuntu-24.04 -- bash scripts/start_chat_rag.sh)

set LLM_BACKEND=ollama
set OLLAMA_BASE_URL=http://localhost:11435
set LLM_CTX_SIZE=8192
set RUNTIME_MODE=chat_rag

echo === HiveAI Flask: chat_rag mode (ctx=8192, backend=localhost:11435) ===
cd /d c:\Users\theyc\HiveAi\Hive-AI
python -m hiveai.app
