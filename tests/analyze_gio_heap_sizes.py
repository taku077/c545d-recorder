#!/usr/bin/env python3
"""Identify retained heap *size classes* without exporting allocation addresses.

Uses sparse HeapWalk GIO_HEAPSIZE summaries from disposable Windows CI.
Size 2048 is a combined bin of all blocks >=2048 bytes (not exact size).
Results compare registry mutation with no-change control in the same runner.
"""
import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

POINTS = (0, 64, 128, 192, 256, "settled")


def load(path):
    bins = defaultdict(dict)
    expected = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        fields = line.strip().split(",")
        if fields[0] not in ("GIO_HEAP", "GIO_HEAPSIZE"):
            continue
        if fields[1] not in ("baseline", "cycle", "settled_cleanup"):
            continue
        if not fields[2].isdecimal():
            raise ValueError("invalid snapshot index")
        c = int(fields[2])
        t = "settled" if fields[1] == "settled_cleanup" else c
        if t not in POINTS:
            continue
        if fields[0] == "GIO_HEAP":
            if len(fields) != 7 or any(not v.isdecimal() for v in fields[3:]):
                raise ValueError("malformed GIO_HEAP summary")
            if t in expected:
                raise ValueError("duplicate heap summary")
            expected[t] = int(fields[3])
            if int(fields[6]) != 0:
                raise ValueError("incomplete HeapWalk")
        else:
            if len(fields) != 5 or not fields[3].isdecimal() or not fields[4].isdecimal():
                raise ValueError("invalid heap size record")
            size, count = int(fields[3]), int(fields[4])
            if size > 2048 or size in bins[t] or count < 1:
                raise ValueError("out-of-range/duplicate heap size")
            bins[t][size] = count
    for point in POINTS:
        if point not in expected or not bins[point]:
            raise ValueError("missing heap size checkpoint " + str(point))
        total = sum(bins[point].values())
        if total != expected[point]:
            raise ValueError(f"heap size subtotal mismatch at {point}: {total}!={expected[point]}")
    return bins, expected


def compare(control, mutated):
    c, cs = control
    m, ms = mutated
    keys = sorted(set().union(*(set(v) for v in c.values()), *(set(v) for v in m.values())))
    results = []
    for size in keys:
        growth_mut = m[256].get(size, 0) - m[0].get(size, 0)
        growth_control = c[256].get(size, 0) - c[0].get(size, 0)
        net = growth_mut - growth_control
        settled_net = ((m["settled"].get(size, 0)-m[0].get(size, 0)) -
                       (c["settled"].get(size, 0)-c[0].get(size, 0)))
        results.append((size, net, settled_net, growth_mut, growth_control))
    print(f"HEAP_SIZE_BLOCKS: control={cs[256]-cs[0]:+d}, "
          f"registry={ms[256]-ms[0]:+d}, net={(ms[256]-ms[0])-(cs[256]-cs[0]):+d}")
    for size, net, settled_net, mutated_delta, control_delta in sorted(
            results, key=lambda r: r[1], reverse=True)[:20]:
        print(f"HEAP_SIZE_GROWTH,bytes={size}{'+' if size==2048 else ''},"
              f"net_blocks={net:+d},net_settled={settled_net:+d},"
              f"registry={mutated_delta:+d},control={control_delta:+d}")
    return results


def selftest():
    from tempfile import TemporaryDirectory
    def write_sample(path, b, a):
        out = []
        for point in POINTS:
            name = "baseline" if point == 0 else "settled_cleanup" if point == "settled" else "cycle"
            cycle = 258 if point == "settled" else point
            values = b if point == 0 else a
            out.append(f"GIO_HEAP,{name},{cycle},{sum(values.values())},1234,4,0")
            out.extend(f"GIO_HEAPSIZE,{name},{cycle},{size},{n}"
                       for size, n in values.items())
        path.write_text("\n".join(out), encoding="utf-8")
    with TemporaryDirectory() as tmp:
        cp, mp = Path(tmp)/"c.log", Path(tmp)/"m.log"
        write_sample(cp, {64: 3, 80: 10}, {64: 3, 80: 10})
        write_sample(mp, {64: 3, 80: 10}, {64: 15, 80: 10})
        assert compare(load(cp), load(mp))[0][1] == 12
        cp.write_text(cp.read_text().replace("GIO_HEAPSIZE,cycle,64,64,3",
                                             "GIO_HEAPSIZE,cycle,64,64,2"), encoding="utf-8")
        try:
            load(cp)
        except ValueError:
            pass
        else:
            raise AssertionError("failed to reject incomplete heap histogram")
    print("C545D_HEAP_SIZE_ANALYZER_SELFTEST_PASS")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--output", default="artifacts/heap_size_deltas.csv")
    p.add_argument("logs", nargs="*")
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    if len(a.logs) != 2:
        p.error("control and registry-change 256-cycle logs are required")
    changes = compare(load(a.logs[0]), load(a.logs[1]))
    path = Path(a.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(("size_bytes_or_overflow", "net_growth_256_blocks",
                    "net_settled_growth_blocks", "registry_delta", "control_delta"))
        w.writerows(changes)
    print("HEAP_SIZE_PROFILING_PASS; DIAGNOSTIC_ONLY; NO_USER_DATA")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, AssertionError) as e:
        print(f"C545D_HEAP_SIZE_ERROR:{e}", file=sys.stderr)
        sys.exit(2)
