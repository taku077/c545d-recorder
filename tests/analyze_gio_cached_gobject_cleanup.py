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


def analysis(root: Path) -> list[str]:
    sources = {}
    cleanup_presence: set[bool] = set()
    for run in RUNS:
        for mode in MODES:
            for arm in ARMS:
                file = root / str(run) / f"{mode}_{arm}_256.log"
                counts, after = read_types(file.read_text(encoding="utf-8-sig"))
                sources[run, mode, arm] = (counts, after)
                cleanup_presence.add(bool(after[EXTRA[0]]))
    if len(cleanup_presence) != 1:
        raise ValueError("incompatible archived cleanup coverage across runs/arms")
    cleanup_available = next(iter(cleanup_presence))
    results: list[str] = []
    for run in RUNS:
        for mode in MODES:
            no, no_extra = sources[run, mode, "nochange"]
            reg, reg_extra = sources[run, mode, "registry"]
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
    print("C545D_SAVED_GOBJECT_SELFTEST_PASS,positive_cases=2,"
          "negative_cases=4,new_windows_runs=0")


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
