@echo off
cd /d "%~dp0"

echo === Job Pipeline ===
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://python.org
    pause
    exit /b 1
)

REM Install/check dependencies silently
echo Checking dependencies...
python -m pip install -r requirements.txt -q

REM Check .env
if not exist ".env" (
    echo.
    echo WARNING: .env file not found.
    echo Copying .env.example to .env -- add your GEMINI_API_KEY inside.
    copy .env.example .env >nul
)

echo.
echo Starting Job Pipeline UI...
echo Opening: http://localhost:8501
echo Press Ctrl+C to stop.
echo.

streamlit run app.py --server.headless true
pause
