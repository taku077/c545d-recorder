/* CI-only: isolate dynamically loaded C++/WinRT dedicated watcher teardown,
 * especially when the library is unloaded from a C-runtime atexit callback.
 * No GLib/GStreamer or real package operations.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

typedef int (__cdecl *EnterFn)(void);
typedef void (__cdecl *LeaveFn)(void);
typedef int (__cdecl *OpenFn)(void **);
typedef int (__cdecl *SnapshotFn)(void *,uint64_t *,uint64_t *);
typedef void (__cdecl *CloseFn)(void *);
static HMODULE dll;
static EnterFn enter;
static LeaveFn leave;
static OpenFn open_watch;
static SnapshotFn snapshot;
static CloseFn close_watch;
static void *handle;
static void marker(const char *value) {
  printf("C545D_DYNAMIC_UNLOAD_STAGE=%s\n",value); fflush(stdout);
}
static void cleanup(void) {
  marker("atexit_cleanup_enter");
  if(handle) {
    marker("before_close");
    close_watch(handle);
    marker("after_close");
    handle=NULL;
  }
  leave();
  marker("after_runtime_leave");
  if(dll) {
    FreeLibrary(dll);
    dll=NULL;
  }
  marker("after_freelibrary");
}
int main(int argc,char **argv) {
  uint64_t g=0,l=0;
  SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
  if(argc!=3)return 2;
  marker("before_load");
  dll=LoadLibraryA(argv[1]);
  if(!dll)return 3;
  marker("after_load");
#define LOOKUP(fn,name,type) do { fn=(type)GetProcAddress(dll,name); if(!fn) return 4; } while(0)
  LOOKUP(enter,"c545d_dedicated_runtime_enter",EnterFn);
  LOOKUP(leave,"c545d_dedicated_runtime_leave",LeaveFn);
  LOOKUP(open_watch,"c545d_dedicated_open",OpenFn);
  LOOKUP(snapshot,"c545d_dedicated_snapshot",SnapshotFn);
  LOOKUP(close_watch,"c545d_dedicated_close",CloseFn);
#undef LOOKUP
  if(enter()!=0)return 5;
  if(open_watch(&handle)!=0||!handle)return 6;
  marker("after_open");
  if(snapshot(handle,&g,&l)!=0||!g||!l)return 7;
  marker("after_snapshot");
  if(atoi(argv[2])==1) {
    if(atexit(cleanup)!=0)return 8;
    marker("returning_into_atexit");
    return 0;
  }
  cleanup();
  marker("normal_cleanup_complete");
  return 0;
}
