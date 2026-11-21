#!/usr/bin/env python3
"""Independently audit the late epochs of THREE SAVED Windows 2022 GIO runs.

This script never triggers a GStreamer build, Windows runner, registry update,
or new host measurement. It consumes the SAME numerical old artifacts as the
earlier per-64 residual analyzer, with strict paired treatment-minus-control
definitions and an explicit *no false memory-leak-zero claim* conclusion.

HeapWalk exact-sized allocated-block counts are not allocation stack evidence.
PrivateUsage is committed private bytes, not necessarily live allocated bytes.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from analyze_gio_cached_residual_epochs import (
    RUNS, TYPES, CYCLES, parse_log, delta_by_64,
)

METRICS = ("private_usage", "heap_busy", "size:24", "size:28",
           "size:360") + tuple("type:" + t for t in TYPES)


def guard(data: dict[str, dict[str, tuple[int, ...]]]) -> dict[str, object]:
    if set(data) != {str(run) for run in RUNS}:
        raise ValueError("missing or unexpected original saved run")
    rows = []
    for run in RUNS:
        entry = data[str(run)]
        if set(entry) != {"control", "registry"}:
            raise ValueError("missing matched nochange/registry pair")
        ctl = entry["control"]
        treated = entry["registry"]
        if set(ctl) != set(METRICS) or set(treated) != set(METRICS):
            raise ValueError("missing strict metrics")
        for name in METRICS:
            if len(ctl[name]) != 5 or len(treated[name]) != 5:
                raise ValueError("incomplete checkpoint array")
            if any(n < 0 for n in ctl[name] + treated[name]):
                raise ValueError("negative absolute census value")
        net = {}
        for metric in METRICS:
            reg = {cycle: treated[metric][i] for i, cycle in enumerate(CYCLES)}
            nochange = {cycle: ctl[metric][i] for i, cycle in enumerate(CYCLES)}
            net[metric] = delta_by_64({metric: reg}, {metric: nochange}, metric)
        retained_type_net = [sum(net["type:" + typ][2:]) for typ in TYPES]
        if any(retained_type_net):
            raise ValueError("7 checked GObject type counters changed in last128")
        row = {
            "run_id": run,
            "private_last64": net["private_usage"][3],
            "heap_busy_last64": net["heap_busy"][3],
            "last64_24_blocks": net["size:24"][3],
            "last64_28_blocks": net["size:28"][3],
            "last64_360_blocks": net["size:360"][3],
            "last128_checked_GObject_net": sum(retained_type_net),
        }
        rows.append(row)
    # An old last64 result is not a proof of permanence. Require these
    # previously independently published values before trusting the source
    # artifact mapping, without claiming that late growth is always a leak.
    if [r["private_last64"] for r in rows] != [57344, 8192, 0]:
        raise ValueError("saved private late epoch identity mismatch")
    # An EXACT 360-byte-bin repeat appears in all three runs even when
    # PrivateUsage last64 rounds to zero. It is a count, NOT 8*360 leak bytes.
    if [r["last64_360_blocks"] for r in rows] != [8, 8, 8]:
        raise ValueError("late 360-byte exact-size bin identity mismatch")
    if not any(r["private_last64"] > 0 for r in rows):
        raise ValueError("expected historic residual positive last64 was lost")
    return {"rows": rows, "conclusion": "NO_PROVEN_ZERO_LEAK_OR_INFINITE_PLATEAU"}


def load(root: Path) -> dict[str, dict[str, tuple[int, ...]]]:
    data = {}
    for run in RUNS:
        entry = {}
        for label, source in (("control", "cache_nochange_256.log"),
                              ("registry", "cache_registry_256.log")):
            path = root / str(run) / source
            parsed = parse_log(path.read_text(encoding="utf-8-sig"))
            entry[label] = {
                metric: tuple(parsed[metric][cycle] for cycle in CYCLES)
                for metric in METRICS
            }
        data[str(run)] = entry
    return data


def selftest() -> None:
    def sample(base: int, private_growth: int, bin_growth: int):
        obj = {m: [base] * 5 for m in METRICS}
        obj["private_usage"][-1] = base + private_growth
        obj["size:360"][-1] = base + bin_growth
        return {k: tuple(v) for k, v in obj.items()}
    data = {}
    for run, final in zip(RUNS, (57344, 8192, 0)):
        data[str(run)] = {
            "control": sample(1000, 0, 0),
            "registry": sample(1000, final, 8),
        }
    verified = guard(data)
    assert verified["conclusion"] == "NO_PROVEN_ZERO_LEAK_OR_INFINITE_PLATEAU"
    rejected = 0
    for mutation in ("missing", "bad_private", "bad_360", "bad_GObject", "missing_metric"):
        broken = {k: {mode: dict(v) for mode, v in value.items()}
                  for k, value in data.items()}
        target = broken[str(RUNS[0])]["registry"]
        if mutation == "missing":
            broken.pop(str(RUNS[2]))
        elif mutation == "bad_private":
            target["private_usage"] = (1000, 1000, 1000, 1000, 1000)
        elif mutation == "bad_360":
            target["size:360"] = (1000, 1000, 1000, 1000, 1007)
        elif mutation == "bad_GObject":
            target["type:" + TYPES[0]] = (1000, 1000, 1000, 1000, 1001)
        else:
            target.pop("heap_busy")
        try:
            guard(broken)
        except ValueError:
            rejected += 1
        else:
            raise AssertionError("malformed synthetic case accepted: " + mutation)
    assert rejected == 5
    print("C545D_LATE_EPOCH_GUARD_SELFTEST_PASS,valid=1,corrupt_rejected=5,real_host=0")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--selftest", action="store_true")
    a = parser.parse_args()
    if a.selftest:
        selftest()
        return
    if a.root is None:
        parser.error("--root required for saved artifacts")
    result = guard(load(a.root))
    for row in result["rows"]:
        print("C545D_LATE_EPOCH_NUMERIC,run={run_id},private_last64={private_last64},"
              "heap_busy_last64={heap_busy_last64},blocks24_last64={last64_24_blocks},"
              "blocks28_last64={last64_28_blocks},blocks360_last64={last64_360_blocks},"
              "GObjects_seven_last128={last128_checked_GObject_net}".format(**row))
    print("C545D_LATE_EPOCH_GUARD_PASS,old_windows_runs=3,new_windows_runs=0,"
          "control_subtracted=1,private_late_positive=2of3,"
          "exact_360_bin_late_positive=3of3,"
          "no_proven_zero_leak=1,no_proven_infinite_plateau=1,"
          "allocation_stacks_attributed=0,host_validated=0")


if __name__ == "__main__":
    main()
