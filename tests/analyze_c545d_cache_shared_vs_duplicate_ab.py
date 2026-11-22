#!/usr/bin/env python3
"""Independent privacy-safe analysis of SAME-WINDOW synthetic Windows cache AB.

Input must be 8 strictly formatted numeric rows, 4 runs per arm,
alternating order. The original GIO cache hit helper is GIO-private;
the native test models the *same per-hit* g_wcsdup allocation with
g_memdup2 and the new g_bytes_ref path. Neither tests real application
package cache hits nor proves absence of long-run PrivateUsage growth.

The script intentionally does not claim any improvement percentage,
because cold-heap variation and process start baseline are uncontrolled.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
from statistics import median

ORDER=("old","shared","shared","old","shared","old","old","shared")
PAT=re.compile(
    r"C545D_CACHE_SYNTH_AB,mode=(old|shared),rounds=64,keys=32,"
    r"hits=524288,misses=2048,hit_utf16_copies=(0|524288),"
    r"evictions=64,private_delta=(-?\d{1,14}),"
    r"handles_delta=(-?\d{1,6}),cpu_user_100ns=(\d{1,16}),"
    r"cpu_kernel_100ns=(\d{1,16}),wall_us=(\d{1,16}),"
    r"peak_pagefile=(\d{1,16}),windows_synthetic_only=1,"
    r"gio_actual_hits=0,leak_fix_proven=0,host_untouched=1$"
)

def analyze(rows: list[str]) -> list[str]:
    if len(rows)!=len(ORDER):
        raise ValueError("incomplete_ordered_matched_arms")
    summary: dict[str,list[tuple[int,int,int,int,int]]] = {"old":[],"shared":[]}
    for expected,row in zip(ORDER,rows):
        m=PAT.fullmatch(row)
        if m is None: raise ValueError("unexpected_numeric_schema")
        mode,copies,private,handles,user,kernel,wall,peak=m.groups()
        if mode!=expected or int(copies)!=(524288 if mode=="old" else 0):
            raise ValueError("arm_or_exact_hit_copy_mismatch")
        data=tuple(map(int,(private,handles,user,kernel,wall,peak)))
        if not -64*1024*1024 < data[0] < 64*1024*1024:
            raise ValueError("private_delta_outside_bounded_synthetic")
        if not -16 <= data[1] <= 12 or data[2]+data[3] <= 0:
            raise ValueError("resource_counter_impossible")
        if data[4] <= 0 or data[5] <= 0 or data[4] > 60*1000*1000:
            raise ValueError("no_bounded_timing")
        summary[mode].append((data[0],data[1],data[2]+data[3],data[4],data[5]))
    if any(len(x)!=4 for x in summary.values()):
        raise ValueError("missing_replicates")
    result=[]
    for mode in ("old","shared"):
        blocks=summary[mode]
        metrics=[int(median(col)) for col in zip(*blocks)]
        result.append(
            f"C545D_CACHE_SYNTH_AB_ARM,mode={mode},replicates=4,"
            f"median_private_delta={metrics[0]},"
            f"median_handles_delta={metrics[1]},"
            f"median_cpu_100ns={metrics[2]},"
            f"median_wall_us={metrics[3]},"
            f"median_peak_pagefile={metrics[4]},"
            f"per_hit_utf16_copies={524288 if mode=='old' else 0},"
            "real_world_cache_hits_unmeasured=1"
        )
    old=summary["old"]
    new=summary["shared"]
    cpu_diff=int(median(x[2] for x in new)-median(x[2] for x in old))
    priv_diff=int(median(x[0] for x in new)-median(x[0] for x in old))
    handles_diff=int(median(x[1] for x in new)-median(x[1] for x in old))
    result.append(
        "C545D_CACHE_SYNTH_AB_COMPARE,"
        "identical_synthetic_payload=1,"
        "paired_order_control=1,"
        "old_copy_count=524288,new_copy_count=0,"
        f"median_cpu_diff_candidate_minus_old_100ns={cpu_diff},"
        f"median_private_delta_diff_candidate_minus_old={priv_diff},"
        f"median_handles_diff_candidate_minus_old={handles_diff},"
        "synthetic_only=1,source_allocator_not_fully_equivalent=1,"
        "noise_bounds_unproven=1,real_gio_memory_benefit_unproven=1"
    )
    result.append(
        "C545D_CACHE_SYNTH_AB_PASS,"
        "arms=2,replicates_each=4,total_runs=8,"
        "cache_hit_count_each=524288,process_resets_between_arms=1,"
        "no_registry_or_package_modifications=1,"
        "private_memory_leak_fix_proven=0,"
        "cpu_stability_proven=0,"
        "recording_pc_untouched=1"
    )
    return result


def selftest() -> None:
    def line(mode: str) -> str:
        copies=524288 if mode=="old" else 0
        return (
            f"C545D_CACHE_SYNTH_AB,mode={mode},rounds=64,keys=32,"
            f"hits=524288,misses=2048,hit_utf16_copies={copies},"
            "evictions=64,private_delta=0,handles_delta=0,"
            "cpu_user_100ns=100000,cpu_kernel_100ns=0,wall_us=5000,"
            "peak_pagefile=2000000,windows_synthetic_only=1,"
            "gio_actual_hits=0,leak_fix_proven=0,host_untouched=1")
    good=[line(x) for x in ORDER]
    assert len(analyze(good))==4
    corrupt=[
        good[:-1],
        good+[good[-1]],
        [good[1],good[0],*good[2:]],
        [good[0].replace("hit_utf16_copies=524288","hit_utf16_copies=0"),*good[1:]],
        [good[0].replace("private_delta=0","private_delta=999999999"),*good[1:]],
        [good[0].replace("cpu_user_100ns=100000","cpu_user_100ns=0"),*good[1:]],
        [good[0].replace("host_untouched=1","host_untouched=0"),*good[1:]],
        [good[0]+",C:\\private\\source",*good[1:]],
    ]
    for broken in corrupt:
        try: analyze(broken)
        except ValueError: continue
        raise AssertionError("unsafe or incomplete results accepted")
    print("C545D_CACHE_SYNTH_AB_SELFTEST_PASS,"
          "positive=1,negative=8,new_windows_runs=0,"
          "host_untouched=1,raw_string_upload=0")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--file",type=Path)
    args=p.parse_args()
    try:
        if args.selftest:selftest()
        elif args.file:
            raw=args.file.read_text(encoding="utf-8-sig")
            if len(raw)>16384:raise ValueError("data_unbounded")
            print("\n".join(analyze(raw.splitlines())))
        else:p.error("--selftest or --file required")
    except (ValueError,OSError):
        print("C545D_CACHE_SYNTH_AB_FAIL,"
              "reason=INCOMPLETE_OR_UNSAFE_NUMERIC_DATA,"
              "raw_content_uploaded=0")
        raise SystemExit(3) from None


if __name__=="__main__":
    main()
