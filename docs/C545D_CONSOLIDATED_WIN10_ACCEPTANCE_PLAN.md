# C545D — consolidated Windows 10 host acceptance plan (DRAFT / NOT AUTHORIZED)

**Status: HOLD. This is an AI-side plan, NOT permission to stop recording, swap
DLLs, run the candidate, or upload video/credentials.**

## Evidence already retained — DO NOT rerun

- **LATEST [3/3 full GUI+recording repeatability CI #44898929936 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44898929936)**: three independent Windows2022 runners, actual original WinForms START/STOP/QUIT dispatch, unchanged original RecordGUIWorker + in-recording original SegmentNamer worker, two synthetic localhost RTSP, candidate GIO. Each produced four auto-renamed MP4s individually decoded H264/AAC with contiguous fragment mapping, worker exit0, gst exit0, EOS, no reconnect, clean GUI/watcher. Trial MP4 sizes **9,372,629 B**, **9,371,224 B**, **9,381,854 B**; stop latencies **509/410/540ms**; gst 24s postwarmup PrivateUsage-like PrivateMemorySize64 deltas **+221,184 / −73,728 / +24,576 B**, total gst handle delta **−33 all** (not Key subtype). Combined with earlier [#44898649382](https://github.com/taku077/c545d-recorder/actions/runs/44898649382) and [#44898660863](https://github.com/taku077/c545d-recorder/actions/runs/44898660863), **five recent full synthetic GUI/EOS passes**. Previous same-path nonzero worker statuses remain unexplained and NOT declared fixed. Real Win10/actual one-hour segment/Tapo two-lens sync/long CPU and Key slope unverified. Production candidate install HOLD; user action NONE.

- **NEW [full genuine WinForms + original worker + two synthetic RTSP CI #44898649382](https://github.com/taku077/c545d-recorder/actions/runs/44898649382) and [#44898660863](https://github.com/taku077/c545d-recorder/actions/runs/44898660863), both SUCCESS**: real `C545D_App.ps1` WinForms `PerformClick` Start/Stop/Quit handlers start unmodified `RecordGUIWorker.ps1` and `SegmentNamerWorker.ps1` with candidate GIO and localhost simulated two-camera H264+PCMA. Original worker exit0, gst exit0/EOS/STOP and no reconnect; four splitmux 8s-target MP4 auto-renamed while recording, each H264/AAC decoded. Latest four files **9,372,804 B**, GUI STOP-to-exit **559ms**, source hash unchanged, namer shut down and staged gst process0. Over postwarmup24s native gst private +65,536 B and total handles −33, which is NOT proof of sustained leak zero. Earlier combined test repeatedly failed with **nonzero worker exit even though GST exit0/EOS yes**, initially classified `OTHER`, exact signed exit not captured; two successes do NOT prove intermittent failure solved. **[Three parallel independent Windows CI run #44898929936](https://github.com/taku077/c545d-recorder/actions/runs/44898929936)** added to test repeatability. Full synthetic GUI/media integration now has positive evidence, but not guaranteed stability. Actual 3600-second segment, physical Tapo sync, Windows10 host and long resource trends remain unverified. Candidate release HOLD, user action NONE. Details [GUI CI gate](C545D_GUI_WORKER_CTRL_C_EOS_CI_GATE.md).

- **NEW GUI event-handler CI [#44895870962 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44895870962)**: on a disposable Windows2022 VM, an exact-source private clone of `C545D_App.ps1` (original Japanese script text preserved as UTF-8 BOM) received `btnStart.PerformClick`, `btnStop.PerformClick`, and `btnQuit.PerformClick` events from its own real WinForms event thread. Real original `SegmentNamerWorker.ps1` was READY before the GUI's record-worker Start-Process; a CI-owned **stub** worker without a `.ready` marker observed the GUI's durable `.stop` marker and exited safely. Exact `C545D_WINFORMS_BUTTON_DISPATCH_STAGE,start=1,stop=1,quit=1,namer_ready=1,stub_safe_stop=1,source_unchanged=1,real_rtsp=0,real_camera=0,install_approved=0,reason=PASS`. **NOT a real recorder, console-signal, EOS, MP4, camera, or GUI mouse-click test.** Complementary [#44889624247](https://github.com/taku077/c545d-recorder/actions/runs/44889624247) already passed original worker/GStreamer two-synthetic-RTSP live auto-rename with 4 independently decoded final MP4, initiated by CI harness rather than WinForms. The remaining combined same-session WinForms real worker synthetic RTSP/EOS integration is a future AI-only gate, not a reason to demand user manual tests. Several early new CI harness/invalid-YAML attempts failed before this PASS, documented in [GUI gate](C545D_GUI_WORKER_CTRL_C_EOS_CI_GATE.md). Production HOLD; user action NONE.

- **NEW [Windows2022 in-stream event-renamer CI #44889624247 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44889624247)**: unlike earlier after-recording fixture rename test, the exact unmodified `SegmentNamerWorker.ps1` monitored the *ongoing* private output directory and started **before** original GUI worker/source-equivalent recorder launched. With two synthetic localhost H264/PCMA RTSP streams, 4 accelerated (~8s target) splitmux MP4 fragments were **actually auto-renamed while recording** (at least one before GUI STOP), 4 filenames/`00000..00003` logs matched, final renamed MP4s all independently H264/AAC decoded, total 9,434,593 bytes. GUI STOP-before-Ctrl+C, EOS, zero reconnect, watcher clean exit, staged gst leftover zero; stop latency 1,004ms. Numeric `C545D_GUI_INSTREAM_NAMER_CI_PASS,ready=1,renamed_before_stop=1,renamed_total=4,all_decoded=1,watcher_exit_ok=1,source_unchanged=1,real_camera=0,install_approved=0`. The actual GUI startup order was separately asserted **statically**, but a WinForms click was **not executed**. Regressions [original 3600s #44889624282 PASS](https://github.com/taku077/c545d-recorder/actions/runs/44889624282), [accelerated 4 MP4 + after-copy namer #44889624256 PASS](https://github.com/taku077/c545d-recorder/actions/runs/44889624256). Early syntax-only failed CI #44889371332 / #44889371316 / #44889413994 was caused by one unclosed quote added to test-only script, fixed by [2ae60aca](https://github.com/taku077/c545d-recorder/commit/2ae60aca7da3943405000ede20b83fad557ff267), with earlier syntax diagnostics moved before SDK setup. Full recorder 24s postwarmup memory +90,112 B and handles −33: **no sustained leak-zero claim**. Main physical Win10/Tapo 3600s/clock synchronization/long resources remain unverified; no user action / host install approval.

- **Latest [full CI #44888137287 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44888137287)** additionally passes a strict source-level GUI naming initialization order gate: the actual `C545D_App.ps1` calls `Wait-C545DNamerReady` before `RecordGUIWorker.ps1` process start, and original `SegmentNamerWorker.ps1` Created/Renamed subscriptions, ready marker, shutdown draining and `SegmentNamer.ps1` exclusive lock are retained. Exact numeric `C545D_GUI_NAMER_WIRING_SOURCE_CI_PASS,gui_wait_before_record=1,created_event=1,renamed_event=1,ready_marker=1,shutdown_drain=1,exclusive_lock_gate=1,production_sources_unchanged=1,real_camera=0`. Same run all-green four accelerated synthetic H264/AAC MP4 (9,484,934 bytes), controlled GUI EOS 997ms, actual namer isolated fixture locked-defer / 4 renamed / byte-identical / manual preserved / clean exit. Full-recorder 24s post-warmup private bytes −151,552 B and handles −33; **not long-term leak-free**. Source-only GUI start order is NOT live WinForms wiring and private fixture renamed after recording is NOT in-stream renaming. No host authorization; user action NONE.

- **NEW original SegmentNamer worker isolated CI [#44887787945 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44887787945)**: 4 real accelerated splitmux H264/AAC MP4 produced (total 9,505,393 B, separately decoded), GUI STOP/real Ctrl+C/EOS successful (1,024ms), and an **independent actual unmodified `SegmentNamerWorker.ps1`/`SegmentNamer.ps1` event-driven watcher** processed four stage-private copies of a valid MP4. One copy was kept exclusively open through the Created event and first rename attempt; rename was deferred until close. All four were subsequently renamed, each SHA256 matched its original bytes, a user-defined filename was preserved, and watcher exited cleanly on marker. Sanitized numeric record `ready=1,locked_deferred=1,renamed=4,mp4_hashes_intact=1,manual_preserved=1,clean_exit=1,source_unchanged=1,reason=PASS`. Source commits [156184c6](https://github.com/taku077/c545d-recorder/commit/156184c67368e620462ef7a514881a562de83897), [2ce62958](https://github.com/taku077/c545d-recorder/commit/2ce62958052fe2c13b233c2ecbe2b35e9e4eddba), [18431c06](https://github.com/taku077/c545d-recorder/commit/18431c062c3ef9e475653faa1d76003bee12a2ac). Default 3,600-second source unchanged; [original GUI regression #44887769114 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44887769114). **Not tested**: actual WinForms Start-C545DOptionalNamer invocation on the user's PC or in-stream automatic rename, real 3600s boundary or sustained leak-free behavior. Post-warmup 24s full-recorder gst PrivateMemorySize64 delta −110,592 B / total handles −33 is not a zero leak proof. Production HOLD, user action NONE.

- **NEW accelerated split CI [#44887164124 PASS](https://github.com/taku077/c545d-recorder/actions/runs/44887164124)**: private disposable clone of real Record.ps1 used exactly one reversible 3600s→8s splitmux literal change; same original GUI worker and two synthetic RTSP streams produced **4 consecutive numbered MP4 fragments**, all independently H264/AAC decoded at 2560×720@15fps and AAC mono48k, EOS STOP without RECONNECT, 727ms stop and 0 staged gst processes left. Only CI private mirror was modified; **the genuine 3600-second boundary and actual GUI filename renaming are NOT tested**. Baseline unchanged-source GUI tests [#44887050093](https://github.com/taku077/c545d-recorder/actions/runs/44887050093) and [#44887060368](https://github.com/taku077/c545d-recorder/actions/runs/44887060368) also PASS. First new YAML [#44887115745](https://github.com/taku077/c545d-recorder/actions/runs/44887115745) failed with zero jobs due generated workflow syntax, then repaired; not a runtime failure. CI accelerated 24s postwarmup PrivateMemorySize64 delta **+163,840 B**, handles **−33**: do not claim sustained no-leak. Details: [GUI gate](C545D_GUI_WORKER_CTRL_C_EOS_CI_GATE.md).

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
   (h) [#44885984146 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44885984146), [#44886369203 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44886369203), and final [#44886381790 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44886381790): same exact GUI-worker/recorder and two synthetic RTSP streams, but CI-only 60-second synthetic source mode and eleven process-private samples over a nominal 31-second window. The original 22-second source remains intact, independently [#44885920634 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44885920634). Candidate modified GIO **observed loaded** in live gst-launch; in 3 independent postwarm-up 24-second intervals gst private bytes deltas were -40,960 B, -114,688 B and -131,072 B, while total handles each changed 767 to 734 (-33). No monotonically increasing process-wide private bytes/total handles in those short windows. CPU was also sampled, and 0 stage-owned gst processes remained after stop.
   Latest GUI Stop-to-worker-exit **746ms**, strictly bounded to 20s so finite 60s natural EOF cannot masquerade as GUI Ctrl+C EOS. Final H264+AAC MP4 9,366,841 B independently decodable. See [GUI worker gate](C545D_GUI_WORKER_CTRL_C_EOS_CI_GATE.md). This is neither a full 24x365 stress assessment nor a measurement of Key handles as a subtype; previous ETW measurements remain separate. No user action. No real camera or host data.
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
  **Do not demand an exact 3,600.000s file duration**: the unmodified
  Record.ps1 sets `max-size-time=3600000000000` ns and x264
  `key-int-max=30` at 15fps, with
  `send-keyframe-requests=true`. GStreamer splitmuxsink is explicitly
  keyframe-aligned and may overrun the time target by a GOP; the nominal
  keyframe interval is at most 30/15 = 2 seconds under steady encoding,
  but real-source jitter and other delays mean this is NOT a guaranteed
  absolute 2s cap. Judge the first real split using MP4 media timestamps,
  recording-continuity markers and individually finalized H264/AAC streams,
  allowing a cautious bounded margin rather than falsely failing on
  sub-second/keyframe alignment. Require EOS finalization for the final
  fragment, and collect all host metrics in the SAME authorized session.
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
