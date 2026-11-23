#!/usr/bin/env python3
"""Archive-only GIO watch-root lifetime accounting from REAL 2026-11-23 CI log.

Source: disposable Windows run 45133754345 / job 137554982677.
Do not upload logs, registry paths, raw ETL or addresses.
A stable number of watcher subscriptions across a bounded trial is not
evidence that memory PrivateUsage stopped growing or that WinRT/APC is idle.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re

SOURCE_RUN = 45133754345
SOURCE_JOB = 137554982677
MAX_LOG_BYTES = 12_000_000
WATCH = re.compile(
    r"^C545D_GIO_WATCH_RUNTIME_PASS,arm=(nochange|registry),"
    r"registrations=(\d+),completions=(\d+),"
    r"final_pending_status_blocks=(\d+),peak_pending=(\d+),"
    r"bound_per_watched_key=(\d+),"
    r"runtime_APC_on_source_watch_observed=(\d+),"
    r"global_idle_proven=(\d+),private_bytes_owner_proven=(\d+),"
    r"diagnostic_log_perturbation=(\d+),real_host_untouched=(\d+)$"
)
QPC = re.compile(
    r"^C545D_GIO_ETW_WORKER_STOP_QPC,arm=(nochange|registry),"
    r"workers=(\d+),callbacks=(\d+),stop_bracket_observed=(\d+),"
    r"worker_overlapping_stop_bracket=(\d+),"
    r"worker_spanning_entire_stop_bracket=(\d+),"
    r"worker_return_after_stop_ack=(\d+),"
    r"exact_rebuild_status=(no_traced_rebuild_overlaps),"
    r"cross_thread_one_tick_ambiguity_guard=(\d+),"
    r"globally_quiet_proven=(\d+),allocation_owner_proven=(\d+),"
    r"leak_proven=(\d+)$"
)
NUMERIC_LOG = re.compile(r"^20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z ")
LABEL = "C545D_GIO_ACTIVE_WATCH_EPOCH_ARCHIVE_PASS"


def extract(log: str, pattern: re.Pattern[str]) -> dict[str, tuple[int, ...]]:
    if not isinstance(log,str) or len(log.encode("utf-8")) > MAX_LOG_BYTES:
        raise ValueError("source_log_missing_or_oversized")
    hits={}
    for line in log.splitlines():
        m=NUMERIC_LOG.match(line)
        if not m:
            continue
        body=line[m.end():].strip()
        parsed=pattern.fullmatch(body)
        if parsed:
            arm=parsed.group(1)
            if arm in hits:
                raise ValueError("duplicate_exact_runtime_source")
            # 'exact_rebuild_status' is a fixed string, excluded
            numeric=tuple(int(x) for x in parsed.groups()[1:] if x.isdigit())
            hits[arm]=numeric
    if set(hits)!={"registry","nochange"}:
        raise ValueError("missing_exact_paired_runtime_source")
    return hits


def evaluate(log: str) -> str:
    watches=extract(log,WATCH)
    qpcs=extract(log,QPC)
    # Read each fixed field by index, checked for exact provenance.
    n,r=watches["nochange"],watches["registry"]
    if n != (6,0,6,6,1,0,0,0,1,1):
        raise ValueError("nochange_watch_provenance_changed")
    if r != (23,17,6,6,1,1,0,0,1,1):
        raise ValueError("registry_watch_provenance_changed")
    if r[0]-n[0] != 17 or r[1]-n[1]!=17:
        raise ValueError("notification_rearm_not_accounted")
    if any(x[0]-x[1]!=x[2] for x in watches.values()):
        raise ValueError("pending_watch_arithmetic_inconsistent")
    # QPC final true worker-return is a barrier counterexample; this source
    # never establishes a complete producer-closed window.
    qn,qr=qpcs["nochange"],qpcs["registry"]
    if qn != (1,0,1,0,0,0,1,0,0,0):
        raise ValueError("nochange_QPC_provenance_changed")
    if qr != (18,17,1,0,0,1,1,0,0,0):
        raise ValueError("registry_QPC_provenance_changed")
    return (
        f"{LABEL},source_run={SOURCE_RUN},source_job={SOURCE_JOB},"
        "nochange_registration=6,nochange_completion=0,"
        "registry_registration=23,registry_completion=17,"
        "new_watches=17,completed_watches=17,"
        "watch_pending_before=6,watch_pending_after=6,"
        "maximum_pending_in_each_arm=6,"
        "observed_watch_pending_growth=0,"
        "watched_roots_source_max=8,"
        "observed_steady_subscription_count=1,"
        "bounded_trial_only=1,continuous_operation_stability_unproven=1,"
        "private_memory_slope_not_measured_here=1,"
        "post_stop_worker_returned=1,global_async_quiet_unproven=1,"
        "source_owned_heap_bytes_unproven=1,"
        "release_HOLD=1,raw_logs_uploaded=0,real_host_untouched=1"
    )


def sample() -> str:
    no=("C545D_GIO_WATCH_RUNTIME_PASS,arm=nochange,registrations=6,completions=0,"
        "final_pending_status_blocks=6,peak_pending=6,bound_per_watched_key=1,"
        "runtime_APC_on_source_watch_observed=0,global_idle_proven=0,"
        "private_bytes_owner_proven=0,diagnostic_log_perturbation=1,"
        "real_host_untouched=1")
    reg=("C545D_GIO_WATCH_RUNTIME_PASS,arm=registry,registrations=23,completions=17,"
         "final_pending_status_blocks=6,peak_pending=6,bound_per_watched_key=1,"
         "runtime_APC_on_source_watch_observed=1,global_idle_proven=0,"
         "private_bytes_owner_proven=0,diagnostic_log_perturbation=1,"
         "real_host_untouched=1")
    qno=("C545D_GIO_ETW_WORKER_STOP_QPC,arm=nochange,workers=1,callbacks=0,"
         "stop_bracket_observed=1,worker_overlapping_stop_bracket=0,"
         "worker_spanning_entire_stop_bracket=0,worker_return_after_stop_ack=0,"
         "exact_rebuild_status=no_traced_rebuild_overlaps,"
         "cross_thread_one_tick_ambiguity_guard=1,globally_quiet_proven=0,"
         "allocation_owner_proven=0,leak_proven=0")
    qreg=("C545D_GIO_ETW_WORKER_STOP_QPC,arm=registry,workers=18,callbacks=17,"
          "stop_bracket_observed=1,worker_overlapping_stop_bracket=0,"
          "worker_spanning_entire_stop_bracket=0,worker_return_after_stop_ack=1,"
          "exact_rebuild_status=no_traced_rebuild_overlaps,"
          "cross_thread_one_tick_ambiguity_guard=1,globally_quiet_proven=0,"
          "allocation_owner_proven=0,leak_proven=0")
    return "".join(f"2026-11-23T07:52:42.3766101Z {line}\n"
                   for line in [no,reg,qno,qreg])


def selftest() -> None:
    good=sample()
    assert "observed_watch_pending_growth=0" in evaluate(good)
    mutations=[
        ("registrations=23","registrations=24"),
        ("completions=17","completions=16"),
        ("final_pending_status_blocks=6","final_pending_status_blocks=7"),
        ("peak_pending=6","peak_pending=7"),
        ("runtime_APC_on_source_watch_observed=1","runtime_APC_on_source_watch_observed=0"),
        ("global_idle_proven=0","global_idle_proven=1"),
        ("private_bytes_owner_proven=0","private_bytes_owner_proven=1"),
        ("worker_return_after_stop_ack=1","worker_return_after_stop_ack=0"),
        ("globally_quiet_proven=0","globally_quiet_proven=1"),
        ("workers=18","workers=17"),
        ("arm=registry","arm=nochange"),
    ]
    for i,(old,new) in enumerate(mutations):
        corrupted=good.replace(old,new,1)
        if corrupted==good:raise AssertionError("bad_mutation_fixture")
        try:evaluate(corrupted)
        except ValueError:continue
        raise AssertionError(f"false_stable_source_accepted:{i}")
    for i,invalid in enumerate((good+good,good.splitlines()[0],good.replace("2026-11-23T07:52:42.3766101Z ","",1))):
        try:evaluate(invalid)
        except ValueError:continue
        raise AssertionError(f"source_log_shape_accepted:{i}")
    print("C545D_GIO_ACTIVE_WATCH_EPOCH_SELFTEST_PASS,positive=1,negative=14,"
          "no_new_Windows_runs=1,real_host_untouched=1,stable_watches_not_stable_memory=1")


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--log",type=Path)
    a=p.parse_args()
    if a.selftest:
        selftest()
        return
    if not a.log:
        p.error("--log required for original source CI log")
    if a.log.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("original_job_log_oversized")
    print(evaluate(a.log.read_text(encoding="utf-8-sig",errors="replace")))


if __name__=="__main__":
    main()
