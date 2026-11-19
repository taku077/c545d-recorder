// CI ONLY. Direct WinRT API experiment, no GLib/GStreamer or real data.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
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
    bool get_display, uint32_t &found, uint32_t &errors) {
  found = errors = 0;
  uint64_t checksum = 0;
  for (auto const &pkg : manager.FindPackagesForUser(L"")) {
    try {
      auto fullname = pkg.Id().FullName();
      checksum += fullname.size();
      if (get_display) {
        auto displayed = pkg.DisplayName();
        checksum += displayed.size();
      }
      ++found;
    } catch (winrt::hresult_error const &) { ++errors; }
  }
  return checksum;
}

int main(int argc, char** argv) {
  if (argc != 2 || (strcmp(argv[1],"control") && strcmp(argv[1],"display")))
    return 2;
  bool display = strcmp(argv[1],"display") == 0;
  try {
    const PCWSTR empty_from_null = WindowsGetStringRawBuffer(nullptr, nullptr);
    if (empty_from_null == nullptr || empty_from_null[0] != L'\0') {
      fprintf(stderr, "WINRT_NULL_HSTRING_SEMANTIC_FAILURE\n");
      return 7;
    }
    winrt::init_apartment(winrt::apartment_type::single_threaded);
    winrt::Windows::Management::Deployment::PackageManager manager;
    uint32_t packages = 0, errors = 0;
    volatile uint64_t checksum = 0;
    for (int i=0; i<8; ++i)
      checksum = checksum + enumerate(manager, display, packages, errors);
    Sleep(500);
    for (int i=0; i<=128; ++i) {
      if (i) checksum = checksum + enumerate(manager, display, packages, errors);
      if (i%32 == 0) {
        auto mem = get_snapshot();
        printf("WINRT_DIRECT,%s,%d,%llu,%llu,%llu,%lu,%u,%u,%lu\n",
          argv[1], i, static_cast<unsigned long long>(mem.private_usage),
          mem.busy, mem.blocks, static_cast<unsigned long>(mem.handles),
          packages, errors, static_cast<unsigned long>(mem.errors));
        fflush(stdout);
        if (mem.errors) return 4;
      }
    }
    if (packages < 5 || errors > packages/4) return 3;
    printf("WINRT_DIRECT_DONE,%s,cycles=128,package_count=%u,api_errors=%u,checksum=%llu\n",
      argv[1],packages,errors,static_cast<unsigned long long>(checksum));
  } catch (winrt::hresult_error const&) {
    fprintf(stderr,"WINRT_DIRECT_WINRT_EXCEPTION\n");
    return 5;
  } catch (std::exception const&) {
    fprintf(stderr,"WINRT_DIRECT_NATIVE_EXCEPTION\n");
    return 6;
  }
  return 0;
}
