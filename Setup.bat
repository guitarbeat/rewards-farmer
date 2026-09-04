@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo Rewards Farmer setup
echo ====================
echo.

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

echo Using:
py -%PY% --version

py -%PY% -m pip install --upgrade pip poetry >nul
if errorlevel 1 (
  echo [ERROR] Could not install Poetry.
  pause
  exit /b 1
)

echo.
echo Creating local .venv in this folder...
py -%PY% -m poetry env remove --all >nul 2>&1
py -%PY% -m poetry install --no-interaction
if errorlevel 1 (
  echo [ERROR] poetry install failed.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Expected .venv\Scripts\python.exe was not created.
  pause
  exit /b 1
)

if not exist "assets\rewards-farmer.ico" (
  echo Generating launcher icon...
  ".venv\Scripts\python.exe" "assets\generate_icon.py"
)

echo.
echo Verifying imports...
set "OPENBLAS_NUM_THREADS=1"
set "OMP_NUM_THREADS=1"
".venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, 'src'); import customtkinter; import site_registry; site_registry.resolve('ms_rewards'); print('launcher imports ok')"
if errorlevel 1 (
  echo [ERROR] Import check failed.
  pause
  exit /b 1
)

if not exist "visual_search.jpg" (
  echo.
  echo Downloading visual search image...
  ".venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, 'src'); import random_image_for_visual_search; random_image_for_visual_search.get_random_image()" >nul 2>&1
  if exist "visual_search.jpg" (
    echo visual_search.jpg ready.
  ) else (
    echo [WARN] Could not download visual_search.jpg. The launcher can retry before each run.
  )
)

echo.
echo Installing desktop shortcut...
".venv\Scripts\python.exe" "src\install_shortcut.py"

echo.
echo Setup complete.
echo Local Python: .venv\Scripts\python.exe
echo Launch with:  Launch.bat
echo.
pause
