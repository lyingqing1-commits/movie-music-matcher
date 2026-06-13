@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   Movie Music Matcher v3.0
echo ============================================================
echo.
echo   正在启动...
echo.
start http://localhost:5000
python app.py
pause
