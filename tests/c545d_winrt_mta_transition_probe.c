/* CI ONLY: deterministic open/close-vs-runtime-leave interleavings.
 * No recorder, user registry, camera, package mutations or private strings.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include "c545d_winrt_dedicated_watch.h"

typedef struct {
  c545d_dedicated_watch *watch;
  int result;
} Work;

static int error(int step) {
  fprintf(stderr,"C545D_MTA_TRANSITION_FAIL_STEP=%d\n",step);
  return step;
}
static int numbers(uint32_t *refs,uint32_t *opening,
                   uint32_t *closing,uint32_t *watches) {
  return c545d_dedicated_ci_lifetime_counters(
      refs,opening,closing,watches);
}
static DWORD WINAPI open_worker(void *ctx) {
  Work *work=(Work *)ctx;
  work->result=c545d_dedicated_open(&work->watch);
  return 0;
}
static DWORD WINAPI close_worker(void *ctx) {
  Work *work=(Work *)ctx;
  c545d_dedicated_close(work->watch);
  return 0;
}
static int await_transition(int which) {
  uint32_t refs=0,opening=0,closing=0,watches=0;
  for(int i=0;i<2000;i++) {
    if(numbers(&refs,&opening,&closing,&watches)!=0)return 0;
    if(which==1 && refs==1 && opening==1 && watches==0)return 1;
    if(which==2 && refs==1 && closing==1 && watches==0)return 1;
    Sleep(1);
  }
  return 0;
}
static int wait_thread(HANDLE h) {
  if(!h)return 0;
  DWORD rc=WaitForSingleObject(h,15000);
  CloseHandle(h);
  return rc==WAIT_OBJECT_0;
}
int main(void) {
  uint32_t refs=0,opening=0,closing=0,watches=0;
  uint64_t gen=0,locale=0;
  Work open_work={0};
  if(c545d_dedicated_runtime_enter()!=0)return error(1);
  if(!SetEnvironmentVariableW(L"C545D_CI_PAUSE_WATCH_OPEN",L"1"))
    return error(2);
  HANDLE open_thread=CreateThread(NULL,0,open_worker,&open_work,0,NULL);
  if(!open_thread)return error(3);
  if(!await_transition(1))return error(4);
  c545d_dedicated_runtime_leave(); // adversarial overlapping last-leave
  if(numbers(&refs,&opening,&closing,&watches)!=0 ||
     refs!=1 || opening!=1 || closing!=0 || watches!=0)
    return error(5);
  if(!wait_thread(open_thread))return error(6);
  if(!SetEnvironmentVariableW(L"C545D_CI_PAUSE_WATCH_OPEN",NULL))
    return error(7);
  if(open_work.result!=0 || !open_work.watch)return error(8);
  if(numbers(&refs,&opening,&closing,&watches)!=0 ||
     refs!=1 || opening!=0 || closing!=0 || watches!=1)
    return error(9);
  if(c545d_dedicated_snapshot(open_work.watch,&gen,&locale)!=0 ||
     !gen || !locale)
    return error(10);
  c545d_dedicated_close(open_work.watch);
  c545d_dedicated_runtime_leave();
  if(numbers(&refs,&opening,&closing,&watches)!=0 ||
     refs || opening || closing || watches)
    return error(11);

  Work close_work={0};
  if(c545d_dedicated_runtime_enter()!=0)return error(12);
  if(c545d_dedicated_open(&close_work.watch)!=0 || !close_work.watch)
    return error(13);
  if(!SetEnvironmentVariableW(L"C545D_CI_PAUSE_WATCH_CLOSE",L"1"))
    return error(14);
  HANDLE close_thread=CreateThread(NULL,0,close_worker,&close_work,0,NULL);
  if(!close_thread)return error(15);
  if(!await_transition(2))return error(16);
  c545d_dedicated_runtime_leave(); // table empty; worker still subscribed
  if(numbers(&refs,&opening,&closing,&watches)!=0 ||
     refs!=1 || opening!=0 || closing!=1 || watches!=0)
    return error(17);
  if(!wait_thread(close_thread))return error(18);
  if(!SetEnvironmentVariableW(L"C545D_CI_PAUSE_WATCH_CLOSE",NULL))
    return error(19);
  if(numbers(&refs,&opening,&closing,&watches)!=0 ||
     refs!=1 || opening!=0 || closing!=0 || watches!=0)
    return error(20);
  if(c545d_dedicated_snapshot(close_work.watch,&gen,&locale)!=3)
    return error(21); // already-retired token cannot be revived
  c545d_dedicated_runtime_leave();
  if(numbers(&refs,&opening,&closing,&watches)!=0 ||
     refs || opening || closing || watches)
    return error(22);
  puts("C545D_MTA_TRANSITION_PASS,open_reserved=1,close_reserved=1,"
       "early_leave_blocked_both=1,post_join_leave=1,"
       "stale_token_rejected=1,CI_only=true");
  return 0;
}
