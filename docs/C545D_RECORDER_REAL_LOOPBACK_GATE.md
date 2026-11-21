# C545D actual Record.ps1 + finite localhost dual-RTSP Windows CI — development gate

**CI-only, not approved for user's Windows 10 recording host.** Do not install candidate DLLs, change user settings/registry, stop active capture or touch actual Tapo RTSP URLs, credentials or video.

## Previously verified independent prerequisites

- [#44874736247](https://github.com/taku077/c545d-recorder/actions/runs/44874736247) SUCCESS: official pinned GStreamer1.28.8 MSVC SDK, actual loaded candidate GIO, 5 synthetic H264/AAC MP4 fragments independently decoded.
- [#44878301067](https://github.com/taku077/c545d-recorder/actions/runs/44878301067) SUCCESS: two genuine TCP localhost RTSP sources /stream1 and /stream6 at 127.0.0.1:554, H264 + PCMA audio on both and four decoded media paths.
- [#44879915942](https://github.com/taku077/c545d-recorder/actions/runs/44879915942) SUCCESS: byte-equivalent source mirror of actual Record.ps1 starts under PowerShell5.1 with dummy DPAPI and **pre-existing** STOP marker, validates decoder/AAC/graph startup and exits before RTSP. Direct native PS5.1 invocation is proven for GitHub Windows dummy DPAPI; previously attempted Start-Process and managed launcher variants failed this isolated dummy password test. They are NOT evidence of a user host failure.

## New finite localhost RTSP integration probe (NOT YET QUALIFIED)

Sources: [CI integration script](../tests/Assert-C545DRecorderLiveLoopbackCI.ps1), [finite RTSP source](../tests/c545d_ci_finite_rtsp_server.c) and [Windows workflow](../.github/workflows/c545d-recorder-live-loopback-ci.yml).

The CI runner makes a strictly owned isolated GUID folder under RUNNER_TEMP with a checked ownership marker and reparse-safe cleanup. It verifies the official SIX core SDK DLL SHA256 values and fixed candidate GIO checksum. It stages only private copies of genuine GStreamer executables and candidate DLL, then calls the already-qualified AST single-assignment mirror helpers. The cloned Record.ps1 is byte-equivalent except its single SDK bin assignment, and cloned CommonSettings changes only its private output location. Original 3600-second splitmux, 2560x720 15fps, x264 medium QP24, avdec_h264, AAC mono 48kHz 192k target and existing stop/reconnect policies remain unchanged.

Only fake LOCALAPPDATA settings (IP 127.0.0.1, dummy user, dummy PS5.1 DPAPI secret) are used. The new MSVC-built GStreamer RTSP server refuses to run outside Windows GitHub Actions and listens **only on 127.0.0.1:554** with two distinct H264 1280x720@15fps sources and PCMA/8000 mono audio. Both servers produce a finite 330 video buffers and 550 PCMA audio buffers; this probes a **naturally ending RTSP server**, not the GUI Ctrl+C stop path.

The test invokes actual mirrored Record.ps1 directly with Windows PowerShell5.1 to retain proven DPAPI semantics. A CI-only background job observes the private synthetic MP4 file, waits a short bounded period and writes a private stop marker to prevent reconnect AFTER the finite media source ends. It does not send a Ctrl+C signal, kill the production recorder, connect to any real camera or modify installed DLLs. If the RTP pipeline does not terminate naturally, GitHub's bounded job timeout fails the experiment rather than pretending EOS worked. All raw media and potentially path-bearing logs are deleted with private scratch, and only fixed numeric diagnostic lines are allowed in CI.

If the cloned recorder returns, CI requires one launch, recognized stop marker and stop policy, exactly one finalized MP4, H264/AAC 2560x720@15fps and AAC mono 48kHz caps from gst-discoverer, independent actual H264 and AAC decode, unchanged source/DLL hashes, and owner-verified rollback. A source end with a nonzero GStreamer exit code or unfinalized MP4 is not success.

Initial run [#44880791076](https://github.com/taku077/c545d-recorder/actions/runs/44880791076) was started on [e7c68c3](https://github.com/taku077/c545d-recorder/commit/e7c68c3dc0bd94961d5594da2ed810035dbcd690). Verify its final run and numeric logs before claiming a result.

## Strict limits

Even a successful CI is NOT a test of genuine GUI Ctrl+C, in-flight controlled EOS, reconnect after unsolicited network errors, camera authentication, real Tapo inter-lens timestamps, a 3600s segment, or 24x365 Win10 CPU/PrivateUsage/Key-handle slopes. Keep host deployment HOLD, ask for no user action, and do not revisit completed WPR/UMDH or request repeated multihour tests.
