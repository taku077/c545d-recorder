#!/usr/bin/env python3
"""Disposable CI-only add-on to EXISTING HeapWalk, no extra enumeration.

Adds Windows10-compatible optional Region.dwCommittedSize sum to each
already requested HeapWalk snapshot. A region's committed size may be zero
when the OS cannot report it; some large heaps omit REGION markers.
Never claim full heap/process coverage, global idle, or leak ownership.
"""
from pathlib import Path
import sys


def once(src: str, old: str, new: str, label: str) -> str:
    n = src.count(old)
    if n != 1:
        raise ValueError(f"{label}: expected 1 source anchor, got {n}")
    return src.replace(old, new, 1)


def patch(src: str) -> str:
    src = once(src,
        "    unsigned int size_slot;\n"
        "    memset(c545d_heap_sizes, 0, sizeof(c545d_heap_sizes));",
        "    unsigned int size_slot;\n"
        "    unsigned int c545d_ci_region_count = 0;\n"
        "    unsigned int c545d_ci_region_known = 0;\n"
        "    unsigned int c545d_ci_region_unknown = 0;\n"
        "    unsigned long long c545d_ci_region_commit = 0;\n"
        "    memset(c545d_heap_sizes, 0, sizeof(c545d_heap_sizes));",
        "region counters in original report_heaps")
    src = once(src,
        "        while (HeapWalk(heaps[i], &entry)) {\n"
        "            if (entry.wFlags & PROCESS_HEAP_ENTRY_BUSY) {",
        "        while (HeapWalk(heaps[i], &entry)) {\n"
        "            if (entry.wFlags & PROCESS_HEAP_REGION) {\n"
        "                ++c545d_ci_region_count;\n"
        "                if (entry.Region.dwCommittedSize != 0) {\n"
        "                    ++c545d_ci_region_known;\n"
        "                    c545d_ci_region_commit += entry.Region.dwCommittedSize;\n"
        "                } else ++c545d_ci_region_unknown;\n"
        "            }\n"
        "            if (entry.wFlags & PROCESS_HEAP_ENTRY_BUSY) {",
        "reuse existing locked HeapWalk")
    src = once(src,
        '           busy_blocks, busy_bytes, (unsigned long)found, (unsigned long)bad);\n'
        '    if (bad == 0) {',
        '           busy_blocks, busy_bytes, (unsigned long)found, (unsigned long)bad);\n'
        '    printf("C545D_CI_HEAP_REGION,%s,%d,%u,%u,%u,%llu,%llu,%lu\\n",\n'
        '           label, cycle, c545d_ci_region_count, c545d_ci_region_known,\n'
        '           c545d_ci_region_unknown, c545d_ci_region_commit, busy_bytes,\n'
        '           (unsigned long)bad);\n'
        '    if (bad == 0) {',
        "numeric-only matched resource output")
    return src


def selftest():
    src = (
        "    unsigned int size_slot;\n"
        "    memset(c545d_heap_sizes, 0, sizeof(c545d_heap_sizes));\n"
        "        while (HeapWalk(heaps[i], &entry)) {\n"
        "            if (entry.wFlags & PROCESS_HEAP_ENTRY_BUSY) {\n"
        '           busy_blocks, busy_bytes, (unsigned long)found, (unsigned long)bad);\n'
        "    if (bad == 0) {\n"
    )
    edited = patch(src)
    assert edited.count("entry.Region.dwCommittedSize") == 2
    assert edited.count("C545D_CI_HEAP_REGION,%s,%d") == 1
    cases = (
        src.replace("HeapWalk(heaps[i], &entry)", "HeapWalk(another, &entry)"),
        src.replace("size_slot;", "other_slot;"),
        src.replace("    if (bad == 0) {", "    if (bad != 0) {"),
    )
    for c in cases:
        try:
            patch(c)
        except ValueError:
            continue
        raise AssertionError("drifted source accepted")
    print("C545D_HEAP_REGION_OVERLAY_SELFTEST_PASS,negative_cases=3,"
          "extra_heapwalk_calls=0,host_modified=0")


def main():
    if sys.argv[1:] == ["--selftest"]:
        selftest()
        return
    if len(sys.argv) != 2:
        raise SystemExit("usage: overlay <disposable probe.c>")
    path = Path(sys.argv[1])
    original = path.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    result = patch(original.decode("utf-8").replace("\r\n", "\n"))
    path.write_bytes(result.replace("\n", newline).encode("utf-8"))
    print("C545D_HEAP_REGION_OVERLAY_PATCHED,source_disposable_only=1,"
          "no_new_enumeration=1,registry_untouched=1")


if __name__ == "__main__":
    main()
