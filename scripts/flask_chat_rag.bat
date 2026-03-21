@echo off
echo.
echo ============================================================
echo   BLOCKED: Flask runs in WSL, not Windows.
echo   Windows is for backups only.
echo.
echo   Correct way to start:
echo     wsl -d Ubuntu-24.04 -- bash /opt/hiveai/project/scripts/start_chat_rag.sh
echo.
echo   This starts BOTH llama-server AND Flask in WSL.
echo   One database. One environment. Zero risk.
echo ============================================================
echo.
pause
