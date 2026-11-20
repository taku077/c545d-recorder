#!/usr/bin/env python3
"""Analyze isolated AppInfo stage ablations against same-stage no-change control.

All inputs are aggregate GIO_PROBE/GIO_HEAP/GIO_VM lines from CI synthetic
HKCU test; no raw registry names, handles or memory addresses.
"""
import argparse
import csv
from pathlib import Path

STAGES = ("default", "skip_uwp", "skip_uwp_enum", "skip_uwp_handlers")
EVENTS = ("baseline", "settled_cleanup")


def parse(path):
    data = {}
    completed = 0
    cycles = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        cells = line.split(",")
        if cells[0] == "GIO_PROBE_DONE":
            if "cycles=64" in line:
                completed += 1
        if cells[0] == "GIO_PROBE" and cells[1] == "cycle":
            cycles += 1
        if cells[0] not in ("GIO_PROBE", "GIO_HEAP", "GIO_VM"):
            continue
        if len(cells) != {"GIO_PROBE": 6, "GIO_HEAP": 7, "GIO_VM": 8}[cells[0]]:
            raise ValueError(f"{path}: malformed {cells[0]} record")
        if cells[1] not in EVENTS:
            continue
        key = cells[0], cells[1]
        if key in data or any(not v.isdecimal() for v in cells[2:]):
            raise ValueError(f"{path}: bad/duplicated checkpoint {key}")
        data[key] = [int(c) for c in cells[2:]]
    if completed != 1 or cycles != 64:
        raise ValueError(f"{path}: incomplete synthetic workload")
    if len(data) != 6:
        raise ValueError(f"{path}: missing checkpoints: {len(data)}")
    for phase in EVENTS:
        if data[("GIO_HEAP", phase)][-1] or data[("GIO_VM", phase)][-1]:
            raise ValueError(f"{path}: failed HeapWalk or VirtualQuery")
    before = {tag: data[(tag, "baseline")] for tag in ("GIO_PROBE", "GIO_HEAP", "GIO_VM")}
    after = {tag: data[(tag, "settled_cleanup")] for tag in before}
    # Values are [cycle,changed_count,handles,private]; [cycle,blocks,bytes,heaps,bad];
    # [cycle,private,mapped,image,regions,bad].
    return {
        "private": after["GIO_PROBE"][3] - before["GIO_PROBE"][3],
        "heap_blocks": after["GIO_HEAP"][1] - before["GIO_HEAP"][1],
        "heap_busy": after["GIO_HEAP"][2] - before["GIO_HEAP"][2],
        "vm_private": after["GIO_VM"][1] - before["GIO_VM"][1],
        "handles": after["GIO_PROBE"][2] - before["GIO_PROBE"][2],
    }


def analyze(root):
    metrics = ("private", "heap_busy", "heap_blocks", "vm_private", "handles")
    out = []
    for stage in STAGES:
        control = parse(root / f"{stage}_nochange_64.log")
        active = parse(root / f"{stage}_registry_64.log")
        net = {metric: active[metric] - control[metric] for metric in metrics}
        out.append((stage, control, active, net))
        print("STAGE_ISOLATION," + stage + "," +
              ",".join(f"{metric}={net[metric]:+d}" for metric in metrics))
    baseline = out[0][3]
    print("STAGE_ISOLATION_NOTE=All stage skips are DIAGNOSTIC ONLY; "
          "functionality differs; neither ABI nor recorder suitability is established.")
    for stage, control, active, net in out[1:]:
        print(f"STAGE_DIFFERENCE,{stage},private_vs_default="
              f"{net['private']-baseline['private']:+d},"
              f"heap_busy_vs_default={net['heap_busy']-baseline['heap_busy']:+d},"
              f"heap_blocks_vs_default={net['heap_blocks']-baseline['heap_blocks']:+d}")
    return out, metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="artifacts")
    ap.add_argument("--output", default="artifacts/stage_isolation.csv")
    args = ap.parse_args()
    records, metrics = analyze(Path(args.dir))
    path = Path(args.output)
    with path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(("stage", "activity", *metrics))
        for stage, control, active, net in records:
            for activity, values in (("nochange", control), ("registry", active), ("net", net)):
                writer.writerow([stage, activity] + [values[k] for k in metrics])
    print("C545D_STAGE_ISOLATION_ANALYSIS_PASS")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        raise SystemExit(f"C545D_STAGE_ISOLATION_INVALID: {exc}")
