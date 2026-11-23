#!/usr/bin/env python3
"""Fail-closed Xperf stack top-N coverage arithmetic, NOT leak attribution.

Runs on private, ephemeral Xperf text from the disposable Windows CI runner.
Only allowlisted aggregate integers are output.  In particular, the arithmetic
difference GLOBAL.Out - accepted well-formed Out is NOT a proven count of
disjoint, unidentified heap objects.  Invalid rows may overlap and top-N
output may omit other rows.  Never upload raw stack names, addresses or ETL.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
from analyze_c545d_gio_etw_stack_cohorts_ci import (
    DASH, GLOBAL, TOP, METRICS, CAP, MAX_REPORT, num, GROUPS, cohort
)

def evaluate(raw: str, arm: str) -> str:
    if arm not in {"registry", "nochange"}:
        raise ValueError("arm_not_allowed")
    if not isinstance(raw, str) or not (100 <= len(raw) <= MAX_REPORT):
        raise ValueError("invalid_report_length")
    if len(GLOBAL.findall(raw)) != 1 or len(TOP.findall(raw)) != 1:
        raise ValueError("missing_or_ambiguous_global_top")
    blocks = [p.strip() for p in DASH.split(raw) if p.strip()]
    globals_ = [p for p in blocks if GLOBAL.search(p)]
    tops = [p for p in blocks if TOP.search(p)]
    if len(globals_) != 1 or len(tops) != 1:
        raise ValueError("invalid_report_partition")
    global_alloc, _, global_out, _, _ = num(globals_[0])
    top_n = int(TOP.findall(raw)[0])
    if not 1 <= top_n <= 10000:
        raise ValueError("unexpected_top_limit")
    metrics = [p for p in blocks if not GLOBAL.search(p)
               and not TOP.search(p)
               and any(rx.search(p) for rx in METRICS.values())]
    if not metrics or len(metrics) > top_n:
        raise ValueError("inconsistent_metric_rows")
    accepted_alloc = accepted_out = rejected_alloc = rejected_out = 0
    complete_numeric_rejected = malformed = rejected_exceeds = 0
    accepted_count = 0
    for item in metrics:
        matches = {key: rx.findall(item) for key, rx in METRICS.items()}
        if any(len(x) != 1 for x in matches.values()):
            malformed += 1
            continue
        a, o, r = (int(matches["alloc"][0][0]),
                   int(matches["out"][0][0]),
                   int(matches["realloc"][0]))
        if max(a, o, r) > CAP:
            # Do not mix malformed/overflow values into raw rejected sums.
            malformed += 1
            continue
        try:
            aa, _, oo, _, _ = num(item)
        except ValueError:
            complete_numeric_rejected += 1
            rejected_alloc += a
            rejected_out += o
            if o > a:
                rejected_exceeds += 1
        else:
            accepted_count += 1
            accepted_alloc += aa
            accepted_out += oo
    if accepted_out > global_out or accepted_alloc > global_alloc:
        raise ValueError("validated_count_exceeds_global")
    residual = global_out - accepted_out
    # These raw rejected per-row metrics are not an independent heap census.
    # A surplus cannot be "fixed" by arbitrarily subtracting duplicates.
    # A deficit cannot be simply called 466 true leaked objects.
    raw_row_out = accepted_out + rejected_out
    if raw_row_out < global_out:
        relation = "rejected_raw_less_than_residual"
    elif raw_row_out == global_out:
        relation = "rejected_raw_equals_residual"
    else:
        relation = "rejected_raw_exceeds_residual"
    truncated = int(len(metrics) >= top_n)
    validated_complete = int(
        not malformed and not complete_numeric_rejected
        and accepted_out == global_out and accepted_alloc == global_alloc
        and not truncated
    )
    return (
        "C545D_GIO_ETW_STACK_COVERAGE_BOUNDS,"
        f"arm={arm},global_alloc={global_alloc},global_out={global_out},"
        f"top_limit={top_n},metric_rows={len(metrics)},top_saturated={truncated},"
        f"accepted_rows={accepted_count},rejected_numeric_rows={complete_numeric_rejected},"
        f"rejected_malformed_rows={malformed},rejected_out_exceeds_alloc_rows={rejected_exceeds},"
        f"accepted_alloc_sum={accepted_alloc},accepted_out_sum={accepted_out},"
        f"rejected_raw_alloc_sum={rejected_alloc},rejected_raw_out_sum={rejected_out},"
        f"global_minus_accepted_out={residual},"
        f"raw_rows_minus_global_out={raw_row_out-global_out},"
        f"rejected_relation={relation},"
        f"validated_full_count_coverage={validated_complete},"
        "residual_is_not_proven_disjoint_objects=1,"
        "stack_member_not_causal_owner=1,"
        "allocation_lifetime_unproven=1,host_untouched=1,raw_uploaded=0"
    )

def sample(*, rej_out: int, global_out: int = 10, top: int = 2) -> str:
    return (
        f"GLOBAL ALLOCATIONS:\nAlloc : 40, 4.0 KB\nRealloc : 0\n"
        f"Outstanding : {global_out}, 1.0 KB\n"
        "-------------------------------------------\n"
        f"TOP {top}:\nAlloc : 40, 4.0 KB\nRealloc : 0\n"
        f"Outstanding : {global_out}, 1.0 KB\n"
        "-------------------------------------------\n"
        "ntdll.dll!RtlAllocateHeap\ngio-2.0-0.dll!f\n"
        "Alloc : 25, 2.5 KB\nRealloc : 0\nOutstanding : 6, 0.6 KB\n"
        "-------------------------------------------\n"
        "ntdll.dll!RtlAllocateHeap\nglib-2.0-0.dll!f\n"
        f"Alloc : 1, 0.2 KB\nRealloc : 0\nOutstanding : {rej_out}, 0.4 KB\n"
    )

def selftest() -> None:
    assert "rejected_relation=rejected_raw_equals_residual" in evaluate(sample(rej_out=4), "registry")
    assert "global_minus_accepted_out=4" in evaluate(sample(rej_out=4), "registry")
    assert "validated_full_count_coverage=0" in evaluate(sample(rej_out=4), "registry")
    assert "rejected_raw_less_than_residual" in evaluate(sample(rej_out=2), "registry")
    assert "rejected_raw_exceeds_residual" in evaluate(sample(rej_out=7), "registry")
    nochange = sample(rej_out=4).replace("GLOBAL ALLOCATIONS:", "GLOBAL ALLOCATIONS:")
    assert "top_saturated=1" in evaluate(nochange, "nochange")
    malformed = sample(rej_out=4).replace("Outstanding : 4, 0.4 KB", "Outstanding : unknown")
    assert "rejected_malformed_rows=1" in evaluate(malformed, "registry")
    negatives = [
        sample(rej_out=4).replace("GLOBAL ALLOCATIONS:", "HEADER:"),
        sample(rej_out=4).replace("TOP 2:", "TOP INVALID:"),
        sample(rej_out=4).replace("TOP 2:", "TOP 0:"),
        sample(rej_out=4).replace("TOP 2:", "TOP 10001:"),
        sample(rej_out=4).replace("TOP 2:", "TOP 1:"),
        sample(rej_out=4) + sample(rej_out=4),
        sample(rej_out=4).replace("Outstanding : 10, 1.0 KB", "Outstanding : 2, 1.0 KB", 1),
        sample(rej_out=4).replace("Alloc : 40, 4.0 KB", "Alloc : 1, 4.0 KB", 1),
    ]
    for i, invalid in enumerate(negatives):
        try:
            evaluate(invalid, "registry")
        except ValueError:
            continue
        raise AssertionError(f"unsafe_xperf_stack_coverage_sample_accepted:{i}")
    try:
        evaluate(sample(rej_out=4), "invalid")
    except ValueError:
        pass
    else:
        raise AssertionError("unapproved_arm_accepted")
    print("C545D_GIO_ETW_STACK_BOUNDS_SELFTEST_PASS,"
          "positive=6,negative=9,residual_not_proven_owner=1,"
          "unsafe_row_coercion=0,new_windows_runs=0,host_untouched=1")

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--report", type=Path)
    p.add_argument("--arm", choices=("nochange", "registry"))
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    if args.report is None or args.arm is None:
        p.error("--report and --arm required")
    if args.report.stat().st_size > MAX_REPORT:
        raise ValueError("bounded_runner_only")
    print(evaluate(args.report.read_text(encoding="utf-8-sig", errors="replace"),
                   args.arm))

if __name__ == "__main__":
    main()
