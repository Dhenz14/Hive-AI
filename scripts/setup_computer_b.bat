@echo off
title Spirit Bomb - Computer B Setup (GPU Worker)
color 0A
echo.
echo  ============================================
echo   SPIRIT BOMB - Computer B Setup
echo   Join the GPU cluster as a worker node
echo  ============================================
echo.

:: ── Step 1: Check GPU ──────────────────────────────────
echo [1/5] Checking GPU...
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>nul
if ERRORLEVEL 1 (
    echo  ERROR: No NVIDIA GPU detected. GPU required for clustering.
    pause
    exit /b 1
)
echo  GPU detected!
echo.

:: ── Step 2: Check Docker ───────────────────────────────
echo [2/5] Checking Docker...
docker --version >nul 2>&1
if ERRORLEVEL 1 (
    echo  ERROR: Docker not installed.
    echo  Download from: https://www.docker.com/products/docker-desktop/
    echo  Install, restart, then run this script again.
    pause
    exit /b 1
)

:: Start Docker if not running
docker info >nul 2>&1 || (
    echo  Starting Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    :WAIT_DOCKER
    timeout /t 5 /nobreak >nul
    docker info >nul 2>&1 || goto WAIT_DOCKER
)
echo  Docker is running!
echo.

:: ── Step 3: Test GPU in Docker ─────────────────────────
echo [3/5] Testing GPU access in Docker...
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi >nul 2>&1
if ERRORLEVEL 1 (
    echo  ERROR: Docker cannot access GPU.
    echo  Make sure NVIDIA Container Toolkit is installed.
    echo  Try: Restart Docker Desktop, or restart your computer.
    pause
    exit /b 1
)
echo  GPU works in Docker!
echo.

:: ── Step 4: Open Firewall ──────────────────────────────
echo [4/5] Opening firewall ports...
netsh advfirewall firewall add rule name="Allow Ping" protocol=icmpv4 dir=in action=allow >nul 2>&1
netsh advfirewall firewall add rule name="SpiritBomb Worker" protocol=tcp dir=in localport=8100 action=allow >nul 2>&1
netsh advfirewall firewall add rule name="SpiritBomb Ray" protocol=tcp dir=in localport=6379,8265 action=allow >nul 2>&1
echo  Firewall rules added!
echo.

:: ── Step 5: Get Computer A address ─────────────────────
echo [5/5] Configuration
echo.
set /p COMPUTER_A_IP="  Enter Computer A's IP address (e.g. 192.168.0.101): "
if "%COMPUTER_A_IP%"=="" set COMPUTER_A_IP=192.168.0.101

:: Test connectivity
echo.
echo  Testing connection to Computer A (%COMPUTER_A_IP%)...
ping -n 2 -w 2000 %COMPUTER_A_IP% >nul 2>&1
if ERRORLEVEL 1 (
    echo  WARNING: Cannot ping Computer A. Check that:
    echo    - Computer A is on and running Spirit Bomb
    echo    - Both computers are on the same network
    echo    - Computer A's firewall allows ping
    echo.
    set /p CONTINUE="  Continue anyway? (y/n): "
    if /i not "%CONTINUE%"=="y" exit /b 1
) else (
    echo  Connection OK!
)

:: ── Start Worker ───────────────────────────────────────
echo.
echo  ============================================
echo   Starting GPU Worker
echo   Connecting to Computer A at %COMPUTER_A_IP%:5000
echo  ============================================
echo.

:: Kill Ollama to free GPU
taskkill /F /IM ollama.exe >nul 2>&1
taskkill /F /IM "ollama app.exe" >nul 2>&1
timeout /t 3 /nobreak >nul

:: Pull vLLM if needed
docker images vllm/vllm-openai:latest -q 2>nul | findstr /r "." >nul 2>&1
if ERRORLEVEL 1 (
    echo  Downloading vLLM image (30GB, first time only)...
    docker pull vllm/vllm-openai:latest
)

:: Start vLLM worker
docker rm -f spiritbomb-worker >nul 2>&1
echo  Starting vLLM worker node...
docker run -d --name spiritbomb-worker --gpus all -p 8100:8000 -v hf_cache:/root/.cache/huggingface --ipc=host vllm/vllm-openai:latest --model Qwen/Qwen3-14B-AWQ --quantization awq_marlin --gpu-memory-utilization 0.70 --max-model-len 1024 --enforce-eager --host 0.0.0.0 --port 8000

:: Wait for model to load
echo  Loading model (first time takes longer)...
:WAIT_VLLM
timeout /t 10 /nobreak >nul
curl -s http://localhost:8100/health >nul 2>&1 && goto VLLM_READY
goto WAIT_VLLM
:VLLM_READY

:: Register with Computer A
echo.
echo  Registering with Computer A...
python scripts/start_spiritbomb.py --hivepoa-url http://%COMPUTER_A_IP%:5000 --worker-only

echo.
echo  ============================================
echo   Computer B is LIVE and connected!
echo.
echo   vLLM API:    http://localhost:8100/v1/completions
echo   Connected:   http://%COMPUTER_A_IP%:5000
echo.
echo   Close this window to disconnect.
echo  ============================================
echo.
pause
