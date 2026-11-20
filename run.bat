@echo off
REM Start Heckle & Hint on this computer (Windows). Needs Python 3.10+ from python.org.
cd /d "%~dp0"
py -m pip install -q -r backend\requirements.txt
echo.
echo   Heckle ^& Hint is running:  http://localhost:8000
echo   Phones on the same Wi-Fi: use this PC's IP address (run "ipconfig") with :8000
echo   Stop with Ctrl+C
echo.
py -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
