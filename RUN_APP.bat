@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Python environment was not found.
  echo Run these commands first:
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" launcher.py
if errorlevel 1 (
  echo.
  echo ShareNet stopped with an error. Keep this window open and report the message above.
  pause
)
