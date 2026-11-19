#!/usr/bin/env python3
"""Analyze a *single* Windows CI run's 256-cycle residual-memory series.

The metric is slope and stabilization, NOT a blanket leak/plateau certificate.
PrivateUsage (committed private bytes), HeapWalk BUSY bytes and VirtualQuery
region counts are distinct observables. No raw memory, PIDs or paths are
exported; only aggregate counts from disposable camera-free CI.
"""
import argparse
import csv
import sys
from pathlib import Path

CHECKPOINTS = (0, 64, 128, 192, 256)
KIND = {"GIO_PROBE": (6, 5), "GIO_HEAP": (7, 4), "GIO_VM": (9, 3)}


def read_series(filename):
    text = Path(filename).read_text(encoding="utf-8")
    data = {tag: {} for tag in KIND}
    completion = []
    count_cycles = 0
    for line in text.splitlines():
        cells = line.strip().split(",")
        tag = cells[0]
        if tag == "GIO_PROBE_DONE":
            completion.append(line)
        if tag == "GIO_PROBE" and len(cells) >= 3 and cells[1] == "cycle":
            count_cycles += 1
        if tag not in data:
            continue
        field_count, metric_index = KIND[tag]
        if len(cells) != field_count:
            raise ValueError(f"Malformed {tag} in {filename}")
        phase = cells[1]
        if phase not in ("baseline", "cycle", "settled_cleanup"):
            continue
        if not cells[2].isdecimal():
            raise ValueError(f"Noninteger cycle in {filename}")
        cycle = int(cells[2])
        if phase == "baseline":
            if cycle != 0:
                raise ValueError("invalid baseline index")
        elif phase == "settled_cleanup":
            if cycle != 258:
                raise ValueError("invalid settled index")
        elif cycle not in CHECKPOINTS:
            continue
        marker = "settled" if phase == "settled_cleanup" else cycle
        if marker in data[tag]:
            raise ValueError(f"duplicate {tag} {marker}")
        if any(not v.isdecimal() for v in cells[3:]):
            raise ValueError(f"nonnumeric {tag} counters")
        values = tuple(map(int, cells[3:]))
        data[tag][marker] = values

    if len(completion) != 1 or "GIO_PROBE_DONE,cycles=256" not in completion[0]:
        raise ValueError("256-cycle run completion marker missing")
    if count_cycles != 256:
        raise ValueError(f"Expected 256 cycle reports, got {count_cycles}")
    for tag, points in data.items():
        for t in (*CHECKPOINTS, "settled"):
            if t not in points:
                raise ValueError(f"Missing {tag} checkpoint {t}")
        if tag == "GIO_HEAP" and any(v[-1] != 0 for v in points.values()):
            raise ValueError("HeapWalk snapshot failed")
        if tag == "GIO_VM" and any(v[-1] != 0 for v in points.values()):
            raise ValueError("VirtualQuery snapshot failed")
    return data


def summarize(label, data):
    # Raw row cell positions after splitting:
    # PROBE: phase,cycle,notifications,handles,private
    # HEAP: phase,cycle,busy_blocks,busy_bytes,heap_count,bad
    # VM: phase,cycle,committed_private,mapped,image,regions,errors
    probe = {t: r[2] for t, r in data["GIO_PROBE"].items()}
    heap = {t: r[1] for t, r in data["GIO_HEAP"].items()}
    vm = {t: r[0] for t, r in data["GIO_VM"].items()}
    results = {}
    for kind, series in (("private_usage", probe), ("heap_busy", heap),
                         ("vm_private_commit", vm)):
        windows = tuple(series[b] - series[a] for a, b in zip(CHECKPOINTS, CHECKPOINTS[1:]))
        last_half = series[256] - series[128]
        first_half = series[128] - series[0]
        results[kind] = {
            "by_64": windows,
            "first_half": first_half,
            "last_half": last_half,
            "settled_delta": series["settled"] - series[0],
            "last_value": series[256],
        }
        print(f"MEMORY_SLOPE,{label},{kind},"
              f"{windows[0]},{windows[1]},{windows[2]},{windows[3]},"
              f"first_half={first_half},last_half={last_half},"
              f"settled_delta={series['settled']-series[0]}")
    return results


def assess(control, changed):
    if control is None:
        return "INCONCLUSIVE_NO_CONTROL"
    a = changed["private_usage"]["last_half"]
    b = control["private_usage"]["last_half"]
    heap_a = changed["heap_busy"]["last_half"]
    heap_b = control["heap_busy"]["last_half"]
    net = a - b
    heap_net = heap_a - heap_b
    if net > 1024 * 1024 or heap_net > 512 * 1024:
        status = "PERSISTENT_GROWTH_INDICATED"
    elif abs(net) <= 256 * 1024 and abs(heap_net) <= 256 * 1024:
        status = "SHORT_WINDOW_PLATEAU_CANDIDATE"
    else:
        status = "INCONCLUSIVE_RESIDUAL_SLOPE"
    print(f"NET_LAST_128_PRIVATE_BYTES={net}")
    print(f"NET_LAST_128_HEAP_BUSY_BYTES={heap_net}")
    print(f"RESIDUAL_CLASSIFICATION={status}")
    print("NOTICE=CAMERA_FREE_WINDOWS_CI_ONLY; NOT_PRODUCTION_PROOF")
    return status


def selftest():
    from tempfile import TemporaryDirectory
    from pathlib import Path

    def make_test(path, growth):
        rows = []
        for index in range(257):
            phase = "baseline" if index == 0 else "cycle"
            if index in CHECKPOINTS or index > 0:
                rows.append(f"GIO_PROBE,{phase},{index},0,680,{5_000_000 + (index//64)*growth}")
            if index in CHECKPOINTS:
                rows.append(f"GIO_HEAP,{phase},{index},1,{1_000_000+(index//64)*growth//2},4,0")
                rows.append(f"GIO_VM,{phase},{index},{6_000_000+(index//64)*growth},30000,40000,70,0")
        rows.extend((
            f"GIO_PROBE,settled_cleanup,258,0,680,{5_000_000+4*growth}",
            f"GIO_HEAP,settled_cleanup,258,1,{1_000_000+2*growth},4,0",
            f"GIO_VM,settled_cleanup,258,{6_000_000+4*growth},30000,40000,70,0",
            "GIO_PROBE_DONE,cycles=256,notifications=0,reg_changes=1",
        ))
        path.write_text("\n".join(rows), encoding="utf-8")

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        control_path, growth_path = root/"control.log", root/"growth.log"
        make_test(control_path, 0)
        make_test(growth_path, 900_000)
        ctrl = summarize("selftest_control", read_series(control_path))
        load = summarize("selftest_growth", read_series(growth_path))
        assert assess(ctrl, load) == "PERSISTENT_GROWTH_INDICATED"
        corrupted = growth_path.read_text().replace("GIO_VM,cycle,128,", "GIO_VM,cycle,128,notanumber")
        growth_path.write_text(corrupted, encoding="utf-8")
        try:
            read_series(growth_path)
        except ValueError:
            pass
        else:
            raise AssertionError("corrupt VirtualQuery record accepted")
    print("C545D_RESIDUAL_GROWTH_ANALYZER_SELFTEST_PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--output", default="artifacts/residual_slope.csv")
    parser.add_argument("logs", nargs="*")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if len(args.logs) != 2:
        parser.error("expected control 256 log, then modified-registry 256 log")
    output = []
    modes = []
    for file in args.logs:
        name = Path(file).stem
        parsed = read_series(file)
        series = summarize(name, parsed)
        modes.append(series)
        for metric, values in series.items():
            output.append((name, metric, *values["by_64"], values["first_half"],
                           values["last_half"], values["settled_delta"]))
    status = assess(modes[0], modes[1])
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(("mode", "metric", "delta_0_64", "delta_64_128",
                    "delta_128_192", "delta_192_256",
                    "delta_first_128", "delta_last_128", "settled_delta"))
        w.writerows(output)
    Path(str(out) + ".status.txt").write_text(status + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, AssertionError) as ex:
        print(f"C545D_RESIDUAL_ANALYSIS_INVALID:{ex}", file=sys.stderr)
        sys.exit(2)
