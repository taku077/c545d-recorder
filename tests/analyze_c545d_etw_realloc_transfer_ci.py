#!/usr/bin/env python3
"""Sanitized real Xperf realloc-stack transfer calibration, not leak detection.

Runs only on private synthetic Windows2022 ETW report. A zero-Alloc/nonzero-
Outstanding Xperf call-stack group is reported as a grouping observation,
NOT as source-owned leaked allocations. Never emit raw stacks or addresses.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
from analyze_c545d_gio_etw_stack_cohorts_ci import (
    DASH, GLOBAL, TOP, METRICS, num
)

SOURCES = ("c545d_ci_alloc_360", "c545d_ci_realloc_720")


def analyze(raw: str) -> str:
    if not isinstance(raw, str) or not 100 <= len(raw) <= 2_000_000:
        raise ValueError("synthetic_stack_report_missing_or_oversized")
    if len(GLOBAL.findall(raw)) != 1 or len(TOP.findall(raw)) != 1:
        raise ValueError("unexpected_heap_summary_shape")
    blocks = [x.strip() for x in DASH.split(raw) if x.strip()]
    globals_ = [x for x in blocks if GLOBAL.search(x)]
    if len(globals_) != 1:
        raise ValueError("ambiguous_heap_summary")
    ga, _, go, _, _ = num(globals_[0])
    found: dict[str, list[tuple[int,int,int]]] = {x: [] for x in SOURCES}
    for b in blocks:
        if GLOBAL.search(b) or TOP.search(b):
            continue
        matches = {k: rx.findall(b) for k, rx in METRICS.items()}
        if not any(matches.values()):
            continue
        if any(len(v)!=1 for v in matches.values()):
            raise ValueError("incomplete_stack_row")
        alloc = int(matches["alloc"][0][0])
        outstanding = int(matches["out"][0][0])
        realloc = int(matches["realloc"][0])
        if min(alloc, outstanding, realloc) < 0:
            raise ValueError("invalid_raw_count")
        for name in SOURCES:
            if re.search(r"\b" + re.escape(name) + r"\b", b):
                found[name].append((alloc, outstanding, realloc))
    for name in SOURCES:
        if not found[name] or len(found[name]) > 16:
            raise ValueError("missing_or_duplicated_synthetic_owner")
    src_a = found[SOURCES[0]]
    src_r = found[SOURCES[1]]
    a_alloc, a_out, a_realloc = map(sum, zip(*src_a))
    r_alloc, r_out, r_realloc = map(sum, zip(*src_r))
    # The *source fixture* performs 64 allocations and 16 reallocations,
    # but Xperf's grouping may attribute outstanding blocks differently.
    # Do not make one unverified grouping interpretation a hard PASS.
    if a_alloc != 64:
        raise ValueError("known_original_source_alloc_unverified")
    if a_realloc > 16 or r_realloc > 16:
        raise ValueError("impossible_realloc_group_counts")
    if r_out > go or a_out > go:
        raise ValueError("source_group_exceeds_global")
    return (
        "C545D_ETW_REALLOC_STACK_GROUP_DIAGNOSTIC,"
        f"global_alloc={ga},global_out={go},"
        f"original_source_rows={len(src_a)},"
        f"original_source_alloc={a_alloc},original_source_out={a_out},"
        f"original_source_realloc={a_realloc},"
        f"realloc_source_rows={len(src_r)},"
        f"realloc_source_alloc={r_alloc},realloc_source_out={r_out},"
        f"realloc_source_realloc={r_realloc},"
        f"realloc_source_zeroalloc_positiveout={int(r_alloc==0 and r_out>0)},"
        "grouping_not_proof_of_memory_leak=1,"
        "real_gio_owner_unproven=1,source_groups_not_disjoint_proven=1,"
        "CI_only=1,raw_uploaded=0"
    )

def fixture(realloc_alloc: int, realloc_out: int) -> str:
    return (
        "GLOBAL ALLOCATIONS:\nAlloc : 80, 30.0 KB\n"
        "Realloc : 16\nOutstanding : 16, 11.3 KB\n"
        "-----------------------------------------\n"
        "TOP 3:\nAlloc : 80, 30.0 KB\n"
        "Realloc : 16\nOutstanding : 16, 11.3 KB\n"
        "-----------------------------------------\n"
        "c545d_realloc_cal.exe!c545d_ci_alloc_360\n"
        "Alloc : 64, 22.5 KB\nRealloc : 0\nOutstanding : 0, 0.0 KB\n"
        "-----------------------------------------\n"
        "c545d_realloc_cal.exe!c545d_ci_realloc_720\n"
        f"Alloc : {realloc_alloc}, 6.0 KB\nRealloc : 16\n"
        f"Outstanding : {realloc_out}, 6.0 KB\n"
    )

def selftest() -> None:
    value = analyze(fixture(0,16))
    assert "realloc_source_zeroalloc_positiveout=1" in value
    assert "realloc_source_alloc=0,realloc_source_out=16" in value
    assert "realloc_source_zeroalloc_positiveout=0" in analyze(fixture(16,16))
    bad = [
        fixture(0,16).replace("GLOBAL ALLOCATIONS:", "INVALID:"),
        fixture(0,16).replace("c545d_ci_realloc_720", "unknown_symbol"),
        fixture(0,16).replace("c545d_ci_alloc_360", "unknown_symbol"),
        fixture(0,16).replace("Alloc : 64, 22.5 KB", "Alloc : 63, 22.5 KB"),
        fixture(0,16).replace("Realloc : 16\nOutstanding : 16, 6.0 KB",
                              "Realloc : 17\nOutstanding : 16, 6.0 KB"),
        fixture(0,16).replace("Outstanding : 16, 6.0 KB",
                              "Outstanding : 17, 6.0 KB"),
        fixture(0,16) + fixture(0,16),
        fixture(0,16).replace("TOP 3:", "TOP ??"),
    ]
    for i, source in enumerate(bad):
        try: analyze(source)
        except ValueError: continue
        raise AssertionError(f"corrupted_realloc_source_report_accepted:{i}")
    print("C545D_ETW_REALLOC_DIAGNOSTIC_SELFTEST_PASS,positive=2,negative=8,"
          "source_scope_only=1,no_runtime_GIO=1,raw_symbols_uploaded=0")

def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--report",type=Path)
    a=p.parse_args()
    if a.selftest:
        selftest()
        return
    if a.report is None or a.report.stat().st_size > 2_000_000:
        raise ValueError("missing_or_oversized_local_report")
    print(analyze(a.report.read_text("utf-8-sig",errors="replace")))

if __name__=="__main__":
    main()
