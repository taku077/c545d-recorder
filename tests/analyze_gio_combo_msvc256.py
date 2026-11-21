#!/usr/bin/env python3
"""Strict, CI-only 256-cycle combined MSVC GIO controlled residual analysis.

Four matched 256-cycle arms, plus two 16-cycle WinRT/native path parity
checks. A size-bin delta is NOT allocation stack attribution. Quantized
PrivateUsage and HeapWalk BUSY need not be leaks. Never certify the host.
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


def numeric_rows(raw: str, label: str, width: int, out: dict, index: int) -> None:
    for line in raw.splitlines():
        if not line.startswith(label + ","):
            continue
        fields = line.split(",")
        if len(fields) != width or fields[0] != label:
            raise ValueError(f"invalid numeric {label} record")
        try:
            nums = tuple(int(v) for v in fields[index:])
            point = (fields[1], int(fields[2]))
        except ValueError as exc:
            raise ValueError(f"non-numeric {label} evidence") from exc
        if point not in CHECKS or point in out or any(v < 0 for v in nums):
            raise ValueError(f"duplicate, invalid or negative {label} checkpoint")
        out[point] = fields


def read(root: Path, mode: str, arm: str) -> dict:
    raw = (root / f"{mode}-{arm}-256.txt").read_text(encoding="utf-8-sig")
    done = re.findall(
        r"^GIO_PROBE_DONE,cycles=256,notifications=(\d+),reg_changes=([01])$",
        raw, re.M)
    if len(done) != 1 or done[0][1] != ("1" if arm == "registry" else "0"):
        raise ValueError("wrong or incomplete 256-cycle scope probe")
    heap_fields, probe_fields, key_fields = {}, {}, {}
    numeric_rows(raw, "GIO_HEAP", 7, heap_fields, 3)
    numeric_rows(raw, "GIO_PROBE", 6, probe_fields, 3)
    # GIO_KEY is not at every checkpoint; parse its baseline+settled endpoints.
    for row in re.findall(r"^GIO_KEY,([a-z_]+),(\d+),(\d+)$", raw, re.M):
        point = (row[0], int(row[1]))
        if point in key_fields or int(row[2]) < 0:
            raise ValueError("duplicate/negative Key census")
        key_fields[point] = int(row[2])
    if set(heap_fields) != set(CHECKS) or set(probe_fields) != set(CHECKS):
        raise ValueError("missing 256-cycle heap or process checkpoint")
    if not all(point in key_fields for point in (CHECKS[0], CHECKS[-1])):
        raise ValueError("missing baseline/settled Key census")
    heap = {}
    mem = {}
    handles = {}
    for point in CHECKS:
        h, p = heap_fields[point], probe_fields[point]
        if int(h[5]) < 1 or int(h[6]) != 0:
            raise ValueError("incomplete HeapWalk summary")
        heap[point] = int(h[4])  # BUSY bytes
        handles[point] = int(p[4])
        mem[point] = int(p[5])   # PrivateUsage
    bins = {}
    valid_histogram = set()
    for match in re.finditer(
        r"^GIO_HEAPSIZE,([a-z_]+),(\d+),(\d+),(\d+)$", raw, re.M
    ):
        phase, index, size, count = match.groups()
        point = (phase, int(index))
        if point not in CHECKS:
            raise ValueError("extra size histogram checkpoint")
        key = (point, int(size))
        if key in bins or int(count) < 0:
            raise ValueError("duplicate or negative size histogram")
        bins[key] = int(count)
        valid_histogram.add(point)
    if valid_histogram != set(CHECKS):
        raise ValueError("missing size histogram checkpoint")
    if mode == "combo":
        native = [tuple(map(int, m)) for m in re.findall(
            r"^GIO_NATIVE_PATH,(\d+),(\d+),(\d+),(\d+)$", raw, re.M)]
        if not native or sum(row[0] for row in native) == 0 or any(row[3] for row in native):
            raise ValueError("combined native path absent or mismatch")
        cache = [tuple(map(int, m)) for m in re.findall(
            r"^C545D_DISPLAY_CACHE,hits=(\d+),misses=(\d+),entries=(\d+)$",
            raw, re.M)]
        if not cache or not any(misses > 0 and 0 < entries <= 1024
                                for hits, misses, entries in cache):
            raise ValueError("combined DisplayName cache not populated")
        if any(entries > 1024 for hits, misses, entries in cache):
            raise ValueError("combined DisplayName cache exceeded hard cap")
        if arm == "registry" and not any(hits > 0 for hits, _, _ in cache):
            raise ValueError("registry mutation failed to reuse cache")
        bridge = [tuple(map(int, m)) for m in re.findall(
            r"^C545D_WINRT_BRIDGE,scans=(\d+),injections=(\d+),"
            r"evictions=(\d+),errors=(\d+),ready=(\d+)$", raw, re.M)]
        if not bridge or not any(row[0] > 0 and row[4] == 1 for row in bridge):
            raise ValueError("dedicated MTA bridge not ready")
        if any(row[3] or row[4] != 1 for row in bridge):
            raise ValueError("dedicated MTA bridge error or dropout")
    return {
        "heap": heap, "mem": mem, "handles": handles, "key": key_fields,
        "bins": {size: {p: bins.get((p, size), 0) for p in CHECKS}
                 for size in SIZES},
    }


def parity(root: Path, arm: str) -> None:
    raw = (root / f"compare-{arm}-16.txt").read_text(encoding="utf-8-sig")
    if len(re.findall(r"^GIO_PROBE_DONE,cycles=16,notifications=\d+,reg_changes=([01])$",
                      raw, re.M)) != 1:
        raise ValueError("missing 16-cycle path comparison")
    native = [tuple(map(int, x)) for x in re.findall(
        r"^GIO_NATIVE_PATH,(\d+),(\d+),(\d+),(\d+)$", raw, re.M)]
    if not native or sum(v[0] for v in native) == 0 or \
       sum(v[2] for v in native) == 0 or any(v[3] for v in native):
        raise ValueError("native/WinRT path disagreement")


def effect(control: dict, test: dict, metric: str, left: tuple, right: tuple) -> int:
    return ((test[metric][right] - test[metric][left]) -
            (control[metric][right] - control[metric][left]))


def analyze(root: Path, emit: bool = True) -> list[str]:
    for arm in ARMS:
        parity(root, arm)
    data = {(mode, arm): read(root, mode, arm)
            for mode in MODES for arm in ARMS}
    for mode in MODES:
        proof = (root / f"{mode}-public-api.txt").read_text(encoding="utf-8-sig")
        if len(re.findall(
            r"^GIO_API_PASS,cycles=8,default_type=[01],default_uri=[01],all_for_type=[01],held_valid=1$",
            proof, re.M)) != 1:
            raise ValueError("official SDK-linked public GAppInfo API not proved")
    out = []
    for left, right in zip(EPOCHS[:-1], EPOCHS[1:]):
        label = f"{left[1]}_{right[1]}"
        for metric in ("mem", "heap", "handles"):
            values = [effect(data[m, "nochange"], data[m, "registry"],
                             metric, left, right) for m in MODES]
            out.append(f"C545D_COMBO_MSVC256_EPOCH,metric={metric},window={label},"
                       f"core_effect={values[0]},combo_effect={values[1]},CI_only=1")
        for size in SIZES:
            values = [effect(data[m, "nochange"]["bins"],
                             data[m, "registry"]["bins"], size, left, right)
                      for m in MODES]
            out.append(f"C545D_COMBO_MSVC256_BIN,size={size},window={label},"
                       f"core_effect={values[0]},combo_effect={values[1]},"
                       "stack_attributed=0")
    for metric in ("mem", "heap", "handles", "key"):
        values = [effect(data[m, "nochange"], data[m, "registry"],
                         metric, CHECKS[0], CHECKS[-1]) for m in MODES]
        out.append(f"C545D_COMBO_MSVC256_SETTLED,metric={metric},"
                   f"core_effect={values[0]},combo_effect={values[1]},CI_only=1")
    out.append("C545D_COMBO_MSVC_AB256_PASS,official_sdk_linked=1,"
               "core_vs_combo=1,matched_controls=1,cycles=256,"
               "native_path=1,display_cache_registry_reuse=1,"
               "bridge_ready_errors0=1,zero_longterm_leak_proven=0,"
               "real_camera=0,host_install_approved=0")
    if emit:
        for row in out:
            print(row)
    return out


def selftest() -> None:
    with tempfile.TemporaryDirectory(prefix="c545d_combo256_") as work:
        root = Path(work)
        for mode in MODES:
            for arm in ARMS:
                rows = []
                for phase, cycle in CHECKS:
                    rows.extend((
                        f"GIO_HEAP,{phase},{cycle},1,{1000+cycle},1,0",
                        f"GIO_HEAPSIZE,{phase},{cycle},360,1",
                        f"GIO_PROBE,{phase},{cycle},0,100,{15000+cycle}"))
                    if (phase, cycle) in (CHECKS[0], CHECKS[-1]):
                        rows.append(f"GIO_KEY,{phase},{cycle},10")
                if mode == "combo":
                    rows.extend((
                        "GIO_NATIVE_PATH,32,0,0,0",
                        f"C545D_DISPLAY_CACHE,hits={512 if arm == 'registry' else 0},misses=32,entries=32",
                        "C545D_WINRT_BRIDGE,scans=3,injections=0,evictions=0,errors=0,ready=1"))
                rows.append(f"GIO_PROBE_DONE,cycles=256,notifications=0,reg_changes={int(arm == 'registry')}")
                (root / f"{mode}-{arm}-256.txt").write_text("\n".join(rows)+"\n", encoding="utf-8")
        for mode in MODES:
            (root / f"{mode}-public-api.txt").write_text(
                "GIO_API_PASS,cycles=8,default_type=1,default_uri=1,all_for_type=1,held_valid=1\n",
                encoding="utf-8")
        for arm in ARMS:
            (root / f"compare-{arm}-16.txt").write_text(
                "GIO_NATIVE_PATH,32,0,32,0\n"
                f"GIO_PROBE_DONE,cycles=16,notifications=0,reg_changes={int(arm == 'registry')}\n",
                encoding="utf-8")
        assert analyze(root, emit=False)[-1].startswith("C545D_COMBO_MSVC_AB256_PASS,")
        file = root / "combo-registry-256.txt"
        good = file.read_text(encoding="utf-8")
        damaged = [
            good.replace("GIO_HEAP,cycle,192,1,1192,1,0", "", 1),
            good.replace("hits=512", "hits=0", 1),
            good.replace("errors=0,ready=1", "errors=1,ready=1", 1),
            good.replace("entries=32", "entries=1025", 1),
        ]
        for bad in damaged:
            file.write_text(bad, encoding="utf-8")
            try:
                analyze(root, emit=False)
            except ValueError:
                pass
            else:
                raise AssertionError("bad 256-cycle evidence accepted")
        file.write_text(good, encoding="utf-8")
        assert analyze(root, emit=False)[-1].startswith("C545D_COMBO_MSVC_AB256_PASS,")
    print("C545D_COMBO_MSVC256_ANALYZER_SELFTEST_PASS,negative_cases=4")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        selftest()
    elif len(sys.argv) == 3 and sys.argv[1] == "--root":
        analyze(Path(sys.argv[2]))
    else:
        raise SystemExit("usage: analyzer (--selftest | --root DIR)")
