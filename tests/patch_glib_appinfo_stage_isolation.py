#!/usr/bin/env python3
"""DIAGNOSTIC ONLY: gate AppInfo scan stages by environment on disposable CI.
Never build this optional stage-skip variant for the recorder or as a release.
This does not modify the combined production-candidate patch logic.
"""
from pathlib import Path
import sys


def patch(filename):
    p = Path(filename)
    raw = p.read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    s = raw.decode("utf-8").replace("\r\n", "\n")
    target = "static void\nupdate_registry_data (void)\n{"
    if s.count(target) != 1:
        raise ValueError("unexpected GLib AppInfo refresh anchor")
    a = s.index(target)
    b = s.index("\nstatic void\nwatch_keys (void);", a)
    section = s[a:b]
    changes = [
        ('  read_urls (url_associations);',
         '  if (g_getenv ("C545D_DIAG_SKIP_ASSOCIATIONS") == NULL)\n    read_urls (url_associations);'),
        ('  read_exts (file_exts);',
         '  if (g_getenv ("C545D_DIAG_SKIP_ASSOCIATIONS") == NULL)\n    read_exts (file_exts);'),
        ('  read_exeapps ();',
         '  if (g_getenv ("C545D_DIAG_SKIP_EXE_CLASSES") == NULL)\n    read_exeapps ();'),
        ('  read_classes (classes_root);',
         '  if (g_getenv ("C545D_DIAG_SKIP_EXE_CLASSES") == NULL)\n    read_classes (classes_root);'),
        ('  if (!g_win32_package_parser_enum_packages (uwp_package_cb, NULL, &error))',
         '  if (g_getenv ("C545D_DIAG_SKIP_UWP") == NULL &&\n      !g_win32_package_parser_enum_packages (uwp_package_cb, NULL, &error))'),
        ('  read_uwp_handler_info ();',
         '  if (g_getenv ("C545D_DIAG_SKIP_UWP") == NULL)\n    read_uwp_handler_info ();'),
    ]
    for before, after in changes:
        if section.count(before) != 1:
            raise ValueError("stage isolation source signature changed: " + before)
        section = section.replace(before, after, 1)
    s = s[:a] + section + s[b:]
    p.write_bytes(s.replace("\n", nl).encode("utf-8"))
    print("C545D_STAGE_ISOLATION_DIAGNOSTIC_ONLY_PATCHED")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_glib_appinfo_stage_isolation.py <gio/gwin32appinfo.c>")
    patch(sys.argv[1])
