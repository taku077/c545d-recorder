# CI-only two comparable post-baseline GIO epochs, one continuous ETL per disposable arm; never recorder PC.
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
if(([IO.Path]::GetFileName($Probe)) -ne 'c545d_gio_active_epoch_probe.exe'){
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
$args=@('--cycles=2','--heap-summary','--vm-summary')
if($Arm -eq 'nochange'){$args+='--no-registry-change'}
$local=Join-Path $env:RUNNER_TEMP ("c545d_gio_etw_"+$Arm+"_"+[guid]::NewGuid().ToString('N'))
if(Test-Path $local){throw 'Refuse pre-existing owned ETW local path'}
New-Item -ItemType Directory -Path $local | Out-Null
New-Item -ItemType File -Path (Join-Path $local 'ci_owned.signal') | Out-Null
$rawLocal=Join-Path $local 'xperf_output_private.txt'
$loggers=Join-Path $local 'xperf_status_private.txt'
$etl=Join-Path $local 'heap_private.etl'
$stack=Join-Path $local 'stacks_private.txt'
$out=Join-Path $Root ('active-'+$Arm+'-private.txt')
$err=Join-Path $Root ($Arm+'-error-private.txt')
$proc=$null;$kernelOn=$false;$heapOn=$false;$success=$false
$oldFence=$env:C545D_CI_ETW_PHASE_ROOT
$oldSymbols=$env:_NT_SYMBOL_PATH
$oldTrace=$env:C545D_CI_APPINFO_PHASE_TRACE
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
  $env:C545D_CI_APPINFO_PHASE_TRACE='1'
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
  Write-Host "C545D_GIO_ETW_WINDOW_STAGE,arm=$Arm,total_cycles=2,before_first_AppInfo=1,after_settled_cleanup=1,process_alive_at_stop=1"
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
     -not([IO.File]::ReadAllText($out).Contains('GIO_PROBE_DONE,cycles=2,'))){
    throw 'Missing disposable two-cycle completion'
  }
  if(-not(Test-Path $etl -PathType Leaf) -or (Get-Item $etl).Length -lt 512 -or
     (Get-Item $etl).Length -gt 256MB){
    throw 'ETW local file empty or exceeds bounded capacity'
  }
  # Use the SAME private ETL and independently validated private GIO DLL
  # PDB with matching CodeView GUID+age; this is not a zero-leak verdict.
  # Before the ETLX replay, independently validate process-local numeric
  # CPU, PrivateUsage, VirtualQuery and exact AppInfo worker parity.
  py tests/audit_c545d_gio_active_two_epoch_ci.py --input $out
  if($LASTEXITCODE -ne 0){throw 'Incomplete two-cycle numeric resource phases'}
  py tests/audit_c545d_gio_active_worker_epochs_ci.py --input $out --arm $Arm
  if($LASTEXITCODE -ne 0){throw 'Two active workers not comparable or incomplete'}
  $phaseRows=@(Get-Content $out | Where-Object {
    $_ -match '^C545D_CI_ACTIVE_EPOCH,(baseline|cycle),[0-2],\d+,\d+,\d+$'
  })
  if($phaseRows.Count -ne 3){throw 'Missing exact QPC phase cut triplet'}
  $marks=@{}
  foreach($line in $phaseRows){
    $parts=$line.Split(',')
    $key=$parts[1]+$parts[2]
    if($key -notin @('baseline0','cycle1','cycle2') -or $marks.ContainsKey($key)){
      throw 'Duplicated or unknown active source phase'
    }
    $marks[$key]=[long]$parts[3]
  }
  if($marks.Count -ne 3 -or $marks['baseline0'] -le 0 -or
     $marks['baseline0'] -ge $marks['cycle1'] -or
     $marks['cycle1'] -ge $marks['cycle2']){
    throw 'Source ETW QPC phase cuts not monotonic'
  }
  # The ETW stop handshake happened after settled cleanup. The source is
  # private on this Windows runner, and QPC values are never printed.
  $source=@(& dotnet run --no-build --project tests/C545DGioEtlxOwnerCensus/C545DGioEtlxOwnerCensus.csproj --configuration Release -- --etl $etl --pid "$($proc.Id)" --build $Build --arm $Arm --preinit-losszero-and-pdb-match-verified --qpc-baseline "$($marks['baseline0'])" --qpc-cycle1 "$($marks['cycle1'])" --qpc-cycle2 "$($marks['cycle2'])" 2> $rawLocal)
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
  $names=@('MissingStack','NoGioFrame','GioMethodUnmatched','UpdateRegistryData',
    'KeysUpdated','WatchKeys','AppinfoWorker','RegistryKeyWatch','PackageEnum',
    'AmbiguousMultipleMethods')
  $rows=@($source | Where-Object { $_ -like "C545D_GIO_METHOD_COHORT,arm=$Arm,*" })
  if($rows.Count -ne 10 -or $safeCensus.Count -ne 1){throw 'cohort_row_count_gap'}
  $seen=@{}
  $totalLive=0L;$totalBytes=0L
  $gioAlloc=0L;$gioRealloc=0L;$gioFree=0L
  $pattern='^C545D_GIO_METHOD_COHORT,arm='+[regex]::Escape($Arm)+
    ',category=([A-Za-z]+),original=(\d+),realloc=(\d+),logical_free=(\d+),'+
    'live=(\d+),request_bytes_live=(\d+),'+
    'source_original_stack_only=1,global_leak_proven=0,release_HOLD=1$'
  foreach($row in $rows){
    $m=[regex]::Match($row,$pattern)
    if(-not $m.Success){throw 'invalid_cohort_shape'}
    $name=$m.Groups[1].Value
    if($names -notcontains $name -or $seen.ContainsKey($name)){
      throw 'duplicate_or_unknown_cohort'
    }
    $seen[$name]=1
    $a=[long]$m.Groups[2].Value
    $r=[long]$m.Groups[3].Value
    $f=[long]$m.Groups[4].Value
    $l=[long]$m.Groups[5].Value
    $b=[long]$m.Groups[6].Value
    if($a-$f -ne $l){throw 'cohort_balance_mismatch'}
    $totalLive+=$l;$totalBytes+=$b
    if($name -notin @('MissingStack','NoGioFrame','GioMethodUnmatched')){
      $gioAlloc+=$a;$gioRealloc+=$r;$gioFree+=$f
    }
  }
  if($seen.Count -ne 10){throw 'missing_named_cohort'}
  $summary=@{}
  foreach($item in $safeCensus[0].Split(',') | Select-Object -Skip 1){
    $pair=$item.Split('=',2)
    if($pair.Count -eq 2){$summary[$pair[0]]=$pair[1]}
  }
  if($totalLive -ne [long]$summary['original_allocation_live'] -or
     $totalBytes -ne [long]$summary['request_bytes_live'] -or
     $gioAlloc -ne [long]$summary['gio_source_origin_alloc'] -or
     $gioRealloc -ne [long]$summary['gio_source_origin_realloc'] -or
     $gioFree -ne [long]$summary['gio_source_origin_logical_free']){
    throw 'cohort_census_reconciliation_failed'
  }
  foreach($row in $rows){Write-Host $row}
  Write-Host "C545D_GIO_METHOD_COHORT_ACCOUNTING_PASS,arm=$Arm,cohorts=10,checks=5,release_HOLD=1"
  # The nearest allowlisted method is an ordered-stack PROXY, not proof of
  # the exact allocating function. Preserve independent ambiguous counts.
  $nearRows=@($source | Where-Object {
    $_ -like "C545D_GIO_NEAREST_METHOD_COHORT,arm=$Arm,*"
  })
  if($nearRows.Count -ne 10){throw 'missing_nearest_method_cohorts'}
  $nearSeen=@{}
  $nLive=0L;$nBytes=0L;$nAlloc=0L;$nRealloc=0L;$nFree=0L
  $nearPattern='^C545D_GIO_NEAREST_METHOD_COHORT,arm='+[regex]::Escape($Arm)+
    ',category=([A-Za-z]+),original=(\d+),realloc=(\d+),logical_free=(\d+),'+
    'live=(\d+),request_bytes_live=(\d+),'+
    'nearest_allowlisted_proxy=1,exact_alloc_owner_not_proven=1,release_HOLD=1$'
  foreach($row in $nearRows){
    $m=[regex]::Match($row,$nearPattern)
    if(-not $m.Success){throw 'malformed_nearest_cohort'}
    $name=$m.Groups[1].Value
    if($names -notcontains $name -or $nearSeen.ContainsKey($name)){
      throw 'unknown_or_duplicate_nearest_cohort'
    }
    $nearSeen[$name]=1
    $aa=[long]$m.Groups[2].Value
    $rr=[long]$m.Groups[3].Value
    $ff=[long]$m.Groups[4].Value
    $ll=[long]$m.Groups[5].Value
    $bb=[long]$m.Groups[6].Value
    if($aa-$ff -ne $ll){throw 'nearest_cohort_balance_mismatch'}
    $nLive+=$ll;$nBytes+=$bb
    if($name -notin @('MissingStack','NoGioFrame','GioMethodUnmatched')){
      $nAlloc+=$aa;$nRealloc+=$rr;$nFree+=$ff
    }
  }
  if($nearSeen.Count -ne 10 -or
     $nLive -ne [long]$summary['original_allocation_live'] -or
     $nBytes -ne [long]$summary['request_bytes_live'] -or
     $nAlloc -ne [long]$summary['gio_source_origin_alloc'] -or
     $nRealloc -ne [long]$summary['gio_source_origin_realloc'] -or
     $nFree -ne [long]$summary['gio_source_origin_logical_free']){
    throw 'nearest_cohort_census_reconciliation_failed'
  }
  $nearScope=@($source | Where-Object {
    $_ -match ('^C545D_GIO_NEAREST_FRAME_SCOPE,arm='+$Arm+
      ',raw_first_gio_exact_method=\d+,raw_not_logical_owner_count=1,release_HOLD=1$')
  })
  if($nearScope.Count -ne 1){throw 'nearest_frame_scope_missing'}
  foreach($row in $nearRows){Write-Host $row}
  Write-Host $nearScope[0]
  Write-Host "C545D_GIO_NEAREST_METHOD_ACCOUNTING_PASS,arm=$Arm,cohorts=10,checks=5,exact_owner_not_proven=1,release_HOLD=1"
  # A 3 x 2 x 10 strict named-category ledger is required.
  $epochRows=@($source | Where-Object {
    $_ -like "C545D_GIO_ACTIVE_SOURCE_EPOCH_COHORT,arm=$Arm,*"
  })
  $epochScopes=@($source | Where-Object {
    $_ -like "C545D_GIO_ACTIVE_SOURCE_EPOCH_SCOPE,arm=$Arm,*"
  })
  $epochPass=@($source | Where-Object {
    $_ -eq "C545D_GIO_ACTIVE_SOURCE_EPOCH_ACCOUNTING_PASS,arm=$Arm,phases=3,models=2,categories=10,crosschecked_generic_live_and_bytes=1,crosscut_realloc_guard=1,global_leak_not_proven=1,release_HOLD=1"
  })
  if($epochRows.Count -ne 60 -or $epochScopes.Count -ne 3 -or
     $epochPass.Count -ne 1){
    throw 'Three original-source epoch cohorts incomplete'
  }
  $seenEpochs=@{}
  $pat='^C545D_GIO_ACTIVE_SOURCE_EPOCH_COHORT,arm='+[regex]::Escape($Arm)+
    ',phase=(baseline|cycle1|cycle2),model=(strict|nearest),category=([A-Za-z]+),'+
    'live=\d+,request_bytes_live=\d+,'+
    'source_heap_only=1,direct_allocator_not_proven=1,release_HOLD=1$'
  foreach($line in $epochRows){
    $match=[regex]::Match($line,$pat)
    if(-not $match.Success){throw 'Malformed source phase/category counters'}
    $key=$match.Groups[1].Value+'-'+$match.Groups[2].Value+'-'+$match.Groups[3].Value
    if($names -notcontains $match.Groups[3].Value -or $seenEpochs.ContainsKey($key)){
      throw 'Duplicate or not allowlisted GIO source epoch category'
    }
    $seenEpochs[$key]=1
  }
  if($seenEpochs.Count -ne 60){throw 'Incomplete distinct GIO source epoch category'}
  $scopes=@{}
  foreach($line in $epochScopes){
    $match=[regex]::Match($line,
      ('^C545D_GIO_ACTIVE_SOURCE_EPOCH_SCOPE,arm='+[regex]::Escape($Arm)+
       ',phase=(baseline|cycle1|cycle2),tracked_source_live=\d+,'+
       'tracked_request_bytes_live=\d+,'+
       'comparable_worker_epoch_not_proven_by_etlx=1,release_HOLD=1$'))
    if(-not $match.Success -or $scopes.ContainsKey($match.Groups[1].Value)){
      throw 'Malformed or repeated source epoch reconciliation scope'
    }
    $scopes[$match.Groups[1].Value]=1
  }
  if($scopes.Count -ne 3){throw 'Source epoch scope missing'}
  foreach($line in $epochRows){Write-Host $line}
  foreach($line in $epochScopes){Write-Host $line}
  Write-Host $epochPass[0]
  # Two mechanisms must not be conflated: this is an exact CI-only GIO
  # wrapper frame around IPackage2_get_DisplayName, not a direct proof of
  # WinRT OS allocation ownership or a production-safe fix.
  $getters=@($source | Where-Object {
    $_ -like "C545D_GIO_ACTIVE_GETTER_FRAME_SCOPE,arm=$Arm,*"
  })
  if($getters.Count -ne 3){throw 'Getter original source cutoff scope incomplete'}
  $gseen=@{}
  $getterShape='^C545D_GIO_ACTIVE_GETTER_FRAME_SCOPE,arm='+[regex]::Escape($Arm)+
    ',phase=(baseline|cycle1|cycle2),live=\d+,request_bytes_live=\d+,'+
    'package_nearest_live=\d+,package_nearest_bytes=\d+,'+
    'verified_module_and_symbol=1,original_allocation_stack_only=1,'+
    'direct_winrt_owner_not_proven=1,release_HOLD=1$'
  foreach($line in $getters){
    $m=[regex]::Match($line,$getterShape)
    if(-not $m.Success -or $gseen.ContainsKey($m.Groups[1].Value)){
      throw 'Getter source phase malformed or duplicated'
    }
    $gseen[$m.Groups[1].Value]=1
  }
  if($gseen.Count -ne 3){throw 'Getter source phases not complete'}
  $rawGetter=@($source | Where-Object {
    $_ -match ('^C545D_GIO_GETTER_MARKER_ORIGINALS,arm='+[regex]::Escape($Arm)+
      ',raw_original_stack_hits=\d+,exact_private_gio_symbol=1,'+
      'direct_winrt_owner_not_proven=1,release_HOLD=1$')
  })
  if($rawGetter.Count -ne 1){throw 'Getter frame original-hit evidence missing'}
  $hits=[regex]::Match($rawGetter[0],'raw_original_stack_hits=(\d+)')
  if(-not $hits.Success){throw 'Getter original-hit numeric field malformed'}
  if($Arm -eq 'registry' -and [long]$hits.Groups[1].Value -eq 0){
    throw 'Getter function exact PDB frame not exercised in registry path'
  }
  foreach($row in $getters){Write-Host $row}
  Write-Host $rawGetter[0]
  Write-Host "C545D_GIO_GETTER_FRAME_QPC_ACCOUNTING_PASS,arm=$Arm,phases=3,source_private_marker=1,release_HOLD=1"
  Write-Host $safePass[0]
  # The disposable probe performs equivalent PSAPI+VirtualQuery phases,
  # but positive deltas do NOT imply a leak and cannot be subtracted from
  # selected heap request bytes without accounting for other memory paths.
  $lines=@(Get-Content $out -ErrorAction Stop)
  $private=@{}
  $region=@{}
  $handles=@{}
  foreach($phase in @('preappinfo','baseline','settled_cleanup')){
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
  if($null -eq $oldTrace){Remove-Item Env:C545D_CI_APPINFO_PHASE_TRACE -ErrorAction SilentlyContinue}
  else{$env:C545D_CI_APPINFO_PHASE_TRACE=$oldTrace}
  if((Test-Path $local) -and (Test-Path (Join-Path $local 'ci_owned.signal')) -and
     $local.StartsWith($env:RUNNER_TEMP,[StringComparison]::OrdinalIgnoreCase)){
    Remove-Item $local -Force -Recurse -ErrorAction SilentlyContinue
  }
}
if($success){$global:LASTEXITCODE=0}
