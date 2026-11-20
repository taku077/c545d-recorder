#!/usr/bin/env python3
"""Isolated 16-cycle GIO exact-DisplayName cache with/without WinRT C ABI.
Requires matched no-registry control for each mode, original name parity,
real connected event polling (synthetic notifications only) and fail-closed.
No package identities or video are emitted.
"""
import re
import sys
from pathlib import Path
from analyze_gio_uwp_api_isolation import parse

root = Path("artifacts")
MODES = ("cache_plain", "bridge_plain", "bridge_injected", "bridge_missing")


def get_stats(path):
    data = path.read_text(encoding="utf-8")
    results = parse(path)
    matches = re.findall(
        r"^C545D_DISPLAY_CACHE,hits=(\d+),misses=(\d+),entries=(\d+)$",
        data, re.MULTILINE)
    if not matches:
        raise ValueError(f"{path}: missing cache telemetry")
    hits, misses, entries = map(int, matches[-1])
    bridge = re.findall(
        r"^C545D_WINRT_BRIDGE,scans=(\d+),injections=(\d+),"
        r"evictions=(\d+),errors=(\d+),ready=(\d+)$", data, re.MULTILINE)
    bridge_stats = tuple(map(int, bridge[-1])) if bridge else None
    return results, (hits, misses, entries), bridge_stats


def assert_original_value_cache(control, changed, mode, refills=1):
    # Windows CI users do not always have 32 packages installed (31 in run
    # #44693332873). GLib's background AppInfo initialization can also queue
    # one extra baseline rescan. Enforce exact per-package misses and strong
    # bounded hit invariants instead of hardcoding a package inventory size.
    n = changed[2]
    if n <= 0 or control[2] != n:
        raise ValueError(f"{mode}: invalid cache entry population: {control},{changed}")
    if control[1] != n or changed[1] != refills * n:
        raise ValueError(f"{mode}: original-name refetch count wrong: {control},{changed}")
    if control[0] < 0 or control[0] > 2 * n or control[0] % n != 0:
        raise ValueError(f"{mode}: baseline async cache hit bounds violated: {control}")
    if changed[0] < 12 * n or changed[0] % n != 0:
        raise ValueError(f"{mode}: repeated AppInfo cache scan hit bounds violated: {changed}")
    return n


def main():
    for mode in MODES:
        control, c0, b0 = get_stats(root / f"{mode}_nochange_16.log")
        changed, c1, b1 = get_stats(root / f"{mode}_registry_16.log")
        delta = {k: changed[k] - control[k] for k in control}
        if delta["total_handles"] > 4:
            raise ValueError(f"{mode}: positive post-cleanup handle growth")
        if mode == "cache_plain":
            if b0 is not None or b1 is not None:
                raise ValueError("ordinary cache illegally used C bridge")
            assert_original_value_cache(c0, c1, mode)
        elif mode == "bridge_plain":
            if b0 != (1, 0, 0, 0, 1) or b1 != (18, 0, 0, 0, 1):
                raise ValueError(f"real C ABI bridge not healthy: {b0}, {b1}")
            assert_original_value_cache(c0, c1, mode)
        elif mode == "bridge_injected":
            if b0 != (1, 0, 0, 0, 1) or b1 != (18, 1, 1, 0, 1):
                raise ValueError(f"synthetic package event did not evict: {b1}")
            assert_original_value_cache(c0, c1, mode, refills=2)
        else:
            if b0 is None or b1 is None or b0[-1] or b1[-1] or b1[3] == 0:
                raise ValueError(f"missing DLL did not fail closed: {b0},{b1}")
            if c0 != (0, 0, 0) or c1 != (0, 0, 0):
                raise ValueError("missing C ABI DLL returned stale cached values")
        print("C545D_GLIB_BRIDGE_STAGE," + mode + "," +
              ",".join(f"{k}={v:+d}" for k, v in delta.items()) +
              f",cache_hits={c1[0]},cache_misses={c1[1]},"
              f"cached_entries={c1[2]},bridge={b1}")
    print("C545D_GLIB_WINRT_C_ABI_CONNECTED_PASS; "
          "SYNTHETIC_EVENT_ONLY; SINGLE_OWNER_THREAD; NOT_FOR_PRODUCTION")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        print(f"C545D_GLIB_WINRT_BRIDGE_INVALID:{exc}", file=sys.stderr)
        sys.exit(2)
