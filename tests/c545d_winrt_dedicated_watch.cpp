// Windows 2022 CI ONLY. Prototype fail-closed WinRT package notifications on
// a private MTA thread. No GIO integration or production DLL is generated.
#define WIN32_LEAN_AND_MEAN
#define C545D_DEDICATED_BUILD
#include "c545d_winrt_dedicated_watch.h"
#include <windows.h>
#include <objbase.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.ApplicationModel.h>
#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <memory>
#include <mutex>
#include <new>
#include <stdexcept>
#include <string>
#include <thread>
#include <type_traits>
#include <unordered_map>
#include <vector>

namespace {
std::atomic<uint64_t> g_registration_count{0};
std::atomic<uint64_t> g_revocation_count{0};
std::atomic<uint64_t> g_shutdown_errors{0};
std::mutex g_mta_lock;
CO_MTA_USAGE_COOKIE g_mta_cookie{};
unsigned g_mta_references=0;
// Includes windows where a watch is being constructed or its worker is
// being joined after the opaque token was retired. Guarded by g_mta_lock.
unsigned g_pending_opens=0;
unsigned g_pending_closes=0;
// A C ABI handle is an ever-increasing opaque token, never a raw object
// address. The table owns one shared reference; each operation takes a short
// lease under the mutex before accessing native state. Closing removes the
// token first, so concurrent calls fail closed rather than dereference freed
// memory. Tokens cannot suffer allocator address-reuse ABA after close.
struct WatchTable {
  std::mutex lock;
  std::unordered_map<uintptr_t,std::shared_ptr<c545d_dedicated_watch>> watches;
  std::atomic<uintptr_t> next{1};
};
// The GIO bridge currently invokes close from a process-exit handler in
// another DLL. A destructible DLL-global unordered_map can already have
// completed CRT teardown when that late close arrives. Keep only this tiny
// empty-by-close registry alive until OS process reclamation, avoiding a
// static-destruction-order UAF. Never allocate one table per open/close.
WatchTable& watch_table() {
  static WatchTable* const table=new WatchTable;
  return *table;
}

// Test-only deterministic scheduler hold. No delay outside an explicitly
// opted-in disposable CI process; the production-like path is unchanged.
void ci_lifetime_test_pause(const wchar_t* flag) noexcept {
  wchar_t enabled[4]{};
  if(GetEnvironmentVariableW(flag,enabled,4)==1 && enabled[0]==L'1')
    Sleep(80);
}

struct WatchState {
  std::atomic<uint64_t> generation{1};
  std::atomic<bool> active{true};
  // Diagnostics only. These counters do not control the cache or alter
  // notification behavior. The real OS can deliver several progress events.
  std::atomic<uint64_t> ci_install_complete{0};
  std::atomic<uint64_t> ci_update_complete{0};
  std::atomic<uint64_t> ci_uninstall_complete{0};
  // Diagnostic-only fault injection and fail-closed exception observability.
  // Normal production-like operation keeps the injector false.
  std::atomic<bool> ci_throw_on_next_matching_event{false};
  std::atomic<uint64_t> ci_callback_exceptions{0};
};

bool hash_language_list(bool user, uint64_t& digest) {
  ULONG count=0, chars=0;
  const auto get = [&](PWSTR target) {
    if (user) return GetUserPreferredUILanguages(MUI_LANGUAGE_NAME,&count,target,&chars);
    return GetThreadPreferredUILanguages(MUI_LANGUAGE_NAME,&count,target,&chars);
  };
  if(!get(nullptr) || count == 0 || chars == 0 || chars > 16384)
    return false;
  std::vector<wchar_t> buffer(chars);
  if(!get(buffer.data())) return false;
  digest ^= user ? uint64_t{0x19} : uint64_t{0xa9};
  digest *= 1099511628211ULL;
  for(ULONG i=0;i<chars;i++) {
    const auto word=static_cast<uint16_t>(buffer[i]);
    digest ^= (word & 255u);
    digest *= 1099511628211ULL;
    digest ^= (word >> 8u);
    digest *= 1099511628211ULL;
  }
  return true;
}
}

struct c545d_dedicated_watch {
  std::shared_ptr<WatchState> state=std::make_shared<WatchState>();
  std::thread worker;
  std::mutex lock;
  std::mutex join_lock;
  std::condition_variable cv;
  bool started=false, ready=false, stop=false;

  c545d_dedicated_watch() {
    worker=std::thread([this] { run(); });
    std::unique_lock<std::mutex> guard(lock);
    cv.wait(guard,[this]{return started;});
    const bool ok=ready;
    guard.unlock();
    if (!ok) {
      worker.join();
      throw std::runtime_error("WinRT MTA event subscriptions not available");
    }
  }

  void run() noexcept {
    using winrt::Windows::ApplicationModel::PackageCatalog;
    bool apartment=false, initialized=false;
    try {
      // The only thread that ever owns catalog and token revocation.
      // MTA permits blocking without starving an STA message pump.
      winrt::init_apartment(winrt::apartment_type::multi_threaded);
      apartment=true;
      auto catalog=PackageCatalog::OpenForCurrentUser();
      if (!catalog) throw std::runtime_error("current-user catalog absent");
      std::weak_ptr<WatchState> weak=state;
      // CI-only event provenance control. If unset, preserve original
      // production-like semantics of reacting to ANY current-user package.
      // With a filter, only the ephemeral synthetic package can advance
      // the observed generation; unrelated runner activity is excluded.
      wchar_t ci_name_buf[160] = {};
      const DWORD ci_len=GetEnvironmentVariableW(
          L"C545D_CI_EVENT_PACKAGE_NAME",ci_name_buf,160);
      if(ci_len>=160)throw std::runtime_error("CI event filter too long");
      const std::wstring ci_name(ci_name_buf,ci_len);
      auto callback=[weak,ci_name](auto const&,auto const& args) noexcept {
        if(auto p=weak.lock()) {
          if(!p->active.load(std::memory_order_acquire)) return;
          if(!ci_name.empty()) {
            // A test filter may only attribute events for a verifiable
            // identity. Never count unrelated runner package events.
            try {
              using Args=std::decay_t<decltype(args)>;
              const auto pkg=[&]() {
                if constexpr(std::is_same_v<
                    Args,winrt::Windows::ApplicationModel::PackageUpdatingEventArgs>)
                  return args.TargetPackage();
                else
                  return args.Package();
              }();
              if(!pkg || std::wstring(pkg.Id().Name().c_str())!=ci_name)
                return;
            } catch(...) {
              p->ci_callback_exceptions.fetch_add(1,std::memory_order_relaxed);
              return; // Attribution unavailable, never claim a CI package.
            }
          }
          // C++/WinRT projected IsComplete accessors can throw hresult_error.
          // NEVER allow an exception to escape this noexcept OS callback.
          // Even on a failed property read, advance the cache generation:
          // the package may have changed and returning an old name is unsafe.
          try {
            if(p->ci_throw_on_next_matching_event.exchange(
                  false,std::memory_order_acq_rel))
              throw winrt::hresult_error(E_FAIL); // opt-in CI fault only
            using ArgsType=std::decay_t<decltype(args)>;
            if constexpr(std::is_same_v<
                ArgsType,winrt::Windows::ApplicationModel::PackageInstallingEventArgs>) {
              if(args.IsComplete())
                p->ci_install_complete.fetch_add(1,std::memory_order_relaxed);
            } else if constexpr(std::is_same_v<
                ArgsType,winrt::Windows::ApplicationModel::PackageUpdatingEventArgs>) {
              if(args.IsComplete())
                p->ci_update_complete.fetch_add(1,std::memory_order_relaxed);
            } else if constexpr(std::is_same_v<
                ArgsType,winrt::Windows::ApplicationModel::PackageUninstallingEventArgs>) {
              if(args.IsComplete())
                p->ci_uninstall_complete.fetch_add(1,std::memory_order_relaxed);
            }
          } catch(...) {
            p->ci_callback_exceptions.fetch_add(1,std::memory_order_relaxed);
          }
          p->generation.fetch_add(1,std::memory_order_acq_rel);
        }
      };
      // Partial subscription failures are safely revoked in stack unwind.
      auto i=catalog.PackageInstalling(winrt::auto_revoke,callback);
      auto u=catalog.PackageUpdating(winrt::auto_revoke,callback);
      auto d=catalog.PackageUninstalling(winrt::auto_revoke,callback);
      auto s=catalog.PackageStatusChanged(winrt::auto_revoke,callback);
      g_registration_count.fetch_add(4,std::memory_order_relaxed);
      {
        std::lock_guard<std::mutex> guard(lock);
        ready=true;
        started=true;
      }
      cv.notify_all();
      {
        std::unique_lock<std::mutex> guard(lock);
        cv.wait(guard,[this]{return stop;});
      }
      state->active.store(false,std::memory_order_release);
      // Explicit revoke and count on this *same* owner thread.
      i.revoke();u.revoke();d.revoke();s.revoke();
      g_revocation_count.fetch_add(4,std::memory_order_relaxed);
      initialized=true;
    } catch(...) {
      state->active.store(false,std::memory_order_release);
      g_shutdown_errors.fetch_add(1,std::memory_order_relaxed);
      // Publish a creation failure (or count an unexpected exit).
      {
        std::lock_guard<std::mutex> guard(lock);
        if(!started) {
          ready=false;
          started=true;
        }
      }
      cv.notify_all();
    }
    if(apartment)winrt::uninit_apartment();
    if(!initialized)state->active.store(false,std::memory_order_release);
  }

  void stop_and_join() noexcept {
    // Publishing inactive prevents newly entering callbacks from touching
    // native state even if an asynchronous notification is still in-flight.
    state->active.store(false,std::memory_order_release);
    {
      std::lock_guard<std::mutex> guard(lock);
      stop=true;
    }
    cv.notify_all();
    // Close must wait for MTA handler revocation regardless of outstanding
    // snapshot leases; destructor may call this again after the last reader.
    std::lock_guard<std::mutex> join_guard(join_lock);
    if(worker.joinable())worker.join();
  }

  ~c545d_dedicated_watch() noexcept {
    stop_and_join();
  }
};

static std::shared_ptr<c545d_dedicated_watch>
c545d_watch_lease(c545d_dedicated_watch* token) {
  if(!token)return {};
  std::lock_guard<std::mutex> guard(watch_table().lock);
  const auto it=watch_table().watches.find(reinterpret_cast<uintptr_t>(token));
  return it==watch_table().watches.end()?std::shared_ptr<c545d_dedicated_watch>{}:it->second;
}

extern "C" int c545d_dedicated_runtime_enter(void) {
  std::lock_guard<std::mutex> guard(g_mta_lock);
  if(g_mta_references==0) {
    const auto hr=CoIncrementMTAUsage(&g_mta_cookie);
    if(FAILED(hr))return 2;
  }
  ++g_mta_references;
  return 0;
}
extern "C" void c545d_dedicated_runtime_leave(void) {
  std::lock_guard<std::mutex> guard(g_mta_lock);
  if(g_mta_references==0)return;
  if(g_mta_references==1) {
    // Protect *transitions* too: an opening watch is not yet in the table,
    // and close removes its token before revocation/join completes.
    // A concurrent leave cannot retire the last COM MTA usage in either gap.
    if(g_pending_opens || g_pending_closes)return;
    std::lock_guard<std::mutex> watches(watch_table().lock);
    if(!watch_table().watches.empty())return;
  }
  if(--g_mta_references==0) {
    CoDecrementMTAUsage(g_mta_cookie);
    g_mta_cookie=CO_MTA_USAGE_COOKIE{};
  }
}
extern "C" int c545d_dedicated_open(c545d_dedicated_watch** out) {
  if(!out)return 2;
  *out=nullptr;
  {
    std::lock_guard<std::mutex> guard(g_mta_lock);
    if(g_mta_references==0)return 7; // Enter COM MTA before opening.
    ++g_pending_opens; // Reserve before releasing g_mta_lock.
  }
  ci_lifetime_test_pause(L"C545D_CI_PAUSE_WATCH_OPEN");
  int result=3;
  try {
    auto owned=std::make_shared<c545d_dedicated_watch>();
    std::lock_guard<std::mutex> guard(watch_table().lock);
    const auto id=watch_table().next.fetch_add(1,std::memory_order_relaxed);
    if(id!=0) {
      const auto inserted=watch_table().watches.emplace(id,std::move(owned));
      if(inserted.second) {
        *out=reinterpret_cast<c545d_dedicated_watch*>(id);
        result=0;
      }
    }
  } catch(...) {
    // Failed construction or registration must release the reservation too.
  }
  {
    std::lock_guard<std::mutex> guard(g_mta_lock);
    --g_pending_opens;
  }
  return result;
}
extern "C" int c545d_dedicated_snapshot(
    c545d_dedicated_watch* p,uint64_t* gen,uint64_t* locale) {
  if(!p || !gen || !locale)return 2;
  try {
    auto watch=c545d_watch_lease(p);
    if(!watch)return 3;
    auto state=watch->state;
    if(!state->active.load(std::memory_order_acquire))return 3;
    const auto before=state->generation.load(std::memory_order_acquire);
    uint64_t hash=14695981039346656037ULL;
    if(!hash_language_list(true,hash) || !hash_language_list(false,hash))
      return 4;
    const auto after=state->generation.load(std::memory_order_acquire);
    if(before!=after || !state->active.load(std::memory_order_acquire))
      return 5; // retry rather than mix language and generation data
    *gen=after;
    *locale=hash;
    return 0;
  }catch(...) {return 6;}
}
extern "C" int c545d_dedicated_synthetic_event(c545d_dedicated_watch* p) {
  auto watch=c545d_watch_lease(p);
  if(!watch || !watch->state->active.load(std::memory_order_acquire))return 2;
  watch->state->generation.fetch_add(1,std::memory_order_acq_rel);
  return 0;
}
extern "C" void c545d_dedicated_close(c545d_dedicated_watch* p) {
  if(!p)return;
  std::shared_ptr<c545d_dedicated_watch> owned;
  {
    // Same lock order as runtime_leave(): MTA first, then watch table.
    // Mark the closing transition *before* publishing an empty table.
    std::lock_guard<std::mutex> mta_guard(g_mta_lock);
    std::lock_guard<std::mutex> table_guard(watch_table().lock);
    const auto it=watch_table().watches.find(reinterpret_cast<uintptr_t>(p));
    if(it==watch_table().watches.end())return;
    ++g_pending_closes;
    owned=std::move(it->second);
    watch_table().watches.erase(it);
  }
  ci_lifetime_test_pause(L"C545D_CI_PAUSE_WATCH_CLOSE");
  // The last MTA usage stays alive until owner-thread callback revocation
  // and join complete, despite removal of the public token.
  owned->stop_and_join();
  {
    std::lock_guard<std::mutex> guard(g_mta_lock);
    --g_pending_closes;
  }
}
extern "C" int c545d_dedicated_ci_completion_counters(
    c545d_dedicated_watch* p, uint64_t* install_done,
    uint64_t* update_done, uint64_t* uninstall_done) {
  if(!p || !install_done || !update_done || !uninstall_done) return 2;
  auto watch=c545d_watch_lease(p);
  if(!watch)return 3;
  auto state=watch->state;
  *install_done=state->ci_install_complete.load(std::memory_order_acquire);
  *update_done=state->ci_update_complete.load(std::memory_order_acquire);
  *uninstall_done=state->ci_uninstall_complete.load(std::memory_order_acquire);
  return 0;
}

extern "C" int c545d_dedicated_ci_arm_callback_exception(
    c545d_dedicated_watch* p) {
  auto watch=c545d_watch_lease(p);
  if(!watch || !watch->state->active.load(std::memory_order_acquire))
    return 3;
  watch->state->ci_throw_on_next_matching_event.store(
      true,std::memory_order_release);
  return 0;
}

extern "C" int c545d_dedicated_ci_callback_exception_count(
    c545d_dedicated_watch* p, uint64_t* faults) {
  if(!faults)return 2;
  auto watch=c545d_watch_lease(p);
  if(!watch)return 3;
  *faults=watch->state->ci_callback_exceptions.load(
      std::memory_order_acquire);
  return 0;
}

extern "C" int c545d_dedicated_ci_lifetime_counters(
    uint32_t* references,uint32_t* opening,uint32_t* closing,
    uint32_t* registered) {
  if(!references || !opening || !closing || !registered)return 2;
  // Read the two tables under their established global lock order.
  std::lock_guard<std::mutex> guard(g_mta_lock);
  std::lock_guard<std::mutex> table_guard(watch_table().lock);
  *references=g_mta_references;
  *opening=g_pending_opens;
  *closing=g_pending_closes;
  *registered=static_cast<uint32_t>(watch_table().watches.size());
  return 0;
}

extern "C" void c545d_dedicated_global_counters(
    uint64_t* registered,uint64_t* revoked,uint64_t* shutdown_errors) {
  if(registered)*registered=g_registration_count.load(std::memory_order_acquire);
  if(revoked)*revoked=g_revocation_count.load(std::memory_order_acquire);
  if(shutdown_errors)*shutdown_errors=g_shutdown_errors.load(std::memory_order_acquire);
}
