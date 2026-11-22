#!/usr/bin/env python3
"""Independent sign-only triangulation of three *different* archived GIO16 runs.

Never merge the numeric magnitudes into a single memory curve. Validates
each original sanitized Windows Actions artifact through its independent
existing fail-closed archive validator, then reports whether each matched
registry-minus-nochange 0→16 experiment exhibits the same sign pattern.
No new GIO, Windows, camera, RTSP or other host run.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import analyze_c545d_heapregion_archived as region16
import analyze_c545d_heap_owner_archived as owner16
import analyze_c545d_gio_busy_bands_archived as bands16

# The *different* instrumentation may change absolute magnitudes/timing.
# (PrivateUsage delta, reported HeapWalk REGION commit delta, BUSY cbData).
EVIDENCE = (
    (44995353780, 14742913868, 151552, 143360, -11964, "region"),
    (45000301159, 14745224055, 290816, 221184, -7792, "owner"),
    (45020938670, 14754166140, 151552, 69632, -16136, "bands"),
)


def test_pattern(measures: tuple[tuple[int, int, int, int], ...]) -> str:
    seen = set()
    if len(measures) != 3:
        raise ValueError("missing_original_experiments")
    for run, private, region, busy in measures:
        if run in seen or run not in {x[0] for x in EVIDENCE}:
            raise ValueError("duplicate_or_unexpected_source_run")
        seen.add(run)
        if private <= 0 or region <= 0 or busy >= 0:
            raise ValueError("not_all_archived_signs_match")
    return (
        "C545D_GIO16_TRIANGULATION_PASS,"
        "independent_windows_source_runs=3,"
        "matched_0_16_positive_private=3,"
        "matched_0_16_positive_reported_region_commit=3,"
        "matched_0_16_negative_heapwalk_busy=3,"
        "cross_run_magnitudes_not_pooled=1,"
        "original_256_not_interpreted_from_16=1,"
        "precise_allocation_owner_proven=0,"
        "whole_heap_commit_coverage_proven=0,"
        "global_quiescence_proven=0,"
        "bounded_plateau_proven=0,"
        "host_recorder_tested=0,"
        "new_windows_runs=0"
    )


def check_originals(paths: tuple[Path, Path, Path]) -> str:
    if len(paths) != 3:
        raise ValueError("three_archived_source_files_required")
    expected = [(r, p, c, b) for r, _, p, c, b, _ in EVIDENCE]
    raw = [p.read_text(encoding="utf-8-sig") for p in paths]
    # Validate *entire exact archived reports* before any source inference.
    result0 = region16.validate(raw[0])
    if not any(x.startswith("C545D_HEAP_REGION_ARCHIVE_VERIFIED,") for x in result0):
        raise ValueError("first_source_not_verified")
    result1 = owner16.validate(raw[1])
    if not any(x.startswith("C545D_HEAP_OWNER_ARCHIVE_VERIFIED,") for x in result1):
        raise ValueError("second_source_not_verified")
    result2 = bands16.verify(raw[2])
    if not result2.startswith("C545D_GIO_BUSY_BANDS_ARCHIVE_PASS,"):
        raise ValueError("third_source_not_verified")
    # Cross-check the original validators' pinned controlled deltas, not an
    # invented common allocator identity across disparate Windows processes.
    current = (
        (EVIDENCE[0][0], region16.REGION_CONTROLLED["0_16"][1],
         region16.REGION_CONTROLLED["0_16"][0],
         region16.REGION_CONTROLLED["0_16"][2]),
        (EVIDENCE[1][0], owner16.REGIONS["0_16"][1],
         owner16.REGIONS["0_16"][0],
         owner16.REGIONS["0_16"][2]),
        (EVIDENCE[2][0], bands16.REGION["0_16"][1],
         bands16.REGION["0_16"][0],
         bands16.REGION["0_16"][2]),
    )
    if list(current) != expected:
        raise ValueError("source_validator_controlled_metrics_changed")
    return test_pattern(current)


def selftest() -> None:
    valid = tuple((r, p, c, b) for r, _, p, c, b, _ in EVIDENCE)
    assert test_pattern(valid).startswith("C545D_GIO16_TRIANGULATION_PASS,")
    bad = [
        valid[:2],
        (valid[0], valid[0], valid[2]),
        ((0, *valid[0][1:]), *valid[1:]),
        ((valid[0][0], 0, valid[0][2], valid[0][3]), *valid[1:]),
        (valid[0], (valid[1][0], valid[1][1], 0, valid[1][3]), valid[2]),
        (valid[0], valid[1], (valid[2][0], valid[2][1], valid[2][2], 1)),
    ]
    for altered in bad:
        try:
            test_pattern(altered)
        except ValueError:
            continue
        raise AssertionError("corrupted sign/provenance fixture accepted")
    print("C545D_GIO16_TRIANGULATION_SELFTEST_PASS,negative=6,"
          "positive=1,new_windows_runs=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--region", type=Path)
    p.add_argument("--owner", type=Path)
    p.add_argument("--bands", type=Path)
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    if not (a.region and a.owner and a.bands):
        p.error("--region --owner --bands are all required")
    print(check_originals((a.region, a.owner, a.bands)))


if __name__ == "__main__":
    main()
