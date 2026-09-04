@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PY=3.12"
set "PY_PYTHON=%PY%"
set "OPENBLAS_NUM_THREADS=1"
set "OMP_NUM_THREADS=1"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "PYTHONW=%~dp0.venv\Scripts\pythonw.exe"
set "LOGDIR=%~dp0logs"

if not exist "%PYTHON%" (
  echo First run: setting up Python environment...
  call "%~dp0Setup.bat"
  if errorlevel 1 exit /b 1
)

if not exist "%PYTHON%" (
  echo [ERROR] Missing .venv\Scripts\python.exe
  echo Run Setup.bat first.
  pause
  exit /b 1
)

"%PYTHON%" -c "import customtkinter" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] customtkinter is missing from .venv
  echo Run Setup.bat to install dependencies.
  pause
  exit /b 1
)

if not exist "%~dp0assets\rewards-farmer.ico" (
  "%PYTHON%" "%~dp0assets\generate_icon.py" >nul 2>&1
)

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

rem Prefer pythonw for a clean desktop launch; uncaught errors still write
rem logs\launcher_crash.log via launcher.py. Fall back to python.exe if needed.
if exist "%PYTHONW%" (
  start "" "%PYTHONW%" "%~dp0src\launcher.py"
) else (
  start "" "%PYTHON%" "%~dp0src\launcher.py"
)
