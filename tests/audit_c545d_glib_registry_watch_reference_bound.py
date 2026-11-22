#!/usr/bin/env python3
"""Source-only bound for GLib 2.82.4 Win32 AppInfo watch *registrations*.

This confirms the documented rearm/CAS/reference balancing contract in
upstream source, NOT that the Windows APC runs, nor that COM/WinRT/worker
allocations are freed. An uncompleted watch can retain one reference even
when AppInfo update_counter == 0. Do not treat a static watch bound as a
global heap-leak zero proof or apply it to the patched recorder DLL.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

UPSTREAM_COMMIT = "ca20e4ac71864f08e980dc044ac96c06d5482b37"
ROOTS = (
    "url_associations_key", "file_exts_key", "user_clients_key",
    "system_clients_key", "applications_key",
    "user_registered_apps_key", "system_registered_apps_key",
    "classes_root_key",
)


def section(src: str, start: str, end: str) -> str:
    if src.count(start) != 1:
        raise ValueError("changed_or_ambiguous_upstream_source_anchor")
    after = src.split(start, 1)[1]
    if end not in after:
        raise ValueError("missing_section_end")
    return after.split(end, 1)[0]


def required_order(src: str, *parts: str) -> None:
    pos = 0
    for part in parts:
        at = src.find(part, pos)
        if at == -1:
            raise ValueError("watch_state_or_lifetime_sequence_drifted")
        pos = at + len(part)


def audit(appinfo: str, registry: str) -> list[str]:
    watch = section(
        registry,
        "gboolean\ng_win32_registry_key_watch (",
        "/**\n * g_win32_registry_key_erase_change_indicator:"
    )
    # Only one transition from UNWATCHED to WATCHED is permitted while the
    # watch is pending; duplicate registrations return before taking a ref.
    required_order(
        watch, "g_atomic_int_compare_and_exchange (",
        "G_WIN32_KEY_UNWATCHED,", "G_WIN32_KEY_WATCHED);",
        "if (!started_to_watch)", "return TRUE;",
        "g_object_ref (key);",
        "status_block = g_malloc (sizeof (IO_STATUS_BLOCK));",
        "status = nt_notify_change_multiple_keys (",
        "if (status == STATUS_PENDING || status == STATUS_SUCCESS)",
        "return TRUE;", "g_object_unref (key);", "g_free (status_block);",
        "return FALSE;",
    )
    if watch.count("g_object_ref (key);") != 1 or watch.count("g_object_unref (key);") != 1:
        raise ValueError("watch_reference_balance_changed")
    apc = section(registry, "static VOID NTAPI\nkey_changed (",
                  "/**\n * g_win32_registry_key_watch:")
    required_order(
        apc, "g_free (status_block);",
        "g_atomic_int_set (&key->priv->watch_indicator, G_WIN32_KEY_UNWATCHED);",
        "if (callback)", "callback (key, user_data);", "g_object_unref (key);"
    )
    if apc.count("g_object_unref (key);") != 1:
        raise ValueError("apc_release_changed")
    init = section(appinfo, "void\ngio_win32_appinfo_init (gboolean do_wait)",
                   "static void g_win32_app_info_iface_init")
    required_order(init, "static gsize initialized;",
                   "g_once_init_enter (&initialized)", "watch_keys ();",
                   "g_once_init_leave (&initialized, TRUE)")
    for root in ROOTS:
        if init.count(root + " =") != 1:
            raise ValueError("appinfo_root_initialization_drift")
    watches = section(appinfo, "static void\nwatch_keys (void)\n{",
                      "/* This is the main function of the AppInfo thread */")
    found = re.findall(r"g_win32_registry_key_watch \((\w+),", watches)
    if len(found) != len(ROOTS) or set(found) != set(ROOTS):
        raise ValueError("global_appinfo_watched_key_set_changed")
    # A callback rearms at most the existing watched-key set. It does not
    # allocate another set of global root keys on each rescan.
    notify = section(appinfo, "static void\nkeys_updated (GWin32RegistryKey  *key,",
                     "static void\nwatch_keys (void)\n{")
    required_order(notify, "watch_keys ();",
                   "g_atomic_int_inc (&gio_win32_appinfo_update_counter);",
                   "g_thread_pool_push (")
    return [
        "C545D_GIO_WATCH_SOURCE_AUDIT_PASS,"
        f"glib_tag=2_82_4,global_key_slots={len(ROOTS)},"
        "watch_deduplicated_by_CAS=1,apc_callback_releases_ref=1,"
        "failure_releases_ref_and_status=1,"
        "one_pending_watch_ref_per_key_while_WATCHED=1,"
        "worker_allocations_bounded_proven=0,"
        "apc_delivery_guaranteed=0,global_quiescence_proven=0,"
        "memory_leak_zero_proven=0,windows_runs=0,real_host_untouched=1"
    ]


def selftest(appinfo: str, registry: str) -> None:
    assert audit(appinfo, registry)[0].startswith(
        "C545D_GIO_WATCH_SOURCE_AUDIT_PASS,"
    )
    altered = [
        (appinfo, registry.replace("if (!started_to_watch)", "if (started_to_watch)", 1)),
        (appinfo, registry.replace("/* Keep it alive until APC is called */\n  g_object_ref (key);",
                                   "/* Keep it alive until APC is called */\n  g_object_ref (key);\n  g_object_ref (key);", 1)),
        (appinfo, registry.replace("g_free (status_block);", "/*missing*/", 1)),
        (appinfo.replace("g_win32_registry_key_watch (classes_root_key,",
                         "g_win32_registry_key_watch (new_unbounded_key,", 1), registry),
        (appinfo.replace("g_once_init_leave (&initialized, TRUE);\n    }\n\n  if (!do_wait)",
                         "g_once_init_leave (&initialized, FALSE);\n    }\n\n  if (!do_wait)", 1), registry),
    ]
    for changed_app, changed_registry in altered:
        try:
            audit(changed_app, changed_registry)
        except ValueError:
            continue
        raise AssertionError("altered Win32 APC watch ownership accepted")
    print("C545D_GIO_WATCH_SOURCE_SELFTEST_PASS,"
          "positive=1,negative=5,windows_runs=0,"
          "no_actual_watch_test=1,raw_uploaded=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--appinfo", type=Path, required=True)
    p.add_argument("--registry", type=Path, required=True)
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    appinfo = args.appinfo.read_text(encoding="utf-8")
    registry = args.registry.read_text(encoding="utf-8")
    if args.selftest:
        selftest(appinfo, registry)
    print("\n".join(audit(appinfo, registry)))


if __name__ == "__main__":
    main()
