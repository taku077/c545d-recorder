/* C545D isolated calibration only: known HeapAlloc/HeapFree ownership.
 * No GIO, RTSP, real device, persistent registry or source modifications.
 * All file names are local signals inside a GitHub Actions-owned temp root.
 * No heap pointer, file path, package name or PID is printed publicly.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <wchar.h>
#include <stdint.h>

#define C545D_COUNT 64
#define C545D_EARLY_FREES 48
static void *blocks[C545D_COUNT];
static wchar_t root[MAX_PATH];

static int location(wchar_t *output, size_t capacity, const wchar_t *file) {
  int count = _snwprintf_s(output, capacity, _TRUNCATE, L"%ls\\%ls", root, file);
  return count > 0 && (size_t)count < capacity;
}
static int emit(const wchar_t *filename) {
  wchar_t file[MAX_PATH];
  HANDLE h;
  if (!location(file, MAX_PATH, filename)) return 0;
  h = CreateFileW(file, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_NEW,
                  FILE_ATTRIBUTE_NORMAL, NULL);
  if (h == INVALID_HANDLE_VALUE) return 0;
  return CloseHandle(h) ? 1 : 0;
}
static int await(const wchar_t *filename) {
  wchar_t file[MAX_PATH];
  DWORD i;
  if (!location(file, MAX_PATH, filename)) return 0;
  for (i=0; i < 1800; ++i) {
    DWORD attrs=GetFileAttributesW(file);
    if (attrs != INVALID_FILE_ATTRIBUTES &&
        !(attrs & FILE_ATTRIBUTE_DIRECTORY)) return 1;
    Sleep(50);
  }
  return 0;
}
int wmain(void) {
  HANDLE heap = GetProcessHeap();
  DWORD length = GetEnvironmentVariableW(L"C545D_OWNER_CAL_ROOT", root, MAX_PATH);
  unsigned i;
  if (!heap || !length || length >= MAX_PATH) return 10;
  if (!emit(L"ready.signal") || !await(L"allocate.signal")) return 11;
  for (i=0; i < C545D_COUNT; ++i) {
    blocks[i] = HeapAlloc(heap, 0, 360);
    if (!blocks[i]) return 12;
    *((volatile unsigned char *) blocks[i]) = (unsigned char)i;
  }
  if (!emit(L"allocated.signal") || !await(L"free.signal")) return 13;
  for (i=0; i < C545D_EARLY_FREES; ++i) {
    if (!HeapFree(heap,0,blocks[i])) return 14;
    blocks[i]=NULL;
  }
  if (!emit(L"freed.signal") || !await(L"exit.signal")) return 15;
  for (i=C545D_EARLY_FREES; i<C545D_COUNT; ++i) {
    if (!HeapFree(heap,0,blocks[i])) return 16;
    blocks[i]=NULL;
  }
  printf("C545D_OWNER_CAL_KNOWN_LIFETIME_PASS,allocated=64,freed_before_trace_end=48,outstanding_during_trace=16,requested_bytes_each=360,pointers_reported=0,camera=0\n");
  return 0;
}
