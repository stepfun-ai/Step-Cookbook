@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\bootstrap.ps1" %*
if errorlevel 1 (
  echo.
  echo 启动未完成，请查看上方提示，处理后再次双击。
  pause
  exit /b 1
)
