@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
where py >nul 2>nul
if errorlevel 1 (echo Python launcher not found. Install Python 3 and enable the py launcher. & pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if errorlevel 1 (echo Could not create Python environment. & pause & exit /b 1)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo Could not install requirements. & pause & exit /b 1)
".venv\Scripts\python.exe" localize.py install
pause