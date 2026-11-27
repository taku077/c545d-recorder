#!/usr/bin/env python3
"""CI-only committed-memory classification; overlapping views, not a partition."""
import argparse
import re
from pathlib import Path
from audit_c545d_gio_sparse_heap_ci import KEYS, heap_parse, need
from audit_c545d_gio_16_cycle_ci import parse

VM=re.compile(r"GIO_VM,(baseline|cycle|after_cleanup|settled_cleanup),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)")
HS=re.compile(r"C545D_HEAP_COMMIT_RAW,(baseline|cycle|after_cleanup|settled_cleanup),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)")
ALL=[("baseline",0)]+[("cycle",i) for i in range(1,17)]+[("after_cleanup",17),("settled_cleanup",18)]

def patch(s):
    def once(a,b):
        nonlocal s
        need(s.count(a)==1,"source_anchor")
        s=s.replace(a,b,1)
    once("static void report_heaps(const char *label, int cycle)",r"""/* Local ABI equivalent of HEAP_SUMMARY, dynamic lookup avoids a mandatory
 * HeapSummary import. This disposable probe is not shipped to the host. */
typedef struct {
    DWORD cb;
    SIZE_T allocated, committed, reserved, max_reserve;
} C545DHeapSummary;
typedef BOOL (WINAPI *C545DHeapSummaryFn)(HANDLE,DWORD,C545DHeapSummary *);
static void report_heaps(const char *label, int cycle)""")
    once("    DWORD n, found, i, bad = 0;",r"""    DWORD n, found, i, bad = 0;
    unsigned long long allocated=0, committed=0, reserved=0;
    DWORD summary_ok=0, summary_bad=0;
    HMODULE kernel=GetModuleHandleW(L"kernel32.dll");
    C545DHeapSummaryFn summary=kernel ? (C545DHeapSummaryFn)GetProcAddress(kernel,"HeapSummary") : NULL;""")
    once("        memset(&entry, 0, sizeof(entry));",r"""        C545DHeapSummary h;
        memset(&h,0,sizeof(h));
        h.cb=sizeof(h);
        if (summary && summary(heaps[i],0,&h)) {
            allocated+=h.allocated; committed+=h.committed; reserved+=h.reserved;
            summary_ok++;
        } else summary_bad++;
        memset(&entry, 0, sizeof(entry));""")
    once("    free(heaps);\n    printf(\"GIO_HEAP,",r"""    free(heaps);
    printf("C545D_HEAP_COMMIT_RAW,%s,%d,%llu,%llu,%llu,%lu,%lu,%lu\n",
           label,cycle,allocated,committed,reserved,(unsigned long)found,
           (unsigned long)summary_ok,(unsigned long)summary_bad);
    printf("GIO_HEAP,""")
    return s

def collect(raw):
    need(len(raw)<=1_000_000,"size")
    vm,hs={},{}
    for line in raw.splitlines():
        for regex,prefix,d,keys in ((VM,"GIO_VM,",vm,ALL),(HS,"C545D_HEAP_COMMIT_RAW,",hs,KEYS)):
            if not line.startswith(prefix): continue
            m=regex.fullmatch(line)
            need(m is not None,"format")
            k=(m[1],int(m[2]))
            need(k in keys and k not in d,"key")
            d[k]=tuple(map(int,m.groups()[2:]))
    need(list(vm)==ALL and list(hs)==KEYS,"coverage")
    need(all(v[3]>0 and v[4]==0 for v in vm.values()),"vm_error")
    need(all(h[3]>0 and h[4]==h[3] and h[5]==0 and h[0]<=h[1]<=h[2] for h in hs.values()),"heap_summary_coverage")
    return vm,hs

def summary(raw,arm):
    vm,hs=collect(raw)
    heap,_=heap_parse(raw)
    data=parse(raw,arm)
    points={}
    for k in KEYS:
        phase,i=k
        need(hs[k][3]==heap[k][2],"heap_count_mismatch")
        private=data[4][k][2]
        v=(private,*vm[k][:3],*hs[k][:3],heap[k][1])
        points[i]=v
        yield f"C545D_COMMIT_POINT,cycle={i},"+",".join(f"{n}={x}" for n,x in zip(NAMES,v))
    for a,b in ((0,1),(1,8),(8,12),(12,16),(1,16),(0,16),(0,18)):
        yield f"C545D_COMMIT_WINDOW,start={a},end={b},"+",".join(f"{n}_delta={y-x}" for n,x,y in zip(NAMES,points[a],points[b]))
    yield "C545D_COMMIT_COVERAGE,vm_points=19,heap_points=7,all_enumerated_heaps=1,atomic_snapshot=0,ownership_proven=0"

NAMES=("private","vm_private","vm_mapped","vm_image","heap_allocated","heap_committed","heap_reserved","heap_busy")
def selftest():
    raw="\n".join([f"GIO_VM,{p},{i},4096,8192,12288,10,0" for p,i in ALL]+[f"C545D_HEAP_COMMIT_RAW,{p},{i},100,200,300,4,4,0" for p,i in KEYS])
    need(len(collect(raw)[0])==19,"valid")
    for bad in (raw.replace(",10,0",",10,1",1),raw.replace(",4,4,0",",4,3,1",1),
                raw.replace(",100,200,300",",400,200,300",1),raw+"\n"+raw.splitlines()[0],
                "\n".join(raw.splitlines()[:-1])):
        try: collect(bad)
        except ValueError: continue
        raise AssertionError("invalid_accepted")
    print("C545D_COMMIT_SELFTEST_PASS,positive=1,negative=5")
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--patch",type=Path)
    ap.add_argument("--input",type=Path)
    ap.add_argument("--arm",choices=("registry","nochange"))
    a=ap.parse_args()
    if a.selftest: selftest()
    elif a.patch:
        need(a.patch.name=="c545d_gio_preinit_probe.c","disposable")
        raw=a.patch.read_bytes()
        nl="\r\n" if b"\r\n" in raw else "\n"
        a.patch.write_bytes(patch(raw.decode("utf-8").replace("\r\n","\n")).replace("\n",nl).encode("utf-8"))
        print("C545D_COMMIT_PATCH_PASS,optional_dynamic_api=1")
    elif a.input and a.arm:
        need(a.input.stat().st_size<=1_000_000,"size")
        for line in summary(a.input.read_text(encoding="utf-8-sig"),a.arm): print(line)
    else: ap.error("mode required")
if __name__=="__main__": main()
