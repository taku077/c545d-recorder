#!/usr/bin/env python3
"""Strict archived-only UWP package-parser API-boundary heap-bin reanalysis.

Archives were generated in disposable MSYS2 Windows2022 16-cycle tests.
Semantics-changing ablation arms are NOT release candidates. Exact size bins
do not identify allocation call stacks or prove long-run leaks.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

RUNS=("44579422709","44555197215","44537408775")
STAGES=("default","noop_callback","skip_manifest","skip_path","skip_location",
        "skip_displayname","no_displayname_getter","call_displayname_discard",
        "cache_displayname","skip_current")
SIZES=(56,120,190,194,196,360)
CHECKS=(("baseline",0),("cycle",16),("after_cleanup",17),("settled_cleanup",18))

def parse(text: str, changed: bool):
    done=re.findall(r"^GIO_PROBE_DONE,cycles=(\d+),notifications=\d+,reg_changes=([01])$",text,re.M)
    if done!=[("16",str(int(changed)))]:
        raise ValueError("unexpected/missing 16-cycle completion")
    cycles=list(map(int,re.findall(r"^GIO_PROBE,cycle,(\d+),\d+,\d+,\d+$",text,re.M)))
    if cycles!=list(range(1,17)):
        raise ValueError("incomplete 16-cycle probe")
    totals={}
    hist={}
    for line in text.splitlines():
        a=line.split(",")
        if a[0]=="GIO_HEAP":
            if len(a)!=7 or any(not x.isdecimal() for x in a[2:]):
                raise ValueError("malformed heap")
            key=(a[1],int(a[2]))
            if key in totals or int(a[5])<1 or int(a[6])!=0:
                raise ValueError("duplicate/failed heap census")
            totals[key]=int(a[3])
        elif a[0]=="GIO_HEAPSIZE":
            if len(a)!=5 or any(not x.isdecimal() for x in a[2:]):
                raise ValueError("malformed histogram")
            key=(a[1],int(a[2]))
            size,count=int(a[3]),int(a[4])
            if size<0 or size>2048 or count<=0:
                raise ValueError("invalid histogram")
            bucket=hist.setdefault(key,{})
            if size in bucket:
                raise ValueError("duplicate histogram bin")
            bucket[size]=count
    if set(totals)!=set(CHECKS) or set(hist)!=set(CHECKS):
        raise ValueError("missing/extra census")
    for key in CHECKS:
        if sum(hist[key].values())!=totals[key]:
            raise ValueError("heap histogram count mismatch")
    return {size:{c:hist[c].get(size,0) for c in CHECKS} for size in SIZES}

def analyze(root:Path):
    lines=[]
    for run in RUNS:
        for stage in STAGES:
            active=parse((root/run/f"{stage}_registry_16.log").read_text(encoding="utf-8-sig"),True)
            baseline=parse((root/run/f"{stage}_nochange_16.log").read_text(encoding="utf-8-sig"),False)
            for size in SIZES:
                b=baseline[size];a=active[size]
                def e(k):
                    return a[k]-a[("baseline",0)]-b[k]+b[("baseline",0)]
                lines.append(
                    f"C545D_SAVED_UWP_BOUNDARY_BIN,run={run},stage={stage},size={size},"
                    f"cycle16={e(('cycle',16))},settled={e(('settled_cleanup',18))},"
                    "msys2_only=1,source_attributed=0,host_approved=0"
                )
    lines.append(
        "C545D_SAVED_UWP_BOUNDARY_PASS,old_windows_runs=3,stages=10,"
        "arms=2,sizes=6,windows_reruns=0,semantic_ablation_only=1,"
        "allocation_stacks_unproven=1,host_approved=0"
    )
    return lines

def selftest():
    def sample():
        out=["GIO_PROBE_DONE,cycles=16,notifications=0,reg_changes=1"]
        out.extend(f"GIO_PROBE,cycle,{i},0,100,40000" for i in range(1,17))
        for phase,num in CHECKS:
            out.extend((f"GIO_HEAP,{phase},{num},2,310,1,0",
                        f"GIO_HEAPSIZE,{phase},{num},190,1",
                        f"GIO_HEAPSIZE,{phase},{num},120,1"))
        return "\n".join(out)
    good=sample()
    assert parse(good,True)[190][("cycle",16)]==1
    broken=(
        good.replace("cycles=16,","cycles=15,"),
        good.replace("GIO_PROBE,cycle,15,0,100,40000",""),
        good.replace("GIO_HEAPSIZE,cycle,16,190,1",""),
        good.replace("GIO_HEAPSIZE,cycle,16,190,1","GIO_HEAPSIZE,cycle,16,190,2"),
        good.replace("GIO_HEAPSIZE,cycle,16,190,1","GIO_HEAPSIZE,cycle,16,190,1\nGIO_HEAPSIZE,cycle,16,190,1"),
        good.replace("GIO_HEAP,cycle,16,2,310,1,0","GIO_HEAP,cycle,16,2,310,1,1"),
    )
    for text in broken:
        try:parse(text,True)
        except ValueError:pass
        else:raise AssertionError("corrupt input accepted")
    print("C545D_SAVED_UWP_BOUNDARY_SELFTEST_PASS,negative_cases=6,real_camera=0")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--root",type=Path)
    args=ap.parse_args()
    if args.selftest:selftest()
    else:
        if args.root is None:ap.error("--root required")
        for row in analyze(args.root):
            print(row)

if __name__=="__main__":main()
