#!/usr/bin/env python3
"""CI-only 16-cycle resource and worker comparison; no allocation ownership claim."""
import argparse
import re
from pathlib import Path
from patch_c545d_gio_active_two_epoch_ci import patch as patch_two

N = 16
PHASES = ("worker_begin","worker_scan_end","worker_unlocked","worker_after_notify")
CLOCK = re.compile(r"C545D_CI_ACTIVE_EPOCH,(baseline|cycle),(\d+),(\d+),(\d+),(\d+)")
RESOURCE = re.compile(r"GIO_PROBE,(baseline|cycle|after_cleanup|settled_cleanup),(\d+),(\d+),(\d+),(\d+)")
WORKER = re.compile(r"C545D_CI_APPINFO_QPC,phase=(\w+),ordinal=(\d+),qpc=(\d+)")
FREQ = re.compile(r"C545D_GIO_16_FREQ,hz=(\d+)")

def need(ok, reason):
    if not ok:
        raise ValueError(reason)

def patch(src):
    s = patch_two(src)
    need(s.count("cycle_count == 2") == 3, "checkpoint_anchor")
    s = s.replace("cycle_count == 2", "cycle_count == 16")
    anchor = "    LARGE_INTEGER qpc;\n    FILETIME created, exited, kernel, user;"
    need(s.count(anchor)==1, "frequency_anchor")
    s = s.replace(anchor, "    LARGE_INTEGER qpc, frequency;\n    FILETIME created, exited, kernel, user;", 1)
    anchor = "    k.LowPart = kernel.dwLowDateTime;"
    need(s.count(anchor)==1, "frequency_emit_anchor")
    s = s.replace(anchor, r'''    if (cycle == 0) {
        if (!QueryPerformanceFrequency(&frequency) || frequency.QuadPart <= 0)
            return 0;
        printf("C545D_GIO_16_FREQ,hz=%lld\n", (long long)frequency.QuadPart);
    }
''' + anchor, 1)
    return s

def parse(raw, arm):
    need(arm in ("registry","nochange") and len(raw)<=1_000_000,"input")
    clocks, resources, workers = {}, {}, {}
    freq = None
    for line in raw.splitlines():
        m = CLOCK.fullmatch(line)
        if m:
            key = (m[1],int(m[2]))
            need(key not in clocks,"duplicate_clock")
            clocks[key] = tuple(map(int,m.groups()[2:]))
        elif line.startswith("C545D_CI_ACTIVE_EPOCH,"):
            raise ValueError("clock_format")
        m = RESOURCE.fullmatch(line)
        if m:
            key = (m[1],int(m[2]))
            need(key not in resources,"duplicate_resource")
            resources[key] = tuple(map(int,m.groups()[2:]))
        elif line.startswith("GIO_PROBE,"):
            raise ValueError("resource_format")
        m = FREQ.fullmatch(line)
        if m:
            need(freq is None and int(m[1])>0,"frequency")
            freq=int(m[1])
        elif line.startswith("C545D_GIO_16_FREQ,"):
            raise ValueError("frequency_format")
        m = WORKER.fullmatch(line)
        if m:
            phase, ordinal, stamp = m[1],int(m[2]),int(m[3])
            need(stamp>0,"worker_clock")
            if phase in ("parser_begin","parser_end","registry_callback"):
                continue
            need(phase in PHASES and ordinal>0,"worker_phase")
            d=workers.setdefault(ordinal,{})
            need(phase not in d,"duplicate_worker")
            d[phase]=stamp
        elif line.startswith("C545D_CI_APPINFO_QPC,"):
            raise ValueError("worker_format")
    keys=[("baseline",0)]+[("cycle",i) for i in range(1,N+1)]
    need(freq is not None and set(clocks)==set(keys),"clock_coverage")
    need(set(resources)==set(keys+[("after_cleanup",N+1),("settled_cleanup",N+2)]),"resource_coverage")
    c=[clocks[k] for k in keys]
    v=[resources[k] for k in keys]
    need(all(x[0]>0 for x in c),"clock_positive")
    for a,b in zip(c,c[1:]):
        need(b[0]>a[0] and b[1]>=a[1] and b[2]>=a[2],"clock_cpu_monotonic")
    need(all(b[0]>=a[0] for a,b in zip(v,v[1:])),"notification_monotonic")
    counts=[0]*N
    for w in workers.values():
        need(set(w)==set(PHASES),"worker_incomplete")
        t=[w[p] for p in PHASES]
        need(t==sorted(t),"worker_order")
        if t[-1]<=c[0][0] or t[0]>c[-1][0]:
            continue
        match=[i for i in range(N) if c[i][0]<t[0]<=t[-1]<=c[i+1][0]]
        need(len(match)==1,"worker_cross_boundary")
        counts[match[0]]+=1
    need(all(n==0 for n in counts) if arm=="nochange" else
         all(n>0 for n in counts),"worker_coverage")
    return freq,c,v,counts,resources

def summarize(data):
    freq,c,v,counts,resources=data
    out=[f"C545D_GIO_16_WORKERS,counts={':'.join(map(str,counts))},hz={freq}"]
    for i,(clock,resource) in enumerate(zip(c,v)):
        q,k,u=clock
        notices,handles,private=resource
        out.append(f"C545D_GIO_16_POINT,cycle={i},private_bytes={private},handles={handles},notifications={notices},qpc={q},cpu100ns={k+u}")
    for phase,index in (("after_cleanup",17),("settled_cleanup",18)):
        notices,handles,private=resources[phase,index]
        out.append(f"C545D_GIO_16_CLEANUP,phase={phase},private_bytes={private},handles={handles},notifications={notices}")
    for a,b in ((0,1),(1,4),(4,8),(8,12),(12,16),(1,16),(0,16)):
        out.append(f"C545D_GIO_16_WINDOW,start={a},end={b},private_delta={v[b][2]-v[a][2]},handles_delta={v[b][1]-v[a][1]},cpu100ns={sum(c[b][1:])-sum(c[a][1:])},qpc_ticks={c[b][0]-c[a][0]}")
    return out

def selftest():
    rows=["C545D_GIO_16_FREQ,hz=1000"]
    for i in range(17):
        phase="cycle" if i else "baseline"
        rows.extend([f"C545D_CI_ACTIVE_EPOCH,{phase},{i},{1000+100*i},{i},{i}",
                     f"GIO_PROBE,{phase},{i},0,20,{10000+4096*min(i,1)}"])
        if i:
            rows.extend(f"C545D_CI_APPINFO_QPC,phase={p},ordinal={i},qpc={900+100*i+j+1}" for j,p in enumerate(PHASES))
    rows += ["GIO_PROBE,after_cleanup,17,0,19,14096","GIO_PROBE,settled_cleanup,18,0,19,10000"]
    raw="\n".join(rows)
    good=parse(raw,"registry")
    need(good[3]==[1]*16,"workers")
    need(any("start=1,end=16,private_delta=0" in l for l in summarize(good)),"plateau")
    need(parse("\n".join(l for l in rows if not l.startswith("C545D_CI_APPINFO_QPC")),"nochange")[3]==[0]*16,"control")
    for bad in (raw.replace(rows[0],""),raw+"\n"+rows[1],raw.replace(rows[-1],""),
                raw.replace("ordinal=1,qpc=1001","ordinal=1,qpc=999"),
                raw.replace("phase=worker_scan_end,ordinal=1,qpc=1002","phase=worker_begin,ordinal=1,qpc=1002"),
                raw.replace("GIO_PROBE,cycle,16,","GIO_PROBE,cycle,15,")):
        try:
            parse(bad,"registry")
        except ValueError:
            continue
        raise AssertionError("negative_accepted")
    print("C545D_GIO_16_SELFTEST_PASS,positive=3,negative=6")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--patch",type=Path)
    ap.add_argument("--input",type=Path)
    ap.add_argument("--arm",choices=("registry","nochange"))
    a=ap.parse_args()
    if a.selftest:
        selftest()
    elif a.patch:
        need(a.patch.name=="c545d_gio_preinit_probe.c","disposable")
        raw=a.patch.read_bytes()
        nl="\r\n" if b"\r\n" in raw else "\n"
        s=patch(raw.decode("utf-8").replace("\r\n","\n"))
        a.patch.write_bytes(s.replace("\n",nl).encode("utf-8"))
        print("C545D_GIO_16_PATCH_PASS,checkpoints=17,CI_only=1")
    elif a.input and a.arm:
        need(a.input.stat().st_size<=1_000_000,"size")
        for line in summarize(parse(a.input.read_text(encoding="utf-8-sig"),a.arm)):
            print(line)
    else:
        ap.error("mode required")

if __name__=="__main__":
    main()
