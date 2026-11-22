#!/usr/bin/env python3
"""Lock the original saved Combo GIO ETW16 numeric evidence to run 45015173260.

The generic paired validator checks safe schema and both arms, but those
checks alone permit valid *different* numbers. This optional strict offline
check makes an altered archive fail without collecting any new Windows data.
It never processes raw ETL, symbol strings, addresses or camera materials.
"""
from __future__ import annotations
import argparse
from pathlib import Path

import analyze_c545d_etw16_safe_pair as pair

# Original Windows run 45015173260, artifact 14750474942, independent
# successful replay 45015660780. Counts are module-frame occurrences from
# truncated top-25 circular ETW, NOT allocated/live bytes or proof of owner.
COUNTS = {
    "nochange": (470, 125, 164, 25, 47, 87, 0, 22),
    "registry": (458, 134, 184, 0, 53, 87, 0, 0),
}


def expected_arm(arm: str) -> str:
    frames, *category_counts = COUNTS[arm]
    return (
        f"C545D_GIO_ETW16_PAIRED_REPLAY_ARM,arm={arm},frames={frames},"
        + ",".join(f"{key}_frames={count}" for key, count in
                   zip(pair.GROUPS, category_counts))
        + ",source_owner_proven=0,top25_not_full_census=1"
    )


def verify(content: str) -> str:
    out = pair.parse(content)  # all original count, safety and privacy gates
    if out != [expected_arm("nochange"), expected_arm("registry"),
               "C545D_GIO_ETW16_PAIRED_REPLAY_PASS,"
               "distinct_processes=2,cycles_each=16,"
               "actual_private_commit_ownership_proven=0,"
               "stack_frame_count_not_allocation_bytes=1,"
               "real_host_untouched=1,original_256_rerun=0"]:
        raise ValueError("saved_run_numeric_fingerprint_mismatch")
    return (
        "C545D_GIO_ETW16_FROZEN_ARCHIVE_PASS,"
        "source_run=45015173260,artifact_id=14750474942,"
        "two_exact_arms=1,counts_locked=1,circular_trace=1,"
        "alloc_owner_proven=0,windows_runs=0,real_host_untouched=1"
    )


def safe_row(arm: str) -> str:
    frames, *values = COUNTS[arm]
    cells = [f"arm={arm}", "classification=module_frame_occurrences",
             f"frame_lines={frames}", f"frames={frames}"]
    cells += [f"{key}_frames={n}" for key, n in zip(pair.GROUPS, values)]
    cells += [f"{k}={v}" for k, v in pair.FLAGS.items()
              if k != "classification"]
    return pair.PREFIX + ",".join(cells)


def selftest() -> None:
    valid = safe_row("nochange") + "\n" + safe_row("registry")
    assert verify(valid).startswith("C545D_GIO_ETW16_FROZEN_ARCHIVE_PASS,")
    # The swapped category counts still sum to 470 and pass the *generic*
    # validator; they MUST fail the exact saved-run provenance check.
    corrupt = valid.replace("gio_frames=125,glib_frames=164",
                            "gio_frames=124,glib_frames=165")
    assert corrupt != valid
    assert len(pair.parse(corrupt)) == 3
    try:
        verify(corrupt)
    except ValueError:
        pass
    else:
        raise AssertionError("valid but changed numbers accepted as archived")
    try:
        verify(valid + "\n" + safe_row("registry"))
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate registry arm accepted")
    print("C545D_GIO_ETW16_FROZEN_SELFTEST_PASS,"
          "positive=1,negative=2,new_windows_runs=0,raw_uploaded=0")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--source", type=Path)
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    if a.source is None:
        p.error("--source required")
    try:
        print(verify(a.source.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError):
        print("C545D_GIO_ETW16_FROZEN_ARCHIVE_FAIL,"
              "reason=INVALID_OR_CHANGED_NUMERIC_ARCHIVE,raw_uploaded=0")
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
