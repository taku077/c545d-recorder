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

## Precise remaining discriminator before a production fix
Identify *which of the recurring 214 Key names remain referenced*, and attribute their owning GIO code path rather than merely counting all 42,662 transient Opens. Existing handle-stacks TXT alone has neither per-key identities nor per-handle close lifetime; an exact leaking statement cannot be inferred from it. Avoid repeating the same long host measurement.

Engineering-side candidate test: isolated Windows CI reproduction on GLib **2.82.4**, invoking GAppInfo enumeration and registry change notifications against test-only registry keys, with per-cycle Key-handle counts and explicit cleanup; no camera, credentials, or recorder modification. If the bug reproduces, change only the responsible ownership or update logic and assert count stabilization against the failing test. If not reproducible, treat the exact host-only trigger as unverified, not as proof of a fix.

## Acceptance guardrails
- Current recorder (CPU-stable avdec_h264 baseline) remains unchanged.
- Do not change x264 medium, quantizer 24, 2560x720/15fps, two RTSP feeds, sync logic, or splitmuxsink without evidence.
- No forced handle closes, registry writes, or production GIO DLL replacement.
- Only a verified narrowly scoped patch is a candidate for automated smoke tests. Check both Key live-handle delta and private memory independently; an improvement in one does not automatically fix the other.
- No personal paths, camera credentials, raw registry key names, raw ETL, or full WPA stack dumps in GitHub.
