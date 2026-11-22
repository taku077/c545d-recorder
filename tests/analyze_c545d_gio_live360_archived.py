#!/usr/bin/env python3
"""Strict offline replay of actual CI-only live360 Combo16 numeric artifact.

Windows source run #45018787046; sanitized artifact ID #14753270867.
A 360-byte BUSY block's same address at two snapshots does NOT prove
continuous lifetime because address reuse is possible. This is NOT a
stack owner, a PSAPI byte conversion, or a 256-cycle/recorder result.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

SOURCE_RUN = 45018787046
ARTIFACT_ID = 14753270867

ROWS = {
    "nochange": ((47, 0, 0, 0),
                 (47, 47, 0, 0),
                 (47, 47, 0, 0),
                 (47, 47, 0, 0)),
    "registry": ((46, 0, 0, 0),
                 (46, 46, 0, 0),
                 (47, 46, 1, 0),
                 (46, 46, 0, 1)),
}
EFFECTS = (0, 1, -1)
RESOURCE = {
    ("private", "0_16"): (217088, 40960, 176128),
    ("private", "16_17"): (40960, 0, 40960),
    ("private", "17_18"): (4096, 0, 4096),
    ("busy", "0_16"): (-20308, 0, -20308),
    ("busy", "16_17"): (-756124, 0, -756124),
    ("busy", "17_18"): (760296, 0, 760296),
}
REGION = {
    "0_16": (176128, 176128, -20308),
    "16_17": (45056, 40960, -756124),
    "17_18": (0, 4096, 760296),
}
ARM = re.compile(
    r"C545D_GIO_LIVE360_ARM,arm=(nochange|registry),stage=([0-3]),"
    r"now=(\d+),same_address=(\d+),appeared_address=(\d+),"
    r"disappeared_address=(\d+),continuous_lifetime_proven=0,"
    r"allocation_site_proven=0$"
)
DELTA = re.compile(
    r"C545D_GIO_LIVE360_CONTROLLED,stage_window=([0-2])_([1-3]),"
    r"count_difference_in_differences=(-?\d+),"
    r"separate_processes=1,addresses_not_cross_compared=1,"
    r"not_private_usage_bytes=1,leak_rate_proven=0$"
)
RES = re.compile(
    r"C545D_COMBO16_SCANFREE_RESOURCE,kind=(private|busy),"
    r"window=(0_16|16_17|17_18),"
    r"registry_raw=(-?\d+),nochange_raw=(-?\d+),"
    r"controlled=(-?\d+),new_alloc_site_proven=0,"
    r"real_host_untested=1$"
)
REG = re.compile(
    r"C545D_HEAP_REGION_CONTROLLED,window=(0_16|16_17|17_18),"
    r"region_commit_delta=(-?\d+),private_delta=(-?\d+),"
    r"busy_cbData_delta=(-?\d+),optional_data_incomplete=0,"
    r"heap_region_largemalloc_coverage_proven=0,"
    r"cause_of_private_delta_proven=0$"
)
PAIR_PASS = (
    "C545D_GIO_LIVE360_PAIRED_PASS,"
    "arms=2,cycles_each=16,phase_count=4,snapshots_valid=8,"
    "original_256_rerun=0,address_reuse_unexcluded=1,"
    "allocation_owner_proven=0,global_quiescence_proven=0,"
    "real_host_tested=0"
)
COMBO_PASS = (
    "C545D_COMBO16_SCANFREE_PASS,source_mode=combo,cycles=16,"
    "valid_GObject_types=7,GObject_census_unavailable=0,"
    "GAppInfo_final_query_skipped=1,worker_quiescence_unproven=1,"
    "results_not_256cycle_equivalent=1,production_unmodified=1,"
    "host_install_approved=0,CI_only=1"
)


def extract(raw: str, prefix: str, regex: re.Pattern[str], key_indices: tuple[int, ...]):
    out = {}
    for row in raw.splitlines():
        if not row.startswith(prefix):
            continue
        m = regex.fullmatch(row)
        if m is None:
            raise ValueError("source_row_schema_changed")
        parts = m.groups()
        key = tuple(parts[i] for i in key_indices)
        if key in out:
            raise ValueError("duplicated_original_numeric_row")
        out[key] = parts
    return out


def verify(raw: str) -> str:
    lines = raw.splitlines()
    if len(raw) > 150000 or len(lines) > 1500:
        raise ValueError("unbounded_original_numeric_artifact")
    # Reject ANY private stack/path/address text in the entire archived file.
    # All source data were intentionally recorded as numeric ASCII only.
    if not lines or any(re.fullmatch(r"[A-Za-z0-9_,=\-]+", row) is None
                        for row in lines):
        raise ValueError("unsafe_non_numeric_original_artifact")
    arm = extract(raw, "C545D_GIO_LIVE360_ARM,", ARM, (0, 1))
    if len(arm) != 8:
        raise ValueError("missing_original_snapshot_rows")
    for cohort, expected in ROWS.items():
        for stage, value in enumerate(expected):
            row = arm.get((cohort, str(stage)))
            if row is None or tuple(map(int, row[2:])) != value:
                raise ValueError("original_360_snapshot_count_changed")
            if stage > 0:
                now, same, appeared, gone = value
                previous = expected[stage - 1][0]
                if same + appeared != now or same + gone != previous:
                    raise ValueError("invalid_original_live_block_conservation")
    delta = extract(raw, "C545D_GIO_LIVE360_CONTROLLED,", DELTA, (0, 1))
    for stage, expected in enumerate(EFFECTS):
        row = delta.get((str(stage), str(stage + 1)))
        if row is None or int(row[2]) != expected:
            raise ValueError("original_matched_count_effect_changed")
        calculated = ((ROWS["registry"][stage + 1][0] -
                       ROWS["registry"][stage][0]) -
                      (ROWS["nochange"][stage + 1][0] -
                       ROWS["nochange"][stage][0]))
        if calculated != expected:
            raise ValueError("control_math_inconsistent")
    if len(delta) != 3:
        raise ValueError("extra_invalid_controlled_window")
    resource = extract(raw, "C545D_COMBO16_SCANFREE_RESOURCE,", RES, (0, 1))
    if len(resource) != 6:
        raise ValueError("resource_evidence_missing")
    for key, expected in RESOURCE.items():
        row = resource.get(key)
        if row is None or tuple(map(int, row[2:])) != expected:
            raise ValueError("different_original_private_or_busy_record")
    region = extract(raw, "C545D_HEAP_REGION_CONTROLLED,", REG, (0,))
    if len(region) != 3:
        raise ValueError("heap_region_evidence_missing")
    for window, expected in REGION.items():
        row = region.get((window,))
        if row is None or tuple(map(int, row[1:])) != expected:
            raise ValueError("different_original_reported_region_commit")
    if lines.count(PAIR_PASS) != 1 or lines.count(COMBO_PASS) != 1:
        raise ValueError("source_provenance_or_gates_missing")
    return (
        "C545D_GIO_LIVE360_ARCHIVE_PASS,"
        f"source_run={SOURCE_RUN},artifact_id={ARTIFACT_ID},"
        "snapshot_rows=8,controlled_windows=3,"
        "registry_net_360_0_16=0,registry_net_360_0_18=0,"
        "controlled_private_usage_0_16=176128,"
        "reported_region_commit_0_16=176128,"
        "heapwalk_busy_0_16=-20308,"
        "owner_unproven=1,address_reuse_unexcluded=1,"
        "old_256_unmodified=1,windows_reruns=0,real_recorder_untested=1"
    )


def fixture() -> str:
    rows = [COMBO_PASS, PAIR_PASS]
    for cohort, snapshots in ROWS.items():
        for stage, (now, same, appeared, gone) in enumerate(snapshots):
            rows.append(
                "C545D_GIO_LIVE360_ARM,"
                f"arm={cohort},stage={stage},now={now},"
                f"same_address={same},appeared_address={appeared},"
                f"disappeared_address={gone},"
                "continuous_lifetime_proven=0,allocation_site_proven=0"
            )
    for i, effect in enumerate(EFFECTS):
        rows.append(
            "C545D_GIO_LIVE360_CONTROLLED,"
            f"stage_window={i}_{i+1},"
            f"count_difference_in_differences={effect},"
            "separate_processes=1,addresses_not_cross_compared=1,"
            "not_private_usage_bytes=1,leak_rate_proven=0"
        )
    for (kind, window), (r, c, diff) in RESOURCE.items():
        rows.append(
            "C545D_COMBO16_SCANFREE_RESOURCE,"
            f"kind={kind},window={window},"
            f"registry_raw={r},nochange_raw={c},controlled={diff},"
            "new_alloc_site_proven=0,real_host_untested=1"
        )
    for window, (committed, private, busy) in REGION.items():
        rows.append(
            "C545D_HEAP_REGION_CONTROLLED,"
            f"window={window},region_commit_delta={committed},"
            f"private_delta={private},busy_cbData_delta={busy},"
            "optional_data_incomplete=0,"
            "heap_region_largemalloc_coverage_proven=0,"
            "cause_of_private_delta_proven=0"
        )
    return "\n".join(rows)


def selftest() -> None:
    original = fixture()
    assert verify(original).startswith("C545D_GIO_LIVE360_ARCHIVE_PASS,")
    changed = [
        original.replace("now=46,same_address=46,appeared_address=0",
                         "now=47,same_address=46,appeared_address=0", 1),
        original.replace("same_address=47", "same_address=46", 1),
        original.replace("stage_window=1_2,count_difference_in_differences=1",
                         "stage_window=1_2,count_difference_in_differences=2", 1),
        original.replace("controlled=176128", "controlled=176129", 1),
        original.replace("region_commit_delta=176128",
                         "region_commit_delta=176127", 1),
        original.replace("allocation_site_proven=0",
                         "allocation_site_proven=1", 1),
        original.replace("address_reuse_unexcluded=1",
                         "address_reuse_unexcluded=0", 1),
        original + "\nC:\\Users\\Private\\raw.etl",
        original + "\n" + original.splitlines()[2],
        "\n".join(original.splitlines()[:-1]),
    ]
    for corrupt in changed:
        if corrupt == original:
            raise AssertionError("synthetic mutation not applied")
        try:
            verify(corrupt)
        except ValueError:
            continue
        raise AssertionError("altered Windows saved evidence passed")
    print(
        "C545D_GIO_LIVE360_ARCHIVE_SELFTEST_PASS,"
        "positive=1,negative=10,original_256_rerun=0,"
        "raw_uploaded=0,windows_runs=0"
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--source", type=Path)
    a = p.parse_args()
    try:
        if a.selftest:
            selftest()
        else:
            if a.source is None:
                p.error("--source required")
            print(verify(a.source.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError):
        print(
            "C545D_GIO_LIVE360_ARCHIVE_FAIL,"
            "reason=ORIGINAL_NUMERIC_EVIDENCE_INVALID,raw_uploaded=0"
        )
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
