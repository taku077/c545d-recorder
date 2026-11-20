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

    bridge = exactly_one(
        r"^C545D_WINRT_BRIDGE,scans=(\d+),injections=(\d+),"
        r"evictions=(\d+),errors=(\d+),ready=(\d+)$",
        text, "real GIO bridge telemetry")
    scans, injected, evicted, errors, ready = map(int, bridge)
    if scans < 4 or injected or evicted < 3 or errors or ready != 1:
        raise ValueError(f"GIO bridge missed a real package invalidation: {bridge}")

    cache = exactly_one(
        r"^C545D_DISPLAY_CACHE,hits=(\d+),misses=(\d+),entries=(\d+)$",
        text, "original-value GIO cache telemetry")
    hits, misses, entries = map(int, cache)
    if misses < 96 or not (1 <= entries <= 200):
        raise ValueError(f"GIO did not refill the cached original names: {cache}")

    if text.count("C545D_REAL_APPX_CLEANUP_EXECUTED=true,runner_only=true") != 1:
        raise ValueError("temporary package and cert cleanup absent")

    print(f"C545D_REAL_MSIX_GIO_E2E_PASS,package_events={total},"
          f"terminal_completions={ci+cu+cr},cache_evictions={evicted},"
          f"original_name_misses={misses},gio_scans={scans},"
          f"cache_entries={entries},bridge_errors=0,injections=0,"
          "ci_only=true,not_real_tapo_or_windows10=true")


def selftest():
    valid = ("\n".join([
        "C545D_REAL_PACKAGECATALOG_EVENT_PASS,install_delta=9,update_delta=7,"
        "uninstall_delta=2,total_delta=18,install_complete=1,update_complete=1,"
        "uninstall_complete=1,no_synthetic_notifications=true,"
        "only_ci_package_events_counted=true,gio_same_process=True,CI_only=true",
        *(f"C545D_GIO_REAL_MSIX_STEP_OK,stage={i},apps={32+i}" for i in range(5)),
        "C545D_WINRT_BRIDGE,scans=5,injections=0,evictions=3,errors=0,ready=1",
        "C545D_DISPLAY_CACHE,hits=80,misses=127,entries=32",
        "C545D_REAL_APPX_CLEANUP_EXECUTED=true,runner_only=true",
    ]) + "\n")
    verify(valid)
    for old, new in (
        ("evictions=3", "evictions=2"),
        ("update_complete=1", "update_complete=0"),
        ("injections=0", "injections=1"),
        ("stage=2", "stage=1"),
        ("misses=127", "misses=32"),
    ):
        try:
            verify(valid.replace(old, new))
        except ValueError:
            continue
        raise AssertionError(f"invalid E2E evidence accepted: {old}")
    print("C545D_REAL_MSIX_GIO_E2E_SELFTEST_PASS,corrupt_cases=5")


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--selftest"]:
            selftest()
        else:
            verify(Path("artifacts/real_msix_gio_output.txt").read_text(encoding="utf-8"))
    except (OSError, ValueError, AssertionError) as exc:
        print(f"C545D_REAL_MSIX_GIO_E2E_INVALID:{exc}", file=sys.stderr)
        sys.exit(2)
