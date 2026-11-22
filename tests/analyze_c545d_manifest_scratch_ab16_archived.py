#!/usr/bin/env python3
"""Immutable Windows #45033642809 manifest scratch numeric A/B release gate.

This test replays the *existing* sanitized 16-cycle paired-run artifact.
A source-only optimisation is NOT a proven memory leak fix; the private
difference is just one page and Win32 heap committed-region delta worsened.
Do not compare it with differently instrumented Combo256 or the real host.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

SOURCE_RUN = 45033642809
ARTIFACT = 14758892656
EXPECTED = {
    "baseline_private": 212992,
    "scratch_private": 208896,
    "delta_private": -4096,
    "baseline_busy": -16136,
    "scratch_busy": -11964,
    "delta_busy": 4172,
    "baseline_region": 139264,
    "scratch_region": 208896,
    "delta_region": 69632,
}
FLAGS = {
    "same_runner": 1,
    "pairs": 2,
    "cycles_per_arm": 16,
    "causality_unproven": 1,
    "old256_untouched": 1,
    "real_host_untouched": 1,
}
LINE = re.compile(r"C545D_MANIFEST_SCRATCH_AB16(?:,[a-z][a-z0-9_]*=-?\\d+)+$")


def validate(raw: str) -> str:
    lines = raw.strip().splitlines()
    if len(lines) != 1 or len(raw) > 1024 or LINE.fullmatch(lines[0]) is None:
        raise ValueError("not_one_sanitized_numeric_line")
    pairs = [token.split("=", 1) for token in lines[0].split(",")[1:]]
    if len(pairs) != len(EXPECTED) + len(FLAGS):
        raise ValueError("unknown_duplicate_or_missing_fields")
    data = {}
    for key, v in pairs:
        if key in data:
            raise ValueError("duplicate_field")
        data[key] = int(v)
    if set(data) != set(EXPECTED) | set(FLAGS):
        raise ValueError("original_ab16_schema_changed")
    if any(data[k] != v for k, v in {**EXPECTED, **FLAGS}.items()):
        raise ValueError("original_ab16_numeric_evidence_changed")
    for metric in ("private", "busy", "region"):
        if data["scratch_" + metric] - data["baseline_" + metric] != data["delta_" + metric]:
            raise ValueError("arithmetic_inconsistent")
    improvement_pct = 100 * (data["baseline_private"] - data["scratch_private"]) / data["baseline_private"]
    if not (1.9 < improvement_pct < 2.0 and data["delta_region"] > 0 and data["delta_busy"] > 0):
        raise ValueError("release_decision_basis_not_met")
    return (
        "C545D_MANIFEST_SCRATCH_SAVED_AB16_VERIFIED,"
        "source_run=45033642809,artifact=14758892656,"
        "baseline_private=212992,scratch_private=208896,"
        "private_reduction_bytes=4096,private_reduction_pct_approx=1.923,"
        "region_delta_worsening=69632,busy_delta_relative=4172,"
        "decision=DO_NOT_PROMOTE_UNPROVEN_MICRO_OPT,"
        "source_only_candidate=1,original_256_unmodified=1,"
        "allocation_owner_proven=0,host_untested=1,"
        "new_windows_runs=0"
    )


def selftest() -> None:
    good = "C545D_MANIFEST_SCRATCH_AB16," + ",".join(
        f"{k}={v}" for k, v in {**EXPECTED, **FLAGS}.items()) + "\n"
    assert validate(good).startswith("C545D_MANIFEST_SCRATCH_SAVED_AB16_VERIFIED,")
    mutants = [
        good.replace("delta_private=-4096", "delta_private=0", 1),
        good.replace("scratch_private=208896", "scratch_private=208895", 1),
        good.replace("delta_region=69632", "delta_region=-69632", 1),
        good.replace("pairs=2", "pairs=4", 1),
        good.replace("causality_unproven=1", "causality_unproven=0", 1),
        good + good,
        good.replace("baseline_busy=-16136", "baseline_busy=-16136,baseline_busy=-16136", 1),
        good.replace("host_untouched=1", "host_untouched=0", 1),
    ]
    for bad in mutants:
        try:
            validate(bad)
        except ValueError:
            continue
        raise AssertionError("corrupted-original-evidence-accepted")
    print("C545D_MANIFEST_SCRATCH_AB16_ARCHIVE_SELFTEST_PASS,negative=8,positive=1,Windows_runs=0")


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
        print(validate(args.source.read_text(encoding="utf-8-sig")))


if __name__ == "__main__":
    main()
