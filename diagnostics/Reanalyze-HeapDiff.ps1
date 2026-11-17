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

# V3 uses numeric and allowlisted categories only. It distinguishes a
# Windows-runtime-only stack from a stack with no parseable module symbols.
function Build-SafeStackClass([string]$rawFile,[string]$safeFile) {
  $rows=New-Object 'System.Collections.Generic.List[object]'
  $current=$null
  foreach($line in [IO.File]::ReadLines($rawFile)) {
    $m=[regex]::Match($line,'^\s*([+-])\s+(?:0x)?([0-9a-fA-F]{1,16})\s+\([^)]*\).*?BackTrace[0-9a-fA-F]+')
    if($m.Success) {
      $delta=[Convert]::ToInt64($m.Groups[2].Value,16)
      if($m.Groups[1].Value -eq '-') {$delta=-$delta}
      $current=[PSCustomObject]@{
        rank=$rows.Count+1;delta=[long]$delta;module='unknown'
        windows=0;non_system=0;other=0;address_like=0;nonempty=0
      }
      [void]$rows.Add($current)
      continue
    }
    if($null -eq $current -or [string]::IsNullOrWhiteSpace($line)) {continue}
    $current.nonempty++
    $mod=Safe-Module $line
    if($mod -eq 'windows-runtime') {$current.windows++;continue}
    if($mod -eq 'other-module') {$current.other++;continue}
    if($mod) {
      $current.non_system++
      if($current.module -eq 'unknown') {$current.module=$mod}
      continue
    }
    # This is only a shape indicator; a hexadecimal-looking line need not
    # actually be a valid stack frame. Never emit the actual address.
    if($line -match '^\s*(?:0x)?[0-9a-fA-F]{8,16}(?:\s|$)' -or
       $line -match '(?i)\b0x[0-9a-f]{8,16}\b') {
      $current.address_like++
    }
  }
  if($rows.Count -eq 0) {throw 'No valid UMDH delta records; no recapture required.'}
  $net=0L;$pos=0L;$neg=0L
  $counters=@{};$bytes=@{}
  foreach($r in $rows) {
    $net += [long]$r.delta
    if($r.delta -gt 0) {$pos += [long]$r.delta}
    if($r.delta -lt 0) {$neg += [long]$r.delta}
    $category='no-recognized-frames'
    if($r.non_system -gt 0) {$category='recognized-non-system'}
    elseif($r.other -gt 0) {$category='other-module-symbol'}
    elseif($r.windows -gt 0) {$category='windows-runtime-only'}
    elseif($r.address_like -gt 0) {$category='address-like-no-symbol'}
    $r | Add-Member -NotePropertyName category -NotePropertyValue $category
    if($r.delta -gt 0) {
      if(-not $counters.ContainsKey($category)) {$counters[$category]=0;$bytes[$category]=0L}
      $counters[$category]++
      $bytes[$category] += [long]$r.delta
    }
  }
  $out=New-Object 'System.Collections.Generic.List[string]'
  [void]$out.Add('C545D HEAP SAFE SUMMARY V3 (offline stack classification)')
  [void]$out.Add('raw_snapshots_included=no')
  [void]$out.Add('raw_diff_included=no')
  [void]$out.Add('parsed_backtraces='+$rows.Count)
  [void]$out.Add('parsed_net_delta_bytes='+$net)
  [void]$out.Add('parsed_positive_delta_bytes='+$pos)
  [void]$out.Add('parsed_negative_delta_bytes='+$neg)
  foreach($category in @('recognized-non-system','windows-runtime-only',
      'other-module-symbol','address-like-no-symbol','no-recognized-frames')) {
    $count=0;$amount=0L
    if($counters.ContainsKey($category)) {$count=$counters[$category];$amount=$bytes[$category]}
    [void]$out.Add(('positive_{0}_traces={1}' -f $category,$count))
    [void]$out.Add(('positive_{0}_bytes={1}' -f $category,$amount))
  }
  [void]$out.Add('Note: windows-runtime-only means only system symbols recognized, not proved allocation owner.')
  [void]$out.Add('Note: address-like counts are line-shape hints, not verified stack frames.')
  [void]$out.Add('Note: no-recognized-frames may be a symbol, encoding, or format limitation.')
  [void]$out.Add('Note: Windows Heap delta is not process Private Memory delta; no leak claim.')
  [void]$out.Add('rank,delta_bytes,category,allowlisted_module,windows_symbol_lines,known_symbol_lines,other_symbol_lines,address_like_lines,nonempty_lines')
  $top=@($rows | Where-Object {$_.delta -gt 0} | Sort-Object delta -Descending | Select-Object -First 30)
  foreach($r in $top) {
    [void]$out.Add(('{0},{1},{2},{3},{4},{5},{6},{7},{8}' -f
      $r.rank,$r.delta,$r.category,$r.module,$r.windows,$r.non_system,
      $r.other,$r.address_like,$r.nonempty))
  }
  [IO.File]::WriteAllLines($safeFile,[string[]]$out,(New-Object Text.UTF8Encoding($false)))
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

    $classRaw=Join-Path $temp 'class-raw.txt'
    $classSafe=Join-Path $temp 'class-safe.txt'
    @(
      '+ 5d000 ( 5d000 - 0000) 1 allocs BackTraceAAA',
      'C:\Users\PRIVATE123\secrets\ntdll!RtlAllocateHeap+0x12',
      '+ 2b800 ( 2b800 - 0000) 1 allocs BackTraceAAB',
      '0x00007FFABCDEF012',
      '+ 17000 ( 17000 - 0000) 1 allocs BackTraceAAC',
      'C:\Users\PRIVATE123\secrets\glib-2.0-0!g_malloc',
      'password=DO_NOT_LEAK'
    ) | Set-Content -LiteralPath $classRaw -Encoding UTF8
    [void](Build-SafeStackClass $classRaw $classSafe)
    $classified=[IO.File]::ReadAllText($classSafe)
    if($classified -notmatch '1,380928,windows-runtime-only,unknown,1,0,0,' -or
       $classified -notmatch '2,178176,address-like-no-symbol,unknown,0,0,0,1,' -or
       $classified -notmatch '3,94208,recognized-non-system,glib-2.0-0,0,1,0,' -or
       $classified -match 'PRIVATE123|DO_NOT_LEAK|password|g_malloc|RtlAllocateHeap|0x00007FFA') {
      throw 'V3 safe stack category and privacy self-test failed.'
    }
    Write-Host '[C545D] PASS positive stack class, Windows-only, address-only and privacy gate.'

  } finally {Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue}
  exit 0
}
if(-not (Test-Path -LiteralPath $DataRoot -PathType Container)) {throw 'HeapTrace data directory not found. No recapture requested.'}
$rawDiff=Join-Path $DataRoot ('UMDH_RAW_DIFF_PID'+$TargetPid+'.txt')
if(-not (Test-Path -LiteralPath $rawDiff -PathType Leaf)) {throw 'Existing raw UMDH diff not found. No recapture requested.'}
$summary=Join-Path $DataRoot ('C545D_HEAP_SAFE_SUMMARY_PID'+$TargetPid+'_V3.txt')
$zip=Join-Path $DataRoot ('C545D_HEAP_SAFE_REPORT_PID'+$TargetPid+'_V3.zip')
$n=Build-SafeStackClass $rawDiff $summary
if(Test-Path -LiteralPath $zip) {Remove-Item -LiteralPath $zip -Force}
Compress-Archive -LiteralPath $summary -DestinationPath $zip -CompressionLevel Optimal
Write-Host ('[C545D] Reanalyzed '+$n+' historical UMDH deltas; no new measurement.')
Write-Host ('[C545D] Upload ONLY: '+$zip)
Write-Host '[C545D] Raw logs, diff, symbols and recordings remain local.'
