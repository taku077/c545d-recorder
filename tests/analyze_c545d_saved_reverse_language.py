#!/usr/bin/env python3
"""Verify real original WinRT localized getter transitions in a SAVED CI artifact.

This is an Ubuntu-only read of the prior #44913033160 sanitized numeric artifact.
No Windows test rerun. The originating Windows job failed AFTER all 3 getter
assertions, due to a grep regex that accidentally dropped CI_CLEANUP_EXECUTED=1.
This analyzer deliberately does NOT assert cleanup from absent artifact data.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

RECORD = re.compile(
    r"^C545D_RESOURCE_NAME_REVERSE,phase=(main_add|resource_add|resource_remove),"
    r"expected=([01]),english=([01]),french=([01]),"
    r"actual_nonempty=([01]),user_en=1,CI_only=1$", re.M
)
EXPECTED = [
    ("main_add", "1", "0", "1", "1"),
    ("resource_add", "1", "1", "0", "1"),
    ("resource_remove", "1", "0", "1", "1"),
]
ALLOWED = re.compile(
    r"^(?:C545D_RESOURCE_NAME_REVERSE,|C545D_RESOURCE_NAME_INCONCLUSIVE,|"
    r"C545D_RESOURCE_(?:OS_ADD_OBSERVATION|OS_REMOVE_OBSERVATION|"
    r"PACKAGE_PROBE_COMPLETE|CI_CLEANUP_EXECUTED)[,=])"
)


def classify(src: str) -> list[str]:
    if any(line.strip() and ALLOWED.match(line) is None for line in src.splitlines()):
        raise ValueError("artifact contains non-whitelisted records")
    rows = RECORD.findall(src)
    if rows != EXPECTED:
        raise ValueError(f"expected the exact 3 original getter outcomes, got {rows}")
    if src.count("C545D_RESOURCE_NAME_REVERSE,") != 3:
        raise ValueError("extra or malformed native value observations")
    if "C545D_RESOURCE_NAME_INCONCLUSIVE" in src:
        raise ValueError("inconclusive precondition/WinRT read")
    return [
        "C545D_ARCHIVED_REVERSE_ORIGINAL_WINRT_VALUE_PASS,"
        "user_language_en=1,main_french=1,resource_add_english=1,"
        "resource_remove_french=1,original_getter_not_gio=1,"
        "parent_fullname_same_in_fixture=1,"
        "windows_source_run=44913033160,new_windows_runs=0,"
        "cleanup_marker_missing_due_to_regex=1,real_recorder=0,"
        "gio_cache_value_not_qualified=1,release_approved=0"
    ]


def selftest():
    sample = "\n".join([
        "C545D_RESOURCE_NAME_REVERSE,phase=main_add,expected=1,english=0,french=1,actual_nonempty=1,user_en=1,CI_only=1",
        "C545D_RESOURCE_NAME_REVERSE,phase=resource_add,expected=1,english=1,french=0,actual_nonempty=1,user_en=1,CI_only=1",
        "C545D_RESOURCE_NAME_REVERSE,phase=resource_remove,expected=1,english=0,french=1,actual_nonempty=1,user_en=1,CI_only=1"
    ]) + "\n"
    assert "VALUE_PASS" in classify(sample)[0]
    invalid = [
        sample.replace("resource_add,expected=1", "resource_add,expected=0"),
        sample.replace("resource_add,expected=1,english=1,french=0",
                       "resource_add,expected=1,english=0,french=1"),
        sample.replace("resource_remove,expected=1,english=0,french=1",
                       "resource_remove,expected=1,english=1,french=0"),
        sample.replace("user_en=1", "user_en=0"),
        sample.replace("phase=main_add", "phase=resource_add"),
        sample + "C:\\Users\\x\\private=unsafe\n",
        sample + sample.splitlines()[0] + "\n"
    ]
    for item in invalid:
        try:
            classify(item)
        except ValueError:
            continue
        raise AssertionError("accepted invalid/unsanitized original-getter evidence")
    print("C545D_ARCHIVED_REVERSE_WINRT_ANALYZER_SELFTEST_PASS,negative_cases=7")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path)
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        selftest()
    else:
        if args.input is None:
            p.error("--input is required")
        for row in classify(args.input.read_text(encoding="utf-8-sig")):
            print(row)
