# C545D — DisplayName getter-frame allocation origin, 2026-11-24 JST

## Verification

- **Latest real Windows2022 CI: [#45220933192 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45220933192)**, job `137854664260`, native modified GLib/GIO 2.82.4 rebuilt with verified GIO PDB and official GStreamer 1.28.8 2047 exports. Private 256MiB-capped ETW HeapAlloc/ReAlloc/Free, 2M-event ceiling, zero-loss gate, one trace per arm, QPC cutoffs after initialization and each of two comparable active cycles; worker-phase and numeric resource gates passed. No recorder host/RTSP, raw ETL or private source upload.
- **New exact source marker:** `tests/patch_c545d_gio_displayname_frame_ci.py` wraps `IPackage2_get_DisplayName` in a private MSVC noinline function `c545d_ci_displayname_getter_scope` without altering the actual HRESULT, HSTRING or public exports. Original HeapAlloc stacks that contain this exact PDB-matched GIO frame inherit a Boolean source tag across ReAlloc and Free. It is a synchronous getter callsite marker, NOT proof of direct OS allocator ownership.

## Original heap retained at each process-local QPC cutoff

| Original source, live blocks / request bytes | baseline | cycle1 | cycle2 | cycle2 minus cycle1 |
|---|---:|---:|---:|---:|
| nochange getter-marked | 889 / 128256 | 889 / 128256 | 889 / 128256 | **0 / 0** |
| registry getter-marked | 812 / 147108 | 877 / 156912 | 941 / 162544 | **+64 / +5632** |
| nochange nearest-package proxy | 2845 / 368375 | 2845 / 368375 | 2845 / 368375 | **0 / 0** |
| registry nearest-package proxy | 2802 / 392544 | 2896 / 406622 | 2992 / 417808 | **+96 / +11186** |
| nochange entire tracked heap | 11026 / 914240 | 11026 / 914240 | 11026 / 914240 | **0 / 0** |
| registry entire tracked heap | 9996 / 850365 | 18352 / 1321820 | 18448 / 1333006 | **+96 / +11186** |

All tagged getter originals are a **subset** of the nearest `g_win32_package_parser_enum_packages` proxy, checked at every cutoff. In the second registry epoch, of the 96 extra blocks / 11186 bytes in the package proxy, **64 blocks / 5632 bytes** have the exact noinline getter callsite frame, and the remaining **32 blocks / 5554 bytes** do not. These must NEVER be added a second time. Exact marker was exercised for **19754 raw original HeapAlloc stack hits in nochange** and **39811 registry**, with both symbol matches and phase accounting PASS.

Same modified/ETW-instrumented CI, second epoch PSAPI PrivateUsage **+20480 bytes** registry, handles **0**, VM MEM_PRIVATE **0**, user+kernel CPU time **7656250×100ns**, one completed AppInfo worker; nochange second-epoch PrivateUsage **0**, handles **0**, CPU **0**. The request bytes are not process commitment; two cycles do not establish an unbounded leak rate. The GAppInfoMonitor `changed` signal is disabled by the CI-only worker-fire opt-in variable in this run.

Previous independent no-getter-marker [#45217120186 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45217120186) found registry epoch2 nearest package +98/+15470B and tracked total +97/+11298B. Do not compare the exact magnitudes as an improvement; the code instrumentation, runs and heap layout differ. The *source cohort* increase is reproducible, not a certified leak slope.

## Historical ablation and source-grounded remaining gap

Official [GNOME GLib 2.82.4 gwin32packageparser.c](https://github.com/GNOME/glib/blob/2.82.4/gio/gwin32packageparser.c) releases the per-package HSTRING and COM/manifest objects at cleanup. Earlier [#44910338100 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44910338100) already reanalyzed independent 16-cycle WinRT ablations: 190/194/196 byte-bin effects persisted through no-op callback, disabled XML/path/location and even immediate HSTRING discard, but were absent when the DisplayName getter itself was disabled/cached. Those OLD 16-cycle size buckets are related context, **not proof** the new +64 getter-tagged originals are never freed. Do not rerun old ablation/4h host tests.

Initial [#45220366114 FAILURE](https://github.com/taku077/c545d-recorder/actions/runs/45220366114) was caused by an exact source-anchor one-space mismatch with the composed bridge patch; fixed [591412a8](https://github.com/taku077/c545d-recorder/commit/591412a8a8e5483520b67ec5fffbfadc0efa0fba), fast preflight [#45220794422 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45220794422), then full #45220933192 SUCCESS. Do not retry already resolved source anchor.

**Next AI-only:** reuse saved historical WinRT/256-cycle data and examine native getter-related ownership/COM cache outside the synchronous call frame; compare exact QPC cuts and original allocations, then consider one bounded integrated automatic follow-up only if existing data cannot distinguish transient warmup from persistent retention. Any proposed fix must preserve current package/locale DisplayName freshness and MSVC ABI, not merely hide allocation behind a permanent cached string. Four release evidence gaps remain: `install_approved=0`, `live_test_authorized=0`, release HOLD, real Windows10 C545D recorder and two-camera audio/MP4/24×365 stability UNTESTED. No user action.