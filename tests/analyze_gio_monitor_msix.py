#!/usr/bin/env python3
"""CI ONLY: classify GAppInfoMonitor signals around TRUE signed MSIX events.

Counts before each natural g_app_info_get_all() tell whether signals are
spontaneous. A post-query changed count is NOT proof of spontaneous signaling.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path
from analyze_gio_natural_msix_refresh import parse, EVENT, CLEANUP, NATURAL

OBSERVE = re.compile(r"^C545D_APPINFO_MONITOR_OBSERVATION,stage=(\d+),changed=(\d+)$",re.M)
FINAL = re.compile(r"^C545D_APPINFO_MONITOR_FINAL,changed=(\d+),clean_stop=1$",re.M)
START = "C545D_APPINFO_MONITOR_STARTED,context_ready=1"


def parse_real_event_only(raw: str):
    if CLEANUP not in raw:
        raise ValueError("missing test package/certificate cleanup")
    matches=EVENT.findall(raw)
    if len(matches)!=1:
        raise ValueError("missing/duplicate real PackageCatalog OS event evidence")
    nums=tuple(map(int,matches[0]))
    if nums != (9,7,2,18,1,1,1):
        raise ValueError("wrong real signed MSIX OS event/completion counters")
    baseline=re.findall(r"(?m)^C545D_GIO_REAL_MSIX_STEP_OK,stage=0,apps=(\d+)\s*$",raw)
    cleanup=re.findall(r"(?m)^C545D_GIO_REAL_MSIX_STEP_OK,stage=4,apps=(\d+)\s*$",raw)
    if len(baseline)!=1 or len(cleanup)!=1:
        raise ValueError("missing/duplicate GIO baseline/final scans")
    base=int(baseline[0])
    stages=[(int(i),int(n)) for i,n in NATURAL.findall(raw)]
    if stages != [(1,base+1),(2,base+1),(3,base)] or int(cleanup[0])!=base:
        raise ValueError("natural app list population not correct under no-registry stimulus")
    no_writes=[int(s) for s in re.findall(r"(?m)^C545D_GIO_NO_CI_REGISTRY_STIMULUS,stage=(\d+),write=0\s*$",raw)]
    if no_writes != [1,2,3]:
        raise ValueError("synthetic registry stimulus was not disabled in all three stages")
    if re.search(r"(?m)^C545D_GIO_REAL_MSIX_STEP_OK,stage=[123],",raw):
        raise ValueError("synthetic registry positive-control scan was erroneously executed")
    return {"natural_install_refreshed":1,"natural_uninstall_refreshed":1}


def classify(raw: str, no_registry_stimulus: bool = False) -> str:
    base = parse_real_event_only(raw) if no_registry_stimulus else parse(raw)
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
    expected_post = (1,2,3) if no_registry_stimulus else (1,3,5)
    expected_final = "3" if no_registry_stimulus else "6"
    if post != expected_post:
        raise ValueError(f"missing or duplicate AppInfo worker monitor signal {post}")
    if not all(before in (expected_post[i]-1,expected_post[i])
               for i,before in enumerate(pre)):
        raise ValueError(f"unexpected monitor signal before genuine stage {pre}")
    # A monitor signal before each public GAppInfo query is possible only
    # if the ORIGINAL registry-watcher worker rebuilt independently. It
    # is not proof that a PackageCatalog-only event signals GLib.

    m = FINAL.findall(raw)
    if m != [expected_final]:
        raise ValueError(f"monitor cleanup/final count not exact: {m}")
    return ("C545D_APPINFO_MONITOR_CI_PASS,"
            "real_package_events=18,natural_apps_39_40_40_39=1,"
            "pre_query_changed_cumulative=" + ";".join(map(str,pre)) + ","
            "post_stage_changed_cumulative=" + ";".join(map(str,post)) + ","
            "changed_total=" + expected_final + ","
            "worker_rebuild_notification=1,monitor_stopped=1,"
            "CI_registry_stimulus_disabled=" + str(int(no_registry_stimulus)) + ","
            "PackageCatalog_only_spontaneous_NOT_proven=1,"
            "live_Win10_unverified=1,CI_only=1")


def selftest():
    fixture = "\n".join([
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=0,apps=39",
        START,
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=11,changed=0",
        "C545D_GIO_REAL_MSIX_NATURAL_STAGE,stage=1,apps=40",
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=21,changed=1",
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=1,apps=40",
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=12,changed=2",
        "C545D_GIO_REAL_MSIX_NATURAL_STAGE,stage=2,apps=40",
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=22,changed=3",
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=2,apps=40",
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=13,changed=4",
        "C545D_GIO_REAL_MSIX_NATURAL_STAGE,stage=3,apps=39",
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=23,changed=5",
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=3,apps=39",
        "C545D_APPINFO_MONITOR_FINAL,changed=6,clean_stop=1",
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=4,apps=39",
        "C545D_REAL_PACKAGECATALOG_EVENT_PASS,install_delta=9,update_delta=7,"
        "uninstall_delta=2,total_delta=18,install_complete=1,"
        "update_complete=1,uninstall_complete=1,no_synthetic_notifications=true,"
        "only_ci_package_events_counted=true",
        "C545D_REAL_APPX_CLEANUP_EXECUTED=true,runner_only=true"
    ]) + "\n"
    assert "C545D_APPINFO_MONITOR_CI_PASS" in classify(fixture)
    broken = [
        fixture.replace("stage=11,changed=0","stage=11,changed=2"),
        fixture.replace("stage=22,changed=3","stage=22,changed=1"),
        fixture.replace("stage=23,changed=5","stage=23,changed=6"),
        fixture.replace("stage=12,changed=2","stage=11,changed=2"),
        fixture.replace("total_delta=18","total_delta=17"),
        fixture.replace("clean_stop=1","clean_stop=0"),
        fixture.replace("apps=39\nC545D_APPINFO_MONITOR_FINAL","apps=38\nC545D_APPINFO_MONITOR_FINAL"),
    ]
    for i,raw in enumerate(broken):
        try:classify(raw)
        except ValueError:continue
        raise AssertionError(f"accepted invalid monitor evidence {i}")
    spontaneous = fixture.replace("stage=11,changed=0","stage=11,changed=1")
    assert "C545D_APPINFO_MONITOR_CI_PASS" in classify(spontaneous)
    no_registry=fixture
    for old,new in (("stage=12,changed=2","stage=12,changed=1"),
                    ("stage=22,changed=3","stage=22,changed=2"),
                    ("stage=13,changed=4","stage=13,changed=2"),
                    ("stage=23,changed=5","stage=23,changed=3"),
                    ("FINAL,changed=6","FINAL,changed=3")):
        no_registry=no_registry.replace(old,new)
    for stage in (1,2,3):
        no_registry=no_registry.replace(
            f"C545D_GIO_REAL_MSIX_STEP_OK,stage={stage},apps={40 if stage<3 else 39}",
            f"C545D_GIO_NO_CI_REGISTRY_STIMULUS,stage={stage},write=0")
    assert "CI_registry_stimulus_disabled=1" in classify(no_registry,True)
    rejects=[
        no_registry.replace("stage=2,write=0","stage=2,write=1"),
        no_registry + "C545D_GIO_REAL_MSIX_STEP_OK,stage=2,apps=40\n",
        no_registry.replace("NATURAL_STAGE,stage=3,apps=39",
                            "NATURAL_STAGE,stage=3,apps=40")
    ]
    for corrupt in rejects:
        try:classify(corrupt,True)
        except ValueError:continue
        raise AssertionError("malformed registry-free evidence accepted")
    print("C545D_APPINFO_MONITOR_ANALYZER_SELFTEST_PASS,valid=3,rejected=10")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--no-registry-stimulus",action="store_true")
    parser.add_argument("--input",type=Path)
    args=parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.input is None:
        parser.error("--input required")
    print(classify(args.input.read_text(encoding="utf-8-sig",errors="replace"), args.no_registry_stimulus))


if __name__=="__main__":
    main()
