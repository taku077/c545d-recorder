#!/usr/bin/env python3
"""Bounded, disposable, two-comparable-active-epoch GIO probe overlay.

Run only on a copied tests/gio_appinfo_key_handle_probe.c in an isolated Windows
CI runner, never on the installed recorder. No sensitive event data logged.
The original first-AppInfo fence/collector is a separate overlay; this only
adds explicit baseline, cycle1, cycle2 QPC+CPU checkpoints after identical VM
and heap inventory work. Checkpoints do NOT themselves imply worker quiescence.
"""
from __future__ import annotations
import argparse
from pathlib import Path

ARG = '        else if (strcmp(argv[arg], "--cycles=64") == 0) cycle_count = 64;\n'
BASE = '    report_vm("baseline", 0);\n'
CYCLE_IF = '        if (i % (cycle_count > 64 ? 64 : 16) == 0 || i == cycle_count) {\n'
CYCLE_TAIL = '            report_vm("cycle", i);\n        }\n    }\n'
MAIN = 'int main(int argc, char **argv)\n{'
HELPER = r'''
/* Numeric QPC and process CPU checkpoints; only disposable Windows CI. */
static int c545d_ci_active_epoch_checkpoint(const char *phase, int cycle)
{
    LARGE_INTEGER qpc;
    FILETIME created, exited, kernel, user;
    ULARGE_INTEGER k, u;
    if (!QueryPerformanceCounter(&qpc) ||
        !GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user))
        return 0;
    k.LowPart = kernel.dwLowDateTime;
    k.HighPart = kernel.dwHighDateTime;
    u.LowPart = user.dwLowDateTime;
    u.HighPart = user.dwHighDateTime;
    printf("C545D_CI_ACTIVE_EPOCH,%s,%d,%lld,%llu,%llu\n",
           phase, cycle, (long long)qpc.QuadPart,
           (unsigned long long)k.QuadPart,
           (unsigned long long)u.QuadPart);
    fflush(stdout);
    return 1;
}
'''

def patch(src: str) -> str:
    if "c545d_ci_active_epoch_checkpoint" in src:
        raise ValueError("active_epoch_overlay_already_applied")
    for anchor in (ARG, BASE, CYCLE_IF, CYCLE_TAIL, MAIN):
        if src.count(anchor) != 1:
            raise ValueError("missing_or_duplicated_active_epoch_source_anchor")
    if not (src.index(MAIN) < src.index(BASE) < src.index(CYCLE_IF) < src.index(CYCLE_TAIL)):
        raise ValueError("active_epoch_measurement_order_invalid")
    # Immutable patch sequence; never use regex interpolation on untrusted C.
    src = src.replace(MAIN, HELPER + "\n" + MAIN, 1)
    src = src.replace(ARG, ARG +
        '        else if (strcmp(argv[arg], "--cycles=2") == 0) cycle_count = 2;\n', 1)
    src = src.replace(BASE, BASE +
        '    if (cycle_count == 2 &&\n'
        '        !c545d_ci_active_epoch_checkpoint("baseline", 0)) return 11;\n', 1)
    src = src.replace(CYCLE_IF,
        '        if (cycle_count == 2 || i % (cycle_count > 64 ? 64 : 16) == 0 || i == cycle_count) {\n', 1)
    src = src.replace(CYCLE_TAIL,
        '            report_vm("cycle", i);\n'
        '        }\n'
        '        if (cycle_count == 2 &&\n'
        '            !c545d_ci_active_epoch_checkpoint("cycle", i)) return 12;\n'
        '    }\n', 1)
    if src.count("c545d_ci_active_epoch_checkpoint(") != 3:
        raise ValueError("unexpected_checkpoint_call_count")
    for term in ('"baseline", 0', '"cycle", i', '"--cycles=2"'):
        if term not in src:
            raise ValueError("checkpoint_phase_or_cycle_mode_lost")
    return src

def selftest() -> None:
    sample = (MAIN + "\n" + ARG + BASE + CYCLE_IF +
              CYCLE_TAIL + "    return 0;\n}\n")
    ok = patch(sample)
    assert ok.index('c545d_ci_active_epoch_checkpoint("baseline"') < \
           ok.index('c545d_ci_active_epoch_checkpoint("cycle"')
    assert "cycle_count == 2 ||" in ok
    assert "GetProcessTimes(GetCurrentProcess()" in ok
    assert "QueryPerformanceCounter(&qpc)" in ok
    rejected = 0
    cases = [
        ok, sample.replace(ARG, ""), sample.replace(BASE, ""),
        sample.replace(CYCLE_TAIL, ""),
        sample.replace(MAIN, "int main(void)\n{"),
        sample.replace(BASE, BASE + BASE),
        sample.replace(CYCLE_IF, CYCLE_IF + CYCLE_IF),
        sample.replace(CYCLE_TAIL, CYCLE_TAIL + CYCLE_TAIL),
        sample.replace(CYCLE_IF, "").replace(BASE, CYCLE_IF + BASE),
    ]
    for bad in cases:
        try:
            patch(bad)
        except ValueError:
            rejected += 1
        else:
            raise AssertionError("invalid_active_epoch_overlay_accepted")
    assert rejected == len(cases)
    print(f"C545D_GIO_ACTIVE_TWO_EPOCH_PATCH_SELFTEST_PASS,positive=1,"
          f"negative={rejected},qpc_cpu_monotonic_check_pending=1,"
          "worker_quiescence_not_assumed=1,recorder_host_untouched=1")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?", type=Path)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if args.source is None:
        ap.error("isolated disposable source path required")
    if args.source.name != "c545d_gio_preinit_probe.c":
        raise ValueError("refusing_non_disposable_source")
    raw = args.source.read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    rendered = patch(raw.decode("utf-8").replace("\r\n", "\n"))
    args.source.write_bytes(rendered.replace("\n", nl).encode("utf-8"))
    print("C545D_GIO_ACTIVE_TWO_EPOCH_SOURCE_PATCH_PASS,cycles=2,"
          "qpc_and_cpu_bracketed=1,same_process=1,CI_only=1,"
          "worker_quiescence_not_proven=1,host_untouched=1")

if __name__ == "__main__":
    main()
