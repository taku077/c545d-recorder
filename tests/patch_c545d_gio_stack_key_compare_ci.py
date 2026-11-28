#!/usr/bin/env python3
"""CI-only same-DLL A/B switch and numeric counters for the qualified stack key."""
import argparse
from pathlib import Path
from patch_c545d_gio_stack_lookup_key_ci import patch, once

FLAG = "C545D_DIAG_UWP_STACK_LOOKUP_KEY"
DECL = r'''static guint64 c545d_stack_key_fast, c545d_stack_key_heap;
static gsize c545d_stack_key_mode;
static gboolean
c545d_stack_key_enabled (void)
{
  if (g_once_init_enter (&c545d_stack_key_mode))
    {
      const gchar *flag = g_getenv ("C545D_DIAG_UWP_STACK_LOOKUP_KEY");
      g_once_init_leave (&c545d_stack_key_mode,
                         flag != NULL && strcmp (flag, "1") == 0 ? 2 : 1);
    }
  return c545d_stack_key_mode == 2;
}
'''
def overlay(s):
    s = patch(s)
    s = once(s, "static gboolean\nc545d_ascii_stack_key", DECL + "\nstatic gboolean\nc545d_ascii_stack_key")
    s = once(s, "  if (c545d_ascii_stack_key ((const gunichar2 *) full_name, stack_key))",
             "  if (c545d_stack_key_enabled () &&\n      c545d_ascii_stack_key ((const gunichar2 *) full_name, stack_key))")
    start = s.index("static gunichar2 *\nc545d_cache_display_lookup")
    end = s.index("\nstatic void\nc545d_cache_display_store", start)
    body = s[start:end]
    body = once(body, "  g_mutex_lock (&c545d_display_cache_lock);",
                "  g_mutex_lock (&c545d_display_cache_lock);\n  if (owned_key == NULL)\n    c545d_stack_key_fast++;\n  else\n    c545d_stack_key_heap++;")
    s = s[:start] + body + s[end:]
    start = s.index("static void\nc545d_cache_display_report (void)")
    end = s.index("\n}", start)
    body = s[start:end]
    body = once(body, "  guint misses;", "  guint misses;\n  guint64 fast, heap;")
    body = once(body, "  misses = c545d_display_cache_misses;",
                "  misses = c545d_display_cache_misses;\n  fast = c545d_stack_key_fast;\n  heap = c545d_stack_key_heap;")
    body = once(body, "  /* Numeric counters only:", '''  g_print ("C545D_STACK_KEY_COUNTS,enabled=%d,fast=%" G_GUINT64_FORMAT ",heap=%" G_GUINT64_FORMAT "\\n",
           c545d_stack_key_enabled (), fast, heap);
  /* Numeric counters only:''')
    return s[:start] + body + s[end:]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("source", type=Path)
    a = p.parse_args()
    if a.source.name != "gwin32packageparser.c" or a.source.parent.name != "gio":
        raise ValueError("source_name")
    raw = a.source.read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    a.source.write_bytes(overlay(raw.decode("utf-8").replace("\r\n", "\n")).replace("\n", nl).encode("utf-8"))
    print("C545D_STACK_COMPARE_OVERLAY_PASS,same_dll=1,epoch_guards=2,counters_locked=1")
if __name__ == "__main__":
    main()
