#!/usr/bin/env python3
"""CI-only, number-only comparison of genuine PackageCatalog events vs GIO rescans.

Natural scans (5..7) execute before any registry stimulus for that stage;
forced stage 0..3 scans are the POSITIVE CONTROL after same-run HKCU stimulus.
A result describes one Windows runner, never proves a Windows10 host behavior.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

NATURAL = re.compile(r"(?m)^C545D_GIO_REAL_MSIX_NATURAL_STAGE,stage=(\d+),apps=(\d+)\s*$")
CONTROL = re.compile(r"(?m)^C545D_GIO_REAL_MSIX_STEP_OK,stage=(\d+),apps=(\d+)\s*$")
EVENT = re.compile(
    r"C545D_REAL_PACKAGECATALOG_EVENT_PASS,"
    r"install_delta=(\d+),update_delta=(\d+),uninstall_delta=(\d+),"
    r"total_delta=(\d+),install_complete=(\d+),update_complete=(\d+),"
    r"uninstall_complete=(\d+),.*?only_ci_package_events_counted=true"
)
CLEANUP = "C545D_REAL_APPX_CLEANUP_EXECUTED=true"
PARALLEL = re.compile(r"(?m)^C545D_GIO_PARALLEL_QUERY_PASS,stage=(\d+),callers=(\d+),apps=(\d+),failures=0,real_os_package_event=1\s*$")
QUEUED = re.compile(r"(?m)^C545D_CI_LAZY_RESCAN_QUEUED,seq=(\d+)\s*$")


def parse(data: str) -> dict[str, int | str]:
    if CLEANUP not in data:
        raise ValueError("missing disposable package and certificate cleanup")
    events = EVENT.findall(data)
    if len(events) != 1:
        raise ValueError("expected exactly one real filtered PackageCatalog lifecycle")
    ins, upd, rem, total, ci, cu, cr = map(int, events[0])
    if not (ins > 0 and upd > 0 and rem > 0 and total == ins + upd + rem
            and ci > 0 and cu > 0 and cr > 0):
        raise ValueError("missing real event or completion evidence")

    def checked_map(pattern: re.Pattern[str], required: set[int]) -> dict[int, int]:
        matches = [(int(i), int(count)) for i, count in pattern.findall(data)]
        if len(matches) != len(required) or set(i for i, _ in matches) != required:
            raise ValueError("missing/duplicate/unexpected stage evidence")
        if any(count <= 0 for _, count in matches):
            raise ValueError("impossible AppInfo population")
        return dict(matches)

    natural = checked_map(NATURAL, {1, 2, 3})
    control = checked_map(CONTROL, {0, 1, 2, 3, 4})
    baseline = control[0]
    if (control[1] != baseline + 1 or control[2] != baseline + 1
            or control[3] != baseline or control[4] != baseline):
        raise ValueError("explicit registry-change positive control did not track package lifecycle")
    if natural[1] not in {baseline, baseline + 1}:
        raise ValueError("natural install observation outside expected population")
    if natural[2] != baseline + 1:
        raise ValueError("natural update observation outside installed population")
    if natural[3] not in {baseline, baseline + 1}:
        raise ValueError("natural uninstall observation outside expected population")

    return {
        "baseline_apps": baseline,
        "natural_install_apps": natural[1],
        "positive_control_install_apps": control[1],
        "natural_update_apps": natural[2],
        "positive_control_update_apps": control[2],
        "natural_uninstall_apps": natural[3],
        "positive_control_uninstall_apps": control[3],
        "natural_install_refreshed": int(natural[1] == baseline + 1),
        "natural_uninstall_refreshed": int(natural[3] == baseline),
        "real_events": total,
        "terminal_completions": ci + cu + cr,
    }


def validate_parallel(data: str, values: dict[str, int | str],
                      expect_parser_fault: bool = False) -> None:
    rows = [(int(stage), int(callers), int(apps))
            for stage, callers, apps in PARALLEL.findall(data)]
    if (len(rows) != 3 or {stage for stage, _, _ in rows} != {1, 2, 3}
            or any(callers != 8 for _, callers, _ in rows)):
        raise ValueError("missing/duplicate or failed 8-way Windows GAppInfo query")
    for stage, _, apps in rows:
        if apps != values[f"natural_{('install', 'update', 'uninstall')[stage-1]}_apps"]:
            raise ValueError("parallel GAppInfo callers disagreed with natural count")
    seq = [int(n) for n in QUEUED.findall(data)]
    expected = [1, 2, 3, 4] if expect_parser_fault else [1, 2, 3]
    if seq != expected:
        raise ValueError(f"duplicate or missing queued GLib generation rebuild: {seq!r}")
    faults = len(re.findall(r"(?m)^C545D_CI_PACKAGE_PARSE_FAULT,once=1\s*$", data))
    if faults != int(expect_parser_fault):
        raise ValueError(f"wrong one-shot parser failure count: {faults}")

def selftest() -> None:
    fixture = "\n".join([
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=0,apps=39",
        "C545D_GIO_REAL_MSIX_NATURAL_STAGE,stage=1,apps=39",
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=1,apps=40",
        "C545D_GIO_REAL_MSIX_NATURAL_STAGE,stage=2,apps=40",
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=2,apps=40",
        "C545D_GIO_REAL_MSIX_NATURAL_STAGE,stage=3,apps=40",
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=3,apps=39",
        "C545D_GIO_REAL_MSIX_STEP_OK,stage=4,apps=39",
        "C545D_REAL_PACKAGECATALOG_EVENT_PASS,install_delta=9,update_delta=7,"
        "uninstall_delta=2,total_delta=18,install_complete=1,"
        "update_complete=1,uninstall_complete=1,no_synthetic_notifications=true,"
        "only_ci_package_events_counted=true,gio_same_process=True,CI_only=true",
        CLEANUP + ",runner_only=true"
    ]) + "\n"
    r = parse(fixture)
    assert (r["baseline_apps"], r["natural_install_refreshed"],
            r["natural_uninstall_refreshed"], r["real_events"]) == (39, 0, 0, 18)
    auto = fixture.replace("NATURAL_STAGE,stage=1,apps=39",
                           "NATURAL_STAGE,stage=1,apps=40").replace(
                               "NATURAL_STAGE,stage=3,apps=40",
                               "NATURAL_STAGE,stage=3,apps=39")
    assert parse(auto)["natural_install_refreshed"] == 1
    assert parse(auto)["natural_uninstall_refreshed"] == 1
    invalid = [
        fixture.replace(CLEANUP, "UNVERIFIED_CLEANUP"),
        fixture + "C545D_GIO_REAL_MSIX_NATURAL_STAGE,stage=1,apps=39\n",
        fixture.replace("STEP_OK,stage=1,apps=40", "STEP_OK,stage=1,apps=39"),
        fixture.replace("total_delta=18", "total_delta=17"),
        fixture.replace("install_complete=1", "install_complete=0"),
        fixture.replace("NATURAL_STAGE,stage=2,apps=40",
                        "NATURAL_STAGE,stage=2,apps=38"),
        fixture.replace("only_ci_package_events_counted=true",
                        "only_ci_package_events_counted=false"),
    ]
    for i, broken in enumerate(invalid):
        try:
            parse(broken)
        except ValueError:
            continue
        raise AssertionError(f"corrupt evidence {i} incorrectly accepted")
    print("C545D_NATURAL_MSIX_ANALYZER_SELFTEST_PASS,valid=2,rejected=7")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--expect-parallel", action="store_true")
    ap.add_argument("--expect-parser-fault", action="store_true")
    ap.add_argument("--input", type=Path,
                    default=Path("artifacts/real_msix_natural_output.txt"))
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    raw = args.input.read_text(encoding="utf-8-sig", errors="replace")
    values = parse(raw)
    if args.expect_parser_fault and not args.expect_parallel:
        raise ValueError('parser fault check requires parallel query evidence')
    if args.expect_parallel:
        validate_parallel(raw, values, args.expect_parser_fault)
        values["parallel_eight_callers_each_event"] = 1
        values["lazy_epoch_rebuilds_queued"] = 4 if args.expect_parser_fault else 3
        values["parser_failure_retried"] = int(args.expect_parser_fault)
    fields = ",".join(f"{k}={v}" for k, v in values.items())
    print(f"C545D_NATURAL_MSIX_REFRESH_OBSERVATION,{fields},"
          "window_s=1.3,update_freshness_not_proven=1,"
          "windows_ci_only=1,host_not_certified=1")


if __name__ == "__main__":
    main()
