#!/usr/bin/env python3
"""Offline guard for original Combo256 bounded DisplayName cache evidence.

Uses saved FOUR ARM MSVC Windows2022 #44918598339 numeric-only traces.
The observable reported cache values are FINAL process-level counters,
NOT a 257-point cache-cardinality time series. Do not infer that it never
temporarily grew, nor that a cache of 32 objects explains PrivateUsage.
The cache is a CI-only diagnostic with known production freshness limits.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

import analyze_gio_combo_msvc256_saved as original

CACHE = re.compile(r"C545D_DISPLAY_CACHE,hits=(\d+),misses=(\d+),entries=(\d+)")


def source_guard(source: str) -> None:
    required = (
        "g_hash_table_size (c545d_display_cache) < 1024",
        "g_hash_table_replace (c545d_display_cache, key, value);",
        "g_hash_table_remove_all (c545d_display_cache);",
        "static GHashTable *c545d_display_cache;",
        "g_hash_table_new_full (g_str_hash, g_str_equal,",
        "g_print (\"C545D_DISPLAY_CACHE,hits=%u,misses=%u,entries=%u",
    )
    for marker in required:
        expected = 2 if marker == "g_hash_table_new_full (g_str_hash, g_str_equal," else 1
        if source.count(marker) != expected:
            raise ValueError(f"unpinned diagnostic cache ownership: {marker}")
    if ("Locale/resource updates and re-installation while running are NOT handled."
            not in source or "NEVER ship as a fix" not in source):
        raise ValueError("production freshness caveat removed")


def sample(rows: list[str]) -> tuple[int, int, int]:
    records = []
    for row in rows:
        if not row.startswith("C545D_DISPLAY_CACHE,"):
            continue
        m = CACHE.fullmatch(row)
        if not m:
            raise ValueError("unrecognized/malformed cache numeric record")
        records.append(tuple(map(int, m.groups())))
    if len(records) != 1:
        raise ValueError(f"require single final cache report, got {len(records)}")
    return records[0]


def audit(group: dict[str, list[str]], code: str) -> list[str]:
    source_guard(code)
    guard = original.analyze(group, print_output=False)
    if not guard[-1].startswith(
        "C545D_SAVED256_NUMERIC_ANALYSIS_PASS,source_windows_run=44918598339,"
    ):
        raise ValueError("original complete four-arm 256 archive identity missing")
    expected = {"nochange": (0, 32, 32), "registry": (8224, 32, 32)}
    records = {}
    for arm in original.ARMS:
        reading = sample(group[f"combo-{arm}-256"])
        if reading != expected[arm]:
            raise ValueError(f"original {arm} cache counters changed")
        records[arm] = reading
    if records["registry"][0] != 257 * records["registry"][2]:
        raise ValueError("cumulative cache reuse not independently reconciled")
    if max(x[2] for x in records.values()) > 1024:
        raise ValueError("cache storage cap exceeded")
    p = {arm: original.parse(group, "combo", arm) for arm in original.ARMS}
    final_private = original.difference(
        p, "mem", ("baseline", 0), ("settled_cleanup", 258)
    )
    if final_private != 368640:
        raise ValueError("original Combo256 private-commit reference changed")
    return [
        "C545D_COMBO256_CACHE_BOUND_SOURCE,source_run=44918598339,"
        "diagnostic_cache_hard_cap=1024,cache_is_NOT_production_safe=1,"
        "owned_key_and_utf16_value=1,optional_resets_present=1",
        "C545D_COMBO256_CACHE_BOUND_NUMERIC,source_run=44918598339,"
        f"nochange_final_hits={records['nochange'][0]},"
        f"nochange_final_misses={records['nochange'][1]},"
        f"nochange_final_entries={records['nochange'][2]},"
        f"registry_final_hits={records['registry'][0]},"
        f"registry_final_misses={records['registry'][1]},"
        f"registry_final_entries={records['registry'][2]},"
        f"combo_private_controlled_final={final_private},"
        "cache_per_cycle_cardinality_available=0",
        "C545D_COMBO256_CACHE_BOUND_INFERENCE,"
        "final_registry_cache_entries_greater_than_nochange=0,"
        "unbounded_entry_count_growth_observed=0,"
        "cache_replacement_transient_bytes_unknown=1,"
        "private_committed_ownership_from_cache_proven=0,"
        "cache_cannot_be_shipped_without_freshness_fix=1,"
        "heap_allocator_highwater_excluded=0,"
        "global_worker_APC_quiescence_proven=0",
        "C545D_COMBO256_CACHE_BOUND_PASS,original_windows_run=44918598339,"
        "original_256_rerun=0,other_windows_rerun=0,"
        "real_camera_tested=0,user_host_modified=0",
    ]


def selftest() -> None:
    assert sample(["C545D_DISPLAY_CACHE,hits=8224,misses=32,entries=32"]) == (
        8224, 32, 32
    )
    mutants = (
        [],
        ["C545D_DISPLAY_CACHE,hits=8224,misses=32,entries=32"] * 2,
        ["C545D_DISPLAY_CACHE,hits=8224,misses=-32,entries=32"],
        ["C545D_DISPLAY_CACHE,hits=8224,misses=32,entries=32,text"],
        ["C545D_DISPLAY_CACHE,hits=NaN,misses=32,entries=32"],
    )
    for rows in mutants:
        try:
            sample(rows)
        except ValueError:
            continue
        raise AssertionError("bad original numeric record accepted")
    print("C545D_COMBO256_CACHE_BOUND_SELFTEST_PASS,negative_cases=5,"
          "positive_cases=1,windows_runs=0,real_host_untouched=1")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--root", type=Path)
    ap.add_argument("--cache-source", type=Path)
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if args.root is None or args.cache_source is None:
        ap.error("need --root and --cache-source")
    group = original.load(args.root)
    for line in audit(group, args.cache_source.read_text(encoding="utf-8")):
        print(line)


if __name__ == "__main__":
    main()
