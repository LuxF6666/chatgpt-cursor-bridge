@echo off

REM Change to current directory
cd /d "%~dp0"

echo ====================================
echo L Bridge Tool Startup Script
echo ====================================

echo Starting L Bridge Tool...
echo If this is the first launch, dependency installation may take a while.
echo If the GUI does not appear, check this window for errors.

REM Set environment variable to reduce Qt warnings
set QT_LOGGING_RULES=qt.qpa.*=false

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python not found
    echo Please install Python 3.6 or higher
    pause
    exit /b 1
)

echo Python version check passed

REM Install dependencies
echo Installing dependencies...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Error: Dependency installation failed
    echo Please check network connection or install dependencies manually
    pause
    exit /b 1
)

echo Dependency installation completed

REM Start L Tool GUI
echo Starting L Bridge Tool GUI...
python l_bridge_tool_gui.py
if %errorlevel% neq 0 (
    echo Error: L Bridge Tool exited with an error
    echo Please check error messages above
    pause
    exit /b 1
)

pause