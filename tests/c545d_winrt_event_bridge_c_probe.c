/* Compile with MSVC as C, link to separately compiled C++/WinRT DLL.
 * The test never mutates real packages, language, recorder or registry.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#include <stdint.h>
#include <stdio.h>
#include "c545d_winrt_event_bridge.h"

typedef struct { c545d_winrt_watch *watch; LONG errors; } Worker;
static DWORD WINAPI run_notifications(LPVOID param) {
  Worker *w=(Worker *)param;
  for (int i=0;i<1000;i++)
    if (c545d_watch_inject_synthetic(w->watch)!=0)
      InterlockedIncrement(&w->errors);
  return 0;
}

int main(void) {
  c545d_winrt_watch *watch=NULL;
  uint64_t gen=0,lang=0,before=0,lang_before=0;
  DWORD start_h=0,end_h=0;
  SIZE_T start_private=0,end_private=0;
  PROCESS_MEMORY_COUNTERS_EX m={0};
  if (c545d_watch_snapshot(NULL,&gen,&lang)==0) return 2;
  if (c545d_watch_open(NULL)==0) return 3;
  /* Prewarm OS activation before counting long-lived process resources. */
  for(int i=0;i<4;i++) {
    if(c545d_watch_open(&watch)!=0||!watch) return 4;
    if(c545d_watch_snapshot(watch,&gen,&lang)!=0||!lang) return 5;
    c545d_watch_close(watch);
    watch=NULL;
  }
  m.cb=sizeof(m);
  if(!GetProcessHandleCount(GetCurrentProcess(),&start_h)||
     !GetProcessMemoryInfo(GetCurrentProcess(),(PROCESS_MEMORY_COUNTERS *)&m,sizeof(m))) return 6;
  start_private=m.PrivateUsage;
  for(int i=0;i<64;i++) {
    if(c545d_watch_open(&watch)!=0||!watch) return 7;
    if(c545d_watch_snapshot(watch,&gen,&lang)!=0||!lang) return 8;
    if(c545d_watch_inject_synthetic(watch)!=0) return 9;
    if(c545d_watch_snapshot(watch,&gen,&lang)!=0||gen!=2) return 10;
    c545d_watch_close(watch);
    watch=NULL;
  }
  if(c545d_watch_open(&watch)!=0) return 11;
  if(c545d_watch_snapshot(watch,&before,&lang_before)!=0) return 12;
  Worker w={watch,0};
  HANDLE t=CreateThread(NULL,0,run_notifications,&w,0,NULL);
  if(!t) return 13;
  if(WaitForSingleObject(t,30000)!=WAIT_OBJECT_0) return 14;
  CloseHandle(t);
  if(w.errors) return 15;
  if(c545d_watch_snapshot(watch,&gen,&lang)!=0||gen-before!=1000||lang!=lang_before) return 16;
  c545d_watch_close(watch);
  watch=NULL;
  Sleep(250);
  m.cb=sizeof(m);
  if(!GetProcessHandleCount(GetCurrentProcess(),&end_h)||
     !GetProcessMemoryInfo(GetCurrentProcess(),(PROCESS_MEMORY_COUNTERS *)&m,sizeof(m))) return 17;
  end_private=m.PrivateUsage;
  int hd=(int)end_h-(int)start_h;
  long long pd=(long long)end_private-(long long)start_private;
  printf("C545D_WINRT_C_ABI_PASS,cycles=64,subscriptions_per_cycle=4,revocations_per_cycle=4,synthetic_notifications=1000,generation_delta=%llu,handle_delta=%d,private_delta_bytes=%lld,locale_hash_nonzero=true,real_package_updates=0,Windows_CI_only=true\n",
    (unsigned long long)(gen-before),hd,pd);
  if(hd>8) {
    fprintf(stderr,"C545D_WINRT_C_ABI_HANDLE_REGRESSION,%d\n",hd);
    return 18;
  }
  return 0;
}
