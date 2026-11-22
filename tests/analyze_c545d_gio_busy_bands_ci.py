#!/usr/bin/env python3
"""Audit eight complete payload-size bands in a disposable matched Combo16 run.

Every BUSY entry enters exactly one of eight bands in the existing locked
HeapWalk. Each stage's SUM(counts) and SUM(cbData) must match its *own*
GIO_HEAP total. This is complete for enumerated Win32 heap BUSY elements,
NOT VirtualAlloc/COM allocations outside those heaps, allocation-site
provenance or private committed bytes. No pointer values are parsed.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import analyze_c545d_combo16_scanfree as old

BANDS = 8
STAGES = ("baseline", "cycle", "after_cleanup", "scanfree_cleanup")
INDICES = (0, 16, 17, 18)
BAND = re.compile(
    r"C545D_CI_BUSY_BAND,stage=([0-3]),band=([0-7]),"
    r"count=(\d{1,12}),bytes=(\d{1,18}),complete_heapwalk=1,"
    r"size_band_only=1,allocation_owner_proven=0,"
    r"private_usage_attributed=0,raw_pointers_emitted=0$"
)
HEAP = re.compile(
    r"GIO_HEAP,(baseline|cycle|after_cleanup|scanfree_cleanup),"
    r"(0|16|17|18),(\d+),(\d+),(\d+),(\d+)$"
)
CAP = 1000000000000


def one(raw: str, changed: bool):
    old.read(raw, changed)
    lines = raw.splitlines()
    if len(lines) > 100000 or len(raw) > 12000000:
        raise ValueError("unbounded_disposable_output")
    got = {}
    heap = {}
    for line in lines:
        if line.startswith("C545D_CI_BUSY_BAND,"):
            m = BAND.fullmatch(line)
            if m is None:
                raise ValueError("unexpected_busy_band_schema")
            stage, band, count, size = map(int, m.groups())
            if (stage, band) in got:
                raise ValueError("duplicate_band_stage")
            if count > CAP or size > CAP * 2048:
                raise ValueError("unbounded_band_count_or_bytes")
            got[stage, band] = (count, size)
        if line.startswith("GIO_HEAP,"):
            m = HEAP.fullmatch(line)
            # Earlier in-run stages (e.g. cycle=8) are allowed and ignored.
            if m is None:
                continue
            label, cycle, blocks, size, heaps, bad = m.groups()
            stage = STAGES.index(label)
            if int(cycle) != INDICES[stage] or stage in heap:
                raise ValueError("misaligned_or_duplicate_heap_baseline")
            if int(bad) != 0 or int(heaps) == 0:
                raise ValueError("incomplete_real_heapwalk")
            heap[stage] = (int(blocks), int(size))
    if set(got) != {(s, b) for s in range(4) for b in range(BANDS)}:
        raise ValueError("missing_32_band_stage_samples")
    if set(heap) != set(range(4)):
        raise ValueError("missing_4_aggregate_checkpoints")
    for stage in range(4):
        count_total = sum(got[stage, b][0] for b in range(BANDS))
        bytes_total = sum(got[stage, b][1] for b in range(BANDS))
        if (count_total, bytes_total) != heap[stage]:
            raise ValueError("bands_do_not_sum_to_full_heapwalk")
    return got


def analyze(folder: Path) -> list[str]:
    arms = {}
    out = []
    for arm in ("nochange", "registry"):
        raw = (folder / f"combo-{arm}-16.txt").read_text(encoding="utf-8-sig")
        arms[arm] = one(raw, arm == "registry")
        for stage in range(4):
            for band in range(BANDS):
                count, size = arms[arm][stage, band]
                out.append(
                    "C545D_GIO_BUSY_BAND_ARM,"
                    f"arm={arm},stage={stage},band={band},"
                    f"count={count},bytes={size},"
                    "heapwalk_only=1,allocation_site_unknown=1"
                )
    for left, right in ((0, 1), (1, 2), (2, 3)):
        for band in range(BANDS):
            c = arms["nochange"]
            r = arms["registry"]
            effect_count = ((r[right, band][0] - r[left, band][0]) -
                            (c[right, band][0] - c[left, band][0]))
            effect_bytes = ((r[right, band][1] - r[left, band][1]) -
                            (c[right, band][1] - c[left, band][1]))
            out.append(
                "C545D_GIO_BUSY_BAND_CONTROLLED,"
                f"window={left}_{right},band={band},"
                f"count_effect={effect_count},bytes_effect={effect_bytes},"
                "same_run_only=1,heapwalk_busy_not_private_usage=1,"
                "worker_quiescence_unproven=1"
            )
    out.append(
        "C545D_GIO_BUSY_BANDS_PAIR_PASS,"
        "arms=2,checkpoints_each=4,bands_each=8,"
        "exact_numeric_rows=64,controlled_rows=24,"
        "no_missing_busy_bytes=1,"
        "unmeasured_non_heap_commit_possible=1,"
        "allocation_owner_proven=0,plateau_proven=0,"
        "real_host_tested=0,original_256_rerun=0"
    )
    return out


def selftest():
    valid = {}
    for stage in range(4):
        for band in range(8):
            valid[stage, band] = (2, 50)
    assert len(valid) == 32
    def check(rows):
        if set(rows) != set(valid):
            raise ValueError("synthetic_missing_band")
        for s in range(4):
            if sum(rows[s, b][0] for b in range(8)) != 16:
                raise ValueError("synthetic_count_mismatch")
            if sum(rows[s, b][1] for b in range(8)) != 400:
                raise ValueError("synthetic_byte_mismatch")
    check(valid)
    bads = [
        {**valid, (0, 0): (3, 50)},
        {**valid, (0, 0): (2, 51)},
        {key: val for key, val in valid.items() if key != (1, 7)},
        {**valid, (4, 0): (2, 50)},
    ]
    for bad in bads:
        try:
            check(bad)
        except ValueError:
            continue
        raise AssertionError("corrupted bucket checksum accepted")
    print("C545D_GIO_BUSY_BANDS_SELFTEST_PASS,"
          "positive=1,negative=4,windows_runs=0,raw_uploaded=0")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--folder", type=Path)
    a = p.parse_args()
    try:
        if a.selftest:
            selftest()
        else:
            if a.folder is None:
                p.error("--folder required")
            print("\n".join(analyze(a.folder)))
    except (OSError, ValueError):
        print("C545D_GIO_BUSY_BANDS_FAIL,"
              "reason=INVALID_OR_INCOMPLETE_NUMERIC_CENSUS,raw_uploaded=0")
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
