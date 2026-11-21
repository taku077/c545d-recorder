#!/usr/bin/env python3
"""Saved-only cross-stage GIO exact heap-size analysis; no Windows rerun.

The old MSYS2 stage-ablation builds change GAppInfo functionality. Differences
locate an experimental source stage, not a shippable fix, stack or OS leak.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

RUNS = ("44579422831", "44555197012", "44537380799")
STAGES = ("default", "skip_uwp", "skip_uwp_enum", "skip_uwp_handlers")
ARMS = ("nochange", "registry")
SIZES = (56, 120, 190, 194, 196, 360)
CHECKS = (("baseline", 0), ("cycle", 16), ("cycle", 32),
          ("cycle", 48), ("cycle", 64), ("after_cleanup", 65),
          ("settled_cleanup", 66))


def parse(raw: str, modified: bool) -> dict[int, dict[tuple[str,int],int]]:
    done = re.findall(
        r"^GIO_PROBE_DONE,cycles=(\d+),notifications=\d+,reg_changes=([01])$",
        raw, re.M)
    if done != [("64", str(int(modified)))]:
        raise ValueError("wrong/missing exact 64-cycle completion")
    cycles = re.findall(r"^GIO_PROBE,cycle,(\d+),\d+,\d+,\d+$", raw, re.M)
    if list(map(int, cycles)) != list(range(1,65)):
        raise ValueError("missing/duplicate chronological probe cycles")
    heaps: dict[tuple[str,int],int] = {}
    size_counts: dict[tuple[str,int],dict[int,int]] = {}
    for row in raw.splitlines():
        a = row.split(",")
        if a[0] == "GIO_HEAP":
            if len(a) != 7 or any(not x.isdecimal() for x in a[2:]):
                raise ValueError("malformed heap checkpoint")
            key = (a[1], int(a[2]))
            if key in heaps or int(a[5]) < 1 or int(a[6]) != 0:
                raise ValueError("duplicate/failed heap census")
            heaps[key] = int(a[3])
        elif a[0] == "GIO_HEAPSIZE":
            if len(a) != 5 or any(not x.isdecimal() for x in a[2:]):
                raise ValueError("malformed heap bin")
            key = (a[1], int(a[2]))
            size, count = int(a[3]), int(a[4])
            if not (0 <= size <= 2048) or count <= 0:
                raise ValueError("invalid heap size")
            bucket = size_counts.setdefault(key,{})
            if size in bucket:
                raise ValueError("duplicate heap size entry")
            bucket[size] = count
    if set(heaps) != set(CHECKS) or set(size_counts) != set(CHECKS):
        raise ValueError("missing/extra heap bin checkpoint")
    for key in CHECKS:
        if sum(size_counts[key].values()) != heaps[key]:
            raise ValueError("GIO_HEAP busy-block total does not match histogram")
    return {size: {key: size_counts[key].get(size,0) for key in CHECKS}
            for size in SIZES}


def analyze(root: Path) -> list[str]:
    rows=[]
    for run in RUNS:
        for stage in STAGES:
            pair={}
            for arm in ARMS:
                p=root/run/f"{stage}_{arm}_64.log"
                pair[arm]=parse(p.read_text(encoding="utf-8-sig"), arm=="registry")
            for size in SIZES:
                changed=pair["registry"][size]
                control=pair["nochange"][size]
                zero=("baseline",0)
                def effect(where):
                    return changed[where]-changed[zero]-(control[where]-control[zero])
                s0=effect(("cycle",48))
                s1=effect(("cycle",64))
                sc=effect(("settled_cleanup",66))
                rows.append(
                    f"C545D_SAVED_STAGE_BIN64,run={run},stage={stage},size={size},"
                    f"net48={s0},net64={s1},last16={s1-s0},settled={sc},"
                    "msys2_only=1,source_attributed=0,real_camera=0"
                )
    rows.append(
        "C545D_SAVED_STAGE_BIN64_PASS,archived_windows_runs=3,stages=4,"
        "matched_arms=2,bin_sizes=6,new_windows_runs=0,"
        "msvc_parity_not_proven=1,allocation_owner_unproven=1,host_approved=0"
    )
    return rows


def selftest():
    def sample(active=1):
        rows=[f"GIO_PROBE_DONE,cycles=64,notifications=0,reg_changes={active}"]
        rows += [f"GIO_PROBE,cycle,{n},0,100,40000" for n in range(1,65)]
        for phase,n in CHECKS:
            rows += [f"GIO_HEAP,{phase},{n},2,310,1,0",
                     f"GIO_HEAPSIZE,{phase},{n},190,1",
                     f"GIO_HEAPSIZE,{phase},{n},120,1"]
        return "\n".join(rows)
    good=sample()
    assert parse(good,True)[190][("cycle",64)]==1
    corrupt=(
        good.replace("cycles=64","cycles=63"),
        good.replace("GIO_PROBE,cycle,32,0,100,40000",""),
        good.replace("GIO_HEAPSIZE,cycle,16,190,1",""),
        good.replace("GIO_HEAPSIZE,cycle,16,190,1","GIO_HEAPSIZE,cycle,16,190,2"),
        good.replace("GIO_HEAPSIZE,cycle,16,190,1",
                     "GIO_HEAPSIZE,cycle,16,190,1\nGIO_HEAPSIZE,cycle,16,190,1"),
        good.replace("GIO_HEAP,cycle,16,2,310,1,0","GIO_HEAP,cycle,16,2,310,1,1"),
    )
    for bad in corrupt:
        try:
            parse(bad,True)
        except ValueError:
            pass
        else:
            raise AssertionError("malformed archive accepted")
    print("C545D_SAVED_STAGE_BIN64_SELFTEST_PASS,negative_cases=6,real_camera=0")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--root",type=Path)
    args=ap.parse_args()
    if args.selftest:
        selftest()
    else:
        if args.root is None: ap.error("--root required")
        for row in analyze(args.root):
            print(row)


if __name__=="__main__":
    main()
