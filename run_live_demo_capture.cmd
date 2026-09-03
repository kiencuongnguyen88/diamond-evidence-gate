@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_live_demo_capture.ps1"
set "rc=%ERRORLEVEL%"
endlocal & exit /b %rc%
