@echo off
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Monitor-C545DHandleTypes.ps1"
echo.
echo Monitoring finished or stopped. Review the output above.
pause
