#!/usr/bin/env python3
"""Assert real signed MSIX v2 app title refresh at UNCHANGED AppInfo list count.
All package names in helper are static throwaway CI fixture strings; artifacts
contain numeric counts only. No host registry write or personal apps listed.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path
from analyze_gio_native_spontaneous_msix import analyze

RECORD=re.compile(r"(?m)^C545D_GIO_FIXTURE_DISPLAY_VERSION,stage=(\d+),fresh=(\d+),"
                  r"old_count=(\d+),new_count=(\d+),CI_only=1\s*$")
PASS=re.compile(r"(?m)^C545D_GIO_FIXTURE_DISPLAY_VERSION_PASS,stage=(\d+),fresh=1\s*$")
EXPECTED=((1,1,1,0),(2,1,0,1),(3,1,0,0))


def classify(raw):
    if "C545D_APPINFO_NATIVE_SPONTANEOUS_CI_PASS" not in analyze(raw):
        raise ValueError("real notification comparator not complete")
    rows=tuple(tuple(map(int,row)) for row in RECORD.findall(raw))
    if rows!=EXPECTED:
        raise ValueError(f"versioned DisplayName not fresh or absent: {rows}")
    passed=tuple(int(x) for x in PASS.findall(raw))
    if passed!=(1,2,3):
        raise ValueError(f"missing duplicate or unordered version assertions: {passed}")
    if raw.count("C545D_GIO_VERSIONED_FIXTURE_DISPLAY_STALE") != 0:
        raise ValueError("stale display warning")
    return ("C545D_REAL_MSIX_VERSIONED_DISPLAYNAME_PASS,"
            "installed_v1_old=1,updated_v2_new=1,same_app_count=1,"
            "uninstall_both_absent=1,native_notifications_pre_query=1;2;3,"
            "no_user_registry=1,safe_fixture_only=1,Win10_unverified=1")


def selftest():
    base="\n".join([
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=0,apps=39",
        "C545D_APPINFO_MONITOR_STARTED,context_ready=1",
        "C545D_CI_NATIVE_MONITOR_SINK_REGISTRATION,ok=1",
        *sum(([f"C545D_CI_NATIVE_MONITOR_DISPATCH,seq={i}",
              f"C545D_APPINFO_MONITOR_OBSERVATION,stage={10+i},changed={i}",
              f"C545D_GIO_REAL_MSIX_NATURAL_STAGE,stage={i},apps={40 if i<3 else 39}",
              f"C545D_APPINFO_MONITOR_OBSERVATION,stage={20+i},changed={i}",
              f"C545D_GIO_NO_CI_REGISTRY_STIMULUS,stage={i},write=0"] for i in (1,2,3)),[]),
        "C545D_APPINFO_MONITOR_FINAL,changed=3,clean_stop=1",
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=4,apps=39",
        "C545D_REAL_PACKAGECATALOG_EVENT_PASS,install_delta=9,update_delta=7,"
        "uninstall_delta=2,total_delta=18,install_complete=1,"
        "update_complete=1,uninstall_complete=1,no_synthetic_notifications=true,"
        "only_ci_package_events_counted=true",
        "C545D_REAL_APPX_CLEANUP_EXECUTED=true,runner_only=true",
        *[f"C545D_GIO_FIXTURE_DISPLAY_VERSION,stage={s},fresh={f},old_count={o},"
          f"new_count={n},CI_only=1" for s,f,o,n in EXPECTED],
        *[f"C545D_GIO_FIXTURE_DISPLAY_VERSION_PASS,stage={i},fresh=1" for i in (1,2,3)]
    ])+"\n"
    assert "C545D_REAL_MSIX_VERSIONED_DISPLAYNAME_PASS" in classify(base)
    bad=[
        base.replace("stage=2,fresh=1,old_count=0,new_count=1",
                     "stage=2,fresh=1,old_count=1,new_count=0"),
        base.replace("stage=3,fresh=1,old_count=0,new_count=0",
                     "stage=3,fresh=1,old_count=0,new_count=1"),
        base.replace("VERSION_PASS,stage=2,fresh=1","VERSION_PASS,stage=1,fresh=1"),
        base.replace("stage=11,changed=1","stage=11,changed=0"),
        base.replace("total_delta=18","total_delta=17")
    ]
    for i,raw in enumerate(bad):
        try:classify(raw)
        except ValueError:pass
        else:raise AssertionError(f"accepted stale title or false real event {i}")
    print("C545D_REAL_MSIX_VERSIONED_ANALYZER_SELFTEST_PASS,valid=1,rejected=5")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--input",type=Path)
    a=p.parse_args()
    if a.selftest:
        selftest()
        return
    if a.input is None:
        p.error("--input required")
    print(classify(a.input.read_text(encoding="utf-8-sig",errors="replace")))


if __name__=="__main__":
    main()
