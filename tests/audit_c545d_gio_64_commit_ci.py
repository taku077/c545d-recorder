#!/usr/bin/env python3
"""64-cycle disposable commit trend probe, no HeapWalk or ownership claim."""
import argparse
import re
from pathlib import Path
from audit_c545d_gio_16_cycle_ci import patch as patch16, need, PHASES, CLOCK, RESOURCE, WORKER, FREQ
N=64
KEYS=[("baseline",0)]+[("cycle",i) for i in (1,16,32,48,64)]+[("after_cleanup",65),("settled_cleanup",66)]
VM=re.compile(r"GIO_VM,(baseline|cycle|after_cleanup|settled_cleanup),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)")
HEAP=re.compile(r"C545D_64_HEAP,(baseline|cycle|after_cleanup|settled_cleanup),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)")
REPLACEMENT=r"""typedef struct {
    DWORD cb;
    SIZE_T allocated, committed, reserved, max_reserve;
} C545DHeapSummary;
typedef BOOL (WINAPI *C545DHeapSummaryFn)(HANDLE,DWORD,C545DHeapSummary *);
static void report_heaps(const char *label, int cycle)
{
    HANDLE heaps[4096], primary=GetProcessHeap();
    DWORD n, found, i, primary_count=0, errors=0;
    unsigned long long a[2]={0,0}, c[2]={0,0}, r[2]={0,0};
    HMODULE kernel=GetModuleHandleW(L"kernel32.dll");
    C545DHeapSummaryFn summary=kernel ? (C545DHeapSummaryFn)GetProcAddress(kernel,"HeapSummary") : NULL;
    if (!report_heap_summary) return;
    if (strcmp(label,"cycle")==0 && cycle!=1 && cycle!=16 && cycle!=32 && cycle!=48 && cycle!=64) return;
    n=GetProcessHeaps(0,NULL);
    if (!summary || !primary || n==0 || n>4096) exit(21);
    found=GetProcessHeaps(n,heaps);
    if (found!=n) exit(22);
    for(i=0;i<found;i++){
        C545DHeapSummary h;
        int group=heaps[i]==primary ? 0 : 1;
        DWORD j;
        for(j=0;j<i;j++) if(heaps[j]==heaps[i]) exit(23);
        if(group==0) primary_count++;
        memset(&h,0,sizeof(h)); h.cb=sizeof(h);
        if(!summary(heaps[i],0,&h) || h.allocated>h.committed || h.committed>h.reserved){errors++;continue;}
        a[group]+=h.allocated; c[group]+=h.committed; r[group]+=h.reserved;
    }
    if(GetProcessHeaps(0,NULL)!=n || primary_count!=1) errors++;
    printf("C545D_64_HEAP,%s,%d,%llu,%llu,%llu,%llu,%llu,%llu,%lu,%lu\n",
        label,cycle,a[0],c[0],r[0],a[1],c[1],r[1],(unsigned long)found,(unsigned long)errors);
    fflush(stdout);
    if(errors) exit(24);
}
"""
def patch(src):
    s=patch16(src)
    need(s.count("cycle_count == 16")==3,"checkpoint_anchor")
    s=s.replace("cycle_count == 16","cycle_count == 64")
    a="static void report_heaps(const char *label, int cycle)"
    b="static void report_types(const char *label, int cycle)"
    need(s.count(a)==1 and s.count(b)==1 and s.index(a)<s.index(b),"heap_anchor")
    return s[:s.index(a)]+REPLACEMENT+"\n"+s[s.index(b):]

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

def collect(raw):
    heap,vm={},{}
    for line in raw.splitlines():
        for regex,prefix,d in ((HEAP,"C545D_64_HEAP,",heap),(VM,"GIO_VM,",vm)):
            if not line.startswith(prefix): continue
            m=regex.fullmatch(line)
            need(m is not None,"format")
            k=(m[1],int(m[2]))
            need(k not in d,"duplicate")
            d[k]=tuple(map(int,m.groups()[2:]))
    need(list(heap)==KEYS,"heap_coverage")
    need(list(vm)==[("baseline",0)]+[("cycle",i) for i in range(1,65)]+KEYS[-2:],"vm_coverage")
    need(all(x[6]>0 and x[7]==0 and x[0]<=x[1]<=x[2] and x[3]<=x[4]<=x[5] for x in heap.values()),"heap_valid")
    need(all(x[3]>0 and x[4]==0 for x in vm.values()),"vm_valid")
    return heap,vm

NAMES=("private","handles","default_allocated","default_committed","default_reserved","other_allocated","other_committed","other_reserved","heap_count","vm_private","vm_mapped","vm_image")
WINDOWS=((0,1),(1,16),(16,32),(32,48),(48,64),(1,64),(0,64),(0,66))
def summarize(raw,arm):
    freq,c,v,counts,res=parse(raw,arm)
    heap,vm=collect(raw)
    points={}
    yield f"C545D_64_WORKERS,counts={':'.join(map(str,counts))},hz={freq}"
    for i,(clock,resource) in enumerate(zip(c,v)):
        yield f"C545D_64_RESOURCE,cycle={i},private={resource[2]},handles={resource[1]},qpc={clock[0]},cpu100ns={sum(clock[1:])}"
    for k in KEYS:
        i=k[1]
        points[i]=(res[k][2],res[k][1],*heap[k][:7],*vm[k][:3])
        yield f"C545D_64_POINT,cycle={i},"+",".join(f"{n}={x}" for n,x in zip(NAMES,points[i]))
    for a,b in WINDOWS:
        yield f"C545D_64_WINDOW,start={a},end={b},"+",".join(f"{n}_delta={y-x}" for n,x,y in zip(NAMES,points[a],points[b]))
    yield "C545D_64_COVERAGE,resource_points=65,vm_points=67,heap_points=8,heapwalk=0,ownership_proven=0,atomic_snapshot=0"

def fixture():
    rows=["C545D_GIO_16_FREQ,hz=1000"]
    for i in range(65):
        p="cycle" if i else "baseline"
        rows += [f"C545D_CI_ACTIVE_EPOCH,{p},{i},{1000+i*100},{i},{i}",f"GIO_PROBE,{p},{i},0,20,4096",f"GIO_VM,{p},{i},4096,8192,12288,10,0"]
        if i:
            rows += [f"C545D_CI_APPINFO_QPC,phase={p},ordinal={i},qpc={900+100*i+j+1}" for j,p in enumerate(PHASES)]
    for p,i in KEYS[-2:]:
        rows += [f"GIO_PROBE,{p},{i},0,20,4096",f"GIO_VM,{p},{i},4096,8192,12288,10,0"]
    rows += [f"C545D_64_HEAP,{p},{i},100,200,300,50,100,200,2,0" for p,i in KEYS]
    return "\n".join(rows)

def selftest():
    raw=fixture()
    need(len(list(summarize(raw,"registry")))==83,"rows")
    need(parse(raw,"registry")[3]==[1]*64,"workers")
    for bad in (raw.replace("cycle,64,","cycle,63,",1),raw.replace(",2,0\n",",2,1\n",1),
                raw.replace(",100,200,300,",",400,200,300,",1),raw.replace(",10,0\n",",10,1\n",1),
                "\n".join(raw.splitlines()[:-1])):
        try: list(summarize(bad,"registry"))
        except ValueError: continue
        raise AssertionError("invalid_accepted")
    print("C545D_64_SELFTEST_PASS,positive=2,negative=5")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--patch",type=Path)
    p.add_argument("--input",type=Path)
    p.add_argument("--arm",choices=("registry","nochange"))
    a=p.parse_args()
    if a.selftest: selftest()
    elif a.patch:
        need(a.patch.name=="c545d_gio_preinit_probe.c","disposable")
        raw=a.patch.read_bytes()
        nl="\r\n" if b"\r\n" in raw else "\n"
        a.patch.write_bytes(patch(raw.decode("utf-8").replace("\r\n","\n")).replace("\n",nl).encode("utf-8"))
        print("C545D_64_PATCH_PASS,checkpoints=65,heapwalk=0")
    elif a.input and a.arm:
        need(a.input.stat().st_size<=1_000_000,"size")
        for line in summarize(a.input.read_text(encoding="utf-8-sig"),a.arm): print(line)
    else: p.error("mode required")
if __name__=="__main__": main()
