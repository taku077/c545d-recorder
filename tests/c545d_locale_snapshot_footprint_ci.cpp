/*
 * CI-only original two-call Windows preferred-UI-language hashing work.
 * Extracted from tests/c545d_winrt_dedicated_watch.cpp's hash_language_list().
 * This probes an allocator/API confound, NOT an AppInfo / WinRT leak site.
 * Never prints language strings, locale hashes, paths, memory addresses.
 */
#define WIN32_LEAN_AND_MEAN
#define _WIN32_WINNT 0x0601
#include <windows.h>
#include <psapi.h>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

static std::atomic<uint64_t> checksum{0};

static bool hash_language_list(bool user, uint64_t& digest) {
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

static int sample(const char* phase) {
    PROCESS_MEMORY_COUNTERS_EX pmc={};
    pmc.cb=sizeof(pmc);
    DWORD handles=0;
    if(!GetProcessMemoryInfo(GetCurrentProcess(),
           reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&pmc),sizeof(pmc))
       || !GetProcessHandleCount(GetCurrentProcess(),&handles))
        return 4;
    // Only numerical resource statistics: language or hash NEVER serialized.
    std::printf("C545D_LOCALE_FOOTPRINT,%s,%llu,%lu\n",phase,
            static_cast<unsigned long long>(pmc.PrivateUsage),
            static_cast<unsigned long>(handles));
    std::fflush(stdout);
    return 0;
}

static int batch(bool actual, int n) {
    for(int i=0;i<n;i++){
        uint64_t digest=14695981039346656037ULL;
        if(actual){
            if(!hash_language_list(true,digest) ||
               !hash_language_list(false,digest))return 6;
        } else {
            // Same arithmetic loop count, but no OS locale or vector work.
            digest ^= static_cast<uint64_t>(i);
            digest *= 1099511628211ULL;
        }
        checksum.fetch_xor(digest,std::memory_order_relaxed);
    }
    return 0;
}

int main(int argc,char**argv){
    if(argc!=2 || (std::strcmp(argv[1],"--locale")!=0 &&
                   std::strcmp(argv[1],"--control")!=0))return 2;
    const bool actual=std::strcmp(argv[1],"--locale")==0;
    // Warm the same process first; exclude one-time loader setup effects.
    if(batch(actual,64)!=0)return 5;
    Sleep(700);
    if(sample("baseline")!=0)return 4;
    if(batch(actual,8192)!=0)return 6;
    if(sample("first8192")!=0)return 4;
    if(batch(actual,8192)!=0)return 6;
    if(sample("second8192")!=0)return 4;
    Sleep(700);
    if(sample("post_idle")!=0)return 4;
    std::puts(actual
        ?"C545D_LOCALE_FOOTPRINT_DONE,arm=locale,iterations=16384,api_calls_per_iteration=4,windows_runner_only=1"
        :"C545D_LOCALE_FOOTPRINT_DONE,arm=control,iterations=16384,api_calls_per_iteration=0,windows_runner_only=1");
    return 0;
}
