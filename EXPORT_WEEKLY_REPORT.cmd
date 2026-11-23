@echo off
setlocal DisableDelayedExpansion
set "OBSERVER=%~dp0diagnostics\C545D-WeeklyObserver.ps1"
if not exist "%OBSERVER%" (
  echo Weekly observer is missing. Extract the ENTIRE recorder ZIP.
  pause
  exit /b 2
)
echo C545D: Generate a safe last-7-days ZIP on this PC.
echo This does NOT stop the recorder or upload any files.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%OBSERVER%" -ExportNow
if errorlevel 1 (
  echo Safe weekly ZIP generation failed. Previous data are kept intact.
  pause
  exit /b 1
)
echo Report created. Attach only the C545D_SAFE_WEEKLY_*.zip to the project chat.
pause
endlocal
