# C545D v2 safe diagnostic exporter: count the full scanned time range.
# Never writes source logs or MP4. Never copies arbitrary log message text.
[CmdletBinding()]
param(
    [string]$LogsDirectory = (Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\Logs'),
    [string]$OutputDirectory = (Join-Path $env:USERPROFILE 'Downloads')
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $LogsDirectory -PathType Container)) {
    throw 'C545D logs directory not found. Run diagnostic recording first.'
}
if (-not (Test-Path -LiteralPath $OutputDirectory -PathType Container)) {
    $OutputDirectory = [Environment]::GetFolderPath('Desktop')
}
# Start from the most recently modified diagnostic sessions, then select the
# largest children (usually gst-launch rather than tiny plugin preflight logs).
$gstRecent = @(Get-ChildItem -LiteralPath $LogsDirectory -File -Filter 'GST_DIAG_*.log' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 12)
$gst = @($gstRecent | Sort-Object Length -Descending | Select-Object -First 2)
$rec = @(Get-ChildItem -LiteralPath $LogsDirectory -File -Filter 'Recording_*.txt' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 2)
$selected = @($gst) + @($rec)
if ($selected.Count -eq 0) { throw 'No diagnostic logs found.' }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$work = Join-Path $env:TEMP ('C545D_safe_report_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work -Force | Out-Null
$zip = Join-Path $OutputDirectory ('C545D_SAFE_DIAGNOSTICS_' + $stamp + '.zip')
$eventPath = Join-Path $work 'media_events.tsv'
$ratePath = Join-Path $work 'event_rates.tsv'
$summaryPath = Join-Path $work 'summary.txt'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$tab = [char]9
$events = New-Object System.IO.StreamWriter($eventPath,$false,$utf8)
$events.WriteLine((@('source_id','clock','second','thread_id','category','event','numeric_metrics') -join $tab))
$counts = @{}
$perSecond = @{}
$samples = @{}
$details = New-Object System.Collections.Generic.List[string]
$maxRows = 16000
$maxLinesPerFile = 5000000
$totalLines = 0
$maxTotalLines = 10000000
$written = 0
$truncated = $false
$culture = [System.Globalization.CultureInfo]::InvariantCulture
try {
    $fileNum = 0
    foreach ($file in $selected) {
        $fileNum++
        $source = 'LOG_' + $fileNum.ToString('00') + $(if ($file.Name -like 'GST_DIAG_*') {'_GST'} else {'_WORKER'})
        $read = 0; $exported = 0; $fileTruncated = $false
        $stream = New-Object System.IO.StreamReader($file.FullName,$utf8,$true)
        try {
            while ($true) {
                if ($read -ge $maxLinesPerFile -or $totalLines -ge $maxTotalLines) {
                    $fileTruncated = $true; $truncated = $true; break
                }
                $line = $stream.ReadLine()
                if ($null -eq $line) { break }
                $read++; $totalLines++
                if ($line.Length -gt 32000) { continue }
                $kind = ''
                if ($line -match '(?i)\bno frame!') { $kind = 'LIBAV_NO_FRAME' }
                elseif ($line -match '(?i)\bdecreasing DTS value\b') { $kind = 'QTMUX_DTS_BACKWARD' }
                elseif ($line -match '(?i)(?:erroneous pipeline|syntax error|could not link|no element|could not construct pipeline|failed to parse|pipeline could not be constructed|not-negotiated|not-linked)') { $kind = 'GST_PIPELINE_ERROR' }
                elseif ($line -match 'GStreamer returned; exitCode=') { $kind = 'GST_EXIT' }
                elseif ($line -match 'GStreamer launching \(EOS enabled\)') { $kind = 'GST_LAUNCH' }
                elseif ($line -match '(?i)\b(?:lost packet|packet lost|packet loss|missing packet)\b') { $kind = 'RTP_PACKET_LOSS' }
                elseif ($line -match '(?i)\bdiscont(?:inuity)?\b') { $kind = 'DISCONTINUITY' }
                elseif ($line -match '(?i)\b(?:invalid timestamp|timestamp jump|out.of.order|dropped frame)\b') { $kind = 'TIMESTAMP_OR_FRAME_WARNING' }
                elseif ($line -match '(?i)\b(?:rtph264depay|h264parse|rtpjitterbuffer|qtmux|audiorate)\b') {
                    $kind = 'DEBUG_SAMPLE'
                } else { continue }
                $t = [regex]::Match($line,'\b[0-9]{1,2}:[0-9]{2}:[0-9]{2}\.[0-9]{3,12}\b')
                $clock = if ($t.Success) { $t.Value } else { '-' }
                $sec = '-1'
                if ($t.Success) {
                    $part = $clock.Split(':')
                    try {
                        $second = 3600 * [int]$part[0] + 60 * [int]$part[1] +
                            [int][Math]::Floor([double]::Parse($part[2],$culture))
                        $sec = [string]$second
                    } catch { $sec = '-1' }
                }
                $key = $source + '|' + $kind
                if (-not $counts.ContainsKey($key)) { $counts[$key] = 0 }
                $counts[$key]++
                $rateKey = $source + '|' + $sec + '|' + $kind
                if (-not $perSecond.ContainsKey($rateKey)) { $perSecond[$rateKey] = 0 }
                $perSecond[$rateKey]++

                # Count ALL recognized events, but only export representative
                # lines, so thousands of routine DEBUG messages cannot push
                # H264 errors out of a capped ZIP. Never copy raw messages.
                $sampleKey = $rateKey
                $maxPerSecond = switch ($kind) {
                    'DEBUG_SAMPLE' { 1 }
                    'LIBAV_NO_FRAME' { 4 }
                    'QTMUX_DTS_BACKWARD' { 100 }
                    'RTP_PACKET_LOSS' { 20 }
                    'DISCONTINUITY' { 20 }
                    default { 12 }
                }
                if (-not $samples.ContainsKey($sampleKey)) { $samples[$sampleKey] = 0 }
                if ($samples[$sampleKey] -ge $maxPerSecond -or $written -ge $maxRows) { continue }
                $samples[$sampleKey]++
                $cat = '-'
                foreach ($c in @('qtmux','libav','rtph264depay','h264parse','rtpjitterbuffer','audiorate','splitmuxsink')) {
                    if ($line -match ('(?i)\b' + $c + '\b')) { $cat = $c; break }
                }
                # Thread ID is a fixed numeric field in the GStreamer header,
                # not an arbitrary user-supplied log string.
                $thread = '-'
                $header = [regex]::Match($line,'^\s*\d{1,2}:\d\d:\d\d\.\d+\s+\d{1,10}\s+([0-9a-fA-F]{1,16})\s+')
                if ($header.Success) { $thread = $header.Groups[1].Value }
                $metric = '-'
                if ($kind -eq 'GST_EXIT') {
                    $m = [regex]::Match($line,'exitCode=([0-9]{1,3})')
                    if ($m.Success) { $metric = 'exit_code=' + $m.Groups[1].Value }
                }
                if ($kind -eq 'QTMUX_DTS_BACKWARD') {
                    $offset = $line.IndexOf('decreasing DTS value',[StringComparison]::OrdinalIgnoreCase)
                    $tail = $line.Substring($offset)
                    $times = @([regex]::Matches($tail,'\b\d{1,2}:\d\d:\d\d\.\d{1,12}\b') |
                        Select-Object -First 2 | ForEach-Object { $_.Value })
                    if ($times.Count -eq 2) { $metric = 'dts_1=' + $times[0] + ';dts_2=' + $times[1] }
                } elseif ($kind -in @('RTP_PACKET_LOSS','DISCONTINUITY','DEBUG_SAMPLE')) {
                    $mvals = @()
                    foreach ($lab in @('seqnum','rtptime','dts','pts','duration','nal_type')) {
                        $m = [regex]::Match($line, '(?i)\b' + $lab + '[=: ]+([0-9]{1,10})\b')
                        if ($m.Success) { $mvals += ($lab + '=' + $m.Groups[1].Value) }
                    }
                    if ($mvals.Count) { $metric = $mvals -join ';' }
                }
                $events.WriteLine((@($source,$clock,$sec,$thread,$cat,$kind,$metric) -join $tab))
                $written++; $exported++
            }
        } finally { $stream.Dispose() }
        $details.Add(($source + ' scanned_lines=' + $read + ' exported_events=' + $exported +
            ' status=' + $(if ($fileTruncated) { 'TRUNCATED' } else { 'COMPLETE' })))
    }
} finally { $events.Dispose() }

# Include all aggregate counts even for events skipped by row sampling.
$rates = New-Object System.IO.StreamWriter($ratePath,$false,$utf8)
try {
    $rates.WriteLine((@('source_id','second','event','count') -join $tab))
    foreach ($key in @($perSecond.Keys | Sort-Object)) {
        $a = $key.Split('|')
        $rates.WriteLine((@($a[0],$a[1],$a[2],[string]$perSecond[$key]) -join $tab))
    }
} finally { $rates.Dispose() }
$info = New-Object System.Collections.Generic.List[string]
$info.Add('C545D SAFE DIAGNOSTICS V2 / SCHEMA ONLY')
$info.Add('Generated: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
$info.Add('Scanned file count: ' + $selected.Count)
$info.Add('Total scanned lines: ' + $totalLines)
$info.Add('Sampled exported rows: ' + $written)
$info.Add('Scan status: ' + $(if ($truncated) { 'TRUNCATED - full recording cannot be inferred' } else { 'COMPLETE for selected source files' }))
$info.Add('WARNING: counted error messages are not equivalent to missing video frames.')
$info.Add('Raw log messages, RTSP URIs, authentication headers, credentials, usernames and Windows paths are never copied.')
foreach ($d in $details) { $info.Add($d) }
foreach ($key in @($counts.Keys | Sort-Object)) { $info.Add($key + '=' + $counts[$key]) }
[IO.File]::WriteAllLines($summaryPath,[string[]]$info,$utf8)
try {
    Compress-Archive -LiteralPath @($eventPath,$ratePath,$summaryPath) -DestinationPath $zip -CompressionLevel Optimal -ErrorAction Stop
    Write-Host ('SAFE_REPORT_OK: ' + $zip)
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
