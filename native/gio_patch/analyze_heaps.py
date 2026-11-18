#!/usr/bin/env python3
"""Compare Win32 HeapSummary allocated vs committed bytes on synthetic runner."""
import csv,sys

def read(path):
    phases={}
    with open(path,encoding="utf-8-sig",newline="") as f:
        for row in csv.reader(f):
            if len(row)==7 and row[0]=="GIO_HEAPS" and row[1] in ("baseline","after_cleanup"):
                phases[row[1]]=tuple(int(x) for x in row[3:7])
    if not all(k in phases for k in ("baseline","after_cleanup")):
        return None
    b,a=phases["baseline"],phases["after_cleanup"]
    return {
        "allocated_delta":a[0]-b[0],
        "committed_delta":a[1]-b[1],
        "baseline_success":b[2],
        "final_success":a[2],
        "baseline_failed":b[3],
        "final_failed":a[3],
    }

for label,path in zip(("PATCHED","PATCHED_UWP_SKIPPED"),sys.argv[1:]):
    d=read(path)
    if d is None:
        print(f"{label}_HEAP_STATUS=UNAVAILABLE")
        continue
    for key,val in d.items():
        print(f"{label}_{key.upper()}={val}")
    print(f"{label}_HEAP_STATUS="+("MEASURED" if d["baseline_success"] and d["final_success"] else "UNAVAILABLE"))
print("NOTE=HeapSummary reports process heaps; non-heap VirtualAlloc/COM reservations and allocator reuse still require interpretation.")
