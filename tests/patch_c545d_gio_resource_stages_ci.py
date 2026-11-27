#!/usr/bin/env python3
"""Disposable CI probe stage markers and loaded GIO path check, no raw paths."""
from pathlib import Path
import sys

MAIN = "int main(int argc, char **argv)\n{"
HELPER = r'''
static void c545d_stage(const char *stage, int index)
{
    printf("C545D_GIO_RESOURCE_STAGE,stage=%s,index=%d\n", stage, index);
    fflush(stdout);
}
static int c545d_verify_loaded_gio(void)
{
    wchar_t expected[32768], actual[32768];
    HMODULE module = GetModuleHandleW(L"gio-2.0-0.dll");
    DWORD n = GetEnvironmentVariableW(L"C545D_EXPECTED_GIO_DLL", expected, 32768);
    DWORD m = module ? GetModuleFileNameW(module, actual, 32768) : 0;
    int match = n > 0 && n < 32768 && m > 0 && m < 32768 &&
                _wcsicmp(expected, actual) == 0;
    printf("C545D_GIO_RESOURCE_DLL_PATH,match=%d\n", match);
    fflush(stdout);
    return match;
}
'''
def once(s, before, after):
    if s.count(before) != 1:
        raise ValueError("missing_or_duplicate_stage_anchor")
    return s.replace(before, after, 1)

def patch(s):
    if "c545d_verify_loaded_gio" in s:
        raise ValueError("already_patched")
    # Insert before main; all instrumented calls below are within main.
    s = once(s, MAIN, HELPER + MAIN +
        '\n    c545d_stage("main",0);\n    if (!c545d_verify_loaded_gio()) return 13;')
    s = once(s, "    monitor = g_app_info_monitor_get();",
        '    c545d_stage("monitor_begin",0);\n    monitor = g_app_info_monitor_get();\n'
        '    c545d_stage("monitor_end",0);')
    s = once(s, "    enumerate_apps();    /* Ensure registry watchers and AppInfo cache initialize. */",
        '    c545d_stage("enum_begin",0);\n'
        '    enumerate_apps();    /* Ensure registry watchers and AppInfo cache initialize. */\n'
        '    c545d_stage("enum_end",0);')
    s = once(s, '        drain_context();\n        enumerate_apps();',
        '        c545d_stage("drain_begin",i);\n        drain_context();\n'
        '        c545d_stage("drain_end",i);\n        c545d_stage("enum_begin",i);\n'
        '        enumerate_apps();\n        c545d_stage("enum_end",i);')
    for label, index, indent in (("baseline","0","    "),("cycle","i","            "),
                                  ("after_cleanup","cycle_count + 1","    "),
                                  ("settled_cleanup","cycle_count + 2","    ")):
        a = f'{indent}report_vm("{label}", {index});'
        s = once(s, a, f'{indent}c545d_stage("vm_begin",{index});\n'+a+
            f'\n{indent}c545d_stage("vm_end",{index});')
    s = once(s, '    Sleep(1200);\n    enumerate_apps();',
        '    Sleep(1200);\n    c545d_stage("enum_begin",cycle_count+1);\n'
        '    enumerate_apps();\n    c545d_stage("enum_end",cycle_count+1);')
    s = once(s, '    Sleep(2500);\n    drain_context();\n    enumerate_apps();',
        '    Sleep(2500);\n    c545d_stage("drain_begin",cycle_count+2);\n'
        '    drain_context();\n    c545d_stage("drain_end",cycle_count+2);\n'
        '    c545d_stage("enum_begin",cycle_count+2);\n'
        '    enumerate_apps();\n    c545d_stage("enum_end",cycle_count+2);')
    a = '    printf("GIO_PROBE_DONE,cycles=%d,notifications=%ld,reg_changes=%d\\n",'
    s = once(s, a, '    c545d_stage("main_done",cycle_count);\n'+a)
    return s

if __name__ == "__main__":
    p = Path(sys.argv[1])
    if p.name != "c545d_gio_preinit_probe.c":
        raise SystemExit("refusing_non_disposable_source")
    raw = p.read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    result = patch(raw.decode("utf-8").replace("\r\n","\n"))
    p.write_bytes(result.replace("\n",nl).encode("utf-8"))
    print("C545D_GIO_RESOURCE_STAGE_PATCH_PASS,loaded_path_check=1,raw_uploaded=0")
