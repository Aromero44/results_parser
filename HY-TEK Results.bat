@echo off
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo Python was not found. Install it from python.org and check "Add Python to PATH".
    pause
    exit /b 1
)

python -c "import PySide6, pdfplumber, pandas" >nul 2>&1
if errorlevel 1 (
    echo First-time setup: installing required libraries. This can take a few minutes...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Setup failed. Take a screenshot of this window and send it for help.
        pause
        exit /b 1
    )
)

start "" pythonw gui.py
