#!/usr/bin/env python3
"""CI ONLY: forward native completed PackageCatalog events to GAppInfoMonitor.

Must run AFTER the GLib 2.82.4 dedicated WinRT bridge integration, lazy
rescan and optional completed-worker monitor patches.
- Native WinRT OS callback NEVER calls GLib.
- The same dedicated WinRT MTA owner thread calls our GIO sink only AFTER it
  is woken by an IsComplete event and is outside any native mutex.
- GIO sends a context-specific changed signal; public GAppInfo API on the
  awakened consumer still performs lazy coherent package-epoch rebuild.
- Closing the watch explicitly unregisters the sink, waits for any in-flight
  callback, revokes COM events and joins the MTA worker before leave.
- No timer, new threads, forced handles or recorder code alterations.
"""
from pathlib import Path
import sys


def once(s,old,new,reason):
    count=s.count(old)
    if count!=1:
        raise ValueError(f"{reason}: {count} matching GLib source anchors")
    return s.replace(old,new,1)


def patch_appinfo(s):
    needle="static GMutex gio_win32_appinfo_mutex;"
    return once(s,needle,
"""/* CI ONLY: runs on native watch MTA owner thread *outside* the COM
 * package-event callback and without watcher/GIO locks held. The monitor
 * infrastructure marshals changed into each thread-default main context.
 * The actual graph is rebuilt by the next public GAppInfo query.
 */
static gint c545d_ci_native_monitor_dispatches;
void __cdecl
c545d_ci_spontaneous_monitor_sink (void *ignored)
{
  (void) ignored;
  gint event_no = g_atomic_int_add (&c545d_ci_native_monitor_dispatches, 1) + 1;
  g_print ("C545D_CI_NATIVE_MONITOR_DISPATCH,seq=%d\\n", event_no);
  g_app_info_monitor_fire ();
}

"""+needle,"public GIO monitor sink")


def patch_parser(s):
    s=once(s,"static C545DWatch *c545d_bridge_watch;",
"""typedef int (__cdecl *C545DMonitorSinkRegister) (C545DWatch *,
                                                    void (__cdecl *)(void *),
                                                    void *);
void __cdecl c545d_ci_spontaneous_monitor_sink (void *unused);
static C545DMonitorSinkRegister c545d_bridge_set_monitor_sink;
static C545DWatch *c545d_bridge_watch;""","GIO parser C ABI sink symbol")
    before="""  if (c545d_bridge_watch != NULL)
    c545d_bridge_close (c545d_bridge_watch);
  fprintf (stderr, "C545D_GIO_EXIT_STAGE=after_watch_close\\n"); fflush (stderr);
  c545d_bridge_watch = NULL;"""
    after="""  if (c545d_bridge_watch != NULL)
    {
      /* Strict teardown: detach and wait for in-flight notification before
       * watcher revocation/join and MTA runtime leave. No native callback can
       * call into GIO after this step returns.
       */
      if (c545d_bridge_set_monitor_sink != NULL)
        c545d_bridge_set_monitor_sink (c545d_bridge_watch, NULL, NULL);
      c545d_bridge_close (c545d_bridge_watch);
    }
  fprintf (stderr, "C545D_GIO_EXIT_STAGE=after_watch_close\\n"); fflush (stderr);
  c545d_bridge_watch = NULL;"""
    s=once(s,before,after,"process-exit watcher teardown")
    before="""  return TRUE;
failed:
  if (c545d_bridge_module != NULL)"""
    after="""  if (g_getenv ("C545D_DIAG_APPINFO_MONITOR_UNSOLICITED") != NULL)
    {
      c545d_bridge_set_monitor_sink = (void *)
          GetProcAddress (c545d_bridge_module,
                          "c545d_dedicated_ci_set_monitor_sink");
      if (c545d_bridge_set_monitor_sink == NULL ||
          c545d_bridge_set_monitor_sink (
              c545d_bridge_watch, c545d_ci_spontaneous_monitor_sink, NULL) != 0)
        {
          g_print ("C545D_CI_NATIVE_MONITOR_SINK_REGISTRATION,ok=0\\n");
          /* Fail closed: do not claim notification support on this watcher. */
          return FALSE;
        }
      g_print ("C545D_CI_NATIVE_MONITOR_SINK_REGISTRATION,ok=1\\n");
    }
  return TRUE;
failed:
  if (c545d_bridge_module != NULL)"""
    s=once(s,before,after,"register native notify sink after atexit setup")
    return s


def rewrite(p,fn):
    raw=p.read_bytes()
    newline="\r\n" if b"\r\n" in raw else "\n"
    s=raw.decode("utf-8").replace("\r\n","\n")
    out=fn(s)
    p.write_bytes(out.replace("\n",newline).encode("utf-8"))


def main():
    if len(sys.argv)!=3:
        raise SystemExit("usage: spontaneous_glib.py <gwin32appinfo.c> <gwin32packageparser.c>")
    rewrite(Path(sys.argv[1]),patch_appinfo)
    rewrite(Path(sys.argv[2]),patch_parser)
    print("C545D_GIO_NATIVE_MONITOR_BRIDGE_CI_ONLY,"
          "COM_callback_calls_GIO=0,thread_safe_signal=1,"
          "native_event_coalesced_by_GIO_monitor=1,shutdown_unregister_and_join=1")


if __name__=="__main__":
    main()
