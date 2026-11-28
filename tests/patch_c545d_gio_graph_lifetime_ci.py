#!/usr/bin/env python3
"""CI-only numeric lifetime census of six Win32 AppInfo GObject classes.

No extra references, weak notifications, object allocation, or production ABI.
Count actual init/finalize (not dispose, which can run more than once).
Snapshots at the public get-all lock, before allocating returned wrappers.
Not a global heap census or proof of ownership of all memory.
Apply after Core weak-backref and other pinned overlays.
"""
import argparse
from pathlib import Path

TYPES = (
    ("g_win32_appinfo_url_schema", "GWin32AppInfoURLSchema", "self"),
    ("g_win32_appinfo_file_extension", "GWin32AppInfoFileExtension", "self"),
    ("g_win32_appinfo_shell_verb", "GWin32AppInfoShellVerb", "self"),
    ("g_win32_appinfo_handler", "GWin32AppInfoHandler", "self"),
    ("g_win32_appinfo_application", "GWin32AppInfoApplication", "self"),
    ("g_win32_app_info", "GWin32AppInfo", "local"),
)
def once(s, a, b):
    if s.count(a) != 1:
        raise ValueError("lifetime_anchor")
    return s.replace(a, b, 1)

def patch(s):
    if "c545d_graph_birth" in s:
        raise ValueError("already_patched")
    anchor = "static void\ng_win32_appinfo_url_schema_dispose (GObject *object)"
    helper = """/* CI only; bounded probe, no object ownership changes. */
static gint c545d_graph_birth[6], c545d_graph_final[6];
static gint c545d_graph_sample;

static void
c545d_graph_report (void)
{
  gint b[6], f[6], i;
  for (i = 0; i < 6; i++)
    {
      b[i] = g_atomic_int_get (&c545d_graph_birth[i]);
      f[i] = g_atomic_int_get (&c545d_graph_final[i]);
    }
  g_print ("C545D_GRAPH_LIFETIME,seq=%d,birth=%d:%d:%d:%d:%d:%d,final=%d:%d:%d:%d:%d:%d\\n",
           g_atomic_int_add (&c545d_graph_sample, 1) + 1,
           b[0], b[1], b[2], b[3], b[4], b[5],
           f[0], f[1], f[2], f[3], f[4], f[5]);
}

"""
    s = once(s, anchor, helper + anchor)
    for i, (name, typ, var) in enumerate(TYPES):
        init = f"static void\n{name}_init ({typ} *{var})\n{{"
        s = once(s, init, init+f"\n  g_atomic_int_inc (&c545d_graph_birth[{i}]);")
        chain = f"  G_OBJECT_CLASS ({name}_parent_class)->finalize (object);"
        if name in ("g_win32_appinfo_shell_verb", "g_win32_app_info"):
            # Preserve the existing actual weak-ref and wrapper finalizers.
            s = once(s, chain, f"  g_atomic_int_inc (&c545d_graph_final[{i}]);\n"+chain)
        else:
            mark = f"static void\n{name}_class_init ({typ}Class *klass)"
            fn = f"""static void
{name}_finalize (GObject *object)
{{
  g_atomic_int_inc (&c545d_graph_final[{i}]);
{chain}
}}

"""
            s = once(s, mark, fn + mark)
            dispose = f"  gobject_class->dispose = {name}_dispose;"
            s = once(s, dispose, dispose+f"\n  gobject_class->finalize = {name}_finalize;")
    begin = s.index("GList *\ng_app_info_get_all_impl (void)")
    end = s.index("GList *\ng_app_info_get_all_for_type_impl",begin)
    body = s[begin:end]
    lock = "  g_mutex_lock (&gio_win32_appinfo_mutex);"
    body = once(body, lock, lock + "\n  c545d_graph_report ();")
    s = s[:begin]+body+s[end:]
    return s

def main():
    p = argparse.ArgumentParser()
    p.add_argument("source",type=Path)
    a=p.parse_args()
    if a.source.name!="gwin32appinfo.c" or a.source.parent.name!="gio":
        raise ValueError("source_name")
    raw=a.source.read_bytes()
    nl="\r\n" if b"\r\n" in raw else "\n"
    s=patch(raw.decode("utf-8").replace("\r\n","\n"))
    for i in range(6):
        if s.count(f"g_atomic_int_inc (&c545d_graph_birth[{i}]);")!=1 or s.count(f"g_atomic_int_inc (&c545d_graph_final[{i}]);")!=1:
            raise ValueError("counter_coverage")
    a.source.write_bytes(s.replace("\n",nl).encode("utf-8"))
    print("C545D_GRAPH_LIFETIME_PATCH_PASS,types=6,extra_refs=0,actual_finalizers=1,raw_addresses=0")
if __name__=="__main__": main()
