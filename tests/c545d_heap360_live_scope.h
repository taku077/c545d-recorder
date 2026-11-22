/* CI-ONLY 360-byte BUSY allocation snapshot collector, read-only.
 * Snapshot overlap means same heap slot and same pointer value at TWO
 * checkpoints. Reuse (ABA) means it is NOT uninterrupted allocation lifetime.
 * No raw pointer/heap handle is logged, hashed or persisted to disk.
 * No additional HeapWalk, HeapCompact, free, registry writes or ETW.
 * A maximum-size limit must fail closed, not silently truncate.
 */
#ifndef C545D_HEAP360_LIVE_SCOPE_H
#define C545D_HEAP360_LIVE_SCOPE_H
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define C545D_LIVE360_MAX 4096U
#define C545D_LIVE360_STAGES 4

typedef struct {
    uintptr_t pointer;
    DWORD local_heap_ordinal;
} C545DLive360Row;

static C545DLive360Row c545d_live360_rows[C545D_LIVE360_STAGES][C545D_LIVE360_MAX];
static unsigned int c545d_live360_used[C545D_LIVE360_STAGES];
static unsigned char c545d_live360_valid[C545D_LIVE360_STAGES];
static int c545d_live360_overflow;

static int
c545d_live360_stage(const char *label, int cycle)
{
    if (strcmp(label, "baseline") == 0 && cycle == 0) return 0;
    if (strcmp(label, "cycle") == 0 && cycle == 16) return 1;
    if (strcmp(label, "after_cleanup") == 0 && cycle == 17) return 2;
    if (strcmp(label, "scanfree_cleanup") == 0 && cycle == 18) return 3;
    return -1; /* Do not infer lifetime outside four exact checkpoints. */
}

static void
c545d_live360_collect(int stage, DWORD heap_ordinal, const PROCESS_HEAP_ENTRY *entry)
{
    unsigned int j;
    C545DLive360Row *dst;
    if (stage < 0 || stage >= C545D_LIVE360_STAGES ||
        (entry->wFlags & PROCESS_HEAP_ENTRY_BUSY) == 0 ||
        entry->cbData != 360)
        return;
    if (c545d_live360_used[stage] >= C545D_LIVE360_MAX) {
        c545d_live360_overflow = 1;
        return;
    }
    /* Fail if the same slot/address appears more than once in a snapshot. */
    for (j = 0; j < c545d_live360_used[stage]; ++j)
        if (c545d_live360_rows[stage][j].pointer == (uintptr_t) entry->lpData &&
            c545d_live360_rows[stage][j].local_heap_ordinal == heap_ordinal) {
            c545d_live360_overflow = 1;
            return;
        }
    dst = &c545d_live360_rows[stage][c545d_live360_used[stage]++];
    dst->pointer = (uintptr_t) entry->lpData;
    dst->local_heap_ordinal = heap_ordinal;
}

static unsigned int
c545d_live360_overlap(int left, int right)
{
    unsigned int i, j, matched = 0;
    for (i = 0; i < c545d_live360_used[left]; ++i) {
        for (j = 0; j < c545d_live360_used[right]; ++j) {
            if (c545d_live360_rows[left][i].pointer ==
                    c545d_live360_rows[right][j].pointer &&
                c545d_live360_rows[left][i].local_heap_ordinal ==
                    c545d_live360_rows[right][j].local_heap_ordinal) {
                ++matched;
                break;
            }
        }
    }
    return matched;
}

/* Emit only after all heap locks are released; never serialize addresses. */
static int
c545d_live360_finish(int stage, int owner_stable, DWORD census_errors)
{
    unsigned int same = 0, appeared = 0, disappeared = 0, old = 0, now;
    if (stage < 0)
        return 1;
    if (stage >= C545D_LIVE360_STAGES ||
        (stage > 0 && !c545d_live360_valid[stage - 1]) ||
        c545d_live360_valid[stage] || c545d_live360_overflow ||
        !owner_stable || census_errors != 0)
        return 0;
    now = c545d_live360_used[stage];
    if (stage > 0) {
        old = c545d_live360_used[stage - 1];
        same = c545d_live360_overlap(stage - 1, stage);
        if (same > now || same > old)
            return 0;
        appeared = now - same;
        disappeared = old - same;
    }
    c545d_live360_valid[stage] = 1;
    printf("C545D_CI_LIVE360_SNAPSHOT,stage=%d,old=%u,now=%u,"
           "same_address=%u,appeared_address=%u,disappeared_address=%u,"
           "address_reuse_unexcluded=1,continuous_lifetime_proven=0,"
           "allocation_owner_proven=0,global_quiescence_proven=0,"
           "raw_address_emitted=0\n",
           stage, old, now, same, appeared, disappeared);
    return 1;
}
#endif
