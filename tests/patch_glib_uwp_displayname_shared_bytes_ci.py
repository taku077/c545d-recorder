#!/usr/bin/env python3
"""CI-only lossless immutable-GBytes cache-hit sharing for GLib WinRT DisplayName.

Apply ONLY after the existing bounded UTF-16 DisplayName cache and dedicated
PackageCatalog+locale epoch bridge. The current baseline duplicates UTF-16
on EVERY cache hit. Retain a GBytes reference instead. This is an independently
testable allocator churn reduction candidate, not a proven PrivateUsage fix.

GBytes owns an immutable NUL-terminated UTF-16 copy; a transient ref taken
while the cache mutex is held survives concurrent event/locale invalidation.
The per-package cleanup drops that ref, including all early goto paths.
No API bypass, no locale changes, no cache policy/size changes, no OS writes.
"""
from pathlib import Path
import sys


def replace_exact(s: str, before: str, after: str, name: str,
                  count: int = 1) -> str:
    n = s.count(before)
    if n != count:
        raise ValueError(f"{name}: source drift or duplicate, count={n}")
    return s.replace(before, after)


def patch(s: str) -> str:
    if ("C545D_DISPLAY_CACHE_DIAGNOSTIC_ONLY_PATCHED" in s or
        "c545d_cache_display_lookup" not in s or
        "c545d_bridge_epoch_still_valid" not in s or
        "c545d_display_cache_lock" not in s):
        raise ValueError("dedicated locale-aware cache source required")
    if "C545D_CI_CACHE_SHARED_BYTES" in s:
        raise ValueError("shared bytes overlay already applied")

    s = replace_exact(
        s, "static gunichar2 *\nc545d_cache_display_lookup (",
        "static GBytes *\nc545d_cache_display_lookup (",
        "cache lookup result now retained immutable GBytes")
    s = replace_exact(
        s, "  gunichar2 *result = NULL;\n",
        "  GBytes *result = NULL;\n",
        "temporary lookup result", 1)
    s = replace_exact(
        s, "  const gunichar2 *stored = g_hash_table_lookup (c545d_display_cache, key);",
        "  GBytes *stored = g_hash_table_lookup (c545d_display_cache, key);",
        "cache table values are immutable GBytes")
    s = replace_exact(
        s, "      result = g_wcsdup (stored, -1);\n",
        "      result = g_bytes_ref (stored); /* no per-hit UTF-16 duplicate */\n",
        "acquire value reference while holding cache mutex")
    s = replace_exact(
        s, "g_clear_pointer (&result, g_free);",
        "g_clear_pointer (&result, g_bytes_unref);",
        "epoch-invalidated lookup releases own reference")
    s = replace_exact(
        s, "  gunichar2 *value;\n",
        "  GBytes *value;\n",
        "store owned immutable bytes")
    s = replace_exact(
        s, "  value = g_wcsdup ((const gunichar2 *) display_name, -1);\n",
        "  /* Each cache MISS duplicates original WinRT text once.\n"
        "   * Include the UTF-16 terminator for unchanged API semantics.\n"
        "   * g_bytes_new_take frees the GLib-allocated copy on final unref.\n"
        "   */\n"
        "  value = g_bytes_new_take (\n"
        "    g_wcsdup ((const gunichar2 *) display_name, -1),\n"
        "    (wcslen (display_name) + 1) * sizeof (gunichar2));\n",
        "only misses allocate the cache-owned string copy")
    s = replace_exact(
        s,
        "c545d_display_cache = g_hash_table_new_full (g_str_hash, g_str_equal,\n"
        "                                                  g_free, g_free);",
        "c545d_display_cache = g_hash_table_new_full (g_str_hash, g_str_equal,\n"
        "                                                  g_free, (GDestroyNotify) g_bytes_unref);",
        "both cache create branches release GBytes", 2)
    s = replace_exact(
        s, "      gunichar2 *c545d_cached_display_name = NULL;",
        "      GBytes *c545d_cached_display_name = NULL;",
        "per-package cache-hold variable")
    s = replace_exact(
        s, "wcs_display_name = c545d_cached_display_name != NULL\n"
        "        ? (const wchar_t *) c545d_cached_display_name",
        "wcs_display_name = c545d_cached_display_name != NULL\n"
        "        ? (const wchar_t *) g_bytes_get_data (c545d_cached_display_name, NULL)",
        "borrow live immutable bytes only during this package")
    s = replace_exact(
        s, "g_clear_pointer (&c545d_cached_display_name, g_free);",
        "g_clear_pointer (&c545d_cached_display_name, g_bytes_unref);",
        "early-error-safe per-package reference release")
    s = replace_exact(
        s,
        '  g_print ("C545D_DISPLAY_CACHE_REFRESH,scans=%u,resets=%u\\n",\n'
        '           c545d_diag_refresh_scans, c545d_diag_refresh_resets);',
        '  g_print ("C545D_DISPLAY_CACHE_REFRESH,scans=%u,resets=%u\\n",\n'
        '           c545d_diag_refresh_scans, c545d_diag_refresh_resets);\n'
        '  g_print ("C545D_CI_CACHE_SHARED_BYTES,hits=%u,utf16_hit_copies=0,"\n'
        '           "cache_capacity=1024,epoch_bridge_required=1\\n",\n'
        '           hits);',
        "numerically report avoided hit copies only", 1)
    if ("result = g_wcsdup (stored, -1)" in s or
        "g_clear_pointer (&c545d_cached_display_name, g_free)" in s or
        "c545d_display_cache = g_hash_table_new_full (g_str_hash, g_str_equal,\n"
        "                                                  g_free, g_free);" in s):
        raise ValueError("old copy/free cache paths remain")
    if s.count("g_bytes_ref (stored)") != 1 or (
            s.count("(GDestroyNotify) g_bytes_unref") != 2):
        raise ValueError("acquisition or table destructor count invalid")
    return s


def selftest():
    # Source text fixture models the real post-bridge owner paths. Actual
    # upstream exact anchors are also enforced when this runs in Windows CI.
    import patch_glib_uwp_displayname_cache_diagnostic as cached
    s = cached.HELPERS + (
        '\nstatic gboolean c545d_bridge_epoch_still_valid (void) { return TRUE; }\n'
        'void fake (void) {\n'
        '  GBytes *dummy = NULL;\n'
        '      gunichar2 *c545d_cached_display_name = NULL;\n'
        '  const wchar_t *wcs_display_name;\n'
        '  wcs_display_name = c545d_cached_display_name != NULL\n'
        '        ? (const wchar_t *) c545d_cached_display_name\n'
        '        : L"";\n'
        '  g_clear_pointer (&c545d_cached_display_name, g_free);\n'
        '}\n')
    # The bridge adds the post-read epoch gate and the snippet below,
    # already pinned by the actual-graft test.
    s=s.replace("  g_free (key);\n  return result;\n}",
        "  g_free (key);\n"
        "  if (result != NULL && !c545d_bridge_epoch_still_valid ())\n"
        "    g_clear_pointer (&result, g_free);\n"
        "  return result;\n}",1)
    modified = patch(s)
    if "g_bytes_ref (stored)" not in modified or (
       "g_clear_pointer (&c545d_cached_display_name, g_bytes_unref)" not in modified):
        raise AssertionError("synthetic owner path did not change")
    for original in (
        s.replace("      result = g_wcsdup (stored, -1);", "      result = g_strdup (stored);"),
        s.replace("g_clear_pointer (&c545d_cached_display_name, g_free);", ""),
        s.replace("  gunichar2 *value;", "  int *value;"),
        s.replace("  const gunichar2 *stored =", "  gpointer stored ="),
        modified,
    ):
        try:
            patch(original)
        except ValueError:
            continue
        raise AssertionError("unsafe source mutation accepted")
    print("C545D_CACHE_SHARED_BYTES_SELFTEST_PASS,positive=1,negative=5,"
          "lookup_duplicate_removed=1,per_package_unref_preserved=1,"
          "real_GIO_runs=0,original_256_rerun=0")


def main():
    if sys.argv[1:] == ["--selftest"]:
        selftest()
        return
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_glib_uwp_displayname_shared_bytes_ci.py "
                         "<disposable-gwin32packageparser.c>")
    path=Path(sys.argv[1])
    raw=path.read_bytes()
    newline="\r\n" if b"\r\n" in raw else "\n"
    changed=patch(raw.decode("utf-8").replace("\r\n","\n"))
    path.write_bytes(changed.replace("\n",newline).encode("utf-8"))
    print("C545D_CACHE_SHARED_BYTES_PATCHED,CI_only=1,"
          "public_API_changed=0,extra_WinRT_getters=0,"
          "real_recorder_unmodified=1")


if __name__ == "__main__":
    main()
