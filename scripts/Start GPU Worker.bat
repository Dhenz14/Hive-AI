@echo off
title Spirit Bomb - GPU Worker
color 0A
echo.
echo  ============================================
echo   SPIRIT BOMB - GPU Worker
echo   Share your GPU, earn HBD rewards
echo  ============================================
echo.

:: Default HivePoA server (Computer A)
set HIVEPOA=http://192.168.0.101:5000
if not "%1"=="" set HIVEPOA=%1

echo  Connecting to: %HIVEPOA%
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Install Python 3.10+
    echo  https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Install dependencies
echo [1/3] Installing dependencies...
pip install aiohttp >nul 2>&1

:: Open firewall (may need admin)
echo [2/3] Opening firewall...
netsh advfirewall firewall add rule name="SpiritBomb Ping" protocol=icmpv4 dir=in action=allow >nul 2>&1
netsh advfirewall firewall add rule name="SpiritBomb Port" protocol=tcp dir=in localport=8101 action=allow >nul 2>&1

:: Start worker
echo [3/3] Starting GPU worker...
echo.
echo  ============================================
echo   GPU Worker is starting!
echo.
echo   Your GPU will be shared with the community.
echo   You earn HBD rewards for every AI request served.
echo.
echo   Close this window to stop sharing.
echo  ============================================
echo.

cd /d "%~dp0.."
python scripts/start_spiritbomb.py --hivepoa-url %HIVEPOA%
