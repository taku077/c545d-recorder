/* Only trigger the CI-only internal GWin32AppInfo dup smoke via the
 * existing GIO public entry point. The internal smoke exits early with
 * NULL after constructing all-synthetic application vectors.
 * No Windows package enumeration, registry writes or private ID logging.
 */
#include <gio/gio.h>

int main(void)
{
  GList *unused = g_app_info_get_all ();
  if (unused != NULL)
    {
      g_list_free_full (unused, g_object_unref);
      return 3; /* Internal synthetic path failed to intercept. */
    }
  return 0; /* CI validates the internal PASS record separately. */
}
