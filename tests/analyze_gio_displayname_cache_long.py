#!/usr/bin/env python3
"""Compare exact-WinRT-DisplayName cache vs uncached across two 256-cycle controls.

Both treatment and control are separate processes on one Windows CI runner.
Never call a plateau a production memory-leak cure. No package names leak.
"""
import csv
import re
import sys
from pathlib import Path

from analyze_gio_residual_growth import read_series, summarize, assess


def parse_mode(root, mode):
    c = read_series(root / f"{mode}_nochange_256.log")
    e = read_series(root / f"{mode}_registry_256.log")
    c_slope = summarize(f"{mode}_nochange", c)
    e_slope = summarize(f"{mode}_registry", e)
    status = assess(c_slope, e_slope)
    for scope, data in (("nochange", c), ("registry", e)):
        h0, hs = data["GIO_PROBE"][0][1], data["GIO_PROBE"]["settled"][1]
        dh = hs - h0
        print(f"C545D_CACHE_LONG_HANDLE,{mode},{scope},baseline={h0},settled={hs},delta={dh}")
        if abs(dh) > 4:
            raise ValueError(f"{mode}/{scope}: post-cleanup total handle growth {dh}")
    net = {
        field: (e_slope[field]["last_half"] - c_slope[field]["last_half"])
        for field in ("private_usage", "heap_busy", "vm_private_commit")
    }
    if mode == "cache":
        for scope in ("nochange", "registry"):
            log = (root / f"{mode}_{scope}_256.log").read_text(encoding="utf-8")
            rows = re.findall(
                r"^C545D_DISPLAY_CACHE,hits=(\d+),misses=(\d+),entries=(\d+)$",
                log, re.MULTILINE
            )
            if not rows:
                raise ValueError(f"No cache stats for {scope}")
            hits, misses, entries = map(int, rows[-1])
            print(f"C545D_CACHE_LONG_USAGE,{scope},hits={hits},misses={misses},entries={entries}")
            if misses <= 0 or entries <= 0 or entries > 1024:
                raise ValueError("Missing initial entries or unbounded cache")
            if scope == "registry" and hits <= 0:
                raise ValueError("No actual reuse under 256 registry mutations")
    return net, status


def main():
    root = Path("artifacts")
    default, status_default = parse_mode(root, "default")
    cache, status_cache = parse_mode(root, "cache")
    rows = []
    for metric in ("private_usage", "heap_busy", "vm_private_commit"):
        old, new = default[metric], cache[metric]
        reduction = 100.0 * (old - new) / old if old > 0 else float("nan")
        rows.append((metric, old, new, reduction))
        print(f"C545D_CACHE_LONG_NET_LAST128,{metric},uncached={old},cache={new},reduction_pct={reduction:.2f}")
    with (root / "cache_long_comparison.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(("metric", "uncached_net_last128_bytes",
                    "cache_net_last128_bytes", "relative_reduction_percent"))
        w.writerows(rows)
    (root / "cache_long_status.txt").write_text(
        f"UNCACHED_STATUS={status_default}\nCACHED_STATUS={status_cache}\n"
        "REAL_TAPO_PC_UNTESTED; CACHE_NOT_RELEASE_SAFE; "
        "REGISTRY_UPDATE_LOCALE_INVALIDATION_UNVERIFIED\n", encoding="utf-8")
    # The test is an experiment, not a gate that forces memory to plateau.
    # A regression should be visible as a failure, but NEVER mask it by
    # silently widening the threshold.
    for metric in ("private_usage", "heap_busy"):
        if default[metric] > 0 and cache[metric] > default[metric]:
            raise ValueError(f"cache worsens control-subtracted {metric} growth")
    print("C545D_DISPLAY_CACHE_LONG_COMPARISON_PASS; "
          "PLATEAU_NOT_ASSUMED; NOT_PRODUCTION_SAFE")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, AssertionError, ZeroDivisionError) as exc:
        print(f"C545D_DISPLAY_CACHE_LONG_INVALID:{exc}", file=sys.stderr)
        sys.exit(2)
