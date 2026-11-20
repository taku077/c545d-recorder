/*
 * C545D: Windows GIO AppInfo API compatibility after cache rebuild.
 * Only touches a temporary HKCU RegisteredApplications value on CI runner.
 * Does not launch apps, query cameras, or record media.
 */
#include <windows.h>
#include <gio/gio.h>
#include <stdio.h>
#include <wchar.h>
#include <string.h>

typedef struct {
    int default_type_exists;
    int default_uri_exists;
    int all_for_type_nonempty;
    int all_nonempty;
} ProbeSummary;

static gboolean valid_info(GAppInfo *info)
{
    if (!info) return FALSE;
    return g_app_info_get_name(info) != NULL;
}

static int sample_api(ProbeSummary *summary)
{
    GAppInfo *type = g_app_info_get_default_for_type(".txt", FALSE);
    GAppInfo *uri = g_app_info_get_default_for_uri_scheme("http");
    GList *matches = g_app_info_get_all_for_type(".txt");
    GList *all = g_app_info_get_all();
    GList *it;
    int ok = 1;

    summary->default_type_exists = type != NULL;
    summary->default_uri_exists = uri != NULL;
    summary->all_for_type_nonempty = matches != NULL;
    summary->all_nonempty = all != NULL;
    if (type && !valid_info(type)) ok = 0;
    if (uri && !valid_info(uri)) ok = 0;
    for (it = matches; it; it = it->next)
        if (!valid_info(G_APP_INFO(it->data))) ok = 0;
    for (it = all; it; it = it->next)
        if (!valid_info(G_APP_INFO(it->data))) ok = 0;
    g_clear_object(&type);
    g_clear_object(&uri);
    g_list_free_full(matches, g_object_unref);
    g_list_free_full(all, g_object_unref);
    return ok;
}

int main(void)
{
    HKEY key = NULL;
    wchar_t test_name[96];
    const int cycles = 8;
    int exit_code = 4;
    int i;
    GList *apps = g_app_info_get_all();
    GAppInfo *held = NULL;
    gchar *name = NULL, *exe = NULL;
    ProbeSummary baseline, current;
    LONG status;
    for (GList *it = apps; it != NULL; it = it->next) {
        GAppInfo *candidate = G_APP_INFO(it->data);
        if (g_app_info_get_name(candidate)) {
            held = g_object_ref(candidate);
            break;
        }
    }
    g_list_free_full(apps, g_object_unref);
    if (!held) {
        fprintf(stderr, "GIO_API_INCONCLUSIVE,no-app-name\n");
        return 3;
    }
    name = g_strdup(g_app_info_get_name(held));
    exe = g_strdup(g_app_info_get_executable(held)); /* Validly NULL for UWP. */
    if (!sample_api(&baseline) || !baseline.all_nonempty) {
        fprintf(stderr, "GIO_API_INCONCLUSIVE,initial-lookup\n");
        goto cleanup;
    }
    _snwprintf(test_name, 95, L"C545D_API_CI_%lu", (unsigned long)GetCurrentProcessId());
    test_name[95] = L'\0';
    status = RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\RegisteredApplications",
                           0, KEY_SET_VALUE, &key);
    if (status != ERROR_SUCCESS) {
        fprintf(stderr, "GIO_API_INCONCLUSIVE,open-test-registry\n");
        goto cleanup;
    }
    for (i = 0; i < cycles; i++) {
        wchar_t value[100];
        _snwprintf(value, 99, L"Software\\C545D_APITest_Missing_%d", i);
        value[99] = L'\0';
        status = RegSetValueExW(key, test_name, 0, REG_SZ,
                                (const BYTE *)value, (DWORD)((wcslen(value) + 1) * sizeof(wchar_t)));
        if (status != ERROR_SUCCESS) {
            fprintf(stderr, "GIO_API_FAIL,reg-set,%ld\n", (long)status);
            goto cleanup;
        }
        Sleep(400);
        if (!sample_api(&current)) {
            fprintf(stderr, "GIO_API_FAIL,invalid-object-cycle=%d\n", i + 1);
            goto cleanup;
        }
        if ((baseline.default_type_exists && !current.default_type_exists) ||
            (baseline.default_uri_exists && !current.default_uri_exists) ||
            (baseline.all_for_type_nonempty && !current.all_for_type_nonempty) ||
            (baseline.all_nonempty && !current.all_nonempty)) {
            fprintf(stderr, "GIO_API_FAIL,missing-association-cycle=%d\n", i + 1);
            goto cleanup;
        }
        if (g_strcmp0(name, g_app_info_get_name(held)) != 0 ||
            g_strcmp0(exe, g_app_info_get_executable(held)) != 0) {
            fprintf(stderr, "GIO_API_FAIL,held-object-changed-cycle=%d\n", i + 1);
            goto cleanup;
        }
    }
    printf("GIO_API_PASS,cycles=%d,default_type=%d,default_uri=%d,all_for_type=%d,held_valid=1\n",
           cycles, baseline.default_type_exists, baseline.default_uri_exists,
           baseline.all_for_type_nonempty);
    exit_code = 0;
cleanup:
    if (key != NULL) {
        RegDeleteValueW(key, test_name);
        RegCloseKey(key);
    }
    g_clear_object(&held);
    g_free(name);
    g_free(exe);
    return exit_code;
}
