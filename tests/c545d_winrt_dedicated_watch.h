/* CI ONLY — Dedicated-thread WinRT PackageCatalog watcher, C interface.
 * There is no dependency on the calling thread's COM apartment.
 * No real package install/update, secrets or recorder state accessed.
 * Concurrent close and snapshot on same watch is outside this prototype API.
 */
#ifndef C545D_WINRT_DEDICATED_WATCH_H
#define C545D_WINRT_DEDICATED_WATCH_H
#include <stdint.h>
#if defined(C545D_DEDICATED_BUILD)
#define C545D_API __declspec(dllexport)
#else
#define C545D_API __declspec(dllimport)
#endif
#ifdef __cplusplus
extern "C" {
#endif
typedef struct c545d_dedicated_watch c545d_dedicated_watch;
/* Keep the COM MTA alive across multiple watcher open/close operations.
 * Must balance enter/leave outside DllMain, and leave only after last close.
 */
C545D_API int c545d_dedicated_runtime_enter(void);
C545D_API void c545d_dedicated_runtime_leave(void);
C545D_API int c545d_dedicated_open(c545d_dedicated_watch **out);
C545D_API int c545d_dedicated_snapshot(c545d_dedicated_watch *watch,
                                          uint64_t *generation, uint64_t *locale_hash);
C545D_API int c545d_dedicated_synthetic_event(c545d_dedicated_watch *watch);
C545D_API void c545d_dedicated_close(c545d_dedicated_watch *watch);
/* CI-only read-only counters: native IsComplete() callbacks for the three
 * package deployment event types. Count only, never print package identity.
 */
C545D_API int c545d_dedicated_ci_completion_counters(
    c545d_dedicated_watch *watch, uint64_t *install_done,
    uint64_t *update_done, uint64_t *uninstall_done);
C545D_API void c545d_dedicated_global_counters(uint64_t *registered,
                                                    uint64_t *revoked,
                                                    uint64_t *shutdown_errors);
#ifdef __cplusplus
}
#endif
#endif
