/* CI ONLY. Synthetic 360-byte Win32 heap allocations, no camera, registry,
 * GIO, or persistent process state. The controller owns UST/GFlags cleanup.
 * All snapshots are local to the disposable Windows runner. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>

static void *keep[64];

static int flag_present(const wchar_t *path) {
    return GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES;
}
static int wait_for_flag(const wchar_t *path) {
    unsigned int i;
    for (i=0; i<300; i++) {
        if (flag_present(path)) return 1;
        Sleep(100);
    }
    return 0;
}
static int write_flag(const wchar_t *path) {
    HANDLE h = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return 0;
    CloseHandle(h);
    return 1;
}
int main(void) {
    unsigned int i;
    if (!write_flag(L"ready.signal")) return 10;
    if (!wait_for_flag(L"allocate.signal")) return 11;
    for (i=0; i<64; i++) {
        keep[i] = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, 360);
        if (!keep[i]) return 12;
        ((volatile unsigned char *)keep[i])[0] = (unsigned char)i;
    }
    if (!write_flag(L"allocated.signal")) return 13;
    if (!wait_for_flag(L"exit.signal")) return 14;
    for (i=0; i<64; i++)
        HeapFree(GetProcessHeap(), 0, keep[i]);
    return 0;
}
