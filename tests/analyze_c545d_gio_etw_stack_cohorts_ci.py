#!/usr/bin/env python3
"""CI-only Xperf outstanding allocations grouped by bounded source-stack cohorts.

Input is a LOCAL disposable Windows runner's UNFILTERED Xperf -a heap -stacks
report, never an uploaded ETL nor a module-frame occurrence histogram.
Only allowlisted numeric aggregate fields leave the runner. A stack containing
GIO/GLib is a *call-stack cohort*, not automatically the allocation's causal
owner. Outstanding at ETW stop is not automatically a leak.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

DASH = re.compile(r"(?m)^\s*-{8,}\s*$")
METRICS = {
    "alloc": re.compile(r"(?im)^\s*Alloc\s*:\s*(\d+)\s*,\s*(\d+(?:\.\d+)?)\s*KB\s*$"),
    "out": re.compile(r"(?im)^\s*Outstanding\s*:\s*(\d+)\s*,\s*(\d+(?:\.\d+)?)\s*KB\s*$"),
    "realloc": re.compile(r"(?im)^\s*Realloc\s*:\s*(\d+)\s*$"),
}
TOP = re.compile(r"(?im)^\s*TOP\s+(\d+)\s*:")
GLOBAL = re.compile(r"(?im)^\s*GLOBAL\s+ALLOCATIONS\s*:")
FRAME = re.compile(r"(?im)^\s*([a-z0-9_.-]+)(?:\.dll|\.exe)?!([^\s]+)")
GROUPS = ("GIO", "GLIB", "GOBJECT", "COM_WINRT", "PROBE", "OTHER")
MAX_REPORT = 16 * 1024 * 1024
CAP = 500_000_000

def num(section: str) -> tuple[int, Decimal, int, Decimal, int]:
    vals = {}
    for key, rx in METRICS.items():
        matches = rx.findall(section)
        if len(matches) != 1:
            raise ValueError("heap_stack_metric_missing_or_duplicated")
        vals[key] = matches[0]
    a, ak = vals["alloc"]
    o, ok = vals["out"]
    r = vals["realloc"]
    if max(int(a), int(o), int(r)) > CAP or int(o) > int(a):
        raise ValueError("invalid_heap_counts")
    try:
        akb, okb = Decimal(ak), Decimal(ok)
    except InvalidOperation as exc:
        raise ValueError("invalid_heap_kb") from exc
    if akb < 0 or okb < 0 or okb > akb + Decimal("0.2"):
        raise ValueError("invalid_heap_sizes")
    return int(a), akb, int(o), okb, int(r)

def cohort(section: str) -> str:
    frames = FRAME.findall(section)
    # Never emit the actual symbol or module string in user-visible output.
    if not frames:
        return "OTHER"
    # More specific GIO and GLib stack inclusion wins. These indicate the
    # stack *contains* the named module and DO NOT establish sole ownership.
    modules = [m.lower() for m, func in frames]
    if any(m.startswith("gio-2.0") for m in modules):
        return "GIO"
    if any(m.startswith("glib-2.0") for m in modules):
        return "GLIB"
    if any(m.startswith("gobject-2.0") for m in modules):
        return "GOBJECT"
    if any(m.startswith(("combase", "windows.storage", "twinapi",
                         "windows.application", "windows.foundation")) for m in modules):
        return "COM_WINRT"
    if any(m.startswith("c545d_disposable_scanfree") for m in modules):
        return "PROBE"
    return "OTHER"

def analyze(source: str, *, arm: str) -> str:
    if arm not in {"nochange", "registry"}:
        raise ValueError("not_a_disposable_control_arm")
    if not isinstance(source, str) or not (100 <= len(source) <= MAX_REPORT):
        raise ValueError("invalid_or_oversized_stack_report")
    if len(GLOBAL.findall(source)) != 1 or len(TOP.findall(source)) != 1:
        raise ValueError("missing_or_ambiguous_global_top_section")
    parts = [x.strip() for x in DASH.split(source) if x.strip()]
    global_sections = [p for p in parts if GLOBAL.search(p)]
    if len(global_sections) != 1:
        raise ValueError("ambiguous_global_section")
    # Xperf may place TOP in the next partition, or combine it with
    # the first row header; only strictly parsed metric-containing rows count.
    top_sections = [p for p in parts if TOP.search(p)]
    if len(top_sections) != 1:
        raise ValueError("ambiguous_top_section")
    glob = num(global_sections[0])
    if glob[0] == 0:
        raise ValueError("no_allocations_recorded")
    seen = defaultdict(lambda: [0, Decimal(0), 0, Decimal(0), 0, 0])
    rowcount = 0
    for part in parts:
        if GLOBAL.search(part) or TOP.search(part):
            continue
        if not any(rx.search(part) for rx in METRICS.values()):
            continue
        a, ak, o, ok, r = num(part)
        if a == 0:
            continue
        group = cohort(part)
        dest = seen[group]
        dest[0] += a
        dest[1] += ak
        dest[2] += o
        dest[3] += ok
        dest[4] += r
        dest[5] += 1
        rowcount += 1
        if rowcount > 8192:
            raise ValueError("stack_rows_exceeded")
    if rowcount == 0:
        raise ValueError("no_source_stack_rows")
    all_a = sum(z[0] for z in seen.values())
    all_o = sum(z[2] for z in seen.values())
    all_kb = sum((z[3] for z in seen.values()), Decimal(0))
    if all_a > glob[0] or all_o > glob[2] or all_kb > glob[3] + Decimal("0.2") * rowcount:
        raise ValueError("aggregate_source_rows_exceed_global")
    # Completeness cannot be concluded when Xperf -top is truncated or
    # when repeated/overlapping stacks have not been reconciled.
    complete = int(all_a == glob[0] and all_o == glob[2])
    fields = [
        "C545D_GIO_ETW_OWNER_STACK_COHORT",
        f"arm={arm}",
        f"global_alloc={glob[0]}",
        f"global_out={glob[2]}",
        f"global_out_kb_tenths={int(glob[3]*10)}",
        f"parsed_stack_rows={rowcount}",
        f"parsed_alloc={all_a}",
        f"parsed_out={all_o}",
        f"allocation_count_coverage_complete={complete}",
        "window_preworkload_fenced=1",
        "global_async_quiescence_proven=0",
        "stack_contains_module_not_proven_allocation_owner=1",
        "private_usage_attribution_proven=0",
    ]
    for group in GROUPS:
        z = seen[group]
        fields.extend((
            f"{group.lower()}_rows={z[5]}",
            f"{group.lower()}_alloc={z[0]}",
            f"{group.lower()}_out={z[2]}",
            f"{group.lower()}_out_kb_tenths={int(z[3]*10)}",
        ))
    fields += ["raw_report_uploaded=0", "real_camera=0", "real_host_untouched=1"]
    return ",".join(fields)


def selftest() -> None:
    head = ("GLOBAL ALLOCATIONS:\nAlloc : 12, 2.0 KB\n"
            "Realloc : 0\nOutstanding : 3, 0.5 KB\n"
            "----------------------------------\n"
            "TOP 1024:\nAlloc : 12, 2.0 KB\n"
            "Realloc : 0\nOutstanding : 3, 0.5 KB\n"
            "----------------------------------\n")
    gio = ("ntdll.dll!RtlAllocateHeap\n"
           "gio-2.0-0.dll!g_win32_registry_key_watch\n"
           "Alloc : 7, 1.2 KB\nRealloc : 0\nOutstanding : 2, 0.3 KB\n")
    other = ("ntdll.dll!RtlAllocateHeap\n"
             "kernelbase.dll!HeapAlloc\n"
             "Alloc : 5, 0.8 KB\nRealloc : 0\nOutstanding : 1, 0.2 KB\n")
    valid = head + gio + "----------------------------------\n" + other
    assert "gio_out=2" in analyze(valid, arm="registry")
    assert "allocation_count_coverage_complete=1" in analyze(valid, arm="registry")
    clipped = valid.replace("TOP 1024:", "TOP 1:").replace(
        "----------------------------------\n"+other, "")
    result = analyze(clipped, arm="nochange")
    assert "allocation_count_coverage_complete=0" in result
    assert "parsed_out=2" in result
    invalid = [
        valid.replace("GLOBAL ALLOCATIONS:", "SUMMARY:"),
        valid.replace("TOP 1024:", "TOP XX:"),
        valid.replace("Outstandi","Outstannn"),
        valid.replace("Alloc : 7, 1.2 KB", "Alloc : 70, 1.2 KB"),
        valid.replace("Outstanding : 2, 0.3 KB", "Outstanding : 8, 0.3 KB"),
        valid.replace("Alloc : 12, 2.0 KB", "Alloc : 1, 2.0 KB", 1),
        valid+valid,
        valid.replace("Realloc : 0", "Realloc : bad", 1),
    ]
    for index, value in enumerate(invalid):
        try:
            analyze(value, arm="registry")
        except ValueError:
            continue
        raise AssertionError(f"invalid_etw_stack_accepted,index={index}")
    print("C545D_GIO_ETW_STACK_COHORT_SELFTEST_PASS,positive=2,negative=8,"
          "source_stack_coverage_gated=1,unknown_frames_not_discarded=1,"
          "raw_symbols_output=0,real_GIO_tested=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--report", type=Path)
    p.add_argument("--arm", choices=("nochange", "registry"))
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    if a.report is None or a.arm is None:
        p.error("--arm and --report required")
    raw = a.report.read_text(encoding="utf-8-sig", errors="replace")
    print(analyze(raw, arm=a.arm))

if __name__ == "__main__":
    main()
