#!/usr/bin/env python3
"""Determine Xperf heap action text schema on DISPOSABLE Windows local ETL.

Two Microsoft documentation versions differ on '-image' and '-images'.
This fast, fail-closed scanner emits ONLY fixed enums and numeric counts,
not a single source frame, symbol, pointer, machine path or raw report line.
It does not infer heap ownership or a real GIO leak.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

MAX_REPORT = 16 * 1024 * 1024
GLOBAL = re.compile(r"(?im)^\s*GLOBAL\s+ALLOCATIONS\s*:")
TOP = re.compile(r"(?im)^\s*TOP\s+\d+\s*:")
ALLOC = re.compile(r"(?im)^\s*Alloc\s*:\s*\d+\s*,\s*\d+(?:\.\d+)?\s*KB")
OUT = re.compile(r"(?im)^\s*Outstanding\s*:\s*\d+\s*,\s*\d+(?:\.\d+)?\s*KB")
DASH = re.compile(r"(?m)^\s*-{8,}\s*$")
HELP = re.compile(r"(?im)(?:^\s*usage\s*:|^\s*xperf\s+[-/]|^\s*option(?:s)?\s*:|unknown\s+option|invalid\s+option)")

def inspect(source: str, mode: str, exit_code: int) -> str:
    if mode not in {"image", "images", "frames"}:
        raise ValueError("unknown_heap_action_mode")
    if not isinstance(source, str) or len(source) > MAX_REPORT:
        raise ValueError("unbounded_action_report")
    if exit_code < 0 or exit_code > 999:
        raise ValueError("invalid_action_exit_code")
    global_headers = len(GLOBAL.findall(source))
    top_headers = len(TOP.findall(source))
    alloc_lines = len(ALLOC.findall(source))
    out_lines = len(OUT.findall(source))
    dash_parts = len([p for p in DASH.split(source) if p.strip()])
    looks_like_usage = int(bool(HELP.search(source)))
    if exit_code:
        schema = "action_failed"
    elif not source.strip():
        schema = "empty_report"
    elif looks_like_usage:
        schema = "help_or_invalid_option"
    elif global_headers == top_headers == 1 and alloc_lines >= 2 and out_lines >= 2:
        schema = "stack_compatible_metric_sections"
    elif alloc_lines or out_lines or global_headers or top_headers:
        schema = "partial_metric_schema"
    else:
        schema = "unknown_nonmetric_text"
    return (
        "C545D_XPERF_HEAP_ACTION_LAYOUT,"
        f"mode={mode},schema={schema},exit_code={exit_code},"
        f"global_headers={global_headers},top_headers={top_headers},"
        f"alloc_lines={alloc_lines},out_lines={out_lines},dash_parts={dash_parts},"
        f"help_pattern={looks_like_usage},"
        f"bounded_report=1,raw_text_uploaded=0,source_owner_proven=0,"
        "real_GIO_tested=0,Windows_host_untouched=1"
    )

def selftest() -> None:
    report = (
        "GLOBAL ALLOCATIONS:\nAlloc : 64, 22.5 KB\n"
        "Realloc : 0\nOutstanding : 16, 5.6 KB\n"
        "------------------------------------------\n"
        "TOP 64:\nAlloc : 64, 22.5 KB\nRealloc : 0\n"
        "Outstanding : 16, 5.6 KB\n"
        "------------------------------------------\n"
        "c545d_owner_life_cal.exe!known_symbol\n"
        "Alloc : 64, 22.5 KB\nRealloc : 0\nOutstanding : 16, 5.6 KB\n"
    )
    for m in ("frames", "images", "image"):
        result = inspect(report, m, 0)
        assert "schema=stack_compatible_metric_sections" in result
        assert "known_symbol" not in result
    assert "schema=help_or_invalid_option" in inspect(
        "Usage: Xperf -a heap [-stacks] [-images]", "image", 0)
    assert "schema=action_failed" in inspect("unknown option", "image", 2)
    assert "schema=empty_report" in inspect("", "images", 0)
    assert "schema=unknown_nonmetric_text" in inspect(
        "An undocumented table heading and body", "frames", 0)
    assert "schema=partial_metric_schema" in inspect(
        "GLOBAL ALLOCATIONS:\nAlloc : 64, 22.5 KB", "frames", 0)
    negatives = [("INVALID", report, 0), ("frames", report, -1),
                 ("images", report, 1000), ("images", "X" * (MAX_REPORT + 1), 0)]
    for i, (mode, data, status) in enumerate(negatives):
        try:
            inspect(data, mode, status)
        except ValueError:
            continue
        raise AssertionError(f"invalid_action_schema_accepted:{i}")
    print("C545D_XPERF_ACTION_LAYOUT_SELFTEST_PASS,positive=8,negative=4,"
          "raw_symbols_leaked=0,new_windows_runs=0,host_untouched=1")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--mode", choices=("frames", "images", "image"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--exit", type=int, default=0)
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.mode is None or args.report is None:
        parser.error("mode and local report required")
    if not args.report.exists() or args.report.stat().st_size > MAX_REPORT:
        raise ValueError("missing_or_oversized_private_report")
    print(inspect(args.report.read_text("utf-8-sig", errors="replace"), args.mode, args.exit))

if __name__ == "__main__":
    main()
