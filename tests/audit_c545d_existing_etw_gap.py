#!/usr/bin/env python3
"""Audit WHY archived GIO ETW did not identify outstanding allocation owners.

This proves the limitations of the *existing* CI source without rerunning
an ETL capture. New instrumentation is not legitimate until the archived
trace's prelaunch, circular-window, top-N and lifetime problems are solved.
No addresses, private paths, ETL or symbolized stack names are processed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

SRC_MARKERS = (
    "$proc=Start-Process -FilePath $Probe",
    "Invoke-SafeXperf 'kernel' @('-on','BASE')",
    "'-FileMode','Circular'",
    "Invoke-SafeXperf 'symbol_stacks' @('-i',$etl,'-o',$stack,'-symbols','-a','heap','-stacks','-top','25')",
    "prebaseline_trace_proven=0,trace_circular=1,earlier_heap_events_may_be_lost=1,source_owner_proven=0",
)
FROZEN_MARKERS = (
    "# Original Windows run 45015173260, artifact 14750474942, independent",
    "truncated top-25 circular ETW, NOT allocated/live bytes or proof of owner.",
    "source_owner_proven=0,top25_not_full_census=1",
)


def audit(controller: str, frozen: str) -> str:
    for marker in SRC_MARKERS:
        if controller.count(marker) != 1:
            raise ValueError("etw_capture_source_contract_changed")
    for marker in FROZEN_MARKERS:
        if frozen.count(marker) != 1:
            raise ValueError("archived_etw_evidence_provenance_changed")
    proc = controller.index(SRC_MARKERS[0])
    kernel = controller.index(SRC_MARKERS[1])
    circular = controller.index(SRC_MARKERS[2])
    report = controller.index(SRC_MARKERS[3])
    if not (proc < kernel < circular < report):
        raise ValueError("trace_timing_or_window_contract_changed")
    if "WaitForExit(90000)" not in controller or (
            controller.index("WaitForExit(90000)") > report):
        raise ValueError("archive_not_post_process")
    return (
        "C545D_ETW_GAP_AUDIT_PASS,"
        "original_run=45015173260,"
        "original_artifact=14750474942,"
        "prelaunch_events_not_proven=1,"
        "circular_event_loss_possible=1,"
        "module_frames_top25_not_allocation_bytes=1,"
        "quiescent_lifetime_owner_proven=0,"
        "exact_gap=ALLOCATION_FREE_LIFETIME_WITH_COMPLETE_COVERAGE,"
        "no_new_capture=1,real_host_untouched=1"
    )


def selftest() -> None:
    controller = "\n".join(SRC_MARKERS) + "\n" + "WaitForExit(90000)"
    frozen = "\n".join(FROZEN_MARKERS)
    # The isolated source fixture is not a real script, so the post-process
    # marker must occur before symbolized report, matching real ordering.
    controller = controller.replace(
        SRC_MARKERS[3],
        "WaitForExit(90000)\n" + SRC_MARKERS[3]
    ).replace("\nWaitForExit(90000)\nWaitForExit(90000)", "\nWaitForExit(90000)")
    # Source-only checks cannot prove completeness. They MUST fail when a
    # declared limitation is altered or a prelaunch ordering claim is faked.
    assert audit(controller, frozen).startswith("C545D_ETW_GAP_AUDIT_PASS,")
    bad = [
        (controller.replace(SRC_MARKERS[0], ""), frozen),
        (controller.replace(SRC_MARKERS[2], ""), frozen),
        (controller.replace(SRC_MARKERS[3], ""), frozen),
        (controller.replace(SRC_MARKERS[4], ""), frozen),
        (controller, frozen.replace(FROZEN_MARKERS[1], "")),
        (controller, frozen.replace(FROZEN_MARKERS[2], "")),
        (controller.replace(SRC_MARKERS[0]+"\n", "").replace(SRC_MARKERS[1],
             SRC_MARKERS[1]+"\n"+SRC_MARKERS[0]), frozen),
        (controller.replace("WaitForExit(90000)", ""), frozen),
    ]
    for a, b in bad:
        try:
            audit(a, b)
        except ValueError:
            continue
        raise AssertionError("unsafe_etw_gap_fixture_accepted")
    print("C545D_ETW_GAP_SELFTEST_PASS,negative=8,positive=1,new_windows_runs=0")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--controller", type=Path)
    ap.add_argument("--frozen", type=Path)
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.controller or not args.frozen:
        ap.error("--controller and --frozen required")
    print(audit(args.controller.read_text(encoding="utf-8"),
                args.frozen.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
