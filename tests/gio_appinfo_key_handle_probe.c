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
#include <stdint.h>

static int report_type_instances = 0;

static int report_heap_summary = 0;
/* Debug-only SIZE HISTOGRAM. Sizes/counts contain no addresses or registry names.
 * Bin 2048 aggregates all allocations >=2048 bytes. Global, never heap-alloced.
 */
static unsigned long long c545d_heap_sizes[2049];


/*
 * Read-only VirtualQuery inventory: counts committed memory by region type.
 * A MEM_PRIVATE region total is NOT equivalent to process PrivateUsage.
 * This census is sampled sparsely and only in disposable CI.
 */
static int report_vm_summary = 0;
static void report_vm(const char *label, int cycle)
{
    SYSTEM_INFO info;
    uintptr_t address, limit;
    unsigned long long private_bytes = 0, mapped_bytes = 0, image_bytes = 0;
    unsigned long long regions = 0;
    unsigned int errors = 0;
    if (!report_vm_summary) return;
    GetSystemInfo(&info);
    address = (uintptr_t)info.lpMinimumApplicationAddress;
    limit = (uintptr_t)info.lpMaximumApplicationAddress;
    while (address < limit) {
        MEMORY_BASIC_INFORMATION mbi;
        SIZE_T got = VirtualQuery((LPCVOID)address, &mbi, sizeof(mbi));
        uintptr_t next;
        if (got != sizeof(mbi)) {
            ++errors;
            break;
        }
        next = (uintptr_t)mbi.BaseAddress + mbi.RegionSize;
        if (next <= address) {
            ++errors;
            break;
        }
        if (mbi.State == MEM_COMMIT) {
            ++regions;
            if (mbi.Type == MEM_PRIVATE) private_bytes += (unsigned long long)mbi.RegionSize;
            else if (mbi.Type == MEM_MAPPED) mapped_bytes += (unsigned long long)mbi.RegionSize;
            else if (mbi.Type == MEM_IMAGE) image_bytes += (unsigned long long)mbi.RegionSize;
        }
        address = next;
    }
    printf("GIO_VM,%s,%d,%llu,%llu,%llu,%llu,%u\n",
           label, cycle, private_bytes, mapped_bytes, image_bytes,
           regions, errors);
    fflush(stdout);
    if (errors != 0) {
        fprintf(stderr, "GIO_VM_ERROR: VirtualQuery scan incomplete\n");
        exit(6);
    }
}



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
    unsigned int size_slot;
    memset(c545d_heap_sizes, 0, sizeof(c545d_heap_sizes));
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
                size_slot = entry.cbData < 2048 ? (unsigned int)entry.cbData : 2048U;
                c545d_heap_sizes[size_slot]++;
            }
        }
        last_error = GetLastError();
        if (last_error != ERROR_NO_MORE_ITEMS) bad++;
        if (!HeapUnlock(heaps[i])) bad++;
    }
    free(heaps);
    printf("GIO_HEAP,%s,%d,%llu,%llu,%lu,%lu\n", label, cycle,
           busy_blocks, busy_bytes, (unsigned long)found, (unsigned long)bad);
    if (bad == 0) {
        for (size_slot = 0; size_slot <= 2048; ++size_slot) {
            if (c545d_heap_sizes[size_slot] != 0)
                printf("GIO_HEAPSIZE,%s,%d,%u,%llu\n", label, cycle,
                       size_slot, c545d_heap_sizes[size_slot]);
        }
    }
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

/*
 * CI-only Key-handle census through Microsoft's official Sysinternals Handle.
 * The tool is downloaded on the disposable runner; no registry names or handle
 * values are recorded, only the numeric type summary for the current PID.
 * This differentiates a small total-handle fluctuation from a Key leak.
 */
static void report_key_handles(const char *label, int cycle)
{
    const char *tool = getenv("C545D_HANDLE_EXE");
    char command[2048], line[512];
    FILE *pipe;
    unsigned long long keys = 0, reported_total = 0, type_sum = 0;
    int found_key = 0, found_heading = 0, found_total = 0, in_summary = 0;
    int row_count = 0, parse_error = 0, rc;
    DWORD native_before = 0, native_after = 0;
    if (!tool || !*tool) return;
    if (!GetProcessHandleCount(GetCurrentProcess(), &native_before)) {
        fprintf(stderr, "GIO_KEY_ERROR: native count before census failed\n");
        exit(5);
    }
    if (strlen(tool) > 1700) {
        fprintf(stderr, "GIO_KEY_ERROR: tool path unexpectedly long\n");
        exit(5);
    }
    snprintf(command, sizeof(command),
             "\"%s\" -accepteula -s -p %lu 2>NUL", tool,
             (unsigned long)GetCurrentProcessId());
    pipe = _popen(command, "r");
    if (!pipe) {
        fprintf(stderr, "GIO_KEY_ERROR: cannot start handle type census\n");
        exit(5);
    }
    while (fgets(line, sizeof(line), pipe)) {
        char *entry = line;
        char *colon, *last;
        char type_name[96];
        size_t length, i;
        unsigned long long count;
        int safe = 1;
        while (*entry == ' ' || *entry == '\t') ++entry;
        if (strncmp(entry, "Handle type summary:", 20) == 0) {
            if (found_heading) parse_error = 1; /* never merge processes */
            found_heading = 1;
            in_summary = 1;
            continue;
        }
        if (!in_summary) continue;
        if (strncmp(entry, "Total handles:", 14) == 0) {
            if (sscanf(entry + 14, " %llu", &reported_total) != 1)
                parse_error = 1;
            found_total = 1;
            in_summary = 0;
            continue;
        }
        colon = strchr(entry, ':');
        if (!colon || sscanf(colon + 1, " %llu", &count) != 1)
            continue;
        last = colon;
        while (last > entry && (last[-1] == ' ' || last[-1] == '\t')) --last;
        length = (size_t)(last - entry);
        if (length == 0 || length >= sizeof(type_name)) {
            parse_error = 1;
            continue;
        }
        memcpy(type_name, entry, length);
        type_name[length] = '\0';
        if (strcmp(type_name, "<Unknown type>") == 0)
            strcpy(type_name, "UnknownType");
        else {
            for (i = 0; i < length; ++i) {
                char ch = type_name[i];
                if (!((ch >= 'A' && ch <= 'Z') ||
                      (ch >= 'a' && ch <= 'z') ||
                      (ch >= '0' && ch <= '9') || ch == ' ')) {
                    safe = 0;
                    break;
                }
            }
            if (!safe) strcpy(type_name, "OtherType");
        }
        if (strcmp(type_name, "Key") == 0) {
            if (found_key) parse_error = 1;
            keys = count;
            found_key = 1;
        }
        type_sum += count;
        row_count++;
        /* Only kernel object *type names* and counts are recorded. No paths. */
        printf("GIO_H64TYPE,%s,%d,%s,%llu\n", label, cycle,
               type_name, count);
    }
    rc = _pclose(pipe);
    if (!GetProcessHandleCount(GetCurrentProcess(), &native_after)) {
        fprintf(stderr, "GIO_KEY_ERROR: native count after census failed\n");
        exit(5);
    }
    printf("GIO_H64NATIVE,%s,%d,%lu,%lu\n", label, cycle,
           (unsigned long)native_before, (unsigned long)native_after);
    if (rc != 0 || parse_error || !found_heading || !found_total ||
        !found_key || row_count == 0 || type_sum != reported_total) {
        fprintf(stderr, "GIO_KEY_ERROR: invalid type census (exit=%d, rows=%d, "
                        "sum=%llu, total=%llu)\n", rc, row_count,
                type_sum, reported_total);
        exit(5);
    }
    printf("GIO_H64TOTAL,%s,%d,%llu,%llu\n", label, cycle,
           reported_total, type_sum);
    printf("GIO_KEY,%s,%d,%llu\n", label, cycle, keys);
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
        else if (strcmp(argv[arg], "--cycles=256") == 0) cycle_count = 256;
        else if (strcmp(argv[arg], "--report-types") == 0) report_type_instances = 1;
        else if (strcmp(argv[arg], "--heap-summary") == 0) report_heap_summary = 1;
        else if (strcmp(argv[arg], "--vm-summary") == 0) report_vm_summary = 1;
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
    report_key_handles("baseline", 0);
    report_types("baseline", 0);
    report_heaps("baseline", 0);
    report_vm("baseline", 0);

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
        if (i % (cycle_count > 64 ? 64 : 16) == 0 || i == cycle_count) {
            report_heaps("cycle", i);
            report_vm("cycle", i);
        }
    }
    /* The last steady-state sample, before the probe deletes its disposable
     * registration. Cleanup can legitimately release a large AppInfo graph. */
    report_key_handles("before_cleanup", cycle_count);
    if (hkey) { RegDeleteValueW(hkey, value_name); RegCloseKey(hkey); }
    Sleep(1200);
    enumerate_apps();
    report("after_cleanup", cycle_count + 1);
    report_key_handles("after_cleanup", cycle_count + 1);
    report_types("after_cleanup", cycle_count + 1);
    report_heaps("after_cleanup", cycle_count + 1);
    report_vm("after_cleanup", cycle_count + 1);
    /* Repeat after quiescence to distinguish async cleanup from a Handle64
     * versus GetProcessHandleCount enumeration mismatch. CI only. */
    Sleep(2500);
    drain_context();
    enumerate_apps();
    report("settled_cleanup", cycle_count + 2);
    report_key_handles("settled_cleanup", cycle_count + 2);
    report_types("settled_cleanup", cycle_count + 2);
    report_heaps("settled_cleanup", cycle_count + 2);
    report_vm("settled_cleanup", cycle_count + 2);
    printf("GIO_PROBE_DONE,cycles=%d,notifications=%ld,reg_changes=%d\n", cycle_count, (long)g_atomic_int_get(&changed_count), mutate_registry);
    return 0;
}
