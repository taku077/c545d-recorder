#!/usr/bin/env python3
"""Independent audit of sanitized 16-cycle CI output; no native replay."""
import argparse
import re
from pathlib import Path
from audit_c545d_gio_16_cycle_ci import need

KEYS=[(m,a) for m in ("uncached","event-cache") for a in ("nochange","registry")]
WINDOWS=((0,1),(1,4),(4,8),(8,12),(12,16),(1,16),(0,16))
PREFIX="C545D_GIO_16_"
BEGIN=re.compile(PREFIX+r"BEGIN,mode=(uncached|event-cache),arm=(nochange|registry),etw=0,external_handle_census=0,heapwalk=0")
END=re.compile(PREFIX+r"ARM_PASS,mode=(uncached|event-cache),arm=(nochange|registry),elapsed_ms=(\d+),etw=0,lineage_proven=0")
WORK=re.compile(PREFIX+r"WORKERS,counts=(\d+(?::\d+){15}),hz=(\d+)")
POINT=re.compile(PREFIX+r"POINT,cycle=(\d+),private_bytes=(\d+),handles=(\d+),notifications=(\d+),qpc=(\d+),cpu100ns=(\d+)")
CLEAN=re.compile(PREFIX+r"CLEANUP,phase=(after_cleanup|settled_cleanup),private_bytes=(\d+),handles=(\d+),notifications=(\d+)")
WIN=re.compile(PREFIX+r"WINDOW,start=(\d+),end=(\d+),private_delta=(-?\d+),handles_delta=(-?\d+),cpu100ns=(\d+),qpc_ticks=(\d+)")
CACHE=re.compile(r"C545D_DISPLAY_CACHE,hits=(\d+),misses=(\d+),entries=(\d+)")
BRIDGE=re.compile(r"C545D_WINRT_BRIDGE,scans=(\d+),injections=(\d+),evictions=(\d+),errors=(\d+),ready=([01])")
DONE=PREFIX+"COMPARE_PASS,arms=4,cycles=16,cross_mode_worker_parity=1,etw=0,lineage_proven=0,release_HOLD=1"

def parse(raw):
    need(len(raw)<=16_000_000,"size")
    data={}
    active=None
    done=False
    for rawline in raw.splitlines():
        line=re.sub(r"^(?:.*?\t)?\d{4}-\d\d-\d\dT\S+Z\s+","",rawline).strip()
        m=BEGIN.fullmatch(line)
        if m:
            need(not done and active is None and len(data)<4 and m.groups()==KEYS[len(data)],"begin")
            active=m.groups()
            data[active]={"points":{},"clean":{},"windows":{}}
            continue
        m=END.fullmatch(line)
        if m:
            need(active==m.groups()[:2] and int(m[3])>0,"end")
            data[active]["elapsed"]=int(m[3])
            active=None
            continue
        if line==DONE:
            need(not done and active is None and list(data)==KEYS,"done")
            done=True
            continue
        if not line.startswith((PREFIX+"WORKERS,",PREFIX+"POINT,",PREFIX+"CLEANUP,",PREFIX+"WINDOW,","C545D_DISPLAY_CACHE,","C545D_WINRT_BRIDGE,")):
            if line.startswith((PREFIX+"BEGIN,",PREFIX+"ARM_",PREFIX+"COMPARE_PASS,",PREFIX+"TIMEOUT,")):
                raise ValueError("invalid_or_failed_arm")
            continue
        need(active is not None and not done,"record_scope")
        d=data[active]
        m=POINT.fullmatch(line)
        if m:
            key=int(m[1])
            need(key==len(d["points"]) and key<=16,"point_order")
            d["points"][key]=tuple(map(int,m.groups()[1:]))
            continue
        m=CLEAN.fullmatch(line)
        if m:
            need(m[1] not in d["clean"],"cleanup_duplicate")
            d["clean"][m[1]]=tuple(map(int,m.groups()[1:]))
            continue
        m=WIN.fullmatch(line)
        if m:
            key=tuple(map(int,m.groups()[:2]))
            need(key in WINDOWS and key not in d["windows"],"window_key")
            d["windows"][key]=tuple(map(int,m.groups()[2:]))
            continue
        m=WORK.fullmatch(line)
        if m:
            name="workers"
            value=(tuple(map(int,m[1].split(":"))),int(m[2]))
        else:
            m=CACHE.fullmatch(line)
            if m:
                name="cache"
            else:
                m=BRIDGE.fullmatch(line)
                need(m is not None,"record_format")
                name="bridge"
            value=tuple(map(int,m.groups()))
        need(name not in d,"duplicate_record")
        d[name]=value
    need(done,"incomplete")
    for (mode,arm),d in data.items():
        p=d["points"]
        need(set(p)==set(range(17)) and set(d["clean"])=={"after_cleanup","settled_cleanup"} and set(d["windows"])==set(WINDOWS) and "workers" in d,"coverage")
        counts,hz=d["workers"]
        need(hz>0 and (all(n==0 for n in counts) if arm=="nochange" else all(n>0 for n in counts)),"worker")
        need(all(p[i][3]>p[i-1][3] and p[i][4]>=p[i-1][4] and p[i][2]>=p[i-1][2] for i in range(1,17)),"counter_order")
        for a,b in WINDOWS:
            need(d["windows"][a,b]==tuple(p[b][i]-p[a][i] for i in (0,1,4,3)),"window_mismatch")
        if mode=="uncached":
            need("cache" not in d and "bridge" not in d,"unexpected_cache")
        else:
            need("cache" in d and "bridge" in d,"missing_cache")
            h,m,n=d["cache"]
            scans,inject,evict,errors,ready=d["bridge"]
            need(m>0 and 0<n<=1024 and (arm!="registry" or h>0),"cache_activity")
            need(scans>0 and inject==evict==errors==0 and ready==1,"bridge")
    need(len({d["workers"][1] for d in data.values()})==1,"frequency_parity")
    need(data["uncached","registry"]["workers"][0]==data["event-cache","registry"]["workers"][0],"worker_parity")
    return data

def summarize(data):
    out=[]
    def emit(metric,v):
        u0,u1,c0,c1=v
        out.append(f"C545D_16_MATCHED,metric={metric},uncached_nochange={u0},uncached_registry={u1},cached_nochange={c0},cached_registry={c1},registry_difference={c1-u1},control_adjusted_difference={(c1-c0)-(u1-u0)},descriptive_only=1")
    for a,b in WINDOWS:
        for i,name in enumerate(("private_bytes","handles","cpu100ns","qpc_ticks")):
            emit(f"window_{a}_{b}_{name}",[data[k]["windows"][a,b][i] for k in KEYS])
    for i,name in ((0,"private_bytes"),(1,"handles")):
        emit("baseline_"+name,[data[k]["points"][0][i] for k in KEYS])
        emit("settled_"+name,[data[k]["clean"]["settled_cleanup"][i] for k in KEYS])
        emit("settled_delta_"+name,[data[k]["clean"]["settled_cleanup"][i]-data[k]["points"][0][i] for k in KEYS])
        emit("late_peak_to_trough_"+name,[max(data[k]["points"][j][i] for j in range(8,17))-min(data[k]["points"][j][i] for j in range(8,17)) for k in KEYS])
    return out

def fixture():
    rows=[]
    for mode,arm in KEYS:
        reg=int(arm=="registry")
        rows.append(f"{PREFIX}BEGIN,mode={mode},arm={arm},etw=0,external_handle_census=0,heapwalk=0")
        if mode=="event-cache":
            rows+=["C545D_DISPLAY_CACHE,hits=96,misses=32,entries=32","C545D_WINRT_BRIDGE,scans=4,injections=0,evictions=0,errors=0,ready=1"]
        counts=":".join([str(reg)]*16)
        rows.append(f"{PREFIX}WORKERS,counts={counts},hz=1000")
        for i in range(17):
            rows.append(f"{PREFIX}POINT,cycle={i},private_bytes={4096+reg*i},handles=20,notifications=0,qpc={100+i*100},cpu100ns={i*10}")
        for phase in ("after_cleanup","settled_cleanup"):
            rows.append(f"{PREFIX}CLEANUP,phase={phase},private_bytes=4096,handles=19,notifications=0")
        for a,b in WINDOWS:
            rows.append(f"{PREFIX}WINDOW,start={a},end={b},private_delta={reg*(b-a)},handles_delta=0,cpu100ns={(b-a)*10},qpc_ticks={(b-a)*100}")
        rows.append(f"{PREFIX}ARM_PASS,mode={mode},arm={arm},elapsed_ms=24000,etw=0,lineage_proven=0")
    rows.append(DONE)
    return "\n".join(rows)

def selftest():
    raw=fixture()
    need(len(summarize(parse(raw)))==36,"metrics")
    for bad in (raw.replace(DONE,""),raw+"\n"+DONE,raw.replace("cycle=16,","cycle=15,",1),
                raw.replace("private_delta=0,","private_delta=1,",1),
                raw.replace("hz=1000","hz=2000",1),raw.replace("entries=32","entries=1025",1),
                raw.replace("qpc=200,","qpc=99,",1)):
        try:
            parse(bad)
        except ValueError:
            continue
        raise AssertionError("negative_accepted")
    print("C545D_16_MATCHED_SELFTEST_PASS,positive=1,negative=7,actual_qualified=0")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--input",type=Path)
    a=ap.parse_args()
    if a.selftest:
        selftest()
    elif a.input:
        need(a.input.stat().st_size<=16_000_000,"size")
        for line in summarize(parse(a.input.read_text(encoding="utf-8-sig"))):
            print(line)
        print("C545D_16_MATCHED_PASS,arms=4,metrics=36,long_run_proven=0,lineage_proven=0")
    else:
        ap.error("mode required")
if __name__=="__main__":
    main()
