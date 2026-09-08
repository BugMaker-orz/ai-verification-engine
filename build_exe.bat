@echo off
chcp 65001 >nul
title AI 验真引擎 - 一键打包
cd /d "%~dp0"

echo ============================================
echo    AI 验真引擎 — Windows 一键打包脚本
echo ============================================
echo.
echo 本脚本会自动：建虚拟环境 → 装依赖 → 打包 exe
echo 需要联网，全程约 5-10 分钟
echo.

REM 1. 创建虚拟环境（如果不存在）
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] 创建虚拟环境 .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo 创建虚拟环境失败！请确认：
        echo   1. 已安装 Python 3.9+（https://www.python.org/downloads/）
        echo   2. 安装时勾选了 "Add Python to PATH"
        pause
        exit /b 1
    )
) else (
    echo [1/4] 虚拟环境已存在，跳过创建
)

echo [2/4] 安装项目依赖 ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo 依赖安装失败！
    pause
    exit /b 1
)

echo [3/4] 安装打包工具 PyInstaller ...
".venv\Scripts\python.exe" -m pip install pyinstaller -q
if errorlevel 1 (
    echo PyInstaller 安装失败！
    pause
    exit /b 1
)

echo [4/4] 开始打包（此步骤较慢，请耐心等待）...
".venv\Scripts\python.exe" -m PyInstaller ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --name "AI验真引擎" ^
  --collect-all gradio ^
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
    echo 打包失败！请把上方错误信息发给项目作者。
    pause
    exit /b 1
)

echo.
echo ============================================
echo    打包完成！
echo    exe 位置：dist\AI验真引擎.exe
echo.
echo    使用方法：
echo      1. 双击 AI验真引擎.exe
echo      2. 浏览器会自动打开操作界面
echo      3. 关闭浏览器后，点 exe 窗口上的 X 退出
echo.
echo    可以把这个 exe 发给同学，对方电脑无需装 Python
echo ============================================
pause
