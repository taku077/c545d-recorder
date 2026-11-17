# Read-only offline UMDH differential reanalysis for C545D recorder.
# Does not invoke UMDH, change GFlags, touch recordings, or emit raw stack/path data.
[CmdletBinding()]
param(
  [ValidateSet('Analyze','SelfTest')][string]$Mode='Analyze',
  [ValidateRange(1,2147483647)][int]$TargetPid=9424,
  [string]$DataRoot=(Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\HeapTrace')
)
$ErrorActionPreference='Stop'
function Safe-Module([string]$line) {
  # Symbols are generally written as "ntdll!Function" or "avcodec-61!Symbol",
  # NOT necessarily "example.dll!Symbol". Do not emit untrusted paths or symbols.
  $match=[regex]::Match($line,'(?i)(?:^|[^a-z0-9_.-])([a-z][a-z0-9_.-]{1,63})!\S')
  if(-not $match.Success) {return ''}
  $name=$match.Groups[1].Value.ToLowerInvariant()
  $stem=$name -replace '\.dll$',''
  if($stem -match '^(?:ntdll|kernel32|kernelbase|ucrtbase|msvcrt|vcruntime[0-9_]*|msvcp[0-9_]*|win32u|combase|rpcrt4)$') {
    return 'windows-runtime'
  }
  if($stem -match '^(?:(?:lib)?gst[a-z0-9_.-]*|(?:lib)?glib[a-z0-9_.-]*|(?:lib)?gobject[a-z0-9_.-]*|(?:lib)?gio[a-z0-9_.-]*|(?:lib)?avcodec[a-z0-9_.-]*|(?:lib)?avutil[a-z0-9_.-]*|(?:lib)?swscale[a-z0-9_.-]*|(?:lib)?swresample[a-z0-9_.-]*|(?:lib)?x264[a-z0-9_.-]*|(?:lib)?openh264[a-z0-9_.-]*|c545d[a-z0-9_.-]*)$') {
    return $name
  }
  # Unknown module basenames may be user-chosen or sensitive. No arbitrary names.
  return 'other-module'
}
function Build-SafeDiff([string]$rawFile,[string]$safeFile) {
  $rows=New-Object 'System.Collections.Generic.List[object]'
  $current=$null
  foreach($line in [IO.File]::ReadLines($rawFile)) {
    $match=[regex]::Match($line,'^\s*([+-])\s+(?:0x)?([0-9a-fA-F]{1,16})\s+\([^)]*\).*?BackTrace[0-9a-fA-F]+')
    if($match.Success) {
      $delta=[Convert]::ToInt64($match.Groups[2].Value,16)
      if($match.Groups[1].Value -eq '-') {$delta=-$delta}
      $current=[PSCustomObject]@{index=$rows.Count+1;delta=[long]$delta;preferred='unknown';fallback='unknown'}
      [void]$rows.Add($current)
      continue
    }
    if($null -eq $current) {continue}
    $mod=Safe-Module $line
    if(-not $mod) {continue}
    if($current.fallback -eq 'unknown') {$current.fallback=$mod}
    if($current.preferred -eq 'unknown' -and $mod -ne 'windows-runtime') {
      $current.preferred=$mod
    }
  }
  if($rows.Count -eq 0) {throw 'No valid UMDH BackTrace delta records. Preserve RAW files; no leak conclusion.'}
  $net=0L;$positive=0L;$negative=0L;$known=0;$other=0
  foreach($r in $rows) {
    $net += [long]$r.delta
    if($r.delta -gt 0) {$positive += [long]$r.delta}
    if($r.delta -lt 0) {$negative += [long]$r.delta}
    if($r.preferred -ne 'unknown' -and $r.preferred -ne 'other-module') {$known++}
    if($r.preferred -eq 'other-module') {$other++}
  }
  $lines=New-Object 'System.Collections.Generic.List[string]'
  [void]$lines.Add('C545D HEAP SAFE SUMMARY V2 (offline reanalysis)')
  [void]$lines.Add('raw_snapshots_included=no')
  [void]$lines.Add('raw_diff_included=no')
  [void]$lines.Add('parsed_backtraces='+$rows.Count)
  [void]$lines.Add('parsed_net_delta_bytes='+$net)
  [void]$lines.Add('parsed_positive_delta_bytes='+$positive)
  [void]$lines.Add('parsed_negative_delta_bytes='+$negative)
  [void]$lines.Add('recognized_non_system_traces='+$known)
  [void]$lines.Add('other_module_traces='+$other)
  [void]$lines.Add('Note: UMDH tracks selected Windows Heap allocations, not all Private Memory.')
  [void]$lines.Add('Note: module attribution is a stack hint, not proof of ownership or leak.')
  [void]$lines.Add('Note: other-module and unknown deliberately suppress arbitrary names/symbols.')
  [void]$lines.Add('rank,delta_bytes,non_system_module')
  $top=@($rows|Where-Object {$_.delta -gt 0}|Sort-Object delta -Descending|Select-Object -First 30)
  foreach($r in $top) {[void]$lines.Add(('{0},{1},{2}' -f $r.index,$r.delta,$r.preferred))}
  [IO.File]::WriteAllLines($safeFile,[string[]]$lines,(New-Object Text.UTF8Encoding($false)))
  return $rows.Count
}
if($Mode -eq 'SelfTest') {
  $temp=Join-Path $env:TEMP ('c545d-reanalysis-'+[guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $temp|Out-Null
  try {
    $raw=Join-Path $temp 'raw-private.txt'
    $safe=Join-Path $temp 'safe.txt'
    @(
      '+ 5320 ( f110 - 9df0) 3a allocs BackTrace00B53',
      'C:\Users\PRIVATE123\secrets\ntdll!RtlAllocateHeap+0x01',
      'C:\Users\PRIVATE123\secrets\avcodec-61!av_malloc+0x02',
      'token=DO_NOT_LEAK',
      '- 0010 ( 0010 - 0020) 1 allocs BackTrace00054',
      'kernelbase!HeapFree+0x1',
      'glib-2.0-0.dll!g_free+0x1'
    ) | Set-Content -LiteralPath $raw -Encoding UTF8
    [void](Build-SafeDiff $raw $safe)
    $result=[IO.File]::ReadAllText($safe)
    if($result -notmatch 'parsed_backtraces=2' -or
       $result -notmatch 'parsed_net_delta_bytes=21264' -or
       $result -notmatch '1,21280,avcodec-61' -or
       $result -match 'PRIVATE123|DO_NOT_LEAK|secrets|av_malloc|RtlAllocateHeap') {
      throw 'Offline diff attribution and privacy self-test failed.'
    }
    Write-Host '[C545D] PASS offline UMDH module attribution, hex deltas, privacy gate.'
  } finally {Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue}
  exit 0
}
if(-not (Test-Path -LiteralPath $DataRoot -PathType Container)) {throw 'HeapTrace data directory not found. No recapture requested.'}
$rawDiff=Join-Path $DataRoot ('UMDH_RAW_DIFF_PID'+$TargetPid+'.txt')
if(-not (Test-Path -LiteralPath $rawDiff -PathType Leaf)) {throw 'Existing raw UMDH diff not found. No recapture requested.'}
$summary=Join-Path $DataRoot ('C545D_HEAP_SAFE_SUMMARY_PID'+$TargetPid+'_V2.txt')
$zip=Join-Path $DataRoot ('C545D_HEAP_SAFE_REPORT_PID'+$TargetPid+'_V2.zip')
$n=Build-SafeDiff $rawDiff $summary
if(Test-Path -LiteralPath $zip) {Remove-Item -LiteralPath $zip -Force}
Compress-Archive -LiteralPath $summary -DestinationPath $zip -CompressionLevel Optimal
Write-Host ('[C545D] Reanalyzed '+$n+' historical UMDH deltas; no new measurement.')
Write-Host ('[C545D] Upload ONLY: '+$zip)
Write-Host '[C545D] Raw logs, diff, symbols and recordings remain local.'
