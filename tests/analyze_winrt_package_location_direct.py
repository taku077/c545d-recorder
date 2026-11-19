#!/usr/bin/env python3
"""Compare 128 rounds of WinRT InstalledLocation.Path() vs ID-only and DisplayName.

This is NOT a leak verdict, only control-subtracted same-run growth. OS can
retain cache allocations. No package identities/paths are ever serialized.
"""
import csv
from pathlib import Path
import sys

ROOT=Path("artifacts")
MODES=("id_only","display","location")

def parse(mode):
    text=(ROOT/f"winrt_{mode}_128.log").read_text(encoding="utf-8")
    points={}
    marker=f"C545D_PATH_DIRECT_DONE,{mode},cycles=128,"
    if text.count(marker)!=1:
        raise ValueError(f"{mode}: completion not found")
    for line in text.splitlines():
        v=line.strip().split(",")
        if not v or v[0]!="C545D_PATH_DIRECT":
            continue
        if len(v)!=10 or v[1]!=mode:
            raise ValueError(f"{mode}: wrong row")
        k=int(v[2])
        if k in points: raise ValueError("duplicate checkpoint")
        points[k]=list(map(int,v[3:]))
    if set(points)!={0,32,64,96,128}:
        raise ValueError(f"{mode}: missing checkpoints")
    if any(p[6] != 0 for p in points.values()):
        raise ValueError(f"{mode}: incomplete HeapWalk")
    if min(p[4] for p in points.values())<5:
        raise ValueError(f"{mode}: insufficient packages")
    return points

def main():
    points={m:parse(m) for m in MODES}
    if max(points[m][128][4] for m in MODES)-min(points[m][128][4] for m in MODES)>2:
        raise ValueError("incomparable package enumeration counts")
    names=("private_usage_bytes","heap_busy_bytes","heap_busy_blocks","handles")
    rows=[]
    for metric,col in zip(names,range(4)):
        baseline=points["id_only"][128][col]-points["id_only"][0][col]
        for mode in ("display","location"):
            intervals=[points[mode][b][col]-points[mode][a][col] -
                       (points["id_only"][b][col]-points["id_only"][a][col])
                       for a,b in ((0,32),(32,64),(64,96),(96,128))]
            difference=sum(intervals)
            rows.append((mode,metric,*intervals,difference))
            print(f"C545D_PATH_GETTER_COMPARISON,{mode},{metric},"
                  f"id_only_growth={baseline},getter_minus_control={difference},"
                  f"intervals={';'.join(map(str,intervals))}")
    with (ROOT/"winrt_location_direct_comparison.csv").open(
            "w",newline="",encoding="utf-8") as stream:
        writer=csv.writer(stream)
        writer.writerow(("getter","metric","net_0_32","net_32_64",
                         "net_64_96","net_96_128","net_0_128"))
        writer.writerows(rows)
    print("C545D_PATH_GETTER_DIAGNOSTIC_PASS;"
          " NO_GLIB; WINDOWS_2022_ONLY; NOT_FINAL_LEAK_PROOF")

if __name__=="__main__":
    try: main()
    except (OSError,ValueError) as ex:
        print(f"C545D_PATH_GETTER_DIAGNOSTIC_INVALID:{ex}",file=sys.stderr)
        sys.exit(2)
