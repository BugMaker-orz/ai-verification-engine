@echo off
echo ============================================
echo   AI Verification Engine - Stop All
echo ============================================
echo.
echo Stopping all AI-Verification-Engine.exe processes...
taskkill /F /IM AI-Verification-Engine.exe 2>nul
if %errorlevel%==0 (
    echo.
    echo [OK] All instances stopped. Ports released.
) else (
    echo.
    echo [INFO] No running instances found.
)
echo.
echo You can close this window.
pause >nul
