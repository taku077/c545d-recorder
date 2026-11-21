# C545D — consolidated Windows 10 host acceptance plan (DRAFT / NOT AUTHORIZED)

**Status: HOLD. This is an AI-side plan, NOT permission to stop recording, swap
DLLs, run the candidate, or upload video/credentials.**

## Evidence already retained — DO NOT rerun

- The user reported the read-only Windows 10 official GStreamer 1.28.8 MSVC
  core DLL reference fingerprint: 6/6 exact SHA256, 0 missing/PE errors,
  Windows10=1, existing recorder active=1, check exit=0.
- Isolated Windows2022 CI verified candidate GIO ABI (2047 exported names),
  actual app-local module identity, synthetic GIO/WAV output, rollback,
  and several negative rejection paths. Six-case follow-up CI also verified
  falsified numeric fingerprint and altered candidate manifest refusal.
- Prior corrected 64-cycle CI-only A/B: PrivateUsage effect decreased
  98.2414% (official +91,533,312 B; candidate +1,609,728 B), Key-handle
  effect official +20,932 and candidate +2. This is NOT proof of zero slope,
  zero residual growth, or Windows 10/Tapo runtime stability.
- Source-level regression gate verifies 2 inputs, stream1 wide left,
  stream6 tele right, 2560x720 15fps, x264 medium QP24, AAC mono48kHz
  192kbps target, one-hour splitmuxsink, EOS and safe stop.

## Required remaining AI-side gates BEFORE asking user to do anything

1. Complete latest Windows2022 CI for plugin-path isolation and fail-closed
   recursive cleanup against reparse points. Record both successful and
   intermediate failing runs, and inspect the actual numeric artifacts.
2. Independently audit the **existing 7-file future-only camera-free package**:
   exact candidate binary SHA256, six hardcoded SDK reference values, source
   syntax on PowerShell 5.1, approved/blocked flags, record-active refusal,
   true loaded-GIO module path, ownership marker, link/reparse refusal,
   failure cleanup, environment-variable restoration, and safe child exit.
   A created ZIP alone is not host approval.
3. The future-only launcher remains **camera-free and NOT HOST APPROVED**.
   Four independent Windows2022 CI milestones are now completed:
   (a) [#44874736247 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44874736247): official MSVC1.28.8 SDK, real candidate GIO module observed, five shortened synthetic H264/AAC MP4 fragments verified.
   (b) [#44878301067 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44878301067): real TCP localhost RTSP on 127.0.0.1:554 /stream1 and /stream6, H264+PCMA decoded on both.
   (c) [#44879915942 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44879915942): genuine source-equivalent Record.ps1 startup in WinPS5 with isolated dummy DPAPI and a pre-existing STOP marker. No RTSP opened.
   (d) [#44881283742 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44881283742): **genuine cloned Record.ps1 executed and recorded both synthetic local RTSP sessions** and one finalized 6,547,122-byte H264/AAC 2560x720@15fps mono48k MP4, independently decoded. A post-start STOP marker was present by the time the **finite RTSP sources ended naturally**, recorder selected STOP rather than RECONNECT, GStreamer exit 0. This is **NOT** a GUI Ctrl+C / active GStreamer EOS signal test.
   (e) [#44881597094 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44881597094): isolated camera-free exact Windows GUI worker Ctrl+C handler and marker-before-event protocol passed without running GStreamer.
   (f) [#44885391598 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44885391598): exact original RecordGUIWorker.ps1 plus cloned Record.ps1 ran active two-mount synthetic RTSP recording. The CI-only owned-console sender wrote STOP before real Ctrl+C; gst-launch -e exited 0, EOS and STOP-without-reconnect passed, one independently H264/AAC-decoded 1,375,553-byte MP4, worker and owned stage cleaned. Source code was unchanged; prior failure was an RTSP/worker ready-variable name collision in CI only, fixed at 4938cbec.
   (g) [#44885660589 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44885660589): non-invasive 4x1s CPU, private memory and total handle snapshots of the exact owned GUI worker plus staged gst-launch; no gst process remained after Ctrl+C. Initial gst private bytes grew from 34,344,960 to 408,342,528 B and handles from 498 to 767 in the 4-second startup window. Do NOT label these first seconds a leak slope: codecs and queues allocate during startup.
   New automated follow-up [GUI worker gate](C545D_GUI_WORKER_CTRL_C_EOS_CI_GATE.md): a CI-only **opt-in 60-second synthetic media fixture** with 11 samples over a nominal 31-second window and a 24-second post-warm-up interval; the original 22-second finite RTSP fixture remains the default. The new Windows CI #44885984146 is pending as of this update and must be checked for final output before any conclusion about later memory/handle behavior. No user action. No user secrets or host recordings.
   Preserve the production 3,600-second splitmux, x264 medium QP24, avdec_h264, AAC mono48kHz/192k and safe stop. A real one-hour boundary and physical Tapo two-lens sync/CPU/PrivateUsage/handles still require one separately approved consolidated Win10 acceptance session only AFTER all AI-side gates.
4. Prepare a single self-contained, supervised test script which verifies
   preconditions, collects already-identified metrics automatically,
   preserves any test outputs only in a user-owned private location,
   and emits a sanitized numeric summary. All failures block rollout.

## ONE future user-approved host session (only after AI gates)

- Obtain **separate explicit approval** and schedule during an authorized
  natural safe stop; do not kill or interrupt the running evidence recorder.
  Existing Win10 six-core fingerprint should not be requested again.
- First run the camera-free pinned candidate app-local smoke exactly once
  after safe stop, requiring one fixed numeric result line and exact GIO
  module observation. If it fails, cancel the trial and resume original
  installed recorder without DLL substitution.
- Only if an independently qualified production-equivalent runner exists,
  execute **one consolidated real-camera session** rather than sequential
  repeated 4-hour investigations. To actually test a one-hour split boundary,
  the single session must cross at least one 3,600-second production segment.
  Short synthetic splitmux results cannot substitute for this.
- In that SAME automated session capture: two RTSP stream health,
  stream1/stream6 layout, true 2560x720@15fps, h264/x264 QP and preset
  invariants, AAC mono48k/192k target, timestamps and audio/video sync,
  at least one real hourly MP4 boundary, finalized/decodable MP4 segments,
  expected filenames, EOS/clean stop, reconnect behavior where safe,
  per-process CPU, PrivateUsage/PrivateBytes, total handles, and Key subtype
  counts only if a privacy-safe validated collector exists.
- Compare against already available production baseline data when possible.
  Do NOT infer absolute memory/handle leak-free status from a brief run.
  A 24x365 stability claim requires separate sustained evidence, not a
  single CI success.
- On any failed gate, no live candidate rollout. Preserve the original
  GStreamer install and production recorder; restore normal operation
  according to its existing safe start/stop procedure. No periodic forced
  restart proposed as a leak fix.

## Privacy and reporting

Never commit camera RTSP URLs, passwords, recordings, full private logs,
raw ETL, command lines containing credentials, Windows host paths or local
machine-specific hashes to the public repository. Publish only aggregate
pass/fail gates and sanitized numeric deltas with source commit/CI run IDs.

**Current user action required: NONE. Candidate production status: HOLD.**
