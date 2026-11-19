#!/usr/bin/env python3
"""Disposable-CI-only native Windows package-path alternative; never ship.

Preserves WinRT PackageManager enumeration, display metadata, manifest XML and
callbacks. On GetPackagePathByFullName failure, uses the original WinRT path.
Comparison mode calls BOTH and emits counts only, never package paths/names.
"""
from pathlib import Path
import sys


def replace_one(s, before, after, reason):
    if s.count(before) != 1:
        raise ValueError("C545D_NATIVE_PATH_REFUSED: " + reason)
    return s.replace(before, after, 1)


def patch(filename):
    p = Path(filename)
    data = p.read_bytes()
    nl = "\r\n" if b"\r\n" in data else "\n"
    s = data.decode("utf-8").replace("\r\n", "\n")
    s = replace_one(s, "#include <windows.h>",
                    "#include <windows.h>\n#include <appmodel.h>", "appmodel.h")
    s = replace_one(s, "  struct _xml_sax_state *sax = &sax_stack;",
       """  struct _xml_sax_state *sax = &sax_stack;
  guint native_success = 0, native_fallback = 0;
  guint native_match = 0, native_mismatch = 0;""", "counters")
    s = replace_one(s, "      HSTRING path = NULL;",
       """      HSTRING path = NULL;
      wchar_t *native_path = NULL;
      gboolean native_enabled = g_getenv ("C545D_DIAG_UWP_NATIVE_PATH") != NULL;
      gboolean native_compare = g_getenv ("C545D_DIAG_UWP_NATIVE_COMPARE") != NULL;""",
       "native path local")
    before = """      hr = IPackage_get_InstalledLocation (ipackage, &package_install_location);
      canned_com_error_handler_pkg_named ("IPackage_get_InstalledLocation()", package_cleanup);

      hr = IUnknown_QueryInterface (package_install_location, &IID_IStorageItem, (void **) &storage_item);
      canned_com_error_handler_pkg_named ("IUnknown_QueryInterface(IID_IStorageItem)", package_cleanup);"""
    after = """      /* DIAGNOSTIC ONLY. Do not remove any UWP app parsing/callback. */
      if (native_enabled)
        {
          UINT32 n = 0;
          LONG rc = GetPackagePathByFullName (wcs_full_name, &n, NULL);
          if (rc == ERROR_INSUFFICIENT_BUFFER && n > 1 && n <= 32768)
            {
              native_path = g_new (wchar_t, n);
              rc = GetPackagePathByFullName (wcs_full_name, &n, native_path);
              if (rc != ERROR_SUCCESS)
                g_clear_pointer (&native_path, g_free);
            }
          if (native_path)
            native_success++;
          else
            native_fallback++;
        }
      if (!native_path || native_compare)
        {
          hr = IPackage_get_InstalledLocation (ipackage, &package_install_location);
          canned_com_error_handler_pkg_named ("IPackage_get_InstalledLocation()", package_cleanup);
          hr = IUnknown_QueryInterface (package_install_location, &IID_IStorageItem, (void **) &storage_item);
          canned_com_error_handler_pkg_named ("IUnknown_QueryInterface(IID_IStorageItem)", package_cleanup);
        }"""
    s = replace_one(s, before, after, "WinRT InstalledLocation block")
    before = """      hr = IStorageItem_get_Path (storage_item, &path);
      canned_com_error_handler_pkg_named ("IStorageItem_get_Path()", package_cleanup);

      wcs_path = LoadedWindowsGetStringRawBuffer (path, NULL);"""
    after = """      if (!native_path || native_compare)
        {
          hr = IStorageItem_get_Path (storage_item, &path);
          canned_com_error_handler_pkg_named ("IStorageItem_get_Path()", package_cleanup);
        }
      if (native_compare && native_path && path)
        {
          const wchar_t *original = LoadedWindowsGetStringRawBuffer (path, NULL);
          if (wcscmp (native_path, original) == 0)
            native_match++;
          else
            {
              native_mismatch++;
              /* Strict path match failed: use unmodified original. */
              g_clear_pointer (&native_path, g_free);
            }
        }
      wcs_path = native_path ? native_path : LoadedWindowsGetStringRawBuffer (path, NULL);"""
    s = replace_one(s, before, after, "IStorageItem Path block")
    s = replace_one(s,
       "      package_cleanup:\n      g_clear_pointer (&manifest_filename, g_free);",
       "      package_cleanup:\n      g_clear_pointer (&manifest_filename, g_free);\n"
       "      g_clear_pointer (&native_path, g_free);", "native buffer release")
    s = replace_one(s, "  return result;\n}\n\nstatic gboolean\nparse_manifest_file",
       """  if (g_getenv ("C545D_DIAG_UWP_NATIVE_PATH") != NULL)
    printf ("GIO_NATIVE_PATH,%u,%u,%u,%u\\n", native_success,
            native_fallback, native_match, native_mismatch);
  return result;
}

static gboolean
parse_manifest_file""", "aggregate results")
    p.write_bytes(s.replace("\n", nl).encode("utf-8"))
    print("C545D_DIAGNOSTIC_NATIVE_PATH_ONLY_PATCHED")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_glib_uwp_native_path_diagnostic.py <gio/gwin32packageparser.c>")
    patch(sys.argv[1])
