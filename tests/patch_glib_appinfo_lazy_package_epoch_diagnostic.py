#!/usr/bin/env python3
"""CI ONLY: make an actual PackageCatalog generation change request a GLib
AppInfo rebuild when a caller next queries GAppInfo (lazy, no background poll).

Applied AFTER exact GLib 2.82.4 weak-ref/UTF16 and dedicated MTA epoch patches.
This is NOT a product patch: no monitor signal without a caller query, and
watcher-unavailable fallback & general Win10 lifecycle remain unqualified.\nThis single-flight prototype serializes concurrent GAppInfo caller work.
"""
from pathlib import Path
import sys


def replace_exact(src: str, old: str, new: str, label: str) -> str:
    n = src.count(old)
    if n != 1:
        raise ValueError(f"{label}: expected exact one source match, got {n}")
    return src.replace(old, new, 1)


def edit(path: Path, transform) -> None:
    original = path.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    src = original.decode("utf-8").replace("\r\n", "\n")
    amended = transform(src)
    if amended == src:
        raise ValueError("no source change made")
    path.write_bytes(amended.replace("\n", newline).encode("utf-8"))


def patch_parser(src: str) -> str:
    src = replace_exact(
        src, "static guint64 c545d_bridge_generation, c545d_bridge_locale;",
        "static guint64 c545d_bridge_generation, c545d_bridge_locale;\n"
        "/* Last package generation for which GIO's AppInfo parse was queued. */\n"
        "static guint64 c545d_ci_last_parsed_package_generation;",
        "last parsed generation state")
    src = replace_exact(
        src, "  c545d_bridge_scans++;\n",
        "  /* The AppInfo worker is now scanning the current package catalog. */\n"
        "  g_mutex_lock (&c545d_bridge_lock);\n"
        "  c545d_ci_last_parsed_package_generation = c545d_bridge_generation;\n"
        "  g_mutex_unlock (&c545d_bridge_lock);\n"
        "  c545d_bridge_scans++;\n",
        "mark current parse generation")
    helper = r"""/* DIAGNOSTIC ONLY: do not change the calling thread's UI-language epoch.
 * The dedicated MTA watcher already owns the package generation counter;
 * this read-only bridge snapshot is used ONLY to request a GLib rebuild.
 * It does NOT populate/return a DisplayName cache entry on this caller.
 */
/* GCC -Wmissing-prototypes: internal cross-object declaration first. */
gboolean c545d_ci_package_generation_needs_rescan (void);

gboolean
c545d_ci_package_generation_needs_rescan (void)
{
  gboolean changed = FALSE;
  guint64 generation = 0, ignored_locale = 0;

  if (!c545d_bridge_mode ())
    return FALSE;
  g_mutex_lock (&c545d_bridge_lock);
  if (c545d_bridge_ready && c545d_bridge_watch != NULL &&
      c545d_bridge_snapshot_func != NULL &&
      c545d_ci_last_parsed_package_generation != 0 &&
      c545d_bridge_snapshot_func (c545d_bridge_watch, &generation,
                                  &ignored_locale) == 0)
    changed = generation != c545d_ci_last_parsed_package_generation;
  g_mutex_unlock (&c545d_bridge_lock);
  return changed;
}

"""
    return replace_exact(
        src, "gboolean\ng_win32_package_parser_enum_packages",
        helper + "gboolean\ng_win32_package_parser_enum_packages",
        "insert generation-only query before real package parser")


def patch_appinfo(src: str) -> str:
    src = replace_exact(
        src, "void\ngio_win32_appinfo_init (gboolean do_wait)\n{",
        "/* CI-only forward declaration for same-DLL package epoch helper. */\n"
        "gboolean c545d_ci_package_generation_needs_rescan (void);\n\n"
        "void\ngio_win32_appinfo_init (gboolean do_wait)\n{",
        "declare one-way epoch query")
    src = replace_exact(
        src,
        "static GMutex gio_win32_appinfo_mutex;",
        "static GMutex gio_win32_appinfo_mutex;\n"
        "/* CI ONLY: single-flight generation check across GAppInfo callers.\n"
        " * Never acquired by the AppInfo worker; do not hold parser bridge\n"
        " * locks when entering this mutex.\n"
        " */\n"
        "static GMutex c545d_ci_lazy_singleflight_lock;\n"
        "static guint c545d_ci_lazy_scheduled_count;",
        "single-flight gate")
    tail = """      g_mutex_unlock (&gio_win32_appinfo_mutex);
    }
}


static void g_win32_app_info_iface_init"""
    guarded = """      g_mutex_unlock (&gio_win32_appinfo_mutex);
    }

  /* DIAGNOSTIC ONLY: package install/remove may not mutate the registry
   * keys watched by stock GLib. When a GAppInfo caller asks for the data,
   * request one normal AppInfo worker rebuild if PackageCatalog generation
   * advanced. Do NOT poll a background timer, run WinRT on the caller, or
   * rebuild the graph synchronously on an arbitrary application thread.
   * The regular mutex/condition path below preserves API wait semantics.
   */
  if (g_getenv ("C545D_DIAG_UWP_LAZY_PACKAGE_RESCAN") != NULL)
    {
      /* Serialize *check + queue + worker completion*. Multiple readers
       * otherwise observe the same unparsed generation and enqueue many
       * identical graph rebuilds. Keep native bridge lock outside the
       * AppInfo mutex to avoid inversion with worker/parser callbacks.
       * This gate is not entered by the AppInfo worker.
       */
      g_mutex_lock (&c545d_ci_lazy_singleflight_lock);
      if (c545d_ci_package_generation_needs_rescan ())
        {
          g_atomic_int_inc (&gio_win32_appinfo_update_counter);
          c545d_ci_lazy_scheduled_count++;
          g_print ("C545D_CI_LAZY_RESCAN_QUEUED,seq=%u\\n",
                   c545d_ci_lazy_scheduled_count);
          g_thread_pool_push (gio_win32_appinfo_threadpool,
                              (gpointer) keys_updated, NULL);
          g_mutex_lock (&gio_win32_appinfo_mutex);
          while (g_atomic_int_get (&gio_win32_appinfo_update_counter) > 0)
            g_cond_wait (&gio_win32_appinfo_cond, &gio_win32_appinfo_mutex);
          g_mutex_unlock (&gio_win32_appinfo_mutex);
        }
      g_mutex_unlock (&c545d_ci_lazy_singleflight_lock);
    }
}


static void g_win32_app_info_iface_init"""
    return replace_exact(src, tail, guarded, "call-site generation gate")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: lazy_epoch.py <gwin32appinfo.c> <gwin32packageparser.c>")
    edit(Path(sys.argv[1]), patch_appinfo)
    edit(Path(sys.argv[2]), patch_parser)
    print("C545D_GLIB_CI_ONLY_LAZY_PACKAGE_GENERATION_RESCAN_PATCHED")


if __name__ == "__main__":
    main()
