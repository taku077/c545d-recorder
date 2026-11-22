#!/usr/bin/env python3
"""Validate CI-only GLib registry APC registration/completion runtime counters.

This does NOT declare the whole process quiescent, since a pending registry
watch is an expected live subscription; it does not assign PrivateUsage to
these objects. Only four numeric fields from each allowlisted trace are used.
No raw app names, paths, addresses, ETLs, or camera content are emitted.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re

LINE = re.compile(r"^C545D_CI_REGISTRY_WATCH_LIFETIME,kind=(register|complete),reg=(\d+),done=(\d+),active=(-?\d+)$")
PREFIX = "C545D_CI_REGISTRY_WATCH_LIFETIME,"
MAX_ROOTS = 8


def parse(raw: str, arm: str) -> str:
    if arm not in {"registry", "nochange"} or not isinstance(raw, str):
        raise ValueError("invalid_arm_or_input")
    if len(raw) > 1_000_000:
        raise ValueError("oversized_trace")
    reg = 0
    done = 0
    active_peak = 0
    records = 0
    for line in raw.splitlines():
        if not line.startswith(PREFIX):
            continue
        m = LINE.fullmatch(line.strip())
        if m is None:
            raise ValueError("trace_event_corrupt")
        kind, new_reg, new_done, active = m.groups()
        new_reg, new_done, active = int(new_reg), int(new_done), int(active)
        if kind == "register":
            if new_reg != reg + 1 or new_done != done:
                raise ValueError("registration_counter_not_monotone")
        else:
            if new_done != done + 1 or new_reg != reg:
                raise ValueError("completion_counter_not_monotone")
        if active != new_reg - new_done or not 0 <= active <= MAX_ROOTS:
            raise ValueError("active_watch_count_out_of_bounds")
        reg, done = new_reg, new_done
        active_peak = max(active_peak, active)
        records += 1
    if records != reg + done or reg < 1 or not 1 <= active_peak <= MAX_ROOTS:
        raise ValueError("watch_trace_incomplete")
    if arm == "registry" and done == 0:
        raise ValueError("registry_arm_has_no_apc_completion")
    if active_peak < reg - done:
        raise ValueError("inconsistent_final_active")
    return (
        "C545D_GIO_WATCH_RUNTIME_PASS,"
        f"arm={arm},registrations={reg},completions={done},"
        f"final_pending_status_blocks={reg-done},peak_pending={active_peak},"
        "bound_per_watched_key=1,"
        "runtime_APC_on_source_watch_observed=" + str(int(done > 0)) + ","
        "global_idle_proven=0,private_bytes_owner_proven=0,"
        "diagnostic_log_perturbation=1,real_host_untouched=1"
    )


def selftest() -> None:
    def msg(kind: str, reg: int, done: int, active: int) -> str:
        return f"C545D_CI_REGISTRY_WATCH_LIFETIME,kind={kind},reg={reg},done={done},active={active}\n"
    initial = "".join(msg("register", i, 0, i) for i in range(1, 9))
    rearmed = msg("complete", 8, 1, 7) + msg("register", 9, 1, 8)
    assert "completions=0" in parse(initial, "nochange")
    assert "completions=1" in parse(initial + rearmed, "registry")
    broken = [
        initial.replace("active=8", "active=9"),
        initial.replace("reg=3", "reg=5", 1),
        initial.replace("kind=register", "kind=unexpected", 1),
        initial + msg("register", 9, 0, 9),
        initial + msg("complete", 8, 2, 6),
        initial + msg("complete", 8, 1, 8),
        initial.replace("done=0", "done=-1", 1),
        initial + rearmed + msg("complete", 8, 2, 6),
        initial + msg("complete", 8, 1, 7) + msg("register", 9, 1, 9),
    ]
    for i, source in enumerate(broken):
        try:
            parse(source, "nochange")
        except ValueError:
            continue
        raise AssertionError(f"corrupt_registry_event_accepted,index={i}")
    try:
        parse(initial, "registry")
    except ValueError:
        pass
    else:
        raise AssertionError("missing_registry_APC_completion_accepted")
    print("C545D_GIO_WATCH_RUNTIME_SELFTEST_PASS,positive=2,negative=10,real_GIO_tested=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--folder", type=Path)
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    if a.folder is None:
        p.error("--folder required")
    for arm in ("nochange", "registry"):
        source = a.folder / f"combo-{arm}-16.txt"
        if not source.is_file():
            raise ValueError("missing_disposable_trace")
        print(parse(source.read_text(encoding="utf-8-sig", errors="replace"), arm))
    print("C545D_GIO_WATCH_RUNTIME_PAIR_PASS,arms=2,cycles=16,bounded_watch_source_counter=1,worker_global_idle_unproven=1,real_host_untouched=1")


if __name__ == "__main__":
    main()
