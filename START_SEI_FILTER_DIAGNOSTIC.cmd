@echo off
setlocal DisableDelayedExpansion
rem Opt-in C545D H264 SEI-only AU filter candidate. Normal EXE stays OFF.
rem First stop the old recorder using its usual GUI EOS button.
if not exist "%~dp0plugins\gstc545dsei.dll" (
  echo Optional native H264 filter DLL is absent. No test was started.
  pause
  exit /b 1
)
set "C545D_SEI_AU_FILTER=on"
call "%~dp0START_DIAGNOSTIC.cmd"
endlocal
