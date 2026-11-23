#!/usr/bin/env python3
"""Archive-only fail-closed reconciliation of GIO 466 realloc-group evidence.

Consumes only sanitized original artifact 14799580784 from actual disposable
Windows2022 run 45133754345. This proves per-stack integer compatibility
and complete global numeric count coverage, NOT HeapAlloc owner identity,
free-after-worker lifetime, global APC quiet, or a leak/production result.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import tempfile

RUN = 45133754345
ARTIFACT = 14799580784
NAMES = {
    "etw-nochange-totals-summary-only.txt",
    "etw-registry-totals-summary-only.txt",
    "etw-registry-stack-gap-summary-only.txt",
    "etw-registry-image-gap-summary-only.txt",
    "etw-registry-stack-1024-bounds-only.txt",
    "etw-registry-stack-8192-bounds-only.txt",
    "same-run-resource-only.txt",
    "etw-worker-stop-qpc-only.txt",
}
ALLOWED = re.compile(r"^C545D_[A-Z0-9_]+(?:,[A-Za-z0-9_]+=-?[A-Za-z0-9_.]+)+$")

def rows(folder: Path) -> list[tuple[str, dict[str, str]]]:
    if not folder.is_dir():
        raise ValueError("archived_numeric_artifact_missing")
    found = {x.name for x in folder.iterdir() if x.is_file()}
    if found != NAMES or any(x.is_dir() for x in folder.iterdir()):
        raise ValueError("unexpected_numeric_artifact_shape")
    result = []
    for name in sorted(NAMES):
        file = folder / name
        if not 1 <= file.stat().st_size <= 100_000:
            raise ValueError("unbounded_or_missing_numeric_file")
        for line in file.read_text(encoding="utf-8-sig").strip().splitlines():
            if not ALLOWED.fullmatch(line):
                raise ValueError("unallowlisted_raw_profile_line")
            bits = line.split(",")
            fields = {}
            for pair in bits[1:]:
                key, val = pair.split("=", 1)
                if key in fields:
                    raise ValueError("repeated_profile_field")
                fields[key] = val
            result.append((bits[0], fields))
    return result

def one(result: list[tuple[str, dict[str, str]]], tag: str, **filter: str) -> dict[str, str]:
    candidates = [f for name, f in result
                  if name == tag and all(f.get(k) == v for k, v in filter.items())]
    if len(candidates) != 1:
        raise ValueError("numeric_record_ambiguous_or_missing")
    return candidates[0]

def val(row: dict[str, str], key: str) -> int:
    src = row.get(key, "")
    if not re.fullmatch(r"-?\d+", src):
        raise ValueError("missing_integer_metric")
    return int(src)

def expect(row: dict[str, str], **kwargs: int | str) -> None:
    for k, wanted in kwargs.items():
        if row.get(k) != str(wanted):
            raise ValueError("source_provenance_or_metric_mismatch")

def evaluate(folder: Path) -> str:
    data = rows(folder)
    no = one(data, "C545D_GIO_ETW_HEAP_TOTALS_NUMERIC", arm="nochange")
    reg = one(data, "C545D_GIO_ETW_HEAP_TOTALS_NUMERIC", arm="registry")
    diag = one(data, "C545D_GIO_ETW_STACK_PARSE_DIAGNOSTIC", arm="registry")
    image = one(data, "C545D_GIO_ETW_IMAGE_PARSE_DIAGNOSTIC", arm="registry")
    b1024 = one(data, "C545D_GIO_ETW_STACK_COVERAGE_BOUNDS", arm="registry", requested_top="1024")
    b8192 = one(data, "C545D_GIO_ETW_STACK_COVERAGE_BOUNDS", arm="registry", requested_top="8192")
    priv = one(data, "C545D_COMBO16_SCANFREE_RESOURCE", kind="private", window="0_16")
    busy = one(data, "C545D_COMBO16_SCANFREE_RESOURCE", kind="busy", window="0_16")
    region = one(data, "C545D_HEAP_REGION_CONTROLLED", window="0_16")
    worker = one(data, "C545D_APPINFO_PHASE_TRACE", arm="registry")
    qpc = one(data, "C545D_GIO_ETW_WORKER_STOP_QPC", arm="registry")
    expect(no, total_alloc=8051, total_out=0)
    expect(reg, total_alloc=619937, total_out=16062, out_kb_tenths=8908)
    expect(diag, rejected_rows=31, rows_out_exceeds_alloc=31,
           accepted_out=15596, unattributed_out=466,
           numeric_rows=1024, full_source_classification_proven=0)
    expect(image, reason="missing_global_or_top_header", global_headers=0,
           top_headers=0, alloc_lines=0)
    for bound, cap, hdr, nrows, accepted_alloc, complete in (
        (b1024,1024,1024,1024,581665,0),
        (b8192,8192,1166,1166,619937,1),
    ):
        expect(bound, global_alloc=619937, global_out=16062,
               requested_top=cap, top_header_rows=hdr, metric_rows=nrows,
               accepted_alloc_sum=accepted_alloc,
               accepted_out_sum=15596,
               rejected_raw_alloc_sum=0,
               rejected_raw_out_sum=466,
               rejected_raw_realloc_sum=3604,
               out_exceeds_alloc_realloc_compatible_rows=31,
               out_exceeds_alloc_realloc_incompatible_rows=0,
               out_exceeds_alloc_realloc_compatible_out=466,
               out_exceeds_alloc_realloc_incompatible_out=0,
               all_out_exceeds_alloc_rows_realloc_compatible=1,
               global_minus_accepted_out=466,
               raw_rows_minus_global_out=0,
               raw_group_totals_numeric_reconcile=complete,
               validated_full_count_coverage=0,
               allocation_lifetime_unproven=1,
               raw_uploaded=0)
    if val(b8192,"requested_cap_reached") != 0 or val(b1024,"requested_cap_reached") != 1:
        raise ValueError("top_limit_coverage_wrong")
    expect(priv, controlled=331776)
    expect(busy, controlled=-7734)
    expect(region, region_commit_delta=303104, private_delta=331776, busy_cbData_delta=-7734)
    expect(worker, callbacks=17, workers=18, quiescence_proven=0)
    expect(qpc, worker_overlapping_stop_bracket=0,
           worker_spanning_entire_stop_bracket=0,
           worker_return_after_stop_ack=1,
           globally_quiet_proven=0, allocation_owner_proven=0, leak_proven=0)
    if val(reg,"total_out") != val(b8192,"accepted_out_sum") + val(b8192,"rejected_raw_out_sum"):
        raise ValueError("global_out_not_reconciled")
    if val(reg,"total_alloc") != val(b8192,"accepted_alloc_sum") + val(b8192,"rejected_raw_alloc_sum"):
        raise ValueError("global_alloc_not_reconciled")
    return (
        "C545D_GIO_ETW_REALLOC_SAVED_RECONCILED,"
        f"source_run={RUN},source_artifact={ARTIFACT},"
        "global_alloc=619937,global_out=16062,"
        "wellformed_out=15596,previous_residual=466,"
        "realloc_group_rows=31,realloc_group_raw_alloc=0,"
        "realloc_group_raw_realloc=3604,realloc_group_out=466,"
        "realloc_compatible_rows=31,realloc_incompatible_rows=0,"
        "requested_cap8192_emitted_rows=1166,"
        "global_alloc_out_count_reconciled=1,"
        "trace_loss_zero_checked_by_source_job=1,"
        "realloc_compatible_not_unique_causal_owner=1,"
        "complete_lifetime_owner_unproven=1,global_async_quiet_unproven=1,"
        "windows_runs_added=0,real_host_untouched=1,release_HOLD=1"
    )

def fixture(folder: Path) -> None:
    folder.mkdir()
    def put(name: str, *lines: str) -> None:
        (folder / name).write_text("\n".join(lines)+"\n",encoding="utf-8")
    put("etw-nochange-totals-summary-only.txt",
        "C545D_GIO_ETW_HEAP_TOTALS_NUMERIC,arm=nochange,total_alloc=8051,total_out=0")
    put("etw-registry-totals-summary-only.txt",
        "C545D_GIO_ETW_HEAP_TOTALS_NUMERIC,arm=registry,total_alloc=619937,total_out=16062,out_kb_tenths=8908")
    put("etw-registry-stack-gap-summary-only.txt",
        "C545D_GIO_ETW_STACK_PARSE_DIAGNOSTIC,arm=registry,rejected_rows=31,rows_out_exceeds_alloc=31,accepted_out=15596,unattributed_out=466,numeric_rows=1024,full_source_classification_proven=0")
    put("etw-registry-image-gap-summary-only.txt",
        "C545D_GIO_ETW_IMAGE_PARSE_DIAGNOSTIC,arm=registry,reason=missing_global_or_top_header,global_headers=0,top_headers=0,alloc_lines=0")
    for cap, hdr, nrows, aa, complete in ((1024,1024,1024,581665,0),(8192,1166,1166,619937,1)):
        put(f"etw-registry-stack-{cap}-bounds-only.txt",
            f"C545D_GIO_ETW_STACK_COVERAGE_BOUNDS,arm=registry,requested_top={cap},"
            f"top_header_rows={hdr},metric_rows={nrows},requested_cap_reached={int(cap==1024)},"
            "global_alloc=619937,global_out=16062,"
            f"accepted_alloc_sum={aa},accepted_out_sum=15596,rejected_raw_alloc_sum=0,"
            "rejected_raw_out_sum=466,rejected_raw_realloc_sum=3604,"
            "out_exceeds_alloc_realloc_compatible_rows=31,"
            "out_exceeds_alloc_realloc_incompatible_rows=0,"
            "out_exceeds_alloc_realloc_compatible_out=466,"
            "out_exceeds_alloc_realloc_incompatible_out=0,"
            "all_out_exceeds_alloc_rows_realloc_compatible=1,"
            "global_minus_accepted_out=466,raw_rows_minus_global_out=0,"
            f"raw_group_totals_numeric_reconcile={complete},"
            "validated_full_count_coverage=0,allocation_lifetime_unproven=1,raw_uploaded=0")
    put("same-run-resource-only.txt",
        "C545D_COMBO16_SCANFREE_RESOURCE,kind=private,window=0_16,controlled=331776",
        "C545D_COMBO16_SCANFREE_RESOURCE,kind=busy,window=0_16,controlled=-7734",
        "C545D_HEAP_REGION_CONTROLLED,window=0_16,region_commit_delta=303104,private_delta=331776,busy_cbData_delta=-7734",
        "C545D_APPINFO_PHASE_TRACE,arm=registry,callbacks=17,workers=18,quiescence_proven=0")
    put("etw-worker-stop-qpc-only.txt",
        "C545D_GIO_ETW_WORKER_STOP_QPC,arm=registry,worker_overlapping_stop_bracket=0,worker_spanning_entire_stop_bracket=0,worker_return_after_stop_ack=1,globally_quiet_proven=0,allocation_owner_proven=0,leak_proven=0")

def selftest() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "numeric"
        fixture(root)
        assert evaluate(root).startswith("C545D_GIO_ETW_REALLOC_SAVED_RECONCILED,")
        corruptions = [
            ("etw-registry-stack-8192-bounds-only.txt","rejected_raw_realloc_sum=3604","rejected_raw_realloc_sum=1"),
            ("etw-registry-stack-8192-bounds-only.txt","realloc_compatible_rows=31","realloc_compatible_rows=30"),
            ("etw-registry-stack-8192-bounds-only.txt","out_exceeds_alloc_realloc_incompatible_rows=0","out_exceeds_alloc_realloc_incompatible_rows=1"),
            ("etw-registry-stack-8192-bounds-only.txt","requested_cap_reached=0","requested_cap_reached=1"),
            ("etw-registry-stack-8192-bounds-only.txt","raw_group_totals_numeric_reconcile=1","raw_group_totals_numeric_reconcile=0"),
            ("etw-registry-stack-8192-bounds-only.txt","top_header_rows=1166","top_header_rows=8192"),
            ("etw-registry-totals-summary-only.txt","total_out=16062","total_out=16061"),
            ("same-run-resource-only.txt","controlled=331776","controlled=999999"),
            ("etw-worker-stop-qpc-only.txt","leak_proven=0","leak_proven=1"),
            ("etw-registry-stack-gap-summary-only.txt","unattributed_out=466","unattributed_out=465"),
        ]
        for i,(file,old,new) in enumerate(corruptions):
            path=root/file
            original=path.read_text("utf-8")
            path.write_text(original.replace(old,new,1),encoding="utf-8")
            try: evaluate(root)
            except ValueError: pass
            else: raise AssertionError(f"unsafe_saved_artifact_mutation_accepted:{i}")
            path.write_text(original,encoding="utf-8")
        (root/"private_raw.etl").write_bytes(b"private")
        try:evaluate(root)
        except ValueError:pass
        else:raise AssertionError("raw_artifact_file_accepted")
    print("C545D_GIO_ETW_REALLOC_SAVED_SELFTEST_PASS,positive=1,negative=11,"
          "realloc_compatible_not_leak=1,new_windows_runs=0,raw_artifact_forbidden=1")

def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--folder",type=Path)
    a=p.parse_args()
    if a.selftest:
        selftest()
        return
    if a.folder is None:
        p.error("--folder required for sanitized artifact")
    print(evaluate(a.folder))

if __name__=="__main__":
    main()
