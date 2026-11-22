#!/usr/bin/env python3
"""Pinned GLib 2.82.4 tracepoint-capability audit for existing Windows CI.

The original source has TRACE(GLIB_MEM_ALLOC) invocations, but glib_trace.h
compiles TRACE() away when HAVE_DTRACE is unset. Earlier isolated *actual*
MSVC GLib build #45000301159 printed dtrace:false/systemtap:false.
Source check is NOT a new Windows binary build or real allocation capture.
Avoid recommending now-unavailable GLib TRACE as leak stack evidence.
"""
from __future__ import annotations
import argparse
from pathlib import Path


def audit(header: str, meson: str, gmem: str) -> list[str]:
    needles = (
        "#if defined(HAVE_DTRACE) && !defined(__clang_analyzer__)",
        '#include "glib_probes.h"',
        "#define TRACE(probe) probe",
        "#define TRACE(probe)\n",
    )
    if any(header.count(marker) != 1 for marker in needles):
        raise ValueError("GLib TRACE macro provenance changed")
    if not (header.index(needles[0]) < header.index(needles[1])
            < header.index(needles[2]) < header.index(needles[3])):
        raise ValueError("DTrace on/off macro order changed")
    required_meson = (
        "enable_dtrace = dtrace_option.allowed()",
        "if enable_dtrace",
        "glib_conf.set('HAVE_DTRACE', 1)",
        "'dtrace' : enable_dtrace,",
    )
    if (meson.count("if enable_dtrace") < 1 or
            any(meson.count(marker) != 1 for marker in required_meson
                if marker != "if enable_dtrace")):
        raise ValueError("GLib DTrace Meson conditional changed")
    if not (meson.index(required_meson[0]) < meson.index(required_meson[1])
            < meson.index(required_meson[2])):
        raise ValueError("HAVE_DTRACE no longer conditional on feature")
    required_memory = (
        "TRACE (GLIB_MEM_ALLOC((void*) mem, (unsigned int) n_bytes, 0, 0));",
        "TRACE (GLIB_MEM_FREE ((void*) mem));",
    )
    if any(gmem.count(marker) != 1 for marker in required_memory):
        raise ValueError("original memory TRACE invocation changed")
    return [
        "C545D_GLIB2824_TRACE_SOURCE,source_tag=2.82.4,"
        "TRACE_requires_HAVE_DTRACE=1,"
        "TRACE_compiles_to_noop_when_missing=1,"
        "glib_malloc_and_free_trace_sites_present=1,"
        "HAVE_DTRACE_controlled_by_Meson_feature=1",
        "C545D_GLIB2824_TRACE_SCOPE,"
        "prior_windows_run=45000301159,"
        "prior_windows_build_log_dtrace_false=1,"
        "prior_windows_build_log_systemtap_false=1,"
        "source_only_not_new_windows_reverification=1,"
        "allocation_stack_owner_unidentified=1,"
        "ETW_new_capture_authorized=0",
        "C545D_GLIB2824_TRACE_SOURCE_PASS,"
        "windows_runs=0,user_host_untouched=1,"
        "production_dll_unchanged=1",
    ]


def selftest() -> None:
    header = (
        "#if defined(HAVE_DTRACE) && !defined(__clang_analyzer__)\n"
        '#include "glib_probes.h"\n'
        "#define TRACE(probe) probe\n"
        "#else\n#define TRACE(probe)\n#endif\n"
    )
    meson = (
        "enable_dtrace = dtrace_option.allowed()\n"
        "if enable_dtrace\n"
        "glib_conf.set('HAVE_DTRACE', 1)\n"
        "'dtrace' : enable_dtrace,\n"
    )
    gmem = (
        "TRACE (GLIB_MEM_ALLOC((void*) mem, (unsigned int) n_bytes, 0, 0));\n"
        "TRACE (GLIB_MEM_FREE ((void*) mem));\n"
    )
    assert len(audit(header, meson, gmem)) == 3
    mutants = (
        (header.replace("#define TRACE(probe)\n", "#define TRACE(probe) probe\n"),
         meson, gmem),
        (header.replace("defined(HAVE_DTRACE)", "defined(WIN32)"), meson, gmem),
        (header.replace('#include "glib_probes.h"', ""), meson, gmem),
        (header, meson.replace("if enable_dtrace", "if host_system == 'windows'"),
         gmem),
        (header, meson.replace("HAVE_DTRACE", "HAVE_UNKNOWN"), gmem),
        (header, meson, gmem.replace("TRACE (GLIB_MEM_FREE", "LOG (GLIB_MEM_FREE")),
    )
    for h, m, g in mutants:
        try:
            audit(h, m, g)
        except ValueError:
            continue
        raise AssertionError("unverified memory TRACE condition accepted")
    print("C545D_GLIB2824_TRACE_SOURCE_SELFTEST_PASS,"
          "negative_cases=6,positive_cases=1,new_windows_runs=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--glib-root", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    if args.glib_root is None:
        p.error("--glib-root is required")
    root = args.glib_root
    for line in audit(
        (root / "glib" / "glib_trace.h").read_text(encoding="utf-8"),
        (root / "meson.build").read_text(encoding="utf-8"),
        (root / "glib" / "gmem.c").read_text(encoding="utf-8"),
    ):
        print(line)


if __name__ == "__main__":
    main()
