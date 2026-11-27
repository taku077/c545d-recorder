#!/usr/bin/env python3
"""Sparse HeapWalk snapshots on the existing sixteen-cycle CI-only probe.
Busy bytes are allocator-reported occupied blocks, not leak ownership.
"""
import argparse
import re
from pathlib import Path
from audit_c545d_gio_16_cycle_ci import need, parse, summarize

KEYS=[("baseline",0),("cycle",1),("cycle",8),("cycle",12),("cycle",16),
      ("after_cleanup",17),("settled_cleanup",18)]
HEAP=re.compile(r"GIO_HEAP,(baseline|cycle|after_cleanup|settled_cleanup),(\d+),(\d+),(\d+),(\d+),(\d+)")
SIZE=re.compile(r"GIO_HEAPSIZE,(baseline|cycle|after_cleanup|settled_cleanup),(\d+),(\d+),(\d+)")
ANCHOR="    if (!report_heap_summary) return;\n"

def patch(src):
    need(src.count(ANCHOR)==1,"heap_anchor")
    return src.replace(ANCHOR,ANCHOR+
        '    if (strcmp(label, "cycle") == 0 && cycle != 1 && cycle != 8 && cycle != 12 && cycle != 16) return;\n',1)

def heap_parse(raw):
    need(len(raw)<=1_000_000,"size")
    data,buckets={},{}
    for line in raw.splitlines():
        m=HEAP.fullmatch(line)
        if m:
            key=(m[1],int(m[2]))
            need(key in KEYS and key not in data,"heap_key")
            blocks,bytes_,heaps,bad=map(int,m.groups()[2:])
            need(bad==0 and heaps>0 and blocks>0 and bytes_>0,"heap_incomplete")
            data[key]=(blocks,bytes_,heaps)
        elif line.startswith("GIO_HEAP,"):
            raise ValueError("heap_format")
        m=SIZE.fullmatch(line)
        if m:
            key=(m[1],int(m[2]))
            size,count=int(m[3]),int(m[4])
            need(key in data and 0<=size<=2048 and count>0,"bucket")
            d=buckets.setdefault(key,{})
            need(size not in d,"duplicate_bucket")
            d[size]=count
        elif line.startswith("GIO_HEAPSIZE,"):
            raise ValueError("bucket_format")
    need(list(data)==KEYS and set(buckets)==set(KEYS),"coverage")
    for key,(blocks,bytes_,_) in data.items():
        d=buckets[key]
        need(sum(d.values())==blocks,"block_reconciliation")
        lower=sum(k*v for k,v in d.items())
        need(lower<=bytes_ and (2048 in d or lower==bytes_),"byte_reconciliation")
    return data,buckets

def heap_summary(raw,arm):
    resource=parse(raw,arm)
    data,buckets=heap_parse(raw)
    v=resource[2]
    for key in KEYS:
        phase,i=key
        private=(v[i] if i<=16 else resource[4][key])[2]
        blocks,bytes_,heaps=data[key]
        yield (f"C545D_SPARSE_HEAP_POINT,phase={phase},cycle={i},private_bytes={private},"
               f"busy_bytes={bytes_},busy_blocks={blocks},heaps={heaps},"
               f"bucket190={buckets[key].get(190,0)},bucket194={buckets[key].get(194,0)},"
               f"bucket196={buckets[key].get(196,0)},bucket360={buckets[key].get(360,0)},ownership_proven=0")
    for a,b in ((0,1),(1,8),(8,12),(12,16),(1,16),(0,16),(0,18)):
        ka=next(k for k in KEYS if k[1]==a)
        kb=next(k for k in KEYS if k[1]==b)
        pa=(v[a] if a<=16 else resource[4][ka])[2]
        pb=(v[b] if b<=16 else resource[4][kb])[2]
        yield (f"C545D_SPARSE_HEAP_WINDOW,start={a},end={b},private_delta={pb-pa},"
               f"busy_delta={data[kb][1]-data[ka][1]},blocks_delta={data[kb][0]-data[ka][0]},"
               f"bucket360_delta={buckets[kb].get(360,0)-buckets[ka].get(360,0)},ownership_proven=0")

def selftest():
    raw="\n".join(f"GIO_HEAP,{p},{i},3,2510,1,0\nGIO_HEAPSIZE,{p},{i},100,1\nGIO_HEAPSIZE,{p},{i},360,1\nGIO_HEAPSIZE,{p},{i},2048,1" for p,i in KEYS)
    need(len(heap_parse(raw)[0])==7,"valid")
    for bad in (raw.replace(",3,2510,1,0",",3,2510,1,1",1),
                raw.replace(",3,2510,1,0",",4,2510,1,0",1),
                raw.replace(",3,2510,1,0",",3,2400,1,0",1),
                raw+"\n"+raw.splitlines()[0],"\n".join(raw.splitlines()[:-4])):
        try: heap_parse(bad)
        except ValueError: continue
        raise AssertionError("invalid_heap_accepted")
    print("C545D_SPARSE_HEAP_SELFTEST_PASS,positive=1,negative=5")

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
        print("C545D_SPARSE_HEAP_PATCH_PASS,points=7,CI_only=1")
    elif a.input and a.arm:
        need(a.input.stat().st_size<=1_000_000,"size")
        for line in heap_summary(a.input.read_text(encoding="utf-8-sig"),a.arm): print(line)
    else: p.error("mode required")
if __name__=="__main__": main()
