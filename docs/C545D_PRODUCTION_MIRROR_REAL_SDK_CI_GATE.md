# Production-exact C545D source mirror and real GStreamer SDK media — CI ONLY

Status: Windows2022 real-SDK CI SUCCESS. NOT an installer. Not approved for Windows10 host use.

## Completed 2026-11-21

- PR [#62](https://github.com/taku077/c545d-recorder/pull/62). [Windows CI #44874736247 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44874736247), job 136756826417. Numeric-only artifact 14695144578 expires 2026-11-28 06:20 UTC.
- CI installed real official GStreamer 1.28.8 MSVC x64 on a disposable Windows Server 2022 runner. Six original core DLL SHA256 values matched independently pinned official values. Candidate GIO SHA256 was verified as 67b9f7246e4744fef7ee1ead3bed4ce2179c6f0465ec68a92d01dd12b4a3ccad with provenance manifest.
- Created random directly runner-owned temporary stage with exact real SDK gst-launch, gst-inspect and gst-discoverer EXE copies, plus pinned app-local candidate gio-2.0-0.dll. EXE copies verified byte-identical by SHA256.
- Reused proven CI-only mirror scripts to clone Record.ps1 changing exactly ONE GStreamer executable-bin assignment; all other source including 2 lens layout, x264/AAC, 3600s segment, EOS and reconnect remains character-identical. The cloned CommonSettings.ps1 adds ONLY one CI-owned private output-folder assignment. Originals are hashed before and after.
- Important: CI NEVER INVOKED the cloned Record.ps1. Running that mirror would read local camera config and attempt actual RTSP. This CI uses only generated synthetic test pipelines, no physical camera, login, RTSP, DPAPI or user recording files.
- Real staged gst-launch was started for synthetic GIO/WAV. While running, its actual gio-2.0-0.dll loaded-module path was observed and matched the staged candidate, not the original SDK GIO. Output WAV valid and child exited normally.
- On the SAME private bin, the existing qualified Assert-GStreamerOverlaySplitMux.ps1 ran two synthetic H.264/RTP pay-depay video paths using avdec_h264, plus AAC mono 48kHz 192kbps. Output graph matches core codec/layout choices 2560x720@15fps, x264 medium QP24 and synchronous splitmuxsink. The media test uses SHORTENED split times exclusively in CI; it never modifies production's 3600s setting. All 5 MP4 segments were checked for H.264 and AAC, media caps and independent video/audio decode. EOS passed and synthetic MP4 files were removed.
- Isolated test process GST plugin paths and registry are restored; private stage deleted only after exact owner marker, direct-child name, no reparse points and original input hashes checked.
- Exact log observation:
  C545D_PRODUCTION_MIRROR_REAL_SDK_CI_PASS,source_mirror=1,private_settings_output=1,official_sdk_pinned=1,real_private_exe=1,real_candidate_gio_loaded=1,giosink_wav=1,synthetic_dual_rtp_h264_aac=1,segments=5,mp4_decode=1,eos=1,originals_unchanged=1,owned_rollback=1,real_tapo_tested=0,real_hourly_split_tested=0,install_approved=0
- New [fast Windows PowerShell5.1 and PowerShell7 parser CI #44874959906 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44874959906) confirms syntax and required safety/media hooks without a SDK download.

## Intermediate CI failures — actual causes

- [#44874698237 FAIL](https://github.com/taku077/c545d-recorder/actions/runs/44874698237) was a YAML harness input bug: literal backslash before the GitHub token expression made artifact download fail, before SDK installation. Fixed in [7c1b874](https://github.com/taku077/c545d-recorder/commit/7c1b874e7b9eb3ef6b9cb3e3d0955be582a99794), followed by full real-SDK CI #44874736247 SUCCESS.
- [#44874912059 FAIL](https://github.com/taku077/c545d-recorder/actions/runs/44874912059) was another harness bug: PowerShell -Command with extraneous -source argument. Fixed in [31af3f1](https://github.com/taku077/c545d-recorder/commit/31af3f12c3ae9f71ef23c297ab6fe95f7bcf84fb) by a temporary -File parser, followed by fast CI #44874959906 SUCCESS. Neither failure is a GIO DLL/runtime/Win10 user fault.

## Unresolved and next AI-side work

This PASS is actual GStreamer app-local candidate loading plus synthetic five-fragment media in the same directory as an exact-source mirror. It is NOT execution of mirrored Record.ps1, real RTSP stream1/stream6 negotiation, NTP synchronization, real hour-long boundary, natural stop/reconnect or Win10 long-run leak-free evidence. A future authorized runner must point the private process environment to the official scanner and plugins, because the cloned Record.ps1's parent directory differs from the installed SDK root. No user-host authorization today.

Next, if useful, CI-qualify a truly synthetic local RTSP server that permits executing the mirrored graph with dummy credentials and private configuration; preserve GUI/EOS/audio/segment invariants. Do NOT request another SDK fingerprint, WPR/UMDH or serial 4-hour manual investigations. User's already collected official 6/6 Windows10 SDK hashes remain valid.

Prior corrected 64-cycle Windows CI A/B: PrivateUsage effect 98.2414% smaller; official Key effect +20,932 vs candidate +2. These CI numbers do NOT prove zero residual memory leak or safe 24x365 Tapo operation.

Production candidate HOLD. User action: NONE. Do not upload private camera details/RTSP, logs, video, or ETL to public GitHub.
