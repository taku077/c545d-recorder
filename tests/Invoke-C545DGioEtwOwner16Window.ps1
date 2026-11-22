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
  Wait-Signal 'baseline_ready.signal' 60
  Write-Host "C545D_GIO_ETW_WINDOW_STAGE,arm=$Arm,baseline_ready=1,controlled_cycles_started=0"
  Invoke-SafeXperf 'kernel' @('-on','BASE')
  $kernelOn=$true
  $captureArgs=@('-start','HeapSession','-heap','-pids',"$($proc.Id)",
    '-BufferSize','1024','-MinBuffers','128','-MaxBuffers','128',
    '-FileMode','Sequential','-MaxFile','256','-stackwalk','HeapAlloc+HeapRealloc')
  if(($captureArgs -join ' ') -notmatch '(?i)-FileMode Sequential' -or
     ($captureArgs -join ' ') -match '(?i)\bCircular\b|PidNewProcess'){
     throw 'Unsafe ETW capture mode'
  }
  Invoke-SafeXperf 'preworkload_heap' $captureArgs
  $heapOn=$true
  Signal 'trace_armed.signal'
  Wait-Signal 'precleanup_ready.signal' 55
  Write-Host "C545D_GIO_ETW_WINDOW_STAGE,arm=$Arm,controlled_cycles=16,pre_cleanup=1"
  & $xperf -loggers *> $loggers
  if($LASTEXITCODE -ne 0){throw 'ETW loss status unavailable'}
  $stats=Get-Content $loggers -Raw -ErrorAction Stop
  if($stats -notmatch '(?im)Logger Name\s*:\s*HeapSession[\s\S]*?Events Lost\s*:\s*(\d+)[\s\S]*?Log Buffers Lost\s*:\s*(\d+)'){
    throw 'ETW logger lost-event counters not independently parsed'
  }
  if([int]$Matches[1] -ne 0 -or [int]$Matches[2] -ne 0){
    throw 'ETW event loss or buffer loss detected: classification forbidden'
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
     (Get-Item $etl).Length -gt 256MB){
    throw 'ETW local file empty or exceeds bounded capacity'
  }
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
    throw 'Incomplete or unsafely parsed source stack cohort report'
  }
  $numericOnly=$counts[0]
  Set-Content -Path (Join-Path $Root ('etw-'+$Arm+'-source-cohorts-only.txt')) -Encoding ascii -Value $numericOnly
  Write-Host $numericOnly
  Write-Host "C545D_GIO_ETW_OWNER_WINDOW_PASS,arm=$Arm,cycles=16,sequential=1,lost_events_zero=1,preworkload=1,precleanup=1,global_quiet_proven=0,leak_proven=0,raw_uploaded=0,host_untouched=1"
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
