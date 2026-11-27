#!/usr/bin/env python3
"""CI-only boundaries around list retrieval, unref and context drain."""
from pathlib import Path
import sys

ORIGINAL = """static void enumerate_apps(void)
{
    GList *apps = g_app_info_get_all();
    g_list_free_full(apps, g_object_unref);
    drain_context();
}
"""
REPLACEMENT = r"""static int c545d_enum_index;
static void c545d_enum_mark(const char *stage, int index)
{
    LARGE_INTEGER qpc;
    if (QueryPerformanceCounter(&qpc)) {
        printf("C545D_GIO_ENUM_SUBSTAGE,stage=%s,index=%d,qpc=%lld\n",
               stage,index,(long long)qpc.QuadPart);
        fflush(stdout);
    }
}
static void enumerate_apps(void)
{
    int index = c545d_enum_index++;
    GList *apps;
    c545d_enum_mark("get_begin",index);
    apps = g_app_info_get_all();
    c545d_enum_mark("get_end",index);
    c545d_enum_mark("free_begin",index);
    g_list_free_full(apps, g_object_unref);
    c545d_enum_mark("free_end",index);
    c545d_enum_mark("context_begin",index);
    drain_context();
    c545d_enum_mark("context_end",index);
}
"""
def patch(s):
    if s.count(ORIGINAL) != 1 or "c545d_enum_mark" in s:
        raise ValueError("missing_or_duplicate_enum_anchor")
    return s.replace(ORIGINAL, REPLACEMENT, 1)

def selftest():
    good = patch(ORIGINAL)
    assert good.count("c545d_enum_mark(") == 7
    for before, call, after in (("get_begin","apps = g_app_info_get_all();","get_end"),
        ("free_begin","g_list_free_full(apps, g_object_unref);","free_end"),
        ("context_begin","drain_context();","context_end")):
        assert good.index('"'+before+'"') < good.index(call) < good.index('"'+after+'"')
    for bad in ("", ORIGINAL*2, good):
        try:
            patch(bad)
        except ValueError:
            continue
        raise AssertionError("invalid_anchor_accepted")
    print("C545D_GIO_ENUM_SUBSTAGE_SELFTEST_PASS,positive=1,negative=3")

if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    else:
        p = Path(sys.argv[1])
        if p.name != "c545d_gio_preinit_probe.c":
            raise SystemExit("refusing_non_disposable_source")
        raw = p.read_bytes()
        nl = "\r\n" if b"\r\n" in raw else "\n"
        s = patch(raw.decode("utf-8").replace("\r\n","\n"))
        p.write_bytes(s.replace("\n",nl).encode("utf-8"))
        print("C545D_GIO_ENUM_SUBSTAGE_PATCH_PASS,CI_only=1")
