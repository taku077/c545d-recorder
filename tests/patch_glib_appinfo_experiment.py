#!/usr/bin/env python3
"""EXPERIMENT ONLY: force-dispose stale AppInfo application nodes on tree replacement.
Never deploy to a recorder. This can invalidate externally held GAppInfo objects.
Produces a surgical source rewrite for an isolated CI comparison.
"""
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
src = path.read_text(encoding="utf-8")
needle = """static void
update_registry_data (void)
{"""
assert src.count(needle) == 1, "GLib 2.82.4 source signature changed"
helper = """/*
 * C545D DIAGNOSTIC EXPERIMENT -- NOT A PRODUCTION OWNERSHIP FIX.
 * Force dispose cached applications before releasing the old tree.
 * Cyclic Application<->ShellVerb refs otherwise survive simple unrefs.
 * EXTERNAL GAppInfo references may be invalidated by this experiment.
 */
static void
c545d_dispose_stale_app (gpointer key,
                         gpointer value,
                         gpointer user_data)
{
  (void) key;
  (void) user_data;
  if (value != NULL)
    g_object_run_dispose (G_OBJECT (value));
}

static void
c545d_dispose_stale_apps (void)
{
  if (apps_by_id != NULL)
    g_hash_table_foreach (apps_by_id, c545d_dispose_stale_app, NULL);
  if (apps_by_exe != NULL)
    g_hash_table_foreach (apps_by_exe, c545d_dispose_stale_app, NULL);
  if (fake_apps != NULL)
    g_hash_table_foreach (fake_apps, c545d_dispose_stale_app, NULL);
}

"""
src = src.replace(needle, helper + needle)
needle2 = """  g_clear_pointer (&apps_by_id, g_hash_table_destroy);"""
assert src.count(needle2) == 1, "Cache-clear marker changed"
src = src.replace(needle2, "  c545d_dispose_stale_apps();\n" + needle2)
path.write_text(src, encoding="utf-8")
print("C545D_DIAGNOSTIC_PATCH_APPLIED: stale AppInfo cache disposal before rebuild")
