/* Disposable CI only: drive GIO AppInfo enumeration in the SAME process as
 * a REAL Windows signed MSIX install/update/uninstall test. Do not deploy.
 * No recording/camera/network access. A single runner-local HKCU value is
 * used solely to force GLib AppInfo's asynchronous registry refresh.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <gio/gio.h>
#include <stdio.h>
#include <wchar.h>
#include <stdint.h>

static HKEY ci_key;
static wchar_t ci_value_name[96];
static int ci_started;

static int enumerate_and_release(void)
{
  GList *list = g_app_info_get_all();
  int count = 0;
  for (GList *l = list; l; l=l->next) {
    const char *name = g_app_info_get_display_name(G_APP_INFO(l->data));
    if (!name) { g_list_free_full(list, g_object_unref); return -20; }
    count++;
  }
  g_list_free_full(list, g_object_unref);
  return count;
}

__declspec(dllexport) int __cdecl c545d_ci_scan_real_msix_stage(int stage)
{
  LONG rc;
  /* Natural package-notification observation: stages 5/6/7 enumerate
   * AFTER genuine install/update/uninstall, BEFORE any CI registry stimulus.
   * They never write a registry value or disable existing callbacks.
   * The existing 0..4 positive-control path remains unchanged.
   */
  if (stage < 0 || stage > 7) return -1;
  if (stage >= 5 && stage <= 7) Sleep(1300);
  if (!ci_started) {
    _snwprintf(ci_value_name,95,L"C545D_RealMSIX_CI_%lu",
               (unsigned long)GetCurrentProcessId());
    ci_value_name[95]=L'\0';
    rc=RegOpenKeyExW(HKEY_CURRENT_USER,L"Software\\RegisteredApplications",
                     0,KEY_SET_VALUE,&ci_key);
    if(rc!=ERROR_SUCCESS)return -2;
    ci_started=1;
  }
  if (stage >= 1 && stage <= 3) {
    wchar_t value[128];
    _snwprintf(value,127,L"Software\\C545D_NoSuchCapabilities\\msix_step_%d",
               stage);
    value[127]=L'\0';
    rc=RegSetValueExW(ci_key,ci_value_name,0,REG_SZ,(BYTE *)value,
                      (DWORD)((wcslen(value)+1)*sizeof(wchar_t)));
    if(rc!=ERROR_SUCCESS)return -3;
    Sleep(1300);
  }
  if(stage == 4) {
    RegDeleteValueW(ci_key,ci_value_name);
    RegCloseKey(ci_key);
    ci_key=NULL;
    Sleep(700);
  }
  /* GLib's registry-rebuild task is asynchronous. Drain and enumerate
   * on the already initialized GIO process, not a new process per stage.
   */
  for(int i=0;i<30 && g_main_context_pending(NULL);i++)
    g_main_context_iteration(NULL,FALSE);
  int count=enumerate_and_release();
  if(count<=0)return count?count:-4;
  printf("C545D_GIO_REAL_MSIX_STAGE,step=%d,apps=%d\n",stage,count);
  fflush(stdout);
  return count;
}
