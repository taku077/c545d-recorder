#!/usr/bin/env python3
"""Classify WinRT InstalledLocation.Path() 512-cycle growth vs ID-only control.

A plateau candidate is NOT memory-leak proof. This only reports four 128-cycle
control-subtracted windows and private vs live HeapWalk BUSY divergence.
No package names, paths, credentials or host data are persisted.
"""
from pathlib import Path
import sys
import csv
ROOT=Path("artifacts")

def load(mode):
    p=ROOT/f"{mode}_512.log"
    text=p.read_text(encoding="utf-8")
    if text.count(f"C545D_PATH_DIRECT_DONE,{mode},cycles=512,")!=1:
        raise ValueError(f"{mode}: missing completed 512-cycle marker")
    rows={}
    for line in text.splitlines():
        v=line.strip().split(",")
        if not v or v[0]!="C545D_PATH_DIRECT":continue
        if len(v)!=10 or v[1]!=mode:raise ValueError("malformed row")
        i=int(v[2])
        if i in rows:raise ValueError("duplicate checkpoint")
        rows[i]=list(map(int,v[3:]))
    if set(rows)!=set(range(0,513,64)):raise ValueError("incomplete 64-cycle snapshots")
    if any(z[6]!=0 for z in rows.values()):
        raise ValueError("invalid HeapWalk snapshot")
    if min(z[4] for z in rows.values())<5:raise ValueError("insufficient packages")
    return rows

def main():
    control=load("id_only")
    getter=load("location")
    if abs(control[512][4]-getter[512][4])>2:
        raise ValueError("noncomparable package count")
    rows=[]
    for metric,index in (("private_bytes",0),("heap_busy_bytes",1),
                         ("heap_busy_blocks",2),("handles",3)):
        per64=[]
        for a,b in zip(range(0,512,64),range(64,513,64)):
            change=(getter[b][index]-getter[a][index]-
                    control[b][index]+control[a][index])
            per64.append(change)
        by128=[per64[i]+per64[i+1] for i in (0,2,4,6)]
        print(f"C545D_PATH_512_NET,{metric},per128="
              f"{';'.join(map(str,by128))},last128={by128[-1]},"
              f"total512={sum(by128)}")
        rows.append((metric,*by128,sum(by128)))
    with (ROOT/"path_512_control_subtracted.csv").open(
            "w",newline="",encoding="utf-8") as f:
        w=csv.writer(f)
        w.writerow(("metric","net_0_128","net_128_256",
                    "net_256_384","net_384_512","net_0_512"))
        w.writerows(rows)
    print("C545D_PATH_512_DIAGNOSTIC_PASS; NO_GLIB; WINDOWS_2022; "
          "NO_PRODUCTION_CHANGES; NO_UNBOUNDED_LEAK_CONCLUSION")

if __name__=="__main__":
    try:main()
    except (ValueError,OSError) as exc:
        print(f"C545D_PATH_512_INVALID:{exc}",file=sys.stderr)
        sys.exit(2)
