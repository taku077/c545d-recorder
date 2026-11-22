#!/usr/bin/env python3
"""Fail-closed eight-bin BUSY-only overlay on disposable short GIO probe.

Requires scanfree+phase+region+per-heap overlays. Adds NO HeapWalk and NO
HeapLock. The only saved data are eight per-stage counts and data-byte
sums (not addresses, stacks, symbol strings or unrestricted bin lists).
"""
from __future__ import annotations
from pathlib import Path
import sys
import patch_gio_probe_scanfree_ci as scanfree
import patch_gio_probe_phase_census_ci as phase
import patch_gio_probe_heapregion_ci as region
import patch_gio_probe_per_heap_owner_ci as owner

HEADER = "c545d_ci_busy_bands.h"


def once(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise ValueError("source_change_or_duplicate_insertion")
    return text.replace(before, after, 1)


def patch(text: str, header: str) -> str:
    if ("#define C545D_CI_OWNER_LIMIT 64" not in text or
            "scanfree_cleanup" not in text or
            "#define C545D_BUSY_BANDS 8" not in header or
            "C545D_CI_BUSY_BAND" in text):
        raise ValueError("not_disposable_or_already_instrumented")
    before_walk = text.count("while (HeapWalk(")
    before_lock = text.count("HeapLock(")
    text = once(
        text, "#define C545D_CI_OWNER_LIMIT 64\n",
        header + "\n#define C545D_CI_OWNER_LIMIT 64\n",
    )
    text = once(
        text, "    int c545d_ci_owner_stable = 1;\n",
        "    int c545d_ci_owner_stable = 1;\n"
        "    int c545d_ci_band_stage = c545d_busy_band_stage(label, cycle);\n",
    )
    text = once(
        text, "                c545d_ci_owner_busy += entry.cbData;\n",
        "                c545d_busy_band_collect(c545d_ci_band_stage, &entry);\n"
        "                c545d_ci_owner_busy += entry.cbData;\n",
    )
    text = once(
        text, '    free(heaps);\n    printf("GIO_HEAP,%s,%d,',
        '    free(heaps);\n'
        '    if (!c545d_busy_band_finish(c545d_ci_band_stage,\n'
        '                               c545d_ci_owner_stable, bad,\n'
        '                               busy_blocks, busy_bytes)) {\n'
        '        fprintf(stderr, "C545D_CI_BUSY_BANDS_ERROR,invalid_numeric_census\\n");\n'
        '        exit(29);\n'
        '    }\n'
        '    printf("GIO_HEAP,%s,%d,',
    )
    if (text.count("while (HeapWalk(") != before_walk or
            text.count("HeapLock(") != before_lock or
            text.count("C545D_CI_BUSY_BAND,stage=") != 1):
        raise ValueError("extra_heap_enumeration_or_lost_schema")
    return text


def fixture() -> str:
    s = Path(__file__).with_name("gio_appinfo_key_handle_probe.c").read_text()
    return owner.patch(region.patch(phase.patch(scanfree.patch(s))))


def selftest() -> None:
    before = fixture()
    header = Path(__file__).with_name(HEADER).read_text()
    edited = patch(before, header)
    assert edited.count("c545d_busy_band_collect(c545d_ci_band_stage") == 1
    assert edited.count("c545d_busy_band_finish(c545d_ci_band_stage") == 1
    variations = [
        edited,
        before.replace("#define C545D_CI_OWNER_LIMIT 64", "INVALID", 1),
        before.replace("                c545d_ci_owner_busy += entry.cbData;",
                       "                data += entry.cbData;", 1),
        before.replace("    int c545d_ci_owner_stable = 1;",
                       "    int unsafe_stage = 1;", 1),
        before.replace('    free(heaps);\n    printf("GIO_HEAP,%s,%d,',
                       '    printf("GIO_HEAP,%s,%d,', 1),
    ]
    for broken in variations:
        try:
            patch(broken, header)
        except ValueError:
            continue
        raise AssertionError("source drift or duplicate accepted")
    print("C545D_BUSY_BANDS_OVERLAY_SELFTEST_PASS,"
          "positive=1,negative=5,extra_heapwalk=0,"
          "pointer_output=0,windows_runs=0")


def main() -> None:
    if sys.argv[1:] == ["--selftest"]:
        selftest()
        return
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_gio_probe_busy_bands_ci.py <disposable.c>")
    p = Path(sys.argv[1])
    raw = p.read_bytes()
    eol = "\r\n" if b"\r\n" in raw else "\n"
    header = Path(__file__).with_name(HEADER).read_text(encoding="utf-8")
    p.write_bytes(
        patch(raw.decode("utf-8").replace("\r\n", "\n"), header)
        .replace("\n", eol).encode("utf-8")
    )
    print("C545D_BUSY_BANDS_OVERLAY_PASS,disposable_only=1,"
          "extra_heapwalk=0,raw_pointer_output=0,release_approved=0")


if __name__ == "__main__":
    main()
