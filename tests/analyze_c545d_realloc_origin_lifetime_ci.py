#!/usr/bin/env python3
"""Source-only fail-closed HeapAlloc -> HeapReAlloc -> HeapFree lifetime model.

Microsoft ETW_HEAP_EVENT_REALLOC fields OldAddress/NewAddress and
OldSize/NewSize permit identity transfer, but this module deliberately
consumes ONLY synthetic event fixture dicts. It does not parse actual ETL,
observe real GIO, establish actual APC/WinRT quiet or approve deployment.
All addresses are internal synthetic numeric tokens and never printed.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

MAX_EVENTS = 250_000
OWNERS = {"FIXTURE_HEAPALLOC", "GIO", "GLIB", "WINRT", "OTHER"}
HEAPS = {"DEFAULT", "OTHER"}
SITES = {"FIXTURE_REALLOC", "GIO", "WINRT", "OTHER"}
PHASES = ("precleanup", "producer_ack", "post_epoch")


@dataclass(frozen=True)
class Lifetime:
    owner: str
    bytes: int
    origin_seq: int
    reallocs: int


def track(events: list[dict], *, preworkload_trace: bool, events_lost: int,
          buffers_lost: int, producer_closed_verified: bool,
          synthetic_contract_only: bool) -> dict[str, Any]:
    if (preworkload_trace is not True or events_lost != 0 or buffers_lost != 0 or
            producer_closed_verified is not True or synthetic_contract_only is not True):
        raise ValueError("incomplete_capture_or_unverified_producer_epoch")
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_EVENTS:
        raise ValueError("unbounded_or_absent_synthetic_events")
    live: dict[tuple[str, int], Lifetime] = {}
    counters = defaultdict(lambda: {"alloc": 0, "realloc": 0, "free": 0})
    markers: dict[str, dict[str, int]] = {}
    seen_phases: list[str] = []
    initial_allocs = realloc_calls = frees = 0
    moved = inplace = 0
    for index, row in enumerate(events):
        if not isinstance(row, dict) or "op" not in row:
            raise ValueError("invalid_synthetic_event_schema")
        op = row["op"]
        if op == "marker":
            if set(row) != {"op", "phase"} or row["phase"] not in PHASES:
                raise ValueError("untrusted_phase_marker")
            if row["phase"] != PHASES[len(seen_phases)] if len(seen_phases) < len(PHASES) else True:
                raise ValueError("source_phase_order_invalid")
            if row["phase"] in seen_phases:
                raise ValueError("duplicated_source_phase")
            seen_phases.append(row["phase"])
            markers[row["phase"]] = {
                "live_count": len(live),
                "live_bytes": sum(ent.bytes for ent in live.values()),
                "reallocated_live": sum(ent.reallocs > 0 for ent in live.values()),
            }
            continue
        heap = row.get("heap")
        if heap not in HEAPS or type(heap) is not str:
            raise ValueError("unknown_synthetic_heap")
        if op == "alloc":
            if set(row) != {"op", "heap", "address", "size", "owner"}:
                raise ValueError("invalid_alloc_record")
            address, size, owner = row["address"], row["size"], row["owner"]
            if (type(address) is not int or address <= 0 or type(size) is not int
                    or not 1 <= size <= (1<<34) or owner not in OWNERS):
                raise ValueError("invalid_allocation_identity")
            key = heap, address
            if key in live:
                raise ValueError("overlapping_heap_allocations")
            live[key] = Lifetime(owner, size, index, 0)
            counters[owner]["alloc"] += 1
            initial_allocs += 1
        elif op == "realloc":
            if set(row) != {"op", "heap", "old_address", "new_address",
                            "old_size", "new_size", "site"}:
                raise ValueError("invalid_reallocation_record")
            old, new = row["old_address"], row["new_address"]
            before, after, site = row["old_size"], row["new_size"], row["site"]
            if (type(old) is not int or type(new) is not int or old <= 0 or new <= 0
                    or type(before) is not int or type(after) is not int
                    or not 1 <= before <= (1<<34) or not 1 <= after <= (1<<34)
                    or site not in SITES):
                raise ValueError("invalid_realloc_address_or_size")
            before_key, after_key = (heap, old), (heap, new)
            prior = live.get(before_key)
            if prior is None:
                raise ValueError("orphan_realloc_original_alloc_outside_scope")
            if prior.bytes != before:
                raise ValueError("realloc_old_size_mismatch")
            if after_key != before_key and after_key in live:
                raise ValueError("realloc_target_collides_with_live_allocation")
            del live[before_key]
            live[after_key] = Lifetime(prior.owner, after, prior.origin_seq, prior.reallocs + 1)
            counters[prior.owner]["realloc"] += 1
            realloc_calls += 1
            if old == new:
                inplace += 1
            else:
                moved += 1
        elif op == "free":
            if set(row) != {"op", "heap", "address"} or type(row["address"]) is not int:
                raise ValueError("invalid_free_record")
            prior = live.pop((heap, row["address"]), None)
            if prior is None:
                raise ValueError("orphan_free_or_stale_realloc_address")
            counters[prior.owner]["free"] += 1
            frees += 1
        else:
            raise ValueError("unsupported_source_event")
    if seen_phases != list(PHASES):
        raise ValueError("missing_closed_epoch_observations")
    if not (markers["precleanup"]["live_count"] >= markers["producer_ack"]["live_count"] >=
            markers["post_epoch"]["live_count"]):
        # Fixture contract says there are no new allocations after precleanup.
        # This does NOT generalize to actual GIO where new work may be queued.
        raise ValueError("synthetic_post_stop_new_workload")
    if any(v["alloc"] < v["free"] for v in counters.values()):
        raise ValueError("free_count_exceeds_original_alloc")
    # Real code must validate producer closure independently; this model
    # cannot assert expected lifetime or actual memory leak from a timeout.
    return {
        "initial_allocs": initial_allocs,
        "realloc_calls": realloc_calls,
        "realloc_moved": moved,
        "realloc_inplace": inplace,
        "free_calls": frees,
        "precleanup_live": markers["precleanup"]["live_count"],
        "precleanup_live_bytes": markers["precleanup"]["live_bytes"],
        "precleanup_reallocated_live": markers["precleanup"]["reallocated_live"],
        "after_producer_ack_live": markers["producer_ack"]["live_count"],
        "post_epoch_live": markers["post_epoch"]["live_count"],
        "post_epoch_live_bytes": markers["post_epoch"]["live_bytes"],
        "original_owner_preserved_on_realloc": 1,
        "synthetic_only": 1,
        "real_gio_lifetime_proven": 0,
        "production_release_approved": 0,
    }


def fixture(*, move: bool = True, post_free: bool = True) -> list[dict]:
    events = [
        {"op": "alloc", "heap": "DEFAULT", "address": i+1,
         "size": 360, "owner": "FIXTURE_HEAPALLOC"}
        for i in range(64)
    ]
    for i in range(48, 64):
        events.append({
            "op": "realloc", "heap": "DEFAULT", "old_address": i+1,
            "new_address": 1000+i+1 if move else i+1,
            "old_size": 360, "new_size": 720, "site": "FIXTURE_REALLOC",
        })
    events.extend({"op": "free", "heap": "DEFAULT", "address": i+1}
                  for i in range(48))
    events.append({"op": "marker", "phase": "precleanup"})
    events.append({"op": "marker", "phase": "producer_ack"})
    if post_free:
        for i in range(48, 64):
            events.append({
                "op": "free", "heap": "DEFAULT",
                "address": 1000+i+1 if move else i+1
            })
    events.append({"op": "marker", "phase": "post_epoch"})
    return events


def selftest() -> None:
    def run(ev: list[dict], **overrides: Any) -> dict[str, Any]:
        gates = dict(preworkload_trace=True, events_lost=0, buffers_lost=0,
                     producer_closed_verified=True, synthetic_contract_only=True)
        gates.update(overrides)
        return track(ev, **gates)
    r = run(fixture())
    assert (r["initial_allocs"], r["realloc_calls"], r["realloc_moved"],
            r["free_calls"], r["precleanup_live"], r["post_epoch_live"]) == (
            64,16,16,64,16,0)
    assert r["precleanup_live_bytes"] == 16*720
    assert r["precleanup_reallocated_live"] == 16
    assert r["post_epoch_live_bytes"] == 0
    assert r["production_release_approved"] == 0
    assert run(fixture(move=False))["realloc_inplace"] == 16
    assert run(fixture(post_free=False))["post_epoch_live"] == 16
    negatives: list[tuple[list[dict], dict[str, Any]]] = []
    events=fixture()
    negatives += [(events, {"preworkload_trace": False}),
                  (events, {"events_lost": 1}),
                  (events, {"buffers_lost": 1}),
                  (events, {"producer_closed_verified": False}),
                  (events, {"synthetic_contract_only": False})]
    def corrupted(where: int, **changes: Any) -> list[dict]:
        rows=[dict(v) for v in events]
        rows[where].update(changes)
        return rows
    negatives.extend([
        (corrupted(64, old_address=9999), {}),
        (corrupted(64, old_size=359), {}),
        (corrupted(64, new_address=49), {}),
        (corrupted(64, site="UNKNOWN_SOURCE"), {}),
        (corrupted(64, new_size=-1), {}),
        (corrupted(64, heap="OTHER"), {}),
        (corrupted(0, address=2), {}),
        (corrupted(-2, address=49), {}),
        (corrupted(-1, phase="precleanup"), {}),
        (events[:], {}),
    ])
    negatives[-1] = (events[:-1], {})
    for i, (rows, overrides) in enumerate(negatives):
        try:run(rows, **overrides)
        except ValueError:continue
        raise AssertionError(f"unverified_realloc_lifetime_accepted_{i}")
    # The Xperf late4-of-16 GIO interval begins after earlier allocations:
    # a realloc of an untraced address must fail, not invent a source owner.
    try:
        run(fixture()[64:])
    except ValueError as exc:
        assert "orphan_realloc_original_alloc_outside_scope" in str(exc)
    else:
        raise AssertionError("late_window_orphan_realloc_accepted")
    print("C545D_REALLOC_ORIGIN_LIFETIME_SELFTEST_PASS,positive=3,"
          f"negative={len(negatives)+1},original_owner_survives_realloc=1,"
          "late4_orphan_fails_closed=1,synthetic_only=1,raw_addresses_printed=0,"
          "new_windows_runs=0,real_host_untouched=1")


if __name__ == "__main__":
    selftest()
