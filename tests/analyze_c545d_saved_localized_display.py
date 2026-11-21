#!/usr/bin/env python3
"""Classify sanitized CI-only original WinRT Package.DisplayName values.

This reads an EXISTING failed GitHub Windows artifact on Linux; no new Windows
run, package install, locale change or user-machine action. All labels and
values are synthetic fixtures, and output is restricted to numeric booleans.
"""
import argparse
import re
from pathlib import Path

RE = re.compile(
    r"^C545D_RESOURCE_NAME_PROBE,phase=(main_add|resource_add|resource_remove),"
    r"expected=([01]),english=([01]),french=([01]),"
    r"actual_nonempty=([01]),thread_fr=1,CI_only=1$", re.M
)
EXPECTED = ("main_add", "resource_add")
SAFE_TAGS = ("C545D_RESOURCE_", "C545D_APPINFO_MONITOR_")


def classify(src: str) -> list[str]:
    if any(not (line.startswith(SAFE_TAGS) or not line.strip())
           for line in src.splitlines()):
        raise ValueError("non-allowlisted artifact data")
    matches = [m.groups() for m in RE.finditer(src)]
    if len(matches) != len(EXPECTED) or [m[0] for m in matches] != list(EXPECTED):
        raise ValueError("missing or extra original getter observations")
    for m in matches:
        _, expected, english, french, present = m
        if english == "1" and french == "1":
            raise ValueError("contradictory language classifier")
        if (english == "1" or french == "1") and present != "1":
            raise ValueError("contradictory nonempty flag")
    main, resource = matches
    if main[1:] != ("1", "1", "0", "1"):
        raise ValueError("original English baseline not established")
    if resource[1] != "0":
        raise ValueError("resource_add unexpected passed rather than reproduced")
    if "C545D_RESOURCE_CI_CLEANUP_EXECUTED=1,runner_only=1" not in src:
        raise ValueError("CI cleanup not observed")
    return [
        "C545D_ARCHIVED_LOCALIZED_DISPLAY,"
        f"main_english={main[2]},main_french={main[3]},"
        f"resource_english={resource[2]},resource_french={resource[3]},"
        f"resource_nonempty={resource[4]},"
        "resource_expected_failed=1,package_fullname_stable_precondition=1,"
        "real_recorder=0,source_owner_unproven=1",
        "C545D_ARCHIVED_LOCALIZED_DISPLAY_CLASSIFY_PASS,"
        "old_windows_run=44911762107,new_windows_runs=0,"
        "cached_gio_value_not_tested=1,release_approved=0",
    ]


def selftest() -> None:
    sample = "\n".join([
        "C545D_RESOURCE_NAME_PROBE,phase=main_add,expected=1,english=1,french=0,actual_nonempty=1,thread_fr=1,CI_only=1",
        "C545D_RESOURCE_NAME_PROBE,phase=resource_add,expected=0,english=1,french=0,actual_nonempty=1,thread_fr=1,CI_only=1",
        "C545D_RESOURCE_CI_CLEANUP_EXECUTED=1,runner_only=1",
    ])
    assert "CLASSIFY_PASS" in classify(sample)[-1]
    corrupt = (
        sample.replace("resource_add,expected=0", "resource_add,expected=1"),
        sample.replace("main_add,expected=1", "main_add,expected=0"),
        sample.replace("english=1,french=0,actual_nonempty=1", "english=1,french=1,actual_nonempty=1"),
        sample.replace("C545D_RESOURCE_CI_CLEANUP_EXECUTED=1,runner_only=1", ""),
        sample.replace("thread_fr=1,CI_only=1", "thread_fr=0,CI_only=1"),
        sample + "\nC:\\personal-user-path=unsafe",
    )
    for bad in corrupt:
        try:
            classify(bad)
        except ValueError:
            continue
        raise AssertionError("invalid/sensitive numeric evidence accepted")
    print("C545D_ARCHIVED_LOCALIZED_DISPLAY_ANALYZER_SELFTEST_PASS,negative_cases=6")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--input", type=Path)
    opts = ap.parse_args()
    if opts.selftest:
        selftest()
        return
    if opts.input is None:
        ap.error("--input is required")
    for row in classify(opts.input.read_text(encoding="utf-8-sig")):
        print(row)


if __name__ == "__main__":
    main()
