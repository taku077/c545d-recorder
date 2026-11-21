# C545D synthetic loopback RTSP Windows CI gate (NOT APPROVED for host)

The previous Windows2022 real-GStreamer and candidate GIO five-MP4 test [#44874736247](https://github.com/taku077/c545d-recorder/actions/runs/44874736247) passed. It did NOT execute the production source mirror or open RTSP connections.

## New localhost-only components

- [C source](../tests/c545d_synthetic_loopback_rtsp_ci.c) implements a genuine GStreamer RTSP server, fixed bind address 127.0.0.1, fixed port 554, mounts /stream1 and /stream6. Both streams have synthetic H264/RTP video and PCMA/RTP audio. The native client connects with two rtspsrc TCP sources to these only two fixed URLs and verifies receipt of decoded video+audio buffers from both.
- [CI workflow](../.github/workflows/c545d-synthetic-loopback-rtsp-ci.yml) downloads the pinned official 1.28.8 MSVC x64 SDK onto a disposable Windows2022 GitHub runner, verifies all six core DLL SHA256 values, compiles the native code using MSVC, and runs only spawned test processes. It restores process-local GStreamer settings and deletes only a strictly owned temporary folder after refusing reparse points. It does not access a physical camera or change any recorder software or settings.
- Official API references: [RTSP server](https://gstreamer.freedesktop.org/documentation/gst-rtsp-server/rtsp-server.html), [RTSP media factory](https://gstreamer.freedesktop.org/documentation/gst-rtsp-server/rtsp-media-factory.html), [RTSP client and SDP](https://gstreamer.freedesktop.org/documentation/rtsp/rtspsrc.html).
- Separately [dummy configuration and DPAPI test #44877588530 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44877588530) confirmed that copied CommonSettings.ps1 reads only a synthetic 127.0.0.1 address, a fake locally encrypted DPAPI password and a private output directory. Original source remained byte-identical; fake config and password were deleted. No user credential was accessed.

## Failures and status

- The first native RTSP CI [#44877501470 FAILED](https://github.com/taku077/c545d-recorder/actions/runs/44877501470) after successful official SDK installation and MSVC compilation: the private test directory could not be deleted because the spawned processes had it as their working directory. This is a cleanup harness defect, not evidence of GIO or Win10 recorder failure; it also does NOT prove media negotiation succeeded.
- [f668307](https://github.com/taku077/c545d-recorder/commit/f668307d175050d287b9c6cc8b6ddbb0908331e6) moved the spawned children workdir to the parent runner temp directory and added sanitized stage diagnostics and a short closure delay. The follow-up [CI #44877694445](https://github.com/taku077/c545d-recorder/actions/runs/44877694445) determines whether synthetic RTSP and cleanup actually pass; verify its final status before declaring success.

## Strict limits and next work

Even if loopback RTSP succeeds, the cloned production Record.ps1 has NOT yet been executed. This test is not proof of Tapo camera authentication, stream1/stream6 clock sync, GUI-managed EOS, safe restart, 3600-second fragment boundary or 24x365 CPU/PrivateUsage/Key-handle stability. A later AI-only test could combine the independently verified fake config with real candidate GIO, local synthetic RTSP and a CI-only bounded, explicitly authorized test of the cloned source. It must be safely isolated and stop without damaging existing files. Do not request any user PC action or reinstall, WPR/UMDH, or multihour measurement at this time.

Production rollout: HOLD. User action: NONE.
