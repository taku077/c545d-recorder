#!/usr/bin/env python3
"""Read only the original pinned Windows 2022 4-arm 256-cycle numeric artifact.

Purpose: preserve the actual UNINSTRUMENTED per-arm 360B counts instead of
confusing a treatment-minus-control effect (+5) with an absolute registry
arm increase, or making a paired effect from TWO DIFFERENT UST CI runners.

Source: Windows run 44918598339, artifact 14713900393; the original Python
job failed, but 4x256 numeric probes completed and the archive was separately
validated by Ubuntu run 44921018494. No recorder, Win32 UST, or camera use.
"""
from __future__ import annotations
import sys
from pathlib import Path
import analyze_gio_combo_msvc256_saved as saved

START = ("cycle", 192)
END = ("cycle", 256)
MODES = ("core", "combo")
ARMS = ("nochange", "registry")

def treatment_effect(data: dict[str, dict], start=START, end=END) -> int:
    # The actual SAME Windows CI run's nochange counterfactual.
    return ((data["registry"][end] - data["registry"][start])
          - (data["nochange"][end] - data["nochange"][start]))

def inspect(group: dict[str, list[str]]) -> list[str]:
    # Full content, all four 256-cycle arms and two separate 16-cycle parity
    # controls MUST pass first. Prevent mixing files from different runs.
    marker = saved.analyze(group, print_output=False)[-1]
    if not marker.startswith("C545D_SAVED256_NUMERIC_ANALYSIS_PASS,"):
        raise ValueError("original pinned four-arm proof incomplete")
    out: list[str] = []
    for mode in MODES:
        data = {arm: saved.parse(group, mode, arm) for arm in ARMS}
        for arm in ARMS:
            rows = data[arm]["bins"][360]
            begin, end = rows[START], rows[END]
            if begin < 0 or end < 0:
                raise ValueError("invalid original bucket count")
            out.append(
                f"C545D_360_UNINSTRUMENTED_RAW,source_run=44918598339,"
                f"mode={mode},arm={arm},cycle192={begin},cycle256={end},"
                f"late_raw_delta={end-begin},ust_enabled=0,CI_only=1"
            )
        effect = treatment_effect({
            arm: data[arm]["bins"][360] for arm in ARMS
        })
        expected = {"core": 7, "combo": 5}[mode]
        if effect != expected:
            raise ValueError("original same-run 360B controlled effect changed")
        out.append(
            f"C545D_360_UNINSTRUMENTED_PAIRED,source_run=44918598339,"
            f"mode={mode},late_control_adjusted={effect},"
            "matched_same_run=1,CI_only=1"
        )
        # Use the ORIGINAL same-run archive to check ALL four consecutive
        # 64-cycle windows, not only a selected positive late window.
        cohort = {arm: data[arm]["bins"][360] for arm in ARMS}
        effects = []
        for left, right in zip(saved.EPOCHS[:-1], saved.EPOCHS[1:]):
            delta = treatment_effect(cohort, left, right)
            effects.append(delta)
            out.append(
                f"C545D_360_UNINSTRUMENTED_EPOCH,source_run=44918598339,"
                f"mode={mode},window={left[1]}_{right[1]},"
                f"controlled_delta={delta},matched_same_run=1,CI_only=1"
            )
        expected_epochs = {"core": (1, 0, 0, 7),
                           "combo": (0, 1, -2, 5)}[mode]
        if tuple(effects) != expected_epochs:
            raise ValueError("original 360B interval trajectory changed")
        total = treatment_effect(cohort, saved.EPOCHS[0], saved.EPOCHS[-1])
        if total != sum(effects) or total != {"core": 8, "combo": 4}[mode]:
            raise ValueError("360B epoch totals do not telescope")
        out.append(
            f"C545D_360_UNINSTRUMENTED_CUMULATIVE,source_run=44918598339,"
            f"mode={mode},window=0_256,controlled_delta={total},"
            "bucket_owner_unknown=1,CI_only=1"
        )
    # Both facts are already in the sanitized CI job logs. These are NOT
    # raw snapshots from the original run; never pair their values with it.
    out.extend((
        "C545D_360_UST_OTHER_RUN,source_run=44927366590,"
        "arm=nochange,cycle192=46,cycle256=45,late_raw_delta=-1,"
        "ust_enabled=1,CI_only=1",
        "C545D_360_UST_OTHER_RUN,source_run=44928707023,"
        "arm=registry,cycle192=49,cycle256=49,late_raw_delta=0,"
        "ust_enabled=1,CI_only=1",
        "C545D_360_COMPARABILITY,uncontrolled_ust_differences=1,"
        "cross_runner_control_pair_is_invalid=1,"
        "exact_360_owner_proven=0,zero_leak_proven=0,"
        "same_run_uninstrumented_combo_effect=5,windows_reruns=0"
    ))
    print("\n".join(out))
    return out

def selftest() -> None:
    def effect(no_a, no_b, reg_a, reg_b):
        points = {"nochange": {START: no_a, END: no_b},
                  "registry": {START: reg_a, END: reg_b}}
        return treatment_effect(points)
    assert effect(46, 45, 49, 49) == 1
    assert effect(46, 45, 49, 54) == 6
    assert effect(46, 45, 49, 48) == 0
    # These arithmetic examples are synthetic and MUST NOT be reported as
    # matched evidence for the actual two separate UST CI runs.
    print("C545D_360_COMPARABILITY_SELFTEST_PASS,synthetic_cases=3,"
          "windows_runs=0,same_runner_claim_from_cross_runs=0")

if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    elif len(sys.argv) == 3 and sys.argv[1] == "--root":
        inspect(saved.load(Path(sys.argv[2])))
    else:
        raise SystemExit("usage: 360 comparisons (--selftest | --root DIR)")
