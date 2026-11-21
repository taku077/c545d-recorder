#!/usr/bin/env python3
"""Offline-only seven-type GObject snapshot audit of THREE original Windows runs.

Exactly the archived 2026-11-19 MSYS2 display-cache AB256 artifacts are read.
This is NOT the subsequent MSVC Core/Combo experiment: its numeric archive
explicitly excluded GIO_TYPE. No Windows re-runs, recordings, raw logs or
allocation stacks are produced. A live count is not an allocation lifetime
trace or proof that the remaining PrivateUsage is owned by a particular type.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

from analyze_gio_cached_residual_epochs import RUNS, TYPES, CYCLES, parse_log

MODES = ("default", "cache")
ARMS = ("nochange", "registry")
EXTRA = (("after_cleanup", 257), ("settled_cleanup", 258))
LINE = re.compile(
    r"GIO_TYPE,(after_cleanup|settled_cleanup),(257|258),"
    r"(GWin32AppInfo(?:Application|ShellVerb|Handler|FileExtension|URLSchema)?"
    r"|GWin32RegistryKey),(\d+)$"
)


def read_types(raw: str) -> tuple[dict[str, dict[int, int]], dict[tuple[str, int], dict[str, int]]]:
    # Strict shared reader rechecks the expected 256-cycle completion and
    # all seven GObject type counts at original checkpoints 0,64,128,192,256.
    old = parse_log(raw)
    baseline = {typ: dict(old["type:" + typ]) for typ in TYPES}
    extra = {point: {} for point in EXTRA}
    for row in raw.splitlines():
        if not row.startswith("GIO_TYPE,"):
            continue
        fields = row.split(",")
        if len(fields) != 5:
            raise ValueError("malformed GObject census")
        phase, value = fields[1], fields[2]
        if phase not in ("after_cleanup", "settled_cleanup"):
            continue
        m = LINE.fullmatch(row)
        if not m or (m.group(1), int(m.group(2))) not in EXTRA:
            raise ValueError("invalid cleanup type checkpoint or count")
        point = (m.group(1), int(m.group(2)))
        typ, value = m.group(3), int(m.group(4))
        if typ not in TYPES or typ in extra[point]:
            raise ValueError("unknown/duplicate cleanup GObject type")
        extra[point][typ] = value
    # Entire type series present, or explicitly unavailable. Incomplete
    # checkpoint arrays cannot be used to attribute a cleanup rebound.
    sizes = {len(v) for v in extra.values()}
    if sizes not in ({0}, {len(TYPES)}):
        raise ValueError("partial/mismatched cleanup GObject evidence")
    if sizes == {len(TYPES)} and any(set(x) != set(TYPES) for x in extra.values()):
        raise ValueError("incomplete cleanup GObject names")
    return baseline, extra



def read_cleanup_resources(raw: str) -> dict[tuple[str, int], dict[str, int]]:
    """Verify optional exact private-commit and heap-busy cleanup checkpoints.

    These are resource totals from the old source process; not estimates of
    live GObject heap bytes or object ownership.
    """
    result = {p: {} for p in EXTRA}
    for row in raw.splitlines():
        if not (row.startswith("GIO_VM,") or row.startswith("GIO_HEAP,")):
            continue
        a = row.split(",")
        if len(a) < 3 or a[1] not in ("after_cleanup", "settled_cleanup"):
            continue
        if not a[2].isdigit() or (a[1], int(a[2])) not in EXTRA:
            raise ValueError("invalid cleanup resource checkpoint")
        key = (a[1], int(a[2]))
        metric = "mem" if a[0] == "GIO_VM" else "heap"
        if (len(a) != (8 if metric == "mem" else 7)
                or any(not v.isdecimal() for v in a[2:])
                or int(a[-1]) != 0
                or (metric == "heap" and int(a[5]) < 1)
                or metric in result[key]):
            raise ValueError("invalid/duplicate numeric cleanup resource")
        result[key][metric] = int(a[3] if metric == "mem" else a[4])
    sizes = {len(result[p]) for p in EXTRA}
    if sizes not in ({0}, {2}) or (
            sizes == {2} and any(set(v) != {"mem", "heap"} for v in result.values())):
        raise ValueError("partial cleanup resource metrics")
    return result


def analysis(root: Path) -> list[str]:
    sources = {}
    cleanup_presence: set[bool] = set()
    resource_presence: set[bool] = set()
    for run in RUNS:
        for mode in MODES:
            for arm in ARMS:
                file = root / str(run) / f"{mode}_{arm}_256.log"
                raw = file.read_text(encoding="utf-8-sig")
                counts, after = read_types(raw)
                resources = read_cleanup_resources(raw)
                old = parse_log(raw)
                at256 = {"mem": old["private_usage"][256],
                         "heap": old["heap_busy"][256]}
                sources[run, mode, arm] = (counts, after, resources, at256)
                cleanup_presence.add(bool(after[EXTRA[0]]))
                resource_presence.add(bool(resources[EXTRA[0]]))
    if len(cleanup_presence) != 1 or len(resource_presence) != 1:
        raise ValueError("incompatible archived cleanup coverage across runs/arms")
    cleanup_available = next(iter(cleanup_presence))
    resource_available = next(iter(resource_presence))
    results: list[str] = []
    # Exact old source-run identity. Pin individual cleanup resource windows,
    # not a rounded percentage or a cross-run average. If the old saved
    # artifact changes or gets mixed, the audit must fail closed.
    pinned = {
        RUNS[0]: {
            "default": {"heap": (-352579, 363765), "mem": (0, 0)},
            "cache": {"heap": (-169044, 164872), "mem": (0, 0)},
        },
        RUNS[1]: {
            "default": {"heap": (-423749, 430763), "mem": (0, 135168)},
            "cache": {"heap": (-176120, 176120), "mem": (0, 0)},
        },
        RUNS[2]: {
            "default": {"heap": (-307424, 322782), "mem": (0, 0)},
            "cache": {"heap": (-167684, 167684), "mem": (0, 0)},
        },
    }
    for run in RUNS:
        for mode in MODES:
            no, no_extra, no_resources, no256 = sources[run, mode, "nochange"]
            reg, reg_extra, reg_resources, reg256 = sources[run, mode, "registry"]
            if cleanup_available:
                # For each type the matched treatment effect is the difference
                # between two separately run processes in the SAME Windows job.
                e256_257, e257_258 = [], []
                for typ in TYPES:
                    e256_257.append(
                        (reg_extra[EXTRA[0]][typ] - reg[typ][256])
                        - (no_extra[EXTRA[0]][typ] - no[typ][256])
                    )
                    e257_258.append(
                        (reg_extra[EXTRA[1]][typ] - reg_extra[EXTRA[0]][typ])
                        - (no_extra[EXTRA[1]][typ] - no_extra[EXTRA[0]][typ])
                    )
                for typ, early, late in zip(TYPES, e256_257, e257_258):
                    results.append(
                        f"C545D_SAVED_GOBJECT_CLEANUP_TYPE,run={run},"
                        f"mode={mode},type={typ},delta256_257={early},"
                        f"delta257_258={late},CI_only=1"
                    )
            else:
                e256_257, e257_258 = None, None
            if cleanup_available:
                # Exact identity of the three already-finished archival runs.
                # The only nonzero checked-type cleanup effect was a
                # *transient* GWin32RegistryKey count, fully reversed by 258.
                expected_key = {
                    RUNS[0]: {"default": 1, "cache": 2},
                    RUNS[1]: {"default": 1, "cache": 2},
                    RUNS[2]: {"default": 1, "cache": 1},
                }[run][mode]
                for typ, early, late in zip(TYPES, e256_257, e257_258):
                    expected = (expected_key, -expected_key) if (
                        typ == "GWin32RegistryKey") else (0, 0)
                    if (early, late) != expected:
                        raise ValueError("archived GObject transient identity changed")
            last128 = [
                (reg[t][256] - reg[t][128]) - (no[t][256] - no[t][128])
                for t in TYPES
            ]
            # This old three-run cached-AB result was previously checked.
            # Pin it as an exact per-type (not aggregate sum) identity.
            if any(last128):
                raise ValueError("historic six-cohort last128 GObject counts changed")
            if resource_available:
                for metric in ("mem", "heap"):
                    for point_a, point_b in ((("cycle", 256), EXTRA[0]),
                                             (EXTRA[0], EXTRA[1])):
                        reg_a = reg256[metric] if point_a[0] == "cycle" else reg_resources[point_a][metric]
                        no_a = no256[metric] if point_a[0] == "cycle" else no_resources[point_a][metric]
                        reg_b, no_b = reg_resources[point_b][metric], no_resources[point_b][metric]
                        a, b = reg_b - reg_a, no_b - no_a
                        idx = 0 if point_b == EXTRA[0] else 1
                        if b != 0 or a != pinned[run][mode][metric][idx]:
                            raise ValueError("original cleanup resource trajectory changed")
                        results.append(
                            f"C545D_SAVED_GOBJECT_RESOURCE_WINDOW,run={run},"
                            f"mode={mode},metric={metric},"
                            f"window={point_a[1]}_{point_b[1]},"
                            f"registry_raw={a},nochange_raw={b},"
                            f"control_adjusted={a-b},GObject_owner_unproven=1,CI_only=1"
                        )
            results.append(
                f"C545D_SAVED_GOBJECT_COHORT,run={run},mode={mode},"
                f"types={len(TYPES)},last128_net={sum(last128)},"
                f"last128_nonzero_types={sum(bool(x) for x in last128)},"
                f"cleanup_types_present={int(cleanup_available)},"
                f"cleanup256_257_net={sum(e256_257) if cleanup_available else 'NA'},"
                f"cleanup257_258_net={sum(e257_258) if cleanup_available else 'NA'},"
                f"cleanup257_258_nonzero_types={sum(bool(x) for x in e257_258) if cleanup_available else 'NA'},"
                "distinct_from_MSVCCoreCombo=1,CI_only=1"
            )
    if cleanup_available:
        results.append(
            "C545D_SAVED_GOBJECT_CROSSRUN_IDENTITY,source_runs=3,"
            "cohorts=6,seven_types_no_last128_growth=6of6,"
            "transient_GWin32RegistryKey_cleanup=6of6,"
            "other_six_GObject_types_cleanup_effect=0,"
            "registry_key_restored_by258=6of6,MSVC_Combo_not_tested=1,CI_only=1"
        )
    if resource_available:
        results.append(
            "C545D_SAVED_GOBJECT_RESOURCE_CROSSRUN_IDENTITY,source_runs=3,"
            "cohorts=6,heap_drop_then_rebound=6of6,"
            "private_memory_unchanged_both_cleanup_windows=5of6,"
            "private_late_plus135168=1of6,"
            "registry_key_transient_full_return=6of6,"
            "no_absolute_leak_claim=1,CI_only=1"
        )
    results.append(
        f"C545D_SAVED_GOBJECT_RESOURCE_SCOPE,archived_windows_runs=3,"
        f"cohorts=6,cleanup_metrics_available={int(resource_available)},"
        "old_MSVCCoreCombo_not_conflated=1,new_windows_runs=0,CI_only=1"
    )
    results.append(
        f"C545D_SAVED_GOBJECT_CLEANUP_PASS,archived_windows_runs=3,"
        f"arms=2,modes=2,types={len(TYPES)},cleanup_available={int(cleanup_available)},"
        f"new_windows_runs=0,MSVC_Combo_GObject_257_258_unavailable=1,"
        "PrivateUsage_owner_proven=0,user_host_modified=0"
    )
    return results


def selftest() -> None:
    # Ensure split/disjoint checkpoint evidence is not silently completed.
    lines = ["GIO_PROBE_DONE,cycles=256"]
    for cycle in CYCLES:
        p = "baseline" if cycle == 0 else "cycle"
        lines += [
            f"GIO_VM,{p},{cycle},10000,20,20,20,0",
            f"GIO_HEAP,{p},{cycle},5,1000,1,0",
        ]
        lines += [f"GIO_TYPE,{p},{cycle},{typ},2" for typ in TYPES]
    base = "\n".join(lines)
    x, extra = read_types(base)
    assert x[TYPES[0]][256] == 2 and not extra[EXTRA[1]]
    complete = base + "\n" + "\n".join(
        f"GIO_TYPE,{p},{i},{typ},2" for p, i in EXTRA for typ in TYPES
    )
    assert len(read_types(complete)[1][EXTRA[0]]) == len(TYPES)
    assert not read_cleanup_resources(complete)[EXTRA[0]]
    res = complete + "\n" + "\n".join(
        f"GIO_VM,{p},{i},10000,20,20,20,0\n"
        f"GIO_HEAP,{p},{i},5,1000,1,0" for p, i in EXTRA
    )
    assert read_cleanup_resources(res)[EXTRA[1]] == {"mem": 10000, "heap": 1000}
    for corrupt in (
        res.replace("GIO_HEAP,after_cleanup,257,5,1000,1,0", ""),
        res + "\nGIO_VM,after_cleanup,257,10000,20,20,20,0",
        res.replace("GIO_VM,settled_cleanup,258,10000,20,20,20,0",
                    "GIO_VM,settled_cleanup,258,10000,20,20,20,1"),
    ):
        try:
            read_cleanup_resources(corrupt)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid resource record accepted")
    bad = [
        complete.replace(f"GIO_TYPE,settled_cleanup,258,{TYPES[0]},2", ""),
        complete.replace(f"GIO_TYPE,after_cleanup,257,{TYPES[0]},2",
                         f"GIO_TYPE,after_cleanup,257,{TYPES[0]},-1"),
        complete + f"\nGIO_TYPE,settled_cleanup,258,{TYPES[0]},2",
        complete.replace(f"GIO_TYPE,after_cleanup,257,{TYPES[0]},2",
                         f"GIO_TYPE,after_cleanup,258,{TYPES[0]},2"),
    ]
    for sample in bad:
        try:
            read_types(sample)
        except ValueError:
            pass
        else:
            raise AssertionError("corrupt GObject cleanup census accepted")
    print("C545D_SAVED_GOBJECT_SELFTEST_PASS,positive_cases=3,"
          "negative_cases=7,new_windows_runs=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path)
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    if args.root is None:
        p.error("--root required")
    print("\n".join(analysis(args.root)))


if __name__ == "__main__":
    main()
