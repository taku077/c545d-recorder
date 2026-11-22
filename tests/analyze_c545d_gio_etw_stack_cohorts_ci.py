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
        "window_late4_fenced=1,capture_includes_first12_cycles=0",
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


REASONS = {
    "invalid_or_oversized_stack_report", "missing_or_ambiguous_global_top_section",
    "ambiguous_global_section", "heap_stack_metric_missing_or_duplicated",
    "invalid_heap_counts", "invalid_heap_kb", "invalid_heap_sizes",
    "no_allocations_recorded", "ambiguous_top_section",
    "no_source_stack_rows", "stack_rows_exceeded",
    "aggregate_source_rows_exceed_global"
}
def diagnose(raw: str, arm: str) -> str:
    # A diagnostic is not a leak claim; its fields are strictly numerical
    # and enum-only, no stacks, paths, registry keys, symbols or addresses.
    reason = "NONE"
    try:
        analyze(raw, arm=arm)
    except ValueError as exc:
        candidate = str(exc).split(",", 1)[0]
        reason = candidate if candidate in REASONS else "OTHER_REJECTED"
    parts = [x.strip() for x in DASH.split(raw) if x.strip()]
    global_parts = [x for x in parts if GLOBAL.search(x)]
    glob_alloc = glob_out = glob_valid = 0
    if len(global_parts) == 1:
        try:
            metrics = num(global_parts[0])
            glob_alloc, glob_out, glob_valid = metrics[0], metrics[2], 1
        except ValueError:
            pass
    # The real late-window registry #45053779999 has 619727 Alloc /
    # 16061 Out in the independent totals, but a top-1024 stack row
    # violated the numeric invariant. Inspect ONLY aggregate counts of
    # the rejected row types. Never print a source frame, pointer, path,
    # individual size or private ETL.
    numeric_rows = 0
    rejected_count_rows = 0
    rows_out_exceeds_alloc = 0
    rows_cap_exceeded = 0
    rows_missing_field = 0
    rows_invalid_kb = 0
    accepted_alloc = 0
    accepted_out = 0
    accepted_out_kb_tenths = 0
    partial_cohorts = defaultdict(lambda: [0, 0, 0])
    for block in parts:
        if GLOBAL.search(block) or TOP.search(block):
            continue
        if not any(rx.search(block) for rx in METRICS.values()):
            continue
        numeric_rows += 1
        fields = {key: rx.findall(block) for key, rx in METRICS.items()}
        if any(len(v) != 1 for v in fields.values()):
            rows_missing_field += 1
            continue
        alloc = int(fields["alloc"][0][0])
        out = int(fields["out"][0][0])
        realloc = int(fields["realloc"][0])
        if out > alloc:
            rows_out_exceeds_alloc += 1
        if max(alloc, out, realloc) > CAP:
            rows_cap_exceeded += 1
        try:
            a, _, o, kb, _ = num(block)
        except ValueError as exc:
            rejected_count_rows += 1
            if str(exc) in {"invalid_heap_kb", "invalid_heap_sizes"}:
                rows_invalid_kb += 1
        else:
            accepted_alloc += a
            accepted_out += o
            accepted_out_kb_tenths += int(kb * 10)
            bucket = partial_cohorts[cohort(block)]
            bucket[0] += a
            bucket[1] += o
            bucket[2] += int(kb * 10)
    # A top-1024 row report is not a complete census merely because the
    # standalone heap totals table is complete. This is a coverage gap.
    top_k = int(TOP.findall(raw)[0]) if len(TOP.findall(raw)) == 1 else 0
    top_limit_may_truncate = int(top_k > 0 and numeric_rows >= top_k)
    unresolved_valid = int(bool(glob_valid) and accepted_out <= glob_out)
    unknown_out = glob_out - accepted_out if unresolved_valid else 0
    # This is a numeric LOWER BOUND among well-formed rows only; source
    # frame inclusion is not ownership, and dropped rows/top-k truncation
    # MUST remain an explicit unknown rather than being silently 'OTHER'.
    partial = "".join(
        f",{g.lower()}_wellformed_alloc={partial_cohorts[g][0]}"
        f",{g.lower()}_wellformed_out={partial_cohorts[g][1]}"
        for g in GROUPS
    )
    return (
        "C545D_GIO_ETW_STACK_PARSE_DIAGNOSTIC,"
        f"arm={arm},reason={reason},global_headers={len(GLOBAL.findall(raw))},"
        f"top_headers={len(TOP.findall(raw))},"
        f"dash_parts={len(parts)},"
        f"alloc_lines={len(METRICS['alloc'].findall(raw))},"
        f"out_lines={len(METRICS['out'].findall(raw))},"
        f"realloc_lines={len(METRICS['realloc'].findall(raw))},"
        f"global_valid={glob_valid},global_alloc={glob_alloc},global_out={glob_out},"
        f"numeric_rows={numeric_rows},rejected_rows={rejected_count_rows},"
        f"rows_out_exceeds_alloc={rows_out_exceeds_alloc},"
        f"rows_cap_exceeded={rows_cap_exceeded},"
        f"rows_missing_field={rows_missing_field},rows_invalid_kb={rows_invalid_kb},"
        f"accepted_alloc={accepted_alloc},accepted_out={accepted_out},"
        f"accepted_out_kb_tenths={accepted_out_kb_tenths},"
        f"top_limit={top_k},top_limit_may_truncate={top_limit_may_truncate},"
        f"unattributed_out={unknown_out},unattributed_out_valid={unresolved_valid},"
        f"wellformed_cohort_summary_not_owner=1{partial},"
        "full_source_classification_proven=0,raw_uploaded=0"
    )

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
    assert "reason=missing_or_ambiguous_global_top_section" in diagnose(valid.replace("TOP 1024:", "MISSING:"), "registry")
    # Synthetic top-limited row with Out > Alloc must remain unclassified.
    bad_source = valid.replace("Alloc : 7, 1.2 KB", "Alloc : 1, 1.2 KB")
    diagnostic = diagnose(bad_source, "registry")
    assert "reason=invalid_heap_counts" in diagnostic
    assert "rows_out_exceeds_alloc=1" in diagnostic
    assert "rejected_rows=1" in diagnostic
    assert "full_source_classification_proven=0" in diagnostic
    assert "top_limit_may_truncate=0" in diagnostic
    assert "unattributed_out=2" in diagnostic
    assert "gio_wellformed_out=0" in diagnostic
    assert "other_wellformed_out=1" in diagnostic
    print("C545D_GIO_ETW_STACK_COHORT_SELFTEST_PASS,positive=2,negative=8,"
          "source_stack_coverage_gated=1,unknown_frames_not_discarded=1,"
          "raw_symbols_output=0,real_GIO_tested=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--diagnose", action="store_true")
    p.add_argument("--report", type=Path)
    p.add_argument("--arm", choices=("nochange", "registry"))
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    if a.report is None or a.arm is None:
        p.error("--arm and --report required")
    raw = a.report.read_text(encoding="utf-8-sig", errors="replace")
    print(diagnose(raw, arm=a.arm) if a.diagnose else analyze(raw, arm=a.arm))

if __name__ == "__main__":
    main()
