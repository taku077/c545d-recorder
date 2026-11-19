// Windows 2022 CI ONLY. Prototype fail-closed WinRT package notifications on
// a private MTA thread. No GIO integration or production DLL is generated.
#define WIN32_LEAN_AND_MEAN
#define C545D_DEDICATED_BUILD
#include "c545d_winrt_dedicated_watch.h"
#include <windows.h>
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
#include <thread>
#include <vector>

namespace {
std::atomic<uint64_t> g_registration_count{0};
std::atomic<uint64_t> g_revocation_count{0};
std::atomic<uint64_t> g_shutdown_errors{0};

struct WatchState {
  std::atomic<uint64_t> generation{1};
  std::atomic<bool> active{true};
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
      auto callback=[weak](auto const&,auto const&) noexcept {
        if(auto p=weak.lock()) {
          if(p->active.load(std::memory_order_acquire))
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

  ~c545d_dedicated_watch() noexcept {
    state->active.store(false,std::memory_order_release);
    {
      std::lock_guard<std::mutex> guard(lock);
      stop=true;
    }
    cv.notify_all();
    if(worker.joinable())worker.join();
  }
};

extern "C" int c545d_dedicated_open(c545d_dedicated_watch** out) {
  if(!out)return 2;
  *out=nullptr;
  try {
    *out=new c545d_dedicated_watch;
    return 0;
  } catch(...) {return 3;}
}
extern "C" int c545d_dedicated_snapshot(
    c545d_dedicated_watch* p,uint64_t* gen,uint64_t* locale) {
  if(!p || !gen || !locale)return 2;
  try {
    auto state=p->state;
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
  if(!p || !p->state->active.load(std::memory_order_acquire))return 2;
  p->state->generation.fetch_add(1,std::memory_order_acq_rel);
  return 0;
}
extern "C" void c545d_dedicated_close(c545d_dedicated_watch* p) {
  delete p;
}
extern "C" void c545d_dedicated_global_counters(
    uint64_t* registered,uint64_t* revoked,uint64_t* shutdown_errors) {
  if(registered)*registered=g_registration_count.load(std::memory_order_acquire);
  if(revoked)*revoked=g_revocation_count.load(std::memory_order_acquire);
  if(shutdown_errors)*shutdown_errors=g_shutdown_errors.load(std::memory_order_acquire);
}
