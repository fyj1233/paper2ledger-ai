@echo off
chcp 65001 > nul
cd /d %~dp0
echo ============================================
echo   Paper2Ledger - Install (Windows)
echo ============================================

echo [1/5] Finding Python 3.11+ ...
set "PYEXE="
for /f "delims=" %%i in ('where python 2^>nul') do (
  if not defined PYEXE (
    "%%i" -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1 && set "PYEXE=%%i"
  )
)
if not defined PYEXE (
    echo [ERROR] Python 3.11+ not found in PATH.
    echo Install Python 3.11+ and make sure it is added to PATH.
    pause & exit /b 1
)
echo Using Python: %PYEXE%
"%PYEXE%" --version

echo [2/5] Checking Node.js ...
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install Node.js 18+ first.
    pause & exit /b 1
)
node --version

echo [3/5] Installing backend dependencies ...
cd /d %~dp0backend
"%PYEXE%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Backend dependencies install failed. Check network and retry.
    pause & exit /b 1
)

echo [4/5] Installing frontend dependencies ...
cd /d %~dp0frontend
if not exist node_modules (
    call npm install
    if errorlevel 1 (
        echo [TIP] If npm install failed, try: npm install --ignore-scripts
        pause & exit /b 1
    )
) else (
    echo node_modules exists, skip
)

echo [5/5] Building frontend ...
node node_modules\vite\bin\vite.js build
if errorlevel 1 (
    echo [ERROR] Frontend build failed.
    pause & exit /b 1
)

if not exist "%~dp0backend\.env" (
    copy "%~dp0.env.example" "%~dp0backend\.env" >nul
    echo Created backend\.env from template
)
python "%~dp0backend\setup_env.py"

echo.
echo ============================================
echo   Install done. Run start.bat to start.
echo ============================================
pause
