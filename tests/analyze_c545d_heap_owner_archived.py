#!/usr/bin/env python3
"""Pinned replay of actual Windows2022 short Combo16 run #45000301159.

Source numeric-only artifact ID 14745224055. This only verifies numeric
evidence, never calls GIO, Windows APIs, or an installed Tapo recorder.
Do not merge with 256-cycle uninstrumented measurements or interpret
REGION commitment as full PrivateUsage or proof of allocation-site ownership.
"""
from __future__ import annotations
import argparse
from pathlib import Path

RUN = 45000301159
ARTIFACT = 14745224055
POINTS = ("baseline", "cycle16", "after_cleanup", "scanfree_final")

# All eight actual process-local ordinal profiles. Across independent
# processes the ordinal is NOT the same heap identity.
HEAPS = {
    "nochange": {
        0: (1, 2179072, 2179072, 2179072, 2179072, 0),
        1: (0, 4096, 4096, 4096, 4096, 0),
        2: (0, 57344, 57344, 57344, 57344, 0),
        3: (0, 8192, 8192, 8192, 8192, 0),
    },
    "registry": {
        0: (1, 2351104, 2572288, 2572288, 2572288, -7792),
        1: (0, 4096, 4096, 4096, 4096, 0),
        2: (0, 57344, 57344, 57344, 57344, 0),
        3: (0, 8192, 8192, 8192, 8192, 0),
    },
}
RESOURCES = {
    ("private", "0_16"): (331776, 40960, 290816),
    ("private", "16_17"): (4096, 0, 4096),
    ("private", "17_18"): (-8192, 0, -8192),
    ("busy", "0_16"): (-7792, 0, -7792),
    ("busy", "16_17"): (-757030, 0, -757030),
    ("busy", "17_18"): (757030, 0, 757030),
}
REGIONS = {
    "0_16": (221184, 290816, -7792),
    "16_17": (0, 4096, -757030),
    "17_18": (0, -8192, 757030),
}
SENTINEL = (
    "C545D_HEAP_OWNER_PASS,arms=2,cycles=16,"
    "same_process_heap_identity_verified=1,"
    "default_vs_other_commit_partition_verified=1,"
    "optional_region_commit_not_full_private=1,"
    "original_256_not_rerun=1,real_device_untested=1,"
    "recording_process_untouched=1"
)


def exact_records(raw: str, prefix: str, expected: list[str]) -> None:
    observed = [l.strip() for l in raw.splitlines() if l.startswith(prefix)]
    if len(observed) != len(expected) or set(observed) != set(expected):
        raise ValueError(f"{prefix} missing/altered/duplicated numeric evidence")


def expected_owner() -> list[str]:
    records = []
    for arm, per_heap in HEAPS.items():
        for ordinal, (default, baseline, cycle, after, final, busy) in per_heap.items():
            records.append(
                "C545D_HEAP_OWNER_HISTORY,"
                f"arm={arm},heap_ordinal_local={ordinal},"
                f"is_default={default},"
                f"commit_baseline={baseline},commit_cycle16={cycle},"
                f"commit_after_cleanup={after},commit_scanfree_final={final},"
                f"commit_change_0_16={cycle-baseline},"
                f"busy_data_change_0_16={busy},"
                "identity_stable_in_process=1,"
                "cross_process_heap_ordinal_comparable=0"
            )
    return records


def expected_resources() -> list[str]:
    return [
        "C545D_COMBO16_SCANFREE_RESOURCE,"
        f"kind={kind},window={window},registry_raw={reg},"
        f"nochange_raw={nochange},controlled={controlled},"
        "new_alloc_site_proven=0,real_host_untested=1"
        for (kind, window), (reg, nochange, controlled) in RESOURCES.items()
    ]


def expected_regions() -> list[str]:
    return [
        "C545D_HEAP_REGION_CONTROLLED,"
        f"window={window},region_commit_delta={committed},"
        f"private_delta={private},busy_cbData_delta={busy},"
        "optional_data_incomplete=0,"
        "heap_region_largemalloc_coverage_proven=0,"
        "cause_of_private_delta_proven=0"
        for window, (committed, private, busy) in REGIONS.items()
    ]


def expected_cohorts() -> list[str]:
    return [
        "C545D_HEAP_OWNER_COHORT,"
        f"cohort={cohort},registry_growth={growth},nochange_growth=0,"
        f"controlled_growth={growth},source_owner_proven=0,"
        "region_coverage_complete=0,cross_process_heap_identity_assumed=0"
        for cohort, growth in (("default", 221184), ("other", 0))
    ]


def validate(raw: str) -> list[str]:
    exact_records(raw, "C545D_HEAP_OWNER_HISTORY,", expected_owner())
    exact_records(raw, "C545D_HEAP_OWNER_COHORT,", expected_cohorts())
    exact_records(raw, "C545D_HEAP_OWNER_PASS,", [SENTINEL])
    exact_records(raw, "C545D_HEAP_REGION_CONTROLLED,", expected_regions())
    exact_records(raw, "C545D_COMBO16_SCANFREE_RESOURCE,", expected_resources())
    if HEAPS["registry"][0][2] - HEAPS["registry"][0][1] != 221184:
        raise AssertionError("pinned process baseline contradiction")
    for arm in HEAPS:
        if (sum(HEAPS[arm][i][2] - HEAPS[arm][i][1] for i in HEAPS[arm])
                != (221184 if arm == "registry" else 0)):
            raise AssertionError("per-heap commit arithmetic mismatch")
    if REGIONS["0_16"] != (221184, 290816, -7792):
        raise AssertionError("source-type mixing")
    if REGIONS["0_16"][1] - REGIONS["0_16"][0] != 69632:
        raise AssertionError("numeric scale difference changed")
    # Counter check for related but NOT causally attributed GObject rebound.
    types = ("GWin32AppInfoApplication", "GWin32AppInfoFileExtension",
             "GWin32AppInfoHandler", "GWin32AppInfoShellVerb",
             "GWin32AppInfoURLSchema", "GWin32RegistryKey")
    counts = (118, 312, 344, 593, 28, 227)
    for typ, count in zip(types, counts):
        for window, change in (("16_17", -count), ("17_18", count)):
            exact_records(
                raw, f"C545D_COMBO16_SCANFREE_GOBJECT,type={typ},window={window},",
                [f"C545D_COMBO16_SCANFREE_GOBJECT,type={typ},window={window},"
                 f"registry_raw={change},nochange_raw=0,controlled={change},"
                 "instance_count_not_heap_owner=1,CI_only=1"]
            )
    return [
        "C545D_HEAP_OWNER_ARCHIVE_VERIFIED,source_run=45000301159,"
        "artifact_id=14745224055,arms=2,heaps_per_arm=4,"
        "phase_checkpoints=4,resource_windows=6,"
        "new_windows_runs=0,real_host_untouched=1",
        "C545D_HEAP_OWNER_ARCHIVE_INFERENCE,"
        "default_heap_controlled_region_commit_delta=221184,"
        "other_three_heaps_controlled_region_commit_delta=0,"
        "PrivateUsage_controlled_delta=290816,"
        "busy_cbData_controlled_delta=-7792,"
        "numeric_private_minus_visible_region_commit=69632,"
        "gobject_drop=-1622,gobject_rebound=1622,"
        "region_commit_source_owner_proven=0,"
        "original_256_same_owner_proven=0,"
        "global_quiescence_proven=0,"
        "instrumentation_timing_perturbation_possible=1"
    ]


def fixture() -> str:
    rows = expected_owner() + expected_cohorts() + [SENTINEL]
    rows += expected_regions() + expected_resources()
    types = ("GWin32AppInfoApplication", "GWin32AppInfoFileExtension",
             "GWin32AppInfoHandler", "GWin32AppInfoShellVerb",
             "GWin32AppInfoURLSchema", "GWin32RegistryKey")
    counts = (118, 312, 344, 593, 28, 227)
    for typ, count in zip(types, counts):
        for window, change in (("16_17", -count), ("17_18", count)):
            rows.append(
                f"C545D_COMBO16_SCANFREE_GOBJECT,type={typ},window={window},"
                f"registry_raw={change},nochange_raw=0,controlled={change},"
                "instance_count_not_heap_owner=1,CI_only=1"
            )
    return "\n".join(rows)


def selftest():
    valid = fixture()
    assert len(validate(valid)) == 2
    mutations = (
        valid.replace("commit_change_0_16=221184", "commit_change_0_16=217088", 1),
        valid.replace("cohort=default,registry_growth=221184",
                      "cohort=default,registry_growth=0", 1),
        valid.replace("controlled=290816", "controlled=286720", 1),
        valid.replace("busy_cbData_delta=-7792", "busy_cbData_delta=7792", 1),
        valid.replace("source_owner_proven=0", "source_owner_proven=1", 1),
        valid.replace("identity_stable_in_process=1",
                      "identity_stable_in_process=0", 1),
        valid.replace("original_256_not_rerun=1", "original_256_not_rerun=0", 1),
        "\n".join(valid.splitlines()[:-1]),
        valid + "\n" + valid.splitlines()[0],
    )
    for mutant in mutations:
        if mutant == valid:
            raise AssertionError("mutant did not modify fixture")
        try:
            validate(mutant)
        except ValueError:
            pass
        else:
            raise AssertionError("corrupted source accepted")
    print("C545D_HEAP_OWNER_ARCHIVE_SELFTEST_PASS,negative_cases=9,"
          "positive_cases=1,original_windows_rerun=0")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--source", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
    else:
        if args.source is None:
            p.error("--source required")
        print("\n".join(validate(args.source.read_text(encoding="utf-8-sig"))))


if __name__ == "__main__":
    main()
