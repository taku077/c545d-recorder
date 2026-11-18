@echo off
setlocal
set "ETL=%LOCALAPPDATA%\C545D_GStreamer\WPR_Handle\C545D_Handle_20261118_210100.etl"
set "OUT=%LOCALAPPDATA%\C545D_GStreamer\WPR_Handle\C545D_Handle_20261118_210100_SAFE_SUMMARY.txt"
if not exist "%~dp0EtwHandleOffline.exe" (
  echo ERROR: EtwHandleOffline.exe is missing from this folder.
  pause
  exit /b 1
)
if not exist "%ETL%" (
  echo ERROR: Saved ETL not found. The original recording is untouched.
  pause
  exit /b 2
)
echo Analyzing the SAVED ETL for PID 6168. No new capture.
"%~dp0EtwHandleOffline.exe" --etl "%ETL%" --pid 6168 --out "%OUT%"
if errorlevel 1 (
  echo Analysis did not complete. Do NOT upload the raw ETL.
  pause
  exit /b 3
)
echo.
echo COMPLETE: review SAFE_SUMMARY.txt in your WPR_Handle folder.
echo Please share ONLY the safe summary text, not the ETL.
pause
