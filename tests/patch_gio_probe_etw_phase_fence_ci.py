#!/usr/bin/env python3
"""CI-only pre-workload/start-stop fence for GIO ETW allocation lifetime.

The fenced C probe has two controlled phases:
  1. after AppInfo initial tree + baseline census (NO test cycles yet)
  2. after last cycle but BEFORE test registry cleanup.
Both phases use isolated files under RUNNER_TEMP. This is a measurement
window barrier, NOT an assertion that queued Windows APCs are all drained.
Never patch production probe/recording or change user registry settings.
"""
from __future__ import annotations
import argparse
from pathlib import Path

PRE = '''    report_vm("baseline", 0);
'''
POST = '''    report_key_handles("before_cleanup", cycle_count);
'''
HELPER = r'''
/* CI-only ETW measurement timing. Never used on user's recording PC. */
static int c545d_ci_etw_phase_fence (const wchar_t *ready, const wchar_t *released)
{
    wchar_t root[MAX_PATH], marker[MAX_PATH], gate[MAX_PATH];
    DWORD chars = GetEnvironmentVariableW(L"C545D_CI_ETW_PHASE_ROOT", root, MAX_PATH);
    HANDLE handle;
    unsigned i;
    if (chars == 0) return 1; /* ordinary probe has no timing fence */
    if (chars >= MAX_PATH) return 0;
    if (_snwprintf_s(marker, MAX_PATH, _TRUNCATE, L"%ls\\%ls", root, ready) <= 0 ||
        _snwprintf_s(gate, MAX_PATH, _TRUNCATE, L"%ls\\%ls", root, released) <= 0)
        return 0;
    handle = CreateFileW(marker, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                         CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
    if (handle == INVALID_HANDLE_VALUE) return 0;
    CloseHandle(handle);
    for (i = 0; i < 400; i++) {
        DWORD attr = GetFileAttributesW(gate);
        if (attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY))
            return 1;
        SleepEx(50, TRUE); /* deliver *current* APC, NOT proof of future quiescence */
    }
    return 0;
}
'''

def patch(src: str) -> str:
    if "c545d_ci_etw_phase_fence" in src:
        raise ValueError("disposable_fence_already_present")
    if src.count(PRE) != 1 or src.count(POST) != 1:
        raise ValueError("probe_phase_anchor_changed")
    start = src.index("int main(int argc, char **argv)")
    if src.index(PRE) < start or src.index(POST) <= src.index(PRE):
        raise ValueError("misordered_probe_phase")
    # Insert helper outside main so there is no public API or ABI change.
    src = src[:start] + HELPER + "\n" + src[start:]
    src = src.replace(PRE, PRE +
      '    if (!c545d_ci_etw_phase_fence(L"baseline_ready.signal", L"trace_armed.signal")) return 8;\n', 1)
    src = src.replace(POST, POST +
      '    if (!c545d_ci_etw_phase_fence(L"precleanup_ready.signal", L"trace_stopped.signal")) return 9;\n', 1)
    assert src.count("c545d_ci_etw_phase_fence(") == 2
    return src

def selftest(src: str) -> None:
    good = patch(src)
    assert "SleepEx(50, TRUE)" in good
    for i, bad in enumerate((
        src.replace(PRE, "", 1),
        src.replace(POST, "", 1),
        src.replace(PRE, PRE + PRE, 1),
        src.replace(POST, POST + POST, 1),
        good,
    )):
        try:
            patch(bad)
        except ValueError:
            continue
        raise AssertionError(f"timing_fence_invalid_probe_accepted,index={i}")
    print("C545D_CI_ETW_PROBE_FENCE_SELFTEST_PASS,positive=1,negative=5,host_modified=0")

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("path", type=Path)
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    original = a.path.read_text(encoding="utf-8")
    if a.selftest:
        selftest(original)
        return
    a.path.write_text(patch(original), encoding="utf-8")
    print("C545D_CI_ETW_PROBE_FENCE_PATCH_PASS,window=after_baseline_before_cleanup,whole_process_idle_proven=0")

if __name__ == "__main__":
    main()
