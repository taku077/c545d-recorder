# CI-only GUI worker Ctrl+C EOS integration gate — Tapo C545D

**Development test, NOT host approval.** No user PC, real camera, credentials, installed GStreamer, registry or recording process is touched.

## Independent prerequisites already PASS

- [#44874736247](https://github.com/taku077/c545d-recorder/actions/runs/44874736247): candidate GIO observed within pinned official GStreamer SDK, five synthetic H264/AAC 2560x720 segments decoded.
- [#44878301067](https://github.com/taku077/c545d-recorder/actions/runs/44878301067): genuine synthetic dual TCP RTSP streams /stream1 and /stream6 at 127.0.0.1:554 with H264 and PCMA audio decoded on both.
- [#44879915942](https://github.com/taku077/c545d-recorder/actions/runs/44879915942): source-exact cloned Record.ps1 starts and honors a pre-existing stop marker; no RTSP.
- [#44881283742](https://github.com/taku077/c545d-recorder/actions/runs/44881283742): exact cloned Record.ps1 recorded real localhost RTSP from both mounts, source-ended cleanly with a post-start STOP marker and yielded one 6,547,122-byte decoded H264/AAC MP4. **Natural finite RTSP end is not GUI Ctrl+C.**
- [#44881597094](https://github.com/taku077/c545d-recorder/actions/runs/44881597094): extracted actual C# Ctrl+C handler from RecordGUIWorker.ps1, used synthetic Windows worker to verify marker-before-event, private console Ctrl+C and worker survival, without media.

Official GStreamer gst-launch -e docs: https://gstreamer.freedesktop.org/documentation/tools/gst-launch.html . Official Win32 console API: https://learn.microsoft.com/en-us/windows/console/generateconsolectrlevent .

## New combined experiment — requires real CI result

- [Actual GUI worker + RTSP integration test](../tests/Assert-C545DGUIWorkerLiveLoopbackCI.ps1)
- [Strict owned-console signal helper](../tools/Send-C545DPrivateConsoleStopCI.ps1)
- [Windows workflow](../.github/workflows/c545d-gui-worker-live-loopback-ci.yml)

On Windows2022 GitHub-hosted runner only, validate six official SDK core DLL hashes, candidate GIO SHA, and cloned source equality. Render a private actual Record.ps1 mirror with ONLY its Find-GstBin source assignment changed and a cloned CommonSettings with ONLY private output path override. Copy the **original RecordGUIWorker.ps1 byte-for-byte**. Create fake private LOCALAPPDATA IP 127.0.0.1, fake camera username and dummy DPAPI password inside the spawned Windows PowerShell5.1 worker process (known hosted runner Start-Process DPAPI issue if generated in a distinct process). The private bootstrap then calls exact original GUI worker, which starts the real source mirror, not a synthetic replacement script.

The synthetic GStreamer RTSP server binds exclusively 127.0.0.1:554 and serves two finite H264 1280x720@15fps plus PCMA mono 8kHz endpoints. Require a callback from BOTH media factories, proving both sessions exist, before issuing Ctrl+C. An isolated CI-only signal sender verifies the exact owned GUID stage, original GUI worker ready-file PID, Windows PowerShell5 executable, and target console process list containing exclusively worker, private staged gst-launch, and sender. Write the worker's actual STOP file before calling AttachConsole and GenerateConsoleCtrlEvent(0,0). Refuse any unrecognized process rather than risking a stray signal. This is NEVER valid for user's recording PC.

After Ctrl+C, require natural worker completion, GStreamer EOS exit code0, STOP policy (never RECONNECT), one finalized MP4, original output video 2560x720 15fps H264 and audio mono48k AAC, real H264/AAC decode, original hashes unchanged, privately owned scratch deletion. If cleanup forcibly terminates any test process, it MUST fail the EOS qualification. Only strict sanitized numeric lines may enter public CI logs; no camera credentials, RTSP secrets, raw video, path-bearing logs or ETL are uploaded.

Initial new workflow [#44881856117](https://github.com/taku077/c545d-recorder/actions/runs/44881856117) launched at [6426301](https://github.com/taku077/c545d-recorder/commit/642630147b2900627038755c4421de8f6046a345). **Verify the final job and result before claiming PASS.**

## Unproven after CI

Actual Tapo two-lens clock and login, GUI file naming behavior, real 3,600-second split, long-run Win10 CPU/PrivateUsage/Key-handle slope and zero memory leak remain unproven. Candidate GIO release status HOLD. User action NONE; no multi-hour repeated manual tests.
