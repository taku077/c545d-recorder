#!/usr/bin/env python3
"""Diagnostic-only GLib 2.82.4 UWP package API stage isolation.

Everything added here is guarded by C545D_DIAG_* environment variables and
only linked into a throwaway Windows CI build. NEVER release these bypasses.
"""
from pathlib import Path
import sys


def replace_one(src, before, after, label):
    count = src.count(before)
    if count != 1:
        raise ValueError(f"{label}: expected one anchor, found {count}")
    return src.replace(before, after, 1)


def patch_appinfo(filename):
    p = Path(filename)
    data = p.read_bytes()
    nl = "\r\n" if b"\r\n" in data else "\n"
    s = data.decode("utf-8").replace("\r\n", "\n")
    before = "static void\nupdate_registry_data (void)\n{"
    callback = """/* CI-only no-op callback; package enumeration and XML parsing still run.
 * An empty callback lets us discriminate AppInfo graph allocation from WinRT.
 */
static gboolean
c545d_diag_noop_uwp_callback (gpointer u,
                              const gunichar2 *full_name,
                              const gunichar2 *name,
                              const gunichar2 *display_name,
                              const gunichar2 *aumid,
                              gboolean show,
                              GPtrArray *extgroups,
                              GPtrArray *protocols)
{
  (void) u; (void) full_name; (void) name; (void) display_name;
  (void) aumid; (void) show; (void) extgroups; (void) protocols;
  return TRUE;
}

"""
    s = replace_one(s, before, callback + before, "callback insertion")
    s = replace_one(s,
        "if (!g_win32_package_parser_enum_packages (uwp_package_cb, NULL, &error))",
        'if (!g_win32_package_parser_enum_packages (\n'
        '       g_getenv ("C545D_DIAG_UWP_NOOP_CALLBACK") != NULL ?\n'
        '       c545d_diag_noop_uwp_callback : uwp_package_cb,\n'
        '       NULL, &error))',
        "callback selector")
    p.write_bytes(s.replace("\n", nl).encode("utf-8"))


def patch_packageparser(filename):
    p = Path(filename)
    data = p.read_bytes()
    nl = "\r\n" if b"\r\n" in data else "\n"
    s = data.decode("utf-8").replace("\r\n", "\n")
    # The diagnostic early exits reach the package_cleanup label before the
    # normal memset(sax,...). Initialize only the field read by cleanup.
    s = replace_one(s,
        "      hr = IIterator_get_Current (packages_iterator, &item);",
        "      sax->exit_early = FALSE;\n"
        "      hr = IIterator_get_Current (packages_iterator, &item);",
        "SAX early-exit safety")
    # Skip only per-item COM retrieval while preserving PackageManager,
    # iterable construction and iterator advancement.
    current = """      hr = IIterator_get_Current (packages_iterator, &item);"""
    skipped_current = """      /* DIAGNOSTIC ONLY: isolate WinRT iterator overhead without
       * retrieving IPackage/identity objects. Nothing is allocated here.
       */
      if (g_getenv ("C545D_DIAG_UWP_SKIP_CURRENT") != NULL)
        {
          hr = IIterator_MoveNext (packages_iterator, &has_current);
          if (FAILED (hr))
            result = FALSE;
          continue;
        }
""" + current
    s = replace_one(s, current, skipped_current, "per-item getter bypass")

    # Keep GetCurrent/identity/Name but exit before DisplayName and location.
    display = """      hr = IPackage2_get_DisplayName (ipackage2, &display_name);"""
    skipped_display = """      /* DIAGNOSTIC ONLY: stop before IPackage2 DisplayName. */
      if (g_getenv ("C545D_DIAG_UWP_SKIP_DISPLAYNAME") != NULL)
        {
          hr = IIterator_MoveNext (packages_iterator, &has_current);
          if (FAILED (hr))
            result = FALSE;
          goto package_cleanup;
        }
""" + display
    s = replace_one(s, display, skipped_display, "DisplayName bypass")
    # Isolate ONLY the DisplayName WinRT getter, not all subsequent work.
    # The diagnostic substitutes the Name field as display text, so this
    # mode is deliberately semantically different and must never be shipped.
    display_pair = ("""      hr = IPackage2_get_DisplayName (ipackage2, &display_name);
      canned_com_error_handler_pkg ("IPackage2_get_DisplayName()", package_cleanup);""")
    display_guard = """      /* CI DIAGNOSTIC ONLY: retain location, family, XML and callback. */
      if (g_getenv ("C545D_DIAG_UWP_NO_DISPLAYNAME_GETTER") == NULL)
        {
          hr = IPackage2_get_DisplayName (ipackage2, &display_name);
          canned_com_error_handler_pkg ("IPackage2_get_DisplayName()", package_cleanup);
        }"""
    s = replace_one(s, display_pair, display_guard,
                    "DisplayName getter-only bypass")
    s = replace_one(s,
        "      wcs_display_name = LoadedWindowsGetStringRawBuffer (display_name, NULL);",
        """      /* Diagnostic-only comparison: call WinRT DisplayName normally,
       * then release its HSTRING before downstream processing. Compare to
       * skip-getter using identical Name fallback and UWP callback behavior.
       * A source-stage experiment; NEVER ship this semantic substitution.
       */
      if (g_getenv ("C545D_DIAG_UWP_CALL_DISPLAYNAME_DISCARD") != NULL &&
          display_name != NULL)
        {
#ifndef G_WINAPI_ONLY_APP
          LoadedWindowsDeleteString (display_name);
#else
          WindowsDeleteString (display_name);
#endif
          display_name = NULL;
        }
      /* WinRT HSTRING(NULL) represents the empty string, not Package Name.
       * Preserve the original GLib semantics even in the CI-only build.
       */
      wcs_display_name = LoadedWindowsGetStringRawBuffer (display_name, NULL);""",
        "DisplayName getter-call and immediate-HSTRING-release ablation")
    location = """      hr = IPackage_get_InstalledLocation (ipackage, &package_install_location);
      canned_com_error_handler_pkg_named ("IPackage_get_InstalledLocation()", package_cleanup);"""
    location2 = """      /* DIAGNOSTIC ONLY: retain WinRT package/identity enumeration, but skip
       * installed location, XML and callback. This is not a product fallback.
       */
      if (g_getenv ("C545D_DIAG_UWP_SKIP_LOCATION") != NULL)
        {
          hr = IIterator_MoveNext (packages_iterator, &has_current);
          if (FAILED (hr))
            result = FALSE;
          goto package_cleanup;
        }

""" + location
    s = replace_one(s, location, location2, "InstalledLocation bypass")
    path = """      hr = IStorageItem_get_Path (storage_item, &path);
      canned_com_error_handler_pkg_named ("IStorageItem_get_Path()", package_cleanup);"""
    path2 = """      /* DIAGNOSTIC ONLY: retain InstalledLocation/QI, skip Path and XML. */
      if (g_getenv ("C545D_DIAG_UWP_SKIP_PATH") != NULL)
        {
          hr = IIterator_MoveNext (packages_iterator, &has_current);
          if (FAILED (hr))
            result = FALSE;
          goto package_cleanup;
        }

""" + path
    s = replace_one(s, path, path2, "IStorageItem Path bypass")
    s = replace_one(s,
        "      parse_manifest_file (sax);",
        """      if (g_getenv ("C545D_DIAG_UWP_SKIP_MANIFEST") == NULL)
        parse_manifest_file (sax);""",
        "XML manifest bypass")
    p.write_bytes(s.replace("\n", nl).encode("utf-8"))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: patch_glib_uwp_api_isolation.py <gwin32appinfo.c> <gwin32packageparser.c>")
    patch_appinfo(sys.argv[1])
    patch_packageparser(sys.argv[2])
    print("C545D_UWP_DIAGNOSTIC_ONLY_PATCHED")
