#!/usr/bin/env python3
"""Camera-free 384-cycle MEM_PRIVATE region-size attribution (numeric only).

Paired registry-change/nochange controls. VirtualQuery region bins identify
committed regions by size, NOT who allocated or whether they leaked.
The same 512-cycle diagnostic branch is used; all work is Windows CI only.
"""
import csv
from pathlib import Path
import sys

CHECKPOINTS = tuple(range(0, 385, 64))
SETTLED = 386
TAGS = {"GIO_PROBE": 6, "GIO_VM": 8, "GIO_VMCLASS": 12}
NAMES = ("private_usage", "vm_private", "vm_4k", "vm_4k_to_64k",
         "vm_64k_to_1m", "vm_over_1m",
         "count_4k", "count_4k_to_64k", "count_64k_to_1m",
         "count_over_1m")

def parse_lines(text, scope):
    done = f"GIO_PROBE_DONE,cycles=384,"
    if text.count(done) != 1:
        raise ValueError(f"{scope}: missing/duplicate completion marker")
    expected_change = 0 if scope == "nochange" else 1
    if f"reg_changes={expected_change}" not in text.split(done)[1].splitlines()[0]:
        raise ValueError(f"{scope}: wrong registry-change mode")
    data = {tag: {} for tag in TAGS}
    for line in text.splitlines():
        p = line.strip().split(",")
        tag = p[0]
        if tag not in data:
            continue
        if len(p) != TAGS[tag]:
            raise ValueError(f"{scope}: malformed {tag} with {len(p)} fields")
        label = p[1]
        if label not in ("cycle", "baseline", "settled_cleanup"):
            continue
        if not p[2].isdecimal():
            raise ValueError(f"{scope}: invalid cycle number")
        ix = SETTLED if label == "settled_cleanup" else int(p[2])
        if ix not in (*CHECKPOINTS, SETTLED):
            continue
        if ix in data[tag]:
            raise ValueError(f"{scope}: duplicate {tag} at {ix}")
        if not all(v.isdecimal() for v in p[3:]):
            raise ValueError(f"{scope}: invalid numeric data in {tag}")
        data[tag][ix] = [int(v) for v in p[3:]]
    expected = set((*CHECKPOINTS, SETTLED))
    for tag in TAGS:
        if set(data[tag]) != expected:
            raise ValueError(f"{scope}: missing {tag} checkpoints")
    for ix in expected:
        vm, cls = data["GIO_VM"][ix], data["GIO_VMCLASS"][ix]
        if vm[-1] or cls[-1]:
            raise ValueError(f"{scope}: incomplete VirtualQuery census at {ix}")
        if sum(cls[:4]) != vm[0]:
            raise ValueError(f"{scope}: MEM_PRIVATE bucket sum mismatch at {ix}")
        if any(x < 0 for x in cls):
            raise ValueError(f"{scope}: negative class value")
    h = data["GIO_PROBE"]
    if h[SETTLED][1] - h[0][1] > 4:
        raise ValueError(f"{scope}: retained handle growth")
    return data

def series(d, metric):
    if metric == "private_usage":
        return {i: d["GIO_PROBE"][i][2] for i in CHECKPOINTS}
    if metric == "vm_private":
        return {i: d["GIO_VM"][i][0] for i in CHECKPOINTS}
    ix = NAMES.index(metric) - 2
    return {i: d["GIO_VMCLASS"][i][ix] for i in CHECKPOINTS}

def analyze(a, b):
    rows, by_metric = [], {}
    for name in NAMES:
        base, changed = series(a, name), series(b, name)
        net = [changed[y] - changed[x] - (base[y] - base[x])
               for x, y in zip(CHECKPOINTS, CHECKPOINTS[1:])]
        vals = [name, *net, sum(net[:2]), sum(net[2:]), sum(net[-2:])]
        by_metric[name] = vals
        rows.append(vals)
        print(f"C545D_VMCLASS,{name},per64={';'.join(map(str, net))},"
              f"first128={vals[-3]},last256={vals[-2]},last128={vals[-1]}")
    for i in range(1, 7):
        if sum(by_metric[n][i] for n in NAMES[2:6]) != by_metric["vm_private"][i]:
            raise ValueError(f"MEM_PRIVATE per64 bucket checksum mismatch at window {i}")
    p = by_metric["private_usage"][-1]
    v = by_metric["vm_private"][-1]
    sizes = [by_metric[n][-1] for n in NAMES[2:6]]
    print(f"C545D_VMCLASS_LATE_SUMMARY,private_last128={p},vm_private_last128={v},"
          f"size_bin_deltas={';'.join(map(str,sizes))},"
          "classification=REGION_SIZE_CORRELATION_ONLY_NOT_ALLOCATION_CAUSALITY")
    return rows

def selftest():
    def make(scope, broken=False):
        lines=[]
        for ix in (*CHECKPOINTS, SETTLED):
            label="baseline" if ix == 0 else ("settled_cleanup" if ix == SETTLED else "cycle")
            bump = (ix//64)*4096 if scope=="registry" and ix != SETTLED else 0
            small = 8192+bump
            lines.append(f"GIO_PROBE,{label},{ix},0,100,{1000000+bump}")
            lines.append(f"GIO_VM,{label},{ix},{small+65536},0,0,6,0")
            lines.append(f"GIO_VMCLASS,{label},{ix},{small+(1 if broken else 0)},65536,0,0,2,1,0,0,0")
        lines.append(f"GIO_PROBE_DONE,cycles=384,notifications=0,reg_changes={int(scope=='registry')}")
        return "\n".join(lines)+"\n"
    a=parse_lines(make("nochange"), "nochange")
    b=parse_lines(make("registry"), "registry")
    rows=analyze(a,b)
    assert next(x for x in rows if x[0]=="vm_private")[-1] == 8192
    try:
        parse_lines(make("registry",broken=True), "registry")
    except ValueError as e:
        assert "bucket sum mismatch" in str(e)
    else:
        raise AssertionError("corrupt census was accepted")
    print("C545D_VMCLASS_SELFTEST_PASS")

def main():
    if sys.argv[1:] == ["--selftest"]:
        selftest()
        return
    root=Path("artifacts")
    a=parse_lines((root/"vm_nochange_384.log").read_text(encoding="utf-8"),"nochange")
    b=parse_lines((root/"vm_registry_384.log").read_text(encoding="utf-8"),"registry")
    rows=analyze(a,b)
    with (root/"vm_384_aggregate.csv").open("w",encoding="utf-8",newline="") as f:
        writer=csv.writer(f)
        writer.writerow(("metric","net_0_64","net_64_128","net_128_192",
                         "net_192_256","net_256_320","net_320_384",
                         "first128","last256","last128"))
        writer.writerows(rows)
    print("C545D_VMCLASS_384_DIAGNOSTIC_PASS; WINDOWS_2022_ONLY;"
          "NO_REAL_PACKAGE_EVENTS; NO_HOST_OR_REGISTRY_CHANGES_OUTSIDE_RUNNER;"
          "NOT_ZERO_LEAK_PROOF")

if __name__=="__main__":
    try:
        main()
    except (ValueError,OSError,AssertionError) as e:
        print(f"C545D_VMCLASS_INVALID:{e}",file=sys.stderr)
        sys.exit(2)
