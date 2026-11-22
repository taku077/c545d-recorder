#!/usr/bin/env python3
"""CI-only QPC bracket for AppInfo rebuild worker at Xperf stop.

Apply to DISPOSABLE Windows GIO/probe sources only, after the established
AppInfo phase trace and ETW fence overlays. These markers bound the ETW stop;
they do not prove WinRT/APC global quiescence or allocation lifetime.
"""
from __future__ import annotations

import argparse
from pathlib import Path

TRACE_ORIGINAL = r'''  if (g_getenv ("C545D_CI_APPINFO_PHASE_TRACE") != NULL)
    g_print ("C545D_CI_APPINFO_TRACE,phase=%s,ordinal=%d,tick_ms=%llu\n",
             phase, ordinal, (unsigned long long) GetTickCount64 ());
'''
TRACE_REPLACEMENT = r'''  if (g_getenv ("C545D_CI_APPINFO_PHASE_TRACE") != NULL)
    {
      LARGE_INTEGER c545d_qpc;
      if (QueryPerformanceCounter (&c545d_qpc))
        g_print ("C545D_CI_APPINFO_QPC,phase=%s,ordinal=%d,qpc=%lld\n",
                 phase, ordinal, (long long) c545d_qpc.QuadPart);
      g_print ("C545D_CI_APPINFO_TRACE,phase=%s,ordinal=%d,tick_ms=%llu\n",
               phase, ordinal, (unsigned long long) GetTickCount64 ());
    }
'''
APPINFO_TAIL = '''}\n\n/* Initializes Windows AppInfo.'''
APPINFO_TAIL_NEW = '''  /* CI-only: this scan has passed monitor notification dispatch.
   * It is NOT proof of a globally drained WinRT/APC queue.
   */
  if (saved_counter > 0 &&
      g_getenv ("C545D_CI_APPINFO_PHASE_TRACE") != NULL)
    {
      LARGE_INTEGER c545d_qpc;
      if (QueryPerformanceCounter (&c545d_qpc))
        g_print ("C545D_CI_APPINFO_QPC,phase=worker_after_notify,ordinal=%d,qpc=%lld\\n",
                 g_atomic_int_get (&c545d_ci_trace_active_worker),
                 (long long) c545d_qpc.QuadPart);
    }
}\n\n/* Initializes Windows AppInfo.'''
PROBE_BEFORE = '''    handle = CreateFileW(marker, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                         CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);'''
PROBE_BEFORE_NEW = '''    /* Captured before precleanup_ready.signal exists: stop cannot have
     * begun because the controller has not observed this signal yet.
     */
    if (wcscmp(ready, L"precleanup_ready.signal") == 0) {
        LARGE_INTEGER now;
        if (!QueryPerformanceCounter(&now)) return 0;
        printf("C545D_CI_ETW_FENCE_QPC,phase=precleanup_ready_before,qpc=%lld\\n",
               (long long)now.QuadPart);
        fflush(stdout);
    }
    handle = CreateFileW(marker, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                         CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);'''
PROBE_AFTER = '''        if (attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY))
            return 1;'''
PROBE_AFTER_NEW = '''        if (attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY)) {
            /* trace_stopped.signal is created only AFTER xperf stop+merge.
             * This marker is therefore strictly after the ETW stop.
             */
            if (wcscmp(released, L"trace_stopped.signal") == 0) {
                LARGE_INTEGER now;
                if (!QueryPerformanceCounter(&now)) return 0;
                printf("C545D_CI_ETW_FENCE_QPC,phase=trace_stopped_ack,qpc=%lld\\n",
                       (long long)now.QuadPart);
                fflush(stdout);
            }
            return 1;
        }'''


def once(src: str, original: str, replacement: str, label: str) -> str:
    if src.count(original) != 1:
        raise ValueError(f"{label}: expected exact unique source anchor; found {src.count(original)}")
    return src.replace(original, replacement, 1)


def appinfo(src: str) -> str:
    if "C545D_CI_APPINFO_QPC" in src:
        raise ValueError("qpc_trace_already_applied")
    if "/* Notify from the completed AppInfo worker," not in src:
        raise ValueError("monitor_worker_overlay_missing")
    src = once(src, TRACE_ORIGINAL, TRACE_REPLACEMENT, "worker_qpc_trace")
    return once(src, APPINFO_TAIL, APPINFO_TAIL_NEW, "worker_after_notify")


def probe(src: str) -> str:
    if "C545D_CI_ETW_FENCE_QPC" in src:
        raise ValueError("qpc_fence_already_applied")
    if 'L"precleanup_ready.signal", L"trace_stopped.signal"' not in src:
        raise ValueError("etw_precleanup_fence_missing")
    src = once(src, PROBE_BEFORE, PROBE_BEFORE_NEW, "qpc_pre_signal")
    return once(src, PROBE_AFTER, PROBE_AFTER_NEW, "qpc_post_stop")


def selftest() -> None:
    app = ('''/* Notify from the completed AppInfo worker, */\n'''
           '''static void c545d_ci_appinfo_trace (const gchar *phase, gint ordinal)\n{\n'''
           + TRACE_ORIGINAL + '''}\n'''
           '''static void gio_win32_appinfo_thread_func (void) {\n'''
           '''  gint saved_counter = 1;\n'''
           '''  g_mutex_unlock (&gio_win32_appinfo_mutex);\n'''
           '''}\n\n/* Initializes Windows AppInfo. */\n''')
    fence = ('''int c545d_ci_etw_phase_fence(void) {\n'''
             '''    if (!c545d_ci_etw_phase_fence(L"precleanup_ready.signal", L"trace_stopped.signal")) return 9;\n'''
             + PROBE_BEFORE + '\n' + PROBE_AFTER + '\n}\n')
    patched_app, patched_probe = appinfo(app), probe(fence)
    assert "worker_after_notify" in patched_app
    assert "precleanup_ready_before" in patched_probe
    assert "trace_stopped_ack" in patched_probe
    assert patched_app.count("C545D_CI_APPINFO_QPC") == 2  # regular phase + post-notify
    assert r'worker_after_notify,ordinal=%d,qpc=%lld\n"' in patched_app  # C escaped LF
    assert patched_probe.count("C545D_CI_ETW_FENCE_QPC") == 2
    negatives = 0
    cases = [
        (appinfo, app.replace(TRACE_ORIGINAL, ""), "missing trace"),
        (appinfo, app.replace(APPINFO_TAIL, ""), "missing worker tail"),
        (appinfo, app.replace("/* Notify from the completed AppInfo worker,", "MISSING"), "missing monitor overlay"),
        (appinfo, patched_app, "double patch"),
        (appinfo, app.replace(TRACE_ORIGINAL, TRACE_ORIGINAL * 2), "ambiguous trace"),
        (probe, fence.replace(PROBE_BEFORE, ""), "missing ready anchor"),
        (probe, fence.replace(PROBE_AFTER, ""), "missing stop anchor"),
        (probe, fence.replace('L"precleanup_ready.signal", L"trace_stopped.signal"', "WRONG"), "missing fence"),
        (probe, patched_probe, "double patch"),
        (probe, fence.replace(PROBE_BEFORE, PROBE_BEFORE * 2), "ambiguous ready"),
    ]
    for f, sample, why in cases:
        try:
            f(sample)
        except ValueError:
            negatives += 1
        else:
            raise AssertionError(f"invalid QPC overlay accepted: {why}")
    assert negatives == 10
    print("C545D_GIO_ETW_QPC_SOURCE_SELFTEST_PASS,positive=2,negative=10,"
          "qpc_same_pid=1,stop_bracket=1,global_quiet_proven=0,host_untouched=1")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--appinfo", type=Path)
    p.add_argument("--probe", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    if bool(args.appinfo) == bool(args.probe):
        p.error("supply exactly one of --appinfo or --probe")
    path = args.appinfo or args.probe
    if (args.appinfo and path.name != "gwin32appinfo.c") or (
            args.probe and path.name != "c545d_disposable_scanfree.c"):
        raise ValueError("refusing non-disposable source")
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    src = raw.decode("utf-8").replace("\r\n", "\n")
    out = appinfo(src) if args.appinfo else probe(src)
    path.write_bytes(out.replace("\n", newline).encode("utf-8"))
    print("C545D_GIO_ETW_QPC_SOURCE_PATCH_PASS,mode="
          + ("appinfo" if args.appinfo else "probe")
          + ",CI_only=1,host_untouched=1")


if __name__ == "__main__":
    main()
