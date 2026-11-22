#!/usr/bin/env python3
"""CI-only monotonic observation markers for a disposable scanfree probe copy.

Run AFTER patch_gio_probe_scanfree_ci.py. No new public GAppInfo calls,
registry modifications, or camera access are added. A 2.5 second silent
window is a bounded observation, NOT a guaranteed worker-idle handshake.
"""
from pathlib import Path
import sys


def once(src: str, before: str, after: str, label: str) -> str:
    n = src.count(before)
    if n != 1:
        raise ValueError(f"{label}: expected one source anchor; found {n}")
    return src.replace(before, after, 1)


def patch(src: str) -> str:
    if "C545D_CI_SCANFREE_FINAL,enabled=" not in src:
        raise ValueError("scanfree disposable probe patch is missing")
    src = once(
        src, '    report("after_cleanup", cycle_count + 1);',
        '    printf("C545D_CI_PROBE_PHASE,phase=after_cleanup,tick_ms=%llu\\n",\n'
        '           (unsigned long long) GetTickCount64 ());\n'
        '    report("after_cleanup", cycle_count + 1);',
        "post-cleanup marker")
    src = once(
        src, '    Sleep(2500);\n    drain_context();',
        '    printf("C545D_CI_PROBE_PHASE,phase=idle_begin,tick_ms=%llu\\n",\n'
        '           (unsigned long long) GetTickCount64 ());\n'
        '    Sleep(2500);\n    drain_context();\n'
        '    printf("C545D_CI_PROBE_PHASE,phase=idle_end,tick_ms=%llu\\n",\n'
        '           (unsigned long long) GetTickCount64 ());',
        "bounded observation window")
    return once(
        src, '    report(last, cycle_count + 2);',
        '    printf("C545D_CI_PROBE_PHASE,phase=scanfree_cleanup,tick_ms=%llu\\n",\n'
        '           (unsigned long long) GetTickCount64 ());\n'
        '    report(last, cycle_count + 2);',
        "last scanfree observation")


def selftest() -> None:
    src = (
        'printf("C545D_CI_SCANFREE_FINAL,enabled=%d\\n", x);\n'
        '    report("after_cleanup", cycle_count + 1);\n'
        '    Sleep(2500);\n    drain_context();\n'
        '    report(last, cycle_count + 2);\n'
    )
    out = patch(src)
    for label in ("after_cleanup", "idle_begin", "idle_end", "scanfree_cleanup"):
        assert f"phase={label}" in out
    for broken in (
        src.replace("    Sleep(2500);", "    Sleep(1000);"),
        src.replace("    report(last, cycle_count + 2);", ""),
        src.replace("C545D_CI_SCANFREE_FINAL", "INVALID"),
    ):
        try: patch(broken)
        except ValueError: pass
        else: raise AssertionError("drifted probe accepted")
    print("C545D_PROBE_PHASE_SOURCE_SELFTEST_PASS,negative_cases=3,"
          "windows_runs=0,production_untouched=1")


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        selftest()
        return
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_gio_probe_phase_census_ci.py <disposable-probe-copy.c>")
    path = Path(sys.argv[1])
    original = path.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    patched = patch(original.decode("utf-8").replace("\r\n", "\n"))
    path.write_bytes(patched.replace("\n", newline).encode("utf-8"))
    print("C545D_PROBE_PHASE_SOURCE_PATCHED,scanfree=1,monotonic_ticks=1,"
          "quiescence_proven=0")


if __name__ == "__main__":
    main()
