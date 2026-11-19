/* CI-ONLY C ABI prototype for a current-user WinRT package event source.
 * Not a production GIO binary. Callers must stop polling before destroy.
 * All returned data are aggregate numbers; never transmit package identities.
 */
#ifndef C545D_WINRT_EVENT_BRIDGE_H
#define C545D_WINRT_EVENT_BRIDGE_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#ifdef C545D_BRIDGE_BUILD
#define C545D_EXPORT __declspec(dllexport)
#else
#define C545D_EXPORT __declspec(dllimport)
#endif
typedef struct c545d_winrt_watch c545d_winrt_watch;
/* Initialize the calling thread's WinRT apartment ONCE for a series of
 * watch open/close operations; uninitialize only after all watches close.
 * Nested enter/leave pairs are permitted. If initialization fails, callers
 * must bypass the cache and use the original WinRT getter.
 */
C545D_EXPORT int c545d_thread_enter(void);
C545D_EXPORT void c545d_thread_leave(void);
/* Returns 0 only when all four subscriptions succeeded. On error: *out=NULL.
 * Thread must have called c545d_thread_enter; close on same thread.
 */
C545D_EXPORT int c545d_watch_open(c545d_winrt_watch **out);
/* Read atomic event generation AND effective user/thread UI-language hash.
 * 0=success; nonzero means fail-closed, so use original WinRT getter.
 */
C545D_EXPORT int c545d_watch_snapshot(c545d_winrt_watch *watch,
                                        uint64_t *generation, uint64_t *lang_hash);
/* Synthetic notification only, isolated diagnostic testing; never host changes. */
C545D_EXPORT int c545d_watch_inject_synthetic(c545d_winrt_watch *watch);
C545D_EXPORT void c545d_watch_close(c545d_winrt_watch *watch);
#ifdef __cplusplus
}
#endif
#endif
