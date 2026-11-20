#!/usr/bin/env python3
"""CI-only end-to-end GIO locale cache invalidation check, numeric-only.

Compare identical 16-cycle synthetic registry activity, with a single
GIO AppInfo pool-thread SetThreadPreferredUILanguages change at scan 5. No system-wide
language changes, real installed package mutations, or recorder/camera.
"""
import re
from pathlib import Path

def require(condition, why):
    if not condition:
        raise ValueError(why)

def parse(path):
    data=Path(path).read_text(encoding="utf-8")
    require(data.count("GIO_PROBE_DONE,cycles=16,")==1, f"{path}: incomplete run")
    applied=re.findall(r"^C545D_GIO_WORKER_LOCALE_CHANGE,scan=5,count=(\d+)$",data,re.M)
    require(len(applied)==1 and int(applied[0])>0,
            f"{path}: missing real thread-locale mutation")
    cache=re.findall(r"^C545D_DISPLAY_CACHE,hits=(\d+),misses=(\d+),entries=(\d+)$",
                     data,re.M)
    require(bool(cache),f"{path}: cache telemetry absent")
    bridge=re.findall(r"^C545D_WINRT_BRIDGE,scans=(\d+),injections=(\d+),"
                      r"evictions=(\d+),errors=(\d+),ready=(\d+)$",data,re.M)
    handles=re.findall(r"^GIO_PROBE,(baseline|settled_cleanup),(\d+),\d+,(\d+),\d+$",
                       data,re.M)
    d={k:int(h) for k,_,h in handles}
    require("baseline" in d and "settled_cleanup" in d,
            f"{path}: no settled handle counters")
    require(d["settled_cleanup"]-d["baseline"]<=4,
            f"{path}: retained handle growth")
    return tuple(map(int,cache[-1])),tuple(map(int,bridge[-1])) if bridge else None

def main():
    plain,b0=parse("artifacts/locale_plain_16.log")
    changed,b1=parse("artifacts/locale_bridge_16.log")
    # GIO's asynchronous rebuild scheduling can produce one extra/omitted
    # final rescan. Assert the decisive cache refill instead of an exact
    # number of unrelated cache hits.
    require(plain[1:]==(32,32) and plain[0]>=480 and plain[0]%32==0,
            f"plain cache unexpected: {plain}")
    require(b0 is None,"plain cache unexpectedly enabled watch bridge")
    require(changed[1:]==(64,32) and changed[0]>=448 and changed[0]%32==0,
            f"locale change did not refetch 32 original names: {changed}")
    require(b1 is not None and b1[0]>=16 and b1[1:]==(0,1,0,1),
            f"epoch/language invalidation failed under real worker change: {b1}")
    print("C545D_GLIB_REAL_THREAD_LOCALE_INVALIDATION_PASS,"
          f"plain_hits={plain[0]},plain_misses=32,"
          f"bridge_hits={changed[0]},bridge_misses=64,"
          "locale_evictions=1,package_injections=0,errors=0,"
          "real_install_events_not_tested=true,ci_only=true")

if __name__=="__main__":
    try:
        main()
    except (OSError,ValueError) as e:
        raise SystemExit(f"C545D_GLIB_REAL_THREAD_LOCALE_INVALID:{e}")
