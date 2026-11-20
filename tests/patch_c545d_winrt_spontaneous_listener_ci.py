#!/usr/bin/env python3
"""CI-only: signal GIO from *outside* a WinRT OS callback, with safe MTA teardown.

A real PackageCatalog callback increments numeric generation as before.
Only a terminal IsComplete event wakes its existing dedicated MTA owner thread.
The MTA worker invokes an opt-in callback *after leaving the OS callback*
and without any watcher locks; unregister waits for in-flight delivery.
No additional timer, polling loop, worker thread or OS handles are created.
This code is NOT a release candidate: package commit ordering and Win10
user-host behavior require explicit independent qualification.
"""
from pathlib import Path
import sys


def once(s, before, after, label):
    n=s.count(before)
    if n!=1:
        raise ValueError(f"{label}: expected one native source anchor, found {n}")
    return s.replace(before,after,1)


def patch(s):
    s=once(s, "#include <condition_variable>", "#include <condition_variable>\n#include <exception>", "native headers")
    s=once(s, """  std::atomic<uint64_t> ci_callback_exceptions{0};
};""",
"""  std::atomic<uint64_t> ci_callback_exceptions{0};
  // CI-only one-shot unsolicited GIO AppInfo signal service, using the
  // existing dedicated COM MTA watcher thread. The Windows callback
  // touches only this native state and never enters GLib or takes a GMutex.
  std::mutex signal_mutex;
  std::condition_variable signal_cv;
  uint64_t completed_generation=0;
  bool notification_inflight=false;
  void (__cdecl *notification)(void*)=nullptr;
  void* notification_data=nullptr;
  std::atomic<uint64_t> delivered{0};
};""", "native event state")
    s=once(s, """          try {
            if(p->ci_throw_on_next_matching_event.exchange(""",
"""          bool terminal = false;
          try {
            if(p->ci_throw_on_next_matching_event.exchange(""", "terminal flag")
    s=once(s, """              if(args.IsComplete())
                p->ci_install_complete.fetch_add(1,std::memory_order_relaxed);""",
"""              if(args.IsComplete()) {
                p->ci_install_complete.fetch_add(1,std::memory_order_relaxed);
                terminal=true;
              }""", "install terminal")
    s=once(s, """              if(args.IsComplete())
                p->ci_update_complete.fetch_add(1,std::memory_order_relaxed);""",
"""              if(args.IsComplete()) {
                p->ci_update_complete.fetch_add(1,std::memory_order_relaxed);
                terminal=true;
              }""", "update terminal")
    s=once(s, """              if(args.IsComplete())
                p->ci_uninstall_complete.fetch_add(1,std::memory_order_relaxed);""",
"""              if(args.IsComplete()) {
                p->ci_uninstall_complete.fetch_add(1,std::memory_order_relaxed);
                terminal=true;
              }""", "uninstall terminal")
    s=once(s, """          p->generation.fetch_add(1,std::memory_order_acq_rel);
        }
      };
      // Partial subscription failures""",
"""          // Always publish generation before a prospective UI notification.
          p->generation.fetch_add(1,std::memory_order_acq_rel);
          if(terminal) {
            {
              std::lock_guard<std::mutex> guard(p->signal_mutex);
              ++p->completed_generation;
            }
            p->signal_cv.notify_one();
          }
        }
      };
      // Partial subscription failures""", "notify on terminal outside GLib")
    s=once(s, """      {
        std::unique_lock<std::mutex> guard(lock);
        cv.wait(guard,[this]{return stop;});
      }
      state->active.store(false,std::memory_order_release);
      // Explicit revoke""",
"""      {
        std::unique_lock<std::mutex> guard(state->signal_mutex);
        uint64_t last_dispatched=state->completed_generation;
        while(state->active.load(std::memory_order_acquire)) {
          state->signal_cv.wait(guard,[&] {
            return !state->active.load(std::memory_order_acquire) ||
                   state->completed_generation != last_dispatched;
          });
          if(!state->active.load(std::memory_order_acquire))break;
          last_dispatched=state->completed_generation;
          const auto sink=state->notification;
          void* const context=state->notification_data;
          if(sink) {
            // Callback MUST run without any native watcher mutex and is
            // never directly invoked from Windows' COM notification context.
            // A detach waits for this in-flight delivery to finish.
            state->notification_inflight=true;
            guard.unlock();
            try { sink(context); }
            catch(...) { g_shutdown_errors.fetch_add(1,std::memory_order_relaxed); }
            state->delivered.fetch_add(1,std::memory_order_relaxed);
            guard.lock();
            state->notification_inflight=false;
            state->signal_cv.notify_all();
          }
        }
      }
      state->active.store(false,std::memory_order_release);
      // Explicit revoke""", "replace sleeping MTA waiter")
    s=once(s, """    state->active.store(false,std::memory_order_release);
    {
      std::lock_guard<std::mutex> guard(lock);
      stop=true;
    }
    cv.notify_all();
    // Close must wait""",
"""    state->active.store(false,std::memory_order_release);
    state->signal_cv.notify_all();
    {
      std::lock_guard<std::mutex> guard(lock);
      stop=true;
    }
    cv.notify_all();
    // Close must wait""", "wake native notifier shutdown")
    s=once(s, """extern "C" int c545d_dedicated_synthetic_event(c545d_dedicated_watch* p) {""",
"""/* Called from GIO's setup on a disposable CI build, not from DllMain.
 * Token registry lease prevents watch pointer ABA/UAF. Unregister NULL is
 * serialized against any in-flight notification; close joins the MTA owner.
 */
extern "C" __declspec(dllexport) int c545d_dedicated_ci_set_monitor_sink(
    c545d_dedicated_watch* token, void (__cdecl *callback)(void*),
    void* context) {
  auto watch=c545d_watch_lease(token);
  if(!watch)return 3;
  auto p=watch->state;
  std::unique_lock<std::mutex> guard(p->signal_mutex);
  if(!p->active.load(std::memory_order_acquire))return 3;
  if(callback && p->notification!=nullptr)return 4;
  p->notification=nullptr;
  p->notification_data=nullptr;
  p->signal_cv.wait(guard,[&]{return !p->notification_inflight;});
  if(callback && p->active.load(std::memory_order_acquire)) {
    p->notification=callback;
    p->notification_data=context;
    return 0;
  }
  return callback?3:0;
}
extern "C" __declspec(dllexport) int c545d_dedicated_ci_monitor_delivered(
    c545d_dedicated_watch* token,uint64_t* delivered) {
  if(!delivered)return 2;
  auto watch=c545d_watch_lease(token);
  if(!watch)return 3;
  *delivered=watch->state->delivered.load(std::memory_order_acquire);
  return 0;
}
extern "C" int c545d_dedicated_synthetic_event(c545d_dedicated_watch* p) {""", "C ABI sink registration")
    return s


def main():
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_c545d_winrt_spontaneous.py <native watch.cpp>")
    p=Path(sys.argv[1])
    data=p.read_bytes()
    newline="\r\n" if b"\r\n" in data else "\n"
    source=data.decode("utf-8").replace("\r\n","\n")
    out=patch(source)
    p.write_bytes(out.replace("\n",newline).encode("utf-8"))
    print("C545D_NATIVE_MONITOR_SINK_PATCHED,COM_callback_calls_GLib=0,"
          "new_worker_threads=0,new_native_handles=0,terminal_only=1,"
          "MTA_shutdown_join=1,CI_only=1")


if __name__=="__main__":
    main()
