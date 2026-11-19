# CI-ONLY: official MSVC GStreamer 1.28.8 + isolated candidate GIO.
# Simulates hourly segmentation on shortened thresholds, with 2 synthetic
# H264/RTP/avdec_h264 video paths and AAC. No camera or real output files.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$SdkRoot,
  [Parameter(Mandatory=$true)][string]$OverlayDir
)
$ErrorActionPreference='Stop'
$bin=Join-Path $SdkRoot 'bin'
$candidate=Join-Path $OverlayDir 'gio-2.0-0.dll'
if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw 'Candidate GIO overlay absent' }
$env:PATH="$OverlayDir;$bin;$env:PATH"
$scanner=Join-Path $SdkRoot 'libexec\gstreamer-1.0\gst-plugin-scanner.exe'
if (Test-Path $scanner) { $env:GST_PLUGIN_SCANNER=$scanner }
$env:GST_REGISTRY=Join-Path $env:RUNNER_TEMP 'c545d_overlay_splitmux_registry.bin'
$gst=Join-Path $OverlayDir 'gst-launch-1.0.exe'
$discover=Join-Path $OverlayDir 'gst-discoverer-1.0.exe'
$inspect=Join-Path $OverlayDir 'gst-inspect-1.0.exe'
foreach($p in @($gst,$discover,$inspect)) {
  if (-not (Test-Path $p)) { throw "GStreamer overlay executable missing: $p" }
}
foreach($e in @('splitmuxsink','qtdemux','mp4mux','avdec_h264','avdec_aac','avenc_aac',
  'h264timestamper','audiotestsrc','videotestsrc','rtph264pay','rtph264depay')) {
  & $inspect $e 1>$null 2>$null
  if ($LASTEXITCODE -ne 0) { throw "Required splitmux test element missing: $e" }
}
New-Item -ItemType Directory -Path artifacts -Force | Out-Null
$root=[IO.Path]::GetFullPath('artifacts')
$pattern=(Join-Path $root 'ci_split_%03d.mp4').Replace('\','/')
$files=@()
$script:badFragmentDurations=0
try {
  $argsMedia=@(
    '-e','-q',
    'compositor','name=mix','background=black','ignore-inactive-pads=true',
       'sink_0::xpos=0','sink_1::xpos=1280',
    '!','video/x-raw,width=2560,height=720,framerate=15/1',
    '!','videoconvert','!','video/x-raw,format=I420',
    '!','queue','max-size-buffers=12','max-size-bytes=0',
        'max-size-time=0','leaky=downstream',
    '!','x264enc','pass=qual','quantizer=24','bitrate=15000',
        'speed-preset=medium','key-int-max=30','bframes=3','rc-lookahead=10',
    '!','video/x-h264,profile=high','!','h264parse',
    '!','h264timestamper',
    '!','splitmuxsink','name=mux',("location="+$pattern),
        'max-size-time=1500000000','async-finalize=false',
        'send-keyframe-requests=true',
    'videotestsrc','num-buffers=90','pattern=black',
    '!','video/x-raw,format=I420,width=1280,height=720,framerate=15/1',
    '!','x264enc','speed-preset=ultrafast','tune=zerolatency','key-int-max=30',
    '!','h264parse','!','rtph264pay','config-interval=1','!','rtph264depay',
        'request-keyframe=true','wait-for-keyframe=true',
    '!','video/x-h264,alignment=au','!','h264parse','config-interval=0',
    '!','video/x-h264,stream-format=byte-stream,alignment=au',
    '!','avdec_h264','!','videoconvert',
    '!','video/x-raw,format=I420,width=1280,height=720,framerate=15/1',
    '!','queue','max-size-buffers=8','max-size-bytes=0','max-size-time=0',
        'leaky=downstream','!','mix.sink_0',
    'videotestsrc','num-buffers=90','pattern=white',
    '!','video/x-raw,format=I420,width=1280,height=720,framerate=15/1',
    '!','x264enc','speed-preset=ultrafast','tune=zerolatency','key-int-max=30',
    '!','h264parse','!','rtph264pay','config-interval=1','!','rtph264depay',
        'request-keyframe=true','wait-for-keyframe=true',
    '!','video/x-h264,alignment=au','!','h264parse','config-interval=0',
    '!','video/x-h264,stream-format=byte-stream,alignment=au',
    '!','avdec_h264','!','videoconvert',
    '!','video/x-raw,format=I420,width=1280,height=720,framerate=15/1',
    '!','queue','max-size-buffers=8','max-size-bytes=0','max-size-time=0',
        'leaky=downstream','!','mix.sink_1',
    'audiotestsrc','num-buffers=288','wave=sine',
    '!','audioconvert','!','audioresample',
    '!','audio/x-raw,format=F32LE,layout=interleaved,rate=48000,channels=1',
    '!','avenc_aac','bitrate=192000','aac-coder=twoloop',
    '!','aacparse','!','mux.audio_0'
  )
  & $gst @argsMedia 1>artifacts/ci_splitmux_stdout.txt 2>artifacts/ci_splitmux_stderr.txt
  if ($LASTEXITCODE -ne 0) { throw "Synthetic splitmuxsink pipeline failure: $LASTEXITCODE" }
  $files=@(Get-ChildItem -LiteralPath $root -Filter 'ci_split_*.mp4' -File | Sort-Object Name)
  if ($files.Count -lt 2 -or $files.Count -gt 8) {
    throw "Unexpected MP4 segment count: $($files.Count)"
  }
  $seconds=0.0
  $segmentLines=@()
  foreach($f in $files) {
    if ($f.Length -lt 4000) { throw "Incomplete MP4 segment: $($f.Name) $($f.Length) bytes" }
    $info=(& $discover -v ([Uri]$f.FullName).AbsoluteUri 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Unplayable MP4 segment: $($f.Name)" }
    if ($info -notmatch '(?i)h\.?264|video/x-h264' -or
        $info -notmatch '(?i)aac|audio/mpeg') {
      throw "MP4 has missing H264 or AAC track: $($f.Name)"
    }
    foreach($patternCheck in @('(?i)width:\s*2560','(?i)height:\s*720',
      '(?i)(frame rate|framerate):\s*15/1',
      '(?i)(sample rate|rate):\s*48000','(?i)channels:\s*1\b')) {
      if ($info -notmatch $patternCheck) {
        throw "Incorrect per-fragment media caps in $($f.Name): $patternCheck"
      }
    }
    # Every fragment must decode BOTH compressed tracks independently.
    $decode=@('-q','filesrc',("location="+$f.FullName.Replace('\','/')),
      '!','qtdemux','name=d',
      'd.video_0','!','queue','!','h264parse','!','avdec_h264',
      '!','fakesink','sync=false',
      'd.audio_0','!','queue','!','aacparse','!','avdec_aac',
      '!','fakesink','sync=false')
    & $gst @decode 1>$null 2>artifacts/ci_split_decode_stderr.txt
    if ($LASTEXITCODE -ne 0) { throw "MP4 segment A/V decode failed: $($f.Name)" }
    $match=[regex]::Match($info,'(?im)^\s*Duration:\s*(\d+):(\d+):(\d+)\.(\d+)')
    if (-not $match.Success) { throw "Missing segment duration: $($f.Name)" }
    $fraction=[double]("0."+$match.Groups[4].Value)
    $lengthSec=3600*[int]$match.Groups[1].Value+60*[int]$match.Groups[2].Value+[int]$match.Groups[3].Value+$fraction
    $seconds += $lengthSec
    $segmentLines += ("segment=$($f.Name) bytes=$($f.Length) duration_s=$([math]::Round($lengthSec,3)) tracks=H264+AAC")
    if ($lengthSec -lt 0.3 -or $lengthSec -gt 4.0) {
      $segmentLines += ("DURATION_GATE_FAIL segment=$($f.Name) duration_s=$([math]::Round($lengthSec,6))")
      $script:badFragmentDurations++
    }
  }
  # Persist complete sanitized diagnostics BEFORE enforcing the duration gates.
  $segmentLines | Set-Content artifacts/ci_splitmux_segment_diagnostics.txt
  if ($script:badFragmentDurations -ne 0) {
    throw "$($script:badFragmentDurations) fragments failed duration gate; inspect complete ci_splitmux_segment_diagnostics.txt"
  }
  if ($seconds -lt 5.0 -or $seconds -gt 7.8) {
    throw "Incorrect total MP4 duration $seconds across segments"
  }
  "C545D_SPLITMUX_MSVC_GIO_PASS segments=$($files.Count) " +
    "duration_sum_s=$([math]::Round($seconds,3)) " +
    "two_RTP_H264_decoders=avdec_h264 AAC=48kHz_mono " +
    "output=2560x720@15fps x264=medium_quantizer24 " +
    "async_finalize=false all_segments_av_decodable=true Windows_CI_only=true" |
    Tee-Object -FilePath artifacts/ci_splitmux_summary.txt
  $segmentLines | Add-Content artifacts/ci_splitmux_summary.txt
}
finally {
  # Do not upload even synthetic media. Only sanitized summary/logs.
  @(Get-ChildItem -LiteralPath $root -Filter 'ci_split_*.mp4' -File -ErrorAction SilentlyContinue) |
    Remove-Item -Force -ErrorAction SilentlyContinue
}
