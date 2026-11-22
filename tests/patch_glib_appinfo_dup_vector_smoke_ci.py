#!/usr/bin/env python3
"""CI-only synthetic *actual* Windows GIO GWin32AppInfo dup smoke.

Source hook is injected exclusively into the disposable Windows GLib DLL,
never the releasable candidate. It calls real g_win32_app_info_dup() on
GWin32AppInfo instances populated with 0/1/3/8 fixed synthetic supported
types and proves a deep, NUL-terminated copy and finalizer unrefs.
No registry writes, user package identifiers, camera, or memory addresses.
"""
from __future__ import annotations

from pathlib import Path
import sys

HOOK = r"""/* CI-ONLY: direct actual GIO supported-types deep-copy and ownership gate.
 * No actual registry/package enumeration, no private identifiers and no
 * production code path. Kept separate from the deployable dup fix overlay.
 */
static gboolean
c545d_ci_appinfo_dup_vector_smoke (void)
{
  static const guint counts[] = { 0, 1, 3, 8 };
  guint case_index, iteration, passed = 0;

  for (case_index = 0; case_index < G_N_ELEMENTS (counts); ++case_index)
    {
      for (iteration = 0; iteration < 32; ++iteration)
        {
          GWin32AppInfo *source = g_object_new (G_TYPE_WIN32_APP_INFO, NULL);
          GWin32AppInfo *copy;
          guint i, count = counts[case_index];
          gboolean valid = TRUE;

          source->supported_types = g_new0 (gchar *, count + 1);
          for (i = 0; i < count; ++i)
            source->supported_types[i] = g_strdup_printf ("C545D_CI_TYPE_%u", i);

          copy = G_WIN32_APP_INFO (g_win32_app_info_dup (G_APP_INFO (source)));
          if (copy == NULL || copy->supported_types == NULL ||
              copy->supported_types == source->supported_types)
            valid = FALSE;

          if (valid)
            {
              for (i = 0; i < count; ++i)
                if (copy->supported_types[i] == source->supported_types[i] ||
                    g_strcmp0 (copy->supported_types[i],
                               source->supported_types[i]) != 0)
                  valid = FALSE;
              if (copy->supported_types[count] != NULL)
                valid = FALSE;
            }

          /* Destroy original and verify independence of the deep copy. */
          g_object_unref (source);
          if (valid)
            for (i = 0; i < count; ++i)
              {
                gchar expected[32];
                g_snprintf (expected, sizeof expected, "C545D_CI_TYPE_%u", i);
                if (g_strcmp0 (copy->supported_types[i], expected) != 0)
                  valid = FALSE;
              }

          g_clear_object (&copy);
          if (!valid)
            return FALSE;
          ++passed;
        }
    }

  g_print ("C545D_APPINFO_DUP_ACTUAL_GIO_SMOKE_PASS,"
           "cases=4,empty=32,single=32,multi3=32,multi8=32,"
           "total_copies=%u,deep_copy_verified=1,"
           "terminator_preserved=1,source_destroyed_before_copy=1,"
           "winrt_enumeration=0,registry_modified=0,host_untouched=1\n",
           passed);
  return TRUE;
}

"""
DEF="g_win32_app_info_dup (GAppInfo *appinfo)"
FUNC_START="GList *\ng_app_info_get_all_impl (void)\n{\n"
STARTUP="  gio_win32_appinfo_init (TRUE);\n  g_mutex_lock (&gio_win32_appinfo_mutex);\n"
INJECT='''  if (g_getenv ("C545D_CI_DUP_STRV_SMOKE") != NULL)
    {
      if (!c545d_ci_appinfo_dup_vector_smoke ())
        g_printerr ("C545D_APPINFO_DUP_ACTUAL_GIO_SMOKE_FAIL,code=BAD_VECTOR\\\\n");
      return NULL;
    }

'''


def patch(s: str) -> str:
    if s.count(DEF)!=1 or s.count(FUNC_START)!=1:
        raise ValueError("wrong_source_or_public_entry")
    if "new_info->supported_types = g_strdupv (info->supported_types);" not in s:
        raise ValueError("safe_dup_patch_required_first")
    if "C545D_CI_DUP_STRV_SMOKE" in s:
        raise ValueError("duplicate_CI_only_smoke")
    insertion = "\nstatic gboolean\ng_win32_app_info_equal"
    if s.count(insertion)!=1:
        raise ValueError("dup_tail_anchor_not_unique")
    s=s.replace(insertion,"\n"+HOOK+insertion,1)
    start=s.index(FUNC_START)
    next_fn=s.index("\nGList *\ng_app_info_get_all_for_type_impl",start)
    sub=s[start:next_fn]
    if sub.count(STARTUP)!=1:
        raise ValueError("public_lookup_not_safe_to_bypass")
    sub=sub.replace(STARTUP,INJECT+STARTUP,1)
    s=s[:start]+sub+s[next_fn:]
    if s.count("C545D_APPINFO_DUP_ACTUAL_GIO_SMOKE_PASS")!=1:
        raise ValueError("smoke_provenance_not_unique")
    return s


def main() -> None:
    if len(sys.argv)!=2:
        raise SystemExit("usage: patch_glib_appinfo_dup_vector_smoke_ci.py <disposable-appinfo.c>")
    p=Path(sys.argv[1])
    raw=p.read_bytes()
    nl="\r\n" if b"\r\n" in raw else "\n"
    modified=patch(raw.decode("utf-8").replace("\r\n","\n"))
    p.write_bytes(modified.replace("\n",nl).encode("utf-8"))
    print("C545D_APPINFO_DUP_ACTUAL_GIO_SMOKE_PATCHED,"
          "releasable=0,synthetic_only=1,private_paths_emitted=0")


if __name__=="__main__":
    main()
