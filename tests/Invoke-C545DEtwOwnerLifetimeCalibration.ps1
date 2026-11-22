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
  & cl.exe /nologo /W4 /WX /MT /Zi /TC tests/c545d_etw_owner_lifetime_calibration.c "/Fe:$exe" "/Fd:$root\\c545d_owner_cal.pdb" /link /DEBUG "/PDB:$root\\c545d_owner_cal.pdb" *> $raw
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
  if($statChecked -ne 1 -or $lostChecked -ne 1){
    throw 'Missing strict ETW event and log-buffer zero-loss evidence'
  }
  Check-Xperf 'merge' @('-stop','-stop','HeapSession','-d',$etl)
  $heapStarted=$false;$kernelStarted=$false
  if(-not(Test-Path $etl) -or (Get-Item $etl).Length -lt 512 -or
     (Get-Item $etl).Length -gt 128MB){throw 'Missing, empty or excessive private ETL'}
  Check-Xperf 'totals' @('-i',$etl,'-o',$totals,'-a','heap','-totals')
  if(-not(Test-Path $totals) -or (Get-Item $totals).Length -lt 40){
    throw 'Whole-interval heap totals action output missing'
  }
  # Read-only local filtered report. The parser prints ONLY validated numeric
  # aggregates, never a heap address, process name, symbol, or raw report row.
  $filteredTotals=Join-Path $root 'filtered_size360_totals_local_only.txt'
  Check-Xperf 'filtered_totals' @('-i',$etl,'-o',$filteredTotals,
                                 '-a','heap','-totals','-size','360','361')
  if(-not(Test-Path $filteredTotals) -or (Get-Item $filteredTotals).Length -lt 40){
    throw 'No filtered Xperf totals output'
  }
  $numerics=@(& py tests/analyze_c545d_xperf_size360_totals_calibration.py --report $filteredTotals)
  if($LASTEXITCODE -ne 0 -or
     @($numerics | Where-Object {$_ -match '^C545D_XPERF_360_TOTALS_CALIBRATION_PASS,[A-Za-z0-9_,=]+$'}).Count -ne 1){
    throw 'Xperf filtered outstanding count not independently confirmed'
  }
  Write-Host $numerics[0]
  # A unique non-inlined, local-PDB synthetic allocator is required to
  # separate 64 fixture allocations from the 20 additional process
  # allocations observed by prior Xperf in the same 360 B size bucket.
  # Failure is explicitly an attribution gap; NEVER publish the raw stack.
  $ownerTotals=Join-Path $root 'owner_size360_totals_local_only.txt'
  $ownerVerified=0;$ownerReason='NONE'
  $priorOwnerSymbolPath=$env:_NT_SYMBOL_PATH
  try {
    $env:_NT_SYMBOL_PATH="$root;srv*$(Join-Path $root 'ms_symbols_local_only')*https://msdl.microsoft.com/download/symbols"
    & $tool -i $etl -o $ownerTotals -symbols -a heap -totals -size 360 361 -requireframes c545d_synthetic_owner_alloc_360 *> $raw
    $ownerExit=$LASTEXITCODE
  } finally {
    if($null -eq $priorOwnerSymbolPath){Remove-Item Env:_NT_SYMBOL_PATH -ErrorAction SilentlyContinue}
    else{$env:_NT_SYMBOL_PATH=$priorOwnerSymbolPath}
  }
  if($ownerExit -eq 0 -and (Test-Path $ownerTotals) -and
     (Get-Item $ownerTotals).Length -gt 40){
    # Keep parser stderr private as well: only allowlisted success line
    # or numeric-only discrepancy codes may enter public job log.
    $ownerNumeric=@(& py tests/analyze_c545d_xperf_size360_totals_calibration.py --report $ownerTotals --owner-only 2> $raw)
    if($LASTEXITCODE -eq 0 -and
       @($ownerNumeric | Where-Object {$_ -match '^C545D_XPERF_360_TOTALS_CALIBRATION_PASS,scope=owner,[A-Za-z0-9_,=]+$'}).Count -eq 1) {
      $ownerVerified=1
      Write-Host $ownerNumeric[0]
    } else {$ownerReason='OWNER_STACK_REPORT_NOT_EXACT'}
  } else {$ownerReason='OWNER_STACK_FILTER_UNAVAILABLE'}
  if($ownerVerified -ne 1){
    # Only diagnostic enum/counts may escape; raw report, symbol table,
    # addresses, locations and Python tracebacks stay runner-local.
    $localError=Get-Content $raw -Raw -ErrorAction SilentlyContinue
    if($localError -match 'ValueError: calibration_mismatch,observed_alloc=(\d+),observed_outstanding=(\d+)'){
      Write-Host "C545D_OWNER_CAL_FILTER_NUMERIC,observed_alloc=$($Matches[1]),observed_out=$($Matches[2]),source_filter_unverified=1,raw_uploaded=0"
    } elseif($localError -match 'ValueError: owner_specific_calibration_mismatch,observed_alloc=(\d+),observed_realloc=(\d+)'){
      Write-Host "C545D_OWNER_CAL_FILTER_NUMERIC,observed_alloc=$($Matches[1]),observed_realloc=$($Matches[2]),source_filter_unverified=1,raw_uploaded=0"
    }
    $ownerStackVisible=0
    if((Test-Path $sizes) -and
       (Select-String -Path $sizes -SimpleMatch 'c545d_synthetic_owner_alloc_360' -Quiet)){
      $ownerStackVisible=1
    }
    $imageVisible=[int]((Test-Path $sizes) -and
      [bool](Select-String -Path $sizes -SimpleMatch 'c545d_owner_life_cal' -Quiet))
    $wmainVisible=[int]((Test-Path $sizes) -and
      [bool](Select-String -Path $sizes -SimpleMatch 'wmain' -Quiet))
    $ntdllVisible=[int]((Test-Path $sizes) -and
      [bool](Select-String -Path $sizes -SimpleMatch 'ntdll' -Quiet))
    $pdbVisible=[int](Test-Path (Join-Path $root 'c545d_owner_cal.pdb'))
    # Determine whether the 'top' stack section contains actual frames
    # rather than only aggregate GLOBAL ALLOCATIONS counters; all probing
    # stays in the disposable CI directory and prints only safe booleans.
    $safeSizes=[string]((Get-Content $sizes -Raw -ErrorAction SilentlyContinue) -join "`n")
    $stackGlobal=0;$stackTop=0;$filteredExclam=0
    if($safeSizes -match '(?i)GLOBAL\s+ALLOCATIONS'){$stackGlobal=1}
    if($safeSizes -match '(?i)TOP\s+100\s*:'){$stackTop=1}
    if($safeSizes -match '[A-Za-z0-9_.]+![A-Za-z0-9_?@]+'){$filteredExclam=1}
    Write-Host "C545D_OWNER_CAL_STACK_CAPABILITY,local_pdb_exists=$pdbVisible,synthetic_image_present=$imageVisible,synthetic_wmain_present=$wmainVisible,synthetic_allocator_present=$ownerStackVisible,ntdll_present=$ntdllVisible,global_section_present=$stackGlobal,top100_section_present=$stackTop,symbol_frame_pattern_present=$filteredExclam,raw_symbol_names_uploaded=0"
    $unfilteredStacks=Join-Path $root 'all_stack_heads_local_only.txt'
    $unfilteredAction=0
    $priorFullSymbolPath=$env:_NT_SYMBOL_PATH
    try {
      $env:_NT_SYMBOL_PATH="$root;srv*$(Join-Path $root 'ms_symbols_local_only')*https://msdl.microsoft.com/download/symbols"
      & $tool -i $etl -o $unfilteredStacks -symbols -a heap -stacks -top 100 *> $raw
      if($LASTEXITCODE -eq 0 -and (Test-Path $unfilteredStacks) -and
         (Get-Item $unfilteredStacks).Length -gt 40){$unfilteredAction=1}
    } finally {
      if($null -eq $priorFullSymbolPath){Remove-Item Env:_NT_SYMBOL_PATH -ErrorAction SilentlyContinue}
      else{$env:_NT_SYMBOL_PATH=$priorFullSymbolPath}
    }
    $fullKnown=0;$fullFrame=0;$fullGlobal=0
    if($unfilteredAction -eq 1){
      $fullReport=[string]((Get-Content $unfilteredStacks -Raw) -join "`n")
      if($fullReport -match 'c545d_synthetic_owner_alloc_360'){$fullKnown=1}
      if($fullReport -match '[A-Za-z0-9_.]+![A-Za-z0-9_?@]+'){$fullFrame=1}
      if($fullReport -match '(?i)GLOBAL\s+ALLOCATIONS'){$fullGlobal=1}
    }
    Write-Host "C545D_OWNER_CAL_FULL_STACK_CAPABILITY,action=$unfilteredAction,synthetic_allocator_present=$fullKnown,any_symbol_frame_pattern=$fullFrame,global_section_present=$fullGlobal,raw_uploaded=0"
    if($fullKnown -eq 1){
      $ownerStackRows=@(& py tests/analyze_c545d_xperf_owner_stack_calibration.py --report $unfilteredStacks 2> $raw)
      $ownerPass=@($ownerStackRows | Where-Object { $_ -like 'C545D_XPERF_OWNER_STACK_CALIBRATION_PASS,*' })
      if($LASTEXITCODE -eq 0 -and $ownerPass.Count -eq 1){
        $ownerVerified=1
        Write-Host $ownerPass[0]
      } else {
        $ownerPrivateError=Get-Content $raw -Raw -ErrorAction SilentlyContinue
        if($ownerPrivateError -match 'owner_stack_calibration_mismatch,observed_alloc=(\d+),observed_outstanding=(\d+),owner_stack_groups=(\d+)'){
          Write-Host "C545D_OWNER_CAL_UNFILTERED_STACK_NUMERIC_GAP,alloc=$($Matches[1]),out=$($Matches[2]),groups=$($Matches[3]),raw_uploaded=0"
        } else {
          Write-Host 'C545D_OWNER_CAL_UNFILTERED_STACK_SCHEMA_GAP,raw_uploaded=0'
        }
      }
    }
    if($ownerVerified -ne 1){
      Write-Host "C545D_OWNER_CAL_OWNER_ATTRIBUTION_GAP,reason=$ownerReason,synthetic_symbol_visible_in_filtered_stacks=$ownerStackVisible,raw_uploaded=0"
    }
  }
  # Symbol/filter options are an INDEPENDENT capability, not the ETW
  # capture itself. A failure remains explicitly incomplete evidence.
  # It must NEVER be mistaken for source attribution or leak absence.
  $filterOk=0;$filterReason='NONE'
  $priorSymbolPath=$env:_NT_SYMBOL_PATH
  try {
    $env:_NT_SYMBOL_PATH="$root;srv*$(Join-Path $root 'ms_symbols_local_only')*https://msdl.microsoft.com/download/symbols"
    & $tool -i $etl -o $sizes -symbols -a heap -stacks -size 360 361 -top 100 *> $raw
    $filteredExit=$LASTEXITCODE
  } finally {
    if($null -eq $priorSymbolPath){Remove-Item Env:_NT_SYMBOL_PATH -ErrorAction SilentlyContinue}
    else{$env:_NT_SYMBOL_PATH=$priorSymbolPath}
  }
  if($filteredExit -eq 0 -and (Test-Path $sizes) -and
     (Get-Item $sizes).Length -gt 40) {
    $filterOk=1
  } else {
    $privateMessage=Get-Content $raw -Raw -ErrorAction SilentlyContinue
    $filterReason='OTHER_UNCLASSIFIED'
    if($privateMessage -match '(?i)symbol|pdb|dbghelp'){$filterReason='MISSING_SYMBOL_CONTEXT'}
    elseif($privateMessage -match '(?i)invalid|option|parameter|syntax|size|usage'){$filterReason='FILTER_SYNTAX_OR_VERSION'}
    elseif($privateMessage -match '(?i)insufficient|memory|buffer'){$filterReason='FILTER_RESOURCE_ERROR'}
    Write-Host "C545D_OWNER_CAL_FILTER_CAPABILITY,available=0,reason=$filterReason,not_memleak_result=1,raw_uploaded=0"
  }
  # The ETL and raw outputs never leave the runner. The first verified
  # capability is a complete controlled WORKLOAD window and heap totals
  # report, NOT a verified exact-16 ETW outstanding count. Missing stack
  # filter or lost-event statistics are a recorded blocker.
  $traceOk=$true
  Write-Host "C545D_OWNER_CAL_ETW_PREFLIGHT_PASS,known_alloc=64,known_free=48,known_outstanding=16,size=360,prelaunch=0,preworkload_trace=1,sequential=1,circular=0,totals_action=1,size_filtered_action=$filterOk,logger_stats_parsed=$statChecked,logger_loss_zero_checked=$lostChecked,exact_outstanding_from_etw_proven=1,synthetic_owner_verified=$ownerVerified,real_GIO_allocation_owner_proven=0,source_GIO=0,raw_uploaded=0,host_untouched=1"
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
if($traceOk){
  if($ownerVerified -ne 1){
    Write-Host 'C545D_OWNER_CAL_GATE_BLOCKED,reason=SOURCE_STACK_NOT_VERIFIED,classification_ready=0'
    throw 'Cannot complete source attribution calibration without exact 64/16 stack proof'
  }
  $global:LASTEXITCODE=0
}
