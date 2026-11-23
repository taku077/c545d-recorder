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

def evaluate(raw: str, arm: str, *, requested_top: int | None = None) -> str:
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
        raise ValueError("unexpected_reported_top_rows")
    if requested_top is not None and (
            not 1 <= requested_top <= 10000 or top_n > requested_top):
        raise ValueError("inconsistent_requested_vs_reported_top")
    # Xperf's TOP header may display the number of groups actually emitted,
    # not the requested -top argument: -top 8192 emitted TOP 1164 on the
    # actual 2026-11-23 disposable Windows GIO report. An equality between
    # TOP header and row count alone DOES NOT prove truncation.
    requested_known = int(requested_top is not None)
    cap_reached = int(top_n == requested_top) if requested_known else -1
    metrics = [p for p in blocks if not GLOBAL.search(p)
               and not TOP.search(p)
               and any(rx.search(p) for rx in METRICS.values())]
    if not metrics or len(metrics) > top_n:
        raise ValueError("inconsistent_metric_rows")
    accepted_alloc = accepted_out = rejected_alloc = rejected_out = 0
    complete_numeric_rejected = malformed = rejected_exceeds = 0
    rejected_realloc_sum = 0
    realloc_compatible_rows = realloc_incompatible_rows = 0
    realloc_compatible_out_sum = realloc_incompatible_out_sum = 0
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
            rejected_realloc_sum += r
            if o > a:
                rejected_exceeds += 1
                if a + r >= o:
                    realloc_compatible_rows += 1
                    realloc_compatible_out_sum += o
                else:
                    realloc_incompatible_rows += 1
                    realloc_incompatible_out_sum += o
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
    grouped_raw_alloc = accepted_alloc + rejected_alloc
    grouped_raw_out = accepted_out + rejected_out
    raw_group_totals_reconcile = int(
        not malformed and grouped_raw_alloc == global_alloc and
        grouped_raw_out == global_out and requested_known and not cap_reached
    )
    validated_complete = int(
        raw_group_totals_reconcile and not complete_numeric_rejected
    )
    return (
        "C545D_GIO_ETW_STACK_COVERAGE_BOUNDS,"
        f"arm={arm},global_alloc={global_alloc},global_out={global_out},"
        f"top_header_rows={top_n},requested_top={requested_top or 0},"
        f"requested_top_known={requested_known},"
        f"metric_rows={len(metrics)},requested_cap_reached={cap_reached},"
        "top_header_equal_metric_rows_not_truncation_proof=1,"
        f"accepted_rows={accepted_count},rejected_numeric_rows={complete_numeric_rejected},"
        f"rejected_malformed_rows={malformed},rejected_out_exceeds_alloc_rows={rejected_exceeds},"
        f"accepted_alloc_sum={accepted_alloc},accepted_out_sum={accepted_out},"
        f"rejected_raw_alloc_sum={rejected_alloc},rejected_raw_out_sum={rejected_out},"
        f"rejected_raw_realloc_sum={rejected_realloc_sum},"
        f"out_exceeds_alloc_realloc_compatible_rows={realloc_compatible_rows},"
        f"out_exceeds_alloc_realloc_incompatible_rows={realloc_incompatible_rows},"
        f"out_exceeds_alloc_realloc_compatible_out={realloc_compatible_out_sum},"
        f"out_exceeds_alloc_realloc_incompatible_out={realloc_incompatible_out_sum},"
        f"all_out_exceeds_alloc_rows_realloc_compatible={int(rejected_exceeds>0 and realloc_incompatible_rows==0)},"
        f"global_minus_accepted_out={residual},"
        f"raw_rows_minus_global_out={raw_row_out-global_out},"
        f"rejected_relation={relation},"
        f"raw_group_totals_numeric_reconcile={raw_group_totals_reconcile},"
        f"validated_full_count_coverage={validated_complete},"
        "residual_is_not_proven_disjoint_objects=1,"
        "stack_member_not_causal_owner=1,"
        "allocation_lifetime_unproven=1,host_untouched=1,raw_uploaded=0"
    )

def sample(*, rej_out: int, global_out: int = 10, top: int = 2,
           rej_realloc: int = 0) -> str:
    return (
        f"GLOBAL ALLOCATIONS:\nAlloc : 40, 4.0 KB\nRealloc : {rej_realloc}\n"
        f"Outstanding : {global_out}, 1.0 KB\n"
        "-------------------------------------------\n"
        f"TOP {top}:\nAlloc : 40, 4.0 KB\nRealloc : {rej_realloc}\n"
        f"Outstanding : {global_out}, 1.0 KB\n"
        "-------------------------------------------\n"
        "ntdll.dll!RtlAllocateHeap\ngio-2.0-0.dll!f\n"
        "Alloc : 25, 2.5 KB\nRealloc : 0\nOutstanding : 6, 0.6 KB\n"
        "-------------------------------------------\n"
        "ntdll.dll!RtlAllocateHeap\nglib-2.0-0.dll!f\n"
        f"Alloc : 1, 0.2 KB\nRealloc : {rej_realloc}\nOutstanding : {rej_out}, 0.4 KB\n"
    )

def selftest() -> None:
    assert "rejected_relation=rejected_raw_equals_residual" in evaluate(sample(rej_out=4), "registry")
    assert "global_minus_accepted_out=4" in evaluate(sample(rej_out=4), "registry")
    assert "validated_full_count_coverage=0" in evaluate(sample(rej_out=4), "registry")
    assert "rejected_raw_less_than_residual" in evaluate(sample(rej_out=2), "registry")
    assert "rejected_raw_exceeds_residual" in evaluate(sample(rej_out=7), "registry")
    compatible = evaluate(sample(rej_out=4, rej_realloc=3), "registry", requested_top=8192)
    assert "rejected_raw_realloc_sum=3" in compatible
    assert "out_exceeds_alloc_realloc_compatible_rows=1" in compatible
    assert "all_out_exceeds_alloc_rows_realloc_compatible=1" in compatible
    incompatible = evaluate(sample(rej_out=4, rej_realloc=2), "registry", requested_top=8192)
    assert "out_exceeds_alloc_realloc_incompatible_rows=1" in incompatible
    assert "all_out_exceeds_alloc_rows_realloc_compatible=0" in incompatible
    nochange = sample(rej_out=4).replace("GLOBAL ALLOCATIONS:", "GLOBAL ALLOCATIONS:")
    assert "requested_cap_reached=1" in evaluate(nochange, "nochange", requested_top=2)
    assert "requested_cap_reached=0" in evaluate(nochange, "nochange", requested_top=8192)
    assert "requested_cap_reached=-1" in evaluate(nochange, "nochange")
    fullcount = sample(rej_out=4).replace("Alloc : 40, 4.0 KB",
                                           "Alloc : 26, 4.0 KB")
    assert "raw_group_totals_numeric_reconcile=1" in evaluate(
        fullcount, "registry", requested_top=8192)
    assert "validated_full_count_coverage=0" in evaluate(
        fullcount, "registry", requested_top=8192)
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
        evaluate(sample(rej_out=4), "registry", requested_top=1)
    except ValueError:
        pass
    else:
        raise AssertionError("reported_top_exceeds_requested_cap_accepted")
    try:
        evaluate(sample(rej_out=4), "invalid")
    except ValueError:
        pass
    else:
        raise AssertionError("unapproved_arm_accepted")
    print("C545D_GIO_ETW_STACK_BOUNDS_SELFTEST_PASS,"
          "positive=12,negative=10,residual_not_proven_owner=1,"
          "unsafe_row_coercion=0,new_windows_runs=0,host_untouched=1")

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--report", type=Path)
    p.add_argument("--arm", choices=("nochange", "registry"))
    p.add_argument("--requested-top", type=int)
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    if args.report is None or args.arm is None:
        p.error("--report and --arm required")
    if args.report.stat().st_size > MAX_REPORT:
        raise ValueError("bounded_runner_only")
    print(evaluate(args.report.read_text(encoding="utf-8-sig", errors="replace"),
                   args.arm, requested_top=args.requested_top))

if __name__ == "__main__":
    main()
