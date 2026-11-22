#!/usr/bin/env python3
"""Offline CI-only GIO ETW owner/lifetime scope reconciliation.

Consumes only sanitized original numeric artifact from Windows run 45059995357.
Do not infer causality from distinct windows or from a GIO-containing stack.
The active-after-cleanup worker demonstrates the expected-lifetime boundary
was NOT globally proven in this run. Never log raw symbols/ETL/pointers.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import tempfile

SOURCE_RUN = 45059995357
ARTIFACT_ID = 14768938259
ALLOWED = re.compile(r"^C545D_[A-Z0-9_]+(?:,[A-Za-z0-9_]+=-?[A-Za-z0-9_.]+)+$")
EXPECTED_FILES = (
    "etw-nochange-totals-summary-only.txt",
    "etw-registry-totals-summary-only.txt",
    "etw-registry-stack-gap-summary-only.txt",
    "etw-registry-image-gap-summary-only.txt",
    "same-run-resource-only.txt",
)

def records(folder: Path) -> list[tuple[str, dict[str, str]]]:
    if not folder.is_dir():
        raise ValueError("original_numeric_artifact_directory_missing")
    found = set(x.name for x in folder.iterdir() if x.is_file())
    if set(EXPECTED_FILES) != found:
        raise ValueError("unexpected_or_missing_sanitized_source_files")
    items: list[tuple[str, dict[str, str]]] = []
    for name in EXPECTED_FILES:
        raw = (folder / name).read_text(encoding="utf-8-sig")
        if len(raw) > 200_000:
            raise ValueError("unbounded_numeric_artifact")
        for line in raw.strip().splitlines():
            if not ALLOWED.fullmatch(line):
                raise ValueError("nonallowlisted_original_trace_content")
            parts = line.split(",")
            fields: dict[str, str] = {}
            for term in parts[1:]:
                key, value = term.split("=", 1)
                if key in fields:
                    raise ValueError("duplicated_original_field")
                fields[key] = value
            items.append((parts[0], fields))
    return items

def one(rows: list[tuple[str, dict[str, str]]], record_type: str, **selector: str) -> dict[str, str]:
    match = [f for k, f in rows if k == record_type and all(f.get(x) == str(y) for x, y in selector.items())]
    if len(match) != 1:
        raise ValueError("incomplete_or_duplicated_source_row")
    return match[0]

def number(data: dict[str, str], key: str) -> int:
    if re.fullmatch(r"-?[0-9]+", data.get(key, "")) is None:
        raise ValueError("numeric_field_missing")
    return int(data[key])

def require(data: dict[str, str], **expected: int | str) -> None:
    for key, expected_value in expected.items():
        if key not in data or data[key] != str(expected_value):
            raise ValueError("source_evidence_mismatch")

def evaluate(folder: Path) -> str:
    rows = records(folder)
    no = one(rows, "C545D_GIO_ETW_HEAP_TOTALS_NUMERIC", arm="nochange")
    reg = one(rows, "C545D_GIO_ETW_HEAP_TOTALS_NUMERIC", arm="registry")
    diag = one(rows, "C545D_GIO_ETW_STACK_PARSE_DIAGNOSTIC", arm="registry")
    image = one(rows, "C545D_GIO_ETW_IMAGE_PARSE_DIAGNOSTIC", arm="registry")
    priv = one(rows, "C545D_COMBO16_SCANFREE_RESOURCE", kind="private", window="0_16")
    busy = one(rows, "C545D_COMBO16_SCANFREE_RESOURCE", kind="busy", window="0_16")
    region = one(rows, "C545D_HEAP_REGION_CONTROLLED", window="0_16")
    worker = one(rows, "C545D_APPINFO_PHASE_TRACE", arm="registry")
    no_worker = one(rows, "C545D_APPINFO_PHASE_TRACE", arm="nochange")
    watch = one(rows, "C545D_GIO_WATCH_RUNTIME_PASS", arm="registry")
    require(no,total_alloc=8045,total_out=0,host_untouched=1)
    require(reg,total_alloc=619727,total_out=16061,out_kb_tenths=8908,host_untouched=1)
    require(diag,reason="invalid_heap_counts",global_out=16061,
            numeric_rows=1024,rejected_rows=30,rows_out_exceeds_alloc=30,
            accepted_out=15595,gio_wellformed_out=15595,
            top_limit_may_truncate=1,full_source_classification_proven=0)
    require(image,reason="missing_global_or_top_header",global_headers=0,
            top_headers=0,source_owner_unproven=1)
    require(priv,registry_raw=188416,nochange_raw=49152,controlled=139264)
    require(busy,controlled=-3658)
    require(region,region_commit_delta=69632,private_delta=139264,
            busy_cbData_delta=-3658)
    require(worker,callbacks=17,workers=18,worker_active_after_cleanup=1,
            worker_active_final=0,boundary_tick_ambiguous=1,quiescence_proven=0)
    require(no_worker,callbacks=0,worker_active_after_cleanup=0,
            worker_active_final=0,quiescence_proven=0)
    require(watch,registrations=23,completions=17,final_pending_status_blocks=6,
            global_idle_proven=0,private_bytes_owner_proven=0)
    outstanding = number(reg, "total_out")
    known = number(diag, "accepted_out")
    unknown = number(diag, "unattributed_out")
    if outstanding != known + unknown or unknown != 466:
        raise ValueError("outstanding_stack_coverage_arithmetic_inconsistent")
    if number(priv, "registry_raw") - number(priv, "nochange_raw") != number(priv, "controlled"):
        raise ValueError("private_control_arithmetic_inconsistent")
    return (
        "C545D_GIO_ETW_SAVED_SCOPE_RECONCILED,"
        f"source_run={SOURCE_RUN},artifact={ARTIFACT_ID},"
        f"late4_registry_out={outstanding},late4_nochange_out={number(no,'total_out')},"
        f"wellformed_gio_stack_out={known},unknown_stack_out={unknown},"
        f"invalid_top1024_stack_rows={number(diag,'rejected_rows')},"
        f"private_controlled_0_16={number(priv,'controlled')},"
        f"region_controlled_0_16={number(region,'region_commit_delta')},"
        f"heap_busy_controlled_0_16={number(busy,'controlled')},"
        f"worker_active_after_cleanup={number(worker,'worker_active_after_cleanup')},"
        f"worker_active_final={number(worker,'worker_active_final')},"
        "image_source_format_unrecognized=1,process_global_quiet_proven=0,"
        "etw_window_only_cycles_13_16=1,private_window_cycles_0_16=1,"
        "cross_window_causal_comparison_prohibited=1,"
        "source_stack_contains_gio_not_direct_owner=1,"
        "leak_proven=0,allocation_owner_complete=0,"
        "all_cases_closed=0,release_approved=0,new_windows_runs=0,host_untouched=1"
    )

def fixture() -> dict[str, str]:
    rows = {
       "etw-nochange-totals-summary-only.txt":
         "C545D_GIO_ETW_HEAP_TOTALS_NUMERIC,arm=nochange,total_alloc=8045,total_out=0,host_untouched=1\n",
       "etw-registry-totals-summary-only.txt":
         "C545D_GIO_ETW_HEAP_TOTALS_NUMERIC,arm=registry,total_alloc=619727,total_out=16061,out_kb_tenths=8908,host_untouched=1\n",
       "etw-registry-stack-gap-summary-only.txt":
         "C545D_GIO_ETW_STACK_PARSE_DIAGNOSTIC,arm=registry,reason=invalid_heap_counts,global_out=16061,numeric_rows=1024,rejected_rows=30,rows_out_exceeds_alloc=30,accepted_out=15595,gio_wellformed_out=15595,top_limit_may_truncate=1,full_source_classification_proven=0,unattributed_out=466\n",
       "etw-registry-image-gap-summary-only.txt":
         "C545D_GIO_ETW_IMAGE_PARSE_DIAGNOSTIC,arm=registry,reason=missing_global_or_top_header,global_headers=0,top_headers=0,source_owner_unproven=1\n",
       "same-run-resource-only.txt":
         "\n".join([
            "C545D_COMBO16_SCANFREE_RESOURCE,kind=private,window=0_16,registry_raw=188416,nochange_raw=49152,controlled=139264",
            "C545D_COMBO16_SCANFREE_RESOURCE,kind=busy,window=0_16,controlled=-3658",
            "C545D_HEAP_REGION_CONTROLLED,window=0_16,region_commit_delta=69632,private_delta=139264,busy_cbData_delta=-3658",
            "C545D_APPINFO_PHASE_TRACE,arm=registry,callbacks=17,workers=18,worker_active_after_cleanup=1,worker_active_final=0,boundary_tick_ambiguous=1,quiescence_proven=0",
            "C545D_APPINFO_PHASE_TRACE,arm=nochange,callbacks=0,worker_active_after_cleanup=0,worker_active_final=0,quiescence_proven=0",
            "C545D_GIO_WATCH_RUNTIME_PASS,arm=registry,registrations=23,completions=17,final_pending_status_blocks=6,global_idle_proven=0,private_bytes_owner_proven=0",
         ])+"\n",
    }
    return rows

def selftest() -> None:
    original = fixture()
    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp)
        def write(data: dict[str, str]) -> None:
            for file, contents in data.items():
                (parent / file).write_text(contents, encoding="utf-8")
        write(original)
        assert "unknown_stack_out=466" in evaluate(parent)
        changes = [
          ("etw-registry-totals-summary-only.txt", "total_out=16061", "total_out=16060"),
          ("etw-registry-stack-gap-summary-only.txt", "accepted_out=15595", "accepted_out=16061"),
          ("etw-registry-stack-gap-summary-only.txt", "unattributed_out=466", "unattributed_out=0"),
          ("etw-registry-stack-gap-summary-only.txt", "rejected_rows=30", "rejected_rows=0"),
          ("etw-registry-image-gap-summary-only.txt", "global_headers=0", "global_headers=1"),
          ("same-run-resource-only.txt", "worker_active_after_cleanup=1", "worker_active_after_cleanup=0"),
          ("same-run-resource-only.txt", "quiescence_proven=0", "quiescence_proven=1"),
          ("same-run-resource-only.txt", "controlled=139264", "controlled=139263"),
          ("same-run-resource-only.txt", "C545D_GIO_WATCH_RUNTIME_PASS", "C545D_FAKE_WATCH"),
          ("same-run-resource-only.txt", "registrations=23", "registrations=24"),
        ]
        for n, (name, old, new) in enumerate(changes):
            bad = original.copy()
            if old not in bad[name]:
                raise AssertionError(f"selftest_mutation_missing_{n}")
            bad[name] = bad[name].replace(old, new, 1)
            write(bad)
            try:
                evaluate(parent)
            except ValueError:
                pass
            else:
                raise AssertionError(f"bad_numeric_evidence_accepted_{n}")
        write(original)
        # Source privacy gate rejects line-level stack/pointer record.
        with (parent / "same-run-resource-only.txt").open("a", encoding="utf-8") as handle:
            handle.write("some-process.exe!SecretFrame 0x100000\n")
        try:
            evaluate(parent)
        except ValueError:
            pass
        else:
            raise AssertionError("raw_stack_content_accepted")
    print("C545D_GIO_ETW_SAVED_SCOPE_SELFTEST_PASS,positive=1,negative=11,"
          "registry_outstanding_verified=16061,active_worker_during_cleanup=1,"
          "cross_window_causality_not_claimed=1,new_windows_runs=0")

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--numeric-folder", type=Path)
    a = p.parse_args()
    if a.selftest:
        selftest()
    else:
        if a.numeric_folder is None:
            p.error("--numeric-folder required")
        print(evaluate(a.numeric_folder))

if __name__ == "__main__":
    main()
