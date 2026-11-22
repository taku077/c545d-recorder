/*
 * Windows 2022 CI ONLY: same synthetic UTF-16 inputs and cache invalidation
 * count for original per-hit duplicate vs candidate immutable GBytes ref.
 *
 * Isolated process for each arm; not a GIO build or a real WinRT workload.
 * The original GLib-private g_wcsdup() is equivalent here to one NUL-
 * terminated UTF-16 copy on every cache hit, implemented using g_memdup2.
 * No actual OS package IDs, registry modifications, camera, or media data.
 *
 * Never interpret process PrivateUsage deltas as a proven memory-leak fix.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#include <glib.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

enum { ENTRIES=32, ROUNDS=64, QUERIES=8192, WARM=4 };
static const wchar_t ci_sample[] = { 0x65e5, 0x672c, 0x8a9e,
                                     0x30ab, 0x30e1, 0x30e9, 0x0000 };
static const gsize ci_sample_bytes = sizeof(ci_sample);
static volatile uint64_t ci_checksum;

typedef struct {
  SIZE_T private_bytes;
  SIZE_T peak_pagefile;
  DWORD handles;
  uint64_t cpu_user_100ns;
  uint64_t cpu_kernel_100ns;
  LARGE_INTEGER qpc;
} Sample;

static uint64_t filetime_num(FILETIME v) {
  ULARGE_INTEGER t;
  t.LowPart=v.dwLowDateTime;
  t.HighPart=v.dwHighDateTime;
  return (uint64_t)t.QuadPart;
}

static int sample(Sample *out) {
  PROCESS_MEMORY_COUNTERS_EX pm;
  FILETIME created,exited,kernel,user;
  memset(&pm,0,sizeof(pm));
  pm.cb=sizeof(pm);
  if (!GetProcessMemoryInfo(GetCurrentProcess(),
                            (PROCESS_MEMORY_COUNTERS *)&pm,
                            sizeof(pm))) return 0;
  if (!GetProcessHandleCount(GetCurrentProcess(),&out->handles)) return 0;
  if (!GetProcessTimes(GetCurrentProcess(),&created,&exited,
                       &kernel,&user)) return 0;
  if (!QueryPerformanceCounter(&out->qpc)) return 0;
  out->private_bytes=pm.PrivateUsage;
  out->peak_pagefile=pm.PeakPagefileUsage;
  out->cpu_user_100ns=filetime_num(user);
  out->cpu_kernel_100ns=filetime_num(kernel);
  return 1;
}

static void discard(void *value) {
  g_bytes_unref((GBytes *)value);
}

static int consume(gboolean shared, gboolean warm) {
  GHashTable *table=g_hash_table_new_full(g_str_hash,g_str_equal,g_free,
                                         shared ? discard : g_free);
  GMutex mu;
  char keys[ENTRIES][24];
  int round,query,j;
  if(!table)return 0;
  g_mutex_init(&mu);
  for(j=0;j<ENTRIES;j++)
    if(g_snprintf(keys[j],sizeof(keys[j]),"ci_fixed_%02d",j)<=0)
      return 0;
  for(round=0;round<(warm?WARM:ROUNDS);round++) {
    g_mutex_lock(&mu);
    g_hash_table_remove_all(table);
    for(j=0;j<ENTRIES;j++) {
      gpointer val;
      const wchar_t *original=ci_sample;
      if(shared)
        val=g_bytes_new_take(g_memdup2(original,ci_sample_bytes),
                             ci_sample_bytes);
      else
        val=g_memdup2(original,ci_sample_bytes);
      g_hash_table_insert(table,g_strdup(keys[j]),val);
    }
    g_mutex_unlock(&mu);
    for(query=0;query<QUERIES;query++) {
      unsigned slot=(unsigned)((query*17+round)&(ENTRIES-1));
      gpointer stored;
      const wchar_t *text;
      gpointer held;
      gsize n=ci_sample_bytes;
      g_mutex_lock(&mu);
      stored=g_hash_table_lookup(table,keys[slot]);
      if(!stored){g_mutex_unlock(&mu);return 0;}
      if(shared) {
        held=g_bytes_ref((GBytes*)stored);
      } else {
        held=g_memdup2(stored,ci_sample_bytes);
      }
      g_mutex_unlock(&mu);
      text=shared ? (const wchar_t*)g_bytes_get_data((GBytes*)held,&n)
                  : (const wchar_t*)held;
      if(n!=ci_sample_bytes || memcmp(text,ci_sample,ci_sample_bytes)!=0)
        return 0;
      ci_checksum+=(uint64_t)text[(unsigned)query % 6u];
      if(shared)g_bytes_unref((GBytes*)held);
      else g_free(held);
    }
  }
  g_mutex_lock(&mu);
  g_hash_table_remove_all(table);
  g_mutex_unlock(&mu);
  g_hash_table_unref(table);
  g_mutex_clear(&mu);
  return 1;
}

int main(int argc,char **argv) {
  Sample before,after;
  LARGE_INTEGER frequency;
  int shared;
  int64_t private_diff,handle_diff;
  uint64_t user_time,kernel_time,elapsed_us;
  if(argc!=2 || (strcmp(argv[1],"old")&&strcmp(argv[1],"shared")))
    return 2;
  if(sizeof(wchar_t)!=sizeof(gunichar2))return 3;
  shared=!strcmp(argv[1],"shared");
  if(!QueryPerformanceFrequency(&frequency) || frequency.QuadPart<1)
    return 4;
  if(!consume(shared,TRUE))return 5;
  if(!sample(&before))return 6;
  if(!consume(shared,FALSE))return 7;
  if(!sample(&after))return 8;
  if(after.cpu_user_100ns<before.cpu_user_100ns ||
     after.cpu_kernel_100ns<before.cpu_kernel_100ns ||
     after.qpc.QuadPart<before.qpc.QuadPart)return 9;
  private_diff=(int64_t)after.private_bytes-(int64_t)before.private_bytes;
  handle_diff=(int64_t)after.handles-(int64_t)before.handles;
  user_time=after.cpu_user_100ns-before.cpu_user_100ns;
  kernel_time=after.cpu_kernel_100ns-before.cpu_kernel_100ns;
  elapsed_us=(uint64_t)(((after.qpc.QuadPart-before.qpc.QuadPart)*1000000ULL)
                        /(uint64_t)frequency.QuadPart);
  if(ci_checksum==0 || user_time+kernel_time==0 ||
     private_diff > 64*1024*1024 || handle_diff>12)return 10;
  printf("C545D_CACHE_SYNTH_AB,mode=%s,rounds=%u,keys=%u,"
         "hits=%u,misses=%u,hit_utf16_copies=%u,evictions=%u,"
         "private_delta=%lld,handles_delta=%lld,"
         "cpu_user_100ns=%llu,cpu_kernel_100ns=%llu,"
         "wall_us=%llu,peak_pagefile=%llu,"
         "windows_synthetic_only=1,gio_actual_hits=0,"
         "leak_fix_proven=0,host_untouched=1\n",
         argv[1],(unsigned)ROUNDS,(unsigned)ENTRIES,
         (unsigned)(ROUNDS*QUERIES),(unsigned)(ROUNDS*ENTRIES),
         shared?0u:(unsigned)(ROUNDS*QUERIES),(unsigned)ROUNDS,
         (long long)private_diff,(long long)handle_diff,
         (unsigned long long)user_time,(unsigned long long)kernel_time,
         (unsigned long long)elapsed_us,
         (unsigned long long)after.peak_pagefile);
  return 0;
}
