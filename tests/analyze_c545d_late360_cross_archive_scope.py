#!/usr/bin/env python3
"""Compare ORIGINAL late Combo256 vs NEW Combo16 360-byte count *scopes*.

Sources are only the two already finished, numeric-only GitHub Actions
artifacts. Original Windows2022 four-arm run 44918598339, artifact 14713900393;
live360 two-arm run 45018787046, artifact 14753270867.

The primary distinction: a treated-minus-control count effect is NOT the
absolute number of new allocations in the treated process, and a 360B
HeapWalk bucket count is NOT an allocation-site identity. Do not equate
16-cycle and 192-to-256-cycle time horizons, instrumentation or memory slopes.
No new Windows experiments, RTSP, camera, registry writes or ETW are used.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import analyze_gio_combo_msvc256_saved as saved
import analyze_c545d_gio_live360_archived as live

OLD_RUN = 44918598339
NEW_RUN = 45018787046
LEFT = ("cycle", 192)
RIGHT = ("cycle", 256)
LAST = ("settled_cleanup", 258)


def controlled(reg_begin: int, reg_end: int,
               ctl_begin: int, ctl_end: int) -> int:
    return (reg_end - reg_begin) - (ctl_end - ctl_begin)


def inspect(original_root: Path, live360_source: Path) -> list[str]:
    original = saved.load(original_root)
    check = saved.analyze(original, print_output=False)
    if check[-1] != (
        "C545D_SAVED256_NUMERIC_ANALYSIS_PASS,"
        "source_windows_run=44918598339,cycles=256,controls=4,compare16=2,"
        "raw_host_data=0,sdk_public_api_not_rechecked_from_archive=1,"
        "zero_leak_proven=0,host_install_approved=0"
    ):
        raise ValueError("original_four_arm_source_check_invalid")
    if not live.verify(live360_source.read_text(encoding="utf-8-sig")).startswith(
        "C545D_GIO_LIVE360_ARCHIVE_PASS,"
        f"source_run={NEW_RUN},artifact_id=14753270867,"
    ):
        raise ValueError("new_two_arm_numeric_source_invalid")

    out: list[str] = []
    for mode, expected_count, expected_private in (
        ("core", 7, 729088),
        ("combo", 5, 53248),
    ):
        data = {arm: saved.parse(original, mode, arm)
                for arm in saved.ARMS}
        bins = {arm: data[arm]["bins"][360] for arm in saved.ARMS}
        reg_early = bins["registry"][LEFT]
        reg_late = bins["registry"][RIGHT]
        ctl_early = bins["nochange"][LEFT]
        ctl_late = bins["nochange"][RIGHT]
        count_effect = controlled(reg_early, reg_late,
                                  ctl_early, ctl_late)
        private_effect = saved.difference(data, "mem", LEFT, RIGHT)
        if (count_effect, private_effect) != (expected_count,
                                              expected_private):
            raise ValueError("historical_late_360_or_private_effect_changed")
        out.append(
            "C545D_LATE360_256_ARM_SCOPE,"
            f"source_run={OLD_RUN},mode={mode},window=192_256,"
            f"registry_start={reg_early},registry_end={reg_late},"
            f"registry_raw_delta={reg_late-reg_early},"
            f"nochange_start={ctl_early},nochange_end={ctl_late},"
            f"nochange_raw_delta={ctl_late-ctl_early},"
            f"controlled_360_delta={count_effect},"
            f"controlled_private_delta={private_effect},"
            "bucket_not_allocation_site=1,leak_rate_unproven=1"
        )
        # Same-run size class census, but ONLY the eight already recorded
        # exact HeapWalk BUSY sizes. It is not a whole-heap leak census.
        if mode == "combo":
            for size in saved.SIZES:
                reg_bin = data["registry"]["bins"][size]
                ctl_bin = data["nochange"]["bins"][size]
                reg_change = reg_bin[RIGHT] - reg_bin[LEFT]
                ctl_change = ctl_bin[RIGHT] - ctl_bin[LEFT]
                delta = reg_change - ctl_change
                out.append(
                    "C545D_LATE256_COMBO_BIN_SCOPE,"
                    f"source_run={OLD_RUN},window=192_256,"
                    f"size={size},"
                    f"registry_raw_delta={reg_change},"
                    f"nochange_raw_delta={ctl_change},"
                    f"controlled_count_delta={delta},"
                    "selected_bins_only=1,"
                    "not_a_complete_heap_census=1,"
                    "not_private_usage_allocation_site=1"
                )
                if size == 360 and delta != 5:
                    raise ValueError("360_class_cross_check_failed")
        settled_effect = controlled(
            bins["registry"][RIGHT], bins["registry"][LAST],
            bins["nochange"][RIGHT], bins["nochange"][LAST]
        )
        out.append(
            "C545D_LATE360_256_SETTLED_SCOPE,"
            f"source_run={OLD_RUN},mode={mode},"
            f"late_360_controlled_delta={count_effect},"
            f"settled_360_controlled_change={settled_effect},"
            "global_quiescence_unproven=1,allocation_owner_unproven=1"
        )
    old_combo = [x for x in out if
                 x.startswith("C545D_LATE360_256_ARM_SCOPE,") and
                 "mode=combo," in x]
    assert len(old_combo) == 1
    # New GIO16's per-stage counts are *validated against an independent
    # archive*. Only the number of live 360B blocks is comparable as a kind
    # of metric; the workload/observation horizons are NOT equivalent.
    current = live.ROWS
    for arm in ("nochange", "registry"):
        stages = tuple(row[0] for row in current[arm])
        expected_stages = {
            "nochange": (47, 47, 47, 47),
            "registry": (46, 46, 47, 46),
        }
        if stages != expected_stages[arm]:
            raise ValueError("short_exact360_checkpoint_changed")
        out.append(
            "C545D_LATE360_16_ARM_SCOPE,"
            f"source_run={NEW_RUN},arm={arm},"
            f"baseline={stages[0]},cycle16={stages[1]},"
            f"cleanup17={stages[2]},final18={stages[3]},"
            "zero_late256_inference=1,address_reuse_unexcluded=1"
        )
    out.append(
        "C545D_LATE360_SCOPE_CONCLUSION,"
        f"old_source_run={OLD_RUN},new_source_run={NEW_RUN},"
        "old_combo_late_controlled_360=5,"
        "old_combo_late_controlled_private=53248,"
        "new_combo_0_16_controlled_360=0,"
        "new_combo_0_16_controlled_private=176128,"
        "not_same_window=1,not_same_instrumentation=1,"
        "five_not_necessarily_registry_new_blocks=1,"
        "nominal_five_times_360_bytes=1800,"
        "nominal_bytes_not_attributed_private_usage=1,"
        "real_host_untested=1,no_zero_leak_proof=1"
    )
    out.append(
        "C545D_LATE360_SCOPE_ARCHIVES_PASS,"
        "original_256_windows_rerun=0,new_16_windows_rerun=0,"
        "source_runs=2,paired_comparisons_within_run_only=1,"
        "new_user_measurements=0,release_approved=0"
    )
    return out


def selftest() -> None:
    # A controlled +5 is compatible with DIFFERENT treated trajectories.
    candidates = (
        (0, 5, 0, 0),     # treatment gains 5
        (0, 0, 5, 0),     # control loses 5
        (0, 3, 3, 1),     # treatment +3 and control -2
    )
    assert all(controlled(*row) == 5 for row in candidates)
    assert len({row[1] - row[0] for row in candidates}) == 3
    assert controlled(0, 0, 0, 0) == 0
    assert controlled(45, 44, 40, 42) == -3
    print(
        "C545D_LATE360_SCOPE_SELFTEST_PASS,"
        "counterfactual_same_effect_distinct_raw=3,"
        "different_window_conflation_rejected=1,"
        "new_windows_runs=0,raw_uploaded=0"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--old-root", type=Path)
    ap.add_argument("--new-source", type=Path)
    args = ap.parse_args()
    try:
        if args.selftest:
            selftest()
        else:
            if args.old_root is None or args.new_source is None:
                ap.error("--old-root and --new-source required")
            print("\n".join(inspect(args.old_root, args.new_source)))
    except (OSError, ValueError):
        print("C545D_LATE360_SCOPE_ARCHIVES_FAIL,"
              "reason=MISSING_OR_ALTERED_SAVED_NUMERIC,raw_uploaded=0")
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
