@echo off
setlocal enabledelayedexpansion

echo Starting HiveAI Knowledge Refinery...
echo.

REM Load .env file if it exists (skip comments and blank lines)
if exist .env (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
        if not "%%a"=="" if not "%%b"=="" (
            set "%%a=%%b"
        )
    )
)

REM Check if .env exists at all
if not exist .env (
    echo WARNING: No .env file found. Run setup.bat first.
    echo.
    pause
    exit /b 1
)

REM Check if Ollama is running
echo Checking Ollama status...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo.
    echo NOTE: Ollama does not appear to be running.
    echo   - Make sure Ollama is installed and started
    echo   - Download from: https://ollama.com/download/windows
    echo   - It should start automatically after installation
    echo.
    echo Continuing anyway (will use OpenRouter if configured^)...
    echo.
) else (
    echo Ollama: running
)

echo.
echo Starting web server on http://localhost:5000 ...
echo Press Ctrl+C to stop.
echo.

python -m hiveai.app

if errorlevel 1 (
    echo.
    echo HiveAI stopped with an error. Check the output above for details.
    pause
)

endlocal
