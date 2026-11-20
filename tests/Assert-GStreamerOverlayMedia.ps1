# CI-only integration: candidate MSVC GIO with exact official GStreamer 1.28.8.
# Fake generated video/audio only. Never start Record.ps1 or access cameras.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$SdkRoot,
  [Parameter(Mandatory=$true)][string]$OverlayDir
)
$ErrorActionPreference='Stop'
$bin=Join-Path $SdkRoot 'bin'
$env:PATH="$OverlayDir;$bin;$env:PATH"
$scanner=Join-Path $SdkRoot 'libexec\gstreamer-1.0\gst-plugin-scanner.exe'
if (Test-Path $scanner) { $env:GST_PLUGIN_SCANNER=$scanner }
$env:GST_REGISTRY=Join-Path $env:RUNNER_TEMP 'c545d_overlay_media_registry.bin'
foreach($name in @('gst-launch-1.0.exe','gst-inspect-1.0.exe',
                   'gst-discoverer-1.0.exe')) {
  $src=Join-Path $bin $name
  if (-not (Test-Path $src)) { throw "GStreamer SDK program missing: $name" }
  Copy-Item -LiteralPath $src -Destination (Join-Path $OverlayDir $name) -Force
}
$candidate=Join-Path $OverlayDir 'gio-2.0-0.dll'
if (-not (Test-Path $candidate)) { throw 'Patched MSVC GIO overlay missing' }
$gst=Join-Path $OverlayDir 'gst-launch-1.0.exe'
$inspect=Join-Path $OverlayDir 'gst-inspect-1.0.exe'
$discover=Join-Path $OverlayDir 'gst-discoverer-1.0.exe'
foreach($e in @('videotestsrc','compositor','videoconvert','queue',
  'x264enc','h264parse','h264timestamper','rtph264pay','rtph264depay',
  'avdec_h264','audiotestsrc','audioconvert','audioresample',
  'avenc_aac','aacparse','mp4mux','qtdemux','filesink','identity')) {
  & $inspect $e 1>$null 2>$null
  if ($LASTEXITCODE -ne 0) { throw "Required exact-GStreamer media element absent: $e" }
}
New-Item -ItemType Directory -Path artifacts -Force | Out-Null
$mp4=[IO.Path]::GetFullPath((Join-Path 'artifacts' 'ci_two_video_aac.mp4'))
$rgb=[IO.Path]::GetFullPath((Join-Path 'artifacts' 'ci_first_frame.rgb'))
# Two physically separate H264/RTP encode/decode inputs feed one compositor.
# Encoder and mux use real recorder quality/geometry settings.
$argsMedia=@(
 '-e','-q',
 'compositor','name=mix','background=black','ignore-inactive-pads=true',
 'sink_0::xpos=0','sink_1::xpos=1280',
 '!','video/x-raw,width=2560,height=720,framerate=15/1',
 '!','videoconvert','!','video/x-raw,format=I420',
 '!','queue','max-size-buffers=12','max-size-bytes=0','max-size-time=0','leaky=downstream',
 '!','x264enc','pass=qual','quantizer=24','bitrate=15000',
    'speed-preset=medium','key-int-max=30','bframes=3','rc-lookahead=10',
 '!','video/x-h264,profile=high','!','h264parse',
 '!','h264timestamper','!','mux.video_0',
 'mp4mux','name=mux','!','filesink',("location="+$mp4.Replace('\','/')),
 'videotestsrc','num-buffers=45','pattern=black',
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
 'videotestsrc','num-buffers=45','pattern=white',
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
 'audiotestsrc','num-buffers=144','wave=sine',
 '!','audioconvert','!','audioresample',
 '!','audio/x-raw,format=F32LE,layout=interleaved,rate=48000,channels=1',
 '!','avenc_aac','bitrate=192000','aac-coder=twoloop',
 '!','aacparse','!','mux.audio_0'
)
try {
  & $gst @argsMedia 1>artifacts/ci_pipeline_stdout.txt 2>artifacts/ci_pipeline_stderr.txt
  if ($LASTEXITCODE -ne 0) {
    throw "Synthetic 2-video RTP/decode + AAC/MP4 pipeline failed: $LASTEXITCODE"
  }
  $mp4Size=(Get-Item -LiteralPath $mp4).Length
  if ($mp4Size -lt 15000) { throw "Synthetic MP4 unexpectedly small: $mp4Size" }
  $uri=([Uri]$mp4).AbsoluteUri
  $info=(& $discover -v $uri 2>&1 | Out-String)
  if ($LASTEXITCODE -ne 0) { throw 'GStreamer discoverer rejected synthetic MP4' }
  # Discoverer validates EOS finalization and media stream negotiation.
  if ($info -notmatch '(?i)h\.?264|video/x-h264') { throw 'Encoded H264 not detected' }
  if ($info -notmatch '(?i)aac|audio/mpeg') { throw 'Encoded AAC not detected' }
  if ($info -notmatch '(?i)width:\s*2560') { throw 'Video width not 2560' }
  if ($info -notmatch '(?i)height:\s*720') { throw 'Video height not 720' }
  if ($info -notmatch '(?i)(frame rate|framerate):\s*15/1') { throw 'Output frame rate not 15fps' }
  if ($info -notmatch '(?i)(sample rate|rate):\s*48000') { throw 'AAC rate not 48kHz' }
  if ($info -notmatch '(?i)channels:\s*1\b') { throw 'AAC audio not mono' }
  # Decode only the first composite frame to assert black left / white right
  # in actual MP4 pixels, not just muxer metadata.
  $decode=@('-q','filesrc',("location="+$mp4.Replace('\','/')),
    '!','qtdemux','name=demux','demux.video_0','!','queue',
    '!','h264parse','!','avdec_h264','!','videoconvert',
    '!','video/x-raw,format=RGB','!','identity','eos-after=1',
    '!','filesink',("location="+$rgb.Replace('\','/')))
  & $gst @decode 1>artifacts/ci_decode_stdout.txt 2>artifacts/ci_decode_stderr.txt
  if ($LASTEXITCODE -ne 0) { throw "Synthetic MP4 decode failed: $LASTEXITCODE" }
  $buf=[IO.File]::ReadAllBytes($rgb)
  $stride=2560*3
  if ($buf.Length -lt ($stride*720)) { throw "Composite frame incomplete: $($buf.Length) bytes" }
  $y=360
  $leftIndex=$y*$stride + 640*3
  $rightIndex=$y*$stride + 1920*3
  $left=([int]$buf[$leftIndex]+$buf[$leftIndex+1]+$buf[$leftIndex+2])/3
  $right=([int]$buf[$rightIndex]+$buf[$rightIndex+1]+$buf[$rightIndex+2])/3
  if ($left -gt 80 -or $right -lt 175) {
    throw "Left/right video mapping failed: left=$left right=$right"
  }
  "MSVC_GIO_GSTREAMER_MEDIA_PASS mp4_bytes=$mp4Size output=2560x720@15fps " +
    "AAC=48000Hz_mono x264=medium_quantizer24 left_mean=$left right_mean=$right " +
    "two_RTP_H264_decoders=avdec_h264 EOS=finalized Windows_runner_only=true" |
      Tee-Object -FilePath artifacts/media_overlay_summary.txt
}
finally {
  # Keep only sanitized status/log files. Synthetic video/audio do not need
  # to be retained in GitHub Actions; never upload real media or credentials.
  Remove-Item -LiteralPath $mp4,$rgb -ErrorAction SilentlyContinue
}
