@echo off
echo.
echo ============================================================
echo   BLOCKED: HiveAI runs entirely in WSL, not Windows.
echo   Windows is for code editing and backups only.
echo.
echo   To start HiveAI:
echo     wsl -d Ubuntu-24.04 -- bash /opt/hiveai/project/scripts/start_chat_rag.sh
echo.
echo   This launches llama-server + Flask in WSL.
echo   One database. One environment. Zero data loss risk.
echo ============================================================
echo.
pause
