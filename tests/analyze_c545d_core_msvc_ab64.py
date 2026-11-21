#!/usr/bin/env python3
"""Analyze SAVED numeric 64-cycle MSVC GIO SDK/candidate A/B logs.

No new registry test, DLL build or host interaction. The original A/B workflow
incorrectly subtracted a -29-handle *natural cleanup* from the patched +1
absolute handle lifetime, calling it +30. Both numbers are useful, but only
the +1 is a valid absolute lifetime-plateau assertion.

Do not interpret positive PrivateUsage as a zero-leak result.
"""
import argparse
import json
from pathlib import Path
import re


def parse(root: Path, mode: str, scenario: str) -> dict:
    p = root / f"{mode}-{scenario}-64.txt"
    text = p.read_text(encoding="utf-8", errors="replace")

    done = re.findall(
        r"^GIO_PROBE_DONE,cycles=(\d+),notifications=(\d+),reg_changes=([01])$",
        text, re.M,
    )
    if len(done) != 1 or int(done[0][0]) != 64:
        raise ValueError(f"{p}: missing exact 64-cycle completion")
    if int(done[0][2]) != int(scenario == "registry"):
        raise ValueError(f"{p}: incorrect registry/no-change control label")

    records = re.findall(
        r"^GIO_PROBE,(baseline|settled_cleanup),(\d+),(\d+),(\d+),(\d+)$",
        text, re.M,
    )
    if len(records) != 2:
        raise ValueError(f"{p}: wrong process-memory boundary count")
    d = {tag: (int(cyc), int(notify), int(handles), int(private))
         for tag, cyc, notify, handles, private in records}
    if set(d) != {"baseline", "settled_cleanup"} or (
        d["baseline"][0], d["settled_cleanup"][0]
    ) != (0, 66):
        raise ValueError(f"{p}: incorrect sample stage")

    key_records = re.findall(
        r"^GIO_KEY,(baseline|settled_cleanup),(\d+),(\d+)$",
        text, re.M,
    )
    if len(key_records) != 2:
        raise ValueError(f"{p}: missing independent Sysinternals Key census")
    keys = {tag: (int(cyc), int(count))
            for tag, cyc, count in key_records}
    if set(keys) != {"baseline", "settled_cleanup"}:
        raise ValueError(f"{p}: wrong Key snapshot stages")
    if (keys["baseline"][0], keys["settled_cleanup"][0]) != (0, 66):
        raise ValueError(f"{p}: Key boundary cycle mismatch")
    if len(re.findall(r"^GIO_PROBE,cycle,\d+,", text, re.M)) != 64:
        raise ValueError(f"{p}: missing cycle records")

    return {
        "handles": d["settled_cleanup"][2] - d["baseline"][2],
        "private_bytes": d["settled_cleanup"][3] - d["baseline"][3],
        "key": keys["settled_cleanup"][1] - keys["baseline"][1],
        "cycles": 64,
        "registry_mutation_enabled": int(scenario == "registry"),
    }


def evaluate(rows: dict) -> tuple:
    effect = {
        metric: {
            mode: (rows[f"{mode}_registry"][metric]
                   - rows[f"{mode}_nochange"][metric])
            for mode in ("official", "candidate")
        }
        for metric in ("handles", "key", "private_bytes")
    }
    # Key comparison is control-subtracted because the same 3 system Key
    # handles naturally close during both no-change process lifetimes.
    if effect["key"]["official"] <= 20:
        raise ValueError("Official SDK Key-leak positive control missing")
    if effect["key"]["candidate"] > 4:
        raise ValueError("Candidate retained Key count exceeds strict gate")

    # ABSOLUTE candidate registry lifetime is the correct handle-plateau
    # condition; an ordinary -29 no-change baseline must not be added back
    # and misrepresented as 30 retained handles.
    if rows["candidate_registry"]["handles"] > 4:
        raise ValueError("Candidate absolute total-handle lifetime regressed")
    if rows["candidate_registry"]["key"] > 4:
        raise ValueError("Candidate absolute Key lifetime regressed")
    if effect["private_bytes"]["candidate"] >= effect["private_bytes"]["official"]:
        raise ValueError("PrivateUsage control-subtracted effect did not improve")

    old_p = effect["private_bytes"]["official"]
    new_p = effect["private_bytes"]["candidate"]
    pct = (100.0 * (old_p - new_p) / old_p) if old_p > 0 else None
    return effect, pct


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("artifacts"))
    args = ap.parse_args()
    rows = {
        f"{mode}_{scenario}": parse(args.root, mode, scenario)
        for mode in ("official", "candidate")
        for scenario in ("nochange", "registry")
    }
    effect, pct = evaluate(rows)
    summary = {
        "source": "artifact from exact MSVC core-only candidate A/B run 44759302126",
        "criteria": "candidate absolute handles<=4; control-subtracted Key effect<=4; PrivateUsage improved",
        "modes": rows,
        "control_subtracted_effect": effect,
        "private_usage_effect_reduction_percent": round(pct, 4) if pct is not None else None,
        "real_windows10_tapo_verified": False,
        "leak_free_claim": False,
    }
    (args.root / "ab64_corrected_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(
        "C545D_CORE_ONLY_MSVC_64_AB_CORRECTED_PASS,"
        f"official_Key_effect={effect['key']['official']},"
        f"candidate_Key_effect={effect['key']['candidate']},"
        f"candidate_absolute_handles={rows['candidate_registry']['handles']},"
        f"official_PrivateUsage_effect_B={effect['private_bytes']['official']},"
        f"candidate_PrivateUsage_effect_B={effect['private_bytes']['candidate']},"
        f"PrivateUsage_reduction_pct={pct:.4f},"
        "cycles_per_mode=64,modes=4,CI_only=1,zero_leak_NOT_proven=1"
    )


if __name__ == "__main__":
    main()
