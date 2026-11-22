#!/usr/bin/env python3
"""Disposable-only GLib registry APC ownership event instrumentation.

Patches pinned 2.82.4 gwin32registrykey.c after the owned-path patch.
The runtime trace exposes ONLY numeric registered/completed/pending counts.
Never touches production GIO, no new public ABI, no registry paths.
Status-block and key-ref lifetime is already source-bounded; this measures
whether the same per-key boundedness is respected at runtime.
"""
from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "C545D_CI_REGISTRY_WATCH_LIFETIME"

HELPER = r'''/* C545D disposable CI-only registry watch lifetime counters.
 * These counters are intentionally not exported. Logging can change
 * scheduling, so do not compare PrivateUsage from traced/untraced builds.
 */
static GMutex c545d_watch_trace_mutex;
static gint c545d_watch_trace_registered;
static gint c545d_watch_trace_completed;
static gint c545d_watch_trace_active;

static void
c545d_watch_trace_update (gboolean registered)
{
  gint reg, done, active;
  if (g_getenv ("C545D_CI_WATCH_LIFETIME_TRACE") == NULL)
    return;

  g_mutex_lock (&c545d_watch_trace_mutex);
  if (registered)
    {
      reg = ++c545d_watch_trace_registered;
      done = c545d_watch_trace_completed;
      active = ++c545d_watch_trace_active;
    }
  else
    {
      reg = c545d_watch_trace_registered;
      done = ++c545d_watch_trace_completed;
      active = --c545d_watch_trace_active;
    }
  g_print ("C545D_CI_REGISTRY_WATCH_LIFETIME,kind=%s,reg=%d,done=%d,active=%d\n",
           registered ? "register" : "complete", reg, done, active);
  g_mutex_unlock (&c545d_watch_trace_mutex);
}
'''

CALLBACK = """  g_object_unref (key);\n}"""
CALLBACK_PATCHED = """  c545d_watch_trace_update (FALSE);
  g_object_unref (key);
}"""

SUCCESS = """  if (status == STATUS_PENDING || status == STATUS_SUCCESS)
    return TRUE;"""
SUCCESS_PATCHED = """  if (status == STATUS_PENDING || status == STATUS_SUCCESS)
    {
      c545d_watch_trace_update (TRUE);
      return TRUE;
    }"""

def region(s: str, first: str, until: str) -> tuple[int, int]:
    if s.count(first) != 1:
        raise ValueError("source_anchor_missing_or_duplicated")
    a = s.index(first)
    b = s.find(until, a + len(first))
    if b < 0:
        raise ValueError("function_end_missing")
    return a, b

def patch(s: str) -> str:
    if MARKER in s or "c545d_watch_trace_update" in s:
        raise ValueError("already_instrumented_or_conflicting")
    a, b = region(s, "static VOID NTAPI\nkey_changed (", "/**\n * g_win32_registry_key_watch:")
    body = s[a:b]
    if body.count(CALLBACK) != 1 or "g_free (status_block);" not in body:
        raise ValueError("APC_ownership_contract_changed")
    # Instrument BEFORE the terminal unref in the completion callback.
    body = body.replace(CALLBACK, CALLBACK_PATCHED)
    s = s[:a] + HELPER + "\n" + body + s[b:]
    a, b = region(s, "gboolean\ng_win32_registry_key_watch (",
                  "/**\n * g_win32_registry_key_erase_change_indicator:")
    body = s[a:b]
    if body.count(SUCCESS) != 1 or "g_object_ref (key);" not in body:
        raise ValueError("watch_registration_contract_changed")
    body = body.replace(SUCCESS, SUCCESS_PATCHED)
    s = s[:a] + body + s[b:]
    if s.count("c545d_watch_trace_update (TRUE);") != 1 or s.count("c545d_watch_trace_update (FALSE);") != 1:
        raise ValueError("trace_injection_failed")
    return s

def selftest(s: str) -> None:
    good = patch(s)
    assert good.count(MARKER) == 2
    invalid = [
        s.replace(CALLBACK, "  /* no unref */\n}", 1),
        s.replace(SUCCESS, "  if (status == STATUS_PENDING)\n    return TRUE;", 1),
        good,
        s.replace("static VOID NTAPI\nkey_changed (", "static VOID NTAPI\nkey_mutated (", 1),
        s.replace("gboolean\ng_win32_registry_key_watch (", "gboolean\ng_win32_registry_key_watch_changed (", 1),
    ]
    for i, wrong in enumerate(invalid):
        try:
            patch(wrong)
        except ValueError:
            continue
        raise AssertionError(f"unsafe_watch_trace_patch_accepted,index={i}")
    print("C545D_GIO_WATCH_LIFETIME_PATCH_SELFTEST_PASS,positive=1,negative=5,public_API_added=0")

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("path", type=Path)
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    s = a.path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if a.selftest:
        selftest(s)
        return
    patched = patch(s)
    a.path.write_text(patched, encoding="utf-8")
    print("C545D_GIO_WATCH_LIFETIME_DISPOSABLE_SOURCE_PASS,no_new_exports=1,no_user_host_changes=1")

if __name__ == "__main__":
    main()
