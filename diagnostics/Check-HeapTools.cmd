@echo off
setlocal
echo RC35 Heap tools read-only preflight. No recording or settings modified.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0HeapTrace.ps1" -Mode Check
if errorlevel 1 echo Preflight failed. See README_HEAP_TRACE_JA.md
pause
endlocal
