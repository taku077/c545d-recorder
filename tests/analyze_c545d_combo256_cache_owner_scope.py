#!/usr/bin/env python3
"""Verify ORIGINAL Combo256 258 cache snapshots without Windows re-execution.

The saved four-arm Windows2022 #44918598339 file contains one cache report
after each registry parser scan (258 in registry arm, one in nochange).
Cache size snapshots are NOT memory allocation stacks. Observed no increase
in the SIZE of this CI-only diagnostic cache does not attribute process
PrivateUsage or prove absence of transient bytes / global async work.
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
        'g_print ("C545D_DISPLAY_CACHE,hits=%u,misses=%u,entries=%u',
    )
    for marker in required:
        expected = 2 if marker.startswith("g_hash_table_new_full") else 1
        if source.count(marker) != expected:
            raise ValueError(f"pinned cache source mismatch: {marker}")
    if ("Locale/resource updates and re-installation while running are NOT handled."
            not in source or "NEVER ship as a fix" not in source):
        raise ValueError("production freshness limitation removed")


def cache_rows(rows: list[str]) -> list[tuple[int, int, int]]:
    found = []
    for row in rows:
        if not row.startswith("C545D_DISPLAY_CACHE,"):
            continue
        m = CACHE.fullmatch(row)
        if m is None:
            raise ValueError("malformed numeric cache report")
        found.append(tuple(map(int, m.groups())))
    if not found:
        raise ValueError("no matching cache reports")
    return found


def check_series(rows: list[tuple[int, int, int]], arm: str) -> dict[str, int]:
    if arm not in original.ARMS:
        raise ValueError("invalid archive arm")
    count = 258 if arm == "registry" else 1
    if len(rows) != count:
        raise ValueError(f"expected {count} cache scan reports, found {len(rows)}")
    first = (0, 32, 32)
    final = (8224, 32, 32) if arm == "registry" else first
    if rows[0] != first or rows[-1] != final:
        raise ValueError("original first/final scan counters mismatch")
    if any(misses != 32 or entries != 32 for _, misses, entries in rows):
        raise ValueError("observed cache cardinality increased or misses changed")
    increments = [rows[i][0] - rows[i-1][0] for i in range(1, len(rows))]
    if any(delta < 0 or delta % 32 != 0 for delta in increments):
        raise ValueError("unexplained nonmonotonic/reuse-counter step")
    if sum(increments) != final[0]:
        raise ValueError("cumulative reuse does not telescope")
    return {
        "reports": count,
        "hits": final[0],
        "misses": final[1],
        "entries": final[2],
        "zero_hit_steps": sum(delta == 0 for delta in increments),
        "multi_scan_steps": sum(delta > 32 for delta in increments),
    }


def audit(group: dict[str, list[str]], source: str) -> list[str]:
    source_guard(source)
    guard = original.analyze(group, print_output=False)
    if not guard[-1].startswith(
        "C545D_SAVED256_NUMERIC_ANALYSIS_PASS,source_windows_run=44918598339,"
    ):
        raise ValueError("not the original complete 256 four-arm numeric artifact")
    cache = {
        arm: check_series(cache_rows(group[f"combo-{arm}-256"]), arm)
        for arm in original.ARMS
    }
    if cache["registry"]["hits"] != 257 * cache["registry"]["entries"]:
        raise ValueError("missing baseline-to-final cache reuse")
    processes = {
        arm: original.parse(group, "combo", arm) for arm in original.ARMS
    }
    final_private = original.difference(
        processes, "mem", ("baseline", 0), ("settled_cleanup", 258)
    )
    if final_private != 368640:
        raise ValueError("original private commit control mismatch")
    return [
        "C545D_COMBO256_CACHE_BOUND_SOURCE,source_run=44918598339,"
        "diagnostic_cache_hard_cap=1024,cache_is_NOT_production_safe=1,"
        "owned_key_and_utf16_value=1,optional_resets_present=1",
        "C545D_COMBO256_CACHE_BOUND_NUMERIC,source_run=44918598339,"
        f"nochange_reports={cache['nochange']['reports']},"
        f"nochange_hits={cache['nochange']['hits']},"
        f"nochange_misses={cache['nochange']['misses']},"
        f"nochange_entries={cache['nochange']['entries']},"
        f"registry_reports={cache['registry']['reports']},"
        f"registry_hits={cache['registry']['hits']},"
        f"registry_misses={cache['registry']['misses']},"
        f"registry_entries={cache['registry']['entries']},"
        f"registry_zero_hit_steps={cache['registry']['zero_hit_steps']},"
        f"registry_multi_scan_steps={cache['registry']['multi_scan_steps']},"
        f"combo_private_controlled_final={final_private},"
        "all_258_reported_registry_cache_entries_equal_32=1",
        "C545D_COMBO256_CACHE_BOUND_INFERENCE,"
        "observed_cache_cardinality_growth=0,"
        "all_allocation_lifetimes_observed=0,"
        "cache_replacement_transient_bytes_unknown=1,"
        "private_commit_owner_proven=0,"
        "diagnostic_cache_freshness_production_safe=0,"
        "heap_allocator_highwater_excluded=0,"
        "global_worker_APC_quiescence_proven=0",
        "C545D_COMBO256_CACHE_BOUND_PASS,source_run=44918598339,"
        "original_256_rerun=0,other_windows_rerun=0,"
        "real_camera_tested=0,user_host_modified=0",
    ]


def selftest() -> None:
    def row(i: int) -> str:
        return f"C545D_DISPLAY_CACHE,hits={i*32},misses=32,entries=32"

    series = [row(i) for i in range(258)]
    one = [row(0)]
    assert check_series(cache_rows(series), "registry")["reports"] == 258
    assert check_series(cache_rows(one), "nochange")["entries"] == 32
    mutants = (
        [],
        series[:-1],
        series + series[-1:],
        series[:100] + series[99:100] + series[101:],
        [series[0].replace("entries=32", "entries=33")] + series[1:],
        [series[0].replace("misses=32", "misses=33")] + series[1:],
        [series[0].replace("hits=0", "hits=1")] + series[1:],
        series[:-1] + ["C545D_DISPLAY_CACHE,hits=NaN,misses=32,entries=32"],
    )
    for mutant in mutants:
        try:
            check_series(cache_rows(mutant), "registry")
        except ValueError:
            continue
        raise AssertionError("malformed original cache sample accepted")
    print("C545D_COMBO256_CACHE_BOUND_SELFTEST_PASS,"
          "negative_cases=8,positive_cases=2,windows_runs=0,"
          "real_host_untouched=1")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--cache-source", type=Path)
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.root or not args.cache_source:
        parser.error("--root and --cache-source required")
    for row in audit(
        original.load(args.root),
        args.cache_source.read_text(encoding="utf-8")
    ):
        print(row)


if __name__ == "__main__":
    main()
