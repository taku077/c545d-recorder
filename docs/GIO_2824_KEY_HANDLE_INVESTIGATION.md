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

## Precise remaining discriminator before a production fix
Identify *which of the recurring 214 Key names remain referenced*, and attribute their owning GIO code path rather than merely counting all 42,662 transient Opens. Existing handle-stacks TXT alone has neither per-key identities nor per-handle close lifetime; an exact leaking statement cannot be inferred from it. Avoid repeating the same long host measurement.

Engineering-side candidate test: isolated Windows CI reproduction on GLib **2.82.4**, invoking GAppInfo enumeration and registry change notifications against test-only registry keys, with per-cycle Key-handle counts and explicit cleanup; no camera, credentials, or recorder modification. If the bug reproduces, change only the responsible ownership or update logic and assert count stabilization against the failing test. If not reproducible, treat the exact host-only trigger as unverified, not as proof of a fix.

## Acceptance guardrails
- Current recorder (CPU-stable avdec_h264 baseline) remains unchanged.
- Do not change x264 medium, quantizer 24, 2560x720/15fps, two RTSP feeds, sync logic, or splitmuxsink without evidence.
- No forced handle closes, registry writes, or production GIO DLL replacement.
- Only a verified narrowly scoped patch is a candidate for automated smoke tests. Check both Key live-handle delta and private memory independently; an improvement in one does not automatically fix the other.
- No personal paths, camera credentials, raw registry key names, raw ETL, or full WPA stack dumps in GitHub.
