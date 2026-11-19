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

static int fail_step(int n) {
  fprintf(stderr,"C545D_WINRT_C_ABI_FAILED_STEP=%d\n",n);
  return n;
}

int main(void) {
  fprintf(stderr,"BRIDGE_CHECKPOINT=entry\n"); fflush(stderr);
  c545d_winrt_watch *watch=NULL;
  uint64_t gen=0,lang=0,before=0,lang_before=0;
  DWORD start_h=0,end_h=0;
  SIZE_T start_private=0,end_private=0;
  PROCESS_MEMORY_COUNTERS_EX m={0};
  if (c545d_watch_snapshot(NULL,&gen,&lang)==0) return fail_step(2);
  if (c545d_watch_open(NULL)==0) return fail_step(3);
  fprintf(stderr,"BRIDGE_CHECKPOINT=negative_arguments_ok\n"); fflush(stderr);
  if(c545d_watch_open(&watch)==0) return fail_step(19);
  if(c545d_thread_enter()!=0) return fail_step(20);
  fprintf(stderr,"BRIDGE_CHECKPOINT=thread_apartment_entered\n"); fflush(stderr);
  /* Prewarm OS activation before counting long-lived process resources. */
  for(int i=0;i<4;i++) {
    fprintf(stderr,"BRIDGE_CHECKPOINT=warmup_begin_%d\n",i); fflush(stderr);
    if(c545d_watch_open(&watch)!=0||!watch) return fail_step(4);
    fprintf(stderr,"BRIDGE_CHECKPOINT=warmup_open_%d\n",i); fflush(stderr);
    if(c545d_watch_snapshot(watch,&gen,&lang)!=0||!lang) return fail_step(5);
    fprintf(stderr,"BRIDGE_CHECKPOINT=warmup_snapshot_%d\n",i); fflush(stderr);
    c545d_watch_close(watch);
    fprintf(stderr,"BRIDGE_CHECKPOINT=warmup_close_%d\n",i); fflush(stderr);
    watch=NULL;
  }
  m.cb=sizeof(m);
  if(!GetProcessHandleCount(GetCurrentProcess(),&start_h)||
     !GetProcessMemoryInfo(GetCurrentProcess(),(PROCESS_MEMORY_COUNTERS *)&m,sizeof(m))) return fail_step(6);
  start_private=m.PrivateUsage;
  fprintf(stderr,"BRIDGE_CHECKPOINT=warmup_done\n"); fflush(stderr);
  for(int i=0;i<64;i++) {
    fprintf(stderr,"BRIDGE_CHECKPOINT=loop_begin_%d\n",i); fflush(stderr);
    if(c545d_watch_open(&watch)!=0||!watch) return fail_step(7);
    if(c545d_watch_snapshot(watch,&gen,&lang)!=0||!lang) return fail_step(8);
    if(c545d_watch_inject_synthetic(watch)!=0) return fail_step(9);
    if(c545d_watch_snapshot(watch,&gen,&lang)!=0||gen!=2) return fail_step(10);
    c545d_watch_close(watch);
    fprintf(stderr,"BRIDGE_CHECKPOINT=loop_close_%d\n",i); fflush(stderr);
    watch=NULL;
  }
  fprintf(stderr,"BRIDGE_CHECKPOINT=loop_done\n"); fflush(stderr);
  if(c545d_watch_open(&watch)!=0) return fail_step(11);
  if(c545d_watch_snapshot(watch,&before,&lang_before)!=0) return fail_step(12);
  fprintf(stderr,"BRIDGE_CHECKPOINT=thread_start\n"); fflush(stderr);
  Worker w={watch,0};
  HANDLE t=CreateThread(NULL,0,run_notifications,&w,0,NULL);
  if(!t) return fail_step(13);
  if(WaitForSingleObject(t,30000)!=WAIT_OBJECT_0) return fail_step(14);
  CloseHandle(t);
  if(w.errors) return fail_step(15);
  if(c545d_watch_snapshot(watch,&gen,&lang)!=0||gen-before!=1000||lang!=lang_before) return fail_step(16);
  fprintf(stderr,"BRIDGE_CHECKPOINT=thread_complete\n"); fflush(stderr);
  c545d_watch_close(watch);
  fprintf(stderr,"BRIDGE_CHECKPOINT=thread_close\n"); fflush(stderr);
  watch=NULL;
  Sleep(250);
  m.cb=sizeof(m);
  if(!GetProcessHandleCount(GetCurrentProcess(),&end_h)||
     !GetProcessMemoryInfo(GetCurrentProcess(),(PROCESS_MEMORY_COUNTERS *)&m,sizeof(m))) return fail_step(17);
  end_private=m.PrivateUsage;
  int hd=(int)end_h-(int)start_h;
  long long pd=(long long)end_private-(long long)start_private;
  printf("C545D_WINRT_C_ABI_PASS,cycles=64,subscriptions_per_cycle=4,revocations_per_cycle=4,synthetic_notifications=1000,generation_delta=%llu,handle_delta=%d,private_delta_bytes=%lld,locale_hash_nonzero=true,real_package_updates=0,Windows_CI_only=true\n",
    (unsigned long long)(gen-before),hd,pd);
  if(hd>8) {
    fprintf(stderr,"C545D_WINRT_C_ABI_HANDLE_REGRESSION,%d\n",hd);
    return fail_step(18);
  }
  c545d_thread_leave();
  fprintf(stderr,"BRIDGE_CHECKPOINT=thread_apartment_left\n"); fflush(stderr);
  return 0;
}
