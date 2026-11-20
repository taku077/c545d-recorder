/* CI ONLY. Test actual GIO AppInfo contents across a live native watcher
 * changing from HEALTHY to UNAVAILABLE while the process is running.
 * The defect is SYNTHETIC, NOT a genuine Windows PackageCatalog failure.
 * One disposable HKCU value on the GitHub-hosted Windows runner requests
 * a normal GIO registry refresh; this value is removed before exit.
 * Output contains counts and flags ONLY, no package strings or private paths.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <gio/gio.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

typedef void (__cdecl *Counters)(uint64_t*,uint64_t*,uint64_t*);
static volatile gint c545d_changed_count = 0;
static void on_changed(GAppInfoMonitor *monitor, gpointer data) {
  (void)monitor;(void)data;
  g_atomic_int_inc(&c545d_changed_count);
}
static void dispatch_pending_main_context(void) {
  for(int k=0;k<300 && g_main_context_pending(NULL);k++)
    g_main_context_iteration(NULL,FALSE);
}
static gint compare_rows(gconstpointer a,gconstpointer b) {
  const char * const *aa=a,* const *bb=b;
  return g_strcmp0(*aa,*bb);
}
static gboolean snapshot(char digest[65],guint *count) {
  GList *list=g_app_info_get_all();
  GChecksum *hash=g_checksum_new(G_CHECKSUM_SHA256);
  GPtrArray *rows=g_ptr_array_new_with_free_func(g_free);
  if(!list||!hash||!rows) {
    if(list)g_list_free_full(list,g_object_unref);
    if(hash)g_checksum_free(hash);
    if(rows)g_ptr_array_free(rows,TRUE);
    return FALSE;
  }
  for(GList *p=list;p;p=p->next) {
    GAppInfo *info=G_APP_INFO(p->data);
    const char *id=g_app_info_get_id(info);
    const char *name=g_app_info_get_display_name(info);
    gchar *record=g_strdup_printf("%zu:%s%zu:%s",
      id?strlen(id):(size_t)0,id?id:"",
      name?strlen(name):(size_t)0,name?name:"");
    g_ptr_array_add(rows,record);
  }
  g_ptr_array_sort(rows,compare_rows);
  for(guint i=0;i<rows->len;i++){
    const char *line=g_ptr_array_index(rows,i);
    g_checksum_update(hash,(const guchar*)line,strlen(line));
    g_checksum_update(hash,(const guchar*)"\n",1);
  }
  *count=rows->len;
  g_strlcpy(digest,g_checksum_get_string(hash),65);
  g_ptr_array_free(rows,TRUE);
  g_checksum_free(hash);
  g_list_free_full(list,g_object_unref);
  return TRUE;
}

int main(void) {
  char initial[65]={0}, after_fault[65]={0}, after_refresh[65]={0};
  guint apps0=0,apps1=0,apps2=0;
  HKEY key=NULL;
  wchar_t value_name[96]={0};
  gboolean wrote=FALSE;
  int status=1;
  HMODULE bridge;
  Counters counters=NULL;
  GAppInfoMonitor *monitor=g_app_info_monitor_get();
  if(!monitor) {
    fprintf(stderr,"C545D_RUNTIME_GIO_FAILURE=monitor_not_available\n");return 1;
  }
  g_signal_connect(monitor,"changed",G_CALLBACK(on_changed),NULL);
  uint64_t regs=0,revs=0,errs=0;
  if(!snapshot(initial,&apps0)||apps0==0) {
    fprintf(stderr,"C545D_RUNTIME_GIO_FAILURE=initial_appinfo\n");goto done;
  }
  bridge=GetModuleHandleW(L"c545d_full_watch.dll");
  if(!bridge) {
    fprintf(stderr,"C545D_RUNTIME_GIO_FAILURE=watcher_not_loaded\n");goto done;
  }
  counters=(Counters)GetProcAddress(bridge,"c545d_dedicated_global_counters");
  if(!counters) {
    fprintf(stderr,"C545D_RUNTIME_GIO_FAILURE=watcher_counter_missing\n");goto done;
  }
  counters(&regs,&revs,&errs);
  if(regs!=4||revs!=0||errs!=0) {
    fprintf(stderr,"C545D_RUNTIME_GIO_FAILURE=watcher_not_healthy\n");goto done;
  }

  if(!SetEnvironmentVariableW(L"C545D_CI_FORCE_RUNTIME_UNAVAILABLE",L"1")) {
    fprintf(stderr,"C545D_RUNTIME_GIO_FAILURE=cannot_arm\n");goto done;
  }
  if(!snapshot(after_fault,&apps1)) {
    fprintf(stderr,"C545D_RUNTIME_GIO_FAILURE=post_arm_query\n");goto done;
  }
  SetEnvironmentVariableW(L"C545D_CI_FORCE_RUNTIME_UNAVAILABLE",NULL);
  gboolean revoked=FALSE;
  for(int n=0;n<400;n++){
    counters(&regs,&revs,&errs);
    if(regs==4&&revs==4&&errs==0){revoked=TRUE;break;}
    Sleep(10);
  }
  if(!revoked || apps1!=apps0 || strcmp(after_fault,initial)!=0) {
    fprintf(stderr,"C545D_RUNTIME_GIO_FAILURE=post_fault_parity_or_revoke\n");goto done;
  }

  /* Trigger one GIO worker rescan independently of PackageCatalog and with
   * native watcher already unavailable. Existing GLib registry monitoring
   * initiates this asynchronously; no forced WinRT/COM handle closure. */
  if(RegOpenKeyExW(HKEY_CURRENT_USER,L"Software\\RegisteredApplications",
                  0,KEY_SET_VALUE,&key)!=ERROR_SUCCESS) {
    fprintf(stderr,"C545D_RUNTIME_GIO_FAILURE=disposable_registry_open\n");goto done;
  }
  _snwprintf(value_name,95,L"C545D_RuntimeDropCI_%lu",(unsigned long)GetCurrentProcessId());
  value_name[95]=L'\0';
  const wchar_t value[]=L"Software\\C545D_CI_NONEXISTENT_CAPABILITIES";
  gint changes_before=g_atomic_int_get(&c545d_changed_count);
  if(RegSetValueExW(key,value_name,0,REG_SZ,(const BYTE*)value,
                    (DWORD)sizeof(value))!=ERROR_SUCCESS) {
    fprintf(stderr,"C545D_RUNTIME_GIO_FAILURE=disposable_registry_write\n");goto done;
  }
  wrote=TRUE;
  /* Stock GLib Win32 registry notification requires processing the
   * thread-default main context, as in the previously verified 16-cycle
   * watcher probe. Do not count mere unchanged g_app_info_get_all queries
   * as a successful cache fallback test. */
  for(int k=0;k<65;k++) {
    Sleep(100);
    dispatch_pending_main_context();
    if(g_atomic_int_get(&c545d_changed_count)>changes_before)break;
  }
  if(g_atomic_int_get(&c545d_changed_count)<=changes_before) {
    fprintf(stderr,"C545D_RUNTIME_GIO_FAILURE=registry_signal_not_delivered\n");
    goto done;
  }
  for(int k=0;k<10;k++) {
    if(!snapshot(after_refresh,&apps2)) {
      fprintf(stderr,"C545D_RUNTIME_GIO_FAILURE=after_refresh_query\n");goto done;
    }
    if(apps2==apps0&&strcmp(initial,after_refresh)==0)break;
    Sleep(200);
  }
  if(apps2!=apps0 || strcmp(initial,after_refresh)!=0) {
    fprintf(stderr,"C545D_RUNTIME_GIO_FAILURE=after_refresh_parity\n");goto done;
  }
  counters(&regs,&revs,&errs);
  if(regs!=4||revs!=4||errs!=0){
    fprintf(stderr,"C545D_RUNTIME_GIO_FAILURE=subscription_balance\n");goto done;
  }
  printf("C545D_GIO_RUNTIME_DROP_CI_PASS,baseline_apps=%u,"
         "post_fault_apps=%u,post_refresh_apps=%u,hash_parity=1,"
         "owner_COM_registered=4,owner_COM_revoked=4,"
         "watcher_revoked_before_public_GIO_refresh=1,"
         "synthetic_runner_registry_stimuli=1,"
         "real_OS_watch_failure_NOT_observed=1,CI_only=1\n",
         apps0,apps1,apps2);
  status=0;
done:
  SetEnvironmentVariableW(L"C545D_CI_FORCE_RUNTIME_UNAVAILABLE",NULL);
  g_signal_handlers_disconnect_by_func(monitor,G_CALLBACK(on_changed),NULL);
  g_object_unref(monitor);
  if(key!=NULL) {
    if(wrote) RegDeleteValueW(key,value_name);
    RegCloseKey(key);
  }
  return status;
}
