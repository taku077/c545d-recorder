/* CI-only privacy-safe hash of GLib AppInfo IDs and exact display names.
 * Compares default and diagnostic cache semantics without logging user data.
 * No network/camera access and no installed package strings are printed.
 */
#include <gio/gio.h>
#include <string.h>
#include <stdio.h>

static gint
compare_rows (gconstpointer left, gconstpointer right)
{
  const gchar *const *a = left;
  const gchar *const *b = right;
  return g_strcmp0 (*a, *b);
}

int
main (void)
{
  GList *items = g_app_info_get_all ();
  GPtrArray *rows = g_ptr_array_new_with_free_func (g_free);
  GChecksum *digest = g_checksum_new (G_CHECKSUM_SHA256);

  if (items == NULL || digest == NULL)
    return 2;

  for (GList *it = items; it != NULL; it = it->next)
    {
      GAppInfo *info = G_APP_INFO (it->data);
      const gchar *name = g_app_info_get_display_name (info);
      const gchar *id = g_app_info_get_id (info);
      /* NUL safe, length-prefixed rows avoid ambiguity. Hash only! */
      gchar *record = g_strdup_printf ("%zu:%s%zu:%s",
          id ? strlen (id) : (size_t) 0, id ? id : "",
          name ? strlen (name) : (size_t) 0, name ? name : "");
      g_ptr_array_add (rows, record);
    }

  g_ptr_array_sort (rows, compare_rows);
  for (guint i = 0; i < rows->len; i++)
    {
      const gchar *row = g_ptr_array_index (rows, i);
      g_checksum_update (digest, (const guchar *) row, strlen (row));
      g_checksum_update (digest, (const guchar *) "\n", 1);
    }
  g_print ("C545D_APPINFO_DISPLAY_SNAPSHOT,count=%u,sha256=%s\n",
           rows->len, g_checksum_get_string (digest));

  g_checksum_free (digest);
  g_ptr_array_free (rows, TRUE);
  g_list_free_full (items, g_object_unref);
  return 0;
}
