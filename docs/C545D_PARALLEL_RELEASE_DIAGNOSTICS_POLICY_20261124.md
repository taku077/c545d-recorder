# C545D — provisional recorder release + parallel low-overhead diagnostics policy

Decision date: 2026-11-24 (JST). Status: **development policy agreed in chat; implementation and recorder release gates NOT yet passed**.

## Decision

Decouple the **first safe, limited recorder release candidate** from the investigation of the **remaining GLib/GIO/WinRT memory growth**. Release a separate read-only diagnostic companion with the recorder, then run the recorder and low-overhead monitor continuously while conducting independent AI-led GitHub/source/CI research between user-provided report uploads.

**Not** permission to install development DLLs or to claim 24/7 stability. `install_approved=0`, `live_test_authorized=0`, release HOLD until the explicit safe-release checks below pass.

## Fixed reporting cadence

| Event | Decision |
|---|---|
| First report | **72 hours after first approved diagnostic recording start** (one-off early safety check) |
| Regular reports | **Every 7 days thereafter**; one automatically assembled report package per interval |
| Local periodic counters | **Every 60 seconds**, independent recorder-side read-only observer |
| Crash, missing/invalid MP4, repeated RTSP disconnect, rapidly growing resources, low disk | Automatically flag and preserve contextual metrics immediately; offer an extra **one-click report**, but do **not** demand an unrelated long manual experiment |
| User task | Attach the prebuilt sanitized ZIP in the project chat when convenient; no manual WPR/UMDH/WPA inspection or repeated time-consuming captures |
| No report yet | AI continues code review, archived-log reuse, source analysis, Win2022 isolation tests, regression tests, build/release work **without waiting for host data** |

The clock starts **only after** a user-approved diagnostic release is actually installed and recording is started. Do not treat this date as the start of data collection. Every 7-day interval is relative to the prior scheduled report cut. Being late in a chat does not break collection or reset the schedule. The assistant cannot pull local PC data or perform unattended work in a closed chat; reporting requires the user's upload unless an explicitly approved secure connector is available.

## Diagnostic tool v0.1 contract

Run **outside** recorder/GStreamer process, as a replaceable, non-injecting read-only monitor. Do not change the recorder or kernel tracing settings to collect everyday metrics. Default 60-second process sample: timestamp JST+UTC, recorder PID and process start time, CPU process-time delta, PrivateUsage (PSAPI GetProcessMemoryInfo), working set, handle and thread count, recorder alive status, process restart boundaries, own observer overhead and missing/invalid samples. Distinguish PrivateUsage from WorkingSet and MEM_PRIVATE region bytes; never treat raw difference in private commit as proof of leaked allocations.

Add record-window metadata only: output MP4 hourly-segment detected/closed, file name masked/tokenized, byte length, duration, probe success/failure, wide/tele presence and A/V stream metadata when safely obtainable **after** file close, decoder/RTSP reconnect counts if already emitted safely by the recorder, crash/restart/error codes. Media content, raw RTSP URLs, camera hostnames or credentials do NOT belong in report data. Do not parse MP4 still being written. Do not run a heavyweight media validation pipeline on every 60-second tick.

Store bounded local CSV/JSON and compressed per-interval report: `manifest.json` (version, collection boundaries, host-safe OS/GStreamer build hashes, observer version, sample completeness), `process_metrics.csv`, `recording_integrity.csv`, `events.csv`, and `summary.json` (baseline/after-warmup slopes, maxima, growth/day and per-segment quality findings). Include numeric-only phase-aligned progress and a record of absent samples; do not invent averages for gaps. Keep at most **30 days** of bounded local summaries and rotate before exceeding a configurable **200 MiB diagnostic-data cap** (default proposal, subject to real performance verification). Anonymize filenames, user paths and environment in the report, and verify the archive contains no secrets. ZIP generation must not automatically publish anything to GitHub or any network.

On exceptions, emit a status indication and preserve continuous recording; never force-close a GStreamer DLL/handle, modify registry, kill the process, restart recording or trigger WPR by default. No privilege escalation in routine collection. Heavyweight WPR/ETW heap capture is a **separate opt-in**, bounded, low-impact verified operation, normally tested first on a disposable Windows GitHub Actions runner; no automatic detailed ETW triggered on the user's recording host without approval. Microsoft warns that heap tracing can affect performance.

## Two independent work tracks

**Track A — Recorder and diagnostic release:** inventory existing Windows 10 supported, actual tested recorder baseline and MP4/2-RTSP/sync/EOS path. Build a packaged versioned recorder + detached diagnostics + status/fingerprint + safe revert instructions. Preserve stream1 wide left, stream6 tele right, 2560×720@15fps, x264 medium QP24, mono AAC 48kHz target 192kbps, 1-hour MP4 rotation, avdec_h264, audio/video sync, graceful EOS and naming. One integrated user-approved initial practical acceptance check, not serial multi-hour exploratory experiments.

**Track B — leak investigation:** continue regardless of host upload. Reuse prior 16/256-cycle, UMDH/ETL and three-cut CI; current exact DisplayName getter 64 residual blocks/5632B and outside wrapper 32 blocks/5554B in registry epoch2 are **source callstack associations**, not proof of a sustained WinRT leak. Audit COM/cache lifetime, write narrowly scoped source fixes, build/run Windows2022 GitHub Actions with deterministic regression tests and numeric metrics, and collect only a single genuinely discriminating bounded host test if isolation cannot resolve a remaining host-specific question.

When an uploaded ZIP arrives, validate schema/completeness/sanitization, compare trends across days and segmented recording health, and merge new evidence into the independent root-cause hypothesis; then continue both tracks. No repeating earlier analysis unless a new specific contradiction is observed. Missing or late ZIP **never blocks Track B**.

## Limited release safety gates (must pass, not waived by this policy)

1. Reproducible signed/hashed or hash-verified versioned Win10-compatible build and pinned DLL/ABI; no unverified DLL swap or registry change on running recorder.
2. Automated regression for 2-stream composition, H264 decoder selection, AAC audio, nominal media parameters, 1-hour MP4 segments, naming, reconnect, controlled shutdown/EOS, and corrupt/partial-file detection. CI success does not replace host validation.
3. Separate diagnostics that preserve the recording workload and show low overhead; bounded file rotation and privacy redaction, crash safety, graceful failure, no command to modify the recorder.
4. One user-authorized minimum integrated real-camera acceptance session verifying first file close, 2-stream video and audio, EOS safety, sustained process resource observation and practical rollback; exact scope/duration set from existing evidence, NOT repeated 4h sessions.
5. Explicit user acceptance of a **limited monitored release candidate** and residual memory-growth risks; monitor release is not approval to install the current experiment PR #62 DLL. If the measured recorder cannot be used safely, preserve release HOLD and continue Track B with existing environment.

## User burden and reporting rules

Only request user actions that AI/CI cannot carry out. Routine task: **upload one sanitized auto-generated ZIP each 7 days** after one-off initial 72h check. Anomaly reports are optional and event-triggered, not a new mandatory cycle. No recorder source credentials, RTSP frames, raw ETL, raw heap addresses or unprocessed logs in the public repository. The diagnostic cannot directly send a ZIP into ChatGPT unless an explicitly configured/approved integration exists; never promise unattended chat receipt.

## Evidence (official docs and current project)

- [Microsoft Performance Counters Tools](https://learn.microsoft.com/en-us/windows/win32/perfctrs/performance-counters-tools); [Logman create counter](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/logman-create-counter)
- [Microsoft PROCESS_MEMORY_COUNTERS_EX / PrivateUsage](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex); [GetProcessMemoryInfo](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-getprocessmemoryinfo)
- [Microsoft WPR commands / heap tracing overhead](https://learn.microsoft.com/en-us/windows-hardware/test/wpt/wpr-command-line-options)
- [Live PR #62](https://github.com/taku077/c545d-recorder/pull/62); [exact DisplayName getter-frame CI #45220933192](https://github.com/taku077/c545d-recorder/actions/runs/45220933192)
