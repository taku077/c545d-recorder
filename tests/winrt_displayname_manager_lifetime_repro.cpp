// Disposable Windows CI experiment. Does keeping PackageManager alive cause
// Package.DisplayName heap retention? 2x2 factorial, NO GLib or real host data.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.ApplicationModel.h>
#include <winrt/Windows.Management.Deployment.h>
#include <optional>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include <stdexcept>
#include <exception>

using winrt::Windows::Management::Deployment::PackageManager;

struct Snapshot {
 SIZE_T private_bytes=0;
 uint64_t busy=0, blocks=0;
 DWORD handles=0, heap_errors=0;
};
static Snapshot sample() {
 Snapshot s;
 PROCESS_MEMORY_COUNTERS_EX pm{};
 pm.cb=sizeof(pm);
 if(!GetProcessMemoryInfo(GetCurrentProcess(),
   reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&pm),sizeof(pm)) ||
   !GetProcessHandleCount(GetCurrentProcess(),&s.handles))
   throw std::runtime_error("process counter failure");
 s.private_bytes=pm.PrivateUsage;
 DWORD count=GetProcessHeaps(0,nullptr);
 if(count==0 || count>4096) throw std::runtime_error("heap count invalid");
 std::vector<HANDLE> heaps(count);
 if(GetProcessHeaps(count,heaps.data())!=count)
   throw std::runtime_error("heap enumeration race");
 for(HANDLE h:heaps) {
   if(!HeapLock(h)){++s.heap_errors;continue;}
   PROCESS_HEAP_ENTRY ent{};
   while(HeapWalk(h,&ent)){
     if(ent.wFlags & PROCESS_HEAP_ENTRY_BUSY){
       s.busy += ent.cbData;
       ++s.blocks;
     }
   }
   if(GetLastError()!=ERROR_NO_MORE_ITEMS)++s.heap_errors;
   if(!HeapUnlock(h))++s.heap_errors;
 }
 return s;
}
static uint64_t enumerate(PackageManager const& m,bool display,
                          unsigned& count,unsigned& errors) {
 count=errors=0;
 uint64_t checksum=0;
 for(auto const& pkg:m.FindPackagesForUser(L"")) {
   try{
     checksum += pkg.Id().FullName().size();
     if(display) checksum += pkg.DisplayName().size();
     ++count;
   }catch(winrt::hresult_error const&){++errors;}
 }
 return checksum;
}
int main(int argc,char** argv){
 if(argc!=2) return 2;
 const bool scoped=strncmp(argv[1],"scoped_",7)==0;
 const bool persistent=strncmp(argv[1],"persistent_",11)==0;
 if(!scoped && !persistent)return 2;
 const char* suffix=argv[1]+(scoped?7:11);
 const bool getter=strcmp(suffix,"display")==0;
 if(!getter && strcmp(suffix,"id")!=0)return 2;
 try{
   winrt::init_apartment(winrt::apartment_type::single_threaded);
   std::optional<PackageManager> keep;
   if(persistent) keep.emplace();
   unsigned count=0,errors=0;
   volatile uint64_t checksum=0;
   auto work=[&](){
     if(scoped){
       PackageManager local;
       checksum=checksum+enumerate(local,getter,count,errors);
     } else {
       checksum=checksum+enumerate(*keep,getter,count,errors);
     }
   };
   for(int i=0;i<8;i++)work();
   Sleep(300);
   for(int i=0;i<=128;i++){
     if(i>0)work();
     if(i%32==0){
       auto m=sample();
       std::printf("C545D_MANAGER_LIFETIME,%s,%d,%llu,%llu,%llu,%lu,%u,%u,%lu\n",
           argv[1],i,static_cast<unsigned long long>(m.private_bytes),
           static_cast<unsigned long long>(m.busy),
           static_cast<unsigned long long>(m.blocks),
           static_cast<unsigned long>(m.handles),count,errors,
           static_cast<unsigned long>(m.heap_errors));
       fflush(stdout);
       if(m.heap_errors)return 6;
     }
   }
   if(count<5 || errors>count/4)return 3;
   std::printf("C545D_MANAGER_LIFETIME_DONE,%s,cycles=128,count=%u,errors=%u,checksum=%llu\n",
       argv[1],count,errors,static_cast<unsigned long long>(checksum));
 } catch(winrt::hresult_error const& e){
   std::fprintf(stderr,"C545D_MANAGER_WINRT_HRESULT=0x%08lx\n",
     static_cast<unsigned long>(static_cast<uint32_t>(e.code().value)));
   return 4;
 } catch(std::exception const&){
   std::fprintf(stderr,"C545D_MANAGER_EXCEPTION\n");
   return 5;
 }
 return 0;
}
