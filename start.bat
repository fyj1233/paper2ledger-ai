@echo off
chcp 65001 > nul
cd /d %~dp0
echo ============================================
echo   Paper2Ledger - Start
echo ============================================

if not exist "%~dp0backend\.env" (
    copy "%~dp0.env.example" "%~dp0backend\.env" >nul
    echo Created backend\.env from template
)
python "%~dp0backend\setup_env.py"
if not exist "%~dp0frontend\dist\index.html" (
    echo [ERROR] Frontend build not found. Run install.bat first.
    pause & exit /b 1
)

rem ---- find a Python that has project dependencies installed ----
rem Walk every python on PATH and pick the first one that can import uvicorn.
set "PYEXE="
for /f "delims=" %%i in ('where python 2^>nul') do (
  if not defined PYEXE (
    "%%i" -c "import uvicorn" >nul 2>&1 && set "PYEXE=%%i"
  )
)
if not defined PYEXE (
    echo [ERROR] No Python with project dependencies found.
    echo Run install.bat first, or check your Python installation.
    pause & exit /b 1
)
echo Using Python: %PYEXE%

echo Starting backend at http://127.0.0.1:8000 ...
start "paper2ledger-backend" /D "%~dp0backend" cmd /k ""%PYEXE%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

timeout /t 4 /nobreak >nul
start http://127.0.0.1:8000

echo.
echo Browser will open http://127.0.0.1:8000
echo Close the backend window to stop the system.
pause
