#!/usr/bin/env python3
"""Reanalyze *already archived* per-cycle PrivateUsage: Windows runs=0.

Control adjustment is within each Core or Combo 256-cycle original pair:
  D_i = (registry_i - registry_0) - (nochange_i - nochange_0)
Reg/unchanged were separate processes and run sequentially, so D_i is a
synthetic workload comparator, not a time-synchronized live memory trace.
Positive D_i is not by itself an allocation stack or endless leak slope.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import analyze_gio_combo_msvc256_saved as source

MODES = ("core", "combo")
ARMS = ("registry", "nochange")
N = 256
POINTS = (0, 64, 128, 192, 256)
FIELDS = ("handles", "private")
PROBE = re.compile(
    r"GIO_PROBE,(baseline|cycle|after_cleanup|settled_cleanup),"
    r"(\d+),(\d+),(\d+),(\d+)$"
)


def readings(rows: list[str]) -> dict:
    cycles: dict[int, tuple[int, int]] = {}
    cleanup: dict[str, tuple[int, int]] = {}
    for line in rows:
        if not line.startswith("GIO_PROBE,"):
            continue
        match = PROBE.fullmatch(line)
        if not match:
            raise ValueError("malformed per-cycle GIO_PROBE")
        label, index, _, handles, private = match.groups()
        i, h, p = int(index), int(handles), int(private)
        if p < 0 or h < 0:
            raise ValueError("negative process resource count")
        if label == "baseline":
            if i != 0 or i in cycles:
                raise ValueError("invalid/duplicate baseline")
            cycles[i] = (h, p)
        elif label == "cycle":
            if not (1 <= i <= N) or i in cycles:
                raise ValueError("extra/duplicate process cycle")
            cycles[i] = (h, p)
        else:
            expected = 257 if label == "after_cleanup" else 258
            if i != expected or label in cleanup:
                raise ValueError("extra/duplicate cleanup sample")
            cleanup[label] = (h, p)
    if set(cycles) != set(range(N + 1)) or set(cleanup) != {
        "after_cleanup", "settled_cleanup"
    }:
        raise ValueError("incomplete 256-cycle process timeline")
    return {"cycles": cycles, "cleanup": cleanup}


def effects(group: dict[str, list[str]]) -> dict:
    data = {mode: {
        arm: readings(group[f"{mode}-{arm}-256"]) for arm in ARMS
    } for mode in MODES}
    result = {}
    for mode in MODES:
        no = data[mode]["nochange"]["cycles"]
        reg = data[mode]["registry"]["cycles"]
        for dim, field in enumerate(FIELDS):
            idx = dim
            b_reg, b_no = reg[0][idx], no[0][idx]
            series = [
                (reg[i][idx] - b_reg) - (no[i][idx] - b_no)
                for i in range(N + 1)
            ]
            settled_reg = data[mode]["registry"]["cleanup"]["settled_cleanup"][idx]
            settled_no = data[mode]["nochange"]["cleanup"]["settled_cleanup"][idx]
            settled = (settled_reg - b_reg) - (settled_no - b_no)
            result[mode, field] = (series, settled)
    return result


def summarize(data: dict, verbose: bool = True) -> list[str]:
    lines = []
    for metric in FIELDS:
        for start, end in zip(POINTS[:-1], POINTS[1:]):
            for mode in MODES:
                series, settled = data[mode, metric]
                steps = [series[i] - series[i - 1] for i in range(start + 1, end + 1)]
                pos = sum(x > 0 for x in steps)
                neg = sum(x < 0 for x in steps)
                flat = sum(x == 0 for x in steps)
                assert len(steps) == 64 and pos + neg + flat == 64
                window = f"{start}_{end}"
                lines.append(
                    f"C545D_SAVED256_STEP,metric={metric},mode={mode},"
                    f"window={window},net={series[end] - series[start]},"
                    f"positive={pos},negative={neg},flat={flat},"
                    f"largest_up={max(steps)},largest_down={min(steps)},"
                    f"range={max(series[start:end+1]) - min(series[start:end+1])},"
                    "host_modified=0"
                )
        for mode in MODES:
            series, settled = data[mode, metric]
            lines.append(
                f"C545D_SAVED256_END,metric={metric},mode={mode},"
                f"cycle256={series[256]},settled258={settled},"
                f"cleanup_change={settled-series[256]},"
                "causal_owner_known=0,zero_leak_proven=0"
            )
    lines.append(
        "C545D_SAVED256_STEP_ANALYSIS_PASS,source_run=44918598339,"
        "original_cycles=256,windows_runs=0,resource_metrics=2,"
        "counterfactuals_matched=1,zero_leak_proven=0,host_install_approved=0"
    )
    if verbose:
        print("\n".join(lines))
    return lines


def analyze(group: dict[str, list[str]]) -> list[str]:
    # Do not bypass old strict checks for complete 4 arms, 16-cycle native
    # parity, cache population/bridge validity and exact resource snapshots.
    original = source.analyze(group, print_output=False)
    if not original[-1].startswith("C545D_SAVED256_NUMERIC_ANALYSIS_PASS,"):
        raise ValueError("original pinned numeric archive failed source checks")
    measurements = effects(group)
    output = summarize(measurements, verbose=False)
    expected = {
        ("core", "private"): [1499136, 573440, 286720, 729088],
        ("combo", "private"): [151552, 233472, -12288, 53248],
        ("core", "handles"): [32, 3, 0, 4],
        ("combo", "handles"): [-1, 1, -1, -3],
    }
    for (mode, metric), deltas in expected.items():
        v, settled = measurements[mode, metric]
        for j, (left, right) in enumerate(zip(POINTS[:-1], POINTS[1:])):
            if v[right] - v[left] != deltas[j]:
                raise ValueError("pinned original 256-cycle effect mismatch")
    if measurements["core", "private"][1] != 3272704 or \
       measurements["combo", "private"][1] != 368640 or \
       measurements["core", "handles"][1] != 38 or \
       measurements["combo", "handles"][1] != -7:
        raise ValueError("pinned original settled memory/handle effect mismatch")
    print("\n".join(output))
    return output


def selftest() -> None:
    def fake():
        o = {}
        for mode in MODES:
            for arm in ARMS:
                label = f"{mode}-{arm}-256"
                o[label] = [
                    f"GIO_PROBE,baseline,0,0,100,15000"
                ] + [
                    f"GIO_PROBE,cycle,{i},0,{100+i},{15000+4096*(i//32)}"
                    for i in range(1, N + 1)
                ] + [
                    "GIO_PROBE,after_cleanup,257,0,400,52000",
                    "GIO_PROBE,settled_cleanup,258,0,390,50000",
                ]
        return o
    clean = fake()
    for metric in FIELDS:
        assert all(len(effects(clean)[mode, metric][0]) == 257
                   for mode in MODES)
    tag = "combo-registry-256"
    baseline = clean[tag][:]
    variants = [
        [r for r in baseline if not r.startswith("GIO_PROBE,cycle,101,")],
        baseline + ["GIO_PROBE,cycle,101,0,201,25000"],
        baseline + ["GIO_PROBE,cycle,259,0,201,25000"],
        [x.replace("GIO_PROBE,cycle,103,0", "GIO_PROBE,cycle,103,WRONG")
         for x in baseline],
        [x.replace("GIO_PROBE,cycle,103,0,203,", "GIO_PROBE,cycle,103,0,-203,")
         for x in baseline],
    ]
    for bad in variants:
        clean[tag] = bad
        try:
            effects(clean)
        except ValueError:
            pass
        else:
            raise AssertionError("corrupted timeline accepted")
    clean[tag] = baseline
    print("C545D_SAVED256_STEP_SELFTEST_PASS,negative_cases=5,original_windows_runs=0")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    elif len(sys.argv) == 3 and sys.argv[1] == "--root":
        analyze(source.load(Path(sys.argv[2])))
    else:
        raise SystemExit("usage: trend (--selftest | --root DIR)")
