#!/usr/bin/env python3
"""Offline audit of previously UNUSED GIO_HEAP busy-block/heap-count fields.

Uses ONLY original 4-arm 256-cycle Windows 2022 archive #44918598339.
Probe prints GIO_HEAP,label,cycle,busy_blocks,busy_cbData,heap_count,errors.
Heap count is GetProcessHeaps() size, not an allocation/commit census.
Busy blocks are HeapWalk BUSY entries, NOT GObject instances.
Matched control differences compare DIFFERENT processes.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
import analyze_gio_combo_msvc256_saved as source

P = re.compile(r"GIO_HEAP,(baseline|cycle|after_cleanup|settled_cleanup),"
               r"(\d+),(\d+),(\d+),(\d+),(\d+)$")
MEASURES = ("busy_blocks", "busy_cbData", "heap_count")
WINDOWS = (
    (("baseline", 0), ("cycle", 64)),
    (("cycle", 64), ("cycle", 128)),
    (("cycle", 128), ("cycle", 192)),
    (("cycle", 192), ("cycle", 256)),
    (("cycle", 256), ("after_cleanup", 257)),
    (("after_cleanup", 257), ("settled_cleanup", 258)),
)


def parse(rows: list[str]) -> dict[tuple[str, int], tuple[int, int, int]]:
    found = {}
    for row in rows:
        if not row.startswith("GIO_HEAP,"):
            continue
        m = P.fullmatch(row)
        if m is None:
            raise ValueError("malformed original GIO_HEAP numeric row")
        label, cycle_str, busy_blocks, busy_data, heaps, errors = m.groups()
        key = label, int(cycle_str)
        numbers = (int(busy_blocks), int(busy_data), int(heaps))
        if (key not in source.CHECKS or key in found or any(v < 0 for v in numbers)
                or int(errors) != 0 or numbers[2] <= 0):
            raise ValueError("invalid/duplicate counted heaps or heap blocks")
        found[key] = numbers
    if set(found) != set(source.CHECKS):
        raise ValueError("missing/extra original heap checkpoints")
    return found


def audit(group: dict[str, list[str]]) -> list[str]:
    validated = source.analyze(group, print_output=False)
    if validated[-1] != (
        "C545D_SAVED256_NUMERIC_ANALYSIS_PASS,source_windows_run=44918598339,"
        "cycles=256,controls=4,compare16=2,raw_host_data=0,"
        "sdk_public_api_not_rechecked_from_archive=1,"
        "zero_leak_proven=0,host_install_approved=0"
    ):
        raise ValueError("different source/experiment archive")
    snapshots = {
        (mode, arm): parse(group[f"{mode}-{arm}-256"])
        for mode in source.MODES for arm in source.ARMS
    }
    result = []
    for mode in source.MODES:
        parsed = {arm: source.parse(group, mode, arm) for arm in source.ARMS}
        for arm in source.ARMS:
            observed = snapshots[mode, arm]
            result.append(
                "C545D_SAVED256_HEAP_ENUM_ENDPOINT,"
                f"mode={mode},arm={arm},"
                f"baseline_heaps={observed['baseline', 0][2]},"
                f"cycle256_heaps={observed['cycle', 256][2]},"
                f"final258_heaps={observed['settled_cleanup', 258][2]},"
                "heap_identity_known=0,individual_heap_commit_known=0"
            )
        for left, right in WINDOWS:
            reg, no = snapshots[mode, "registry"], snapshots[mode, "nochange"]
            d = {}
            for index, metric in enumerate(MEASURES):
                regdiff = reg[right][index] - reg[left][index]
                nodiff = no[right][index] - no[left][index]
                d[metric] = (regdiff, nodiff, regdiff - nodiff)
            if (d["busy_cbData"][2] !=
                    source.difference(parsed, "heap", left, right)):
                raise ValueError("GIO_HEAP busy total versus old parser changed")
            result.append(
                "C545D_SAVED256_HEAP_ENUM_WINDOW,"
                f"mode={mode},window={left[1]}_{right[1]},"
                + ",".join(
                    f"{metric}_registry={d[metric][0]},"
                    f"{metric}_nochange={d[metric][1]},"
                    f"{metric}_controlled={d[metric][2]}"
                    for metric in MEASURES
                )
                + ",processes_separate=1,"
                "heap_count_is_not_alloc_count=1,"
                "commit_ownership_unproven=1"
            )
    result.append(
        "C545D_SAVED256_HEAP_ENUM_PASS,"
        "source_run=44918598339,source_arms=4,checkpoints_per_arm=7,"
        "controlled_intervals=12,original_windows_rerun=0,"
        "real_host_untouched=1,leak_owner_identified=0"
    )
    return result


def selftest() -> None:
    points = source.CHECKS
    base = "\n".join(
        f"GIO_HEAP,{name},{cycle},100,20000,2,0"
        for name, cycle in points
    )
    good = parse(base.splitlines())
    assert len(good) == 7 and good["baseline", 0] == (100, 20000, 2)
    broken = (
        "\n".join(base.splitlines()[:-1]),
        base + "\n" + base.splitlines()[0],
        base.replace(",2,0", ",0,0", 1),
        base.replace(",2,0", ",2,1", 1),
        base.replace("cycle,64", "cycle,99", 1),
        base.replace("GIO_HEAP,cycle,64", "GIO_HEAP,cycle,ABC", 1),
    )
    for v in broken:
        try:
            parse(v.splitlines())
        except ValueError:
            pass
        else:
            raise AssertionError("bad original heap census accepted")
    print("C545D_SAVED256_HEAP_ENUM_SELFTEST_PASS,negative_cases=6,"
          "windows_runs=0,real_host_untouched=1")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--root", type=Path)
    args = ap.parse_args()
    if args.selftest:
        selftest()
    else:
        if args.root is None:
            ap.error("--root required")
        print("\n".join(audit(source.load(args.root))))


if __name__ == "__main__":
    main()
