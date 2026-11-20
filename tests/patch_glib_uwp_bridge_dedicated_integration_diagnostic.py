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
    # The only cleanup registration is a process-exit atexit handler.
    # Do NOT force-unload a C++/WinRT event DLL at that point: late
    # asynchronous COM callbacks and C++ static destructors can still be
    # in flight. The OS releases the module when the process ends. Keep
    # FreeLibrary for *failed initialization* (no subscribed callbacks).
    s=replace_once(s,
      "  if (c545d_bridge_module != NULL)\n"
      "    FreeLibrary (c545d_bridge_module);\n"
      "  c545d_bridge_module = NULL;\n"
      "  c545d_bridge_ready = FALSE;",
      "  /* CI ONLY: process-exit cleanup must not unload WinRT DLL while\n"
      "   * asynchronous callbacks/static destructors might still run. */\n"
      "  c545d_bridge_module = NULL;\n"
      "  c545d_bridge_ready = FALSE;",
      "skip hazardous watcher DLL unload from process-exit atexit")
    s=replace_once(s, "static DWORD c545d_bridge_owner;\n","", "old owner-thread variable")
    s=replace_once(s, "  c545d_bridge_owner = GetCurrentThreadId ();\n","",
                   "old owner-thread binding")
    s=replace_once(s,
       "  if (!c545d_bridge_ready || c545d_bridge_owner != GetCurrentThreadId () ||\n"
       "      c545d_bridge_snapshot_func (c545d_bridge_watch, &generation, &locale) != 0)",
       "  if (!c545d_bridge_ready ||\n"
       "      c545d_bridge_snapshot_func (c545d_bridge_watch, &generation, &locale) != 0)",
       "thread-independent read")
    # Both PackageCatalog generation and effective UI locale are part of
    # the cache lifetime. A locale change without package event MUST invalidate.
    s=replace_once(s,
      r"""static guint64
c545d_bridge_read_generation (void)
{
  guint64 generation;
  if (!c545d_bridge_poll ())
    return G_MAXUINT64;
  g_mutex_lock (&c545d_bridge_lock);
  generation = c545d_bridge_generation;
  g_mutex_unlock (&c545d_bridge_lock);
  return generation;
}

/* True on no-bridge old diagnostics; in bridge mode both successful
 * pre-getter epoch and current post-getter epoch must be identical.
 */
static gboolean
c545d_bridge_allow_store (guint64 pre_getter)
{
  if (!c545d_bridge_mode ())
    return TRUE;
  if (pre_getter == G_MAXUINT64 || !c545d_bridge_poll ())
    return FALSE;
  g_mutex_lock (&c545d_bridge_lock);
  gboolean current = c545d_bridge_generation == pre_getter;
  g_mutex_unlock (&c545d_bridge_lock);
  return current;
}""",
      r"""static C545DBridgeEpoch
c545d_bridge_read_epoch (void)
{
  C545DBridgeEpoch epoch = { 0, 0, FALSE };
  if (!c545d_bridge_poll ())
    return epoch;
  g_mutex_lock (&c545d_bridge_lock);
  epoch.generation = c545d_bridge_generation;
  epoch.locale = c545d_bridge_locale;
  epoch.valid = TRUE;
  g_mutex_unlock (&c545d_bridge_lock);
  return epoch;
}

/* Reject an in-flight package or locale change. A failed snapshot is a
 * cache miss, never a reason to return a previously cached string.
 */
static gboolean
c545d_bridge_epoch_still_valid (C545DBridgeEpoch previous)
{
  if (!previous.valid || !c545d_bridge_poll ())
    return FALSE;
  g_mutex_lock (&c545d_bridge_lock);
  const gboolean unchanged =
    (previous.generation == c545d_bridge_generation &&
     previous.locale == c545d_bridge_locale);
  g_mutex_unlock (&c545d_bridge_lock);
  return unchanged;
}

static gboolean
c545d_bridge_allow_store (C545DBridgeEpoch pre_getter)
{
  return !c545d_bridge_mode () ||
         c545d_bridge_epoch_still_valid (pre_getter);
}""",
      "complete package/locale cache epoch")

    original.BRIDGE=s
    source=Path(sys.argv[1])
    original.main(source)
    raw=source.read_bytes()
    newline="\r\n" if b"\r\n" in raw else "\n"
    code=raw.decode("utf-8").replace("\r\n","\n")
    code=replace_once(code,
      "static gboolean c545d_bridge_poll (void);",
      """typedef struct {
  guint64 generation;
  guint64 locale;
  gboolean valid;
} C545DBridgeEpoch;
static gboolean c545d_bridge_poll (void);
static C545DBridgeEpoch c545d_bridge_read_epoch (void);
static gboolean c545d_bridge_epoch_still_valid (C545DBridgeEpoch epoch);""",
      "epoch forward declaration before lookup")
    code=replace_once(code,
      """  if (!c545d_bridge_poll ())
    return NULL; /* fail closed to original getter */
  gchar *key = g_utf16_to_utf8""",
      """  C545DBridgeEpoch before = c545d_bridge_read_epoch ();
  if (!before.valid)
    return NULL; /* fail closed to original getter */
  gchar *key = g_utf16_to_utf8""",
      "capture pre-lookup epoch")
    code=replace_once(code,
      """  if (result != NULL && !c545d_bridge_poll ())
    g_clear_pointer (&result, g_free);""",
      """  if (result != NULL && !c545d_bridge_epoch_still_valid (before))
    g_clear_pointer (&result, g_free);""",
      "reject in-flight lookup invalidation")
    code=replace_once(code,
      "guint64 c545d_before_getter_generation = 0;",
      "C545DBridgeEpoch c545d_before_getter_epoch = { 0, 0, FALSE };",
      "full pre-getter epoch storage")
    code=replace_once(code,
      "c545d_before_getter_generation = c545d_bridge_read_generation ();",
      "c545d_before_getter_epoch = c545d_bridge_read_epoch ();",
      "capture pre-getter package/locale")
    code=replace_once(code,
      "c545d_bridge_allow_store (c545d_before_getter_generation)",
      "c545d_bridge_allow_store (c545d_before_getter_epoch)",
      "reject outdated getter cache store")
    source.write_bytes(code.replace("\n",newline).encode("utf-8"))
    print("C545D_GLIB_DEDICATED_MTA_COMPLETE_EPOCH_CI_ONLY_PATCHED")

if __name__=="__main__":
    main()
