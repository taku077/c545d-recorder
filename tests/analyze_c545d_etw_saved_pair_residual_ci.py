#!/usr/bin/env python3
"""Check TWO original numeric-only Windows ETW artifacts without a rerun.

The 466 is a subtraction residual, not a deduplicated inventory of 466
addresses or allocation owners. Neither report preserves invalid stack row
counts or free events at item identity granularity. Print no raw paths/frames,
addresses, ETL or registry. Fail closed on run/artifact provenance.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import tempfile

RUNS = ((45059995357, 14768938259), (45062227506, 14770031930))
LINE = re.compile(r"^C545D_[A-Z0-9_]+(?:,[a-zA-Z0-9_]+=-?[a-zA-Z0-9_.]+)+$")
FILES_OLD = {
    "etw-nochange-totals-summary-only.txt",
    "etw-registry-totals-summary-only.txt",
    "etw-registry-stack-gap-summary-only.txt",
    "etw-registry-image-gap-summary-only.txt",
    "same-run-resource-only.txt",
}
FILES_NEW = FILES_OLD | {"etw-worker-stop-qpc-only.txt"}


def read_numeric(directory: Path, expect: set[str]) -> list[tuple[str, dict[str, str]]]:
    if not directory.is_dir():
        raise ValueError("artifact_directory_missing")
    names = {x.name for x in directory.iterdir() if x.is_file()}
    if names != expect or any(x.is_dir() for x in directory.iterdir()):
        raise ValueError("artifact_files_mismatched")
    rows: list[tuple[str, dict[str, str]]] = []
    for name in sorted(expect):
        path = directory / name
        if not 1 <= path.stat().st_size <= 100_000:
            raise ValueError("artifact_numeric_file_size_invalid")
        for line in path.read_text("utf-8-sig").strip().splitlines():
            if LINE.fullmatch(line) is None:
                raise ValueError("raw_or_unallowlisted_artifact_content")
            parts = line.split(",")
            fields: dict[str, str] = {}
            for item in parts[1:]:
                k, val = item.split("=", 1)
                if k in fields:
                    raise ValueError("duplicate_numeric_key")
                fields[k] = val
            rows.append((parts[0], fields))
    return rows


def unique(rows: list[tuple[str, dict[str, str]]], kind: str, **filter: str) -> dict[str, str]:
    match = [f for k, f in rows if k == kind and all(f.get(n) == v for n, v in filter.items())]
    if len(match) != 1:
        raise ValueError("numeric_identity_not_unique")
    return match[0]


def iv(row: dict[str, str], key: str) -> int:
    if not re.fullmatch(r"-?\d+", row.get(key, "")):
        raise ValueError("numeric_field_invalid")
    return int(row[key])


def compare(old_dir: Path, new_dir: Path) -> str:
    rows = [
        read_numeric(old_dir, FILES_OLD),
        read_numeric(new_dir, FILES_NEW),
    ]
    expectations = [
        # Measured in two original, independent disposable Windows jobs.
        {"global_out": 16061, "accepted_out": 15595,
         "global_alloc": 619727, "callbacks": 17, "workers": 18},
        {"global_out": 16252, "accepted_out": 15786,
         "global_alloc": 1323925, "callbacks": 27, "workers": 24},
    ]
    for i, entries in enumerate(rows):
        required = expectations[i]
        no = unique(entries, "C545D_GIO_ETW_HEAP_TOTALS_NUMERIC", arm="nochange")
        reg = unique(entries, "C545D_GIO_ETW_HEAP_TOTALS_NUMERIC", arm="registry")
        diag = unique(entries, "C545D_GIO_ETW_STACK_PARSE_DIAGNOSTIC", arm="registry")
        image = unique(entries, "C545D_GIO_ETW_IMAGE_PARSE_DIAGNOSTIC", arm="registry")
        worker = unique(entries, "C545D_APPINFO_PHASE_TRACE", arm="registry")
        private = unique(entries, "C545D_COMBO16_SCANFREE_RESOURCE",
                         kind="private", window="0_16")
        if iv(no, "total_out") != 0 or iv(reg, "total_alloc") != required["global_alloc"]:
            raise ValueError("unexpected_original_windows_totals")
        if iv(reg, "total_out") != required["global_out"]:
            raise ValueError("original_windows_outstanding_changed")
        if iv(diag, "global_out") != required["global_out"]:
            raise ValueError("global_total_stack_report_mismatch")
        if iv(diag, "accepted_out") != required["accepted_out"]:
            raise ValueError("accepted_stack_report_mismatch")
        if (iv(diag, "unattributed_out") !=
                iv(reg, "total_out") - iv(diag, "accepted_out")):
            raise ValueError("residual_arithmetic_incorrect")
        if iv(diag, "unattributed_out") != 466:
            raise ValueError("archived_466_residual_not_reproduced")
        if any(iv(diag, k) != want for k, want in (
            ("numeric_rows", 1024), ("rejected_rows", 30),
            ("rows_out_exceeds_alloc", 30),
            ("top_limit_may_truncate", 1),
            ("full_source_classification_proven", 0),
        )):
            raise ValueError("invalid_row_or_top_cap_scope_changed")
        if image.get("reason") != "missing_global_or_top_header" or any(
            iv(image, k) != 0 for k in ("global_headers", "top_headers", "alloc_lines")
        ):
            raise ValueError("image_schema_falsely_accepted")
        if iv(worker, "callbacks") != required["callbacks"] or iv(worker, "workers") != required["workers"]:
            raise ValueError("instrumentation_comparability_changed")
        if iv(worker, "quiescence_proven") != 0:
            raise ValueError("worker_quiet_falsely_proven")
        if iv(private, "controlled") != (139264 if i == 0 else 839680):
            raise ValueError("distinct_window_resource_delta_mismatch")
        if i == 1:
            if iv(diag, "gio_wellformed_out") != 15608 or iv(diag, "com_winrt_wellformed_out") != 178:
                raise ValueError("new_source_cohorts_mismatch")
            for arm in ("nochange", "registry"):
                stop = unique(entries, "C545D_GIO_ETW_WORKER_STOP_QPC", arm=arm)
                if (iv(stop, "stop_bracket_observed") != 1
                    or iv(stop, "worker_overlapping_stop_bracket") != 0
                    or iv(stop, "globally_quiet_proven") != 0
                    or iv(stop, "leak_proven") != 0):
                    raise ValueError("stop_bracket_proof_falsified")
    return (
        "C545D_GIO_ETW_SAVED_PAIR_RESIDUAL_RECONCILED,"
        f"older_run={RUNS[0][0]},older_artifact={RUNS[0][1]},"
        f"newer_run={RUNS[1][0]},newer_artifact={RUNS[1][1]},"
        "old_global_out=16061,old_accepted_out=15595,old_residual=466,"
        "new_global_out=16252,new_accepted_out=15786,new_residual=466,"
        "invalid_out_exceeds_alloc_rows=30,top1024_saturated_both=1,"
        "same_residual_not_same_objects=1,rejected_out_raw_not_preserved=1,"
        "new_gio_stack_out=15608,new_com_winrt_stack_out=178,"
        "different_instrumentation=1,process_global_idle_proven=0,"
        "complete_allocation_owner_proven=0,leak_proven=0,"
        "new_windows_runs=0,real_host_untouched=1"
    )


def fixture(directory: Path, newer: bool) -> None:
    directory.mkdir()
    spec = (1323925, 16252, 15786, 27, 24, 839680) if newer else (
        619727, 16061, 15595, 17, 18, 139264)
    alloc, out, accepted, callbacks, workers, delta = spec
    def store(name: str, text: str) -> None:
        (directory / name).write_text(text + "\n", encoding="utf-8")
    store("etw-nochange-totals-summary-only.txt",
          "C545D_GIO_ETW_HEAP_TOTALS_NUMERIC,arm=nochange,total_out=0")
    store("etw-registry-totals-summary-only.txt",
          f"C545D_GIO_ETW_HEAP_TOTALS_NUMERIC,arm=registry,total_alloc={alloc},total_out={out}")
    cohort = ",gio_wellformed_out=15608,com_winrt_wellformed_out=178" if newer else ""
    store("etw-registry-stack-gap-summary-only.txt",
          f"C545D_GIO_ETW_STACK_PARSE_DIAGNOSTIC,arm=registry,global_out={out},"
          f"accepted_out={accepted},unattributed_out=466,numeric_rows=1024,"
          f"rejected_rows=30,rows_out_exceeds_alloc=30,top_limit_may_truncate=1,"
          f"full_source_classification_proven=0{cohort}")
    store("etw-registry-image-gap-summary-only.txt",
          "C545D_GIO_ETW_IMAGE_PARSE_DIAGNOSTIC,arm=registry,"
          "reason=missing_global_or_top_header,global_headers=0,top_headers=0,alloc_lines=0")
    store("same-run-resource-only.txt", "\n".join((
          f"C545D_APPINFO_PHASE_TRACE,arm=registry,callbacks={callbacks},workers={workers},quiescence_proven=0",
          f"C545D_COMBO16_SCANFREE_RESOURCE,kind=private,window=0_16,controlled={delta}")))
    if newer:
        store("etw-worker-stop-qpc-only.txt", "\n".join(
            f"C545D_GIO_ETW_WORKER_STOP_QPC,arm={arm},stop_bracket_observed=1,"
            "worker_overlapping_stop_bracket=0,globally_quiet_proven=0,leak_proven=0"
            for arm in ("nochange", "registry")))


def selftest() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        old, new = root / "old", root / "new"
        fixture(old, False)
        fixture(new, True)
        assert compare(old, new).startswith("C545D_GIO_ETW_SAVED_PAIR_RESIDUAL_RECONCILED,")
        damaged = [
            ("old", "etw-registry-stack-gap-summary-only.txt", "accepted_out=15595", "accepted_out=15596"),
            ("new", "etw-registry-stack-gap-summary-only.txt", "unattributed_out=466", "unattributed_out=465"),
            ("old", "etw-registry-stack-gap-summary-only.txt", "rejected_rows=30", "rejected_rows=29"),
            ("new", "etw-registry-stack-gap-summary-only.txt", "com_winrt_wellformed_out=178", "com_winrt_wellformed_out=179"),
            ("new", "same-run-resource-only.txt", "callbacks=27", "callbacks=17"),
            ("old", "same-run-resource-only.txt", "controlled=139264", "controlled=839680"),
            ("new", "etw-worker-stop-qpc-only.txt", "globally_quiet_proven=0", "globally_quiet_proven=1"),
            ("old", "etw-registry-image-gap-summary-only.txt", "global_headers=0", "global_headers=1"),
            ("new", "etw-worker-stop-qpc-only.txt", "leak_proven=0", "leak_proven=1"),
        ]
        for i, (folder, filename, oldtext, newtext) in enumerate(damaged):
            path = (old if folder == "old" else new) / filename
            original = path.read_text("utf-8")
            path.write_text(original.replace(oldtext, newtext, 1), encoding="utf-8")
            try:
                compare(old, new)
            except ValueError:
                pass
            else:
                raise AssertionError(f"unsafe_mutation_accepted:{i}")
            path.write_text(original, encoding="utf-8")
        path = new / "raw-address.etl"
        path.write_bytes(b"raw")
        try:
            compare(old, new)
        except ValueError:
            pass
        else:
            raise AssertionError("extra_raw_file_accepted")
    print("C545D_GIO_ETW_SAVED_PAIR_SELFTEST_PASS,positive=1,negative=10,"
          "same_residual_not_source_identity=1,artifact_sanitized=1,new_windows_runs=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--old", type=Path)
    p.add_argument("--new", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    if args.old is None or args.new is None:
        p.error("--old and --new artifact directories required")
    print(compare(args.old, args.new))


if __name__ == "__main__":
    main()
