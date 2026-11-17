# Regression guard for the verified C545D recording baseline.
# This file parses *source text only*: no cameras, passwords or GStreamer are used.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$recordFile = Join-Path $root 'Record.ps1'
if (-not (Test-Path -LiteralPath $recordFile -PathType Leaf)) {
    throw 'Record.ps1 is missing.'
}
$record = [IO.File]::ReadAllText($recordFile)
function Assert-Contains([string]$pattern, [string]$label) {
    if ($record -cnotmatch $pattern) { throw "Baseline invariant missing: $label" }
    Write-Host ("PASS: " + $label)
}

# Guard the long-duration CPU-stable baseline against accidental reversion.
Assert-Contains '\$decoderCandidates\s*=\s*@\(\s*''avdec_h264''\s*,\s*''openh264dec''' 'avdec_h264 before OpenH264 in automatic decoder selection'
Assert-Contains "'speed-preset=medium'" 'x264 medium'
Assert-Contains "'quantizer=24'" 'x264 quantizer 24'
Assert-Contains "'key-int-max=30'" 'keyframe interval'
Assert-Contains "'max-size-time=3600000000000'" 'hourly MP4 splitting'
Assert-Contains "'splitmuxsink'" 'MP4 segmenter'
Assert-Contains "'send-keyframe-requests=true'" 'keyframe request on splits'
Assert-Contains "'video/x-raw,width=2560,height=720,framerate=15/1'" '2560x720 15fps compositor output'
Assert-Contains "'ntp-sync=true'" 'RTSP NTP sync'
Assert-Contains "'tcp-timestamp=true'" 'RTSP TCP timestamp'
Assert-Contains "'max-size-buffers=12'" 'bounded pre-encoder queue'
Assert-Contains "'leaky=downstream'" 'drop old frames rather than buffering indefinitely'
Assert-Contains "'video/x-raw,format=I420,width=1280,height=720,framerate=15/1'" 'per-camera 1280x720 15fps'
Assert-Contains "'mux.audio_0'" 'single muxed AAC audio stream'
# Repair the known repeated H.264 decoder errors and MP4 DTS regressions without
# changing x264 quality, RTSP clock, or replacing the known-good media backend.
Assert-Contains "'video/x-h264,alignment=au'" 'depayloader emits access units after packet loss'
Assert-Contains "'h264timestamper'" 'optional output DTS correction supported'
Assert-Contains "C545D_DTS_GUARD" 'DTS correction rollback switch'
Assert-Contains "Test-C545DDtsPath" 'synthetic DTS compatibility preflight'
# Guard discard-only audio memory bound, preserving actual AAC/video.
Assert-Contains "'max-size-buffers=8','max-size-bytes=262144'" 'bounded discarded telephoto RTP audio queue'
Assert-Contains "'max-size-time=250000000','leaky=downstream'" 'drop stale discarded audio'
Assert-Contains "'fakesink','async=false','sync=false','enable-last-sample=false'" 'do not retain discarded audio sample'
# Keep the safe version gate visible in the startup log. This must be
# informational only: never upgrade plugins or stop an existing recording.
Assert-Contains 'H264 parser plugin \(videoparsersbad\)' 'parser plugin version logged at startup'
Assert-Contains "h264parse' 2>" 'only plugin metadata is probed'
Assert-Contains 'No GStreamer files or recording settings were changed' 'version gate never upgrades GStreamer'
Write-Host 'Verified recorder baseline invariants PASS (static only).'
