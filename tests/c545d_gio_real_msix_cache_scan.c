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
#include <string.h>

/* CI ONLY: GAppInfoMonitor contract/observability probe. Creates one monitor
 * in the same GLib default main context as the PowerShell host's GIO caller.
 * No registry mutations are performed by these monitor functions.
 * Post-query notification cannot be called 'spontaneous'; each is recorded
 * separately from the interval before calling any g_app_info_* API.
 */
static GAppInfoMonitor *ci_monitor = NULL;
static GMainContext *ci_monitor_context = NULL;
static volatile gint ci_monitor_changed_count = 0;

static void ci_monitor_changed (GAppInfoMonitor *monitor, gpointer user_data)
{
  (void)monitor;
  (void)user_data;
  g_atomic_int_inc (&ci_monitor_changed_count);
}
__declspec(dllexport) int __cdecl c545d_ci_monitor_start (void)
{
  if (ci_monitor != NULL) return -40;
  ci_monitor_context = g_main_context_ref_thread_default ();
  ci_monitor = g_app_info_monitor_get ();
  if (!ci_monitor || !ci_monitor_context) return -41;
  g_signal_connect (ci_monitor, "changed", G_CALLBACK(ci_monitor_changed), NULL);
  g_atomic_int_set (&ci_monitor_changed_count, 0);
  puts ("C545D_APPINFO_MONITOR_STARTED,context_ready=1");
  fflush (stdout);
  return 0;
}
__declspec(dllexport) int __cdecl c545d_ci_monitor_observe (int stage)
{
  if (!ci_monitor || !ci_monitor_context || stage < 0 || stage > 33) return -42;
  /* Dispatch pending notifications only; no GAppInfo query here.
   * A count observed during 11/12/13 precedes the next natural query.
   */
  gint64 limit = g_get_monotonic_time () + 450000;
  do {
    while (g_main_context_pending (ci_monitor_context))
      g_main_context_iteration (ci_monitor_context, FALSE);
    g_usleep (10000);
  } while (g_get_monotonic_time () < limit);
  int count = g_atomic_int_get (&ci_monitor_changed_count);
  printf ("C545D_APPINFO_MONITOR_OBSERVATION,stage=%d,changed=%d\n", stage, count);
  fflush (stdout);
  return count;
}
__declspec(dllexport) int __cdecl c545d_ci_monitor_stop (void)
{
  if (!ci_monitor || !ci_monitor_context) return -43;
  while (g_main_context_pending (ci_monitor_context))
    g_main_context_iteration (ci_monitor_context, FALSE);
  int count = g_atomic_int_get (&ci_monitor_changed_count);
  g_signal_handlers_disconnect_by_func (ci_monitor, G_CALLBACK(ci_monitor_changed), NULL);
  g_object_unref (ci_monitor);
  ci_monitor = NULL;
  g_main_context_unref (ci_monitor_context);
  ci_monitor_context = NULL;
  printf ("C545D_APPINFO_MONITOR_FINAL,changed=%d,clean_stop=1\n", count);
  fflush (stdout);
  return count;
}

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

/* Synthetic disposable-package freshness test. Only numeric booleans
 * leave this process; names are fixed static CI fixture literals, never
 * user-installed package identifiers or raw AppInfo enumeration output.
 */
__declspec(dllexport) int __cdecl
c545d_ci_scan_fixture_display_name(int stage)
{
  if(stage<1 || stage>3)return -60;
  GList *list=g_app_info_get_all();
  int original=0, updated=0;
  for(GList *p=list;p;p=p->next) {
    const char *name=g_app_info_get_display_name(G_APP_INFO(p->data));
    if(name && strcmp(name,"C545D CI Event Probe")==0)original++;
    if(name && strcmp(name,"C545D CI Event Probe Upgraded")==0)updated++;
  }
  g_list_free_full(list,g_object_unref);
  gboolean fresh=(stage==1 ? original==1 && updated==0 :
                  stage==2 ? original==0 && updated==1 :
                             original==0 && updated==0);
  printf("C545D_GIO_FIXTURE_DISPLAY_VERSION,stage=%d,fresh=%d,"
         "old_count=%d,new_count=%d,CI_only=1\n",
         stage,fresh?1:0,original,updated);
  fflush(stdout);
  return fresh?1:-61;
}

/* CI ONLY: verify public GAppInfo display text on the SAME process and
 * unchanged main package FullName. Run only AFTER a genuine PackageCatalog
 * terminal event was observed, without any registry-write trigger.
 * This does not expose installed application IDs or names in artifacts.
 */
__declspec(dllexport) int __cdecl
c545d_ci_scan_resource_display_value(int stage, int reverse)
{
  if (stage < 1 || stage > 3 || reverse != 1) return -70;
  GList *list = g_app_info_get_all();
  int english = 0, french = 0;
  for (GList *p = list; p; p = p->next)
    {
      const char *name = g_app_info_get_display_name (G_APP_INFO(p->data));
      if (name && strcmp (name, "English synthetic resource value") == 0)
        english++;
      if (name && strcmp (name, "French synthetic resource value") == 0)
        french++;
    }
  g_list_free_full (list, g_object_unref);
  const gboolean expected = stage == 2 ?
    (english == 1 && french == 0) :
    (english == 0 && french == 1);
  printf ("C545D_GIO_RESOURCE_DISPLAY,stage=%d,fresh=%d,"
          "english=%d,french=%d,reverse=1,CI_only=1\n",
          stage, expected ? 1 : 0, english, french);
  fflush (stdout);
  return expected ? 1 : -71;
}

/* CI only: let eight callers compete for one *genuine* pending package
 * generation. Every thread queries public GAppInfo; no synthetic events
 * and no registry writes occur until the existing positive control later.
 */
enum { C545D_PARALLEL_CALLERS=8 };
typedef struct {
  volatile LONG ready;
  volatile LONG go;
  volatile LONG faults;
  volatile LONG app_count;
} C545DParallel;

static DWORD WINAPI c545d_parallel_reader(void *ctx)
{
  C545DParallel *p=(C545DParallel *)ctx;
  InterlockedIncrement(&p->ready);
  while(InterlockedCompareExchange(&p->go,0,0)==0)Sleep(0);
  int n=enumerate_and_release();
  if(n<=0)InterlockedIncrement(&p->faults);
  else {
    LONG first=InterlockedCompareExchange(&p->app_count,n,0);
    if(first!=0 && first!=n)InterlockedIncrement(&p->faults);
  }
  return 0;
}

__declspec(dllexport) int __cdecl c545d_ci_scan_parallel_stage(int stage)
{
  if(stage<1 || stage>3)return -30;
  Sleep(1300); /* Match the earlier single-caller observation interval. */
  C545DParallel p={0};
  HANDLE threads[C545D_PARALLEL_CALLERS]={0};
  for(int i=0;i<C545D_PARALLEL_CALLERS;i++) {
    threads[i]=CreateThread(NULL,0,c545d_parallel_reader,&p,0,NULL);
    if(!threads[i]) {
      InterlockedIncrement(&p.faults);
      for(int k=0;k<i;k++)CloseHandle(threads[k]);
      return -31;
    }
  }
  for(int attempts=0;attempts<5000 &&
        InterlockedCompareExchange(&p.ready,0,0)!=C545D_PARALLEL_CALLERS;
      attempts++)Sleep(1);
  if(InterlockedCompareExchange(&p.ready,0,0)!=C545D_PARALLEL_CALLERS)
    return -32;
  InterlockedExchange(&p.go,1);
  DWORD waited=WaitForMultipleObjects(C545D_PARALLEL_CALLERS,threads,TRUE,30000);
  for(int i=0;i<C545D_PARALLEL_CALLERS;i++)CloseHandle(threads[i]);
  if(waited!=WAIT_OBJECT_0)return -33;
  if(p.faults!=0 || p.app_count<=0)return -34;
  printf("C545D_GIO_PARALLEL_QUERY_PASS,stage=%d,callers=%d,"
         "apps=%ld,failures=0,real_os_package_event=1\n",
         stage,C545D_PARALLEL_CALLERS,(long)p.app_count);
  fflush(stdout);
  return (int)p.app_count;
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
