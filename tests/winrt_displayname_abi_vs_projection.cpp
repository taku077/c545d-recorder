// CI ONLY. Direct raw WinRT ABI vs C++/WinRT projection, no GLib or camera data.
// Every raw HSTRING is freed with WindowsDeleteString. Matched 128-cycle controls.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#include <windows.applicationmodel.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winstring.h>
#include <winrt/Windows.ApplicationModel.h>
#include <winrt/Windows.Management.Deployment.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include <stdexcept>
#include <exception>

struct Snapshot {
  SIZE_T private_usage = 0;
  unsigned long long busy = 0, blocks = 0;
  DWORD handles = 0, errors = 0;
};

static Snapshot get_snapshot() {
  Snapshot s;
  PROCESS_MEMORY_COUNTERS_EX mem{};
  mem.cb = sizeof(mem);
  if (!GetProcessMemoryInfo(GetCurrentProcess(),
      reinterpret_cast<PROCESS_MEMORY_COUNTERS *>(&mem), sizeof(mem)) ||
      !GetProcessHandleCount(GetCurrentProcess(), &s.handles))
    throw std::runtime_error("Process-memory/handle snapshot failed");
  s.private_usage = mem.PrivateUsage;
  DWORD n = GetProcessHeaps(0, nullptr);
  if (n == 0 || n > 4096) throw std::runtime_error("GetProcessHeaps count invalid");
  std::vector<HANDLE> heaps(n);
  if (GetProcessHeaps(n, heaps.data()) != n)
    throw std::runtime_error("GetProcessHeaps second call failed");
  for (HANDLE h : heaps) {
    if (!HeapLock(h)) { ++s.errors; continue; }
    PROCESS_HEAP_ENTRY e{};
    while (HeapWalk(h, &e)) {
      if (e.wFlags & PROCESS_HEAP_ENTRY_BUSY) {
        s.busy += e.cbData;
        ++s.blocks;
      }
    }
    if (GetLastError() != ERROR_NO_MORE_ITEMS) ++s.errors;
    if (!HeapUnlock(h)) ++s.errors;
  }
  return s;
}

static uint64_t enumerate(
    winrt::Windows::Management::Deployment::PackageManager const &manager,
    int mode, uint32_t &found, uint32_t &errors) {
  found = errors = 0;
  uint64_t checksum = 0;
  for (auto const &pkg : manager.FindPackagesForUser(L"")) {
    try {
      auto fullname = pkg.Id().FullName();
      checksum += fullname.size();
      if (mode == 1) {
        // C++/WinRT projection owns/destroys the returned hstring.
        auto displayed = pkg.DisplayName();
        checksum += displayed.size();
      } else if (mode == 2) {
        // Raw ABI IPackage2 getter used in GLib 2.82.4. The owning
        // com_ptr releases QI and WindowsDeleteString releases HSTRING.
        auto package2 = pkg.as<ABI::Windows::ApplicationModel::IPackage2>();
        HSTRING raw = nullptr;
        HRESULT hr = package2->get_DisplayName(&raw);
        if (FAILED(hr)) {
          if (raw) WindowsDeleteString(raw);
          winrt::check_hresult(hr);
        }
        UINT32 len = 0;
        PCWSTR value = WindowsGetStringRawBuffer(raw, &len);
        if (!value) {
          if(raw) WindowsDeleteString(raw);
          throw std::runtime_error("HSTRING buffer unexpectedly null");
        }
        checksum += len;
        if (raw) winrt::check_hresult(WindowsDeleteString(raw));
      }
      ++found;
    } catch (winrt::hresult_error const &) { ++errors; }
  }
  return checksum;
}

int main(int argc, char** argv) {
  if (argc != 2 || (strcmp(argv[1],"control") &&
      strcmp(argv[1],"projected") && strcmp(argv[1],"raw") &&
      strcmp(argv[1],"freshcontrol") && strcmp(argv[1],"freshraw")))
    return 2;
  const int mode = strcmp(argv[1],"control") == 0 ? 0 :
                   strcmp(argv[1],"projected") == 0 ? 1 :
                   strcmp(argv[1],"raw") == 0 ? 2 :
                   strcmp(argv[1],"freshcontrol") == 0 ? 3 : 4;
  try {
    const PCWSTR empty_from_null = WindowsGetStringRawBuffer(nullptr, nullptr);
    if (empty_from_null == nullptr || empty_from_null[0] != L'\0') {
      fprintf(stderr, "WINRT_NULL_HSTRING_SEMANTIC_FAILURE\n");
      return 7;
    }
    winrt::init_apartment(winrt::apartment_type::single_threaded);
    using winrt::Windows::Management::Deployment::PackageManager;
    // In the control/projected/raw modes one PackageManager stays alive
    // until the process exits. In freshcontrol/freshraw modes it is
    // constructed/destroyed once per enumeration, like GLib's per-scan
    // package parser. Keep a matched identity-only "fresh" control.
    PackageManager manager{nullptr};
    if (mode < 3) manager = PackageManager();
    uint32_t packages = 0, errors = 0;
    auto one_pass = [&]() -> uint64_t {
      if (mode >= 3) {
        PackageManager fresh;
        return enumerate(fresh, mode == 3 ? 0 : 2, packages, errors);
      }
      return enumerate(manager, mode, packages, errors);
    };
    volatile uint64_t checksum = 0;
    for (int i=0; i<8; ++i)
      checksum = checksum + one_pass();
    Sleep(500);
    for (int i=0; i<=128; ++i) {
      if (i) checksum = checksum + one_pass();
      if (i%32 == 0) {
        auto mem = get_snapshot();
        printf("WINRT_ABI,%s,%d,%llu,%llu,%llu,%lu,%u,%u,%lu\n",
          argv[1], i, static_cast<unsigned long long>(mem.private_usage),
          mem.busy, mem.blocks, static_cast<unsigned long>(mem.handles),
          packages, errors, static_cast<unsigned long>(mem.errors));
        fflush(stdout);
        if (mem.errors) return 4;
      }
    }
    if (packages < 5 || errors > packages/4) return 3;
    printf("WINRT_ABI_DONE,%s,cycles=128,package_count=%u,api_errors=%u,checksum=%llu\n",
      argv[1],packages,errors,static_cast<unsigned long long>(checksum));
  } catch (winrt::hresult_error const&) {
    fprintf(stderr,"WINRT_ABI_WINRT_EXCEPTION\n");
    return 5;
  } catch (std::exception const&) {
    fprintf(stderr,"WINRT_ABI_NATIVE_EXCEPTION\n");
    return 6;
  }
  return 0;
}
