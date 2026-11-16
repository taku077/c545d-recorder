# Explicit manual recovery ONLY. Not run on a timer or at startup.
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'CommonSettings.ps1')
. (Join-Path $PSScriptRoot 'SegmentNamer.ps1')
try {
    $settings=Read-C545DSettings
    $folder=[string]$settings.output_folder
    Write-Host ('未改名MP4を手動確認: ' + $folder)
    Invoke-C545DRenameSegments -OutputDirectory $folder
    Write-Host '完了。録画中・未確定のMP4は変更されません。'
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
}
Read-Host 'Enterで閉じる'
