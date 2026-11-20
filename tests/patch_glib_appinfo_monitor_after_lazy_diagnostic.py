#!/usr/bin/env python3
"""CI ONLY: emit GAppInfoMonitor::changed following a lazy PackageCatalog
generation-triggered rescan, never while holding the single-flight lock.

This is NOT a complete fix: until someone calls a public GAppInfo API the
native event counter is only polled by that caller. Real unsolicited signals
still require a safe native-to-GLib event bridge with shutdown ownership.
"""
import sys
from pathlib import Path


def patch(source: str) -> str:
    before = '  if (g_getenv ("C545D_DIAG_UWP_LAZY_PACKAGE_RESCAN") != NULL)\n    {\n'
    after = (before +
             '      gboolean c545d_ci_fire_after_query = FALSE;\n')
    if source.count(before) != 1:
        raise ValueError(f"unexpected lazy gate count: {source.count(before)}")
    source = source.replace(before, after, 1)
    before = """          g_mutex_unlock (&gio_win32_appinfo_mutex);
        }
      g_mutex_unlock (&c545d_ci_lazy_singleflight_lock);
    }
}


static void g_win32_app_info_iface_init"""
    after = """          g_mutex_unlock (&gio_win32_appinfo_mutex);
          c545d_ci_fire_after_query = TRUE;
        }
      g_mutex_unlock (&c545d_ci_lazy_singleflight_lock);
      /* Do not call user monitor handlers with the lazy single-flight
       * mutex held. Existing GIO monitor semantics coalesce until the
       * application calls another g_app_info_* API to re-arm them.
       * Deliberately NOT a spontaneous PackageCatalog event signal.
       */
      if (c545d_ci_fire_after_query &&
          g_getenv ("C545D_DIAG_APPINFO_MONITOR_POST_QUERY") != NULL)
        g_app_info_monitor_fire ();
    }
}


static void g_win32_app_info_iface_init"""
    if source.count(before) != 1:
        raise ValueError(f"unexpected post-wait boundary count: {source.count(before)}")
    return source.replace(before, after, 1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: monitor_after_lazy.py <glib/gio/gwin32appinfo.c>")
    p = Path(sys.argv[1])
    data = p.read_bytes()
    newline = "\r\n" if b"\r\n" in data else "\n"
    original = data.decode("utf-8").replace("\r\n", "\n")
    updated = patch(original)
    p.write_bytes(updated.replace("\n", newline).encode("utf-8"))
    print("C545D_MONITOR_AFTER_LAZY_PATCH_CI_ONLY,spontaneous_notification_unimplemented=true")


if __name__ == "__main__":
    main()
