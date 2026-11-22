# CI-only calibration: Xperf PID-only capture BEFORE controlled allocation workload.
# No GIO, no camera, no recorder host, no raw ETL/stack upload.
param([switch]$SelfTest)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'

function Check-Plan([string[]]$argv) {
  $line=$argv -join ' '
  if($line -notmatch '(?i)-Pids?\s+[0-9]+' -or
     $line -notmatch '(?i)-FileMode\s+Sequential' -or
     $line -notmatch 'HeapAlloc\+HeapRealloc' -or
     $line -match '(?i)\bCircular\b|PidNewProcess|gflags|TracingFlags|\bust\b') {
    throw 'Incomplete or unsafe prelaunch ETW plan'
  }
}
if($SelfTest){
  $base=@('-start','HeapSession','-heap','-Pids','1234',
          '-FileMode','Sequential','-stackwalk','HeapAlloc+HeapRealloc')
  Check-Plan $base
  $bad=@(
    @('-start','HeapSession','-heap','-PidNewProcess','ci_only.exe','-FileMode','Sequential','-stackwalk','HeapAlloc+HeapRealloc'),
    @('-start','HeapSession','-heap','-Pids','1234','-FileMode','Circular','-stackwalk','HeapAlloc+HeapRealloc'),
    @('-start','HeapSession','-heap','-Pids','1234','-stackwalk','HeapAlloc+HeapRealloc'),
    @('-start','HeapSession','-heap','-Pids','1234','-FileMode','Sequential'),
    @('-start','HeapSession','-heap','-Pids','1234','-FileMode','Sequential','-stackwalk','HeapAlloc+HeapRealloc','gflags')
  )
  foreach($b in $bad){
    $caught=$false
    try { Check-Plan $b } catch { $caught=$true }
    if(-not $caught){throw 'Unsafe prelaunch plan accepted'}
  }
  Write-Host 'C545D_ETW_OWNER_CAL_STATIC_PASS,negative=5,positive=1,CI_only=1'
  return
}
if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows'){
  throw 'Dedicated Windows Actions-only synthetic calibration'
}
$tool=$null
foreach($parent in @([Environment]::GetEnvironmentVariable('ProgramFiles(x86)'),$env:ProgramFiles)){
  if($parent){
    $candidate=Join-Path $parent 'Windows Kits\10\Windows Performance Toolkit\xperf.exe'
    if(Test-Path $candidate -PathType Leaf){$tool=$candidate;break}
  }
}
if(-not $tool) {
  $cmd=Get-Command 'xperf.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
  if($cmd){$tool=$cmd.Source}
}
if(-not $tool){ throw 'No xperf in isolated Windows runner: capability not verified' }
$root=Join-Path $env:RUNNER_TEMP ('c545d_owner_cal_'+[guid]::NewGuid().ToString('N'))
if(Test-Path $root){throw 'Refuse to overwrite existing fixture'}
New-Item -ItemType Directory -Path $root | Out-Null
$marker=Join-Path $root 'c545d_ci_owned.signal'
New-Item -ItemType File $marker | Out-Null
$exe=Join-Path $root 'c545d_owner_life_cal.exe'
$name='c545d_owner_life_cal'
$ifeo='HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\c545d_owner_life_cal.exe'
$raw=Join-Path $root 'private_output_suppressed.txt'
$etl=Join-Path $root 'heap_owner_local_only.etl'
$totals=Join-Path $root 'heap_totals_local_only.txt'
$sizes=Join-Path $root 'heap_size360_local_only.txt'
$heapStarted=$false
$kernelStarted=$false
$traceOk=$false
$rawStats=Join-Path $root 'logger_local_only.txt'
function Signal([string]$which) {
  $path=Join-Path $root $which
  if(Test-Path $path){throw 'Unexpected stale signal'}
  New-Item -ItemType File $path | Out-Null
}
function Wait-Signal([string]$which) {
  $path=Join-Path $root $which
  for($i=0;$i -lt 200;$i++){
    if(Test-Path $path -PathType Leaf){return}
    Start-Sleep -Milliseconds 100
  }
  Write-Host "C545D_OWNER_CAL_TIMEOUT,signal=$which,real_host=0,raw_uploaded=0"
  throw 'Synthetic calibration stage timeout'
}
function Check-Xperf([string]$phase,[string[]]$arguments){
  & $tool @arguments *> $raw
  if($LASTEXITCODE -ne 0){
    $msg=Get-Content $raw -Raw -ErrorAction SilentlyContinue
    $kind='XPERF_ERROR'
    if($msg -match '(?i)access.denied|administrator|privilege'){$kind='NO_ELEVATION'}
    elseif($msg -match '(?i)invalid|unknown|syntax|usage'){$kind='UNSUPPORTED_SYNTAX'}
    elseif($msg -match '(?i)already|in use|exists'){$kind='SESSION_COLLISION'}
    Write-Host "C545D_OWNER_CAL_FAILURE,stage=$phase,reason=$kind,raw_uploaded=0"
    throw 'xperf source attribution preflight failed'
  }
}
try {
  if(Test-Path $ifeo){throw 'Existing synthetic IFEO policy — refuse changes'}
  if(@(Get-Process -Name $name -ErrorAction SilentlyContinue).Count){throw 'Synthetic EXE name already active'}
  & cl.exe /nologo /W4 /WX /MT /TC tests/c545d_etw_owner_lifetime_calibration.c "/Fe:$exe" *> $raw
  if($LASTEXITCODE -ne 0 -or -not(Test-Path $exe)){throw 'Synthetic known-allocation C compile failed'}
  $existing=@(& logman.exe query -ets 2>$null)
  if($LASTEXITCODE -ne 0 -or @($existing | Where-Object {$_ -match '(?i)\bHeapSession\b|\bNT Kernel Logger\b'}).Count){
    throw 'Refuse existing ETW sessions'
  }
  $env:C545D_OWNER_CAL_ROOT=$root
  $proc=Start-Process -FilePath $exe -WorkingDirectory $root -PassThru
  Wait-Signal 'ready.signal'
  Write-Host 'C545D_OWNER_CAL_STAGE,preworkload_ready=1,known_allocations_started=0'
  Check-Xperf 'kernel' @('-on','BASE')
  $kernelStarted=$true
  $arguments=@('-start','HeapSession','-heap','-Pids',"$($proc.Id)",
               '-BufferSize','1024','-MinBuffers','64','-MaxBuffers','64',
               '-FileMode','Sequential','-MaxFile','64','-stackwalk','HeapAlloc+HeapRealloc')
  Check-Plan $arguments
  Check-Xperf 'preworkload_trace_started' $arguments
  $heapStarted=$true
  Write-Host 'C545D_OWNER_CAL_STAGE,preworkload_trace_started=1,known_allocations_started=0'
  Signal 'allocate.signal'
  Wait-Signal 'allocated.signal'
  Signal 'free.signal'
  Wait-Signal 'freed.signal'
  Write-Host 'C545D_OWNER_CAL_STAGE,alloc64_completed=1,free48_completed=1'
  # Stop before the process releases its known final 16 HeapAlloc blocks.
  # Thus the 16 blocks are outstanding at the ETW interval endpoint.
  # Buffer/EventsLost status is inspected privately and never ignored
  # if it explicitly shows a loss.
  $statChecked=0;$lostChecked=0
  & $tool -loggers *> $rawStats
  if($LASTEXITCODE -eq 0){
    $txt=Get-Content $rawStats -Raw -ErrorAction SilentlyContinue
    if($txt -match '(?im)Logger Name\s*:\s*HeapSession[\s\S]*?Events Lost\s*:\s*(\d+)[\s\S]*?Log Buffers Lost\s*:\s*(\d+)'){
      $statChecked=1
      if([int]$Matches[1] -ne 0 -or [int]$Matches[2] -ne 0){
        throw 'Observed lost ETW heap buffers: classification prohibited'
      }
      $lostChecked=1
    }
  }
  Check-Xperf 'merge' @('-stop','-stop','HeapSession','-d',$etl)
  $heapStarted=$false;$kernelStarted=$false
  if(-not(Test-Path $etl) -or (Get-Item $etl).Length -lt 512 -or
     (Get-Item $etl).Length -gt 128MB){throw 'Missing, empty or excessive private ETL'}
  Check-Xperf 'totals' @('-i',$etl,'-o',$totals,'-a','heap','-totals')
  Check-Xperf 'filtered_outstanding' @('-i',$etl,'-o',$sizes,'-a','heap','-stacks','-size360361','-top','100')
  if(-not(Test-Path $totals) -or -not(Test-Path $sizes) -or
     (Get-Item $totals).Length -lt 40 -or (Get-Item $sizes).Length -lt 40){
    throw 'No heap owner-capable offline action output'
  }
  # The report is not uploaded nor printed. This proves the method can
  # produce whole-trace (totals) and bounded known-size outstanding views,
  # NOT that exact 16 outstanding were attributed by parser or all events
  # were captured. Separate parser and event-loss gates must follow.
  $traceOk=$true
  Write-Host "C545D_OWNER_CAL_ETW_PREFLIGHT_PASS,known_alloc=64,known_free=48,known_outstanding=16,size=360,prelaunch=0,preworkload_trace=1,sequential=1,circular=0,totals_action=1,size_filtered_action=1,logger_stats_parsed=$statChecked,logger_loss_zero_checked=$lostChecked,allocation_owner_proven=0,source_GIO=0,raw_uploaded=0,host_untouched=1"
} finally {
  if($heapStarted){& $tool -stop HeapSession *> $raw}
  if($kernelStarted){& $tool -stop *> $raw}
  if(Test-Path $root){
    if((Test-Path (Join-Path $root 'freed.signal')) -and
       -not (Test-Path (Join-Path $root 'exit.signal'))){
      New-Item -ItemType File -Path (Join-Path $root 'exit.signal') | Out-Null
    }
    Start-Sleep -Milliseconds 500
    foreach($p in @(Get-Process -Name $name -ErrorAction SilentlyContinue)){
      try {
        if($p.Path -eq $exe) {
          if(-not $p.WaitForExit(4000)){Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue}
        }
      } catch {}
    }
    if(Test-Path $ifeo){throw 'Synthetic image IFEO persisted unexpectedly'}
    if((Test-Path $marker) -and $root.StartsWith($env:RUNNER_TEMP,[StringComparison]::OrdinalIgnoreCase)){
      Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}
if($traceOk){$global:LASTEXITCODE=0}
