# C545D — ETLX original HeapAlloc call-stack ownership through ReAlloc and Free (2026-11-23 JST)

## Exact continuation and problem solved

Active work is PR [#62](https://github.com/taku077/c545d-recorder/pull/62), development branch `investigate/c545d-status-only-monitor-20261120`. Prior verified Windows2022 mixed-size fixture [CI #45169421721 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45169421721) could follow HeapAlloc→HeapReAlloc→HeapFree addresses at multiple allocation sizes, but all **original allocating function sources were unresolved**. A per-stack Xperf group or an ETW `Source` allocator type (LFH/lookaside) is not a reliable source function; that distinction is preserved.

New code [`tests/C545DHeapOriginStackProbe/Program.cs`](https://github.com/taku077/c545d-recorder/blob/investigate/c545d-status-only-monitor-20261120/tests/C545DHeapOriginStackProbe/Program.cs) uses pinned `Microsoft.Diagnostics.Tracing.TraceEvent` **3.2.8**:

1. Only a disposable Windows2022 Actions worker, a temporary ETL under `RUNNER_TEMP`, exact selected fixture PID, existing preworkload start and logger zero-loss checks, and a locally compiled trusted EXE/PDB are permitted.
2. Convert the **same** private ETL to ETLX via `TraceLog.OpenOrConvert`. Use `TraceLog.Processes.LastProcessWithID`, native module-loaded metadata and `TraceLog.CodeAddresses.LookupSymbolsForModule` to resolve the exact fixture's symbols. `SymbolReaderOptions.CacheOnly` and a private-directory-only `SecurityCheck` deny remote/untrusted symbol paths. Neither PDB, ETLX, raw ETL, path, address, PID nor stack text is ever emitted or uploaded.
3. For each original `HeapTraceAlloc` typed event, retrieve `TraceEvent.CallStack()` and accept source proof **only when a frame in the exact original fixture EXE resolves the exact `mixed_alloc` function name**. Module-only, unresolved stack, same function in a different module, later `mixed_realloc`, and symbol lookalikes are separately rejected. The fixture's original size classes help select the known control experiment only; this is **not** a real-GIO classification strategy.
4. The revised [`GenericHeapLifetime.cs`](https://github.com/taku077/c545d-recorder/blob/investigate/c545d-status-only-monitor-20261120/tests/C545DEtwHeapIdentity/GenericHeapLifetime.cs) carries this original-source proof token with the allocation across moved and in-place reallocations, including native Free-before-ReAlloc, later explicit HeapFree, and foreign-size address reuse without wrongly handing an old owner to a different allocation.
5. The controller invokes the probe only with opt-in `-GenericMixed -ThroughCleanup -OriginStackAudit`: initial 24 alloc, six realloc, early free18/held6, then explicit final six frees, native `freed.signal` acknowledgement **before** ETW stop; the process exits normally only after ETW parsing.

All experimental C# source lives in `tests/`. There was **no change to production GStreamer, GLib, recorder, camera connection, Windows10 host, DLL, registry or MP4 output**.

## CI evidence (real Windows heap ETW + ETLX, controlled native fixture)

- **[Windows CI #45171175038 — SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45171175038), job `137680799593`**: `selected_alloc=24,original_stack_attached=24,fixture_module_seen=24,exact_native_alloc_method=24,unresolved_original_alloc=0,native_symbol_lookup_modules=1`. One positive and 11 negative original-callstack source checks passed. The separately verified mixed-size address-tracker also passed 24alloc/6realloc/24 final logical frees. **No GIO original function is proven by this calibration.**
- **[Windows CI #45171657774 — SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45171657774), job `137682447864`**: same original fixture control model, now with proof token propagation:
  - `selected_alloc=24`, `original_stack_attached=24`, `exact_native_alloc_method=24`, `unresolved_original_alloc=0`.
  - `linked_realloc=6`, **`fixture_origin_realloc_proven=6`**, including six native old-address Free-before-ReAlloc matches and moved destination identities.
  - `fixture_logical_frees=24`, **`fixture_origin_free_proven=24`**, `precleanup_held_six=1`, `postcleanup_live=0`, `postcleanup_live_bytes=0`.
  - Same-run generic non-owning reader's 24alloc/6realloc/24free passed with 118 selected PID heap ETW events and one different-size address reuse; its `fixture_proven_...` counts remain ZERO intentionally because the generic non-symbol reader does **not** invent source ownership.
  - All original stack probe negatives passed `positive=1,negative=11`; model negatives continue to verify bad old-size, orphan realloc, duplicated Free, lost scope, address collisions, and false address reuse. Recording device, original GIO owner and global APC/WinRT quiet all remain `0`/UNPROVEN.
- **[Windows #45171545615 — SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45171545615)** separately confirms the model provenance counter additions did not break the known mixed-size ETW reader.

This is the first CI proof in this PR that ORIGINAL native **source function** (not just stack count or heap address) survives a later realloc and remains attributable at final free. It **does not prove** whether real GIO retains/leaks the 466 previous stack-group outstanding items or explain the measured PrivateUsage increase.

## Strict next step (automated, avoid repeating existing tests)

1. Source audit the actual pinned rebuilt GLib/GIO 2.82.4 Windows disposable CI for original allocation stack coverage and private PDB/module naming. Do **not** assume the synthetic `mixed_alloc` source label is meaningful for actual GLib/GIO: a complete-before-workload trace plus native symbol identity and source mapping to modules/callers is required, with `unresolved_stack_count` and `unmatched_realloc_origin_count` explicitly exposed.
2. Align any genuinely new real-GIO trace with the **active subscribed** AppInfo phase (not a fictional zero-watcher globally quiet endpoint): original [Windows GIO #45133754345](https://github.com/taku077/c545d-recorder/actions/runs/45133754345) recorded six persistent pending watches in both arms (6→6), while PrivateUsage cycle0→16 **+331776 B**, heap REGION **+303104 B**, BUSY **-7734 B**. Those numbers cannot directly be assigned to particular allocations without source and phase evidence.
3. Only when source frame resolution, full-start allocation history and comparable AppInfo work-phase gates can all be asserted, run ONE bounded disposable Windows GIO alloc→realloc→free comparison alongside phase-aligned PSAPI PrivateUsage/REGION/CPU/handle readings. Fail closed on missing frames, source proofs, stale/orphan reallocs and ETW loss; do not upload stack symbols/raw ETL. No Windows10 host or user long-running measurement.
4. Maintain four overall memory classification cases as `evidence_gap`, `release_state=HOLD`, `install_approved=0`, `live_test_authorized=0`, `real_host_verified=0`, all original two-stream recording, x264, AV synchronization, AAC, hourly MP4 and EOS gates unchanged.

## Public technical references

- [Microsoft PerfView TraceEvent Programmers Guide](https://github.com/microsoft/perfview/blob/main/documentation/TraceEvent/TraceEventProgrammersGuide.md) — `TraceLog.OpenOrConvert`, `CallStack`, native symbol resolution limitations.
- [Microsoft ETW_HEAP_EVENT_ALLOC](https://learn.microsoft.com/en-us/windows/win32/memory/etw-heap-event-alloc) — event's `Source` is allocator memory source, **not original allocating function**.
- [Microsoft ETW_HEAP_EVENT_REALLOC](https://learn.microsoft.com/en-us/windows/win32/memory/etw-heap-event-realloc) — `OldAddress`, `NewAddress`, old/new sizes.
- [Microsoft TraceEvent sample 40_SimpleTraceLog.cs](https://github.com/microsoft/perfview/blob/main/src/TraceEvent/Samples/40_SimpleTraceLog.cs) — explicit `LookupSymbolsForModule` and native `CodeAddress.Method.FullMethodName`.
