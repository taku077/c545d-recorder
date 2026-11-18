#!/usr/bin/env python3
"""Experimental GLib 2.82.4 Win32 GAppInfo refcycle patch.
Applies only to an isolated upstream source checkout (NOT the installed GIO DLL).
Fails closed if source layout differs.
"""
from pathlib import Path
import re
import sys

def main(path):
    p = Path(path)
    s = p.read_text(encoding="utf-8")
    def swap(old, new, count=1):
        nonlocal s
        actual = s.count(old)
        if actual != count:
            raise RuntimeError(f"Source mismatch expected {count} occurrences, found {actual}: {old[:110]!r}")
        s = s.replace(old, new)
    def replace_body(start_marker, end_marker, body):
        nonlocal s
        i = s.index(start_marker)
        j = s.index(end_marker, i + len(start_marker))
        s = s[:i] + body + s[j:]

    swap("  /* The application that is linked to this verb. */\n  GWin32AppInfoApplication *app;",
         "  /* A weak back-reference: an application owns its verb list. */\n  GWeakRef app;")
    swap("  g_clear_object (&shverb->app);", "  g_weak_ref_clear (&shverb->app);")
    swap("""static void
g_win32_appinfo_shell_verb_init (GWin32AppInfoShellVerb *self)
{
}
""", """static void
g_win32_appinfo_shell_verb_init (GWin32AppInfoShellVerb *self)
{
  g_weak_ref_init (&self->app, NULL);
}

/* The GAppInfo registry may rebuild on its worker thread.  Use GWeakRef
 * instead of a raw weak pointer so that readers can acquire a safe ref. */
static void
shell_verb_set_app (GWin32AppInfoShellVerb *verb,
                    GWin32AppInfoApplication *app)
{
  g_weak_ref_set (&verb->app, app);
}

static GWin32AppInfoApplication *
shell_verb_ref_app (GWin32AppInfoShellVerb *verb)
{
  return g_weak_ref_get (&verb->app);
}

static gboolean
shell_verb_has_app (GWin32AppInfoShellVerb *verb)
{
  GWin32AppInfoApplication *app = shell_verb_ref_app (verb);
  if (!app)
    return FALSE;
  g_object_unref (app);
  return TRUE;
}
""")

    s, n = re.subn(r"\b(shverb|handler_verb)->app = g_object_ref \((app|app_rec)\);",
                   r"shell_verb_set_app (\1, \2);", s)
    if n != 9:
        raise RuntimeError(f"Expected 9 strong back-reference assignments; got {n}")
    s = s.replace("handler_verb->app != NULL", "shell_verb_has_app (handler_verb)")
    s = s.replace("handler_verb->app == NULL", "!shell_verb_has_app (handler_verb)")

    marker = "g_app_info_get_default_for_uri_scheme_impl (const char *uri_scheme)"
    first = s.index(marker)
    start = s.index("  if (scheme != NULL &&", first)
    end = s.index("  g_clear_object (&scheme);", start)
    s = s[:start] + """  if (scheme != NULL &&
      scheme->chosen_handler != NULL &&
      scheme->chosen_handler->verbs->len > 0)
    {
      GWin32AppInfoApplication *app;
      shverb = _verb_idx (scheme->chosen_handler->verbs, 0);
      app = shell_verb_ref_app (shverb);
      if (app != NULL)
        {
          result = g_win32_app_info_new_from_app (app, scheme->chosen_handler);
          g_object_unref (app);
        }
    }

""" + s[end:]

    marker = "g_app_info_get_default_for_type_impl (const char *content_type,"
    first = s.index(marker)
    start = s.index("  if (ext->chosen_handler != NULL", first)
    end = s.index("  g_clear_object (&ext);", start)
    s = s[:start] + """  if (ext->chosen_handler != NULL &&
      ext->chosen_handler->verbs->len > 0)
    {
      GWin32AppInfoApplication *app;
      shverb = _verb_idx (ext->chosen_handler->verbs, 0);
      app = shell_verb_ref_app (shverb);
      if (app != NULL)
        {
          if (!must_support_uris || g_win32_app_supports_uris (app))
            result = g_win32_app_info_new_from_app (app, ext->chosen_handler);
          g_object_unref (app);
        }
    }

  if (result == NULL)
    {
      GHashTableIter iter;
      GWin32AppInfoHandler *handler;

      g_hash_table_iter_init (&iter, ext->handlers);

      while (result == NULL &&
             g_hash_table_iter_next (&iter, NULL, (gpointer *) &handler))
        {
          GWin32AppInfoApplication *app;

          if (handler->verbs->len == 0)
            continue;

          shverb = _verb_idx (handler->verbs, 0);
          app = shell_verb_ref_app (shverb);
          if (app != NULL)
            {
              if (!must_support_uris || g_win32_app_supports_uris (app))
                result = g_win32_app_info_new_from_app (app, handler);
              g_object_unref (app);
            }
        }
    }

""" + s[end:]

    marker = "g_app_info_get_all_for_type_impl (const char *content_type)"
    first = s.index(marker)
    start = s.index("  result = NULL;", first)
    end = s.index("  g_clear_object (&ext);", start)
    s = s[:start] + """  result = NULL;
  /* Keys own one strong reference for the duration of this enumeration.
   * This is necessary because the AppInfo cache may rebuild concurrently. */
  apps = g_hash_table_new_full (g_direct_hash, g_direct_equal,
                                g_object_unref, NULL);

  if (ext->chosen_handler != NULL &&
      ext->chosen_handler->verbs->len > 0)
    {
      GWin32AppInfoApplication *app;
      shverb = _verb_idx (ext->chosen_handler->verbs, 0);
      app = shell_verb_ref_app (shverb);
      if (app != NULL)
        {
          g_hash_table_add (apps, app);  /* Takes ownership of the ref. */
          result = g_list_prepend (result,
                                   g_win32_app_info_new_from_app (app,
                                                                  ext->chosen_handler));
        }
    }

  g_hash_table_iter_init (&iter, ext->handlers);

  while (g_hash_table_iter_next (&iter, NULL, (gpointer *) &handler))
    {
      gsize vi;

      for (vi = 0; vi < handler->verbs->len; vi++)
        {
          GWin32AppInfoApplication *app;
          shverb = _verb_idx (handler->verbs, vi);
          app = shell_verb_ref_app (shverb);
          if (app == NULL)
            continue;
          if (g_hash_table_contains (apps, app))
            {
              g_object_unref (app);
              continue;
            }

          g_hash_table_add (apps, app);  /* Takes ownership of the ref. */
          result = g_list_prepend (result,
                                   g_win32_app_info_new_from_app (app, handler));
        }
    }

""" + s[end:]

    # A dangling raw ShellVerb->app access is never acceptable after the change.
    leaked = re.findall(r"\b(?:shverb|handler_verb)->app\b", s)
    # references inside shell_verb helpers are expected; direct dereference must be absent
    if len(leaked) != 3:
        raise RuntimeError(f"Unexpected direct weak app references: {len(leaked)}")
    if "shverb->app = g_object_ref" in s or "handler_verb->app = g_object_ref" in s:
        raise RuntimeError("Strong cycle still present")
    p.write_text(s, encoding="utf-8", newline="\n")
    print("PATCH_APPLIED: experimental GWeakRef cycle-break patch for GLib 2.82.4")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: apply_gio_weakref_patch.py SOURCE/gio/gwin32appinfo.c")
    main(sys.argv[1])
