#!/usr/bin/env python3
"""Pinned GLib 2.82.4 Win32 AppInfo/watch/APC lifetime audit.

External source is fetched ONLY from GNOME's exact tag and matched to three
known Git blob IDs, so newer or unreviewed sources cannot silently change
the interpretation. No registry, camera, recorder or Windows host access.

Key distinction:
  stable watcher subscription != worker idle != full producer closure
  != independently traced owned allocations/ frees != memory leak.

This audit never modifies GLib, creates a unwatch API, force-closes an APC
handle, or declares installed Tapo recording safe.
"""
from __future__ import annotations
import argparse
import hashlib
import re
import urllib.request

ROOT = "https://raw.githubusercontent.com/GNOME/glib/2.82.4/gio/"
PIN = {
    "gwin32appinfo.c": "f2b9cf346a18e4a525885fbd49f8bf77dc973bb5",
    "gwin32registrykey.c": "bd83b38b5ec0de126e94fd3b8b2372c492f0fc5d",
    "gwin32registrykey.h": "e2b25da4648c3e842a1d10285a88590c581c15d9",
    "gwin32packageparser.c": "a73dbba642c842606e30e6cf6cf339264fd18e70",
}
MAX_SOURCE = 280_000


def section(src: str, beginning: str, ending: str, label: str) -> str:
    if src.count(beginning) != 1:
        raise ValueError(f"{label}_missing_or_ambiguous_start")
    start = src.index(beginning)
    end = src.find(ending, start + len(beginning))
    if end == -1:
        raise ValueError(f"{label}_missing_end")
    result = src[start:end]
    if not 40 < len(result) < 25_000:
        raise ValueError(f"{label}_out_of_bounds")
    return result


def verify_source(app: str, key: str, header: str, package: str) -> str:
    if any(not isinstance(x, str) or len(x) > MAX_SOURCE for x in (app, key, header, package)):
        raise ValueError("source_size_or_type_invalid")
    callback = section(app, "static void\nkeys_updated (", "static void\nwatch_keys (void)\n{", "appinfo_callback")
    watchers = section(app, "static void\nwatch_keys (void)\n{",
                       "/* This is the main function of the AppInfo thread */", "appinfo_watchers")
    worker = section(app, "static void\ngio_win32_appinfo_thread_func (",
                     "/* Initializes Windows AppInfo.", "appinfo_worker")
    init = section(app, "void\ngio_win32_appinfo_init (gboolean do_wait)",
                   "static void g_win32_app_info_iface_init", "appinfo_init")
    package_enum = section(
        package, "gboolean\ng_win32_package_parser_enum_packages (",
        "static gboolean\nparse_manifest_file (", "winrt_package_enum")
    apc = section(key, "static VOID NTAPI\nkey_changed (",
                  "/**\n * g_win32_registry_key_watch:", "registry_apc")
    watch = section(key, "gboolean\ng_win32_registry_key_watch (",
                    "/**\n * g_win32_registry_key_erase_change_indicator:", "registry_watch")
    dispose = section(key, "static void\ng_win32_registry_key_dispose (",
                      "/**\n * g_win32_registry_key_new:", "registry_dispose")
    watches = re.findall(r"g_win32_registry_key_watch\s*\(", watchers)
    if len(watches) != 8:
        raise ValueError("watched_key_count_changed")
    requirements = [
        (callback, "  watch_keys ();", "rearm_before_update"),
        (callback, "g_atomic_int_inc (&gio_win32_appinfo_update_counter)", "rebuild_demand"),
        (callback, "g_thread_pool_push (gio_win32_appinfo_threadpool", "queued_rebuild"),
        (worker, "g_mutex_lock (&gio_win32_appinfo_mutex);", "single_update_mutex"),
        (worker, "update_registry_data ();", "real_rebuild"),
        (worker, "g_atomic_int_compare_and_exchange", "coalesced_rebuild_counter"),
        (init, "g_thread_pool_new (gio_win32_appinfo_thread_func", "dedicated_pool"),
        (init, "                                                        1,", "one_worker_pool"),
        (init, "GetModuleHandleEx (GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,", "pinned_DLL"),
        (init, "g_cond_wait (&gio_win32_appinfo_cond", "update_cond_only"),
        (apc, "g_atomic_int_set (&key->priv->watch_indicator, G_WIN32_KEY_UNWATCHED);", "watch_reset_after_apc"),
        (apc, "callback (key, user_data);", "watch_callback_invoked"),
        (apc, "g_object_unref (key);", "apc_releases_ref"),
        (watch, "g_object_ref (key);", "apc_holds_ref"),
        (watch, "nt_notify_change_multiple_keys (", "asynchronous_nt_registration"),
        (watch, "if (!started_to_watch)\n    return TRUE;", "already_watching_does_not_add_ref"),
        (dispose, "RegCloseKey (priv->handle);", "key_dispose_close"),
    ]
    for area, evidence, label in requirements:
        if area.count(evidence) != 1:
            raise ValueError(f"{label}_missing_or_drifted")
    # Source-scoped WinRT parser iteration is synchronous; COM cleanup
    # precedes return. No implication of globally empty COM/WinRT caches.
    for term in ("CoInitializeEx (", "IIterable_First (",
                 "IIterator_get_HasCurrent (", "IIterator_get_Current (",
                 "parse_manifest_file (sax);", "IIterator_MoveNext (",
                 "CoUninitialize ();", "return result;"):
        if term not in package_enum:
            raise ValueError("winrt_owned_package_enumeration_changed")
    if not (package_enum.index("IIterable_First (") <
            package_enum.index("IIterator_MoveNext (") <
            package_enum.index("CoUninitialize ();") <
            package_enum.index("return result;")):
        raise ValueError("package_iterator_cleanup_order_changed")
    if "IAsyncOperation" in package_enum:
        raise ValueError("package_enumerator_now_async_reassess")
    if "g_win32_registry_key_unwatch" in header or "g_win32_registry_key_unwatch" in key:
        raise ValueError("new_unwatch_api_requires_source_reassessment")
    # The header has a public watch function and *no* public unwatch.
    if header.count("g_win32_registry_key_watch") < 2:
        raise ValueError("public_watch_interface_missing")
    if app.find("static void\nwatch_keys (void)\n{") < app.find("static void\nkeys_updated ("):
        raise ValueError("rearm_source_order_ambiguous")
    # The order inside callback is important: source can rearm before
    # signalling new worker demand. No barrier exists in this callback.
    if not (callback.index("watch_keys ();") <
            callback.index("g_atomic_int_inc") <
            callback.index("g_thread_pool_push")):
        raise ValueError("registry_rearm_order_changed")
    if not (apc.index("callback (key, user_data);") < apc.index("g_object_unref (key);")):
        raise ValueError("apc_ref_lifetime_changed")
    return (
        "C545D_GLIB_2824_PRODUCER_SOURCE_AUDIT_PASS,"
        "watched_roots=8,one_appinfo_worker_pool=1,source_rearm_before_queue=1,"
        "source_apc_ref_held_until_callback=1,source_public_unwatch_api=0,"
        "source_gio_DLL_PIN=1,source_cond_not_queue_drain=1,"
        "source_winrt_enum_iterator_and_COM_cleanup=1,"
        "no_global_COM_cache_quiet_inference=1,"
        "watch_zero_not_valid_default=1,worker_idle_not_global_quiet=1,"
        "actual_GIO_closed_epoch_proven=0,actual_heap_owner_proven=0,"
        "production_release_HOLD=1,host_untouched=1"
    )


def require_closed_epoch(*, registration_closed: bool, rearm_disabled: bool,
                         pending_watches: int, queued_rebuild_jobs: int,
                         active_workers: int, in_flight_apcs: int,
                         winrt_callbacks: int, full_start_coverage: bool,
                         lost_events: int, size_owner_matched: bool) -> str:
    """Proof contract only: never asserts that live GLib meets these inputs.

    The existing GLib 2.82.4 implementation has no verified source-backed
    registration_closed/rearm_disabled ack. Those flags MUST NOT be made up.
    """
    counters = (pending_watches, queued_rebuild_jobs, active_workers,
                in_flight_apcs, winrt_callbacks, lost_events)
    if any(type(x) is not int or not 0 <= x <= 100000 for x in counters):
        raise ValueError("unverified_or_unsafe_counter")
    flags = (registration_closed, rearm_disabled,
             full_start_coverage, size_owner_matched)
    if any(type(x) is not bool for x in flags):
        raise ValueError("incomplete_or_untrusted_source_flags")
    if not registration_closed or not rearm_disabled:
        raise ValueError("producer_may_still_rearm_or_register")
    if pending_watches > 0 or in_flight_apcs > 0:
        raise ValueError("registry_apc_lifetime_unclosed")
    if queued_rebuild_jobs > 0 or active_workers > 0:
        raise ValueError("appinfo_work_queue_unclosed")
    if winrt_callbacks > 0:
        raise ValueError("winrt_callbacks_unclosed")
    if not full_start_coverage or lost_events != 0:
        raise ValueError("heap_event_origin_scope_unverified")
    if not size_owner_matched:
        raise ValueError("heap_allocation_owner_unverified")
    return (
        "C545D_SOURCE_EPOCH_CONTRACT_PASS,source_closed=1,"
        "watchers=0,queued_jobs=0,active_workers=0,apc_inflight=0,"
        "winrt_inflight=0,alloc_owner_matched=1,"
        "synthetic_contract_only=1,actual_GIO_closed_epoch_proven=0,"
        "release_HOLD=1"
    )


def selftest() -> None:
    # A positive synthetic contract does NOT prove the pinned source has
    # these observables. GLib runtime must first implement source-specific
    # registration-close acknowledgment or isolate the worker lifecycle.
    ok = dict(registration_closed=True,rearm_disabled=True,
              pending_watches=0,queued_rebuild_jobs=0,active_workers=0,
              in_flight_apcs=0,winrt_callbacks=0,
              full_start_coverage=True,lost_events=0,size_owner_matched=True)
    assert "synthetic_contract_only=1" in require_closed_epoch(**ok)
    cases = [
        dict(registration_closed=False),
        dict(rearm_disabled=False),
        dict(pending_watches=8),
        dict(queued_rebuild_jobs=1),
        dict(active_workers=1),
        dict(in_flight_apcs=1),
        dict(winrt_callbacks=1),
        dict(full_start_coverage=False),
        dict(lost_events=1),
        dict(size_owner_matched=False),
        dict(active_workers=-1),
        dict(pending_watches=True),
        dict(registration_closed=1),
    ]
    for i, mutation in enumerate(cases):
        try:
            require_closed_epoch(**(ok | mutation))
        except ValueError:
            continue
        raise AssertionError(f"false_global_source_epoch_accepted:{i}")
    print("C545D_GLIB_SOURCE_EPOCH_CONTRACT_SELFTEST_PASS,positive=1,"
          "negative=13,quiet_not_closed=1,"
          "watch_pending_not_leak=1,real_GIO_lifetime_unproven=1")


def get_pinned(name: str) -> str:
    if name not in PIN:
        raise ValueError("unexpected_source_name")
    req = urllib.request.Request(ROOT+name, headers={"User-Agent":"C545D-GIO-pinned-source-ci"})
    with urllib.request.urlopen(req, timeout=20) as response:
        body = response.read(MAX_SOURCE+1)
    if not 0 < len(body) < MAX_SOURCE:
        raise ValueError("source_download_missing_or_oversized")
    git_blob = b"blob " + str(len(body)).encode("ascii") + b"\0" + body
    if hashlib.sha1(git_blob).hexdigest() != PIN[name]:
        raise ValueError("pinned_glib_git_blob_mismatch")
    return body.decode("utf-8")


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--verify-pinned",action="store_true")
    args=p.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.verify_pinned:
        p.error("must explicitly choose --selftest or --verify-pinned")
    app,key,header,package=(get_pinned(name) for name in PIN)
    print(verify_source(app,key,header,package))


if __name__ == "__main__":
    main()
