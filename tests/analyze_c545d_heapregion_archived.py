#!/usr/bin/env python3
"""Fail-closed replay of actual Windows2022 run #44995353780 numeric artifact.

The archived Windows runner ran disposable GLib 2.82.4 Combo with two 16-cycle
arms. This is *not* the earlier #44992842208 phase/heap snapshot or the
original four-arm 256-cycle #44918598339 experiment.

Source artifact: c545d-combo16-scanfree-numeric-only-CI, id 14742913868.
Metrics are control-subtracted differences across separate processes.
A ratio between PROCESS_HEAP_REGION.dwCommittedSize and PrivateUsage is
ONLY a numeric scale comparison; it does not prove allocation ownership,
exact coverage of all heaps, stable region identity or a global idle state.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
from pathlib import Path

RUN = 44995353780
ARTIFACT = 14742913868
WINDOWS = ("0_16", "16_17", "17_18")
TYPES = {
    "GWin32AppInfo": (0, 0, 0),
    "GWin32AppInfoApplication": (0, -118, 118),
    "GWin32AppInfoFileExtension": (0, -312, 312),
    "GWin32AppInfoHandler": (0, -344, 344),
    "GWin32AppInfoShellVerb": (0, -593, 593),
    "GWin32AppInfoURLSchema": (0, -28, 28),
    "GWin32RegistryKey": (0, -225, 225),
}
RESOURCES = {
    ("private", "0_16"): (192512, 40960, 151552),
    ("private", "16_17"): (0, 0, 0),
    ("private", "17_18"): (0, 0, 0),
    ("busy", "0_16"): (-11964, 0, -11964),
    ("busy", "16_17"): (-756485, 0, -756485),
    ("busy", "17_18"): (756485, 0, 756485),
}
PHASES = {
    "nochange": (0, 1, 2532, 0, 0, 0, 0, 0, 0, 0),
    "registry": (17, 18, 2516, 0, 1, 1, 1, 0, 1, 1),
}
PHASE_NAMES = (
    "callbacks", "workers", "idle_ms", "callbacks_idle",
    "worker_scans_idle", "parser_ends_idle", "worker_active_after_cleanup",
    "worker_active_final", "worker_completed_after_cleanup",
    "boundary_tick_ambiguous",
)
REGION_COMMIT = {
    ("nochange", "baseline", 0): 2342912,
    ("nochange", "cycle", 16): 2342912,
    ("nochange", "after_cleanup", 17): 2342912,
    ("nochange", "scanfree_cleanup", 18): 2342912,
    ("registry", "baseline", 0): 2215936,
    ("registry", "cycle", 16): 2359296,
    ("registry", "after_cleanup", 17): 2359296,
    ("registry", "scanfree_cleanup", 18): 2359296,
}
REGION_CONTROLLED = {
    "0_16": (143360, 151552, -11964),
    "16_17": (0, 0, -756485),
    "17_18": (0, 0, 756485),
}
POINTS = (
    ("baseline", 0), ("cycle", 16),
    ("after_cleanup", 17), ("scanfree_cleanup", 18),
)


def expected_lines() -> list[str]:
    rows: list[str] = []
    for (kind, window), (reg, nochange, controlled) in RESOURCES.items():
        rows.append(
            f"C545D_COMBO16_SCANFREE_RESOURCE,kind={kind},window={window},"
            f"registry_raw={reg},nochange_raw={nochange},controlled={controlled},"
            "new_alloc_site_proven=0,real_host_untested=1"
        )
    for typ, values in TYPES.items():
        for window, value in zip(WINDOWS, values):
            rows.append(
                f"C545D_COMBO16_SCANFREE_GOBJECT,type={typ},window={window},"
                f"registry_raw={value},nochange_raw=0,controlled={value},"
                "instance_count_not_heap_owner=1,CI_only=1"
            )
    rows.append(
        "C545D_COMBO16_SCANFREE_PASS,source_mode=combo,cycles=16,"
        "valid_GObject_types=7,GObject_census_unavailable=0,"
        "GAppInfo_final_query_skipped=1,worker_quiescence_unproven=1,"
        "results_not_256cycle_equivalent=1,production_unmodified=1,"
        "host_install_approved=0,CI_only=1"
    )
    for arm, counters in PHASES.items():
        d = {"arm": arm}
        d.update(zip(PHASE_NAMES, counters))
        rows.append(
            "C545D_APPINFO_PHASE_TRACE,"
            + ",".join(f"{k}={v}" for k, v in d.items())
            + ",timing_perturbation_possible=1,quiescence_proven=0"
        )
    rows.append(
        "C545D_APPINFO_PHASE_TRACE_PASS,arms=2,cycles=16,"
        "GAppInfo_final_query_skipped=1,allocation_owner_proven=0,"
        "real_camera=0,host_modified=0"
    )
    for (arm, phase, cycle), committed in REGION_COMMIT.items():
        rows.append(
            "C545D_HEAP_REGION_OBSERVATION,"
            f"arm={arm},phase={phase},cycle={cycle},regions=8,"
            f"known=8,unknown=0,reported_region_commit={committed},"
            "whole_heap_commit_proven=0,global_quiescence_proven=0"
        )
    for window, (region, private, busy) in REGION_CONTROLLED.items():
        rows.append(
            "C545D_HEAP_REGION_CONTROLLED,"
            f"window={window},region_commit_delta={region},"
            f"private_delta={private},busy_cbData_delta={busy},"
            "optional_data_incomplete=0,"
            "heap_region_largemalloc_coverage_proven=0,"
            "cause_of_private_delta_proven=0"
        )
    rows.append(
        "C545D_HEAP_REGION_16_PASS,arms=2,cycles=16,windows16_only=1,"
        "original_256_not_rerun=1,real_camera=0,release_approved=0,"
        "global_quiescence_proven=0"
    )
    return rows


def validate(raw: str) -> list[str]:
    rows = [line.strip() for line in raw.splitlines() if line.strip()]
    expected = expected_lines()
    if len(set(expected)) != len(expected):
        raise AssertionError("internal expected numeric fixture duplicated")
    if len(rows) != len(expected) or len(set(rows)) != len(rows):
        raise ValueError("missing or duplicated archived numeric record")
    missing, extra = set(expected) - set(rows), set(rows) - set(expected)
    if missing or extra:
        raise ValueError(f"pinned archived numeric record mismatch: "
                         f"missing={len(missing)},extra={len(extra)}")
    # These are arithmetic identities in same-run *control-subtracted*
    # windows, not additive ownership claims about private memory.
    region_delta, private_delta, busy_delta = REGION_CONTROLLED["0_16"]
    if (REGION_COMMIT["registry", "cycle", 16]
            - REGION_COMMIT["registry", "baseline", 0]
            - (REGION_COMMIT["nochange", "cycle", 16]
               - REGION_COMMIT["nochange", "baseline", 0])
            != region_delta):
        raise AssertionError("internal region arithmetic mismatch")
    if (private_delta - region_delta != 8192
            or Fraction(region_delta, private_delta) != Fraction(35, 37)
            or busy_delta != -11964):
        raise AssertionError("internal resource arithmetic mismatch")
    for window in ("16_17", "17_18"):
        region, private, _ = REGION_CONTROLLED[window]
        if (region, private) != (0, 0):
            raise AssertionError("internal cleanup-region contract mismatch")
    drop = sum(values[1] for values in TYPES.values())
    rebound = sum(values[2] for values in TYPES.values())
    if (drop, rebound) != (-1620, 1620):
        raise AssertionError("internal GObject rebound count mismatch")
    if (PHASES["registry"][4], PHASES["registry"][6],
            PHASES["registry"][7]) != (1, 1, 0):
        raise AssertionError("internal worker phase mismatch")
    return [
        f"C545D_HEAP_REGION_ARCHIVE_VERIFIED,source_run={RUN},"
        f"artifact_id={ARTIFACT},resource_windows=6,gobject_windows=21,"
        "region_observations=8,region_windows=3,phase_arms=2,"
        "original_windows_rerun=0",
        "C545D_HEAP_REGION_ARCHIVE_INFERENCE,source_run=44995353780,"
        "private_delta=151552,reported_region_commit_delta=143360,"
        "numeric_difference=8192,numeric_fraction=35/37,"
        "heap_busy_cbData_delta=-11964,"
        "reported_region_count=8,reported_region_known=8,"
        "reported_region_unknown=0,"
        "cleanup_region_commit_delta=0,cleanup_private_delta=0,"
        "gobject_drop=-1620,gobject_rebound=1620,"
        "worker_scans_idle=1,tick_boundary_ambiguous=1,"
        "same_process_allocation_owner_proven=0,"
        "whole_heap_commit_proven=0,global_quiescence_proven=0,"
        "original_256_equivalence_proven=0,real_host_untouched=1",
    ]


def selftest() -> None:
    valid = "\n".join(expected_lines())
    assert len(validate(valid)) == 2
    assert len(validate("\n".join(reversed(expected_lines())))) == 2
    cases = [
        valid.replace("controlled=151552", "controlled=151553", 1),
        valid.replace("reported_region_commit=2359296",
                      "reported_region_commit=2355200", 1),
        valid.replace("regions=8,known=8,unknown=0",
                      "regions=8,known=7,unknown=1", 1),
        valid.replace("worker_scans_idle=1", "worker_scans_idle=0", 1),
        valid.replace("boundary_tick_ambiguous=1",
                      "boundary_tick_ambiguous=0", 1),
        valid.replace("original_256_not_rerun=1",
                      "original_256_not_rerun=0", 1),
        valid.replace("cause_of_private_delta_proven=0",
                      "cause_of_private_delta_proven=1", 1),
        valid.replace("GAppInfo_final_query_skipped=1",
                      "GAppInfo_final_query_skipped=0", 1),
        valid.replace("heap_region_largemalloc_coverage_proven=0",
                      "heap_region_largemalloc_coverage_proven=1", 1),
        "\n".join(expected_lines()[:-1]),
        valid + "\n" + expected_lines()[0],
        valid + "\nC545D_UNEXPECTED_METRIC,x=0",
    ]
    for case in cases:
        if case == valid:
            raise AssertionError("mutant fixture did not change original")
        try:
            validate(case)
        except ValueError:
            pass
        else:
            raise AssertionError("corrupted archive was accepted")
    print(f"C545D_HEAP_REGION_ARCHIVE_SELFTEST_PASS,negative_cases={len(cases)},"
          "positive_cases=2,source_windows_rerun=0,host_modified=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--source", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
    else:
        if args.source is None:
            p.error("--source required")
        print("\n".join(validate(
            args.source.read_text(encoding="utf-8-sig")
        )))


if __name__ == "__main__":
    main()
