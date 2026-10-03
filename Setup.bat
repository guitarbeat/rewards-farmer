@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PY=3.12"
set "PY_PYTHON=%PY%"

where py >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python launcher ^(py^) not found.
  echo Install Python %PY% from https://www.python.org/downloads/
  pause
  exit /b 1
)

py -%PY% --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python %PY% is not installed.
  echo Install it from https://www.python.org/downloads/
  pause
  exit /b 1
)

py -%PY% "%~dp0src\setup_env.py"
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  pause
  exit /b %ERR%
)
pause
