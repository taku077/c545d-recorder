#!/usr/bin/env python3
"""512-cycle original-value cache stability analysis on Windows CI.

Two-mode same-run control: unchanged registry and synthetic HKCU change.
Report last 64/128/256 control-subtracted PrivateUsage, live HeapWalk BUSY,
BUSY blocks, VirtualQuery private commit and settled handle counts.
A single flat 64-cycle window does not imply indefinite leak-free recording.
"""
from pathlib import Path
import csv
import re
import sys

ROOT=Path("artifacts")
CHECKPOINTS=tuple(range(0,513,64))
METRICS={
    "private_bytes":("GIO_PROBE",2),
    "busy_bytes":("GIO_HEAP",1),
    "busy_blocks":("GIO_HEAP",0),
    "vm_private_commit":("GIO_VM",0),
    "heap_region_committed":("GIO_HEAPREGION",2),
    "heap_region_free_bytes":("GIO_HEAPREGION",4),
}

def load(path):
    data={k:{} for k in ("GIO_PROBE","GIO_HEAP","GIO_VM","GIO_HEAPREGION")}
    text=path.read_text(encoding="utf-8")
    if text.count("GIO_PROBE_DONE,cycles=512,")!=1:
        raise ValueError("missing completion marker: "+str(path))
    count=0
    for line in text.splitlines():
        v=line.strip().split(",")
        if not v or v[0] not in data:continue
        tag=v[0]
        if len(v)!={"GIO_PROBE":6,"GIO_HEAP":7,"GIO_VM":8,"GIO_HEAPREGION":10}[tag]:
            raise ValueError(f"{path}: malformed {tag}")
        if v[1]=="cycle":count+=tag=="GIO_PROBE"
        if v[1] not in ("cycle","baseline","settled_cleanup"):continue
        i=514 if v[1]=="settled_cleanup" else int(v[2])
        if i not in CHECKPOINTS and i!=514:continue
        if i in data[tag]:raise ValueError(f"duplicate {tag} index={i}")
        if any(not x.isdecimal() for x in v[3:]):
            raise ValueError("nonnumeric counters")
        data[tag][i]=list(map(int,v[3:]))
    if count!=512:raise ValueError(f"expected 512 reports, found {count}")
    for tag in data:
        if set(data[tag])!=set((*CHECKPOINTS,514)):
            raise ValueError(f"{path}: missing {tag} checkpoints")
        if tag in ("GIO_HEAP","GIO_VM","GIO_HEAPREGION") and any(z[-1]!=0 for z in data[tag].values()):
            raise ValueError(f"{path}: invalid {tag} snapshot")
    return data,text

def metric(data,tag,index):
    return {i:z[index] for i,z in data[tag].items()}

def main():
    control,_=load(ROOT/"cache_nochange_512.log")
    changed,log=load(ROOT/"cache_registry_512.log")
    cache=re.findall(
        r"^C545D_DISPLAY_CACHE,hits=(\d+),misses=(\d+),entries=(\d+)$",
        log,re.M)
    if not cache:raise ValueError("missing exact-string cache telemetry")
    hits,misses,entries=map(int,cache[-1])
    if hits<4096 or misses!=entries or not 0<entries<=1024:
        raise ValueError("cache not bounded or repeated DisplayName getter misses")
    for scope,data in (("nochange",control),("registry",changed)):
        h=metric(data,"GIO_PROBE",1)
        if h[514]-h[0]>4:
            raise ValueError(f"{scope}: positive retained handles")
        print(f"C545D_CACHE512_HANDLES,{scope},settled_delta={h[514]-h[0]}")
        regions=metric(data,"GIO_HEAPREGION",0)
        known=metric(data,"GIO_HEAPREGION",1)
        if any(known[k]>regions[k] for k in regions):
            raise ValueError(f"{scope}: invalid heap region coverage counts")
        # The Windows API explicitly allows dwCommittedSize=0 (not available).
        # Report coverage and refrain from interpreting incomplete totals.
        complete=sum(1 for k in CHECKPOINTS if regions[k]>0 and regions[k]==known[k])
        print(f"C545D_CACHE512_REGION_COVERAGE,{scope},complete_checkpoints={complete}/9,"
              f"baseline_regions={regions[0]},baseline_known={known[0]}")
    rows=[]
    growth={}
    for name,(tag,index) in METRICS.items():
        a=metric(control,tag,index);b=metric(changed,tag,index)
        windows=[b[y]-b[x] - (a[y]-a[x]) for x,y in zip(CHECKPOINTS,CHECKPOINTS[1:])]
        first256=sum(windows[:4])
        last256=sum(windows[4:])
        last128=sum(windows[6:])
        last64=windows[7]
        growth[name]=(first256,last256,last128,last64)
        print(f"C545D_CACHE512_RESIDUAL,{name},per64={';'.join(map(str,windows))},"
              f"first256={first256},last256={last256},last128={last128},last64={last64}")
        rows.append((name,*windows,first256,last256,last128,last64))
    with (ROOT/"cache_512_aggregate.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f)
        w.writerow(("metric",*[f"net_{x}_{y}" for x,y in zip(CHECKPOINTS,CHECKPOINTS[1:])],
                    "first256","last256","last128","last64"))
        w.writerows(rows)
    private=growth["private_bytes"]
    busy=growth["busy_bytes"]
    label=("SHORT_WINDOW_PLATEAU_CANDIDATE"
           if abs(private[1])<=262144 and abs(busy[1])<=262144
           else "RESIDUAL_GROWTH_REQUIRES_INVESTIGATION")
    print("C545D_CACHE512_REGION_DISPOSITION;"
          f"last256_private_bytes={private[1]};"
          f"last256_busy_bytes={busy[1]};"
          f"last256_heap_region_committed={growth['heap_region_committed'][1]};"
          f"last256_heap_region_free_bytes={growth['heap_region_free_bytes'][1]};"
          "heap_region_committed_is_partial_if_coverage_incomplete=true;"
          "no_allocation_lifetime_or_leak_causality_claim=true")
    print(f"C545D_CACHE512_CLASSIFICATION={label};"
          f"last256_private={private[1]};last256_busy={busy[1]};"
          f"hits={hits};initial_misses={misses};entries={entries}")
    print("C545D_CACHE512_COMPLETED; SAME_RUN_MATCHED_CONTROL;"
          " NOT_ZERO_LEAK_PROOF; WINDOWS_2022_ONLY; NO_RECORDER_HOST_TEST")

if __name__=="__main__":
    try:main()
    except (ValueError,OSError) as e:
        print(f"C545D_CACHE512_INVALID:{e}",file=sys.stderr)
        sys.exit(2)
