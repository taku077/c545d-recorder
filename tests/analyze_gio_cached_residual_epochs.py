#!/usr/bin/env python3
"""Reanalyse three SAVED 256-cycle Windows GIO cache A/B artifacts.

No Windows re-execution, registry access, camera data, package names or paths.
The 2048-byte HeapWalk overflow bin is NOT an exact size; exclude it from
size-owner conclusions. Differences are paired registry minus nochange.
"""
from __future__ import annotations
import argparse
import csv
import pathlib
from collections import defaultdict

RUNS = (44533452892, 44537371920, 44545844200)
CYCLES = (0, 64, 128, 192, 256)
TYPES = ("GWin32AppInfo", "GWin32AppInfoApplication", "GWin32AppInfoFileExtension",
         "GWin32AppInfoHandler", "GWin32AppInfoShellVerb", "GWin32AppInfoURLSchema",
         "GWin32RegistryKey")
SIZES = (24, 28, 360, 736, 912, 1936)
METRICS = ("private_usage", "heap_busy") + tuple("type:" + t for t in TYPES) + tuple("size:" + str(n) for n in SIZES)


def parse_log(contents: str) -> dict[str, dict[int, int]]:
    if contents.count("GIO_PROBE_DONE,cycles=256") != 1:
        raise ValueError("missing or duplicate successful 256-cycle termination")
    values: dict[str, dict[int, int]] = defaultdict(dict)
    for line in contents.splitlines():
        a = line.split(",")
        if a[0] not in {"GIO_VM", "GIO_HEAP", "GIO_TYPE", "GIO_HEAPSIZE"}:
            continue
        if len(a) < 5 or a[1] not in {"baseline", "cycle"}:
            continue
        cycle = int(a[2])
        if cycle not in CYCLES:
            continue
        if a[0] == "GIO_VM":
            if len(a) != 8 or int(a[-1]) != 0:
                raise ValueError("VM census missing fields or reports errors")
            metric, value = "private_usage", int(a[3])
        elif a[0] == "GIO_HEAP":
            if len(a) != 7 or int(a[-1]) != 0:
                raise ValueError("HeapWalk census missing fields or reports errors")
            metric, value = "heap_busy", int(a[4])
        elif a[0] == "GIO_TYPE":
            if len(a) != 5 or a[3] not in TYPES:
                raise ValueError("unrecognized GObject type evidence")
            metric, value = "type:" + a[3], int(a[4])
        else:
            if len(a) != 5:
                raise ValueError("bad HeapWalk size census")
            size = int(a[3])
            if not 1 <= size <= 2048:
                raise ValueError("out-of-bounds size bucket")
            if size not in SIZES:
                continue
            metric, value = "size:" + str(size), int(a[4])
        if cycle in values[metric]:
            raise ValueError(f"duplicate {metric} at cycle {cycle}")
        values[metric][cycle] = value
    for metric in METRICS:
        if metric.startswith("size:"):
            # Zero is a legitimate absent bin at any fixed checkpoint.
            for cycle in CYCLES:
                values[metric].setdefault(cycle, 0)
        if set(values[metric]) != set(CYCLES):
            raise ValueError(f"incomplete metric/cycles: {metric}, {sorted(values[metric])}")
        if any(val < 0 for val in values[metric].values()):
            raise ValueError(f"negative census: {metric}")
    return values


def delta_by_64(registry: dict[str, dict[int, int]],
                nochange: dict[str, dict[int, int]], metric: str) -> tuple[int, ...]:
    net = [registry[metric][c] - nochange[metric][c] for c in CYCLES]
    return tuple(net[i + 1] - net[i] for i in range(4))


def analyze(root: pathlib.Path) -> tuple[list[dict[str, str | int]], list[str]]:
    rows: list[dict[str, str | int]] = []
    summaries: list[str] = []
    cache_privates: list[tuple[int, ...]] = []
    for run in RUNS:
        data = {}
        for mode in ("default", "cache"):
            for scope in ("registry", "nochange"):
                f = root / str(run) / f"{mode}_{scope}_256.log"
                data[(mode, scope)] = parse_log(f.read_text(encoding="utf-8-sig"))
        for mode in ("default", "cache"):
            for metric in METRICS:
                vals = delta_by_64(data[(mode, "registry")], data[(mode, "nochange")], metric)
                row = {"run_id": run, "mode": mode, "metric": metric,
                       **{f"net_{CYCLES[i]}_{CYCLES[i+1]}": vals[i] for i in range(4)}}
                rows.append(row)
                if mode == "cache" and metric == "private_usage":
                    cache_privates.append(vals)
                    summaries.append(f"C545D_SAVED_CACHE_PRIVATE,run={run},per64=" + ";".join(map(str, vals)))
        # All seven GObject type counters: no registry-subtracted growth from
        # cycle 128 to cycle 256, not proof that every non-GObject is released.
        for typ in TYPES:
            vals = delta_by_64(data[("cache", "registry")], data[("cache", "nochange")], "type:" + typ)
            if sum(vals[2:]) != 0:
                raise ValueError(f"GObject type counter residual was not zero: {typ}")
        for size in (24, 28):
            vals = delta_by_64(data[("cache", "registry")], data[("cache", "nochange")], "size:" + str(size))
            if vals[3] >= vals[2]:
                raise ValueError(f"size {size} accelerated rather than settling")
            summaries.append(f"C545D_SAVED_HEAP_BIN,run={run},size={size},per64=" + ";".join(map(str, vals)))
    if len(cache_privates) != 3 or not all(v[3] < v[2] for v in cache_privates):
        raise ValueError("late-64 PrivateUsage deceleration was not consistent")
    summaries.append("C545D_SAVED_RESIDUAL_3RUN_PASS,"
                     "late64_private_bytes=" + ";".join(str(v[3]) for v in cache_privates) +
                     ",late64_deceleration=3of3,"
                     "seven_GObject_type_counters_no_last128_net_growth=3of3,"
                     "plateau_unproven=true,allocation_stack_unattributed=true,"
                     "windows_CI_NOT_rerun=true,host_unverified=true")
    return rows, summaries


def selftest() -> None:
    # Numeric parser negative controls; do NOT print real package identities.
    samples = ["GIO_PROBE_DONE,cycles=256"]
    for i in CYCLES:
        phase = "baseline" if i == 0 else "cycle"
        samples.extend([f"GIO_VM,{phase},{i},10000,10,20,30,0",
                        f"GIO_HEAP,{phase},{i},12,1000,1,0"])
        samples.extend(f"GIO_TYPE,{phase},{i},{typ},2" for typ in TYPES)
    good = "\n".join(samples)
    parsed = parse_log(good)
    assert parsed["size:24"][128] == 0
    bad = [good.replace("GIO_PROBE_DONE,cycles=256", "GIO_PROBE_DONE,cycles=255"),
           good.replace("GIO_VM,cycle,64,", "GIO_VM,cycle,32,"),
           good.replace("GIO_HEAP,cycle,128,12,1000,1,0", "GIO_HEAP,cycle,128,12,1000,1,1"),
           good.replace("GIO_TYPE,cycle,192,GWin32AppInfo,2", "GIO_TYPE,cycle,192,GUnexpected,2"),
           good + "\nGIO_VM,cycle,256,10000,10,20,30,0"]
    for i, broken in enumerate(bad):
        try:
            parse_log(broken)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted malformed numeric evidence case {i}")
    print("C545D_SAVED_RESIDUAL_SELFTEST_PASS,valid=1,rejected=5")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=pathlib.Path)
    p.add_argument("--output", type=pathlib.Path)
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    if not a.root or not a.output:
        p.error("--root and --output are required")
    rows, messages = analyze(a.root)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for msg in messages:
        print(msg)


if __name__ == "__main__":
    main()
