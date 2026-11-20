/* Isolated GAppInfo API/lifetime smoke, no camera or recording.
 * A disposable CI HKCU RegisteredApplications value is modified and removed.
 * Keeps a GAppInfo from the original cache alive across repeated rebuilds.
 */
#include <windows.h>
#include <gio/gio.h>
#include <stdio.h>
#include <wchar.h>

static gboolean valid_info(GAppInfo *info)
{
  return info == NULL ||
         (G_IS_APP_INFO(info) && g_app_info_get_name(info) != NULL);
}

int main(void)
{
  HKEY key = NULL;
  wchar_t name[96];
  LONG rc;
  GList *apps;
  GAppInfo *held = NULL;
  int i;
  int n_default_type = 0, n_default_uri = 0, n_all_for_type = 0;

  _snwprintf(name, 95, L"C545D_GIO_Lifetime_%lu", (unsigned long)GetCurrentProcessId());
  name[95] = L'\0';
  rc = RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\RegisteredApplications",
                     0, KEY_SET_VALUE, &key);
  if (rc != ERROR_SUCCESS)
    return 2;

  apps = g_app_info_get_all();
  if (apps)
    held = g_object_ref(apps->data);
  g_list_free_full(apps, g_object_unref);

  for (i = 0; i < 16; i++)
    {
      wchar_t value[96];
      GAppInfo *default_type;
      GAppInfo *default_uri;
      GList *by_type;
      GList *it;

      _snwprintf(value, 95, L"Software\\C545D_Absent\\%d", i);
      value[95] = L'\0';
      rc = RegSetValueExW(key, name, 0, REG_SZ, (const BYTE *) value,
                          (DWORD)((wcslen(value) + 1) * sizeof(wchar_t)));
      if (rc != ERROR_SUCCESS)
        {
          RegDeleteValueW(key, name);
          RegCloseKey(key);
          return 3;
        }

      Sleep(500);
      default_type = g_app_info_get_default_for_type(".txt", FALSE);
      default_uri = g_app_info_get_default_for_uri_scheme("http");
      by_type = g_app_info_get_all_for_type(".txt");
      if (!valid_info(held) || !valid_info(default_type) || !valid_info(default_uri))
        {
          fprintf(stderr, "GIO_API_INVALID_AFTER_REBUILD,%d\n", i);
          RegDeleteValueW(key, name);
          RegCloseKey(key);
          return 4;
        }
      if (default_type) n_default_type++;
      if (default_uri) n_default_uri++;
      for (it = by_type; it; it = it->next)
        {
          if (!valid_info(it->data))
            {
              fprintf(stderr, "GIO_API_INVALID_TYPE_LIST,%d\n", i);
              RegDeleteValueW(key, name);
              RegCloseKey(key);
              return 5;
            }
          n_all_for_type++;
        }
      g_clear_object(&default_type);
      g_clear_object(&default_uri);
      g_list_free_full(by_type, g_object_unref);
    }
  g_clear_object(&held);
  RegDeleteValueW(key, name);
  RegCloseKey(key);
  printf("GIO_API_PASS,cycles=16,default_type=%d,default_uri=%d,all_for_type=%d\n",
         n_default_type, n_default_uri, n_all_for_type);
  return 0;
}
