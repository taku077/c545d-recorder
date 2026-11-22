/* CI-only Windows synthetic test of exact eight-band GIO collector.
 * No GLib, GIO, media, camera, registry mutation, ETW or uploaded addresses.
 * Assertions on absolute band totals do NOT compare process-local addresses.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include "c545d_ci_busy_bands.h"

#define SYNTH_COUNT 64
static void *c545d_synth_blocks[SYNTH_COUNT];
static const SIZE_T c545d_requested[8] =
    {18,44,80,160,360,720,1400,3200};

static int
snapshot(int stage)
{
    HANDLE heap = GetProcessHeap();
    PROCESS_HEAP_ENTRY e;
    DWORD error;
    unsigned long long total_bytes = 0, total_blocks = 0;
    if (heap == NULL || !HeapLock(heap)) return 0;
    memset(&e, 0, sizeof e);
    while (HeapWalk(heap, &e)) {
        if (e.wFlags & PROCESS_HEAP_ENTRY_BUSY) {
            ++total_blocks;
            total_bytes += (unsigned long long)e.cbData;
            c545d_busy_band_collect(stage, &e);
        }
    }
    error = GetLastError();
    if (!HeapUnlock(heap) || error != ERROR_NO_MORE_ITEMS) return 0;
    return c545d_busy_band_finish(stage, 1, 0, total_blocks, total_bytes);
}

int main(void)
{
    HANDLE heap=GetProcessHeap();
    unsigned int i, group;
    if (!snapshot(0)) return 10;
    for (i=0;i<SYNTH_COUNT;++i) {
        group=i % 8;
        c545d_synth_blocks[i] = HeapAlloc(heap,0,c545d_requested[group]);
        if (!c545d_synth_blocks[i]) return 11;
        *((volatile unsigned char *)c545d_synth_blocks[i])=(unsigned char)i;
    }
    if (!snapshot(1)) return 12;
    for (group=0;group<8;++group) {
        if (c545d_busy_band_counts[1][group] <
            c545d_busy_band_counts[0][group] + 8ULL) return 13;
    }
    for (i=0;i<SYNTH_COUNT;i+=2)
        if (!HeapFree(heap,0,c545d_synth_blocks[i])) return 14;
    if (!snapshot(2)) return 15;
    for (i=1;i<SYNTH_COUNT;i+=2)
        if (!HeapFree(heap,0,c545d_synth_blocks[i])) return 16;
    if (!snapshot(3)) return 17;
    /* Artificial mismatch is rejected before any report. */
    if (c545d_busy_band_finish(3,1,0,0,0)) return 18;
    if (c545d_busy_band_number(31) != 0 ||
        c545d_busy_band_number(32) != 1 ||
        c545d_busy_band_number(2047) != 6 ||
        c545d_busy_band_number(2048) != 7)
        return 19;
    printf("C545D_BUSY_BANDS_SYNTHETIC_PASS,"
           "known_allocs=64,known_frees=64,stages=4,bands=8,"
           "reported_census_consistent=1,duplicate_rejected=1,"
           "no_extra_heapwalk=1,windows_only_synthetic=1,"
           "gio_runs=0,raw_addresses_emitted=0\n");
    return 0;
}
