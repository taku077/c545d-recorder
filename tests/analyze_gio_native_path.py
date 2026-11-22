#!/usr/bin/env python3
"""Analyze disposable Windows UWP package-path comparison; never log paths."""
from pathlib import Path
import csv
import sys

STAGES = ("winrt", "native", "compare")

def read(path):
    data = {}
    cycles = 0
    done = 0
    sums = [0, 0, 0, 0]
    api_records = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        row = line.strip().split(",")
        if row[0] == "GIO_PROBE_DONE" and "cycles=16" in line:
            done += 1
        if row[0] == "GIO_PROBE" and row[1] == "cycle":
            cycles += 1
        if row[0] == "GIO_NATIVE_PATH":
            if len(row) != 5 or not all(x.isdecimal() for x in row[1:]):
                raise ValueError("invalid native path counts")
            api_records += 1
            for i, count in enumerate(map(int, row[1:])):
                sums[i] += count
        if row[0] not in ("GIO_PROBE", "GIO_HEAP", "GIO_VM"):
            continue
        if row[1] not in ("baseline", "settled_cleanup"):
            continue
        expected = {"GIO_PROBE": 6, "GIO_HEAP": 7, "GIO_VM": 8}[row[0]]
        if len(row) != expected or any(not x.isdecimal() for x in row[2:]):
            raise ValueError("invalid counters")
        k = row[0], row[1]
        if k in data:
            raise ValueError("duplicate snapshot")
        data[k] = list(map(int, row[2:]))
    if cycles != 16 or done != 1 or len(data) != 6:
        raise ValueError(f"missing expected 16-cycle records for {path}")
    for kind in ("GIO_HEAP", "GIO_VM"):
        for phase in ("baseline", "settled_cleanup"):
            if data[(kind, phase)][-1] != 0:
                raise ValueError("invalid heap/virtual query scan")
    result = {}
    for kind, name, i in (("GIO_PROBE", "private", 3),
                          ("GIO_PROBE", "handles", 2),
                          ("GIO_HEAP", "heap_busy", 2),
                          ("GIO_HEAP", "heap_blocks", 1),
                          ("GIO_VM", "vm_private", 1)):
        result[name] = data[(kind, "settled_cleanup")][i]-data[(kind, "baseline")][i]
    return result, sums, api_records

def main():
    out = []
    for mode in STAGES:
        changed, changed_api, n_changed = read(Path(f"artifacts/{mode}_registry_16.log"))
        control, control_api, n_control = read(Path(f"artifacts/{mode}_nochange_16.log"))
        net = {k: changed[k]-control[k] for k in changed}
        if mode != "winrt":
            if n_changed == 0 or n_control == 0 or changed_api[0] == 0:
                raise ValueError(f"native API was not exercised: {mode}")
            if mode == "compare" and changed_api[2] <= 0:
                raise ValueError("no WinRT/native path matches")
            if mode == "compare" and any((changed_api[3], control_api[3])):
                raise ValueError("WinRT/native path disagreement, NOT safe for substitution")
        print("NATIVE_PATH_MODE,"+mode+","+",".join(f"{k}={v:+d}" for k,v in net.items())+
              f",native_success={changed_api[0]},native_fallback={changed_api[1]},"+
              f"matches={changed_api[2]},mismatches={changed_api[3]}")
        out.append((mode,net,changed_api))
    with Path("artifacts/native_path_comparison.csv").open("w",encoding="utf-8",newline="") as f:
        w = csv.writer(f)
        w.writerow(("mode", *out[0][1].keys(),"native_success","native_fallback","matches","mismatches"))
        for mode,net,a in out:
            w.writerow((mode,*net.values(),*a))
    print("NATIVE_PATH_DIAGNOSTIC_PASS; NOT_PRODUCTION_CERTIFICATION")

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, IndexError) as e:
        print("NATIVE_PATH_INVALID:"+str(e),file=sys.stderr)
        sys.exit(2)
