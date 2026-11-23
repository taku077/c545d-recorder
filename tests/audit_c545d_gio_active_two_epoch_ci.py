#!/usr/bin/env python3
"""Strict numeric-only three-phase resource gate for disposable GIO two-epoch CI.

Not a leak verdict: the caller must independently prove equivalent completed
worker epochs and ETW source attribution before inferring a steady-state slope.
Do not accept raw ETL, handles, PDB, addresses, paths or registry strings.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re

PHASES = (("baseline", 0), ("cycle", 1), ("cycle", 2))
NAMES = ("baseline0", "cycle1", "cycle2")
# These are the only admitted input record types (others from probe ignored).
PATTERNS = {
    "clock": re.compile(r"^C545D_CI_ACTIVE_EPOCH,(baseline|cycle),(\d+),(\d+),(\d+),(\d+)$"),
    "psapi": re.compile(r"^GIO_PROBE,(baseline|cycle),(\d+),(\d+),(\d+),(\d+)$"),
    "vm": re.compile(r"^GIO_VM,(baseline|cycle),(\d+),(\d+),(\d+),(\d+),(\d+),0$"),
}

class Gap(ValueError):
    pass

def audit(raw: str) -> dict[str, int]:
    if len(raw) > 1_000_000:
        raise Gap("unbounded_numeric_probe_output")
    found: dict[str, dict[tuple[str, int], tuple[int, ...]]] = {
        kind: {} for kind in PATTERNS
    }
    for line in raw.splitlines():
        for kind, regex in PATTERNS.items():
            if not line.startswith(("C545D_CI_ACTIVE_EPOCH,", "GIO_PROBE,", "GIO_VM,")):
                break
            match = regex.fullmatch(line)
            if match is None:
                if line.startswith({
                    "clock": "C545D_CI_ACTIVE_EPOCH,",
                    "psapi": "GIO_PROBE,",
                    "vm": "GIO_VM,",
                }[kind]):
                    # Outside the three selected points: reject malformed but
                    # ignore valid alternative phases such as after_cleanup.
                    if not re.fullmatch(r"[A-Z0-9_,]+", line):
                        raise Gap("malformed_numeric_probe_line")
                continue
            phase, cycle = match.group(1), int(match.group(2))
            if (phase, cycle) not in PHASES:
                continue
            key = (phase, cycle)
            if key in found[kind]:
                raise Gap("duplicate_phase_metric")
            found[kind][key] = tuple(int(x) for x in match.groups()[2:])
    if any(set(x) != set(PHASES) for x in found.values()):
        raise Gap("missing_phase_metric")
    clk = [found["clock"][point] for point in PHASES]
    api = [found["psapi"][point] for point in PHASES]
    vm = [found["vm"][point] for point in PHASES]
    if any(clk[i][0] >= clk[i+1][0] for i in (0, 1)):
        raise Gap("qpc_nonmonotonic")
    if any(clk[i][j] > clk[i+1][j] for i in (0, 1) for j in (1, 2)):
        raise Gap("cpu_nonmonotonic")
    if any(vm[i][0] == 0 or api[i][1] == 0 for i in range(3)):
        raise Gap("invalid_vm_or_handle_baseline")
    result = {}
    for i in (0, 1):
        label = f"epoch{i+1}"
        result[f"{label}_qpc"] = clk[i+1][0] - clk[i][0]
        result[f"{label}_cpu100ns"] = (
            clk[i+1][1] + clk[i+1][2] - clk[i][1] - clk[i][2]
        )
        result[f"{label}_private_delta"] = api[i+1][2] - api[i][2]
        result[f"{label}_region_private_delta"] = vm[i+1][1] - vm[i][1]
        result[f"{label}_handles_delta"] = api[i+1][1] - api[i][1]
        result[f"{label}_notifications_delta"] = api[i+1][0] - api[i][0]
    # No mandatory positive notification for the nochange control arm.
    if any(result[f"epoch{i}_notifications_delta"] < 0 for i in (1, 2)):
        raise Gap("notification_count_regressed")
    return result

def selftest() -> None:
    def row(phase: str, cycle: int, index: int) -> str:
        return (
            f"C545D_CI_ACTIVE_EPOCH,{phase},{cycle},{1000+100*index},"
            f"{30+10*index},{40+10*index}\n"
            f"GIO_PROBE,{phase},{cycle},{index},{200+index},{10000+256*index}\n"
            f"GIO_VM,{phase},{cycle},{15+index},{40000+4096*index},"
            f"1000,2000,0\n"
        )
    pieces = [row(*pair, i) for i, pair in enumerate(PHASES)]
    good = "".join(pieces)
    r = audit(good)
    assert r["epoch1_private_delta"] == 256
    assert r["epoch2_handles_delta"] == 1
    assert r["epoch1_cpu100ns"] == 20
    bad = [
        good.replace("C545D_CI_ACTIVE_EPOCH,cycle,2,", "C545D_CI_ACTIVE_EPOCH,cycle,5,"),
        good + pieces[1],
        good.replace("cycle,2,1200", "cycle,2,999"),
        good.replace("cycle,2,50,60", "cycle,2,1,1"),
        good.replace("GIO_VM,cycle,2,", "GIO_VM,cycle,2,x"),
        good.replace("GIO_PROBE,cycle,1,", "GIO_PROBE,cycle,3,"),
        good.replace("GIO_PROBE,baseline,0,0,200", "GIO_PROBE,baseline,0,0,0"),
    ]
    for item in bad:
        try:
            audit(item)
        except Gap:
            pass
        else:
            raise AssertionError("invalid_phase_data_accepted")
    print("C545D_GIO_ACTIVE_TWO_EPOCH_NUMERIC_SELFTEST_PASS,"
          "positive=1,negative=7,three_phases=1,"
          "qpc_cpu_monotonicity=1,missing_and_duplicate_denied=1,"
          "global_quiescence_not_proven=1,release_HOLD=1")

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--input", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    if args.input is None:
        p.error("--input CI-owned local probe output required")
    if os.environ.get("GITHUB_ACTIONS") != "true" or \
       os.environ.get("RUNNER_OS") != "Windows":
        raise SystemExit("C545D_GIO_ACTIVE_TWO_EPOCH_GAP,reason=CI_only,release_HOLD=1")
    root = os.environ.get("RUNNER_TEMP")
    if not root or not args.input.resolve().is_relative_to(Path(root).resolve()):
        raise SystemExit("C545D_GIO_ACTIVE_TWO_EPOCH_GAP,reason=nonprivate_input,release_HOLD=1")
    try:
        if args.input.stat().st_size > 1_000_000:
            raise Gap("unbounded_numeric_probe_output")
        values = audit(args.input.read_text(encoding="utf-8", errors="strict"))
    except (Gap, OSError, UnicodeError):
        print("C545D_GIO_ACTIVE_TWO_EPOCH_GAP,reason=missing_duplicate_or_unverified_phase,release_HOLD=1")
        raise SystemExit(2)
    fields = ",".join(f"{name}={value}" for name, value in values.items())
    print("C545D_GIO_ACTIVE_TWO_EPOCH_RESOURCE_AUDIT," + fields +
          ",worker_completion_unproven=1,leak_slope_unproven=1,release_HOLD=1")

if __name__ == "__main__":
    main()
