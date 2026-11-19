#!/usr/bin/env python3
"""CI-only: same genuine GLib 2.82.4 cache integration probes, with a dedicated
C++/WinRT MTA worker instead of an apartment owned by the GIO caller.
No production GIO DLL or real package mutation. Actual OS events untested.
"""
import sys
from pathlib import Path
import patch_glib_uwp_bridge_integration_diagnostic as original

def replace_once(data, before, after, label):
    if data.count(before)!=1:
        raise ValueError(f"{label}: expected 1 occurrence, saw {data.count(before)}")
    return data.replace(before, after, 1)

def main():
    if len(sys.argv)!=2: raise SystemExit("Usage: dedicated.py <GLib source>")
    s=original.BRIDGE
    s=replace_once(s,
      " * Caller thread is pinned to its first watch owner; foreign threads fail\n"
      " * closed and ALWAYS call the original WinRT DisplayName getter.",
      " * A dedicated MTA worker owns the WinRT catalog and revocation; arbitrary\n"
      " * GIO callers only poll numeric atomic generation and language values.",
      "thread ownership semantics")
    s=replace_once(s, "typedef struct c545d_winrt_watch C545DWatch;",
      "typedef struct c545d_dedicated_watch C545DWatch;", "C ABI type")
    for old,new in (
        ("c545d_thread_enter","c545d_dedicated_runtime_enter"),
        ("c545d_thread_leave","c545d_dedicated_runtime_leave"),
        ("c545d_watch_open","c545d_dedicated_open"),
        ("c545d_watch_close","c545d_dedicated_close"),
        ("c545d_watch_snapshot","c545d_dedicated_snapshot"),
        ("c545d_watch_inject_synthetic","c545d_dedicated_synthetic_event"),
    ):
        s=replace_once(s,f'"{old}"',f'"{new}"',"C ABI symbol "+old)
    s=replace_once(s, "static DWORD c545d_bridge_owner;\n","", "old owner-thread variable")
    s=replace_once(s, "  c545d_bridge_owner = GetCurrentThreadId ();\n","",
                   "old owner-thread binding")
    s=replace_once(s,
       "  if (!c545d_bridge_ready || c545d_bridge_owner != GetCurrentThreadId () ||\n"
       "      c545d_bridge_snapshot_func (c545d_bridge_watch, &generation, &locale) != 0)",
       "  if (!c545d_bridge_ready ||\n"
       "      c545d_bridge_snapshot_func (c545d_bridge_watch, &generation, &locale) != 0)",
       "thread-independent read")
    original.BRIDGE=s
    original.main(Path(sys.argv[1]))
    print("C545D_GLIB_DEDICATED_MTA_WATCH_CI_ONLY_PATCHED")

if __name__=="__main__":
    main()
