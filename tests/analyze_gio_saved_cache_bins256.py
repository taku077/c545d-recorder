#!/usr/bin/env python3
"""Archived three-run 256-cycle exact DisplayName cache vs uncached bin audit.

Reuse numeric-only saved Windows2022 snapshots. No new Windows runs. The
experimental cache is NOT production-safe; 256 cycles do not prove plateau.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

RUNS=("44533452892","44537371920","44545844200")
MODES=("default","cache")
ARMS=("nochange","registry")
SIZES=(56,120,190,194,196,360)
CHECKS=(("baseline",0),("cycle",64),("cycle",128),("cycle",192),
        ("cycle",256),("after_cleanup",257),("settled_cleanup",258))


def parse(raw:str,changed:bool):
    done=re.findall(r"^GIO_PROBE_DONE,cycles=(\d+),notifications=\d+,reg_changes=([01])$",raw,re.M)
    if done!=[("256",str(int(changed)))]:
        raise ValueError("wrong/missing exact 256-cycle completion")
    cycles=list(map(int,re.findall(r"^GIO_PROBE,cycle,(\d+),\d+,\d+,\d+$",raw,re.M)))
    if cycles!=list(range(1,257)):
        raise ValueError("missing or duplicate sequential cycles")
    totals={}
    hist={}
    for line in raw.splitlines():
        a=line.split(",")
        if a[0]=="GIO_HEAP":
            if len(a)!=7 or any(not s.isdecimal() for s in a[2:]):
                raise ValueError("malformed heap")
            key=(a[1],int(a[2]))
            if key in totals or int(a[5])<1 or int(a[6])!=0:
                raise ValueError("bad/duplicate HeapWalk")
            totals[key]=int(a[3])
        elif a[0]=="GIO_HEAPSIZE":
            if len(a)!=5 or any(not s.isdecimal() for s in a[2:]):
                raise ValueError("malformed bin")
            key=(a[1],int(a[2]))
            size,count=int(a[3]),int(a[4])
            if not 0<=size<=2048 or count<=0:
                raise ValueError("invalid size/count")
            bucket=hist.setdefault(key,{})
            if size in bucket:
                raise ValueError("duplicate size")
            bucket[size]=count
    if set(totals)!=set(CHECKS) or set(hist)!=set(CHECKS):
        raise ValueError("missing HeapWalk checkpoint")
    for key in CHECKS:
        if sum(hist[key].values())!=totals[key]:
            raise ValueError("histogram total/count mismatch")
    return {size:{key:hist[key].get(size,0) for key in CHECKS} for size in SIZES}

def analyze(root:Path):
    lines=[]
    for run in RUNS:
        for mode in MODES:
            a={}
            for arm in ARMS:
                a[arm]=parse((root/run/f"{mode}_{arm}_256.log").read_text(encoding="utf-8-sig"),arm=="registry")
            for size in SIZES:
                r=a["registry"][size];c=a["nochange"][size]
                b=("baseline",0)
                def effect(key):
                    return r[key]-r[b]-c[key]+c[b]
                n=[0]+[effect(("cycle",cycle)) for cycle in (64,128,192,256)]
                epochs=[n[i+1]-n[i] for i in range(4)]
                lines.append(
                    f"C545D_SAVED_CACHE_BIN256,run={run},mode={mode},size={size},"
                    f"epochs={';'.join(map(str,epochs))},"
                    f"net256={n[-1]},settled={effect(('settled_cleanup',258))},"
                    "original_msys2=1,allocation_owner_unproven=1,real_camera=0"
                )
    lines.append(
        "C545D_SAVED_CACHE_BIN256_PASS,archived_windows_runs=3,arms=2,"
        "modes=2,sizes=6,new_windows_runs=0,cache_not_release_safe=1,"
        "zero_leak_proven=0,host_install_approved=0"
    )
    return lines

def selftest():
    def fixture():
        rows=["GIO_PROBE_DONE,cycles=256,notifications=0,reg_changes=1"]
        rows.extend(f"GIO_PROBE,cycle,{i},0,100,40000" for i in range(1,257))
        for p,num in CHECKS:
            rows.extend([f"GIO_HEAP,{p},{num},2,310,1,0",
                         f"GIO_HEAPSIZE,{p},{num},190,1",
                         f"GIO_HEAPSIZE,{p},{num},120,1"])
        return "\n".join(rows)
    good=fixture()
    assert parse(good,True)[190][("cycle",256)]==1
    wrong=(
        good.replace("cycles=256,","cycles=255,"),
        good.replace("GIO_PROBE,cycle,100,0,100,40000",""),
        good.replace("GIO_HEAPSIZE,cycle,64,190,1",""),
        good.replace("GIO_HEAPSIZE,cycle,64,190,1","GIO_HEAPSIZE,cycle,64,190,2"),
        good.replace("GIO_HEAPSIZE,cycle,64,190,1","GIO_HEAPSIZE,cycle,64,190,1\nGIO_HEAPSIZE,cycle,64,190,1"),
        good.replace("GIO_HEAP,cycle,64,2,310,1,0","GIO_HEAP,cycle,64,2,310,1,1"),
    )
    for bad in wrong:
        try:parse(bad,True)
        except ValueError:pass
        else:raise AssertionError("corrupt input accepted")
    print("C545D_SAVED_CACHE_BIN256_SELFTEST_PASS,negative_cases=6")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--root",type=Path)
    args=ap.parse_args()
    if args.selftest:selftest()
    else:
        if args.root is None:ap.error("--root required")
        for row in analyze(args.root):print(row)
if __name__=="__main__":main()
