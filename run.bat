@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo Starting Movie Music Matcher...
python desktop_app.py
 