# Tapo C545D / GStreamer: 2 RTSP cameras -> one MP4 (Windows PowerShell 5.1)
# This script never writes camera credentials to a file. While running, gst-launch
# arguments can still be inspected by administrators on this PC.
[CmdletBinding()]
param([string]$StopFile = '')
$ErrorActionPreference = 'Stop'

function Test-C545DStopRequested {
    # Only the GUI's durable, session-specific stop marker authorizes the
    # recorder to terminate instead of reconnecting. An unrelated CTRL+C
    # must not permanently stop a 24x365 evidence recorder.
    # This also protects normal stop while Gst is still initializing.
    return [bool]($StopFile -and (Test-Path -LiteralPath $StopFile -PathType Leaf))
}
function Take-C545DUnexpectedCtrlCCount {
    try { return [int][C545DWorkerStopSignal]::TakeCtrlCSignals() }
    catch { return 0 }
}

function Find-GstBin {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\gstreamer\1.0\msvc_x86_64\bin'),
        (Join-Path $env:ProgramFiles 'gstreamer\1.0\msvc_x86_64\bin'),
        'C:\gstreamer\1.0\msvc_x86_64\bin'
    )
    foreach ($p in $candidates) {
        if ($p -and (Test-Path -LiteralPath (Join-Path $p 'gst-launch-1.0.exe'))) { return $p }
    }
    $located = Get-Command 'gst-launch-1.0.exe' -ErrorAction SilentlyContinue
    if ($located) { return (Split-Path -Parent $located.Source) }
    throw 'GStreamer MSVC x64 Runtime was not found.'
}

function Has-GstElement([string]$name) {
    $prior = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $inspect $name 1>$null 2>$null
        return ($LASTEXITCODE -eq 0)
    }
    finally { $ErrorActionPreference = $prior }
}

function Gst-Value([string]$value) {
    # Values are parsed by gst-launch as GStreamer launch syntax, not as a shell.
    # Escape backslash and literal quotation marks, then quote the whole value.
    return '"' + $value.Replace('\', '\\').Replace('"', '\"') + '"'
}

$bin = Find-GstBin
$gst = Join-Path $bin 'gst-launch-1.0.exe'
$inspect = Join-Path $bin 'gst-inspect-1.0.exe'
$env:PATH = "$bin;$env:PATH"
# Capture the runtime version only at startup for correlating known GStreamer
# memory fixes. No network connection, camera credentials, or pipeline edits.
$originalPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    $versionLines = @(& $gst '--gst-version' 2>$null)
    if ($LASTEXITCODE -eq 0 -and $versionLines.Count -gt 0) {
        $versionLine = [string]$versionLines[0]
        if ($versionLine -match '^GStreamer') {
            Write-Host ('GStreamer runtime: ' + $versionLine) -ForegroundColor Cyan
        }
    }
} catch {
    # An unavailable version string must never abort a valid recording.
} finally {
    $ErrorActionPreference = $originalPreference
}
$rootGst = Split-Path -Parent $bin
$scanner = Join-Path $rootGst 'libexec\gstreamer-1.0\gst-plugin-scanner.exe'
if (Test-Path -LiteralPath $scanner) { $env:GST_PLUGIN_SCANNER = $scanner }

# GStreamer 1.28.2 fixed a gst_h264_parser_parse_nal() memory leak in
# videoparsersbad (upstream issue #4966 / MR !11060).
# The recorder uses h264parse on two RTSP inputs and the encoded output.
# Log ONLY the plugin version so existing recording logs can distinguish
# outdated parser builds from those known to include the upstream fix.
# This does not connect to a camera, modify the pipeline, or update packages.
$priorPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    $parserInfo = @(& $inspect 'h264parse' 2>$null)
    if ($LASTEXITCODE -eq 0) {
        $parserVersion = $null
        foreach ($infoLine in $parserInfo) {
            if ([string]$infoLine -match '^\s*Version\s+(\d+\.\d+\.\d+)\b') {
                $parserVersion = [version]$Matches[1]
                break
            }
        }
        if ($null -ne $parserVersion) {
            Write-Host ('H264 parser plugin (videoparsersbad): ' + $parserVersion.ToString()) -ForegroundColor Cyan
            if ($parserVersion.Major -eq 1 -and
                ($parserVersion.Minor -lt 28 -or
                 ($parserVersion.Minor -eq 28 -and $parserVersion.Build -lt 2))) {
                Write-Warning ('The upstream H.264 parser memory-leak fix first shipped in 1.28.2. ' +
                    'This installed plugin version may not contain it (backports are possible). ' +
                    'No GStreamer files or recording settings were changed.')
            }
        } else {
            Write-Host 'H264 parser plugin version: unavailable (gst-inspect output not recognized).' -ForegroundColor Yellow
        }
    }
} catch {
    # A metadata probe must never stop an otherwise valid recording.
} finally {
    $ErrorActionPreference = $priorPreference
}

$required = @('rtspsrc','rtph264depay','h264parse','decodebin','videoconvert',
              'videoscale','videorate','compositor','queue','x264enc',
              'splitmuxsink','mp4mux','fakesink',
              'audioconvert','audioresample','aacparse')
$missing = @($required | Where-Object { -not (Has-GstElement $_) })
if ($missing.Count -gt 0) { throw "Missing GStreamer elements: $($missing -join ', ')" }

# CPU-GROWTH EXPERIMENT: prefer the PRIMARY-ranked libav decoder when it
# really decodes a small synthetic H.264 stream; the prior app forced the
# MARGINAL-ranked OpenH264 decoder even with libav installed.
# This isolates the decoder implementation, NOT codec quality / A-V timing.
# Env override for a precise A/B: C545D_VIDEO_DECODER=openh264 or =avdec.
# The short local smoke test uses NO camera connection or credentials and
# cannot hang startup indefinitely. If the preferred decoder fails, retain
# the former implementation as a safe fallback.
function Get-C545DDecoderArgs([string]$candidate) {
    switch ($candidate) {
        'avdec_h264' { return @('avdec_h264') }
        'openh264dec' { return @('video/x-h264,stream-format=byte-stream,alignment=au','!','openh264dec') }
        'decodebin' { return @('decodebin') }
        default { throw ('Unsupported decoder candidate: ' + $candidate) }
    }
}
function Test-C545DDecoder([string]$candidate) {
    if (-not (Has-GstElement $candidate)) { return $false }
    # Explicit fixed test stream: 15 synthetic frames, 320x240 I420, 15fps.
    # No file output, no RTSP, no live recording interference.
    $testArgs = @('-q','videotestsrc','num-buffers=15','pattern=smpte',
        '!','video/x-raw,format=I420,width=320,height=240,framerate=15/1',
        '!','x264enc','speed-preset=ultrafast','tune=zerolatency','key-int-max=15',
        '!','h264parse','!') + @(Get-C545DDecoderArgs $candidate) + @(
        '!','videoconvert','!','video/x-raw,format=I420','!',
        'fakesink','sync=false')
    $testProcess = $null
    try {
        # -ArgumentList receives one string, made only of trusted static tokens.
        # The real RTSP address and password are deliberately never used here.
        $testProcess = Start-Process -FilePath $gst -ArgumentList ($testArgs -join ' ') `
            -WorkingDirectory $bin -WindowStyle Hidden -PassThru -ErrorAction Stop
        if (-not $testProcess.WaitForExit(10000)) {
            Write-Warning ("Decoder smoke test timed out: $candidate")
            try { $testProcess.Kill() } catch { }
            try { [void]$testProcess.WaitForExit(2000) } catch { }
            return $false
        }
        return ($testProcess.ExitCode -eq 0)
    } catch {
        Write-Warning ("Decoder smoke test error ($candidate): " + $_.Exception.Message)
        return $false
    } finally {
        if ($testProcess) { try { $testProcess.Dispose() } catch { } }
    }
}
$decoderChoice = ([string]$env:C545D_VIDEO_DECODER).Trim().ToLowerInvariant()
if (-not $decoderChoice) { $decoderChoice = 'auto' }
switch ($decoderChoice) {
    'auto' { $decoderCandidates = @('avdec_h264','openh264dec','decodebin') }
    'avdec' { $decoderCandidates = @('avdec_h264','openh264dec','decodebin') }
    'openh264' { $decoderCandidates = @('openh264dec','avdec_h264','decodebin') }
    default { throw "C545D_VIDEO_DECODER must be auto, avdec, or openh264." }
}
$decoderLabel = ''
$decoder = @()
foreach ($candidate in $decoderCandidates) {
    if (Test-C545DDecoder $candidate) {
        $decoderLabel = $candidate
        $decoder = @(Get-C545DDecoderArgs $candidate)
        break
    }
}
if (-not $decoderLabel) {
    throw 'No H.264 decoder passed a local synthetic encode/decode test. RTSP recording was not started.'
}
# Audio quality priority: prefer FFmpeg/libav AAC, the same codec family used by OBS.
# Do not silently fall back to voaacenc, which was preferred in earlier releases.
# Every encoder candidate must actually encode 48kHz mono AAC to an MP4 muxer
# in a short local synthetic test BEFORE any camera login is requested.
function Test-AacCandidate($choice) {
    $testArgs = @('-q', 'audiotestsrc', 'num-buffers=36', 'wave=sine',
              '!', 'audioconvert', '!', 'audioresample', '!',
              $choice.Caps, '!') + @($choice.Args) + @('!', 'aacparse', '!', 'mp4mux', '!', 'fakesink', 'sync=false')
    $prior = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $gst @testArgs 1>$null 2>$null
        return ($LASTEXITCODE -eq 0)
    }
    catch { return $false }
    finally { $ErrorActionPreference = $prior }
}

$choices = @(
    @{ Name='avenc_aac (FFmpeg/libav)'; Element='avenc_aac';
       Args=@('avenc_aac','bitrate=192000','aac-coder=twoloop');
       Caps='audio/x-raw,format=F32LE,layout=interleaved,channels=1,rate=48000' },
    @{ Name='fdkaacenc (FDK AAC)'; Element='fdkaacenc';
       Args=@('fdkaacenc','bitrate=192000','rate-control=cbr','afterburner=true');
       Caps='audio/x-raw,format=S16LE,layout=interleaved,channels=1,rate=48000' },
    @{ Name='mfaacenc (Windows Media Foundation)'; Element='mfaacenc';
       Args=@('mfaacenc','bitrate=192000');
       Caps='audio/x-raw,format=S16LE,layout=interleaved,channels=1,rate=48000' }
)
$audioChoice = $null
foreach ($choice in $choices) {
    if (-not (Has-GstElement $choice.Element)) { continue }
    if (Test-AacCandidate $choice) { $audioChoice = $choice; break }
}
if ($null -eq $audioChoice) {
    throw 'No high-quality AAC encoder passed the local 48kHz/192kbps MP4 test (avenc_aac, fdkaacenc, mfaacenc). Check GStreamer Libav/Bad plugins. Old voaacenc was intentionally not selected.'
}
$audioEncoderLabel = $audioChoice.Name
$audioEncoder = @($audioChoice.Args)
$audioCaps = $audioChoice.Caps

# Correct MP4 timestamp anomalies without touching the live recording/files.
# GStreamer h264timestamper derives DTS from the encoded H.264 SPS reordering
# data. Only after x264, not on either incoming RTSP stream. A synthetic
# B-frame + mp4mux EOS test chooses the guard safely at each normal startup.
# If unavailable/fails, fall back to previous path. C545D_DTS_GUARD=off rolls back.
function Test-C545DDtsPath {
    if (-not (Has-GstElement 'h264timestamper')) { return $false }
    $args = @('-e','-q','videotestsrc','num-buffers=45','pattern=ball',
        '!','video/x-raw,format=I420,width=320,height=240,framerate=15/1',
        '!','x264enc','speed-preset=ultrafast','bframes=3','key-int-max=15',
        '!','h264parse','!','h264timestamper',
        '!','mp4mux','!','fakesink','sync=false')
    $p = $null
    try {
        $p = Start-Process -FilePath $gst -ArgumentList ($args -join ' ') -WorkingDirectory $bin -WindowStyle Hidden -PassThru -ErrorAction Stop
        if (-not $p.WaitForExit(15000)) {
            try { $p.Kill() } catch { }
            try { [void]$p.WaitForExit(2000) } catch { }
            return $false
        }
        return ($p.ExitCode -eq 0)
    } catch {
        return $false
    } finally {
        if ($p) { try { $p.Dispose() } catch { } }
    }
}
$script:useDtsGuard = $false
if ($env:C545D_DTS_GUARD -ne 'off') {
    $script:useDtsGuard = Test-C545DDtsPath
}
Write-Host ('MP4 DTS guard: ' + $(if ($script:useDtsGuard) {
    'h264timestamper (synthetic test PASS)'
} else {
    'legacy path (guard absent, failed or disabled)'
})) -ForegroundColor Cyan

Write-Host "Audio: stream1 only, AAC mono 48kHz 192kbps target via $audioEncoderLabel [synthetic MP4 check PASS]" -ForegroundColor Cyan
Write-Host "Decoder: $decoderLabel" -ForegroundColor Cyan
# Long-running CPU-growth guard.  A fall-back switch is provided for a clean
# A/B comparison without changing video/audio encode quality.  The default is
# ON; set an environment variable C545D_TIME_DRIFT_GUARD=off to restore the
# exact RTSP timestamp and videorate properties from the prior medium version.
# In particular, preserve ntp-sync=true and tcp-timestamp=true for dual-lens
# synchronisation. No process recycle or automatic recording interruption.
$script:timeDriftGuard = $env:C545D_TIME_DRIFT_GUARD -ne 'off'
$script:rtspDriftArgs = @()
$script:videoRateArgs = @('videorate')
if ($script:timeDriftGuard) {
    # Limit per-frame changes to the NTP timestamp offset to 1ms. Prevent a
    # sudden RTCP SR correction from making the stream timestamp jump abruptly.
    $script:rtspDriftArgs = @('max-ts-offset-adjustment=1000000')
    # Input gaps must not cause videorate to synthesize an arbitrarily long
    # train of duplicate frames for the software compositor/encoder. A 300ms
    # gap covers normal jitter without spending CPU on very stale frames.
    $script:videoRateArgs = @('videorate','max-duplication-time=300000000','skip-to-first=true')
}
Write-Host ('Long-run timestamp guard: ' + $(if ($script:timeDriftGuard) {'ON'} else {'OFF (legacy behavior)'})) -ForegroundColor Cyan
Write-Host 'RTSP: stream1 on left / stream6 on right' -ForegroundColor Cyan
Write-Host 'MUX MODE: synchronous fragment finalize (targeted experiment, 2026-11-15)' -ForegroundColor Cyan

# Settings are stored separately from the ZIP, so updates do not erase them.
. (Join-Path $PSScriptRoot 'CommonSettings.ps1')
if (-not ((Test-Path -LiteralPath $configPath) -and (Test-Path -LiteralPath $secretPath))) {
    Write-Host 'First-time setup: camera login and output folder.' -ForegroundColor Yellow
    & (Join-Path $PSScriptRoot 'Configure.ps1')
}
$settings = Read-C545DSettings
$cameraIP = [string]$settings.camera_ip
$userName = [string]$settings.camera_user
$securePass = Read-C545DPassword
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePass)
try { $cameraPass = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }

# No GStreamer_Recordings folder is forced: save directly into the chosen folder.
$recordRoot = [string]$settings.output_folder
if (-not (Test-Path -LiteralPath $recordRoot -PathType Container)) {
    throw "The chosen recording folder is unavailable. Run 01_SETTINGS.cmd to change it."
}
function New-PendingPattern {
    # splitmuxsink requires a numeric segment placeholder. Until MP4 finalization,
    # use a timestamp-only pattern, with no camera prefix or random ID.
    $id = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss-fff'
    return (Join-Path $recordRoot ("${id}_%05d.mp4"))
}
$pattern = New-PendingPattern
$wideURL = "rtsp://${cameraIP}:554/stream1"
$teleURL = "rtsp://${cameraIP}:554/stream6"

# One compositor, one encoder and one segment muxer; branches are selected
# explicitly by SDP media caps (not by arrival order of dynamic RTSP pads).
$pipeline = New-Object 'System.Collections.Generic.List[string]'
function Add-Gst([string[]]$p) { foreach ($v in $p) { [void]$pipeline.Add($v) } }

Add-Gst @(
    'compositor','name=mix','background=black','ignore-inactive-pads=true',
      'sink_0::xpos=0','sink_1::xpos=1280',
    '!','video/x-raw,width=2560,height=720,framerate=15/1',
    '!','videoconvert','!','video/x-raw,format=I420',
    # Drop oldest *complete raw video frames* when the encoder falls behind.
    # 12 I420 frames at 2560x720 are ~32 MiB; the former unlimited queue
    # could accumulate gigabytes during a long recording.
    '!','queue','max-size-buffers=12','max-size-bytes=0',
        'max-size-time=0','leaky=downstream',
    '!','x264enc','pass=qual','quantizer=24','bitrate=15000',
         'speed-preset=medium','key-int-max=30','bframes=3','rc-lookahead=10',
    '!','video/x-h264,profile=high','!','h264parse'
)
# Correct DTS for the one H.264 stream after encoding; do not alter input RTSP
# NTP/PTS mapping, x264's B-frame count, or the recorded stream's quality.
if ($script:useDtsGuard) { Add-Gst @('!','h264timestamper') }
Add-Gst @(
    # Targeted experiment 2026-11-15: synchronous MP4 finalize avoids creating a
    # detached muxer/sink pair on every hourly fragment. Does NOT prove or fix
    # the separate continuous Heap growth. Verify possible pause at each split.
    '!','splitmuxsink','name=mux',"location=$(Gst-Value $pattern)",
         'max-size-time=3600000000000',
         'async-finalize=false','send-keyframe-requests=true'
)

function Add-Input([string]$name,[string]$url,[int]$side) {
    Add-Gst @('rtspsrc',"name=$name","location=$(Gst-Value $url)",
      "user-id=$(Gst-Value $userName)","user-pw=$(Gst-Value $cameraPass)",
      'protocols=tcp','latency=750','drop-on-latency=true',
      'ntp-sync=true','tcp-timestamp=true')
    # Apply the same clock-slew limit to both lens sources; do not shift one
    # stream independently or replace their existing NTP sync mechanism.
    if ($script:rtspDriftArgs.Count -gt 0) { Add-Gst $script:rtspDriftArgs }
    Add-Gst @(
      "$name.",'!','application/x-rtp,media=video,encoding-name=H264',
      # Keep H264 RTP queue bounded without dropping arbitrary RTP packets.
      # Backpressure + rtspsrc drop-on-latency avoids endless buffering.
      '!','queue','max-size-buffers=300','max-size-bytes=8388608',
          'max-size-time=2000000000',
      '!','rtph264depay','request-keyframe=true','wait-for-keyframe=true',
      # Force AU output from the depayloader, enabling its documented
      # wait-for-keyframe recovery after RTP packet loss.
      '!','video/x-h264,alignment=au',
      '!','h264parse','config-interval=-1','!')
    Add-Gst $decoder
    Add-Gst @('!','videoconvert','!','videoscale','!')
    Add-Gst $script:videoRateArgs
    Add-Gst @(
      '!','video/x-raw,format=I420,width=1280,height=720,framerate=15/1',
      '!','queue','max-size-buffers=8','max-size-bytes=0',
          'max-size-time=0','leaky=downstream',
      '!',"mix.sink_$side")
    if ($side -eq 0) {
        # Use only cam1's audio. decodebin auto-selects the RTP depayloader and
        # decoder according to SDP media caps (PCMA, PCMU, AAC, etc.).
        Add-Gst @("$name.",'!','application/x-rtp,media=audio',
              # Bounded audio RTP queue. Only discard old audio if downstream
              # is stalled for >3 s, instead of growing without limit.
              '!','queue','max-size-buffers=400','max-size-bytes=4194304',
                  'max-size-time=3000000000','leaky=downstream',
              '!','decodebin',
              '!','audioconvert','!','audioresample',
              '!',$audioCaps,'!')
        Add-Gst $audioEncoder
        Add-Gst @('!','aacparse','!','mux.audio_0')
    }
    else {
        # Discard the second copy of the same physical microphone.
        # The telephoto RTSP audio is never recorded. Keep only a small,
        # leaky handoff queue (instead of the default 200 buffers/10 MB/1 s).
        # Discard stale *unused* audio, never stream1's AAC or either video.
        # Do not retain the discarded last sample in fakesink.
        Add-Gst @("$name.",'!','application/x-rtp,media=audio',
                  '!','queue','max-size-buffers=8','max-size-bytes=262144',
                      'max-size-time=250000000','leaky=downstream',
                  '!','fakesink','async=false','sync=false','enable-last-sample=false')
    }
}
Add-Input 'cam1' $wideURL 0
Add-Input 'cam2' $teleURL 1

# Never echo the pipeline: it includes camera credentials in memory.
# The video graph and bounded queues are preserved; stop is now an explicit state.
# The separate naming worker renames only finalized, CLOSED MP4 fragments.
$initialMuxLocation = "location=$(Gst-Value $pattern)"
$muxLocationIndex = $pipeline.IndexOf($initialMuxLocation)
if ($muxLocationIndex -lt 0) { throw 'Output location for splitmuxsink could not be located.' }

# File naming is handled by an optional short-lived GUI-launched helper.
# Recording never depends on whether this helper starts successfully.
Write-Host 'File naming: GUI-managed (does not block recording).' -ForegroundColor Cyan

$attempt = 0
$gstArgs = $null
try {
    while ($true) {
        if (Test-C545DStopRequested) {
            Write-Host 'Stop requested; skipping any new RTSP session.' -ForegroundColor Cyan
            break
        }
        if ($attempt -gt 0) {
            # Avoid reconnecting too quickly to a server that may still hold
            # the previous RTSP sessions. A new folder avoids overwrites.
            $pattern = New-PendingPattern
            $pipeline[$muxLocationIndex] = "location=$(Gst-Value $pattern)"
        }
        $attempt++
        Write-Host "Recording in: $recordRoot" -ForegroundColor Green
        Write-Host 'Finalized files will be renamed to YYYY-MM-DD_HH-mm_HH-mm.mp4 by the GUI.' 
        Write-Host '1-hour MP4 segments. Stop: Ctrl+C, wait for finalization.'
        Write-Host 'Output: side-by-side H.264 video + ONE AAC track (mono 48kHz / 192kbps target).'
        Write-Host "Connection attempt: $attempt"

        $gstArgs = @('-e') + $pipeline.ToArray()
        Write-Host ('GStreamer launching (EOS enabled); attempt=' + $attempt)
        $previousErrorAction = $ErrorActionPreference
        $rc = 1
        try {
            # PS 5.1 may surface native program stderr as NativeCommandError.
            $ErrorActionPreference = 'Continue'
            & $gst @gstArgs
            $rc = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorAction
            $gstArgs = $null
        }
        $ctrlCEvents = Take-C545DUnexpectedCtrlCCount
        $authorizedStop = Test-C545DStopRequested
        Write-Host ('GStreamer returned; exitCode=' + $rc + '; stopMarker=' +
            $authorizedStop + '; consoleCtrlCEvents=' + $ctrlCEvents)
        if ($authorizedStop) {
            if ($rc -eq 0) {
                Write-Host 'Recording stopped by GUI; GStreamer EOS completed.' -ForegroundColor Green
            } else {
                Write-Warning "GUI stop requested; GStreamer exit=$rc. Final MP4 may need checking. No reconnect."
            }
            break
        }
        if (-not $StopFile -and $rc -eq 0) {
            # Preserve manual console invocation semantics: interactive
            # CTRL+C ends a standalone Record.ps1 session.
            Write-Host 'Standalone recording ended without GUI control session.' -ForegroundColor Yellow
            break
        }
        # An unsolicited CTRL+C can cause gst-launch -e to exit with code 0.
        # Previously this was mistaken for an authorized stop and the 24x365
        # recording was silently abandoned (2026-11-17 worker PIDs
        # 660/11292/11120). The GUI stop marker is the only authority.
        # A clean or nonzero unexpected exit both reconnect after backoff;
        # force-restarting without EOS would risk corrupting the current MP4.
        if ($ctrlCEvents -gt 0) {
            Write-Warning ('UNEXPECTED_CTRL_C without GUI stop marker; ' +
                'previous GStreamer EOS finished; recovering capture.')
        } elseif ($rc -eq 0) {
            Write-Warning 'UNEXPECTED_GSTREAMER_EXIT (code 0, no GUI stop); recovering capture.'
        }
        # Do not propagate a transient EOF as a fatal PowerShell exception.
        # Back off before retrying. Retrying cannot recover an existing gap.
        $seconds = [Math]::Min(60, [Math]::Max(20, (10 * $attempt)))
        Write-Warning "GStreamer exited with code $rc. Retry in $seconds seconds unless stopped."
        # Poll instead of one uninterruptible long sleep. The GUI can stop
        # the worker even while it is waiting between RTSP reconnect attempts.
        for ($i=0; $i -lt ($seconds * 4); $i++) {
            if (Test-C545DStopRequested) { break }
            Start-Sleep -Milliseconds 250
        }
    }
}
finally {
    $cameraPass = $null
    $securePass = $null
    $gstArgs = $null
    $pipeline.Clear()
}
