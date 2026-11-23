@echo off
setlocal DisableDelayedExpansion
set "OBSERVER=%~dp0diagnostics\C545D-WeeklyObserver.ps1"
if not exist "%OBSERVER%" (
  echo Weekly observer is missing. Extract the ENTIRE recorder ZIP.
  pause
  exit /b 2
)
echo C545D: Starting the detached read-only process monitor.
echo No recorder process is stopped, restarted or modified.
echo A second monitor is blocked by a local single-instance mutex.
start "C545D weekly diagnostic observer" /min "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%OBSERVER%"
if errorlevel 1 (
  echo Monitor launch failed.
  pause
  exit /b 1
)
echo Observer started as a separate process. It writes only local CSV/ZIP reports.
echo First report is generated after 72 hours; later reports every 7 days.
endlocal
