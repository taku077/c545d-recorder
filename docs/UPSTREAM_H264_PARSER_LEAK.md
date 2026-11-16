# H.264 parser memory-growth candidate — upstream fix review

Date: 2026-11-16

## Why this is materially relevant
The current C545D pipeline creates **three** `h264parse` elements: one on
each Tapo RTSP input and one after x264 encoding. The GStreamer docs confirm
that `h264parse` belongs to `videoparsersbad`.

Earlier local heap analysis included allocation stacks referencing
`gstvideoparsersbad.dll`. The new `avdec_h264` version has reduced
the encoder CPU growth but still shows about **+6.17 MB/h** in private
memory after a six-hour warmup during a ~15h23m run. Those observations
motivate investigation; **they do not prove an H.264 parser leak**.

## Actual upstream fix
GStreamer **1.28.2 (2026-04-07)** release notes include:

- `h264parser: Fix memory leak in gst_h264_parser_parse_nal()`
- Issue: `gstreamer/gstreamer#4966`
- Merge request: `gstreamer/gstreamer!11060`

This is a real upstream memory-leak fix on the relevant library path.
A downstream backport may exist; the version alone cannot prove that
older builds are unpatched.

## What changed in this PR
`Record.ps1` now collects the **installed** `h264parse` plugin
version via `gst-inspect-1.0 h264parse` at startup and writes the
version to the *existing* recording transcript. If the version belongs
to an older release series, it emits a caution **only**.

It does not:

- stop/restart the current or new recording;
- change x264, NTP sync, muxer, or decoder properties;
- download/install new GStreamer packages;
- include camera credentials, RTSP URLs, or local paths in the new log line.

The pre-existing GStreamer core version logging remains intact.
The actual plugin version matters because plugin files may be older
than the core executable if installations are mixed.

## Version-based decision
- `h264parse` **1.28.2 or later in the 1.28 line**:
  that upstream fix should be present; do *not* claim this bug explains
  any remaining memory growth.
- `h264parse` **earlier**: a controlled **side-by-side** test of a
  newer official MSVC x86_64 GStreamer runtime is justified, preserving
  the current known-good install as rollback. Do not overwrite the
  working installation or update during an active recording.
- Version unrecognized: keep recording; do not make a speculative change.

The official Windows download page currently lists binary installers
for 1.28.8 even though the release history lists 1.28.9 (2026-11-06)
as the latest tagged release. Never invent a download URL. Use only
verified official binaries when a controlled upgrade is warranted.

## Future validation
The acceptance metric is the change in the post-warmup **private MB/h**
slope for the same video/encoder settings, while verifying audio/video
synchronization, hourly MP4 splits, normal EOS stop and restart.
A one-time drop in total private MB or CPU is not adequate proof.

## References
- https://gstreamer.freedesktop.org/releases/1.28/
- https://gstreamer.freedesktop.org/documentation/videoparsersbad/h264parse.html
- https://gitlab.freedesktop.org/gstreamer/gstreamer/-/issues/4966
- https://gitlab.freedesktop.org/gstreamer/gstreamer/-/merge_requests/11060
- https://gstreamer.freedesktop.org/documentation/tools/gst-inspect.html
- https://gstreamer.freedesktop.org/download/
