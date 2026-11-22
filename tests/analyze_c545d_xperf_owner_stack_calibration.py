#!/usr/bin/env python3
"""Strict local Xperf -a heap -stacks report owner extraction.

The actual Windows runner produces source stacks only WITHOUT -size.
This test uses the unique, noinline synthetic allocation symbol as
a structural separator, checking allocations/outstanding in that stack,
not claiming global source attribution of GIO. Raw stack names and pointers
are never logged or uploaded.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

OWNER = "c545d_synthetic_owner_alloc_360"
COUNTS = {
    "Alloc": re.compile(r"(?im)^\s*Alloc\s*:\s*(\d+)\s*,\s*(\d+(?:\.\d+)?)\s*KB\b"),
    "Realloc": re.compile(r"(?im)^\s*Realloc\s*:\s*(\d+)\s*(?:,|$)"),
    "Outstanding": re.compile(r"(?im)^\s*Outstanding\s*:\s*(\d+)\s*,\s*(\d+(?:\.\d+)?)\s*KB\b"),
}
SEPARATOR = re.compile(r"(?m)^\s*-{8,}\s*$")
OWNER_RE = re.compile(r"(?i)\b" + re.escape(OWNER) + r"\b")


def parse_stacks(text: str) -> str:
    if not isinstance(text, str) or not 0 < len(text) < 2_000_000:
        raise ValueError("stack_report_missing_or_oversized")
    if not ("GLOBAL ALLOCATIONS:" in text and re.search(r"\bTOP\s+\d+\s*:", text)):
        raise ValueError("no_global_or_top_summary")
    parts = [p for p in SEPARATOR.split(text) if p.strip()]
    owners: list[tuple[int, int, float]] = []
    for block in parts:
        if not OWNER_RE.search(block):
            continue
        if "GLOBAL ALLOCATIONS:" in block or re.search(r"\bTOP\s+\d+\s*:", block):
            raise ValueError("owner_name_in_summary_section")
        seen = {}
        for key, regex in COUNTS.items():
            matches = regex.findall(block)
            if len(matches) != 1:
                raise ValueError("owner_stack_missing_or_duplicated_metric")
            seen[key] = matches[0]
        alloc, kb = int(seen["Alloc"][0]), float(seen["Alloc"][1])
        outstanding, out_kb = int(seen["Outstanding"][0]), float(seen["Outstanding"][1])
        reallocs = int(seen["Realloc"][0])
        if alloc < outstanding or alloc <= 0 or reallocs != 0 or kb < 0 or out_kb < 0:
            raise ValueError("invalid_owner_stack_lifetime")
        owners.append((alloc, outstanding, out_kb))
    if not owners or len(owners) > 8:
        raise ValueError("owner_stack_missing_or_ambiguous")
    allocated = sum(n[0] for n in owners)
    outstanding = sum(n[1] for n in owners)
    out_size_kb = sum(n[2] for n in owners)
    if allocated != 64 or outstanding != 16:
        raise ValueError(
            f"owner_stack_calibration_mismatch,observed_alloc={allocated},"
            f"observed_outstanding={outstanding},owner_stack_groups={len(owners)}"
        )
    # Report is decimal KB to one place; exact requested bytes derive
    # from known 360-B fixture and in-scope block count, NOT KB rounding.
    if not (5.4 <= out_size_kb <= 6.0):
        raise ValueError("owner_stack_outstanding_size_inconsistent")
    return (
        "C545D_XPERF_OWNER_STACK_CALIBRATION_PASS,"
        f"owner_stack_groups={len(owners)},"
        "synthetic_source_alloc=64,synthetic_source_outstanding=16,"
        "synthetic_source_requested_out_bytes=5760,"
        "synthetic_owner_symbol_matched=1,"
        "source_stack_report_unfiltered=1,"
        "source_specific_etw_calibrated=1,"
        "real_GIO_owner_proven=0,host_untouched=1,raw_stack_uploaded=0"
    )


def selftest() -> None:
    fixture = (
        "GLOBAL ALLOCATIONS:\n"
        "Alloc : 84, 25.6 KB\n"
        "Realloc : 0\n"
        "Outstanding : 16, 5.6 KB\n"
        "------------------------------------------------\n"
        "TOP 100:\n"
        "Alloc : 84, 25.6 KB\n"
        "Realloc : 0\n"
        "Outstanding : 16, 5.6 KB\n"
        "------------------------------------------------\n"
        "ntdll.dll!RtlAllocateHeap\n"
        "c545d_owner_life_cal.exe!c545d_synthetic_owner_alloc_360\n"
        "Alloc : 64, 22.5 KB\n"
        "Realloc : 0\n"
        "Outstanding : 16, 5.6 KB\n"
        "------------------------------------------------\n"
        "ntdll.dll!RtlAllocateHeap\n"
        "Alloc : 20, 3.1 KB\n"
        "Realloc : 0\n"
        "Outstanding : 0, 0.0 KB\n"
    )
    assert "synthetic_source_outstanding=16" in parse_stacks(fixture)
    broken = [
        fixture.replace("c545d_synthetic_owner_alloc_360", "other_function"),
        fixture.replace("Alloc : 64, 22.5 KB", "Alloc : 63, 22.5 KB"),
        fixture.replace("Outstanding : 16, 5.6 KB\n------------------------------------------------\nntdll.dll!RtlAllocateHeap\nAlloc : 20", "Outstanding : 15, 5.6 KB\n------------------------------------------------\nntdll.dll!RtlAllocateHeap\nAlloc : 20"),
        fixture.replace("Realloc : 0\nOutstanding : 16, 5.6 KB\n------------------------------------------------\nntdll.dll!RtlAllocateHeap\nAlloc : 20", "Realloc : 1\nOutstanding : 16, 5.6 KB\n------------------------------------------------\nntdll.dll!RtlAllocateHeap\nAlloc : 20"),
        fixture.replace("TOP 100:", "TOP MISSING:"),
        fixture.replace("c545d_synthetic_owner_alloc_360", OWNER + "\nAlloc : 64, 22.5 KB"),
        fixture.replace("Outstanding : 16, 5.6 KB\n------------------------------------------------\nntdll.dll!RtlAllocateHeap\nAlloc : 20", "Outstanding : 16, 12.0 KB\n------------------------------------------------\nntdll.dll!RtlAllocateHeap\nAlloc : 20"),
    ]
    for i, v in enumerate(broken):
        try:
            parse_stacks(v)
        except ValueError:
            continue
        raise AssertionError(f"owner_report_corruption_accepted,index={i}")
    print(
        "C545D_XPERF_OWNER_STACK_SELFTEST_PASS,positive=1,negative=7,"
        "owner_specific=1,raw_stack_uploaded=0,real_GIO_tested=0"
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--report", type=Path)
    a = p.parse_args()
    if a.selftest:
        selftest()
    elif a.report:
        print(parse_stacks(a.report.read_text(encoding="utf-8-sig", errors="replace")))
    else:
        p.error("--selftest or --report required")


if __name__ == "__main__":
    main()
