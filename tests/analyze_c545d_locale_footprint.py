#!/usr/bin/env python3
"""Compare two fresh, isolated Windows 8,192-call-block locale API trials.

The input is a number-only summary from C++ Win32 API calls; no package
or language values. A positive PrivateUsage difference is not a leak proof
or direct explanation of patched GIO residual.
"""
from __future__ import annotations
from pathlib import Path
import re
import argparse

POINTS = ("baseline", "first8192", "second8192", "post_idle")
ARMS = ("control", "locale")
LINE = re.compile(r"C545D_LOCALE_FOOTPRINT,([a-z0-9_]+),(\d+),(\d+)$")
END = re.compile(
    r"C545D_LOCALE_FOOTPRINT_DONE,arm=(control|locale),"
    r"iterations=16384,api_calls_per_iteration=(0|4),"
    r"windows_runner_only=1$"
)


def read(text: str, arm: str) -> dict[str, tuple[int, int]]:
    entries: dict[str, tuple[int, int]] = {}
    end: list[tuple[str, str]] = []
    for line in text.splitlines():
        if line.startswith("C545D_LOCALE_FOOTPRINT_DONE,"):
            m = END.fullmatch(line)
            if m is None:
                raise ValueError("bad end marker")
            end.append(m.groups())
        elif line.startswith("C545D_LOCALE_FOOTPRINT,"):
            m = LINE.fullmatch(line)
            if not m:
                raise ValueError("bad numeric footprint")
            phase, private, handles = m.groups()
            if phase not in POINTS or phase in entries:
                raise ValueError("unknown/duplicate phase")
            if int(private) <= 0 or int(handles) <= 0:
                raise ValueError("invalid process resources")
            entries[phase] = (int(private), int(handles))
    if list(entries) != list(POINTS):
        raise ValueError("missing or nonchronological snapshot")
    if end != [(arm, "4" if arm == "locale" else "0")]:
        raise ValueError("missing/wrong-matched arm completion")
    return entries


def analyze(folder: Path) -> list[str]:
    a = {arm: read((folder / f"{arm}.txt").read_text(encoding="utf-8-sig"),
                   arm) for arm in ARMS}
    output = []
    for i in range(len(POINTS) - 1):
        start, end = POINTS[i], POINTS[i + 1]
        for metric, name in ((0, "PrivateUsage"), (1, "handles")):
            ctl = a["control"][end][metric] - a["control"][start][metric]
            loc = a["locale"][end][metric] - a["locale"][start][metric]
            output.append(
                f"C545D_LOCALE_AB,metric={name},"
                f"window={start}_{end},"
                f"control_raw={ctl},locale_raw={loc},"
                f"control_adjusted={loc-ctl},"
                "two_separate_processes=1,allocator_cause_unproven=1,CI_only=1"
            )
    output.append(
        "C545D_LOCALE_FOOTPRINT_PASS,source=dedicated_snapshot_hash_language_list,"
        "windows_api=1,per_arm_iterations=16384,locale_arm_API_calls=65536,"
        "matched_processes=2,original_combo_256_unrerun=1,"
        "no_GIO_DLL_loaded=1,real_host_untested=1,"
        "leak_attribution_unproven=1"
    )
    return output


def selftest() -> None:
    def good(arm: str) -> str:
        lines = [f"C545D_LOCALE_FOOTPRINT,{p},{10000+i*4096},{15+i}"
                 for i, p in enumerate(POINTS)]
        lines.append(
            "C545D_LOCALE_FOOTPRINT_DONE,"
            f"arm={arm},iterations=16384,"
            f"api_calls_per_iteration={4 if arm == 'locale' else 0},"
            "windows_runner_only=1"
        )
        return "\n".join(lines)
    assert len(read(good("locale"), "locale")) == 4
    assert len(read(good("control"), "control")) == 4
    cases = (
        good("locale").replace("arm=locale", "arm=control"),
        good("locale").replace("second8192", "first8192"),
        good("locale").replace("10000", "-1"),
        good("locale").replace("windows_runner_only=1", "windows_runner_only=0"),
        good("locale").replace("baseline", "post_idle"),
    )
    for case in cases:
        try: read(case, "locale")
        except ValueError: pass
        else: raise AssertionError("invalid locale A/B evidence accepted")
    print("C545D_LOCALE_FOOTPRINT_SELFTEST_PASS,positive=2,negative=5,"
          "Windows_API_calls=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--folder", type=Path)
    a = p.parse_args()
    if a.selftest:
        selftest()
    else:
        if a.folder is None:
            p.error("--folder required")
        print("\n".join(analyze(a.folder)))


if __name__ == "__main__":
    main()
