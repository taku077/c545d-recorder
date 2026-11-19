// CI-only ownership and invalidation model for *exact* WinRT DisplayName.
// Never change a real package, UI language, user registry key or camera.
// This is NOT yet a GLib production integration.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.ApplicationModel.h>
#include <winrt/Windows.Management.Deployment.h>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <exception>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

using winrt::Windows::ApplicationModel::PackageCatalog;
using winrt::Windows::Management::Deployment::PackageManager;

class EventGeneration {
 public:
  uint64_t snapshot() const noexcept { return epoch_.load(std::memory_order_acquire); }
  void invalidate() noexcept { epoch_.fetch_add(1, std::memory_order_acq_rel); }
 private:
  std::atomic<uint64_t> epoch_{1};
};

// Deterministic cache model. A real GLib integration must preserve these
// guards and additionally handle subscription failure and OS language changes.
class DisplayNameCache {
 public:
  explicit DisplayNameCache(EventGeneration& generation, size_t limit = 1024)
      : generation_(generation), limit_(limit) {
    if (limit == 0) throw std::invalid_argument("zero capacity");
  }

  bool lookup(const std::wstring& full_name, const std::wstring& languages,
              std::wstring& output) {
    std::lock_guard<std::mutex> guard(mutex_);
    if (!enabled_) return false; // Original WinRT getter must run uncached.
    synchronize(languages);
    auto it = values_.find(full_name);
    if (it == values_.end()) {
      ++misses_;
      return false;
    }
    output = it->second; // Own an independent copy, not an OS pointer.
    ++hits_;
    return true;
  }

  // Caller records the event generation BEFORE reading WinRT; it may be stale.
  // Reject an in-flight WinRT result if a notification occurred meanwhile.
  bool remember(const std::wstring& full_name, const std::wstring& display,
                const std::wstring& languages, uint64_t read_generation) {
    std::lock_guard<std::mutex> guard(mutex_);
    if (!enabled_) return false; // Subscription/locale query failure: fail closed.
    synchronize(languages);
    if (generation_.snapshot() != read_generation ||
        languages_ != languages) {
      ++rejected_stale_;
      return false;
    }
    if (values_.find(full_name) == values_.end() && values_.size() >= limit_) {
      ++rejected_capacity_;
      return false; // Original API fallback, never unbounded growth.
    }
    values_[full_name] = display; // empty string is a valid positive cache entry.
    return true;
  }

  void disable() {
    std::lock_guard<std::mutex> guard(mutex_);
    enabled_ = false;
    values_.clear(); // no indefinitely stale entries if event subscription fails
  }

  size_t count() const {
    std::lock_guard<std::mutex> guard(mutex_);
    return values_.size();
  }
  unsigned long long invalidations() const {
    std::lock_guard<std::mutex> guard(mutex_);
    return invalidations_;
  }
  unsigned long long stale_rejections() const {
    std::lock_guard<std::mutex> guard(mutex_);
    return rejected_stale_;
  }
  unsigned long long capacity_rejections() const {
    std::lock_guard<std::mutex> guard(mutex_);
    return rejected_capacity_;
  }
  unsigned long long hits() const {
    std::lock_guard<std::mutex> guard(mutex_);
    return hits_;
  }

 private:
  void synchronize(const std::wstring& languages) {
    const auto epoch = generation_.snapshot();
    if (current_epoch_ != epoch || languages_ != languages) {
      if (current_epoch_ != 0) ++invalidations_;
      values_.clear(); // owned strings freed without racing active lookup copies.
      languages_ = languages;
      current_epoch_ = epoch;
    }
  }

  EventGeneration& generation_;
  const size_t limit_;
  mutable std::mutex mutex_;
  bool enabled_ = true;
  std::unordered_map<std::wstring, std::wstring> values_;
  std::wstring languages_;
  uint64_t current_epoch_ = 0;
  unsigned long long hits_ = 0, misses_ = 0, invalidations_ = 0;
  unsigned long long rejected_stale_ = 0, rejected_capacity_ = 0;
};

static void require(bool value, const char* message) {
  if (!value) throw std::runtime_error(message);
}

static std::wstring preferred_user_languages() {
  ULONG count = 0, chars = 0;
  if (!GetUserPreferredUILanguages(MUI_LANGUAGE_NAME, &count, nullptr, &chars) ||
      count == 0 || chars == 0 || chars > 16384)
    throw std::runtime_error("invalid user UI language census");
  std::vector<wchar_t> buffer(chars);
  if (!GetUserPreferredUILanguages(MUI_LANGUAGE_NAME, &count,
                                    buffer.data(), &chars))
    throw std::runtime_error("failed user UI language census");
  return std::wstring(buffer.data(), chars); // include MULTI_SZ's embedded NULs
}

static std::wstring effective_language_fingerprint() {
  // Package resource resolution can be affected by thread/process preferences,
  // not only the per-user list. Include both; preserve MULTI_SZ separators.
  const auto user = preferred_user_languages();
  ULONG count = 0, chars = 0;
  if (!GetThreadPreferredUILanguages(MUI_LANGUAGE_NAME, &count, nullptr, &chars) ||
      count == 0 || chars == 0 || chars > 16384)
    throw std::runtime_error("invalid effective thread UI language census");
  std::vector<wchar_t> buffer(chars);
  if (!GetThreadPreferredUILanguages(MUI_LANGUAGE_NAME, &count,
                                      buffer.data(), &chars))
    throw std::runtime_error("failed effective thread UI language census");
  std::wstring fingerprint = user;
  fingerprint.push_back(L'\x1e'); // disambiguate user/thread MULTI_SZ fields
  fingerprint.append(buffer.data(), chars);
  return fingerprint;
}

static void deterministic_scenarios(EventGeneration& gen) {
  DisplayNameCache cache(gen, 4);
  std::wstring empty, output;
  const std::wstring en = L"en-US", ja = L"ja-JP";
  const auto gen_before = gen.snapshot();
  require(!cache.lookup(L"pkg-a", en, output), "initial miss expected");
  require(cache.remember(L"pkg-a", empty, en, gen_before),
          "empty WinRT HSTRING must be cacheable");
  require(cache.lookup(L"pkg-a", en, output) && output.empty(),
          "cached empty DisplayName must remain empty, not Package.Name");

  const auto in_flight = gen.snapshot();
  gen.invalidate(); // simulate package installation/update/remove event
  require(!cache.lookup(L"pkg-a", en, output), "package event must evict cache");
  require(!cache.remember(L"pkg-a", L"stale", en, in_flight),
          "stale in-flight getter must not re-populate invalidated cache");
  require(cache.remember(L"pkg-a", L"display-en", en, gen.snapshot()),
          "new generation must allow fresh display");
  require(cache.lookup(L"pkg-a", en, output) && output == L"display-en",
          "original display value not preserved after refresh");
  require(!cache.lookup(L"pkg-a", ja, output),
          "preferred language change must evict old localized display");
  require(cache.remember(L"pkg-a", L"display-ja", ja, gen.snapshot()),
          "new language display cache failed");
  require(cache.lookup(L"pkg-a", ja, output) && output == L"display-ja",
          "language refresh failed");
  require(cache.remember(L"pkg-b", L"B", ja, gen.snapshot()), "slot B failed");
  require(cache.remember(L"pkg-c", L"C", ja, gen.snapshot()), "slot C failed");
  require(cache.remember(L"pkg-d", L"D", ja, gen.snapshot()), "slot D failed");
  require(!cache.remember(L"pkg-e", L"E", ja, gen.snapshot()),
          "capacity guard did not refuse unbounded growth");
  require(cache.count() == 4, "maximum capacity exceeded");
  require(cache.capacity_rejections() == 1, "capacity rejection unobserved");
  require(cache.stale_rejections() == 1, "in-flight stale result unobserved");
  require(cache.invalidations() >= 2, "event and language invalidations missing");

  // A missed event subscription or failed locale query must NEVER leave old
  // display strings cached. The caller falls back to the original WinRT getter.
  DisplayNameCache failure_path(gen, 4);
  require(failure_path.remember(L"pkg-x", L"original", ja, gen.snapshot()),
          "failure baseline insertion failed");
  require(failure_path.count() == 1, "failure baseline not cached");
  failure_path.disable();
  require(failure_path.count() == 0, "disabling cache retained entries");
  require(!failure_path.lookup(L"pkg-x", ja, output),
          "disabled cache returned stale display name");
  require(!failure_path.remember(L"pkg-x", L"new", ja, gen.snapshot()),
          "disabled cache silently re-enabled itself");

  // Concurrent notification/lookup exercises ownership under one mutex.
  std::thread writer([&] {
    for (unsigned n = 0; n < 1000; ++n) gen.invalidate();
  });
  std::thread reader([&] {
    for (unsigned n = 0; n < 1000; ++n) {
      std::wstring value;
      const auto epoch = gen.snapshot();
      (void)cache.lookup(L"pkg-a", ja, value);
      (void)cache.remember(L"pkg-a", L"fresh", ja, epoch);
    }
  });
  writer.join();
  reader.join();
  require(cache.count() <= 4, "concurrent access exceeded cache cap");
  std::printf("CACHE_LIFECYCLE_MODEL_PASS,empty_string=true,notification_invalidation=true,locale_invalidation=true,stale_write_rejected=true,subscription_failure_bypasses_cache=true,max_entries=4,concurrent_iterations=1000,evictions=%llu,stale_rejections=%llu,capacity_rejections=%llu\n",
      cache.invalidations(), cache.stale_rejections(), cache.capacity_rejections());
}

int main() {
  try {
    winrt::init_apartment(winrt::apartment_type::single_threaded);
    EventGeneration gen;
    deterministic_scenarios(gen);

    // Validate the source of real display values with no caching of user data
    // outside this test process. No package names or display strings logged.
    PackageManager manager;
    DisplayNameCache cache(gen);
    const auto language = effective_language_fingerprint();
    size_t packages = 0, failures = 0, identical = 0, empty_names = 0;
    for (const auto& pkg : manager.FindPackagesForUser(L"")) {
      try {
        const std::wstring key = pkg.Id().FullName().c_str();
        const std::wstring exact_name = pkg.DisplayName().c_str();
        const auto current = gen.snapshot();
        if (!cache.remember(key, exact_name, language, current))
          continue;
        std::wstring retrieved;
        require(cache.lookup(key, language, retrieved), "exact value not found");
        require(retrieved == exact_name, "live WinRT display value mutated");
        ++identical;
        ++packages;
        if (exact_name.empty()) ++empty_names;
      } catch (const winrt::hresult_error&) { ++failures; }
    }
    require(packages >= 5, "insufficient current user package enumeration");
    require(cache.count() <= 1024, "live cache size exceeds cap");

    // Subscribe to the real per-user catalog; use only the atomic generation
    // from callbacks. Never trigger a package installation in CI.
    auto catalog = PackageCatalog::OpenForCurrentUser();
    auto callback = [&gen](auto const&, auto const&) { gen.invalidate(); };
    auto on_install = catalog.PackageInstalling(callback);
    auto on_update = catalog.PackageUpdating(callback);
    auto on_uninstall = catalog.PackageUninstalling(callback);
    auto on_status = catalog.PackageStatusChanged(callback);

    const auto before = gen.snapshot();
    gen.invalidate(); // synthetic event, safely exercises the same path
    std::wstring any;
    require(!cache.lookup(L"deliberately-nonexistent", language, any),
            "synthetic invalidation did not apply");
    require(gen.snapshot() > before, "event clock did not change");

    catalog.PackageInstalling(on_install);
    catalog.PackageUpdating(on_update);
    catalog.PackageUninstalling(on_uninstall);
    catalog.PackageStatusChanged(on_status);
    std::printf("CACHE_LIFECYCLE_WINRT_PASS,packages=%zu,exact_value_matches=%zu,empty_display_names=%zu,api_errors=%zu,real_event_subscriptions=4,revocations=4,synthetic_event_generation=true,language_fingerprint_chars=%zu,no_mutations=true,Windows_2022_CI_only=true\n",
      packages, identical, empty_names, failures, language.size());
    return 0;
  } catch (const winrt::hresult_error& e) {
    std::fprintf(stderr,"CACHE_LIFECYCLE_WINRT_EXCEPTION,code=0x%08lx\n",
       static_cast<unsigned long>(static_cast<unsigned int>(e.code().value)));
  } catch (const std::exception& e) {
    // Error message contains only static test/assert strings, no app names.
    std::fprintf(stderr,"CACHE_LIFECYCLE_NATIVE_EXCEPTION:%s\n",e.what());
  }
  return 2;
}
