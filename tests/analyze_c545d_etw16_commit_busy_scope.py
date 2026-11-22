#!/usr/bin/env python3
"""Reconcile archived Combo16 private commit, heap region and BUSY trajectories.

Source is the already downloaded numeric-only archive of Windows run
45015173260, never ETL, addresses or symbol strings. Unlike an allocation
census, HeapWalk BUSY cbData and optional Heap REGION committed bytes are
*different metrics*. Their difference is descriptive, NOT measured free bytes
or proof of a specific retained allocation/allocator owner.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

import analyze_c545d_etw16_frozen_archive as frozen

WINDOWS = ("0_16", "16_17", "17_18")
# (region commit, PSAPI private usage, HeapWalk BUSY), controlled A/B
EXPECTED = {
    "0_16": (155648, 221184, -7794),
    "16_17": (40960, 40960, -852951),
    "17_18": (0, 4096, 852951),
}
REGION = re.compile(
    r"C545D_HEAP_REGION_CONTROLLED,window=(0_16|16_17|17_18),"
    r"region_commit_delta=(-?\d+),private_delta=(-?\d+),"
    r"busy_cbData_delta=(-?\d+),optional_data_incomplete=0,"
    r"heap_region_largemalloc_coverage_proven=0,"
    r"cause_of_private_delta_proven=0$"
)
HEAP_COHORT = re.compile(
    r"C545D_HEAP_OWNER_COHORT,cohort=(default|other),"
    r"registry_growth=(-?\d+),nochange_growth=(-?\d+),"
    r"controlled_growth=(-?\d+),source_owner_proven=0,"
    r"region_coverage_complete=0,cross_process_heap_identity_assumed=0$"
)
PHASE = re.compile(
    r"C545D_APPINFO_PHASE_TRACE,arm=(nochange|registry),"
    r"callbacks=(\d+),workers=(\d+),idle_ms=(\d+),"
    r"callbacks_idle=(\d+),worker_scans_idle=(\d+),"
    r"parser_ends_idle=(\d+),worker_active_after_cleanup=([01]),"
    r"worker_active_final=([01]),worker_completed_after_cleanup=(\d+),"
    r"boundary_tick_ambiguous=([01]),"
    r"timing_perturbation_possible=1,quiescence_proven=0$"
)


def unique_records(content: str, marker: str, pattern: re.Pattern[str]) -> dict[str, tuple[int, ...]]:
    found: dict[str, tuple[int, ...]] = {}
    for row in content.splitlines():
        if not row.startswith(marker):
            continue
        m = pattern.fullmatch(row)
        if m is None:
            raise ValueError("unexpected_numeric_metric_schema")
        key = m.group(1)
        if key in found:
            raise ValueError("duplicate_numeric_metric")
        values = tuple(map(int, m.groups()[1:]))
        found[key] = values
    return found


def analyze(content: str) -> list[str]:
    # Exact original two-arm frame counts and all existing privacy/safety
    # checks must pass first. Never derive a conclusion from another run.
    frozen.verify(content)
    region = unique_records(content, "C545D_HEAP_REGION_CONTROLLED,", REGION)
    heaps = unique_records(content, "C545D_HEAP_OWNER_COHORT,", HEAP_COHORT)
    phases = unique_records(content, "C545D_APPINFO_PHASE_TRACE,arm=", PHASE)
    if region != EXPECTED:
        raise ValueError("controlled_heap_region_or_private_counts_changed")
    if heaps != {"default": (155648, 0, 155648), "other": (0, 0, 0)}:
        raise ValueError("changed_default_vs_other_heap_commit")
    if set(phases) != {"registry", "nochange"}:
        raise ValueError("missing_phase_arm")
    # Phase tuple: callback, workers, idle, callback_idle, scans_idle,
    # parser_idle, worker_after_cleanup, worker_final, completed, ambiguous.
    if (phases["nochange"] != (0, 1, 2515, 0, 0, 0, 0, 0, 0, 0)
            or phases["registry"] != (17, 18, 2516, 0, 1, 1, 1, 0, 1, 1)):
        raise ValueError("saved_phase_chronology_changed")
    out: list[str] = []
    for window in WINDOWS:
        commit, private, busy = region[window]
        out.append(
            "C545D_GIO_COMMIT_BUSY_SCOPE,"
            f"window={window},private_delta={private},"
            f"reported_region_commit_delta={commit},heapwalk_busy_delta={busy},"
            f"private_minus_reported_commit={private-commit},"
            f"reported_commit_minus_busy_delta={commit-busy},"
            "difference_not_free_bytes=1,alloc_owner_unproven=1"
        )
    commit = sum(region[w][0] for w in WINDOWS)
    private = sum(region[w][1] for w in WINDOWS)
    busy = sum(region[w][2] for w in WINDOWS)
    assert (commit, private, busy) == (196608, 266240, -7794)
    out += [
        "C545D_GIO_COMMIT_BUSY_FINAL,"
        f"window=0_18,private_delta={private},"
        f"reported_region_commit_delta={commit},heapwalk_busy_delta={busy},"
        f"private_minus_reported_commit={private-commit},"
        "region_commit_not_full_process_commit=1,"
        "no_exact_live_alloc_ownership=1",
        "C545D_GIO_COMMIT_BUSY_QUIESCENCE,"
        "registry_worker_active_after_cleanup=1,"
        "registry_worker_scans_in_idle=1,"
        "boundary_timestamp_ambiguous=1,"
        "global_quiescence_proven=0,"
        "recording_host_tested=0",
        "C545D_GIO_COMMIT_BUSY_ARCHIVE_PASS,"
        "source_run=45015173260,exact_archive=1,"
        "original_256_rerun=0,new_windows_runs=0,"
        "allocator_retention_plausible_not_proven=1,"
        "memory_leak_zero_proven=0,allocation_owner_proven=0",
    ]
    return out


def fixture() -> str:
    rows = [frozen.safe_row("nochange"), frozen.safe_row("registry")]
    rows += [
        "C545D_HEAP_REGION_CONTROLLED,"
        f"window={window},region_commit_delta={v[0]},"
        f"private_delta={v[1]},busy_cbData_delta={v[2]},"
        "optional_data_incomplete=0,"
        "heap_region_largemalloc_coverage_proven=0,"
        "cause_of_private_delta_proven=0"
        for window, v in EXPECTED.items()
    ]
    rows += [
        "C545D_HEAP_OWNER_COHORT,"
        f"cohort={cohort},registry_growth={v[0]},"
        f"nochange_growth={v[1]},controlled_growth={v[2]},"
        "source_owner_proven=0,region_coverage_complete=0,"
        "cross_process_heap_identity_assumed=0"
        for cohort, v in (("default", (155648, 0, 155648)),
                          ("other", (0, 0, 0)))
    ]
    for arm, data in [
        ("nochange", (0, 1, 2515, 0, 0, 0, 0, 0, 0, 0)),
        ("registry", (17, 18, 2516, 0, 1, 1, 1, 0, 1, 1)),
    ]:
        rows += [
            "C545D_APPINFO_PHASE_TRACE,"
            f"arm={arm},callbacks={data[0]},workers={data[1]},"
            f"idle_ms={data[2]},callbacks_idle={data[3]},"
            f"worker_scans_idle={data[4]},parser_ends_idle={data[5]},"
            f"worker_active_after_cleanup={data[6]},"
            f"worker_active_final={data[7]},"
            f"worker_completed_after_cleanup={data[8]},"
            f"boundary_tick_ambiguous={data[9]},"
            "timing_perturbation_possible=1,quiescence_proven=0"
        ]
    return "\n".join(rows)


def selftest() -> None:
    good = fixture()
    result = analyze(good)
    assert len(result) == 6 and result[-1].startswith(
        "C545D_GIO_COMMIT_BUSY_ARCHIVE_PASS,"
    )
    bad = [
        good.replace("private_delta=221184", "private_delta=221183"),
        good.replace("region_commit_delta=155648", "region_commit_delta=155649"),
        good.replace("busy_cbData_delta=-7794", "busy_cbData_delta=-7793"),
        good.replace("worker_active_after_cleanup=1",
                     "worker_active_after_cleanup=0"),
        good.replace("controlled_growth=155648", "controlled_growth=155649"),
        good + "\n" + next(
            x for x in good.splitlines() if
            x.startswith("C545D_HEAP_REGION_CONTROLLED,")
        ),
    ]
    assert all(x != good for x in bad)
    for corrupt in bad:
        try:
            analyze(corrupt)
        except ValueError:
            continue
        raise AssertionError("altered resource/phase data accepted")
    print("C545D_GIO_COMMIT_BUSY_SELFTEST_PASS,"
          "positive=1,negative=6,windows_runs=0,raw_uploaded=0")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.source is None:
        parser.error("--source required")
    try:
        print("\n".join(analyze(
            args.source.read_text(encoding="utf-8-sig")
        )))
    except (OSError, ValueError):
        print("C545D_GIO_COMMIT_BUSY_ARCHIVE_FAIL,"
              "reason=NUMERIC_ARCHIVE_INVALID,raw_uploaded=0")
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
