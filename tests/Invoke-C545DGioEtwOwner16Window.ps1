# CI-only GIO 16-cycle process-specific ETW capture.
# Only existing disposable probe produced by pinned source GLib 2.82.4 build.
# No IFEO/GFlags/UST or real recording process, no raw ETL/paths/stacks upload.
param(
  [Parameter(Mandatory)][string]$Probe,
  [Parameter(Mandatory)][string]$Root,
  [Parameter(Mandatory)][ValidateSet('nochange','registry')][string]$Arm
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows'){
  throw 'CI-only isolated Windows run required'
}
if(([IO.Path]::GetFileName($Probe)) -ne 'c545d_disposable_scanfree.exe'){
  throw 'Refusing non-disposable probe'
}
if(-not(Test-Path $Probe -PathType Leaf) -or -not(Test-Path $Root -PathType Container)){
  throw 'Isolated fixture missing'
}
if(-not($env:C545D_EXPECTED_GIO_DLL -and (Test-Path $env:C545D_EXPECTED_GIO_DLL))){
  throw 'Pinned GIO SDK overlay gate missing'
}
$xperf=$null
foreach($base in @([Environment]::GetEnvironmentVariable('ProgramFiles(x86)'),$env:ProgramFiles)){
  if($base){
    $try=Join-Path $base 'Windows Kits\10\Windows Performance Toolkit\xperf.exe'
    if(Test-Path $try -PathType Leaf){$xperf=$try;break}
  }
}
if(-not $xperf){throw 'Official WPT xperf missing; attribution untested'}
$existing=@(& logman.exe query -ets 2>$null)
if($LASTEXITCODE -ne 0){throw 'Failed to enumerate active ETW sessions'}
if(@($existing | Where-Object {$_ -match '(?i)\bHeapSession\b|\bNT Kernel Logger\b'}).Count){
  throw 'Unowned heap/kernel ETW session: refuse modifications'
}
$args=@('--ci-scanfree-final','--report-types','--heap-summary','--vm-summary')
if($Arm -eq 'nochange'){$args+='--no-registry-change'}
$local=Join-Path $env:RUNNER_TEMP ("c545d_gio_etw_"+$Arm+"_"+[guid]::NewGuid().ToString('N'))
if(Test-Path $local){throw 'Refuse pre-existing owned ETW local path'}
New-Item -ItemType Directory -Path $local | Out-Null
New-Item -ItemType File -Path (Join-Path $local 'ci_owned.signal') | Out-Null
$rawLocal=Join-Path $local 'xperf_output_private.txt'
$loggers=Join-Path $local 'xperf_status_private.txt'
$etl=Join-Path $local 'heap_private.etl'
$stack=Join-Path $local 'stacks_private.txt'
$out=Join-Path $Root ('combo-'+$Arm+'-16.txt')
$err=Join-Path $Root ($Arm+'-error-private.txt')
$proc=$null;$kernelOn=$false;$heapOn=$false;$success=$false
$oldFence=$env:C545D_CI_ETW_PHASE_ROOT
$oldSymbols=$env:_NT_SYMBOL_PATH
function Signal([string]$basename){
  $file=Join-Path $local $basename
  if(Test-Path $file){throw 'Stale ETW handshake signal'}
  New-Item -ItemType File -Path $file | Out-Null
}
function Wait-Signal([string]$basename,[int]$seconds){
  $file=Join-Path $local $basename
  for($i=0;$i -lt ($seconds*10);$i++){
    if(Test-Path $file -PathType Leaf){return}
    if($proc){$proc.Refresh();if($proc.HasExited){throw "GIO signal $basename absent before early exit"}}
    Start-Sleep -Milliseconds 100
  }
  Write-Host "C545D_GIO_ETW_WINDOW_TIMEOUT,arm=$Arm,stage=$basename,raw_uploaded=0"
  throw 'GIO ETW timed out at explicit synchronization barrier'
}
function Invoke-SafeXperf([string]$phase,[string[]]$arguments){
  & $xperf @arguments *> $rawLocal
  if($LASTEXITCODE -ne 0){
    Write-Host "C545D_GIO_ETW_WINDOW_FAILED,arm=$Arm,phase=$phase,raw_uploaded=0"
    throw 'Xperf capture or offline action failed'
  }
}
try {
  if((Test-Path $out) -or (Test-Path $err)){throw 'Refuse overwriting stale CI outputs'}
  $env:C545D_CI_ETW_PHASE_ROOT=$local
  $proc=Start-Process -FilePath $Probe -WorkingDirectory $Root -ArgumentList $args -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
  Wait-Signal 'late_window_ready.signal' 60
  Write-Host "C545D_GIO_ETW_WINDOW_STAGE,arm=$Arm,late_window_ready=1,late_window_cycles_started=0"
  Invoke-SafeXperf 'kernel' @('-on','BASE')
  $kernelOn=$true
  $captureArgs=@('-start','HeapSession','-heap','-pids',"$($proc.Id)",
    '-BufferSize','1024','-MinBuffers','128','-MaxBuffers','128',
    '-FileMode','Sequential','-MaxFile','512','-stackwalk','HeapAlloc+HeapRealloc')
  if(($captureArgs -join ' ') -notmatch '(?i)-FileMode Sequential' -or
     ($captureArgs -join ' ') -match '(?i)\bCircular\b|PidNewProcess'){
     throw 'Unsafe ETW capture mode'
  }
  Invoke-SafeXperf 'preworkload_heap' $captureArgs
  $heapOn=$true
  Signal 'trace_armed.signal'
  Wait-Signal 'precleanup_ready.signal' 55
  Write-Host "C545D_GIO_ETW_WINDOW_STAGE,arm=$Arm,total_cycles=16,etw_window_last_cycles=4,pre_cleanup=1"
  & $xperf -loggers *> $loggers
  if($LASTEXITCODE -ne 0){throw 'ETW loss status unavailable'}
  # Parse only the HeapSession logger section. Other loggers may have
  # different loss counters. Never print raw logger names or machine paths.
  $stats=[string](Get-Content $loggers -Raw -ErrorAction Stop)
  $heapEntry=[regex]::Match($stats,'(?im)^\s*Logger Name\s*:\s*HeapSession\s*$')
  if(-not $heapEntry.Success){
    $anyLogger=[int]([regex]::IsMatch($stats,'(?im)^\s*Logger Name\s*:'))
    Write-Host "C545D_GIO_ETW_LOGGER_GAP,arm=$Arm,heap_session_present=0,any_logger=$anyLogger,raw_uploaded=0"
    throw 'HeapSession disappeared before stop; fail closed'
  }
  $begin=$heapEntry.Index+$heapEntry.Length
  $next=[regex]::Match($stats.Substring($begin),'(?im)^\s*Logger Name\s*:')
  $endPosition=if($next.Success){$begin+$next.Index}else{$stats.Length}
  $heapStatus=$stats.Substring($begin,$endPosition-$begin)
  $eventLoss=[regex]::Match($heapStatus,'(?im)^\s*Events Lost\s*:\s*(\d+)\s*$')
  $bufferLoss=[regex]::Match($heapStatus,'(?im)^\s*Log Buffers Lost\s*:\s*(\d+)\s*$')
  if(-not $eventLoss.Success -or -not $bufferLoss.Success){
    Write-Host "C545D_GIO_ETW_LOGGER_GAP,arm=$Arm,heap_session_present=1,events_line_present=$([int]$eventLoss.Success),log_buffers_line_present=$([int]$bufferLoss.Success),raw_uploaded=0"
    throw 'HeapSession loss counters are incomplete'
  }
  if([int]$eventLoss.Groups[1].Value -ne 0 -or [int]$bufferLoss.Groups[1].Value -ne 0){
    Write-Host "C545D_GIO_ETW_LOSS_DETECTED,arm=$Arm,events=$($eventLoss.Groups[1].Value),buffers=$($bufferLoss.Groups[1].Value),classification_blocked=1"
    throw 'Recorded ETW events or buffers were lost'
  }
  Invoke-SafeXperf 'stop_and_merge' @('-stop','-stop','HeapSession','-d',$etl)
  $heapOn=$false;$kernelOn=$false
  Signal 'trace_stopped.signal'
  if(-not $proc.WaitForExit(25000) -or $proc.ExitCode -ne 0){
    throw 'Disposable GIO process did not exit safely'
  }
  if(-not(Test-Path $out -PathType Leaf) -or
     -not([IO.File]::ReadAllText($out).Contains('GIO_PROBE_DONE,cycles=16,'))){
    throw 'Missing disposable 16-cycle completion'
  }
  if(-not(Test-Path $etl -PathType Leaf) -or (Get-Item $etl).Length -lt 512 -or
     (Get-Item $etl).Length -gt 512MB){
    throw 'ETW local file empty or exceeds bounded capacity'
  }
  # Whole-heap -totals can be interpreted separately even when Xperf
  # -stacks formatting is not safely parseable. This is not source ownership.
  $total=Join-Path $local 'heap_totals_private.txt'
  $totalOK=0
  & $xperf -i $etl -o $total -a heap -totals *> $rawLocal
  if($LASTEXITCODE -eq 0 -and (Test-Path $total) -and (Get-Item $total).Length -gt 40){
    $totLine=@(& py tests/analyze_c545d_xperf_general_totals_ci.py --report $total --arm $Arm 2> $rawLocal)
    $matched=@($totLine | Where-Object {$_ -match ('^C545D_GIO_ETW_HEAP_TOTALS_NUMERIC,arm='+$Arm+',[A-Za-z0-9_,=]+$')})
    if($LASTEXITCODE -eq 0 -and $matched.Count -eq 1){
      New-Item -ItemType Directory -Path (Join-Path $Root 'numeric') -Force | Out-Null
      $matched[0] | Set-Content -Path (Join-Path $Root ("numeric/etw-$Arm-totals-summary-only.txt")) -Encoding ascii
      Write-Host $matched[0]
      $totalOK=1
    }
  }
  if($totalOK -ne 1){Write-Host "C545D_GIO_ETW_TOTALS_PARSE_GAP,arm=$Arm,global_out_unproven=1,raw_uploaded=0"}
  $env:_NT_SYMBOL_PATH="$env:RUNNER_TEMP;srv*$(Join-Path $local 'symbols_private')*https://msdl.microsoft.com/download/symbols"
  Invoke-SafeXperf 'unfiltered_source_stacks' @('-i',$etl,'-o',$stack,
      '-symbols','-a','heap','-stacks','-top','1024')
  if(-not(Test-Path $stack -PathType Leaf) -or (Get-Item $stack).Length -lt 100 -or
     (Get-Item $stack).Length -gt 16MB){
    throw 'Xperf source stack report empty or excessive'
  }
  $safe=@(& py tests/analyze_c545d_gio_etw_stack_cohorts_ci.py --report $stack --arm $Arm 2> $rawLocal)
  $counts=@($safe | Where-Object {$_ -match ('^C545D_GIO_ETW_OWNER_STACK_COHORT,arm='+$Arm+',[A-Za-z0-9_,=]+$')})
  if($LASTEXITCODE -ne 0 -or $counts.Count -ne 1){
    $diag=@(& py tests/analyze_c545d_gio_etw_stack_cohorts_ci.py --report $stack --arm $Arm --diagnose 2> $rawLocal)
    $allow=@($diag | Where-Object {$_ -match ('^C545D_GIO_ETW_STACK_PARSE_DIAGNOSTIC,arm='+$Arm+',[A-Za-z0-9_,=]+$')})
    if($LASTEXITCODE -eq 0 -and $allow.Count -eq 1){
      New-Item -ItemType Directory -Path (Join-Path $Root 'numeric') -Force | Out-Null
      $allow[0] | Set-Content -Path (Join-Path $Root ("numeric/etw-$Arm-stack-gap-summary-only.txt")) -Encoding ascii
      Write-Host $allow[0]
    }
    # When a top-1024 call-stack report is incomplete, try the documented
    # Xperf -images mode as an independent *top-frame-image group* count.
    # It is NOT an allocating function, and can also be incomplete.
    # Any raw image strings, addresses, symbols stay runner-local.
    $imagePrivate=Join-Path $local 'heap_images_private.txt'
    & $xperf -i $etl -o $imagePrivate -symbols -a heap -images -top 1024 *> $rawLocal
    if($LASTEXITCODE -eq 0 -and (Test-Path $imagePrivate -PathType Leaf) -and
       (Get-Item $imagePrivate).Length -gt 100 -and
       (Get-Item $imagePrivate).Length -lt 16MB){
      $imageSafe=@(& py tests/analyze_c545d_gio_etw_image_aggregate_ci.py --report $imagePrivate --arm $Arm 2> $rawLocal)
      $imageMatch=@($imageSafe | Where-Object {$_ -match ('^C545D_GIO_ETW_IMAGE_AGGREGATE,arm='+$Arm+',[A-Za-z0-9_,=]+$')})
      if($LASTEXITCODE -eq 0 -and $imageMatch.Count -eq 1){
        $imageMatch[0] | Set-Content -Path (Join-Path $Root ("numeric/etw-$Arm-image-summary-only.txt")) -Encoding ascii
        Write-Host $imageMatch[0]
      } else {
        $imageDiag=@(& py tests/analyze_c545d_gio_etw_image_aggregate_ci.py --report $imagePrivate --arm $Arm --diagnose 2> $rawLocal)
        $imageAllowed=@($imageDiag | Where-Object {$_ -match ('^C545D_GIO_ETW_IMAGE_PARSE_DIAGNOSTIC,arm='+$Arm+',[A-Za-z0-9_,=]+$')})
        if($LASTEXITCODE -eq 0 -and $imageAllowed.Count -eq 1){
          $imageAllowed[0] | Set-Content -Path (Join-Path $Root ("numeric/etw-$Arm-image-gap-summary-only.txt")) -Encoding ascii
          Write-Host $imageAllowed[0]
        }
        Write-Host "C545D_GIO_ETW_IMAGE_GAP,arm=$Arm,reason=IMAGE_REPORT_SCHEMA_UNVERIFIED,raw_uploaded=0"
      }
    } else {
      Write-Host "C545D_GIO_ETW_IMAGE_GAP,arm=$Arm,reason=IMAGE_ACTION_UNAVAILABLE,raw_uploaded=0"
    }
    throw 'Incomplete or unsafely parsed source stack cohort report'
  }
  $numericOnly=$counts[0]
  Set-Content -Path (Join-Path $Root ('etw-'+$Arm+'-source-cohorts-only.txt')) -Encoding ascii -Value $numericOnly
  Write-Host $numericOnly
  Write-Host "C545D_GIO_ETW_OWNER_WINDOW_PASS,arm=$Arm,total_cycles=16,etw_traced_cycles=4,sequential=1,lost_events_zero=1,prelatewindow=1,precleanup=1,global_quiet_proven=0,leak_proven=0,raw_uploaded=0,host_untouched=1"
  $success=$true
} finally {
  if($heapOn){& $xperf -stop HeapSession *> $rawLocal}
  if($kernelOn){& $xperf -stop *> $rawLocal}
  if((Test-Path $local) -and -not(Test-Path (Join-Path $local 'trace_stopped.signal'))){
    try{Signal 'trace_stopped.signal'}catch{}
  }
  if($proc){
    try{$proc.Refresh();if(-not $proc.WaitForExit(4000)){Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue}}catch{}
  }
  if($null -eq $oldFence){Remove-Item Env:C545D_CI_ETW_PHASE_ROOT -ErrorAction SilentlyContinue}
  else{$env:C545D_CI_ETW_PHASE_ROOT=$oldFence}
  if($null -eq $oldSymbols){Remove-Item Env:_NT_SYMBOL_PATH -ErrorAction SilentlyContinue}
  else{$env:_NT_SYMBOL_PATH=$oldSymbols}
  if((Test-Path $local) -and (Test-Path (Join-Path $local 'ci_owned.signal')) -and
     $local.StartsWith($env:RUNNER_TEMP,[StringComparison]::OrdinalIgnoreCase)){
    Remove-Item $local -Force -Recurse -ErrorAction SilentlyContinue
  }
}
if($success){$global:LASTEXITCODE=0}
