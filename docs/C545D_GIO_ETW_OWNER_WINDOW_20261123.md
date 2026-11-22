# C545D real GIO ETW attribution-window development — 2026-11-23 JST

## Goal and explicit boundaries

This replaces the obsolete GIO ETW **circular / attach-after-work / top25 module-frame occurrence** sample with a **pre-workload, non-circular, loss-gated source-stack outstanding allocation** census. The 16-cycle nochange and synthetic registry-change arms use the same pinned GLib/GIO 2.82.4 COM/WinRT candidate, Windows 2022 MSVC, SDK 1.28.8 and strict **2047 exported-symbol ABI**; no camera, recorder, production DLL or user computer touched.

Microsoft [Enabling Heap Data Capture](https://learn.microsoft.com/en-us/windows-hardware/test/wpt/enabling-heap-data-capture), [Using Actions to Analyze Process Heap Data](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/xperf/using-actions-to-analyze-process-heap-data), [Avoiding Lost Buffers](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/xperf/avoiding-lost-buffers), [Heap Extents](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/xperf/heap-extents): Xperf matches allocations and frees **within the captured interval**. Outstanding is not necessarily a leak, and heap committed pages can remain after a block is freed. Lost events or bounded top-N stack output cannot prove complete owner attribution.

### New code

- `tests/Invoke-C545DGioEtwOwner16Window.ps1`: live Windows disposable-PID `-FileMode Sequential`, ETW start only AFTER `baseline_ready.signal` but BEFORE `trace_armed.signal`; ETW stop only AFTER `precleanup_ready.signal` but BEFORE `trace_stopped.signal`, no IFEO/GFlags, bounded 16 cycles, strict per-logger EventsLost and LogBuffersLost zero proof, private ETL+symbol files removed locally.
- `tests/analyze_c545d_gio_etw_stack_cohorts_ci.py`: parses unfiltered Xperf `-a heap -stacks -top 1024`, categorizes into fixed **stack contains module** cohorts (GIO/GLIB/GOBJECT/COM_WINRT/PROBE/OTHER), computes counts/Out KB and coverage relative to global Xperf count. 8 corrupt fixture types rejected; does **not** falsely claim causal allocation owner, whole-process baseline or completed APC/WinRT work.
- `.github/workflows/c545d-gio-etw-owner-stack-paired16-ci.yml`: real Windows MSVC debug-symbols build, complete SDK 2047 export check, 2 isolated 16-cycle A/B controls, same-PID AppInfo phase and watcher lifetime, **only sanitized numeric** logs/artifact. No raw registry keys, media, addresses, ETL, untrusted symbol names or DLLs uploaded. Classification gate remains OPEN, release HOLD.

### Genuine first attempt and failure scope

[Windows CI #45051751198 FAILURE](https://github.com/taku077/c545d-recorder/actions/runs/45051751198), job 137298173103:

- **MSVC build and 2047 SDK export check SUCCESS**, new source-stack parser 2 positive/8 negative fixtures success, controller PowerShell syntax checked.
- **NOCHANGE actual GIO 16 cycles succeeded**: `global_alloc=32101`, `global_out=0`, `parsed_stack_rows=64`, `parsed_alloc=32101`, `parsed_out=0`, `allocation_count_coverage_complete=1`, GIO call-stack cohort 30816 new allocations and 0 outstanding; GLib cohort 1248 and 0; probe cohort 37 and 0. Xperf loggers zero-loss checked for this arm. The result says **all *newly traced* Windows heap allocations within the controlled nochange interval were freed before stop**. It does **not** say prior allocations or commit were freed, or that recorder memory leak is zero.
- **REGISTRY arm performed all 16 cycles, entered precleanup fence, then FAIL-CLOSED before Xperf merge:** `ETW logger lost-event counters not independently parsed`. It is **NOT known** whether the HeapSession disappeared (e.g., file size cap) or output format changed, and no claim that event loss was zero, that it was a leak, or that a registry heap total exists. The private logger report was deliberately not uploaded.
- [`ed19e4e`](https://github.com/taku077/c545d-recorder/commit/ed19e4e60c2317f20b492781f517bef5bb89cc94) replaces cross-logger regex with strict **HeapSession-only** status block and safe gap flags `heap_session_present` / `events_line_present` / `log_buffers_line_present`; permits a capped 512 MB sequential report only in isolated CI. This corrects the previous diagnostic blind spot; still requires zero event/buffer loss. [Rerun #45052226913](https://github.com/taku077/c545d-recorder/actions/runs/45052226913) status must be checked before any claim of registry owner attribution.

### Next outcome-specific actions

1. If rerun succeeds and shows 0 registry outstanding, do **not** claim all GIO leak-free; compare residual PrivateUsage vs traced freed allocations and original Combo256 post-cleanup, and add same-run committed-heap/worker lifetime evidence.
2. If nonzero registry outstanding, inspect **only** allowlisted owner stack cohorts and coverage; require expected lifetime, worker/APC queue status, and repeatable idle phases before saying LEAK_CONFIRMED. Top-N aggregation is not proof of causal function by itself.
3. If HeapSession disappears with cap, fix **bounded trace capacity** or narrow instrumented window rather than hiding incomplete ETW. If counters are unparseable, fix parser against scoped logger structure; do not re-run long host tests. If losses are positive, reject attribution and optimize bounded capture first.

All four broad evidence-gap cases remain OPEN until actual owner and lifetime classification, and real host release HOLD. User action NONE. Production recording settings and multimedia behavior unchanged.
