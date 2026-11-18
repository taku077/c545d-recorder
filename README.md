# C545D Recorder — public source baseline

A Windows 10 x64, PowerShell 5.1 + GStreamer recorder for two RTSP feeds from Tapo C545D.

## Current baseline (2026-11-16)
- Source: `C545D_新デコーダ版_簡単起動_2026-11-16.zip`
- Launch: double-click `C545D_Start.vbs`
- H.264 decoder: prefer `avdec_h264`, fallback when unavailable
- Output: 2560×720 / 15fps; x264 `medium`, quantizer 24; hourly MP4 segments
- Status: candidate only, **not** verified for unattended 24×365 operation.
- Priority 1: no CPU usage increase as recording time elapses.
- Priority 2: private memory must converge; prevent unbounded growth.
- Preserve two-stream synchronization, audio, stop/restart behavior and MP4 continuity.

## Privacy
This public repository is for source, CI and sanitized notes only.
**Never upload** camera IPs, usernames/passwords, local settings, DPAPI files,
raw recordings, WPR ETL files or unredacted logs (including to the private repo).
No actual network credentials are needed for CI.

## Roadmap
1. Establish an auditable source baseline.
2. Run source checks on public GitHub Actions using a Windows runner.
3. Fix and verify long-duration CPU and memory behavior.
4. Migrate UI/control to C# WinForms and build a Windows EXE.

The source code is user-owned material from the project; third-party dependencies
retain their own licenses. No project-wide license has yet been selected.

## Continue development in a new ChatGPT conversation
**START HERE:** [docs/ACTIVE_HANDOFF.md](docs/ACTIVE_HANDOFF.md) and [docs/HANDOFF_READ_FIRST.md](docs/HANDOFF_READ_FIRST.md). The former is automatically refreshed from the active development PR and its CI runs. The older [docs/HANDOFF_CURRENT.md](docs/HANDOFF_CURRENT.md) on `main` is an archived baseline and MUST NOT override results from the active development branch. Verify the live PR HEAD and CI status before resuming.
