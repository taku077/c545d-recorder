#!/usr/bin/env python3
"""Strict numeric-only replay of actual Windows2022 AppInfo phase run 44992842208.

Source: artifact 'c545d-combo16-scanfree-numeric-only-CI', id 14743065670.
Runs on Linux without rebuilding GIO, changing the registry or touching the
Tapo host. Exact control-adjusted metrics are frozen as *this run's evidence*,
not as leak targets, ABI proof, or evidence from older 256-cycle experiments.
"""
from __future__ import annotations

import argparse
from pathlib import Path

WINDOWS = ("0_16", "16_17", "17_18")
TYPES = {
    "GWin32AppInfo": (0, 0, 0),
    "GWin32AppInfoApplication": (0, -118, 118),
    "GWin32AppInfoFileExtension": (0, -312, 312),
    "GWin32AppInfoHandler": (0, -344, 344),
    "GWin32AppInfoShellVerb": (0, -593, 593),
    "GWin32AppInfoURLSchema": (0, -32, 32),
    "GWin32RegistryKey": (0, -236, 236),
}
RESOURCES = {
    ("private", "0_16"): 286720,
    ("private", "16_17"): 0,
    ("private", "17_18"): -4096,
    ("busy", "0_16"): 856,
    ("busy", "16_17"): -758302,
    ("busy", "17_18"): 754130,
}
PHASES = {
    "nochange": {
        "callbacks": 0,
        "workers": 1,
        "idle_ms": 2516,
        "callbacks_idle": 0,
        "worker_scans_idle": 0,
        "parser_ends_idle": 0,
        "worker_active_after_cleanup": 0,
        "worker_active_final": 0,
        "worker_completed_after_cleanup": 0,
        "boundary_tick_ambiguous": 0,
    },
    "registry": {
        "callbacks": 17,
        "workers": 18,
        "idle_ms": 2515,
        "callbacks_idle": 0,
        "worker_scans_idle": 1,
        "parser_ends_idle": 1,
        "worker_active_after_cleanup": 1,
        "worker_active_final": 0,
        "worker_completed_after_cleanup": 1,
        "boundary_tick_ambiguous": 1,
    },
}
SENTINELS = {
    "C545D_COMBO16_SCANFREE_PASS": {
        "source_mode": "combo", "cycles": "16",
        "valid_GObject_types": "7", "GObject_census_unavailable": "0",
        "GAppInfo_final_query_skipped": "1",
        "worker_quiescence_unproven": "1",
        "results_not_256cycle_equivalent": "1",
        "production_unmodified": "1", "host_install_approved": "0",
        "CI_only": "1",
    },
    "C545D_APPINFO_PHASE_TRACE_PASS": {
        "arms": "2", "cycles": "16",
        "GAppInfo_final_query_skipped": "1",
        "allocation_owner_proven": "0",
        "real_camera": "0", "host_modified": "0",
    },
}
COMMON_TRACE = {"timing_perturbation_possible": "1", "quiescence_proven": "0"}
COMMON_RESOURCE = {"new_alloc_site_proven": "0", "real_host_untested": "1"}
COMMON_TYPE = {"instance_count_not_heap_owner": "1", "CI_only": "1"}


def fields(line: str) -> tuple[str, dict[str, str]]:
    parts = line.split(",")
    name, values = parts[0], {}
    for entry in parts[1:]:
        if entry.count("=") != 1:
            raise ValueError("non-numeric or malformed archived record")
        key, value = entry.split("=", 1)
        if not key or key in values or not value:
            raise ValueError("duplicate or empty archived field")
        values[key] = value
    return name, values


def exact_subset(record: dict[str, str], expected: dict[str, str], label: str) -> None:
    for key, value in expected.items():
        if record.get(key) != value:
            raise ValueError(f"{label}: {key} mismatch")


def check(raw: str) -> list[str]:
    seen_resources: dict[tuple[str, str], int] = {}
    seen_types: dict[tuple[str, str], int] = {}
    seen_phases: dict[str, dict[str, str]] = {}
    seen_sentinels: set[str] = set()

    for line in raw.splitlines():
        if not line.strip():
            continue
        name, d = fields(line)
        if name == "C545D_COMBO16_SCANFREE_RESOURCE":
            k = (d.get("kind", ""), d.get("window", ""))
            if k not in RESOURCES or k in seen_resources:
                raise ValueError("unexpected/duplicate resource window")
            expected = {**COMMON_RESOURCE, "kind": k[0], "window": k[1]}
            exact_subset(d, expected, "resource")
            if set(d) != set(expected) | {"registry_raw", "nochange_raw", "controlled"}:
                raise ValueError("unexpected resource field")
            reg, control, adj = (int(d[n]) for n in ("registry_raw", "nochange_raw", "controlled"))
            if adj != reg - control or adj != RESOURCES[k]:
                raise ValueError("source-control adjusted resource mismatch")
            if control != 0 and k[1] != "0_16":
                raise ValueError("unexpected nochange cleanup footprint")
            seen_resources[k] = adj
        elif name == "C545D_COMBO16_SCANFREE_GOBJECT":
            k = (d.get("type", ""), d.get("window", ""))
            if k[0] not in TYPES or k[1] not in WINDOWS or k in seen_types:
                raise ValueError("unexpected/duplicate GObject cohort")
            expected = {**COMMON_TYPE, "type": k[0], "window": k[1]}
            exact_subset(d, expected, "type")
            if set(d) != set(expected) | {"registry_raw", "nochange_raw", "controlled"}:
                raise ValueError("unexpected type field")
            reg, control, adj = (int(d[n]) for n in ("registry_raw", "nochange_raw", "controlled"))
            if adj != reg - control or adj != TYPES[k[0]][WINDOWS.index(k[1])]:
                raise ValueError("source-control adjusted type mismatch")
            seen_types[k] = adj
        elif name == "C545D_APPINFO_PHASE_TRACE":
            arm = d.get("arm", "")
            if arm not in PHASES or arm in seen_phases:
                raise ValueError("unexpected/duplicate phase arm")
            expected = {**COMMON_TRACE, "arm": arm,
                        **{key: str(v) for key, v in PHASES[arm].items()}}
            if d != expected:
                raise ValueError(f"phase trace differs from archived Windows {arm}")
            seen_phases[arm] = d
        elif name in SENTINELS:
            if name in seen_sentinels or d != SENTINELS[name]:
                raise ValueError("missing or altered Windows evidence sentinel")
            seen_sentinels.add(name)
        else:
            raise ValueError(f"unknown archived record type: {name}")

    if (set(seen_resources) != set(RESOURCES) or
        set(seen_types) != {(name, w) for name in TYPES for w in WINDOWS} or
        set(seen_phases) != set(PHASES) or
        seen_sentinels != set(SENTINELS)):
        raise ValueError("incomplete original Windows numeric archive")

    object_drop = sum(seen_types[t, "16_17"] for t in TYPES)
    object_rebound = sum(seen_types[t, "17_18"] for t in TYPES)
    if (object_drop, object_rebound) != (-1635, 1635):
        raise ValueError("type count rebound sum changed")
    if seen_resources["private", "16_17"] + seen_resources["private", "17_18"] != -4096:
        raise ValueError("cleanup private net changed")
    if seen_resources["busy", "16_17"] + seen_resources["busy", "17_18"] != -4172:
        raise ValueError("cleanup heap net changed")
    return [
        "C545D_PHASE_ARCHIVE_VERIFIED,source_run=44992842208,"
        "archive_id=14743065670,resource_windows=6,type_windows=21,"
        "phase_arms=2,windows_rerun=0",
        "C545D_PHASE_ARCHIVE_INFERENCE,registry_callbacks=17,"
        "worker_scans_idle=1,parser_ends_idle=1,"
        "idle_callbacks=0,object_drop=-1635,object_rebound=1635,"
        "private_cleanup_net=-4096,heap_busy_cleanup_net=-4172,"
        "tick_boundary_ambiguous=1,worker_quiescence_proven=0,"
        "allocation_owner_proven=0,real_device_untested=1",
    ]


def fixture() -> str:
    rows = []
    for (kind, window), value in RESOURCES.items():
        control = 45056 if (kind, window) == ("private", "0_16") else 0
        rows.append("C545D_COMBO16_SCANFREE_RESOURCE,"
                    f"kind={kind},window={window},registry_raw={value + control},"
                    f"nochange_raw={control},controlled={value},"
                    "new_alloc_site_proven=0,real_host_untested=1")
    for typ, values in TYPES.items():
        for window, value in zip(WINDOWS, values):
            rows.append("C545D_COMBO16_SCANFREE_GOBJECT,"
                        f"type={typ},window={window},registry_raw={value},"
                        f"nochange_raw=0,controlled={value},"
                        "instance_count_not_heap_owner=1,CI_only=1")
    for arm, values in PHASES.items():
        d = {**{"arm": arm}, **values, **COMMON_TRACE}
        rows.append("C545D_APPINFO_PHASE_TRACE," +
                    ",".join(f"{k}={v}" for k, v in d.items()))
    for name, values in SENTINELS.items():
        rows.append(name + "," + ",".join(f"{k}={v}" for k, v in values.items()))
    return "\n".join(rows)


def selftest() -> None:
    valid = fixture()
    assert len(check(valid)) == 2
    bad = [
        valid.replace("controlled=286720", "controlled=286721"),
        valid.replace("worker_scans_idle=1", "worker_scans_idle=0"),
        valid.replace("private,window=17_18", "private,window=16_17"),
        valid.replace("worker_quiescence_unproven=1", "worker_quiescence_unproven=0"),
        valid.replace("timing_perturbation_possible=1", "timing_perturbation_possible=0"),
        valid + "\nC545D_APPINFO_PHASE_TRACE_PASS,arms=2",
    ]
    bad = [candidate for candidate in bad if candidate != valid]
    for candidate in bad:
        try:
            check(candidate)
        except (ValueError, KeyError):
            continue
        raise AssertionError("corrupt archived fixture accepted")
    print(f"C545D_PHASE_ARCHIVE_SELFTEST_PASS,negative_cases={len(bad)},"
          "windows_rerun=0,real_host_untouched=1")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--source", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    if args.source is None:
        p.error("--source required")
    print("\n".join(check(args.source.read_text(encoding="utf-8-sig"))))


if __name__ == "__main__":
    main()
