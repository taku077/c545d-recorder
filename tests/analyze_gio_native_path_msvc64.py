#!/usr/bin/env python3
"""Strict numeric-only MSVC WinRT InstalledLocation vs Win32 package path A/B.

CI-only, no host data or package paths are emitted. HeapWalk bins do not
establish an allocation owner or a zero long-term memory slope.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path
from analyze_gio_core_heap64 import CHECKS, parse, effect

SIZES = (24, 28, 56, 120, 190, 194, 196, 360)
MODES = ("core", "native")
ARMS = ("nochange", "registry")


def read(root: Path, mode: str, arm: str):
    raw = (root / f"{mode}-{arm}-64.txt").read_text(encoding="utf-8-sig")
    record = parse(raw, arm == "registry")
    bins = {}
    for match in re.finditer(
        r"^GIO_HEAPSIZE,([a-z_]+),(\d+),(\d+),(\d+)$", raw, re.M
    ):
        phase, step, size, count = match.groups()
        key = ((phase, int(step)), int(size))
        if key in bins:
            raise ValueError("duplicate heap bin")
        bins[key] = int(count)
    if not all(any(k[0] == step for k in bins) for step in CHECKS):
        raise ValueError("missing histogram checkpoint")
    if mode == "native":
        native = [tuple(map(int, m)) for m in re.findall(
            r"^GIO_NATIVE_PATH,(\d+),(\d+),(\d+),(\d+)$", raw, re.M
        )]
        if not native or sum(row[0] for row in native) == 0:
            raise ValueError("native Win32 API not exercised")
        if any(row[3] for row in native):
            raise ValueError("unexpected native path mismatch")
    record["bins"] = {size: {
        check: bins.get((check, size), 0) for check in CHECKS
    } for size in SIZES}
    return record


def equivalence(root: Path, arm: str):
    raw = (root / f"compare-{arm}-16.txt").read_text(encoding="utf-8-sig")
    if len(re.findall(r"^GIO_PROBE_DONE,cycles=16,notifications=\d+,reg_changes=(0|1)$",
                      raw, re.M)) != 1:
        raise ValueError("16-cycle comparison not complete")
    native = [tuple(map(int, m)) for m in re.findall(
        r"^GIO_NATIVE_PATH,(\d+),(\d+),(\d+),(\d+)$", raw, re.M
    )]
    if not native or sum(x[0] for x in native) == 0 or \
       sum(x[2] for x in native) == 0 or any(x[3] for x in native):
        raise ValueError("native vs WinRT exact path equivalence failed")


def analyze(root: Path):
    for arm in ARMS:
        equivalence(root, arm)
    parsed = {(mode, arm): read(root, mode, arm)
              for mode in MODES for arm in ARMS}
    for mode in MODES:
        proof = (root / f"{mode}-public-api.txt").read_text(encoding="utf-8-sig")
        if len(re.findall(r"^GIO_API_PASS,cycles=8,default_type=[01],default_uri=[01],all_for_type=[01],held_valid=1$", proof, re.M)) != 1:
            raise ValueError("public GAppInfo regression absent")
    for size in SIZES:
        results = []
        for mode in MODES:
            nochange = parsed[mode, "nochange"]["bins"][size]
            registry = parsed[mode, "registry"]["bins"][size]
            results.append(effect({"n": nochange}, {"n": registry}, "n",
                                  CHECKS[0], CHECKS[4]))
        print(f"C545D_NATIVE_MSVC_BIN,size={size},core_effect={results[0]},native_effect={results[1]},allocation_stack_attributed=0")
    for metric in ("heap", "mem", "key", "handles"):
        results = []
        for mode in MODES:
            ctrl = parsed[mode, "nochange"]
            reg = parsed[mode, "registry"]
            results.append(effect(ctrl, reg, metric, CHECKS[0],
                                  CHECKS[-1] if metric != "heap" else CHECKS[4]))
        print(f"C545D_NATIVE_MSVC_METRIC,metric={metric},core_effect={results[0]},native_effect={results[1]}")
    print("C545D_NATIVE_MSVC_AB64_PASS,official_sdk_linked=1,core_vs_native=1,matched_controls=1,cycles=64,real_camera=0,zero_leak_proven=0,host_install_approved=0")


def selftest():
    assert SIZES[-1] == 360 and len(CHECKS) == 7
    assert not re.findall(r"^GIO_NATIVE_PATH,(\d+),(\d+),(\d+),(\d+)$",
                          "GIO_NATIVE_PATH,1,0,1,not_numeric", re.M)
    try:
        equivalence(Path("/__missing_c545d_ci__"), "nochange")
    except OSError:
        pass
    else:
        raise AssertionError("missing numeric evidence accepted")
    print("C545D_NATIVE_MSVC_ANALYZER_SELFTEST_PASS")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        selftest()
    elif len(sys.argv) == 3 and sys.argv[1] == "--root":
        analyze(Path(sys.argv[2]))
    else:
        raise SystemExit("usage: analyzer (--selftest | --root <artifacts>)")
