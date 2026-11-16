@echo off
cd /d "%~dp0"

echo === JobPilot ===
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11 or newer from https://python.org
    pause
    exit /b 1
)

REM Keep dependencies in a local environment so nothing is installed system-wide
if not exist ".venv\Scripts\python.exe" (
    echo Creating local Python environment, first run only...
    python -m venv .venv
)

echo Checking dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q

REM Check .env
if not exist ".env" (
    echo.
    echo No .env file yet. Creating one -- add your Gemini API key in the Settings tab.
    copy .env.example .env >nul
)

REM Check master CV
if not exist "master_cv.md" (
    echo No master_cv.md yet. Copying the example -- replace it with your own CV.
    copy master_cv.example.md master_cv.md >nul
)

echo.
echo Starting JobPilot...
echo Opening: http://localhost:8501
echo Press Ctrl+C to stop.
echo.

".venv\Scripts\python.exe" -m streamlit run app.py
pause
