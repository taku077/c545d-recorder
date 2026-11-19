#!/usr/bin/env python3
"""CI-only 16-cycle UWP internals A/B analyzer.

Compares each isolated stage with a no-registry-change control under
the exact same diagnostic build. All outputs are aggregate numeric counts.
"""
import csv
import sys
from pathlib import Path

STAGES = ("default", "noop_callback", "skip_manifest", "skip_path", "skip_location", "skip_displayname", "no_displayname_getter", "call_displayname_discard", "cache_displayname", "skip_current")
TAGS = {"GIO_PROBE": 6, "GIO_HEAP": 7, "GIO_VM": 8}


def parse(path):
    data = {}
    count = 0
    done = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(",")
        tag = parts[0]
        if tag == "GIO_PROBE_DONE":
            if "cycles=16" in line:
                done += 1
        if tag == "GIO_PROBE" and len(parts) >= 2 and parts[1] == "cycle":
            count += 1
        if tag not in TAGS:
            continue
        if len(parts) != TAGS[tag]:
            raise ValueError(f"{path}: malformed {tag}")
        if parts[1] not in ("baseline", "settled_cleanup"):
            continue
        if any(not value.isdecimal() for value in parts[2:]):
            raise ValueError(f"{path}: invalid numeric fields")
        key = (tag, parts[1])
        if key in data:
            raise ValueError(f"{path}: duplicate {key}")
        data[key] = list(map(int, parts[2:]))
    if done != 1 or count != 16 or len(data) != 6:
        raise ValueError(f"{path}: missing 16-cycle result or required checkpoint")
    for phase in ("baseline", "settled_cleanup"):
        if data[("GIO_HEAP", phase)][-1] or data[("GIO_VM", phase)][-1]:
            raise ValueError(f"{path}: invalid heap or VirtualQuery census")
    before = {tag: data[(tag, "baseline")] for tag in TAGS}
    after = {tag: data[(tag, "settled_cleanup")] for tag in TAGS}
    return {
        "private_bytes": after["GIO_PROBE"][3]-before["GIO_PROBE"][3],
        "busy_bytes": after["GIO_HEAP"][2]-before["GIO_HEAP"][2],
        "busy_blocks": after["GIO_HEAP"][1]-before["GIO_HEAP"][1],
        "vm_private_bytes": after["GIO_VM"][1]-before["GIO_VM"][1],
        "total_handles": after["GIO_PROBE"][2]-before["GIO_PROBE"][2],
    }


def main():
    root = Path("artifacts")
    rows = []
    for name in STAGES:
        control = parse(root / f"{name}_nochange_16.log")
        changed = parse(root / f"{name}_registry_16.log")
        net = {k: changed[k]-control[k] for k in control}
        if name == "cache_displayname":
            import re
            for suffix in ("nochange", "registry"):
                log = (root / f"cache_displayname_{suffix}_16.log").read_text(
                    encoding="utf-8"
                )
                cache_rows = re.findall(
                    r"^C545D_DISPLAY_CACHE,hits=(\d+),misses=(\d+),entries=(\d+)$",
                    log, re.MULTILINE
                )
                if not cache_rows:
                    raise ValueError("Missing cache counters: " + suffix)
                hits, misses, entries = map(int, cache_rows[-1])
                # The no-change control may need only one initial scan,
                # legitimately producing zero cache hits. Registry mutations
                # must trigger repeated scans and actual cache reuse.
                if misses <= 0 or not 0 < entries <= 1024 or (suffix == "registry" and hits <= 0):
                    raise ValueError("Unusable cache census: " + suffix)
                print(f"C545D_DISPLAY_CACHE_VALIDATED,{suffix},"
                      f"hits={hits},misses={misses},entries={entries}")
        print("UWP_API_STAGE," + name + "," +
              ",".join(f"{k}={v:+d}" for k, v in net.items()))
        rows.append((name, net))
    with (root / "uwp_api_stage_deltas.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("stage", *rows[0][1].keys()))
        for name, results in rows:
            writer.writerow([name, *results.values()])
    print("UWP_API_STAGE_DIAGNOSTIC_PASS; NO_PRODUCT_FEATURES_DISABLED")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as e:
        print(f"UWP_API_STAGE_DIAGNOSTIC_INVALID: {e}", file=sys.stderr)
        sys.exit(2)
