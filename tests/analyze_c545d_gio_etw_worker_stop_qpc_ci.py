#!/usr/bin/env python3
"""Same-PID QPC interval proof for Xperf stop vs GIO AppInfo rebuild workers.

Use a newly QPC-instrumented disposable Windows CI log ONLY. A spanning
worker proves it was still rebuilding during the entire Xperf stop bracket.
Neither lack of such a worker nor an observed worker return proves global APC,
WinRT or GIO quiescence, an allocation owner, or a memory leak.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

FENCE = re.compile(r"C545D_CI_ETW_FENCE_QPC,phase="
                   r"(precleanup_ready_before|trace_stopped_ack),qpc=([1-9]\d*)")
WORKER = re.compile(r"C545D_CI_APPINFO_QPC,phase="
                    r"(registry_callback|worker_begin|parser_begin|parser_end|"
                    r"worker_scan_end|worker_unlocked|worker_after_notify),"
                    r"ordinal=([1-9]\d*),qpc=([1-9]\d*)")
WORKER_PHASES = ("worker_begin", "parser_begin", "parser_end",
                 "worker_scan_end", "worker_unlocked", "worker_after_notify")


def parse(raw: str, arm: str) -> dict[str, int | str]:
    if arm not in ("registry", "nochange"):
        raise ValueError("arm_not_allowlisted")
    done = [s for s in raw.splitlines() if s.startswith("GIO_PROBE_DONE,")]
    if len(done) != 1 or not re.fullmatch(
        rf"GIO_PROBE_DONE,cycles=16,notifications=\d+,reg_changes={int(arm == 'registry')}",
        done[0],
    ):
        raise ValueError("not_the_expected_same_pid_16_cycle_probe")
    fences: dict[str, int] = {}
    workers: dict[int, dict[str, int]] = {}
    callback_seen: set[int] = set()
    for line in raw.splitlines():
        if line.startswith("C545D_CI_ETW_FENCE_QPC,"):
            match = FENCE.fullmatch(line)
            if match is None:
                raise ValueError("invalid_or_raw_fence_qpc")
            phase, qpc = match.groups()
            if phase in fences:
                raise ValueError("duplicated_stop_fence")
            fences[phase] = int(qpc)
        elif line.startswith("C545D_CI_APPINFO_QPC,"):
            match = WORKER.fullmatch(line)
            if match is None:
                raise ValueError("invalid_or_raw_worker_qpc")
            phase, ordinal, qpc = match.groups()
            n = int(ordinal)
            if phase == "registry_callback":
                if n in callback_seen:
                    raise ValueError("duplicate_registry_callback_qpc")
                callback_seen.add(n)
            else:
                timeline = workers.setdefault(n, {})
                if phase in timeline:
                    raise ValueError("duplicated_worker_phase")
                timeline[phase] = int(qpc)
    if set(fences) != {"precleanup_ready_before", "trace_stopped_ack"}:
        raise ValueError("missing_exact_etw_stop_bracket")
    before = fences["precleanup_ready_before"]
    after = fences["trace_stopped_ack"]
    if before >= after:
        raise ValueError("nonmonotonic_etw_stop_bracket")
    if not workers:
        raise ValueError("no_instrumented_workers")
    if set(workers) != set(range(1, len(workers) + 1)):
        raise ValueError("noncontiguous_worker_ordinals")
    if callback_seen and callback_seen != set(range(1, len(callback_seen) + 1)):
        raise ValueError("noncontiguous_registry_callbacks")
    for state in workers.values():
        if set(state) != set(WORKER_PHASES):
            raise ValueError("worker_lifecycle_incomplete")
        timeline = [state[p] for p in WORKER_PHASES]
        if timeline != sorted(timeline):
            raise ValueError("worker_qpc_phase_order_invalid")
    # Microsoft QPC guidance: cross-thread timestamp differences of one
    # counter tick cannot establish strict before/after ordering. Treat the
    # +/-1 tick vicinity as ambiguous, not as proof of continuous activity.
    def possibly_overlaps(state: dict[str, int]) -> bool:
        return (state["worker_begin"] <= after + 1 and
                state["worker_after_notify"] >= before - 1)
    overlapping = [x for x in workers.values() if possibly_overlaps(x)]
    spanning = [x for x in overlapping
                if x["worker_begin"] < before - 1 and
                   x["worker_after_notify"] > after + 1]
    # A worker that started or finished inside the stop bracket makes the
    # worker's *precise state at xperf stop* indeterminate.
    status = ("rebuild_continuously_active" if spanning else
              "rebuild_status_ambiguous" if overlapping else
              "no_traced_rebuild_overlaps")
    return {
        "arm": arm,
        "workers": len(workers),
        "callbacks": len(callback_seen),
        "stop_bracket_observed": 1,
        "worker_overlapping_stop_bracket": len(overlapping),
        "worker_spanning_entire_stop_bracket": len(spanning),
        "worker_return_after_stop_ack": sum(
            s["worker_after_notify"] > after + 1 for s in workers.values()),
        "exact_rebuild_status": status,
        "cross_thread_one_tick_ambiguity_guard": 1,
        "globally_quiet_proven": 0,
        "allocation_owner_proven": 0,
        "leak_proven": 0,
    }


def selftest() -> None:
    base = [
        "GIO_PROBE_DONE,cycles=16,notifications=17,reg_changes=1",
        "C545D_CI_ETW_FENCE_QPC,phase=precleanup_ready_before,qpc=300",
        "C545D_CI_ETW_FENCE_QPC,phase=trace_stopped_ack,qpc=400",
        "C545D_CI_APPINFO_QPC,phase=registry_callback,ordinal=1,qpc=101",
    ]
    for ordinal, points in (
        (1, (100, 150, 200, 250, 280, 450)),
        (2, (460, 465, 470, 475, 480, 485)),
    ):
        for stage, qpc in zip(WORKER_PHASES, points):
            base.append(f"C545D_CI_APPINFO_QPC,phase={stage},ordinal={ordinal},qpc={qpc}")
    raw = "\n".join(base)
    assert parse(raw, "registry")["worker_spanning_entire_stop_bracket"] == 1
    assert parse(raw, "registry")["worker_return_after_stop_ack"] == 2
    no = raw.replace("reg_changes=1", "reg_changes=0")
    assert parse(no, "nochange")["stop_bracket_observed"] == 1
    near_tick = raw.replace("qpc=300", "qpc=100").replace("qpc=400", "qpc=449")
    assert parse(near_tick, "registry")["exact_rebuild_status"] == "rebuild_status_ambiguous"
    # All non-spanning possibilities are retained without calling them idle.
    nonspanning = raw.replace(
        "phase=worker_after_notify,ordinal=1,qpc=450",
        "phase=worker_after_notify,ordinal=1,qpc=350")
    assert parse(nonspanning, "registry")["exact_rebuild_status"] == "rebuild_status_ambiguous"
    nonoverlap = raw.replace(
        "phase=worker_begin,ordinal=1,qpc=100",
        "phase=worker_begin,ordinal=1,qpc=50")
    for stage, old, new in (
        ("parser_begin", "150", "60"), ("parser_end", "200", "70"),
        ("worker_scan_end", "250", "80"), ("worker_unlocked", "280", "90"),
        ("worker_after_notify", "450", "95"),
    ):
        nonoverlap = nonoverlap.replace(
            f"phase={stage},ordinal=1,qpc={old}",
            f"phase={stage},ordinal=1,qpc={new}")
    assert parse(nonoverlap, "registry")["exact_rebuild_status"] == "no_traced_rebuild_overlaps"
    cases = [
        raw.replace("trace_stopped_ack", "not_a_fence"),
        raw.replace("qpc=400", "qpc=200"),
        raw.replace("qpc=400", "qpc=300"),
        raw.replace("phase=trace_stopped_ack,qpc=400", "phase=trace_stopped_ack,qpc=400\n"
                    "C545D_CI_ETW_FENCE_QPC,phase=trace_stopped_ack,qpc=500"),
        raw.replace("phase=worker_after_notify,ordinal=1,qpc=450", ""),
        raw.replace("phase=worker_after_notify,ordinal=1,qpc=450",
                    "phase=worker_after_notify,ordinal=1,qpc=450\n"
                    "C545D_CI_APPINFO_QPC,phase=worker_after_notify,ordinal=1,qpc=455"),
        raw.replace("phase=parser_end,ordinal=1,qpc=200",
                    "phase=parser_end,ordinal=1,qpc=90"),
        raw.replace("ordinal=2,qpc=460", "ordinal=3,qpc=460").replace(
                    "ordinal=2,qpc=465", "ordinal=3,qpc=465").replace(
                    "ordinal=2,qpc=470", "ordinal=3,qpc=470").replace(
                    "ordinal=2,qpc=475", "ordinal=3,qpc=475").replace(
                    "ordinal=2,qpc=480", "ordinal=3,qpc=480").replace(
                    "ordinal=2,qpc=485", "ordinal=3,qpc=485"),
        raw.replace("phase=worker_begin,ordinal=1,qpc=100",
                    "phase=worker_begin,ordinal=1,qpc=secret"),
        raw.replace("reg_changes=1", "reg_changes=0"),
        raw.replace("GIO_PROBE_DONE,cycles=16,", "GIO_PROBE_DONE,cycles=15,"),
    ]
    for i, corrupt in enumerate(cases):
        try:
            parse(corrupt, "registry")
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid worker/stop interval accepted: {i}")
    print(f"C545D_GIO_ETW_WORKER_QPC_SELFTEST_PASS,positive=5,negative={len(cases)},"
          "global_idle_proven=0,worker_lifetime_only=1,host_untouched=1")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--report", type=Path)
    p.add_argument("--arm", choices=("registry", "nochange"))
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    if not a.report or not a.arm:
        p.error("--report and --arm required")
    if a.report.stat().st_size > 20_000_000:
        raise ValueError("unbounded_private_runner_log")
    data = parse(a.report.read_text(encoding="utf-8-sig"), a.arm)
    print("C545D_GIO_ETW_WORKER_STOP_QPC," +
          ",".join(f"{k}={v}" for k, v in data.items()))


if __name__ == "__main__":
    main()
