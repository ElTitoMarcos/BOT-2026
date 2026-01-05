@echo off
cd /d "%~dp0"

echo Starting MoneyBot...
set "PYTHON_EXE=.\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Error: Virtual environment not found at "%PYTHON_EXE%".
  echo Run: python -m venv .venv ^&^& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  pause >nul
  exit /b 1
)

rem Ensure dependencies are installed (including email-validator required by FastAPI/Pydantic).
%PYTHON_EXE% -m pip show email-validator >nul 2>&1
if errorlevel 1 (
  echo Installing required dependencies...
  %PYTHON_EXE% -m pip install -r requirements.txt
)
start "" /b "%PYTHON_EXE%" BOT.py

timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8000/ui

echo.
echo MoneyBot started. Close this window to stop the launcher.
echo If the server crashes, run: .\.venv\Scripts\python.exe BOT.py
pause >nul
