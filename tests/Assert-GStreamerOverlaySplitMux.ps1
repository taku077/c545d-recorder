# CI-ONLY: official MSVC GStreamer 1.28.8 + isolated candidate GIO.
# Simulates hourly segmentation on shortened thresholds, with 2 synthetic
# H264/RTP/avdec_h264 video paths and AAC. No camera or real output files.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$SdkRoot,
  [Parameter(Mandatory=$true)][string]$OverlayDir,
  [string]$Prefix='ci_split'
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
$pattern=(Join-Path $root ($Prefix+'_%03d.mp4')).Replace('\','/')
$files=@()
$script:badFragmentDurations=0
# CI-only bounded execution; never let a stuck mux/decode hang the Windows job.
function Invoke-C545DBoundedGst([string[]]$Arguments,[string]$Label,[int]$TimeoutMs) {
  $out=Join-Path 'artifacts' ("$Label.stdout.txt")
  $err=Join-Path 'artifacts' ("$Label.stderr.txt")
  $proc=Start-Process -FilePath $gst -ArgumentList ($Arguments -join ' ') `
    -PassThru -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err
  try {
    if (-not $proc.WaitForExit($TimeoutMs)) {
      try { $proc.Kill() } catch { }
      try { [void]$proc.WaitForExit(5000) } catch { }
      throw "$Label did not complete before timeout; possible EOS/decode hang"
    }
    if ($proc.ExitCode -ne 0) { throw "$Label exited $($proc.ExitCode); inspect sanitized stderr" }
  }
  finally { $proc.Dispose() }
}
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
    'videotestsrc','is-live=true','num-buffers=90','pattern=black',
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
    'videotestsrc','is-live=true','num-buffers=90','pattern=white',
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
    'audiotestsrc','is-live=true','num-buffers=288','wave=sine',
    '!','audioconvert','!','audioresample',
    '!','audio/x-raw,format=F32LE,layout=interleaved,rate=48000,channels=1',
    '!','avenc_aac','bitrate=192000','aac-coder=twoloop',
    '!','aacparse','!','mux.audio_0'
  )
  Invoke-C545DBoundedGst -Arguments $argsMedia -Label ($Prefix+'_record') -TimeoutMs 70000
  $files=@(Get-ChildItem -LiteralPath $root -Filter ($Prefix+'_*.mp4') -File | Sort-Object Name)
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
    Invoke-C545DBoundedGst -Arguments $decode -Label ($Prefix+"_decode_"+$f.BaseName) -TimeoutMs 25000
    $match=[regex]::Match($info,'(?im)^\s*Duration:\s*(\d+):(\d+):(\d+)\.(\d+)')
    if (-not $match.Success) { throw "Missing segment duration: $($f.Name)" }
    $fraction=[double]("0."+$match.Groups[4].Value)
    $lengthSec=3600*[int]$match.Groups[1].Value+60*[int]$match.Groups[2].Value+[int]$match.Groups[3].Value+$fraction
    $seconds += $lengthSec
    $segmentLines += ("segment=$($f.Name) bytes=$($f.Length) duration_s=$([math]::Round($lengthSec,3)) tracks=H264+AAC")
    # The first splitmux fragment can be short while synthetic RTP/H264
    # chains reach the initial keyframe: official SDK and candidate both
    # produced ~0.15s in CI 44555196915. Only the FIRST fragment gets
    # the 0.10s startup allowance; later fragments retain the strict
    # 0.30s minimum. Decode/caps and aggregate-duration checks are unchanged.
    $minimumSeconds=if ($f.FullName -eq $files[0].FullName) { 0.10 } else { 0.30 }
    if ($lengthSec -lt $minimumSeconds -or $lengthSec -gt 4.0) {
      $segmentLines += ("DURATION_GATE_FAIL segment=$($f.Name) duration_s=$([math]::Round($lengthSec,6))")
      $script:badFragmentDurations++
    }
  }
  # Persist complete sanitized diagnostics BEFORE enforcing the duration gates.
  $segmentLines | Set-Content ('artifacts/'+$Prefix+'_segment_diagnostics.txt')
  if ($script:badFragmentDurations -ne 0) {
    throw "$($script:badFragmentDurations) fragments failed duration gate; inspect prefixed segment diagnostics"
  }
  if ($seconds -lt 5.0 -or $seconds -gt 7.8) {
    throw "Incorrect total MP4 duration $seconds across segments"
  }
  "C545D_SPLITMUX_MSVC_GIO_PASS segments=$($files.Count) " +
    "duration_sum_s=$([math]::Round($seconds,3)) " +
    "two_RTP_H264_decoders=avdec_h264 AAC=48kHz_mono " +
    "output=2560x720@15fps x264=medium_quantizer24 " +
    "async_finalize=false all_segments_av_decodable=true Windows_CI_only=true" |
    Tee-Object -FilePath ('artifacts/'+$Prefix+'_summary.txt')
  $segmentLines | Add-Content ('artifacts/'+$Prefix+'_summary.txt')
}
finally {
  # Do not upload even synthetic media. Only sanitized summary/logs.
  @(Get-ChildItem -LiteralPath $root -Filter ($Prefix+'_*.mp4') -File -ErrorAction SilentlyContinue) |
    Remove-Item -Force -ErrorAction SilentlyContinue
}
