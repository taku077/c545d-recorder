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
3. The future-only launcher remains **camera-free**. The production source
   mirror plus private output-folder static gate passed Windows CI #44873653092.
   The NEXT isolated integration gate has also passed: Windows Server 2022
   [real SDK CI #44874736247](https://github.com/taku077/c545d-recorder/actions/runs/44874736247)
   used the exact official pinned GStreamer MSVC1.28.8 SDK, staged real
   GStreamer executables and pinned candidate GIO in the SAME private bin
   as the cloned production source, observed the actual loaded candidate
   GIO module for synthetic WAV, produced and independently decoded **five**
   shorter synthetic dual RTP H264/AAC MP4 fragments, and cleaned its owned
   private stage. Details: [real SDK source-mirror gate](C545D_PRODUCTION_MIRROR_REAL_SDK_CI_GATE.md).
   **Neither CI executes the mirrored Record.ps1, authenticates camera RTSP
   nor verifies the true 3,600-second boundary.** Next qualify a genuine
   synthetic local RTSP endpoint and a safe private configuration/metrics
   harness before considering a user-host session. Never change the user's
   installed SDK DLLs, registry, original Record.ps1 or active recording.
   If offline source/runtime equivalence cannot be shown, do not request
   host testing.
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
