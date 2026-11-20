// CI ONLY: status-only native sink behavior, without real Windows package mutations.
// This tests the synthetic STATUS branch dispatch and teardown, NOT real OS event provenance.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <thread>
using Watch=void*;
using Enter=int (__cdecl*)();
using Leave=void (__cdecl*)();
using Open=int (__cdecl*)(Watch*);
using Close=void (__cdecl*)(Watch);
using SetSink=int (__cdecl*)(Watch,void (__cdecl*)(void*),void*);
using Status=int (__cdecl*)(Watch);
using Delivered=int (__cdecl*)(Watch,uint64_t*);
using Lifetimes=int (__cdecl*)(uint32_t*,uint32_t*,uint32_t*,uint32_t*);
using Globals=void (__cdecl*)(uint64_t*,uint64_t*,uint64_t*);

static void require(bool ok,const char *why) {
  if(!ok) {std::fprintf(stderr,"C545D_STATUS_TEST_ERROR=%s\n",why);std::exit(9);}
}
template<typename T>static T symbol(HMODULE module,const char* name) {
  auto ptr=GetProcAddress(module,name);
  require(ptr!=nullptr,"symbol_not_found");
  return reinterpret_cast<T>(ptr);
}
struct State {std::atomic<int> count{0},entered{0},release{0};};
static void __cdecl ordinary(void *ptr) {
  auto *state=static_cast<State*>(ptr);
  state->count.fetch_add(1,std::memory_order_release);
}
static void __cdecl blocked(void *ptr) {
  auto* state=static_cast<State*>(ptr);
  state->entered.store(1,std::memory_order_release);
  while(!state->release.load(std::memory_order_acquire))Sleep(1);
  state->count.fetch_add(1,std::memory_order_release);
}
static bool await(std::atomic<int> &c,int target) {
  for(int tries=0;tries<5000;tries++) {
    if(c.load(std::memory_order_acquire)>=target)return true;
    Sleep(1);
  }
  return false;
}
int main(int argc,char**argv) {
  require(argc==2,"dll_arg");
  auto dll=LoadLibraryA(argv[1]);require(dll!=nullptr,"load");
  auto enter=symbol<Enter>(dll,"c545d_dedicated_runtime_enter");
  auto leave=symbol<Leave>(dll,"c545d_dedicated_runtime_leave");
  auto open=symbol<Open>(dll,"c545d_dedicated_open");
  auto close=symbol<Close>(dll,"c545d_dedicated_close");
  auto set=symbol<SetSink>(dll,"c545d_dedicated_ci_set_monitor_sink");
  auto status=symbol<Status>(dll,"c545d_dedicated_ci_force_status_only");
  auto delivered=symbol<Delivered>(dll,"c545d_dedicated_ci_monitor_delivered");
  auto lifetime=symbol<Lifetimes>(dll,"c545d_dedicated_ci_lifetime_counters");
  auto global=symbol<Globals>(dll,"c545d_dedicated_global_counters");
  DWORD before=0,after=0;
  require(GetProcessHandleCount(GetCurrentProcess(),&before)!=FALSE,"handles_before");
  require(enter()==0,"MTA_enter");
  State state;
  Watch w=nullptr;
  require(open(&w)==0&&w!=nullptr,"open");
  require(set(w,ordinary,&state)==0,"register");
  require(status(w)==0,"status_only");
  require(await(state.count,1),"missing_status_only_signal");
  uint64_t n=0;require(delivered(w,&n)==0&&n==1,"first_delivery_count");
  require(set(w,nullptr,nullptr)==0,"detach");
  require(status(w)==0,"status_without_sink");
  Sleep(40);
  require(state.count.load()==1,"callback_after_detach");
  close(w);
  require(set(w,ordinary,&state)!=0,"stale_token_register");
  require(status(w)!=0,"stale_token_status");
  // Exact native in-flight unregister contract under a status-only signal:
  Watch second=nullptr;require(open(&second)==0&&second,"second_open");
  State slow;
  require(set(second,blocked,&slow)==0,"register_blocking_sink");
  require(status(second)==0,"status_with_blocking_sink");
  require(await(slow.entered,1),"blocking_sink_not_entered");
  std::atomic<int> detached{0};
  std::thread t([&]{
    detached.store(set(second,nullptr,nullptr)==0?1:-1,std::memory_order_release);
  });
  Sleep(40);
  require(detached.load()==0,"detached_while_callback_running");
  slow.release.store(1,std::memory_order_release);
  t.join();
  require(detached.load()==1&&slow.count.load()==1,"blocked_detach_not_completed");
  close(second);
  leave();
  uint32_t refs=9,opens=9,closes=9,live=9;
  require(lifetime(&refs,&opens,&closes,&live)==0,"lifetime");
  require(refs==0&&opens==0&&closes==0&&live==0,"native_remaining_resources");
  uint64_t registrations=0,revocations=0,errors=0;
  global(&registrations,&revocations,&errors);
  require(registrations==revocations&&errors==0,"COM_revocation_or_shutdown_error");
  require(GetProcessHandleCount(GetCurrentProcess(),&after)!=FALSE,"handles_after");
  std::printf("C545D_STATUS_ONLY_SYNTHETIC_CI_PASS,"
              "synthetic_status_notifications=2,no_listener_callback_after_detach=1,"
              "stale_token_rejected=1,inflight_detach_waited=1,"
              "COM_registered=%llu,COM_revoked=%llu,shutdown_errors=0,"
              "refs=0,pending_opens=0,pending_closes=0,live_watches=0,"
              "initial_handles=%lu,final_handles=%lu,"
              "OS_PackageStatusChanged_NOT_observed=1,CI_only=1\n",
              static_cast<unsigned long long>(registrations),
              static_cast<unsigned long long>(revocations),
              static_cast<unsigned long>(before),static_cast<unsigned long>(after));
  FreeLibrary(dll);
  return 0;
}
