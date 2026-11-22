#!/usr/bin/env python3
"""CI-only conservative GLib 2.82.4 GWin32AppInfo dup vector-size fix.

Original g_win32_app_info_dup() erroneously BREAKS in the counting loop,
always leaving i=0 and allocating only one pointer while copying N
supported types and their NUL terminator. A nonempty array overflows.
Replace ONLY that exact pinned function with GLib's deep-copy g_strdupv.
The existing GWin32AppInfo finalize already g_strfreev()s the result.
Source patch is NOT installed on the user's Windows recorder host.
"""
from __future__ import annotations

from pathlib import Path
import sys

OLD = """  if (info->supported_types)
    {
      int i;

      for (i = 0; info->supported_types[i]; i++)
        break;

      new_info->supported_types = g_new (gchar *, i + 1);

      for (i = 0; info->supported_types[i]; i++)
        new_info->supported_types[i] = g_strdup (info->supported_types[i]);

      new_info->supported_types[i] = NULL;
    }
"""
NEW = """  /* Copy the entire NULL-terminated vector, including its terminator.
   * The former counting loop used 'break', so an array with one or more
   * supported types allocated only one gchar* before copying N+1 entries.
   * g_win32_app_info_finalize() already frees it with g_strfreev().
   */
  new_info->supported_types = g_strdupv (info->supported_types);
"""
DEF = "g_win32_app_info_dup (GAppInfo *appinfo)"
FINAL = "  g_clear_pointer (&info->supported_types, g_strfreev);"


def patch(source: str) -> str:
    if source.count(DEF) != 1:
        raise ValueError("wrong_or_missing_dup_function")
    if source.count(OLD) != 1:
        raise ValueError("original_dup_count_loop_changed")
    if source.count(FINAL) != 1:
        raise ValueError("copied_vector_cleanup_contract_changed")
    before = source.index(DEF)
    after = source.find("\nstatic gboolean\ng_win32_app_info_equal", before)
    if after == -1 or OLD not in source[before:after]:
        raise ValueError("dup_loop_not_in_original_function")
    result = source.replace(OLD, NEW, 1)
    if result.count("new_info->supported_types = g_strdupv (info->supported_types);") != 1:
        raise ValueError("new_deep_copy_not_unique")
    if OLD in result:
        raise ValueError("unsafe_old_break_remains")
    return result


def selftest() -> None:
    source = (
        FINAL + "\n"
        "static GAppInfo *\n" + DEF + "\n{\n" + OLD +
        "return G_APP_INFO (new_info);\n}\n"
        "\nstatic gboolean\ng_win32_app_info_equal (GAppInfo *a,GAppInfo *b)\n{}\n"
    )
    changed = patch(source)
    assert NEW in changed
    changes = [
        source.replace("        break;", "        continue;"),
        source.replace("g_strfreev", "g_free"),
        source.replace(DEF, "g_win32_app_info_dup_old (GAppInfo *appinfo)"),
        source.replace("g_new (gchar *, i + 1)", "g_new (gchar *, i + 2)"),
        changed,
    ]
    for bad in changes:
        try:
            patch(bad)
        except ValueError:
            continue
        raise AssertionError("unsafe or repeated source mutation accepted")
    print("C545D_APPINFO_DUP_SOURCE_SELFTEST_PASS,"
          "positive=1,negative=5,corrupt_original_rejected=1,"
          "new_windows_runs=0,host_untouched=1")


def main() -> None:
    if sys.argv[1:] == ["--selftest"]:
        selftest()
        return
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_glib_appinfo_dup_strv_ci.py <disposable-gwin32appinfo.c>")
    p = Path(sys.argv[1])
    original = p.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    result = patch(original.decode("utf-8").replace("\r\n", "\n"))
    p.write_bytes(result.replace("\n", newline).encode("utf-8"))
    print("C545D_APPINFO_DUP_SOURCE_PATCHED,"
          "glib_source=2_82_4,deep_copy=1,vector_terminator_preserved=1,"
          "finalizer_preserved=1,CI_only=1,host_untouched=1")


if __name__ == "__main__":
    main()
