#!/usr/bin/env python3
"""CI-only Handle64 type-delta analyzer. No handle names or registry paths.

The four snapshots distinguish steady 64-cycle registry churn from deleting
the probe's disposable registry value at cleanup. Independent verification:
each type subtotal equals the Handle64 summary total and the Key type count
equals the number logged separately by the probe.
"""
import argparse
import csv
import re
import sys
from pathlib import Path

MARKS = ("baseline", "before_cleanup", "after_cleanup", "settled_cleanup")
TYPE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 ]{0,63}$")


def parse(text: str):
    snapshots = {name: {} for name in MARKS}
    totals = {}
    keys = {}
    natives = {}
    for line in text.splitlines():
        cells = line.strip().split(",")
        if not cells:
            continue
        if cells[0] == "GIO_H64TYPE":
            if len(cells) != 5:
                raise ValueError("malformed GIO_H64TYPE")
            _, mark, cycle, kind, count = cells
            if mark not in snapshots or not TYPE_RE.fullmatch(kind):
                raise ValueError("unknown mark or unsanitized type name")
            if not cycle.isdecimal() or not count.isdecimal():
                raise ValueError("invalid type counter")
            if kind in snapshots[mark]:
                raise ValueError("duplicate type counter")
            snapshots[mark][kind] = int(count)
        elif cells[0] == "GIO_H64TOTAL":
            if len(cells) != 5:
                raise ValueError("malformed GIO_H64TOTAL")
            _, mark, cycle, total, subtotal = cells
            if mark not in snapshots or mark in totals:
                raise ValueError("unknown or duplicate total")
            if not cycle.isdecimal() or not total.isdecimal() or not subtotal.isdecimal():
                raise ValueError("invalid Handle64 total")
            totals[mark] = int(total), int(subtotal)
        elif cells[0] == "GIO_H64NATIVE":
            if len(cells) != 5:
                raise ValueError("malformed GIO_H64NATIVE")
            _, mark, cycle, n_before, n_after = cells
            if mark not in snapshots or mark in natives:
                raise ValueError("unknown or duplicate native census")
            if not cycle.isdecimal() or not n_before.isdecimal() or not n_after.isdecimal():
                raise ValueError("invalid native count")
            natives[mark] = int(n_before), int(n_after)
        elif cells[0] == "GIO_KEY":
            if len(cells) != 4:
                raise ValueError("malformed GIO_KEY")
            _, mark, cycle, count = cells
            if mark not in snapshots or mark in keys:
                raise ValueError("unknown or duplicate Key summary")
            if not cycle.isdecimal() or not count.isdecimal():
                raise ValueError("invalid Key count")
            keys[mark] = int(count)
    for mark in MARKS:
        typed = snapshots[mark]
        if not typed or mark not in totals or mark not in keys or mark not in natives:
            raise ValueError("missing full Handle64 snapshot: " + mark)
        total, subtotal = totals[mark]
        if sum(typed.values()) != total or subtotal != total:
            raise ValueError("Handle64 type sum mismatch: " + mark)
        if typed.get("Key") != keys[mark]:
            raise ValueError("Key counter inconsistent: " + mark)
        # Handle64 can take seconds; native-before/after bracket its execution.
        # A moving cleanup graph may be transient, but steady and settled
        # checkpoints must agree within a small process-spawn tolerance.
        native_lo, native_hi = sorted(natives[mark])
        if not native_lo - 12 <= total <= native_hi + 12:
            if mark != "after_cleanup":
                raise ValueError("Handle64 versus native total mismatch: " + mark)
            print("TRANSIENT_CENSUS_MISMATCH: after_cleanup was not quiescent")
    return snapshots, totals, natives


def analyze(label, text, threshold=4):
    snapshots, totals, natives = parse(text)
    keys = sorted(set().union(*(set(x) for x in snapshots.values())))
    results = []
    problems = []
    for kind in keys:
        before, steady, after, settled = (snapshots[t].get(kind, 0) for t in MARKS)
        during, cleanup, settled_delta = steady - before, after - before, settled - before
        results.append((label, kind, before, steady, after, settled,
                        during, cleanup, settled_delta))
        if during > threshold or cleanup > threshold or settled_delta > threshold:
            problems.append((kind, during, cleanup, settled_delta))
    print(f"{label}: H64 total baseline={totals['baseline'][0]}, "
          f"before_cleanup={totals['before_cleanup'][0]}, "
          f"after_cleanup={totals['after_cleanup'][0]}, "
          f"settled={totals['settled_cleanup'][0]}")
    print(f"{label}: Key baseline={snapshots['baseline'].get('Key', 0)}, "
          f"before_cleanup={snapshots['before_cleanup'].get('Key', 0)}, "
          f"after_cleanup={snapshots['after_cleanup'].get('Key', 0)}, "
          f"settled={snapshots['settled_cleanup'].get('Key', 0)}")
    for row in sorted(results,
                      key=lambda r: max(abs(r[-3]), abs(r[-2]), abs(r[-1])),
                      reverse=True)[:12]:
        print(f"TYPE_DELTA mode={label} type={row[1]} "
              f"during={row[-3]:+d} after_cleanup={row[-2]:+d} "
              f"settled={row[-1]:+d}")
    return results, problems


def selftest():
    def generate(b, s, a, q):
        lines = []
        for mark, data in zip(MARKS, (b, s, a, q)):
            for name, value in data.items():
                lines.append(f"GIO_H64TYPE,{mark},0,{name},{value}")
            total = sum(data.values())
            lines.append(f"GIO_H64TOTAL,{mark},0,{total},{total}")
            lines.append(f"GIO_H64NATIVE,{mark},0,{total},{total}")
            lines.append(f"GIO_KEY,{mark},0,{data['Key']}")
        return "\n".join(lines)
    stable = generate({"Key": 435, "Event": 240},
                      {"Key": 436, "Event": 241},
                      {"Key": 434, "Event": 242},
                      {"Key": 434, "Event": 242})
    assert analyze("selftest-stable", stable)[1] == []
    masked = generate({"Key": 435, "Event": 240},
                      {"Key": 435, "Event": 240},
                      {"Key": 208, "Event": 467},
                      {"Key": 208, "Event": 467})
    problem = analyze("selftest-masked", masked)[1]
    assert problem and problem[0][0] == "Event"
    try:
        parse(stable.replace("GIO_KEY,baseline,0,435", "GIO_KEY,baseline,0,434"))
    except ValueError:
        pass
    else:
        raise AssertionError("inconsistent Key count was not rejected")
    print("C545D_HANDLE_TYPE_ANALYZER_SELFTEST_PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--output", default="artifacts/handle_type_deltas.csv")
    parser.add_argument("logs", nargs="*")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return 0
    if not args.logs:
        parser.error("pass at least one 64-cycle probe log")
    results = []
    unexpected = []
    for path in args.logs:
        label = Path(path).stem
        found, problems = analyze(label, Path(path).read_text(encoding="utf-8"))
        results.extend(found)
        unexpected.extend((label, *x) for x in problems)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(("mode", "type", "baseline", "before_cleanup",
                    "after_cleanup", "settled_cleanup", "delta_during",
                    "delta_after_cleanup", "delta_settled"))
        w.writerows(results)
    if unexpected:
        for label, kind, during, cleanup, settled in unexpected:
            print(f"UNEXPLAINED_POSITIVE_TYPE_GROWTH: {label} {kind} "
                  f"during={during:+d} after_cleanup={cleanup:+d} "
                  f"settled={settled:+d}", file=sys.stderr)
        return 2
    print("C545D_HANDLE_TYPE_GATE_PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as exc:
        print(f"C545D_HANDLE_TYPE_DATA_INVALID: {exc}", file=sys.stderr)
        sys.exit(3)
