@echo off
rem ============================================================
rem  LegalAssist Demo launcher (ASCII only - do not add CN text)
rem  Chinese text inside .bat breaks on GBK-locale Windows.
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"

echo.
echo   Starting LegalAssist demo ...
echo   URL: http://127.0.0.1:8000
echo.

"%PY%" app\server.py --port 8000 --open
pause

