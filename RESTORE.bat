@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
where py >nul 2>nul
if errorlevel 1 (echo Python launcher not found. & pause & exit /b 1)
py -3 localize.py restore
pause