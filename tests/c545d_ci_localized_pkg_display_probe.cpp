// CI ONLY. Probe the real WinRT Package.DisplayName of one fixed disposable
// synthetic MSIX identity under fr-FR thread UI language; output booleans only.
// No raw package names, paths, OS registry values or recording information.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winrt/base.h>
#include <winrt/Windows.Management.Deployment.h>
#include <winrt/Windows.ApplicationModel.h>
#include <string>
#include <vector>
#include <cwchar>
#include <cstdio>

static bool user_has_en_us(void) {
  ULONG number=0, chars=0;
  if(!GetUserPreferredUILanguages(MUI_LANGUAGE_NAME,&number,nullptr,&chars) ||
     number==0 || chars<2 || chars>16384)
    return false;
  std::vector<wchar_t> values(chars);
  if(!GetUserPreferredUILanguages(MUI_LANGUAGE_NAME,&number,values.data(),&chars))
    return false;
  const wchar_t* ptr=values.data();
  const wchar_t* end=values.data()+values.size();
  while(ptr<end && *ptr) {
    if(_wcsicmp(ptr,L"en-US")==0)
      return true;
    const size_t size=wcslen(ptr);
    if(size>=static_cast<size_t>(end-ptr))
      return false;
    ptr+=size+1;
  }
  return false;
}

int wmain(int argc, wchar_t** argv) {
  if (argc != 3 && argc != 4) return 2;
  const bool reverse=(argc==4 && std::wstring(argv[3])==L"reverse");
  if(argc==4 && !reverse)return 2;
  const std::wstring full(argv[1]);
  const std::wstring phase(argv[2]);
  if (full.rfind(L"C545D.CI.PackageEvents_", 0) != 0 ||
      (phase != L"main_add" && phase != L"resource_add" &&
       phase != L"resource_remove")) {
    puts("C545D_RESOURCE_NAME_PROBE_REFUSED,invalid_fixture_or_stage=1");
    return 2;
  }
  // In reverse mode the runner must ACTUALLY have en-US in its user MUI
  // language list; a thread-only override is not an applicability guarantee.
  if(reverse && !user_has_en_us()) {
    puts("C545D_RESOURCE_NAME_INCONCLUSIVE,user_en_us_preference=0,CI_only=1");
    return 3;
  }
  ULONG language_count = 0;
  const wchar_t* thread_language = reverse ? L"en-US" : L"fr-FR";
  if (!SetThreadPreferredUILanguages(MUI_LANGUAGE_NAME, thread_language, &language_count) ||
      language_count < 1) {
    puts("C545D_RESOURCE_NAME_PROBE_INCONCLUSIVE,thread_locale_setup=0");
    return 3;
  }
  try {
    winrt::init_apartment(winrt::apartment_type::multi_threaded);
    winrt::Windows::Management::Deployment::PackageManager pm;
    auto package = pm.FindPackageForUser(L"", winrt::hstring(full));
    if (!package) {
      puts("C545D_RESOURCE_NAME_PROBE_INCONCLUSIVE,test_package_not_found=1");
      return 3;
    }
    const std::wstring actual(package.DisplayName().c_str());
    const bool english = actual == L"English synthetic resource value";
    const bool french = actual == L"French synthetic resource value";
    const bool expected = reverse ?
      (phase == L"resource_add" ? english : french) :
      (phase == L"resource_add" ? french : english);
    // Never emit names, paths, versions, identity strings or HRESULT details.
    const char* stage=phase == L"main_add" ? "main_add" :
                      phase == L"resource_add" ? "resource_add" : "resource_remove";
    if(reverse)
      std::printf("C545D_RESOURCE_NAME_REVERSE,phase=%s,expected=%d,"
                  "english=%d,french=%d,actual_nonempty=%d,"
                  "user_en=1,CI_only=1\n",
                  stage,expected ? 1 : 0,english ? 1 : 0,french ? 1 : 0,
                  actual.empty() ? 0 : 1);
    else
      std::printf("C545D_RESOURCE_NAME_PROBE,phase=%s,expected=%d,"
                  "english=%d,french=%d,actual_nonempty=%d,"
                  "thread_fr=1,CI_only=1\n",
                  stage,expected ? 1 : 0,english ? 1 : 0,french ? 1 : 0,
                  actual.empty() ? 0 : 1);
    return expected ? 0 : 4;
  } catch (...) {
    puts("C545D_RESOURCE_NAME_PROBE_INCONCLUSIVE,winrt_error=1");
    return 5;
  }
}
