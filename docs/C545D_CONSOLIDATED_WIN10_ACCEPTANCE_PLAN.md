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
3. The future-only launcher remains **camera-free** and NOT APPROVED.
   Three **distinct** Windows2022 CI gates are now qualified:
   (a) [#44874736247 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44874736247)
       actual official MSVC SDK, pinned candidate GIO module observed, private
       source mirror and five shortened synthetic dual RTP H264/AAC MP4 fragments
       independently decoded and rolled back;
   (b) [#44878301067 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44878301067)
       genuine localhost-only dual 127.0.0.1:554 /stream1 and /stream6 RTSP
       TCP media, two synthetic H264 and two PCMA 8kHz tracks all decoded;
   (c) [#44879915942 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44879915942)
       the actual cloned production Record.ps1 executed in Windows PowerShell5.1
       with isolated dummy LOCALAPPDATA/DPAPI and a pre-existing STOP marker,
       passed original GStreamer startup and graph validation then exited
       WITHOUT any RTSP launch or MP4 creation, with all originals untouched.
   These gates do not yet prove an IN-FLIGHT recording by actual Record.ps1
   with both synthetic RTSP streams, safe Ctrl+C/EOS/GUI stop, reconnect and
   finalized MP4. Next AI-only: integrate the already-qualified localhost
   source server with the exact recorder mirror, verify it can start and stop
   safely and inspect MP4 and CPU/PrivateUsage/handles automatically. No
   original source or user-installed SDK/registry is to be altered.
   The 3600s actual MP4 boundary and real Tapo clocks/credentials still
   require separately approved host verification only after AI gates.
   Supporting records: [real SDK/recorder pre-stop](C545D_PRODUCTION_MIRROR_REAL_SDK_CI_GATE.md)
   and [synthetic RTSP CI](C545D_SYNTHETIC_LOOPBACK_RTSP_CI_GATE.md).
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
