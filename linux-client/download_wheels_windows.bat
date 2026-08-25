@echo off
REM ============================================================
REM  CapsWriter Offline Linux 客户端 —— Windows 联网机一键下载
REM  双击运行即可，内部调用 download_wheels_windows.ps1
REM  目标机默认按 Python 3.7（银河麒麟 V10 自带）下载 aarch64 包
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo [*] 正在为 arm64 银河麒麟 V10 (Python 3.7) 下载离线依赖...
echo.

where pwsh >nul 2>nul
if %errorlevel%==0 (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "download_wheels_windows.ps1" -PyVer 3.7
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "download_wheels_windows.ps1" -PyVer 3.7
)

echo.
pause
