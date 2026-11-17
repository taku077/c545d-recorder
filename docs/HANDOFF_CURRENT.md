# HANDOFF_CURRENT — C545D recorder

**Last updated:** 2026-11-16 (JST)  
**Purpose:** Canonical cross-chat handoff. When the user says **「続きから再開してください」** in the context of the C545D recorder, **read this document first**, inspect the current GitHub HEAD/CI/PRs and continue from the next action rather than restarting diagnosis.

## Confirmed user environment result — 2026-11-16 (supersedes previous version blocker)

- The read-only process-path-based `gst-inspect-1.0 h264parse` check **succeeded**.
- Reported `h264parse` plugin version: **1.28.8.1**.
- The GStreamer installation is a **per-user Windows MSVC x86_64 installation** under Local AppData (do not publish the personal Windows account name or absolute path).
- Because upstream fixed `gst_h264_parser_parse_nal()` in **1.28.2**, the inspected 1.28.8.1 plugin is expected to **already contain that fix** in a standard official build. The specific previously suspected parser leak therefore drops in priority as explanation of the observed residual growth; do NOT recommend updating the runtime on the basis of that fix alone.
- The command also emitted warnings: `External plugin loader failed` and `Failed to load plugin gstpython.dll` (unresolved DLL dependency). These warnings refer to the plugin-scanner helper and Python binding plugin, **not evidence that H.264 parsing or the active recording failed**. The requested `h264parse` version was returned successfully. The recorder does not directly require `gstpython.dll`; do not delete DLLs or reinstall while recording.
- This version verification **completes the previous immediate blocker**. Do **not** ask for this same version again unless the installed GStreamer changes.
- **Next engineering task:** investigate the still-unexplained positive private-memory slope, checking current 1.28.8.1 components and actual object lifetime, allocator/RTSP and muxer behavior, before proposing a targeted fix. Preserve `avdec_h264` CPU improvement and current A/V sync/recording settings. Do not add speculative diagnostic loops or daily auto-restarts.
- The currently running recording is unaffected by the PowerShell inspection. No GitHub code changes to the recorder were needed for the version check.
- References: https://gstreamer.freedesktop.org/releases/1.28/ ; https://gstreamer.freedesktop.org/documentation/installing/on-windows.html ; https://discourse.gstreamer.org/t/user-getting-error-priv-gst-plugin-load-file-for-registry-module-open-failed/4499

## Canonical repositories
- Public source and GitHub Actions: https://github.com/taku077/c545d-recorder
- Private sanitized development notes: `taku077/c545d-recorder-internal` (requires connected GitHub access).
- Public issue for long-run stability: https://github.com/taku077/c545d-recorder/issues/1 (OPEN).
- Merged PRs: [#2](https://github.com/taku077/c545d-recorder/pull/2) baseline regression checks; [#3](https://github.com/taku077/c545d-recorder/pull/3) GStreamer core version logging and existing CSV analyzer; [#4](https://github.com/taku077/c545d-recorder/pull/4) H.264 parser plugin version reporting and upstream leak eligibility note.
- Last verified public `main` when this was authored: `d3854fe98421a6f6b2d92c2819f3844792921374`. Check the live HEAD before editing; do **not** assume it remains unchanged.
- Last verified successful Windows CI: https://github.com/taku077/c545d-recorder/actions/runs/43852965696 (syntax, invariants, synthetic tests, ZIP packaging; NOT a real camera recording test).

## User's goal and non-negotiable constraints
- 24 hours/day, 365 days/year unattended security recording from Tapo C545D, combining two RTSP feeds into **one** video with efficient storage.
- Wide `stream1` on left, telephoto `stream6` on right. Preserve 2-stream time synchronization, audio continuity, one-hour MP4 segments, safe stop/restart and file naming.
- x264 **medium**, quantizer **24**, **2560×720**, **15fps**; AAC mono 48kHz / 192kbps target. Do not silently switch to fast, GPU decode or unrelated new technologies.
- Priority was NOT a low instantaneous CPU percentage, but **CPU usage increasing with elapsed recording time**. This improved substantially after preferring `avdec_h264` over `openh264dec`. Do not undo that baseline.
- Next open technical objective is **private-memory growth over time**, without reducing video/audio quality or causing recording gaps.
- No forced daily/periodic restart as an alleged fix; preserving evidence continuity matters.
- Eventually port to C# WinForms EXE with public Windows GitHub Actions; **not yet** and not until the existing pipeline is stable. No Visual Studio/.NET SDK required on the end-user recording PC.

## Known empirical results (sanitized aggregates only)
- New `avdec_h264`-preferred run: around **15h23m**, measured CPU around **19–21%** over hourly windows; private memory **593.7MB to 706.1MB**.
- Post-six-hour regression: approximately **+6.17MB/hour**, R² about **0.9965**. No plateau observed; no established root cause.
- Earlier `openh264dec`-preferred run had rising CPU toward ~40% and much faster memory growth.
- The working pipeline includes three `h264parse` elements; earlier ETL analysis reported allocation paths through `gstvideoparsersbad.dll`.
- GStreamer 1.28.2 release notes identify a fix for a memory leak in `gst_h264_parser_parse_nal()` (issue #4966 / MR !11060). **Candidate only**, not proof of causality; possible downstream backports.
- Current recorder's installed GStreamer core / h264parse plugin versions have **not yet been established**.

## IMMEDIATE NEXT STEP (current blocker, 2026-11-16)
The user tried a previous PowerShell path check and received **「GStreamerが見つかりません」**. The failed command only searched three assumed directories, so this **does not establish that GStreamer is absent**. The working recorder itself previously found GStreamer (`Record.ps1` also has a `Get-Command` fallback).

Ask for the output of this **read-only** PowerShell command, preferably **while recording**, which derives the actual `gst-inspect-1.0.exe` path from the running `gst-launch-1.0.exe` process:

```powershell
$p = Get-CimInstance Win32_Process -Filter "Name = 'gst-launch-1.0.exe'" | Select-Object -First 1
if ($p -and $p.ExecutablePath) {
    $gst = Join-Path (Split-Path $p.ExecutablePath -Parent) 'gst-inspect-1.0.exe'
    if (Test-Path -LiteralPath $gst) {
        & $gst h264parse | Select-String '^\s*Version\s+'
    } else { Write-Host "gst-inspect.exeが同じフォルダーにありません" }
} else { Write-Host "録画中のGStreamerプロセスが見つかりません" }
```

Interpretation:
- Plugin version **1.28.2 or newer** in the 1.28 branch: upstream parser fix expected to be present; look at other causes if memory still increases.
- Plugin **older**: relevant upstream fix might be missing; check backports and compare supported, verified official MSVC x64 GStreamer runtime **side by side** with rollback and **only after safe stopping**, never during a live recording.
- If process not present, don't claim it is uninstalled. Check whether recording is actually active; alternatively use `Get-Command gst-launch-1.0.exe` and existing log, without full HDD searches.
- If version output unavailable due to permissions, may use `Get-Process` `Path` or point-and-click Task Manager -> open file location.

## Working-code scope and guardrails
- User launcher: `C545D_Start.vbs`.
- GUI: `C545D_App.ps1` ; recorder: `Record.ps1`; worker: `RecordGUIWorker.ps1`; filename processing: `SegmentNamerWorker.ps1` / `SegmentNamer.ps1`; settings helper: `CommonSettings.ps1`.
- `Record.ps1` on current GitHub main logs `GStreamer runtime:` and `H264 parser plugin (videoparsersbad):` **at next startup only** (current already-running recorder will not automatically obtain new logging).
- Never claim CI proves actual 24x365 stability. Changes go in feature branches, are checked on `windows-2022` CI and PR, then merged if supported; `main` is a known-good candidate baseline.
- Public repo may be read by anyone; no camera credentials, local IP, usernames/passwords, `settings.json`, `camera_password.dpapi`, recorded media, ETL, or raw diagnostic logs in either repo. Sanitize any analysis.

## To resume reliably
1. Read **this** file and, if accessible, the private `docs/HANDOFF_CURRENT.md`.
2. Check current GitHub main SHA, Issue #1, open PRs and latest CI.
3. Continue from current blocker / user-supplied version result; don't re-ask already answered constraints or repeat costly diagnostic loops.
4. If the user only says **「続きから再開してください」** and multiple ongoing projects make the reference ambiguous, confirm this is the C545D recorder rather than silently choosing another project.


## Follow-up: plugin scanner file exists (2026-11-16 JST)
- User confirmed the PowerShell scanner existence probe returned **「補助プログラム：存在します」**.
- Therefore, `gst-plugin-scanner.exe` is present at the path derived from the actual running GStreamer executable. The earlier warning `External plugin loader failed` means it could not be launched/used in that invocation; **file absence is ruled out**, but missing DLL dependencies, environment PATH/scanner configuration, permissions, etc. remain possible.
- `gstpython.dll` failed to load with Windows' missing-module message. This can indicate a dependency of that DLL is absent; it does NOT prove the plugin file itself is missing. This optional Python plugin is not directly required by the C545D recorder pipeline.
- **Next safe test**: run `gst-inspect-1.0 h264parse` from the currently running GStreamer executable's directory in a separate PowerShell process/session with temporary, process-local `PATH` prepended with its `bin` folder and `GST_PLUGIN_SCANNER` set explicitly to the existing scanner path. Do not write system environment variables or interrupt live recording. Compare warnings; note registry caching can suppress re-scans, so absence of warning in one run is not definitive.
- If warning persists under correct environment, focus on missing dependency or scanner execution failure; do NOT reinstall or delete DLLs speculatively. Preserve `avdec_h264` stability and long-run memory work.
- Official docs: https://gstreamer.freedesktop.org/documentation/installing/on-windows.html ; https://gstreamer.freedesktop.org/documentation/gstreamer/running.html


## Repeated scanner warnings with process-local environment — 2026-11-16 JST
- User reran `gst-inspect-1.0 h264parse` with the **actual running** `gst-launch` binary directory prepended to `PATH` and `GST_PLUGIN_SCANNER` pointed explicitly at the existing scanner executable. **Both warnings persisted**: `External plugin loader failed` and `Failed to load plugin ... gstpython.dll` (Windows reported missing module). `h264parse Version 1.28.8.1` was returned again.
- A simple omitted `PATH` or `GST_PLUGIN_SCANNER` setting is therefore **not enough** to explain/fix the symptoms. Do not repeat that test or claim the complete install failed.
- Scanner existence was previously confirmed, but not that it executes successfully; DLL/CRT dependency, plugin scanner start failure, plugin path/registry issues remain hypotheses. `gstpython.dll` is optional for this recorder and may have a missing transitive dependency.
- Upstream `gstregistry.c` falls back to in-process scanning if external loader fails, explaining how required plugins can remain available. Matching discussion: https://discourse.gstreamer.org/t/user-getting-error-priv-gst-plugin-load-file-for-registry-module-open-failed/4499 . Official Windows setup: https://gstreamer.freedesktop.org/documentation/installing/on-windows.html
- **Recommendation:** Do not delete `gstpython.dll`, globally set `GST_REGISTRY_FORK=no` as if that fixed the root cause, delete the plugin registry cache, reinstall, or interrupt currently working evidence recording just to silence warnings. These messages have **not** been tied causally to the remaining +6.17MB/h private-memory growth.
- **Next action:** Keep working recorder unchanged. If a specific necessary recording element fails or the user prioritizes warning repair, diagnose the exact failing helper/DLL dependency using a bounded, evidence-driven test before recommending a repair; otherwise prioritize identifying long-run memory growth separately.


## EXE migration stage 1 built — 2026-11-16 (user requested pivot while memory runs)
- On 2026-11-16 user suggested checking private-memory trend **tomorrow (2026-11-17)** after a longer recording, and doing EXE work meanwhile. Respect this ordering. Do not infer residual leak fixed from the EXE build.
- Public [PR #5](https://github.com/taku077/c545d-recorder/pull/5) was **merged** (main commit `fac5263676e5f687214a8365c13475692ca985a9`). C# `.NET Framework 4.8` x64 `WinExe` was created at `src/C545D.Launcher/`. In this **stage-1 launcher**, `C545D_Recorder.exe` launches the **existing PowerShell WinForms GUI** (script `C545D_App.ps1`) in hidden STA PowerShell and sets `C545D_VIDEO_DECODER=avdec`; it exits while the original app manages the session.
- The nine existing .ps1/.vbs/README baseline files were not edited in this PR. Stop markers, CTRL+C→EOS, RTSP pipeline, AAC, 2560×720/15fps, x264 medium/Q24 and filename handling stay unchanged.
- New workflow `.github/workflows/build-exe.yml` uses `windows-2022` and `microsoft/setup-msbuild@v3` to build, package and smoke-test in a Unicode directory **without connecting to a camera**. PR CI passed: https://github.com/taku077/c545d-recorder/actions/runs/43863192829 . Main workflow: https://github.com/taku077/c545d-recorder/actions/runs/43863396922 ; job passed.
- Main workflow generated artifact named `c545d-exe-win10-x64` containing `C545D_Recorder_EXE_Win10_x64.zip`, with `C545D_Recorder.exe` and nine original source files. Current artifact expires 2026-11-23 UTC; download from the workflow run's **Artifacts** section while signed into GitHub. It may require unzipping the artifact wrapper then the app ZIP.
- Critical truth: this is **an EXE launcher**, not a complete C# WinForms controller or standalone single-file recorder; it still requires the bundled PowerShell scripts and separately installed GStreamer. No real Windows 10 camera recording validation yet. Do not instruct running it in parallel with currently active recorder.
- User's Windows 10 22H2 has `.NET Framework 4.8` as part of the OS, so no extra .NET runtime or Visual Studio should be needed. Source: https://learn.microsoft.com/en-us/dotnet/framework/install/on-windows-10 .
- Follow-on work is tracked in [Issue #6](https://github.com/taku077/c545d-recorder/issues/6): native C# WinForms **UI/control** port while retaining the working PowerShell/GStreamer back-end until confirmed stable. Preserve optional rename worker and safe stop/EOS semantics; test state transitions before on-device deployment.
- Tomorrow's memory review: use the **existing** local `Memory_Trend.csv` (or sanitized aggregate) over the extended session. Compare post-warmup private-memory slope with prior ~+6.17 MB/hour and check plateau without disrupting recording. Do not demand repeated costly diagnostics if existing data suffices.


## Memory mitigation candidate PR #7 — 2026-11-17 JST
- User explicitly requested an actual code change, without installing further diagnostic tools or repeating 24–48h waiting loops.
- Two VMMap snapshots from the same gst-launch PID (4820), about 18m04s apart, showed Heap committed roughly +5.64 MiB, with existing Heap about +3.39 MiB and one new Heap region about +2.23 MiB. This **does not identify** the allocating plugin, prove a leak or establish that any one branch caused the increase.
- PR #7 changes only the **discarded** telephoto/stream6 RTP audio branch in Record.ps1: queue max-size-buffers=8/max-size-bytes=262144/max-size-time=250000000/leaky=downstream; fakesink enable-last-sample=false. Default GStreamer queue was already bounded (200 buffers/10 MB/1 s); do not claim the old queue was unbounded.
- Recorded stream1 AAC, both videos, avdec_h264, x264 medium/Q24, 2560x720/15fps, NTP/tcp sync, splitmuxsink hourly segments, stop/EOS are not changed.
- This is a concrete retention-reduction patch, **NOT a verified fix for the residual Heap slope**. No real camera test or 24×365 validation was performed by public CI.
- If build/CI passed and main was merged, use new main artifact only at a safe stop, preserving rollback to 2026-11-16 known-good baseline. Do not run the old and new recorders simultaneously.
- No further user-installed tool is required for this candidate. Actual slope/quality changes require comparing existing Memory_Trend.csv over the same PID and checking MP4/AAC/dual-lens sync on the user PC.


## Stage 2 native WinForms EXE — 2026-11-17 JST (PR #8)
- User reported **stage-1 launcher EXE successfully starts recording on their PC**. This is a user-observed start/record result, NOT a passed stop/EOS/restart/long-run test.
- The Stage-2 candidate replaces the stage-1 PowerShell GUI launcher with a **native C# WinForms controller** in src/C545D.Launcher/RecorderForm.cs. It retains the UNCHANGED Record.ps1/RecordGUIWorker.ps1 media path and original C545D_App.ps1/C545D_Start.vbs as rollback.
- Native controller includes camera settings, same-user DPAPI secret via stdin-only PowerShell C545D_SettingsBridge.ps1, session-specific stop/ready markers, console Ctrl+C and GStreamer -e EOS, optional event-driven rename worker, restart after stop, tray actions, memory CSV and explicit emergency stop.
- No modification to x264 medium, Quantizer 24, 2560×720/15fps, avdec_h264 preference, AAC, dual RTSP NTP/tcp timestamp or hourly MP4 splitting.
- Public Windows GitHub Actions verifies compilation, synthetic native GUI startup and synthetic DPAPI round-trip. It CANNOT prove real-camera EOS stop, MP4 playback, RTSP sync or 24×365 stability. The user must preserve old stage-1 app until a normal real-PC stop→restart check is completed at a safe stop opportunity.
- Artifact accessibility: user reported **Actions > Artifacts did not expose a clickable download**, despite existing artifacts. GitHub docs require a signed-in account with read access for Actions artifacts and note expiry. Stage-2 workflow publishes a numbered **prerelease asset** to https://github.com/taku077/c545d-recorder/releases after successful push to main; direct ZIP links from Releases are the preferred download path. Also attach ZIP directly in ChatGPT when possible.
- This migration is NOT evidence that the unexplained private Heap increase (+5.64 MiB in ~18min VMMap comparison, historical post-warmup +6.17 MiB/h) has been fixed. Do not add user-installed diagnostics or 24–48h waiting loops as a default.
- Confirm GitHub main HEAD / PR #8 merge / release asset URL / live CI before continuing. The last known working stage-1 build is separate; never run both versions simultaneously.


## 2026-11-17 — RC11 interrupted-recording recovery
- Existing user logs: Native GUI worker PIDs 660, 11292, 11120 ended with `GStreamer returned; exitCode=0; stopMarker=False`, while gst-launch reported `handling interrupt`. Cause of unsolicited console events is **not proven**; native Stage 2 displayed a console and RC10 addressed it.
- Previously Record.ps1 treated any C545DWorkerStopSignal.StopRequested as an authorized stop and also treated gst exit-code 0 as terminal for a managed session. This can silently end an evidence capture without the GUI stop marker.
- RC11 only recognizes the per-session durable GUI `.stop` marker as authorized. Unexpected `CTRL_C_EVENT` or any unexpected GStreamer exit now follows existing bounded backoff/reconnect, even when gst exits code 0. Preserve standalone PS1 Ctrl+C behavior when no control session exists.
- Worker counts console control events via atomic counter (no I/O in control handler); logs `consoleCtrlCEvents`, `UNEXPECTED_CTRL_C`, `UNEXPECTED_GSTREAMER_EXIT` and explicit exit-policy. Native WinForms shows a red status and logs `UNEXPECTED_WORKER_EXIT` if the worker itself dies without a stop request.
- Unit tests for pure exit policy are executed in Windows CI without connecting cameras; original source invariant tests, native UI, DPAPI and EXE smoke tests remain. No recorder format/quality/synchronization change. Unknown real-camera success; do not claim a fixed memory leak or resolved libav/qtmux issue.
- Never run two recorders simultaneously. Keep RC10 as rollback and switch only after normal stop/EOS finalization.


## 2026-11-17 — RC13 H264 decoder / muxer timestamp errors
- User clarified that CTRL+C on visible Stage 2 console was **manually pressed by the user** because of error output; it is NOT evidence of unsolicited interruptions. Do not present worker PIDs 660/11292/11120 as spontaneous CTRL+C. Previous attribution in RC12 plan was incorrect. RC12 reconnect code remains in main for now, but the requested RC13 work **specifically targets repeated libav 'no frame!' and qtmux 'decreasing DTS'**, not UI/stop controls.
- FFmpeg H264 decoder's 'no frame!' is produced when no decodable slice/frame is present in packet; the RTSP logs show repeated examples near camera GOP cadence for both inputs (see GStreamer official docs and libavcodec h264dec.c source).
- Before RC13 parser used config-interval=-1 (reinsert SPS/PPS at each IDR). RC13 conditionally switches to config-interval=0 + byte-stream,alignment=au after rtph264depay; tests with synthetic RTP stream before camera startup, logs strategy; C545D_H264_INPUT=legacy rollback.
- qtmux decreasing DTS may be video or AAC; RC10's optional h264timestamper protects encoded video DTS but does not ensure AAC timestamp monotonicity. RC13 conditionally inserts audiorate skip-to-first=true tolerance=40000000 in stream1 decoded audio before AAC, with an AAC/MP4 synthetic preflight; C545D_AUDIO_TS=legacy rollback. This may insert/drop samples at discontinuities.
- No changes to video x264 medium/Q24, 2560×720 15fps, two NTP-linked sources, AAC target, 1h MP4 split, or stop/EOS. No filtering or suppression of GStreamer error messages.
- Synthetic pipeline success demonstrates negotiation only. It is **not proof** that camera-specific libav errors, MP4 DTS, or increasing Heap usage are fixed. Do not claim production validation.
- No extra user software installations or destructive MP4 testing. Existing worker transcript will show H264 RTP input guard, AAC timestamp guard and MP4 DTS guard states.


## 2026-11-17 — RC16 opt-in media diagnostic launcher
- User consented to a comprehensive evidence-first investigation, with tool/log requirements declared upfront, focused on `libav: no frame!`, `qtmux decreasing DTS`, and subsequent Heap retention.
- PR adding `START_DIAGNOSTIC.cmd`: no recorder pipeline edits, no new tools, and no debug logging in normal EXE start. Run only after normally stopping any active recorder.
- Launcher sets `GST_DEBUG=*:2,rtph264depay:5,h264parse:5,rtpjitterbuffer:4,qtmux:5,audiorate:4,splitmuxsink:4`, `GST_DEBUG_FILE=%LOCALAPPDATA%\C545D_GStreamer\Logs\GST_DIAG_%p_%r.log`, `GST_DEBUG_NO_COLOR=1` **only for subprocesses started from launcher**. Each child process gets unique file by PID/random. On short (~5–10min) diagnostic recording, provide Recording_*.txt, relevant largest gst-launch GST_DIAG_*.log (after checking for any RTSP credentials), optional Stop_Control.log only for genuine stop problem, Memory_Trend.csv if memory is focus.
- GStreamer official documentation confirms debug categories and GST_DEBUG_FILE %p and %r substitution. Do not assume warning-count=damaged frame-count; first attribute to stream and actual decoder damage.
- No extra tools now. If Heap cause demanded later, Microsoft Debugging Tools package GFlags+UMDH should be disclosed as one staged dependency (needs per-image UST prior to process launch). Wireshark already present optional for evidence of network packet anomaly.
- Stage RC16 is *diagnostic capture only*, not a cure for existing decode/DTS or Heap warnings.


## 2026-11-17 — Privacy-preserving diagnostic export
- User wants to upload logs directly to ChatGPT but correctly notes manual credential searching through enormous `GST_DIAG_*.log` is too much work.
- Added `EXPORT_SAFE_LOGS.cmd` + `Export-SafeDiagnostics.ps1`: schema-only allowlist export, no raw log lines, URLs, passwords, user names, local paths, raw debug text, or MP4 bytes in the ZIP. Scans latest 8 matching log files, up to 400k lines each, caps exported events at 18k; emits `summary.txt` and `media_events.tsv` to `C545D_SAFE_DIAGNOSTICS_<time>.zip` in Downloads. No admin/additional software. Source log and recordings are read-only.
- Synthetic Windows CI test includes literal credential, RTSP URI, IP and base64 token and verifies ZIP excludes them while retaining `LIBAV_NO_FRAME` and `QTMUX_DTS_BACKWARD`.
- Scope: lossy diagnostic extract; it may not suffice to distinguish audio/video pad or precise H264 AU issue. If insufficient, enhance safe allowlist (not ask user to browse raw logs manually). Never claim generic redaction guarantees all arbitrary log text.
- User should upload safe ZIP to existing ChatGPT conversation only; no raw log into public GitHub issues. Personal ChatGPT data controls may affect training and retention; avoid categorical security guarantees.


## 2026-11-17 — Safe ZIP first actual user capture, exporter V2
- User uploaded `C545D_SAFE_DIAGNOSTICS_20261117_182408.zip` (schema only: media_events.tsv + summary.txt). We inspected exact bytes in current turn. Original V1 exporter selected 8 logs, `LOG_02` read 400000 lines then stopped. It exported the first 18000 events, of which 15446 were routine DEBUG_SAMPLE, 2553 LIBAV_NO_FRAME (about 0.5s through 115.15s), one DISCONTINUITY. Summary counted 4242 LIBAV_NO_FRAME (including events not exported). No QTMUX_DTS_BACKWARD in exported subset, which does **NOT** exclude later qtmux DTS events. The exported error cadence was ~22/s, not once per 2s. Counts represent decoder error messages NOT confirmed missing frames.
- V2 exporter addresses V1 selection/cap issue by scanning newest diagnostics (2 largest among 12 latest GST_DIAG; 2 latest Recording logs), aggregating **all scanned** event counts per second, exporting only a few representative messages per second, and preserving QTMUX/dynamic error events. Output: summary.txt, media_events.tsv, event_rates.tsv. Scan is bounded to 5m lines/file and 10m lines total; must disclose TRUNCATED if any limit hit.
- CI synthetic test injects 20000 ordinary H264 debug lines *before* additional `no frame!`/qtmux DTS events and checks both are counted after previous V1 cap, plus fake password/IP/Authorization/RTSP URL do not appear. No raw messages copied, no new installs.
- User should **not** run another recording if original raw `GST_DIAG_*.log` files remain: install V2 exporter ZIP, double-click EXPORT_SAFE_LOGS.cmd, share newly generated SAFE_DIAGNOSTICS ZIP privately in conversation. Note that detailed logs are highly sensitive and safe schema-only report is intentionally lossy.
- Root cause H.264 vs qtmux vs native Heap remains unproven. Do not move to speculative pipeline repairs from V1 counts alone.
