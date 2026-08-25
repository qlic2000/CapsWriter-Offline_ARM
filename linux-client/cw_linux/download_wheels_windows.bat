@echo off
REM ============================================================
REM  CapsWriter Offline Linux Client - Windows one-click wheel download
REM
REM  Double-click to run. It calls download_wheels_windows.ps1
REM  Target: Kylin V10 arm64, default Python 3.7 (system python).
REM
REM  To use another target Python version (e.g. 3.8), edit the two
REM  "-PyVer 3.7" arguments below accordingly.
REM
REM  NOTE: Keep this file pure ASCII. Non-ASCII characters in a .bat
REM        depend on the console code page and can break cmd parsing.
REM ============================================================
cd /d "%~dp0"

echo.
echo [*] Downloading aarch64 wheels for Kylin V10 (Python 3.7)...
echo     Messages below may be shown in Chinese by the PowerShell script.
echo.

where pwsh >nul 2>nul
if %errorlevel%==0 (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "download_wheels_windows.ps1" -PyVer 3.7
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "download_wheels_windows.ps1" -PyVer 3.7
)

echo.
pause
