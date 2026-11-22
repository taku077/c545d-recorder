#!/usr/bin/env python3
"""Verify that the real GLib diagnostic cache frees/reuses entries on invalidation.

Paired Windows 2022 short tests; production invalidation is NOT implemented.
No installed package names or personal data are recorded.
"""
from pathlib import Path
import re
import sys
from analyze_gio_uwp_api_isolation import parse

root=Path("artifacts")

def read(mode, kind):
    path=root/f"{mode}_{kind}_16.log"
    text=path.read_text(encoding="utf-8")
    values=parse(path)
    match=re.findall(r"^C545D_DISPLAY_CACHE,hits=(\d+),misses=(\d+),entries=(\d+)$",text,re.M)
    refresh=re.findall(r"^C545D_DISPLAY_CACHE_REFRESH,scans=(\d+),resets=(\d+)$",text,re.M)
    nulls=re.findall(r"^C545D_DISPLAY_CACHE_NULL_HSTRING_RETURNS=(\d+)$",text,re.M)
    if not (match and refresh and nulls):
        raise ValueError("missing cache/refresh/empty-display census: "+str(path))
    hits, misses, entries = map(int,match[-1])
    scans, resets=map(int,refresh[-1])
    empty=int(nulls[-1])
    if entries != 32 or hits < 0:
        raise ValueError(f"{path}: unexpected cache size or hits")
    if mode == "cache":
        # The ordinary cache never enables synthetic refresh counting.
        if scans != 0 or resets != 0 or empty != 1:
            raise ValueError(f"{path}: control cache telemetry invalid")
    else:
        # Each actual reset re-fetches one empty HSTRING, preserving its
        # original value. Do NOT confuse successful empty re-fetches with leaks.
        if scans < 1 or empty != resets + 1:
            raise ValueError(f"{path}: invalid synthetic reset or null-result census")
    return values,(hits,misses,entries,scans,resets,empty)

def main():
    baseline={}
    for mode in ("cache", "refresh"):
        normal,c0=read(mode,"nochange")
        reg,c1=read(mode,"registry")
        d={key:reg[key]-normal[key] for key in normal}
        baseline[mode]=d
        if abs(d["total_handles"]) > 4:
            raise ValueError(f"{mode}: significant change in handle delta")
        if c0[4] != 0:
            raise ValueError(f"{mode}: control must have zero refreshes")
        if mode == "cache":
            if c1[4] != 0 or c1[1] != c1[2]:
                raise ValueError("baseline cache unexpectedly misses again")
        else:
            if c1[4] < 2 or c1[4] > 6:
                raise ValueError("no deterministic synthetic invalidations")
            if c1[1] != c1[2]*(c1[4]+1):
                raise ValueError("refreshed cache failed to refetch exactly once after invalidation")
        print(f"C545D_CACHE_REFRESH_STAGE,{mode},"
              f"private_bytes={d['private_bytes']:+d},"
              f"busy_bytes={d['busy_bytes']:+d},"
              f"busy_blocks={d['busy_blocks']:+d},"
              f"handles={d['total_handles']:+d},"
              f"hits={c1[0]},misses={c1[1]},entries={c1[2]},"
              f"scans={c1[3]},resets={c1[4]},null_getters={c1[5]}")
    # A refill naturally can cost memory; this test does not fake a plateau.
    print("C545D_GLIB_CACHE_FORCED_REFRESH_PASS; SYNTHETIC_INVALIDATION_ONLY; "
          "UI_RESOURCE_AND_REAL_EVENT_INVALIDATION_NOT_CERTIFIED")

if __name__=="__main__":
    try: main()
    except (ValueError,OSError) as e:
        print("C545D_GLIB_CACHE_FORCED_REFRESH_INVALID:"+str(e),file=sys.stderr)
        sys.exit(2)
