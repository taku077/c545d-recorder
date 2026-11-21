#!/usr/bin/env python3
"""Compare saved GIO HeapWalk 360B bins across existing CI stages only.

Never launches Windows, touches registry or records video. A heap bucket count
is not an allocation-stack identity, nor proof of retained lifetime/leak.
"""
from __future__ import annotations

import argparse
from pathlib import Path

RUN_IDS = (44533452892, 44537371920, 44545844200)
MODES = ("default", "cache")
CYCLES = (0, 64, 128, 192, 256)
STAGES_16 = ("default", "skip_displayname", "skip_current", "skip_location")


def read_counts(path: Path, cycles: tuple[int, ...], changed: bool) -> dict[int, int]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    termination = (f"GIO_PROBE_DONE,cycles={cycles[-1]},"
                   f"notifications=0,reg_changes={int(changed)}")
    if sum(x == termination for x in lines) != 1:
        raise ValueError("missing exactly one matching completion marker")
    heaps: set[int] = set()
    size_bins: dict[int, int] = {}
    for line in lines:
        fields = line.split(",")
        if fields[0] == "GIO_HEAP" and len(fields) == 7:
            try:
                cycle = int(fields[2])
                bad = int(fields[6])
            except ValueError as exc:
                raise ValueError("malformed heap checkpoint") from exc
            if cycle in cycles:
                if cycle in heaps or bad != 0:
                    raise ValueError("duplicate/error heap checkpoint")
                heaps.add(cycle)
        elif fields[0] == "GIO_HEAPSIZE" and len(fields) == 5:
            try:
                cycle, size, count = map(int, fields[2:])
            except ValueError as exc:
                raise ValueError("malformed heap size record") from exc
            if cycle in cycles and size == 360:
                if cycle in size_bins or count < 0:
                    raise ValueError("duplicate/negative exact360 bin")
                size_bins[cycle] = count
    if heaps != set(cycles):
        raise ValueError("incomplete heap checkpoints")
    return {c: size_bins.get(c, 0) for c in cycles}


def net_epochs(folder: Path, prefix: str, cycles: tuple[int, ...]) -> tuple[int, ...]:
    t = read_counts(folder / f"{prefix}_registry_{cycles[-1]}.log", cycles, True)
    c = read_counts(folder / f"{prefix}_nochange_{cycles[-1]}.log", cycles, False)
    net = [t[k] - c[k] for k in cycles]
    return tuple(b - a for a, b in zip(net, net[1:]))


def assess(run256: dict[int, dict[str, tuple[int, ...]]],
           old16: dict[str, tuple[int, ...]]) -> str:
    if set(run256) != set(RUN_IDS) or set(old16) != set(STAGES_16):
        raise ValueError("saved runs/stages incomplete")
    for run in RUN_IDS:
        d = run256[run]
        if set(d) != set(MODES) or any(len(d[m]) != 4 for m in MODES):
            raise ValueError("wrong 256-cycle layout")
        if not all(d[m][-1] == 8 for m in MODES):
            raise ValueError("late 360-bin mismatch")
        if d["default"][-1] != d["cache"][-1]:
            raise ValueError("apparent late cache effect")
    if not all(len(v) == 1 and v[0] == 0 for v in old16.values()):
        raise ValueError("early 16-cycle bin mismatch")
    return "LATE_360_BIN_CACHE_INVARIANT_OWNER_UNATTRIBUTED"


def selftest() -> None:
    good = {r: {m: (2, 0, 0, 8) for m in MODES} for r in RUN_IDS}
    old = {s: (0,) for s in STAGES_16}
    assert assess(good, old) == "LATE_360_BIN_CACHE_INVARIANT_OWNER_UNATTRIBUTED"
    rejected = 0
    for mutation in ("missingrun", "missmode", "late7", "cachelate9", "early1"):
        a = {k: dict(v) for k, v in good.items()}
        b = dict(old)
        if mutation == "missingrun":
            del a[RUN_IDS[0]]
        elif mutation == "missmode":
            del a[RUN_IDS[0]]["cache"]
        elif mutation == "late7":
            a[RUN_IDS[0]]["default"] = (2, 0, 0, 7)
        elif mutation == "cachelate9":
            a[RUN_IDS[0]]["cache"] = (2, 0, 0, 9)
        else:
            b["skip_current"] = (1,)
        try:
            assess(a, b)
        except ValueError:
            rejected += 1
        else:
            raise AssertionError("bad synthetic case accepted: " + mutation)
    assert rejected == 5
    print("C545D_HEAP360_CROSSMODE_SELFTEST_PASS,negative_rejected=5,host=0")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path)
    ap.add_argument("--old16", type=Path)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.root or not args.old16:
        ap.error("--root and --old16 required")
    data = {run: {m: net_epochs(args.root / str(run), m, CYCLES)
                  for m in MODES} for run in RUN_IDS}
    early = {s: net_epochs(args.old16, s, (0, 16)) for s in STAGES_16}
    assess(data, early)
    for run in RUN_IDS:
        d = data[run]
        print(f"C545D_HEAP360_ARCHIVE,run={run},default_last64={d['default'][-1]},"
              f"cache_last64={d['cache'][-1]},"
              f"cache_minus_default_last64={d['cache'][-1]-d['default'][-1]},"
              "allocation_stack_known=0")
    print("C545D_HEAP360_EARLY_API_STAGE,default_16=0,skip_displayname_16=0,"
          "skip_current_16=0,skip_location_16=0,noncomparative_duration=1")
    print("C545D_HEAP360_CROSSMODE_PASS,original_256_runs=3,original_16_runs=1,"
          "new_windows_runs=0,late360_equal_default_cache=3of3,"
          "early16_all_zero=4of4,heap_size_does_not_identify_owner=1,"
          "no_proven_leak_source=1,real_host=0")


if __name__ == "__main__":
    main()
