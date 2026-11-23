# C545D — Real GIO ETLX zero-request allocation identity fix (2026-11-23 JST)

## Exact starting point

Active PR [#62](https://github.com/taku077/c545d-recorder/pull/62). As of 2026-11-23 the actual isolated Windows2022 initial-AppInfo source-origin trial reached source symbols and a first-call ETL, **not** a completed GIO memory-leak classification.

On [Windows run #45177912867 (FAILURE)](https://github.com/taku077/c545d-recorder/actions/runs/45177912867), disposable Windows2022 GLib 2.82.4 pinned patched source compiled with MSVC x64. The GIO DLL CodeView RSDS and private MSVC PDB GUID+age matched; SDK exports matched 2047; one nochange AppInfo trial captured ETW **before the first selected AppInfo call**, with loss-zero logger and before settled cleanup. The exact ETLX decoder fail-closed result was:

`C545D_GIO_ETLX_FIRST_SOURCE_GAP,reason=allocation_zero_size_unmodeled,stage=heap_event_replay,alloc_observed=44380,realloc_observed=313,free_observed=38460,stack_missing=0,gio_module_in_original_stack=44287,exact_gio_method=44252,gio_modules_loaded=1,gio_module_symbol_lookup=1,tracked_live_count=5947,gio_origin_alloc=43952,gio_origin_realloc=303,gio_origin_freed=37491,raw_uploaded=0,release_HOLD=1`

**Interpretation:** 44,252 resolved original GIO source-method stacks were observed **before the first size-zero request**, but the parser stopped early and did **not** finish the nochange arm. No completed registry-arm results or leak attribution can be inferred from those truncated counters. GIO PDB and native stack resolution no longer the immediate blocker in that trial.

Previous CI [#45177071857 FAILURE](https://github.com/taku077/c545d-recorder/actions/runs/45177071857) had `realloc_new_address_collision` at just 61 alloc events. [Commit `44d7100`](https://github.com/taku077/c545d-recorder/commit/44d710030561bb2a292098c6c4d75aed071f1a2c) added a bounded exact-heap/target-size/young-target pairing for Windows HeapAlloc(new) before HeapReAlloc(old,new), with fail-closed collision checks. The new 44k-event trace bypassed the earlier collision and encountered the next explicitly diagnosed missing case, zero requested allocation size.

## New fix

Commit [`c9bfc52`](https://github.com/taku077/c545d-recorder/commit/c9bfc520e94b71d40624d1267a56831c25cdca99) updates two test-only files:

- `tests/C545DEtwHeapIdentity/GenericHeapLifetime.cs`: validates heap handle and **nonzero address** with requested size **>=0** (negative and unbounded sizes rejected); tracks `HeapAlloc(0)` as an allocated **object identity with zero requested payload bytes**, not a phantom or zero committed heap pages; supports subsequent reallocation old/new size zero, Free, address reuse and original GIO source proof token. Tracks separate numerical zero-request counts and keeps both invalid address and negative-size tests. New positive tests for 0→32→0 request-size changes, frees, GIO origin and same-address generation reuse; two new negative tests.
- `tests/C545DGioEtlxOwnerCensus/Program.cs`: removes the old unconditional `if (ev.AllocSize<=0) throw allocation_zero_size_unmodeled` guard; relies on strict common heap-address/size validation and exposes only numeric `zero_req_original_alloc,zero_req_realloc,zero_req_old_size,zero_req_new_size` counters in safe census and fail-closed diagnostics. Does not leak addresses, raw ETL/PDB, registry or media.

Microsoft official [HeapAlloc](https://learn.microsoft.com/en-us/windows/win32/api/heapapi/nf-heapapi-heapalloc), [HeapReAlloc](https://learn.microsoft.com/en-us/windows/win32/api/heapapi/nf-heapapi-heaprealloc), [HeapFree](https://learn.microsoft.com/en-us/windows/win32/api/heapapi/nf-heapapi-heapfree) specify pointers returned on success and a separate requested byte size; allocation *request size zero* must not be treated as proof of *zero actual committed memory*. This model accounts request bytes, **not** allocator usable/committed block bytes.

## CI and open decisions

- **[Mixed-size real heap ETW regression #45185626659 — SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45185626659)** under the amended model. All generic fixture negative tests and original 24/6/24 native ETW route still pass.
- **[First-AppInfo source preflight #45185626517 — SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45185626517)**, verified pinned source contracts and C# source classifier.
- **[Real first-AppInfo GIO ETLX #45185626631](https://github.com/taku077/c545d-recorder/actions/runs/45185626631)** began on the updated commit; status must be verified at resume. Do not treat a queued/in-progress CI or an early fail-closed census as success.
- If the new first GIO run still fails, read the allowlisted reason, `stage`, and integer counters FIRST. Diagnose the **next new event behavior**, create exact negative fixtures, and avoid unbounded retry/long host captures. A new real GIO run is justified only if the fix provides a previously unavailable discriminator.
- Do not infer PrivateUsage or REGION growth from request bytes; once first AppInfo GIO source end census succeeds, compare exact same-arm phase-matched PSAPI PrivateUsage/region/handles and owner lifetime. Six persistent registry watchers may represent a healthy subscribed baseline, and no single quiet worker moment proves APC/WinRT global quiescence.

Safety unchanged: four broad cases still `evidence_gap`, `release_state=HOLD`, `install_approved=0`, `live_test_authorized=0`, real Windows10/Tapo host untested; no production video/codec/AV/MP4/EOS changes. No user action.
