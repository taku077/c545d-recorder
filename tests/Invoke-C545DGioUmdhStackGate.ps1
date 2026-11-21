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
  for($i=0;$i -lt 2300;$i++){
    if(Test-Path $flag -PathType Leaf){return}
    if($proc){$proc.Refresh();if($proc.HasExited){throw "Process exited before gated point $point"}}
    Start-Sleep -Milliseconds 100
  }
  throw "Stage $point handshake missing"
}
function Snapshot([int]$point){
  $path=Join-Path $dir ("snap_"+$point+".txt")
  $status=Join-Path $dir ("status_"+$point+".txt")
  & $Umdh "-p:$($proc.Id)" "-f:$path" > $status 2>&1
  if($LASTEXITCODE -ne 0 -or -not(Test-Path $path -PathType Leaf)){throw "UMDH failed at stage $point; raw suppressed"}
  return $path
}
function Compare([int]$left,[int]$right,[string]$before,[string]$after){
  $diff=Join-Path $dir ("diff_"+$left+"_"+$right+".txt")
  & $Umdh $before $after > $diff 2>&1
  if($LASTEXITCODE -ne 0){throw 'UMDH diff failed (raw suppressed)'}
  $content=[IO.File]::ReadAllText($diff)
  $headers=[regex]::Matches($content,'(?im)^\s*\+\s+(?:0x)?[0-9a-f]+\s+\([^)]*\)\s+[0-9a-f]+\s+allocs\s+BackTrace([0-9a-f]+)')
  $afterText=[IO.File]::ReadAllText($after)
  $gio=0;$glib=0
  foreach($h in $headers){
    $id=$h.Groups[1].Value.TrimStart('0')
    if(-not $id){$id='0'}
    $find=[regex]::Match($afterText,'(?is)\bby:\s*BackTrace0*'+[regex]::Escape($id)+'\b([\s\S]{0,4500})')
    if($find.Success){
      $stack=$find.Groups[1].Value
      if($stack -match '(?i)gio-2[.]0-0'){ $gio++ }
      if($stack -match '(?i)glib-2[.]0-0|gobject-2[.]0-0'){ $glib++ }
    }
  }
  $positive=$headers.Count
  Write-Host "C545D_GIO_UMDH_STACK,arm=$arm,cycles=$Cycles,window=$($left)_$right,positive_backtraces=$positive,has_gio_module=$gio,has_glib_module=$glib,exact_360_owner_proven=0,raw_uploaded=0,CI_only=1"
  if($positive -lt 1){throw 'Actual GIO UMDH snapshot diff contains no positive stacks'}
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
    Compare $stages[$j] $stages[$j+1] $snaps[$stages[$j]] $snaps[$stages[$j+1]]
  }
  if($Cycles -eq256){
    $m192=[regex]::Match($output,'(?m)^GIO_HEAPSIZE,cycle,192,360,(\d+)$')
    $m256=[regex]::Match($output,'(?m)^GIO_HEAPSIZE,cycle,256,360,(\d+)$')
    if(-not($m192.Success -and $m256.Success)){throw 'GIO 360-byte HeapWalk checkpoints missing'}
    $start=[long]::Parse($m192.Groups[1].Value);$end=[long]::Parse($m256.Groups[1].Value)
    $delta=$end-$start
    Write-Host "C545D_GIO_UMDH_HEAP360,arm=$arm,cycle192=$start,cycle256=$end,raw_delta=$delta,matched_control_not_in_this_arm=1,owner_known=0,CI_only=1"
  }
  Write-Host "C545D_GIO_UMDH_PROCESS_PASS,arm=$arm,cycles=$Cycles,ust=1,signed_legacy_umdh=1,raw_uploaded=0,user_host_modified=0,release_approved=0"
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
