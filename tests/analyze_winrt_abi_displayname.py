#!/usr/bin/env python3
"""Numeric-only source-layer differential: C++/WinRT vs raw IPackage2 HSTRING.
No installed package names, paths or registry values appear in input/output.
This test cannot prove an OS bug, a Win10 recorder issue or zero long-run leak.
"""
from __future__ import annotations
import argparse
import csv
import re
from pathlib import Path

SAMPLE = re.compile(r"^WINRT_ABI,(control|projected|raw),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)$")
DONE = re.compile(r"^WINRT_ABI_DONE,(control|projected|raw),cycles=128,package_count=(\d+),api_errors=(\d+),checksum=(\d+)$")
FIELDS = ("private_bytes","heap_busy_bytes","heap_busy_blocks","handles")
STEPS = (0,32,64,96,128)


def parse(data: str, mode: str):
    samples = {}
    completed = []
    for line in data.splitlines():
        d = SAMPLE.fullmatch(line.strip())
        if d:
            if d.group(1) != mode:
                raise ValueError("wrong mode in numeric sample")
            nums = tuple(int(n) for n in d.groups()[1:])
            n, *fields = nums
            if n in samples:
                raise ValueError("duplicate numeric checkpoint")
            samples[n] = tuple(fields)
            continue
        d = DONE.fullmatch(line.strip())
        if d:
            if d.group(1) != mode:
                raise ValueError("wrong mode in completion")
            completed.append(tuple(int(n) for n in d.groups()[1:]))
    if set(samples) != set(STEPS) or len(completed) != 1:
        raise ValueError("missing checkpoints or duplicate completion")
    pkg_count, errors, checksum = completed[0]
    if pkg_count < 5 or errors or checksum <= 0:
        raise ValueError("failed Windows PackageManager query")
    if any(row[4] != pkg_count or row[5] != 0 or row[6] != 0 for row in samples.values()):
        raise ValueError("changing packages, Windows API errors, or incomplete HeapWalk")
    if samples[0][0] <= 0 or samples[0][1] <= 0:
        raise ValueError("uninitialized memory census")
    return samples, pkg_count


def compare(contents):
    tables = {}
    counts = {}
    for mode in ("control","projected","raw"):
        tables[mode], counts[mode] = parse(contents[mode],mode)
    if max(counts.values()) - min(counts.values()) > 2:
        raise ValueError("noncomparable package counts")
    output = []
    for i,field in enumerate(FIELDS):
        diffs = {m: t[128][i] - t[0][i] for m,t in tables.items()}
        row = {
            "metric":field,
            "control_growth":diffs["control"],
            "projected_growth":diffs["projected"],
            "raw_growth":diffs["raw"],
            "projected_minus_control":diffs["projected"]-diffs["control"],
            "raw_minus_control":diffs["raw"]-diffs["control"],
            "projected_last64_minus_control":
                (tables["projected"][128][i]-tables["projected"][64][i])-
                (tables["control"][128][i]-tables["control"][64][i]),
            "raw_last64_minus_control":
                (tables["raw"][128][i]-tables["raw"][64][i])-
                (tables["control"][128][i]-tables["control"][64][i]),
        }
        output.append(row)
    return output, counts


def selftest():
    def fake(mode):
        s=[]
        factors={"control":0,"projected":2,"raw":2}
        for step in STEPS:
            f=factors[mode]*step
            s.append(f"WINRT_ABI,{mode},{step},{100000+f*4096},"
                     f"{10000+f*1024},{1000+f},{130},32,0,0")
        s.append(f"WINRT_ABI_DONE,{mode},cycles=128,package_count=32,"
                 "api_errors=0,checksum=123")
        return "\n".join(s)
    data={mode:fake(mode) for mode in ("control","projected","raw")}
    good, counts=compare(data)
    assert counts == {mode:32 for mode in data}
    assert next(row for row in good if row["metric"]=="heap_busy_blocks")["raw_minus_control"] == 256
    invalid=[
        {**data,"raw":data["raw"].replace("WINRT_ABI,raw,32,","WINRT_ABI,raw,64,")},
        {**data,"projected":data["projected"].replace("api_errors=0","api_errors=1")},
        {**data,"raw":data["raw"].replace("32,0,0\nWINRT_ABI_DONE","32,0,1\nWINRT_ABI_DONE")},
        {**data,"raw":data["raw"].replace("package_count=32","package_count=2")},
    ]
    for broken in invalid:
        try:compare(broken)
        except ValueError: pass
        else: raise AssertionError("corrupt evidence was accepted")
    print("C545D_WINRT_ABI_ANALYZER_SELFTEST_PASS,valid=1,rejected=4")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--directory",type=Path,default=Path("artifacts"))
    ap.add_argument("--selftest",action="store_true")
    args=ap.parse_args()
    if args.selftest:
        selftest()
        return
    files={mode:(args.directory/f"winrt_abi_{mode}.txt").read_text(encoding="utf-8-sig")
           for mode in ("control","projected","raw")}
    rows,counts=compare(files)
    with (args.directory/"winrt_abi_comparison.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    for row in rows:
        print("C545D_WINRT_ABI_COMPARISON,"+
              ",".join(f"{key}={value}" for key,value in row.items()))
    print(f"C545D_WINRT_ABI_EXPERIMENT_PASS,cycles=128,"
          f"control_packages={counts['control']},"
          f"projected_packages={counts['projected']},raw_packages={counts['raw']},"
          "all_hstrings_released=1,NO_GLIB=1,NO_RECORDER=1,"
          "OS_CAUSALITY_NOT_PROVEN=1")


if __name__ == "__main__":
    main()
