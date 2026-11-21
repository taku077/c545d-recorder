#!/usr/bin/env python3
"""Reanalyze exact saved Windows2022 64-cycle GIO HeapWalk size bins.

No new Windows workload. A size-bin count does not identify allocation stacks,
root cause, lifetime retention or a 24x365 leak slope.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path
from analyze_gio_core_heap64 import CHECKS, parse as core_parse

SIZES = (24, 28, 56, 120, 190, 194, 196, 360)
MODES = ("official", "candidate")
ARMS = ("nochange", "registry")
INTERVALS = (0, 16, 32, 48, 64)
KEYS = [("baseline", 0), *[("cycle", x) for x in INTERVALS[1:]], ("after_cleanup", 65), ("settled_cleanup", 66)]


def read(text: str, changed: bool) -> dict:
    base = core_parse(text, changed)
    heap_blocks: dict[tuple, int] = {}
    bins: dict[tuple, dict[int, int]] = {}
    for line in text.splitlines():
        fields = line.split(",")
        if fields[0] == "GIO_HEAP":
            if len(fields) != 7:
                raise ValueError("heap record malformed")
            step = (fields[1], int(fields[2]))
            if step in heap_blocks:
                raise ValueError("duplicate heap checkpoint")
            heap_blocks[step] = int(fields[3])
        elif fields[0] == "GIO_HEAPSIZE":
            if len(fields) != 5:
                raise ValueError("heap size record malformed")
            step = (fields[1], int(fields[2]))
            size = int(fields[3])
            count = int(fields[4])
            if size < 0 or size > 2048 or count <= 0:
                raise ValueError("invalid heap size or count")
            bucket = bins.setdefault(step, {})
            if size in bucket:
                raise ValueError("duplicate heap size")
            bucket[size] = count
    if set(heap_blocks) != set(CHECKS) or set(bins) != set(CHECKS):
        raise ValueError("missing/extra heap checkpoints")
    for k in CHECKS:
        if sum(bins[k].values()) != heap_blocks[k]:
            raise ValueError("heap block total/histogram mismatch")
    return {size: {k: bins[k].get(size, 0) for k in CHECKS} for size in SIZES}


def analyze(root: Path) -> list[str]:
    samples = {}
    for mode in MODES:
        for arm in ARMS:
            path = root / f"{mode}-{arm}-64.txt"
            samples[mode, arm] = read(path.read_text(encoding="utf-8-sig"), arm == "registry")
    result: list[str] = []
    for mode in MODES:
        ctrl, treatment = samples[mode, "nochange"], samples[mode, "registry"]
        for size in SIZES:
            b = ctrl[size]
            a = treatment[size]
            base = ("baseline", 0)
            net = {key: (a[key] - a[base]) - (b[key] - b[base]) for key in KEYS}
            epochs = [net[("cycle", 16)]]
            epochs.extend(net[("cycle", x)] - net[("cycle", x-16)] for x in (32, 48, 64))
            line = (
                f"C545D_SAVED_BIN64,mode={mode},size={size},"
                f"net16={net[('cycle', 16)]},net32={net[('cycle', 32)]},"
                f"net48={net[('cycle', 48)]},net64={net[('cycle', 64)]},"
                f"epoch16_1={epochs[0]},epoch16_2={epochs[1]},"
                f"epoch16_3={epochs[2]},epoch16_4={epochs[3]},"
                f"cleanup={net[('after_cleanup', 65)]},"
                f"settled={net[('settled_cleanup', 66)]},"
                "source_attributed=0,host_validated=0"
            )
            result.append(line)
    result.append(
        "C545D_SAVED_GIO_BIN_EPOCHS_PASS,"
        "archived_windows_run_id=44907202861,modes=2,arms=2,"
        "windows_reruns=0,camera=0,zero_leak_proven=0,"
        "stack_attributed=0,install_approved=0"
    )
    return result


def selftest():
    def fixture(reg: int = 1):
        lines = [f"GIO_PROBE_DONE,cycles=64,notifications=0,reg_changes={reg}"]
        for phase, cycle in CHECKS:
            lines.extend((f"GIO_HEAP,{phase},{cycle},2,176,1,0",
                          f"GIO_HEAPSIZE,{phase},{cycle},56,1",
                          f"GIO_HEAPSIZE,{phase},{cycle},120,1",
                          f"GIO_PROBE,{phase},{cycle},0,100,12345"))
            if phase in ("baseline", "settled_cleanup"):
                lines.append(f"GIO_KEY,{phase},{cycle},10")
        return "\n".join(lines)
    good = fixture()
    if read(good, True)[56][("cycle", 64)] != 1:
        raise AssertionError("valid histogram rejected")
    wrong = (
        good.replace("cycles=64,", "cycles=63,"),
        good.replace("GIO_HEAPSIZE,cycle,16,56,1", ""),
        good.replace("GIO_HEAPSIZE,cycle,16,56,1",
                     "GIO_HEAPSIZE,cycle,16,56,1\nGIO_HEAPSIZE,cycle,16,56,1"),
        good.replace("GIO_HEAPSIZE,cycle,16,56,1", "GIO_HEAPSIZE,cycle,16,56,2"),
        good.replace("GIO_HEAPSIZE,cycle,16,56,1", "GIO_HEAPSIZE,cycle,16,3000,1"),
        good.replace("GIO_HEAP,cycle,16,2,176,1,0", "GIO_HEAP,cycle,16,2,176,1,1"),
    )
    for bad in wrong:
        try:
            read(bad, True)
        except ValueError:
            pass
        else:
            raise AssertionError("corrupt archived numeric data accepted")
    print("C545D_SAVED_GIO_BIN_EPOCHS_SELFTEST_PASS,negative_cases=6,real_camera=0")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--root", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
    else:
        if args.root is None:
            p.error("--root is required")
        for row in analyze(args.root):
            print(row)


if __name__ == "__main__":
    main()
