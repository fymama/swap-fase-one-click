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
".venv\Scripts\python.exe" "run.py"
if errorlevel 1 (
    echo.
    echo Swap-Fase stopped with an error. Check the message above.
    pause
)
