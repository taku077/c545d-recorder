# C545D / RC35: opt-in Windows Heap allocation diagnostics.
# Only Enable/Restore change image-file UST, and only with admin rights.
# Never edits recordings or the running gst-launch process.
[CmdletBinding()]
param(
  [ValidateSet('Check','Enable','Launch','Capture','Compare','Restore','SelfTest')]
  [string]$Mode='Check',
  [string]$ExePath='',
  [string]$ToolsDir='',
  [int]$TargetPid=0,
  [string]$DataRoot=(Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\HeapTrace')
)
$ErrorActionPreference='Stop'
$imageName='gst-launch-1.0.exe'
$flagPath='HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\gst-launch-1.0.exe'
$stateFile=Join-Path $DataRoot 'enabled-by-c545d.json'
$sessionFile=Join-Path $DataRoot 'snapshots.json'
function Out-Status([string]$s) { Write-Host ('[C545D Heap] '+$s) }
function Find-Tool([string]$file) {
  if($ToolsDir) {
    $p=Join-Path $ToolsDir $file
    if(Test-Path -LiteralPath $p -PathType Leaf) {return $p}
    throw "$file not found under ToolsDir"
  }
  $bases=@($env:ProgramFiles,[Environment]::GetEnvironmentVariable('ProgramFiles(x86)'))
  foreach($b in $bases) {
    if(-not $b) {continue}
    $p=Join-Path $b ('Windows Kits\10\Debuggers\x64\'+$file)
    if(Test-Path -LiteralPath $p -PathType Leaf) {return $p}
  }
  $cmd=Get-Command $file -ErrorAction SilentlyContinue | Select-Object -First 1
  if($cmd) {return $cmd.Source}
  return $null
}
function Is-USTEnabled {
  $k=Get-ItemProperty -LiteralPath $flagPath -Name GlobalFlag -ErrorAction SilentlyContinue
  if(-not $k) {return $false}
  $v=$k.GlobalFlag
  if($v -is [string]) {
    if($v -match '^0x([a-fA-F0-9]+)$') { $n=[Convert]::ToUInt32($Matches[1],16) }
    elseif($v -match '^[a-fA-F0-9]{8}$') { $n=[Convert]::ToUInt32($v,16) }
    else { $n=[Convert]::ToUInt32($v) }
  } else { $n=[Convert]::ToUInt32($v) }
  return (($n -band 0x1000) -ne 0)
}
function Is-Admin {
  $p=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
  return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Need-Tools {
  $g=Find-Tool 'gflags.exe';$u=Find-Tool 'umdh.exe'
  if(-not $g -or -not $u) {throw 'Install Microsoft Debugging Tools for Windows x64: https://learn.microsoft.com/windows-hardware/drivers/debugger/debugger-download-tools'}
  return @{gflags=$g;umdh=$u}
}
function Live-Gst {
  $all=@(Get-Process -Name 'gst-launch-1.0' -ErrorAction SilentlyContinue)
  if($TargetPid -gt 0) {$all=@($all|Where-Object {$_.Id -eq $TargetPid})}
  if($all.Count -ne 1) {
    throw ('Expected exactly one gst-launch process. Found '+$all.Count+
      '. If more than one, supply -TargetPid (do not kill other processes).')
  }
  return $all[0]
}
function Save-Json([string]$path,[object]$obj) {
  [IO.File]::WriteAllText($path,(ConvertTo-Json $obj -Depth 5),(New-Object Text.UTF8Encoding($false)))
}
# Save-Json uses BOM-less UTF-8. Windows PowerShell 5.1's plain
# Get-Content defaults to ANSI when there is no BOM: Japanese profile paths
# become mojibake. Always decode state explicitly as UTF-8.
function Read-Json([string]$path) {
  $utf8=[System.Text.UTF8Encoding]::new($false,$true)
  return ([IO.File]::ReadAllText($path,$utf8)|ConvertFrom-Json)
}
# Recover a captured pair using ONLY files with exactly the expected PID,
# snapshot slot, and timestamped basename in the private HeapTrace directory.
# Never guess if multiple candidate raw files exist; never modify a raw log.
function Resolve-CapturePair([object]$session,[string]$root) {
  $pidNumber=[int]$session.pid
  if($pidNumber -le 0) {throw 'Invalid snapshot PID in metadata.'}
  $resolved=@{}
  $rootPath=[IO.Path]::GetFullPath($root).TrimEnd('\')
  foreach($slot in @(1,2)) {
    $property=if($slot -eq 1){'first'}else{'second'}
    $saved=[string]$session.$property
    $pattern='^UMDH_RAW_PID'+$pidNumber+'_T'+$slot+'_[0-9]{8}_[0-9]{6}\.txt
  $rows=New-Object System.Collections.Generic.List[object];$current=$null
  foreach($line in [IO.File]::ReadLines($raw)) {
    $m=[regex]::Match($line,'^\s*([+-])\s+(?:0x)?([0-9a-fA-F]{1,16})\s+\([^)]*\).*?BackTrace[0-9a-fA-F]+')
    if($m.Success) {
      $delta=[Convert]::ToInt64($m.Groups[2].Value,16)
      if($m.Groups[1].Value -eq '-') {$delta=-$delta}
      $current=[PSCustomObject]@{delta=$delta;module='unknown';index=$rows.Count+1}
      $rows.Add($current);continue
    }
    if($null -eq $current -or $current.module -ne 'unknown') {continue}
    # Only copy a DLL basename, never paths, PDB strings, symbols or addresses.
    $dll=[regex]::Match($line,'(?i)([a-z][a-z0-9_.-]{1,63}\.dll)![a-z_?@$]')
    if($dll.Success) {$current.module=$dll.Groups[1].Value.ToLowerInvariant()}
  }
  $total=0L;foreach($r in $rows) {$total += [long]$r.delta}
  $out=New-Object System.Collections.Generic.List[string]
  $out.Add('C545D HEAP SAFE SUMMARY V1')
  $out.Add('raw_snapshots_included=no')
  $out.Add('parsed_backtraces='+$rows.Count)
  $out.Add('parsed_net_delta_bytes='+$total)
  $out.Add('Note: this is Windows Heap, not all Private Memory.')
  $out.Add('Note: missing symbols/other allocators may limit attribution.')
  $out.Add('rank,delta_bytes,first_dll')
  $top=@($rows|Sort-Object delta -Descending|Select-Object -First 30)
  foreach($r in $top) {$out.Add(('{0},{1},{2}' -f $r.index,$r.delta,$r.module))}
  [IO.File]::WriteAllLines($safe,[string[]]$out,(New-Object Text.UTF8Encoding($false)))
  return $rows.Count
}
if($Mode -eq 'SelfTest') {
  $isElevated=Is-Admin
  if($isElevated -isnot [bool]) {throw 'Privilege-check test failed'}
  $dir=Join-Path $env:TEMP ('c545d-heap-selftest-'+[guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $dir|Out-Null
  try {
    $raw=Join-Path $dir 'raw.txt';$safe=Join-Path $dir 'safe.txt'
    @('+ 5320 ( f110 - 9df0) 3a allocs BackTrace00B53',
      'C:\Users\PRIVATE123\secret\avcodec-61.dll!sensitive_symbol+0x12',
      'token=DO_NOT_LEAK_USERNAME',
      '+ 0100 ( 0200 - 0100) 01 allocs BackTrace001',
      'glib-2.0-0.dll!another_symbol+0x10')|Set-Content -LiteralPath $raw -Encoding UTF8
    $n=Make-SafeSummary $raw $safe;$txt=[IO.File]::ReadAllText($safe)
    if($n -ne 2 -or $txt -notmatch '21280' -or
       $txt -notmatch 'avcodec-61.dll' -or
       $txt -match 'PRIVATE123|DO_NOT_LEAK|secret\\|sensitive_symbol') {
       throw 'Safe diff self-test failed'
    }
    Out-Status 'PASS safe UMDH parser and synthetic credential exclusion.'
    # Japanese user profile paths are written as BOM-less UTF-8. Windows
    # PowerShell 5.1 must read the JSON with explicit UTF-8, not ANSI.
    $unicodeName=[string][char]0x4fdd + [string][char]0x7ba1
    $unicodeRoot=Join-Path $dir $unicodeName
    New-Item -ItemType Directory -Path $unicodeRoot -Force|Out-Null
    $t1=Join-Path $unicodeRoot 'UMDH_RAW_PID9424_T1_20261117_223501.txt'
    $t2=Join-Path $unicodeRoot 'UMDH_RAW_PID9424_T2_20261117_230044.txt'
    [IO.File]::WriteAllText($t1,('T1-H2048'+('x'*400)),(New-Object Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText($t2,('T2-H2048'+('y'*400)),(New-Object Text.UTF8Encoding($false)))
    # Ensure filesystem ordering and same-PID naming (no real UMDH invoked).
    (Get-Item -LiteralPath $t1).LastWriteTime=(Get-Date).AddMinutes(-25)
    (Get-Item -LiteralPath $t2).LastWriteTime=(Get-Date)
    $j=Join-Path $unicodeRoot 'snapshots.json'
    Save-Json $j ([ordered]@{pid=9424;first=$t1;second=$t2;first_private_mb=632.28;second_private_mb=633.43})
    $reloaded=Read-Json $j
    if($reloaded.first -cne $t1 -or $reloaded.second -cne $t2) {
      throw 'UTF-8 Japanese snapshot path roundtrip failed.'
    }
    $reloaded.first='C:\MOJIBAKE_FIRST.txt'
    $reloaded.second='C:\MOJIBAKE_SECOND.txt'
    $recovered=Resolve-CapturePair $reloaded $unicodeRoot
    if($recovered.first -cne $t1 -or $recovered.second -cne $t2) {
      throw 'Unique same-PID existing snapshot recovery failed.'
    }
    $extra=Join-Path $unicodeRoot 'UMDH_RAW_PID9424_T2_20261117_230545.txt'
    [IO.File]::WriteAllText($extra,('duplicate'+('z'*400)),(New-Object Text.UTF8Encoding($false)))
    $reloaded.second='C:\MOJIBAKE_SECOND.txt'
    $ambiguousFailed=$false
    try {$null=Resolve-CapturePair $reloaded $unicodeRoot} catch {$ambiguousFailed=$true}
    if(-not $ambiguousFailed) {throw 'Ambiguous snapshot recovery should fail closed.'}
    Out-Status 'PASS explicit UTF-8 Japanese path roundtrip, existing T1/T2 recovery, ambiguity refusal.'
  } finally {Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue}
  exit 0
}
if($Mode -eq 'Check') {
  Out-Status ('gflags.exe: '+$(if(Find-Tool 'gflags.exe'){'FOUND'}else{'MISSING'}))
  Out-Status ('umdh.exe: '+$(if(Find-Tool 'umdh.exe'){'FOUND'}else{'MISSING'}))
  Out-Status ('UST for gst-launch: '+$(if(Is-USTEnabled){'ON'}else{'OFF'}))
  Out-Status ('gst-launch processes: '+@(Get-Process -Name 'gst-launch-1.0' -ErrorAction SilentlyContinue).Count)
  Out-Status 'Read-only check completed; no GFlags, processes, or MP4 changed.'
  exit 0
}
$tools=Need-Tools
if($Mode -in @('Enable','Restore') -and -not (Is-Admin)) {
  throw 'Enable/Restore require Administrator PowerShell. Do NOT run recorder as admin.'
}
if($Mode -eq 'Enable') {
  if(@(Get-Process -Name 'gst-launch-1.0' -ErrorAction SilentlyContinue).Count -gt 0) {
    throw 'Use GUI Stop to finalize current MP4 before enabling UST. No process touched.'
  }
  if(Is-USTEnabled) {
    Out-Status 'UST already enabled. Did NOT modify it; Restore will not remove another user setting.'
    exit 0
  }
  New-Item -ItemType Directory -Path $DataRoot -Force|Out-Null
  & $tools.gflags '/i' $imageName '+ust'|Out-Null
  if($LASTEXITCODE -ne 0 -or -not (Is-USTEnabled)) {throw 'Could not verify +ust'}
  Save-Json $stateFile @{image=$imageName;marker='C545D-v1'}
  Out-Status 'UST enabled for future gst-launch instances. Restart recorder normally via Launch mode.'
  exit 0
}
if($Mode -eq 'Restore') {
  if(-not (Test-Path -LiteralPath $stateFile -PathType Leaf)) {
    Out-Status 'No ownership marker. Not changing someone else’s GFlags setting.';exit 0
  }
  $marker=Read-Json $stateFile
  if($marker.marker -ne 'C545D-v1' -or $marker.image -ne $imageName) {
    throw 'Invalid ownership marker; refusing to change UST.'
  }
  & $tools.gflags '/i' $imageName '-ust'|Out-Null
  if($LASTEXITCODE -ne 0 -or (Is-USTEnabled)) {throw 'Could not verify -ust; marker preserved'}
  Remove-Item -LiteralPath $stateFile -Force
  Out-Status 'UST restored OFF for future gst-launch; recordings untouched.'
  exit 0
}
if($Mode -eq 'Launch') {
  if(-not (Is-USTEnabled)) {throw 'UST not enabled (start with Enable after normal stop).'}
  if(Is-Admin) {throw 'Launch RC35 in ordinary PowerShell; not as Administrator.'}
  if(@(Get-Process -Name 'gst-launch-1.0' -ErrorAction SilentlyContinue).Count -gt 0) {
    throw 'Another gst-launch already active. Do not run dual recorders.'
  }
  if(-not $ExePath -or -not (Test-Path -LiteralPath $ExePath -PathType Leaf) -or
     [IO.Path]::GetFileName($ExePath) -ne 'C545D_Recorder.exe') {throw 'Supply -ExePath path to RC35 C545D_Recorder.exe'}
  $old=[Environment]::GetEnvironmentVariable('OANOCACHE','Process')
  try {
    [Environment]::SetEnvironmentVariable('OANOCACHE','1','Process')
    Start-Process -FilePath $ExePath -WorkingDirectory (Split-Path -Parent $ExePath)
  } finally {[Environment]::SetEnvironmentVariable('OANOCACHE',$old,'Process')}
  Out-Status 'RC35 started (process-only OANOCACHE=1). Use its normal Record button.'
  exit 0
}
if($Mode -eq 'Capture') {
  if(-not (Is-USTEnabled)) {throw 'UST OFF; cannot retrieve past heap stacks retrospectively.'}
  $p=Live-Gst
  $start=[long]$p.StartTime.ToUniversalTime().Ticks
  New-Item -ItemType Directory -Path $DataRoot -Force|Out-Null
  $s=$null
  if(Test-Path -LiteralPath $sessionFile) {
    $s=Read-Json $sessionFile
  }
  $second=($s -and $s.first -and -not $s.second)
  if($second) {
    if([int]$s.pid -ne [int]$p.Id -or [long]$s.start_ticks -ne $start) {
      throw 'PID/start time differs from first capture. Refusing cross-session comparison.'
    }
  } else {
    $s=[ordered]@{pid=[int]$p.Id;start_ticks=$start;first=$null;second=$null;
      first_private_mb=$null;second_private_mb=$null;first_at=$null;second_at=$null}
  }
  $num=if($second){2}else{1}
  $where=Join-Path $DataRoot ('UMDH_RAW_PID'+$p.Id+'_T'+$num+'_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'.txt')
  if(-not $env:_NT_SYMBOL_PATH) {
    $env:_NT_SYMBOL_PATH='srv*'+(Join-Path $DataRoot 'Symbols')+'*https://msdl.microsoft.com/download/symbols'
  }
  & $tools.umdh ('-p:'+$p.Id) ('-f:'+$where) 2>&1|Out-Null
  if($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $where) -or
    (Get-Item -LiteralPath $where).Length -lt 256) {
    throw 'UMDH failed or empty; keep recorder running and check access/UST.'
  }
  $memory=[math]::Round($p.PrivateMemorySize64/1MB,2)
  $at=(Get-Date).ToString('o')
  if($second){$s.second=$where;$s.second_private_mb=$memory;$s.second_at=$at}
  else {$s.first=$where;$s.first_private_mb=$memory;$s.first_at=$at}
  Save-Json $sessionFile $s
  Out-Status ('Saved RAW snapshot '+$num+' (same PID) locally, Private='+$memory+'MB.')
  if(-not $second){Out-Status 'Continue recording ~15 minutes, then Capture again.'}
  else {Out-Status 'Capture 2 done. Use Compare, then Restore UST.'}
  exit 0
}
if($Mode -eq 'Compare') {
  if(-not (Test-Path -LiteralPath $sessionFile -PathType Leaf)) {throw 'No capture state.'}
  $s=Read-Json $sessionFile
  # Read-Json now decodes Japanese paths correctly. Recover historical
  # paths if an old Capture already persisted ANSI-misdecoded data.
  $s=Resolve-CapturePair $s $DataRoot
  $raw=Join-Path $DataRoot ('UMDH_RAW_DIFF_PID'+$s.pid+'.txt')
  # -v includes stack frames so we can attribute growth to specific DLLs.
  & $tools.umdh '-v' $s.first $s.second 2>&1|Out-File -LiteralPath $raw -Encoding UTF8
  if($LASTEXITCODE -ne 0) {throw 'UMDH comparison failed.'}
  $safe=Join-Path $DataRoot ('C545D_HEAP_SAFE_SUMMARY_PID'+$s.pid+'.txt')
  $n=Make-SafeSummary $raw $safe
  if($n -eq 0) {throw 'UMDH diff format unknown: keeping raw local; do not infer no leak.'}
  # Repair legacy JSON only once the same-PID snapshot comparison succeeds.
  Save-Json $sessionFile $s
  Add-Content -LiteralPath $safe -Value ('private_before_mb='+$s.first_private_mb)
  Add-Content -LiteralPath $safe -Value ('private_after_mb='+$s.second_private_mb)
  Add-Content -LiteralPath $safe -Value ('elapsed_minutes='+[math]::Round((([datetime]$s.second_at)-([datetime]$s.first_at)).TotalMinutes,2))
  $zip=Join-Path $DataRoot ('C545D_HEAP_SAFE_REPORT_PID'+$s.pid+'.zip')
  if(Test-Path -LiteralPath $zip) {Remove-Item -LiteralPath $zip -Force}
  Compress-Archive -LiteralPath $safe -DestinationPath $zip -CompressionLevel Optimal
  Out-Status ('Heap backtraces compared: '+$n+'. Upload ONLY: '+$zip)
  Out-Status 'Raw UMDH snapshots/diff kept locally and not uploaded.'
  exit 0
}
throw 'Unknown action'
    $accepted=$null
    if($saved -and [IO.File]::Exists($saved)) {
      $savedFile=[IO.FileInfo]::new($saved)
      if($savedFile.Name -match $pattern -and
         [string]::Equals($savedFile.Directory.FullName.TrimEnd('\'),$rootPath,[StringComparison]::OrdinalIgnoreCase)) {
        $accepted=$savedFile
      }
    }
    if(-not $accepted) {
      $candidates=@(Get-ChildItem -LiteralPath $root -File -Filter ("UMDH_RAW_PID"+$pidNumber+"_T"+$slot+"_*.txt") |
        Where-Object {$_.Name -match $pattern})
      if($candidates.Count -ne 1) {
        throw ("Snapshot T"+$slot+" path cannot be resolved unambiguously: "+$candidates.Count+
          " matching files. Refusing to guess or overwrite any data.")
      }
      $accepted=$candidates[0]
      Out-Status ("Recovered snapshot T"+$slot+" using PID and exact filename in HeapTrace directory.")
    }
    if($accepted.Length -lt 256) {throw ("Snapshot T"+$slot+" is too small: capture cannot be trusted.")}
    $resolved[$property]=$accepted
  }
  if($resolved.first.LastWriteTimeUtc -gt $resolved.second.LastWriteTimeUtc) {
    throw 'T1 appears newer than T2; refusing out-of-order comparison.'
  }
  $session.first=$resolved.first.FullName
  $session.second=$resolved.second.FullName
  return $session
}
function Make-SafeSummary([string]$raw,[string]$safe) {
  $rows=New-Object System.Collections.Generic.List[object];$current=$null
  foreach($line in [IO.File]::ReadLines($raw)) {
    $m=[regex]::Match($line,'^\s*([+-])\s+(?:0x)?([0-9a-fA-F]{1,16})\s+\([^)]*\).*?BackTrace[0-9a-fA-F]+')
    if($m.Success) {
      $delta=[Convert]::ToInt64($m.Groups[2].Value,16)
      if($m.Groups[1].Value -eq '-') {$delta=-$delta}
      $current=[PSCustomObject]@{delta=$delta;module='unknown';index=$rows.Count+1}
      $rows.Add($current);continue
    }
    if($null -eq $current -or $current.module -ne 'unknown') {continue}
    # Only copy a DLL basename, never paths, PDB strings, symbols or addresses.
    $dll=[regex]::Match($line,'(?i)([a-z][a-z0-9_.-]{1,63}\.dll)![a-z_?@$]')
    if($dll.Success) {$current.module=$dll.Groups[1].Value.ToLowerInvariant()}
  }
  $total=0L;foreach($r in $rows) {$total += [long]$r.delta}
  $out=New-Object System.Collections.Generic.List[string]
  $out.Add('C545D HEAP SAFE SUMMARY V1')
  $out.Add('raw_snapshots_included=no')
  $out.Add('parsed_backtraces='+$rows.Count)
  $out.Add('parsed_net_delta_bytes='+$total)
  $out.Add('Note: this is Windows Heap, not all Private Memory.')
  $out.Add('Note: missing symbols/other allocators may limit attribution.')
  $out.Add('rank,delta_bytes,first_dll')
  $top=@($rows|Sort-Object delta -Descending|Select-Object -First 30)
  foreach($r in $top) {$out.Add(('{0},{1},{2}' -f $r.index,$r.delta,$r.module))}
  [IO.File]::WriteAllLines($safe,[string[]]$out,(New-Object Text.UTF8Encoding($false)))
  return $rows.Count
}
if($Mode -eq 'SelfTest') {
  $isElevated=Is-Admin
  if($isElevated -isnot [bool]) {throw 'Privilege-check test failed'}
  $dir=Join-Path $env:TEMP ('c545d-heap-selftest-'+[guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $dir|Out-Null
  try {
    $raw=Join-Path $dir 'raw.txt';$safe=Join-Path $dir 'safe.txt'
    @('+ 5320 ( f110 - 9df0) 3a allocs BackTrace00B53',
      'C:\Users\PRIVATE123\secret\avcodec-61.dll!sensitive_symbol+0x12',
      'token=DO_NOT_LEAK_USERNAME',
      '+ 0100 ( 0200 - 0100) 01 allocs BackTrace001',
      'glib-2.0-0.dll!another_symbol+0x10')|Set-Content -LiteralPath $raw -Encoding UTF8
    $n=Make-SafeSummary $raw $safe;$txt=[IO.File]::ReadAllText($safe)
    if($n -ne 2 -or $txt -notmatch '21280' -or
       $txt -notmatch 'avcodec-61.dll' -or
       $txt -match 'PRIVATE123|DO_NOT_LEAK|secret\\|sensitive_symbol') {
       throw 'Safe diff self-test failed'
    }
    Out-Status 'PASS safe UMDH parser and synthetic credential exclusion.'
  } finally {Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue}
  exit 0
}
if($Mode -eq 'Check') {
  Out-Status ('gflags.exe: '+$(if(Find-Tool 'gflags.exe'){'FOUND'}else{'MISSING'}))
  Out-Status ('umdh.exe: '+$(if(Find-Tool 'umdh.exe'){'FOUND'}else{'MISSING'}))
  Out-Status ('UST for gst-launch: '+$(if(Is-USTEnabled){'ON'}else{'OFF'}))
  Out-Status ('gst-launch processes: '+@(Get-Process -Name 'gst-launch-1.0' -ErrorAction SilentlyContinue).Count)
  Out-Status 'Read-only check completed; no GFlags, processes, or MP4 changed.'
  exit 0
}
$tools=Need-Tools
if($Mode -in @('Enable','Restore') -and -not (Is-Admin)) {
  throw 'Enable/Restore require Administrator PowerShell. Do NOT run recorder as admin.'
}
if($Mode -eq 'Enable') {
  if(@(Get-Process -Name 'gst-launch-1.0' -ErrorAction SilentlyContinue).Count -gt 0) {
    throw 'Use GUI Stop to finalize current MP4 before enabling UST. No process touched.'
  }
  if(Is-USTEnabled) {
    Out-Status 'UST already enabled. Did NOT modify it; Restore will not remove another user setting.'
    exit 0
  }
  New-Item -ItemType Directory -Path $DataRoot -Force|Out-Null
  & $tools.gflags '/i' $imageName '+ust'|Out-Null
  if($LASTEXITCODE -ne 0 -or -not (Is-USTEnabled)) {throw 'Could not verify +ust'}
  Save-Json $stateFile @{image=$imageName;marker='C545D-v1'}
  Out-Status 'UST enabled for future gst-launch instances. Restart recorder normally via Launch mode.'
  exit 0
}
if($Mode -eq 'Restore') {
  if(-not (Test-Path -LiteralPath $stateFile -PathType Leaf)) {
    Out-Status 'No ownership marker. Not changing someone else’s GFlags setting.';exit 0
  }
  $marker=Get-Content -LiteralPath $stateFile -Raw|ConvertFrom-Json
  if($marker.marker -ne 'C545D-v1' -or $marker.image -ne $imageName) {
    throw 'Invalid ownership marker; refusing to change UST.'
  }
  & $tools.gflags '/i' $imageName '-ust'|Out-Null
  if($LASTEXITCODE -ne 0 -or (Is-USTEnabled)) {throw 'Could not verify -ust; marker preserved'}
  Remove-Item -LiteralPath $stateFile -Force
  Out-Status 'UST restored OFF for future gst-launch; recordings untouched.'
  exit 0
}
if($Mode -eq 'Launch') {
  if(-not (Is-USTEnabled)) {throw 'UST not enabled (start with Enable after normal stop).'}
  if(Is-Admin) {throw 'Launch RC35 in ordinary PowerShell; not as Administrator.'}
  if(@(Get-Process -Name 'gst-launch-1.0' -ErrorAction SilentlyContinue).Count -gt 0) {
    throw 'Another gst-launch already active. Do not run dual recorders.'
  }
  if(-not $ExePath -or -not (Test-Path -LiteralPath $ExePath -PathType Leaf) -or
     [IO.Path]::GetFileName($ExePath) -ne 'C545D_Recorder.exe') {throw 'Supply -ExePath path to RC35 C545D_Recorder.exe'}
  $old=[Environment]::GetEnvironmentVariable('OANOCACHE','Process')
  try {
    [Environment]::SetEnvironmentVariable('OANOCACHE','1','Process')
    Start-Process -FilePath $ExePath -WorkingDirectory (Split-Path -Parent $ExePath)
  } finally {[Environment]::SetEnvironmentVariable('OANOCACHE',$old,'Process')}
  Out-Status 'RC35 started (process-only OANOCACHE=1). Use its normal Record button.'
  exit 0
}
if($Mode -eq 'Capture') {
  if(-not (Is-USTEnabled)) {throw 'UST OFF; cannot retrieve past heap stacks retrospectively.'}
  $p=Live-Gst
  $start=[long]$p.StartTime.ToUniversalTime().Ticks
  New-Item -ItemType Directory -Path $DataRoot -Force|Out-Null
  $s=$null
  if(Test-Path -LiteralPath $sessionFile) {
    $s=Read-Json $sessionFile
  }
  $second=($s -and $s.first -and -not $s.second)
  if($second) {
    if([int]$s.pid -ne [int]$p.Id -or [long]$s.start_ticks -ne $start) {
      throw 'PID/start time differs from first capture. Refusing cross-session comparison.'
    }
  } else {
    $s=[ordered]@{pid=[int]$p.Id;start_ticks=$start;first=$null;second=$null;
      first_private_mb=$null;second_private_mb=$null;first_at=$null;second_at=$null}
  }
  $num=if($second){2}else{1}
  $where=Join-Path $DataRoot ('UMDH_RAW_PID'+$p.Id+'_T'+$num+'_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'.txt')
  if(-not $env:_NT_SYMBOL_PATH) {
    $env:_NT_SYMBOL_PATH='srv*'+(Join-Path $DataRoot 'Symbols')+'*https://msdl.microsoft.com/download/symbols'
  }
  & $tools.umdh ('-p:'+$p.Id) ('-f:'+$where) 2>&1|Out-Null
  if($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $where) -or
    (Get-Item -LiteralPath $where).Length -lt 256) {
    throw 'UMDH failed or empty; keep recorder running and check access/UST.'
  }
  $memory=[math]::Round($p.PrivateMemorySize64/1MB,2)
  $at=(Get-Date).ToString('o')
  if($second){$s.second=$where;$s.second_private_mb=$memory;$s.second_at=$at}
  else {$s.first=$where;$s.first_private_mb=$memory;$s.first_at=$at}
  Save-Json $sessionFile $s
  Out-Status ('Saved RAW snapshot '+$num+' (same PID) locally, Private='+$memory+'MB.')
  if(-not $second){Out-Status 'Continue recording ~15 minutes, then Capture again.'}
  else {Out-Status 'Capture 2 done. Use Compare, then Restore UST.'}
  exit 0
}
if($Mode -eq 'Compare') {
  if(-not (Test-Path -LiteralPath $sessionFile -PathType Leaf)) {throw 'No capture state.'}
  $s=Read-Json $sessionFile
  if(-not $s.first -or -not $s.second -or
    -not (Test-Path -LiteralPath $s.first) -or -not (Test-Path -LiteralPath $s.second)) {
    throw 'Two captures of one process are required.'
  }
  $raw=Join-Path $DataRoot ('UMDH_RAW_DIFF_PID'+$s.pid+'.txt')
  & $tools.umdh $s.first $s.second 2>&1|Out-File -LiteralPath $raw -Encoding UTF8
  if($LASTEXITCODE -ne 0) {throw 'UMDH comparison failed.'}
  $safe=Join-Path $DataRoot ('C545D_HEAP_SAFE_SUMMARY_PID'+$s.pid+'.txt')
  $n=Make-SafeSummary $raw $safe
  if($n -eq 0) {throw 'UMDH diff format unknown: keeping raw local; do not infer no leak.'}
  Add-Content -LiteralPath $safe -Value ('private_before_mb='+$s.first_private_mb)
  Add-Content -LiteralPath $safe -Value ('private_after_mb='+$s.second_private_mb)
  Add-Content -LiteralPath $safe -Value ('elapsed_minutes='+[math]::Round((([datetime]$s.second_at)-([datetime]$s.first_at)).TotalMinutes,2))
  $zip=Join-Path $DataRoot ('C545D_HEAP_SAFE_REPORT_PID'+$s.pid+'.zip')
  if(Test-Path -LiteralPath $zip) {Remove-Item -LiteralPath $zip -Force}
  Compress-Archive -LiteralPath $safe -DestinationPath $zip -CompressionLevel Optimal
  Out-Status ('Heap backtraces compared: '+$n+'. Upload ONLY: '+$zip)
  Out-Status 'Raw UMDH snapshots/diff kept locally and not uploaded.'
  exit 0
}
throw 'Unknown action'