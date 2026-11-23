# CI-only small synthetic ETW realloc-source grouping experiment.
# No GIO, camera, recorder, host registry writes, IFEO, WPR, or raw ETL upload.
param([switch]$SelfTest)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'

function Check-Plan([string[]]$argsLine) {
  $line=$argsLine -join ' '
  if($line -notmatch '(?i)-Pids?\s+\d+' -or
     $line -notmatch '(?i)-FileMode\s+Sequential' -or
     $line -notmatch 'HeapAlloc\+HeapRealloc' -or
     $line -match '(?i)\bCircular\b|PidNewProcess|TracingFlags|gflags|IFEO'){
    throw 'Unsafe or incomplete synthetic realloc ETW capture plan'
  }
}
if($SelfTest){
  $ok=@('-start','HeapSession','-heap','-Pids','1234','-FileMode','Sequential','-stackwalk','HeapAlloc+HeapRealloc')
  Check-Plan $ok
  $bad=@(
    @('-start','HeapSession','-heap','-PidNewProcess','sample.exe','-FileMode','Sequential','-stackwalk','HeapAlloc+HeapRealloc'),
    @('-start','HeapSession','-heap','-Pids','1234','-FileMode','Circular','-stackwalk','HeapAlloc+HeapRealloc'),
    @('-start','HeapSession','-heap','-Pids','1234','-FileMode','Sequential'),
    @('-start','HeapSession','-heap','-Pids','1234','-stackwalk','HeapAlloc+HeapRealloc')
  )
  foreach($entry in $bad) {
    $blocked=$false
    try{Check-Plan $entry}catch{$blocked=$true}
    if(-not $blocked){throw 'Unsafe synthetic plan accepted'}
  }
  Write-Host 'C545D_REALLOC_SYNTHETIC_CONTROLLER_SELFTEST_PASS,positive=1,negative=4,CI_only=1,host_untouched=1'
  return
}
if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows'){
  throw 'Only isolated disposable Windows GitHub Actions accepted'
}
$xperf=$null
foreach($parent in @([Environment]::GetEnvironmentVariable('ProgramFiles(x86)'),$env:ProgramFiles)){
  if($parent){
    $candidate=Join-Path $parent 'Windows Kits\10\Windows Performance Toolkit\xperf.exe'
    if(Test-Path $candidate -PathType Leaf){$xperf=$candidate;break}
  }
}
if(-not $xperf){throw 'Official WPT Xperf not found; do not guess tool'}
$root=Join-Path $env:RUNNER_TEMP ('c545d_realloc_ci_'+[guid]::NewGuid().ToString('N'))
if(Test-Path $root){throw 'Refuse existing disposable source directory'}
New-Item -Path $root -ItemType Directory | Out-Null
$owned=Join-Path $root 'ci_owned.signal'
New-Item -Path $owned -ItemType File | Out-Null
$exe=Join-Path $root 'c545d_realloc_cal.exe'
$raw=Join-Path $root 'private_tool_output.txt'
$stats=Join-Path $root 'private_logger_status.txt'
$etl=Join-Path $root 'private_heap.etl'
$report=Join-Path $root 'private_stack_report.txt'
$proc=$null;$kernelOn=$false;$heapOn=$false;$complete=$false
$oldRoot=$env:C545D_REALLOC_CAL_ROOT
$oldSymbols=$env:_NT_SYMBOL_PATH

function Signal([string]$name){
  $target=Join-Path $root $name
  if(Test-Path $target){throw 'Stale source signal present'}
  New-Item -ItemType File -Path $target | Out-Null
}
function Wait-Signal([string]$name,[int]$seconds) {
  $target=Join-Path $root $name
  for($i=0;$i -lt ($seconds*10);$i++){
    if(Test-Path $target -PathType Leaf){return}
    if($proc){$proc.Refresh();if($proc.HasExited){throw 'Synthetic process exited before signal'}}
    Start-Sleep -Milliseconds 100
  }
  throw 'Bounded synthetic source handshake not delivered'
}
function Run-Xperf([string]$stage,[string[]]$argsLine) {
  & $xperf @argsLine *> $raw
  if($LASTEXITCODE -ne 0){
    Write-Host "C545D_REALLOC_XPERF_GAP,stage=$stage,reason=LOCAL_ACTION_FAILED,raw_uploaded=0"
    throw 'Isolated Xperf action did not complete'
  }
}

try {
  $existing=@(& logman.exe query -ets 2>$null)
  if($LASTEXITCODE -ne 0){throw 'Could not inspect ETW sessions'}
  if(@($existing | Where-Object {$_ -match '(?i)\bHeapSession\b|\bNT Kernel Logger\b'}).Count){
    throw 'Refuse to modify existing external ETW sessions'
  }
  & cl.exe /nologo /W4 /WX /MT /Od /Zi /TC tests/c545d_etw_realloc_transfer_ci.c "/Fe:$exe" "/Fd:$root\realloc.pdb" /link /DEBUG "/PDB:$root\realloc.pdb" *> $raw
  if($LASTEXITCODE -ne 0 -or -not(Test-Path $exe -PathType Leaf)){
    throw 'Synthetic realloc source compilation failed'
  }
  # Compile the original-address event adapter BEFORE tracing; no CI-build
  # noise enters the tiny known 64/16/48 native heap ETW interval.
  $adapter=Join-Path $root 'C545DEtwHeapIdentity.dll'
  & dotnet build tests/C545DEtwHeapIdentity/C545DEtwHeapIdentity.csproj --configuration Release --output $root --nologo *> $raw
  if($LASTEXITCODE -ne 0 -or -not(Test-Path $adapter -PathType Leaf)){
    Write-Host 'C545D_REALLOC_ETW_IDENTITY_GAP,stage=BUILD,reason=DOTNET_ADAPTER_BUILD_FAILED,raw_uploaded=0'
    throw 'Private source-event adapter compilation did not succeed'
  }
  $env:C545D_REALLOC_CAL_ROOT=$root
  $proc=Start-Process -FilePath $exe -WorkingDirectory $root -PassThru
  Wait-Signal 'ready.signal' 30
  Write-Host 'C545D_REALLOC_WINDOW_STAGE,synthetic_ready=1,heap_calls_started=0,real_host=0'
  Run-Xperf 'kernel' @('-on','BASE')
  $kernelOn=$true
  $args=@('-start','HeapSession','-heap','-Pids',"$($proc.Id)",
     '-BufferSize','1024','-MinBuffers','64','-MaxBuffers','64',
     '-FileMode','Sequential','-MaxFile','128','-stackwalk','HeapAlloc+HeapRealloc')
  Check-Plan $args
  Run-Xperf 'source_trace' $args
  $heapOn=$true
  Signal 'go.signal'
  Wait-Signal 'finished.signal' 30
  Write-Host 'C545D_REALLOC_WINDOW_STAGE,known_alloc=64,known_realloc=16,known_free=48,held=16'
  & $xperf -loggers *> $stats
  if($LASTEXITCODE -ne 0){throw 'ETW logger integrity unavailable'}
  $statString=[IO.File]::ReadAllText($stats)
  $start=[regex]::Match($statString,'(?im)^\s*Logger Name\s*:\s*HeapSession\s*$')
  if(-not $start.Success){throw 'HeapSession missing at stop'}
  $from=$start.Index+$start.Length
  $next=[regex]::Match($statString.Substring($from),'(?im)^\s*Logger Name\s*:')
  $until=if($next.Success){$from+$next.Index}else{$statString.Length}
  $heapSection=$statString.Substring($from,$until-$from)
  $events=[regex]::Match($heapSection,'(?im)^\s*Events Lost\s*:\s*(\d+)\s*$')
  $buffers=[regex]::Match($heapSection,'(?im)^\s*Log Buffers Lost\s*:\s*(\d+)\s*$')
  if(-not $events.Success -or -not $buffers.Success){throw 'Heap logger zero-loss status unparseable'}
  if([int]$events.Groups[1].Value -ne 0 -or [int]$buffers.Groups[1].Value -ne 0){
    throw 'Heap event/log buffers lost: attribution forbidden'
  }
  Run-Xperf 'stop_merge' @('-stop','-stop','HeapSession','-d',$etl)
  $heapOn=$false;$kernelOn=$false
  if(-not(Test-Path $etl -PathType Leaf) -or (Get-Item $etl).Length -gt 128MB){
    throw 'Local ETW trace absent or excessive'
  }
  $env:_NT_SYMBOL_PATH="$root;srv*$(Join-Path $root 'private_symbols')*https://msdl.microsoft.com/download/symbols"
  Run-Xperf 'stacks' @('-i',$etl,'-o',$report,'-symbols','-a','heap','-stacks','-top','4096')
  if(-not(Test-Path $report -PathType Leaf) -or (Get-Item $report).Length -gt 2MB){
    throw 'Local synthetic stack report missing or excessive'
  }
  $evidence=@(& py tests/analyze_c545d_etw_realloc_transfer_ci.py --report $report 2> $raw)
  $pass=@($evidence | Where-Object {$_ -match '^C545D_ETW_REALLOC_STACK_GROUP_DIAGNOSTIC,[A-Za-z0-9_,=.-]+$'})
  if($LASTEXITCODE -ne 0 -or $pass.Count -ne 1){
    $diagnostic=@(& py tests/analyze_c545d_etw_realloc_transfer_ci.py --report $report --diagnose 2> $raw)
    $safe=@($diagnostic | Where-Object {$_ -match '^C545D_ETW_REALLOC_STACK_PARSE_DIAGNOSTIC,[A-Za-z0-9_,=.-]+$'})
    if($LASTEXITCODE -eq 0 -and $safe.Count -eq 1){Write-Host $safe[0]}
    Write-Host 'C545D_REALLOC_XPERF_GAP,stage=source_stack,reason=SOURCE_METRIC_NOT_VERIFIED,raw_uploaded=0'
    throw 'Cannot infer realloc group behavior from report'
  }
  Write-Host $pass[0]
  $bounds=@(& py tests/analyze_c545d_etw_stack_coverage_bounds_ci.py --report $report --arm registry --requested-top 4096 2> $raw)
  $allow=@($bounds | Where-Object {$_ -match '^C545D_GIO_ETW_STACK_COVERAGE_BOUNDS,[A-Za-z0-9_,=.-]+$'})
  if($LASTEXITCODE -eq 0 -and $allow.Count -eq 1){
    Write-Host $allow[0]
  } else {
    Write-Host 'C545D_REALLOC_STACK_BOUNDS_GAP,reason=UNVERIFIED_REPORT_NUMBERS,raw_uploaded=0'
  }
  # Parse the SAME local ETL before the 16 intentionally held blocks are
  # freed. Do not export the ETL, payload pointers, stack names or PID.
  # This is a distinct real-event validation, not another GIO measurement.
  $identities=@(& dotnet $adapter --etl $etl --pid "$($proc.Id)" --preworkload-and-losszero-verified 2> $raw)
  $identityStatus=$LASTEXITCODE
  $safeIdentity=@($identities | Where-Object {
    $_ -match '^C545D_ETW_REALLOC_IDENTITY_MATCHED,[A-Za-z0-9_,=.-]+$'
  })
  if($identityStatus -ne 0 -or $safeIdentity.Count -ne 1){
    $gap=@($identities | Where-Object {
      $_ -match '^C545D_ETW_REALLOC_IDENTITY_GAP,reason=[A-Za-z0-9_]+(?:,[a-zA-Z0-9_]+=-?[0-9]+)*,raw_uploaded=0,release_HOLD=1$'
    })
    if($gap.Count -eq 1){Write-Host $gap[0]}
    else{Write-Host 'C545D_ETW_REALLOC_IDENTITY_GAP,reason=unverified_adapter_output,raw_uploaded=0,release_HOLD=1'}
    throw 'Real ETW old-new identity unverified: synthetic source still safe'
  }
  Write-Host $safeIdentity[0]
  Signal 'exit.signal'
  if(-not $proc.WaitForExit(10000) -or $proc.ExitCode -ne 0){
    throw 'Synthetic realloc process did not exit normally'
  }
  $complete=$true
  Write-Host 'C545D_REALLOC_SYNTHETIC_ETW_COMPLETE,known_alloc=64,known_realloc=16,known_free=48,known_held=16,logger_loss_zero=1,source_owner_not_real_GIO=1,raw_uploaded=0,host_untouched=1'
} finally {
  if($heapOn){& $xperf -stop HeapSession *> $raw}
  if($kernelOn){& $xperf -stop *> $raw}
  if($proc){
    try{
      $proc.Refresh()
      if(-not $proc.HasExited){
        if(-not(Test-Path (Join-Path $root 'exit.signal'))){
          New-Item -ItemType File (Join-Path $root 'exit.signal') | Out-Null
        }
        if(-not $proc.WaitForExit(4000)){Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue}
      }
    }catch{}
  }
  if($null -eq $oldRoot){Remove-Item Env:C545D_REALLOC_CAL_ROOT -ErrorAction SilentlyContinue}
  else{$env:C545D_REALLOC_CAL_ROOT=$oldRoot}
  if($null -eq $oldSymbols){Remove-Item Env:_NT_SYMBOL_PATH -ErrorAction SilentlyContinue}
  else{$env:_NT_SYMBOL_PATH=$oldSymbols}
  if((Test-Path $owned) -and $root.StartsWith($env:RUNNER_TEMP,[StringComparison]::OrdinalIgnoreCase)){
    Remove-Item -Recurse -Force -Path $root -ErrorAction SilentlyContinue
  }
}
if($complete){$global:LASTEXITCODE=0}
