#!/usr/bin/env python3
"""Read independent Xperf -a heap -totals report: ONLY numeric data leaves CI.

This does not claim ownership. It can still give a valid outstanding
*count and rounded size* when an Xperf full-stack parser rejects complex
registry activity. All heap handles, stack rows and paths stay local.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from analyze_c545d_xperf_size360_totals_calibration import parse_totals

def summarize(content: str, arm: str) -> str:
    if arm not in ("nochange", "registry"):
        raise ValueError("unapproved_arm")
    result = parse_totals(content)
    return (
        "C545D_GIO_ETW_HEAP_TOTALS_NUMERIC,"
        f"arm={arm},total_alloc={result['alloc']},"
        f"total_out={result['outstanding']},"
        f"out_kb_tenths={int(result['outstanding_kb']*10)},"
        f"heap_count={result['heaps']},"
        "source_allocation_owner_proven=0,"
        "rounded_kb_not_exact_bytes=1,"
        "expected_lifetime_unproven=1,"
        "global_async_quiet_unproven=1,"
        "raw_handles_uploaded=0,host_untouched=1"
    )

def selftest() -> None:
    good = ("Alloc#, Alloc KB, Out#, Out KB, Realloc#, Extents KB, Out Ext KB, Heap Handle\n"
            "12, 4.1, 3, 0.8, 0, 5.1, 5.0, TOTAL\n"
            "12, 4.1, 3, 0.8, 0, 5.1, 5.0, 0x1234\n")
    assert "total_out=3" in summarize(good, "registry")
    assert "total_out=3" in summarize(good, "nochange")
    broken = [
        good.replace("Out#", "Missing#"),
        good.replace("12, 4.1, 3", "12, 4.1, 13", 1),
        good.replace("12, 4.1, 3", "11, 4.1, 3", 1),
        good.replace("TOTAL", "0x5678"),
        good.replace("0x1234", "TOTAL"),
        good + good,
    ]
    for i, text in enumerate(broken):
        try: summarize(text, "registry")
        except ValueError: continue
        raise AssertionError(f"unsafe_heap_total_fixture_accepted,index={i}")
    print("C545D_GIO_ETW_HEAP_TOTALS_SELFTEST_PASS,positive=2,negative=6,no_raw_addresses=1")

def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--report", type=Path)
    p.add_argument("--arm", choices=("nochange","registry"))
    a=p.parse_args()
    if a.selftest: selftest();return
    if a.report is None or a.arm is None: p.error("--arm and --report required")
    print(summarize(a.report.read_text(encoding="utf-8-sig",errors="replace"), a.arm))

if __name__=="__main__":
    main()
