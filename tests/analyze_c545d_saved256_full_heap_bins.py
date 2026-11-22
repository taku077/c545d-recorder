#!/usr/bin/env python3
"""Reconstruct ALL exact (<2048B) saved256 HeapWalk size buckets offline.

The original probe reports each exact BUSY cbData size 0..2047, and caps
every larger size at bucket 2048. The *actual* total BUSY bytes and blocks
remain available in GIO_HEAP, so the >=2048-byte aggregate can be found
by subtracting all exactly known small-size data bytes and counts.

This is a same-run registered-vs-nochange counterfactual and a partial
Win32 HeapWalk inventory, NOT allocation-stack ownership, GLib source
identity, permanent leak proof, or full PSAPI PrivateUsage attribution.
Original Windows2022 run 44918598339 / sanitized artifact 14713900393.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
import analyze_gio_combo_msvc256_saved as saved

RUN = 44918598339
CAP = 2048
STAGES = (192, 256)
HEAP = re.compile(r"GIO_HEAP,cycle,(192|256),(\d+),(\d+),(\d+),(\d+)$")
SIZE = re.compile(r"GIO_HEAPSIZE,cycle,(192|256),(\d+),(\d+)$")
KNOWN = {
    24: (10, 0, 10),
    28: (3, 0, 3),
    56: (-1, 0, -1),
    120: (0, 0, 0),
    190: (0, 0, 0),
    194: (0, 0, 0),
    196: (0, 0, 0),
    360: (4, -1, 5),
}


def parse_one(raw: list[str], step: int) -> dict:
    lines = [l for l in raw if l.startswith(f"GIO_HEAP,cycle,{step},")]
    if len(lines) != 1:
        raise ValueError("missing_or_duplicate_heap_checkpoint")
    m = HEAP.fullmatch(lines[0])
    if m is None or int(m[1]) != step:
        raise ValueError("bad_heap_checkpoint_schema")
    blocks, total_busy, numheaps, bad = map(int, m.groups()[1:])
    if blocks < 0 or total_busy < 0 or numheaps < 1 or bad != 0:
        raise ValueError("incomplete_heap_enumeration")
    count = {}
    for row in raw:
        if not row.startswith(f"GIO_HEAPSIZE,cycle,{step},"):
            continue
        v = SIZE.fullmatch(row)
        if v is None or int(v[1]) != step:
            raise ValueError("malformed_size_bucket")
        size, n = int(v[2]), int(v[3])
        if not 0 <= size <= CAP or n <= 0 or size in count:
            raise ValueError("capped_bucket_invalid_or_duplicate")
        count[size] = n
    if sum(count.values()) != blocks:
        raise ValueError("heap_busy_blocks_do_not_match_all_bins")
    small = sum(s * n for s, n in count.items() if s < CAP)
    large_count = count.get(CAP, 0)
    large_bytes = total_busy - small
    if large_bytes < CAP * large_count or (large_count == 0 and large_bytes != 0):
        raise ValueError("large_block_bytes_not_consistent_with_bucket_cap")
    return {
        "counts": count,
        "blocks": blocks,
        "busy": total_busy,
        "small_bytes": small,
        "large_bytes": large_bytes,
        "large_count": large_count,
    }


def source_gate(src: str) -> None:
    # This exact sentinel explains why bin2048 cannot be multiplied by 2048
    # to recover its byte footprint. Protect original probe provenance.
    tokens = (
        "size_slot = entry.cbData < 2048 ? (unsigned int)entry.cbData : 2048U;",
        "c545d_heap_sizes[size_slot]++;",
        "busy_bytes += entry.cbData;",
        'printf("GIO_HEAPSIZE,%s,%d,%u,%llu\\n",',
        'printf("GIO_HEAP,%s,%d,%llu,%llu,%lu,%lu\\n",',
    )
    if any(src.count(t) != 1 for t in tokens):
        raise ValueError("original_heap_bin_source_semantics_drifted")


def inspect(root: Path, source: Path) -> list[str]:
    source_gate(source.read_text(encoding="utf-8"))
    group = saved.load(root)
    if not saved.analyze(group, print_output=False)[-1].startswith(
            "C545D_SAVED256_NUMERIC_ANALYSIS_PASS,"):
        raise ValueError("incomplete_pinned_four_arm_source")
    samples = {
        arm: {i: parse_one(group[f"combo-{arm}-256"], i) for i in STAGES}
        for arm in saved.ARMS
    }
    out = []
    for arm in saved.ARMS:
        for step in STAGES:
            d = samples[arm][step]
            out.append(
                "C545D_HEAP_FULLBINS_ARM,"
                f"source_run={RUN},mode=combo,arm={arm},cycle={step},"
                f"total_blocks={d['blocks']},total_busy={d['busy']},"
                f"small_lt2048_bytes={d['small_bytes']},"
                f"large_ge2048_bytes={d['large_bytes']},"
                f"large_ge2048_count={d['large_count']},"
                f"exact_small_size_classes={len(d['counts']) - int(CAP in d['counts'])},"
                "heapwalk_complete_check=1,allocation_site_unproven=1"
            )

    def delta(metric: str) -> int:
        r = samples["registry"]
        c = samples["nochange"]
        return ((r[256][metric] - r[192][metric]) -
                (c[256][metric] - c[192][metric]))

    total_busy_delta = delta("busy")
    small_busy_delta = delta("small_bytes")
    large_busy_delta = delta("large_bytes")
    if total_busy_delta != 28600 or small_busy_delta + large_busy_delta != total_busy_delta:
        raise ValueError("original_complete_busy_not_reconciled")
    buckets = sorted(
        set(samples["registry"][192]["counts"]) |
        set(samples["registry"][256]["counts"]) |
        set(samples["nochange"][192]["counts"]) |
        set(samples["nochange"][256]["counts"])
    )
    count_deltas = {}
    for size in buckets:
        def item(arm: str, step: int) -> int:
            return samples[arm][step]["counts"].get(size, 0)
        reg_delta = item("registry", 256) - item("registry", 192)
        no_delta = item("nochange", 256) - item("nochange", 192)
        controlled = reg_delta - no_delta
        count_deltas[size] = (reg_delta, no_delta, controlled)
        if size in KNOWN and count_deltas[size] != KNOWN[size]:
            raise ValueError("previously_pinned_selected_size_effect_changed")
    if any(size not in count_deltas for size in KNOWN):
        # A zero-size class can be entirely absent from the original output;
        # no presence is required for the zero-change selected bins.
        for size, expected in KNOWN.items():
            if size not in count_deltas and expected != (0, 0, 0):
                raise ValueError("mandatory_original_size_class_disappeared")
    selected = sum(size * count_deltas.get(size, (0, 0, 0))[2]
                   for size in KNOWN)
    if selected != 2068:
        raise ValueError("previous_selected8_reconstruction_mismatch")
    exact_reconstructed = sum(
        size * count_deltas[size][2] for size in buckets if size < CAP
    )
    if exact_reconstructed != small_busy_delta:
        raise ValueError("exact_small_histogram_failed_to_telescope")
    remaining_small = small_busy_delta - selected
    out.append(
        "C545D_HEAP_FULLBINS_RECONCILE,"
        f"source_run={RUN},mode=combo,window=192_256,"
        f"total_busy_effect={total_busy_delta},"
        f"small_lt2048_busy_effect={small_busy_delta},"
        f"large_ge2048_busy_effect={large_busy_delta},"
        f"selected8_effect={selected},"
        f"other_exact_small_effect={remaining_small},"
        f"largest_bucket_is_capped=1,"
        "not_private_usage=1,allocator_owner_unproven=1"
    )
    ranked = sorted(
        ((size, *info, size * info[2]) for size, info in count_deltas.items()
         if size < CAP and info[2] != 0),
        key=lambda x: (-abs(x[4]), x[0])
    )
    for rank, (size, reg, no, effect, nominal_bytes) in enumerate(ranked[:12], 1):
        out.append(
            "C545D_HEAP_FULLBINS_TOP,"
            f"source_run={RUN},rank={rank},size={size},"
            f"registry_raw_delta={reg},nochange_raw_delta={no},"
            f"controlled_count_delta={effect},"
            f"controlled_cbData_delta={nominal_bytes},"
            "exact_small_bucket=1,not_source_owner=1"
        )
    out.append(
        "C545D_HEAP_FULLBINS_PASS,"
        f"source_run={RUN},arms=2,checkpoints_each=2,"
        f"selected_size_classes={len(KNOWN)},"
        f"observed_size_classes={len(buckets)},"
        f"reported_top_classes={min(12, len(ranked))},"
        "original_256_windows_rerun=0,real_device_untouched=1,"
        "heapwalk_busy_reconciled=1,private_usage_owner_proven=0"
    )
    return out


def selftest() -> None:
    good = [
        "GIO_HEAP,cycle,192,3,2348,1,0",
        "GIO_HEAPSIZE,cycle,192,24,2",
        "GIO_HEAPSIZE,cycle,192,2048,1",
    ]
    got = parse_one(good, 192)
    assert (got["blocks"], got["small_bytes"], got["large_bytes"],
            got["large_count"]) == (3, 48, 2300, 1)
    corrupt = [
        good[:-1],
        good + [good[-1]],
        [good[0].replace("3,2348", "4,2348"), *good[1:]],
        [good[0].replace("2348", "2040"), *good[1:]],
        [good[0].replace(",1,0", ",1,1"), *good[1:]],
        [good[0], good[1].replace(",24,2", ",99999,2"), good[2]],
        [good[0], good[1].replace(",24,2", ",24,-2"), good[2]],
    ]
    for trial in corrupt:
        try:
            parse_one(trial, 192)
        except ValueError:
            continue
        raise AssertionError("invalid complete heap histogram accepted")
    print("C545D_HEAP_FULLBINS_SELFTEST_PASS,"
          "positive=1,negative=7,windows_runs=0,raw_uploaded=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--root", type=Path)
    p.add_argument("--probe-source", type=Path)
    args = p.parse_args()
    try:
        if args.selftest:
            selftest()
        else:
            if args.root is None or args.probe_source is None:
                p.error("--root and --probe-source required")
            print("\n".join(inspect(args.root, args.probe_source)))
    except (OSError, ValueError):
        print("C545D_HEAP_FULLBINS_FAIL,"
              "reason=INVALID_SOURCE_OR_ARCHIVE,raw_uploaded=0")
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
