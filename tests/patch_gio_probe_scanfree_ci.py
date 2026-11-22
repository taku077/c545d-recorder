#!/usr/bin/env python3
"""CI-only opt-in no-AppInfo-query final census on an isolated probe copy.

Existing tests/gio_appinfo_key_handle_probe.c MUST remain byte-for-byte
unchanged. The additional checkpoint does NOT guarantee OS/worker quiescence,
only excludes a public GAppInfo enumeration *at that checkpoint*.
"""
from pathlib import Path
import sys


def replace_once(src: str, before: str, after: str, label: str) -> str:
    n = src.count(before)
    if n != 1:
        raise ValueError(f"{label}: expected exactly one anchor, found {n}")
    return src.replace(before, after, 1)


def patch(src: str) -> str:
    src = replace_once(src, "    int mutate_registry = 1;",
                       "    int mutate_registry = 1;\n"
                       "    int c545d_ci_scanfree_final = 0;",
                       "opt-in switch storage")
    src = replace_once(src,
                       '        if (strcmp(argv[arg], "--no-registry-change") == 0) mutate_registry = 0;',
                       '        if (strcmp(argv[arg], "--no-registry-change") == 0) mutate_registry = 0;\n'
                       '        else if (strcmp(argv[arg], "--ci-scanfree-final") == 0) c545d_ci_scanfree_final = 1;',
                       "opt-in parser")
    tail = '''    Sleep(2500);
    drain_context();
    enumerate_apps();
    report("settled_cleanup", cycle_count + 2);
    report_key_handles("settled_cleanup", cycle_count + 2);
    report_types("settled_cleanup", cycle_count + 2);
    report_heaps("settled_cleanup", cycle_count + 2);
    report_vm("settled_cleanup", cycle_count + 2);'''
    replacement = '''    Sleep(2500);
    drain_context();
    /* CI-only: avoid a new caller-triggered reparse at the final census.
     * This is not an assurance that the OS watcher/worker has settled.
     */
    if (!c545d_ci_scanfree_final)
        enumerate_apps();
    const char *last = c545d_ci_scanfree_final ? "scanfree_cleanup" : "settled_cleanup";
    report(last, cycle_count + 2);
    report_key_handles(last, cycle_count + 2);
    report_types(last, cycle_count + 2);
    report_heaps(last, cycle_count + 2);
    report_vm(last, cycle_count + 2);'''
    src = replace_once(src, tail, replacement, "caller-free final census")
    return replace_once(src,
                        '    printf("GIO_PROBE_DONE,cycles=%d,notifications=%ld,reg_changes=%d\\n",',
                        '    printf("C545D_CI_SCANFREE_FINAL,enabled=%d\\n", c545d_ci_scanfree_final);\n'
                        '    printf("GIO_PROBE_DONE,cycles=%d,notifications=%ld,reg_changes=%d\\n",',
                        "numeric-only mode marker")


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        src = Path(__file__).with_name("gio_appinfo_key_handle_probe.c").read_text(encoding="utf-8")
        result = patch(src)
        assert 'if (!c545d_ci_scanfree_final)' in result
        assert 'scanfree_cleanup' in result
        for bad in (src.replace("    Sleep(2500);", "    Sleep(1500);"),
                    src.replace("    int mutate_registry = 1;", ""),
                    src.replace('    report_vm("settled_cleanup", cycle_count + 2);', "")):
            try: patch(bad)
            except ValueError: pass
            else: raise AssertionError("drifted probe code accepted")
        print("C545D_SCANFREE_SOURCE_SELFTEST_PASS,negative_cases=3,new_windows_memory_runs=0")
        return
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_gio_probe_scanfree_ci.py <disposable-probe-copy.c>")
    p = Path(sys.argv[1])
    raw = p.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    s = patch(raw.decode("utf-8").replace("\r\n", "\n"))
    p.write_bytes(s.replace("\n", newline).encode("utf-8"))
    print("C545D_SCANFREE_SOURCE_PATCHED,disposable_copy_only=1,original_probe_unchanged=1")


if __name__ == "__main__":
    main()
