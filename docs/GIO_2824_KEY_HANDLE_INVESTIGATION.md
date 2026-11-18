# C545D: GIO 2.82.4 Key-handle investigation (2026-11-18)

## Scope and decision
Read-only root-cause investigation before any change to the running recorder, registry, or media pipeline. No request for fresh WPR/UMDH capture, long user-run test, or manual WPA operation.

**State: root-cause location NOT YET CONFIRMED.** Working hypothesis: Windows GIO AppInfo registry enumeration/rebuild path may retain a small fraction of opened Key handles across repeated rebuilds. Rebuild function and ownership edge are not yet proven to be where handles remain outstanding.

## Evidence (sanitized, previous user-provided measurements)
- 4-hour fixed-process handle type series: Key 12,370 -> 15,794 (**+3,424**), all 16 other types net zero; around each hh:01 and hh:24 event, **+428 Key**.
- One local snapshot: 17,078 Key handles across 382 distinct names. 214 names had 79 handles each (16,906/17,078). No actual key names are retained in this note.
- 2026-11-18 short WPR Handle capture across an event: total process handles +428. This alone does not prove which of the 42k Open events had no corresponding Close event.
- Previously provided WPA `C545D_Handle_Stacks.txt` (47,051 data rows; root count 42,662 Key creations): 42,645 events (~99.96%) have a shared GLib/GIO stack prefix; 34,242 (~80.26%) pass through `KernelBase!RegOpenKeyExW` across disjoint tree nodes. The tree displays <PDB not found> for GIO frames; no precise function attribution from this export. **These are cumulative trace events, not a count of outstanding Key handles.**
- Running `gio-2.0-0.dll` version: **2.82.4**.

## GLib upstream source read, tag 2.82.4
1. `gio/gwin32appinfo.c` `keys_updated()` re-arms registry watchers, increments update counter, and enqueues a worker; `gio_win32_appinfo_thread_func()` calls `update_registry_data()` when the counter is nonzero.
2. `update_registry_data()` enumerates Windows registration and association data, destroys prior app/extension/handler maps, and releases top-level `GWin32RegistryKey` references at exit. It calls several helpers that create child registry objects. A particular missing release was **not** identified in this audit.
3. `gio/gwin32registrykey.c`: `g_win32_registry_key_initable_init()` and `g_win32_registry_key_get_child_w()` call `RegOpenKeyExW`; `g_win32_registry_key_dispose()` calls `RegCloseKey` for non-predefined handles. `key_changed()` releases the additional watch-time `g_object_ref()`.
4. Corresponding notification/rebuild and object-disposal functions were compared against GLib tag 2.88.3. They remain materially the same; a blind library version update is **not a demonstrated fix**.
5. An experimental patch that suppresses rescans when `C545D_GIO_APPINFO_STATIC=1` exists as a source patch only. It has not been built or verified; disabling legitimate Windows AppInfo updates is a functional tradeoff and is **not** an approved production fix.

Sources:
- https://github.com/GNOME/glib/blob/2.82.4/gio/gwin32appinfo.c
- https://github.com/GNOME/glib/blob/2.82.4/gio/gwin32registrykey.c
- https://github.com/GNOME/glib/blob/2.88.3/gio/gwin32appinfo.c
- https://github.com/GNOME/glib/blob/2.88.3/gio/gwin32registrykey.c
- https://learn.microsoft.com/en-us/windows/win32/sysinfo/opening-creating-and-closing-keys
- https://learn.microsoft.com/en-us/windows/win32/api/winreg/nf-winreg-regclosekey


## Newly found: candidate strong-reference cycles (concrete source-level finding)

A more specific mechanism than a generic missing `RegCloseKey` is visible in the exact source:

- `g_win32_appinfo_application_init()` (around line 553) constructs `app->verbs` as an owning `GPtrArray` whose free function is `g_object_unref`.
- `app_add_verb()` (around 1882-1897), `uwp_app_add_verb()` (1914-1930), and related paths assign `shverb->app = g_object_ref(app_rec)` and add the same verb to `app->verbs`. This makes a **strong app -> verb -> app reference cycle**.
- `GWin32AppInfoApplication.supported_exts` and `supported_urls` hold handlers with owning `g_object_unref` destructors (around 545-552). `link_handlers_to_fake_apps()` (around 3239-3259 and 3289-3310) inserts a `g_object_ref(handler)` while `handler->verbs` owns a verb whose `app` references this app. This makes a **strong app -> handler -> verb -> app cycle** on those paths.
- `get_handler_object()` (around 1722-1731) retains `handler_rec->key = g_object_ref(handler_key)`. Only `g_win32_appinfo_handler_dispose()` (405) releases that reference. If the above cycle survives replacement of the app registry tables, a registry key reference can persist and keep its HKEY open.
- `update_registry_data()` destroys old hash tables before rescanning, but ordinary GObject refcounting cannot collect reference cycles. Thus these exact ownership edges are a **specific, testable candidate** for the recurring retained registry keys.
- The same essential ownership edges were found in GLib tag **2.88.3**, so a generic update alone is not shown to remove this candidate.

**Important limit:** a source-level cycle is established; whether the specific 214 persistent registry keys are held by this cycle on this machine, or how many new cyclic objects survive each run, is not yet established. Avoid converting source-level suspicion into a definitive causal claim.

### Narrow fix approach for an isolated branch

A safe production patch must break the strong reference cycle while preserving the lifetime of externally returned GAppInfo/handler objects. Merely removing the `g_object_ref` from `shverb->app` could leave a dangling pointer; force-closing a live HKEY could corrupt state. First add a test that triggers two AppInfo rebuilds and checks that the old handler's GObject dispose and HKEY closure run after references are released. Then change one ownership edge to a controlled weak reference or another verified lifetime design, and run the same test plus existing recorder invariants. This is a targeted implementation gate, not a request for long host-side recording.


## Camera-free Windows CI reproduction — FIRST RUN observed (2026-11-19 JST)

- The real GLib/GIO DLL loaded by the official GStreamer 1.28.8 SDK on a clean GitHub Actions windows-2022 runner is `gio-2.0-0.dll 2.82.4.0` (exact target version).
- 16 iterations of `g_app_info_get_all()` while updating only a disposable CI HKCU RegisteredApplications value, using `tests/gio_appinfo_key_handle_probe.c`.
- Process total handle count reported by its own `GetProcessHandleCount`: **700 baseline → 5,853** after 16 iterations, with nearly constant **+322 handles per iteration**.
- PrivateUsage reported by `GetProcessMemoryInfo`: **5,533,696 → 28,913,664 bytes**. This is +23,379,968 bytes, **~22.30 MiB**.
- Independent Microsoft Sysinternals Handle64 `-s -p`: first Key sample **25**, last **5,585**; +5,560 Key during sampled window (first sample was before the GIO baseline initialization). 25 samples of Key/Total counts all report OK.
- `GAppInfoMonitor::changed` callback count was **0** throughout this first test; do **not** claim that the registry changes triggered all cache rebuilds. The only demonstrated fact is unbounded-looking Key and Private Bytes growth over 16 successive enumerate/change iterations.
- CI build and run succeeded. Artifact: `gio-appinfo-short-probe-sanitized`, GitHub Actions run **44331665421**. The artifact contains only numerical process measurements and status codes (no camera or personal registry key names).
- A second short control test **without any registry modification** was added to distinguish plain repeated `g_app_info_get_all()` from notification-triggered rebuild. Compare both before selecting a patch.
- This is a reproducible short-run candidate mechanism under the same GIO DLL version; it is **not yet a validated production fix** and not proof that the user's host has the identical path.


## Second CI run: no-registry-change control isolates trigger (2026-11-19 JST)

GitHub Actions run **44332409627**, GLib/GIO **2.82.4.0**, both 16-cycle programs compile and run.

- **Control: no registry modifications.** Repeated \`g_app_info_get_all()\` calls, baseline **698 total handles / 5,918,720 Private bytes**, and every cycle through cycle 16 and cleanup remained *exactly 698 handles and 5,918,720 bytes*.
- **Trigger: alter one synthetic user-scoped HKCU RegisteredApplications value in each cycle, then call \`g_app_info_get_all()\`.** Baseline **696 handles / 5,484,544 bytes**, cycle16 **5,849 handles / 28,377,088 bytes**, cleanup **5,848 handles / 28,377,088 bytes**. Per cycle +322 or +323 handles, almost all open Registry Key handles as independently sampled by Handle64.
- Independent Handle64 observations: first sample **Key 168 / total 295** (prior to AppInfo initialization), later **Key 434 / total 696** (post-initialization), final **Key 5585 / total 5848**. Use post-initialization to final for like-for-like comparison (Key +5,151), rather than first sample to final.
- \`GAppInfoMonitor::changed\` signal was not observed (\`notifications=0\`) in both tests. This signal is *not* a required proof of the internally triggered registry rebuild. The control comparison proves the growth is caused by the added synthetic-registry-modification path under the tested schedule. More granular internal callback attribution requires instrumentation, not another long host measurement.
- \`322=2x161\` on CI and \`428=2x214\` on user's machine: **hypothesis** that two retained handles per registered handler/association per rebuild explain both environmental cardinalities. The actual number of unique retained keys on CI was not separately enumerated.
- Source inspection confirms potential strong reference cycles \`Application->ShellVerb->Application\` and \`Application->Handler->ShellVerb->Application\` where Handler retains \`GWin32RegistryKey\`. The controlled trigger and registry-only handle growth now strongly support examining those cycles, but do not independently establish causality of each key without a patched runtime or finalizer/closure instrumentation.
- **Decision:** no further host 4-hour measurement at this stage. Proceed with controlled GLib ref/lifetime patch experiment and re-run the same CI harness against baseline and candidate in one job. No user actions needed.


## 2026-11-19: Controlled patched-GLib comparison SUCCESS (diagnostic fix only)

GitHub Actions run https://github.com/taku077/c545d-recorder/actions/runs/44347320582 — **SUCCESS**, GLib 2.82.4 compiled from upstream source twice with exactly the same MinGW64 toolchain, first unmodified then with \`tests/patch_glib_appinfo_experiment.py\`.

Results (16 HKCU synthetic registry updates and 16 \`g_app_info_get_all()\` calls, each run 16 cycles):

| Variant | Total handle baseline→end | Δ handles | Private bytes baseline→end | Δ Private bytes |
|---|---:|---:|---:|---:|
| unmodified, no registry change | 677→677 | 0 | 5,664,768→5,664,768 | 0 |
| unmodified, registry change | 678→5,830 | **+5,152** | 5,644,288→28,725,248 | **+23,080,960** |
| experimental patch, no registry change | 677→677 | 0 | 5,713,920→5,713,920 | 0 |
| experimental patch, registry change | 678→678 | **0** | 5,668,864→15,712,256 | **+10,043,392** |

- Experimental patch invokes \`g_object_run_dispose()\` on old AppInfo applications in \`apps_by_id\`, \`apps_by_exe\`, \`fake_apps\` before cache table replacements. It **eliminates the reproducible +322 handle/cycle in CI** and halves the Private Bytes growth, without changing any Windows recorder files.
- A retained \`GAppInfo\` instance tested by name and executable across 3 registry updates printed \`C545D_RETAINED_APPINFO,PASS\` in both baseline and patched configurations. **This tests only two properties on one instance**, not every supported GAppInfo operation nor multithreaded lifetime correctness.
- Private Bytes still increased by **10,043,392 bytes (~9.58 MiB)** in the patched experiment, so a memory leak fix has **not** been established even though live total handle leak was stopped.
- The patch is intentionally **NOT production-safe**: forced disposal during cache replacement can disrupt externally held object relationships. Do not package replacement DLL or deploy to the user's recorder. GObject documentation: \`g_object_run_dispose()\` can break cycles but requires careful lifetime discipline https://gnome.pages.gitlab.gnome.org/gtk/gobject/concepts.html .
- Next engineering gate: prove safe lifetime under retained external \`GAppInfo\`/handler references, and implement a less invasive ownership fix with equivalent zero-handle-growth regression. Separately test whether remaining Private Bytes reaches a steady plateau under additional rapid synthetic cycles; no user-side 4-hour measurements.



## 2026-11-19 JST — Tested disposal mechanism (real GLib 2.82.4 source rebuild)

The Windows-2022 / MSYS2 GitHub Actions run **44348396190** built actual upstream GLib **2.82.4** twice, first untouched and then after an experimental force-dispose of old AppInfo applications at cache replacement (`tests/patch_glib_appinfo_experiment.py`). The resulting artifact `gio-refcycle-baseline-vs-forced-dispose-experiment` was downloaded and inspected.

| Measurement (16 cycles) | Untouched | Forced-dispose experiment |
|---|---:|---:|
| Registry unchanged, total handle delta | 0 | 0 |
| Registry changed, total handle delta | **+5152** | **0** |
| Registry changed, Private Bytes delta | **+22921216 bytes** | **+10113024 bytes** |
| Previously-held GAppInfo name / executable check | PASS | PASS |

**Interpretation:** The AppInfo object-lifetime/ownership pathway is causally involved in the recurring Key-handle increase under CI conditions; forcing cached app disposal makes total handles plateau in this test. **This is not a production-safe fix:** g_object_run_dispose() can clear fields in objects which other threads or caller-owned GAppInfo objects still reference, even though one retained-name/executable smoke test passed. Private Bytes still increased about 9.65 MiB, requiring separate investigation of residual allocations or allocator behavior. No user PC actions or long tests were involved.

A separate opt-in patch `patches/glib-2.82.4-static-appinfo-experiment.patch` was also applied successfully to the exact source tag, and an MSVC DLL build completed in GitHub Actions run **44348889962**. This disables refresh only under `C545D_GIO_APPINFO_STATIC=1`; it is a diagnostic A/B control, not a safe default production fix. As of this note, no A/B runtime validation of the opt-in patch has been completed.

Next engineering goal: break the AppInfo/Verb/Handler strong-reference cycle without prematurely disposing caller-owned objects, and verify (a) live Key count plateau, (b) retained app handles/properties remain valid, and (c) private memory behavior with test-controlled cycles. Do not deploy either exploratory patch to production.


## 2026-11-19: 64-cycle follow-up (no user machine), SUCCESS workflow

GitHub Actions https://github.com/taku077/c545d-recorder/actions/runs/44348683100 completed successfully with the experimental patch and a separate *64-cycle* registry-change workload.

- Patched process handles: baseline 678, cycle 1 678, cycle 64 680, after cleanup 679. Difference first→last sampled cycle **+2**, compared to +5,152 in the old 16-cycle baseline. This is **not** a return of the original proportional Key handle growth.
- Private bytes: baseline **6,107,136**, cycle 64/end **45,166,592**, delta **39,059,456 bytes (~37.25 MiB)** over 64 cycles.
- Private Bytes cycles 1→16 delta **9,388,032**; cycles 49→64 delta **9,129,984**. The growth rate **did not meaningfully fall**, so the experimental patch **does not fix ongoing Private Bytes growth**.
- The diagnostic patch is still **not approved for production**; it force-disposes old AppInfo objects, which may invalidate legitimately retained external references beyond the narrow tested methods. User's recorder remains untouched.
- Additional source audit: \`g_win32_registry_value_iter_get_data_w()\` returns a **transfer-none** pointer to iterator-owned data (\`gwin32registrykey.c\` lines ~1519–1558). Do **NOT** add \`g_free(value_data)\` to \`collect_capable_apps_from_registered_apps()\`; that would be an invalid free. The iterator is cleaned by \`g_win32_registry_value_iter_clear()\`.
- Next investigation must target genuinely owned allocations/refcount cycles or allocator caching in the rebuild pathway (prefer malloc/free diagnostics or controlled second patch in Windows CI); avoid assumptions based only on PrivateUsage monotonic growth. No further four-hour real-host tests.


## Precise remaining discriminator before a production fix
Identify *which of the recurring 214 Key names remain referenced*, and attribute their owning GIO code path rather than merely counting all 42,662 transient Opens. Existing handle-stacks TXT alone has neither per-key identities nor per-handle close lifetime; an exact leaking statement cannot be inferred from it. Avoid repeating the same long host measurement.

Engineering-side candidate test: isolated Windows CI reproduction on GLib **2.82.4**, invoking GAppInfo enumeration and registry change notifications against test-only registry keys, with per-cycle Key-handle counts and explicit cleanup; no camera, credentials, or recorder modification. If the bug reproduces, change only the responsible ownership or update logic and assert count stabilization against the failing test. If not reproducible, treat the exact host-only trigger as unverified, not as proof of a fix.

## Acceptance guardrails
- Current recorder (CPU-stable avdec_h264 baseline) remains unchanged.
- Do not change x264 medium, quantizer 24, 2560x720/15fps, two RTSP feeds, sync logic, or splitmuxsink without evidence.
- No forced handle closes, registry writes, or production GIO DLL replacement.
- Only a verified narrowly scoped patch is a candidate for automated smoke tests. Check both Key live-handle delta and private memory independently; an improvement in one does not automatically fix the other.
- No personal paths, camera credentials, raw registry key names, raw ETL, or full WPA stack dumps in GitHub.
