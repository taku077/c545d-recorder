// CI-only C++/WinRT event bridge to exercise a C-compatible GIO integration.
#define WIN32_LEAN_AND_MEAN
#define C545D_BRIDGE_BUILD
#include "c545d_winrt_event_bridge.h"
#include <windows.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.ApplicationModel.h>
#include <atomic>
#include <cstdint>
#include <memory>
#include <new>
#include <vector>

using winrt::Windows::ApplicationModel::PackageCatalog;

namespace {
struct EventState final {
  std::atomic<uint64_t> generation{1};
  std::atomic<bool> active{true};
};

bool add_user_languages(uint64_t& digest) {
  ULONG count=0, chars=0;
  if (!GetUserPreferredUILanguages(MUI_LANGUAGE_NAME,&count,nullptr,&chars) ||
      count == 0 || chars == 0 || chars > 16384) return false;
  std::vector<wchar_t> values(chars);
  if (!GetUserPreferredUILanguages(MUI_LANGUAGE_NAME,&count,values.data(),&chars))
    return false;
  for (ULONG i=0; i<chars; ++i) {
    const auto v=static_cast<uint16_t>(values[i]);
    digest ^= (v & 0xffu);
    digest *= 1099511628211ULL;
    digest ^= (v >> 8);
    digest *= 1099511628211ULL;
  }
  return true;
}
bool add_thread_languages(uint64_t& digest) {
  ULONG count=0, chars=0;
  if (!GetThreadPreferredUILanguages(MUI_LANGUAGE_NAME,&count,nullptr,&chars) ||
      count == 0 || chars == 0 || chars > 16384) return false;
  std::vector<wchar_t> values(chars);
  if (!GetThreadPreferredUILanguages(MUI_LANGUAGE_NAME,&count,values.data(),&chars))
    return false;
  // The delimiter distinguishes user + thread MULTI_SZ boundaries.
  digest ^= 0xff;
  digest *= 1099511628211ULL;
  for (ULONG i=0; i<chars; ++i) {
    const auto v=static_cast<uint16_t>(values[i]);
    digest ^= (v & 0xffu);
    digest *= 1099511628211ULL;
    digest ^= (v >> 8);
    digest *= 1099511628211ULL;
  }
  return true;
}
}

struct c545d_winrt_watch {
  std::shared_ptr<EventState> state = std::make_shared<EventState>();
  PackageCatalog catalog{nullptr};
  winrt::event_token installing{}, updating{}, uninstalling{}, status{};
  bool have_installing=false, have_updating=false;
  bool have_uninstalling=false, have_status=false;

  c545d_winrt_watch() {
    catalog = PackageCatalog::OpenForCurrentUser();
    // Weak capture + atomic active flag ensure late callbacks cannot use a
    // destroyed watch. No GObject or GMutex is touched by event threads.
    std::weak_ptr<EventState> weak = state;
    auto callback = [weak](auto const&, auto const&) noexcept {
      if (auto shared = weak.lock())
        if (shared->active.load(std::memory_order_acquire))
          shared->generation.fetch_add(1, std::memory_order_acq_rel);
    };
    installing = catalog.PackageInstalling(callback);
    have_installing=true;
    updating = catalog.PackageUpdating(callback);
    have_updating=true;
    uninstalling = catalog.PackageUninstalling(callback);
    have_uninstalling=true;
    status = catalog.PackageStatusChanged(callback);
    have_status=true;
  }

  ~c545d_winrt_watch() noexcept {
    state->active.store(false,std::memory_order_release);
    try { if(have_installing) catalog.PackageInstalling(installing); } catch(...) {}
    try { if(have_updating) catalog.PackageUpdating(updating); } catch(...) {}
    try { if(have_uninstalling) catalog.PackageUninstalling(uninstalling); } catch(...) {}
    try { if(have_status) catalog.PackageStatusChanged(status); } catch(...) {}
  }
};

extern "C" int c545d_watch_open(c545d_winrt_watch **out) {
  if (!out) return 2;
  *out=nullptr;
  try {
    winrt::init_apartment(winrt::apartment_type::single_threaded);
    try {
      *out=new c545d_winrt_watch;
      return 0;
    } catch (...) {
      winrt::uninit_apartment();
      return 3;
    }
  } catch (...) { return 4; }
}
extern "C" void c545d_watch_close(c545d_winrt_watch *watch) {
  if (!watch) return;
  delete watch; // revoke every event token while state is still alive
  winrt::uninit_apartment();
}
extern "C" int c545d_watch_snapshot(c545d_winrt_watch *watch,
                                       uint64_t *generation,uint64_t *lang_hash) {
  if (!watch || !generation || !lang_hash) return 2;
  try {
    uint64_t digest=14695981039346656037ULL;
    if (!add_user_languages(digest) || !add_thread_languages(digest))
      return 3; // Fail closed: caller bypasses cache
    const auto state=watch->state;
    if (!state->active.load(std::memory_order_acquire)) return 4;
    *generation=state->generation.load(std::memory_order_acquire);
    *lang_hash=digest;
    return 0;
  } catch (...) { return 5; }
}
extern "C" int c545d_watch_inject_synthetic(c545d_winrt_watch *watch) {
  if (!watch || !watch->state->active.load(std::memory_order_acquire))
    return 2;
  watch->state->generation.fetch_add(1,std::memory_order_acq_rel);
  return 0;
}
