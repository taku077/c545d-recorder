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

## Feedback-driven rolling release and diagnostic evolution — AGREED 2026-11-24

The first release's diagnostic instrument is **not assumed to capture every future root-cause discriminator**. Its measurement schema and collectors are versioned, continually improved according to actual evidence, and released in tandem with **recorder updates when needed**. The user-proposed loop is binding as the project development workflow:

**Safe recorder + detached diagnostics release candidate -> recording and continuous low-overhead collection -> AI source/CI research without waiting -> 72h/weekly sanitized ZIP from host -> immediate analysis of what is measured, what remains unmeasured, and why -> independently implement/test both recorder corrections and next diagnostic version -> publish the next safe versioned release pair (or diagnostics-only update when recorder unchanged) -> repeat.**

Do **not** make release frequency automatically equal to the seven-day upload cadence. The 7-day rhythm is for report delivery, while software updates are **evidence-driven** and pass release-specific safety tests. Continue the installed, known-safe recorder while independently developing or updating the diagnostics whenever recorder modification would introduce unwarranted risk.

### Mandatory decision output after EACH uploaded diagnostic ZIP

Within the current active chat, analyze the new ZIP together with earlier ZIPs, historical ETW/WPR/UMDH/16/256-cycle CI and the live GitHub PR, without restarting completed investigations. Produce a durable, concise **evidence-to-next-release ledger**:

1. **Validated measurements**: collector/schema version, fingerprint, source build hash, time boundaries, number of samples, completeness/lost intervals, CPU/PrivateUsage/handles/thread trend, MP4/finalization/2-RTSP/A-V health. Distinguish initial warmup, steady state, recorder restarts and observer overhead.
2. **Evidence and uncertainty**: what is new, what hypothesis it confirms/rejects, any changed or conflicting historical reading, and exact unknown cause. Never label a missing metric merely unexplained: identify the missing event, counter, stack, parser or synchronization condition that prevented classification and the least disruptive way to obtain it.
3. **Instrument gap backlog**: for every meaningful unclassified growth component, specify the required new field/event, collection trigger and duration, expected overhead/storage/privacy, and which hypothesis it will discriminate. Rank by actionable value and minimal impact. Reuse any existing counters/trace before adding a probe.
4. **Next diagnostic release**: implement the smallest **versioned and backward-compatible** update needed to close the highest-value evidence gaps. Validate via isolated Win2022 CI synthetic inputs, Windows API / runtime compatibility, privacy/low-overhead tests and failure isolation BEFORE any host upgrade.
5. **Recorder release candidate**: assess independently whether source fix or packaging/quality improvements have passed their separate unit, 2-stream/media/sync/EOS, pinned DLL-ABI and practical acceptance gates. If not, only diagnostics may advance and recorder remains at its last approved version.
6. **Handoff and next-cycle verification**: publish GitHub commits, PR HEAD, CI pass/fail, exact measured facts, implementation status, release HOLD/approval and the next diagnostic's *specific expected new evidence*; do not treat a weekly report as approval to install.

A diagnostic update may add e.g. **handle-type trend**, GIO worker-cycle event counters, RTSP reconnect causal timestamps, segment-finalization checks, time-series slope after initial warmup or low-volume error/event ring buffer **only when new evidence makes it necessary**. Detailed per-HeapAlloc ETW remains opt-in, separate, bounded and never silently enabled.

### Versioning, upgrades and continuity

- Each package carries independent `recorder_version`, `diagnostics_version`, `diagnostic_schema_version`, hash/fingerprint and UTC+local capture range. Reports retain these plus optional `feature_flags` and **field availability/collection gaps**, so historical reports remain interpretable.
- Additive schema fields preferred; old JSON/CSV readers accept unknown new fields, new readers accept previous supported versions and annotate `not_collected` rather than silently setting zero. Test migration, mixed-version weekly archives and malformed/missing sample rejection in CI. Include an archive manifest and producer/consumer schema compatibility assertions.
- Preserve existing local counter history and rolling data across tool upgrades, with atomic backup/rollback; record a `diagnostics_upgrade` event and version transition so trends are split/normalized across instrumentation changes. Never interpret a step caused by the new collector as a recorder regression.
- Diagnostic-only updates must not change, inject into, pause or restart the recorder; users should be able to update the observer with minimal action and recover automatically if it fails. Recorder binary/DLL updates require a separately approved safe recorder stop/EOS, offline install, rollback and smoke check; never hot-swap DLLs. No forced regular recorder restart as a memory-leak fix.
- A ZIP may be generated automatically **on the recording PC**, but it is uploaded to the private chat by the user; no automatic sending to ChatGPT, GitHub or another server without explicit setup and permission. Public repo has only synthetic fixtures and aggregated results—never camera footage, RTSP credentials, raw diagnostic logs, private ETL or host paths.
- If reporting is delayed, the monitor continues **bounded** safe collection/rotation and both engineering tracks advance in chat on request; nothing is "blocked waiting for this week's ZIP" except conclusions requiring new host-specific evidence. If evidence is too thin to specify a useful new collector, defer that collector rather than adding broad, high-overhead logging.

### Definition of a successful iteration

An iteration is useful when it yields **either** a verified reliability/recording improvement **or** a narrower, explicitly measurable explanation of the remaining increase **or** a validated diagnostic feature that discriminates an important unresolved hypothesis. Do not maximize the number of captures/commits as the objective. Keep one release changelog containing fixed issues, new observability, resource overhead, known problems and rollback path, and compare identical conditions before asserting percent improvement.

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
