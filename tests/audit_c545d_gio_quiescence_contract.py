#!/usr/bin/env python3
"""Source-grounded, fail-closed audit of Win32 AppInfo quiescence semantics.

This script NEVER waits on or mutates the user's recorder. It verifies exact
GLib 2.82.4 sources and the already-saved numeric results from Windows
Actions #44992842208. A GLib update_counter==0 is NOT a guarantee that
queued Windows APC/WinRT callbacks are drained, nor is a fixed sleep.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import analyze_c545d_phase_trace_archived as archived


def unique_segment(source: str, start: str, stop: str, label: str) -> str:
    if source.count(start) != 1:
        raise ValueError(f"{label}: expected exactly one start anchor")
    body = source.split(start, 1)[1]
    if body.count(stop) < 1:
        raise ValueError(f"{label}: missing end anchor")
    return body.split(stop, 1)[0]


def require(body: str, needles: tuple[str, ...], label: str) -> None:
    for needle in needles:
        if needle not in body:
            raise ValueError(f"{label}: missing required source invariant: {needle}")


def audit_source(app: str, registry: str) -> list[str]:
    # Match the actual upstream functions, not preprocessed comment snippets.
    notification = unique_segment(
        app,
        "static void\nkeys_updated (GWin32RegistryKey  *key,\n"
        "              gpointer            user_data)\n{",
        "\nstatic void\nwatch_keys (void)\n{",
        "GIO registry callback")
    require(notification, (
        "watch_keys ();",
        "g_atomic_int_inc (&gio_win32_appinfo_update_counter);",
        "g_thread_pool_push (gio_win32_appinfo_threadpool, (gpointer) keys_updated, NULL);",
    ), "GIO registry callback")

    worker = unique_segment(
        app,
        "static void\ngio_win32_appinfo_thread_func (gpointer data,\n"
        "                               gpointer user_data)\n{",
        "/* Initializes Windows AppInfo.", "GIO worker")
    require(worker, (
        "g_mutex_lock (&gio_win32_appinfo_mutex);",
        "saved_counter = g_atomic_int_get (&gio_win32_appinfo_update_counter);",
        "update_registry_data ();",
        "g_atomic_int_compare_and_exchange  (&gio_win32_appinfo_update_counter,",
        "g_cond_broadcast (&gio_win32_appinfo_cond);",
        "g_mutex_unlock (&gio_win32_appinfo_mutex);",
    ), "GIO worker")

    init = unique_segment(
        app, "void\ngio_win32_appinfo_init (gboolean do_wait)\n{",
        "static void g_win32_app_info_iface_init", "GIO public wait")
    require(init, (
        "g_thread_pool_new (gio_win32_appinfo_thread_func,",
        "                                                        1,",
        "  if (!do_wait)\n    return;",
        "g_atomic_int_get (&gio_win32_appinfo_update_counter) > 0",
        "g_cond_wait (&gio_win32_appinfo_cond, &gio_win32_appinfo_mutex);",
    ), "GIO public wait")

    apc = unique_segment(
        registry,
        "static VOID NTAPI\nkey_changed (PVOID            closure,\n"
        "             PIO_STATUS_BLOCK status_block,\n"
        "             ULONG            reserved)\n{",
        "/**\n * g_win32_registry_key_watch:", "Windows registry APC")
    require(apc, (
        "g_atomic_int_set (&key->priv->change_indicator, G_WIN32_KEY_CHANGED);",
        "callback (key, user_data);",
        "g_object_unref (key);",
    ), "Windows registry APC")

    watch = unique_segment(
        registry,
        "gboolean\ng_win32_registry_key_watch (GWin32RegistryKey                   *key,",
        "/**\n * g_win32_registry_key_erase_change_indicator:", "registry watch")
    require(watch, (
        "key_changed,",
        "g_object_ref (key);",
        "status == STATUS_PENDING || status == STATUS_SUCCESS",
    ), "registry watch")
    require(registry, (
        "The APC\n * will run when the current thread enters alertable state",
    ), "APC documentation")
    # The source-level wait acknowledges only a fully processed AppInfo
    # update_counter. It does NOT acknowledge a Windows APC not delivered yet.
    return [
        "C545D_IDLE_SOURCE_AUDIT_PASS,glib=2.82.4,"
        "watcher_APC_delivery=1,worker_update_counter=1,"
        "conditional_wait=1,public_wait_for_APC_drain=0,"
        "counter_zero_is_global_idle=0",
    ]


@dataclass(frozen=True)
class Observation:
    app_update_counter: int
    worker_active: bool
    queued_jobs: int
    undelivered_apc: int | None
    untracked_winrt_work: int | None
    producers_frozen: bool

    def app_worker_drained(self) -> bool:
        return (self.app_update_counter == 0
                and not self.worker_active and self.queued_jobs == 0)

    def defensible_global_idle(self) -> bool:
        # Strictly a *hypothetical* externally coordinated barrier. GLib
        # 2.82.4 does not expose/implement this contract.
        return (self.app_worker_drained()
                and self.producers_frozen
                and self.undelivered_apc == 0
                and self.untracked_winrt_work == 0)


def audit_archive(raw: str) -> list[str]:
    # Validate every archived line through the independent existing checker
    # before interpreting the specific Windows numeric observations.
    archived.check(raw)
    controls = archived.PHASES
    nochange, registry = controls["nochange"], controls["registry"]
    if (registry["worker_active_after_cleanup"] != 1
            or registry["worker_scans_idle"] != 1
            or registry["parser_ends_idle"] != 1
            or registry["worker_completed_after_cleanup"] != 1
            or registry["worker_active_final"] != 0
            or registry["boundary_tick_ambiguous"] != 1
            or registry["callbacks_idle"] != 0
            or nochange["workers"] != 1
            or nochange["worker_scans_idle"] != 0):
        raise ValueError("actual archived 16-cycle chronology is not the pinned result")

    # Having an in-flight worker at after_cleanup makes this a transitional
    # measurement, not an async-idle memory baseline. The final sample is
    # merely 'no worker observed active', never 'OS globally quiescent'.
    return [
        "C545D_IDLE_ARCHIVE_INTERPRETATION,source_run=44992842208,"
        "registry_after_cleanup_worker_active=1,"
        "registry_idle_window_worker_rebuild=1,"
        "registry_final_worker_active=0,"
        "counter_and_APC_barrier_observed=0,"
        "global_quiescence_proven=0,"
        "post_cleanup_steady_state_valid=0,"
        "final_steady_state_proven=0,"
        "prior_256_cycle_private_leak_owner_proven=0,"
        "windows_rerun=0,real_host_untouched=1",
    ]


def selftest() -> None:
    clean = Observation(0, False, 0, 0, 0, True)
    assert clean.app_worker_drained()
    assert clean.defensible_global_idle()
    # The crucial counterexample: a Windows APC can still be waiting after
    # the GIO appinfo counter becomes 0 and after an idle sleep.
    cases = [
        Observation(0, False, 0, 1, 0, True),
        Observation(0, False, 0, None, 0, True),
        Observation(0, False, 0, 0, None, True),
        Observation(0, False, 0, 0, 0, False),
        Observation(1, False, 0, 0, 0, True),
        Observation(0, True, 0, 0, 0, True),
        Observation(0, False, 1, 0, 0, True),
    ]
    assert all(not c.defensible_global_idle() for c in cases)
    assert cases[0].app_worker_drained()
    assert cases[1].app_worker_drained()
    print("C545D_IDLE_MODEL_SELFTEST_PASS,unproven_quiet_scenarios=7,"
          "counter_zero_pending_APC_case_rejected=1,windows_runs=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--appinfo", type=Path)
    p.add_argument("--registry", type=Path)
    p.add_argument("--numeric", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    if not (args.appinfo and args.registry and args.numeric):
        p.error("--appinfo, --registry, and --numeric are all required")
    print("\n".join(
        audit_source(args.appinfo.read_text(encoding="utf-8"),
                     args.registry.read_text(encoding="utf-8"))
        + audit_archive(args.numeric.read_text(encoding="utf-8-sig"))
    ))


if __name__ == "__main__":
    main()
