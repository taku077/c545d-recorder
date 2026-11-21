# CI-only GUI worker Ctrl+C EOS integration gate — Tapo C545D


## VERIFIED 2026-11-21 — original GUI worker Ctrl+C + EOS real Windows CI PASS

- [Windows Server 2022 CI #44885391598 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44885391598), job136789453398, artifact14699566963 numeric-only. Actual RecordGUIWorker.ps1 byte-for-byte, isolated mirrored Record.ps1 source, pinned official GStreamer 1.28.8 MSVC SDK and candidate GIO; only disposable Windows CI, fake DPAPI, 127.0.0.1/stream1 and /stream6 dual synthetic H264+PCMA RTSP.
- Original GUI worker ready marker and worker survival were observed. Safe CI helper checked exclusively owned console clients then sent real GUI-style STOP-file-before-Ctrl+C. Gst-launch -e returned 0 with EOS; source logged STOP policy without reconnect. One finalized 1,375,553 byte H264/AAC MP4 decoded with expected 2560x720@15fps and mono AAC 48kHz. Original source files unchanged; privately owned files removed. No camera or user Win10 host touched.
- Logged exact stage: C545D_GUI_WORKER_RTSP_STAGE,worker_exit=0,worker_exited=1,gui_ctrlc_sent=1,wide_mount=1,tele_mount=1,launch_count=1,stop_at_gst_return=1,native_gst_exit=0,policy_stop=1,policy_reconnect=0,eos_message=1,worker_returned=1,mp4_count=1,mp4_bytes=1375553,stop_marker=1,ready_removed=1,real_camera=0.
- Logged strict final: C545D_GUI_WORKER_REAL_SOURCE_CTRL_C_CI_PASS,original_worker=1,original_recorder_mirror=1,two_local_rtsp=1,gui_ctrlc_event=1,worker_survived=1,gst_eos=1,mp4_h264_aac_decoded=1,owned_rollback=1,real_camera=0,real_hourly_split_tested=0,install_approved=0.
- Previous GUI failure [#44883613017](https://github.com/taku077/c545d-recorder/actions/runs/44883613017) was a CI harness variable shadow: $ready was first the actual GUI session ready file path and later overwritten by RTSP server's expected ready-line text. Its sanitized diagnostic already showed ready_candidate_count=1, ready_candidate_pid_match=1, ready_candidate_name_match=0 with recording and MP4 created. [4938cbec](https://github.com/taku077/c545d-recorder/commit/4938cbec579ef63a93bd6edf7acfdc7eb09f5c6c) splits the RTSP text into $rtspReadyLine and fixes this without changing production worker or recorder.
- New bounded 4-second CPU-time/PrivateMemorySize64/HandleCount sampling of only owned worker + staged gst-launch and explicit post-exit staged process check added in [292e378](https://github.com/taku077/c545d-recorder/commit/292e378839396762547e84ce7f52cd5df4f432e7), plus numeric log whitelist [3ea33e3](https://github.com/taku077/c545d-recorder/commit/3ea33e3ee8670a16bf187b4ba4a49d84dc9d60f4). [Windows CI #44885660589](https://github.com/taku077/c545d-recorder/actions/runs/44885660589) is the new authoritative telemetry outcome; do not call it PASS before final numeric output. Four samples do not demonstrate a zero long-run memory/Key leak or real camera/3600-second segment.


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
