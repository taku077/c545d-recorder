/* Isolated Windows CI only: no GIO, camera, registry, ETW or UST.
 * Verify whether locked HeapWalk can distinguish deliberately live from
 * deliberately freed 360-byte HeapAlloc blocks across four checkpoints.
 * In-process raw pointers are NEVER printed or uploaded. Even if this works,
 * reused addresses mean snapshots alone DO NOT prove a GLib allocation's
 * continuous lifetime or identify its allocating stack.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

enum { TARGETS = 64, RELEASE_EARLY = 48, MAX_ENTRIES = 16384 };
typedef struct {
    uintptr_t address;
    SIZE_T bytes;
} Entry;

/* Fixed .bss: avoid creating heap allocations merely to store snapshots. */
static Entry observed[4][MAX_ENTRIES];
static SIZE_T count[4];
static void *held[TARGETS];

static int snapshot(unsigned int stage) {
    PROCESS_HEAP_ENTRY e;
    DWORD status;
    HANDLE heap = GetProcessHeap();
    SIZE_T n = 0;
    if (stage >= 4 || heap == NULL)
        return 0;
    memset(&e, 0, sizeof e);
    if (!HeapLock(heap))
        return 0;
    while (HeapWalk(heap, &e)) {
        if ((e.wFlags & PROCESS_HEAP_ENTRY_BUSY) != 0) {
            if (n >= MAX_ENTRIES) {
                (void)HeapUnlock(heap);
                return 0;
            }
            observed[stage][n].address = (uintptr_t)e.lpData;
            observed[stage][n].bytes = (SIZE_T)e.cbData;
            ++n;
        }
    }
    status = GetLastError();
    if (!HeapUnlock(heap) || status != ERROR_NO_MORE_ITEMS)
        return 0;
    count[stage] = n;
    return 1;
}

static int active_at(unsigned int stage, void *ptr) {
    SIZE_T i;
    uintptr_t exact = (uintptr_t)ptr;
    if (stage >= 4 || ptr == NULL)
        return -1;
    for (i = 0; i < count[stage]; ++i) {
        if (observed[stage][i].address == exact)
            return observed[stage][i].bytes >= 360 ? 1 : -1;
    }
    return 0;
}

static int known_live(unsigned int stage, int want_early_released) {
    int i;
    int live = 0;
    for (i = 0; i < TARGETS; ++i) {
        int present = active_at(stage, held[i]);
        if (present < 0)
            return -1;
        if (present == 1)
            ++live;
        if (want_early_released && i < RELEASE_EARLY && present != 0)
            return -1;
    }
    return live;
}

int main(void) {
    HANDLE heap = GetProcessHeap();
    int i, b, middle, after, final, success = 0;
    if (heap == NULL || !snapshot(0))
        return 10;
    for (i = 0; i < TARGETS; ++i) {
        held[i] = HeapAlloc(heap, 0, 360);
        if (!held[i])
            return 11;
        *((volatile unsigned char *)held[i]) = (unsigned char)i;
    }
    if (!snapshot(1))
        return 12;
    b = known_live(0, 0);
    middle = known_live(1, 0);
    for (i = 0; i < RELEASE_EARLY; ++i) {
        if (!HeapFree(heap, 0, held[i]))
            return 13;
    }
    if (!snapshot(2))
        return 14;
    after = known_live(2, 1);
    for (i = RELEASE_EARLY; i < TARGETS; ++i) {
        if (!HeapFree(heap, 0, held[i]))
            return 15;
    }
    if (!snapshot(3))
        return 16;
    final = known_live(3, 1);
    success = (b == 0 && middle == TARGETS &&
               after == TARGETS - RELEASE_EARLY && final == 0);
    if (!success) {
        /* Numeric-only; process addresses and raw heap data never escape. */
        printf("C545D_HEAP_IDENTITY_SYNTHETIC_FAIL,phase=COUNTS,raw_uploaded=0\n");
        return 17;
    }
    printf("C545D_HEAP_IDENTITY_SYNTHETIC_PASS,"
           "baseline_known_live=%d,after_alloc_known_live=%d,"
           "after_partial_free_known_live=%d,after_all_free_known_live=%d,"
           "requested_size=360,known_allocations=64,known_early_frees=48,"
           "original_256_rerun=0,gio_runs=0,raw_addresses_emitted=0,"
           "continuous_lifetime_proven=0,allocator_owner_proven=0\n",
           b, middle, after, final);
    return 0;
}
