# C545D per-process memory recorder (Windows PowerShell 5.1, ASCII-only).
# Read-only monitoring: no UST/GFlags changes, no recorder stop/restart.
[CmdletBinding()]
param(
    [ValidateRange(1,1440)][int]$DurationMinutes = 240,
    [ValidateRange(10,600)][int]$IntervalSeconds = 60,
    [switch]$SelfTest
)
$ErrorActionPreference = 'Stop'

function New-Sample([string]$status, [object]$proc, [int]$sampleNumber, [datetime]$begin) {
    $now = Get-Date
    $processId = ''
    $processStart = ''
    $privateMb = ''
    $workingSetMb = ''
    $handles = ''
    $cpuSeconds = ''
    if ($null -ne $proc) {
        try {
            $proc.Refresh()
            $processId = [string]$proc.Id
            $processStart = $proc.StartTime.ToString('yyyy-MM-dd HH:mm:ss')
            $privateMb = [math]::Round($proc.PrivateMemorySize64 / 1MB, 2)
            $workingSetMb = [math]::Round($proc.WorkingSet64 / 1MB, 2)
            $handles = $proc.HandleCount
            $cpuSeconds = [math]::Round($proc.TotalProcessorTime.TotalSeconds, 2)
        }
        catch {
            $status = 'PROCESS_DISAPPEARED'
            $privateMb = ''
            $workingSetMb = ''
            $handles = ''
            $cpuSeconds = ''
        }
    }
    [PSCustomObject]@{
        LocalTime = $now.ToString('yyyy-MM-dd HH:mm:ss')
        ElapsedMinutes = [math]::Round(($now - $begin).TotalMinutes, 2)
        Sample = $sampleNumber
        Status = $status
        PID = $processId
        ProcessStart = $processStart
        PrivateMB = $privateMb
        WorkingSetMB = $workingSetMb
        Handles = $handles
        CPUSeconds = $cpuSeconds
    }
}

if ($SelfTest) {
    $begin = Get-Date
    $tmp = Join-Path $env:TEMP ('C545D_memory_test_' + [guid]::NewGuid().ToString('N') + '.csv')
    try {
        $me = Get-Process -Id $PID -ErrorAction Stop
        $rows = @(
            (New-Sample 'OK' $me 1 $begin),
            (New-Sample 'NOT_RUNNING' $null 2 $begin)
        )
        $rows | Export-Csv -LiteralPath $tmp -NoTypeInformation -Encoding UTF8
        $loaded = @(Import-Csv -LiteralPath $tmp)
        if ($loaded.Count -ne 2 -or $loaded[0].Status -ne 'OK' -or
            $loaded[1].Status -ne 'NOT_RUNNING' -or
            -not $loaded[0].PrivateMB -or -not $loaded[0].PID) {
            throw 'SELFTEST_FAILED'
        }
        Write-Output 'SELFTEST_PASS: process sample, CSV header, CSV readback.'
    }
    finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
    exit 0
}

$logDir = Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\MemoryMonitor'
if (-not (Test-Path -LiteralPath $logDir -PathType Container)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$outFile = Join-Path $logDir ('C545D_Memory_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.csv')
$started = Get-Date
$deadline = $started.AddMinutes($DurationMinutes)
$sampleNumber = 0
Write-Host ('Monitoring gst-launch-1.0.exe for {0} minutes (every {1} seconds).' -f $DurationMinutes,$IntervalSeconds)
Write-Host ('CSV: ' + $outFile)
Write-Host 'Do not open the CSV in Excel before this logger finishes.'
Write-Host 'Recording continues normally. No administrator permission required.'

while ($true) {
    $sampleNumber++
    $processes = @()
    $status = 'NOT_RUNNING'
    $selected = $null
    try {
        $processes = @(Get-Process -Name 'gst-launch-1.0' -ErrorAction SilentlyContinue)
        if ($processes.Count -eq 1) {
            $status = 'OK'
            $selected = $processes[0]
        }
        elseif ($processes.Count -gt 1) { $status = 'MULTIPLE_PROCESSES' }
    }
    catch { $status = 'PROCESS_LOOKUP_ERROR' }

    $row = New-Sample $status $selected $sampleNumber $started
    # A unique CSV is created for each run and flushed once per minute.
    $row | Export-Csv -LiteralPath $outFile -NoTypeInformation -Encoding UTF8 -Append
    if ($sampleNumber -eq 1 -or ($sampleNumber % 30) -eq 0 -or $row.Status -ne 'OK') {
        Write-Host ('{0}  sample={1}  status={2}  PID={3}  PrivateMB={4}' -f
            $row.LocalTime,$row.Sample,$row.Status,$row.PID,$row.PrivateMB)
    }
    if ((Get-Date) -ge $deadline) { break }
    $remaining = ($deadline - (Get-Date)).TotalSeconds
    if ($remaining -le 0) { break }
    $sleepSec = [math]::Min($IntervalSeconds, [math]::Ceiling($remaining))
    Start-Sleep -Seconds ([int]$sleepSec)
}
Write-Host ('COMPLETE: ' + $outFile)
Write-Host 'Upload only this CSV for analysis. No camera or network credentials are collected.'
