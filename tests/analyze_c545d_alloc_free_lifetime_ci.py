#!/usr/bin/env python3
"""CI-only loss-detecting allocation lifetime state machine.

Calibrates alloc/free pairing with deliberately known synthetic heap events.
No addresses, raw stack names, paths, original event rows or raw ETL are
printed. This is NOT a parser for the previous xperf top25 report and
does NOT prove actual GIO allocation ownership.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass

VALID_OWNER = {"FIXTURE_HEAPALLOC", "GIO", "WINRT", "CRT", "OTHER"}
MAX_EVENTS = 250_000

@dataclass(frozen=True)
class Entry:
    size: int
    owner: str
    seq: int

def pair_events(rows: list[dict], *, prelaunch: bool, lost: int, quiet: bool) -> dict[str, object]:
    if not prelaunch or not quiet or lost != 0:
        raise ValueError("capture_completeness_or_quiescence_unproven")
    if not rows or len(rows) > MAX_EVENTS:
        raise ValueError("events_missing_or_too_many")
    live: dict[tuple[str, int], Entry] = {}
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"alloc": 0, "free": 0, "live_bytes": 0, "live_count": 0})
    next_seq = 0
    for row in rows:
        if not isinstance(row, dict) or set(row) not in (
            {"op", "heap", "address", "size", "owner"},
            {"op", "heap", "address"}
        ):
            raise ValueError("unexpected_event_schema")
        op, heap, addr = row["op"], row["heap"], row["address"]
        if type(heap) is not str or heap not in {"DEFAULT", "OTHER"} or type(addr) is not int or addr <= 0:
            raise ValueError("invalid_heap_or_address")
        key = heap, addr
        if op == "alloc":
            size = row["size"]
            owner = row["owner"]
            if type(size) is not int or size <= 0 or size > 2**34 or owner not in VALID_OWNER:
                raise ValueError("unsafe_allocation_size_or_owner")
            if key in live:
                raise ValueError("address_reused_without_matching_free")
            live[key] = Entry(size, owner, next_seq)
            next_seq += 1
            totals[owner]["alloc"] += 1
        elif op == "free":
            if set(row) != {"op", "heap", "address"}:
                raise ValueError("untrusted_free_fields")
            item = live.pop(key, None)
            if item is None:
                raise ValueError("orphan_free_capture_incomplete")
            totals[item.owner]["free"] += 1
        else:
            raise ValueError("unsupported_event_op_including_realloc")
    for ent in live.values():
        totals[ent.owner]["live_bytes"] += ent.size
        totals[ent.owner]["live_count"] += 1
    for owner in totals:
        if totals[owner]["alloc"] - totals[owner]["free"] != totals[owner]["live_count"]:
            raise ValueError("invalid_owner_balance")
    return {
        "allocations": sum(v["alloc"] for v in totals.values()),
        "frees": sum(v["free"] for v in totals.values()),
        "outstanding_count": len(live),
        "outstanding_bytes": sum(z.size for z in live.values()),
        "owners": {k: totals[k] for k in sorted(totals)},
        "leak_proven": False,  # not knowing expected lifetime != leak
    }


def fixture() -> list[dict]:
    # The tracked "addresses" are synthetic IDs, never real process pointers.
    rows = [
        {"op": "alloc", "heap": "DEFAULT", "address": i+1,
         "size": 360, "owner": "FIXTURE_HEAPALLOC"}
        for i in range(64)
    ]
    rows.extend({"op": "free", "heap": "DEFAULT", "address": i+1} for i in range(48))
    return rows


def selftest() -> None:
    original = fixture()
    result = pair_events(original, prelaunch=True, lost=0, quiet=True)
    assert result["allocations"] == 64 and result["frees"] == 48
    assert result["outstanding_count"] == 16 and result["outstanding_bytes"] == 5760
    assert result["leak_proven"] is False
    # Reallocated address after free is fine if a *new* alloc event arrives.
    reuse = original + [
        {"op": "alloc", "heap": "DEFAULT", "address": 1,
         "size": 360, "owner": "FIXTURE_HEAPALLOC"},
        {"op": "free", "heap": "DEFAULT", "address": 1},
    ]
    assert pair_events(reuse, prelaunch=True, lost=0, quiet=True)["outstanding_bytes"] == 5760
    invalid = [
        (original, False, 0, True),
        (original, True, 1, True),
        (original, True, 0, False),
        (original[:64]+original[:1], True, 0, True),
        (original + [{"op": "free", "heap": "DEFAULT", "address": 999}], True, 0, True),
        (original + [{"op": "realloc", "heap": "DEFAULT", "address": 50}], True, 0, True),
        (original + [{"op": "free", "heap": "DEFAULT", "address": 60, "size": 360}], True, 0, True),
        (original[:1] + [{"op": "alloc", "heap": "DEFAULT", "address": 90,
                          "size": 360, "owner": "UNCHECKED"}] + original[1:], True, 0, True),
        (original[:48] + [{"op": "free", "heap": "OTHER", "address": 1}] + original[48:], True, 0, True),
        (original + [{"op": "free", "heap": "DEFAULT", "address": 1}], True, 0, True),
    ]
    for rows, prelaunch, lost, quiet in invalid:
        try:
            pair_events(rows, prelaunch=prelaunch, lost=lost, quiet=quiet)
        except ValueError:
            continue
        raise AssertionError("incomplete_or_broken_event_stream_accepted")
    print("C545D_ALLOC_FREE_MATCHER_SELFTEST_PASS,negative=10,positive=2,"
          "known_alloc=64,known_freed=48,expected_outstanding=16,"
          "expected_outstanding_bytes=5760,"
          "address_reuse_after_free_accepted=1,"
          "lost_event_fails_closed=1,"
          "unknown_free_fails_closed=1,"
          "actual_xperf_adapter_verified=0,real_GIO_tested=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    if a.selftest:
        selftest()
    else:
        p.error("Only synthetic selftest is supported until a privacy-safe complete ETW event adapter is validated")


if __name__ == "__main__":
    main()
