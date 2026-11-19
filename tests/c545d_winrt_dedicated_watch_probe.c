// Pure C ABI Windows CI probe. No app name, package path, token or camera data.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#include <stdint.h>
#include <stdio.h>
#include "c545d_winrt_dedicated_watch.h"

typedef struct {c545d_dedicated_watch *watch; volatile LONG failures; unsigned loops;} Worker;
static DWORD WINAPI reader(LPVOID arg) {
  Worker *w=(Worker*)arg;
  for(unsigned i=0;i<w->loops;i++) {
    uint64_t g=0,l=0;
    int status=c545d_dedicated_snapshot(w->watch,&g,&l);
    if((status!=0 && status!=5)|| (status==0 && (!g||!l)))
      InterlockedIncrement(&w->failures);
  }
  return 0;
}
static DWORD WINAPI injector(LPVOID arg) {
  Worker *w=(Worker*)arg;
  for(unsigned i=0;i<w->loops;i++) {
    if(c545d_dedicated_synthetic_event(w->watch)!=0)
      InterlockedIncrement(&w->failures);
  }
  return 0;
}
static int fail(int n) {fprintf(stderr,"C545D_DEDICATED_FAILED_STEP=%d\n",n);return n;}
int main(void) {
  uint64_t open_count=0,close_count=0,errors=0,gen=0,lang=0;
  c545d_dedicated_watch *watch=NULL;
  DWORD h0=0,h1=0;
  SIZE_T p0=0,p1=0;
  PROCESS_MEMORY_COUNTERS_EX mem={0};
  mem.cb=sizeof(mem);
  if(c545d_dedicated_open(NULL)==0)return fail(2);
  if(c545d_dedicated_snapshot(NULL,&gen,&lang)==0)return fail(3);
  // Warm up Windows COM and apartment caches outside resource delta.
  for(int i=0;i<4;i++){
    if(c545d_dedicated_open(&watch)!=0 || !watch)return fail(4);
    if(c545d_dedicated_snapshot(watch,&gen,&lang)!=0)return fail(5);
    c545d_dedicated_close(watch);watch=NULL;
  }
  if(!GetProcessHandleCount(GetCurrentProcess(),&h0) ||
     !GetProcessMemoryInfo(GetCurrentProcess(),
            (PROCESS_MEMORY_COUNTERS*)&mem,sizeof(mem)))return fail(6);
  p0=mem.PrivateUsage;

  for(int i=0;i<64;i++){
    if(c545d_dedicated_open(&watch)!=0 || !watch)return fail(7);
    if(c545d_dedicated_snapshot(watch,&gen,&lang)!=0 || gen!=1 || lang==0)
      return fail(8);
    if(c545d_dedicated_synthetic_event(watch)!=0)return fail(9);
    if(c545d_dedicated_snapshot(watch,&gen,&lang)!=0 || gen!=2)return fail(10);
    c545d_dedicated_close(watch);watch=NULL;
  }
  if(c545d_dedicated_open(&watch)!=0)return fail(11);
  uint64_t before=0;
  if(c545d_dedicated_snapshot(watch,&before,&lang)!=0)return fail(12);
  Worker shared={watch,0,1000};
  HANDLE threads[5]={0};
  for(int i=0;i<4;i++)threads[i]=CreateThread(NULL,0,reader,&shared,0,NULL);
  threads[4]=CreateThread(NULL,0,injector,&shared,0,NULL);
  for(int i=0;i<5;i++)if(!threads[i])return fail(13);
  if(WaitForMultipleObjects(5,threads,TRUE,30000)!=WAIT_OBJECT_0)return fail(14);
  for(int i=0;i<5;i++)CloseHandle(threads[i]);
  if(shared.failures!=0)return fail(15);
  // A clean final snapshot after all readers and injector finish.
  if(c545d_dedicated_snapshot(watch,&gen,&lang)!=0 || gen-before!=1000)
     return fail(16);
  c545d_dedicated_close(watch);watch=NULL;
  Sleep(300);
  c545d_dedicated_global_counters(&open_count,&close_count,&errors);
  if(open_count!=close_count || open_count!=4*(64+4+1) || errors!=0)
    return fail(17);
  mem.cb=sizeof(mem);
  if(!GetProcessHandleCount(GetCurrentProcess(),&h1) ||
     !GetProcessMemoryInfo(GetCurrentProcess(),
           (PROCESS_MEMORY_COUNTERS*)&mem,sizeof(mem)))return fail(18);
  p1=mem.PrivateUsage;
  int handles=(int)h1-(int)h0;
  long long private_delta=(long long)p1-(long long)p0;
  printf("C545D_DEDICATED_WINRT_WATCH_PASS,watch_cycles=64,registrations=%llu,revocations=%llu,synthetic_notifications=1000,concurrent_readers=4,reader_snapshots=4000,handles_delta=%d,private_usage_delta=%lld,shutdown_errors=%llu,real_package_update_events=0,CI_only=true\n",
       (unsigned long long)open_count,(unsigned long long)close_count,handles,
       private_delta,(unsigned long long)errors);
  if(handles>8)return fail(19);
  return 0;
}
