@echo off
setlocal
cd /d "%~dp0"
echo C545D future isolated GIO camera-free smoke: DEVELOPMENT ONLY.
echo NOT APPROVED for the recorder PC or production installation.
echo Do not run unless separately authorized after a natural safe recording stop.
echo Never copy the bundled GIO DLL into the installed GStreamer folders.
echo This verifies a private temporary process, not real Tapo video or 1-hour MP4.
echo.
choice /C YN /M "Explicit supervised approval AND recorder safely stopped? "
if errorlevel 2 exit /b 3
if not errorlevel 1 exit /b 3
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Invoke-C545DWin10IsolatedGioSmoke.ps1"
set "C545D_TEST_RC=%errorlevel%"
echo.
echo Do not send files, debug traces, local paths, or camera information.
echo Only the C545D_GIO_ISOLATED_SMOKE numeric result line is needed.
echo Exit code: %C545D_TEST_RC%  [0 = camera-free smoke pass; 3 = blocked/failure]
echo Neither outcome authorizes a live Tapo test or DLL installation.
pause
exit /b %C545D_TEST_RC%
