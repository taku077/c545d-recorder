# CI only: snapshot exact disposable MSVC GIO process with signed Win10 UMDH.
# Raw heap addresses/stacks and package details never leave the runner.
[CmdletBinding()]
param(
 [Parameter(Mandatory)][string]$Probe,
 [Parameter(Mandatory)][string]$Gflags,
 [Parameter(Mandatory)][string]$Umdh,
 [Parameter(Mandatory)][string]$WorkRoot,
 [ValidateSet(16,256)][int]$Cycles=256,
 [switch]$NoRegistryChange
)
$ErrorActionPreference='Stop'
foreach($tool in @($Probe,$Gflags,$Umdh)){if(-not(Test-Path $tool -PathType Leaf)){throw 'Missing runner-only tool'}}
if((Get-Item $Probe).Name -ne 'c545d_gio_umdh_probe.exe'){throw 'Refuse to trace non-disposable image'}
$v=[Diagnostics.FileVersionInfo]::GetVersionInfo($Umdh)
if($v.FileBuildPart -le 0 -or $v.FileBuildPart -ge 22000){throw 'Refuse known broken SDK UMDH'}
$exeName='c545d_gio_umdh_probe.exe'
$ifeo="HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\$exeName"
if(Test-Path $ifeo){throw 'Refuse to overwrite existing runner IFEO policy'}
$arm=if($NoRegistryChange){'nochange'}else{'registry'}
$stages=if($Cycles -eq16){@(0,16)}else{@(0,192,256)}
$dir=Join-Path $WorkRoot ("umdh_"+$arm+"_"+$Cycles)
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$stdout=Join-Path $dir 'process_output_local_only.txt'
$stderr=Join-Path $dir 'process_stderr_local_only.txt'
$proc=$null;$ustChanged=$false
$oldNoCache=$env:OANOCACHE;$oldPause=$env:C545D_UMDH_PAUSE;$oldEarly=$env:C545D_UMDH_EARLY_GATE
function Wait-Stage([int]$point) {
  $flag=Join-Path $dir ("stage_"+$point+".signal")
  # Original 44927366590: the registry arm remained alive yet did not reach
  # cycle192 within 230 s; the nochange arm DID finish. Do not classify this
  # as a GIO crash, and do not rerun the completed nochange control.
  $pollLimit=if($Cycles -eq 256 -and -not $NoRegistryChange -and $point -eq 192){6000}else{2300}
  for($i=0;$i -lt $pollLimit;$i++){
    if(Test-Path $flag -PathType Leaf){return}
    if($proc){$proc.Refresh();if($proc.HasExited){throw "Process exited before gated point $point"}}
    Start-Sleep -Milliseconds 100
  }
  $alive=0
  if($proc){$proc.Refresh();$alive=[int](-not $proc.HasExited)}
  Write-Host "C545D_GIO_UMDH_STAGE_TIMEOUT,arm=$arm,cycles=$Cycles,target_cycle=$point,proc_alive=$alive,limit_ticks=$pollLimit,raw_uploaded=0"
  throw "Stage $point handshake missing"
}
function Snapshot([int]$point){
  $path=Join-Path $dir ("snap_"+$point+".txt")
  $status=Join-Path $dir ("status_"+$point+".txt")
  & $Umdh "-p:$($proc.Id)" "-f:$path" > $status 2>&1
  if($LASTEXITCODE -ne 0 -or -not(Test-Path $path -PathType Leaf)){throw "UMDH failed at stage $point; raw suppressed"}
  return $path
}
function Compare-C545DUmdhStacks([int]$left,[int]$right,[string]$before,[string]$after){
  $diff=Join-Path $dir ("diff_"+$left+"_"+$right+".txt")
  # UMDH -v resolves symbols in the local *diff*. Raw snapshots from
  # -f are not symbol-resolved: searching them can falsely report 0 modules.
  & $Umdh '-v' $before $after > $diff 2>&1
  if($LASTEXITCODE -ne 0){throw 'UMDH symbolized diff failed (raw suppressed)'}
  . (Join-Path $PSScriptRoot 'Get-C545DUmdhSafeSummary.ps1')
  $summary=Get-C545DUmdhSafeSummary -Content ([IO.File]::ReadAllText($diff))
  $positive=$summary.Positive
  Write-Host "C545D_GIO_UMDH_STACK,arm=$arm,cycles=$Cycles,window=$($left)_$right,positive_backtraces=$positive,symbolized_backtraces=$($summary.Symbolized),unresolved_backtraces=$($summary.Unresolved),gio_module_stacks=$($summary.GIO),glib_module_stacks=$($summary.GLib),winrt_module_stacks=$($summary.WinRT),exact_360_owner_proven=0,raw_uploaded=0,CI_only=1"
  # A valid 0->16 UMDH diff may have zero positive stacks. The 360B
  # residual appeared late; do not treat an early plateau as tool failure.
  # A zero count at 192->256 means inconclusive attribution, not zero leak.
  if($positive -eq 0) {
    Write-Host "C545D_GIO_UMDH_NO_POSITIVE_STACKS,arm=$arm,cycles=$Cycles,window=$($left)_$right,snapshots_valid=1,leak_absent_proven=0,CI_only=1"
  }
}
try {
  & $Gflags /i $exeName +ust > $null 2>&1
  if($LASTEXITCODE -ne 0){throw 'Runner-only UST enable failed'}
  $ustChanged=$true
  $env:C545D_UMDH_PAUSE='1'
  $env:OANOCACHE='1'
  if($Cycles -eq16){$env:C545D_UMDH_EARLY_GATE='1'}
  else{Remove-Item Env:C545D_UMDH_EARLY_GATE -ErrorAction SilentlyContinue}
  $args=@("--cycles=$Cycles",'--heap-summary')
  if($NoRegistryChange){$args+='--no-registry-change'}
  $proc=Start-Process -FilePath $Probe -WorkingDirectory $dir -ArgumentList $args -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
  $snaps=@{}
  foreach($stage in $stages){
    Wait-Stage $stage
    $snaps[$stage]=Snapshot $stage
    New-Item -ItemType File -Force -Path (Join-Path $dir ("resume_"+$stage+".signal")) | Out-Null
  }
  if(-not $proc.WaitForExit(30000)){throw 'GIO probe never completed cleanup'}
  if($proc.ExitCode -ne 0){throw "GIO probe exited $($proc.ExitCode)"}
  $output=[IO.File]::ReadAllText($stdout)
  if(-not $output.Contains("GIO_PROBE_DONE,cycles=$Cycles,")){throw 'GIO probe completion missing'}
  for($j=0;$j -lt ($stages.Count-1);$j++){
    Compare-C545DUmdhStacks $stages[$j] $stages[$j+1] $snaps[$stages[$j]] $snaps[$stages[$j+1]]
  }
  if($Cycles -eq256){
    # MSVC stdout is CRLF, and the C probe omits zero-count size bins.
    # Require both valid HeapWalk checkpoints before interpreting absence
    # of a 360B row as zero rather than an incomplete heap traversal.
    foreach($point in @(192,256)) {
      $heap=[regex]::Match($output,("(?m)^GIO_HEAP,cycle,"+$point+",\d+,\d+,\d+,0\r?$"))
      if(-not $heap.Success){throw "Incomplete or invalid HeapWalk checkpoint $point"}
    }
    $m192=[regex]::Match($output,'(?m)^GIO_HEAPSIZE,cycle,192,360,(\d+)\r?$')
    $m256=[regex]::Match($output,'(?m)^GIO_HEAPSIZE,cycle,256,360,(\d+)\r?$')
    $start=if($m192.Success){[long]::Parse($m192.Groups[1].Value)}else{[long]0}
    $end=if($m256.Success){[long]::Parse($m256.Groups[1].Value)}else{[long]0}
    $delta=$end-$start
    Write-Host "C545D_GIO_UMDH_HEAP360,arm=$arm,cycle192=$start,cycle256=$end,raw_delta=$delta,matched_control_not_in_this_arm=1,owner_known=0,CI_only=1"
  }
  Write-Host "C545D_GIO_UMDH_PROCESS_CAPTURE_COMPLETE,arm=$arm,cycles=$Cycles,ust=1,signed_legacy_umdh=1,exact_360_owner_proven=0,zero_leak_proven=0,raw_uploaded=0,user_host_modified=0,release_approved=0"
} finally {
  if($proc){
    foreach($point in $stages){New-Item -ItemType File -Force -Path (Join-Path $dir ("resume_"+$point+".signal")) | Out-Null}
    if(-not $proc.WaitForExit(1500)){Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue}
  }
  if($ustChanged){
    & $Gflags /i $exeName -ust > $null 2>&1
    if($LASTEXITCODE -ne 0){throw 'Runner UST cleanup failed'}
    if(Test-Path $ifeo){Remove-Item $ifeo -Recurse -Force}
  }
  if($null -eq $oldNoCache){Remove-Item Env:OANOCACHE -ErrorAction SilentlyContinue}else{$env:OANOCACHE=$oldNoCache}
  if($null -eq $oldPause){Remove-Item Env:C545D_UMDH_PAUSE -ErrorAction SilentlyContinue}else{$env:C545D_UMDH_PAUSE=$oldPause}
  if($null -eq $oldEarly){Remove-Item Env:C545D_UMDH_EARLY_GATE -ErrorAction SilentlyContinue}else{$env:C545D_UMDH_EARLY_GATE=$oldEarly}
}
