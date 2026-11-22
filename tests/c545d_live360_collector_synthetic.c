/* CI ONLY: exercise the exact live360 collector used by the disposable GIO
 * overlay on a process with 64 known allocations and 48+16 known frees.
 * No GIO, camera, recorder, ETL, UST, IFEO, raw pointers in output.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "c545d_heap360_live_scope.h"

#define BLOCKS 64
#define FIRST_FREE 48
static void *known[BLOCKS];

static int
snapshot(int stage)
{
    PROCESS_HEAP_ENTRY e;
    DWORD status;
    HANDLE heap = GetProcessHeap();
    memset(&e, 0, sizeof(e));
    if (heap == NULL || !HeapLock(heap))
        return 0;
    while (HeapWalk(heap, &e)) {
        if (e.wFlags & PROCESS_HEAP_ENTRY_BUSY)
            c545d_live360_collect(stage, 0, &e);
    }
    status = GetLastError();
    if (!HeapUnlock(heap) || status != ERROR_NO_MORE_ITEMS)
        return 0;
    return c545d_live360_finish(stage, 1, 0);
}

static int
known_count(int stage)
{
    int n, live = 0;
    unsigned int i;
    for (n = 0; n < BLOCKS; ++n) {
        for (i = 0; i < c545d_live360_used[stage]; ++i) {
            if (c545d_live360_rows[stage][i].pointer == (uintptr_t)known[n] &&
                c545d_live360_rows[stage][i].local_heap_ordinal == 0) {
                ++live;
                break;
            }
        }
    }
    return live;
}

static int
selftest_negative_cases(void)
{
    unsigned int before = c545d_live360_used[3];
    PROCESS_HEAP_ENTRY bogus;
    C545DLive360Row first = c545d_live360_rows[1][0];
    unsigned int original_count = c545d_live360_used[1];
    if (original_count == 0)
        return 0;
    /* Address reuse counterexample: a later different object at the same
     * address is counted by overlap. This is NOT continuous lifetime.
     */
    c545d_live360_rows[2][0] = first;
    c545d_live360_used[2] = 1;
    if (c545d_live360_overlap(1, 2) == 0)
        return 0;
    /* Deliberately full array: collector must reject the 4097th entry. */
    c545d_live360_used[3] = C545D_LIVE360_MAX;
    memset(&bogus, 0, sizeof(bogus));
    bogus.wFlags = PROCESS_HEAP_ENTRY_BUSY;
    bogus.cbData = 360;
    bogus.lpData = (void *)(uintptr_t)0x12340;
    c545d_live360_collect(3, 0, &bogus);
    if (!c545d_live360_overflow)
        return 0;
    /* No further calls to finish: this is a deliberately corrupted
     * selftest state, never part of a user recorder or real GIO process.
     */
    c545d_live360_used[3] = before;
    return 1;
}

int main(void)
{
    int i;
    HANDLE heap = GetProcessHeap();
    if (heap == NULL || !snapshot(0)) return 10;
    for (i = 0; i < BLOCKS; ++i) {
        known[i] = HeapAlloc(heap, 0, 360);
        if (!known[i]) return 11;
        *((volatile unsigned char *)known[i]) = (unsigned char)i;
    }
    if (!snapshot(1)) return 12;
    if (known_count(1) != BLOCKS) return 13;
    for (i = 0; i < FIRST_FREE; ++i)
        if (!HeapFree(heap, 0, known[i])) return 14;
    if (!snapshot(2)) return 15;
    if (known_count(2) != BLOCKS - FIRST_FREE) return 16;
    for (i = FIRST_FREE; i < BLOCKS; ++i)
        if (!HeapFree(heap, 0, known[i])) return 17;
    if (!snapshot(3)) return 18;
    if (known_count(3) != 0 || !selftest_negative_cases()) return 19;
    printf("C545D_LIVE360_SYNTHETIC_PASS,"
           "known_allocated=64,known_mid_live=16,known_final_live=0,"
           "simulated_ABA_reuse_counterexample=1,"
           "capacity_overflow_rejected=1,"
           "raw_address_emitted=0,continuous_lifetime_proven=0,"
           "gio_runs=0,recorder_untouched=1\n");
    return 0;
}
