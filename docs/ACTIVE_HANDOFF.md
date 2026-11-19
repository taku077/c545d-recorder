# C545D — ACTIVE DEVELOPMENT HANDOFF (AUTO-GENERATED)

**Read this before the old main-branch HANDOFF_CURRENT.** The experiment branch is not installed on the user's recording PC.

- **Active PR:** [#54](https://github.com/taku077/c545d-recorder/pull/54) / state `open`
- **Exact branch HEAD:** `investigate/gio-2824-key-handle-lifecycle` / `2f10b4e8645cf4397f1ae822ee1a29162da356e2`
- **PR updated at (UTC):** `2026-11-19T07:20:18Z`
- **Verified snapshot source:** [HANDOFF_CURRENT.md at that commit](https://github.com/taku077/c545d-recorder/blob/2f10b4e8645cf4397f1ae822ee1a29162da356e2/docs/HANDOFF_CURRENT.md)

## CI runs at exactly this HEAD

| Workflow | Outcome | Evidence |
|---|---|---|
| GLib 2.82.4 experimental AppInfo rescan isolation | in_progress | [#44478842494](https://github.com/taku077/c545d-recorder/actions/runs/44478842494) |
| C545D isolate GLib 2.82.4 AppInfo ownership candidate | in_progress | [#44478842441](https://github.com/taku077/c545d-recorder/actions/runs/44478842441) |
| C545D GIO AppInfo camera-free short Key-handle probe | in_progress | [#44478842359](https://github.com/taku077/c545d-recorder/actions/runs/44478842359) |
| Windows PowerShell source validation | in_progress | [#44478842357](https://github.com/taku077/c545d-recorder/actions/runs/44478842357) |
| C545D GLib 2.82.4 weak-backref ownership A/B | in_progress | [#44478842334](https://github.com/taku077/c545d-recorder/actions/runs/44478842334) |
| C545D active development handoff auto-refresh | in_progress | [#44478836258](https://github.com/taku077/c545d-recorder/actions/runs/44478836258) |

## Current development findings from the active PR

### UPDATE 2026-11-19 JST — 64-cycle handle-type census narrowed; native/Handle64 timing consistency gate added

- Active development: PR #54 https://github.com/taku077/c545d-recorder/pull/54 . **No recording PC modification, no release DLL deployment, no new user-side recording/ETL or manual test.** Always compare this handoff SHA with live PR HEAD and **both pass and fail CI**.
- Strong preserved result (Windows runner, not real recorder): weakref + redundant UTF-16 path copy removal reduced 64-cycle PrivateUsage +39,497,728 B (weakref only) to +1,466,368 B (combined), **96.29% reduction**. Earlier baseline 16 synthetic registry changes leaked +5,152 total handles; combined had 0. Official GStreamer 1.28.8 SDK-linked MSVC GIO candidate run #44376017336 PASSED export parity (2047 vs 2047, missing 0) plus real candidate DLL loader/basic GAppInfo API. Full app/GStreamer concurrency and production safety remain UNVERIFIED.
- **New decisive Handle64 type evidence** from camera-free run [#44378212869](https://github.com/taku077/c545d-recorder/actions/runs/44378212869): in both weakref-only and combined conditions, Handle64 Key count **435 baseline -> 435 just before deleting disposable registry value after 64 mutations**. Other handle classes increased at most +1 (Event, Section, Thread). No hundreds of hidden other-type handles. However AFTER deletion, Handle64 type sum dropped from 686 to 365 (Key 435 to 114), whereas a GetProcessHandleCount sample just before Handle64 still showed **683**; do not treat these asynchronous/inconsistent samples as a stable whole-process total or conclusively claim Key-handle deletion under production workload.
- A second full type CI [#44378692427](https://github.com/taku077/c545d-recorder/actions/runs/44378692427) passed the new sanitized *type growth* analyzer and its masked Event-vs-Key-growth selftest, but its **overall CI failed** because older native total count gate found +5 handles against limit +/-4. This is not a demonstrated new Key leak. Do NOT loosen the whole-process gate without evidence.
- New code in tests/gio_appinfo_key_handle_probe.c adds (a) three-phase summary of all kernel-object **type names/counts only** from official Handle64 (never raw handle names, paths or ETL), (b) bracketing GetProcessHandleCount samples just before/after Handle64 invocation, and (c) a delayed settled_cleanup checkpoint. New tests/analyze_gio_handle_types.py validates sums/Key consistency/native timing and detects masked per-type positive growth. The version with native-bracket/settled gate is at commits **56dda788** and **12e6c2e1**; Windows CI started at #44380292724 and is not yet confirmed PASS at this writing.
- **Existing memory artifact reanalysis** #44375471946: combined candidate after 64 cycles + final cleanup PrivateUsage **5,095,424 -> 6,533,120 B** (+1,437,696 B) but HeapWalk BUSY **1,493,746 -> 1,221,425 B** (-272,321 B). Windows PrivateUsage is process private commit; HeapWalk BUSY is narrower. Thus these readings do **not** prove the remaining ~1.37 MiB is live heap leakage; allocator retention or other commit sources remain plausible. No plateau proof yet. Reference: https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex
- **Next work (AI/CI only)**: inspect latest exact-HEAD and later Windows CI artifacts for bracketing native-before/native-after total vs Handle64 total, and settled_cleanup, decide scientifically whether this is an asynchronous rescan, incomplete Handle64 enumeration, or genuine handle growth. Repair measurement/gates without weakening safety. Afterward differentiate residual private commit vs live allocations and verify full GStreamer pipeline/API, thread, dependency compatibility before any on-host deployment.

### UPDATE 2026-11-19 JST — MSVC SDK-linked GIO runtime smoke SUCCESS, Key-handle census pending

- Active development PR: https://github.com/taku077/c545d-recorder/pull/54 . This is NOT a recorder release; no user PC DLL or recording config modified.
- Confirmed [Windows-2022 MSVC CI #44376017336](https://github.com/taku077/c545d-recorder/actions/runs/44376017336) SUCCESS: combined GWeakRef+UTF16 GLib 2.82.4 source patch builds with MSVC x64. Official GStreamer 1.28.8 SDK exports=2047, candidate exports=2047, missing=0. Both original and patched GIO now depend on **z-1.dll**, with no candidate-only DLL imports. SDK-linked C test loaded the candidate DLL by actual path and executed basic GAppInfo API. Full multi-threaded ABI and recorder pipeline still unverified.
- Cause of previous 0xC0000135: fallback z.dll in candidate vs official SDK z-1.dll. CI now installs SDK BEFORE GLib Meson configuration and supplies SDK LIB/INCLUDE/PKG_CONFIG_PATH/CMAKE_PREFIX_PATH/PATH; SDK contains z.lib, zlib.pc and zlib.h. No unsafe DLL renaming or host replacement.
- Preserved prior camera-free CI evidence: weakref-only 64-cycle PrivateUsage +39,497,728B versus combined +1,466,368B, **96.29% reduction**. 16-cycle baseline total handles +5,152 vs combined 0. Earlier same-run HeapWalk BUSY deltas weakref-only +32,632,218B versus combined +272,214B, positive residual requiring classification. These are not user recording-PC results.
- Key handle type census newly uses read-only official Microsoft Handle64 -s -p in isolated Windows CI and stores only numeric GIO_KEY baseline/end counts; strict total handle gate stays in effect. Earlier runs stopped due to missing unzip or Key type summary parsing; fixes committed. **Latest 64-cycle Key-specific CI must be checked before claiming PASS**.
- Next: await/review latest Key-specific CI result and artifacts, isolate remaining live allocations, expand retained GAppInfo/thread tests and GStreamer two-stream synthetic media compatibility before any production release. No user 4-hour capture, repeated WPA/UMDH, or manual investigation requested.


### UPDATE 2026-11-19 JST — continued after 96.29% result: MSVC export parity PASS, runtime blocker and type-specific handle gate in CI

- **Active PR #54 remains on this branch**. Previous 64-cycle camera-free Windows runner result: weakref-only PrivateUsage +39,497,728B versus combined weakref+UTF16 +1,466,368B (**96.29% reduction**); 16-cycle baseline +5,152 handles versus combined 0; combined 64 cycles +2 handles. **No user machine, recorder, or production DLL has been changed**.
- New investigation of prior failing run [#44366839862](https://github.com/taku077/c545d-recorder/actions/runs/44366839862): total handles +7 under weakref-only, +2 under combined. The saved Windows \`HeapWalk\` data show BUSY heap deltas weakref-only **+32,632,218B** versus combined **+272,214B**; combined PrivateUsage delta in that same run **+1,540,096B**. Live BUSY bytes are not PrivateUsage. Residual heap growth and whether it plateaus remain **unresolved**, and +7 total handles are not independently proven to be Key handles.
- MSVC ABI diff run [#44366839819](https://github.com/taku077/c545d-recorder/actions/runs/44366839819) revealed exactly one official GStreamer 1.28.8 SDK export absent in the source-built DLL: \`_g_io_modules_ensure_extension_points_registered\` (GIO private routine already defined in GLib source). New \`tests/patch_glib_msvc_gio_sdk_export.py\` exports the **real existing function** using the MSVC-only GIO link configuration; no dummy function. This produced [#44372463416](https://github.com/taku077/c545d-recorder/actions/runs/44372463416) **SUCCESS**, official SDK exports 2047, candidate 2047, missing 0. This verifies the subset of exports, **not entire ABI/runtime compatibility**.
- Stronger test \`tests/gio_msvc_sdk_overlay_smoke.c\` is compiled using the OFFICIAL SDK import libraries and deliberately runs in an isolated directory with candidate GIO. [#44373607049](https://github.com/taku077/c545d-recorder/actions/runs/44373607049): compile and link succeeded but candidate load failed \`0xC0000135\` (missing dependent DLL). A new workflow diagnostic compares candidate versus official SDK DLL imports to identify the specific missing dependency; results must be inspected before changing dependencies or deploying. Another MSVC run [#44373550401](https://github.com/taku077/c545d-recorder/actions/runs/44373550401) failed in upstream zlib fallback download due to SHA256 mismatch, an **independent CI dependency problem**, not evidence of a GIO patch regression.
- New CI-only \`GIO_KEY\` counters use Microsoft's read-only Sysinternals Handle64 \`-s -p\` for only the candidate process, to distinguish small total-handle variation from retained Key growth. First attempt [#44373277646](https://github.com/taku077/c545d-recorder/actions/runs/44373277646) stopped at runner setup (\`unzip: command not found\`); \`unzip\` was explicitly added to the MSYS2 package list. Keep the existing strict total-handle gate until measured Key counts justify a scientifically grounded change; do not silently dismiss +7.
- **Next engineer-only checks:** read the newest same-HEAD (or later) CI logs/artifacts for the DLL dependency inventory, SDK overlay smoke and Key census; fix root causes in disposable Windows runners, then test native GStreamer pipeline and concurrency/ABI before any release. **No host 4-hour test, WPR/UMDH repetition, recorder restart or manual investigation requested.**


### UPDATE 2026-11-19 JST — Combined weak-reference + UTF-16 path ownership fix passes 16/64-cycle A/B

- GitHub Actions run **44363594321** SUCCESS (isolated Windows-2022/MSYS2, GLib 2.82.4 source build), PR #54: https://github.com/taku077/c545d-recorder/actions/runs/44363594321
- Three conditions tested in one CI run: **unmodified** (16 registry changes: +5,152 total handles / +23,187,456 bytes PrivateUsage), **weakref-only** (16 changes: 0 total handle growth, +10,084,352 private bytes; 64 changes: +2 handles, +39,497,728 bytes), and **weakref + UTF-16 constructor ownership** (16 changes: 0 handles, +532,480 bytes; 64 changes: +2 handles, +1,466,368 bytes). The combined patch reduces residual 64-cycle PrivateUsage increase by **96.29%**, without increasing handles.
- Additional source-specific patch script: `tests/patch_glib_registry_owned_path.py` targets `gio/gwin32registrykey.c::g_win32_registry_key_new_w()`; pointer-prop setter already calls `g_wcsdup()` (owned copy), but caller unnecessarily also passed `g_wcsdup(path,-1)` into `g_initable_new()` and leaked that intermediate allocation. Combined candidate now fixes two distinct bugs: strong-reference cycles (Key handles) and this duplicated UTF-16 allocation (PrivateUsage).
- Retained `GAppInfo` name/exe + public filetype/URL association API regression PASS for combined patch, no-GIO-registry-change control stable. GLib GObject live instance counts under combined candidate stable between initial and 64 cycles: Application 123→123, Handler 390→390, ShellVerb 680→680, RegistryKey 384→385 (a small bounded process-global change), FileExtension 383→383, URLSchema 49→49. The 64-cycle net handles +2 is not the original repeating +322 Key-per-cycle.
- Source audit shows redundant UTF-16 copy remains in GLib 2.82.4, 2.86.4 and 2.88.3 at the time checked; blind upgrade is not sufficient.
- **Remaining**: combined patch still has ~1.40 MiB PrivateUsage increase over 64 cycles (not proven plateau). Distinguish live heap allocation vs allocator holding memory. Verify MSVC-built GLib from the exact GStreamer 1.28.8 SDK and further lifetime/thread/API tests **before any recorder DLL deployment**. No live recorder/PC changes and no user manual or multihour test requested.
- Latest run artifact: `c545d-glib-2824-weak-backref-ab` with `utf16_memory_comparison.csv`, `gobject_live_types.csv`, `ownedpath_registry_64.log` and `registry_utf16_ownership.diff`.



### UPDATE 2026-11-19 JST — Weak-reference AppInfo ownership patch BUILT and A/B tested

- New source-specific patch script: `tests/patch_glib_appinfo_weak_backrefs.py`. Changes `GWin32AppInfoShellVerb->app` from owning pointer to `GWeakRef`, initializes/clears it, uses `g_weak_ref_get()` to acquire strong lifetime protection in public lookups, and avoids disposing retained app objects. Checks exact GLib 2.82.4 source signatures, preserves source newline convention. **This is a candidate, not a released replacement DLL.**
- CI `C545D GLib 2.82.4 weak-backref ownership A/B`, run **44353261870** SUCCESS: untouched GLib 2.82.4 16 reg changes **+5,152 handles**, **+23,433,216 Private Bytes**; patched same source **0 handles**, **+10,125,312 Private Bytes**; no-registry-change controls 0 handles in both; retained GAppInfo basic check PASS. Artifact `c545d-glib-2824-weak-backref-ab` includes before/after numerical CSV and source diff.
- **Key fix candidate supported on CI; remaining Private Memory growth is not fixed.** Older additional CI had `HeapSummary` allocated bytes ~+8.1MB per 16 cycles even when Key counts plateaued. UWP-skip explained only ~8% of Private Memory growth, so cannot dismiss remaining memory as allocator cache or solve by disabling UWP.
- New tests `tests/gio_appinfo_public_api_regression.c` and workflow `.github/workflows/c545d-gio-weak-backref-ci.yml` include 8-cycle public API checks and patched 64-cycle handle/memory measurement, GitHub Actions execution launched. Consult its finalized result before claiming strong functional correctness or 64-cycle stability.
- **Next engineering action**: isolate remaining live allocations automatically on Windows runner, using existing short scans and heap accounting, then address them without disabling legitimate AppInfo notifications. After that, compile with the MSVC-compatible SDK matching the user's GStreamer 1.28.8. No user action, new 4h recording, forced `RegCloseKey`, or registry change on user's PC.
- No production change or release made; investigate branch stays separate in draft PR #54.



### UPDATE: Two successful camera-free CI runs (2026-11-19 JST)

- Run #44331665421: 16 synthetic-registry-change cycles on exact GIO **2.82.4.0**, process total handles **700→5853**, Private Bytes **5,533,696→28,913,664**; Handle64 reports overwhelmingly Key increase.
- Run #44332409627: decisive **16-cycle control with NO registry changes**: total handles **698→698**, Private Bytes **5,918,720→5,918,720**. With one disposable HKCU RegisteredApplications value modified per cycle: total handles **696→5848** (+5,152 after cleanup), Private Bytes **5,484,544→28,377,088**. Growth ~322 handles per cycle; Handle64 post-init Key **434→5585** (+5,151). GAppInfoMonitor changed callback=0, so do not claim this callback necessarily caused growth; test comparison demonstrates a registry-change-dependent resource leak.
- Host observed +428 per event = 214×2; CI +322 ≈161×2. Per-registration two handles per rebuild is plausible, **not a proven object cardinality** for CI.
- Results are sanitized and recorded in `docs/GIO_2824_KEY_HANDLE_INVESTIGATION.md`. CI source `tests/gio_appinfo_key_handle_probe.c`, workflow `.github/workflows/c545d-gio-key-probe.yml`, PR #54. Still no native GIO patched DLL, no real PC modification.
- **Next engineer-side**: implement narrowed GLib reference-lifetime patch in CI isolated build, prove live Key plateau in this reproducible short synthetic test, and preserve GAppInfo functional semantics. No additional user WPR / 4h measurement for now.

### UPDATE: 2026-11-19 JST — Controlled 16/64-cycle leak elimination results

- Exact GLib 2.82.4 built from source on isolated Windows CI. Experimental forced-dispose source patch built and run in PR #54; run **44347320582** SUCCESS: unmodified 16 registry changes +5,152 total live handles / +23,080,960 Private bytes; experimental patch 0 live handle growth / +10,043,392 Private bytes. The no-registry-change control has 0 handle increase in both conditions. Retained GAppInfo name/executable basic check PASS.
- Additional patched 64-cycle stress run **44348683100** SUCCESS: 678 baseline→679 after cleanup handles (within normal small variation); Private bytes 6,107,136→45,166,592 (+39,059,456). First 16-cycle Private bytes delta 9,388,032; last 16-cycle delta 9,129,984: **remaining linear-ish Private Bytes growth not fixed**.
- All evidence / source and CI commands now in `docs/GIO_2824_KEY_HANDLE_INVESTIGATION.md`, `tests/patch_glib_appinfo_experiment.py`, `tests/gio_appinfo_key_handle_probe.c`, `tests/gio_appinfo_retained_lifetime.c`, `.github/workflows/c545d-gio-ownership-experiment.yml`. No user operation required so far. No recorder production changes.
- **Hard safety constraint**: diagnostic `g_object_run_dispose()` on old app nodes is NOT production-ready due externally retained objects. **Must implement a safe ownership/lifetime fix and distinguish true remaining allocations from allocator caching** before a release. Do not repeat 4-hour host recording; design isolated CI tests first.
- Confirmed `g_win32_registry_value_iter_get_data_w()` returns borrowed iterator-owned storage (transfer none): do not free pointer manually. Avoid inventing a fix based on that line.

## CURRENT 2026-11-19 JST — GIO 2.82.4 source-level leak candidate and zero-user-effort CI gate

- User's instruction: Do all source inspection, existing-data analysis, CI and automated checks **before** any fresh user-side work. Manual checks only when technically necessary; do not request serial 4-hour experiments. If a host-only test eventually remains necessary, aggregate all required metrics into **one** automated capture and analyze before proposing any further run.
- Investigation draft PR #54: https://github.com/taku077/c545d-recorder/pull/54 on branch `investigate/gio-2824-key-handle-lifecycle`; no production recorder edits or release.
- Investigation note: `docs/GIO_2824_KEY_HANDLE_INVESTIGATION.md`. 4-hour measured +3424 Key, 214 registry names duplicated 79 times, WPA creating stack rooted in GLib/GIO. Key creation **events** are not outstanding handles.
- New source-level finding (tag GLib 2.82.4): `Application->verbs` owns `ShellVerb` and `ShellVerb->app` owns `Application` (strong reference cycle); some fake-app paths additionally create `Application->Handler->ShellVerb->Application` cycle; Handler holds GWin32RegistryKey. This is a promising leak mechanism but **not** confirmed as the exact source of the host's periodic +428 live Key handles.
- Added camera-free 16-cycle Windows CI prototype: `tests/gio_appinfo_key_handle_probe.c` with `.github/workflows/c545d-gio-key-probe.yml`. It uses a disposable runner HKCU value, queries GAppInfo, and measures total process handles/Private Bytes and Key counts using Microsoft's Handle. Tests and ownership change must not use camera credentials or modify the actual user recorder.
- Source-level inspection of GLib 2.82.4 vs 2.88.3 shows the key AppInfo reference edges persist, so blind version upgrade is not a demonstrated solution.
- **Next**: Inspect CI outcome, correct any build/test harness errors, determine whether real rescan was triggered (`GAppInfoMonitor::changed` events). If reproducible, implement **narrow** ownership/lifetime fix with regression tests in isolation. If not reproducible, document status and only then consider a single minimal on-host automated discriminator; no repeat 4-hour monitor.
- Preserve CPU-stable recorder baseline, no forced handle closing, no GIO DLL swapping into an active process, no privileged tool instructions to user.

## Resume rules (fail closed)

1. Compare the HEAD above against the current live PR HEAD; if different, re-read the live PR before using this snapshot.
2. Verify both success and **latest failed** CI jobs; do not quietly regress to an earlier successful run.
3. The 96.29% PrivateUsage improvement and zero handle delta in 16 cycles were **camera-free CI** results, not real-PC improvements.
4. Do not deploy unverified DLLs, restart the active recorder, run new multi-hour host tests, or re-request completed WPA/ETL work.
5. To switch projects or active PR, deliberately update ACTIVE_HANDOFF_CONFIG.json.

This file is generated by tools/refresh_active_handoff.py, using API reads and the selected PR's existing public handoff.
