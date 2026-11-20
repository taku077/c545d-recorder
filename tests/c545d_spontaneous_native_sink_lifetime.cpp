// Windows CI ONLY: deterministic native terminal notifier teardown races.
// Do not execute on the user's recording PC; no real package changes.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <chrono>

using Watch=void*;
using Enter=int (__cdecl*)();
using Leave=void (__cdecl*)();
using Open=int (__cdecl*)(Watch*);
using Close=void (__cdecl*)(Watch);
using SetSink=int (__cdecl*)(Watch,void (__cdecl*)(void*),void*);
using Signal=int (__cdecl*)(Watch);
using Delivered=int (__cdecl*)(Watch,uint64_t*);
using Lifetimes=int (__cdecl*)(uint32_t*,uint32_t*,uint32_t*,uint32_t*);
using Globals=void (__cdecl*)(uint64_t*,uint64_t*,uint64_t*);
struct SinkState {
  std::atomic<int> entered{0};
  std::atomic<int> proceed{0};
};
static void __cdecl slow_sink(void *ctx) {
  auto* state=static_cast<SinkState*>(ctx);
  state->entered.fetch_add(1,std::memory_order_relaxed);
  while(state->proceed.load(std::memory_order_acquire)==0)
    Sleep(1);
}
static void __cdecl fast_sink(void *ctx) {
  auto* counter=static_cast<std::atomic<int>*>(ctx);
  counter->fetch_add(1,std::memory_order_relaxed);
}
static bool wait_count(std::atomic<int>& n,int expected,int ms) {
  for(int i=0;i<ms;i++) {
    if(n.load(std::memory_order_acquire)>=expected)return true;
    Sleep(1);
  }
  return false;
}
static void require(bool ok,const char *reason) {
  if(!ok) {
    std::fprintf(stderr,"C545D_NATIVE_SINK_LIFETIME_TEST_FAILURE=%s\n",reason);
    std::exit(9);
  }
}
template<typename T>
static T sym(HMODULE dll,const char* name) {
  auto p=GetProcAddress(dll,name);
  require(p!=nullptr,"required_native_symbol_missing");
  return reinterpret_cast<T>(p);
}
int main(int argc,char** argv) {
  require(argc==2,"expected_one_DLL_path");
  HMODULE dll=LoadLibraryA(argv[1]);
  require(dll!=nullptr,"LoadLibraryA_failed");
  const auto enter=sym<Enter>(dll,"c545d_dedicated_runtime_enter");
  const auto leave=sym<Leave>(dll,"c545d_dedicated_runtime_leave");
  const auto open=sym<Open>(dll,"c545d_dedicated_open");
  const auto close=sym<Close>(dll,"c545d_dedicated_close");
  const auto set=sym<SetSink>(dll,"c545d_dedicated_ci_set_monitor_sink");
  const auto trigger=sym<Signal>(dll,"c545d_dedicated_ci_force_terminal");
  const auto delivered=sym<Delivered>(dll,"c545d_dedicated_ci_monitor_delivered");
  const auto lifetime=sym<Lifetimes>(dll,"c545d_dedicated_ci_lifetime_counters");
  const auto globals=sym<Globals>(dll,"c545d_dedicated_global_counters");
  DWORD start_handles=0,end_handles=0;
  require(GetProcessHandleCount(GetCurrentProcess(),&start_handles)!=FALSE,"handle_count_start");
  require(enter()==0,"CoIncrementMTAUsage_enter_failed");
  {
    Watch token=nullptr;
    require(open(&token)==0&&token!=nullptr,"watch_open");
    SinkState state;
    require(set(token,slow_sink,&state)==0,"listener_register");
    require(trigger(token)==0,"trigger_terminal_for_detach");
    require(wait_count(state.entered,1,5000),"notify_callback_not_entered");
    std::atomic<int> detached{0};
    std::thread detach([&](){
      int rc=set(token,nullptr,nullptr);
      detached.store(rc==0?1:-1,std::memory_order_release);
    });
    Sleep(40);
    require(detached.load()==0,"unregister_returned_before_inflight_callback");
    state.proceed.store(1,std::memory_order_release);
    detach.join();
    require(detached.load()==1,"unregister_failed");
    uint64_t n=0;
    require(delivered(token,&n)==0&&n==1,"unregister_delivery_count_wrong");
    require(trigger(token)==0,"trigger_after_unregistration_failed");
    Sleep(40);
    require(state.entered.load()==1,"callback_after_unregister");
    close(token);
  }
  {
    // Close must likewise join a callback that is already in flight.
    Watch token=nullptr;
    require(open(&token)==0&&token!=nullptr,"second_watch_open");
    SinkState state;
    require(set(token,slow_sink,&state)==0,"second_listener_register");
    require(trigger(token)==0,"trigger_terminal_for_close");
    require(wait_count(state.entered,1,5000),"close_case_callback_not_entered");
    std::atomic<int> closed{0};
    std::thread closer([&](){close(token);closed.store(1,std::memory_order_release);});
    Sleep(40);
    require(closed.load()==0,"close_returned_before_callback_finished");
    state.proceed.store(1,std::memory_order_release);
    closer.join();
    require(closed.load()==1,"close_failed");
    // Stale opaque token cannot be reused to register callbacks.
    require(set(token,fast_sink,nullptr)!=0,"closed_watch_token_reused");
  }
  std::atomic<int> count{0};
  for(int i=0;i<24;i++) {
    Watch token=nullptr;
    require(open(&token)==0&&token!=nullptr,"loop_watch_open");
    require(set(token,fast_sink,&count)==0,"loop_sink_register");
    const int previous=count.load();
    require(trigger(token)==0,"loop_terminal_trigger");
    require(wait_count(count,previous+1,5000),"loop_notify_missing");
    require(set(token,nullptr,nullptr)==0,"loop_unregister");
    close(token);
  }
  leave();
  uint32_t refs=1,opening=1,closing=1,registered=1;
  require(lifetime(&refs,&opening,&closing,&registered)==0,"lifetime_read_failed");
  require(refs==0&&opening==0&&closing==0&&registered==0,"native_live_watch_residue");
  uint64_t regs=0,revs=0,errs=0;
  globals(&regs,&revs,&errs);
  require(regs==revs&&errs==0,"COM_event_revocation_or_errors");
  require(GetProcessHandleCount(GetCurrentProcess(),&end_handles)!=FALSE,"handle_count_end");
  const int delta=static_cast<int>(end_handles)-static_cast<int>(start_handles);
  // Allow small one-time COM/runtime initialization retained by Windows.
  require(delta<=8,"handle_count_growth_above_lazy_init_allowance");
  std::printf("C545D_NATIVE_SINK_LIFETIME_PASS,scans=26,inflight_detach_waits=1,"
              "inflight_close_waits=1,stale_token_rejected=1,"
              "fast_deliveries=%d,registered=%llu,revoked=%llu,"
              "shutdown_errors=%llu,refs=0,opening=0,closing=0,live_watches=0,"
              "handles_delta=%d,CI_only=1\n",
              count.load(),static_cast<unsigned long long>(regs),
              static_cast<unsigned long long>(revs),
              static_cast<unsigned long long>(errs),delta);
  FreeLibrary(dll);
  return 0;
}
