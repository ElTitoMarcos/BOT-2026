@echo off
cd /d "%~dp0"

echo Starting MoneyBot...
start "" cmd /c ".\.venv\Scripts\python.exe BOT.py"

timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8000/ui

echo.
echo MoneyBot started. Close this window to stop the launcher.
echo If the server crashes, run: .\.venv\Scripts\python.exe BOT.py
pause >nul
