#!/usr/bin/env python3
"""Read-only high-water/churn audit of original saved Windows2022 C545D experiments.

Original 4-arm 256-cycle source run 44918598339; three DIFFERENT earlier
cache-mode 256-cycle experiments 44533452892/44537371920/44545844200.
Never reinterpret different binaries/configurations as a shared timeseries,
or a difference between TWO processes as a physical process memory trace.

Windows PRIVATE committed bytes are NOT live heap data and a finite plateau
(or deceleration) proves neither bounded memory forever nor leak freedom.
No WinRT/registry/GStreamer invocation or new Windows/camera test is made.
"""
from __future__ import annotations
import argparse
from pathlib import Path

import analyze_gio_combo_msvc256_saved as original
import analyze_gio_combo_msvc256_trend as series_src
import analyze_gio_cached_residual_plateau_guard as prior


def describe(values: list[int], start: int, end: int) -> dict[str, int]:
    if len(values) != 257 or not 0 <= start < end <= 256:
        raise ValueError("require a full 257-point genuine series")
    steps = [values[i] - values[i - 1] for i in range(start + 1, end + 1)]
    record = max(values[:start + 1])
    new_highs = 0
    for i in range(start + 1, end + 1):
        if values[i] > record:
            record = values[i]
            new_highs += 1
    local_max = max(values[start:end + 1])
    local_min = min(values[start:end + 1])
    return {
        "start": start,
        "end": end,
        "net": values[end] - values[start],
        "gross_positive": sum(v for v in steps if v > 0),
        "gross_negative_abs": -sum(v for v in steps if v < 0),
        "up": sum(v > 0 for v in steps),
        "down": sum(v < 0 for v in steps),
        "flat": sum(v == 0 for v in steps),
        "new_running_highs": new_highs,
        "running_high_gain": max(values[:end + 1]) - max(values[:start + 1]),
        "local_range": local_max - local_min,
        "end_below_running_high": max(values[:end + 1]) - values[end],
        "terminal_min_not_proven": int(values[end] != min(values[start:end + 1])),
    }


def strict_original(group: dict[str, list[str]]) -> tuple[list[str], dict]:
    guard = original.analyze(group, print_output=False)
    if guard[-1] != (
        "C545D_SAVED256_NUMERIC_ANALYSIS_PASS,source_windows_run=44918598339,"
        "cycles=256,controls=4,compare16=2,raw_host_data=0,"
        "sdk_public_api_not_rechecked_from_archive=1,"
        "zero_leak_proven=0,host_install_approved=0"
    ):
        raise ValueError("original 256 source identity invalid")

    effects = series_src.effects(group)
    if (effects["combo", "private"][0][256] != 425984
            or effects["combo", "private"][1] != 368640
            or effects["core", "private"][1] != 3272704):
        raise ValueError("control-adjusted source snapshots no longer pinned")

    output: list[str] = []
    highwater = {}
    for mode in ("core", "combo"):
        raw = {
            arm: series_src.readings(group[f"{mode}-{arm}-256"])["cycles"]
            for arm in ("registry", "nochange")
        }
        paths = {
            "registry_raw": [raw["registry"][i][1] for i in range(257)],
            "nochange_raw": [raw["nochange"][i][1] for i in range(257)],
            "controlled": effects[mode, "private"][0],
        }
        for arm, measurements in paths.items():
            # Only the raw process-specific series describes one process.
            # Control-adjusted D_i is a between-process workload comparator.
            if len(measurements) != 257 or any(n < 0 for n in paths["registry_raw"]):
                raise ValueError("incomplete original raw process series")
            for a, b in ((0, 64), (64, 128), (128, 192), (192, 256)):
                d = describe(measurements, a, b)
                if d["up"] + d["down"] + d["flat"] != 64:
                    raise AssertionError("step count incorrect")
                highwater[(mode, arm, a, b)] = d
                output.append(
                    "C545D_256_HIGHWATER_EPOCH,"
                    f"mode={mode},arm={arm},window={a}_{b},"
                    + ",".join(f"{k}={v}" for k, v in d.items()
                               if k not in ("start", "end"))
                    + f",single_process={int(arm != 'controlled')},"
                    "allocator_capacity_measured=0"
                )

    # Historic Combo latest: late 64 control-adjusted +53,248 despite a
    # preceding 128-192 negative net (-12,288); the steps may be mixed.
    latest = highwater["combo", "controlled", 192, 256]
    if latest["net"] != 53248:
        raise ValueError("pinned Combo last64 net diverged")
    for mode in ("core", "combo"):
        controlled = effects[mode, "private"][0]
        if sum(
            highwater[mode, "controlled", a, b]["net"]
            for a, b in ((0, 64), (64, 128), (128, 192), (192, 256))
        ) != controlled[256]:
            raise AssertionError("original per-cycle intervals not additive")
    if effects["combo", "private"][0][192] != 372736:
        raise ValueError("original Combo 192 checkpoint changed")

    output.append(
        "C545D_256_HIGHWATER_ORIGINAL_SUMMARY,source_run=44918598339,"
        f"combo_controlled_last64_net={latest['net']},"
        f"combo_controlled_last64_new_highs={latest['new_running_highs']},"
        f"combo_controlled_last64_running_high_gain={latest['running_high_gain']},"
        f"combo_controlled_last64_down_steps={latest['down']},"
        f"combo_controlled_last64_up_steps={latest['up']},"
        f"combo_controlled_final_below_high={latest['end_below_running_high']},"
        "separate_process_control_difference=1,finite_window=1,"
        "linear_leak_or_plateau_proven=0,real_recorder_tested=0"
    )
    return output, highwater


def audit_older(root: Path) -> list[str]:
    # These are different older patch/config artifacts; do NOT splice their
    # timepoints into original Combo's 256-cycle resource series.
    checked = prior.guard(prior.load(root))
    out = []
    for item in checked["rows"]:
        out.append(
            f"C545D_256_HIGHWATER_OLDER_CACHE,run={item['run_id']},"
            f"private_last64={item['private_last64']},"
            f"heap_busy_last64={item['heap_busy_last64']},"
            f"exact360_blocks_last64={item['last64_360_blocks']},"
            "different_experiment_from_combo=1,"
            "last64_not_forever=1,allocation_owner_known=0"
        )
    out.append(
        "C545D_256_HIGHWATER_OLDER_SUMMARY,old_runs=3,"
        "private_last64_values=57344;8192;0,"
        "different_patch_experiments=1,not_single_convergence_curve=1,"
        "plateau_not_proven=1"
    )
    return out


def selftest() -> None:
    values = [100] * 257
    for i in range(193, 257):
        values[i] = 100 + (i - 192)
    r = describe(values, 192, 256)
    assert (r["net"], r["new_running_highs"], r["running_high_gain"],
            r["up"], r["down"], r["flat"]) == (64, 64, 64, 64, 0, 0)
    oscillating = [100] * 257
    for i in range(193, 257):
        oscillating[i] = 102 if i % 2 else 100
    r2 = describe(oscillating, 192, 256)
    assert r2["net"] == 0 and r2["up"] == 32 and r2["down"] == 32
    assert r2["new_running_highs"] == 1 and r2["running_high_gain"] == 2
    assert r2["end_below_running_high"] == 2
    constant = describe([123] * 257, 192, 256)
    assert constant["new_running_highs"] == constant["up"] == 0
    negatives = (
        ([0] * 256, 192, 256),
        ([0] * 258, 192, 256),
        ([0] * 257, 193, 192),
        ([0] * 257, 192, 257),
        ([0] * 257, 192, 192),
    )
    for values, start, end in negatives:
        try:
            describe(values, start, end)
        except ValueError:
            pass
        else:
            raise AssertionError("malformed high-water window accepted")
    print("C545D_256_HIGHWATER_SELFTEST_PASS,positive_cases=3,"
          "negative_cases=5,new_windows_runs=0,real_host_modified=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--source", type=Path)
    p.add_argument("--older", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    if args.source is None or args.older is None:
        p.error("require --source and --older for preserved artifacts")
    group = original.load(args.source)
    output, _ = strict_original(group)
    output.extend(audit_older(args.older))
    output.append(
        "C545D_256_HIGHWATER_PASS,source_original=44918598339,"
        "older_archived_runs=3,original_processes=4,"
        "per_cycle_checkpoints=257,original_windows_rerun=0,"
        "all_outputs_numeric_only=1,permanent_plateau_proven=0,"
        "production_changes=0"
    )
    print("\n".join(output))


if __name__ == "__main__":
    main()
