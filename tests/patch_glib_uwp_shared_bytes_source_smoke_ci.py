#!/usr/bin/env python3
"""CI-only deterministic hit/eviction hook for the patched GIO package parser.

This is a SECOND overlay, not the candidate patch: never include it in an
installable build. It exercises the actual static cache helper functions
already compiled inside a disposable patched GIO DLL, but with synthetic,
non-personal UTF16 text, no WinRT enumeration and no package/registry write.
The hook is opt-in in a short CI subprocess only.
"""
from pathlib import Path
import sys

HOOK = r"""/* CI-ONLY SOURCE SMOKE: fixed UTF16, no names/paths from the host.
 * This test is intentionally NOT part of the shared-bytes candidate patch.
 * Its caller sets C545D_CI_CACHE_REF_SMOKE only in the disposable runner.
 */
static gboolean
c545d_ci_shared_bytes_source_smoke (void)
{
  const wchar_t key[] = L"C545D_CI_SYNTHETIC_KEY";
  const wchar_t text[] = { 0x65e5, 0x672c, 0x8a9e, 0x30ab, 0x30e1, 0x30e9, 0 };
  const gsize expected_bytes = sizeof (text);
  const gpointer first_data;
  GBytes *first = NULL, *second = NULL;
  gsize length = 0;
  gboolean good = FALSE;

  /* The cache is isolated from real WinRT by the CI-only process flags. */
  c545d_cache_display_store (key, text);
  first = c545d_cache_display_lookup (key);
  second = c545d_cache_display_lookup (key);
  if (first == NULL || second == NULL)
    goto done;
  first_data = g_bytes_get_data (first, &length);
  if (first_data == NULL || length != expected_bytes ||
      memcmp (first_data, text, expected_bytes) != 0 ||
      g_bytes_get_data (second, NULL) != first_data)
    goto done;

  /* Simulate PackageCatalog/locale invalidation while both short-lived
   * reader references are held. They MUST remain valid after eviction. */
  g_mutex_lock (&c545d_display_cache_lock);
  g_hash_table_remove_all (c545d_display_cache);
  g_mutex_unlock (&c545d_display_cache_lock);
  good = g_bytes_get_data (first, &length) == first_data &&
         length == expected_bytes &&
         memcmp (first_data, text, expected_bytes) == 0 &&
         g_bytes_get_data (second, NULL) == first_data;

done:
  g_clear_pointer (&first, g_bytes_unref);
  g_clear_pointer (&second, g_bytes_unref);
  g_mutex_lock (&c545d_display_cache_lock);
  if (c545d_display_cache != NULL)
    g_hash_table_remove_all (c545d_display_cache);
  g_mutex_unlock (&c545d_display_cache_lock);
  if (good)
    g_print ("C545D_SHARED_BYTES_SOURCE_SMOKE_PASS,synthetic_utf16=1,"
             "same_cached_pointer=1,reader_valid_after_eviction=1,"
             "hit_utf16_copies=0,external_WinRT_enumeration=0,"
             "raw_host_identifiers_printed=0\n");
  return good;
}

"""

def replace_one(s: str, needle: str, changed: str) -> str:
    if s.count(needle) != 1:
        raise ValueError("CI-only shared cache source smoke anchor drift")
    return s.replace(needle,changed,1)

def patch(s: str) -> str:
    if "C545D_CI_CACHE_SHARED_BYTES" not in s or (
       "GBytes *\nc545d_cache_display_lookup" not in s):
        raise ValueError("must first apply real GBytes candidate patch")
    if "C545D_CI_CACHE_REF_SMOKE" in s:
        raise ValueError("duplicate CI-only bypass")
    s = replace_one(s, "gboolean\ng_win32_package_parser_enum_packages (",
                    HOOK+"gboolean\ng_win32_package_parser_enum_packages (")
    s = replace_one(s,
                    "  struct _xml_sax_state *sax = &sax_stack;\n",
                    '  struct _xml_sax_state *sax = &sax_stack;\n'
                    '  if (g_getenv ("C545D_CI_CACHE_REF_SMOKE") != NULL)\n'
                    '    return c545d_ci_shared_bytes_source_smoke ();\n')
    return s


def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: patch_glib_uwp_shared_bytes_source_smoke_ci.py "
                         "<disposable-patched-gwin32packageparser.c>")
    path=Path(sys.argv[1])
    raw=path.read_bytes()
    nl="\r\n" if b"\r\n" in raw else "\n"
    path.write_bytes(patch(raw.decode("utf-8").replace("\r\n","\n"))
                     .replace("\n",nl).encode("utf-8"))
    print("C545D_CI_SHARED_BYTES_SOURCE_SMOKE_PATCHED,"
          "not_releasable=1,synthetic_only=1,real_host_untouched=1")


if __name__=="__main__":
    main()
