#!/usr/bin/env python3
"""CI ONLY: opt-in missing PackageStatusChanged-only AppInfo monitor path.

Applied after tests/patch_c545d_winrt_spontaneous_listener_ci.py.
PackageStatusChangedEventArgs does not expose IsComplete(). It previously
updated the generation but NEVER woke the native MTA notifier, so an app
status-only change could not produce the unsolicited changed signal.
This prototype flags a status event as potentially changed and hands it
off through the ALREADY EXISTING MTA owner/sink, outside the COM callback.
Event delivery is coalesced only at GAppInfoMonitor; do not claim that
exactly one raw notification corresponds to one logical package update.
"""
import sys
from pathlib import Path

def once(s: str, before: str, after: str, name: str) -> str:
    n=s.count(before)
    if n!=1:raise ValueError(f"{name}: expected exactly one anchor, found {n}")
    return s.replace(before,after,1)

def patch(s: str) -> str:
    old="""              if(args.IsComplete()) {
                p->ci_uninstall_complete.fetch_add(1,std::memory_order_relaxed);
                terminal=true;
              }
            }
          } catch(...) {"""
    new="""              if(args.IsComplete()) {
                p->ci_uninstall_complete.fetch_add(1,std::memory_order_relaxed);
                terminal=true;
              }
            } else if constexpr(std::is_same_v<
                ArgsType,winrt::Windows::ApplicationModel::PackageStatusChangedEventArgs>) {
              // No IsComplete() on PackageStatusChanged. The package status
              // MAY affect application availability; notify without
              // blocking, scanning, invoking GIO or taking any GMutex here.
              // This is not an extra thread or a timer.
              terminal=true;
            }
          } catch(...) {"""
    s=once(s,old,new,"status-only completion detection")
    old="""extern "C" __declspec(dllexport) int c545d_dedicated_ci_monitor_delivered("""
    new="""/* A deliberately synthetic status-only event to exercise the SAME
 * native notification state machine without changing Windows packages,
 * registry, recording host or invoking a false PackageCatalog event.
 * This does NOT prove that Windows itself emitted a status-only event.
 */
extern "C" __declspec(dllexport) int c545d_dedicated_ci_force_status_only(
    c545d_dedicated_watch* token) {
  auto watch=c545d_watch_lease(token);
  if(!watch || !watch->state->active.load(std::memory_order_acquire))return 3;
  auto p=watch->state;
  p->generation.fetch_add(1,std::memory_order_acq_rel);
  {
    std::lock_guard<std::mutex> guard(p->signal_mutex);
    ++p->completed_generation;
  }
  p->signal_cv.notify_one();
  return 0;
}
extern "C" __declspec(dllexport) int c545d_dedicated_ci_monitor_delivered("""
    s=once(s,old,new,"synthetic status test entry")
    return s

def main() -> None:
    if len(sys.argv)!=2:
        raise SystemExit("usage: status_only.py <patched dedicated watcher.cpp>")
    p=Path(sys.argv[1])
    raw=p.read_bytes()
    newline="\r\n" if b"\r\n" in raw else "\n"
    original=raw.decode("utf-8").replace("\r\n","\n")
    result=patch(original)
    p.write_bytes(result.replace("\n",newline).encode("utf-8"))
    print("C545D_STATUS_ONLY_MONITOR_PATCH_CI_ONLY,"
          "real_OS_status_only_not_yet_observed=1,"
          "synthetic_status_path_available=1,"
          "new_worker_thread=0,new_timer=0,COM_callback_calls_GIO=0")

if __name__=="__main__":
    main()
