#!/usr/bin/env python3
"""CI ONLY: classify GAppInfoMonitor signals around TRUE signed MSIX events.

Counts before each natural g_app_info_get_all() tell whether signals are
spontaneous. A post-query changed count is NOT proof of spontaneous signaling.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path
from analyze_gio_natural_msix_refresh import parse

OBSERVE = re.compile(r"^C545D_APPINFO_MONITOR_OBSERVATION,stage=(\d+),changed=(\d+)$",re.M)
FINAL = re.compile(r"^C545D_APPINFO_MONITOR_FINAL,changed=(\d+),clean_stop=1$",re.M)
START = "C545D_APPINFO_MONITOR_STARTED,context_ready=1"


def classify(raw: str) -> str:
    base = parse(raw)
    if (base["natural_install_refreshed"] != 1
            or base["natural_uninstall_refreshed"] != 1):
        raise ValueError("ordinary GIO natural cache refresh did not succeed")
    if raw.count(START) != 1:
        raise ValueError("monitor not acquired exactly once")
    pairs = [(int(s),int(n)) for s,n in OBSERVE.findall(raw)]
    stages = (11,21,12,22,13,23)
    if len(pairs) != len(stages) or tuple(s for s,_ in pairs) != stages:
        raise ValueError(f"wrong stages/order/duplicate monitor observations: {pairs}")
    pre = tuple(n for s,n in pairs if s < 20)
    post = tuple(n for s,n in pairs if s > 20)
    if pre != (0,1,2):
        raise ValueError(f"unexpected spontaneous or duplicate monitor signals {pre}")
    if post != (1,2,3):
        raise ValueError(f"post-query signals missing or duplicate {post}")
    m = FINAL.findall(raw)
    if m != ["3"]:
        raise ValueError(f"monitor cleanup/final count not exact: {m}")
    return ("C545D_APPINFO_MONITOR_CI_PASS,"
            "real_package_events=18,natural_apps_39_40_40_39=1,"
            "spontaneous_pre_query_changed=0,"
            "post_query_changed_install=1,post_query_changed_update=1,"
            "post_query_changed_uninstall=1,changed_total=3,"
            "monitor_stopped=1,live_Win10_unverified=1,"
            "spontaneous_behavior_NOT_FIXED=1,CI_only=1")


def selftest():
    fixture = "\n".join([
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=0,apps=39",
        START,
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=11,changed=0",
        "C545D_GIO_REAL_MSIX_NATURAL_STAGE,stage=1,apps=40",
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=21,changed=1",
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=1,apps=40",
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=12,changed=1",
        "C545D_GIO_REAL_MSIX_NATURAL_STAGE,stage=2,apps=40",
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=22,changed=2",
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=2,apps=40",
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=13,changed=2",
        "C545D_GIO_REAL_MSIX_NATURAL_STAGE,stage=3,apps=39",
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=23,changed=3",
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=3,apps=39",
        "C545D_APPINFO_MONITOR_FINAL,changed=3,clean_stop=1",
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=4,apps=39",
        "C545D_REAL_PACKAGECATALOG_EVENT_PASS,install_delta=9,update_delta=7,"
        "uninstall_delta=2,total_delta=18,install_complete=1,"
        "update_complete=1,uninstall_complete=1,no_synthetic_notifications=true,"
        "only_ci_package_events_counted=true",
        "C545D_REAL_APPX_CLEANUP_EXECUTED=true,runner_only=true"
    ]) + "\n"
    assert "C545D_APPINFO_MONITOR_CI_PASS" in classify(fixture)
    broken = [
        fixture.replace("stage=11,changed=0","stage=11,changed=1"),
        fixture.replace("stage=22,changed=2","stage=22,changed=1"),
        fixture.replace("stage=23,changed=3","stage=23,changed=4"),
        fixture.replace("stage=12,changed=1","stage=11,changed=1"),
        fixture.replace("total_delta=18","total_delta=17"),
        fixture.replace("clean_stop=1","clean_stop=0"),
        fixture.replace("apps=39\nC545D_APPINFO_MONITOR_FINAL","apps=38\nC545D_APPINFO_MONITOR_FINAL"),
    ]
    for i,raw in enumerate(broken):
        try:classify(raw)
        except ValueError:continue
        raise AssertionError(f"accepted invalid monitor evidence {i}")
    print("C545D_APPINFO_MONITOR_ANALYZER_SELFTEST_PASS,valid=1,rejected=7")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--input",type=Path)
    args=parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.input is None:
        parser.error("--input required")
    print(classify(args.input.read_text(encoding="utf-8-sig",errors="replace")))


if __name__=="__main__":
    main()
