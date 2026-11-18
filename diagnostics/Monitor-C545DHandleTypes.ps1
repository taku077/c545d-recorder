# C545D read-only handle type monitor for Windows PowerShell 5.1.
# Requires official Microsoft Sysinternals Handle64.exe separately.
# Does not stop/restart recorder or modify GFlags/UST/any handles.
[CmdletBinding()]
param(
    [ValidateRange(1,1440)][int]$DurationMinutes = 240,
    [ValidateRange(30,600)][int]$IntervalSeconds = 60,
    [string]$HandleExe = '',
    [switch]$SelfTest,
    [switch]$Preflight,
    [ValidateRange(0,2147483647)][int]$ProbePid = 0
)
$ErrorActionPreference = 'Stop'

function Parse-HandleSummary([string]$raw) {
    $typeRows = New-Object 'System.Collections.Generic.List[object]'
    $inSummary = $false
    $total = $null
    $hasHeading = $false
    foreach ($line in ($raw -split '\r?\n')) {
        if ($line -match '^\s*Handle type summary:\s*$') {
            if ($hasHeading) { throw 'MULTIPLE_SUMMARIES' }
            $hasHeading = $true
            $inSummary = $true
            continue
        }
        if (-not $inSummary) { continue }
        $m = [regex]::Match($line,'^\s*Total handles:\s*([0-9]+)\s*$')
        if ($m.Success) {
            $total = [long]::Parse($m.Groups[1].Value)
            $inSummary = $false
            break
        }
        $m = [regex]::Match($line,'^\s*(<Unknown type>|[A-Za-z][A-Za-z0-9 ]{0,63})\s*:\s*([0-9]+)\s*$')
        if (-not $m.Success) { continue }
        $type = $m.Groups[1].Value.Trim()
        # Object type names are non-personal kernel classes. Suppress arbitrary strings.
        if ($type -eq '<Unknown type>') { $type = 'UnknownType' }
        elseif ($type -notmatch '^[A-Za-z][A-Za-z0-9 ]{0,39}$') { $type = 'OtherType' }
        $count = [long]::Parse($m.Groups[2].Value)
        [void]$typeRows.Add([pscustomobject]@{Type=$type;Count=$count})
    }
    if (-not $hasHeading -or $null -eq $total -or $typeRows.Count -eq 0) {
        throw 'HANDLE_SUMMARY_UNRECOGNIZED'
    }
    $sum = 0L
    $grouped = New-Object 'System.Collections.Generic.List[object]'
    foreach ($group in ($typeRows | Group-Object Type)) {
        $count = 0L
        foreach ($item in $group.Group) { $count += [long]$item.Count }
        $sum += $count
        [void]$grouped.Add([pscustomobject]@{Type=[string]$group.Name;Count=$count})
    }
    return [pscustomobject]@{Total=$total; Sum=$sum; Rows=$grouped.ToArray()}
}

function Find-HandleExe([string]$preferred) {
    if ($preferred) {
        if (Test-Path -LiteralPath $preferred -PathType Leaf) {
            return (Resolve-Path -LiteralPath $preferred).Path
        }
        throw 'HANDLE_EXE_NOT_FOUND: specified path does not exist.'
    }
    $candidates = @(
        (Join-Path $PSScriptRoot 'handle64.exe'),
        (Join-Path $PSScriptRoot 'handle.exe'),
        (Join-Path $PSScriptRoot 'Handle\handle64.exe'),
        (Join-Path $PSScriptRoot 'Handle\handle.exe'),
        (Join-Path $env:USERPROFILE 'Downloads\Handle\handle64.exe'),
        (Join-Path $env:USERPROFILE 'Downloads\Handle\handle.exe')
    )
    foreach ($path in $candidates) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            return (Resolve-Path -LiteralPath $path).Path
        }
    }
    foreach ($name in @('handle64.exe','handle.exe')) {
        $p=Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($p) {return $p.Source}
    }
    throw 'HANDLE_EXE_NOT_FOUND: download Handle.zip from Microsoft and put handle64.exe beside this script.'
}

function Invoke-HandleSummary([string]$exe,[int]$targetPid,[int]$timeoutMs=30000) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe
    # Numeric PID, summary only. No -a, no per-handle names, never -c.
    $psi.Arguments = ('-accepteula -s -p {0}' -f $targetPid)
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        if (-not $p.Start()) { throw 'HANDLE_EXECUTION_FAILED' }
        $stdoutTask = $p.StandardOutput.ReadToEndAsync()
        $stderrTask = $p.StandardError.ReadToEndAsync()
        if (-not $p.WaitForExit($timeoutMs)) {
            try { $p.Kill() } catch { }
            try { [void]$p.WaitForExit(3000) } catch { }
            throw 'HANDLE_TIMEOUT'
        }
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $null = $stderrTask.GetAwaiter().GetResult()
        if ($p.ExitCode -ne 0) { throw 'HANDLE_EXIT_NONZERO' }
        $result = Parse-HandleSummary $stdout
        $watch.Stop()
        return [pscustomobject]@{
            Total=$result.Total
            Sum=$result.Sum
            Rows=$result.Rows
            ElapsedMs=$watch.ElapsedMilliseconds
        }
    }
    finally {
        if (-not $p.HasExited) {try { $p.Kill() } catch {}}
        $p.Dispose()
        $watch.Stop()
    }
}

function Get-RecorderInfo {
    $procs = @(Get-Process -Name 'gst-launch-1.0' -ErrorAction SilentlyContinue)
    if ($procs.Count -eq 0) { return [pscustomobject]@{Status='NOT_RUNNING'; Process=$null} }
    if ($procs.Count -gt 1) { return [pscustomobject]@{Status='MULTIPLE_RECORDERS'; Process=$null} }
    $p=$procs[0]
    try {
        $p.Refresh()
        $null=$p.StartTime
        return [pscustomobject]@{Status='OK';Process=$p}
    }
    catch {return [pscustomobject]@{Status='PROCESS_DISAPPEARED';Process=$null}}
}

function New-Row([int]$sample, [datetime]$began,[string]$status,[object]$recorder,[object]$handleResult) {
    $now=Get-Date
    $pidString=''; $start=''; $private=''; $working=''; $handles=''
    if ($recorder) {
        try {
            $recorder.Refresh()
            $pidString=[string]$recorder.Id
            $start=$recorder.StartTime.ToString('yyyy-MM-dd HH:mm:ss')
            $private=[math]::Round($recorder.PrivateMemorySize64/1MB,2)
            $working=[math]::Round($recorder.WorkingSet64/1MB,2)
            $handles=$recorder.HandleCount
        } catch {$status='PROCESS_DISAPPEARED'}
    }
    $toolTotal=''; $typeSum=''; $toolMs=''
    if ($handleResult) {
        $toolTotal=$handleResult.Total
        $typeSum=$handleResult.Sum
        $toolMs=$handleResult.ElapsedMs
        if ($handleResult.Total -ne $handleResult.Sum) {$status='COUNT_MISMATCH'}
    }
    return [pscustomobject]@{
        LocalTime=$now.ToString('yyyy-MM-dd HH:mm:ss')
        ElapsedMinutes=[math]::Round(($now-$began).TotalMinutes,2)
        Sample=$sample
        Status=$status
        PID=$pidString
        ProcessStart=$start
        PrivateMB=$private
        WorkingSetMB=$working
        ProcessHandles=$handles
        HandleToolTotal=$toolTotal
        TypesSum=$typeSum
        ToolElapsedMs=$toolMs
    }
}

if ($SelfTest) {
    $example=@'
Handle v5.0
Sysinternals - www.sysinternals.com

Handle type summary:
  ALPC Port       : 7
  Event           : 456
  File            : 36
  Process         : 7670
  <Unknown type>  : 2
Total handles: 8171
'@
    $p=Parse-HandleSummary $example
    if ($p.Total -ne 8171 -or $p.Sum -ne 8171 -or $p.Rows.Count -ne 5 -or
        @($p.Rows|Where-Object { $_.Type -eq 'UnknownType' -and $_.Count -eq 2 }).Count -ne 1) {
        throw 'SELFTEST_PARSER_FAILED'
    }
    $errorCaught=$false
    try { $null=Parse-HandleSummary 'a non-summary response' }
    catch { $errorCaught=$true }
    if (-not $errorCaught) { throw 'SELFTEST_FALSE_SUCCESS' }
    $temp=Join-Path $env:TEMP ('C545D_handle_selftest_'+[guid]::NewGuid().ToString('N')+'.csv')
    try {
        $begin=Get-Date
        $row=New-Row 1 $begin 'OK' $null $p
        @($row) | Export-Csv -LiteralPath $temp -NoTypeInformation -Encoding UTF8
        $read=@(Import-Csv -LiteralPath $temp)
        if ($read.Count -ne 1 -or $read[0].HandleToolTotal -ne '8171') {throw 'SELFTEST_CSV_FAILED'}
    } finally {Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue}
    Write-Host 'SELFTEST_PASS: Handle -s parser, failure gate, sanitized CSV.'
    exit 0
}

# Microsoft docs require elevation to read target handles reliably.
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'ADMIN_REQUIRED: Right-click START_HANDLE_TYPES_4H.cmd and select Run as administrator.'
}
$exe=Find-HandleExe $HandleExe
if ($ProbePid -gt 0) {
    $r=Invoke-HandleSummary $exe $ProbePid
    Write-Host ('PROBE_PASS: Total={0}, SumTypes={1}, TypeKinds={2}' -f $r.Total,$r.Sum,$r.Rows.Count)
    exit 0
}
$initial=Get-RecorderInfo
if ($initial.Status -ne 'OK') {
    throw ('RECORDER_NOT_UNIQUE: status='+$initial.Status+'. Do not stop or restart the recorder.')
}
$initialPid=[int]$initial.Process.Id
Write-Host ('Preflight: reading Handle -s summary for PID '+$initialPid)
try {$initialResult=Invoke-HandleSummary $exe $initialPid}
catch {throw ('PREFLIGHT_FAILED: '+$_.Exception.Message+'. No CSV monitoring started.')}
Write-Host ('Preflight OK: HandleTotal={0}, SumTypes={1}. No names were collected.' -f $initialResult.Total,$initialResult.Sum)
if ($Preflight) { Write-Host 'PREFLIGHT_PASS'; exit 0 }

$dir=Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\HandleTypesMonitor'
if(-not (Test-Path -LiteralPath $dir -PathType Container)){
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$summaryPath=Join-Path $dir ('C545D_HandleSummary_'+$stamp+'.csv')
$typesPath=Join-Path $dir ('C545D_HandleTypes_'+$stamp+'.csv')
$zipPath=Join-Path $dir ('C545D_HandleEvidence_'+$stamp+'.zip')
$started=Get-Date
$deadline=$started.AddMinutes($DurationMinutes)
$sample=0
$previousPid=0
$previousStart=''
Write-Host ('Logging every {0}s for {1}min. Minimize this window.' -f $IntervalSeconds,$DurationMinutes)
Write-Host 'Only numeric counts and generic kernel object type names are saved.'
Write-Host ('Summary: '+$summaryPath)
Write-Host ('Types: '+$typesPath)
while ($true) {
    $sample++
    $selection=Get-RecorderInfo
    $result=$null
    $status=$selection.Status
    $process=$selection.Process
    if ($process) {
        try {
            $startStr=$process.StartTime.ToString('yyyy-MM-dd HH:mm:ss')
            if ($previousPid -ne 0 -and
                ($previousPid -ne $process.Id -or $previousStart -ne $startStr)) {
                $status='PID_CHANGED'
            }
            $previousPid=$process.Id
            $previousStart=$startStr
            $result=Invoke-HandleSummary $exe ([int]$process.Id)
            if ($status -eq 'OK' -and $result.Total -ne $result.Sum) {
                $status='COUNT_MISMATCH'
            }
        }
        catch {
            $status='HANDLE_ERROR'
            Write-Host ('Sample {0}: Handle summary unavailable; no raw output saved.' -f $sample)
        }
    }
    $row=New-Row $sample $started $status $process $result
    $row | Export-Csv -LiteralPath $summaryPath -NoTypeInformation -Encoding UTF8 -Append
    if ($result) {
        foreach($type in $result.Rows) {
            [pscustomobject]@{
                LocalTime=$row.LocalTime
                Sample=$sample
                PID=$row.PID
                Type=$type.Type
                Count=$type.Count
            } | Export-Csv -LiteralPath $typesPath -NoTypeInformation -Encoding UTF8 -Append
        }
    }
    if ($sample -eq 1 -or ($sample % 30) -eq 0 -or $status -ne 'OK') {
        Write-Host ('{0} sample={1} PID={2} Status={3} Handles={4} PrivateMB={5}' -f
            $row.LocalTime,$row.Sample,$row.PID,$row.Status,$row.HandleToolTotal,$row.PrivateMB)
    }
    if ((Get-Date) -ge $deadline) {break}
    $remain=($deadline-(Get-Date)).TotalSeconds
    if ($remain -le 0) {break}
    Start-Sleep -Seconds ([int][math]::Min($IntervalSeconds,[math]::Ceiling($remain)))
}
if ((Test-Path -LiteralPath $summaryPath -PathType Leaf) -and
    (Test-Path -LiteralPath $typesPath -PathType Leaf)) {
    Compress-Archive -LiteralPath @($summaryPath,$typesPath) -DestinationPath $zipPath -CompressionLevel Optimal
    Write-Host ('COMPLETE. Upload only: '+$zipPath)
} else {
    Write-Host 'INCOMPLETE: inspect local CSV paths printed above; no raw Handle logs were saved.'
}
