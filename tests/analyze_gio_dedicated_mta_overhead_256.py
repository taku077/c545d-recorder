#!/usr/bin/env python3
"""GIO exact original-DisplayName cache versus dedicated PackageCatalog MTA.

Isolated Windows 2022 CI only, same-run 2x2 arms (registry/nochange control
times existing exact cache / exact cache with dedicated WinRT watcher).
Reports both first and last 128-cycle slopes; startup cost is not automatically
an ongoing leak. Retains strict positive handle-growth checks.
"""
from pathlib import Path
import csv
import re
import sys
from analyze_gio_residual_growth import read_series, CHECKPOINTS

ROOT=Path("artifacts")
MODES=("cache_only","mta_watch")
METRICS={
  "private_bytes":("GIO_PROBE",2),
  "heap_busy_bytes":("GIO_HEAP",1),
  "heap_busy_blocks":("GIO_HEAP",0),
  "vm_private_commit":("GIO_VM",0),
}

def load(mode,kind):
    path=ROOT/f"{mode}_{kind}_256.log"
    series=read_series(path)
    lines=path.read_text(encoding="utf-8")
    cs=re.findall(r"^C545D_DISPLAY_CACHE,hits=(\d+),misses=(\d+),entries=(\d+)$",
                  lines,re.M)
    if not cs: raise ValueError(f"missing original DisplayName cache census for {mode}/{kind}")
    hits,misses,entries=map(int,cs[-1])
    if not (misses==entries and 0<entries<=1024):
        raise ValueError(f"{mode}/{kind}: recurring getter calls or excessive cache")
    if kind=="registry" and hits<4096:raise ValueError(f"{mode} cache not reused")
    if mode=="mta_watch":
        events=re.findall(
            r"^C545D_WINRT_BRIDGE,scans=(\d+),injections=(\d+),"
            r"evictions=(\d+),errors=(\d+),ready=(\d+)$",lines,re.M)
        if not events:raise ValueError(f"missing dedicated watcher telemetry {kind}")
        scans,inj,evict,errors,ready=map(int,events[-1])
        # An unchanged-registry control opens AppInfo once, while the
        # registry-change arm re-enumerates each cycle. Expect DIFFERENT
        # scan counts; do not falsely flag an idle watcher as unavailable.
        expected_scan_ok = scans==1 if kind=="nochange" else scans>=250
        if not expected_scan_ok or inj or evict or errors or ready!=1:
            raise ValueError(f"dedicated watcher unhealthy in {kind}: {events[-1]}")
    else:
        if "C545D_WINRT_BRIDGE,scans=" in lines:
            raise ValueError("plain cache unexpectedly uses PackageCatalog")
    return series,(hits,misses,entries)

def metric(data,tag,index):
    return {k:v[index] for k,v in data[tag].items()}

def main():
    reported={}
    rows=[]
    for mode in MODES:
        control,c0=load(mode,"nochange")
        changed,c1=load(mode,"registry")
        for name,(tag,index) in METRICS.items():
            a,b=metric(control,tag,index),metric(changed,tag,index)
            net=[b[y]-b[x]-(a[y]-a[x]) for x,y in zip(CHECKPOINTS,CHECKPOINTS[1:])]
            first128=sum(net[:2]);last128=sum(net[2:])
            reported[(mode,name)]=(first128,last128)
            print(f"C545D_MTA_256,{mode},{name},net_per64="
                  f"{';'.join(map(str,net))},first128={first128},last128={last128}")
            rows.append((mode,name,*net,first128,last128))
        for scope,data in (("nochange",control),("registry",changed)):
            handles=metric(data,"GIO_PROBE",1)
            delta=handles["settled"]-handles[0]
            if delta>4:raise ValueError(f"{mode}/{scope}: retained handles +{delta}")
            print(f"C545D_MTA_256_HANDLES,{mode},{scope},settled_delta={delta}")
        print(f"C545D_MTA_256_CACHE,{mode},hits={c1[0]},initial_misses={c1[1]},entries={c1[2]}")
    for key in ("private_bytes","heap_busy_bytes","heap_busy_blocks","vm_private_commit"):
        base_first,base_last=reported[("cache_only",key)]
        watch_first,watch_last=reported[("mta_watch",key)]
        print(f"C545D_MTA_256_INCREMENTAL,{key},first128_diff={watch_first-base_first},"
              f"last128_diff={watch_last-base_last}")
    # Deliberately strict even though 256 scans cannot guarantee indefinite use.
    if reported[("mta_watch","heap_busy_bytes")][1] > 524288:
        raise ValueError("Dedicated watcher has >512 KiB live heap growth last128")
    with (ROOT/"mta_watch_256_aggregate.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f)
        w.writerow(("mode","metric","net_0_64","net_64_128",
                    "net_128_192","net_192_256","net_first128","net_last128"))
        w.writerows(rows)
    print("C545D_MTA_WATCH_256_DIAGNOSTIC_PASS;"
          " SYNTHETIC_EVENT_RECEIVE_ONLY; NO_REAL_INSTALLATION;"
          " ZERO_SUSTAINED_LEAK_NOT_CERTIFIED; WINDOWS_2022_CI_ONLY")

if __name__=="__main__":
    try:main()
    except (ValueError,OSError,AssertionError) as ex:
        print(f"C545D_MTA_WATCH_256_INVALID:{ex}",file=sys.stderr)
        sys.exit(2)
