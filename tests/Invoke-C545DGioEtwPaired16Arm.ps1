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
$local=Join-Path $Root ('etw_'+$Arm+'_local')
New-Item -ItemType Directory -Force -Path $local | Out-Null
$rawLocal=Join-Path $local 'tool_output_private.txt'
$etl=Join-Path $local 'heap_local_only.etl'
$stack=Join-Path $local 'stacks_local_only.txt'
$out=Join-Path $Root ('combo-'+$Arm+'-16.txt')
$err=Join-Path $Root ($Arm+'-error.txt')
$proc=$null
$kernelOn=$false
$heapOn=$false
$success=$false
function Invoke-SafeXperf([string]$Phase,[string[]]$Argv){
  & $xperf @Argv *> $rawLocal
  if($LASTEXITCODE -ne 0){throw "CI_GIO_ETW_FAILED,phase=$Phase,raw_uploaded=0"}
}
try {
  $proc=Start-Process -FilePath $Probe -WorkingDirectory $Root -ArgumentList $args -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
  # This attaches to an existing PID, so startup allocations may be missed.
  # No pre-baseline capture or true quiescence proof is claimed.
  Invoke-SafeXperf 'kernel' @('-on','BASE')
  $kernelOn=$true
  Invoke-SafeXperf 'heap' @('-start','HeapSession','-heap','-pids',"$($proc.Id)",'-BufferSize','1024','-MinBuffers','128','-MaxBuffers','128','-stackwalk','HeapAlloc+HeapRealloc')
  $heapOn=$true
  if(-not $proc.WaitForExit(90000)){throw 'GIO sixteen-cycle test exceeded 90s'}
  if($proc.ExitCode -ne 0){throw 'GIO 16-cycle process failed'}
  if(-not(Test-Path $out -PathType Leaf)){throw 'GIO numeric stdout absent'}
  if(-not([IO.File]::ReadAllText($out).Contains('GIO_PROBE_DONE,cycles=16,'))){
    throw 'GIO completion marker missing'
  }
  Invoke-SafeXperf 'stop_and_merge' @('-stop','-stop','HeapSession','-d',$etl)
  $heapOn=$false
  $kernelOn=$false
  if(-not(Test-Path $etl -PathType Leaf)){throw 'No local ETW trace generated'}
  $len=(Get-Item $etl).Length
  if($len -lt 512 -or $len -gt 100MB){throw 'Unbounded ETW output'}
  $oldSymbols=$env:_NT_SYMBOL_PATH
  try {
    $env:_NT_SYMBOL_PATH='srv*'+(Join-Path $local 'symbol_cache_local_only')+'*https://msdl.microsoft.com/download/symbols'
    Invoke-SafeXperf 'symbol_stacks' @('-i',$etl,'-o',$stack,'-symbols','-a','heap','-stacks','-top','25')
  } finally {
    if($null -eq $oldSymbols){Remove-Item Env:_NT_SYMBOL_PATH -ErrorAction SilentlyContinue}
    else{$env:_NT_SYMBOL_PATH=$oldSymbols}
  }
  $safe=@(& py tests/analyze_c545d_etw_stack_safe.py --source $stack)
  $safeExit=$LASTEXITCODE
  $counts=@($safe | Where-Object { $_ -match '^C545D_ETW_STACK_SAFE_SUMMARY,[A-Za-z0-9_,=]+$' })
  $passed=@($safe | Where-Object { $_ -eq 'C545D_ETW_STACK_SANITIZER_PASS,module_only=1,source_owner_proven=0,real_recorder_untouched=1' })
  if($safeExit -ne 0 -or $counts.Count -ne 1 -or $passed.Count -ne 1){
    throw 'ETW stacks not sanitizable, no owner classification permitted'
  }
  $numericOnly=$counts[0].Replace('C545D_ETW_STACK_SAFE_SUMMARY,','')
  if($numericOnly -notmatch '^classification=module_frame_occurrences,'){
    throw 'Expected sanitized report shape missing'
  }
  Write-Host "C545D_GIO_ETW16_MODULE_COUNTS,arm=$Arm,$numericOnly"
  Write-Host "C545D_GIO_ETW16_ARM_PASS,arm=$Arm,cycles=16,raw_etl_uploaded=0,matched_control_not_in_this_arm=1,prebaseline_trace_proven=0,source_owner_proven=0"
  $success=$true
} finally {
  if($heapOn){& $xperf -stop HeapSession *> $rawLocal}
  if($kernelOn){& $xperf -stop *> $rawLocal}
  if($proc){
    $proc.Refresh()
    if(-not $proc.HasExited){Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue}
  }
  # Reports and ETL never enter GitHub Artifacts, regardless of outcome.
  Remove-Item $local -Force -Recurse -ErrorAction SilentlyContinue
}
if($success){$global:LASTEXITCODE=0}
