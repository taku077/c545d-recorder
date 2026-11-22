# Synthetic, CI-owned, per-PID heap ETW capability only.
# No IFEO changes or use of recording PC/process. Raw ETL and stacks are
# NEVER uploaded, printed, or persisted outside the disposable Windows runner.
param([switch]$SelfTest)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'

function Assert-PidOnly([string[]]$ArgsList) {
  $a=$ArgsList -join ' '
  if($a -match '(?i)PidNewProcess|HeapTracingConfig|TracingFlags|gflags|[+-]ust|Image File Execution Options') {
    throw 'Unsafe registry/UST operation requested'
  }
  if($a -notmatch '(?i)-Pids?\s+[0-9]+' -or $a -notmatch 'HeapAlloc\+HeapRealloc') {
    throw 'Trace missing explicit process PID or heap stackwalk'
  }
}
if($SelfTest) {
  Assert-PidOnly -ArgsList @('-start','HeapSession','-heap','-Pid','1234','-stackwalk','HeapAlloc+HeapRealloc')
  $bad=@(
    @('-start','HeapSession','-heap','-PidNewProcess','foo.exe','-stackwalk','HeapAlloc+HeapRealloc'),
    @('-start','HeapSession','-heap','-Pid','123','TracingFlags','-stackwalk','HeapAlloc+HeapRealloc'),
    @('-start','HeapSession','-heap','-Pid','123'),
    @('-start','HeapSession','-heap','-stackwalk','HeapAlloc+HeapRealloc'),
    @('-start','HeapSession','-heap','-Pid','123','-stackwalk','HeapAlloc'))
  foreach($case in $bad) {
    $rejected=$false
    try { Assert-PidOnly -ArgsList $case } catch { $rejected=$true }
    if(-not $rejected){throw 'Unsafe trace fixture accepted'}
  }
  Write-Host 'C545D_ETW_PID_SYNTHETIC_SELFTEST_PASS,negatives=5,positives=1,host_modified=0'
  return
}
$tool=$null
foreach($root in @([Environment]::GetEnvironmentVariable('ProgramFiles(x86)'),$env:ProgramFiles)) {
  if($root) {
    $candidate=Join-Path $root 'Windows Kits\10\Windows Performance Toolkit\xperf.exe'
    if(Test-Path $candidate -PathType Leaf){$tool=$candidate;break}
  }
}
if(-not $tool) {
  $cmd=Get-Command 'xperf.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
  if($cmd){$tool=$cmd.Source}
}
if(-not $tool) {
  Write-Host 'C545D_ETW_PID_CAPABILITY,xperf_found=0,reason=XPERF_NOT_INSTALLED,trace_attempted=0,raw_uploaded=0'
  Write-Host 'C545D_ETW_PID_PREFLIGHT_PASS,capability_confirmed=0,host_untouched=1'
  return
}
$exeName='c545d_umdh_stack_preflight.exe'
$ifeo='HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\'+$exeName
if(Test-Path $ifeo){throw 'Preexisting IFEO for synthetic image; refuse trace'}
$root=Join-Path $env:RUNNER_TEMP ('c545d_etw_pid_'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root -Force | Out-Null
$exe=Join-Path $root $exeName
$local=Join-Path $root 'local_output_suppressed.txt'
$etl=Join-Path $root 'synthetic_local_only.etl'
$proc=$null
$kernelStarted=$false
$heapStarted=$false
$ok=$false
function Wait-Flag([string]$name){
  for($i=0;$i -lt 120;$i++){
    if(Test-Path (Join-Path $root $name) -PathType Leaf){return}
    Start-Sleep -Milliseconds 100
  }
  throw 'Synthetic ETW handshake timed out'
}
function Call-Xperf([string]$Phase,[string[]]$ArgsList) {
  & $tool @ArgsList *> $local
  if($LASTEXITCODE -ne 0){
    $reason='OTHER'
    $message=Get-Content $local -Raw -ErrorAction SilentlyContinue
    if($message -match '(?i)access.denied|privilege|elevation|administrator'){$reason='PRIVILEGE'}
    elseif($message -match '(?i)already.exists|in.use|already.running|duplicate'){$reason='SESSION_COLLISION'}
    elseif($message -match '(?i)invalid|incorrect|unknown|syntax|usage:'){$reason='COMMAND_UNSUPPORTED'}
    elseif($message -match '(?i)buffer|memory'){$reason='BUFFER_LIMIT'}
    elseif($message -match '(?i)start|service|provider'){$reason='PROVIDER_OR_START'}
    $words=@('pid','pids','process','heap','heapalloc','stackwalk','buffer','session','logger','start','enable','event','supported','unknown','failed','trace','etw')
    $seen=@($words | Where-Object { $message -match "(?i)\\b$([regex]::Escape($_))\\b" })
    $codeMatch=[regex]::Match($message,'(?i)(?<![0-9a-f])0x[0-9a-f]{8}(?![0-9a-f])')
    $statusCode=if($codeMatch.Success){$codeMatch.Value.ToUpperInvariant()}else{'NONE'}
    Write-Host "C545D_ETW_FAILURE_FINGERPRINT,phase=$Phase,code=$statusCode,word_families=$($seen -join ';'),raw_uploaded=0"
    throw "C545D_ETW_PHASE_FAILED,phase=$Phase,reason=$reason,raw_uploaded=0"
  }
}
try {
  & cl.exe /nologo /W4 /WX /MT /O2 /TC tests/c545d_umdh_stack_preflight.c "/Fe:$exe" *> $local
  if($LASTEXITCODE -ne 0){throw 'Synthetic target compile error; local diagnostics suppressed'}
  $sessions=@(& logman.exe query -ets 2>$null)
  if($LASTEXITCODE -ne 0){throw 'Cannot inspect ETW sessions'}
  if(@($sessions | Where-Object {$_ -match '(?i)\bHeapSession\b|\bNT Kernel Logger\b'}).Count -gt 0){
    Write-Host 'C545D_ETW_PID_CAPABILITY,xperf_found=1,trace_attempted=0,reason=EXISTING_LOGGER,raw_uploaded=0'
    Write-Host 'C545D_ETW_PID_PREFLIGHT_PASS,capability_confirmed=0,host_untouched=1'
    return
  }
  $proc=Start-Process -FilePath $exe -WorkingDirectory $root -PassThru
  Wait-Flag 'ready.signal'
  $etwArgs=@('-start','HeapSession','-heap','-pids',"$($proc.Id)",'-BufferSize','1024','-MinBuffers','128','-MaxBuffers','128','-stackwalk','HeapAlloc+HeapRealloc')
  Assert-PidOnly -ArgsList $etwArgs
  Call-Xperf -Phase 'kernel' -ArgsList @('-on','BASE')
  $kernelStarted=$true
  Call-Xperf -Phase 'heap' -ArgsList $etwArgs
  $heapStarted=$true
  New-Item -ItemType File -Path (Join-Path $root 'allocate.signal') -Force | Out-Null
  Wait-Flag 'allocated.signal'
  Start-Sleep -Milliseconds 300
  # Use documented -stop -stop HeapSession -d sequence to merge ETL.
  Call-Xperf -Phase 'merge' -ArgsList @('-stop','-stop','HeapSession','-d',$etl)
  $heapStarted=$false
  $kernelStarted=$false
  if(-not(Test-Path $etl -PathType Leaf)){throw 'No local ETL written'}
  $size=(Get-Item $etl).Length
  if($size -lt 512 -or $size -gt 100MB){throw 'ETL size outside bounded test range'}
  $heapReport=Join-Path $root 'heap_action_local_only.txt'
  $stackReport=Join-Path $root 'stack_action_local_only.txt'
  # Microsoft: xperf -i trace.etl -o output.txt -a heap [-stacks -top 25].
  # Never expose either report or use them for source attribution on their own.
  & $tool -i $etl -o $heapReport -a heap *> $local
  $heapActionCode=$LASTEXITCODE
  $heapActionOk=[int]($heapActionCode -eq 0 -and
                     (Test-Path $heapReport -PathType Leaf) -and
                     (Get-Item $heapReport -ErrorAction SilentlyContinue).Length -gt 0)
  $stackActionOk=0
  if($heapActionOk -eq 1){
    # Follow Microsoft's documented -symbols -a heap -stacks order.
    # Cache public Windows symbols only under a disposable CI directory.
    $priorSymbolPath=$env:_NT_SYMBOL_PATH
    try {
      $env:_NT_SYMBOL_PATH='srv*'+(Join-Path $root 'symbol_cache_local_only')+'*https://msdl.microsoft.com/download/symbols'
      & $tool -i $etl -o $stackReport -symbols -a heap -stacks -top 25 *> $local
    } finally {
      if($null -eq $priorSymbolPath){Remove-Item Env:_NT_SYMBOL_PATH -ErrorAction SilentlyContinue}
      else{$env:_NT_SYMBOL_PATH=$priorSymbolPath}
    }
    $stackActionOk=[int]($LASTEXITCODE -eq 0 -and
                        (Test-Path $stackReport -PathType Leaf) -and
                        (Get-Item $stackReport -ErrorAction SilentlyContinue).Length -gt 0)
  }
  if($heapActionOk -ne 1){
    throw 'Synthetic xperf ETL was generated but offline heap action did not complete'
  }
  $safeStackClassified=0
  if($stackActionOk -eq 1) {
    # Parser has NO passthrough of paths/symbols/addresses. Only aggregate
    # known module-family counts; never publish raw stack report.
    $safeRows=@(& py tests/analyze_c545d_etw_stack_safe.py --source $stackReport)
    $safeExit=$LASTEXITCODE
    $safeLine=@($safeRows | Where-Object { $_ -match '^C545D_ETW_STACK_SAFE_SUMMARY,[A-Za-z0-9_,=]+
} finally {
  if($heapStarted){& $tool -stop HeapSession *> $local}
  if($kernelStarted){& $tool -stop *> $local}
  if($proc){
    New-Item -ItemType File -Path (Join-Path $root 'exit.signal') -Force | Out-Null
    if(-not $proc.WaitForExit(1500)){Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue}
  }
  if(Test-Path $ifeo){throw 'Unexpected synthetic IFEO persisted'}
  Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
}
if($ok){
  Write-Host 'C545D_ETW_PID_PREFLIGHT_PASS,capability_confirmed=1,real_GIO_tested=0,host_untouched=1'
  # An OPTIONAL stack-action return code is not an error in the already
  # verified ETL capture and heap-summary parse. Do not inherit it.
  $global:LASTEXITCODE=0
}
 })
    $safePass=@($safeRows | Where-Object { $_ -eq 'C545D_ETW_STACK_SANITIZER_PASS,module_only=1,source_owner_proven=0,real_recorder_untouched=1' })
    if($safeExit -eq 0 -and $safeLine.Count -eq 1 -and $safePass.Count -eq 1) {
      Write-Host $safeLine[0]
      Write-Host $safePass[0]
      $safeStackClassified=1
    }
  }
  if($safeStackClassified -ne 1) {
    throw 'Synthetic xperf stack file not safely classifiable; attribution gate closed'
  }
  $ok=$true
  Write-Host "C545D_ETW_PID_CAPABILITY,xperf_found=1,trace_attempted=1,local_etl_bytes=$size,synthetic_heap_allocations=64,heap_action_parsed=$heapActionOk,stack_action_parsed=$stackActionOk,stack_report_sanitized=$safeStackClassified,raw_uploaded=0,stack_owner_proven=0,ifeo_changed=0"
} finally {
  if($heapStarted){& $tool -stop HeapSession *> $local}
  if($kernelStarted){& $tool -stop *> $local}
  if($proc){
    New-Item -ItemType File -Path (Join-Path $root 'exit.signal') -Force | Out-Null
    if(-not $proc.WaitForExit(1500)){Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue}
  }
  if(Test-Path $ifeo){throw 'Unexpected synthetic IFEO persisted'}
  Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
}
if($ok){
  Write-Host 'C545D_ETW_PID_PREFLIGHT_PASS,capability_confirmed=1,real_GIO_tested=0,host_untouched=1'
  # An OPTIONAL stack-action return code is not an error in the already
  # verified ETL capture and heap-summary parse. Do not inherit it.
  $global:LASTEXITCODE=0
}
