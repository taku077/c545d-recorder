/*
 * Standalone, disposable CI capability preflight, NOT a GIO or Tapo test.
 * Check whether Win10-compatible PROCESS_HEAP_REGION.dwCommittedSize is
 * supplied by Windows2022 HeapWalk for a known synthetic Win32 heap.
 * Microsoft explicitly permits zero when unavailable, and large-block
 * virtual regions need not be tagged PROCESS_HEAP_REGION. Consequently
 * reported bytes must NEVER be labeled whole-process heap commitment.
 * Do not run on user's host or deployed recorder. No HeapCompact,
 * HeapSetInformation, recorder/DLL, registry or COM operations.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { ALLOCS = 64, BYTES = 4096 };

static int sample(const char *tag)
{
    DWORD n = GetProcessHeaps(0, NULL), found, i;
    HANDLE *heaps;
    unsigned long long busy_bytes = 0, region_commit = 0;
    unsigned int regions = 0, regions_known = 0, unknown = 0, failures = 0;
    if (!n || n > 4096) return 2;
    heaps = (HANDLE *)calloc(n, sizeof(HANDLE));
    if (!heaps) return 3;
    found = GetProcessHeaps(n, heaps);
    if (!found || found > n) {
        free(heaps);
        return 4;
    }
    for (i = 0; i < found; ++i) {
        PROCESS_HEAP_ENTRY item;
        DWORD result;
        ZeroMemory(&item, sizeof(item));
        if (!HeapLock(heaps[i])) {
            ++failures;
            continue;
        }
        while (HeapWalk(heaps[i], &item)) {
            if (item.wFlags & PROCESS_HEAP_REGION) {
                ++regions;
                if (item.Region.dwCommittedSize != 0) {
                    ++regions_known;
                    region_commit += item.Region.dwCommittedSize;
                } else ++unknown;
            }
            if (item.wFlags & PROCESS_HEAP_ENTRY_BUSY)
                busy_bytes += item.cbData;
        }
        result = GetLastError();
        if (result != ERROR_NO_MORE_ITEMS) ++failures;
        if (!HeapUnlock(heaps[i])) ++failures;
    }
    free(heaps);
    printf("C545D_HEAP_REGION_CAPABILITY,stage=%s,heaps=%lu,"
           "regions=%u,regions_known=%u,unknown_optional=%u,"
           "reported_region_commit=%llu,busy_cbData=%llu,"
           "errors=%u,full_process_commit_proven=0,real_camera=0\n",
           tag, (unsigned long)found, regions, regions_known, unknown,
           region_commit, busy_bytes, failures);
    fflush(stdout);
    return failures ? 5 : 0;
}

int main(void)
{
    HANDLE heap = GetProcessHeap();
    void *objects[ALLOCS];
    int i, result;
    if (!heap) return 6;
    memset(objects, 0, sizeof(objects));
    if ((result = sample("baseline")) != 0) return result;
    for (i = 0; i < ALLOCS; ++i) {
        objects[i] = HeapAlloc(heap, 0, BYTES);
        if (objects[i] == NULL) {
            while (--i >= 0) HeapFree(heap, 0, objects[i]);
            return 7;
        }
    }
    if ((result = sample("allocated")) != 0) {
        for (i = 0; i < ALLOCS; ++i) HeapFree(heap, 0, objects[i]);
        return result;
    }
    for (i = 0; i < ALLOCS; ++i) {
        if (!HeapFree(heap, 0, objects[i])) return 8;
    }
    if ((result = sample("released")) != 0) return result;
    puts("C545D_HEAP_REGION_PREFLIGHT_PASS,synthetic_only=1,"
         "windows10_api_compatible=1,heap_commit_optional=1,"
         "large_blocks_may_be_unrepresented=1,windows256_rerun=0,"
         "host_modified=0");
    return 0;
}
