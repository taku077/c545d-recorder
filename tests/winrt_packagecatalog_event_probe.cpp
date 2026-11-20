// CI-only feasibility probe: package update invalidation event subscription.
// Never installs/uninstalls packages or changes user language on the host.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.ApplicationModel.h>
#include <winrt/Windows.Management.Deployment.h>
#include <cstdio>
#include <vector>
#include <exception>

int main() {
  try {
    winrt::init_apartment(winrt::apartment_type::single_threaded);
    auto catalog = winrt::Windows::ApplicationModel::PackageCatalog::OpenForCurrentUser();
    if (!catalog) { std::fprintf(stderr,"PACKAGECATALOG_UNAVAILABLE\n"); return 2; }

    // Retain the catalog and tokens until revoked. The callback does no COM
    // reentrancy and never prints installed app identities or event details.
    LONG events = 0;
    auto installing = catalog.PackageInstalling(
        [&events](auto const&, auto const&) { InterlockedIncrement(&events); });
    auto updating = catalog.PackageUpdating(
        [&events](auto const&, auto const&) { InterlockedIncrement(&events); });
    auto uninstalling = catalog.PackageUninstalling(
        [&events](auto const&, auto const&) { InterlockedIncrement(&events); });
    auto status = catalog.PackageStatusChanged(
        [&events](auto const&, auto const&) { InterlockedIncrement(&events); });

    ULONG count=0, length=0;
    // First call obtains a size for current user's preferred UI languages.
    (void)GetUserPreferredUILanguages(MUI_LANGUAGE_NAME, &count, nullptr, &length);
    if (length == 0 || length > 16384 || count == 0) {
      std::fprintf(stderr,"USER_LANGUAGE_QUERY_SIZE_INVALID\n");
      return 3;
    }
    std::vector<wchar_t> locales(length);
    if (!GetUserPreferredUILanguages(MUI_LANGUAGE_NAME, &count,
                                     locales.data(), &length)) {
      std::fprintf(stderr,"USER_LANGUAGE_QUERY_FAILED\n");
      return 4;
    }
    // Subscribe/unsubscribe only; a real installation or language mutation
    // is explicitly outside CI scope. No fake notification is assumed.
    catalog.PackageInstalling(installing);
    catalog.PackageUpdating(updating);
    catalog.PackageUninstalling(uninstalling);
    catalog.PackageStatusChanged(status);
    std::printf("C545D_PACKAGECATALOG_EVENT_API_PASS,registrations=4,revocations=4,preferred_ui_language_count=%lu,unsolicited_notifications=%ld,Windows_CI_only=true\n",
      static_cast<unsigned long>(count), static_cast<long>(events));
    return 0;
  } catch (winrt::hresult_error const& e) {
    std::fprintf(stderr,"PACKAGECATALOG_WINRT_FAILURE,hresult=0x%08lx\n",
      static_cast<unsigned long>(static_cast<unsigned int>(e.code().value)));
    return 5;
  } catch (std::exception const&) {
    std::fprintf(stderr,"PACKAGECATALOG_NATIVE_EXCEPTION\n");
    return 6;
  }
}
