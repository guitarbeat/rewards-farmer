@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PY=3.12"
set "PY_PYTHON=%PY%"
set "OPENBLAS_NUM_THREADS=1"
set "OMP_NUM_THREADS=1"
set "PYTHON=%~dp0.venv\Scripts\python.exe"

if exist "%PYTHON%" (
  "%PYTHON%" "%~dp0src\launch.py"
) else (
  where py >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Missing .venv and Python launcher.
    echo Run Setup.bat first.
    pause
    exit /b 1
  )
  py -%PY% "%~dp0src\launch.py"
)
if errorlevel 1 (
  pause
  exit /b 1
)
