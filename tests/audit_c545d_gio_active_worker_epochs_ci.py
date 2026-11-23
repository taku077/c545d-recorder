#!/usr/bin/env python3
"""Guard 2 comparable completed AppInfo worker epochs (isolated Windows CI).

Consumes numeric-only QPC markers emitted by CI-instrumented GLib/GIO 2.82.4
and the disposable two-cycle probe. This is a *worker trace parity* guard, NOT
proof of global APC/WinRT quiescence, retained memory leak, or production state.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re

PHASES = ("worker_begin", "worker_scan_end", "worker_unlocked", "worker_after_notify")
CLOCK = re.compile(r"^C545D_CI_ACTIVE_EPOCH,(baseline|cycle),([0-2]),(\d+),(\d+),(\d+)$")
WORKER = re.compile(
    r"^C545D_CI_APPINFO_QPC,phase=(worker_begin|worker_scan_end|worker_unlocked|worker_after_notify),"
    r"ordinal=(\d+),qpc=(\d+)$"
)
class Gap(ValueError):
    pass

def verify(source: str, arm: str) -> dict[str, int]:
    if arm not in ("nochange", "registry"):
        raise Gap("invalid_arm")
    if len(source) > 1_000_000:
        raise Gap("oversized_probe_text")
    stamps: dict[tuple[str, int], int] = {}
    workers: dict[int, dict[str, int]] = {}
    for line in source.splitlines():
        if line.startswith("C545D_CI_ACTIVE_EPOCH,"):
            m = CLOCK.fullmatch(line)
            if m is None:
                raise Gap("malformed_phase_clock")
            key = (m.group(1), int(m.group(2)))
            if key in stamps:
                raise Gap("duplicate_phase_clock")
            stamps[key] = int(m.group(3))
        elif line.startswith("C545D_CI_APPINFO_QPC,"):
            # Other trace phases such as parser_begin and registry_callback are
            # outside this worker-lifetime attribution contract.
            m = WORKER.fullmatch(line)
            if m is None:
                if re.fullmatch(
                    r"C545D_CI_APPINFO_QPC,phase=(parser_begin|parser_end|registry_callback),"
                    r"ordinal=\d+,qpc=\d+", line
                ):
                    continue
                raise Gap("unrecognized_worker_trace")
            ordinal, phase, qpc = int(m.group(2)), m.group(1), int(m.group(3))
            if ordinal <= 0 or qpc <= 0:
                raise Gap("nonpositive_worker_ordinal_or_timestamp")
            by_phase = workers.setdefault(ordinal, {})
            if phase in by_phase:
                raise Gap("duplicate_worker_phase")
            by_phase[phase] = qpc
    keys = (("baseline", 0), ("cycle", 1), ("cycle", 2))
    if set(stamps) != set(keys):
        raise Gap("missing_or_extra_phase_clock")
    t0, t1, t2 = (stamps[k] for k in keys)
    if not (0 < t0 < t1 < t2):
        raise Gap("phase_clock_nonmonotonic")
    counts = [0, 0]
    for phases in workers.values():
        if set(phases) != set(PHASES):
            raise Gap("worker_incomplete")
        times = [phases[k] for k in PHASES]
        if times != sorted(times):
            raise Gap("worker_phase_order_invalid")
        before, after = times[0], times[-1]
        if after <= t0:
            continue  # Completed during initialization, before baseline.
        if before <= t0 < after:
            raise Gap("worker_crossed_initial_baseline")
        if t0 < before <= t1 and after <= t1:
            counts[0] += 1
        elif t1 < before <= t2 and after <= t2:
            counts[1] += 1
        elif before <= t2 and after > t2:
            raise Gap("worker_crossed_cycle_cutoff")
        elif before > t2:
            # No later worker completion claim: scope ends at cycle2.
            continue
        else:
            raise Gap("worker_crossed_epoch_boundary")
    if arm == "registry" and (counts[0] < 1 or counts[0] != counts[1]):
        raise Gap("unequal_or_missing_registry_worker_epochs")
    if arm == "nochange" and (counts[0] or counts[1]):
        raise Gap("unexpected_control_worker")
    return {
        "workers_epoch1": counts[0],
        "workers_epoch2": counts[1],
        "qpc_elapsed_epoch1": t1-t0,
        "qpc_elapsed_epoch2": t2-t1,
    }

def selftest() -> None:
    clocks = (
        "C545D_CI_ACTIVE_EPOCH,baseline,0,1000,20,30\n"
        "C545D_CI_ACTIVE_EPOCH,cycle,1,2000,30,40\n"
        "C545D_CI_ACTIVE_EPOCH,cycle,2,3000,40,50\n"
    )
    def worker(ordinal: int, values: tuple[int, int, int, int]) -> str:
        return "".join(
            f"C545D_CI_APPINFO_QPC,phase={phase},ordinal={ordinal},qpc={qpc}\n"
            for phase, qpc in zip(PHASES, values)
        )
    first = worker(1, (1100,1200,1300,1400))
    second = worker(2, (2100,2200,2300,2400))
    good = clocks+first+second
    assert verify(good, "registry")["workers_epoch2"] == 1
    assert verify(clocks, "nochange")["workers_epoch1"] == 0
    assert verify(clocks+worker(10,(100,200,300,400))+first+second,"registry")["workers_epoch1"]==1
    negatives = [
        good.replace("C545D_CI_ACTIVE_EPOCH,cycle,2,", "C545D_CI_ACTIVE_EPOCH,cycle,3,"),
        good+clocks.splitlines(1)[0],
        good+first,
        good.replace("qpc=1400", "qpc=1250"),
        good.replace("qpc=2400", "qpc=3100"),
        good.replace("ordinal=2,qpc=2300", "ordinal=3,qpc=2300"),
        clocks+first,
        good.replace("qpc=1400", "qpc=2100"),
        good.replace("qpc=1100", "qpc=900"),
        good,
        clocks+first,
        good+"C545D_CI_APPINFO_QPC,phase=worker_begin,ordinal=3,qpc=2500\n",
    ]
    for i,bad in enumerate(negatives):
        mode = "nochange" if i==9 or i==10 else "registry"
        try:
            verify(bad, mode)
        except Gap:
            pass
        else:
            raise AssertionError(f"worker_epoch_negative_accepted:{i}")
    print("C545D_GIO_ACTIVE_WORKER_EPOCH_SELFTEST_PASS,positive=3,negative=12,"
          "worker_done_parity=1,cutoff_crossing_rejected=1,ordinal_join=1,"
          "global_quiescence_not_proven=1,release_HOLD=1")

def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--input",type=Path)
    p.add_argument("--arm",choices=("nochange","registry"))
    a=p.parse_args()
    if a.selftest:
        selftest()
        return
    if a.input is None or a.arm is None:
        p.error("--input and --arm required")
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_OS") != "Windows":
        raise SystemExit("C545D_GIO_ACTIVE_WORKER_EPOCH_GAP,reason=isolated_runner_required,release_HOLD=1")
    root=os.environ.get("RUNNER_TEMP")
    if not root or not a.input.resolve().is_relative_to(Path(root).resolve()):
        raise SystemExit("C545D_GIO_ACTIVE_WORKER_EPOCH_GAP,reason=private_source_required,release_HOLD=1")
    try:
        if a.input.stat().st_size > 1_000_000:
            raise Gap("oversized_probe_text")
        result=verify(a.input.read_text(encoding="utf-8",errors="strict"),a.arm)
    except (Gap,OSError,UnicodeError):
        raise SystemExit("C545D_GIO_ACTIVE_WORKER_EPOCH_GAP,reason=incomplete_or_noncomparable_worker_phases,release_HOLD=1")
    s=",".join(f"{k}={v}" for k,v in result.items())
    print(f"C545D_GIO_ACTIVE_WORKER_EPOCH_AUDIT,arm={a.arm},"+s+
          ",global_quiescence_not_proven=1,leak_slope_unproven=1,release_HOLD=1")

if __name__=="__main__":
    main()
