// CI ONLY. Probe the real WinRT Package.DisplayName of one fixed disposable
// synthetic MSIX identity under fr-FR thread UI language; output booleans only.
// No raw package names, paths, OS registry values or recording information.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winrt/base.h>
#include <winrt/Windows.Management.Deployment.h>
#include <winrt/Windows.ApplicationModel.h>
#include <string>
#include <cstdio>

int wmain(int argc, wchar_t** argv) {
  if (argc != 3) return 2;
  const std::wstring full(argv[1]);
  const std::wstring phase(argv[2]);
  if (full.rfind(L"C545D.CI.PackageEvents_", 0) != 0 ||
      (phase != L"main_add" && phase != L"resource_add" &&
       phase != L"resource_remove")) {
    puts("C545D_RESOURCE_NAME_PROBE_REFUSED,invalid_fixture_or_stage=1");
    return 2;
  }
  ULONG language_count = 0;
  if (!SetThreadPreferredUILanguages(MUI_LANGUAGE_NAME, L"fr-FR", &language_count) ||
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
    const std::wstring actual(package.DisplayName());
    const bool english = actual == L"English synthetic resource value";
    const bool french = actual == L"French synthetic resource value";
    const bool expected = (phase == L"resource_add" ? french : english);
    // Never emit names, paths, versions, identity strings or HRESULT details.
    std::printf("C545D_RESOURCE_NAME_PROBE,phase=%s,expected=%d,"
                "english=%d,french=%d,actual_nonempty=%d,"
                "thread_fr=1,CI_only=1\n",
                phase == L"main_add" ? "main_add" :
                phase == L"resource_add" ? "resource_add" : "resource_remove",
                expected ? 1 : 0, english ? 1 : 0, french ? 1 : 0,
                actual.empty() ? 0 : 1);
    return expected ? 0 : 4;
  } catch (...) {
    puts("C545D_RESOURCE_NAME_PROBE_INCONCLUSIVE,winrt_error=1");
    return 5;
  }
}
