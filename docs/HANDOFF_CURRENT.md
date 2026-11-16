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
