#!/usr/bin/env python3
"""Read-only comparison of experimental UWP package-enumeration isolation."""
import csv
import sys
def read(path):
    d={}
    with open(path,encoding="utf-8-sig",newline="") as f:
        for row in csv.reader(f):
            if len(row)==6 and row[0]=="GIO_PROBE" and row[1] in ("baseline","after_cleanup"):
                d[row[1]]=(int(row[4]),int(row[5]))
    if len(d)!=2: raise ValueError("Incomplete 16-cycle A/B measurement: "+path)
    start,end=d["baseline"],d["after_cleanup"]
    return end[0]-start[0],end[1]-start[1]
if __name__=="__main__":
    normal,skip=map(read,sys.argv[1:3])
    for label,(h,b) in (("PATCHED",normal),("PATCHED_UWP_SKIPPED",skip)):
        print(f"{label}_HANDLE_DELTA={h}")
        print(f"{label}_PRIVATE_DELTA={b}")
    improvement=normal[1]-skip[1]
    print(f"DELTA_EXPLAINED_BY_UWP_CONDITION={improvement}")
    if normal[1]>0: print(f"APPROX_FRACTION={improvement/normal[1]:.4f}")
    print("NOTE=Diagnostic only; UWP disabled is not a shippable runtime fix.")
