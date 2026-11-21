// CI ONLY: deterministic failure AFTER a healthy C++/WinRT watcher starts.
// No real package/registry/camera mutations. The owner thread revokes COM.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

using Watch=void*;
using Enter=int (__cdecl*)();
using Leave=void (__cdecl*)();
using Open=int (__cdecl*)(Watch*);
using Close=void (__cdecl*)(Watch);
using Snapshot=int (__cdecl*)(Watch,uint64_t*,uint64_t*);
using Lifetimes=int (__cdecl*)(uint32_t*,uint32_t*,uint32_t*,uint32_t*);
using Globals=void (__cdecl*)(uint64_t*,uint64_t*,uint64_t*);

static void check(bool v,const char *reason) {
  if(!v) { std::fprintf(stderr,"C545D_RUNTIME_DROP_FAILURE=%s\n",reason);std::exit(8); }
}
template<class T>static T sym(HMODULE dll,const char *name) {
  auto fn=GetProcAddress(dll,name);
  check(fn!=nullptr,"symbol");return reinterpret_cast<T>(fn);
}
int main(int argc,char **argv) {
  check(argc==2,"dll_arg");
  const auto dll=LoadLibraryA(argv[1]);check(dll!=nullptr,"load");
  auto enter=sym<Enter>(dll,"c545d_dedicated_runtime_enter");
  auto leave=sym<Leave>(dll,"c545d_dedicated_runtime_leave");
  auto open=sym<Open>(dll,"c545d_dedicated_open");
  auto close=sym<Close>(dll,"c545d_dedicated_close");
  auto snapshot=sym<Snapshot>(dll,"c545d_dedicated_snapshot");
  auto lifetime=sym<Lifetimes>(dll,"c545d_dedicated_ci_lifetime_counters");
  auto globals=sym<Globals>(dll,"c545d_dedicated_global_counters");

  DWORD handles_before=0,handles_after=0;
  check(GetProcessHandleCount(GetCurrentProcess(),&handles_before)!=FALSE,"handles_before");
  check(enter()==0,"mta_enter");
  Watch watch=nullptr;check(open(&watch)==0&&watch!=nullptr,"open");
  uint64_t gen=0,locale=0;
  check(snapshot(watch,&gen,&locale)==0&&gen>0,"initial_snapshot");
  check(SetEnvironmentVariableW(L"C545D_CI_FORCE_RUNTIME_UNAVAILABLE",L"1")!=FALSE,"arm_fault");
  uint64_t failed_gen=0xBAD,failed_locale=0xBAD;
  check(snapshot(watch,&failed_gen,&failed_locale)==12,"runtime_snapshot_fail_code");
  check(failed_gen==0xBAD&&failed_locale==0xBAD,"returned_invalid_epoch");
  check(SetEnvironmentVariableW(L"C545D_CI_FORCE_RUNTIME_UNAVAILABLE",nullptr)!=FALSE,"disarm_fault");
  check(snapshot(watch,&gen,&locale)!=0,"inactive_watch_cacheable");

  uint64_t registrations=0,revocations=0,shutdown_errors=0;
  bool revoked=false;
  for(int i=0;i<4000;i++) {
    globals(&registrations,&revocations,&shutdown_errors);
    if(registrations==4 && revocations==4){revoked=true;break;}
    Sleep(1);
  }
  check(revoked,"owner_MTA_revocation_not_complete");
  check(shutdown_errors==0,"owner_MTA_shutdown_error");
  close(watch);
  leave();
  uint32_t refs=99,opens=99,closes=99,live=99;
  check(lifetime(&refs,&opens,&closes,&live)==0,"lifetime_query");
  check(refs==0&&opens==0&&closes==0&&live==0,"native_resources_retained");
  check(GetProcessHandleCount(GetCurrentProcess(),&handles_after)!=FALSE,"handles_after");
  std::printf("C545D_RUNTIME_DROP_NATIVE_CI_PASS,initial_snapshot=1,"
              "faulted_snapshot_rejected=1,no_invalid_epoch_returned=1,"
              "COM_registered=%llu,COM_revoked=%llu,shutdown_errors=0,"
              "refs=0,pending_opens=0,pending_closes=0,live_watches=0,"
              "initial_handles=%lu,final_handles=%lu,"
              "real_OS_failure_NOT_observed=1,CI_only=1\n",
              static_cast<unsigned long long>(registrations),
              static_cast<unsigned long long>(revocations),
              static_cast<unsigned long>(handles_before),
              static_cast<unsigned long>(handles_after));
  FreeLibrary(dll);
  return 0;
}
