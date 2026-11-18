/*
 * C545D GLib/GIO Win32 AppInfo registry rescan probe.
 * For an isolated CI account only. Does NOT access cameras or recording.
 * Mutates one disposable HKCU\Software\RegisteredApplications value
 * and removes it on exit. No source process handles are closed.
 */
#include <windows.h>
#include <psapi.h>
#include <gio/gio.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>
#include <string.h>

static int report_type_instances = 0;

static int report_heap_summary = 0;

/*
 * Expensive debug-only heap census. Run on disposable CI exclusively, and
 * at sparse milestones only. Busy bytes are not equivalent to PrivateUsage:
 * separately committed VirtualAlloc/WinRT memory is not represented here.
 */
static void report_heaps(const char *label, int cycle)
{
    DWORD n, found, i, bad = 0;
    HANDLE *heaps = NULL;
    unsigned long long busy_bytes = 0, busy_blocks = 0;
    if (!report_heap_summary) return;
    n = GetProcessHeaps(0, NULL);
    if (n == 0 || n > 4096) {
        printf("GIO_HEAP,%s,%d,0,0,0,1\n", label, cycle);
        return;
    }
    heaps = (HANDLE *)calloc(n, sizeof(HANDLE));
    if (!heaps) {
        printf("GIO_HEAP,%s,%d,0,0,%lu,1\n", label, cycle, (unsigned long)n);
        return;
    }
    found = GetProcessHeaps(n, heaps);
    if (found == 0 || found > n) {
        free(heaps);
        printf("GIO_HEAP,%s,%d,0,0,%lu,1\n", label, cycle, (unsigned long)n);
        return;
    }
    for (i = 0; i < found; ++i) {
        PROCESS_HEAP_ENTRY entry;
        DWORD last_error;
        memset(&entry, 0, sizeof(entry));
        if (!HeapLock(heaps[i])) {
            bad++;
            continue;
        }
        while (HeapWalk(heaps[i], &entry)) {
            if (entry.wFlags & PROCESS_HEAP_ENTRY_BUSY) {
                busy_bytes += entry.cbData;
                busy_blocks++;
            }
        }
        last_error = GetLastError();
        if (last_error != ERROR_NO_MORE_ITEMS) bad++;
        if (!HeapUnlock(heaps[i])) bad++;
    }
    free(heaps);
    printf("GIO_HEAP,%s,%d,%llu,%llu,%lu,%lu\n", label, cycle,
           busy_blocks, busy_bytes, (unsigned long)found, (unsigned long)bad);
    fflush(stdout);
}


/* Only meaningful with -Dglib_debug=enabled and GOBJECT_DEBUG=instance-count.
 * This is a snapshot of *live* GObject instance counts, not allocations.
 */
static void report_types(const char *label, int cycle)
{
    static const char *type_names[] = {
        "GWin32AppInfoApplication",
        "GWin32AppInfoShellVerb",
        "GWin32AppInfoHandler",
        "GWin32AppInfoFileExtension",
        "GWin32AppInfoURLSchema",
        "GWin32RegistryKey",
        "GWin32AppInfo",
        NULL
    };
    int i;
    if (!report_type_instances) return;
    for (i = 0; type_names[i] != NULL; i++) {
        GType type = g_type_from_name(type_names[i]);
        int count = type ? g_type_get_instance_count(type) : -1;
        printf("GIO_TYPE,%s,%d,%s,%d\n", label, cycle, type_names[i], count);
    }
    fflush(stdout);
}

static volatile gint changed_count = 0;
static void on_changed(GAppInfoMonitor *monitor, gpointer unused)
{
    (void) monitor;
    (void) unused;
    g_atomic_int_inc(&changed_count);
}
static void drain_context(void)
{
    int limit = 300;
    while (limit-- > 0 && g_main_context_pending(NULL))
        g_main_context_iteration(NULL, FALSE);
}
static void enumerate_apps(void)
{
    GList *apps = g_app_info_get_all();
    g_list_free_full(apps, g_object_unref);
    drain_context();
}
static void report(const char *label, int cycle)
{
    DWORD count = 0;
    PROCESS_MEMORY_COUNTERS_EX memory;
    ZeroMemory(&memory, sizeof(memory));
    memory.cb = sizeof(memory);
    if (!GetProcessHandleCount(GetCurrentProcess(), &count)) {
        fprintf(stderr, "PROBE_FAIL: GetProcessHandleCount error=%lu\n", (unsigned long)GetLastError());
        return;
    }
    if (!GetProcessMemoryInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS *)&memory, sizeof(memory))) {
        fprintf(stderr, "PROBE_FAIL: GetProcessMemoryInfo error=%lu\n", (unsigned long)GetLastError());
        return;
    }
    printf("GIO_PROBE,%s,%d,%ld,%lu,%llu\n", label, cycle,
           (long)g_atomic_int_get(&changed_count), (unsigned long)count,
           (unsigned long long)memory.PrivateUsage);
    fflush(stdout);
}
int main(int argc, char **argv)
{
    HKEY hkey = NULL;
    int cycle_count = 16;
    int mutate_registry = 1;
    for (int arg = 1; arg < argc; arg++) {
        if (strcmp(argv[arg], "--no-registry-change") == 0) mutate_registry = 0;
        else if (strcmp(argv[arg], "--cycles=64") == 0) cycle_count = 64;
        else if (strcmp(argv[arg], "--report-types") == 0) report_type_instances = 1;
        else if (strcmp(argv[arg], "--heap-summary") == 0) report_heap_summary = 1;
    }
    LONG rc;
    wchar_t value_name[96];
    DWORD pid = GetCurrentProcessId();
    GAppInfoMonitor *monitor;
    int i;
    /* The runner has a disposable HKCU profile. */
    _snwprintf(value_name, 95, L"C545D_CI_Probe_%lu", (unsigned long)pid);
    value_name[95] = L'\0';
    rc = mutate_registry ? RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\RegisteredApplications", 0, KEY_SET_VALUE, &hkey) : ERROR_SUCCESS;
    if (rc != ERROR_SUCCESS) {
        fprintf(stderr, "PROBE_FAIL: open disposable HKCU value target status=%ld\n", (long)rc);
        return 2;
    }

    monitor = g_app_info_monitor_get();
    g_signal_connect(monitor, "changed", G_CALLBACK(on_changed), NULL);
    enumerate_apps();    /* Ensure registry watchers and AppInfo cache initialize. */
    Sleep(1000);
    report("baseline", 0);
    report_types("baseline", 0);
    report_heaps("baseline", 0);

    for (i = 1; i <= cycle_count; i++) {
        /* Different data each iteration guarantees a LAST_SET notification. */
        wchar_t value[128];
        _snwprintf(value, 127, L"Software\\C545D_NoSuchCapabilities\\%d", i);
        value[127] = L'\0';
        rc = mutate_registry ? RegSetValueExW(hkey, value_name, 0, REG_SZ,
                            (const BYTE *)value, (DWORD)((wcslen(value) + 1) * sizeof(wchar_t))) : ERROR_SUCCESS;
        if (rc != ERROR_SUCCESS) {
            fprintf(stderr, "PROBE_FAIL: synthetic HKCU change status=%ld\n", (long)rc);
            if (hkey) { RegDeleteValueW(hkey, value_name); RegCloseKey(hkey); }
            return 3;
        }
        Sleep(900);
        drain_context();
        enumerate_apps();
        report("cycle", i);
        report_types("cycle", i);
        if (i % 16 == 0 || i == cycle_count) report_heaps("cycle", i);
    }
    if (hkey) { RegDeleteValueW(hkey, value_name); RegCloseKey(hkey); }
    Sleep(1200);
    enumerate_apps();
    report("after_cleanup", cycle_count + 1);
    report_types("after_cleanup", cycle_count + 1);
    report_heaps("after_cleanup", cycle_count + 1);
    printf("GIO_PROBE_DONE,cycles=%d,notifications=%ld,reg_changes=%d\n", cycle_count, (long)g_atomic_int_get(&changed_count), mutate_registry);
    return 0;
}
