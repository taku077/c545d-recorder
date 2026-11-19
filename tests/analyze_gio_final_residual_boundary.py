#!/usr/bin/env python3
"""Find the last nonzero GLib AppInfo private/heap memory growth.

Compares exact-value cache with DIAGNOSTIC-ONLY no-DisplayName-getter and
no-UWP-enumeration modes, using same-run registry/nochange controls, 256 cycles
per arm. No synthetic mode is a proposal to remove production functionality.
No raw installed app names, camera data or user paths in artifacts.
"""
import csv
import re
import sys
from pathlib import Path
from analyze_gio_residual_growth import read_series, summarize, CHECKPOINTS

ARTIFACTS = Path("artifacts")
STAGES = ("cached_original", "no_displayname_getter", "skip_uwp_current")
METRICS = {
    "private_usage": ("GIO_PROBE", 2),
    "heap_busy": ("GIO_HEAP", 1),
    "vm_private_commit": ("GIO_VM", 0),
    "busy_blocks": ("GIO_HEAP", 0),
}

def extract(stage, scope):
    path = ARTIFACTS / f"{stage}_{scope}_256.log"
    series = read_series(path)
    summary = summarize(f"{stage}_{scope}", series)
    return path, series, summary

def axis(series, tag, index):
    return {point: record[index] for point, record in series[tag].items()}

def main():
    rows = []
    net_by_stage = {}
    for stage in STAGES:
        control_path, ctrl, ctrl_s = extract(stage, "nochange")
        reg_path, reg, reg_s = extract(stage, "registry")
        last128 = {}
        for metric, (tag, index) in METRICS.items():
            a, b = axis(ctrl, tag, index), axis(reg, tag, index)
            window_growth = [
                (b[right] - b[left]) - (a[right] - a[left])
                for left, right in zip(CHECKPOINTS, CHECKPOINTS[1:])
            ]
            first128 = sum(window_growth[:2])
            second128 = sum(window_growth[2:])
            last128[metric] = second128
            print(f"C545D_FINAL_RESIDUAL,{stage},{metric},"
                  f"windows64={';'.join(map(str, window_growth))},"
                  f"first128={first128},last128={second128},"
                  f"last128_minus_first128={second128-first128}")
            rows.append((stage,metric,*window_growth,first128,second128))
        # A negative handle delta means normal release, NOT a resource leak.
        c_handle = axis(ctrl, "GIO_PROBE", 1)
        r_handle = axis(reg, "GIO_PROBE", 1)
        for scope, data in (("nochange",c_handle),("registry",r_handle)):
            diff = data["settled"] - data[0]
            if diff > 4:
                raise ValueError(f"{stage}/{scope}: positive retained handles +{diff}")
            print(f"C545D_FINAL_RESIDUAL_HANDLE,{stage},{scope},settled_delta={diff}")
        if stage == "cached_original":
            text = reg_path.read_text(encoding="utf-8")
            cache_stats = re.findall(
                r"^C545D_DISPLAY_CACHE,hits=(\d+),misses=(\d+),entries=(\d+)$",
                text, re.M)
            if not cache_stats:
                raise ValueError("cached mode missing owned-string telemetry")
            hits, misses, entries = map(int,cache_stats[-1])
            if not (hits > 0 and misses == entries and 0 < entries <= 1024):
                raise ValueError("unexpected repeated cache miss or unbounded entries")
            print(f"C545D_FINAL_RESIDUAL_CACHE,hits={hits},"
                  f"misses={misses},entries={entries}")
        net_by_stage[stage] = last128
    print("C545D_FINAL_RESIDUAL_CAUSAL_BOUNDARY,"
          "cached_private_last128={cached},no_getter_private_last128={no_getter},"
          "skip_uwp_private_last128={no_uwp},"
          "cached_busy_last128={cached_heap},"
          "no_getter_busy_last128={no_getter_heap},"
          "skip_uwp_busy_last128={no_uwp_heap}".format(
              cached=net_by_stage["cached_original"]["private_usage"],
              no_getter=net_by_stage["no_displayname_getter"]["private_usage"],
              no_uwp=net_by_stage["skip_uwp_current"]["private_usage"],
              cached_heap=net_by_stage["cached_original"]["heap_busy"],
              no_getter_heap=net_by_stage["no_displayname_getter"]["heap_busy"],
              no_uwp_heap=net_by_stage["skip_uwp_current"]["heap_busy"]))
    with (ARTIFACTS / "final_residual_boundary.csv").open(
        "w", encoding="utf-8", newline="") as file:
        writer=csv.writer(file)
        writer.writerow(("diagnostic_stage", "metric", "net_0_64",
                         "net_64_128", "net_128_192", "net_192_256",
                         "net_first128", "net_last128"))
        writer.writerows(rows)
    print("C545D_FINAL_RESIDUAL_BOUNDARY_PASS;"
          " MEMORY_GROWTH_IS_NOT_AUTOMATICALLY_A_LEAK;"
          " DIAGNOSTIC_FUNCTIONALITY_ABLATIONS_ONLY;"
          " WINDOWS_2022_NOT_TAPO_HOST")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, AssertionError) as exc:
        print(f"C545D_FINAL_RESIDUAL_INVALID:{exc}",file=sys.stderr)
        sys.exit(2)
