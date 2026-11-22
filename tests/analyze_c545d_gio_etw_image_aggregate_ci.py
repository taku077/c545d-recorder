#!/usr/bin/env python3
"""Local-only Xperf heap -images grouped outstanding allocation accounting.

Designed as an INDEPENDENT fallback when the top-1024 full-stack report is
truncated or contains a structurally invalid metric row. This deliberately
reports grouped top-frame image membership, NOT exact allocating function,
and never publishes module names, addresses, paths, or raw report lines.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
import re
from analyze_c545d_gio_etw_stack_cohorts_ci import (
    DASH, GLOBAL, TOP, METRICS, CAP, num
)

FAMILIES = ("gio", "glib", "gobject", "com_winrt", "probe", "other")
MAX_REPORT = 16 * 1024 * 1024


def family(section: str) -> str:
    # Images are only *top stack frame modules after default culling*.
    # These regexes intentionally use an allowlisted public module family,
    # not an allocation owner symbol or a raw module string.
    text = section.lower()
    for name, prefix in (
        ("gio", r"\bgio-2\.0-0(?:\.dll)?\b"),
        ("glib", r"\bglib-2\.0-0(?:\.dll)?\b"),
        ("gobject", r"\bgobject-2\.0-0(?:\.dll)?\b"),
        ("com_winrt", r"\b(?:combase|windows\.storage|twinapi|windows\.application)\b"),
        ("probe", r"\bc545d_disposable_scanfree(?:\.exe)?\b"),
    ):
        if re.search(prefix, text):
            return name
    return "other"


def summarize(source: str, arm: str) -> str:
    if arm not in {"registry", "nochange"}:
        raise ValueError("unapproved_control_arm")
    if not isinstance(source, str) or not 100 <= len(source) <= MAX_REPORT:
        raise ValueError("empty_or_oversized_image_report")
    parts = [s.strip() for s in DASH.split(source) if s.strip()]
    if len(GLOBAL.findall(source)) != 1 or len(TOP.findall(source)) != 1:
        raise ValueError("missing_global_or_top_header")
    globals_ = [s for s in parts if GLOBAL.search(s)]
    if len(globals_) != 1:
        raise ValueError("ambiguous_heap_global")
    g = num(globals_[0])
    if g[0] == 0:
        raise ValueError("no_heap_allocations")
    seen = defaultdict(lambda: [0, 0, 0, 0])
    accepted_alloc = accepted_out = bad_rows = rows = 0
    for block in parts:
        if GLOBAL.search(block) or TOP.search(block):
            continue
        if not any(rx.search(block) for rx in METRICS.values()):
            continue
        rows += 1
        try:
            a, _, o, ok, _ = num(block)
        except ValueError:
            bad_rows += 1
            continue
        fam = family(block)
        accepted_alloc += a
        accepted_out += o
        z = seen[fam]
        z[0] += a
        z[1] += o
        z[2] += int(ok * Decimal(10))
        z[3] += 1
    if rows == 0 or rows > 10000:
        raise ValueError("image_metric_rows_absent_or_oversized")
    if accepted_alloc > g[0] or accepted_out > g[2]:
        raise ValueError("image_group_rows_exceed_global")
    full = int(bad_rows == 0 and accepted_alloc == g[0] and accepted_out == g[2])
    # Full group coverage is a condition for interpreting image cohorts,
    # but EVEN full coverage is NOT evidence of source function ownership.
    fields = [
        "C545D_GIO_ETW_IMAGE_AGGREGATE",
        f"arm={arm}",
        f"global_alloc={g[0]}", f"global_out={g[2]}",
        f"global_out_kb_tenths={int(g[3]*10)}",
        f"image_rows={rows}", f"bad_rows={bad_rows}",
        f"accepted_alloc={accepted_alloc}", f"accepted_out={accepted_out}",
        f"unattributed_out={g[2]-accepted_out}",
        f"image_group_coverage_complete={full}",
    ]
    for fam in FAMILIES:
        a, o, kb, n = seen[fam]
        fields += [
            f"{fam}_rows={n}", f"{fam}_alloc={a}",
            f"{fam}_out={o}", f"{fam}_out_kb_tenths={kb}",
        ]
    fields += [
        "top_frame_image_group_not_causal_owner=1",
        "live_allocation_not_automatically_leak=1",
        "global_quiet_unproven=1,real_host_untouched=1,raw_uploaded=0"
    ]
    return ",".join(fields)


def selftest() -> None:
    sample = (
        "GLOBAL ALLOCATIONS:\nAlloc : 20, 3.5 KB\n"
        "Realloc : 0\nOutstanding : 5, 1.0 KB\n"
        "--------------------------------------\n"
        "TOP 1024:\nAlloc : 20, 3.5 KB\n"
        "Realloc : 0\nOutstanding : 5, 1.0 KB\n"
        "--------------------------------------\n"
        "gio-2.0-0.dll\nAlloc : 12, 2.1 KB\n"
        "Realloc : 0\nOutstanding : 4, 0.8 KB\n"
        "--------------------------------------\n"
        "combase.dll\nAlloc : 8, 1.4 KB\n"
        "Realloc : 0\nOutstanding : 1, 0.2 KB\n"
    )
    good = summarize(sample, "registry")
    assert "global_out=5" in good and "gio_out=4" in good
    assert "image_group_coverage_complete=1" in good
    clipped = sample.replace("TOP 1024:", "TOP 1:").split(
        "--------------------------------------\ncombase.dll")[0]
    result = summarize(clipped, "registry")
    assert "image_group_coverage_complete=0" in result
    assert "unattributed_out=1" in result
    corrupted = [
        sample.replace("GLOBAL ALLOCATIONS:", "NO GLOBAL:"),
        sample.replace("TOP 1024:", "TOP ?:"),
        sample.replace("Outstanding : 4, 0.8 KB", "Outstanding : 13, 0.8 KB"),
        sample.replace("Alloc : 20, 3.5 KB", "Alloc : 1, 3.5 KB", 1),
        sample + sample,
        sample.replace("combase.dll\nAlloc", "combase.dll\nAlloc : 10, 0.1 KB\nAlloc"),
    ]
    for index, text in enumerate(corrupted):
        try:
            result = summarize(text, "registry")
        except ValueError:
            continue
        if "bad_rows=0" in result and "image_group_coverage_complete=1" in result:
            raise AssertionError(f"bad_image_report_accepted,index={index}")
    print("C545D_GIO_ETW_IMAGE_AGGREGATE_SELFTEST_PASS,positive=2,negative=6,"
          "top_image_not_owner=1,raw_symbols_not_emitted=1")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--report", type=Path)
    p.add_argument("--arm", choices=("registry", "nochange"))
    a = p.parse_args()
    if a.selftest:
        selftest()
    else:
        if a.report is None or a.arm is None:
            p.error("--report and --arm required")
        print(summarize(a.report.read_text(encoding="utf-8-sig", errors="replace"), a.arm))


if __name__ == "__main__":
    main()
