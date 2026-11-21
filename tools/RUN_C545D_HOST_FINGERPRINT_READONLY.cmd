@echo off
setlocal
cd /d "%~dp0"
echo C545D GStreamer DLL read-only check - no changes to recording.
echo Only the single numeric result line needs to be shared.
echo.
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Get-C545DGStreamerHostFingerprintReadOnly.ps1"
set "C545D_RESULT=%errorlevel%"
echo.
echo No files, settings, recorder processes or registry values were modified.
echo Check result code: %C545D_RESULT%  (0 = exact reference; 3 = mismatch/incomplete)
echo Any match is NOT approval to install or replace DLLs.
pause
exit /b %C545D_RESULT%
