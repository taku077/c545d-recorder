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


## NEWER: ONE continuous ETW with three same-process QPC cutoffs (2026-11-24 JST)

**VERIFIED** [Windows2022 CI #45217120186 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45217120186), job `137841171782`, code HEAD [9eef364](https://github.com/taku077/c545d-recorder/commit/9eef364ca4a103487ab2bbfd615117f8dfa42f37): source-built patched GLib/GIO 2.82.4 and native PDB, 2047 GStreamer export parity, ZERO event/buffer loss gate, one continuous ETW trace before first AppInfo call, post-init baseline, two post-baseline registry/nochange cycles and settled cleanup; numeric QPC worker parity gate, safe original HeapAlloc/ReAlloc/Free strict and nearest-proxy cohort ledgers at each cutoff. Exactly 3 × 2 × 10 category counters per arm, 3 source scopes per arm and accounting PASS. Both traces confined to ephemeral Windows2022 runner, no ETL/PDB/raw pointers uploaded.

| Same-process cutoff | Nochange live blocks | Nochange requested B | Registry live blocks | Registry requested B |
|---|---:|---:|---:|---:|
| post-init baseline | 10513 | 883655 | 12931 | 1020459 |
| active cycle1 | 10513 | 883655 | 18349 | 1309212 |
| active cycle2 | 10513 | 883655 | 18446 | 1320510 |
| delta baseline→cycle1 | 0 | 0 | +5418 | +288753 |
| **delta cycle1→cycle2** | **0** | **0** | **+97** | **+11298** |

### Residual request-size allocation cohort detail

| Nearest allowlisted GIO function / reason, registry | baseline live/request B | cycle1 live/request B | cycle2 live/request B | cycle2−cycle1 |
|---|---|---|---|---|
| `update_registry_data` (proxy) | 9871 / 584901 | 15192 / 863696 | 15192 / 863696 | **0 blocks / 0 B** |
| `g_win32_package_parser_enum_packages` (proxy) | 2794 / 375420 | 2888 / 389498 | 2986 / 404968 | **+98 / +15470 B** |
| `g_win32_registry_key_watch` (proxy) | 0 / 0 | 1 / 16 | 1 / 16 | 0 |
| `keys_updated` (proxy) | 0 / 0 | 3 / 36 | 3 / 36 | 0 |
| GIO module but none of six exact allowlisted frames | 43 / 2776 | 43 / 2776 | 43 / 2776 | 0 |
| No GIO frame | 223 / 57362 | 222 / 53190 | 221 / 49018 | **−1 / −4172 B** |
| Strict multi-method ambiguous original stack (NOT additional) | 12665 / 960321 | 18081 / 1253210 | 18179 / 1268680 | +98 / +15470 B |

**Important:** the strict multi-method category and nearest allowlisted method are *different views of the same original allocations*, not additive; no double counting. The +15470 B nearest package enum and −4172 B no-GIO counterpart plus unchanged remaining categories reconcile to **+11298 B** total request size.

The nearest `update_registry_data` request size plateaued by the second epoch, while the package enumeration proxy gained +98 blocks. This DOES NOT prove the package parser leaks 98 blocks per scan: one more equal observed step is needed to distinguish intentional cache warming, transient GIO ownership and persistent retention. Original request bytes are NOT process private committed bytes.

### Phase-matched physical resource deltas from SAME continuous ETW CI

| Metric | nochange cycle1 | nochange cycle2 | registry cycle1 | registry cycle2 |
|---|---:|---:|---:|---:|
| PSAPI PrivateUsage B | +45056 | 0 | +405504 | **+40960** |
| VirtualQuery MEM_PRIVATE B | 0 | 0 | 0 | +16384 |
| process handles | +3 | 0 | +3 | +1 |
| CPU user+kernel units 100ns | 0 | 0 | 10000000 | 10000000 |
| completed AppInfo workers | 0 | 0 | 1 | 1 |
| changed callbacks | 0 | 0 | 0 | 0 |

The prior separate **non-ETW** two-cycle candidate CI [#45213046661](https://github.com/taku077/c545d-recorder/actions/runs/45213046661) reported registry PrivateUsage +86016 then +356352 B. **Do not substitute or directly compare its resource deltas**: instrumented ETW is a different run and introduces overhead, but both are valid for their own scope.

### Source review in progress

The official upstream pinned source [GLib 2.82.4 gwin32packageparser.c](https://github.com/GNOME/glib/blob/2.82.4/gio/gwin32packageparser.c) explicitly releases per-package HSTRING, IPackage/IPackage2/IPackageId, and XML arrays at cleanup boundaries. The CI-only DisplayName memoization in [patch_glib_uwp_displayname_cache_diagnostic.py](https://github.com/taku077/c545d-recorder/blob/investigate/c545d-status-only-monitor-20261120/tests/patch_glib_uwp_displayname_cache_diagnostic.py) is guarded by an opt-in diagnostic environment variable; presence of its code alone is NOT evidence of the cache being enabled, and its caches can change freshness semantics. Need distinguish actual parser callback/cache retention from resource initialization by additional source-level counters under one bounded isolated CI comparison; no change to production recorder.

Verified release status: `install_approved=0`, `live_test_authorized=0`, release HOLD, real Windows10 camera recording UNTESTED, no user measurement required.

