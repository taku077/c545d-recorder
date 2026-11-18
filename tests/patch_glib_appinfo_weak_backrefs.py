#!/usr/bin/env python3
"""Experimental Win32 AppInfo *weak back-reference* patch for GLib 2.82.4.

Avoid uncollectable App->ShellVerb->App and App->Handler->ShellVerb->App
cycles without force-disposing caller-retained GAppInfo instances.

Safety principle: GWeakRef must be acquired as a strong ref before use.
This patch is source-specific and fails closed if the expected source differs.
Never install the resulting DLL on the user's recording PC until regression
tests and ABI compatibility checks have passed.
"""
from pathlib import Path
import sys


def once(src: str, before: str, after: str, label: str) -> str:
    matches = src.count(before)
    if matches != 1:
        raise ValueError(f"{label}: expected exactly one source match, got {matches}")
    return src.replace(before, after, 1)


def all_count(src: str, before: str, after: str, count: int, label: str) -> str:
    matches = src.count(before)
    if matches != count:
        raise ValueError(f"{label}: expected {count} matches, got {matches}")
    return src.replace(before, after)


def main(filename: str) -> None:
    path = Path(filename)
    s = path.read_text(encoding="utf-8")
    s = once(s, """struct _GWin32AppInfoShellVerb {
  GObject parent_instance;""",
             """struct _GWin32AppInfoShellVerb {
  GObject parent_instance;""", "ShellVerb struct")
    anchor = """  /* The application that is linked to this verb. */
  GWin32AppInfoApplication *app;
};
"""
    s = once(s, anchor, """  /* Weak back-reference: applications own verbs, and some own handlers.
   * Do not create a reference cycle that holds open registry HKEYs.
   */
  GWeakRef app;
};
""", "ShellVerb app field")
    s = once(s, "  g_clear_object (&shverb->app);\n", "", "remove strong app unref")
    marker = """static void
g_win32_appinfo_application_dispose (GObject *object)"""
    helper = """static void
g_win32_appinfo_shell_verb_finalize (GObject *object)
{
  GWin32AppInfoShellVerb *verb = G_WIN32_APPINFO_SHELL_VERB (object);

  g_weak_ref_clear (&verb->app);
  G_OBJECT_CLASS (g_win32_appinfo_shell_verb_parent_class)->finalize (object);
}

/* Acquire the application for use. The caller owns this reference.
 * In particular, a handler can outlive an obsolete registry generation.
 */
static GWin32AppInfoApplication *
c545d_shell_verb_ref_app (GWin32AppInfoShellVerb *verb)
{
  return g_weak_ref_get (&verb->app);
}

static gboolean
c545d_shell_verb_has_app (GWin32AppInfoShellVerb *verb)
{
  GWin32AppInfoApplication *app = c545d_shell_verb_ref_app (verb);

  if (app == NULL)
    return FALSE;

  g_object_unref (app);
  return TRUE;
}

"""
    s = once(s, marker, helper + marker, "helper insertion")
    s = once(s, """  gobject_class->dispose = g_win32_appinfo_shell_verb_dispose;
}""",
             """  gobject_class->dispose = g_win32_appinfo_shell_verb_dispose;
  gobject_class->finalize = g_win32_appinfo_shell_verb_finalize;
}""", "ShellVerb class init")
    s = once(s, """static void
g_win32_appinfo_shell_verb_init (GWin32AppInfoShellVerb *self)
{
}""",
             """static void
g_win32_appinfo_shell_verb_init (GWin32AppInfoShellVerb *self)
{
  g_weak_ref_init (&self->app, NULL);
}""", "ShellVerb instance init")
    s = all_count(s, "shverb->app = g_object_ref (app_rec);",
                  "g_weak_ref_set (&shverb->app, app_rec);", 3, "app_rec assignments")
    s = once(s, "shverb->app = g_object_ref (app);",
             "g_weak_ref_set (&shverb->app, app);", "app assignment")
    s = all_count(s, "handler_verb->app = g_object_ref (app);",
                  "g_weak_ref_set (&handler_verb->app, app);", 6, "handler_verb assignments")
    s = all_count(s, "if (handler_verb->app != NULL)",
                  "if (c545d_shell_verb_has_app (handler_verb))", 3, "has app checks")
    s = all_count(s, "if (handler_verb->app == NULL && handler_verb->is_uwp)",
                  "if (!c545d_shell_verb_has_app (handler_verb) && handler_verb->is_uwp)",
                  2, "UWP has app checks")

    # In the public-facing cache lookups, acquire the weak app reference
    # before releasing/replacing any cached graph. Never use a raw weak ptr.
    start = s.index("GAppInfo *\ng_app_info_get_default_for_uri_scheme_impl")
    end = s.index("GList *\ng_app_info_get_all_impl", start)
    public = s[start:end]
    before = """  result = NULL;

  if (scheme != NULL &&
      scheme->chosen_handler != NULL &&
      scheme->chosen_handler->verbs->len > 0 &&
      (shverb = _verb_idx (scheme->chosen_handler->verbs, 0))->app != NULL)
    result = g_win32_app_info_new_from_app (shverb->app,
                                            scheme->chosen_handler);
"""
    after = """  result = NULL;

  if (scheme != NULL &&
      scheme->chosen_handler != NULL &&
      scheme->chosen_handler->verbs->len > 0)
    {
      GWin32AppInfoApplication *app;

      shverb = _verb_idx (scheme->chosen_handler->verbs, 0);
      app = c545d_shell_verb_ref_app (shverb);
      if (app != NULL)
        {
          result = g_win32_app_info_new_from_app (app,
                                                  scheme->chosen_handler);
          g_object_unref (app);
        }
    }
"""
    public = once(public, before, after, "URI default lookup")
    before = """  result = NULL;

  if (ext->chosen_handler != NULL &&
      ext->chosen_handler->verbs->len > 0 &&
      (shverb = _verb_idx (ext->chosen_handler->verbs, 0))->app != NULL &&
      (!must_support_uris ||
       g_win32_app_supports_uris (shverb->app)))
    result = g_win32_app_info_new_from_app (shverb->app,
                                             ext->chosen_handler);
  else
"""
    after = """  result = NULL;

  if (ext->chosen_handler != NULL &&
      ext->chosen_handler->verbs->len > 0)
    {
      GWin32AppInfoApplication *app;

      shverb = _verb_idx (ext->chosen_handler->verbs, 0);
      app = c545d_shell_verb_ref_app (shverb);
      if (app != NULL)
        {
          if (!must_support_uris || g_win32_app_supports_uris (app))
            result = g_win32_app_info_new_from_app (app, ext->chosen_handler);
          g_object_unref (app);
        }
    }

  if (result == NULL)
"""
    public = once(public, before, after, "filetype default lookup")
    before = """          if (shverb->app &&
              (!must_support_uris ||
               g_win32_app_supports_uris (shverb->app)))
            result = g_win32_app_info_new_from_app (shverb->app, handler);
"""
    after = """          {
            GWin32AppInfoApplication *app = c545d_shell_verb_ref_app (shverb);
            if (app != NULL)
              {
                if (!must_support_uris || g_win32_app_supports_uris (app))
                  result = g_win32_app_info_new_from_app (app, handler);
                g_object_unref (app);
              }
          }
"""
    public = once(public, before, after, "filetype fallback lookup")
    s = s[:start] + public + s[end:]

    start = s.index("GList *\ng_app_info_get_all_for_type_impl")
    end = s.index("GList *\ng_app_info_get_fallback_for_type_impl", start)
    public = s[start:end]
    public = once(public,
                  "  apps = g_hash_table_new (g_direct_hash, g_direct_equal);",
                  """  /* The set owns acquired app references while this lookup is running. */
  apps = g_hash_table_new_full (g_direct_hash, g_direct_equal,
                                g_object_unref, NULL);""", "app set")
    before = """  if (ext->chosen_handler != NULL &&
      ext->chosen_handler->verbs->len > 0 &&
      (shverb = _verb_idx (ext->chosen_handler->verbs, 0))->app != NULL)
    {
      g_hash_table_add (apps, shverb->app);
      result = g_list_prepend (result,
                               g_win32_app_info_new_from_app (shverb->app,
                                                               ext->chosen_handler));
    }
"""
    after = """  if (ext->chosen_handler != NULL &&
      ext->chosen_handler->verbs->len > 0)
    {
      GWin32AppInfoApplication *app;

      shverb = _verb_idx (ext->chosen_handler->verbs, 0);
      app = c545d_shell_verb_ref_app (shverb);
      if (app != NULL)
        {
          g_hash_table_add (apps, app); /* Transfer reference to set. */
          result = g_list_prepend (result,
                                   g_win32_app_info_new_from_app (app,
                                                                   ext->chosen_handler));
        }
    }
"""
    public = once(public, before, after, "all for type chosen")
    before = """          if (shverb->app == NULL ||
              g_hash_table_contains (apps, shverb->app))
            continue;

          g_hash_table_add (apps, shverb->app);
          result = g_list_prepend (result,
                                   g_win32_app_info_new_from_app (shverb->app,
                                                                   handler));
"""
    after = """          {
            GWin32AppInfoApplication *app = c545d_shell_verb_ref_app (shverb);

            if (app == NULL)
              continue;
            if (g_hash_table_contains (apps, app))
              {
                g_object_unref (app);
                continue;
              }

            g_hash_table_add (apps, app); /* Transfer reference to set. */
            result = g_list_prepend (result,
                                     g_win32_app_info_new_from_app (app, handler));
          }
"""
    public = once(public, before, after, "all for type remaining")
    s = s[:start] + public + s[end:]

    # Hard gate: all former raw ShellVerb->app dereferences must be gone.
    import re
    raw = re.findall(r"\b(?:shverb|handler_verb|app_verb|verb)->app\b", s)
    allowed = s.count("&shverb->app") + s.count("&handler_verb->app") + s.count("&verb->app")
    if len(raw) != allowed:
        raise ValueError(f"unconverted ShellVerb app use: {len(raw)} occurrences / {allowed} address-of")
    path.write_text(s, encoding="utf-8")
    print("C545D_WEAK_BACKREF_PATCH_APPLIED", len(raw), "weak-ref accesses")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_glib_appinfo_weak_backrefs.py <gio/gwin32appinfo.c>")
    main(sys.argv[1])
