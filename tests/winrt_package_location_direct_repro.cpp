// CI-only: independent WinRT Path getter A/B vs ID-only and DisplayName.
// Does not print or persist any installed package IDs/paths or user secrets.
// No GLib, no GStreamer, no registry/package mutations, not release code.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.ApplicationModel.h>
#include <winrt/Windows.Management.Deployment.h>
#include <winrt/Windows.Storage.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include <stdexcept>

using winrt::Windows::Management::Deployment::PackageManager;

struct Memory {
  SIZE_T private_usage=0;
  unsigned long long busy=0,blocks=0;
  DWORD handles=0,heap_errors=0;
};
static Memory sample() {
  Memory out;
  PROCESS_MEMORY_COUNTERS_EX pm{};
  pm.cb=sizeof(pm);
  if (!GetProcessMemoryInfo(GetCurrentProcess(),
      reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&pm),sizeof(pm)) ||
      !GetProcessHandleCount(GetCurrentProcess(),&out.handles))
    throw std::runtime_error("process counters failed");
  out.private_usage=pm.PrivateUsage;
  DWORD n=GetProcessHeaps(0,nullptr);
  if(!n || n>4096)throw std::runtime_error("invalid heap count");
  std::vector<HANDLE> heaps(n);
  if(GetProcessHeaps(n,heaps.data())!=n)
    throw std::runtime_error("heap count changed");
  for(auto h: heaps) {
    if(!HeapLock(h)) {++out.heap_errors; continue;}
    PROCESS_HEAP_ENTRY e{};
    while(HeapWalk(h,&e)) {
      if(e.wFlags & PROCESS_HEAP_ENTRY_BUSY) {
        out.busy+=e.cbData;
        ++out.blocks;
      }
    }
    if(GetLastError()!=ERROR_NO_MORE_ITEMS)++out.heap_errors;
    if(!HeapUnlock(h))++out.heap_errors;
  }
  return out;
}
enum class Mode { id_only, display, location };
static const char* label(Mode m) {
  switch(m) {
  case Mode::id_only: return "id_only";
  case Mode::display: return "display";
  case Mode::location: return "location";
  }
  return "invalid";
}
static uint64_t sweep(PackageManager const& manager, Mode m,
                      unsigned& enumerated, unsigned& errors) {
  enumerated=errors=0;
  uint64_t sum=0;
  for(auto const& pkg:manager.FindPackagesForUser(L"")) {
    try {
      auto id=pkg.Id().FullName();
      sum+=id.size();
      if(m==Mode::display) {
        auto display=pkg.DisplayName();
        sum+=display.size();
      } else if(m==Mode::location) {
        auto location=pkg.InstalledLocation();
        if(location) {
          auto path=location.Path();
          sum+=path.size();
        }
      }
      ++enumerated;
    } catch(winrt::hresult_error const&) {
      ++errors;
    }
  }
  return sum;
}
int main(int argc,char** argv) {
  if(argc!=2) return 2;
  Mode mode=Mode::id_only;
  if(strcmp(argv[1],"display")==0) mode=Mode::display;
  else if(strcmp(argv[1],"location")==0) mode=Mode::location;
  else if(strcmp(argv[1],"id_only")!=0) return 2;
  try {
    winrt::init_apartment(winrt::apartment_type::single_threaded);
    PackageManager manager;
    unsigned count=0,errors=0;
    volatile uint64_t sum=0;
    for(int i=0;i<8;i++)sum=sum+sweep(manager,mode,count,errors);
    Sleep(300);
    for(int i=0;i<=128;i++) {
      if(i>0) sum=sum+sweep(manager,mode,count,errors);
      if(i%32==0) {
        const auto m=sample();
        std::printf("C545D_PATH_DIRECT,%s,%d,%llu,%llu,%llu,%lu,%u,%u,%lu\n",
          label(mode),i,
          static_cast<unsigned long long>(m.private_usage),
          m.busy,m.blocks,static_cast<unsigned long>(m.handles),
          count,errors,static_cast<unsigned long>(m.heap_errors));
        std::fflush(stdout);
        if(m.heap_errors) return 6;
      }
    }
    if(count<5 || errors>count/4) return 3;
    std::printf("C545D_PATH_DIRECT_DONE,%s,cycles=128,packages=%u,errors=%u,checksum=%llu\n",
       label(mode),count,errors,static_cast<unsigned long long>(sum));
  } catch(winrt::hresult_error const& e) {
    std::fprintf(stderr,"C545D_PATH_DIRECT_WINRT_HRESULT=0x%08lx\n",
      static_cast<unsigned long>(static_cast<uint32_t>(e.code().value)));
    return 4;
  } catch(std::exception const&) {
    std::fprintf(stderr,"C545D_PATH_DIRECT_EXCEPTION\n");
    return 5;
  }
  return 0;
}
