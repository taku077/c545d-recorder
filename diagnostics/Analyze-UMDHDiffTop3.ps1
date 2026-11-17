# Read-only UMDH diff analysis for C545D (Windows PowerShell 5.1).
# Uses existing diff only. Never outputs raw frames, paths, addresses or functions.
[CmdletBinding()]
param(
    [string]$DiffPath = (Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\HeapTrace\UMDH_RAW_DIFF_PID9424.txt'),
    [switch]$SelfTest
)
$ErrorActionPreference = 'Stop'

# Intentionally uses the same broad prefix as the user's successful 182-row
# probe. Do NOT require the word "allocs" (different header variations exist).
$headerRx = [regex]'(?i)^\s*([+-])\s+(?:0x)?([0-9a-f]{1,16})\s+\('
$symbolRx = [regex]'(?i)(?<![a-z0-9_.-])([a-z][a-z0-9_.-]{1,63})!\S'

function Read-DiffHeaders([string[]]$lines) {
    $records = New-Object 'System.Collections.Generic.List[object]'
    for ($i = 0; $i -lt $lines.Length; $i++) {
        $m = $headerRx.Match($lines[$i])
        if (-not $m.Success) { continue }
        $value = [Convert]::ToUInt64($m.Groups[2].Value, 16)
        if ($value -gt [long]::MaxValue) {
            throw '差分値が64ビット整数の範囲外です。ファイルは変更していません。'
        }
        [void]$records.Add([PSCustomObject]@{
            Index = $i
            Sign  = $m.Groups[1].Value
            Bytes = [long]$value
        })
    }
    return $records.ToArray()
}

# Returns only approved non-private module names or a generic category.
function Get-SafeModule([string]$rawName) {
    $name = $rawName.ToLowerInvariant() -replace '\.dll$', ''
    if ($name -match '^(ntdll|kernel32|kernelbase|ucrtbase|msvcrt|win32u|combase|rpcrt4|user32|advapi32|ole32|dbghelp|vcruntime[0-9_.-]*|msvcp[0-9_.-]*|api-ms-win-[a-z0-9_.-]+)$') {
        return 'windows'
    }
    if ($name -match '^(?:lib)?(?:avcodec|avutil|avformat|avfilter|swscale|swresample)(?:[-_.][0-9][a-z0-9_.-]*)?$') {
        return $name
    }
    if ($name -match '^(?:lib)?(?:glib|gobject|gio|gmodule)-2[._-]0(?:[-_.]0)?$') {
        return $name
    }
    if ($name -match '^(?:lib)?x264(?:[-_.][0-9][a-z0-9_.-]*)?$') {
        return $name
    }
    if ($name -eq 'c545dsei' -or $name -eq 'gstc545dsei') { return 'gstc545dsei' }
    if ($name -match '^(?:lib)?gst[a-z0-9_.-]+$') {
        $knownPlugins = @(
            'gstvideoparsersbad', 'gstlibav', 'gstrtpmanager', 'gstcoreelements',
            'gstisomp4', 'gstplayback', 'gstx264', 'gstcompositor', 'gstrtp',
            'gstrtsp', 'gstapp', 'gstqtmux', 'gsttcp', 'gstvideoconvert',
            'gstaudioconvert', 'gstmultifile', 'gsttypefindfunctions'
        )
        if ($knownPlugins -contains $name -or
            $name -match '^(?:lib)?gst(?:reamer|base|video|audio|app|rtp|rtsp|pbutils|allocators|net|sdp|tag|controller|codecparsers)-1[._-]0(?:[-_.]0)?$') {
            return $name
        }
        return 'gstreamer-other'
    }
    return 'other'
}

function Get-TopDetails([string[]]$lines, [object[]]$headers) {
    $positives = @($headers | Where-Object { $_.Sign -eq '+' })
    if ($positives.Count -lt 3) { throw '正の差分が3件未満で、上位3件を解析できません。' }
    $top = @($positives | Sort-Object Bytes -Descending | Select-Object -First 3)
    $rank = 0
    foreach ($h in $top) {
        $rank++
        $endExclusive = $lines.Length
        foreach ($next in $headers) {
            if ($next.Index -gt $h.Index) {
                $endExclusive = $next.Index
                break
            }
        }
        $symbolLines = 0
        $windows = 0
        $mediaFrames = 0
        $other = 0
        $media = New-Object 'System.Collections.Generic.List[string]'
        $seen = @{}
        for ($j = $h.Index + 1; $j -lt $endExclusive; $j++) {
            $symbolMatches = $symbolRx.Matches($lines[$j])
            if ($symbolMatches.Count -eq 0) { continue }
            $symbolLines++
            foreach ($symbol in $symbolMatches) {
                $category = Get-SafeModule $symbol.Groups[1].Value
                if ($category -eq 'windows') { $windows++ }
                elseif ($category -eq 'other') { $other++ }
                else {
                    $mediaFrames++
                    if (-not $seen.ContainsKey($category)) {
                        $seen[$category] = $true
                        [void]$media.Add($category)
                    }
                }
            }
        }
        $mediaText = if ($media.Count -gt 0) { $media -join ', ' } else { 'none' }
        [PSCustomObject]@{
            Rank          = $rank
            DeltaBytes    = $h.Bytes
            StartLine     = $h.Index + 1
            EndLine       = $endExclusive  # inclusive 1-based line before next header
            SymbolLines   = $symbolLines
            WindowsFrames = $windows
            MediaFrames   = $mediaFrames
            OtherFrames   = $other
            MediaModules  = $mediaText
        }
    }
}

if ($SelfTest) {
    # 182 mixed records, deliberately only 91 with an "allocs" token:
    # previous overconstrained regular expression would have lost half.
    $sample = New-Object 'System.Collections.Generic.List[string]'
    for ($i = 0; $i -lt 182; $i++) {
        $plus = (($i % 2) -eq 0)
        $sign = if ($plus) { '+' } else { '-' }
        $unit = if ($plus) { 'allocs' } else { 'frees' }
        $size = if ($i -eq 0) { 380928L } elseif ($i -eq 2) { 178176L } elseif ($i -eq 4) { 94208L } else { 8L }
        $hex = $size.ToString('x')
        [void]$sample.Add(('{0} {1} ({1} - 0) 1 {2} BackTrace{3:x5}' -f $sign, $hex, $unit, $i))
        if ($i -eq 0) {
            [void]$sample.Add('ntdll!HeapAlloc')
            [void]$sample.Add('gstvideoparsersbad!frame')
            [void]$sample.Add('C:\Users\PRIVATE_SAMPLE\private-name!NeverExport')
        } elseif ($i -eq 2) {
            [void]$sample.Add('libavcodec-61!someFunction')
        } elseif ($i -eq 4) {
            [void]$sample.Add('glib-2.0-0.dll!g_malloc')
        } else {
            [void]$sample.Add('kernelbase!HeapFree')
        }
    }
    $headers = @(Read-DiffHeaders ($sample.ToArray()))
    $positiveCount = @($headers | Where-Object { $_.Sign -eq '+' }).Count
    $negativeCount = @($headers | Where-Object { $_.Sign -eq '-' }).Count
    if ($headers.Count -ne 182 -or $positiveCount -ne 91 -or $negativeCount -ne 91) {
        throw 'SELFTEST FAILED: positive/negative records not both detected.'
    }
    $result = @(Get-TopDetails ($sample.ToArray()) $headers)
    if ($result.Count -ne 3 -or
        $result[0].DeltaBytes -ne 380928 -or
        $result[1].DeltaBytes -ne 178176 -or
        $result[2].DeltaBytes -ne 94208 -or
        $result[0].MediaModules -notmatch 'gstvideoparsersbad' -or
        $result[0].MediaModules -match 'avcodec|PRIVATE|private-name' -or
        $result[1].MediaModules -notmatch 'libavcodec-61' -or
        $result[2].MediaModules -notmatch 'glib-2.0-0') {
        throw 'SELFTEST FAILED: block boundaries / allowlist classification.'
    }
    Write-Output 'PASS: 182 mixed headers, strict block boundaries, three ranks, safe module allowlist.'
    exit 0
}

if (-not (Test-Path -LiteralPath $DiffPath -PathType Leaf)) {
    throw '保存済みUMDH差分ファイルが見つかりません。再測定は不要です。'
}
$lines = [IO.File]::ReadAllLines($DiffPath)
$headers = @(Read-DiffHeaders $lines)
$positiveCount = @($headers | Where-Object { $_.Sign -eq '+' }).Count
$negativeCount = @($headers | Where-Object { $_.Sign -eq '-' }).Count
Write-Output ('差分レコード数={0}  正={1}  負={2}' -f $headers.Count, $positiveCount, $negativeCount)
if ($headers.Count -ne 182) {
    Write-Warning ('過去に確認した182件と一致しません（今回は{0}件）。結果を慎重に解釈してください。' -f $headers.Count)
}
$details = @(Get-TopDetails $lines $headers)
$details | Format-List | Out-String -Width 220 | Write-Output
Write-Output '読み取り専用の解析が完了しました。録画・UST・元ファイルに変更はありません。'
