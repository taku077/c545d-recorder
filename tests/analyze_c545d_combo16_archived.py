#!/usr/bin/env python3
"""Archive-only strict numeric revalidation of the original Combo scanfree run.

Source: Windows2022 run 44990673986, numeric-only upload. This does NOT
assert that OS watcher/worker is idle or identify an allocation stack.
No new Windows or camera runs are needed.
"""
import argparse
from pathlib import Path
import re

TYPES = {
    "GWin32AppInfo": (0, 0, 0),
    "GWin32AppInfoApplication": (0, -118, 118),
    "GWin32AppInfoShellVerb": (0, -593, 593),
    "GWin32AppInfoHandler": (0, -344, 344),
    "GWin32AppInfoFileExtension": (0, -312, 312),
    "GWin32AppInfoURLSchema": (0, -28, 28),
    "GWin32RegistryKey": (0, -226, 226),
}
WINDOWS = ("0_16", "16_17", "17_18")
RESOURCE = {
    "private": (106496, 0, 0),
    "busy": (-3658, -756632, 756632),
}
R = re.compile(
    r"C545D_COMBO16_SCANFREE_RESOURCE,kind=(private|busy),"
    r"window=(0_16|16_17|17_18),"
    r"registry_raw=(-?\d+),nochange_raw=(-?\d+),controlled=(-?\d+),"
    r"new_alloc_site_proven=0,real_host_untested=1$"
)
T = re.compile(
    r"C545D_COMBO16_SCANFREE_GOBJECT,type=([A-Za-z0-9_]+),"
    r"window=(0_16|16_17|17_18),"
    r"registry_raw=(-?\d+),nochange_raw=(-?\d+),controlled=(-?\d+),"
    r"instance_count_not_heap_owner=1,CI_only=1$"
)
P = (
    "C545D_COMBO16_SCANFREE_PASS,source_mode=combo,cycles=16,"
    "valid_GObject_types=7,GObject_census_unavailable=0,"
    "GAppInfo_final_query_skipped=1,worker_quiescence_unproven=1,"
    "results_not_256cycle_equivalent=1,production_unmodified=1,"
    "host_install_approved=0,CI_only=1"
)


def parse(raw: str) -> list[str]:
    records = {}
    types = {}
    gate = 0
    for line in raw.splitlines():
        if line == P:
            gate += 1
        elif line.startswith("C545D_COMBO16_SCANFREE_RESOURCE,"):
            m = R.fullmatch(line)
            if not m:
                raise ValueError("resource parser drift")
            kind, window, reg, ctl, effect = m.groups()
            key = (kind, window)
            if key in records or int(reg) - int(ctl) != int(effect):
                raise ValueError("resource duplicate or bad control subtraction")
            records[key] = int(effect)
        elif line.startswith("C545D_COMBO16_SCANFREE_GOBJECT,"):
            m = T.fullmatch(line)
            if not m:
                raise ValueError("type parser drift")
            name, window, reg, ctl, effect = m.groups()
            key = (name, window)
            if key in types or name not in TYPES or int(reg) - int(ctl) != int(effect):
                raise ValueError("GObject duplicate/unknown/bad control subtraction")
            types[key] = int(effect)
        elif line.startswith("C545D_COMBO16_SCANFREE_"):
            raise ValueError("unapproved extra numeric row")
    if gate != 1 or len(records) != 6 or len(types) != 21:
        raise ValueError("incomplete original 16-cycle numeric cohort")
    for kind, values in RESOURCE.items():
        for i, w in enumerate(WINDOWS):
            if records.get((kind, w)) != values[i]:
                raise ValueError("original resource trajectory differs")
    for name, expected in TYPES.items():
        for i, w in enumerate(WINDOWS):
            if types.get((name, w)) != expected[i]:
                raise ValueError("original GObject trajectory differs")
    if sum(types[name, "16_17"] for name in TYPES) != -1621:
        raise ValueError("disappearing graph count incorrect")
    if sum(types[name, "17_18"] for name in TYPES) != 1621:
        raise ValueError("returned graph count incorrect")
    return [
        "C545D_COMBO16_SAVED_GRAPH,original_run=44990673986,"
        "observed_types=7,control_adjusted_objects_16_17=-1621,"
        "control_adjusted_objects_17_18=1621,"
        "net_types_16_18=0,"
        "object_identity_unobserved=1,worker_quiescence_unproven=1",
        "C545D_COMBO16_SAVED_RESOURCE,original_run=44990673986,"
        "PrivateUsage_0_16=106496,PrivateUsage_16_17=0,"
        "PrivateUsage_17_18=0,HeapWalkBUSY_16_17=-756632,"
        "HeapWalkBUSY_17_18=756632,"
        "PrivateUsage_not_equivalent_HeapWalk=1",
        "C545D_COMBO16_ARCHIVE_AUDIT_PASS,source_run=44990673986,"
        "Windows_reruns=0,source_mode=combo,"
        "GAppInfo_query_final_skipped=1,"
        "post_cleanup_worker_rebuild_plausible_not_proven=1,"
        "native_allocation_owner_unknown=1,"
        "360B_longrun_rate_unproven=1,user_PC_untested=1",
    ]


def selftest() -> None:
    data = [P]
    for k, values in RESOURCE.items():
        for window, v in zip(WINDOWS, values):
            data.append(
                f"C545D_COMBO16_SCANFREE_RESOURCE,kind={k},window={window},"
                f"registry_raw={v},nochange_raw=0,controlled={v},"
                "new_alloc_site_proven=0,real_host_untested=1"
            )
    for name, vals in TYPES.items():
        for window, v in zip(WINDOWS, vals):
            data.append(
                f"C545D_COMBO16_SCANFREE_GOBJECT,type={name},window={window},"
                f"registry_raw={v},nochange_raw=0,controlled={v},"
                "instance_count_not_heap_owner=1,CI_only=1"
            )
    good = "\n".join(data)
    assert parse(good)[-1].startswith("C545D_COMBO16_ARCHIVE_AUDIT_PASS,")
    bad = [
        good.replace("PrivateUsage_0_16", "PrivateUsage_0_15"),
        good.replace("controlled=106496", "controlled=106495"),
        good.replace("controlled=756632", "controlled=756633"),
        good.replace("type=GWin32RegistryKey", "type=UnknownType"),
        good.replace(P, ""),
    ]
    # The first mutation is intentionally absent from input; use a real one.
    bad[0] = good.replace("window=0_16", "window=0_15", 1)
    for text in bad:
        try: parse(text)
        except ValueError: pass
        else: raise AssertionError("corrupt saved numeric cohort accepted")
    print("C545D_COMBO16_SAVED_SELFTEST_PASS,negative_cases=5,Windows_runs=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--file", type=Path)
    a = p.parse_args()
    if a.selftest:
        selftest()
    else:
        if not a.file: p.error("--file required")
        print("\n".join(parse(a.file.read_text(encoding="utf-8-sig"))))


if __name__ == "__main__":
    main()
