#!/usr/bin/env python3
"""Recover strictly numeric 256-cycle Windows traces from a failed CI gate.

The source Windows job already ran the 256-cycle probes. Reuse its SANITIZED
artifact without running Windows again. The unarchived public-API stdout
cannot be independently rechecked; this analyzer proves NUMERIC resource
effects only, never release qualification or absolute memory-leak freedom.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

MODES = ("core", "combo")
ARMS = ("nochange", "registry")
CHECKS = (("baseline", 0), ("cycle", 64), ("cycle", 128),
          ("cycle", 192), ("cycle", 256), ("after_cleanup", 257),
          ("settled_cleanup", 258))
EPOCHS = CHECKS[:5]
SIZES = (24, 28, 56, 120, 190, 194, 196, 360)
TAGS = tuple(f"{mode}-{arm}-256" for mode in MODES for arm in ARMS) + (
    "compare-nochange-16", "compare-registry-16",
)
PREFIXES = ("GIO_HEAP,", "GIO_HEAPSIZE,", "GIO_PROBE,", "GIO_KEY,",
            "GIO_NATIVE_PATH,", "C545D_DISPLAY_CACHE,",
            "C545D_WINRT_BRIDGE,", "GIO_PROBE_DONE,")


def load(root: Path) -> dict[str, list[str]]:
    # The already-finished Windows run #44918598339 reused the old
    # "ab64_safe_trace.txt" output basename in its 256-cycle workflow.
    # Accept the exact existing numeric artifact rather than rerun Windows.
    # An ambiguous directory must fail closed; never merge mixed-run traces.
    candidates = [root / name for name in
                  ("ab256_safe_trace.txt", "ab64_safe_trace.txt")]
    existing = [path for path in candidates if path.is_file()]
    if len(existing) != 1:
        raise ValueError("missing or ambiguous original 256-cycle numeric archive")
    path = existing[0]
    grouped = {tag: [] for tag in TAGS}
    seen = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        meta = re.fullmatch(
            r"C545D_AB256_TRACE,tag=([a-z]+-(?:nochange|registry)-(?:16|256)),"
            r"present=([01]),CI_only=1", raw)
        if meta:
            tag, present = meta.groups()
            if tag not in grouped or tag in seen:
                raise ValueError("duplicate/unknown trace metadata")
            seen[tag] = int(present)
            continue
        if "|" not in raw:
            raise ValueError("unexpected non-numeric archive row")
        tag, entry = raw.split("|", 1)
        if tag not in grouped or not entry.startswith(PREFIXES):
            raise ValueError("unknown numeric tag or non-whitelisted record")
        if not re.fullmatch(r"[A-Za-z0-9_,=]+", entry):
            raise ValueError("non-numeric/unapproved trace value")
        grouped[tag].append(entry)
    if seen != {tag: 1 for tag in TAGS}:
        raise ValueError("incomplete original Windows trace set")
    return grouped


def parse(group: dict[str, list[str]], mode: str, arm: str) -> dict:
    lines = group[f"{mode}-{arm}-256"]
    done = [l for l in lines if l.startswith("GIO_PROBE_DONE,")]
    if len(done) != 1 or not re.fullmatch(
        rf"GIO_PROBE_DONE,cycles=256,notifications=\d+,reg_changes={int(arm=='registry')}",
        done[0]):
        raise ValueError("missing genuine 256-cycle completion")
    heaps, probes, keys, bins = {}, {}, {}, {}
    for line in lines:
        a = line.split(",")
        if a[0] not in ("GIO_HEAP", "GIO_PROBE", "GIO_KEY", "GIO_HEAPSIZE"):
            continue
        if len(a) < 4 or not re.fullmatch(r"[a-z_]+", a[1]):
            raise ValueError("invalid phase metadata")
        try:
            point = (a[1], int(a[2]))
            vals = [int(x) for x in a[3:]]
        except ValueError as exc:
            raise ValueError("non-numeric resource data") from exc
        if any(x < 0 for x in vals):
            raise ValueError("negative resource count")
        if a[0] == "GIO_HEAP":
            if len(a) != 7 or point not in CHECKS or point in heaps or vals[2] < 1 or vals[3] != 0:
                raise ValueError("invalid HeapWalk checkpoint")
            heaps[point] = vals[1]
        elif a[0] == "GIO_PROBE":
            if len(a) != 6 or point in probes:
                raise ValueError("invalid/duplicate per-cycle process sample")
            probes[point] = (vals[1], vals[2])  # handles, PrivateUsage
        elif a[0] == "GIO_KEY":
            if len(a) != 4 or point in keys:
                raise ValueError("duplicate/invalid Key census")
            keys[point] = vals[0]
        elif a[0] == "GIO_HEAPSIZE":
            if len(a) != 5 or point not in CHECKS or vals[0] not in SIZES:
                raise ValueError("unknown/invalid size bin")
            k = (point, vals[0])
            if k in bins:
                raise ValueError("duplicate size-bin evidence")
            bins[k] = vals[1]
    if set(heaps) != set(CHECKS):
        raise ValueError("missing 64-cycle HeapWalk checkpoints")
    all_probes = set(CHECKS) | {("cycle", i) for i in range(1, 257)}
    if set(probes) != all_probes:
        raise ValueError("missing or extra per-cycle PrivateUsage samples")
    if not all(p in keys for p in (CHECKS[0], CHECKS[-1])):
        raise ValueError("missing Key endpoints")
    if mode == "combo":
        natives = [list(map(int, re.fullmatch(
            r"GIO_NATIVE_PATH,(\d+),(\d+),(\d+),(\d+)", l).groups()))
            for l in lines if l.startswith("GIO_NATIVE_PATH,")
            and re.fullmatch(r"GIO_NATIVE_PATH,(\d+),(\d+),(\d+),(\d+)", l)]
        if not natives or sum(n[0] for n in natives) == 0 or any(n[3] for n in natives):
            raise ValueError("native path missing/mismatched")
        cache = [tuple(map(int, m.groups())) for l in lines
                 if (m := re.fullmatch(
                     r"C545D_DISPLAY_CACHE,hits=(\d+),misses=(\d+),entries=(\d+)", l))]
        if not cache or not any(miss > 0 and 0 < ent <= 1024 for hit, miss, ent in cache):
            raise ValueError("cache absent or unpopulated")
        if any(ent > 1024 for hit, miss, ent in cache):
            raise ValueError("cache unbounded")
        if arm == "registry" and not any(hit > 0 for hit, _, _ in cache):
            raise ValueError("cache not reused in registry arm")
        bridge = [tuple(map(int, m.groups())) for l in lines
                  if (m := re.fullmatch(
                      r"C545D_WINRT_BRIDGE,scans=(\d+),injections=(\d+),"
                      r"evictions=(\d+),errors=(\d+),ready=(\d+)", l))]
        if not bridge or not any(row[0] > 0 and row[4] == 1 for row in bridge):
            raise ValueError("bridge not ready")
        if any(row[3] != 0 or row[4] != 1 for row in bridge):
            raise ValueError("bridge reported error/dropout")
    return {
        "mem": {p: probes[p][1] for p in CHECKS},
        "handles": {p: probes[p][0] for p in CHECKS},
        "heap": heaps,
        "key": keys,
        "bins": {s: {p: bins.get((p, s), 0) for p in CHECKS} for s in SIZES},
    }


def compare_path(group: dict[str, list[str]], arm: str) -> None:
    rows = group[f"compare-{arm}-16"]
    done = [r for r in rows if r.startswith("GIO_PROBE_DONE,")]
    if len(done) != 1 or not re.fullmatch(
        rf"GIO_PROBE_DONE,cycles=16,notifications=\d+,reg_changes={int(arm=='registry')}",
        done[0]):
        raise ValueError("16-cycle path comparison incomplete")
    matches = [tuple(map(int, m.groups())) for line in rows
               if (m := re.fullmatch(
                   r"GIO_NATIVE_PATH,(\d+),(\d+),(\d+),(\d+)", line))]
    if not matches or sum(m[0] for m in matches) == 0 or \
       sum(m[2] for m in matches) == 0 or any(m[3] for m in matches):
        raise ValueError("native/WinRT path comparison not equivalent")


def difference(data: dict, metric: str, left: tuple, right: tuple) -> int:
    return ((data["registry"][metric][right] - data["registry"][metric][left]) -
            (data["nochange"][metric][right] - data["nochange"][metric][left]))


def analyze(group: dict[str, list[str]], print_output: bool = True) -> list[str]:
    for arm in ARMS:
        compare_path(group, arm)
    parsed = {mode: {arm: parse(group, mode, arm) for arm in ARMS}
              for mode in MODES}
    results = []
    for left, right in zip(EPOCHS[:-1], EPOCHS[1:]):
        window = f"{left[1]}_{right[1]}"
        for metric in ("mem", "heap", "handles"):
            a, b = (difference(parsed[m], metric, left, right) for m in MODES)
            results.append(f"C545D_SAVED256_EPOCH,window={window},metric={metric},"
                           f"core_effect={a},combo_effect={b},CI_only=1")
        for size in SIZES:
            a, b = (difference({arm: parsed[m][arm]["bins"] for arm in ARMS},
                               size, left, right) for m in MODES)
            results.append(f"C545D_SAVED256_BIN,window={window},size={size},"
                           f"core_effect={a},combo_effect={b},stack_attributed=0")
    for metric in ("mem", "heap", "handles", "key"):
        a, b = (difference(parsed[m], metric, CHECKS[0], CHECKS[-1]) for m in MODES)
        results.append(f"C545D_SAVED256_SETTLED,metric={metric},"
                       f"core_effect={a},combo_effect={b},CI_only=1")
    results.append(
        "C545D_SAVED256_NUMERIC_ANALYSIS_PASS,source_windows_run=44918598339,"
        "cycles=256,controls=4,compare16=2,raw_host_data=0,"
        "sdk_public_api_not_rechecked_from_archive=1,"
        "zero_leak_proven=0,host_install_approved=0")
    if print_output:
        for row in results:
            print(row)
    return results


def selftest() -> None:
    group = {tag: [] for tag in TAGS}
    for mode in MODES:
        for arm in ARMS:
            tag = f"{mode}-{arm}-256"
            for i in range(257):
                phase = "baseline" if i == 0 else "cycle"
                group[tag].append(f"GIO_PROBE,{phase},{i},0,100,{20000+i}")
            for phase, step in CHECKS:
                if step > 256:
                    group[tag].append(f"GIO_PROBE,{phase},{step},0,100,{20000+step}")
                group[tag].extend((
                    f"GIO_HEAP,{phase},{step},1,{1000+step},1,0",
                    f"GIO_HEAPSIZE,{phase},{step},360,2"))
            group[tag].extend((
                "GIO_KEY,baseline,0,10", "GIO_KEY,settled_cleanup,258,11",
                f"GIO_PROBE_DONE,cycles=256,notifications=0,reg_changes={int(arm=='registry')}"))
            if mode == "combo":
                group[tag].extend((
                    "GIO_NATIVE_PATH,32,0,0,0",
                    f"C545D_DISPLAY_CACHE,hits={512 if arm == 'registry' else 0},misses=32,entries=32",
                    "C545D_WINRT_BRIDGE,scans=5,injections=0,evictions=0,errors=0,ready=1"))
    for arm in ARMS:
        group[f"compare-{arm}-16"] = [
            "GIO_NATIVE_PATH,32,0,32,0",
            f"GIO_PROBE_DONE,cycles=16,notifications=0,reg_changes={int(arm=='registry')}"]
    assert analyze(group, False)[-1].startswith("C545D_SAVED256_NUMERIC_ANALYSIS_PASS,")
    # Verify the actual run's unfortunately legacy-named artifact, metadata
    # validation, and refusal to accept duplicate/mixed snapshot sources.
    with tempfile.TemporaryDirectory(prefix="c545d_saved256_loader_") as tmp:
        root = Path(tmp)
        rows = []
        for name, values in group.items():
            rows.append(f"C545D_AB256_TRACE,tag={name},present=1,CI_only=1")
            rows.extend(f"{name}|{value}" for value in values)
        (root / "ab64_safe_trace.txt").write_text(
            "\n".join(rows) + "\n", encoding="ascii")
        assert analyze(load(root), False) == analyze(group, False)
        (root / "ab256_safe_trace.txt").write_text(
            "\n".join(rows) + "\n", encoding="ascii")
        try:
            load(root)
        except ValueError:
            pass
        else:
            raise AssertionError("mixed or duplicate archive basenames accepted")
    tag = "combo-registry-256"
    original = group[tag][:]
    damaged = [
        [l for l in original if l != "GIO_PROBE,cycle,100,0,100,20100"],
        [l.replace("hits=512", "hits=0") for l in original],
        [l.replace("errors=0,ready=1", "errors=1,ready=1") for l in original],
        [l for l in original if l != "GIO_HEAP,cycle,192,1,1192,1,0"],
    ]
    for v in damaged:
        group[tag] = v
        try:
            analyze(group, False)
        except ValueError:
            pass
        else:
            raise AssertionError("corrupt archived numeric trace accepted")
    print("C545D_SAVED256_ANALYZER_SELFTEST_PASS,negative_cases=4")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        selftest()
    elif len(sys.argv) == 3 and sys.argv[1] == "--root":
        analyze(load(Path(sys.argv[2])))
    else:
        raise SystemExit("usage: saved analyzer (--selftest | --root DIR)")
