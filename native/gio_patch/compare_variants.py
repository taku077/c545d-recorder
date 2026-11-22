#!/usr/bin/env python3
"""C545D: compare weakref-only and weakref+LocalizedString cleanup, numerically."""
import csv,sys
def read(path):
    d={}
    with open(path,encoding="utf-8-sig",newline="") as f:
        for row in csv.reader(f):
            if row and row[0]=="GIO_PROBE" and len(row)==6 and row[1] in ("baseline","after_cleanup"):
                d[row[1]]=(int(row[4]),int(row[5]))
    assert len(d)==2, "Missing start/end readings"
    b,e=d["baseline"],d["after_cleanup"]
    return {"handles":e[0]-b[0],"private_bytes":e[1]-b[1]}
a,b=map(read,sys.argv[1:3])
for label,d in (("WEAKREF_ONLY",a),("WITH_FRIENDLY_CLEANUP",b)):
    print(f"{label}_HANDLE_DELTA={d['handles']}")
    print(f"{label}_PRIVATE_DELTA={d['private_bytes']}")
print(f"FRIENDLY_CLEANUP_PRIVATE_SAVINGS={a['private_bytes']-b['private_bytes']}")
print("NOTE=One controlled short-run comparison; only use as isolated regression evidence.")
