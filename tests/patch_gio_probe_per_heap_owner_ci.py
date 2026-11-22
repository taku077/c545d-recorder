#!/usr/bin/env python3
"""CI-only, fail-closed per-heap allocation CAPACITY overlay for Combo16.

Requires earlier patch_gio_probe_heapregion_ci.py applied to a disposable
Windows test probe. Uses the EXISTING HeapWalk pass; no extra heap walking,
compaction, freeing, registry change, process intervention or camera access.

Process-local heap handles are stored in memory but NEVER logged. A heap
ordinal is comparable only within its own process after handle-stability
checks; across processes the only defensible equivalence is DEFAULT heap
versus the aggregate of OTHER heaps. These counters still do not identify
GLib/COM source-allocation ownership or global quiescence.
"""
from pathlib import Path
import sys


def once(source: str, anchor: str, replacement: str, label: str) -> str:
    n = source.count(anchor)
    if n != 1:
        raise ValueError(f"{label}: expected exactly one anchor, found {n}")
    return source.replace(anchor, replacement, 1)


def patch(source: str) -> str:
    if source.count('C545D_CI_HEAP_REGION,%s,%d') != 1:
        raise ValueError("first apply existing optional REGION overlay")
    source = once(source,
        "static void report_heaps(const char *label, int cycle)\n{",
        "#define C545D_CI_OWNER_LIMIT 64\n"
        "static HANDLE c545d_ci_owner_initial[C545D_CI_OWNER_LIMIT];\n"
        "static DWORD c545d_ci_owner_count;\n"
        "static int c545d_ci_owner_ready;\n\n"
        "static void report_heaps(const char *label, int cycle)\n{",
        "stable handle snapshot declaration")
    source = once(source,
        "    unsigned int c545d_ci_region_count = 0;\n",
        "    int c545d_ci_owner_stable = 1;\n"
        "    DWORD c545d_ci_owner_index;\n"
        "    unsigned int c545d_ci_region_count = 0;\n",
        "source-level variables")
    source = once(source,
        "    for (i = 0; i < found; ++i) {\n"
        "        PROCESS_HEAP_ENTRY entry;",
        "    if (found > C545D_CI_OWNER_LIMIT) {\n"
        "        fprintf(stderr, \"C545D_CI_OWNER_ERROR,too_many_heaps\\n\");\n"
        "        free(heaps);\n"
        "        exit(12);\n"
        "    }\n"
        "    if (strcmp(label, \"baseline\") == 0 && cycle == 0) {\n"
        "        memcpy(c545d_ci_owner_initial, heaps, found * sizeof(HANDLE));\n"
        "        c545d_ci_owner_count = found;\n"
        "        c545d_ci_owner_ready = 1;\n"
        "    }\n"
        "    if (!c545d_ci_owner_ready || c545d_ci_owner_count != found)\n"
        "        c545d_ci_owner_stable = 0;\n"
        "    else for (c545d_ci_owner_index = 0;\n"
        "              c545d_ci_owner_index < found; ++c545d_ci_owner_index)\n"
        "        if (c545d_ci_owner_initial[c545d_ci_owner_index] !=\n"
        "            heaps[c545d_ci_owner_index]) c545d_ci_owner_stable = 0;\n"
        "    for (i = 0; i < found; ++i) {\n"
        "        unsigned int c545d_ci_owner_regions = 0;\n"
        "        unsigned int c545d_ci_owner_known = 0;\n"
        "        unsigned int c545d_ci_owner_unknown = 0;\n"
        "        unsigned long long c545d_ci_owner_commit = 0;\n"
        "        unsigned long long c545d_ci_owner_busy = 0;\n"
        "        PROCESS_HEAP_ENTRY entry;",
        "baseline heap identity")
    source = once(source,
        "            if (entry.wFlags & PROCESS_HEAP_REGION) {\n"
        "                ++c545d_ci_region_count;",
        "            if (entry.wFlags & PROCESS_HEAP_REGION) {\n"
        "                ++c545d_ci_owner_regions;\n"
        "                if (entry.Region.dwCommittedSize != 0) {\n"
        "                    ++c545d_ci_owner_known;\n"
        "                    c545d_ci_owner_commit += entry.Region.dwCommittedSize;\n"
        "                } else ++c545d_ci_owner_unknown;\n"
        "                ++c545d_ci_region_count;",
        "per-heap region capture")
    source = once(source,
        "            if (entry.wFlags & PROCESS_HEAP_ENTRY_BUSY) {\n"
        "                busy_bytes += entry.cbData;",
        "            if (entry.wFlags & PROCESS_HEAP_ENTRY_BUSY) {\n"
        "                c545d_ci_owner_busy += entry.cbData;\n"
        "                busy_bytes += entry.cbData;",
        "per-heap live payload capture")
    source = once(source,
        "        if (!HeapUnlock(heaps[i])) bad++;\n"
        "    }\n"
        "    free(heaps);",
        "        if (!HeapUnlock(heaps[i])) bad++;\n"
        "        printf(\"C545D_CI_HEAP_OWNER,%s,%d,%lu,%u,%d,%u,%u,%u,%llu,%llu,%lu\\n\",\n"
        "               label, cycle, (unsigned long)i,\n"
        "               (unsigned int)(heaps[i] == GetProcessHeap()),\n"
        "               c545d_ci_owner_stable, c545d_ci_owner_regions,\n"
        "               c545d_ci_owner_known, c545d_ci_owner_unknown,\n"
        "               c545d_ci_owner_commit, c545d_ci_owner_busy,\n"
        "               (unsigned long)bad);\n"
        "    }\n"
        "    free(heaps);",
        "numeric-only per-heap counters")
    return source


def selftest():
    raw = (
        "static void report_heaps(const char *label, int cycle)\n{\n"
        "    unsigned int c545d_ci_region_count = 0;\n"
        "    for (i = 0; i < found; ++i) {\n"
        "        PROCESS_HEAP_ENTRY entry;\n"
        "            if (entry.wFlags & PROCESS_HEAP_REGION) {\n"
        "                ++c545d_ci_region_count;\n"
        "            if (entry.wFlags & PROCESS_HEAP_ENTRY_BUSY) {\n"
        "                busy_bytes += entry.cbData;\n"
        "        if (!HeapUnlock(heaps[i])) bad++;\n"
        "    }\n"
        "    free(heaps);\n"
        'printf("C545D_CI_HEAP_REGION,%s,%d");\n'
    )
    result = patch(raw)
    assert result.count("C545D_CI_HEAP_OWNER,%s,%d") == 1
    assert result.count("while (HeapWalk(") == 0
    assert result.count("memcpy(c545d_ci_owner_initial, heaps") == 1
    assert "GetProcessHeap()" in result
    for needle in (
        "static void report_heaps(const char *label, int cycle)\n{",
        'printf("C545D_CI_HEAP_REGION,%s,%d");',
        "        if (!HeapUnlock(heaps[i])) bad++;",
        "                ++c545d_ci_region_count;",
    ):
        try:
            patch(raw.replace(needle, "DRIFT", 1))
        except ValueError:
            pass
        else:
            raise AssertionError("changed source anchor accepted")
    print("C545D_HEAP_OWNER_OVERLAY_SELFTEST_PASS,negative_cases=4,"
          "extra_HeapWalk_calls=0,pointers_logged=0,real_host_untouched=1")


def main():
    if sys.argv[1:] == ["--selftest"]:
        selftest()
        return
    if len(sys.argv) != 2:
        raise SystemExit("usage: overlay <disposable-probe.c>")
    file = Path(sys.argv[1])
    original = file.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    edited = patch(original.decode("utf-8").replace("\r\n", "\n"))
    file.write_bytes(edited.replace("\n", newline).encode("utf-8"))
    print("C545D_HEAP_OWNER_OVERLAY_SOURCE_PASS,disposable_only=1,"
          "extra_HeapWalk_calls=0,identity_checked=1,real_host_untouched=1")


if __name__ == "__main__":
    main()
