/*
 * Windows CI-only runtime compatibility smoke test for the GLib/GIO DLL.
 * Build against the OFFICIAL GStreamer MSVC SDK's import libraries,
 * run with the isolated candidate DLL in the executable directory.
 * No camera, credentials, or user registry writes.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <gio/gio.h>
#include <stdio.h>
#include <wchar.h>

int main(void)
{
    GList *apps;
    HMODULE handle;
    wchar_t actual[32768], expected[32768];
    DWORD n;
    DWORD m;

    apps = g_app_info_get_all();
    g_list_free_full(apps, g_object_unref);

    handle = GetModuleHandleW(L"gio-2.0-0.dll");
    if (handle == NULL) {
        fputs("SDK_OVERLAY_FAIL: no GIO loaded\n", stderr);
        return 2;
    }
    n = GetModuleFileNameW(handle, actual, (DWORD)(sizeof(actual) / sizeof(actual[0])));
    m = GetEnvironmentVariableW(L"C545D_EXPECTED_GIO_DLL", expected,
                               (DWORD)(sizeof(expected) / sizeof(expected[0])));
    if (!n || n >= sizeof(actual) / sizeof(actual[0]) ||
        !m || m >= sizeof(expected) / sizeof(expected[0])) {
        fputs("SDK_OVERLAY_FAIL: unable to inspect loaded DLL path\n", stderr);
        return 3;
    }
    if (_wcsicmp(actual, expected) != 0) {
        fputs("SDK_OVERLAY_FAIL: test did not load isolated candidate DLL\n", stderr);
        return 4;
    }

    printf("SDK_OVERLAY_PASS: official MSVC import library linked; "
           "candidate DLL loaded; basic GAppInfo API returned\n");
    return 0;
}
