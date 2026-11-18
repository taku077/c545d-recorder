#!/usr/bin/env python3
"""CI gate: compare same-run native GLib 2.82.4 baseline and weakref candidate."""
from pathlib import Path
import csv
import sys

def read(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    points = {}
    done = False
    for row in rows:
        if not row:
            continue
        if row[0] == "GIO_PROBE" and len(row) == 6:
            name = row[1]
            if name in {"baseline", "after_cleanup"}:
                points[name] = (int(row[4]), int(row[5]))
        if row[0] == "GIO_PROBE_DONE" and "cycles=16" in row:
            done = True
    if not done or not all(k in points for k in ("baseline", "after_cleanup")):
        raise RuntimeError(f"Missing completed 16-cycle measurements: {path}")
    start = points["baseline"]
    end = points["after_cleanup"]
    return {"handle_start":start[0], "handle_end":end[0],
            "handle_delta":end[0]-start[0], "private_start":start[1],
            "private_end":end[1], "private_delta":end[1]-start[1]}

def main():
    old, new = [read(f) for f in sys.argv[1:3]]
    for label, data in (("UPSTREAM", old), ("WEAKREF", new)):
        for k, v in data.items():
            print(f"{label}_{k.upper()}={v}")
    if old["handle_delta"] < 100:
        print("RESULT=INCONCLUSIVE: pristine 2.82.4 did not reproduce Key-handle trend")
        return 2
    threshold = max(16, old["handle_delta"] // 20)
    handles_ok = new["handle_delta"] <= threshold
    memory_ok = new["private_delta"] <= max(1024 * 1024,
                                            old["private_delta"] // 5)
    print(f"HANDLE_DELTA_THRESHOLD={threshold}")
    print("HANDLE_GATE=" + ("PASS" if handles_ok else "FAIL"))
    print("PRIVATE_GATE=" + ("PASS" if memory_ok else "FAIL"))
    if handles_ok and memory_ok:
        print("RESULT=PASS_ISOLATED_SHORT_AB_ONLY")
        return 0
    print("RESULT=FAIL_PATCH_NOT_STABLE")
    return 1

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: evaluate_ab.py baseline.csv patched.csv")
    raise SystemExit(main())
