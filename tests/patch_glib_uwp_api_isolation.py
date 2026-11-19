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
