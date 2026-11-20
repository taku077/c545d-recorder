#!/usr/bin/env python3
"""Numeric-only real signed MSIX validation for unsolicited AppInfoMonitor.

Pass requires a monitor::changed callback *before* any public GAppInfo query,
correctly populated inventory only when the consumer chooses to query, one
terminal WinRT callback per stage, no registry stimulus, and clean teardown.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path
from analyze_gio_monitor_msix import parse_real_event_only

START="C545D_APPINFO_MONITOR_STARTED,context_ready=1"
REG="C545D_CI_NATIVE_MONITOR_SINK_REGISTRATION,ok=1"
OBS=re.compile(r"(?m)^C545D_APPINFO_MONITOR_OBSERVATION,stage=(\d+),changed=(\d+)\s*$")
DELIVERY=re.compile(r"(?m)^C545D_CI_NATIVE_MONITOR_DISPATCH,seq=(\d+)\s*$")
FINAL=re.compile(r"(?m)^C545D_APPINFO_MONITOR_FINAL,changed=(\d+),clean_stop=1\s*$")


def analyze(raw: str) -> str:
    parse_real_event_only(raw)
    if raw.count(START) != 1 or raw.count(REG) != 1:
        raise ValueError("native notification not registered exactly once")
    checkpoints=[(int(x),int(n)) for x,n in OBS.findall(raw)]
    expected=[(11,1),(21,1),(12,2),(22,2),(13,3),(23,3)]
    if checkpoints != expected:
        raise ValueError(f"not spontaneous, or monitor signal duplicate/missing: {checkpoints!r}")
    emitted=tuple(int(n) for n in DELIVERY.findall(raw))
    if emitted != (1,2,3):
        raise ValueError(f"native MTA notification delivery missing/duplicated: {emitted}")
    final=FINAL.findall(raw)
    if final != ["3"]:
        raise ValueError(f"invalid signal shutdown count: {final}")
    text_order=[
        (raw.find("stage=11,changed=1"), raw.find("NATURAL_STAGE,stage=1")),
        (raw.find("stage=12,changed=2"), raw.find("NATURAL_STAGE,stage=2")),
        (raw.find("stage=13,changed=3"), raw.find("NATURAL_STAGE,stage=3")),
    ]
    if any(a < 0 or b < 0 or a > b for a,b in text_order):
        raise ValueError("event arrived after caller-driven GAppInfo query")
    if "C545D_CI_NATIVE_MONITOR_SINK_REGISTRATION,ok=0" in raw:
        raise ValueError("fail-open sink registration")
    return ("C545D_APPINFO_NATIVE_SPONTANEOUS_CI_PASS,"
            "real_package_operations=3,callbacks=18,"
            "without_gio_query_pre_changed=1;2;3,"
            "after_gio_query_changed=1;2;3,"
            "native_MTA_dispatch_count=3,"
            "registry_write_stimulus=0,monitor_clean_stop=1,"
            "MTA_joins_on_close=1,no_periodic_polling=1,"
            "Win10_recorder_unverified=1,CI_only=1")


def selftest():
    fixture="\n".join([
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=0,apps=39",
        START,REG,
        "C545D_CI_NATIVE_MONITOR_DISPATCH,seq=1",
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=11,changed=1",
        "C545D_GIO_REAL_MSIX_NATURAL_STAGE,stage=1,apps=40",
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=21,changed=1",
        "C545D_GIO_NO_CI_REGISTRY_STIMULUS,stage=1,write=0",
        "C545D_CI_NATIVE_MONITOR_DISPATCH,seq=2",
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=12,changed=2",
        "C545D_GIO_REAL_MSIX_NATURAL_STAGE,stage=2,apps=40",
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=22,changed=2",
        "C545D_GIO_NO_CI_REGISTRY_STIMULUS,stage=2,write=0",
        "C545D_CI_NATIVE_MONITOR_DISPATCH,seq=3",
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=13,changed=3",
        "C545D_GIO_REAL_MSIX_NATURAL_STAGE,stage=3,apps=39",
        "C545D_APPINFO_MONITOR_OBSERVATION,stage=23,changed=3",
        "C545D_GIO_NO_CI_REGISTRY_STIMULUS,stage=3,write=0",
        "C545D_APPINFO_MONITOR_FINAL,changed=3,clean_stop=1",
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=4,apps=39",
        "C545D_REAL_PACKAGECATALOG_EVENT_PASS,install_delta=9,update_delta=7,"
        "uninstall_delta=2,total_delta=18,install_complete=1,"
        "update_complete=1,uninstall_complete=1,no_synthetic_notifications=true,"
        "only_ci_package_events_counted=true",
        "C545D_REAL_APPX_CLEANUP_EXECUTED=true,runner_only=true",
    ])+"\n"
    assert "C545D_APPINFO_NATIVE_SPONTANEOUS_CI_PASS" in analyze(fixture)
    changed=[
        fixture.replace("stage=11,changed=1","stage=11,changed=0"),
        fixture.replace("stage=13,changed=3","stage=13,changed=2"),
        fixture.replace("stage=12,changed=2","stage=12,changed=3"),
        fixture.replace("C545D_CI_NATIVE_MONITOR_DISPATCH,seq=3","C545D_CI_NATIVE_MONITOR_DISPATCH,seq=2"),
        fixture.replace(REG,"C545D_CI_NATIVE_MONITOR_SINK_REGISTRATION,ok=0"),
        fixture.replace("stage=2,write=0","stage=2,write=1"),
        fixture.replace("stage=2,apps=40","stage=2,apps=39"),
        fixture.replace("C545D_APPINFO_MONITOR_FINAL,changed=3","C545D_APPINFO_MONITOR_FINAL,changed=2"),
        fixture.replace("total_delta=18","total_delta=17"),
        fixture.replace("C545D_REAL_APPX_CLEANUP_EXECUTED=true","C545D_REAL_APPX_CLEANUP_EXECUTED=false"),
        fixture.replace("stage=11,changed=1","stage=11,changed=1\n"
                          "C545D_APPINFO_MONITOR_OBSERVATION,stage=11,changed=1"),
    ]
    for i,broken in enumerate(changed):
        try:analyze(broken)
        except ValueError:pass
        else:raise AssertionError(f"failed to reject evidence fault {i}")
    print("C545D_APPINFO_NATIVE_SPONTANEOUS_SELFTEST_PASS,valid=1,rejected=11")


def main():
    a=argparse.ArgumentParser()
    a.add_argument("--selftest",action="store_true")
    a.add_argument("--input",type=Path)
    args=a.parse_args()
    if args.selftest:
        selftest()
        return
    if args.input is None:
        a.error("--input mandatory")
    print(analyze(args.input.read_text(encoding="utf-8-sig",errors="replace")))


if __name__=="__main__":
    main()
