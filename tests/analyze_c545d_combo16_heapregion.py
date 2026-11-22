#!/usr/bin/env python3
"""Strict Combo16 optional Win32 heap REGION commit snapshots, CI-only.

This is a *new instrumented 2x16* diagnostic arm, not the original
4-arm 256 cycle archive. Region.dwCommittedSize may be zero (optional)
or omit certain large heap blocks; even a complete count of visible
REGION records is NOT all private committed memory. Async work remains.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

import analyze_c545d_combo16_scanfree as old

REGION = re.compile(
    r"C545D_CI_HEAP_REGION,"
    r"(baseline|cycle|after_cleanup|scanfree_cleanup),"
    r"(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)"
)


def parse_region(raw: str, busy: dict[tuple[str, int], int]) -> dict:
    data: dict[tuple[str, int], tuple[int, int, int, int]] = {}
    for line in raw.splitlines():
        if not line.startswith("C545D_CI_HEAP_REGION,"):
            continue
        match = REGION.fullmatch(line)
        if not match:
            raise ValueError("malformed region observation")
        label = match.group(1)
        nums = [int(x) for x in match.groups()[1:]]
        cycle, total, known, unknown, commit, busy_report, errors = nums
        point = label, cycle
        if (point in data or point not in old.POINTS
                or known + unknown != total
                or errors != 0
                or busy.get(point) != busy_report
                or (known == 0 and commit != 0)):
            raise ValueError("incorrect/incomplete region or HeapWalk linkage")
        data[point] = total, known, unknown, commit
    if set(data) != set(old.POINTS):
        raise ValueError("missing optional commit snapshot")
    return data


def analyze(folder: Path) -> list[str]:
    pair = {}
    for arm in ("nochange", "registry"):
        raw = (folder / f"combo-{arm}-16.txt").read_text(encoding="utf-8-sig")
        regular = old.read(raw, arm == "registry")
        region = parse_region(raw, regular["busy"])
        pair[arm] = {"regular": regular, "region": region}
    lines = []
    for arm in ("nochange", "registry"):
        for phase, cycle in old.POINTS:
            total, known, unknown, commit = pair[arm]["region"][phase, cycle]
            lines.append(
                "C545D_HEAP_REGION_OBSERVATION,"
                f"arm={arm},phase={phase},cycle={cycle},"
                f"regions={total},known={known},unknown={unknown},"
                f"reported_region_commit={commit},"
                "whole_heap_commit_proven=0,global_quiescence_proven=0"
            )
    for start, end in zip(old.POINTS[:-1], old.POINTS[1:]):
        raw = {}
        for arm in ("nochange", "registry"):
            reg = pair[arm]["region"]
            regular = pair[arm]["regular"]
            raw[arm] = {
                "region_commit": reg[end][3] - reg[start][3],
                "private": regular["private"][end] - regular["private"][start],
                "heap_busy": regular["busy"][end] - regular["busy"][start],
                "unknown": int(reg[start][2] > 0 or reg[end][2] > 0
                               or reg[start][1] == 0 or reg[end][1] == 0),
            }
        commit = raw["registry"]["region_commit"] - raw["nochange"]["region_commit"]
        private = raw["registry"]["private"] - raw["nochange"]["private"]
        busy = raw["registry"]["heap_busy"] - raw["nochange"]["heap_busy"]
        unknown = int(raw["registry"]["unknown"] or raw["nochange"]["unknown"])
        lines.append(
            "C545D_HEAP_REGION_CONTROLLED,"
            f"window={start[1]}_{end[1]},"
            f"region_commit_delta={commit},private_delta={private},"
            f"busy_cbData_delta={busy},optional_data_incomplete={unknown},"
            "heap_region_largemalloc_coverage_proven=0,"
            "cause_of_private_delta_proven=0"
        )
    lines.append(
        "C545D_HEAP_REGION_16_PASS,arms=2,cycles=16,"
        "windows16_only=1,original_256_not_rerun=1,"
        "real_camera=0,release_approved=0,global_quiescence_proven=0"
    )
    return lines


def selftest():
    points = old.POINTS
    busy = {point: 1200 + idx for idx, point in enumerate(points)}
    good = "\n".join(
        f"C545D_CI_HEAP_REGION,{phase},{n},2,2,0,{4096*(i+1)},"
        f"{busy[phase,n]},0"
        for i, (phase, n) in enumerate(points)
    )
    assert len(parse_region(good, busy)) == 4
    bad = [
        good.replace(",2,2,0,", ",2,0,2,", 1),
        good.replace(",2,2,0,", ",2,1,0,", 1),
        good.replace(",1201,0", ",1202,0", 1),
        good.replace("baseline,0", "cycle,0", 1),
        "\n".join(good.splitlines()[:3]),
        good + "\n" + good.splitlines()[0],
    ]
    for candidate in bad:
        try:
            parse_region(candidate, busy)
        except ValueError:
            continue
        raise AssertionError("invalid region observation accepted")
    print("C545D_HEAP_REGION_ANALYZER_SELFTEST_PASS,negative_cases=6,"
          "original_256_not_rerun=1,no_original_artifact_mutation=1")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--folder", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    if args.folder is None:
        p.error("missing --folder")
    print("\n".join(analyze(args.folder)))


if __name__ == "__main__":
    main()
