# C545D — First real GIO original-source ETLX paired census (2026-11-23 JST)

## Exact tested milestone

This is an **actual patched GLib/GIO 2.82.4 one-cycle initial AppInfo source ownership** result on disposable Windows2022, NOT a recorder-host test, not a repeated 16-cycle / 4h leak measurement and not a production release.

Original paired Windows Actions [#45186553913 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45186553913), job `137733556139`, commit [`649b287`](https://github.com/taku077/c545d-recorder/commit/649b287c4d904741fbaeb8f72a25b667b99cf1c0):
- Pinned GNOME GLib/GIO 2.82.4 MSVC x64 rebuilt with experimental CI-only fixes, source-phase trace, and privately kept PDB verified against DLL CodeView GUID+Age. Exact SDK 2047 exported-symbol compatibility verified. No production DLL or recorder touched.
- Isolated GIO disposable PID, heap ETW starts before **the first selected AppInfo call** (not before process main), sequential bounded private ETL <=256 MiB, loss-zero gated. The process remains alive at the ETW stop after the one-cycle settled cleanup.
- `TraceLog.OpenOrConvert`, original `HeapTraceAlloc.CallStack()`, exact trusted GIO module + allowlisted method, original heap/address identity propagated through ReAlloc and Free. 0 missing original call stacks in the captured events; not all original owners are assignable to the six allowlisted GIO functions.
- Earlier [#45177912867 FAILURE](https://github.com/taku077/c545d-recorder/actions/runs/45177912867) was specifically `allocation_zero_size_unmodeled`, fixed by [`c9bfc52`](https://github.com/taku077/c545d-recorder/commit/c9bfc520e94b71d40624d1267a56831c25cdca99): accept HeapAlloc request size 0 as a tracked *identity* with nonzero address, not as proof of zero committed pages. First subsequent [#45185626631 FAILURE](https://github.com/taku077/c545d-recorder/actions/runs/45185626631) finished the nochange arm but hit the original 390000 typed-event reader limit in registry arm (observed exactly 196874 alloc,1476 realloc,191650 free at limit), **not** an ETW buffer-loss fault. Both bounded parser/model limits were raised to 2M events against private 256 MiB ETL in `649b287`. Both Windows conditions then passed. [#45186553777 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45186553777) repeats only the existing separate synthetic source model regressions after that change.

## Actual paired initial AppInfo ETLX and phase-matched PSAPI

| Metric | nochange | registry | registry minus nochange |
|---|---:|---:|---:|
| Typed PID heap events | 169078 | 860372 | 691294 |
| HeapAlloc | 88995 | 433999 | 345004 |
| HeapReAlloc | 856 | 3257 | 2401 |
| HeapFree event | 79227 | 423116 | 343889 |
| HeapAlloc request size zero | 12 | 14 | 2 |
| Original HeapAlloc stack missing | **0** | **0** | 0 |
| GIO module present on original stack | 86231 | 429792 | 343561 |
| Original stack matched allowlisted GIO method | 85028 | 428585 | 343557 |
| GIO-owned original allocations after internal ReAlloc target suppression | 84212 | 425361 | 341149 |
| Verified-original GIO owner later ReAlloc | 836 | 3231 | 2395 |
| Original GIO-owner logical final frees | 74002 | 407176 | 333174 |
| **Original GIO-owner still live** (`origin alloc - logical frees`) | **10210** | **18185** | **+7975** |
| All tracked original allocations still live | 10461 | 18429 | +7968 |
| Unknown-original live (all live minus proven owner live) | 251 | 244 | -7 |
| Heap requested sizes held, all source classes | 867257 B | 1323298 B | +456041 B |
| Process PrivateUsage delta preappinfo→settled | +3776512 B | +3796992 B | **+20480 B** |
| VM private/heap REGION delta same phase | +2682880 B | +2732032 B | **+49152 B** |
| Handle delta same phase | +551 | +553 | **+2** |

The two **different workloads** are one initial call each, not a repeated steady-state cohort. More outstanding GIO-owned blocks here does **not** imply 7975 leaked blocks. The 456041 B difference in **requested heap payload** must **not** be equated to +20480 B PrivateUsage or +49152 B REGION; commit and reserve/fragmentation/caches are measured differently. Neither arm demonstrates a source-closed global WinRT/APC phase; six pending registry watch subscriptions from the earlier steady 16-cycle trial remain an expected observed baseline, not an automatic leak.

## Every previously unclassified source row has an explicit *reason*, not a blanket unknown

From the same original complete Actions job, *without another Windows/ETW capture*, the numeric-only offline [`tests/analyze_c545d_gio_first_etlx_archive_ci.py`](https://github.com/taku077/c545d-recorder/blob/investigate/c545d-status-only-monitor-20261120/tests/analyze_c545d_gio_first_etlx_archive_ci.py) recomputes:

| Source classification gap | nochange | registry | Required next discriminator |
|---|---:|---:|---|
| Missing original HeapAlloc call stack | **0** | **0** | Already measured; no rerun |
| Stack includes GIO module but **not one of six allowlisted exact method names** | **1203** | **1207** | On private CI ETLX, classify exact GIO method into finite source-owned function cohort; keep untrusted names and paths private |
| No GIO module frame in original stack | **2764** | **4207** | Identify whether allocator/GLib/COM/CRT/probe module source outside GIO is legitimate. Never infer GIO by size or PID |
| Orphan ReAlloc whose original allocation was outside captured start | **17** | **23** | Since trace starts before first AppInfo **not before process start**, preserve `capture_start_gap`; an original address cannot be inferred from later ReAlloc |
| Orphan Free whose allocation was outside captured start | **693** | **7546** | Same `capture_start_gap`, not necessarily GIO leak |
| Internal HeapAlloc(new) counted in raw exact method stacks but suppressed as ReAlloc target owner | **816** | **3224** | Explicit target-prealloc generation is already modeled; not a second independent owner |
| Original HeapAlloc size zero | **12** | **14** | Identity traced, requested-size 0 does not mean no committed heap allocation |

Unknown total original allocation is **3967** nochange (=1203+2764), **5414** registry (=1207+4207), with zero missing stacks. This explicitly answers *why* not every original was attributed and *what field* must be added for further classification, rather than allowing arbitrary `UNKNOWN` claims.

[Offline archive CI #45187881256 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45187881256), job 137738145188, runs on ubuntu only. It privately downloaded original job logs, extracted exact allowlisted sanitized numeric lines from **both arms**, verified three independent balances:
1. Typed heap events = Alloc+ReAlloc+Free (both arms).
2. All original allocations = exact GIO allowlisted source + `GIO frame unmatched method` + `no GIO frame`.
3. Original verified-GIO still live = verified original allocated − verified logical frees = all tracked still live − unresolved-original still live.

It checks source PDB/method proof flags, pre-first AppInfo→settled equivalent measurement phase, privacy and no misleading global quiet/leak statuses; 1 positive and **15 negative malformed/corrupt cases** pass. Only numerical summary emitted; raw job log deleted locally. No user action.

## Next AI-only discriminator and explicit safety gates

1. Create a privacy-safe **per exact original allocating function** cohort (the six trusted GIO method names) including *still-live original block count and requested bytes* at the same AppInfo phase, correctly transferring function identity through realloc/free/target-preallocation reuse. A stack with several possible owning functions should not silently assign arbitrary root. Keep function/source paths private; print only allowlisted categories and numeric counts.
2. Before any new Windows GIO trace, test this per-function identity model against original native 24/6/24 regression + synthetic negative owner/collision/ambiguous-frame fixtures in fast isolated CI. Do not run another identical one-cycle GIO capture solely because 7975 more requested source objects were counted.
3. Only one targeted *new* bounded disposable GIO run after per-function stack attribution proves a new discriminator. Compare equivalent **active-subscribed** AppInfo *repeated* settled epochs and same-phase PrivateUsage/REGION/handles/CPU, unlike current first-call start (one initial pair). Quantify whether any per-function retained cohort actually accumulates across work cycles after watchers stabilize. Use existing logs wherever possible.
4. Four broad classification cases remain **evidence_gap**, production recording **HOLD**; `install_approved=0`, `live_test_authorized=0`. Windows10/Tapo after patch **untested**. Do not alter user recorder, RTSP streams, x264 QP24, AAC, 2560×720@15fps, one-hour MP4, AV sync, avdec_h264, safe EOS or DLLs.

## References

- [Microsoft HeapAlloc](https://learn.microsoft.com/en-us/windows/win32/api/heapapi/nf-heapapi-heapalloc) and [HeapReAlloc](https://learn.microsoft.com/en-us/windows/win32/api/heapapi/nf-heapapi-heaprealloc)
- [Microsoft PerfView TraceEvent Programmer's Guide](https://github.com/microsoft/perfview/blob/main/documentation/TraceEvent/TraceEventProgrammersGuide.md)
- [Live pinned GIO Windows ETLX source workflow](https://github.com/taku077/c545d-recorder/blob/investigate/c545d-status-only-monitor-20261120/.github/workflows/c545d-gio-first-appinfo-etlx-ci.yml)
