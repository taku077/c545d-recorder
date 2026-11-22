#!/usr/bin/env python3
"""One short Windows CI discriminator: DEFAULT heap vs OTHER heaps.

Read two disposable Combo16 process logs; NEVER compare raw heap indices
between processes. Check stable process-local heap handles (without logging
them), sum exact per-heap optional-region commitment and live BUSY data back
to old aggregate GIO_HEAP and C545D_CI_HEAP_REGION rows, then compare
DEFAULT and pooled OTHER categories across two independent arms.

A default-versus-other comparison is NOT owner/source attribution, complete
heap commit accounting, a quiescence proof, or a 256-cycle/real-host result.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re

import analyze_c545d_combo16_scanfree as old
import analyze_c545d_combo16_heapregion as region

LINE = re.compile(
    r"C545D_CI_HEAP_OWNER,"
    r"(baseline|cycle|after_cleanup|scanfree_cleanup),"
    r"(\d+),(\d+),([01]),([01]),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)$"
)


def parse_owner(raw: str, expected_region: dict, busy: dict) -> dict:
    found: dict[tuple[tuple[str, int], int], dict] = {}
    count = None
    for line in raw.splitlines():
        if not line.startswith("C545D_CI_HEAP_OWNER,"):
            continue
        m = LINE.fullmatch(line)
        if m is None:
            raise ValueError("malformed per-heap diagnostic")
        phase = m.group(1)
        cyc, ordinal, is_default, stable, regions, known, unknown, commit, payload, errors = map(
            int, m.groups()[1:])
        point = phase, cyc
        key = point, ordinal
        if (point not in old.POINTS or ordinal >= 64 or key in found
                or stable != 1 or errors != 0 or known + unknown != regions
                or (known == 0 and commit != 0)):
            raise ValueError("unstable, duplicate, unknown or incomplete heap")
        found[key] = {
            "default": is_default, "regions": regions, "known": known,
            "unknown": unknown, "commit": commit, "busy": payload,
        }
    if not found:
        raise ValueError("missing per-heap owner markers")
    points = {}
    for point in old.POINTS:
        elems = {ordinal: fields for (pt, ordinal), fields in found.items()
                 if pt == point}
        if not elems or set(elems) != set(range(len(elems))):
            raise ValueError("noncontiguous/missing heap ordinals")
        if count is None:
            count = len(elems)
        if count != len(elems) or sum(x["default"] for x in elems.values()) != 1:
            raise ValueError("unstable heap count or missing default heap")
        if (sum(x["regions"] for x in elems.values()) != expected_region[point][0]
                or sum(x["known"] for x in elems.values()) != expected_region[point][1]
                or sum(x["unknown"] for x in elems.values()) != expected_region[point][2]
                or sum(x["commit"] for x in elems.values()) != expected_region[point][3]
                or sum(x["busy"] for x in elems.values()) != busy[point]):
            raise ValueError("per-heap numbers disagree with original aggregate")
        points[point] = elems
    baseline = points[old.POINTS[0]]
    for point in old.POINTS[1:]:
        if any(points[point][i]["default"] != baseline[i]["default"]
               for i in baseline):
            raise ValueError("default heap ordinal changed within process")
    return points


def analyze(folder: Path) -> list[str]:
    arms = {}
    rows = []
    for arm in ("nochange", "registry"):
        raw = (folder / f"combo-{arm}-16.txt").read_text(encoding="utf-8-sig")
        original = old.read(raw, arm == "registry")
        original_region = region.parse_region(raw, original["busy"])
        owner = parse_owner(raw, original_region, original["busy"])
        arms[arm] = {"orig": original, "region": original_region, "owner": owner}
        for i in sorted(owner[old.POINTS[0]]):
            a, b, c, d = [owner[p][i] for p in old.POINTS]
            rows.append(
                "C545D_HEAP_OWNER_HISTORY,"
                f"arm={arm},heap_ordinal_local={i},"
                f"is_default={a['default']},"
                f"commit_baseline={a['commit']},commit_cycle16={b['commit']},"
                f"commit_after_cleanup={c['commit']},"
                f"commit_scanfree_final={d['commit']},"
                f"commit_change_0_16={b['commit'] - a['commit']},"
                f"busy_data_change_0_16={b['busy'] - a['busy']},"
                "identity_stable_in_process=1,"
                "cross_process_heap_ordinal_comparable=0"
            )
    for cohort in ("default", "other"):
        changes = {}
        for arm in arms:
            a = arms[arm]["owner"][old.POINTS[0]]
            b = arms[arm]["owner"][old.POINTS[1]]
            choose = lambda entry: (entry["default"] == 1) == (cohort == "default")
            changes[arm] = sum(
                b[i]["commit"] - a[i]["commit"]
                for i in a if choose(a[i])
            )
        raw_region = {}
        for arm in arms:
            observed = arms[arm]["region"]
            raw_region[arm] = observed[old.POINTS[1]][3] - observed[old.POINTS[0]][3]
        if cohort == "default":
            default_total = changes
        else:
            for arm in arms:
                if default_total[arm] + changes[arm] != raw_region[arm]:
                    raise ValueError("categorized region commit not exhaustive")
        rows.append(
            "C545D_HEAP_OWNER_COHORT,"
            f"cohort={cohort},registry_growth={changes['registry']},"
            f"nochange_growth={changes['nochange']},"
            f"controlled_growth={changes['registry']-changes['nochange']},"
            "source_owner_proven=0,region_coverage_complete=0,"
            "cross_process_heap_identity_assumed=0"
        )
    rows.append(
        "C545D_HEAP_OWNER_PASS,arms=2,cycles=16,"
        "same_process_heap_identity_verified=1,"
        "default_vs_other_commit_partition_verified=1,"
        "optional_region_commit_not_full_private=1,"
        "original_256_not_rerun=1,real_device_untested=1,"
        "recording_process_untouched=1"
    )
    return rows


def selftest() -> None:
    points = old.POINTS
    busy = {point: 600 + x for x, point in enumerate(points)}
    regions = {point: (2, 2, 0, 4096 * (x + 1))
               for x, point in enumerate(points)}
    lines = []
    for x, (p, cycle) in enumerate(points):
        # Two heaps, one default with a REGION and all BUSY data.
        lines.append(
            f"C545D_CI_HEAP_OWNER,{p},{cycle},0,1,1,"
            f"1,1,0,{4096 * (x + 1)},{busy[p, cycle]},0"
        )
        lines.append(
            f"C545D_CI_HEAP_OWNER,{p},{cycle},1,0,1,1,1,0,0,0,0"
        )
    # Fixture with two regions: second heap known region with 0 committed
    # would violate current known!=0 optional rule? It is valid per the parser,
    # while actual REGION total commit equals default. 
    raw = "\n".join(lines)
    assert len(parse_owner(raw, regions, busy)) == 4
    negatives = (
        raw.replace(",0,1,1,1,1,0,", ",0,1,0,1,1,0,", 1),
        raw.replace(",0,1,1,1,1,0,", ",0,0,1,1,1,0,", 1),
        raw.replace(",1,0,1,1,1,0,0,0,0", ",1,1,1,1,1,0,0,0,0", 1),
        raw.replace(",1,0,1,1,1,0,0,0,0", ",2,0,1,1,1,0,0,0,0", 1),
        raw.replace(",0,1,1,1,1,0,4096,", ",0,1,1,1,1,0,8192,", 1),
        "\n".join(lines[:-1]),
        raw + "\n" + lines[0],
    )
    for bad in negatives:
        try:
            parse_owner(bad, regions, busy)
        except ValueError:
            continue
        raise AssertionError("invalid per-heap owner fixture accepted")
    print("C545D_HEAP_OWNER_ANALYZER_SELFTEST_PASS,negative_cases=7,"
          "positive_cases=1,new_windows_runs=0,no_camera=1")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--folder", type=Path)
    args = ap.parse_args()
    if args.selftest:
        selftest()
    else:
        if args.folder is None:
            ap.error("--folder required")
        print("\n".join(analyze(args.folder)))


if __name__ == "__main__":
    main()
