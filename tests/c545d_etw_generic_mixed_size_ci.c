/* CI-only native mixed-size ETW HeapAlloc/ReAlloc/Free discriminator.
 * NOT GLib, not camera/recorder, no registry modifications or raw pointers
 * in logs. The 24 distinct original allocations use three size classes,
 * six are reallocated and held until explicit controller exit.signal.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <wchar.h>
#define TOTAL 24
static void *b[TOTAL];
static wchar_t root[MAX_PATH];

__declspec(noinline) static void *mixed_alloc(HANDLE h, size_t n) {
    return HeapAlloc(h, 0, n);
}
__declspec(noinline) static void *mixed_realloc(HANDLE h, void *p, size_t n) {
    return HeapReAlloc(h, 0, p, n);
}
static int signal_file(const wchar_t *s) {
    wchar_t path[MAX_PATH];
    HANDLE h;
    if (_snwprintf_s(path, MAX_PATH, _TRUNCATE, L"%ls\\%ls", root, s)<=0) return 0;
    h=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);
    if(h==INVALID_HANDLE_VALUE)return 0;
    return CloseHandle(h) ? 1 : 0;
}
static int await_file(const wchar_t *s) {
    wchar_t path[MAX_PATH];
    DWORD i;
    if (_snwprintf_s(path,MAX_PATH,_TRUNCATE,L"%ls\\%ls",root,s)<=0)return 0;
    for(i=0;i<600;i++) {
        DWORD a=GetFileAttributesW(path);
        if(a!=INVALID_FILE_ATTRIBUTES && !(a&FILE_ATTRIBUTE_DIRECTORY))return 1;
        Sleep(50);
    }
    return 0;
}
static int retained(unsigned i) {
    return i==6||i==7||i==14||i==15||i==22||i==23;
}
int wmain(void) {
    unsigned i;
    HANDLE heap=GetProcessHeap();
    DWORD n=GetEnvironmentVariableW(L"C545D_REALLOC_CAL_ROOT",root,MAX_PATH);
    if(!heap || !n || n>=MAX_PATH)return 10;
    if(!signal_file(L"ready.signal")||!await_file(L"go.signal"))return 11;
    for(i=0;i<TOTAL;i++) {
        size_t size=(i<8)?192:(i<16)?448:832;
        b[i]=mixed_alloc(heap,size);
        if(!b[i])return 12;
        *((volatile unsigned char*)b[i])=(unsigned char)i;
    }
    for(i=0;i<TOTAL;i++) {
        if(retained(i)) {
            size_t size=(i<8)?544:(i<16)?1216:1800;
            void *r=mixed_realloc(heap,b[i],size);
            if(!r)return 13;
            b[i]=r;
        }
    }
    for(i=0;i<TOTAL;i++) {
        if(!retained(i)) {
            if(!HeapFree(heap,0,b[i]))return 14;
            b[i]=NULL;
        }
    }
    if(!signal_file(L"finished.signal")||!await_file(L"exit.signal"))return 15;
    for(i=0;i<TOTAL;i++) {
        if(retained(i)) {
            if(!HeapFree(heap,0,b[i]))return 16;
            b[i]=NULL;
        }
    }
    printf("C545D_GENERIC_NATIVE_FIXTURE,alloc24=1,realloc6=1,free24=1,held_final0=1,real_GIO_tested=0,raw_pointers_logged=0\n");
    return 0;
}
