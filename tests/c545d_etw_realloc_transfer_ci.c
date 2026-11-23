/* C545D disposable ETW HeapReAlloc stack-attribution calibration.
 * Purpose: test whether realloc events can produce stack groups with
 * Alloc#=0, Out#>0. This is NOT GIO, a camera, or production recorder code.
 * No user paths, registry keys, media or pointers are logged.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <wchar.h>
#include <stdint.h>

#define C545D_TOTAL 64
#define C545D_EARLY_FREE 48
static void *blocks[C545D_TOTAL];
static wchar_t root[MAX_PATH];

__declspec(noinline) static void *c545d_ci_alloc_360(HANDLE heap) {
    return HeapAlloc(heap, 0, 360);
}
__declspec(noinline) static void *c545d_ci_realloc_720(HANDLE heap, void *ptr) {
    return HeapReAlloc(heap, 0, ptr, 720);
}
static int signal_file(const wchar_t *name) {
    wchar_t path[MAX_PATH];
    HANDLE h;
    if (_snwprintf_s(path, MAX_PATH, _TRUNCATE, L"%ls\\%ls", root, name) <= 0) return 0;
    h = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                    CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return 0;
    return CloseHandle(h) ? 1 : 0;
}
static int await_file(const wchar_t *name) {
    wchar_t path[MAX_PATH];
    DWORD i;
    if (_snwprintf_s(path, MAX_PATH, _TRUNCATE, L"%ls\\%ls", root, name) <= 0) return 0;
    for (i = 0; i < 600; ++i) {
        DWORD attr = GetFileAttributesW(path);
        if (attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY)) return 1;
        Sleep(50);
    }
    return 0;
}
int wmain(void) {
    HANDLE heap = GetProcessHeap();
    DWORD n = GetEnvironmentVariableW(L"C545D_REALLOC_CAL_ROOT", root, MAX_PATH);
    unsigned i;
    if (!heap || !n || n >= MAX_PATH) return 10;
    if (!signal_file(L"ready.signal") || !await_file(L"go.signal")) return 11;
    for (i=0; i<C545D_TOTAL; ++i) {
        blocks[i] = c545d_ci_alloc_360(heap);
        if (!blocks[i]) return 12;
        *((volatile unsigned char*)blocks[i]) = (unsigned char)i;
    }
    /* Reallocations use a distinct noinline source stack, after the
     * original 64 allocations but before the first 48 are freed.
     */
    for (i=C545D_EARLY_FREE; i<C545D_TOTAL; ++i) {
        void *new_block = c545d_ci_realloc_720(heap, blocks[i]);
        if (!new_block) return 13;
        blocks[i] = new_block;
    }
    for (i=0; i<C545D_EARLY_FREE; ++i) {
        if (!HeapFree(heap, 0, blocks[i])) return 14;
        blocks[i] = NULL;
    }
    if (!signal_file(L"finished.signal") || !await_file(L"exit.signal")) return 15;
    for (i=C545D_EARLY_FREE; i<C545D_TOTAL; ++i) {
        if (!HeapFree(heap, 0, blocks[i])) return 16;
        blocks[i] = NULL;
    }
    printf("C545D_REALLOC_KNOWN_LIFETIME,alloc_calls=64,realloc_calls=16,early_free=48,held_at_stop=16,real_camera=0,pointers_printed=0\n");
    return 0;
}
