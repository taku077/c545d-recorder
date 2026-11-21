#!/usr/bin/env python3
"""Read-only audit of exact upstream GLib 2.82.4 registry/APC scheduling.

No Windows runner, registry mutation, DLL build, camera, or memory probe.
Tests source-order *possibility* of late delivery, NOT when an APC fired.
The old 256-cycle sanitized log is validated by saved256-trend CI separately.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def part(text: str, before: str, after: str, label: str) -> str:
    if text.count(before) != 1 or text.count(after) < 1:
        raise ValueError(f"{label}: source anchors missing/ambiguous")
    a = text.index(before)
    b = text.find(after, a + len(before))
    if b < 0:
        raise ValueError(f"{label}: source order changed")
    return text[a:b]


def in_order(fragment: str, needles: tuple[str, ...], label: str) -> None:
    offset = 0
    for needle in needles:
        index = fragment.find(needle, offset)
        if index < 0:
            raise ValueError(f"{label}: required source step missing/out of order")
        offset = index + len(needle)


def audit(app: str, reg: str, probe: str, patch: str,
          workflow: str) -> list[str]:
    worker = part(app, "static void\ngio_win32_appinfo_thread_func (",
                  "/* Initializes Windows AppInfo.", "async worker")
    in_order(worker, ("g_mutex_lock (&gio_win32_appinfo_mutex);",
                      "g_atomic_int_get (&gio_win32_appinfo_update_counter)",
                      "update_registry_data ();",
                      "g_atomic_int_compare_and_exchange",
                      "g_cond_broadcast", "g_mutex_unlock"),
             "worker update and release")
    callback = part(app, "static void\nkeys_updated (",
                    "static void\nwatch_keys (", "registry callback")
    in_order(callback, ("watch_keys ();",
                        "g_atomic_int_inc (&gio_win32_appinfo_update_counter)",
                        "g_thread_pool_push"), "watch rearm/worker queue")
    rebuilt = part(app, "static void\nupdate_registry_data (void)",
                   "static void\nwatch_keys (void);", "app graph rebuild")
    in_order(rebuilt, ("g_clear_pointer (&apps_by_id, g_hash_table_destroy);",
                       "g_clear_pointer (&apps_by_exe, g_hash_table_destroy);",
                       "g_clear_pointer (&fake_apps, g_hash_table_destroy);",
                       "g_clear_pointer (&urls, g_hash_table_destroy);",
                       "g_clear_pointer (&extensions, g_hash_table_destroy);",
                       "g_clear_pointer (&handlers, g_hash_table_destroy);",
                       "apps_by_id =", "g_win32_package_parser_enum_packages",
                       "g_hash_table_unref (uwp_handler_table);"),
             "rebuild old tables disposed before replacement")
    watched = part(reg, "g_win32_registry_key_watch (GWin32RegistryKey",
                   "g_win32_registry_key_erase_change_indicator:", "APC registration")
    in_order(watched, ("g_atomic_int_compare_and_exchange (&key->priv->watch_indicator,",
                       "if (!started_to_watch)", "g_object_ref (key);",
                       "nt_notify_change_multiple_keys",
                       "key_changed,", "TRUE);"), "single in-flight APC watch")
    delivered = part(reg, "static VOID NTAPI\nkey_changed (",
                     "g_win32_registry_key_watch:", "APC completion")
    in_order(delivered, ("g_free (status_block);",
                         "G_WIN32_KEY_UNWATCHED",
                         "if (callback)", "callback (key, user_data);",
                         "g_object_unref (key);"), "APC cleanup")
    if "When the key changes, an APC will be queued" not in reg or (
            "current thread enters alertable state" not in reg):
        raise ValueError("upstream APC delivery contract absent")
    cleanup = part(probe, "/* The last steady-state sample",
                   'printf("GIO_PROBE_DONE,cycles=', "probe after-loop")
    in_order(cleanup, ("RegDeleteValueW(hkey, value_name);",
                       "Sleep(1200);", "enumerate_apps();",
                       'report("after_cleanup", cycle_count + 1);',
                       "Sleep(2500);", "drain_context();", "enumerate_apps();",
                       'report("settled_cleanup", cycle_count + 2);'),
             "non-alertable wait and later enumeration")
    if "SleepEx(" in cleanup:
        raise ValueError("probe cleanup no longer uses ordinary Sleep only")
    if 'g_getenv ("C545D_DIAG_APPINFO_MONITOR_WORKER_FIRE")' not in patch:
        raise ValueError("monitor worker callback opt-in contract changed")
    if "C545D_DIAG_APPINFO_MONITOR_WORKER_FIRE" in workflow:
        raise ValueError("original CI enabled worker monitor callback unexpectedly")
    return [
        "C545D_GIO_APC_SOURCE_AUDIT,glib=2.82.4,registry_watch_uses_APC=1,"
        "one_inflight_watch_guard=1,apc_cleanup_unref=1,CI_only=1",
        "C545D_GIO_WORKER_SOURCE_AUDIT,registry_rearm_before_enqueue=1,"
        "worker_counter_coalesced=1,old_app_tables_destroyed=1,"
        "exact_residual_owner_proven=0,CI_only=1",
        "C545D_GIO_CLEANUP_SOURCE_AUDIT,probe_delete_before_sleep=1,"
        "plain_sleep_alertable=0,post_cleanup_enumerations=2,"
        "apc_delivery_timestamp_observed=0,late_rebuild_possible=1,CI_only=1",
        "C545D_GIO_MONITOR_SCOPE_AUDIT,worker_fire_opt_in=1,"
        "original_256_ci_worker_fire_enabled=0,"
        "zero_callback_is_not_no_rebuild=1,CI_only=1",
        "C545D_GIO_APC_SOURCE_AUDIT_PASS,new_windows_runs=0,"
        "user_host_modified=0,leak_owner_known=0,release_approved=0",
    ]


def selftest() -> None:
    in_order("A B C", ("A", "B", "C"), "synthetic")
    fails = 0
    for data, expected in (("A C B", ("A", "B", "C")),
                           ("A B", ("A", "B", "C")),
                           ("A A C", ("A", "B", "C"))):
        try:
            in_order(data, expected, "synthetic-negative")
        except ValueError:
            fails += 1
    assert fails == 3
    print("C545D_GIO_APC_SOURCE_SELFTEST_PASS,negative_cases=3,windows_runs=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    for item in ("appinfo", "registry", "probe", "monitor-patch", "workflow"):
        p.add_argument("--" + item, type=Path)
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    for name in ("appinfo", "registry", "probe", "monitor_patch", "workflow"):
        if getattr(a, name) is None:
            p.error("--" + name.replace("_", "-") + " required")
    for row in audit(a.appinfo.read_text(encoding="utf-8"),
                     a.registry.read_text(encoding="utf-8"),
                     a.probe.read_text(encoding="utf-8"),
                     a.monitor_patch.read_text(encoding="utf-8"),
                     a.workflow.read_text(encoding="utf-8")):
        print(row)


if __name__ == "__main__":
    main()
