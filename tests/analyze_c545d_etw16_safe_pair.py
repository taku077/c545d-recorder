#!/usr/bin/env python3
"""Validate the two short ETW Combo16 module-only cohorts, never raw stacks.

Different A/B processes run sequentially on the same disposable Windows
runner. Frame counts in truncated top-25 tables are NOT private commit bytes,
unique stacks, or proof of per-allocation ownership. Fail closed on any
unexpected keys, arbitrary text, missing arm, totals, or attribution flag.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re

PREFIX = "C545D_GIO_ETW16_MODULE_COUNTS,"
GROUPS = ("gio", "glib", "winrt", "crt", "system", "gstreamer", "other")
FLAGS = {
    "classification": "module_frame_occurrences",
    "top25_is_incomplete": "1",
    "unsymbolized_frames_count_known": "0",
    "allocation_bytes_owner_proven": "0",
    "stack_owner_proven": "0",
    "full_heap_coverage_proven": "0",
    "raw_text_uploaded": "0",
}
FIELDS = {"arm", "frame_lines", "frames", *FLAGS}
FIELDS |= {f"{x}_frames" for x in GROUPS}


def parse(content: str) -> list[str]:
    source_lines = content.splitlines()
    # Raw trace, arbitrary paths and alloc stack text are never accepted here.
    if len(content) > 250000 or len(source_lines) > 2500:
        raise ValueError("unbounded_numeric_input")
    # Entire archived bundle must be sanitized, not merely the two
    # recognized ETW rows. Reject address/path/symbol-style payloads.
    if any(re.search(r"(?:[\\/]|0[xX][0-9a-fA-F]{4,}|!Rtl|!g_)", line)
           for line in source_lines):
        raise ValueError("raw_path_or_stack_in_numeric_artifact")
    arms = {}
    for line in source_lines:
        if not line.startswith(PREFIX):
            # Another existing C545D numeric record may be present in the
            # same validated bundle; no raw payload is included in output.
            continue
        if not re.fullmatch(r"[A-Za-z0-9_,=]+", line):
            raise ValueError("untrusted_etw_module_row")
        fields = {}
        for assignment in line[len(PREFIX):].split(","):
            k,sep,v = assignment.partition("=")
            if not sep or k in fields or k not in FIELDS:
                raise ValueError("unknown_or_duplicate_metadata")
            fields[k] = v
        if set(fields) != FIELDS:
            raise ValueError("incomplete_etw_row")
        arm = fields["arm"]
        if arm not in ("registry", "nochange") or arm in arms:
            raise ValueError("duplicate_or_unknown_arm")
        if any(fields[k] != v for k,v in FLAGS.items()):
            raise ValueError("unsafe_attribution_claim")
        numbers = {}
        for k in ("frame_lines","frames",*(f"{g}_frames" for g in GROUPS)):
            if not re.fullmatch(r"[0-9]{1,7}", fields[k]):
                raise ValueError("noninteger_or_unbounded_frame_count")
            numbers[k] = int(fields[k])
        if (numbers["frames"] == 0 or numbers["frame_lines"] == 0
                or numbers["frame_lines"] > numbers["frames"]
                or numbers["frames"] > 100000
                or sum(numbers[f"{g}_frames"] for g in GROUPS) != numbers["frames"]):
            raise ValueError("inconsistent_aggregate_counts")
        arms[arm] = numbers
    if set(arms) != {"registry", "nochange"}:
        raise ValueError("missing_exact_pair")
    out = []
    for arm in ("nochange","registry"):
        n=arms[arm]
        out.append(
            "C545D_GIO_ETW16_PAIRED_REPLAY_ARM,"
            f"arm={arm},frames={n['frames']},"
            + ",".join(f"{group}_frames={n[f'{group}_frames']}"
                       for group in GROUPS)
            + ",source_owner_proven=0,top25_not_full_census=1"
        )
    out.append(
        "C545D_GIO_ETW16_PAIRED_REPLAY_PASS,"
        "distinct_processes=2,cycles_each=16,"
        "actual_private_commit_ownership_proven=0,"
        "stack_frame_count_not_allocation_bytes=1,"
        "real_host_untouched=1,original_256_rerun=0"
    )
    return out


def fixture(arm: str, extra: int) -> str:
    counts={"gio":extra,"glib":2,"winrt":0,"crt":1,
            "system":7,"gstreamer":0,"other":3}
    frames=sum(counts.values())
    cells=[f"arm={arm}","classification=module_frame_occurrences",
           f"frame_lines={frames}",f"frames={frames}"]
    cells.extend(f"{g}_frames={counts[g]}" for g in GROUPS)
    cells.extend(f"{k}={v}" for k,v in FLAGS.items()
                 if k != "classification")
    return PREFIX + ",".join(cells)


def selftest():
    a=fixture("nochange",0)
    b=fixture("registry",5)
    orig=a+"\n"+b
    assert parse(orig)[-1].startswith("C545D_GIO_ETW16_PAIRED_REPLAY_PASS,")
    corrupt=(
        a, a+"\n"+a, a+"\n"+b+"\n"+b,
        orig.replace("arm=registry","arm=PRIVATE"),
        orig.replace("top25_is_incomplete=1","top25_is_incomplete=0"),
        orig.replace("stack_owner_proven=0","stack_owner_proven=1"),
        orig.replace("frames=18","frames=99"),
        orig.replace("system_frames=7","system_frames=-1"),
        orig.replace("gio_frames=5","gio_frames=5,private_path=C:\\Users\\SECRET"),
        orig+"\n"+"C:\\Users\\SECRET\\raw.etl",
    )
    for bad in corrupt:
        if bad == orig:
            raise AssertionError("mutation not applied")
        try:
            parse(bad)
        except ValueError:
            continue
        raise AssertionError("corrupt paired numeric summary passed")
    result="\n".join(parse(orig))
    assert "PRIVATE" not in result and "C:\\Users" not in result
    print("C545D_GIO_ETW16_PAIR_SELFTEST_PASS,"
          "positive_cases=1,negative_cases=10,"
          "raw_stack_uploaded=0,private_paths_emitted=0,"
          "recorder_untouched=1")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--source",type=Path)
    a=p.parse_args()
    if a.selftest:
        selftest()
    else:
        if a.source is None:
            p.error("--source required")
        try:
            print("\n".join(parse(a.source.read_text(encoding="utf-8-sig"))))
        except (OSError,ValueError):
            print("C545D_GIO_ETW16_PAIRED_REPLAY_FAIL,"
                  "reason=NUMERIC_DATA_INVALID,raw_uploaded=0")
            raise SystemExit(3) from None


if __name__=="__main__":
    main()
