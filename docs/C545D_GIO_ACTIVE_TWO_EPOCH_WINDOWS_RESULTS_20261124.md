# C545D: two active GIO epochs — Windows evidence, 2026-11-24 JST

## Confirmed CI

1. [Official stock GStreamer 1.28.8 Windows native smoke #45211760632 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45211760632). Builds the instrumented C source with MSVC x64, runs two unchanged-registry epochs in a disposable Windows2022 process and audits numeric QPC, CPU, PSAPI PrivateUsage, VirtualQuery and handles. All sampled stock nochange resource deltas 0. This is a stock-SDK smoke and not a candidate DLL leak verdict.
2. [Modified candidate GLib/GIO 2.82.4 native two-epoch CI #45213046661 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45213046661), job 137826671009. Pinned source, MSVC x64 PDB and 2047 official GIO export parity. A separate disposable process per arm, two sequential active epochs within each process. Both numeric resource gates and QPC per-worker begin→scan_end→unlocked→after_notify parity gates passed. This test does NOT capture phase-scoped ETW allocation provenance.
3. [Source and negative worker audit #45212577550 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45212577550). Worker ordinals and incomplete epoch cutoffs are checked; this does not prove global APC/WinRT quiescence.

## Observed same-process post-initialization epoch deltas

| Delta | nochange epoch1 | nochange epoch2 | registry epoch1 | registry epoch2 |
|---|---:|---:|---:|---:|
| PSAPI PrivateUsage, bytes | +114688 | 0 | +86016 | +356352 |
| VirtualQuery MEM_PRIVATE, bytes | 0 | 0 | 0 | 0 |
| Process handles | +3 | 0 | +3 | 0 |
| CPU user+kernel, 100ns ticks | 0 | 0 | 4218750 | 4531250 |
| GAppInfoMonitor changed callbacks | 0 | 0 | 0 | 0 |
| Completed instrumented AppInfo workers | 0 | 0 | 1 | 1 |
| QPC ticks elapsed | 9084119 | 9077454 | 14149992 | 14123564 |

The modified candidate registry second epoch is associated with a **+356352B PrivateUsage change**. This is not proven retained GIO HeapAlloc source, a leak, or a sustained slope. It could include heap allocator retention or other parts of the process. Process private-region commit and PSAPI PrivateUsage have different accounting. CPU metrics are cumulative time deltas rather than percentages. The changed callback remains 0 in both registry epochs *despite* one completed instrumented worker per epoch; distinguish worker completeness from visible monitor notifications and do not assume why callbacks were absent without source evidence. Only the disposable Windows CI user registry is modified, and the temporary value is cleaned up.

## Single next discriminating automated capture (not yet run)

1. Bound ONE continuous ETW HeapAlloc/ReAlloc/Free trace from before first GIO AppInfo call, across baseline/epoch1/epoch2 and settled cleanup in the SAME patched candidate process. Preserve zero event/buffer loss, <=256MiB private ETL, <=2M typed events, matching native PDB GUID+age, source restrictions and output privacy.
2. Read the source process QPC checkpoints and match to TraceEvent TimeStampQPC with explicit alignment checks; snapshot the same original-owner ledger at each cut. Keep both strict multi-method ambiguity and nearest-allowlisted proxy (not proven direct allocating function). Prevent a provisional Free→ReAlloc from crossing a checkpoint unnoticed, and cross-check source cohort live counts and requested bytes against the independent generic ledger at every cut.
3. Reconcile those source cohort changes against +356352B PSAPI private usage in the registry second epoch. If repeated allocations are retained, check subsequent phase release or plateau in one bounded automated test; avoid successive multi-hour user traces. Do not require all 6 normal subscribed watchers to vanish.
4. The code and Windows2022 automated measurement are NOT a real Windows10 2-RTSP recording or proof of 24/7 stability. Release HOLD; install_approved=0; live_test_authorized=0; no manual user measurement requested.

References: [Microsoft GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes); [PerfView TraceEvent](https://github.com/microsoft/perfview/blob/main/src/TraceEvent/TraceEvent.cs).
