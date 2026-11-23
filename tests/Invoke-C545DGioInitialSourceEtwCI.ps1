# CI-only before-first-AppInfo to settled cleanup, exactly one cycle/arm; never on recording PC.
# Only existing disposable probe produced by pinned source GLib 2.82.4 build.
# No IFEO/GFlags/UST or real recording process, no raw ETL/paths/stacks upload.
param(
  [Parameter(Mandatory)][string]$Probe,
  [Parameter(Mandatory)][string]$Root,
  [Parameter(Mandatory)][string]$Build,
  [Parameter(Mandatory)][ValidateSet('nochange','registry')][string]$Arm
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows'){
  throw 'CI-only isolated Windows run required'
}
if(([IO.Path]::GetFileName($Probe)) -ne 'c545d_gio_preinit_probe.exe'){
  throw 'Refusing non-disposable probe'
}
if(-not(Test-Path $Build -PathType Container) -or -not(
  [IO.Path]::GetFullPath($Build).StartsWith(
    [IO.Path]::GetFullPath($env:RUNNER_TEMP)+[IO.Path]::DirectorySeparatorChar,
    [StringComparison]::OrdinalIgnoreCase))){
  throw 'Compiled GIO/PDB source build root is not runner-private'
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
$args=@('--cycles=1','--heap-summary','--vm-summary')
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
  Wait-Signal 'preinit_ready.signal' 60
  Write-Host "C545D_GIO_ETW_WINDOW_STAGE,arm=$Arm,before_first_AppInfo_call=1,workload_started=0"
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
  Wait-Signal 'postsettle_ready.signal' 90
  Write-Host "C545D_GIO_ETW_WINDOW_STAGE,arm=$Arm,total_cycles=1,before_first_AppInfo=1,after_settled_cleanup=1,process_alive_at_stop=1"
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
     -not([IO.File]::ReadAllText($out).Contains('GIO_PROBE_DONE,cycles=1,'))){
    throw 'Missing disposable one-cycle completion'
  }
  if(-not(Test-Path $etl -PathType Leaf) -or (Get-Item $etl).Length -lt 512 -or
     (Get-Item $etl).Length -gt 256MB){
    throw 'ETW local file empty or exceeds bounded capacity'
  }
  # Use the SAME private ETL and independently validated private GIO DLL
  # PDB with matching CodeView GUID+age; this is not a zero-leak verdict.
  $source=@(& dotnet run --no-build --project tests/C545DGioEtlxOwnerCensus/C545DGioEtlxOwnerCensus.csproj --configuration Release -- --etl $etl --pid "$($proc.Id)" --build $Build --arm $Arm --preinit-losszero-and-pdb-match-verified 2> $rawLocal)
  $exitCode=$LASTEXITCODE
  $safeCensus=@($source | Where-Object {
    $_ -match ('^C545D_GIO_ETLX_FIRST_SOURCE_CENSUS,arm='+$Arm+',[A-Za-z0-9_,=.-]+$')
  })
  if($safeCensus.Count -eq 1){Write-Host $safeCensus[0]}
  $safePass=@($source | Where-Object {
    $_ -match ('^C545D_GIO_ETLX_FIRST_SOURCE_OWNER_PASS,arm='+$Arm+',[A-Za-z0-9_,=.-]+$')
  })
  if($exitCode -ne 0 -or $safePass.Count -ne 1){
    $gap=@($source | Where-Object {
      $_ -match '^C545D_GIO_ETLX_FIRST_SOURCE_GAP,reason=[A-Za-z0-9_]+,stage=[A-Za-z0-9_]+(?:,[A-Za-z0-9_]+=-?[0-9]+)*,raw_uploaded=0,release_HOLD=1$'
    })
    if($gap.Count -eq 1){Write-Host $gap[0]}
    else{Write-Host "C545D_GIO_PREINIT_SOURCE_GAP,arm=$Arm,reason=ETLX_ORIGIN_UNVERIFIED,raw_uploaded=0"}
    throw 'Actual original GIO source attribution not demonstrated'
  }
  Write-Host $safePass[0]
  # The disposable probe performs equivalent PSAPI+VirtualQuery phases,
  # but positive deltas do NOT imply a leak and cannot be subtracted from
  # selected heap request bytes without accounting for other memory paths.
  $lines=@(Get-Content $out -ErrorAction Stop)
  $private=@{}
  $region=@{}
  $handles=@{}
  foreach($phase in @('preappinfo','baseline','cycle','settled_cleanup')){
    $rows=@($lines | Where-Object {
      $_ -match ('^GIO_PROBE,'+$phase+',\d+,\d+,\d+,\d+$')
    })
    $vm=@($lines | Where-Object {
      $_ -match ('^GIO_VM,'+$phase+',\d+,\d+,\d+,\d+,\d+,0$')
    })
    if($rows.Count -ne 1 -or $vm.Count -ne 1){
      Write-Host "C545D_GIO_PREINIT_RESOURCE_GAP,arm=$Arm,reason=PHASE_METRICS_INCOMPLETE,phase=$phase,raw_uploaded=0"
      throw 'Incomplete phase measurements; release HOLD'
    }
    $r=$rows[0].Split(',')
    $v=$vm[0].Split(',')
    $private[$phase]=[long]$r[5]
    $handles[$phase]=[long]$r[4]
    $region[$phase]=[long]$v[3]
  }
  $pd=$private['settled_cleanup']-$private['preappinfo']
  $rd=$region['settled_cleanup']-$region['preappinfo']
  $hd=$handles['settled_cleanup']-$handles['preappinfo']
  Write-Host "C545D_GIO_PREINIT_RESOURCE_SCOPE,arm=$Arm,private_delta=$pd,region_private_delta=$rd,handles_delta=$hd,scope=preappinfo_to_settled_cleanup,persistent_watches_allowed=1,global_idle_proven=0,leak_proven=0,raw_uploaded=0"
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
