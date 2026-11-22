/* CI-only size-band accounting for an ALREADY RUNNING locked HeapWalk.
 * No extra HeapWalk, allocation, heap mutation, registry write or ETW.
 * Seven exact lower/upper range splits + capped >=2048 range: 8 bands.
 * Each recorded cbData is live payload at THIS checkpoint, not an
 * allocation site, an allocation lifetime or PSAPI PrivateUsage.
 * Retain only small fixed integer counters in static process memory.
 */
#ifndef C545D_CI_BUSY_BANDS_H
#define C545D_CI_BUSY_BANDS_H
#include <windows.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#define C545D_BUSY_BANDS 8
#define C545D_BUSY_STAGES 4

static unsigned long long c545d_busy_band_counts[4][8];
static unsigned long long c545d_busy_band_bytes[4][8];
static unsigned char c545d_busy_band_completed[4];
static int c545d_busy_band_bad;

static int
c545d_busy_band_stage(const char *label, int cycle)
{
    if (strcmp(label, "baseline") == 0 && cycle == 0) return 0;
    if (strcmp(label, "cycle") == 0 && cycle == 16) return 1;
    if (strcmp(label, "after_cleanup") == 0 && cycle == 17) return 2;
    if (strcmp(label, "scanfree_cleanup") == 0 && cycle == 18) return 3;
    return -1;
}

static unsigned int
c545d_busy_band_number(SIZE_T cbData)
{
    if (cbData < 32) return 0;    /* 0..31 */
    if (cbData < 64) return 1;    /* 32..63 */
    if (cbData < 128) return 2;   /* 64..127 */
    if (cbData < 256) return 3;   /* 128..255 */
    if (cbData < 512) return 4;   /* 256..511 (includes 360) */
    if (cbData < 1024) return 5;  /* 512..1023 */
    if (cbData < 2048) return 6;  /* 1024..2047 */
    return 7;                     /* >=2048, actual cbData summed */
}

static void
c545d_busy_band_collect(int stage, const PROCESS_HEAP_ENTRY *entry)
{
    unsigned int band;
    unsigned long long size;
    if (stage < 0) return;
    if (stage >= C545D_BUSY_STAGES ||
        c545d_busy_band_completed[stage] ||
        (entry->wFlags & PROCESS_HEAP_ENTRY_BUSY) == 0) {
        c545d_busy_band_bad = 1;
        return;
    }
    band = c545d_busy_band_number(entry->cbData);
    size = (unsigned long long)entry->cbData;
    if (c545d_busy_band_counts[stage][band] == ULLONG_MAX ||
        size > ULLONG_MAX - c545d_busy_band_bytes[stage][band]) {
        c545d_busy_band_bad = 1;
        return;
    }
    ++c545d_busy_band_counts[stage][band];
    c545d_busy_band_bytes[stage][band] += size;
}

/* CALL AFTER HeapUnlock and all aggregate accounting. Fail before printing
 * if the census has errors, the heap handles drift or data do not match
 * the existing GIO_HEAP full busy-block/byte totals.
 */
static int
c545d_busy_band_finish(int stage, int stable, DWORD bad,
                       unsigned long long all_blocks,
                       unsigned long long all_bytes)
{
    unsigned int b;
    unsigned long long total_count = 0, total_bytes = 0;
    if (stage < 0) return 1;
    if (stage >= C545D_BUSY_STAGES || c545d_busy_band_bad ||
        c545d_busy_band_completed[stage] ||
        (stage > 0 && !c545d_busy_band_completed[stage-1]) ||
        !stable || bad != 0) return 0;
    for (b = 0; b < C545D_BUSY_BANDS; ++b) {
        if (c545d_busy_band_counts[stage][b] > ULLONG_MAX - total_count ||
            c545d_busy_band_bytes[stage][b] > ULLONG_MAX - total_bytes)
            return 0;
        total_count += c545d_busy_band_counts[stage][b];
        total_bytes += c545d_busy_band_bytes[stage][b];
    }
    if (total_count != all_blocks || total_bytes != all_bytes)
        return 0;
    c545d_busy_band_completed[stage] = 1;
    for (b = 0; b < C545D_BUSY_BANDS; ++b)
        printf("C545D_CI_BUSY_BAND,stage=%d,band=%u,"
               "count=%llu,bytes=%llu,complete_heapwalk=1,"
               "size_band_only=1,allocation_owner_proven=0,"
               "private_usage_attributed=0,raw_pointers_emitted=0\n",
               stage,b,c545d_busy_band_counts[stage][b],
               c545d_busy_band_bytes[stage][b]);
    return 1;
}
#endif
