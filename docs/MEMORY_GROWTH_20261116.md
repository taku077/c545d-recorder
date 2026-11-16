# Long-duration memory assessment — 2026-11-16

**Scope:** Anonymized aggregate observations from previously supplied local
`Memory_Trend.csv`. Raw CSV, local timestamps, PIDs, paths, IP addresses,
and credentials are **not** committed to this repository.

## Working avdec_h264 candidate (measured, not extrapolated)
- Window: about 15 hours 23 minutes of one uninterrupted recording session.
- Private memory at start: **593.7 MB**.
- Private memory at end: **706.1 MB**.
- Growth over the window: **112.4 MB**.
- After 6-hour warmup: least-squares slope **+6.17 MB/hour**,
  R² approximately **0.9965**. This is *not* yet a plateau.
- GStreamer CPU percentage remained about **19–21% on average** in
  consecutive one-hour windows after the decoder change.
- Memory increases are particularly visible at two recurring
  wall-clock minute windows, but the responsible operation is unknown.
  **Do not attribute those events to MP4 splitting without evidence.**

## Contrasting previous baseline
Before the `avdec_h264` preference change, CPU percentage increased from
about 21% toward 40%, and private memory grew tens of MB per hour.
This shows a major improvement, not proof that residual growth is safe for
24×365 unattended recording.

## Interpretation and safeguards
- A time-correlated upward private-memory slope is **not**, alone,
  proof of a GStreamer leak. GLib, FFmpeg, MP4 muxing or other allocators
  may retain reusable caches.
- GStreamer core and plugin version was absent from earlier logs.
  The associated PR records the core version at the beginning of **new**
  sessions only; existing recordings are not interrupted.
- GStreamer 1.28.x release notes contain memory management and RTP
  fixes. Whether a given fix applies depends on the locally installed
  version. Do not automatically upgrade the runtime on the recording PC.
- Never implement forced daily restarts as a hidden 'memory fix':
  they can leave gaps in the security recording.
- Do not change x264 medium, quantizer 24, 2560×720/15fps, NTP sync,
  or the two-lens composition without a supported hypothesis.

## Reproducible assessment
`tools/analyze_memory_trend.py` reads an *existing* local CSV without
network access, computes whole-session and post-warmup memory slopes,
and excludes rows aggregating multiple PIDs. CI runs only **synthetic**
tests; it never needs actual camera data.

Example, when explicitly analyzing a local copy:
`python tools/analyze_memory_trend.py Memory_Trend.csv --warmup-hours 6`

## Next decision gate
1. Determine the **installed** GStreamer core version from a future
   standard recording log.
2. Match installed version to fixed RTP/decoder/allocator bugs in GStreamer
   release notes.
3. If the version already includes the relevant fixes, examine a
   controlled *single-cause* patch instead of speculative broad changes.
4. Verify that the residual slope trends toward zero over longer captures,
   along with hourly MP4, audio/video sync and clean stop/restart.

Sources:
- https://gstreamer.freedesktop.org/releases/1.28/
- https://gstreamer.freedesktop.org/documentation/tools/gst-launch.html
- https://gstreamer.freedesktop.org/documentation/coreelements/queue.html
