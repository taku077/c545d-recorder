# Schema-only diagnostic export. No arbitrary log text or credential is copied.
# Windows PowerShell 5.1; no admin, camera, or external software required.
[CmdletBinding()]
param(
    [string]$LogsDirectory = (Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\Logs'),
    [string]$OutputDirectory = (Join-Path $env:USERPROFILE 'Downloads')
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $LogsDirectory -PathType Container)) {
    throw 'C545D logs not found. Run a short diagnostic recording first.'
}
if (-not (Test-Path -LiteralPath $OutputDirectory -PathType Container)) {
    $OutputDirectory = [Environment]::GetFolderPath('Desktop')
}
$selected = @(Get-ChildItem -LiteralPath $LogsDirectory -File |
    Where-Object { $_.Name -match '^(Recording_\d{8}_\d{6}_\d+\.txt|GST_DIAG_[\w-]+\.log)$' } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 8)
if ($selected.Count -eq 0) { throw 'No diagnostic logs found.' }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$work = Join-Path $env:TEMP ('C545D_safe_report_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work -Force | Out-Null
$zip = Join-Path $OutputDirectory ('C545D_SAFE_DIAGNOSTICS_' + $stamp + '.zip')
$eventPath = Join-Path $work 'media_events.tsv'
$summaryPath = Join-Path $work 'summary.txt'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$events = New-Object System.IO.StreamWriter($eventPath,$false,$utf8)
$counts = @{}
$sourceStats = New-Object System.Collections.Generic.List[string]
$tab = [char]9
$events.WriteLine(('source_id','clock','category','event','numeric_metrics' -join $tab))
$written = 0; $maxEvents = 18000
try {
    $idx = 0
    foreach ($file in $selected) {
        $idx++; $source = 'LOG_' + $idx.ToString('00')
        $read = 0; $exported = 0
        $sr = New-Object System.IO.StreamReader($file.FullName,$utf8,$true)
        try {
            while ($read -lt 400000) {
                $line = $sr.ReadLine()
                if ($null -eq $line) { break }
                $read++
                if ($line.Length -gt 32000) { continue }
                $kind = ''
                if ($line -match '(?i)\bno frame!') { $kind = 'LIBAV_NO_FRAME' }
                elseif ($line -match '(?i)\bdecreasing DTS value\b') { $kind = 'QTMUX_DTS_BACKWARD' }
                elseif ($line -match '(?i)\b(?:lost packet|packet lost|packet loss|missing packet)\b') { $kind = 'RTP_PACKET_LOSS' }
                elseif ($line -match '(?i)\bdiscont(?:inuity)?\b') { $kind = 'DISCONTINUITY' }
                elseif ($line -match '(?i)\b(?:invalid timestamp|timestamp jump|out.of.order|dropped frame)\b') { $kind = 'TIMESTAMP_OR_FRAME_WARNING' }
                elseif ($line -match '(?i)\b(?:rtph264depay|h264parse|rtpjitterbuffer|qtmux|audiorate)\b') {
                    if (($read % 15) -ne 0) { continue }
                    $kind = 'DEBUG_SAMPLE'
                } else { continue }
                if (-not $counts.ContainsKey($kind)) { $counts[$kind] = 0 }
                $counts[$kind]++
                if ($written -ge $maxEvents) { continue }
                $tm = [regex]::Match($line,'(?<![0-9])(?:[0-9]{1,2}:)?[0-9]{2}:[0-9]{2}\.[0-9]{3,12}(?![0-9])')
                $clock = if ($tm.Success) { $tm.Value } else { '-' }
                $cat = '-'
                foreach ($candidate in @('qtmux','libav','rtph264depay','h264parse','rtpjitterbuffer','audiorate','splitmuxsink')) {
                    if ($line -match ('(?i)\b' + $candidate + '\b')) {
                        $cat = $candidate; break
                    }
                }
                $metric = '-'
                if ($kind -eq 'QTMUX_DTS_BACKWARD') {
                    $offset = $line.IndexOf('decreasing DTS value',[StringComparison]::OrdinalIgnoreCase)
                    $tail = $line.Substring($offset)
                    $times = @([regex]::Matches($tail,'\b[0-9]{1,2}:[0-9]{2}:[0-9]{2}\.[0-9]{1,12}\b') |
                        Select-Object -First 2 | ForEach-Object { $_.Value })
                    if ($times.Count -eq 2) { $metric = 'older=' + $times[0] + ';newer=' + $times[1] }
                } elseif ($kind -in @('RTP_PACKET_LOSS','DISCONTINUITY','DEBUG_SAMPLE')) {
                    $values = @()
                    foreach ($label in @('seqnum','rtptime','dts','pts','duration','nal_type')) {
                        $m = [regex]::Match($line, '(?i)\b' + $label + '[=: ]+([0-9]{1,10})\b')
                        if ($m.Success) { $values += ($label + '=' + $m.Groups[1].Value) }
                    }
                    if ($values.Count -gt 0) { $metric = $values -join ';' }
                }
                # No raw line or free-form debug message is ever output.
                $events.WriteLine((@($source,$clock,$cat,$kind,$metric) -join $tab))
                $written++; $exported++
            }
        } finally { $sr.Dispose() }
        $sourceStats.Add(($source + ' read_lines=' + $read + ' exported_events=' + $exported))
    }
} finally { $events.Dispose() }
$info = New-Object System.Collections.Generic.List[string]
$info.Add('C545D SAFE DIAGNOSTICS / SCHEMA ONLY')
$info.Add('Generated: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
$info.Add('Files scanned: ' + $selected.Count)
$info.Add('Events exported: ' + $written)
$info.Add('Raw messages, file paths, URIs, usernames, passwords and authentication headers are NEVER copied.')
$info.Add('This restricted extract may omit information needed for deeper debugging.')
foreach ($stat in $sourceStats) { $info.Add($stat) }
foreach ($key in @($counts.Keys | Sort-Object)) { $info.Add($key + '=' + $counts[$key]) }
[IO.File]::WriteAllLines($summaryPath,[string[]]$info,$utf8)
try {
    Compress-Archive -LiteralPath @($eventPath,$summaryPath) -DestinationPath $zip -CompressionLevel Optimal -ErrorAction Stop
    Write-Host ('SAFE_REPORT_OK: ' + $zip)
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
