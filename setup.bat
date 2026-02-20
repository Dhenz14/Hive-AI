@echo off
echo ======================================
echo   HiveAI Knowledge Refinery - Setup
echo ======================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Download from: https://www.python.org/downloads/
    echo IMPORTANT: Check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PYVER=%%i
echo Python version: %PYVER%

REM Check Ollama
ollama --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo NOTE: Ollama not found. For local AI without API keys, install from:
    echo   https://ollama.com/download/windows
    echo.
    echo After installing, run:
    echo   ollama pull qwen3:14b
    echo   ollama pull qwen3:8b
) else (
    echo Ollama: installed
)

echo.

REM Install Python dependencies
echo Installing Python dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install dependencies. Try running as Administrator.
    pause
    exit /b 1
)

REM Install Playwright for crawl4ai
echo.
echo Installing Playwright browser (for web crawling)...
python -m playwright install chromium 2>nul
if errorlevel 1 (
    echo Playwright install skipped (crawl4ai will use fallback)
)

REM Create .env if missing
if not exist .env (
    echo.
    echo Creating .env from .env.example...
    copy .env.example .env >nul

    REM Default to SQLite + Ollama for local use
    echo.
    echo Configuring for local operation (SQLite + Ollama)...
    powershell -Command "(Get-Content .env) -replace '^DATABASE_URL=.*', 'DATABASE_URL=sqlite:///hiveai.db' | Set-Content .env"
    powershell -Command "(Get-Content .env) -replace '^AI_INTEGRATIONS_OPENROUTER_API_KEY=.*', '# AI_INTEGRATIONS_OPENROUTER_API_KEY=sk-or-v1-your-key-here' | Set-Content .env"
    powershell -Command "(Get-Content .env) -replace '^AI_INTEGRATIONS_OPENROUTER_BASE_URL=.*', '# AI_INTEGRATIONS_OPENROUTER_BASE_URL=https://openrouter.ai/api/v1' | Set-Content .env"

    echo.
    echo .env created with LOCAL defaults:
    echo   Database: SQLite (hiveai.db - no server needed)
    echo   LLM: Ollama (auto-detected when running)
) else (
    echo.
    echo .env file already exists - keeping your existing config.
)

REM Pre-download embedding model
echo.
echo Pre-downloading embedding model (BAAI/bge-m3)...
echo This may take a few minutes on first run...
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')" 2>nul
if errorlevel 1 (
    echo Model download skipped (will download on first use)
)

echo.
echo ======================================
echo   Setup Complete!
echo ======================================
echo.
echo Next steps:
echo   1. Make sure Ollama is running (it starts automatically on Windows)
echo   2. Pull AI models: ollama pull qwen3:14b ^&^& ollama pull qwen3:8b
echo   3. Run the app: run.bat
echo   4. Open http://localhost:5000 in your browser
echo.
echo No API keys needed - everything runs locally on your PC!
echo.
pause
