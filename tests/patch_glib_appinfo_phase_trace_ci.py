#!/usr/bin/env python3
"""CI-only timing trace of the pinned GLib 2.82.4 Win32 AppInfo worker.

Apply to a DISPOSABLE gwin32appinfo.c checkout AFTER the existing diagnostic
source patches. Do not patch the production DLL or original probe.

The trace logs only phase names, monotonic process-local tick counts and
ordinals. g_print itself can change scheduling: do not compare resource deltas
with an uninstrumented test or claim that a quiet interval proves quiescence.
"""
from pathlib import Path
import sys


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected exactly one anchor; found {count}")
    return source.replace(old, new, 1)


TRACE_HELPER = r'''/* C545D disposable CI-only timing trace. No registry paths, names or
 * allocations are printed. This trace deliberately does not change the
 * registry watcher, parser, lock acquisition order or callback behavior.
 * g_print can affect timing; values are diagnostic, not a matched A/B.
 */
static gint c545d_ci_trace_registry_ordinal;
static gint c545d_ci_trace_worker_ordinal;
static gint c545d_ci_trace_active_worker;

static void
c545d_ci_appinfo_trace (const gchar *phase, gint ordinal)
{
  if (g_getenv ("C545D_CI_APPINFO_PHASE_TRACE") != NULL)
    g_print ("C545D_CI_APPINFO_TRACE,phase=%s,ordinal=%d,tick_ms=%llu\n",
             phase, ordinal, (unsigned long long) GetTickCount64 ());
}

'''


def patch(source: str) -> str:
    source = replace_once(
        source,
        "static void\nkeys_updated (GWin32RegistryKey  *key,\n"
        "              gpointer            user_data)\n{",
        TRACE_HELPER +
        "static void\nkeys_updated (GWin32RegistryKey  *key,\n"
        "              gpointer            user_data)\n{",
        "trace helper declaration")
    source = replace_once(
        source,
        "keys_updated (GWin32RegistryKey  *key,\n"
        "              gpointer            user_data)\n{\n  watch_keys ();",
        "keys_updated (GWin32RegistryKey  *key,\n"
        "              gpointer            user_data)\n{\n"
        "  gint ordinal = g_atomic_int_add (&c545d_ci_trace_registry_ordinal, 1) + 1;\n"
        "  c545d_ci_appinfo_trace (\"registry_callback\", ordinal);\n"
        "  watch_keys ();",
        "registry callback trace")
    source = replace_once(
        source,
        "  if (saved_counter > 0)\n    update_registry_data ();",
        "  if (saved_counter > 0)\n"
        "    {\n"
        "      gint ordinal = g_atomic_int_add (&c545d_ci_trace_worker_ordinal, 1) + 1;\n"
        "      g_atomic_int_set (&c545d_ci_trace_active_worker, ordinal);\n"
        "      c545d_ci_appinfo_trace (\"worker_begin\", ordinal);\n"
        "      update_registry_data ();\n"
        "      c545d_ci_appinfo_trace (\"worker_scan_end\", ordinal);\n"
        "    }",
        "worker scan begin/end")
    source = replace_once(
        source,
        "  if (!g_win32_package_parser_enum_packages (uwp_package_cb, NULL, &error))",
        "  c545d_ci_appinfo_trace (\"parser_begin\",\n"
        "                          g_atomic_int_get (&c545d_ci_trace_active_worker));\n"
        "  if (!g_win32_package_parser_enum_packages (uwp_package_cb, NULL, &error))",
        "package parser begin")
    source = replace_once(
        source,
        "  read_uwp_handler_info ();\n\n  uwp_end = GetTickCount ();",
        "  c545d_ci_appinfo_trace (\"parser_end\",\n"
        "                          g_atomic_int_get (&c545d_ci_trace_active_worker));\n"
        "  read_uwp_handler_info ();\n\n  uwp_end = GetTickCount ();",
        "package parser end")
    source = replace_once(
        source,
        "  g_mutex_unlock (&gio_win32_appinfo_mutex);\n"
        "  /* Notify from the completed AppInfo worker,",
        "  g_mutex_unlock (&gio_win32_appinfo_mutex);\n"
        "  if (saved_counter > 0)\n"
        "    c545d_ci_appinfo_trace (\"worker_unlocked\",\n"
        "                            g_atomic_int_get (&c545d_ci_trace_active_worker));\n"
        "  /* Notify from the completed AppInfo worker,",
        "post-unlock worker trace")
    return source


def selftest() -> None:
    raw = (
        "static void\nkeys_updated (GWin32RegistryKey  *key,\n"
        "              gpointer            user_data)\n{\n"
        "  watch_keys ();\n}\n"
        "  if (saved_counter > 0)\n    update_registry_data ();\n"
        "  if (!g_win32_package_parser_enum_packages (uwp_package_cb, NULL, &error))\n"
        "  read_uwp_handler_info ();\n\n  uwp_end = GetTickCount ();\n"
        "  g_mutex_unlock (&gio_win32_appinfo_mutex);\n"
        "  /* Notify from the completed AppInfo worker,"
    )
    result = patch(raw)
    for marker in ("registry_callback", "worker_begin", "worker_scan_end",
                   "parser_begin", "parser_end", "worker_unlocked"):
        assert marker in result
    for needle in (
        "  if (saved_counter > 0)\n    update_registry_data ();",
        "  read_uwp_handler_info ();\n\n  uwp_end = GetTickCount ();",
        "  /* Notify from the completed AppInfo worker,",
    ):
        try:
            patch(raw.replace(needle, "MISSING", 1))
        except ValueError:
            pass
        else:
            raise AssertionError("drifted source accepted")
    print("C545D_APPINFO_TRACE_SOURCE_SELFTEST_PASS,negative_cases=3,"
          "windows_runs=0,original_source_unchanged=1")


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        selftest()
        return
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_glib_appinfo_phase_trace_ci.py <disposable/gwin32appinfo.c>")
    path = Path(sys.argv[1])
    if path.name != "gwin32appinfo.c":
        raise ValueError("refusing non-gwin32appinfo source")
    original = path.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    edited = patch(original.decode("utf-8").replace("\r\n", "\n"))
    path.write_bytes(edited.replace("\n", newline).encode("utf-8"))
    print("C545D_APPINFO_TRACE_SOURCE_PATCHED,diagnostic_only=1,"
          "no_export_change=1,telemetry_timing_perturbation=1")


if __name__ == "__main__":
    main()
