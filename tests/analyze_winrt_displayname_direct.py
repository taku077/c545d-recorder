#!/usr/bin/env python3
"""Analyze direct WinRT Package.DisplayName 128-cycle vs ID-only control.
All outputs are numerical, no package names/paths or camera data.
"""
import csv
from pathlib import Path
import sys

def parse(path, mode):
    data={}
    lines=path.read_text(encoding="utf-8").splitlines()
    if sum(x.startswith(f"WINRT_DIRECT_DONE,{mode},cycles=128,") for x in lines) != 1:
        raise ValueError(f"{mode}: missing completion marker")
    for line in lines:
        parts=line.split(",")
        if not parts or parts[0] != "WINRT_DIRECT": continue
        if len(parts) != 10 or parts[1] != mode:
            raise ValueError(f"{mode}: malformed report")
        index=int(parts[2])
        if index in data: raise ValueError(f"duplicate {index}")
        data[index]=list(map(int,parts[3:]))
    if set(data) != {0,32,64,96,128}:
        raise ValueError(f"{mode}: missing checkpoints")
    if any(x[6] != 0 for x in data.values()):
        raise ValueError(f"{mode}: incomplete HeapWalk census")
    if min(x[4] for x in data.values()) < 5:
        raise ValueError(f"{mode}: insufficient packages")
    return data

def main():
    control=parse(Path("artifacts/winrt_control.txt"),"control")
    getter=parse(Path("artifacts/winrt_display.txt"),"display")
    if abs(control[128][4]-getter[128][4]) > 2:
        raise ValueError("Noncomparable package enumerations")
    rows=[]
    for index,metric in enumerate(("private_bytes","heap_busy_bytes","heap_blocks","handles")):
        baseline=control[128][index]-control[0][index]
        used=getter[128][index]-getter[0][index]
        differential=used-baseline
        print(f"WINRT_DIRECT_COMPARISON,{metric},control={baseline},display={used},delta={differential}")
        rows.append((metric,baseline,used,differential))
    with open("artifacts/winrt_direct_comparison.csv","w",newline="",encoding="utf-8") as file:
        writer=csv.writer(file)
        writer.writerow(("metric","control_128_growth","display_128_growth","difference"))
        writer.writerows(rows)
    print("WINRT_DIRECT_DIAGNOSTIC_COMPLETE; WINDOWS_2022_ONLY; NO_GLIB; NOT_OS_BUG_PROOF")

if __name__ == "__main__":
    try: main()
    except (ValueError,OSError) as ex:
        print(f"WINRT_DIRECT_INVALID:{ex}",file=sys.stderr)
        sys.exit(2)
