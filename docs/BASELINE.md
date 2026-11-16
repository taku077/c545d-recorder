# Baseline candidate — 2026-11-16

The target migration source is `C545D_新デコーダ版_簡単起動_2026-11-16.zip`, with scripts from that ZIP unchanged.

Evidence from the 2026-11-16 user test:
- Long-running recording reported `Decoder: avdec_h264`.
- Recorded CPU series stayed roughly 19–22% through ~15 hours rather than climbing toward ~40%.
- Private memory still increased gradually; 24×365 stability is **not proven**.

**Do not** change H.264 x264 medium, quantizer 24, 2560×720, 15fps, audio codec or synchronization without a documented reason and a reversible test.

Required real-PC tests: start/stop/restart, split-boundary playback, A/V sync, CPU trend over elapsed time, private-memory trend, and safe MP4 finalization.

Security: no camera IP, credentials, local settings, or raw logs in GitHub.
