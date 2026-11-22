#!/usr/bin/env python3
"""Analyze only numeric C545D CI-only Win32 AppInfo phase trace output.

This is a chronology discriminator, not a memory ownership attribution.
Trace logging can perturb scheduling. An observed idle interval does not
prove that WinRT, APC or registry workers are globally quiescent.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

TRACE = re.compile(
    r"C545D_CI_APPINFO_TRACE,phase="
    r"(registry_callback|worker_begin|parser_begin|parser_end|"
    r"worker_scan_end|worker_unlocked),ordinal=([1-9]\d*),tick_ms=(\d+)"
)
PROBE = re.compile(
    r"C545D_CI_PROBE_PHASE,phase="
    r"(after_cleanup|idle_begin|idle_end|scanfree_cleanup),tick_ms=(\d+)"
)
WORKER_PHASES = ("worker_begin", "parser_begin", "parser_end",
                 "worker_scan_end", "worker_unlocked")
PROBE_PHASES = ("after_cleanup", "idle_begin", "idle_end", "scanfree_cleanup")


def parse(raw: str, arm: str) -> dict:
    if arm not in ("registry", "nochange"):
        raise ValueError("unexpected arm")
    expected_done = f"reg_changes={int(arm == 'registry')}"
    completed = [line for line in raw.splitlines()
                 if line.startswith("GIO_PROBE_DONE,")]
    if (len(completed) != 1 or
            re.fullmatch(r"GIO_PROBE_DONE,cycles=16,notifications=\d+,"
                         r"reg_changes=[01]", completed[0]) is None or
            not completed[0].endswith(expected_done)):
        raise ValueError("wrong or missing completed short probe")
    if raw.splitlines().count("C545D_CI_SCANFREE_FINAL,enabled=1") != 1:
        raise ValueError("missing caller-side scanfree marker")
    stages: dict[str, int] = {}
    workers: dict[int, dict[str, int]] = {}
    callback_ticks: dict[int, int] = {}
    for line in raw.splitlines():
        if line.startswith("C545D_CI_APPINFO_TRACE,"):
            match = TRACE.fullmatch(line)
            if not match:
                raise ValueError("invalid AppInfo phase trace")
            phase, ordinal_text, tick_text = match.groups()
            ordinal, tick = int(ordinal_text), int(tick_text)
            if phase == "registry_callback":
                if ordinal in callback_ticks:
                    raise ValueError("duplicate registry callback")
                callback_ticks[ordinal] = tick
            else:
                state = workers.setdefault(ordinal, {})
                if phase in state:
                    raise ValueError("duplicate worker phase")
                state[phase] = tick
        elif line.startswith("C545D_CI_PROBE_PHASE,"):
            match = PROBE.fullmatch(line)
            if not match:
                raise ValueError("invalid probe phase marker")
            phase, tick_text = match.groups()
            if phase in stages:
                raise ValueError("duplicate probe phase")
            stages[phase] = int(tick_text)

    if set(stages) != set(PROBE_PHASES):
        raise ValueError("incomplete probe phase observations")
    stamps = [stages[name] for name in PROBE_PHASES]
    if stamps != sorted(stamps) or stages["idle_end"] - stages["idle_begin"] < 2000:
        raise ValueError("nonmonotonic or unexpectedly short idle observation")
    if not workers:
        raise ValueError("missing initial AppInfo worker instrumentation")
    if set(workers) != set(range(1, len(workers) + 1)):
        raise ValueError("noncontiguous worker ordinals")
    if set(callback_ticks) != set(range(1, len(callback_ticks) + 1)):
        raise ValueError("noncontiguous callback ordinals")
    for ordinal, state in workers.items():
        if tuple(state) != WORKER_PHASES:
            # Output is from multiple threads; dictionary insertion order is not
            # a timing guarantee. Validate presence and event timestamps instead.
            if set(state) != set(WORKER_PHASES):
                raise ValueError(f"worker {ordinal} missing lifecycle stage")
        ticks = [state[p] for p in WORKER_PHASES]
        if ticks != sorted(ticks):
            raise ValueError(f"worker {ordinal} timestamps are nonmonotonic")
    if any(workers[i]["worker_begin"] < workers[i-1]["worker_begin"]
           for i in range(2, len(workers)+1)):
        raise ValueError("worker ordinal time reversal")

    after = stages["after_cleanup"]
    begin = stages["idle_begin"]
    end = stages["idle_end"]
    final = stages["scanfree_cleanup"]
    def during_idle(t: int) -> bool:
        return begin <= t <= end
    def overlaps_active(t: int) -> bool:
        return any(w["worker_begin"] <= t <= w["worker_scan_end"]
                   for w in workers.values())
    def worker_in_window(w: dict[str, int]) -> bool:
        return (begin <= w["worker_begin"] <= end or
                begin <= w["worker_scan_end"] <= end or
                w["worker_begin"] < begin < end < w["worker_scan_end"])
    boundary_collision = any(
        t in (after, begin, end, final)
        for w in workers.values() for t in w.values()
    ) or any(t in (after, begin, end, final) for t in callback_ticks.values())
    return {
        "arm": arm,
        "callbacks": len(callback_ticks),
        "workers": len(workers),
        "idle_ms": end - begin,
        "callbacks_idle": sum(during_idle(t) for t in callback_ticks.values()),
        "worker_scans_idle": sum(worker_in_window(w) for w in workers.values()),
        "parser_ends_idle": sum(during_idle(w["parser_end"]) for w in workers.values()),
        "worker_active_after_cleanup": int(overlaps_active(after)),
        "worker_active_final": int(overlaps_active(final)),
        "worker_completed_after_cleanup": sum(
            after <= w["worker_scan_end"] <= final for w in workers.values()
        ),
        "boundary_tick_ambiguous": int(boundary_collision),
    }


def summarize(folder: Path) -> list[str]:
    lines = []
    for arm in ("nochange", "registry"):
        d = parse((folder / f"combo-{arm}-16.txt").read_text(encoding="utf-8-sig"), arm)
        fields = ",".join(f"{key}={value}" for key, value in d.items())
        lines.append("C545D_APPINFO_PHASE_TRACE," + fields +
                     ",timing_perturbation_possible=1,quiescence_proven=0")
    lines.append("C545D_APPINFO_PHASE_TRACE_PASS,arms=2,cycles=16,"
                 "GAppInfo_final_query_skipped=1,allocation_owner_proven=0,"
                 "real_camera=0,host_modified=0")
    return lines


def selftest() -> None:
    def specimen(arm: str, with_idle_rebuild: bool) -> str:
        sample = [
            f"GIO_PROBE_DONE,cycles=16,notifications=0,reg_changes={int(arm == 'registry')}",
            "C545D_CI_SCANFREE_FINAL,enabled=1",
            "C545D_CI_PROBE_PHASE,phase=after_cleanup,tick_ms=100",
            "C545D_CI_PROBE_PHASE,phase=idle_begin,tick_ms=101",
            "C545D_CI_PROBE_PHASE,phase=idle_end,tick_ms=2601",
            "C545D_CI_PROBE_PHASE,phase=scanfree_cleanup,tick_ms=2602",
        ]
        def worker(seq: int, ticks: tuple[int, ...]):
            return [f"C545D_CI_APPINFO_TRACE,phase={phase},ordinal={seq},tick_ms={tick}"
                    for phase, tick in zip(WORKER_PHASES, ticks)]
        sample += worker(1, (10, 20, 30, 40, 50))
        if with_idle_rebuild:
            sample += ["C545D_CI_APPINFO_TRACE,phase=registry_callback,"
                       "ordinal=1,tick_ms=150"]
            sample += worker(2, (200, 205, 250, 255, 260))
        return "\n".join(sample)
    with_rebuild = specimen("registry", True)
    no_rebuild = specimen("nochange", False)
    assert parse(with_rebuild, "registry")["worker_scans_idle"] == 1
    assert parse(with_rebuild, "registry")["parser_ends_idle"] == 1
    assert parse(no_rebuild, "nochange")["worker_scans_idle"] == 0
    negatives = (
        with_rebuild.replace("phase=worker_unlocked,ordinal=2", "phase=missing,ordinal=2"),
        with_rebuild.replace("phase=idle_end,tick_ms=2601", "phase=idle_end,tick_ms=500"),
        with_rebuild.replace("phase=worker_scan_end,ordinal=2,tick_ms=255",
                             "phase=worker_scan_end,ordinal=2,tick_ms=203"),
        with_rebuild.replace("ordinal=2,tick_ms=205", "ordinal=1,tick_ms=205"),
        with_rebuild.replace("reg_changes=1", "reg_changes=0"),
    )
    for bad in negatives:
        try: parse(bad, "registry")
        except ValueError: pass
        else: raise AssertionError("invalid phase source accepted")
    print("C545D_APPINFO_PHASE_ANALYZER_SELFTEST_PASS,synthetic_positive=2,"
          "negative_cases=5,new_windows_runs=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--folder", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
    else:
        if args.folder is None: p.error("--folder is required")
        print("\n".join(summarize(args.folder)))


if __name__ == "__main__":
    main()
