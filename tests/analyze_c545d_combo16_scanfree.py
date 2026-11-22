#!/usr/bin/env python3
"""Strict, short Windows2022 original patched-Combo 16-cycle A/B counter analyzer.

The disposable probe has a no-GAppInfo-query final observation. Its metric
comparison is NOT proof of watcher/worker quiescence, linear leak or a fix.
No raw registry values, manifest paths, package names, video or credentials.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

POINTS = (("baseline", 0), ("cycle", 16), ("after_cleanup", 17),
          ("scanfree_cleanup", 18))
TYPES = (
    "GWin32AppInfoApplication", "GWin32AppInfoShellVerb",
    "GWin32AppInfoHandler", "GWin32AppInfoFileExtension",
    "GWin32AppInfoURLSchema", "GWin32RegistryKey", "GWin32AppInfo")
MARKERS = ("C545D_DISPLAY_CACHE,", "C545D_WINRT_BRIDGE,")


def read(raw: str, registry: bool) -> dict:
    expected_done = ("GIO_PROBE_DONE,cycles=16,notifications=",
                     f",reg_changes={int(registry)}")
    done = [l for l in raw.splitlines() if l.startswith("GIO_PROBE_DONE,")]
    if len(done) != 1 or not re.fullmatch(
            r"GIO_PROBE_DONE,cycles=16,notifications=\d+,reg_changes=[01]", done[0]
    ) or not done[0].endswith(expected_done[1]):
        raise ValueError("missing or mismatched 16-cycle completion")
    if raw.splitlines().count("C545D_CI_SCANFREE_FINAL,enabled=1") != 1:
        raise ValueError("missing scan-free proof marker")
    data = {"private": {}, "busy": {}, "types": {}, "scans": []}
    cycles = set()
    for l in raw.splitlines():
        if l.startswith("GIO_PROBE,"):
            m = re.fullmatch(
                r"GIO_PROBE,(baseline|cycle|after_cleanup|scanfree_cleanup),"
                r"(\d+),(\d+),(\d+),(\d+)", l)
            if m is None:
                raise ValueError("bad probe sample")
            phase, index, changed, handles, private = m.groups()
            point = (phase, int(index))
            if point in data["private"] or int(private) < 0:
                raise ValueError("duplicate process checkpoint")
            data["private"][point] = int(private)
            if phase == "cycle":
                cycles.add(int(index))
        elif l.startswith("GIO_HEAP,"):
            m = re.fullmatch(
                r"GIO_HEAP,(baseline|cycle|after_cleanup|scanfree_cleanup),"
                r"(\d+),(\d+),(\d+),(\d+),(\d+)", l)
            if m is None:
                raise ValueError("bad heap checkpoint")
            phase, index, count, busy, heaps, errors = m.groups()
            point = (phase, int(index))
            if point in data["busy"] or int(heaps) < 1 or int(errors) != 0:
                raise ValueError("duplicate/failed HeapWalk census")
            data["busy"][point] = int(busy)
        elif l.startswith("GIO_TYPE,"):
            m = re.fullmatch(
                r"GIO_TYPE,(baseline|cycle|after_cleanup|scanfree_cleanup),"
                r"(\d+),([A-Za-z0-9_]+),(-?\d+)", l)
            if not m:
                raise ValueError("bad GObject type entry")
            phase, index, name, count = m.groups()
            point = (phase, int(index))
            k = (point, name)
            if name not in TYPES or k in data["types"] or int(count) < -1:
                raise ValueError("duplicate/invalid GObject class census")
            data["types"][k] = int(count)
        elif l.startswith(MARKERS):
            data["scans"].append(l)
    expected_probe = set(POINTS) | {("cycle", i) for i in range(1, 17)}
    if set(data["private"]) != expected_probe or cycles != set(range(1, 17)):
        raise ValueError("missing process checkpoints")
    if set(data["busy"]) != set(POINTS):
        raise ValueError("missing heap checkpoints")
    if set(data["types"]) != {(p, n) for p in expected_probe for n in TYPES}:
        raise ValueError("missing GObject census points")
    if registry and not any(x.startswith("C545D_DISPLAY_CACHE,") for x in data["scans"]):
        raise ValueError("patched Combo cache evidence missing")
    data["tracked"] = sum(all(data["types"][p, t] >= 0 for p in POINTS)
                          for t in TYPES)
    return data


def analyze(folder: Path) -> list[str]:
    pair = {}
    for arm in ("nochange", "registry"):
        pair[arm] = read((folder / f"combo-{arm}-16.txt").read_text(encoding="utf-8-sig"),
                         arm == "registry")
    out = []
    for kind in ("private", "busy"):
        for before, after in zip(POINTS[:-1], POINTS[1:]):
            raw = {arm: pair[arm][kind][after] - pair[arm][kind][before]
                   for arm in pair}
            out.append(
                f"C545D_COMBO16_SCANFREE_RESOURCE,kind={kind},"
                f"window={before[1]}_{after[1]},"
                f"registry_raw={raw['registry']},"
                f"nochange_raw={raw['nochange']},"
                f"controlled={raw['registry']-raw['nochange']},"
                "new_alloc_site_proven=0,real_host_untested=1"
            )
    good = sorted(t for t in TYPES if all(
        pair[a]["types"][p, t] >= 0 for a in pair for p in POINTS))
    for t in good:
        for before, after in zip(POINTS[:-1], POINTS[1:]):
            reg = pair["registry"]["types"][after, t] - pair["registry"]["types"][before, t]
            no = pair["nochange"]["types"][after, t] - pair["nochange"]["types"][before, t]
            out.append(
                f"C545D_COMBO16_SCANFREE_GOBJECT,type={t},"
                f"window={before[1]}_{after[1]},registry_raw={reg},"
                f"nochange_raw={no},controlled={reg-no},"
                "instance_count_not_heap_owner=1,CI_only=1"
            )
    out.append(
        "C545D_COMBO16_SCANFREE_PASS,source_mode=combo,cycles=16,"
        f"valid_GObject_types={len(good)},"
        f"GObject_census_unavailable={int(len(good)!=len(TYPES))},"
        "GAppInfo_final_query_skipped=1,worker_quiescence_unproven=1,"
        "results_not_256cycle_equivalent=1,production_unmodified=1,"
        "host_install_approved=0,CI_only=1"
    )
    return out


def selftest() -> None:
    def sample(registry=True):
        out = [
            "C545D_CI_SCANFREE_FINAL,enabled=1",
            f"GIO_PROBE_DONE,cycles=16,notifications=0,reg_changes={int(registry)}",
            "C545D_DISPLAY_CACHE,hits=1,misses=2,entries=2",
        ]
        points = [("baseline",0)] + [("cycle", i) for i in range(1,17)] + list(POINTS[-2:])
        for p, i in points:
            out.append(f"GIO_PROBE,{p},{i},0,30,{1000+i*4096}")
            for t in TYPES:
                out.append(f"GIO_TYPE,{p},{i},{t},2")
            if (p,i) in POINTS:
                out.append(f"GIO_HEAP,{p},{i},6,{1500+i},2,0")
        return "\n".join(out)
    assert read(sample(), True)["tracked"] == len(TYPES)
    assert read(sample(False), False)["tracked"] == len(TYPES)
    bad = [
        sample().replace("enabled=1", "enabled=0"),
        sample().replace("reg_changes=1", "reg_changes=0"),
        sample().replace("GIO_HEAP,cycle,16,6,1516,2,0", ""),
        sample().replace("GIO_TYPE,cycle,16,GWin32RegistryKey,2", ""),
        sample().replace("GIO_PROBE,cycle,10,0,30,41960", ""),
    ]
    for b in bad:
        try: read(b, True)
        except ValueError: pass
        else: raise AssertionError("corrupt sample accepted")
    print("C545D_COMBO16_SCANFREE_SELFTEST_PASS,positive_cases=2,"
          "negative_cases=5,windows_probe_runs=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--folder", type=Path)
    a = p.parse_args()
    if a.selftest:
        selftest()
    else:
        if not a.folder: p.error("--folder required")
        print("\n".join(analyze(a.folder)))


if __name__ == "__main__":
    main()
