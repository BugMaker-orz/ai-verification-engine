@echo off
title AI Verification Engine - One-click Build
cd /d "%~dp0"

echo ============================================
echo    AI Verification Engine - Windows Builder
echo ============================================
echo.

REM ---- Detect a working Python launcher ----
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)
if not defined PY_CMD (
    echo ERROR: Python was not found.
    echo.
    echo Please install Python 3.9+ from:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANT: during install, check "Add Python to PATH"
    echo.
    pause
    exit /b 1
)
echo Using Python launcher: %PY_CMD%
%PY_CMD% --version
echo.

REM ---- 1. Create venv if missing ----
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating virtual environment .venv ...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo.
        echo FAILED to create venv!
        pause
        exit /b 1
    )
) else (
    echo [1/4] venv already exists, skip
)

echo [2/4] Installing dependencies ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo FAILED to install dependencies!
    pause
    exit /b 1
)

echo [3/4] Installing PyInstaller ...
".venv\Scripts\python.exe" -m pip install pyinstaller -q
if errorlevel 1 (
    echo FAILED to install PyInstaller!
    pause
    exit /b 1
)

echo [4/4] Building exe, this is slow, please wait ...
".venv\Scripts\python.exe" -m PyInstaller ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --name "AI-Verification-Engine" ^
  --collect-all gradio ^
  --collect-all gradio_client ^
  --collect-all safehttpx ^
  --collect-all groovy ^
  --collect-all huggingface_hub ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  --add-data "rules;rules" ^
  --add-data "samples;samples" ^
  --add-data "config;config" ^
  --add-data "docs;docs" ^
  app.py
if errorlevel 1 (
    echo.
    echo BUILD FAILED! Please share the error message above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo    BUILD COMPLETE!
echo    exe location: dist\AI-Verification-Engine.exe
echo.
echo    Usage:
echo      1. Double-click AI-Verification-Engine.exe
echo      2. Browser will open automatically
echo      3. Close browser, then close the exe window
echo.
echo    You can share this exe - no Python needed
echo ============================================
pause
