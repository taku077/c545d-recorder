#!/usr/bin/env python3
"""Fail-closed preflight for actual Windows GIO *first* AppInfo call stacks.

Inputs are current unmodified source and the old, verified build workflow.
This does NOT prove that any PDB exists or matches the DLL until a Windows
runner examines the actual build output and resolves real native ETLX frames.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

def verify(probe: str, workflow: str) -> str:
    if any(not isinstance(v,str) or len(v)>400000 for v in (probe,workflow)):
        raise ValueError("missing_or_unbounded_source")
    required_probe=(
        "int main(int argc, char **argv)",
        "monitor = g_app_info_monitor_get();",
        "enumerate_apps();    /* Ensure registry watchers and AppInfo cache initialize. */",
        'report_vm("baseline", 0);',
        'report_key_handles("before_cleanup", cycle_count);',
        'report_vm("settled_cleanup", cycle_count + 2);',
    )
    for item in required_probe:
        if probe.count(item)!=1:raise ValueError("probe_first_use_source_changed")
    if not(probe.index(required_probe[0]) <
           probe.index(required_probe[1]) <
           probe.index(required_probe[2]) <
           probe.index(required_probe[3]) <
           probe.index(required_probe[4]) <
           probe.index(required_probe[5])):
        raise ValueError("probe_first_use_phase_order_invalid")
    required_workflow=(
        "git clone --depth 1 --branch 2.82.4",
        "py -m mesonbuild.mesonmain setup $build $src",
        "-Dbuildtype=debugoptimized",
        "py -m mesonbuild.mesonmain compile -C $build",
        "$built=@(Get-ChildItem $build -Recurse -Filter gio-2.0-0.dll -File)",
        "if($built.Count -ne 1){throw 'Built GIO DLL not unique'}",
        "Invoke-C545DGioEtwOwner16Window.ps1",
        "--late-window",
    )
    for needle in required_workflow:
        seen=workflow.count(needle)
        if seen!=1 and not (needle=="Invoke-C545DGioEtwOwner16Window.ps1" and seen>=1):
            raise ValueError("pinned_build_or_prior_window_drift")
    if not(workflow.index(required_workflow[0])<
           workflow.index(required_workflow[1])<
           workflow.index(required_workflow[2])<
           workflow.index(required_workflow[3])<
           workflow.index(required_workflow[4])):
        raise ValueError("build_order_or_meson_options_changed")
    if ("LookupSymbolsForModule" in workflow or
        "Test-Path (Join-Path $build 'gio-2.0-0.pdb')" in workflow):
        raise ValueError("pdb_already_checked_reassess")
    return (
        "C545D_GIO_ORIGINAL_SOURCE_READINESS,"
        "prior_GIO_ETW_start_after_first_AppInfo_init=1,"
        "prior_late4_loses_earlier_owner_origins=1,"
        "pinned_GLIB_2824_source_clone=1,"
        "meson_debugoptimized_configured=1,"
        "built_GIO_DLL_unique_guard=1,"
        "matching_GIO_PDB_file_physically_verified=0,"
        "native_GIO_PDB_GUID_age_verified=0,"
        "native_GIO_method_symbol_verified=0,"
        "new_capture_start_required_before_first_AppInfo_call=1,"
        "no_GIO_original_source_proven_by_this_preflight=1,"
        "release_HOLD=1,host_untouched=1"
    )

def selftest() -> None:
    probe=('int main(int argc, char **argv)\n'
        '    monitor = g_app_info_monitor_get();\n'
        '    enumerate_apps();    /* Ensure registry watchers and AppInfo cache initialize. */\n'
        '    report_vm("baseline", 0);\n'
        '    report_key_handles("before_cleanup", cycle_count);\n'
        '    report_vm("settled_cleanup", cycle_count + 2);\n')
    workflow=('git clone --depth 1 --branch 2.82.4 xxx\n'
        'py -m mesonbuild.mesonmain setup $build $src --foo -Dbuildtype=debugoptimized\n'
        'py -m mesonbuild.mesonmain compile -C $build\n'
        '$built=@(Get-ChildItem $build -Recurse -Filter gio-2.0-0.dll -File)\n'
        "if($built.Count -ne 1){throw 'Built GIO DLL not unique'}\n"
        'py tests/patch_gio_probe_etw_phase_fence_ci.py $source --late-window\n'
        'Invoke-C545DGioEtwOwner16Window.ps1\n')
    assert "physically_verified=0" in verify(probe,workflow)
    mutations=[
        (probe.replace("monitor = g_app_info_monitor_get();","monitor = none;"),workflow),
        (probe.replace("monitor = g_app_info_monitor_get();","monitor = g_app_info_monitor_get();\nmonitor = g_app_info_monitor_get();"),workflow),
        (probe.replace('report_vm("baseline", 0);','report_vm("after", 0);'),workflow),
        (probe.replace('report_key_handles("before_cleanup", cycle_count);',''),workflow),
        (probe.replace('report_vm("settled_cleanup", cycle_count + 2);',''),workflow),
        (probe.replace('enumerate_apps();    /* Ensure registry watchers and AppInfo cache initialize. */',''),workflow),
        (probe,workflow.replace("debugoptimized","release")),
        (probe,workflow.replace("2.82.4","2.84.0")),
        (probe,workflow.replace("--late-window","--initial-window")),
        (probe,workflow.replace("$built.Count -ne 1","$built.Count -gt 0")),
        (probe,workflow+"LookupSymbolsForModule"),
    ]
    for i,(a,b) in enumerate(mutations):
        try:verify(a,b)
        except ValueError:continue
        raise AssertionError(f"unsafe_gio_first_allocation_gate_accepted:{i}")
    print("C545D_GIO_ORIGINAL_SOURCE_READINESS_SELFTEST_PASS,"
          "positive=1,negative=11,physical_PDB_proof_still_required=1,"
          "new_windows_GIO_run_not_started=1,host_untouched=1")

def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--probe",type=Path)
    p.add_argument("--workflow",type=Path)
    a=p.parse_args()
    if a.selftest:
        selftest()
        return
    if a.probe is None or a.workflow is None:
        p.error("both --probe and --workflow required")
    print(verify(a.probe.read_text(encoding="utf-8"),
                 a.workflow.read_text(encoding="utf-8")))

if __name__=="__main__":
    main()
