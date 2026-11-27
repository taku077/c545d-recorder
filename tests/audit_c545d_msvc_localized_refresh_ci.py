#!/usr/bin/env python3
"""Reuse historical localized-value gate on exact native MSVC Combo build.
Only fixed numeric conclusions are emitted; never print raw package log.
"""
import argparse
from pathlib import Path
import re

ANCHOR = "  if (ci_monitor != NULL) return -40;"
INSERT = r"""  {
    wchar_t expected[32768], actual[32768];
    HMODULE gio = GetModuleHandleW(L"gio-2.0-0.dll");
    DWORD n = GetEnvironmentVariableW(L"C545D_EXPECTED_GIO_DLL", expected, 32768);
    DWORD m = gio ? GetModuleFileNameW(gio, actual, 32768) : 0;
    int match = n > 0 && n < 32768 && m > 0 && m < 32768 &&
                _wcsicmp(expected, actual) == 0;
    printf("C545D_MSVC_LOCALIZED_DLL_PATH,match=%d\n", match);
    fflush(stdout);
    if (!match) return -44;
  }
"""
def patch(src):
    if src.count(ANCHOR)!=1 or "C545D_MSVC_LOCALIZED_DLL_PATH" in src:
        raise ValueError("scanner_anchor")
    return src.replace(ANCHOR,INSERT+ANCHOR,1)

def audit(raw):
    # The older workflow used the same NUL/CR removal for mixed console output.
    text=raw.replace(b"\x00",b"").replace(b"\r",b"").decode("utf-8",errors="replace")
    if re.findall(r"^C545D_MSVC_LOCALIZED_DLL_PATH,match=([01])$",text,re.M)!=["1"]:
        raise ValueError("loaded_path")
    rows=re.findall(r'^C545D_RESOURCE_GIO_PREQUERY,stage=(main_add|resource_add|resource_remove),changed=(\d+),CI_only=1$',text,re.M)
    assert len(rows)==3,('wrong number of actual resource-only monitor observations',rows)
    counts=dict((name,int(n)) for name,n in rows)
    print("C545D_REAL_RESOURCE_GIO_PREQUERY_OBSERVED,main=%d,resource_add=%d,resource_remove=%d,CI_only=1"%(counts["main_add"],counts["resource_add"],counts["resource_remove"]))
    assert [counts[n] for n in ("main_add","resource_add","resource_remove")]==[1,2,3],('real resource PackageCatalog events did not trigger exactly one unsolicited changed signal each',counts)
    assert re.search(r'C545D_RESOURCE_OS_ADD_OBSERVATION,parent_fullname_unchanged=1,resource_installed=1,native_generation_delta=\d+,genuine_status_callbacks_delta=0,install_terminal_delta=1,update_terminal_delta=0,uninstall_terminal_delta=0,synthetic_events=0,CI_only=1',text),'resource install OS provenance missing'
    assert re.search(r'C545D_RESOURCE_OS_REMOVE_OBSERVATION,parent_fullname_unchanged=1,native_generation_delta=\d+,genuine_status_callbacks_delta=0,install_terminal_delta=0,update_terminal_delta=0,uninstall_terminal_delta=1,synthetic_events=0,CI_only=1',text),'resource remove OS provenance missing'
    display=re.findall(r'^C545D_RESOURCE_NAME_REVERSE,phase=(main_add|resource_add|resource_remove),expected=([01]),english=([01]),french=([01]),actual_nonempty=([01]),user_en=1,CI_only=1$',text,re.M)
    assert display==[('main_add','1','0','1','1'),('resource_add','1','1','0','1'),('resource_remove','1','0','1','1')],('Native original WinRT getter value regression',display)
    gio=re.findall(r'^C545D_GIO_RESOURCE_DISPLAY,stage=([123]),fresh=([01]),english=(\d+),french=(\d+),reverse=1,CI_only=1$',text,re.M)
    assert gio==[('1','1','0','1'),('2','1','1','0'),('3','1','0','1')],('Public GAppInfo DisplayName stale, missing, or duplicated',gio)
    assert re.search(r'^C545D_RESOURCE_CI_CLEANUP_EXECUTED=1,runner_only=1$',text,re.M),'real fixture/certificate cleanup marker missing'
    print('C545D_GIO_SAME_FULLNAME_LOCALIZED_DISPLAY_PASS,main_fr=1,resource_en=1,remove_fr=1,prequery_monitor_1_2_3=1,real_OS_events_only=1,release_approved=0')
    print('C545D_REAL_RESOURCE_GIO_PREQUERY_PASS,main=1,resource_add=2,resource_remove=3,no_registry_stimulus=1,real_OS_events_only=1,CI_only=1')
    print("C545D_MSVC_LOCALIZED_REFRESH_PASS,loaded_path=1,real_OS_events_only=1,release_approved=0")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--patch",type=Path)
    p.add_argument("--input",type=Path)
    a=p.parse_args()
    if a.patch:
        if a.patch.name!="c545d_msvc_localized_scan.c":
            raise SystemExit("refusing_non_disposable_source")
        raw=a.patch.read_bytes()
        nl="\r\n" if b"\r\n" in raw else "\n"
        a.patch.write_bytes(patch(raw.decode("utf-8").replace("\r\n","\n")).replace("\n",nl).encode("utf-8"))
    elif a.input:
        try:
            if a.input.stat().st_size>16_000_000: raise ValueError("log_size")
            audit(a.input.read_bytes())
        except (AssertionError,ValueError,KeyError,OSError):
            raise SystemExit("C545D_MSVC_LOCALIZED_REFRESH_GAP,actual_qualified=0") from None
    else: p.error("mode required")

if __name__=="__main__":
    main()
