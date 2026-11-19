#!/usr/bin/env python3
"""CI-ONLY DisplayName exact-string cache for Windows GLib 2.82.4.

A bounded, process-local experiment: identical package full names reuse the
UTF-16 value returned by the original WinRT IPackage2 getter on first use.
This changes freshness/localization/update semantics. NEVER ship as a fix.
Called after patch_glib_uwp_api_isolation.py on disposable source only.
"""
from pathlib import Path
import sys


def replace_one(source, old, new, label):
    count = source.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one source anchor; got {count}")
    return source.replace(old, new, 1)


HELPERS = r"""/* CI DIAGNOSTIC ONLY: a bounded per-process exact original DisplayName cache.
 * Locale/resource updates and re-installation while running are NOT handled.
 * Do not ship this in a production DLL.
 */
static GMutex c545d_display_cache_lock;
static GHashTable *c545d_display_cache;
static guint c545d_display_cache_hits;
static guint c545d_display_cache_misses;
static gint c545d_display_cache_null_hstring_returns;
static guint c545d_diag_refresh_scans;
static guint c545d_diag_refresh_resets;

static gunichar2 *
c545d_cache_display_lookup (const wchar_t *full_name)
{
  gunichar2 *result = NULL;
  gchar *key = g_utf16_to_utf8 ((const gunichar2 *) full_name, -1,
                                NULL, NULL, NULL);
  if (key == NULL)
    return NULL;
  g_mutex_lock (&c545d_display_cache_lock);
  if (c545d_display_cache == NULL)
    c545d_display_cache = g_hash_table_new_full (g_str_hash, g_str_equal,
                                                  g_free, g_free);
  const gunichar2 *stored = g_hash_table_lookup (c545d_display_cache, key);
  if (stored != NULL)
    {
      result = g_wcsdup (stored, -1);
      c545d_display_cache_hits++;
    }
  else
    c545d_display_cache_misses++;
  g_mutex_unlock (&c545d_display_cache_lock);
  g_free (key);
  return result;
}

static void
c545d_cache_display_store (const wchar_t *full_name, const wchar_t *display_name)
{
  gchar *key;
  gunichar2 *value;

  if (full_name == NULL || display_name == NULL)
    return;
  key = g_utf16_to_utf8 ((const gunichar2 *) full_name, -1, NULL, NULL, NULL);
  if (key == NULL)
    return;
  value = g_wcsdup ((const gunichar2 *) display_name, -1);
  g_mutex_lock (&c545d_display_cache_lock);
  if (c545d_display_cache == NULL)
    c545d_display_cache = g_hash_table_new_full (g_str_hash, g_str_equal,
                                                  g_free, g_free);
  /* Hard cap protects a long-lived recorder from an unbounded cache.
   * Beyond the cap the *original getter* runs, preserving functionality. */
  if (g_hash_table_contains (c545d_display_cache, key) ||
      g_hash_table_size (c545d_display_cache) < 1024)
    g_hash_table_replace (c545d_display_cache, key, value);
  else
    {
      g_free (key);
      g_free (value);
    }
  g_mutex_unlock (&c545d_display_cache_lock);
}

static void
c545d_cache_maybe_refresh (void)
{
  const gchar *value;
  gchar *end = NULL;
  guint64 n;

  /* Synthetic event delivery only. Real package events are NOT subscribed
   * by this GLib source; unlike an actual OS notification, this is a fixed
   * scan interval and is never a production invalidation strategy.
   */
  if (g_getenv ("C545D_DIAG_UWP_CACHE_DISPLAYNAME") == NULL)
    return;
  value = g_getenv ("C545D_DIAG_UWP_CACHE_REFRESH_EVERY");
  if (value == NULL)
    return;
  n = g_ascii_strtoull (value, &end, 10);
  if (!end || *end != '\0' || n < 2 || n > 256)
    return;

  g_mutex_lock (&c545d_display_cache_lock);
  c545d_diag_refresh_scans++;
  if (c545d_diag_refresh_scans > 1 &&
      (c545d_diag_refresh_scans - 1) % n == 0)
    {
      /* Caches keep fully-owned UTF16 copies; atomically drop under lock.
       * Future readers must call the actual WinRT getter again.
       */
      if (c545d_display_cache != NULL)
        g_hash_table_remove_all (c545d_display_cache);
      c545d_diag_refresh_resets++;
    }
  g_mutex_unlock (&c545d_display_cache_lock);
}

static void
c545d_cache_display_report (void)
{
  guint entries;
  guint hits;
  guint misses;

  g_mutex_lock (&c545d_display_cache_lock);
  entries = c545d_display_cache ? g_hash_table_size (c545d_display_cache) : 0;
  hits = c545d_display_cache_hits;
  misses = c545d_display_cache_misses;
  g_mutex_unlock (&c545d_display_cache_lock);
  /* Numeric counters only: no installed package IDs, names or paths. */
  g_print ("C545D_DISPLAY_CACHE,hits=%u,misses=%u,entries=%u\n",
           hits, misses, entries);
  g_print ("C545D_DISPLAY_CACHE_NULL_HSTRING_RETURNS=%d\n",
           g_atomic_int_get (&c545d_display_cache_null_hstring_returns));
  g_print ("C545D_DISPLAY_CACHE_REFRESH,scans=%u,resets=%u\n",
           c545d_diag_refresh_scans, c545d_diag_refresh_resets);
}

"""


def main(path):
    original = path.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    s = original.decode("utf-8").replace("\r\n", "\n")

    s = replace_one(
        s, "gboolean\ng_win32_package_parser_enum_packages",
        HELPERS + "gboolean\ng_win32_package_parser_enum_packages",
        "helper functions")

    s = replace_one(
        s, "  gboolean result = TRUE;\n  HRESULT hr;",
        "  gboolean result = TRUE;\n  HRESULT hr;\n"
        "  c545d_cache_maybe_refresh ();",
        "CI-only synthetic cache refresh at each package scan")

    s = replace_one(
        s, "      HSTRING display_name = NULL;",
        "      HSTRING display_name = NULL;\n"
        "      gunichar2 *c545d_cached_display_name = NULL;",
        "per-package owned UTF-16 cache hit")

    start = """      if (g_getenv ("C545D_DIAG_UWP_NO_DISPLAYNAME_GETTER") == NULL)
        {
          hr = IPackage2_get_DisplayName (ipackage2, &display_name);
          canned_com_error_handler_pkg ("IPackage2_get_DisplayName()", package_cleanup);
        }"""
    guarded = """      /* CI DIAGNOSTIC: first use calls the real WinRT getter and caches
       * exactly the returned display string for subsequent package rescans.
       * All remaining XML and callbacks are unchanged.
       */
      if (g_getenv ("C545D_DIAG_UWP_CACHE_DISPLAYNAME") != NULL)
        c545d_cached_display_name = c545d_cache_display_lookup (
          LoadedWindowsGetStringRawBuffer (full_name, NULL));
      if (c545d_cached_display_name == NULL &&
          g_getenv ("C545D_DIAG_UWP_NO_DISPLAYNAME_GETTER") == NULL)
        {
          hr = IPackage2_get_DisplayName (ipackage2, &display_name);
          canned_com_error_handler_pkg ("IPackage2_get_DisplayName()", package_cleanup);
          /* Cache successful NULL HSTRING as the exact empty string.
           * WindowsGetStringRawBuffer(NULL) returns a non-NULL L"" buffer.
           * This prevents the same package being re-fetched every scan.
           */
          if (g_getenv ("C545D_DIAG_UWP_CACHE_DISPLAYNAME") != NULL)
            {
              if (display_name == NULL)
                g_atomic_int_inc (&c545d_display_cache_null_hstring_returns);
              c545d_cache_display_store (
                LoadedWindowsGetStringRawBuffer (full_name, NULL),
                LoadedWindowsGetStringRawBuffer (display_name, NULL));
            }
        }"""
    s = replace_one(s, start, guarded, "getter hit/miss switch")

    s = replace_one(
        s, """      wcs_display_name = LoadedWindowsGetStringRawBuffer (display_name, NULL);""",
        """      wcs_display_name = c545d_cached_display_name != NULL
        ? (const wchar_t *) c545d_cached_display_name
        : LoadedWindowsGetStringRawBuffer (display_name, NULL);""",
        "preserve exact displayed text for callbacks")

    s = replace_one(
        s, "      if (display_name)\n        LoadedWindowsDeleteString (display_name);",
        "      g_clear_pointer (&c545d_cached_display_name, g_free);\n"
        "      if (display_name)\n        LoadedWindowsDeleteString (display_name);",
        "free owned temporary cached copy")

    s = replace_one(
        s, "  return result;\n}\n\nstatic gboolean\nparse_manifest_file",
        """  if (g_getenv ("C545D_DIAG_UWP_CACHE_DISPLAYNAME") != NULL)
    c545d_cache_display_report ();
  return result;
}

static gboolean
parse_manifest_file""",
        "emit sanitized bounded-cache stats")
    path.write_bytes(s.replace("\n", newline).encode("utf-8"))
    print("C545D_DISPLAY_CACHE_DIAGNOSTIC_ONLY_PATCHED")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: patch_glib_uwp_displayname_cache_diagnostic.py "
            "<gwin32packageparser.c>")
    main(Path(sys.argv[1]))
