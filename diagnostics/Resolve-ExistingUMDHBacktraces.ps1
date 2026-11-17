# C545D diagnostic: offline join of existing UMDH difference with original T2 snapshot.
# No UST/GFlags change, no process capture, no recorder restart. Raw stack data is
# consumed locally and NEVER written into the safe output.
[CmdletBinding()]
param(
  [ValidateSet('Analyze','SelfTest')][string]$Mode='Analyze',
  [ValidateRange(1,2147483647)][int]$TargetPid=9424,
  [string]$ToolsDir='',
  [string]$DataRoot=(Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\HeapTrace')
)
$ErrorActionPreference='Stop'
function Normalize-TraceId([string]$value) {
  $s=$value.ToUpperInvariant().TrimStart([char]'0')
  if(-not $s) {return '0'}
  return $s
}
function Find-UMDH {
  if($ToolsDir) {
    $p=Join-Path $ToolsDir 'umdh.exe'
    if(Test-Path -LiteralPath $p -PathType Leaf) {return $p}
    throw 'umdh.exe not found in ToolsDir.'
  }
  foreach($b in @($env:ProgramFiles,[Environment]::GetEnvironmentVariable('ProgramFiles(x86)'))) {
    if(-not $b) {continue}
    $p=Join-Path $b 'Windows Kits\10\Debuggers\x64\umdh.exe'
    if(Test-Path -LiteralPath $p -PathType Leaf) {return $p}
  }
  $cmd=Get-Command 'umdh.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
  if($cmd) {return $cmd.Source}
  throw 'Existing Debugging Tools x64 UMDH not found. No new capture needed.'
}
function Read-TopDiff([string]$diff,[int]$count) {
  if(-not (Test-Path -LiteralPath $diff -PathType Leaf)) {throw 'Existing UMDH diff file not found.'}
  $items=New-Object 'System.Collections.Generic.List[object]'
  foreach($line in [IO.File]::ReadLines($diff)) {
    $m=[regex]::Match($line,'(?i)^\s*\+\s+(?:0x)?([0-9a-f]{1,15})\s+\([^)]*\).*?\bBackTrace([0-9a-f]+)\b')
    if(-not $m.Success) {continue}
    $value=[Convert]::ToInt64($m.Groups[1].Value,16)
    if($value -le 0) {continue}
    $id=Normalize-TraceId $m.Groups[2].Value
    [void]$items.Add([PSCustomObject]@{delta=[long]$value;id=$id})
  }
  if($items.Count -lt $count) {throw 'Fewer positive BackTrace entries than requested; raw evidence unchanged.'}
  return @($items | Sort-Object delta -Descending | Select-Object -First $count)
}
function Classify-Frame([string]$line) {
  # Source paths, addresses and function names are never copied.
  $m=[regex]::Match($line,'(?i)(?:^|[^a-z0-9_.-])([a-z][a-z0-9_.-]{1,63})!\S')
  if(-not $m.Success) {
    if($line -match '(?i)\b0x[0-9a-f]{8,16}\b') {return 'address-only'}
    return ''
  }
  $stem=($m.Groups[1].Value.ToLowerInvariant() -replace '\.dll$','')
  if($stem -match '^(ntdll|kernel32|kernelbase|ucrtbase|msvcrt|win32u|combase|rpcrt4|vcruntime[0-9_.-]*|msvcp[0-9_.-]*)$') {
    return 'windows-runtime'
  }
  # Known, safe module families. Never export arbitrary module identifiers.
  if($stem -match '^(gstvideoparsersbad|gstc545dsei|gstcoreelements|gstrtpmanager|gstlibav|gstrtp|gstrtsp|gstrtspconnection|gstvideo|gstbase|gstreamer-1.0-0|libgstreamer-1.0-0)$') {
    return $stem
  }
  if($stem -match '^(?:lib)?(?:glib|gobject|gio)-2[._-]0(?:[._-]0)?$') {return 'glib-family'}
  if($stem -match '^(?:lib)?(?:avcodec|avutil|avformat|swscale|swresample)(?:-[0-9]+)?$') {return 'ffmpeg-family'}
  if($stem -match '^(?:lib)?x264(?:-[0-9]+)?$') {return 'x264-family'}
  return 'other-module'
}
function New-Context([object[]]$top) {
  $wanted=@{}
  $rank=0
  foreach($x in $top) {
    $rank++
    if($wanted.ContainsKey($x.id)) {throw 'Duplicate normalized BackTrace ID in selected entries.'}
    $wanted[$x.id]=[PSCustomObject]@{
      rank=$rank;delta=$x.delta;found=$false
      windows=0;other=0;addresses=0;recognized=0;nonempty=0;module='unknown'
    }
  }
  return @{wanted=$wanted;active=$null;headers=0}
}
function Feed-AnalyzedLine([hashtable]$ctx,[string]$line) {
  # Microsoft UMDH single-log output: "... bytes ... by: BackTrace00B53"
  $header=[regex]::Match($line,'(?i)\bby\s*:\s*BackTrace([0-9a-f]+)\b')
  if($header.Success) {
    $ctx.headers++
    $id=Normalize-TraceId $header.Groups[1].Value
    if($ctx.wanted.ContainsKey($id)) {
      $ctx.active=$ctx.wanted[$id]
      $ctx.active.found=$true
    } else {$ctx.active=$null}
    return
  }
  $row=$ctx.active
  if($null -eq $row) {return}
  if([string]::IsNullOrWhiteSpace($line)) {$ctx.active=$null;return}
  # Drop data unrelated to an actual stack line. Only count recognizable
  # module symbols or address-like frames. Never emit the source text.
  $class=Classify-Frame $line
  if(-not $class) {return}
  $row.nonempty++
  if($class -eq 'windows-runtime') {$row.windows++}
  elseif($class -eq 'address-only') {$row.addresses++}
  elseif($class -eq 'other-module') {$row.other++}
  else {
    $row.recognized++
    if($row.module -eq 'unknown') {$row.module=$class}
  }
}
function Make-SafeOutput([hashtable]$ctx,[string]$dest) {
  $out=New-Object 'System.Collections.Generic.List[string]'
  [void]$out.Add('C545D SAFE ORIGINAL BACKTRACE JOIN V1')
  [void]$out.Add('raw_snapshots_included=no')
  [void]$out.Add('raw_diff_included=no')
  [void]$out.Add('source_paths_included=no')
  [void]$out.Add('function_symbols_included=no')
  [void]$out.Add('offline_single_snapshot_analysis=yes')
  [void]$out.Add('interpreted_stack_headers_seen='+$ctx.headers)
  [void]$out.Add('rank,delta_bytes,found_in_T2,stack_category,allowlisted_module,windows_frames,known_media_frames,other_module_frames,address_only_frames')
  foreach($r in @($ctx.wanted.Values | Sort-Object rank)) {
    $category='not-found-in-analyzed-T2'
    if($r.found) {
      if($r.recognized -gt 0) {$category='known-media-module-present'}
      elseif($r.other -gt 0) {$category='other-module-symbol-present'}
      elseif($r.windows -gt 0) {$category='windows-runtime-only'}
      elseif($r.addresses -gt 0) {$category='address-only'}
      else {$category='found-but-no-decoded-frames'}
    }
    [void]$out.Add(('{0},{1},{2},{3},{4},{5},{6},{7},{8}' -f
      $r.rank,$r.delta,$r.found.ToString().ToLowerInvariant(),$category,
      $r.module,$r.windows,$r.recognized,$r.other,$r.addresses))
  }
  [void]$out.Add('Note: matching original BackTrace ids is required; a diff alone may omit stacks.')
  [void]$out.Add('Note: module presence is a call-stack hint, not proof of leak ownership.')
  [void]$out.Add('Note: Windows Heap allocations are not all Private Memory.')
  [IO.File]::WriteAllLines($dest,[string[]]$out,(New-Object Text.UTF8Encoding($false)))
}
function Run-OfflineUMDH([string]$exe,[string]$snapshot,[hashtable]$ctx) {
  $psi=New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName=$exe
  # Only the snapshot path is passed to UMDH. Do not use -p or -v.
  $psi.Arguments='"'+$snapshot+'"'
  $psi.UseShellExecute=$false
  $psi.CreateNoWindow=$true
  $psi.RedirectStandardOutput=$true
  $psi.RedirectStandardError=$true
  $proc=New-Object System.Diagnostics.Process
  $proc.StartInfo=$psi
  try {
    if(-not $proc.Start()) {throw 'Unable to start offline UMDH analysis.'}
    $stderrTask=$proc.StandardError.ReadToEndAsync()
    while($null -ne ($line=$proc.StandardOutput.ReadLine())) {
      Feed-AnalyzedLine $ctx $line
    }
    $proc.WaitForExit()
    $null=$stderrTask.GetAwaiter().GetResult()
    if($proc.ExitCode -ne 0) {throw ('Offline UMDH exit code '+$proc.ExitCode+'. No raw logs modified.')}
    if($ctx.headers -eq 0) {throw 'No recognized BackTrace section in offline UMDH output. No new capture required.'}
  } finally {
    if(-not $proc.HasExited) {$proc.Kill()}
    $proc.Dispose()
  }
}
if($Mode -eq 'SelfTest') {
  $dir=Join-Path $env:TEMP ('c545d-backtrace-selftest-'+[guid]::NewGuid().ToString('N'))
  [void](New-Item -ItemType Directory -Path $dir -Force)
  try {
    $diff=Join-Path $dir 'diff.txt'
    @(
      '+ 5d000 (5d000 - 0000) 1 allocs BackTrace00B53'
      '+ 2b800 (2b800 - 0000) 1 allocs BackTrace00046'
      '+ 17000 (17000 - 0000) 1 allocs BackTrace00089'
    ) | Set-Content -LiteralPath $diff -Encoding ASCII
    $top=@(Read-TopDiff $diff 3)
    $ctx=New-Context $top
    @(
      '00005d000 bytes in 0x1 allocations (@ 0x1) by: BackTrace000B53'
      'ntdll!RtlAllocateHeap+0x00000002'
      'C:\Users\PRIVATE123\secret\gstvideoparsersbad!ParseNAL+0x1'
      ''
      '00002b800 bytes in 0x1 allocations (@ 0x1) by: BackTrace00046'
      'ntdll!RtlAllocateHeap+0x00000002'
      ''
      '000017000 bytes in 0x1 allocations (@ 0x1) by: BackTrace00089'
      '0x00007FFABCDEF012'
      'password=DO_NOT_EXPORT_THIS'
    ) | ForEach-Object {Feed-AnalyzedLine $ctx $_}
    $safe=Join-Path $dir 'safe.txt'
    Make-SafeOutput $ctx $safe
    $txt=[IO.File]::ReadAllText($safe)
    if($txt -notmatch '1,380928,true,known-media-module-present,gstvideoparsersbad,1,1,0,0' -or
       $txt -notmatch '2,178176,true,windows-runtime-only,unknown,1,0,0,0' -or
       $txt -notmatch '3,94208,true,address-only,unknown,0,0,0,1' -or
       $txt -match 'PRIVATE123|DO_NOT_EXPORT_THIS|secret|ParseNAL|RtlAllocateHeap|0x00007FFA') {
      throw 'Original-snapshot BackTrace join / privacy self-test failed.'
    }
    Write-Host '[C545D] PASS original T2 BackTrace join, ranked deltas, module categories and privacy.'
  } finally {Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue}
  exit 0
}
if(-not (Test-Path -LiteralPath $DataRoot -PathType Container)) {throw 'Saved HeapTrace directory is missing. No recapture requested.'}
$diff=Join-Path $DataRoot ('UMDH_RAW_DIFF_PID'+$TargetPid+'.txt')
$top=@(Read-TopDiff $diff 3)
$snapshots=@(Get-ChildItem -LiteralPath $DataRoot -File -Filter ('UMDH_RAW_PID'+$TargetPid+'_T2_*.txt') |
  Where-Object {$_.Name -match ('^UMDH_RAW_PID'+$TargetPid+'_T2_[0-9]{8}_[0-9]{6}[.]txt$')})
if($snapshots.Count -ne 1) {throw ('Expected exactly one T2 raw snapshot; found '+$snapshots.Count+'. No files modified.')}
if($snapshots[0].Length -lt 256) {throw 'Original T2 snapshot too small; raw data unchanged.'}
$umdh=Find-UMDH
$ctx=New-Context $top
Run-OfflineUMDH $umdh $snapshots[0].FullName $ctx
$safe=Join-Path $DataRoot ('C545D_SAFE_ORIGINAL_BACKTRACES_PID'+$TargetPid+'.txt')
$zip=Join-Path $DataRoot ('C545D_SAFE_ORIGINAL_BACKTRACES_PID'+$TargetPid+'.zip')
Make-SafeOutput $ctx $safe
if(Test-Path -LiteralPath $zip -PathType Leaf) {Remove-Item -LiteralPath $zip -Force}
Compress-Archive -LiteralPath $safe -DestinationPath $zip -CompressionLevel Optimal
Write-Host '[C545D] Existing T2 analyzed offline. No capture, UST, GFlags or recording changes.'
Write-Host ('[C545D] BackTrace headers analyzed: '+$ctx.headers)
Write-Host ('[C545D] Upload ONLY: '+[IO.Path]::GetFileName($zip))
