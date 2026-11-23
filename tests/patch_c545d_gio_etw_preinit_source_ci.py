#!/usr/bin/env python3
"""Source-locked *initial* AppInfo ETW window: before FIRST public GIO call.

This is a source patch for an isolated disposable probe copy, never the host
recorder, registry hook or installed DLL. It deliberately captures only from
main-before-AppInfo, NOT CRT/loader startup before the process enters main.
Fail closed if old late4 or after-baseline fence was used instead.
"""
from __future__ import annotations
import argparse
from pathlib import Path

MAIN = "int main(int argc, char **argv)\n{"
PRE_INIT = "    monitor = g_app_info_monitor_get();\n"
PRE_CLEANUP = '    report_key_handles("before_cleanup", cycle_count);\n'
HELPER = r'''
/* CI-only initial AppInfo ETW fence; only the disposable probe uses this. */
static int c545d_initial_appinfo_etw_fence(const wchar_t *ready,
                                            const wchar_t *released)
{
    wchar_t root[MAX_PATH], marker[MAX_PATH], gate[MAX_PATH];
    DWORD n=GetEnvironmentVariableW(L"C545D_CI_ETW_PHASE_ROOT",root,MAX_PATH);
    HANDLE h;
    unsigned i;
    if(n==0 || n>=MAX_PATH) return 0; /* no silent fallback */
    if(_snwprintf_s(marker,MAX_PATH,_TRUNCATE,L"%ls\\%ls",root,ready)<=0 ||
       _snwprintf_s(gate,MAX_PATH,_TRUNCATE,L"%ls\\%ls",root,released)<=0)
        return 0;
    h=CreateFileW(marker,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_NEW,
                  FILE_ATTRIBUTE_NORMAL,NULL);
    if(h==INVALID_HANDLE_VALUE)return 0;
    CloseHandle(h);
    for(i=0;i<400;i++){
        DWORD a=GetFileAttributesW(gate);
        if(a!=INVALID_FILE_ATTRIBUTES && !(a&FILE_ATTRIBUTE_DIRECTORY))return 1;
        SleepEx(50,TRUE); /* APC delivery, NEVER an idle/close guarantee */
    }
    return 0;
}
'''

def patch(src: str)->str:
    for word in ("c545d_initial_appinfo_etw_fence", "late_window_ready.signal",
                 "baseline_ready.signal", "C545D_CI_ETW_PROBE_FENCE_PATCH_PASS"):
        if word in src:
            raise ValueError("existing_or_conflicting_old_etw_window")
    if any(src.count(anchor)!=1 for anchor in (MAIN,PRE_INIT,PRE_CLEANUP)):
        raise ValueError("missing_or_ambiguous_probe_window_anchor")
    if not(src.index(MAIN)<src.index(PRE_INIT)<src.index(PRE_CLEANUP)):
        raise ValueError("original_source_workload_order_wrong")
    start=src.index(MAIN)
    out=src[:start]+HELPER+"\n"+src[start:]
    out=out.replace(PRE_INIT,
        '    /* all GIO AppInfo initial work MUST follow the ETW armed acknowledgement */\n'
        '    if (!c545d_initial_appinfo_etw_fence(L"preinit_ready.signal",\n'
        '                                            L"trace_armed.signal")) return 8;\n'
        +PRE_INIT,1)
    out=out.replace(PRE_CLEANUP,PRE_CLEANUP+
        '    if (!c545d_initial_appinfo_etw_fence(L"precleanup_ready.signal",\n'
        '                                            L"trace_stopped.signal")) return 9;\n',1)
    if out.count("c545d_initial_appinfo_etw_fence(")!=3:
        raise ValueError("incorrect_etw_phase_gate_count")
    if not(out.index('L"preinit_ready.signal"') <
           out.index(PRE_INIT) <
           out.index(PRE_CLEANUP) <
           out.index('L"precleanup_ready.signal"')):
        raise ValueError("source_start_not_before_first_appinfo_call")
    return out

def selftest()->None:
    sample=(MAIN+"\n"
        "    HKEY hkey = NULL;\n    GAppInfoMonitor *monitor;\n"
        "    monitor = g_app_info_monitor_get();\n"
        "    enumerate_apps();\n"
        '    report_vm("baseline", 0);\n'
        '    report_key_handles("before_cleanup", cycle_count);\n'
        "    return 0;\n}\n")
    good=patch(sample)
    assert good.index('L"preinit_ready.signal"')<good.index(PRE_INIT)
    assert good.index('L"precleanup_ready.signal"')>good.index(PRE_CLEANUP)
    negatives=[
        sample.replace(PRE_INIT,"",1),
        sample.replace(PRE_CLEANUP,"",1),
        sample.replace(PRE_INIT,PRE_INIT+PRE_INIT,1),
        sample.replace(PRE_CLEANUP,PRE_CLEANUP+PRE_CLEANUP,1),
        sample.replace(MAIN,"int main(void)\n{",1),
        sample.replace(PRE_INIT,PRE_INIT).replace(PRE_CLEANUP,PRE_CLEANUP), # same original, reject after modified below
        good,
        sample.replace(MAIN,MAIN+'\n    /* old */ baseline_ready.signal;\n'),
        sample.replace(MAIN,MAIN+'\n    /* old */ late_window_ready.signal;\n'),
        sample.replace(PRE_CLEANUP,PRE_CLEANUP).replace(PRE_INIT,PRE_CLEANUP+PRE_INIT),
    ]
    negatives.pop(5) # valid input is not a negative
    for i,bad in enumerate(negatives):
        try:patch(bad)
        except ValueError:continue
        raise AssertionError(f"invalid_initial_appinfo_capture_accepted:{i}")
    print("C545D_APPINFO_PREINIT_ETW_FENCE_SELFTEST_PASS,positive=1,"
          "negative=9,start_before_first_appinfo=1,"
          "cannot_prove_before_process_main=1,global_idle_not_assumed=1,host_untouched=1")

def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("source",nargs="?",type=Path)
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:
        selftest()
        return
    if a.source is None:
        p.error("isolated probe source required")
    raw=a.source.read_bytes()
    ending="\r\n" if b"\r\n" in raw else "\n"
    updated=patch(raw.decode("utf-8").replace("\r\n","\n"))
    a.source.write_bytes(updated.replace("\n",ending).encode("utf-8"))
    print("C545D_APPINFO_PREINIT_ETW_FENCE_SOURCE_PASS,"
          "before_first_GIO_AppInfo_call=1,not_before_process_main=1,"
          "private_disposable_source_only=1,host_untouched=1")

if __name__=="__main__":
    main()
