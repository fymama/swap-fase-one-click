@echo off
setlocal
cd /d "%~dp0"
echo Starting Swap-Fase. First-run setup may take several minutes.
if exist ".venv\swapfase-install.complete" if exist ".venv\Scripts\python.exe" goto launch
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -NoModels
    if errorlevel 1 (
        echo.
        echo Setup failed. Check the message above, then double-click this file to retry.
        pause
        exit /b 1
    )
:launch
if not exist ".venv\Scripts\python.exe" (
    echo Project-local Python environment was not created.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\pythonw.exe" (
    echo pythonw.exe was not found in the project environment.
    pause
    exit /b 1
)
".venv\Scripts\pythonw.exe" "run.py"
if errorlevel 1 (
    echo.
    echo The app could not start without a console. Opening a diagnostic console...
    ".venv\Scripts\python.exe" "run.py"
    if errorlevel 1 pause
)
