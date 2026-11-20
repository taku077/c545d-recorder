/* Short isolated Windows CI: safe C ABI snapshot vs concurrent close.
 * Demonstrates no UAF/double free for stale tokens and overlapping readers.
 * Synthetic notifications only, no real installed-package changes, cameras,
 * credentials, registry modifications or recorder DLL replacement.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#include <stdint.h>
#include <stdio.h>
#include "c545d_winrt_dedicated_watch.h"

enum { ROUNDS=16, READERS=6 };
typedef struct {
  c545d_dedicated_watch *token;
  volatile LONG ready, go, stop, bad, observed_closed, passes;
} Race;
static int fail(int step) {
  fprintf(stderr,"C545D_RACE_FAILED_STEP=%d\n",step);
  return step;
}
static DWORD WINAPI race_reader(void *ctx) {
  Race *r=(Race *)ctx;
  InterlockedIncrement(&r->ready);
  while(InterlockedCompareExchange(&r->go,0,0)==0) Sleep(0);
  for(unsigned i=0;i<16000;i++) {
    uint64_t g=0,l=0;
    int rc=c545d_dedicated_snapshot(r->token,&g,&l);
    if(rc==0 && (!g || !l)) InterlockedIncrement(&r->bad);
    else if(rc==3) {
      InterlockedIncrement(&r->observed_closed);
      break;
    } else if(rc==0 || rc==5) {
      InterlockedIncrement(&r->passes);
    } else {
      InterlockedIncrement(&r->bad);
      break;
    }
    if((i&15u)==0u) Sleep(1);
    if(InterlockedCompareExchange(&r->stop,0,0))break;
  }
  return 0;
}
static DWORD WINAPI race_closer(void *ctx) {
  Race *r=(Race *)ctx;
  while(InterlockedCompareExchange(&r->ready,0,0)!=READERS)Sleep(0);
  InterlockedExchange(&r->go,1);
  Sleep(8);
  c545d_dedicated_close(r->token);
  InterlockedExchange(&r->stop,1);
  return 0;
}
int main(void) {
  uint64_t registered=0,revoked=0,errors=0,g=0,l=0;
  DWORD handles0=0,handles1=0;
  PROCESS_MEMORY_COUNTERS_EX mem={0};
  SIZE_T private0=0,private1=0;
  if(c545d_dedicated_runtime_enter()!=0)return fail(1);
  for(int w=0;w<3;w++) {
    c545d_dedicated_watch *warm=NULL;
    if(c545d_dedicated_open(&warm)!=0 || !warm)return fail(2);
    if(c545d_dedicated_snapshot(warm,&g,&l)!=0)return fail(3);
    c545d_dedicated_close(warm);
  }
  mem.cb=sizeof(mem);
  if(!GetProcessHandleCount(GetCurrentProcess(),&handles0) ||
     !GetProcessMemoryInfo(GetCurrentProcess(),(PROCESS_MEMORY_COUNTERS *)&mem,sizeof(mem)))
    return fail(4);
  private0=mem.PrivateUsage;

  LONG read_count=0;
  for(int cycle=0;cycle<ROUNDS;cycle++) {
    c545d_dedicated_watch *watch=NULL;
    if(c545d_dedicated_open(&watch)!=0 || !watch)return fail(5);
    if(cycle==0) {
      /* An accidental early leave must not destroy COM under this live
       * watcher; the caller still owes a matching leave after final close.
       */
      c545d_dedicated_runtime_leave();
      if(c545d_dedicated_snapshot(watch,&g,&l)!=0)return fail(6);
    }
    Race race={0};
    race.token=watch;
    HANDLE handles[READERS+1]={0};
    for(int i=0;i<READERS;i++)
      handles[i]=CreateThread(NULL,0,race_reader,&race,0,NULL);
    handles[READERS]=CreateThread(NULL,0,race_closer,&race,0,NULL);
    for(int i=0;i<READERS+1;i++)if(!handles[i])return fail(7);
    if(WaitForMultipleObjects(READERS+1,handles,TRUE,30000)!=WAIT_OBJECT_0)
      return fail(8);
    for(int i=0;i<READERS+1;i++)CloseHandle(handles[i]);
    if(race.bad || race.passes==0)return fail(9);
    read_count+=race.passes;
    /* Stale token calls must be rejected even if the allocator recycled
     * an internal watch allocation, and duplicate close must not free again.
     */
    if(c545d_dedicated_snapshot(watch,&g,&l)!=3)return fail(10);
    if(c545d_dedicated_synthetic_event(watch)!=2)return fail(11);
    if(c545d_dedicated_ci_completion_counters(watch,&g,&l,&errors)!=3)
      return fail(12);
    c545d_dedicated_close(watch);
    c545d_dedicated_watch *replacement=NULL;
    if(c545d_dedicated_open(&replacement)!=0 || !replacement ||
       replacement==watch)return fail(13);
    if(c545d_dedicated_snapshot(watch,&g,&l)!=3)return fail(14);
    if(c545d_dedicated_snapshot(replacement,&g,&l)!=0)return fail(15);
    c545d_dedicated_close(replacement);
  }
  Sleep(300);
  c545d_dedicated_global_counters(&registered,&revoked,&errors);
  if(registered!=revoked || errors!=0 ||
     registered != 4u*(3u+2u*ROUNDS))return fail(16);
  mem.cb=sizeof(mem);
  if(!GetProcessHandleCount(GetCurrentProcess(),&handles1) ||
     !GetProcessMemoryInfo(GetCurrentProcess(),(PROCESS_MEMORY_COUNTERS *)&mem,sizeof(mem)))
    return fail(17);
  private1=mem.PrivateUsage;
  const int64_t private_delta=(int64_t)private1-(int64_t)private0;
  const int handles_delta=(int)handles1-(int)handles0;
  printf("C545D_WATCH_CONCURRENT_CLOSE_PASS,rounds=%d,readers=%d,"
         "successful_or_raced_snapshots=%ld,registrations=%llu,"
         "revocations=%llu,shutdown_errors=%llu,handles_delta=%d,"
         "private_usage_delta=%lld,stale_tokens_rejected=1,"
         "double_close_safe=1,live_watch_early_runtime_leave_safe=1,"
         "real_package_events=0,CI_only=true\n",
         ROUNDS,READERS,(long)read_count,
         (unsigned long long)registered,
         (unsigned long long)revoked,(unsigned long long)errors,
         handles_delta,(long long)private_delta);
  if(handles_delta>8)return fail(18);
  c545d_dedicated_runtime_leave();
  return 0;
}
