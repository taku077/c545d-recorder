/*
 * Verify GAppInfo returned to callers remains valid after registry cache refresh.
 * The test deliberately retains a GAppInfo before triggering a rescan.
 * A fix which destroys cached application objects prematurely must FAIL.
 */
#include <windows.h>
#include <gio/gio.h>
#include <stdio.h>
#include <wchar.h>
#include <string.h>
int main(void)
{
    HKEY key = NULL;
    GList *apps;
    GAppInfo *held = NULL;
    char *original_name = NULL;
    char *original_executable = NULL;
    LONG status;
    int pass = 0;
    wchar_t name[96];
    _snwprintf(name, 95, L"C545D_Lifetime_Probe_%lu", (unsigned long)GetCurrentProcessId());
    name[95] = L'\0';
    apps = g_app_info_get_all();
    if (!apps) {
        fprintf(stderr, "LIFETIME_INCONCLUSIVE: no registered applications\n");
        return 3;
    }
    held = g_object_ref(apps->data);
    original_name = g_strdup(g_app_info_get_name(held));
    original_executable = g_strdup(g_app_info_get_executable(held));
    g_list_free_full(apps, g_object_unref);
    if (!original_name || !original_executable) {
        fprintf(stderr, "LIFETIME_INCONCLUSIVE: first app has incomplete properties\n");
        goto cleanup;
    }
    status = RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\RegisteredApplications", 0, KEY_SET_VALUE, &key);
    if (status != ERROR_SUCCESS) {
        fprintf(stderr, "LIFETIME_INCONCLUSIVE: test registry unavailable\n");
        goto cleanup;
    }
    for (int i = 0; i < 3; i++) {
        wchar_t val[96];
        _snwprintf(val, 95, L"Software\\C545D_Lifetime_%d", i);
        val[95] = L'\0';
        status = RegSetValueExW(key, name, 0, REG_SZ,
                                (const BYTE *)val, (DWORD)((wcslen(val)+1)*sizeof(wchar_t)));
        if (status != ERROR_SUCCESS) {
            fprintf(stderr, "LIFETIME_INCONCLUSIVE: registry update failed\n");
            goto cleanup;
        }
        Sleep(800);
        GList *again = g_app_info_get_all();
        g_list_free_full(again, g_object_unref);
    }
    const char *new_name = g_app_info_get_name(held);
    const char *new_exe = g_app_info_get_executable(held);
    pass = g_strcmp0(original_name, new_name) == 0 &&
           g_strcmp0(original_executable, new_exe) == 0;
    printf("C545D_RETAINED_APPINFO,%s\n", pass ? "PASS" : "FAIL");
cleanup:
    if (key) {
        RegDeleteValueW(key, name);
        RegCloseKey(key);
    }
    if (held) g_object_unref(held);
    g_free(original_name);
    g_free(original_executable);
    return pass ? 0 : 4;
}
