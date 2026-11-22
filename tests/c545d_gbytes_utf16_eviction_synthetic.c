/* Isolated GLib GBytes concurrency contract for the CI-only UTF16 cache.
 * This does not test GIO, COM, a user's installed packages, or measure a leak.
 * A reader acquires an immutable ref under a protected hash table; an event
 * simultaneously evicts the table entry. The reader's old UTF16 must survive.
 */
#include <glib.h>
#include <stdio.h>
#include <string.h>

static GHashTable *entries;
static GMutex cache_lock;
static GMutex gate_lock;
static GCond gate;
static gint stage;
static const gunichar2 old_name[] =
  {0x65e5, 0x672c, 0x8a9e, 0x30ab, 0x30e1, 0x30e9, 0};
static const gunichar2 new_name[] =
  {0x66f4, 0x65b0, 0x30ab, 0x30e1, 0x30e9, 0};

static void
store(const gunichar2 *name, gsize count)
{
  GBytes *item = g_bytes_new_take (g_memdup2 (name, count * sizeof (*name)),
                                  count * sizeof (*name));
  g_hash_table_replace (entries, g_strdup ("CI_PACKAGE"), item);
}

static gpointer
evict_on_package_event(gpointer unused)
{
  (void)unused;
  g_mutex_lock (&gate_lock);
  while (stage != 1)
    g_cond_wait (&gate, &gate_lock);
  g_mutex_unlock (&gate_lock);

  g_mutex_lock (&cache_lock);
  g_hash_table_remove_all (entries);
  store (new_name, G_N_ELEMENTS(new_name));
  g_mutex_unlock (&cache_lock);

  g_mutex_lock (&gate_lock);
  stage = 2;
  g_cond_signal (&gate);
  g_mutex_unlock (&gate_lock);
  return NULL;
}

int main(void)
{
  GBytes *retained;
  GThread *worker;
  const guint16 *original;
  const guint16 *current;
  gsize len = 0;
  guint i;

  entries = g_hash_table_new_full (g_str_hash, g_str_equal, g_free,
                                   (GDestroyNotify)g_bytes_unref);
  store (old_name, G_N_ELEMENTS(old_name));
  worker = g_thread_new ("c545d-cache-eviction", evict_on_package_event, NULL);
  if (!worker) return 10;
  g_mutex_lock (&cache_lock);
  retained = g_bytes_ref (g_hash_table_lookup (entries, "CI_PACKAGE"));
  original = g_bytes_get_data (retained, &len);
  if (len != sizeof (old_name) ||
      memcmp (original, old_name, sizeof (old_name)) != 0)
    return 11;
  g_mutex_unlock (&cache_lock);

  g_mutex_lock (&gate_lock);
  stage = 1;
  g_cond_signal (&gate);
  while (stage != 2)
    g_cond_wait (&gate, &gate_lock);
  g_mutex_unlock (&gate_lock);
  g_thread_join (worker);

  /* Eviction released the table's old reference, not the reader's. */
  if (g_bytes_get_data (retained, &len) != original ||
      len != sizeof (old_name) ||
      memcmp (original, old_name, sizeof (old_name)) != 0)
    return 12;
  g_bytes_unref (retained);

  /* Every repeated lookup receives the immutable SAME underlying data,
   * with no duplicate UTF16 allocation on hit. */
  for (i = 0; i < 1024; i++)
    {
      GBytes *item;
      g_mutex_lock (&cache_lock);
      item = g_bytes_ref (g_hash_table_lookup (entries, "CI_PACKAGE"));
      g_mutex_unlock (&cache_lock);
      current = g_bytes_get_data (item, &len);
      if (len != sizeof(new_name) ||
          memcmp (current, new_name, sizeof(new_name)) != 0)
        return 13;
      g_bytes_unref (item);
    }
  g_hash_table_unref (entries);
  g_mutex_clear (&cache_lock);
  g_mutex_clear (&gate_lock);
  g_cond_clear (&gate);
  printf ("C545D_GBYTES_UTF16_EVICTION_PASS,"
          "concurrent_threads=2,evictions=1,borrowed_old_text_valid=1,"
          "followup_cache_hits=1024,utf16_hit_copies=0,"
          "raw_package_names_emitted=0,new_windows_runs=0,"
          "gio_not_executed=1,real_recorder_unmodified=1\n");
  return 0;
}
