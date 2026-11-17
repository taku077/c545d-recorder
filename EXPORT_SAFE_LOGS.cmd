@echo off
setlocal DisableDelayedExpansion
echo C545D: Exporting a safe diagnostics ZIP (no recording restart).
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Export-SafeDiagnostics.ps1"
if errorlevel 1 (
    echo Export failed. No original recording or logs were modified.
) else (
    echo ZIP created in Downloads. Upload ONLY C545D_SAFE_DIAGNOSTICS_*.zip.
)
pause
endlocal
