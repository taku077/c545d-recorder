#!/usr/bin/env python3
"""CI ONLY: connect the standalone C++/WinRT PackageCatalog C ABI bridge
to the disposable GLib 2.82.4 DisplayName cache.

This is intentionally NOT production-ready. A single owner thread retains its
watch until process atexit; every foreign-thread call *bypasses* the cache.
Package and UI-language events are polled and invalidate owned strings before
each lookup/store. Synthetic bridge notification is optional for deterministic CI.
No new dependency is linked into any shipped GIO DLL: fully dynamic LoadLibraryW.
"""
from pathlib import Path
import sys


def once(data, old, new, label):
    n = data.count(old)
    if n != 1:
        raise ValueError(f"{label}: expected one anchor; found {n}")
    return data.replace(old, new, 1)


BRIDGE = r"""/* C545D CI-ONLY PackageCatalog C ABI bridge, dynamically loaded.
 * The event callback only modifies atomic state inside the C++ bridge.
 * All GMutex / GHashTable operations remain on the enumerating thread.
 * Caller thread is pinned to its first watch owner; foreign threads fail
 * closed and ALWAYS call the original WinRT DisplayName getter.
 */
typedef struct c545d_winrt_watch C545DWatch;
typedef int (__cdecl *C545DThreadEnter) (void);
typedef void (__cdecl *C545DThreadLeave) (void);
typedef int (__cdecl *C545DWatchOpen) (C545DWatch **);
typedef void (__cdecl *C545DWatchClose) (C545DWatch *);
typedef int (__cdecl *C545DWatchSnapshot) (C545DWatch *, guint64 *, guint64 *);
typedef int (__cdecl *C545DWatchInject) (C545DWatch *);
static GMutex c545d_bridge_lock;
static gboolean c545d_bridge_tried;
static gboolean c545d_bridge_ready;
static HMODULE c545d_bridge_module;
static C545DWatch *c545d_bridge_watch;
static C545DThreadEnter c545d_bridge_enter;
static C545DThreadLeave c545d_bridge_leave;
static C545DWatchOpen c545d_bridge_open;
static C545DWatchClose c545d_bridge_close;
static C545DWatchSnapshot c545d_bridge_snapshot_func;
static C545DWatchInject c545d_bridge_inject_func;
static DWORD c545d_bridge_owner;
static guint64 c545d_bridge_generation, c545d_bridge_locale;
static guint c545d_bridge_scans, c545d_bridge_injections;
static guint c545d_bridge_evictions, c545d_bridge_failures;

static gboolean
c545d_bridge_mode (void)
{
  return g_getenv ("C545D_DIAG_UWP_CACHE_EVENT_BRIDGE") != NULL;
}

/* Registered only for disposable, single-main-thread CI probes. This
 * diagnostic atexit strategy is NOT correct for general GIO worker threads.
 */
static void
c545d_bridge_cleanup (void)
{
  g_mutex_lock (&c545d_bridge_lock);
  if (c545d_bridge_watch != NULL)
    c545d_bridge_close (c545d_bridge_watch);
  c545d_bridge_watch = NULL;
  if (c545d_bridge_leave != NULL)
    c545d_bridge_leave ();
  if (c545d_bridge_module != NULL)
    FreeLibrary (c545d_bridge_module);
  c545d_bridge_module = NULL;
  c545d_bridge_ready = FALSE;
  g_mutex_unlock (&c545d_bridge_lock);
}

static gboolean
c545d_bridge_setup_locked (void)
{
  const gchar *path = g_getenv ("C545D_DIAG_UWP_C_BRIDGE_DLL");
  gunichar2 *wide;
  if (path == NULL)
    return FALSE;  /* No trusted full DLL pathname => bypass cache. */
  wide = g_utf8_to_utf16 (path, -1, NULL, NULL, NULL);
  if (wide == NULL)
    return FALSE;
  c545d_bridge_module = LoadLibraryW ((LPCWSTR) wide);
  g_free (wide);
  if (c545d_bridge_module == NULL)
    return FALSE;
#define C545D_GET_SYMBOL(field, name) \
  do { \
    c545d_bridge_##field = (void *) GetProcAddress (c545d_bridge_module, name); \
    if (c545d_bridge_##field == NULL) \
      goto failed; \
  } while (0)
  C545D_GET_SYMBOL (enter, "c545d_thread_enter");
  C545D_GET_SYMBOL (leave, "c545d_thread_leave");
  C545D_GET_SYMBOL (open, "c545d_watch_open");
  C545D_GET_SYMBOL (close, "c545d_watch_close");
  C545D_GET_SYMBOL (snapshot_func, "c545d_watch_snapshot");
  C545D_GET_SYMBOL (inject_func, "c545d_watch_inject_synthetic");
#undef C545D_GET_SYMBOL
  if (c545d_bridge_enter () != 0)
    goto failed;
  if (c545d_bridge_open (&c545d_bridge_watch) != 0 ||
      c545d_bridge_watch == NULL)
    {
      c545d_bridge_leave ();
      c545d_bridge_leave = NULL;
      goto failed;
    }
  c545d_bridge_owner = GetCurrentThreadId ();
  if (atexit (c545d_bridge_cleanup) != 0)
    {
      c545d_bridge_close (c545d_bridge_watch);
      c545d_bridge_watch = NULL;
      c545d_bridge_leave ();
      c545d_bridge_leave = NULL;
      goto failed;
    }
  return TRUE;
failed:
  if (c545d_bridge_module != NULL)
    FreeLibrary (c545d_bridge_module);
  c545d_bridge_module = NULL;
  return FALSE;
}

/* Called before EVERY lookup or store, not merely at the beginning of a
 * scan: event changes and language changes evict all previously owned names.
 */
static gboolean
c545d_bridge_poll (void)
{
  gboolean ok = TRUE;
  guint64 generation = 0, locale = 0;
  if (!c545d_bridge_mode ())
    return TRUE;
  g_mutex_lock (&c545d_bridge_lock);
  if (!c545d_bridge_tried)
    {
      c545d_bridge_tried = TRUE;
      c545d_bridge_ready = c545d_bridge_setup_locked ();
    }
  if (!c545d_bridge_ready || c545d_bridge_owner != GetCurrentThreadId () ||
      c545d_bridge_snapshot_func (c545d_bridge_watch, &generation, &locale) != 0)
    {
      c545d_bridge_failures++;
      ok = FALSE;
    }
  if (ok && (c545d_bridge_generation != generation ||
             c545d_bridge_locale != locale))
    {
      g_mutex_lock (&c545d_display_cache_lock);
      if (c545d_display_cache != NULL)
        g_hash_table_remove_all (c545d_display_cache);
      g_mutex_unlock (&c545d_display_cache_lock);
      if (c545d_bridge_generation != 0)
        c545d_bridge_evictions++;
      c545d_bridge_generation = generation;
      c545d_bridge_locale = locale;
    }
  if (!ok)
    {
      /* Fail closed even when an event subscription has become unavailable:
       * never allow later reads of a potentially stale DisplayName. */
      g_mutex_lock (&c545d_display_cache_lock);
      if (c545d_display_cache != NULL)
        g_hash_table_remove_all (c545d_display_cache);
      g_mutex_unlock (&c545d_display_cache_lock);
    }
  g_mutex_unlock (&c545d_bridge_lock);
  return ok;
}

static guint64
c545d_bridge_read_generation (void)
{
  guint64 generation;
  if (!c545d_bridge_poll ())
    return G_MAXUINT64;
  g_mutex_lock (&c545d_bridge_lock);
  generation = c545d_bridge_generation;
  g_mutex_unlock (&c545d_bridge_lock);
  return generation;
}

/* True on no-bridge old diagnostics; in bridge mode both successful
 * pre-getter epoch and current post-getter epoch must be identical.
 */
static gboolean
c545d_bridge_allow_store (guint64 pre_getter)
{
  if (!c545d_bridge_mode ())
    return TRUE;
  if (pre_getter == G_MAXUINT64 || !c545d_bridge_poll ())
    return FALSE;
  g_mutex_lock (&c545d_bridge_lock);
  gboolean current = c545d_bridge_generation == pre_getter;
  g_mutex_unlock (&c545d_bridge_lock);
  return current;
}

static void
c545d_bridge_scan_start (void)
{
  const gchar *inject_at = g_getenv ("C545D_DIAG_UWP_BRIDGE_INJECT_SCAN");
  guint64 n = 0;
  gchar *end = NULL;
  if (!c545d_bridge_mode ())
    return;
  if (!c545d_bridge_poll ())
    return;
  c545d_bridge_scans++;
  if (inject_at != NULL)
    n = g_ascii_strtoull (inject_at, &end, 10);
  if (n > 1 && n <= 128 && end != NULL && *end == '\0' &&
      c545d_bridge_scans == n)
    {
      /* Injection invokes the SAME atomic-generation path as the actual
       * PackageCatalog callback, without mutating installed packages. */
      g_mutex_lock (&c545d_bridge_lock);
      if (c545d_bridge_inject_func (c545d_bridge_watch) == 0)
        c545d_bridge_injections++;
      else
        c545d_bridge_failures++;
      g_mutex_unlock (&c545d_bridge_lock);
      (void) c545d_bridge_poll ();
    }
}

static void
c545d_bridge_report (void)
{
  if (!c545d_bridge_mode ())
    return;
  g_print ("C545D_WINRT_BRIDGE,scans=%u,injections=%u,evictions=%u,errors=%u,ready=%u\n",
           c545d_bridge_scans, c545d_bridge_injections,
           c545d_bridge_evictions, c545d_bridge_failures,
           c545d_bridge_ready ? 1 : 0);
}

"""


def main(path):
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    src = raw.decode("utf-8").replace("\r\n", "\n")
    src = once(src, '#include <stdio.h>\n',
               '#include <stdio.h>\n#include <stdlib.h>\n',
               "atexit include")
    src = once(src, 'static gunichar2 *\nc545d_cache_display_lookup (const wchar_t *full_name)',
               'static gboolean c545d_bridge_poll (void);\n\n'
               'static gunichar2 *\nc545d_cache_display_lookup (const wchar_t *full_name)',
               "forward bridge poll declaration")
    src = once(src, 'static void\nc545d_cache_maybe_refresh (void)',
               BRIDGE + 'static void\nc545d_cache_maybe_refresh (void)',
               "add event bridge implementation")
    src = once(src,
        '  const gchar *value;\n  gchar *end = NULL;',
        '  const gchar *value;\n  gchar *end = NULL;',
        "keep declaration section intact")
    src = once(src, '  guint64 n;\n\n  /* Synthetic event delivery only.',
               '  guint64 n;\n  c545d_bridge_scan_start ();\n\n  /* Synthetic event delivery only.',
               "poll/inject at start of scan")
    src = once(src,
        '  gunichar2 *result = NULL;\n  gchar *key = g_utf16_to_utf8',
        '  gunichar2 *result = NULL;\n'
        '  if (!c545d_bridge_poll ())\n'
        '    return NULL; /* fail closed to original getter */\n'
        '  gchar *key = g_utf16_to_utf8',
        "lookup fail-closed")
    src = once(src,
        '  g_free (key);\n  return result;\n}',
        '  g_free (key);\n'
        '  if (result != NULL && !c545d_bridge_poll ())\n'
        '    g_clear_pointer (&result, g_free);\n'
        '  return result;\n}',
        "post-read event race guard")
    src = once(src,
        '  g_print ("C545D_DISPLAY_CACHE_REFRESH,scans=%u,resets=%u\\n",\n'
        '           c545d_diag_refresh_scans, c545d_diag_refresh_resets);',
        '  g_print ("C545D_DISPLAY_CACHE_REFRESH,scans=%u,resets=%u\\n",\n'
        '           c545d_diag_refresh_scans, c545d_diag_refresh_resets);\n'
        '  c545d_bridge_report ();',
        "emit numeric bridge counters")
    src = once(src,
        '      gunichar2 *c545d_cached_display_name = NULL;',
        '      gunichar2 *c545d_cached_display_name = NULL;\n'
        '      guint64 c545d_before_getter_generation = 0;',
        "remember getter epoch")
    src = once(src,
        '          hr = IPackage2_get_DisplayName (ipackage2, &display_name);\n'
        '          canned_com_error_handler_pkg ("IPackage2_get_DisplayName()", package_cleanup);\n'
        '          /* Cache successful NULL HSTRING',
        '          c545d_before_getter_generation = c545d_bridge_read_generation ();\n'
        '          hr = IPackage2_get_DisplayName (ipackage2, &display_name);\n'
        '          canned_com_error_handler_pkg ("IPackage2_get_DisplayName()", package_cleanup);\n'
        '          /* Cache successful NULL HSTRING',
        "capture pre-getter epoch")
    src = once(src,
        '          if (g_getenv ("C545D_DIAG_UWP_CACHE_DISPLAYNAME") != NULL)\n'
        '            {\n'
        '              if (display_name == NULL)',
        '          if (g_getenv ("C545D_DIAG_UWP_CACHE_DISPLAYNAME") != NULL &&\n'
        '              c545d_bridge_allow_store (c545d_before_getter_generation))\n'
        '            {\n'
        '              if (display_name == NULL)',
        "reject stale getter response")
    path.write_bytes(src.replace("\n", newline).encode("utf-8"))
    print("C545D_WINRT_BRIDGE_GLIB_CI_ONLY_PATCHED")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch_glib_uwp_bridge_integration_diagnostic.py <gwin32packageparser.c>")
    main(Path(sys.argv[1]))
