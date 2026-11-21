#!/usr/bin/env python3
"""CI ONLY: after a live dedicated WinRT watcher is operational, simulate its
owner-thread unexpectedly becoming unavailable. No OS package mutation.

Applied AFTER spontaneous and status-only native patch scripts, and NEVER in
a release candidate. Fault is only armed inside a disposable CI process by
C545D_CI_FORCE_RUNTIME_UNAVAILABLE=1 after a healthy initial snapshot.
It deactivates native event delivery and wakes the existing owner thread to
revoke its four subscriptions and unwind normally. No new worker/handles.
"""
from pathlib import Path
import sys


def patch(source: str) -> str:
    before = """    auto state=watch->state;
    if(!state->active.load(std::memory_order_acquire))return 3;
    const auto before=state->generation.load(std::memory_order_acquire);"""
    after = """    auto state=watch->state;
    // CI-only simulated runtime owner unavailability, AFTER successful init.
    // The same owner MTA worker performs ordinary COM unsubscribe and exit.
    wchar_t ci_drop[4]{};
    if(GetEnvironmentVariableW(L"C545D_CI_FORCE_RUNTIME_UNAVAILABLE",
                               ci_drop,4)==1 && ci_drop[0]==L'1') {
      if(state->active.exchange(false,std::memory_order_acq_rel))
        state->signal_cv.notify_all();
      return 12; // Watch invalidated: never return a cacheable epoch.
    }
    if(!state->active.load(std::memory_order_acquire))return 3;
    const auto before=state->generation.load(std::memory_order_acquire);"""
    count = source.count(before)
    if count != 1:
        raise ValueError(f"native snapshot anchor expected once; got {count}")
    return source.replace(before, after, 1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_c545d_winrt_runtime_drop_ci.py <native.cpp>")
    p = Path(sys.argv[1])
    raw = p.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    src = raw.decode("utf-8").replace("\r\n", "\n")
    result = patch(src)
    p.write_bytes(result.replace("\n", newline).encode("utf-8"))
    print("C545D_NATIVE_RUNTIME_DROP_INJECTION_CI_ONLY,default_disabled=1,"
          "new_threads=0,no_forced_handle_closes=1,"
          "owner_thread_performs_COM_revoke=1,not_real_Windows_failure=1")


if __name__ == "__main__":
    main()
