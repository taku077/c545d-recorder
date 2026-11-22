#!/usr/bin/env python3
"""Bounded registry-watch reference/IO_STATUS_BLOCK source-lifetime audit.

Pinned GLib 2.82.4 Windows code intentionally holds one key reference and
one IO_STATUS_BLOCK per active registry watch. The APC completion frees
that status block, resets the watched indicator, calls keys_updated(),
which rearms a watch, and finally drops the old key reference.

This is an audit of a *specific source ownership mechanism*, NOT a
measurement of all residual PrivateUsage, and NOT proof of OS-global idle.
Never accept 'update_counter == 0' as a watch/APC cancellation barrier.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re

WATCHES = 8

def scoped(source: str, start: str, end: str) -> str:
    if source.count(start) != 1:
        raise ValueError("source_signature_missing_or_ambiguous")
    a = source.index(start)
    b = source.find(end, a + len(start))
    if b <= a:
        raise ValueError("source_lifetime_scope_missing")
    return source[a:b]

def ordered(fragment: str, keys: tuple[str, ...], label: str) -> None:
    points = []
    for marker in keys:
        if fragment.count(marker) != 1:
            raise ValueError(f"{label}_ownership_contract_changed")
        points.append(fragment.index(marker))
    if points != sorted(points):
        raise ValueError(f"{label}_lifetime_order_changed")

def audit(registry: str, appinfo: str) -> str:
    apc = scoped(registry, "static VOID NTAPI\nkey_changed (",
                 "/**\n * g_win32_registry_key_watch:")
    ordered(apc, (
        "g_free (status_block);",
        "G_WIN32_KEY_UNWATCHED);",
        "if (callback)",
        "callback (key, user_data);",
        "g_object_unref (key);",
    ), "APC_completion")
    watch = scoped(registry, "gboolean\ng_win32_registry_key_watch (",
                   "/**\n * g_win32_registry_key_erase_change_indicator:")
    ordered(watch, (
        "g_atomic_int_compare_and_exchange (&key->priv->watch_indicator,",
        "G_WIN32_KEY_UNWATCHED,",
        "G_WIN32_KEY_WATCHED);",
        "if (!started_to_watch)\n    return TRUE;",
        "g_object_ref (key);",
        "status_block = g_malloc (sizeof (IO_STATUS_BLOCK));",
        "status = nt_notify_change_multiple_keys (",
        "if (status == STATUS_PENDING || status == STATUS_SUCCESS)\n    return TRUE;",
        "g_object_unref (key);",
        "g_free (status_block);",
    ), "registry_watch")
    if watch.count("status_block = g_malloc (sizeof (IO_STATUS_BLOCK));") != 1:
        raise ValueError("status_block_per_registration_changed")
    if watch.count("g_object_ref (key);") != 1 or watch.count("g_object_unref (key);") != 1:
        raise ValueError("key_reference_balance_changed")
    if "key_changed,\n" not in watch or "TRUE);" not in watch:
        raise ValueError("asynchronous_APC_watch_not_proven")
    callbacks = scoped(appinfo, "static void\nkeys_updated (", "static void\nwatch_keys (void)\n{")
    ordered(callbacks, (
        "watch_keys ();",
        "g_atomic_int_inc (&gio_win32_appinfo_update_counter);",
        "g_thread_pool_push (gio_win32_appinfo_threadpool, (gpointer) keys_updated, NULL);",
    ), "appinfo_rearm")
    roots = scoped(appinfo, "static void\nwatch_keys (void)\n{",
                   "/* This is the main function of the AppInfo thread */")
    if roots.count("g_win32_registry_key_watch (") != WATCHES:
        raise ValueError("registry_root_count_or_rearm_changed")
    init = scoped(appinfo, "void\ngio_win32_appinfo_init (gboolean do_wait)",
                  "static void g_win32_app_info_iface_init (GAppInfoIface *iface);")
    ordered(init, (
        "watch_keys ();",
        "gio_win32_appinfo_threadpool = g_thread_pool_new",
        "g_atomic_int_set (&gio_win32_appinfo_update_counter, 1);",
        "g_thread_pool_push (gio_win32_appinfo_threadpool, (gpointer) keys_updated, NULL);",
        "if (!do_wait)\n    return;",
        "while (g_atomic_int_get (&gio_win32_appinfo_update_counter) > 0)",
    ), "appinfo_initialization")
    if "GET_MODULE_HANDLE_EX_FLAG_PIN" not in init:
        raise ValueError("GIO_module_lifetime_changed")
    if "watch_indicator" in init or "status_block" in init:
        raise ValueError("unexpected_global_APC_barrier_must_be_reaudited")
    worker = scoped(appinfo, "static void\ngio_win32_appinfo_thread_func (",
                    "/* Initializes Windows AppInfo.")
    ordered(worker, (
        "saved_counter = g_atomic_int_get (&gio_win32_appinfo_update_counter);",
        "update_registry_data ();",
        "g_atomic_int_compare_and_exchange  (&gio_win32_appinfo_update_counter,",
        "g_cond_broadcast (&gio_win32_appinfo_cond);",
        "g_mutex_unlock (&gio_win32_appinfo_mutex);",
    ), "appinfo_worker")
    return (
        "C545D_REGISTRY_APC_OWNERSHIP_SOURCE_PASS,glib=2.82.4,"
        "appinfo_watch_roots=8,at_most_one_registered_watch_per_key=1,"
        "watch_attempt_while_watched_skips_new_allocation=1,"
        "status_block_allocated_per_new_registration=1,"
        "status_block_freed_at_APC_or_failed_watch=1,"
        "key_ref_released_at_APC_or_failed_watch=1,"
        "callback_rearms_before_old_key_unref=1,"
        "watch_memory_expected_process_lifetime=1,"
        "appinfo_counter_zero_does_not_drain_APC=1,"
        "source_supported_bounded_subscription_mechanism=1,"
        "measured_owner_live_bytes=0,real_GIO_residual_classified=0,"
        "host_untouched=1"
    )


@dataclass
class Watcher:
    watched: bool = False
    old_ref_in_callback: bool = False
    def arm(self) -> int:
        if self.watched:
            return 0
        self.watched = True
        return 1
    def deliver(self) -> int:
        if not self.watched:
            raise ValueError("completion_for_nonpending_watch")
        # The APC frees its own IO_STATUS_BLOCK and marks it unwatched.
        self.watched = False
        self.old_ref_in_callback = True
        self.arm()  # AppInfo callback watch_keys() establishes new watch.
        self.old_ref_in_callback = False # last g_object_unref in key_changed.
        return 1

def model_test() -> str:
    watchers = [Watcher() for _ in range(WATCHES)]
    assert sum(w.arm() for w in watchers) == WATCHES
    assert sum(w.arm() for w in watchers) == 0
    peak_registered = 0
    for epoch in range(2048):
        watchers[epoch % WATCHES].deliver()
        assert sum(w.watched for w in watchers) == WATCHES
        assert not any(w.old_ref_in_callback for w in watchers)
        peak_registered = max(peak_registered, sum(w.watched for w in watchers))
    assert peak_registered == WATCHES
    try:
        Watcher().deliver()
    except ValueError:
        pass
    else:
        raise AssertionError("unregistered_APC_should_fail_closed")
    return (
        "C545D_REGISTRY_APC_LIFETIME_MODEL_PASS,watch_roots=8,"
        "synthetic_notifications=2048,steady_pending_status_blocks_at_most=8,"
        "steady_watch_refs_at_most=8,"
        "rearm_transient_old_plus_new_reference_possible=1,"
        "per_epoch_unbounded_growth_in_model=0,"
        "not_GIO_runtime_proof=1,no_windows_measurement=1"
    )


def selftest(registry: str, appinfo: str) -> None:
    assert audit(registry, appinfo).startswith("C545D_REGISTRY_APC_OWNERSHIP_SOURCE_PASS,")
    errors = [
        (registry.replace("if (!started_to_watch)\n    return TRUE;",
                          "if (!started_to_watch)\n    return FALSE;", 1), appinfo),
        (registry.replace("g_object_ref (key);", "g_object_ref (key);\n  g_object_ref (key);", 1), appinfo),
        (registry.replace("status_block = g_malloc (sizeof (IO_STATUS_BLOCK));",
                          "status_block = NULL;", 1), appinfo),
        (registry.replace("g_free (status_block);", "/* missed free */", 1), appinfo),
        (registry.replace("g_object_unref (key);", "/* missed unref */", 1), appinfo),
        (registry.replace("G_WIN32_KEY_UNWATCHED);", "G_WIN32_KEY_WATCHED);", 1), appinfo),
        (registry, appinfo.replace("g_win32_registry_key_watch (user_clients_key,", "removed_watch (user_clients_key,", 1)),
        (registry, appinfo.replace("g_atomic_int_inc (&gio_win32_appinfo_update_counter);", "/* lost epoch */", 1)),
        (registry, appinfo.replace("while (g_atomic_int_get (&gio_win32_appinfo_update_counter) > 0)", "while (FALSE)", 1)),
        (registry, appinfo.replace("GET_MODULE_HANDLE_EX_FLAG_PIN", "GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT", 1)),
    ]
    for i, (reg, app) in enumerate(errors):
        try:
            audit(reg, app)
        except ValueError:
            continue
        raise AssertionError(f"source_lifetime_mutation_accepted,index={i}")
    print("C545D_REGISTRY_APC_OWNERSHIP_SELFTEST_PASS,positive=1,negative=10")
    print(model_test())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--registry", type=Path, required=True)
    p.add_argument("--appinfo", type=Path, required=True)
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    reg = a.registry.read_text(encoding="utf-8").replace("\r\n", "\n")
    app = a.appinfo.read_text(encoding="utf-8").replace("\r\n", "\n")
    print(audit(reg, app))
    if a.selftest:
        selftest(reg, app)

if __name__ == "__main__":
    main()
