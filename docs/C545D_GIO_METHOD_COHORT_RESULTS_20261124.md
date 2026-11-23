# C545D — real GIO original-stack source cohorts (2026-11-24 JST)

## Verified evidence, not 24/7 leak proof

Windows 2022 isolated GitHub Actions [#45201355796 PASS](https://github.com/taku077/c545d-recorder/actions/runs/45201355796), code [f9f1eacd](https://github.com/taku077/c545d-recorder/commit/f9f1eacd0d58a5c5680fb00d4e8fc3f0b970bd26): patched source-built GLib/GIO 2.82.4 original HeapAlloc CallStack() and native PDB-resolved six allowlisted methods, one initial AppInfo call per arm, bounded 256 MiB ETL and 2M typed events, zero lost buffers/event gate, private ETL/PDB only on disposable runner. **No Windows10 camera recording host/DLL touched.** This is not a repeated comparable active-subscribed epoch, so it cannot establish memory leak slope.

These ten mutually exclusive original-owner cohorts balance against independent `GenericHeapLifetime` total with five cross-checks in BOTH arms; all `C545D_GIO_METHOD_COHORT_ACCOUNTING_PASS`.

| Original-stack cohort | nochange live | nochange held requested bytes | registry live | registry held requested bytes |
|---|---:|---:|---:|---:|
| Missing original stack | 0 | 0 | 0 | 0 |
| No GIO DLL frame | 217 | 57,150 | 229 | 53,706 |
| GIO frame but no allowlisted method | 43 | 2,776 | 43 | 2,776 |
| Only one distinct allowlisted GIO method (all six combined) | 0 | 0 | 0 | 0 |
| **Multiple distinct allowlisted GIO methods on one original callstack** | **6,313** | **578,859** | **18,172** | **1,268,160** |
| **Total original heap blocks remaining** | **6,573** | **638,785** | **18,444** | **1,324,642** |

The six exact methods are `update_registry_data`, `keys_updated`, `watch_keys`, `gio_win32_appinfo_thread_func`, `g_win32_registry_key_watch`, `g_win32_package_parser_enum_packages`; individually, all singly-owned LIVE blocks are zero at these particular settled cuts. This does NOT mean those methods allocated no memory or that their relevant objects were all freed, because multiple such methods appeared on the same allocation call stack.

Resource scope (preappinfo → settled_cleanup), from the SAME CI run: PrivateUsage **+3,440,640 B** nochange and **+3,809,280 B** registry; private REGION **+2,379,776 B** / **+2,781,184 B**, handle delta **+551** / **+553**. These are separate workloads / initializations, not a temporal slope or leak amount. The 6 expected active registry watches are not required to reach zero. Heap requested bytes are not page commitment or PSAPI private bytes.

Original stack missing = **0** both arms. Remaining unclassified by trusted six methods has a concrete discriminator: no-GIO-frame or GIO-frame-but-unmatched; neither is silently promoted to GIO function source. **The key new deficit:** 100% of proven-GIO still-live original blocks are tagged multi-method ambiguous, because the previous classifier only checked presence of method names, not their call order. This is NOT proof of multiple leaks.

## Next discriminator and evidence gate

A *separately labeled* nearest-allowlisted method-by-ordered-callstack owner **proxy** was committed as [dbfe2c236b5d](https://github.com/taku077/c545d-recorder/commit/dbfe2c236b5d47c5b8cf4117978c3076e91aef77), along with independent allocation→realloc→free accounting and numeric-only output gates. Source-order explanation: TraceEvent `CallStack()` iterates the current frame then `Caller`, so the first matching allowlisted frame is deterministically the *nearest allowlisted* function, not necessarily the exact direct allocating function. Keep original ambiguous cohort simultaneously; never silently re-label this proxy as proven original owner.

At the time of this report, preflight [#45203073900 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45203073900) and actual Windows [#45203073868](https://github.com/taku077/c545d-recorder/actions/runs/45203073868) is **IN PROGRESS**. Before claiming the additional result, check the latest CI run, require each arm's 10 `C545D_GIO_NEAREST_METHOD_COHORT` rows, matching `C545D_GIO_NEAREST_METHOD_ACCOUNTING_PASS` and `C545D_GIO_NEAREST_FRAME_SCOPE`. A first GIO frame outside the allowlist does NOT establish exact source. Once validated, identify top nearest function and measure the new distinction in one bounded **repeated equivalent active-subscribed** AppInfo epoch with phase-matched PrivateUsage/REGION/CPU/handles, rather than repeating new initial-call pairs without a new discriminator.

## Safety status

Four broad classification cases remain evidence gaps, production release HOLD; `install_approved=0`, `live_test_authorized=0`; Windows10 2-RTSP + audio/MP4 postpatch untested. Preserve stream1 wide left / stream6 tele right, 2560×720@15fps, x264 medium QP24, AAC mono 48 kHz 192 kbps target, hourly MP4, sync, avdec_h264, safe stop/EOS. User action **NONE**.
