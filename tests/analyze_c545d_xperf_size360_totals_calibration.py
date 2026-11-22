#!/usr/bin/env python3
"""Strict privacy-safe parser of Xperf heap -totals -size 360 361.

Reads a local ephemeral (never uploaded) Xperf report, emits only allowlisted
counts/sizes. The synthetic fixture deliberately allocates 64 x 360 bytes,
frees 48, and holds 16 during the ETW stop. This tests whether Xperf INDEPENDENTLY
reconstructed the fixture result; no raw pointers, paths, stacks or ETL escape.
Outstanding blocks alone are not necessarily leaks.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

COLUMNS = (
    "alloc#", "alloc kb", "out#", "out kb", "realloc#",
    "extents kb", "out ext kb", "heap handle"
)
KB = Decimal(1024)
SIZE_B = 360
EXPECTED_ALLOC = 64
EXPECTED_OUT = 16


def parse_totals(source: str) -> dict[str, int | Decimal]:
    if not isinstance(source, str) or len(source) > 2_000_000:
        raise ValueError("invalid_report_type_or_size")
    records: list[tuple[list[Decimal], str]] = []
    headers = 0
    for original in source.splitlines():
        line = original.strip()
        if not line:
            continue
        parts = [s.strip() for s in line.split(",")]
        normalized = tuple(re.sub(r"\s+", " ", p.lower()) for p in parts)
        if normalized == COLUMNS:
            headers += 1
            continue
        if headers != 1 or len(parts) != 8:
            continue
        label = parts[7]
        if not (label == "TOTAL" or re.fullmatch(r"0[xX][0-9a-fA-F]+", label)):
            continue
        # Numeric entries must be syntactically exact. No float rounding or
        # free-form report text from stack traces may be interpreted as data.
        for i in (0, 2, 4):
            if re.fullmatch(r"\d+", parts[i]) is None:
                raise ValueError("invalid_count_field")
        numeric: list[Decimal] = []
        for p in parts[:7]:
            if re.fullmatch(r"\d+(?:\.\d+)?", p) is None:
                raise ValueError("invalid_numeric_field")
            try:
                numeric.append(Decimal(p))
            except InvalidOperation as exc:
                raise ValueError("invalid_decimal_field") from exc
        records.append((numeric, label))
    if headers != 1:
        raise ValueError("missing_or_duplicate_xperf_header")
    totals = [n for n, label in records if label == "TOTAL"]
    heaps = [n for n, label in records if label != "TOTAL"]
    if len(totals) != 1 or not heaps:
        raise ValueError("missing_or_duplicate_total_or_heap")
    addresses = [label.lower() for n, label in records if label != "TOTAL"]
    if len(addresses) != len(set(addresses)):
        raise ValueError("duplicate_heap_handle")
    total = totals[0]
    for idx in (0, 2, 4):
        if total[idx] != sum((row[idx] for row in heaps), Decimal(0)):
            raise ValueError("heap_count_rows_do_not_sum_to_total")
    if total[0] < total[2] or total[0] < 1:
        raise ValueError("invalid_outstanding_fraction")
    # Header documents KB, typically rounded to one decimal, so do not
    # claim exact bytes from the decimal size field alone. The narrow
    # size filter [360,361) lets a verified count imply exact request bytes.
    return {
        "alloc": int(total[0]),
        "outstanding": int(total[2]),
        "alloc_kb": total[1],
        "outstanding_kb": total[3],
        "realloc": int(total[4]),
        "heaps": len(heaps),
    }


def verify_calibration(report: str, *, owner_only: bool = False) -> str:
    d = parse_totals(report)
    if d["alloc"] < EXPECTED_ALLOC or d["outstanding"] != EXPECTED_OUT:
        raise ValueError(
            f"calibration_mismatch,observed_alloc={d['alloc']},"
            f"observed_outstanding={d['outstanding']}"
        )
    if owner_only and (d["alloc"] != EXPECTED_ALLOC or d["realloc"] != 0):
        raise ValueError(
            f"owner_specific_calibration_mismatch,observed_alloc={d['alloc']},"
            f"observed_realloc={d['realloc']}"
        )
    # The full process may allocate additional short-lived 360 B blocks.
    # Previous actual ETW showed 84 total vs known 64, but 16 outstanding.
    # A separate unique owner-stack filter must isolate exactly the known 64.
    # Never claim the process-wide total count is fixture-owned.
    if abs(d["outstanding_kb"] - Decimal(EXPECTED_OUT * SIZE_B) / KB) > Decimal("0.1"):
        raise ValueError("display_kb_inconsistent_with_exact_size_filter")
    if abs(d["alloc_kb"] - Decimal(d["alloc"] * SIZE_B) / KB) > Decimal("0.1"):
        raise ValueError("alloc_kb_inconsistent_with_exact_size_filter")
    scope = "owner" if owner_only else "all"
    return (
        "C545D_XPERF_360_TOTALS_CALIBRATION_PASS,"
        f"scope={scope},filtered_requested_size=360,"
        f"etw_alloc_count={d['alloc']},etw_out_count={d['outstanding']},"
        "derived_etw_out_requested_bytes=5760,"
        "reported_size_kb_is_rounded=1,"
        f"reported_heap_count={d['heaps']},"
        "totals_verified_against_heap_rows=1,"
        f"fixture_owner_isolation_proven={int(owner_only)},"
        "real_GIO_owner_proven=0,"
        "synthetic_expected_lifetime_not_leak=1,"
        "real_GIO_tested=0,real_host_untouched=1,"
        "etl_uploaded=0,raw_addresses_logged=0"
    )


def selftest() -> None:
    good = (
        "Alloc#,  Alloc KB,  Out#,  Out KB,  Realloc#,  Extents KB, "
        "Out Ext KB, Heap Handle\n"
        "64, 22.5, 16, 5.6, 0, 24.0, 24.0, TOTAL\n"
        "64, 22.5, 16, 5.6, 0, 24.0, 24.0, 0x123400\n"
    )
    # Extra 20 process-owned 360-byte allocations that have ended
    # at the snapshot must not be mistaken for 20 extra source leaks.
    mixed = good.replace("64, 22.5", "84, 29.5")
    assert "etw_out_count=16" in verify_calibration(good, owner_only=True)
    assert "etw_alloc_count=84" in verify_calibration(mixed)
    errors = [
        good.replace("16, 5.6", "15, 5.3", 1),
        good.replace("64, 22.5", "65, 22.5", 1),
        good.replace("5.6", "12.4"),
        good.replace("16, 5.6", "18, 5.6"),
        good.replace("Realloc#", "Garbage#"),
        good + good,
        good.replace("TOTAL", "0xABCDEF", 1),
        good.replace("0x123400", "TOTAL"),
        good.replace("64, 22.5, 16, 5.6, 0, 24.0, 24.0, 0x123400\n", ""),
        good.replace("0x123400", "0xZZZZZZ"),
        good.replace("16, 5.6, 0", "16, 5.6, 1"),
        mixed,  # valid full process totals, invalid owner-only totals
    ]
    for index, report in enumerate(errors):
        try:
            verify_calibration(report, owner_only=index in (10, 11))
        except ValueError:
            continue
        raise AssertionError("corrupted_or_not_owner_filtered_report_accepted")
    print(
        "C545D_XPERF_TOTALS_SELFTEST_PASS,positive=2,negative=12,"
        "independent_process_extra_allocations=20,"
        "owner_scoped_exact_count_required=1,"
        "real_GIO_tested=0,raw_ETL_uploaded=0"
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--report", type=Path)
    p.add_argument("--owner-only", action="store_true")
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    if a.report is None:
        p.error("--report required")
    print(verify_calibration(a.report.read_text(encoding="utf-8-sig", errors="replace"), owner_only=a.owner_only))


if __name__ == "__main__":
    main()
