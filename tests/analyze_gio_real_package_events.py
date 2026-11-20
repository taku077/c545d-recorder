#!/usr/bin/env python3
"""Strict numeric-only end-to-end TRUE MSIX events -> GIO cache test.

Runs in disposable Windows CI. No recorded media, package names, keys,
installed-package raw logs or user-specific paths are exported.
"""
import re
import sys
from pathlib import Path


def exactly_one(pattern, text, label):
    matches = re.findall(pattern, text, re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(f"{label}: expected 1 marker, found {len(matches)}")
    return matches[0]


def verify(text):
    event = exactly_one(
        r"^C545D_REAL_PACKAGECATALOG_EVENT_PASS,"
        r"install_delta=(\d+),update_delta=(\d+),uninstall_delta=(\d+),"
        r"total_delta=(\d+),install_complete=(\d+),update_complete=(\d+),"
        r"uninstall_complete=(\d+),no_synthetic_notifications=true,"
        r"only_ci_package_events_counted=true,gio_same_process=True,CI_only=true$",
        text, "real MSIX events")
    installed, updated, removed, total, ci, cu, cr = map(int, event)
    if min(installed, updated, removed, ci, cu, cr) < 1:
        raise ValueError("incomplete real install/update/remove event cycle")
    if total < installed + updated + removed:
        raise ValueError("invalid total real event count")

    stages = re.findall(
        r"^C545D_GIO_REAL_MSIX_STEP_OK,stage=(\d+),apps=(\d+)$",
        text, re.MULTILINE)
    if [int(s) for s, _ in stages] != [0, 1, 2, 3, 4]:
        raise ValueError(f"missing same-process GIO stage: {stages}")
    if any(int(n) <= 0 for _, n in stages):
        raise ValueError("GIO enumeration unexpectedly empty")

    # The patched GIO parser reports cumulative telemetry at EVERY
    # enumerate-and-release stage. Compare each stage, rather than treating
    # those five valid snapshots as duplicate final records.
    bridges = [tuple(map(int, v)) for v in re.findall(
        r"^C545D_WINRT_BRIDGE,scans=(\d+),injections=(\d+),"
        r"evictions=(\d+),errors=(\d+),ready=(\d+)$",
        text, re.MULTILINE)]
    caches = [tuple(map(int, v)) for v in re.findall(
        r"^C545D_DISPLAY_CACHE,hits=(\d+),misses=(\d+),entries=(\d+)$",
        text, re.MULTILINE)]
    if len(bridges) != 5 or len(caches) != 5:
        raise ValueError(f"expected five GIO stage snapshots, bridge={len(bridges)},cache={len(caches)}")
    scans = [b[0] for b in bridges]
    evictions = [b[2] for b in bridges]
    if scans != [1, 2, 3, 4, 5]:
        raise ValueError(f"GIO parser scan sequence invalid: {scans}")
    if any(b[1] or b[3] or b[4] != 1 for b in bridges):
        raise ValueError("synthetic injection, bridge failure or watcher not ready")
    if not (evictions[0] == 0 and
            evictions[1] > evictions[0] and
            evictions[2] > evictions[1] and
            evictions[3] > evictions[2] and
            evictions[4] >= evictions[3]):
        raise ValueError(f"real install/update/uninstall did not evict in sequence: {evictions}")
    misses = [c[1] for c in caches]
    entries = [c[2] for c in caches]
    if not (misses[0] >= 1 and
            misses[1] > misses[0] and
            misses[2] > misses[1] and
            misses[3] > misses[2] and
            misses[4] == misses[3]):
        raise ValueError(f"original Windows display names were not refetched at each mutation: {misses}")
    if not (entries[0] >= 1 and entries[1] == entries[0] + 1
            and entries[2] == entries[1] and
            entries[3] == entries[0] and entries[4] == entries[0]):
        raise ValueError(f"installed/updated/removed app not reflected in cache inventory: {entries}")
    app_counts = [int(n) for _, n in stages]
    if not (app_counts[1] == app_counts[0] + 1 and
            app_counts[2] == app_counts[1] and
            app_counts[3] == app_counts[0] and
            app_counts[4] == app_counts[0]):
        raise ValueError(f"GAppInfo app inventory missing a real package state transition: {app_counts}")
    evicted = evictions[4]
    misses_total = misses[4]
    entries_final = entries[4]
    scans_total = scans[4]

    if text.count("C545D_REAL_APPX_CLEANUP_EXECUTED=true,runner_only=true") != 1:
        raise ValueError("temporary package and cert cleanup absent")

    print(f"C545D_REAL_MSIX_GIO_E2E_PASS,package_events={total},"
          f"terminal_completions={ci+cu+cr},cache_evictions={evicted},"
          f"original_name_misses={misses_total},gio_scans={scans_total},"
          f"cache_entries={entries_final},bridge_errors=0,injections=0,"
          "ci_only=true,not_real_tapo_or_windows10=true")


def selftest():
    # Fixture follows actual Windows run #44688737357: intermediate stats
    # are emitted at every real AppInfo enumeration (not just on exit).
    lines = [
        "C545D_REAL_PACKAGECATALOG_EVENT_PASS,install_delta=9,update_delta=7,"
        "uninstall_delta=2,total_delta=18,install_complete=1,update_complete=1,"
        "uninstall_complete=1,no_synthetic_notifications=true,"
        "only_ci_package_events_counted=true,gio_same_process=True,CI_only=true",
    ]
    for stage, (hits, misses, entries) in enumerate(
        ((0,32,32),(0,65,33),(0,98,33),(0,130,32),(32,130,32))):
        lines += [
            f"C545D_WINRT_BRIDGE,scans={stage+1},injections=0,"
            f"evictions={min(stage,3)},errors=0,ready=1",
            f"C545D_DISPLAY_CACHE,hits={hits},misses={misses},entries={entries}",
            f"C545D_GIO_REAL_MSIX_STEP_OK,stage={stage},apps={39 + (stage in (1,2))}",
        ]
    lines.append("C545D_REAL_APPX_CLEANUP_EXECUTED=true,runner_only=true")
    valid="\n".join(lines)+"\n"
    verify(valid)
    corrupt = (
        ("evictions=2", "evictions=0"),
        ("update_complete=1", "update_complete=0"),
        ("injections=0", "injections=1"),
        ("stage=2", "stage=1"),
        ("misses=98", "misses=65"),
        ("apps=40", "apps=39"),
    )
    for old, new in corrupt:
        try:
            verify(valid.replace(old,new,1))
        except ValueError:
            continue
        raise AssertionError(f"corrupted real event evidence was accepted: {old}")
    print(f"C545D_REAL_MSIX_GIO_E2E_SELFTEST_PASS,corrupt_cases={len(corrupt)}")


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--selftest"]:
            selftest()
        else:
            verify(Path("artifacts/real_msix_gio_output.txt").read_text(encoding="utf-8"))
    except (OSError, ValueError, AssertionError) as exc:
        print(f"C545D_REAL_MSIX_GIO_E2E_INVALID:{exc}", file=sys.stderr)
        sys.exit(2)
