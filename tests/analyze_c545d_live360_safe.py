#!/usr/bin/env python3
"""Strict numeric-only evaluator for disposable matched GIO Combo16 live360.

Each process records four snapshots of the current 360-byte HeapWalk BUSY
set. "same_address" is NOT continuous allocation identity due to address
reuse. No pointer, hash, heap handle, ETL, symbol or source stack is emitted.
A/B are separate processes: compare counts, NEVER addresses between arms.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re

import analyze_c545d_combo16_scanfree as old

PATTERN = re.compile(
    r"C545D_CI_LIVE360_SNAPSHOT,stage=([0-3]),"
    r"old=([0-9]{1,6}),now=([0-9]{1,6}),"
    r"same_address=([0-9]{1,6}),"
    r"appeared_address=([0-9]{1,6}),"
    r"disappeared_address=([0-9]{1,6}),"
    r"address_reuse_unexcluded=1,continuous_lifetime_proven=0,"
    r"allocation_owner_proven=0,global_quiescence_proven=0,"
    r"raw_address_emitted=0$"
)
CAP = 4096
WINDOWS = ((0, 1), (1, 2), (2, 3))


def parse_snapshots(raw: str) -> tuple[tuple[int, int, int, int, int], ...]:
    lines = raw.splitlines()
    if len(raw) > 8_000_000 or len(lines) > 200_000:
        raise ValueError("unbounded_local_probe_output")
    samples = {}
    for line in lines:
        if not line.startswith("C545D_CI_LIVE360_SNAPSHOT,"):
            continue
        match = PATTERN.fullmatch(line)
        if match is None:
            raise ValueError("changed_snapshot_or_unsafe_metadata")
        stage, old_count, now, same, appeared, disappeared = map(
            int, match.groups())
        if stage in samples:
            raise ValueError("duplicate_stage")
        if any(n > CAP for n in
               (old_count, now, same, appeared, disappeared)):
            raise ValueError("capacity_exceeded")
        samples[stage] = (old_count, now, same, appeared, disappeared)
    if set(samples) != set(range(4)):
        raise ValueError("missing_stages")
    for stage in range(4):
        old_count, now, same, appeared, disappeared = samples[stage]
        if stage == 0:
            if (old_count, same, appeared, disappeared) != (0, 0, 0, 0):
                raise ValueError("invalid_baseline_transition")
        else:
            if (old_count != samples[stage - 1][1] or
                    same + appeared != now or
                    same + disappeared != old_count):
                raise ValueError("inconsistent_snapshot_conservation")
    return tuple(samples[i] for i in range(4))


def analyze(folder: Path) -> list[str]:
    control = {}
    out = []
    for arm in ("nochange", "registry"):
        raw = (folder / f"combo-{arm}-16.txt").read_text(
            encoding="utf-8-sig")
        # Also verify the old numeric probe cohort, cycle samples, and
        # scanfree caller behavior. Do not pair with a different trial.
        old.read(raw, arm == "registry")
        stages = parse_snapshots(raw)
        control[arm] = [s[1] for s in stages]
        for stage, (prior, now, same, appeared, gone) in enumerate(stages):
            out.append(
                "C545D_GIO_LIVE360_ARM,"
                f"arm={arm},stage={stage},"
                f"now={now},same_address={same},"
                f"appeared_address={appeared},disappeared_address={gone},"
                "continuous_lifetime_proven=0,allocation_site_proven=0"
            )
    for a, b in WINDOWS:
        effect = ((control["registry"][b] - control["registry"][a])
                  - (control["nochange"][b] - control["nochange"][a]))
        out.append(
            "C545D_GIO_LIVE360_CONTROLLED,"
            f"stage_window={a}_{b},count_difference_in_differences={effect},"
            "separate_processes=1,addresses_not_cross_compared=1,"
            "not_private_usage_bytes=1,leak_rate_proven=0"
        )
    out.append(
        "C545D_GIO_LIVE360_PAIRED_PASS,"
        "arms=2,cycles_each=16,phase_count=4,"
        "snapshots_valid=8,original_256_rerun=0,"
        "address_reuse_unexcluded=1,allocation_owner_proven=0,"
        "global_quiescence_proven=0,real_host_tested=0"
    )
    return out


def fixture(now: tuple[int, ...], matched: tuple[int, ...]) -> str:
    lines = []
    for stage in range(4):
        prior = now[stage - 1] if stage else 0
        same = matched[stage]
        appeared = now[stage] - same if stage else 0
        gone = prior - same if stage else 0
        lines.append(
            f"C545D_CI_LIVE360_SNAPSHOT,stage={stage},"
            f"old={prior},now={now[stage]},same_address={same},"
            f"appeared_address={appeared},disappeared_address={gone},"
            "address_reuse_unexcluded=1,continuous_lifetime_proven=0,"
            "allocation_owner_proven=0,global_quiescence_proven=0,"
            "raw_address_emitted=0"
        )
    return "\n".join(lines)


def selftest() -> None:
    clean = fixture((10, 12, 5, 13), (0, 8, 4, 4))
    assert tuple(s[1] for s in parse_snapshots(clean)) == (10, 12, 5, 13)
    corrupt = [
        clean.replace("stage=0", "stage=1", 1),
        clean.replace("old=10,now=12", "old=9,now=12"),
        clean.replace("same_address=8", "same_address=9", 1),
        clean.replace("appeared_address=4", "appeared_address=5", 1),
        clean.replace("now=13", "now=4097", 1),
        clean.replace("allocation_owner_proven=0",
                      "allocation_owner_proven=1", 1),
        clean + "\n" + clean.splitlines()[0],
        "\n".join(clean.splitlines()[:3]),
        clean.replace("raw_address_emitted=0",
                      "raw_address_emitted=C:\\Users\\X\\secret", 1),
    ]
    for change in corrupt:
        if change == clean:
            raise AssertionError("fixture mutation missing")
        try:
            parse_snapshots(change)
        except ValueError:
            continue
        raise AssertionError("unsafe or malformed numeric snapshot accepted")
    print(
        "C545D_LIVE360_NUMERIC_SELFTEST_PASS,"
        "positive=1,negative=9,original_256_rerun=0,"
        "raw_addresses_emitted=0,windows_runs=0"
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--folder", type=Path)
    p.add_argument("--source", type=Path)
    args = p.parse_args()
    try:
        if args.selftest:
            selftest()
        elif args.folder is not None:
            print("\n".join(analyze(args.folder)))
        elif args.source is not None:
            rows = parse_snapshots(args.source.read_text(encoding="utf-8-sig"))
            print(
                "C545D_LIVE360_SINGLE_PARSED_PASS,"
                f"stages={len(rows)},address_reuse_unexcluded=1,"
                "allocation_owner_proven=0,raw_uploaded=0"
            )
        else:
            p.error("--selftest or --folder or --source required")
    except (OSError, ValueError):
        print(
            "C545D_LIVE360_NUMERIC_FAIL,"
            "reason=INVALID_OR_UNSAFE_COUNTS,raw_uploaded=0"
        )
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
