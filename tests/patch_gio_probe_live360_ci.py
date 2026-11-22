#!/usr/bin/env python3
"""Inject a bounded 360B live-block census into a disposable Combo16 probe.

Apply ONLY after the existing scanfree, phase, REGION and per-heap overlays.
This appends to the existing HeapWalk loop (no additional walk), stores
raw pointers solely in static in-process arrays, and emits numeric row
counts only after HeapUnlock. Address overlap is NOT allocation lifetime.
"""
from __future__ import annotations

from pathlib import Path
import sys

import patch_gio_probe_scanfree_ci as scanfree
import patch_gio_probe_phase_census_ci as phase
import patch_gio_probe_heapregion_ci as region
import patch_gio_probe_per_heap_owner_ci as owner

HEADER = "c545d_heap360_live_scope.h"


def once(src: str, old: str, new: str) -> str:
    if src.count(old) != 1:
        raise ValueError("unexpected source drift / duplicate insertion")
    return src.replace(old, new, 1)


def patch(src: str, header: str) -> str:
    if "C545D_CI_OWNER_LIMIT 64" not in src or "scanfree_cleanup" not in src:
        raise ValueError("prior scanfree/per-heap owner overlays required")
    if "C545D_CI_LIVE360_SNAPSHOT" in src or "C545D_LIVE360_MAX" in src:
        raise ValueError("live360 overlay already present")
    if "#define C545D_LIVE360_MAX 4096U" not in header:
        raise ValueError("unexpected collector capacity")
    src = once(src, "#define C545D_CI_OWNER_LIMIT 64\n",
               header + "\n#define C545D_CI_OWNER_LIMIT 64\n")
    src = once(
        src, "    int c545d_ci_owner_stable = 1;\n",
        "    int c545d_ci_owner_stable = 1;\n"
        "    int c545d_live360_phase = c545d_live360_stage(label, cycle);\n"
    )
    src = once(
        src, "                c545d_ci_owner_busy += entry.cbData;\n",
        "                c545d_live360_collect(c545d_live360_phase, i, &entry);\n"
        "                c545d_ci_owner_busy += entry.cbData;\n"
    )
    src = once(
        src, "    free(heaps);\n    printf(\"GIO_HEAP,%s,%d,",
        "    free(heaps);\n"
        "    if (!c545d_live360_finish(c545d_live360_phase,\n"
        "                               c545d_ci_owner_stable, bad)) {\n"
        "        fprintf(stderr, \"C545D_CI_LIVE360_ERROR,unsafe_or_incomplete\\n\");\n"
        "        exit(26);\n"
        "    }\n"
        "    printf(\"GIO_HEAP,%s,%d,"
    )
    return src


def source_fixture() -> str:
    text = Path(__file__).with_name("gio_appinfo_key_handle_probe.c").read_text()
    return owner.patch(region.patch(phase.patch(scanfree.patch(text))))


def selftest() -> None:
    header = Path(__file__).with_name(HEADER).read_text()
    fixture = source_fixture()
    result = patch(fixture, header)
    if result.count("while (HeapWalk(") != fixture.count("while (HeapWalk("):
        raise AssertionError("unexpected additional HeapWalk")
    if result.count("HeapLock(") != fixture.count("HeapLock("):
        raise AssertionError("unexpected additional heap lock")
    for needle in (
        "c545d_live360_collect(c545d_live360_phase, i, &entry)",
        "c545d_live360_finish(c545d_live360_phase,",
        "continuous_lifetime_proven=0",
        "raw_address_emitted=0",
        "address_reuse_unexcluded=1",
    ):
        if needle not in result:
            raise AssertionError("live360 safety marker missing")
    bad = [
        fixture.replace("    int c545d_ci_owner_stable = 1;", "    int broken=0;", 1),
        fixture.replace("                c545d_ci_owner_busy += entry.cbData;",
                        "                busy_bytes += entry.cbData;", 1),
        fixture.replace("    free(heaps);\n    printf(\"GIO_HEAP,%s,%d,",
                        "    printf(\"GIO_HEAP,%s,%d,", 1),
        result,
        fixture.replace("#define C545D_CI_OWNER_LIMIT 64", "INVALID", 1),
    ]
    for corrupt in bad:
        try:
            patch(corrupt, header)
        except ValueError:
            continue
        raise AssertionError("unsafe source drift accepted")
    print(
        "C545D_LIVE360_OVERLAY_SELFTEST_PASS,"
        "positive=1,negative=5,additional_heapwalk=0,"
        "snapshot_count=4,raw_addresses_emitted=0,"
        "continuity_not_proven=1,windows_runs=0"
    )


def main() -> None:
    if sys.argv[1:] == ["--selftest"]:
        selftest()
        return
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_gio_probe_live360_ci.py <disposable.c>")
    path = Path(sys.argv[1])
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    header = Path(__file__).with_name(HEADER).read_text(encoding="utf-8")
    patched = patch(raw.decode("utf-8").replace("\r\n", "\n"), header)
    path.write_bytes(patched.replace("\n", newline).encode("utf-8"))
    print(
        "C545D_LIVE360_OVERLAY_PATCHED,disposable_copy_only=1,"
        "additional_heapwalk=0,raw_addresses_emitted=0,"
        "original_probe_unchanged=1"
    )


if __name__ == "__main__":
    main()
