#!/usr/bin/env python3
"""Reconcile ONLY preexisting Windows2022 real GIO initial-AppInfo ETLX safe lines.

Pinned source: Actions run 45186553913, job 137733556139, revision 649b287.
This is an archive-only analysis, NOT a new GIO Windows trace, host diagnosis
or proof of leak. Raw job logs stay in a disposable runner temp directory.
Reports precisely why 'unknown origin' is still unclassified:
  missing call stack / module present but method not allowlisted /
  no GIO module frame / allocations from before ETW start (orphan events).
Heap request sizes are NOT PrivateUsage/heap commit.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

RUN = 45186553913
JOB = 137733556139
MAX_RAW = 20_000_000
ARM_SET = {"nochange", "registry"}
STAMP = re.compile(r"^20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z ")
PREFIXES = {
    "source": "C545D_GIO_ETLX_FIRST_SOURCE_CENSUS",
    "pass": "C545D_GIO_ETLX_FIRST_SOURCE_OWNER_PASS",
    "resource": "C545D_GIO_PREINIT_RESOURCE_SCOPE",
}
EXPECTED_FIELDS = {
    "pid_heap_events", "original_alloc_events", "zero_req_original_alloc",
    "zero_req_realloc", "zero_req_old_size", "zero_req_new_size",
    "zero_req_not_zero_heap_commit", "realloc_events", "free_events",
    "missing_initial_stack", "gio_module_in_alloc_stack",
    "exact_GIO_source_method_on_original_alloc",
    "unknown_origin_original_alloc", "gio_source_origin_realloc",
    "gio_source_origin_logical_free", "gio_source_origin_alloc",
    "original_allocation_live", "request_bytes_live", "unknown_original_live",
    "orphan_realloc_prior_start", "orphan_free_prior_start",
    "native_GIO_loaded_modules", "native_GIO_symbol_lookups",
    "before_first_appinfo", "after_settled_cleanup",
    "source_closed_globally", "leak_proven", "release_HOLD",
    "no_raw_pointer_or_stack_output",
}
RESOURCE_FIELDS = {
    "private_delta", "region_private_delta", "handles_delta",
    "scope", "persistent_watches_allowed", "global_idle_proven",
    "leak_proven", "raw_uploaded",
}
PASS_FIELDS = {
    "real_GIO_method_stacks_found","source_owner_lifetime_annotated",
    "no_global_quiet_or_leak_claim","release_HOLD","raw_uploaded",
}


def parse_line(body: str, prefix: str, fields: set[str]) -> tuple[str,dict[str,int|str]]:
    if len(body)>2400 or not body.startswith(prefix+","):
        raise ValueError("bad_source_line_shape")
    entries=body.split(",")[1:]
    mapping:dict[str,int|str]={}
    for item in entries:
        match=re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=([A-Za-z0-9_.-]+)",item)
        if match is None:
            raise ValueError("source_line_schema_invalid")
        key,value=match.groups()
        if key in mapping:
            raise ValueError("duplicate_source_field")
        if key=="arm":
            if value not in ARM_SET:
                raise ValueError("wrong_owned_arm")
            mapping[key]=value
        elif key=="scope":
            if value!="preappinfo_to_settled_cleanup":
                raise ValueError("wrong_resource_phase")
            mapping[key]=value
        else:
            if not re.fullmatch(r"-?\d+",value):
                raise ValueError("nonnumeric_unsafe_source_field")
            mapping[key]=int(value)
    if set(mapping)!=(fields|{"arm"}):
        raise ValueError("source_field_missing_or_changed")
    return str(mapping.pop("arm")),mapping


def extract(log:str) -> dict[str,dict[str,dict[str,int|str]]]:
    if not isinstance(log,str) or len(log.encode("utf-8"))>MAX_RAW:
        raise ValueError("raw_source_log_unbounded")
    collected:dict[str,dict[str,dict[str,int|str]]]={}
    for line in log.splitlines():
        m=STAMP.match(line)
        if not m:continue
        body=line[m.end():].strip()
        for kind,prefix in PREFIXES.items():
            if not body.startswith(prefix+","):continue
            fields=(EXPECTED_FIELDS if kind=="source" else
                    RESOURCE_FIELDS if kind=="resource" else PASS_FIELDS)
            arm,values=parse_line(body,prefix,fields)
            if kind in collected.setdefault(arm,{}):
                raise ValueError("duplicate_phase_or_source_proof")
            collected[arm][kind]=values
    if set(collected)!=ARM_SET or any(set(v)!=set(PREFIXES) for v in collected.values()):
        raise ValueError("paired_source_or_resource_phase_missing")
    return collected


def proof(arm:str,entries:dict[str,dict[str,int|str]]) -> dict[str,int]:
    s=entries["source"]
    r=entries["resource"]
    p=entries["pass"]
    def n(k:str)->int:
        v=s[k]
        if type(v) is not int:raise ValueError("invalid_integer_source")
        return v
    for k in ("real_GIO_method_stacks_found","source_owner_lifetime_annotated",
              "no_global_quiet_or_leak_claim","release_HOLD"):
        if p[k]!=1:
            raise ValueError("original_function_proof_incomplete")
    if p["raw_uploaded"]!=0:
        raise ValueError("original_trace_privacy_incomplete")
    for k in ("before_first_appinfo","after_settled_cleanup",
              "zero_req_not_zero_heap_commit","native_GIO_loaded_modules",
              "native_GIO_symbol_lookups","no_raw_pointer_or_stack_output",
              "release_HOLD"):
        if n(k)!=1:
            raise ValueError("trace_provenance_missing")
    for k in ("source_closed_globally","leak_proven"):
        if n(k)!=0:
            raise ValueError("false_global_or_leak_verdict")
    if r["scope"]!="preappinfo_to_settled_cleanup" or r["persistent_watches_allowed"]!=1 or \
       r["global_idle_proven"]!=0 or r["leak_proven"]!=0 or r["raw_uploaded"]!=0:
        raise ValueError("resource_scope_or_quiet_claim_invalid")
    if any(type(v) is not int or v<0 for k,v in s.items() if k!="scope"):
        raise ValueError("negative_heap_event_counter")
    events=n("pid_heap_events")
    a=n("original_alloc_events")
    re=n("realloc_events")
    free=n("free_events")
    exact=n("exact_GIO_source_method_on_original_alloc")
    frames=n("gio_module_in_alloc_stack")
    unknown=n("unknown_origin_original_alloc")
    if not (events==a+re+free and events<=2_000_000 and
            0<=exact<=frames<=a and unknown==a-exact):
        raise ValueError("source_count_arithmetic_inconsistent")
    if n("missing_initial_stack")!=0:
        raise ValueError("original_stack_missing_classify_separately")
    gio_alloc=n("gio_source_origin_alloc")
    gio_free=n("gio_source_origin_logical_free")
    live=n("original_allocation_live")
    unowned_live=n("unknown_original_live")
    if not (0<=gio_alloc<=exact and 0<=gio_free<=gio_alloc and
            0<=unowned_live<=live and gio_alloc-gio_free==live-unowned_live):
        raise ValueError("original_source_lifetime_not_reconciled")
    if n("gio_source_origin_realloc")>re or n("zero_req_original_alloc")>a or \
       n("zero_req_realloc")>re:
        raise ValueError("heap_event_source_counter_out_of_range")
    if n("zero_req_old_size")>n("zero_req_realloc") or \
       n("zero_req_new_size")>n("zero_req_realloc"):
        raise ValueError("zero_size_realloc_counter_invalid")
    if n("request_bytes_live")<0:
        raise ValueError("unbounded_live_request_bytes")
    # Original owners not proven means one of the following, not a generic
    # 'unexplained' bucket. Both are tracked to future missing observables.
    method_not_allowlisted=frames-exact
    no_gio_module=a-frames
    if unknown!=method_not_allowlisted+no_gio_module:
        raise ValueError("origin_unknown_reason_partition_failed")
    for field in ("private_delta","region_private_delta","handles_delta"):
        if type(r[field]) is not int or abs(int(r[field]))>2**44:
            raise ValueError("unbounded_process_resource_delta")
    return {
        "events":events, "alloc":a,"realloc":re,"free":free,
        "exact_method":exact,"verified_source_live":gio_alloc-gio_free,
        "all_live":live,"unresolved_live":unowned_live,
        "unknown_original":unknown,
        "method_not_allowlisted":method_not_allowlisted,
        "no_gio_module_frame":no_gio_module,
        "orphan_realloc":n("orphan_realloc_prior_start"),
        "orphan_free":n("orphan_free_prior_start"),
        "realloc_internal_original":exact-gio_alloc,
        "zero_req_alloc":n("zero_req_original_alloc"),
        "request_bytes_live":n("request_bytes_live"),
        "private_delta":int(r["private_delta"]),
        "region_delta":int(r["region_private_delta"]),
        "handles_delta":int(r["handles_delta"]),
    }


def evaluate(log:str)->str:
    found=extract(log)
    no=proof("nochange",found["nochange"])
    yes=proof("registry",found["registry"])
    diffs={k:yes[k]-no[k] for k in
           ("verified_source_live","all_live","unresolved_live",
            "unknown_original","method_not_allowlisted","no_gio_module_frame",
            "request_bytes_live","private_delta","region_delta","handles_delta")}
    return (
        f"C545D_GIO_FIRST_ETLX_ARCHIVED_PAIR_PASS,source_run={RUN},source_job={JOB},"
        f"nochange_events={no['events']},registry_events={yes['events']},"
        f"nochange_exact_method_original_alloc={no['exact_method']},"
        f"registry_exact_method_original_alloc={yes['exact_method']},"
        f"nochange_source_live={no['verified_source_live']},"
        f"registry_source_live={yes['verified_source_live']},"
        f"source_live_delta={diffs['verified_source_live']},"
        f"all_live_delta={diffs['all_live']},"
        f"unknown_live_delta={diffs['unresolved_live']},"
        f"nochange_unknown_original={no['unknown_original']},"
        f"registry_unknown_original={yes['unknown_original']},"
        f"nochange_unknown_gio_module_method={no['method_not_allowlisted']},"
        f"registry_unknown_gio_module_method={yes['method_not_allowlisted']},"
        f"nochange_unknown_no_gio_frame={no['no_gio_module_frame']},"
        f"registry_unknown_no_gio_frame={yes['no_gio_module_frame']},"
        f"nochange_orphan_realloc={no['orphan_realloc']},"
        f"registry_orphan_realloc={yes['orphan_realloc']},"
        f"nochange_orphan_free={no['orphan_free']},"
        f"registry_orphan_free={yes['orphan_free']},"
        f"nochange_realloc_internal_original={no['realloc_internal_original']},"
        f"registry_realloc_internal_original={yes['realloc_internal_original']},"
        f"nochange_zero_request_alloc={no['zero_req_alloc']},"
        f"registry_zero_request_alloc={yes['zero_req_alloc']},"
        f"source_request_bytes_live_delta={diffs['request_bytes_live']},"
        f"private_usage_delta_between_arms={diffs['private_delta']},"
        f"region_private_delta_between_arms={diffs['region_delta']},"
        f"handles_delta_between_arms={diffs['handles_delta']},"
        "same_initial_AppInfo_phase=1,all_original_stack_frames_present=1,"
        "unknown_reason_partitioned=1,orphan_before_trace_still_unattributed=1,"
        "request_bytes_not_private_commit=1,source_owner_not_leak_proof=1,"
        "one_cycle_only=1,repeat_accumulation_not_tested=1,"
        "new_Windows_capture=0,host_untouched=1,release_HOLD=1"
    )


def sample() -> str:
    # The *same original sanitized lines* are reproduced strictly for
    # parser unit tests. Do not persist any raw stack, PDB or address.
    rows=[
"C545D_GIO_ETLX_FIRST_SOURCE_CENSUS,arm=nochange,pid_heap_events=169078,original_alloc_events=88995,zero_req_original_alloc=12,zero_req_realloc=0,zero_req_old_size=0,zero_req_new_size=0,zero_req_not_zero_heap_commit=1,realloc_events=856,free_events=79227,missing_initial_stack=0,gio_module_in_alloc_stack=86231,exact_GIO_source_method_on_original_alloc=85028,unknown_origin_original_alloc=3967,gio_source_origin_realloc=836,gio_source_origin_logical_free=74002,gio_source_origin_alloc=84212,original_allocation_live=10461,request_bytes_live=867257,unknown_original_live=251,orphan_realloc_prior_start=17,orphan_free_prior_start=693,native_GIO_loaded_modules=1,native_GIO_symbol_lookups=1,before_first_appinfo=1,after_settled_cleanup=1,source_closed_globally=0,leak_proven=0,release_HOLD=1,no_raw_pointer_or_stack_output=1",
"C545D_GIO_ETLX_FIRST_SOURCE_OWNER_PASS,arm=nochange,real_GIO_method_stacks_found=1,source_owner_lifetime_annotated=1,no_global_quiet_or_leak_claim=1,release_HOLD=1,raw_uploaded=0",
"C545D_GIO_PREINIT_RESOURCE_SCOPE,arm=nochange,private_delta=3776512,region_private_delta=2682880,handles_delta=551,scope=preappinfo_to_settled_cleanup,persistent_watches_allowed=1,global_idle_proven=0,leak_proven=0,raw_uploaded=0",
"C545D_GIO_ETLX_FIRST_SOURCE_CENSUS,arm=registry,pid_heap_events=860372,original_alloc_events=433999,zero_req_original_alloc=14,zero_req_realloc=0,zero_req_old_size=0,zero_req_new_size=0,zero_req_not_zero_heap_commit=1,realloc_events=3257,free_events=423116,missing_initial_stack=0,gio_module_in_alloc_stack=429792,exact_GIO_source_method_on_original_alloc=428585,unknown_origin_original_alloc=5414,gio_source_origin_realloc=3231,gio_source_origin_logical_free=407176,gio_source_origin_alloc=425361,original_allocation_live=18429,request_bytes_live=1323298,unknown_original_live=244,orphan_realloc_prior_start=23,orphan_free_prior_start=7546,native_GIO_loaded_modules=1,native_GIO_symbol_lookups=1,before_first_appinfo=1,after_settled_cleanup=1,source_closed_globally=0,leak_proven=0,release_HOLD=1,no_raw_pointer_or_stack_output=1",
"C545D_GIO_ETLX_FIRST_SOURCE_OWNER_PASS,arm=registry,real_GIO_method_stacks_found=1,source_owner_lifetime_annotated=1,no_global_quiet_or_leak_claim=1,release_HOLD=1,raw_uploaded=0",
"C545D_GIO_PREINIT_RESOURCE_SCOPE,arm=registry,private_delta=3796992,region_private_delta=2732032,handles_delta=553,scope=preappinfo_to_settled_cleanup,persistent_watches_allowed=1,global_idle_proven=0,leak_proven=0,raw_uploaded=0"
    ]
    return "".join("2026-11-23T13:46:08.2211464Z "+row+"\n" for row in rows)


def selftest()->None:
    good=sample()
    assert "source_live_delta=7975" in evaluate(good)
    assert "nochange_unknown_gio_module_method=1203" in evaluate(good)
    cases=[
      ("original_alloc_events=88995","original_alloc_events=88994"),
      ("unknown_origin_original_alloc=3967","unknown_origin_original_alloc=3968"),
      ("gio_source_origin_logical_free=74002","gio_source_origin_logical_free=74001"),
      ("unknown_original_live=251","unknown_original_live=250"),
      ("missing_initial_stack=0","missing_initial_stack=1"),
      ("native_GIO_symbol_lookups=1","native_GIO_symbol_lookups=0"),
      ("leak_proven=0","leak_proven=1"),
      ("source_closed_globally=0","source_closed_globally=1"),
      ("private_delta=3776512","private_delta=wrong"),
      ("zero_req_original_alloc=12","zero_req_original_alloc=90000"),
      ("orphan_realloc_prior_start=17","orphan_realloc_prior_start=-10"),
      ("arm=registry","arm=nochange"),
    ]
    for index,(old,new) in enumerate(cases):
        edited=good.replace(old,new,1)
        if edited==good:raise AssertionError("selftest_mutation_did_not_apply")
        try:evaluate(edited)
        except ValueError:continue
        raise AssertionError(f"misleading_source_reconciliation_accepted_{index}")
    for index,edited in enumerate([good+good,good.splitlines()[0],
                                   good.replace("2026-11-23T13:46:08.2211464Z ","",1)]):
        try:evaluate(edited)
        except ValueError:continue
        raise AssertionError(f"incomplete_or_duplicate_source_accepted_{index}")
    print("C545D_GIO_FIRST_ETLX_ARCHIVE_SELFTEST_PASS,positive=1,negative=15,"
          "GIO_owner_origin_unknown_partitioned=1,"
          "request_bytes_never_conflated_with_private_commit=1,"
          "new_Windows_capture=0,release_HOLD=1")


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--log",type=Path)
    args=p.parse_args()
    if args.selftest:
        selftest()
        return
    if args.log is None:
        p.error("--log original owned GitHub Action job")
    if not args.log.is_file() or args.log.stat().st_size>MAX_RAW:
        raise ValueError("raw_source_log_unbounded")
    print(evaluate(args.log.read_text(encoding="utf-8-sig",errors="replace")))


if __name__=="__main__":
    main()
