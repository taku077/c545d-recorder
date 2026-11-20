#!/usr/bin/env python3
"""CI ONLY: deliver AppInfoMonitor::changed after ANY Win32 AppInfo worker rebuild.

This includes registry-driven rebuilds which can update app inventory without
the PR57 lazy package-generation query path. Do not deliver while holding
gio_win32_appinfo_mutex or the lazy single-flight lock. Skip startup build.
This still does NOT guarantee event-only PackageCatalog notifications without
an intervening watched registry change or public GAppInfo query.
"""
import sys
from pathlib import Path


def patch(source: str) -> str:
    anchor = """static void
gio_win32_appinfo_thread_func (gpointer data,
                               gpointer user_data)
{"""
    repl = """/* DIAGNOSTIC ONLY: the first AppInfo build occurs before the monitor
 * is acquired; its completion should not notify an existing monitor.
 */
static gint c545d_ci_appinfo_completed_builds;

static void
gio_win32_appinfo_thread_func (gpointer data,
                               gpointer user_data)
{"""
    if source.count(anchor) != 1:
        raise ValueError("Win32 AppInfo worker anchor missing or duplicate")
    source = source.replace(anchor,repl,1)
    anchor = """    g_cond_broadcast (&gio_win32_appinfo_cond);

  g_mutex_unlock (&gio_win32_appinfo_mutex);
}

/* Initializes Windows AppInfo."""
    repl = """    g_cond_broadcast (&gio_win32_appinfo_cond);

  g_mutex_unlock (&gio_win32_appinfo_mutex);
  /* Notify from the completed AppInfo worker, not from a GAppInfo
   * caller. We never call user handlers under the worker mutex.
   * g_app_info_monitor_fire() marshals to each monitor's main context.
   * Each existing worker scan may be triggered by a genuine Windows
   * registry watcher OR by the current package epoch lazy query.
   */
  if (saved_counter > 0 &&
      g_getenv ("C545D_DIAG_APPINFO_MONITOR_WORKER_FIRE") != NULL)
    {
      gint previously_completed =
        g_atomic_int_add (&c545d_ci_appinfo_completed_builds, 1);
      if (previously_completed > 0)
        {
          g_print ("C545D_CI_MONITOR_WORKER_FIRE,ordinal=%d\\n",
                   previously_completed);
          g_app_info_monitor_fire ();
        }
    }
}

/* Initializes Windows AppInfo."""
    if source.count(anchor) != 1:
        raise ValueError("Win32 AppInfo completion boundary missing or duplicate")
    return source.replace(anchor,repl,1)


def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: worker_monitor.py <glib/gio/gwin32appinfo.c>")
    p=Path(sys.argv[1])
    data=p.read_bytes()
    newline="\r\n" if b"\r\n" in data else "\n"
    src=data.decode("utf-8").replace("\r\n","\n")
    out=patch(src)
    p.write_bytes(out.replace("\n",newline).encode("utf-8"))
    print("C545D_APPINFO_MONITOR_WORKER_CI_ONLY,initial_build_suppressed=1,"
          "public_query_not_required_when_registry_watcher_triggers=1,"
          "spontaneous_PackageCatalog_only_NOT_proven=1")


if __name__=="__main__":
    main()
