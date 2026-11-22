#!/usr/bin/env python3
"""Verify what original saved256 HeapWalk histograms ACTUALLY preserve.

The Windows probe counted all busy cbData sizes 0..2047 plus a 2048
overflow bin. BUT the original GitHub Actions numeric-only exporter
explicitly saved ONLY eight exact sizes, rejecting all other
GIO_HEAPSIZE rows. The lost full histogram is NOT recoverable from
run 44918598339 artifact 14713900393. Do not rerun 256 cycles.

The original GIO_HEAP BUSY byte total remains, so selected eight-bin
bytes and the unclassified remainder can be reported. Remainder is NOT
measured free heap, allocator ownership, or PSAPI PrivateUsage leakage.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import analyze_gio_combo_msvc256_saved as saved

OLD = 44918598339
LEFT = ("cycle", 192)
RIGHT = ("cycle", 256)
ALLOWED = (24, 28, 56, 120, 190, 194, 196, 360)
BIN = re.compile(r"GIO_HEAPSIZE,(?:baseline|cycle|after_cleanup|settled_cleanup),"
                 r"\d+,(\d+),(\d+)$")

# The original exporter is a whitelist, not a complete histogram.
EXPORT_FILTER = (
    "$bin='^GIO_HEAPSIZE,(?:baseline|cycle|after_cleanup|settled_cleanup),"
    "[0-9]+,(?:24|28|56|120|190|194|196|360),[0-9]+$'"
)
EXPORT_DROP = """if($line -match '^GIO_HEAPSIZE,'){
                if($line -cmatch $bin){$rows.Add("$tag|$line")}
                continue
              }"""
ORIGINAL_PROBE_BUCKET = (
    "size_slot = entry.cbData < 2048 ? (unsigned int)entry.cbData : 2048U;"
)


def audit_filter(exporter: str, probe: str) -> None:
    if exporter.count(EXPORT_FILTER) != 1 or exporter.count(EXPORT_DROP) != 1:
        raise ValueError("original_exporter_whitelist_or_skip_drifted")
    if probe.count(ORIGINAL_PROBE_BUCKET) != 1 or \
       probe.count("c545d_heap_sizes[size_slot]++;") != 1 or \
       probe.count("busy_bytes += entry.cbData;") != 1:
        raise ValueError("full_probe_histogram_semantics_drifted")


def audit_archive(root: Path, exporter: str, probe: str) -> list[str]:
    audit_filter(exporter, probe)
    group = saved.load(root)
    pass_marker = saved.analyze(group, print_output=False)[-1]
    if not pass_marker.startswith("C545D_SAVED256_NUMERIC_ANALYSIS_PASS,"):
        raise ValueError("original_four_arm_archive_incomplete")
    # Every size-bin row that survived must be one of the eight explicitly
    # allowed by exporter; absence is NOT proof that a size had zero blocks.
    records = 0
    for tag in saved.TAGS:
        for row in group[tag]:
            if not row.startswith("GIO_HEAPSIZE,"):
                continue
            m = BIN.fullmatch(row)
            if m is None or int(m[1]) not in ALLOWED or int(m[2]) <= 0:
                raise ValueError("unexpected_nonwhitelisted_saved_size_record")
            records += 1
    if records == 0:
        raise ValueError("missing_selected_histogram_data")
    data = {arm: saved.parse(group, "combo", arm) for arm in saved.ARMS}
    def effect(metric: str) -> int:
        return saved.difference(data, metric, LEFT, RIGHT)

    expected = {
        24: 10, 28: 3, 56: -1, 120: 0,
        190: 0, 194: 0, 196: 0, 360: 5
    }
    selected = 0
    for size in ALLOWED:
        selected_delta = saved.difference(
            {arm: data[arm]["bins"] for arm in saved.ARMS},
            size, LEFT, RIGHT
        )
        if selected_delta != expected[size]:
            raise ValueError("selected_size_original_effect_changed")
        selected += size * selected_delta
    all_busy = effect("heap")
    private = effect("mem")
    if (selected, all_busy, private) != (2068, 28600, 53248):
        raise ValueError("pinned_original_byte_accounting_changed")
    remainder = all_busy - selected
    if remainder != 26532:
        raise ValueError("saved_unclassified_busy_remainder_changed")
    return [
        "C545D_SAVED256_EXPORT_SCOPE,"
        f"source_run={OLD},saved_bin_records={records},"
        "full_probe_sized_histogram=1,"
        "exporter_kept_only_eight_sizes=1,"
        "other_exact_sizes_not_archived=1,"
        "capped_ge2048_class_not_archived=1,"
        "full_histogram_recovery_possible=0",
        "C545D_SAVED256_PARTIAL_BUSY_SCOPE,"
        f"source_run={OLD},window=192_256,"
        f"selected_eight_size_busy_delta={selected},"
        f"total_heapwalk_busy_delta={all_busy},"
        f"unclassified_other_size_busy_delta={remainder},"
        f"private_usage_delta={private},"
        "unclassified_cannot_be_subdivided_from_artifact=1,"
        "not_free_heap_bytes=1,not_allocation_site=1",
        "C545D_SAVED256_ARCHIVE_SCOPE_PASS,"
        "original_256_rerun=0,new_windows_runs=0,"
        "raw_256_dump_unavailable=1,release_approved=0,"
        "host_untouched=1,manual_measurement_requested=0",
    ]


def selftest() -> None:
    valid_exporter = EXPORT_FILTER + "\n" + EXPORT_DROP
    valid_probe = ORIGINAL_PROBE_BUCKET + "\n" + (
        "c545d_heap_sizes[size_slot]++;\n"
        "busy_bytes += entry.cbData;"
    )
    audit_filter(valid_exporter, valid_probe)
    corruptions = (
        (valid_exporter.replace("|360", "|361"), valid_probe),
        (valid_exporter.replace("continue", "break"), valid_probe),
        (valid_exporter.replace("$line -cmatch $bin", "$line -cmatch $other"),
         valid_probe),
        (valid_exporter, valid_probe.replace("2048U", "4096U")),
        (valid_exporter, valid_probe.replace("busy_bytes += entry.cbData;",
                                           "busy_bytes += 0;")),
    )
    for bad_exporter, bad_probe in corruptions:
        try:
            audit_filter(bad_exporter, bad_probe)
        except ValueError:
            continue
        raise AssertionError("changed original archive-size whitelist accepted")
    print("C545D_SAVED256_ARCHIVE_SCOPE_SELFTEST_PASS,"
          "positive=1,negative=5,windows_runs=0,raw_uploaded=0")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--root", type=Path)
    ap.add_argument("--exporter", type=Path)
    ap.add_argument("--probe", type=Path)
    args = ap.parse_args()
    try:
        if args.selftest:
            selftest()
        else:
            if args.root is None or args.exporter is None or args.probe is None:
                ap.error("--root, --exporter and --probe required")
            print("\n".join(audit_archive(
                args.root,
                args.exporter.read_text(encoding="utf-8"),
                args.probe.read_text(encoding="utf-8")
            )))
    except (OSError, ValueError):
        print("C545D_SAVED256_ARCHIVE_SCOPE_FAIL,"
              "reason=SOURCE_OR_WHITELIST_INVALID,raw_uploaded=0")
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
