# 2026-11-20 — Windows DisplayName retention: ABI vs projection vs COM lifetime (CI ONLY)

This note records **independent Windows CI experiments and offline reanalysis of already saved numeric artifacts**, not data from the user's Windows 10 recording PC. No credentials, package names, paths, videos, RTSP URLs, or raw ETL logs were captured or published. Do not install any diagnostic DLL/EXE into the recorder.

## Test conditions and proven boundaries

- Child draft [PR #59](https://github.com/taku077/c545d-recorder/pull/59) of current experimental [PR #57](https://github.com/taku077/c545d-recorder/pull/57). Source: `tests/winrt_displayname_abi_vs_projection.cpp`, `tests/analyze_winrt_abi_displayname.py` and matrix workflow `.github/workflows/c545d-winrt-abi-displayname-ci.yml`.
- [Exact Windows 2022 + 2025 matrix #44717337044 — **SUCCESS**](https://github.com/taku077/c545d-recorder/actions/runs/44717337044); tested source SHA `a5d26ef19a3044b0f2aa3733ca4517c1745bfcce`. All seven modes: control, projected, raw, per-scan-fresh control, per-scan-fresh raw, per-scan **new MTA thread** control, per-scan new MTA thread raw; 128 cycles per mode, 0/32/64/96/128 samples. **All HSTRINGs explicitly deleted** for raw modes and COM objects destructed by RAII; each temporary worker balances WinRT MTA initialization/termination. HeapWalk errors0, WinRT API errors0, handle difference0. Exactly 32 packages on Windows 2022; 51 on Windows 2025. Numeric artifacts **14619883300** (2022) and **14619758029** (2025).
- The projected control calls `Package.DisplayName()`; the raw ABI calls `ABI::Windows::ApplicationModel::IPackage2::get_DisplayName(HSTRING*)` and `WindowsDeleteString`, corresponding to the getter interface in GLib 2.82.4. The pure control enumerates the same packages and reads only `Package.Id().FullName()`. In both per-scan-fresh and per-thread comparisons, the identity-only control is also reconstructed in the same way.
- The reported figures are **treatment growth minus matched control growth in separate processes on the same OS runner**, not an assertion that Windows is definitively leaking or that user-host memory would behave identically.

## Same-run 128-cycle matched-control deltas

| Metric / mode | Windows 2022 | Windows 2025 |
|---|---:|---:|
| PrivateUsage — projected DisplayName | +1,921,024 B | +2,437,120 B |
| PrivateUsage — raw ABI DisplayName, persistent manager | +1,994,752 B | +2,306,048 B |
| PrivateUsage — raw ABI, fresh manager per scan | +1,904,640 B | +2,428,928 B |
| **PrivateUsage — raw ABI, fresh MTA apartment/thread per scan** | **+1,867,776 B** | **+2,338,816 B** |
| HeapWalk BUSY — projected DisplayName | +1,423,464 B | +1,727,336 B |
| HeapWalk BUSY — raw persistent | +1,435,980 B | +1,718,992 B |
| HeapWalk BUSY — raw fresh manager | +1,423,464 B | +1,723,164 B |
| **HeapWalk BUSY — raw fresh MTA/thread** | **+1,427,636 B** | **+1,727,336 B** |
| BUSY block count — raw fresh MTA/thread | +12,287 | +16,894 |
| Handles — all four DisplayName modes after matching | 0 | 0 |
| **Last 64 cycles** PrivateUsage — raw fresh MTA/thread | **+888,832 B** | **+1,200,128 B** |

**Observed:** raw ABI, correctly deleted HSTRING, short-lived PackageManager, and balanced short-lived MTA apartment are EACH insufficient to remove the 128-cycle numeric increase. The C++/WinRT language projection alone is not an adequate explanation. Since the last64 interval also grows, this direct API test has not shown a plateau by 128 cycles.

**NOT proven:** a specific defective Windows allocation stack, indefinitely unbounded growth, identity with the upstream Microsoft issue, or causality for real 24×365 Tapo recording PrivateUsage. Standard COM and HSTRING cleanup must be retained. Never force-close COM/OS handles or modify the user's Windows registry to address this.

## Related Microsoft report (not automatically the same bug)

Microsoft [WindowsAppSDK #3789](https://github.com/microsoft/WindowsAppSDK/issues/3789) documents a WinRT `PublisherDisplayName` HSTRING-handling leak. A Microsoft contributor stated in August 2023 the root cause was identified and in June 2024 described a fix planned for a Windows Update. Our measured API is **`Package.DisplayName`**, not `PublisherDisplayName`; the relationship and patch availability across Windows 10/Server versions remain unverified. Official ABI interop and resource cleanup: https://learn.microsoft.com/en-us/windows/apps/develop/cpp-winrt/interop-winrt-abi and https://learn.microsoft.com/en-us/windows/win32/api/roapi/nf-roapi-rouninitialize .

## Offline reanalysis: THREE PRE-EXISTING 256-cycle exact-string-cache Windows A/B runs

Without re-running any Windows 256-/384-/512-cycle CI or requesting a new user measurement, the numeric-only artifacts of three previous matched no-registry-change/registry-change runs were downloaded and reanalyzed:

| Existing Windows 2022 CI | PrivateUsage last128, default | PrivateUsage last128, exact cache | BUSY last128, default | BUSY last128, exact cache |
|---|---:|---:|---:|---:|
| [#44533452892](https://github.com/taku077/c545d-recorder/actions/runs/44533452892) artifact14535369324 | +819,200 B | +176,128 B | +611,752 B | +41,236 B |
| [#44537371920](https://github.com/taku077/c545d-recorder/actions/runs/44537371920) artifact14537548552 | +1,024,000 B | +151,552 B | +731,920 B | +13,320 B |
| [#44545844200](https://github.com/taku077/c545d-recorder/actions/runs/44545844200) artifact14543445471 | +1,069,056 B | +172,032 B | +613,728 B | +37,064 B |

The cache reduced late control-subtracted PrivateUsage by **78.50% / 85.20% / 83.91%** and HeapWalk BUSY by **93.26% / 98.18% / 93.96%**, respectively; **cache nochange hits0/misses32 and cache registry hits8224/misses32/entries32** in all three runs. This is compelling mitigation evidence but **the residual stays positive and no zero-leak/plateau guarantee is established**.

Additional offline examination of the saved `GIO_HEAPSIZE` numeric histogram: the uncached synthetic-registry case has **exact sizes 190, 194 and 196 bytes each +384 BUSY blocks** over the last128 control-subtracted cycles, repeated in all three runs; the cached case removes these three repeating bins. Cached-run residual has reproducible positive last128 bins: size24 +42 blocks, size28 +13, size360 +8, size736 +3, size912 +2, size1936 +3 across all three runs. These are **object-size correlations only**, not allocation stack/function attribution. In the `>=2048` overflow bin the displayed size is a lower-bound bucket, not an exact allocation size. Neither residual allocated bytes nor PrivateUsage can be inferred just by multiplying the histogram counts.

## Existing 384-cycle GLib plateau *evidence*, but not proof of infinite stability

[Windows-2022 VM class CI #44588492110](https://github.com/taku077/c545d-recorder/actions/runs/44588492110), artifact14564212196, used combined GLib weakref/UTF16 on matched nochange vs synthetic registry-change runs (not the above current real-MSIX cache). Control-subtracted PrivateUsage first128 **+1,466,368 B**; last256 **+49,152 B**; last128 **−81,920 B**. The late decline supports *possible short-run settling in this specific workload*, but unlike the standalone direct getter test, the GLib worker, process/apartment lifetimes, and graph rebuild schedules differ. It cannot be extrapolated to real Tapo RTSP 24x7 or eliminate any positive slope under different load.

## Engineering conclusion / next AI-only work

1. **Avoid repeatedly calling raw WinRT DisplayName when the package+locale epoch has NOT changed**, using an exact owned-value cache, strict bounded capacity, real PackageCatalog generation + caller UI language invalidation and race/failure protections. The isolated diagnostic implementation is already tracked in PR #57 with successful actual signed-MSIX, eight-thread/one-shot failure recovery and official SDK dual video/audio MP4 EOS checks. It is still **NOT production/release qualified**, especially true package-update same-count DisplayName parity, spontaneous AppInfo monitor signaling, shutdown races and Windows10 deployment.
2. Investigate the stable cached residual size bins with **source-level/CI-only** allocation owner attribution or shorter deterministic comparisons, using these three saved artifacts first; do not request new WPR/UMDH or user 4-hour tests. Remaining positives might be allocator retention or other source allocations, not necessarily permanent leaks.
3. Before any host test, build a separate fail-closed release candidate preserving stream1(left), stream6(right), 2560×720@15fps, x264 medium QP24, AAC mono48k192kbps goal, splitmux/EOS and safe shutdown, verify ABI and **dual-media integration**. If Windows10 is indispensable, offer **one consolidated, automated host check** with numeric-only output, no in-place DLL replacement, and never disturb the running recorder.

**Current decision: no Windows10/Tapo recorder deployment or extra user measurement.** The direct test is diagnostic and the Windows-side retained-allocation mechanism cannot be fixed solely by changing C++/WinRT projection, HSTRING release, manager, or thread apartment lifetime.
