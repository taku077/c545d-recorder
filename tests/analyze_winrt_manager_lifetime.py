#!/usr/bin/env python3
"""Four isolated WinRT runs: persistent vs per-scan PackageManager lifetime.
Subtract mode-matched ID-only control from original DisplayName workload.
This is not a claim that process creation itself has no OS caches.
"""
import csv
from pathlib import Path
import sys

MODES=("persistent_id","persistent_display","scoped_id","scoped_display")
ART=Path("artifacts")

def load(mode):
    path=ART/f"{mode}_128.log"
    text=path.read_text(encoding="utf-8")
    if text.count(f"C545D_MANAGER_LIFETIME_DONE,{mode},cycles=128,") != 1:
        raise ValueError(f"{mode}: missing completion marker")
    points={}
    for line in text.splitlines():
        v=line.strip().split(",")
        if not v or v[0]!="C545D_MANAGER_LIFETIME": continue
        if len(v)!=10 or v[1]!=mode: raise ValueError("bad sample row")
        k=int(v[2])
        if k in points: raise ValueError("duplicate sample")
        points[k]=list(map(int,v[3:]))
    if set(points)!={0,32,64,96,128}: raise ValueError("incomplete checkpoints")
    if any(p[6]!=0 for p in points.values()): raise ValueError("HeapWalk failed")
    if min(p[4] for p in points.values())<5: raise ValueError("no packages")
    return points

def main():
    data={m:load(m) for m in MODES}
    counts=[data[m][128][4] for m in MODES]
    if max(counts)-min(counts)>2:raise ValueError("incomparable package counts")
    names=("private_bytes","heap_busy_bytes","heap_busy_blocks","handles")
    rows=[]
    for owner in ("persistent","scoped"):
        ctrl=data[f"{owner}_id"]
        active=data[f"{owner}_display"]
        for col,name in enumerate(names):
            intervals=[]
            for a,b in ((0,32),(32,64),(64,96),(96,128)):
                diff=active[b][col]-active[a][col] - (ctrl[b][col]-ctrl[a][col])
                intervals.append(diff)
            net=sum(intervals)
            rows.append((owner,name,*intervals,net))
            print(f"C545D_MANAGER_EFFECT,{owner},{name},"
                  f"intervals={';'.join(map(str,intervals))},net128={net}")
    with (ART/"manager_lifetime_comparison.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f)
        w.writerow(("package_manager_lifetime","metric","net_0_32",
                    "net_32_64","net_64_96","net_96_128","net_0_128"))
        w.writerows(rows)
    print("C545D_MANAGER_LIFETIME_AB_PASS; NOT_DEMONSTRATED_LEAK_FREE; "
          "WINDOWS_2022_ONLY; NO_GLIB; NO_HOST_CHANGES")

if __name__=="__main__":
    try:main()
    except (OSError,ValueError) as exc:
        print(f"C545D_MANAGER_LIFETIME_INVALID:{exc}",file=sys.stderr)
        sys.exit(2)
