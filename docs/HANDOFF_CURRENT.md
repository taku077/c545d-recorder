# HANDOFF_CURRENT — C545D recorder

<!-- CURRENT_HANDOFF_START: update this block, not only append to the archive -->

### UPDATE 2026-11-20 JST — Independent WinRT DisplayName 128-cycle linear growth and Microsoft issue

- **EXISTING CI, no rerun:** [independent Windows-2022 C++/WinRT getter #44579422716](https://github.com/taku077/c545d-recorder/actions/runs/44579422716), artifact `14558426676` downloaded; same tested source file `tests/winrt_displayname_direct_repro.cpp` SHA `bc9a37f9dbdd86e29f26def5186547902719bca9` in both PR #54 and this experiment branch. No GLib, GStreamer, recorder or cameras. It enumerates **32 packages**, with 8 warmup enumerations and 128 measured cycles, snapshots every 32 cycles. Comparing DisplayName versus ID-only control, **private commit delta +1,888,256 B**, **HeapWalk BUSY delta +1,427,636 B**, **BUSY blocks delta +12,287**; **handles delta 0**. DisplayName arm per32 BUSY increment: **+366,220; +353,780; +362,124; +353,780 B**; BUSY blocks **+3074; +3071; +3073; +3071**. Very regular growth through final window, so short warmup alone does not account for it; however exact ownership and longer-term release remain UNPROVEN.
- **External corroboration, not exact same API**: [microsoft/WindowsAppSDK issue #3789](https://github.com/microsoft/WindowsAppSDK/issues/3789) reports memory leak with `PublisherDisplayName()` and `InstalledLocation().Path()` under Windows 10 21H1. Microsoft staff identified an **HSTRING handling error for PublisherDisplayName** in Aug 2023; announced resolution in an unspecified upcoming Windows update in Jun 2024. The issue discusses `PublisherDisplayName`, while our project directly reproduced `DisplayName`: DO NOT assume identical root or that user's Windows 10 build has the fix. Related [microsoft/windows-rs issue #2601](https://github.com/microsoft/windows-rs/issues/2601) confirms both Rust and C++/WinRT reproductions. These support investigating Windows Runtime internals rather than attributing all residual allocation to GStreamer.
- **New isolated 2025-OS comparator**: committed workflow `.github/workflows/c545d-winrt-displayname-os2025-ci.yml` as `09deb38fd7b9eb4023e521e0b9c25b97c91b41c3` on this branch, [CI #44590830433](https://github.com/taku077/c545d-recorder/actions/runs/44590830433) **IN PROGRESS when checked**. It compiles and runs exactly the same independent 128-cycle getter-only source and analyzer on GitHub `windows-2025`, paired with its own ID-only control, captures numeric-only samples and OS build version. Does NOT rerun the Windows 2022 baseline or touch the real Windows 10 recording PC. A different OS-runner result is evidence of OS dependence only, NOT direct Windows10 patch applicability.
- **Parallel outstanding:** [MEM_PRIVATE size buckets 384-cycle Windows #44588492110](https://github.com/taku077/c545d-recorder/actions/runs/44588492110) still IN PROGRESS at this checkpoint (paired nochange/registry test). Synthetic bucketing CI #44589568374 passed 9/9; do not rerun a completed long test, and obtain actual numeric artifacts before concluding.
- **Next work:** Retrieve both pending CI results, compare 128-cycle direct getter memory slopes and 384-cycle private region size bins; determine whether alternative cache invalidation can preserve DisplayName update and localization without repeated leaking getter calls. No release of stale-cache diagnostic or any modified DLL on the recorder. Existing two-stream 2560×720 @15fps, x264 medium QP24 and AAC mono 48k settings unchanged.



### UPDATE 2026-11-20 JST — VM region-size 384 analysis selftests 9/9 PASS

- **Latest short CI:** [VM bucket analyzer unit run #44589568374](https://github.com/taku077/c545d-recorder/actions/runs/44589568374) **SUCCESS (9/9 Python synthetic tests)**. Newly added `tests/test_analyze_gio_vm_private_buckets.py` commit `bc2c572c5f9d6b54d8de22d43468ab716abca54d`; independent short Linux workflow `.github/workflows/c545d-gio-vm-buckets-unit-ci.yml` commit `6a400b23957c5526ca29930404e11a3877ea71e7`. Tests: paired control subtraction, per-bucket sum check, duplicate and missing checkpoints, VM census errors, invalid numeric values, positive retained handles, missing completion, and wrong registry mode. No camera/registry/user recorder execution.
- **Actual Windows-2022 384-cycle run:** [#44588492110](https://github.com/taku077/c545d-recorder/actions/runs/44588492110) at exact HEAD `0843f0501dea28de03b07b7db98e62f7cde24feb`: GLib build and preflight selftest completed, paired registry/nochange measurement **STILL IN PROGRESS on last check**. Its measured MEM_PRIVATE size-bin values, conclusion and final artifacts are **NOT yet verified**. Do not rerun this lengthy workflow merely because a synthetic test or docs changed.
- **Scientific limit:** `VirtualQuery` groups adjacent pages with matching characteristics; MEM_PRIVATE region-size bins quantify committed region accounting, **not** source allocation ownership or provable freed memory/leak rate. Even if PrivateUsage rises in a particular bin, do not assert cause without further evidence. Microsoft documentation: https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualquery .
- **Previously confirmed**: 512-cycle [#44583345720](https://github.com/taku077/c545d-recorder/actions/runs/44583345720), last256 matched-control PrivateUsage +233,472 B, HeapWalk BUSY -2,784 B, HeapWalk tagged region commit 0 B, tagged free bytes +12,688 B; cache MSVC/GStreamer [#44586796586](https://github.com/taku077/c545d-recorder/actions/runs/44586796586) success (2047/2047 GIO exports, MP4, two H264 RTP/avdec_h264 paths, AAC, EOS). **Diagnostic cache is not releasable** because package DisplayName update/localization invalidation is not fully verified.
- **Next AI-only action:** get #44588492110 actual final outcome and numeric aggregate; use its size-bin breakdown to narrow the remaining residual memory; do not confuse initial cache warmup with indefinite leak proof. No Windows 10/Tapo host operation or user manual measurement.


### UPDATE 2026-11-20 JST — 512-cycle heap region result and 384-cycle VM size attribution

- **Verified branch context:** central open PR [#54](https://github.com/taku077/c545d-recorder/pull/54) HEAD `cd12b570a29c0ec7992f7c23aa878a12181e080c`, with all 11 PR-head Windows CI runs successful (including [combined-fix MSVC/GStreamer #44579422769](https://github.com/taku077/c545d-recorder/actions/runs/44579422769)). This separate isolated experimental branch `investigate/c545d-last-residual-slope-20261120` contains the NEWER diagnostic work. Do not confuse branch HEADs.
- **New confirmed experimental CI:** [512-cycle paired control #44583345720](https://github.com/taku077/c545d-recorder/actions/runs/44583345720) **SUCCESS**, commit `811cae162f726571760ee15c548b2953ed6bafce`. Control-subtracted **last256**: PrivateUsage **+233,472 B**, HeapWalk BUSY **-2,784 B** / **+1** BUSY block, VirtualQuery MEM_PRIVATE committed **+233,472 B**, tagged HeapWalk region committed **0 B**, tagged heap free-block bytes **+12,688 B**. Handles settled: registry-change **-2**, no-change **-43**. All 9/9 checkpoints had available `dwCommittedSize` for the **tagged** heap regions (8 tagged regions at baseline); this does NOT imply complete heap allocation coverage. Microsoft documents that some large HeapWalk regions have NO PROCESS_HEAP_REGION record: https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-process_heap_entry
- **Full run windows:** last128 PrivateUsage **+94,208 B**, last64 **+98,304 B**. The analyzer returned `SHORT_WINDOW_PLATEAU_CANDIDATE` by its 256-cycle tolerance heuristic, NOT proof of plateau or zero leak. A positive last64 remains. Earlier 512 CI #44565966197 last256 had +307,200 B; DO NOT splice separate-run data.
- **MSVC cache validation:** [#44585665458](https://github.com/taku077/c545d-recorder/actions/runs/44585665458) failed old splitmux first-fragment >=0.3s gate in BOTH SDK control and cache candidate; artifact 14560968625 confirmed equal 0.149667s startup fragments and valid AV decodes. Imported identical already-verified PR #54 test script to this branch in `6ab7ce264be2b5793bebfe6a6507d503b7a37f1e`, workflow trigger `791bf3e65c06222e04790a3925d6341d623602eb`. **Repaired [run #44586796586](https://github.com/taku077/c545d-recorder/actions/runs/44586796586) SUCCESS**: 2047/2047 exports, no missing, actual SDK-linked client loads candidate; synthetic 2 H264 RTP decoders, 2560x720@15 x264 medium Q24, AAC mono 48k, two 5-fragment splitmux/EOS tests pass (each ~6.231s). The diagnostic cache may return stale DisplayName after real installation/locale changes and is **NOT production qualified**.
- **Next discriminant implemented:** `tests/gio_appinfo_key_handle_probe.c` commit `5fea1bca8d5d6d9117c342b300cb5453bce9345e` reports `GIO_VMCLASS` numeric-only committed MEM_PRIVATE region-size buckets (<=4KB, 4KB..64KB, 64KB..1MB, >1MB) and counts at sparse checkpoints. `tests/analyze_gio_vm_private_buckets.py` commit `e403b6e34d3cd2613bfa1f7e9385c7d2eb7fd0ba` enforces correct no-change/mutation paired checkpoints, exact VM-to-bucket checksums, handle control and a synthetic parser selftest. [Windows CI #44588492110](https://github.com/taku077/c545d-recorder/actions/runs/44588492110) at commit `0843f0501dea28de03b07b7db98e62f7cde24feb` is **IN PROGRESS**, with initial selftest successful; run is NOT yet known PASS. It uses two 384-cycle arms (paired controls), not another 512-cycle run, and uploads only aggregate CSV and sanitized summary. No addresses, raw logs, registry paths or video publicly stored.
- **NEXT ACTION:** inspect #44588492110 final status/logs and numerical aggregate FIRST. Determine which VirtualQuery size bins contribute late PrivateUsage, and whether larger allocations are missed by tagged HeapWalk regions. Do not misinterpret size-class association as causal allocation stacks; avoid another long measurement unless existing CI cannot answer.
- **Safety:** no recording PC modification, camera connection, DLL replacement, forced handle closure, production settings changes, manual ETL, or long user host measurement. Keep exact dual-video + audio/MP4 recording specifications, and require actual Win10 certification before any deployment.



### UPDATE 2026-11-20 JST — cache MSVC startup-fragment gate synced from PR #54

- **Experiment branch** `investigate/c545d-last-residual-slope-20261120`. Previous diagnostic cache MSVC run [#44585665458](https://github.com/taku077/c545d-recorder/actions/runs/44585665458) **FAILED** only at MP4 duration gating. Retrieved artifact 14560968625: both SDK control and cache-enabled candidate emitted the same decodable first short fragment, 0.149667 s; subsequent durations 1.552, 1.683, 1.680, 1.166 s; 5/5 MP4 segments had H264+AAC. Candidate passed SDK exports **2047/2047**, no missing export or candidate-only dependency, GAppInfo runtime loading, and the synthetic two-RTP H264 plus AAC MP4/EOS media smoke. Do not call the overall run success.
- Source mismatch confirmed: isolated branch had older `tests/Assert-GStreamerOverlaySplitMux.ps1` unconditional 0.30 s minimum, while active PR #54 had already passed the corrected first-only 0.10 s exception (all remaining fragments retain 0.30 s). **Exact matching file content** copied from PR #54, commit [6ab7ce2](https://github.com/taku077/c545d-recorder/commit/6ab7ce264be2b5793bebfe6a6507d503b7a37f1e); follow-up workflow trigger update [791bf3e](https://github.com/taku077/c545d-recorder/commit/791bf3e65c06222e04790a3925d6341d623602eb).
- **New Windows CI** [#44586796586](https://github.com/taku077/c545d-recorder/actions/runs/44586796586) was **IN PROGRESS**, not yet declared PASS, at this writing. Inspect both official SDK and cache candidate splitmux results; do not loosen later-fragment/audio/EOS/caps checks.
- **Heap-region 512-cycle CI** [#44583345720](https://github.com/taku077/c545d-recorder/actions/runs/44583345720) still measured 512 control and registry-change cycles when last checked; build succeeded, no final numeric output yet. Do not start another lengthy run.
- **6/6 analyzer synthetic tests PASS** in [#44584997777](https://github.com/taku077/c545d-recorder/actions/runs/44584997777).
- Production Tapo recorder, live DLL, actual video, credentials, registry and recording settings unchanged. Cache has potentially stale DisplayName semantics under install/update and cannot yet be shipped.



### UPDATE 2026-11-20 JST — Six synthetic cache512 analyzer tests PASS; new WinRT cache MSVC smoke in CI

- **Branch:** `investigate/c545d-last-residual-slope-20261120`. The current code-workflow HEAD is `9017a50fb98a4775de3bba7fe0425a4630225c31` before this documentation update. This experiment is NOT deployed or merge-authorized.
- **Actual verified result:** [Linux numeric-only selftest #44584997777](https://github.com/taku077/c545d-recorder/actions/runs/44584997777) **SUCCESS, 6/6 tests** in 0.099 seconds: paired 512-cycle delta, missing heap-region checkpoints, heap walk error, impossible region coverage, retained +5 handles, and unavailable committed-region data. Commits `0accffa81cc87f89ca095009879b5074d1a3d720` and `1c19f912f63a047c95e5c5e2cbed4a587a914bcf`, no Windows host or media.
- **Windows 512-cycle region/free-block test:** [run #44583345720](https://github.com/taku077/c545d-recorder/actions/runs/44583345720), HEAD `811cae162f726571760ee15c548b2953ed6bafce`. Build compiled successfully, measurement in progress on last check. **No new numerical measurements yet confirmed.** Analyze its result and artifact before labeling residual as allocator retention or leak.
- **New independent Windows-2022 MSVC/GStreamer exact DisplayName diagnostic cache test:** workflow `.github/workflows/c545d-gio-displayname-cache-msvc-ci.yml` committed as `9017a50fb98a4775de3bba7fe0425a4630225c31`. [run #44585665458](https://github.com/taku077/c545d-recorder/actions/runs/44585665458) was in progress on last check. Uses GLib 2.82.4 original-source weakref+UTF16 fix, CI-only UWP stage hooks, and original-value cache under MSVC; checks SDK ABI, GAppInfo, synthetic 2×RTP H264 + AAC mux/splitmux/EOS. Cache may stale across real installs/locale changes, so **NEVER ship this diagnostic build**. Distinguish this new run from previously passed basic combined-fix-only MSVC run #44579422769.
- **Next:** retrieve actual final status, failed steps, and sanitized aggregates for both Windows runs; repair code only if evidence warrants. Preserve exact Tapo video/audio settings; no user-side measurements or DLL replacement.



### UPDATE 2026-11-20 JST — Heap-region commit/free 512-cycle discriminator (Windows CI, NOT production)

- **Current isolated experiment branch:** `investigate/c545d-last-residual-slope-20261120`; code commits `4f8e7dd61fd093b20ae63b22b9f8641a946fc62a` (probe) and `811cae162f726571760ee15c548b2953ed6bafce` (analyzer). The exact branch HEAD has advanced further after this note. Do not confuse this branch with active PR #54 HEAD; PR #54 is the main integration investigation.
- **Verified prior baseline:** [512-cycle original DisplayName cache run #44565966197](https://github.com/taku077/c545d-recorder/actions/runs/44565966197) succeeded with same-run registry-change minus unchanged control: last 256 cycles PrivateUsage **+307,200 B** vs HeapWalk BUSY **-6,956 B**; last64 PrivateUsage **-24,576 B** and BUSY **0 B**. This is **not** zero-leak proof. PrivateUsage reflects private committed bytes, while the HeapWalk BUSY census counts live blocks.
- **New code, not yet measured:** `tests/gio_appinfo_key_handle_probe.c` reports sanitised `GIO_HEAPREGION` totals under existing `--heap-summary`: region count; known committed-region count; committed/uncommitted region bytes; free-block bytes and count; errors. Addresses, paths, ETL, registry key names and media are NOT emitted.
- `tests/analyze_gio_cache_512_plateau.py` requires valid region telemetry at every 64-cycle checkpoint, rejects invalid/corrupt records and positive retained handles, subtracts matched no-registry-change control, and reports region coverage. The Win32 `PROCESS_HEAP_ENTRY.Region.dwCommittedSize` field can be 0 when unavailable; therefore partial region inventory **cannot** be equated with PrivateUsage or considered proof of memory release. Source: https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-process_heap_entry .
- Existing workflow `.github/workflows/c545d-gio-cache-512-plateau-ci.yml` has a **push trigger on the modified analyzer**. Its new post-change CI result has **NOT been independently retrieved/verified** at the time of this note (GitHub connector's commit workflow tool enumerates only PR-triggered runs). Do not claim success or new memory results. Inspect actual workflow run and numerical aggregate first. If failed, check build/parser compatibility before touching user host.
- Separately verified: [MSVC/GStreamer CI #44579422769](https://github.com/taku077/c545d-recorder/actions/runs/44579422769) passed on active PR #54 at `cd12b570...`: 5 independently H264+AAC-decodable splitmux fragments under patched GIO and official SDK control (6.229 s / 6.231 s). This is Windows-2022 camera-free CI, not real Windows 10/Tapo certification.
- **Next AI-only action:** inspect newly triggered 512-cycle run, then distinguish genuine live-object growth from allocator-held committed/free heap blocks and other private commit. If region coverage incomplete, treat remaining private difference as unclassified and design another read-only Win32 discriminator. Preserve recorder settings, `avdec_h264`, two-stream mux and audio/EOS behavior. No user manual tests, DLL replacement, registry changes, or release deployment.



### UPDATE 2026-11-19 JST — UWP API leak localized; behavior-preserving Win32 path alternative passes CI, not host-certified

- **Active PR #54**, `investigate/gio-2824-key-handle-lifecycle`. Earlier **96.29% reduction** (combined GWeakRef and UTF16 duplicate-path fix) and elimination of old hundreds-per-cycle Key handle growth were **Windows isolated CI observations**, NOT real Tapo recording-PC results. **No actual recorder, streaming, DLL, registry settings, capture settings or credentials changed.**
- [Win CI #44486691637 — SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44486691637): 16 cycles with matched no-registry-change control: full WinRT UWP processing PrivateUsage +638,976 B, HeapWalk BUSY +189,370 B / 1,636 blocks; skipping UWP callback, XML manifest or IStorageItem Path did **not** remove the majority. Skipping InstalledLocation + downstream: +107,238 B / 548 busy blocks. **These skips were DIAGNOSTIC ONLY, not fixes.**
- [CI #44489681603 — SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44489681603) fixed the diagnostic-only uninitialized sax->exit_early before early goto; added independent early exits before Package2 DisplayName and before IIterator_get_Current. 16-cycle paired conditions: full +205,754 BUSY B / 1,639 blocks, skip InstalledLocation +107,238 / 548, skip DisplayName +21,164 / 6, skip GetCurrent +13,124 / 5. The retained sizes associated with InstalledLocation+downstream are **56 B +544 and 120 B +544**. The remaining ~548 blocks involve DisplayName or later work. Do NOT yet assert a Windows kernel or COM OS bug; this is controlled source-stage correlation.
- Microsoft's [GetPackagePathByFullName](https://learn.microsoft.com/en-us/windows/win32/api/appmodel/nf-appmodel-getpackagepathbyfullname) is available for Windows 10. A CI-only native-path fallback prototype preserved **PackageManager enumeration, IPackage2 DisplayName, package family, XML parsing and UWP callbacks**. Initial [run #44491481980](https://github.com/taku077/c545d-recorder/actions/runs/44491481980) failed at compile due GLib `PACKAGE_VERSION` macro collision with Windows `appmodel.h`; repaired using push_macro/undef/pop_macro (commit `75109d3787257279097ff90a704eac0454252187`).
- **Verified [CI #44492106926 — SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44492106926)**: Win32 path getter succeeded **576/576** calls, all **576/576 strictly identical** to original WinRT InstalledLocation/Path; fallback=0, mismatches=0 in isolated Windows-2022 runner. Matched 16-cycle changes: ORIGINAL WinRT PrivateUsage +970,752 B / BUSY +201,582 B / +1,638 blocks vs NATIVE DIAGNOSTIC PrivateUsage +380,928 B / BUSY +103,066 B / +547 blocks: ~60.8%, 48.9%, 66.6% reductions in those respective residual metrics. 56 B and 120 B bins each **lost +544 accumulated blocks**; 190/194/196 B etc remain. Compare mode invoking both APIs retained old growth, strongly implicating path retrieval in part of residual retention. **This is NOT full UWP semantic/Win10/MSVC/recorder validation or a releasable patch.**
- New diagnostic files: `tests/patch_glib_uwp_api_isolation.py`, `tests/analyze_gio_uwp_api_isolation.py`, `.github/workflows/c545d-gio-uwp-api-isolation-ci.yml`; native path: `tests/patch_glib_uwp_native_path_diagnostic.py`, `tests/analyze_gio_native_path.py`, `.github/workflows/c545d-gio-uwp-native-path-ci.yml`. CI-only flags must **NOT** enter the recorder release.
- **Next actions, AI/CI only:** investigate remaining DisplayName-related ~547 blocks; test any non-invasive, *behavior preserving* fixes using exact source ownership and Windows CI A/B, then build production-candidate GLib GIO under MSVC SDK ABI and full GStreamer audio/video/muxer tests BEFORE requesting narrowly scoped Win10 host tests. Avoid more 4-hour manual tests or repeats of WPR/UMDH. No forced periodic restart or disabling UWP.


### UPDATE 2026-11-19 JST — 256-cycle residual growth confirmed, exact heap-size source isolation in CI

- **PR #54 is ACTIVE; never resume from stale main-only ETL/UMDH instructions.** No recorder PC operation, 4-hour host test, credential, real video, live DLL replacement, or production GStreamer change was made. Actual host fix status: **NOT APPLIED / UNVERIFIED**.
- Verified same-HEAD [Windows CI #44380978708](https://github.com/taku077/c545d-recorder/actions/runs/44380978708) success: 64 registry mutations in combined weakref+UTF16 patch produced Handle64 total 683 baseline → 685 before cleanup → 403 immediately after → **684 settled**; Key **435 → 435 → 153 → 434**. Per-type growth gate passed; old 16-cycle baseline +5,152 handles versus combined 0. The instant-after-cleanup drop is transient, *not* evidence that handles remain closed. GObject settled counts return to baseline.
- Verified [MSVC ABI/runtime CI #44376017336](https://github.com/taku077/c545d-recorder/actions/runs/44376017336) and later exact-HEAD MSVC CI success: SDK and candidate exported names 2047/2047, no missing symbol; candidate linked same SDK z-1.dll, SDK-import-library-linked client loaded patched GIO and exercised GAppInfo API. This is **not** full runtime/thread/GStreamer/recorder certification.
- **Critical new memory evidence:** [Windows CI #44475632844](https://github.com/taku077/c545d-recorder/actions/runs/44475632844) SUCCESS, including 256-cycle **paired no-registry-change control and synthetic HKCU mutation** tests, HeapWalk and VirtualQuery read-only aggregate inventories, and analyzer selftest.
- Combined-fix PrivateUsage deltas per 64 mutated cycles: **+1,540,096; +540,672; +454,656; +475,136 B**. Matched no-change deltas: **-368,640; -94,208; -118,784; +36,864 B**. Last 128 cycles control-subtracted PrivateUsage increase **+1,011,712 B**; control-subtracted HeapWalk BUSY increase **+708,040 B**; classification `PERSISTENT_GROWTH_INDICATED`, **not plateau**. 256-cycles after settled: mutated PrivateUsage +3,010,560 B, HeapWalk BUSY +1,661,942 B; control PrivateUsage -544,768 B, HeapWalk BUSY -172,188 B. VirtualQuery MEM_PRIVATE committed bytes also grew +3,010,560 B mutated over 256; do not confuse MEM_PRIVATE with exact PrivateUsage accounting.
- Across 256 mutated cycles, settled live GObject counts remain constant: GWin32AppInfoApplication 123, ShellVerb 680, Handler 390, GWin32RegistryKey 384. HeapWalk busy **block counts** increased from **19,471 to 29,731** (+10,260), implying continued small non-GObject heap allocations or caches under registry changes; allocation stacks not yet identified. Do not claim unbounded long-term leak or deployment safety solely from 256-cycle slope.
- Independent official GNOME GLib 2.82.4 and 2.88.3 source inspection shows redundant `g_wcsdup(path,-1)` at registry UTF16 constructor + a second setter copy remains in both; simple upstream version bump alone does not remove this duplicate allocation.
- **New current task:** 256-cycle residual data is available and analyzed; `tests/gio_appinfo_key_handle_probe.c` now records sanitized `GIO_HEAPSIZE` counts (exact allocation size 0–2047 B, overflow bin >=2048) alongside HeapWalk, and `tests/analyze_gio_heap_sizes.py` subtracts same-run control to find dominant growing size classes. Corresponding Windows CI changes are in PR #54 at commits a498d624, 2f10b4e8, 4a5fabe3; latest **histogram CI is IN PROGRESS / NOT YET VERIFIED** at time of this update. After it completes, download artifacts and inspect dominant sizes, determine likely GIO source functions, and implement safe targeted fix in **isolated** GLib build. No user-side measurements requested.

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



## CURRENT 2026-11-18 JST — ETL自動オフライン解析ツール完成、実機レポート待ち

- ユーザーはWPAでの多数の画面操作の自動化を要望し、**保存済みETLの自動解析ツール実装**を依頼。Microsoft WPAExporterは.wpaProfile必要で画面操作を減らしにくいため、公式.NET TraceProcessing API `UseHandles`/`CreatingStack`を直接利用するヘッドレス解析方式を採用。公式 https://learn.microsoft.com/en-us/windows/apps/trace-processing/tutorial と https://learn.microsoft.com/en-us/dotnet/api/microsoft.windows.eventtracing.memory.ihandle.creatingstack
- **公開repo PR #52 mainマージ済み**。`diagnostics/EtwHandleOffline/`にC#プロジェクト、起動CMD、日本語README。GitHub Actions Windows2022の.NET8 x64 self-contained publish / --selftest成功（run 44304482529）。出力ZIP `C545D_ETL_Offline_Analyzer_Win10_x64.zip`（約36.36MB、ZIP CRC PASS）をこのチャットに直接添付済み。次チャットで古いsandboxリンクを引き回さず必要ならGitHub artifactを再取得し実体検証。
- **実行するユーザー操作は1つ**：展開したZIPの`START_OFFLINE_ETL_ANALYSIS.cmd`をダブルクリック。既存 `C545D_Handle_20261118_210100.etl`（202MB）だけ読み取る。対象PID6168。出力は `%LOCALAPPDATA%\C545D_GStreamer\WPR_Handle\C545D_Handle_20261118_210100_SAFE_SUMMARY.txt`。**安全なTXTだけ**提示し、ETL本体・レジストリ名・生のアドレス・生スタックをアップロードしない。
- **重要なAPI限界**： `IHandleDataSource.OtherHandles`は汎用型で個別Key型を直接判定しない。さらに `CloseTime=null` はETL内にCloseイベント記録がないことのみを意味しリーク確証ではない。処理系統モジュールから手がかりを得るだけ。生成スタックが未記録なら`STATUS=NO_CREATE_STACKS_AVAILABLE`。標準はsymbol serverアクセスなし（オプトイン`--symbols`のみ）で負荷を抑える。**実ユーザーETLでは未検証**。
- 先行根拠：PID6168、214種類のレジストリキー×79=16906/17078個、毎時01分・24分にKey+428。2026-11-18 20:59–21:04 WPR Handle保存済み、Handles17799→18227（+428）、ETL202MB、`WPA: NOT FOUND`。録画継続、UST解除済みで、再キャプチャ・再起動不要。
- **次にすること**：ユーザーの安全TXTの`STATUS`と`TOP_MODULE_CHAINS`を分析。何も生成スタックがなければ再捕捉を推奨せず、WPAExporter profile方式/ETL対応データソースを見直す。CLIが.NET依存/Win10互換でエラーなら表示された安全な失敗コードだけ確認、録画に影響を与えない。
- 公開repoでは個人の絶対Windowsユーザーパスを掲載しない。


## CURRENT — 2026-11-18 21:04 JST: WPR Handle profile ETL completed exactly across +428 handles

- **User's newest real output**: Target PID=6168; expected burst 2026-11-18 21:01; WPR Handle capture **20:59–21:04**; `Starting WPR Handle capture...`, `Stopping WPR and saving ETL...`, before handles=17799, after=18227, **net +428**; output shows `Saved ETL:` and `COMPLETE`. Exact local saved path is known in the current conversation; keep absolute Windows username path out of public repo.
- **Do not overclaim**: This proves a 428-handle net increase occurred during a successfully ended WPR window, not yet that all 428 were Key in this window, that the ETL contains readable Create Stack, or which DLL caused it. Previous 4h HandleTypes proves repeated +428 Key, and Handle64 user-provided histogram proves 214 unique registry keys ×79 handles =16906 of17078, but create-stack attribution remains unverified.
- **Immediate next action**: On Windows PC run a read-only file size/existence check for saved `C545D_Handle_20261118_210100.etl`, check whether `wpa.exe` exists (WPR installed does not guarantee WPA installed), and if installed open ETL in WPA **File→Open**. Graph Explorer **Memory→Handles** (if present). Table group/filter **Creating Process=6168** and **Handle Type=Key** (also check owning process where available). Expose **Create Stack** and **Count/outstanding**. Use **Trace→Load Symbols** if names unresolved. Official Microsoft: https://learn.microsoft.com/en-us/troubleshoot/windows-server/support-tools/support-tools-xperf-wpa-wpr and https://learn.microsoft.com/en-us/windows-hardware/test/wpt/opening-and-analyzing-etl-files-in-wpa
- **Privacy and performance**: ETL can contain registry keys, file paths and system events; do not upload raw ETL to public repo/chat. Only sanitized DLL or known function names and counts or redacted screenshot. WPA parsing/symbol loading on old HDD PC may be costly; stop analysis if recording suffers, preserve ETL, do not restart/capture again. No UST, GFlags, recorder stoppage, Handle -c or registry modification.
- **Known user path** is available in private handoff; public says `%LOCALAPPDATA%\C545D_GStreamer\WPR_Handle\C545D_Handle_20261118_210100.etl`.



## CURRENT — 2026-11-18 JST 20:29: WPR Handle利用可能、記録停止中（次は短時間ETWで生成スタックを捕捉）

- ユーザー実機報告: `wpr -profiles | Select-String -Pattern 'Handle'` → `Handle Handle usage`、`wpr -status` → Windows Performance Recorder `10.0.19041 (CoreSystem)`, `WPR is not recording`。**Handle profile使用可能で、現在のWPR記録は動いていない**。まだHandle ETLは取得していない。
- 先行実機Key分布: PID6168で17,078個、382種類、うち214種類の各79個=16,906個(約98.99%)。周期Key増加は毎時01分・24分頃に428個=214×2。これは同一集合への重複Open仮説を支持するが生成DLL/関数は未特定。
- Microsoft公式: https://learn.microsoft.com/en-us/troubleshoot/windows-server/support-tools/support-tools-xperf-wpa-wpr はWPR `Handle usage`→WPA `Memory > Handles` の Creating Process / Handle Type / Create Stack を案内。https://learn.microsoft.com/en-us/windows-hardware/test/wpt/wpr-command-line-options は `wpr -start Handle` (既定memory mode), `wpr -stop <file.etl>`, `wpr -status`, `wpr -cancel` を規定。**Heap tracingのTracingFlags設定はHandle captureと別で、録画再起動前提にしない**。
- 予定操作: 管理者PowerShellで事前に現在のWPR不使用を再確認、同一PIDの録画が動いていることを確認し、次の毎時01分または24分の**約1〜2分前**にWPR Handleを開始し、**2〜3分後に自動停止**してローカルETL保存。時刻合わせはWindowsローカルPowerShellが待機するだけでGPTがバックグラウンド作業するわけではない。
- ETLにはKey名、プロセス情報やパス等個人情報が含まれ得るため、**ETL原本はチャットに提出しない**。WPAでPID6168 / Key / Create Stackを限定して関数・DLLの安全な概要を抽出する。まずはWPR終了ステータスとETLのファイルサイズだけ受領する。
- UST解除済み、RC35通常録画を継続。WPRが起動失敗したら別セッションを強制停止しない。録画停止、GFlags変更、再UMDH測定、Handle -c、レジストリ編集不要。短時間Handle ETWでも追加負荷はあり得るため録画の正常性が優先。


## CURRENT 2026-11-18 JST — Keyハンドル分布実測確定：214種類×79個=16906（全Keyの約99%）

ユーザーの最新ヒストグラムは Repetitions79,KeyNames214,Handles16906 / 4,1,4 / 2,1,2 / 1,166,166。382種類、17078 Keyで先行PID6168集計と完全一致。16906/17078=98.993%。

過去のHandle type CSVでは毎時01分・24分にKeyが+428ずつ、4hで+3424。428=214×2、79=1+2×39に整合。周期ごと同じ214のキー各2追加という強い仮説だが直接時系列で214個すべての+2は未検証。RegOpenKey等の作成者とclose漏れ関数は未特定。

次の目標は原因DLL/関数のコールスタック特定。4h集計やUMDH Captureはやり直さない。もし追加確認するならHandle64を2時点だけローカル取得してキー名ごとの増加数を非個人情報の数値のみで照合。RAWレジストリキー名/パスは共有しない。

公式ProcMon v4.13（2026-11-05公開）のサポートOSはWindows11+と記載 https://learn.microsoft.com/en-us/sysinternals/downloads/procmon 。ユーザーWindows10での利用は未検証。Windows10対応の具体的入手方法が確認できるまで最新版を案内しない。WPR/WPAのHandle Usage/Create Stackは公式 https://learn.microsoft.com/en-us/troubleshoot/windows-server/support-tools/support-tools-xperf-wpa-wpr で案内されるがプロセス再起動を要する設定もあるため、現在の録画は維持する。

ユーザーはUST解除・通常録画継続中。録画停止、UST再ON、GFlags設定変更、Handle -cによる強制close、レジストリ編集は禁止。Microsoft RegCloseKey https://learn.microsoft.com/en-us/windows/win32/api/winreg/nf-winreg-regclosekey 。




## CURRENT — 2026-11-18 JST: Key 17078個・固有名382種類、上位10種類は各79個（頻度分布待ち）

- **最新のユーザー実機PowerShell結果**：PID6168、`KeyHandles=17078`, `UniqueKeyNames=382`, `MostRepeatedCount=79`, `Top10RepeatedCounts=79,79,79,79,79,79,79,79,79,79`。これはHandle64 `-a -p`を読んだユーザーのメモリ上での集計結果。**元レジストリキー名の本文は提供されず、こちらにも保有しない**。
- **数学的に注目**：428 = 214×2、17078 = 214×79 + 172。ただし**214種類が79回ずつ開かれていることは未確定**。分布が一致すれば214キー×79本で16906ハンドル、残り168種類が172ハンドルとなる。周期的に一定キー集合を複数回開く強い手がかり。
- 次の1操作は同じPowerShellセッション内の`$groups` (Handle名を `Group-Object` した結果)を`Group-Object Count`で重複回数別に再集計し、`Repetitions`, `KeyNames`, `Handles`の**数字だけ**表示。キー名/パス/ハンドル値は表示・保存・共有しない。前回セッションの変数が消えていれば同じHandle snapshotだけ安全に再取得することを検討し、録画は停止させない。
- 4時間HandleTypes実測はKeyだけ+3424、毎時01分/24分に+428×8回。キー名の重複数だけでは生成者の関数はまだ分からない。頻度分布を確定してから、必要ならMicrosoft Process MonitorでPID・RegOpenKey等を短い時間だけフィルタし、PC内でstackを調べる。ProcMonの高負荷/個人パス公開リスクに留意し、現時点で導入・常時監視は要求しない。
- **公式根拠**：https://learn.microsoft.com/en-us/sysinternals/downloads/handle / https://learn.microsoft.com/en-us/windows/win32/sysinfo/opening-creating-and-closing-keys / https://learn.microsoft.com/en-us/sysinternals/downloads/procmon
- 録画は通常運転中、UST解除済み。再Capture/録画停止/GFlags操作/Handle `-c`は不要。Keyカーネルオブジェクトの増加とPrivateBytesの増加は因果関係未確定。


## CURRENT — 2026-11-18 JST：Handle種類別4h実測で**Keyハンドルだけ+3424個**と確定（最優先）

- ユーザーから実物 `C545D_HandleEvidence_20261118_145921.zip` を受領。ZIP CRC正常。中身2CSV：HandleSummary 239レコード、HandleTypes 3840行。全239レコードStatus=OK、PID=6168固定、ProcessStart=2026-11-18 00:25:43、種類別合計とHandleToolTotalは毎回一致。観測時刻 2026-11-18 14:59:21→18:59:22（4h）。1分間隔は微妙にずれ239件となったが収集は正常。
- **最重要事実**：Keyは `12370→15794` **+3424**。総ハンドルも `12663→16087` **+3424**。他の16種類は開始から終了まで**全て純増0**（例：Event40→40、File17→17、Thread74→74、Section14→14、EtwRegistration99→99）。その他の非Key種別は合計293（Key以外が293）、上述の主要6種以外の残りは35。**KeyはWindowsレジストリのハンドル型**であり、GStreamer自身のバイナリplugin registryとは異なる。
- 同一PIDのPrivateMemory `695.32→717.94MB` **+22.62MB**、WorkingSet `634.28→656.62MB` **+22.34MB**。これはKey増加と同じ期間に起きたが、Keyカーネルオブジェクトの占有領域≠プロセスPrivate Memoryのため**同じリーク原因とはまだ断定不可**。
- 1時間あたり**Key純増856**、毎時01分頃と24分頃に**+428ずつ8回**。Keyは瞬間+431/すぐ−3の周期が4回、直接+428が4回で**安定後の純増は毎回428**。一時的にEvent、EtwRegistrationなど他種が増えても戻る。PID変化なし。
- **新たに絞られた仮説**：周期処理がWindowsレジストリKeyを大量に開き、ハンドルを解放せず保持している疑いが強い。具体的関数、モジュールは未確定。Microsoft公式：https://learn.microsoft.com/en-us/sysinternals/downloads/handle と https://learn.microsoft.com/en-us/windows/win32/sysinfo/opening-creating-and-closing-keys
- **次の最小操作**：録画継続・UST OFFのまま、既に所持するMicrosoft Handle64を**一度だけ** `-a -p <録画PID>` で読み取り専用実行し、Keyオブジェクト名の**重複度（最も多い同一キーの件数、異なるキー名の種類数、上位頻度の数字のみ）**をローカルで集計する。元パス・シンボル・ユーザー名・RAW handle一覧を提出/公開しない。Key名の集中度次第で次の関数トレースを決める。レジストリそのものを編集しない。Handleの`-c`による強制closeは絶対にしない。
- これまでのUMDHはByteDelta91（正27負64）、Top3正+380928/+178176/+94208Bに共通gstisomp4等を認識したが、今回**レジストリKey**へ分類したハンドルは別の資源。GStreamer MP4 muxだけが原因と決めつけない。
- 次チャットはユーザーの新しい Key-handle 重複度の安全な数字と本CURRENTから続行。既存4h監視、UST再Enable、UMDH再キャプチャ、録画再起動を繰り返さない。公開には個人Windows絶対パス/生レジストリキー名を含めない。



## CURRENT — 2026-11-18 JST: Handleの種類別4時間自動記録ツールを用意、実機CSV待ち（最優先）

- ユーザーは4時間メモリCSVのハンドル増加（PID6168、3247→6671、+3424個／4h、約+856個/h、毎時01分・24分に約+428個）を受け、**ハンドル種類別の自動記録を開始することに同意**。これまでのUMDH再測定や手動測定には戻らない。
- 2026-11-18のユーザー提供ファイル `C545D_Memory_20261118_033635.csv` は03:36〜07:36の241記録、Private 621.65→653.42MB (+31.77MB)、WorkingSet 536.71→585.34MB (+48.63MB)、PID6168は維持。今回の優先原因調査対象はハンドル種類ごとの増加。
- 新しい提供物：`C545D_HandleTypes_AutoMonitor_4H.zip`。内容：`Monitor-C545DHandleTypes.ps1`、`START_HANDLE_TYPES_4H.cmd`、`README_JA.txt`。実行コードはGitHub `diagnostics/Monitor-C545DHandleTypes.ps1` [PR #45](https://github.com/taku077/c545d-recorder/pull/45) で**mainへマージ済み**。READMEとCMDも `diagnostics/` に保存。
- **Microsoft純正HandleはZIPへ再配布せず**、ユーザー自身が https://learn.microsoft.com/ja-jp/sysinternals/downloads/handle から `Handle.zip` をダウンロードし、`handle64.exe` をモニタースクリプトと同じフォルダーに配置する。CMDを**右クリック→管理者として実行**（公式にHandle実行へ昇格必要）。初回EULA受諾は `-accepteula`。
- モニターは `handle64.exe -accepteula -s -p <PID>`を**1分間隔、240分**実行。Preflightで取得可否・型別合計確認し失敗なら本測定しない。ProcessHandlesとHandleTotal、種類別件数、PrivateMB、WorkingSetMB、時刻、PID、開始時刻を2CSVに保存。4h後1ZIP `%LOCALAPPDATA%\C545D_GStreamer\HandleTypesMonitor\C545D_HandleEvidence_日時.zip` へまとめる。**提出はZIPのみ**。Raw handle names/paths/credentialsは保存しない。
- **Windows PowerShell 5.1の実ツール試験合格**：CI [run 44246719535](https://github.com/taku077/c545d-recorder/actions/runs/44246719535) で構文検査、合成Handleサマリー・CSV往復、Microsoft公式Handle64実体ダウンロードと実際のPIDで `PROBE_PASS: Total=606, SumTypes=606, TypeKinds=20` を確認。他のSourceValidationとHeapTrace CIもPASS。**ユーザーのWindows10実機で4時間完走は未確認**。
- UST解除済み、RC35通常録画は継続。録画を止めない、PIDが変わる／複数ならそれをエラー状態として記録、Handle -c等強制closeは使用しない。タイプ別結果でもリーク原因関数は未確定。
- 過去のUMDH上位3は +380928/+178176/+94208B、共通 gstisomp4/gstbase/gstreamer/glib。MP4の正常なサンプル蓄積 vs 解放漏れも併存する仮説。まずハンドル種類別の増加状況を分類し、次の調査計画を立てる。
- **次回再開時**、このCURRENT→非公開handoff→ユーザーの新しいHandleEvidence ZIP又はPreflightエラー→GitHub HEAD/CIの順に確認。古い毎時間手動測定やUMDH Captureを再案内しない。チャット内sandbox ZIPのリンクは別会話で再利用せず、必要ならGitHubにあるスクリプトから再生成してパスを検証する。



## CURRENT 2026-11-18 JST — 4時間CSV実機解析：Private +31.77MiB、ハンドル+3424（最優先）

- ユーザーが自動ロガー出力CSVをアップロード。**実ファイルを読み取り分析済み**。241サンプル、約1分間隔、測定4時間（2026-11-18の早朝・JST）、全件`Status=OK`・同一PIDのまま。GST通常録画は継続、USTは解除済み。
- PrivateMB `621.65→653.42`（**+31.77MiB/4h**）、WorkingSetMB `536.71→585.34`（**+48.63MiB/4h**）、Handle Count `3247→6671`（**+3424個/4h、厳密に+856個/hの4連続区間**）。CPUSeconds累積値も4時間で+20698.93秒、これは総CPU時間であり経過時間で割ると約1.44論理コア相当。
- Handle Countは**毎時01分付近と24分付近**の2系列で8回急増。04:01(+494→数分後ネット+428)、04:24(+439→ネット+428)、05:01(+439→+428)、05:24(+439→+428)、06:01(+439→+428)、06:24(+439→+428)、07:01(+495→+428)、07:24(+439→+428)。各イベント間は約23分、37分交互。長時間維持される階段状増加は要優先調査。これは当該プロセスのハンドル数であって、記録用PowerShellのハンドル数ではない。
- Private増加の4つの60分区間は+5.71,+5.98,+12.96,+7.12MiBで直線一様ではない。Privateが分割後にすぐ落ちないことだけでヒープリーク確定とはしないが、ハンドル+856/hの安定増加は正常なmp4 sample table蓄積だけでは説明しきれない。
- GStreamerの`splitmuxsink`は録画時間上限とキーフレームで切り替わり、公開ソースでは`max-size-time=3600000000000, async-finalize=false`。プロセス開始00:25頃に対してxx:24頃の急増は**時刻が近いが、MP4ファイルの実際の切替時刻はCSV未収録**。xx:01頃の別周期もある。MP4 muxerが原因と断定しない。
- **次の目標**：ハンドルが何の種類（File/Event/Thread/Section/Key等）で増加するか確認。Microsoft Sysinternals Handle（公式 https://learn.microsoft.com/ja-jp/sysinternals/downloads/handle ）の`handle -s -p <pid>`はプロセス限定のオブジェクト種類別件数を出力可能（管理者権限）。ユーザーの録画PIDは変わる可能性があるので、新規調査時は現在PIDを読み取る。ハンドル名やフルパス・生の全ハンドルは共有せず種類別の数だけ比較。Handle.exeには`-c`（閉じる）もあるが**絶対に使わない**。
- 可能なら次に、手動待機を要しない安全な種類別スナップショット自動化を検討（追加ツールの導入はユーザーに確認）。録画停止/UST再ON/UMDH再Captureは必要なし。既存PR40 UMDH Top3は`glib-2.0-0,gstisomp4,gstbase-1.0-0,gstreamer-1.0-0`の共通スタックを特定したが、このハンドル増加の発生元と同じとは未証明。
- 元CSVおよびグラフ（2点）は今のチャット添付として存在。古いsandboxリンクを次チャットに流用しない。公開側には実録画パスやカメラ設定/資格情報は載せない。


## CURRENT 2026-11-18 — メモリ増加の自動計測を用意（4時間／60秒間隔）

- **直近のユーザー要望**：「1時間ずっとこれを気にしないといけなくなるので、自動で記録をとるようにはできないか？」。手動の1時間ごとの測定を行わせず、自動ロガーを作成済み。
- ユーザーへの提供物：`C545D_MemoryMonitor_4H.zip`（`Monitor-C545DMemory.ps1`, `START_C545D_MEMORY_4H.cmd`, 日本語README）。4時間・60秒間隔、CSVに時刻/PID/起動時刻/PrivateMB/WorkingSetMB/Handles/CPUSeconds/状態を記録。CSV保存先 `%LOCALAPPDATA%\C545D_GStreamer\MemoryMonitor\C545D_Memory_yyyymmdd_HHmmss.csv`。**起動したか・実際のCSV結果はまだ未確認**。
- スクリプト本体をGitHub `diagnostics/Monitor-C545DMemory.ps1` に追加し、[PR #42](https://github.com/taku077/c545d-recorder/pull/42) をmainへマージ済み。Windows PowerShell 5.1構文とCSV往復自己テスト [Actions 44148976014](https://github.com/taku077/c545d-recorder/actions/runs/44148976014) SUCCESS。ソース検査とHeapTrace CIも成功。**4時間継続・実カメラ環境の動作は未検証**。
- ユーザー側の次の最小操作：既に録画が継続している状態でZIPを展開し `START_C545D_MEMORY_4H.cmd` をダブルクリック。コンソールを閉じず最小化、4時間後にCSV 1ファイルを提出。録画停止/UST再ON/UMDH Capture不要。CSVを記録中Excelで開かない。
- **直近UMDH実測の事実**：ByteDeltaRecords91（正27負64）、CountDeltaRows91、上位3差分 +380928/+178176/+94208 B、3件とも`glib-2.0-0, gstisomp4, gstbase-1.0-0, gstreamer-1.0-0`の17シンボル行（Windows6、Media11）。既存`Record.ps1`は`splitmuxsink ... max-size-time=3600000000000 async-finalize=false`。正常なMP4サンプルテーブル増加 vs 分割を越えるリークが未確定のため、4時間CSVで同一PID・同一セグメント相対時刻の推移を検討する。
- Windowsユーザー名を含む絶対パス・認証情報・RAWスタックは公開しない。古い手動測定手順に戻らない。



## CURRENT 2026-11-18 JST — UMDH上位3スタックの実機解析成功：isomp4 MP4 mux経路、原因は未確定

- ユーザーの **最新の実機PowerShell出力**：`ByteDeltaRecords=91 Positive=27 Negative=64`, `CountDeltaRows=91`, `AllSignedHeaderRows=182`。**182は91個のByte/Count差分ペア**であり、これまでの`parsed_backtraces=182`と、量と件数の混合集計`parsed_net_delta_bytes=-43425`はメモリ純増減として**無効**。過去の正差分693428BもCountDeltaが混じったため要訂正。
- ByteDeltaの上位3件 (1) +380928 B line 124–144、(2) +178176 B line 145–165、(3) +94208 B line 166–186。**3件全て同じ** SymbolLines17 / WindowsFrames6 / MediaFrames11 / OtherFrames0 / MediaModules=`glib-2.0-0, gstisomp4, gstbase-1.0-0, gstreamer-1.0-0`。上位3件合計 +653312 B。これらは正確なByteDelta値。
- 公開レコーダーソース `Record.ps1` を再確認：`splitmuxsink name=mux max-size-time=3600000000000 async-finalize=false send-keyframe-requests=true`。明示的な muxer 変更はなく、GStreamer `splitmuxsink`公式既定は`mp4mux`。**実際のユーザー実行RC35 EXEと公開ソースがバイト一致する検証は行っていない**が、現行ソースのMP4 muxing経路と今回のgstisomp4スタックは整合。
- GStreamer公式qtmuxソース：https://github.com/GStreamer/gst-plugins-good/blob/master/gst/isomp4/gstqtmux.c は、通常MP4がEOS時にmoov/sample tablesを書き、完成までテーブルを増やし得ると明記。**最優先仮説**は正常なMP4サンプル/インデックス情報の一時蓄積。`gstisomp4`が共通だからといってプラグインの解放漏れと断定しない。代替はmuxerがファイル切替後にも保持し続けるリーク。
- **次に判定すべきこと**：同じgst-launch PIDで、各1時間MP4の切替直後（例：5分後）を連続2〜3セグメントの同条件で比較し、PrivateMemoryと必要に応じてWorkingSetが平衡/再利用されるか確認する。ファイル切替の一時的な増減だけでは判定不可：正常にfreeされてもヒープがOSに即座に返されないことがある。録画を止めず、UST OFF維持、再Captureしない。**単一25.54分のUMDH差分では真のリーク未確定**。
- 解析の次順位として、保存済み差分の上位3スタック内の**許可済みgstisomp4関数の種別**を調べれば、サンプルテーブル追加経路か別処理か判別可能。ただし個人名・アドレス・RAWスタックの提出を求めず、コードを無理に変更しない。
- 事実/仮説の区別：観測値=91組、上位3 +653312B、同一モジュール群；仮説=moov/index一時蓄積。レコーダー/GUI/入力RTSP/時刻同期/エンコード品質/分割設定はいじらない。


## CURRENT — 2026-11-18: UMDH 2-line record format explains blank top-three stack output

- ユーザーが実機で完全版 top3 parser を実行した結果：Rank1 380928B StartLine=124 EndLine=124; Rank2 178176B StartLine=145 EndLine=145; Rank3 94208B StartLine=166 EndLine=166; 3件とも SymbolLines=0 / MediaModules=none。録画は通常継続、UST OFF。
- **公式資料で原因解明**：Microsoft AskPerf `Two Minute Drill: UMDH.EXE` は各スタック差分を (1) `+ BYTES_DELTA ... allocs BackTrace TRACEID`、(2) `+ COUNT_DELTA ... BackTrace TRACEID allocations`、(3) stack frames の形式と説明。従来の広い `^\s*[+-]...\(` 正規表現は同一スタックの2つの見出しをそれぞれ別レコードと誤認した。よって182件は91組の2行を数えた可能性が高く、`allocs`に限定した91件こそ真のヒープ差分ブロック数の候補。
- **StartLine=EndLineの直接原因**：124行のbytes headerの直後（125行と推定）にあるcount headerを次の論理ブロックの境界にして、スタック範囲を空にした。上位3件の `none` はDLL欠落/リーク無しを示さない。
- **次の操作**：録画を止めず、既存 `%LOCALAPPDATA%\C545D_GStreamer\HeapTrace\UMDH_RAW_DIFF_PID9424.txt` を読み取り専用で再解析。**bytesヘッダー `allocs\s+BackTrace` のみをlogical block開始として使用**し、次の同形式bytesヘッダー直前までをモジュール抽出範囲とする。91件を固定検証でエラーにせず、ByteRows / CountRows / TotalHeaderRows を別々に報告し、上位3件の符号付きBytesと範囲・既知DLLだけ表示。以前の182件を必須とする案内は破棄。
- 原本T1/T2/DIFF再キャプチャ・再比較・UST再有効化・録画再起動は不要。関数名/アドレス/個人パス/未許可モジュール名は出力しない。リーク原因は未確定。
- 出典 Microsoft TechCommunity https://techcommunity.microsoft.com/blog/askperf/two-minute-drill-umdh-exe/373180/ と Microsoft Learn https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/interpreting-a-log-comparison


## CURRENT 2026-11-18 JST — 完全版 UMDH 91/182境界解析を実装しWindows PS5.1 CI合格、実機出力待ち

- ユーザーの最後の実機エラーは`差分レコード数が想定と異なります: 91`。先行の緩いヘッダー検出では182件。旧PowerShellの正規表現は`allocs BackTrace`を必須としていたため一部形式を取りこぼした可能性。元ログ破損は示さない。
- **新コード**：公開repo `diagnostics/Analyze-UMDHDiffTop3.ps1` [PR #37](https://github.com/taku077/c545d-recorder/pull/37) **mainマージ済み**。緩い差分ヘッダー正負両認識、上位3件を次の正負いずれかのヘッダーで区切り、許可済みメディアDLL名と安全な件数のみ表示。固定182件不一致は警告するが即終了しない。録画/GFlags/UST/RAW変更なし。
- **Windows CI確定**：Windows PowerShell 5.1構文/サンプル182レコード（正91・負91、`allocs`半分のみ）/上位3順位/ブロック分離/個人識別文字列の出力排除のSelfTest **PASS**。workflow [44125638221](https://github.com/taku077/c545d-recorder/actions/runs/44125638221) と [44125638533](https://github.com/taku077/c545d-recorder/actions/runs/44125638533)成功。**実機UMDHの差分分類はまだ実行結果を受領していない**。
- 初回CIではBOMなし日本語.ps1がPowerShell 5.1で誤認識されsyntax error。修正して**PS1本体をASCII限定**にし再CI成功。今後BOMなし日本語スクリプトを安易に配布しない。日本語READMEは別ファイル。
- **現在のチャットの提供物**：`C545D_UMDH_Top3_Fixed_20261118.zip`（PowerShellスクリプトと日本語README）。ローカル生成ZIP CRC PASS、PS1はGitHub版と同じ文字数・ASCIIで確認。別チャットでは旧sandboxリンクを推測せず、必要なら実在するファイルを再生成・確認する。
- **次のユーザー操作**：ZIPを展開したフォルダーから `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Analyze_UMDH_Top3_Fixed.ps1" -SelfTest`、成功後同じコマンドから`-SelfTest`を除いて既存 `%LOCALAPPDATA%\C545D_GStreamer\HeapTrace\UMDH_RAW_DIFF_PID9424.txt`を解析。**出力は安全な件数・許可済みDLL名のみ**なのでそのテキストをこのチャットへ貼付。元UMDH RAW/DIFF全文の提出不要。
- ユーザー報告でUST解除・通常録画再開済み。再Capture/再UMDH比較/録画停止/UST再ONは要求しない。メモリリークの原因は未確定。前回までのブロック±30行集計は隣のレコードの混入を起こすので再実行しない。


## CURRENT 2026-11-18 — PowerShell差分ヘッダー正規表現の誤検出：91件

- ユーザーの実行結果：提示したread-onlyの差分ブロック抽出コードが `差分レコード数が想定と異なります: 91` で中断。これは**元UMDHログが欠損した証拠ではない**。従来のより緩い解析条件では182件検出していた。直前コードのヘッダー正規表現 `...\ballocs\s+BackTrace...` が余分な固定条件となり、一部の行を落とした可能性が高い。
- **次の対応**：同じ既存 `%LOCALAPPDATA%\C545D_GStreamer\HeapTrace\UMDH_RAW_DIFF_PID9424.txt` を再読込する前に、`$headerRx` を `'(?i)^\s*([+-])\s+(?:0x)?([0-9a-f]{1,16})\s+\([^)]*\).*?BackTrace[0-9a-f]+\b'` に1行修正する。旧 `\ballocs\s+` 条件だけを削除。**実機での182件への復帰はまだ未検証**。再Capture、再UMDH比較、USTの再ON、録画停止なし。
- 上位3差分は既存値+380928B（124行）、+178176B（145行）、+94208B（166行）。次の正負ヘッダー直前までを各ブロックとして区切り、既知のGStreamer/FFmpeg/GLibモジュール名だけを安全表示する。上位3件の原因DLLは**未特定**。
- ユーザーはUST解除済み・通常録画再開済み。新しい診断ツール配布を繰り返さず、現在のPowerShellコード1行修正の実行結果を待つ。
- Microsoft公式: https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/interpreting-a-log-comparison


## CURRENT — 2026-11-18: UMDH差分の上位3件の位置関係を実測確認
- 録画は再開済み、UST解除済み。再キャプチャ・再比較・録画停止は不要。
- UMDH差分の正増加上位3件：+380928 Bは124行、+178176 Bは145行、+94208 Bは166行。差分レコード見出しは21行間隔。187行が次の見出しかは未確認。
- ユーザー実測：Rank1の後方30行のmodule!symbol該当24件、次の差分ヘッダー1件。Rank2も後方30行の該当24件/次ヘッダー1件。Rank3も24件/次ヘッダー1件。つまり前後30行の単純集計では隣の差分ブロックのシンボルが混ざる。
- 保存済みUMDH_RAW_DIFF_PID9424.txtは2853行、差分レコード182件、module!symbol該当2366行。元T1/T2に約7万行のBackTrace識別文字列がある。従来のno-recognized-framesはスタック全欠落の証明ではない。
- 次の1操作は、既存差分ファイルを読み取り専用で走査し、正の上位3件それぞれの見出しから次の差分見出し直前までに限定して、許可されたmediaモジュールのbasenameとWindows等のカテゴリ・件数だけを出す。原文/関数名/個人パス/未知モジュール名を公開しない。
- この時点で原因DLL・メモリリークは未確定。新しい長時間測定・UST再ON・診断キット再配布に戻らない。出典: https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/interpreting-a-log-comparison


## 最優先CURRENT — 2026-11-18：実機UMDH原本/差分の形式件数確認済み、差分内の対応関係を調べる

- ユーザー本人が **UST解除・通常録画開始済み**と報告。録画停止、UST再ON、UMDH再Capture/Compare、再インストールは不要。
- ユーザー実測の読み取り専用の行数：**T1** `UMDH_RAW_PID9424_T1_20261117_223501.txt` 358550行 / BackTraceを含む71882行 / OriginalHeaders 0 / SymbolLines 0 / DiffRows 0。**T2** `UMDH_RAW_PID9424_T2_20261117_230044.txt` 357535行 / BackTrace 71018 / OriginalHeaders 0 / SymbolLines 0 / DiffRows 0。**DIFF** `UMDH_RAW_DIFF_PID9424.txt` 2853行 / BackTrace 182 / OriginalHeaders 0 / **SymbolLines 2366** / DiffRows 182。
- Microsoft公式 `Interpreting a UMDH Log`（https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/interpreting-a-umdh-log ）により、**取得RAWがシンボル未解決なのは通常あり得る**。差分に2366行の `module!function` 形状があるため、少なくとも一部の割り当て元を解決できている。**OriginalHeaders=0は旧スクリプトが検索した`by: BackTrace...`に一致しなかっただけ**。USTスタック欠落を断定しない。
- **従来のv5 safe summary**：182レコード、正差分693428B、負差分-736853B、純-43425B、正の上位3件380928/178176/94208B（94.2%）が `no-recognized-frames` だった。しかし原本/差分件数から、**プログラムが差分とスタックの配置・対応を正しく扱っていない疑いが強い**。測定成功/失敗をこの数値だけで断定しない。
- **次の1操作**：同じ保存済み `UMDH_RAW_DIFF_PID9424.txt` の差分ヘッダー上位3件について、**各行の前後30行のシンボル形状行数と差分行数のみ**を読み取り専用PowerShellで集計。行本文、BackTrace ID、アドレス、関数名、個人パスは表示・共有しない。得られた前後の構造を確認するまで次のv7ツールを作らない。
- その結果を踏まえ、必要なら既存差分ファイル内でBackTraceの対応を抽出する小さな安全パーサを一度だけ検討。Microsoft出力例：https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/interpreting-a-log-comparison と https://jpdscore.github.io/blog/debugging/UMDH/ 。原因DLL/真のメモリリークはまだ未確定。
- 絶対パスは非公開 `taku077/c545d-recorder-internal/docs/HANDOFF_CURRENT.md` のみ保管。公開側にWindowsユーザー名は記録しない。


## 最新CURRENT：2026-11-18 JST — 原本UMDH照合エラー、実データ形式の安全確認へ

- **ユーザーの最新実機結果**：`Resolve-ExistingUMDHBacktraces.ps1` を実行したが、155行目で `No recognized BackTrace section in offline UMDH output. No new capture required.` とエラー。`ctx.headers=0`となったという意味で、**保存済みRAW T2にスタックが存在しないとは断定できない**。
- Microsoft公式の `umdh [options] File1` 単独ログ解析構文は正しい。問題はUMDHの標準出力/標準エラーの内容や原本T2形式が、旧 `by: BackTrace...` というパーサの予測と一致したか未検証だったこと。PR #31のWindows CIは**合成データのみ**で、実機UMDH形式を保証しない。
- **次の1操作**：既存の `UMDH_RAW_PID9424_T1_20261117_223501.txt`、`UMDH_RAW_PID9424_T2_20261117_230044.txt`、`UMDH_RAW_DIFF_PID9424.txt` の行数・`BackTrace`行数・`by:BackTrace`行数・シンボルらしき行数・比較差分行数だけを**読み取り専用**PowerShellで計測。本文、関数、アドレス、実パス、認証情報は表示せず、集計だけ共有する。これでデータ形式を確かめる前にv7の解析ツールを推測で作らない。
- **録画と追跡状態**：ユーザーがUST解除を実行済みと報告し、**通常録画は開始済み**。録画停止/再起動、GFlags再Enable、UMDH再Capture/Compare、追加ソフトは必要ない。UMDH RAW/差分は保存。
- **既存解析値**：182差分、正693428B、負-736853B、正の上位3件380928/178176/94208B（正差分94.2%）、v5の`no-recognized-frames`は差分に隣接する行を見つけられなかったことしか示さない。原因ライブラリやメモリリークは未確定。
- 優先順位：**実機の形式を確認→その形式に合う安全な原本照合**。従来の`BackTrace`を想像した連続パッチ配布を避ける。公開repoは個人名を含む絶対Windowsパスを保存しない。


## 最優先CURRENT（2026-11-18 JST）— 通常録画復旧済み・既存UMDH原本とのBackTrace照合待ち

- **新しいユーザー確定報告**：「解除を実行して通常録画はもう開始している」。UST（GFlags +ust）はユーザーが解除操作を実行済みで、**通常録画は再開済み**。これを次回の起動確認待ちとして扱わない。録画再起動/停止・UST再有効化・再Captureを求めない。
- **前回までの最重要根拠**：PID9424のUMDH比較には182差分、正+693428 B、負-736853 B、差分合計-43425 B。上位3件+380928、+178176、+94208 Bの正差分（合計約94.2%）は旧v5スクリプトで`no-recognized-frames`、`nonempty_lines=0`となった。しかしこれは元のRAWにスタックがない意味ではない。
- **原因が分かった解析設計ミス**：Microsoft公式[Using UMDH to Find a User-Mode Memory Leak](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/using-umdh-to-find-a-user-mode-memory-leak)は、UMDH比較結果の`BackTrace`番号を**元の測定ログ**で検索するよう説明。旧v3/v4/v5の解析は差分出力の行の直後からスタックを探していたため、根本的に元のT2を照合していない。漏れ元を`unknown`と断定しない。
- **実装済みの再開作業**：公開GitHub [PR #31](https://github.com/taku077/c545d-recorder/pull/31) はmainマージ。`diagnostics/Resolve-ExistingUMDHBacktraces.ps1` が既存`UMDH_RAW_DIFF_PID9424.txt`の正の差分上位3件を選び、既存T2スナップショットを`umdh.exe T2ログ`で**オフライン解釈**し、BackTrace IDで照合する。RAWや録画に書き込みなし・`-p`新規キャプチャなし・UST/GFlags操作なし。実際のWindows UMDHによるT2シンボル解決はまだ未検証。
- **CI合格**：PowerShell5.1構文、合成テストでBackTrace番号結合・プライバシー除外をPASS（Actions runs [44116225097](https://github.com/taku077/c545d-recorder/actions/runs/44116225097) と [44116225189](https://github.com/taku077/c545d-recorder/actions/runs/44116225189)）。
- **ユーザーに渡すファイル**：`C545D_UMDH_OriginalStackJoin_20261118.zip`（GitHub CIから正規のプログラムを取り出し、照合用のps1と日本語READMEだけ入れたZIP。zip CRC検査済み）。新しいチャットに古いsandboxリンクを引き回さず、再取得して実在確認する。
- **次の1操作（録画継続のまま）**：ZIP展開したディレクトリで通常PowerShellから `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Resolve-ExistingUMDHBacktraces.ps1" -TargetPid 9424` を一度だけ実行する。出力は `%LOCALAPPDATA%\C545D_GStreamer\HeapTrace\C545D_SAFE_ORIGINAL_BACKTRACES_PID9424.zip` **のみ**チャットに提出。RAWログ・差分RAW・スタック・ソースパス等は提出しない。既存T2ログのオフライン解析時は一時的なCPU/ディスク負荷の可能性があるので録画優先。
- **今後の分岐**：元T2の3本のBackTraceが特定できれば安全なモジュール分類から絞り込む。元T2で見つからなければフォーマット・シンボル解決に問題がある可能性を整理する。メモリリーク原因は依然未確定、測定をやり直す根拠なし。
- 他の旧CURRENT（録画未復旧、v5の安全レポート作成待ち、UMDH `Capture` 待ち、GStreamerバージョン確認待ち）は**過去の履歴**であり、現在の手順ではない。次のチャットはこのCURRENTを最優先で参照する。ユーザー固有のWindows絶対パスは非公開リポジトリのみ。


## 最新の再開地点（2026-11-18 JST）— v5実機結果確認済み・録画復旧優先

- ユーザーが `C545D_HEAP_SAFE_REPORT_PID9424_V3.zip` を提出。ZIP CRC PASS、内部 `C545D_HEAP_SAFE_SUMMARY_PID9424_V3.txt` の実バイトを確認済み。**v5オフライン再解析は完了**。v3/v4/v5の再実行や新規Captureは不要。
- v5安全レポート実測：`parsed_backtraces=182`、`parsed_positive_delta_bytes=693428`、`parsed_negative_delta_bytes=-736853`、`parsed_net_delta_bytes=-43425`。正差分は `positive_no-recognized-frames_traces=27`、`bytes=693389`、`positive_recognized-non-system_traces=22`、`bytes=39`、Windows-runtime-only / other-module-symbol / address-like-no-symbol はそれぞれ0。
- 上位3件の正差分 +380928B、+178176B、+94208B（合計653312B、正差分の約94.21%）は全て `no-recognized-frames`、各 `nonempty_lines=0`、認識されたwindows/other/non-system/address行0。**元のUMDH生ログにフレームが全くないという証明ではない**：差分のヘッダーに隣接する行を現スクリプトが取得できない/別セクションにある等もあり得る。正差分の合計値を直ちに真のヒープ増加・リークと断定しない。
- Microsoft公式[UMDH比較解釈](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/interpreting-a-log-comparison)はBackTraceと対応コールスタックの調査が前提。これ以上パーサの推測修正やv6連続配布は優先しない。原本 `UMDH_RAW_DIFF_PID9424.txt` はローカルで保全し、必要時に**構造だけ**を非機密情報で診断する。RAW/スタック/ユーザーパスの送信は要求しない。
- **未解決で高優先度**：ユーザーは「録画ツールを起動できていない状態が続いている」と報告。UMDH用GFlags USTの解除を提案済みだが、**実際に `UST for gst-launch: OFF` となったか、通常のRC35が起動したかの結果はまだ提出されていない**。USTが起動失敗の原因だとは未証明。
- **次の実行優先順位**： (1) 既存 `HeapTrace.ps1 -Mode Check` でUST状態確認、ONならこの診断のマーカーがある場合に限り管理者PowerShellから `-Mode Restore`、(2) `Check`でOFF確認、(3) 通常ユーザー権限で既知のRC35 EXEを直接起動して録画復旧を優先、(4) 失敗時には起動メッセージ/ログで具体的原因を調査。診断用 `-Mode Launch` は使わない。古い/rawログの再測定、新たな長時間計測や追加キットは提案しない。
- 診断キットv5のCI PASSとPR #28は既にマージ済みで新規修正なし。旧版の実行先は非公開 `taku077/c545d-recorder-internal/docs/HANDOFF_CURRENT.md` に保持し、公開repoに絶対Windowsユーザー名を置かない。次回は本ブロック＋非公開ブロック＋ユーザー直近のUST/起動結果を最初に読む。



### **CURRENT 2026-11-18 — v4 Safe Report受領、v5オフライン分類テストPASS、実機v5実行待ち（これが最優先）**

- ユーザーが **`C545D_HEAP_SAFE_REPORT_PID9424_V2.zip`** をチャットに添付。実物ZIP/CRCと内部 `C545D_HEAP_SAFE_SUMMARY_PID9424_V2.txt` を直接読んだ。これは **v4キット**の出力（`V2`は安全レポートのスキーマ名）。**v3のUMDH Compareは既に成功した。再測定・再Compare不要。**
- **正確なv4レポート数値**：`parsed_backtraces=182`、`parsed_positive_delta_bytes=693428`、`parsed_negative_delta_bytes=-736853`、`parsed_net_delta_bytes=-43425`。`recognized_non_system_traces=81`、`other_module_traces=0`。上位正差分：+380,928B（rank1）、+178,176B（rank3）、+94,208B（rank5）で、合計653,312B（正差分の約94.21%）。**3件とも `unknown`**。上位30件で `glib-2.0-0` は5B、4B、3Bなどの小さい正差分のみ。この情報だけでglib原因・リーク確定とは言えない。
- **重要な解釈修正**：v4の `unknown` は「非システム系モジュールを認識できない」という意味にとどまる。`ntdll`/`kernelbase` 等Windows標準モジュールのみのスタックでも `unknown` になり、スタック不在・全シンボル欠落を意味しない。UMDHの純減はWindows Heap内で抽出した差分の合計で、Private Memoryの増加を否定しない。
- **実装済み修正**：[PR #28](https://github.com/taku077/c545d-recorder/pull/28) をmainにマージ。診断キットv5の **`Reanalyze-HeapDiff.ps1`** は既存 `UMDH_RAW_DIFF_PID9424.txt` を**読み取るだけ**で上位30差分を `recognized-non-system`/`windows-runtime-only`/`other-module-symbol`/`address-like-no-symbol`/`no-recognized-frames` に分類。関数・アドレス・未許可モジュール名・パスは出力しない。旧安全レポートは上書きせず、**`C545D_HEAP_SAFE_REPORT_PID9424_V3.zip`**を新規作成。
- **Windows CI成功**：GitHub Actions diagnostics run [44111276454](https://github.com/taku077/c545d-recorder/actions/runs/44111276454) はPS5.1構文、各種分類、秘密情報除外テストPASS。ソース検証run [44111276457](https://github.com/taku077/c545d-recorder/actions/runs/44111276457) PASS。**実機v5分類は未実施**。解析本体・録画への変更なし。
- **チャット直接添付済みv5キット**：`C545D_HeapTrace_Diagnostics_v5.zip`。GitHub Actions artifact `14340467488` の中身を取得・CRC検証済み。別会話に移った際は古い`sandbox`リンクを流用せずファイルの再検証/再取得を行う。古いActions個別URLは404の既往あり。
- **次の1操作**：v5キットを展開し、**通常権限PowerShell**から `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Reanalyze-HeapDiff.ps1" -TargetPid 9424` を1回だけ実行。生成された `%LOCALAPPDATA%\C545D_GStreamer\HeapTrace\C545D_HEAP_SAFE_REPORT_PID9424_V3.zip` **だけ**をチャットに提出。RAW/RAW差分/録画・個人パスをアップロードさせない。**再Capture、再Compare、録画停止、新規ソフト導入は不要**。
- Windows版GStreamer/録画RC35とPID9424の2枚RAW測定（22:35、23:00）は既知。次チャットは**この最新CURRENT最優先**→非公開handoffで正確なパス→直近ユーザー出力→GitHub HEAD/CIの順。古いv2/v3/v4の「次操作」は履歴であり再実行しない。


### 現在の最優先再開地点：2026-11-17 23:55 JST — 実機UMDH Compare成功・v4オフライン再解析待ち

- **ユーザーが `C545D_HEAP_SAFE_REPORT_PID9424.zip` を実際に提出**。ZIP CRC正常・安全要約テキスト1個を確認。実機 `-Mode Compare`（v3）は**成功**した。もう `-Mode Compare` をやり直す必要はない。
- **実測値**：PID9424、Private Memory `632.28 → 633.43 MB`（25.54分、+1.15MB、約+2.70MB/h）。Windows HeapのUMDH差分`parsed_backtraces=182`、`parsed_net_delta_bytes=-43425`（約−42.4KiB、解析されたWindows Heap差分の符号付き合計であってプロセスのPrivate総量ではない）。
- 安全レポートの上位**30件すべて `first_dll=unknown`**。原因モジュールやリークの所在は**未確定**。従来のレポート抽出器は `.dll!` を要求したが、UMDHは `ntdll!Function` のように拡張子なしシンボルを出力する場合があるため、unknownは元のRAWスタックに名前がない証明ではない。
- **改善PR #26** [GitHub](https://github.com/taku077/c545d-recorder/pull/26) は mainにマージ済み：`diagnostics/Reanalyze-HeapDiff.ps1` を追加。ローカル既存 `UMDH_RAW_DIFF_PID9424.txt` **のみ**読み取り、モジュール識別子を安全に再抽出する。録画本体・GFlags/UST・UMDHキャプチャは変更なし。
- Windows PowerShell 5.1構文・合成差分/PII除外のCIは成功：[Actions run 44108444584](https://github.com/taku077/c545d-recorder/actions/runs/44108444584)。**実際のRAW diffに解決済みシンボルが入っているかはまだ不明**。実機再解析結果を待つ。
- **v4キット**：GitHub Actionsの実体を取得し、二重ZIPを解消した `C545D_HeapTrace_Diagnostics_v4.zip` をこのチャットに添付済み。新しいチャットで古い sandbox パスは再利用せず、存在検証または再取得する。以前の404になった個別Actionsリンクを再案内しない。
- **次の唯一のユーザー操作**：v4キットを展開し、通常権限PowerShellで `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Reanalyze-HeapDiff.ps1" -TargetPid 9424` を実行。`%LOCALAPPDATA%\C545D_GStreamer\HeapTrace\C545D_HEAP_SAFE_REPORT_PID9424_V2.zip` **だけ**チャットへ提出。`V2`は安全レポートスキーマで、キット版はv4。実行するps1は既存の `HeapTrace.ps1` **ではない**。
- **禁止/不要**：二つのUMDH生ログの再Capture、再Compare、録画停止・再起動、新たなソフト導入、RAW差分やスタック/ユーザーパスの公開。UST管理のRestoreは前段説明の通り必要時のみ。現在UST状態は未確認。
- **次回チャット開始時**、この最新セクション→非公開hand-off（フォルダ絶対パス）→直近ユーザーのv4実行結果→GitHub HEAD/PR/CIを読む。下に残るv3/v2の指示は履歴として扱い、差分解析以前に戻らない。


### 最新の再開地点：2026-11-17 — HeapTrace v3 UMDH標準エラー問題を修正（次の実機Compare待ち）

- **新しい実機エラー**：ユーザーは修正v2を `-Mode Compare` 実行すると、`HeapTrace.ps1` **279行**で `umdh.exe : Warning: The -v switch is obsolete. Verbose is always on.` および `NativeCommandError` が発生したと報告。**文字化けパス復旧は少なくともUMDH起動まで進んだ**が、UMDHの差分比較はまだ成功していない。
- **新しい修正v3**：[PR #24](https://github.com/taku077/c545d-recorder/pull/24) はmainにマージ済み。UMDH比較から廃止済み `-v` を削除、Windows PowerShell 5.1の `2>&1` と `ErrorActionPreference=Stop` によるstderr警告の例外化を回避。標準出力/標準エラーを.NET ProcessStartInfoで別取得し、終了コード判定＋raw stdoutの保存を実装。
- **Windows CI PASS**：PowerShell 5.1構文、既存の日本語JSON復旧・曖昧拒否、安全parser、さらに**stderrに警告/終了0なら継続、終了19なら失敗**の合成テストPASS。GitHub Actions [HeapTrace test](https://github.com/taku077/c545d-recorder/actions/runs/44106226506) と [source validation](https://github.com/taku077/c545d-recorder/actions/runs/44106226459)。実機の差分完遂/Heap割当元/録画安定性は**未検証**。
- **実体を確認したv3 ZIP**：`C545D_HeapTrace_Diagnostics_v3.zip` を同じチャットに添付済み（GitHub Actions実体取得→二重ZIP解除、3ファイル・CRC・コード内容検証）。**新しいチャットで旧sandboxパスを流用しない**。ユーザー側へv3展開を案内したが、実際の展開は未確認。
- **次の1操作**：ユーザーがv3を展開後、**通常権限PowerShell**でv3の `HeapTrace.ps1 -Mode Compare` を1回だけ実行。例えば `%USERPROFILE%\Downloads\C545D_HeapTrace_Diagnostics_v3\HeapTrace.ps1`。**PID9424のT1/T2再Captureはしない、録画EXEは変更しない。** 成功なら `%LOCALAPPDATA%\C545D_GStreamer\HeapTrace\C545D_HEAP_SAFE_REPORT_PID9424.zip` だけを受け取り解析。失敗時はその新エラーに限定して修正する。
- **保存先の区別**：v3スクリプト展開先は例示で、ユーザー申告のv2展開先・旧キット・RC35 EXE・RAWデータ保存先とは別。既知の**正確なローカルパス**は非公開引継ぎ文書に記載、公開側にユーザー名は載せない。
- UMDHの比較stderrが出た場合ローカルに `UMDH_RAW_DIFF_PID9424.stderr.txt` が残り得る。RAW・stderr・MP4・個人設定ファイルは公開しない。**安全ZIPのみ提出**。USTがまだ有効でこのキットの管理下なら検証後に管理者PowerShellで `-Mode Restore`。
- これ以前のCURRENTブロック内「v2をダウンロードして比較する」という説明は**v3に置き換わった**。旧v2は今回の警告バグを含む。根本のネイティブメモリ増加はまだ未解決。


## 旧時点の作業要約（2026-11-17）— 直上のv3修正が優先

**再開地点はRC35 GStreamer録画のUMDHヒープ差分比較。VMMap・新規計測・GStreamerバージョン確認には戻らない。** 会話名「tapo録画2」「tapo録画3」「続きを再開」でこのプロジェクトを指す場合、まずこのブロックと非公開 companion の同名ファイルを読む。履歴セクションには旧日付の `IMMEDIATE NEXT STEP` が残るが、その指示は失効している。

### ユーザーから得た確定事実（再質問しない）
- Windows 10 Pro / Windows PowerShell 5.1、日本語を含むユーザープロファイル。GStreamer h264parse は 1.28.8.1（確認済み）。
- Microsoft Debugging Tools x64 (gflags.exe / umdh.exe) は導入済み。GFlags UST を有効化してから実測した。今現在のUST有効状態は未確認。
- **録画RC35 EXEの既存展開先**：`%USERPROFILE%\Downloads\C545D_EXE_SEI_Default_ON_Win10_x64\C545D_Recorder.exe`。ユーザーが申告した正確な絶対パスは**非公開** companion に記録。旧バージョンを勝手に消去/置換しない。
- **旧HeapTraceキットの既存展開先**：`%USERPROFILE%\Downloads\C545D_HeapTrace_Diagnostics_Kit\`、そこに `HeapTrace.ps1`。この旧フォルダー内スクリプトがv2に置換済みとは**未確認**。絶対パスは非公開 companion に記録。
- **スナップショットの保存先**：`%LOCALAPPDATA%\C545D_GStreamer\HeapTrace\`（`snapshots.json` と生UMDHログ）。これはキットの展開先とは**別**の場所。
- 同一PID **9424** のRAWログが**2個とも実在**：`UMDH_RAW_PID9424_T1_20261117_223501.txt`（7525.9 KiB、2026-11-17 22:35:13 JST）、`UMDH_RAW_PID9424_T2_20261117_230044.txt`（7480.6 KiB、23:00:45 JST）。
- `snapshots.json`: `FirstRecorded=True`, `SecondRecorded=True` だが `FirstFileOK=False`, `SecondFileOK=False`。`-Mode Compare` は旧版で「Two captures of one process are required」と失敗。生ログが欠落していると推測しない。

### GitHub修正と実機未確認部分
- 修正PR **#22** `fix/heaptrace-utf8-json-recover-existing-pid9424` は **2026-11-17 mainへマージ済み**。`diagnostics/HeapTrace.ps1` はUTF-8でJSON読込、既存PID/T1/T2の唯一候補を復旧、曖昧なら拒否、`umdh -v` 差分、正常時のみ安全な結果ZIPを生成。
- Windows PowerShell 5.1構文テスト / 日本語フォルダーUTF-8読み書き / 旧パス復旧 / 曖昧候補拒否 / safe parser はCI **PASS**：`https://github.com/taku077/c545d-recorder/actions/runs/44102088473` およびPowerShellソース `https://github.com/taku077/c545d-recorder/actions/runs/44102088323`。**実機UMDH差分比較は未実施**。
- 修正版診断v2 ZIPは直前のチャットでGitHub Actions実体から取り寄せ、**チャット内のsandbox添付**として提供済み。ただし sandbox のパスは新しい会話で有効とは限らない。古い **GitHub Actions artifact個別リンクはユーザー環境で404**。有効なReleases配布が検証できない場合はGitHubコネクタから現物を再取得し、**実ファイルの存在を確認したうえで**新しいチャットに直接添付すること。リンクを推測しない。

### 次の1操作（ユーザー側）
1. **v2の `HeapTrace.ps1`** を含む診断ZIPを展開。旧展開先がv1のままかもしれないので、v2版を実行していることを確認する（録画EXEを更新する必要はない）。
2. 通常権限PowerShellでそのv2 `HeapTrace.ps1` のあるフォルダーを開き、`powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\HeapTrace.ps1" -Mode Compare` を**1回だけ**実行。スクリプトは既存 `%LOCALAPPDATA%` にあるPID9424の2ログを検索する。
3. 成功したら `C545D_HEAP_SAFE_REPORT_PID9424.zip` のみこのチャットに提出。`UMDH_RAW*.txt` や `UMDH_RAW_DIFF*.txt`、カメラ設定/資格情報は提出・公開させない。失敗時はエラーメッセージのみを確認し、再Captureを安易に要求しない。
4. 調査後、USTがまだONなら管理者PowerShellでv2の `-Mode Restore` を実行（以前この診断キットでEnableした場合）。録画を強制終了しない。

### 目的・不変条件と進行ルール
- 根本目標は継続録画時のPrivate/Heapメモリ増加の**割当元特定**。過去VMMapでは約18分でHeap committed +5.64 MiB、長時間Private増加は約6–8MB/h。ただし**リーク未断定**。
- Tapo C545Dの広角stream1＋望遠stream6を1画面で同期録画。2560×720/15fps、x264 medium/Q24、`avdec_h264`、AAC 48kHz、1時間MP4、正常EOS/再開、SEIフィルタ既存動作を不用意に変更しない。日次強制再起動や24–48h再測定を安易に提案しない。
- 次チャットでは**最初に**(1)この最新ブロック、(2)非公開hand-off（個人パス）、(3)最新のユーザー出力、(4)GitHub main/CI/PRを照合する。**確定/推定/未検証**を分け、すでに回答済みのフォルダーや設定を再質問しない。
- 状態が変わったら**このブロックと非公開側の先頭ブロックを同じターンで更新**し、日時・実際の保存場所・今止まっているエラー・次の操作・提供リンクの有効性を更新する。末尾の追記だけで済ませない。
- 公開repoにユーザー名を含む絶対パス・生ログ・IP/認証情報を記録しない。非公開側に記録したパスも公開PRへ転記しない。

**参照**: [PR #22](https://github.com/taku077/c545d-recorder/pull/22) / [Issue #21](https://github.com/taku077/c545d-recorder/issues/21) / [診断README](https://github.com/taku077/c545d-recorder/blob/main/diagnostics/README_HEAP_TRACE_JA.md) / private `taku077/c545d-recorder-internal:docs/HANDOFF_CURRENT.md`。
<!-- CURRENT_HANDOFF_END -->

---

## 以下は過去の調査記録（上記CURRENTに優先しない）


**Last updated:** 2026-11-16 (JST)  
**Purpose:** Canonical cross-chat handoff. When the user says **「続きから再開してください」** in the context of the C545D recorder, **read this document first**, inspect the current GitHub HEAD/CI/PRs and continue from the next action rather than restarting diagnosis.

## Confirmed user environment result — 2026-11-16 (supersedes previous version blocker)

- The read-only process-path-based `gst-inspect-1.0 h264parse` check **succeeded**.
- Reported `h264parse` plugin version: **1.28.8.1**.
- The GStreamer installation is a **per-user Windows MSVC x86_64 installation** under Local AppData (do not publish the personal Windows account name or absolute path).
- Because upstream fixed `gst_h264_parser_parse_nal()` in **1.28.2**, the inspected 1.28.8.1 plugin is expected to **already contain that fix** in a standard official build. The specific previously suspected parser leak therefore drops in priority as explanation of the observed residual growth; do NOT recommend updating the runtime on the basis of that fix alone.
- The command also emitted warnings: `External plugin loader failed` and `Failed to load plugin gstpython.dll` (unresolved DLL dependency). These warnings refer to the plugin-scanner helper and Python binding plugin, **not evidence that H.264 parsing or the active recording failed**. The requested `h264parse` version was returned successfully. The recorder does not directly require `gstpython.dll`; do not delete DLLs or reinstall while recording.
- This version verification **completes the previous immediate blocker**. Do **not** ask for this same version again unless the installed GStreamer changes.
- **Next engineering task:** investigate the still-unexplained positive private-memory slope, checking current 1.28.8.1 components and actual object lifetime, allocator/RTSP and muxer behavior, before proposing a targeted fix. Preserve `avdec_h264` CPU improvement and current A/V sync/recording settings. Do not add speculative diagnostic loops or daily auto-restarts.
- The currently running recording is unaffected by the PowerShell inspection. No GitHub code changes to the recorder were needed for the version check.
- References: https://gstreamer.freedesktop.org/releases/1.28/ ; https://gstreamer.freedesktop.org/documentation/installing/on-windows.html ; https://discourse.gstreamer.org/t/user-getting-error-priv-gst-plugin-load-file-for-registry-module-open-failed/4499

## Canonical repositories
- Public source and GitHub Actions: https://github.com/taku077/c545d-recorder
- Private sanitized development notes: `taku077/c545d-recorder-internal` (requires connected GitHub access).
- Public issue for long-run stability: https://github.com/taku077/c545d-recorder/issues/1 (OPEN).
- Merged PRs: [#2](https://github.com/taku077/c545d-recorder/pull/2) baseline regression checks; [#3](https://github.com/taku077/c545d-recorder/pull/3) GStreamer core version logging and existing CSV analyzer; [#4](https://github.com/taku077/c545d-recorder/pull/4) H.264 parser plugin version reporting and upstream leak eligibility note.
- Last verified public `main` when this was authored: `d3854fe98421a6f6b2d92c2819f3844792921374`. Check the live HEAD before editing; do **not** assume it remains unchanged.
- Last verified successful Windows CI: https://github.com/taku077/c545d-recorder/actions/runs/43852965696 (syntax, invariants, synthetic tests, ZIP packaging; NOT a real camera recording test).

## User's goal and non-negotiable constraints
- 24 hours/day, 365 days/year unattended security recording from Tapo C545D, combining two RTSP feeds into **one** video with efficient storage.
- Wide `stream1` on left, telephoto `stream6` on right. Preserve 2-stream time synchronization, audio continuity, one-hour MP4 segments, safe stop/restart and file naming.
- x264 **medium**, quantizer **24**, **2560×720**, **15fps**; AAC mono 48kHz / 192kbps target. Do not silently switch to fast, GPU decode or unrelated new technologies.
- Priority was NOT a low instantaneous CPU percentage, but **CPU usage increasing with elapsed recording time**. This improved substantially after preferring `avdec_h264` over `openh264dec`. Do not undo that baseline.
- Next open technical objective is **private-memory growth over time**, without reducing video/audio quality or causing recording gaps.
- No forced daily/periodic restart as an alleged fix; preserving evidence continuity matters.
- Eventually port to C# WinForms EXE with public Windows GitHub Actions; **not yet** and not until the existing pipeline is stable. No Visual Studio/.NET SDK required on the end-user recording PC.

## Known empirical results (sanitized aggregates only)
- New `avdec_h264`-preferred run: around **15h23m**, measured CPU around **19–21%** over hourly windows; private memory **593.7MB to 706.1MB**.
- Post-six-hour regression: approximately **+6.17MB/hour**, R² about **0.9965**. No plateau observed; no established root cause.
- Earlier `openh264dec`-preferred run had rising CPU toward ~40% and much faster memory growth.
- The working pipeline includes three `h264parse` elements; earlier ETL analysis reported allocation paths through `gstvideoparsersbad.dll`.
- GStreamer 1.28.2 release notes identify a fix for a memory leak in `gst_h264_parser_parse_nal()` (issue #4966 / MR !11060). **Candidate only**, not proof of causality; possible downstream backports.
- Current recorder's installed GStreamer core / h264parse plugin versions have **not yet been established**.

## IMMEDIATE NEXT STEP (current blocker, 2026-11-16)
The user tried a previous PowerShell path check and received **「GStreamerが見つかりません」**. The failed command only searched three assumed directories, so this **does not establish that GStreamer is absent**. The working recorder itself previously found GStreamer (`Record.ps1` also has a `Get-Command` fallback).

Ask for the output of this **read-only** PowerShell command, preferably **while recording**, which derives the actual `gst-inspect-1.0.exe` path from the running `gst-launch-1.0.exe` process:

```powershell
$p = Get-CimInstance Win32_Process -Filter "Name = 'gst-launch-1.0.exe'" | Select-Object -First 1
if ($p -and $p.ExecutablePath) {
    $gst = Join-Path (Split-Path $p.ExecutablePath -Parent) 'gst-inspect-1.0.exe'
    if (Test-Path -LiteralPath $gst) {
        & $gst h264parse | Select-String '^\s*Version\s+'
    } else { Write-Host "gst-inspect.exeが同じフォルダーにありません" }
} else { Write-Host "録画中のGStreamerプロセスが見つかりません" }
```

Interpretation:
- Plugin version **1.28.2 or newer** in the 1.28 branch: upstream parser fix expected to be present; look at other causes if memory still increases.
- Plugin **older**: relevant upstream fix might be missing; check backports and compare supported, verified official MSVC x64 GStreamer runtime **side by side** with rollback and **only after safe stopping**, never during a live recording.
- If process not present, don't claim it is uninstalled. Check whether recording is actually active; alternatively use `Get-Command gst-launch-1.0.exe` and existing log, without full HDD searches.
- If version output unavailable due to permissions, may use `Get-Process` `Path` or point-and-click Task Manager -> open file location.

## Working-code scope and guardrails
- User launcher: `C545D_Start.vbs`.
- GUI: `C545D_App.ps1` ; recorder: `Record.ps1`; worker: `RecordGUIWorker.ps1`; filename processing: `SegmentNamerWorker.ps1` / `SegmentNamer.ps1`; settings helper: `CommonSettings.ps1`.
- `Record.ps1` on current GitHub main logs `GStreamer runtime:` and `H264 parser plugin (videoparsersbad):` **at next startup only** (current already-running recorder will not automatically obtain new logging).
- Never claim CI proves actual 24x365 stability. Changes go in feature branches, are checked on `windows-2022` CI and PR, then merged if supported; `main` is a known-good candidate baseline.
- Public repo may be read by anyone; no camera credentials, local IP, usernames/passwords, `settings.json`, `camera_password.dpapi`, recorded media, ETL, or raw diagnostic logs in either repo. Sanitize any analysis.

## To resume reliably
1. Read **this** file and, if accessible, the private `docs/HANDOFF_CURRENT.md`.
2. Check current GitHub main SHA, Issue #1, open PRs and latest CI.
3. Continue from current blocker / user-supplied version result; don't re-ask already answered constraints or repeat costly diagnostic loops.
4. If the user only says **「続きから再開してください」** and multiple ongoing projects make the reference ambiguous, confirm this is the C545D recorder rather than silently choosing another project.


## Follow-up: plugin scanner file exists (2026-11-16 JST)
- User confirmed the PowerShell scanner existence probe returned **「補助プログラム：存在します」**.
- Therefore, `gst-plugin-scanner.exe` is present at the path derived from the actual running GStreamer executable. The earlier warning `External plugin loader failed` means it could not be launched/used in that invocation; **file absence is ruled out**, but missing DLL dependencies, environment PATH/scanner configuration, permissions, etc. remain possible.
- `gstpython.dll` failed to load with Windows' missing-module message. This can indicate a dependency of that DLL is absent; it does NOT prove the plugin file itself is missing. This optional Python plugin is not directly required by the C545D recorder pipeline.
- **Next safe test**: run `gst-inspect-1.0 h264parse` from the currently running GStreamer executable's directory in a separate PowerShell process/session with temporary, process-local `PATH` prepended with its `bin` folder and `GST_PLUGIN_SCANNER` set explicitly to the existing scanner path. Do not write system environment variables or interrupt live recording. Compare warnings; note registry caching can suppress re-scans, so absence of warning in one run is not definitive.
- If warning persists under correct environment, focus on missing dependency or scanner execution failure; do NOT reinstall or delete DLLs speculatively. Preserve `avdec_h264` stability and long-run memory work.
- Official docs: https://gstreamer.freedesktop.org/documentation/installing/on-windows.html ; https://gstreamer.freedesktop.org/documentation/gstreamer/running.html


## Repeated scanner warnings with process-local environment — 2026-11-16 JST
- User reran `gst-inspect-1.0 h264parse` with the **actual running** `gst-launch` binary directory prepended to `PATH` and `GST_PLUGIN_SCANNER` pointed explicitly at the existing scanner executable. **Both warnings persisted**: `External plugin loader failed` and `Failed to load plugin ... gstpython.dll` (Windows reported missing module). `h264parse Version 1.28.8.1` was returned again.
- A simple omitted `PATH` or `GST_PLUGIN_SCANNER` setting is therefore **not enough** to explain/fix the symptoms. Do not repeat that test or claim the complete install failed.
- Scanner existence was previously confirmed, but not that it executes successfully; DLL/CRT dependency, plugin scanner start failure, plugin path/registry issues remain hypotheses. `gstpython.dll` is optional for this recorder and may have a missing transitive dependency.
- Upstream `gstregistry.c` falls back to in-process scanning if external loader fails, explaining how required plugins can remain available. Matching discussion: https://discourse.gstreamer.org/t/user-getting-error-priv-gst-plugin-load-file-for-registry-module-open-failed/4499 . Official Windows setup: https://gstreamer.freedesktop.org/documentation/installing/on-windows.html
- **Recommendation:** Do not delete `gstpython.dll`, globally set `GST_REGISTRY_FORK=no` as if that fixed the root cause, delete the plugin registry cache, reinstall, or interrupt currently working evidence recording just to silence warnings. These messages have **not** been tied causally to the remaining +6.17MB/h private-memory growth.
- **Next action:** Keep working recorder unchanged. If a specific necessary recording element fails or the user prioritizes warning repair, diagnose the exact failing helper/DLL dependency using a bounded, evidence-driven test before recommending a repair; otherwise prioritize identifying long-run memory growth separately.


## EXE migration stage 1 built — 2026-11-16 (user requested pivot while memory runs)
- On 2026-11-16 user suggested checking private-memory trend **tomorrow (2026-11-17)** after a longer recording, and doing EXE work meanwhile. Respect this ordering. Do not infer residual leak fixed from the EXE build.
- Public [PR #5](https://github.com/taku077/c545d-recorder/pull/5) was **merged** (main commit `fac5263676e5f687214a8365c13475692ca985a9`). C# `.NET Framework 4.8` x64 `WinExe` was created at `src/C545D.Launcher/`. In this **stage-1 launcher**, `C545D_Recorder.exe` launches the **existing PowerShell WinForms GUI** (script `C545D_App.ps1`) in hidden STA PowerShell and sets `C545D_VIDEO_DECODER=avdec`; it exits while the original app manages the session.
- The nine existing .ps1/.vbs/README baseline files were not edited in this PR. Stop markers, CTRL+C→EOS, RTSP pipeline, AAC, 2560×720/15fps, x264 medium/Q24 and filename handling stay unchanged.
- New workflow `.github/workflows/build-exe.yml` uses `windows-2022` and `microsoft/setup-msbuild@v3` to build, package and smoke-test in a Unicode directory **without connecting to a camera**. PR CI passed: https://github.com/taku077/c545d-recorder/actions/runs/43863192829 . Main workflow: https://github.com/taku077/c545d-recorder/actions/runs/43863396922 ; job passed.
- Main workflow generated artifact named `c545d-exe-win10-x64` containing `C545D_Recorder_EXE_Win10_x64.zip`, with `C545D_Recorder.exe` and nine original source files. Current artifact expires 2026-11-23 UTC; download from the workflow run's **Artifacts** section while signed into GitHub. It may require unzipping the artifact wrapper then the app ZIP.
- Critical truth: this is **an EXE launcher**, not a complete C# WinForms controller or standalone single-file recorder; it still requires the bundled PowerShell scripts and separately installed GStreamer. No real Windows 10 camera recording validation yet. Do not instruct running it in parallel with currently active recorder.
- User's Windows 10 22H2 has `.NET Framework 4.8` as part of the OS, so no extra .NET runtime or Visual Studio should be needed. Source: https://learn.microsoft.com/en-us/dotnet/framework/install/on-windows-10 .
- Follow-on work is tracked in [Issue #6](https://github.com/taku077/c545d-recorder/issues/6): native C# WinForms **UI/control** port while retaining the working PowerShell/GStreamer back-end until confirmed stable. Preserve optional rename worker and safe stop/EOS semantics; test state transitions before on-device deployment.
- Tomorrow's memory review: use the **existing** local `Memory_Trend.csv` (or sanitized aggregate) over the extended session. Compare post-warmup private-memory slope with prior ~+6.17 MB/hour and check plateau without disrupting recording. Do not demand repeated costly diagnostics if existing data suffices.


## Memory mitigation candidate PR #7 — 2026-11-17 JST
- User explicitly requested an actual code change, without installing further diagnostic tools or repeating 24–48h waiting loops.
- Two VMMap snapshots from the same gst-launch PID (4820), about 18m04s apart, showed Heap committed roughly +5.64 MiB, with existing Heap about +3.39 MiB and one new Heap region about +2.23 MiB. This **does not identify** the allocating plugin, prove a leak or establish that any one branch caused the increase.
- PR #7 changes only the **discarded** telephoto/stream6 RTP audio branch in Record.ps1: queue max-size-buffers=8/max-size-bytes=262144/max-size-time=250000000/leaky=downstream; fakesink enable-last-sample=false. Default GStreamer queue was already bounded (200 buffers/10 MB/1 s); do not claim the old queue was unbounded.
- Recorded stream1 AAC, both videos, avdec_h264, x264 medium/Q24, 2560x720/15fps, NTP/tcp sync, splitmuxsink hourly segments, stop/EOS are not changed.
- This is a concrete retention-reduction patch, **NOT a verified fix for the residual Heap slope**. No real camera test or 24×365 validation was performed by public CI.
- If build/CI passed and main was merged, use new main artifact only at a safe stop, preserving rollback to 2026-11-16 known-good baseline. Do not run the old and new recorders simultaneously.
- No further user-installed tool is required for this candidate. Actual slope/quality changes require comparing existing Memory_Trend.csv over the same PID and checking MP4/AAC/dual-lens sync on the user PC.


## Stage 2 native WinForms EXE — 2026-11-17 JST (PR #8)
- User reported **stage-1 launcher EXE successfully starts recording on their PC**. This is a user-observed start/record result, NOT a passed stop/EOS/restart/long-run test.
- The Stage-2 candidate replaces the stage-1 PowerShell GUI launcher with a **native C# WinForms controller** in src/C545D.Launcher/RecorderForm.cs. It retains the UNCHANGED Record.ps1/RecordGUIWorker.ps1 media path and original C545D_App.ps1/C545D_Start.vbs as rollback.
- Native controller includes camera settings, same-user DPAPI secret via stdin-only PowerShell C545D_SettingsBridge.ps1, session-specific stop/ready markers, console Ctrl+C and GStreamer -e EOS, optional event-driven rename worker, restart after stop, tray actions, memory CSV and explicit emergency stop.
- No modification to x264 medium, Quantizer 24, 2560×720/15fps, avdec_h264 preference, AAC, dual RTSP NTP/tcp timestamp or hourly MP4 splitting.
- Public Windows GitHub Actions verifies compilation, synthetic native GUI startup and synthetic DPAPI round-trip. It CANNOT prove real-camera EOS stop, MP4 playback, RTSP sync or 24×365 stability. The user must preserve old stage-1 app until a normal real-PC stop→restart check is completed at a safe stop opportunity.
- Artifact accessibility: user reported **Actions > Artifacts did not expose a clickable download**, despite existing artifacts. GitHub docs require a signed-in account with read access for Actions artifacts and note expiry. Stage-2 workflow publishes a numbered **prerelease asset** to https://github.com/taku077/c545d-recorder/releases after successful push to main; direct ZIP links from Releases are the preferred download path. Also attach ZIP directly in ChatGPT when possible.
- This migration is NOT evidence that the unexplained private Heap increase (+5.64 MiB in ~18min VMMap comparison, historical post-warmup +6.17 MiB/h) has been fixed. Do not add user-installed diagnostics or 24–48h waiting loops as a default.
- Confirm GitHub main HEAD / PR #8 merge / release asset URL / live CI before continuing. The last known working stage-1 build is separate; never run both versions simultaneously.


## 2026-11-17 — RC11 interrupted-recording recovery
- Existing user logs: Native GUI worker PIDs 660, 11292, 11120 ended with `GStreamer returned; exitCode=0; stopMarker=False`, while gst-launch reported `handling interrupt`. Cause of unsolicited console events is **not proven**; native Stage 2 displayed a console and RC10 addressed it.
- Previously Record.ps1 treated any C545DWorkerStopSignal.StopRequested as an authorized stop and also treated gst exit-code 0 as terminal for a managed session. This can silently end an evidence capture without the GUI stop marker.
- RC11 only recognizes the per-session durable GUI `.stop` marker as authorized. Unexpected `CTRL_C_EVENT` or any unexpected GStreamer exit now follows existing bounded backoff/reconnect, even when gst exits code 0. Preserve standalone PS1 Ctrl+C behavior when no control session exists.
- Worker counts console control events via atomic counter (no I/O in control handler); logs `consoleCtrlCEvents`, `UNEXPECTED_CTRL_C`, `UNEXPECTED_GSTREAMER_EXIT` and explicit exit-policy. Native WinForms shows a red status and logs `UNEXPECTED_WORKER_EXIT` if the worker itself dies without a stop request.
- Unit tests for pure exit policy are executed in Windows CI without connecting cameras; original source invariant tests, native UI, DPAPI and EXE smoke tests remain. No recorder format/quality/synchronization change. Unknown real-camera success; do not claim a fixed memory leak or resolved libav/qtmux issue.
- Never run two recorders simultaneously. Keep RC10 as rollback and switch only after normal stop/EOS finalization.


## 2026-11-17 — RC13 H264 decoder / muxer timestamp errors
- User clarified that CTRL+C on visible Stage 2 console was **manually pressed by the user** because of error output; it is NOT evidence of unsolicited interruptions. Do not present worker PIDs 660/11292/11120 as spontaneous CTRL+C. Previous attribution in RC12 plan was incorrect. RC12 reconnect code remains in main for now, but the requested RC13 work **specifically targets repeated libav 'no frame!' and qtmux 'decreasing DTS'**, not UI/stop controls.
- FFmpeg H264 decoder's 'no frame!' is produced when no decodable slice/frame is present in packet; the RTSP logs show repeated examples near camera GOP cadence for both inputs (see GStreamer official docs and libavcodec h264dec.c source).
- Before RC13 parser used config-interval=-1 (reinsert SPS/PPS at each IDR). RC13 conditionally switches to config-interval=0 + byte-stream,alignment=au after rtph264depay; tests with synthetic RTP stream before camera startup, logs strategy; C545D_H264_INPUT=legacy rollback.
- qtmux decreasing DTS may be video or AAC; RC10's optional h264timestamper protects encoded video DTS but does not ensure AAC timestamp monotonicity. RC13 conditionally inserts audiorate skip-to-first=true tolerance=40000000 in stream1 decoded audio before AAC, with an AAC/MP4 synthetic preflight; C545D_AUDIO_TS=legacy rollback. This may insert/drop samples at discontinuities.
- No changes to video x264 medium/Q24, 2560×720 15fps, two NTP-linked sources, AAC target, 1h MP4 split, or stop/EOS. No filtering or suppression of GStreamer error messages.
- Synthetic pipeline success demonstrates negotiation only. It is **not proof** that camera-specific libav errors, MP4 DTS, or increasing Heap usage are fixed. Do not claim production validation.
- No extra user software installations or destructive MP4 testing. Existing worker transcript will show H264 RTP input guard, AAC timestamp guard and MP4 DTS guard states.


## 2026-11-17 — RC16 opt-in media diagnostic launcher
- User consented to a comprehensive evidence-first investigation, with tool/log requirements declared upfront, focused on `libav: no frame!`, `qtmux decreasing DTS`, and subsequent Heap retention.
- PR adding `START_DIAGNOSTIC.cmd`: no recorder pipeline edits, no new tools, and no debug logging in normal EXE start. Run only after normally stopping any active recorder.
- Launcher sets `GST_DEBUG=*:2,rtph264depay:5,h264parse:5,rtpjitterbuffer:4,qtmux:5,audiorate:4,splitmuxsink:4`, `GST_DEBUG_FILE=%LOCALAPPDATA%\C545D_GStreamer\Logs\GST_DIAG_%p_%r.log`, `GST_DEBUG_NO_COLOR=1` **only for subprocesses started from launcher**. Each child process gets unique file by PID/random. On short (~5–10min) diagnostic recording, provide Recording_*.txt, relevant largest gst-launch GST_DIAG_*.log (after checking for any RTSP credentials), optional Stop_Control.log only for genuine stop problem, Memory_Trend.csv if memory is focus.
- GStreamer official documentation confirms debug categories and GST_DEBUG_FILE %p and %r substitution. Do not assume warning-count=damaged frame-count; first attribute to stream and actual decoder damage.
- No extra tools now. If Heap cause demanded later, Microsoft Debugging Tools package GFlags+UMDH should be disclosed as one staged dependency (needs per-image UST prior to process launch). Wireshark already present optional for evidence of network packet anomaly.
- Stage RC16 is *diagnostic capture only*, not a cure for existing decode/DTS or Heap warnings.


## 2026-11-17 — Privacy-preserving diagnostic export
- User wants to upload logs directly to ChatGPT but correctly notes manual credential searching through enormous `GST_DIAG_*.log` is too much work.
- Added `EXPORT_SAFE_LOGS.cmd` + `Export-SafeDiagnostics.ps1`: schema-only allowlist export, no raw log lines, URLs, passwords, user names, local paths, raw debug text, or MP4 bytes in the ZIP. Scans latest 8 matching log files, up to 400k lines each, caps exported events at 18k; emits `summary.txt` and `media_events.tsv` to `C545D_SAFE_DIAGNOSTICS_<time>.zip` in Downloads. No admin/additional software. Source log and recordings are read-only.
- Synthetic Windows CI test includes literal credential, RTSP URI, IP and base64 token and verifies ZIP excludes them while retaining `LIBAV_NO_FRAME` and `QTMUX_DTS_BACKWARD`.
- Scope: lossy diagnostic extract; it may not suffice to distinguish audio/video pad or precise H264 AU issue. If insufficient, enhance safe allowlist (not ask user to browse raw logs manually). Never claim generic redaction guarantees all arbitrary log text.
- User should upload safe ZIP to existing ChatGPT conversation only; no raw log into public GitHub issues. Personal ChatGPT data controls may affect training and retention; avoid categorical security guarantees.


## 2026-11-17 — Safe ZIP first actual user capture, exporter V2
- User uploaded `C545D_SAFE_DIAGNOSTICS_20261117_182408.zip` (schema only: media_events.tsv + summary.txt). We inspected exact bytes in current turn. Original V1 exporter selected 8 logs, `LOG_02` read 400000 lines then stopped. It exported the first 18000 events, of which 15446 were routine DEBUG_SAMPLE, 2553 LIBAV_NO_FRAME (about 0.5s through 115.15s), one DISCONTINUITY. Summary counted 4242 LIBAV_NO_FRAME (including events not exported). No QTMUX_DTS_BACKWARD in exported subset, which does **NOT** exclude later qtmux DTS events. The exported error cadence was ~22/s, not once per 2s. Counts represent decoder error messages NOT confirmed missing frames.
- V2 exporter addresses V1 selection/cap issue by scanning newest diagnostics (2 largest among 12 latest GST_DIAG; 2 latest Recording logs), aggregating **all scanned** event counts per second, exporting only a few representative messages per second, and preserving QTMUX/dynamic error events. Output: summary.txt, media_events.tsv, event_rates.tsv. Scan is bounded to 5m lines/file and 10m lines total; must disclose TRUNCATED if any limit hit.
- CI synthetic test injects 20000 ordinary H264 debug lines *before* additional `no frame!`/qtmux DTS events and checks both are counted after previous V1 cap, plus fake password/IP/Authorization/RTSP URL do not appear. No raw messages copied, no new installs.
- User should **not** run another recording if original raw `GST_DIAG_*.log` files remain: install V2 exporter ZIP, double-click EXPORT_SAFE_LOGS.cmd, share newly generated SAFE_DIAGNOSTICS ZIP privately in conversation. Note that detailed logs are highly sensitive and safe schema-only report is intentionally lossy.
- Root cause H.264 vs qtmux vs native Heap remains unproven. Do not move to speculative pipeline repairs from V1 counts alone.


## 2026-11-17 — H264 SEI-only AU native filter candidate (PR #16)
- Existing private GST_DIAG original session about 747.8 seconds: 16,643 libav no-frame errors, ~16,644 SEI NALs parsed, 16,642 within 10ms on same decode thread; many standalone SEI-only AUs carried with an inserted AUD (NAL 9) and no VCL picture, explaining `avdec_h264` warning. A raw `no frame!` event is NOT proof of a lost output video frame.
- Implemented minimal C `c545dseifilter` GstBaseTransform (native/sei_filter/) supporting only `video/x-h264,stream-format=byte-stream,alignment=au`; conservative AU classifier drops **only** NAL type 6 SEI with optional 9 AUD or 12 filler and no slice/header/unknown NAL; VCL (1–5), SPS/PPS (7/8), malformed, AVCC and unknown bypass unchanged. No buffer data rewriting; metadata-only standalone SEI is deliberately not passed to the decoder, with stated metadata caveat.
- The new Windows CI downloads official GStreamer 1.28.8 MSVC development SDK onto GitHub runner ONLY, compiles x64 plugin and classifier, tests synthetic picture decode and custom appsrc/appsink AU pass/drop. No new installation needed on user's machine. CI builds DLL `gstc545dsei.dll` and packages it under app-local `plugins/`, without changing system GStreamer. Do not merge without green CI.
- `Record.ps1` recognizes `C545D_SEI_AU_FILTER=on` ONLY. Default normal EXE/normal diagnostics is OFF; opt-in trial launcher `START_SEI_FILTER_DIAGNOSTIC.cmd` sets environment for child. If DLL absent or synthetic preflight fails, log UNAVAILABLE and use legacy pipeline.
- Opt-in pipeline inserts filter after incoming h264parse (forced byte-stream AU caps) and before avdec_h264 on both lens branches. No change to NTP/tcp, AAC, compositor, x264 medium/Q24, hourly MP4, stop/EOS. This is a candidate to be validated on real C545D for warnings, picture output, metadata implications, CPU and memory.
- Before/after logs should cover matched ~5-minute sessions. Using `EXPORT_SAFE_LOGS.cmd`, user can share schema-only diagnostics. Do not paste private raw GST_DIAG to GitHub.
- Separate qtmux DTS warning not present in analyzed 747.8s session; not changed here. Heap leak remains unresolved. Earlier worker Ctrl+C was manually pressed by user after visible console errors, not an accidental interrupt.


## 2026-11-17 — RC26 field launch failure and real GStreamer release gate
- User reports second SEI opt-in trial **no recording / near-zero CPU**. Private schema-only safe ZIP `C545D_SAFE_DIAGNOSTICS_20261117_201724.zip`: `LOG_03_WORKER` had 3 `GST_LAUNCH`, 3 `GST_PIPELINE_ERROR`, 3 `GST_EXIT exit_code=1`; `LOG_04_WORKER` had 4 of each; total 7 failed launches, **zero success**. GST detailed logs were short: 2690 +701 scanned lines, no libav or DTS errors. A zero error count here does NOT establish decoder improvement.
- Existing CI checked native WinForms startup, synthetic plugin classification, and a naive separator token check; it never used GStreamer's actual parser on the entire production PowerShell-assembled graph. Thus prior claim that RC26 was sufficiently tested for recording was false.
- New PR #18 adds `tests/Export-RecorderGraphForCI.ps1` which extracts the **actual** `Record.ps1` pipeline generator with dummy IP/credentials/path; invokes GStreamer 1.28.8 MSVC native `gst_parse_launchv()` with NO state transition, camera connection, or MP4 writing. Matrix: SEI ON/OFF, input H264 guard ON/OFF, audio guard ON/OFF, output DTS guard ON/OFF = 16 cases. Any parse error fails the build BEFORE EXE packaging/Release.
- **Initial native test actually FAILED** variant 13 with `no element "video"` for SEI=ON, H264 guard=ON. First twelve combos passed. Root cause: when H264 input guard enabled, `Record.ps1` already emits `! video/x-h264,stream-format=byte-stream,alignment=au !`; trial SEI block emitted a second `video/x-h264` capsfilter immediately after, which GStreamer 1.28 grammar rejects. Removing only duplicate ! in PR #17 did not address it.
- Candidate fix in PR #18: re-use first capsfilter when H264 guard active, only add caps in legacy H264 path. **Do not merge/ship unless 16/16 native pipeline parse pass and other Windows tests remain green.** This gate still cannot prove real-camera streaming, EOS, audio/video quality or memory behavior. Field testing remains needed only after CI gate passes. No real passwords/paths used in GitHub CI.


## 2026-11-17 — Native EXE default SEI ON after user-verified RC32 playback
- User reported RC32 opt-in trial recorded for ~5 minutes; finalized MP4 played both wide-angle and telephoto picture with audible AAC and end-to-end playback. Safe GST report scanned ~297s and found 0 no-frame warnings vs prior 22.3/s, 0 DTS backward. This justifies making this filter the **default native EXE UI request**, not a claim of 24x365 stability or metadata preservation.
- User explicitly objects to having to launch an EXE through additional CMD wrappers. Modified `src/C545D.Launcher/RecorderForm.cs`: a visible **SEI対策を有効化（推奨）** checkbox defaults ON for direct `C545D_Recorder.exe` launch, and is disabled while recording. Immediately before starting `RecordGUIWorker.ps1` it sets `C545D_SEI_AU_FILTER` to `on` or `off` **for the EXE process only**; hidden-console child inherits it. No global environment change; no new software installation; no extra high-volume GST_DEBUG for normal EXE.
- `Record.ps1` retains DLL availability, GStreamer element detection and synthetic decode preflight, falling back to legacy path if the filter is missing or incompatible; worker log explicitly records `SEI-only AU filter: ON/UNAVAILABLE/OFF`. The UI check means ON requested, not proof of plugin actually loaded.
- The user can uncheck the box after normal stop to revert to legacy decode input, without external CMD or environment editing. Known good RC32 stays rollback.
- Windows EXE CI smoke now exercises actual native WinForms default ON and an explicit OFF startup, checks bundled plugin DLL, source transition order, and the mandatory 16/16 full gst_parse_launchv production graph gate. Real camera 24x365 and private-Heap slope are not asserted.


## 2026-11-17 — RC35 memory/CPU evidence and separate opt-in HeapTrace diagnostic kit (PR #20)
- 21:09–21:18 RC35 directly launched from native EXE with real recorder worker report `SEI-only AU filter: ON`, wide/tele RTSP PLAYING, GStreamer normal EOS exit 0 and GUI stopMarker=True. Current private heap remained mildly increasing: first 8 minutes PID 10432 592.8→597.5 MiB; after initial warmup 596.7→597.5 MiB in ~6 min. Earlier ~11h session 593.9→678.0 MiB (~7 MiB/hr). No proof of peak-out or actual native leak.
- Safe exporter selects old diagnostic GST logs by size and may produce misleading "zero errors" for current no-GST_DEBUG RC35 session; worker logs still useful to check startup/stop and SEI flag. Do not claim all old no-frame warnings are absent without matching detailed log.
- To attribute Windows Heap allocation growth **without changing RC35 media pipeline** added `diagnostics/HeapTrace.ps1`, one-click read-only check, Japanese procedure, new Windows CI with synthetic UMDH diff/privacy test, then a **separate diagnostic-only GitHub Releases ZIP**. Requires Microsoft Debugging Tools x64 (gflags and umdh) installed on PC.
- The scripted UST enable/disable is per-image `gst-launch-1.0.exe`, admin-only, tracks its own registry-change marker to avoid disabling another user's setting. Must take effect BEFORE launching new gst-launch. Normal RC35 GUI is launched in ordinary user context with process-only OANOCACHE=1. Capture 2 UMDH snapshots against same PID and start timestamp ~10–20 min apart, compare only, safe summary ZIP contains numeric deltas and DLL basename only; never upload raw UMDH stack traces or paths publicly.
- This is a *diagnostic candidate*, not a leak fix or full field-validated instrument. Windows CI covers PS syntax, test diff fake credentials and read-only Check. Real GFlags + UMDH side effects and actual capture have not been exercised on user's PC. UST overhead may change timing/CPU/Private memory, so the RC35 without tracing remains baseline. Restore UST once diagnosis is complete.
- If UMDH does not explain all of growing Private MB, check GLib/FFmpeg custom allocator coverage or GStreamer object tracer carefully before prescribing additional instruments; do not pile on tools without a distinct evidence question. No 24–48h wait loop as a prerequisite.


## 2026-11-17 — HeapTrace v2 recovery, Japanese profile path issue (PR #22)
- User captured two UMDH raw logs from the same PID 9424: T1 22:35 (about 7525.9 KiB) and T2 23:00 (7480.6 KiB). Both files physically exist under %LOCALAPPDATA%/C545D_GStreamer/HeapTrace; snapshots.json first/second both populated but File.Exists returned False for both. No raw files shared.
- Root cause: Save-Json used UTF8Encoding(false) (no BOM), while Windows PowerShell 5.1 Get-Content -Raw defaults to ANSI on BOM-less data; Japanese username path is corrupted, and reserialized on the second capture. This breaks Compare's old guard before UMDH diff can run.
- v2 Read-Json uses [IO.File]::ReadAllText with explicit UTF8. Compare reconstructs raw capture file paths from exactly one T1 and one T2 file matching the stored PID and timestamped filename within private HeapTrace directory, requires non-empty files and chronological order, refuses ambiguity, and saves repaired state only after successful UMDH diff + safe summary. Adds '-v' to UMDH comparison for stack traces. Raw memory trace remains private.
- Windows CI tests PowerShell 5.1 syntax, Japanese Unicode directory UTF8 JSON roundtrip, intentionally corrupted path recovery, ambiguous candidate refusal, synthetic summary privacy, read-only Check and zipped diagnostic release. No MP4/GStreamer recording changes.
- The user must download HeapTrace diagnostic v2 separately (not RC35), reuse existing raw captures, run ONLY '-Mode Compare' under ordinary PowerShell. No recapture/restart. Afterward '-Mode Restore' under Administrator if UST is still on. If Compare fails at UMDH parsing, review error output, not upload raw diff.
- Issue #21 and root investigation #12; no claim of memory-leak cause yet.
