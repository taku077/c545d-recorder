#!/usr/bin/env python3
"""Offline audit of already qualified 256-cycle numeric CI summaries.
No raw heap events, memory addresses, package identities, or host access.
Block medians and commit-minus-allocated are descriptive, not ownership.
"""
import argparse
import re
from pathlib import Path
from statistics import median

STAMP = re.compile(r"^(?:[^\r\n]*?\t)?\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z ")
BEGIN = re.compile(r"C545D_(256|STACK)_BEGIN,mode=([a-z-]+),arm=(nochange|registry),etw=0,external_handle_census=0,heapwalk=0,heapsummary=1")
PASS = re.compile(r"C545D_(256|STACK)_ARM_PASS,mode=([a-z-]+),arm=(nochange|registry),elapsed_ms=\d+,etw=0,lineage_proven=0")
RESOURCE = re.compile(r"C545D_256_RESOURCE,cycle=(\d+),private=(\d+),handles=(\d+),qpc=(\d+),cpu100ns=(\d+)")
POINT = re.compile(r"C545D_256_POINT,cycle=(\d+),private=(\d+),handles=(\d+),default_allocated=(\d+),default_committed=(\d+),default_reserved=(\d+),other_allocated=(\d+),other_committed=(\d+),other_reserved=(\d+),heap_count=(\d+),vm_private=(\d+),vm_mapped=(\d+),vm_image=(\d+)")
CHECKPOINTS = [0, 1, 16, 32, 64, 128, 192, 224, 256, 257, 258]
MODES = {"256": ("uncached", "event-cache"), "STACK": ("heap-key", "stack-key")}
FINAL = {
    "256": "C545D_256_COMPARE_PASS,arms=4,cycles=256,cross_mode_worker_parity=1,etw=0,lineage_proven=0,release_HOLD=1",
    "STACK": "C545D_STACK_COMPARE_PASS,arms=4,cycles=256,same_dll=1,cross_mode_worker_parity=1,cache_bridge_parity=1,etw=0,lineage_proven=0,release_HOLD=1",
}
def need(ok, reason):
    if not ok:
        raise ValueError(reason)

def parse(raw, kind):
    need(kind in MODES, "kind")
    arms, current, done, final = {}, None, set(), 0
    expected = {(m,a) for m in MODES[kind] for a in ("nochange","registry")}
    for line in raw.splitlines():
        stamp = STAMP.match(line)
        if not stamp:
            continue
        row = line[stamp.end():]
        m = BEGIN.fullmatch(row)
        if m:
            key = (m[2], m[3])
            need(m[1] == kind and current is None and key in expected and key not in arms and not final,"begin")
            current = key
            arms[key] = ([], [])
            continue
        m = PASS.fullmatch(row)
        if m:
            need(m[1] == kind and current == (m[2],m[3]),"arm_pass")
            done.add(current)
            current = None
            continue
        if row == FINAL[kind]:
            need(current is None and done == expected and not final,"compare_pass")
            final += 1
            continue
        if row.startswith(("C545D_256_RESOURCE,","C545D_256_POINT,")):
            need(current is not None,"unscoped_row")
            regex, index = (RESOURCE,0) if row.startswith("C545D_256_RESOURCE,") else (POINT,1)
            m = regex.fullmatch(row)
            need(m is not None,"row_format")
            arms[current][index].append(tuple(map(int,m.groups())))
    need(final == 1 and set(arms) == done == expected,"completion")
    for resources, points in arms.values():
        need([x[0] for x in resources] == list(range(257)),"resource_coverage")
        need([x[0] for x in points] == CHECKPOINTS,"heap_coverage")
        need(all(b[3]>a[3] and b[4]>=a[4] for a,b in zip(resources,resources[1:])),"clock_order")
        for p in points:
            need(p[3]<=p[4]<=p[5] and p[6]<=p[7]<=p[8] and p[9]>0,"heap_order")
            if p[0]<=256:
                need(p[1:3]==resources[p[0]][1:3],"point_resource_mismatch")
    return arms

def report(arms, kind):
    for mode in MODES[kind]:
        nr,np = arms[(mode,"nochange")]
        rr,rp = arms[(mode,"registry")]
        base_raw = median(x[1] for x in rr[1:33])
        base_ctrl = median(x[1] for x in nr[1:33])
        for lo in range(1,257,32):
            x = [p[1] for p in rr[lo:lo+32]]
            y = [p[1] for p in nr[lo:lo+32]]
            raw = median(x)-base_raw
            adj = raw-(median(y)-base_ctrl)
            yield f"C545D_BLOCK_TREND,mode={mode},start={lo},end={lo+31},raw_median_delta={raw:.1f},adjusted_median_delta={adj:.1f},raw_range={max(x)-min(x)}"
        def gap(p): return p[4]+p[7]-p[3]-p[6]
        raw_gap = gap(rp[-3])-gap(rp[1])
        ctl_gap = gap(np[-3])-gap(np[1])
        yield f"C545D_COMMIT_ALLOC_GAP,mode={mode},start=1,end=256,raw_delta={raw_gap},control_delta={ctl_gap},adjusted_delta={raw_gap-ctl_gap},ownership_proven=0"
    yield "C545D_BLOCK_TREND_PASS,arms=4,resources_per_arm=257,heap_points_per_arm=11,blocks_per_mode=8,ownership_proven=0"

def fixture():
    t = "2026-01-01T00:00:00Z "
    rows = []
    for m in MODES["256"]:
        for a in ("nochange","registry"):
            rows.append(t+f"C545D_256_BEGIN,mode={m},arm={a},etw=0,external_handle_census=0,heapwalk=0,heapsummary=1")
            for i in range(257):
                rows.append(t+f"C545D_256_RESOURCE,cycle={i},private={10000+i},handles=1,qpc={i+1},cpu100ns={i}")
            for i in CHECKPOINTS:
                rows.append(t+f"C545D_256_POINT,cycle={i},private={10000+i},handles=1,default_allocated=100,default_committed={200+i},default_reserved=1000,other_allocated=10,other_committed=20,other_reserved=30,heap_count=2,vm_private=1000,vm_mapped=0,vm_image=0")
            rows.append(t+f"C545D_256_ARM_PASS,mode={m},arm={a},elapsed_ms=1,etw=0,lineage_proven=0")
    rows.append(t+FINAL["256"])
    return "\n".join(rows)

def selftest():
    raw=fixture()
    good=list(report(parse(raw,"256"),"256"))
    need(len(good)==19 and "raw_median_delta=224.0,adjusted_median_delta=0.0" in good[7] and "raw_delta=255,control_delta=255,adjusted_delta=0" in good[8],"positive")
    for bad in (raw.replace("cycle=256,private=10256","cycle=255,private=10256",1),
                raw.replace("default_allocated=100","default_allocated=10000",1),
                raw.replace("cycle=1,private=10001,handles=1,default_allocated","cycle=1,private=10002,handles=1,default_allocated",1),
                raw.replace("C545D_256_ARM_PASS","C545D_256_ARM_GAP",1),
                raw.replace(FINAL["256"],""),
                raw.replace("qpc=2,cpu100ns=1","qpc=1,cpu100ns=1",1)):
        try: parse(bad,"256")
        except ValueError: continue
        raise ValueError("negative_accepted")
    print("C545D_BLOCK_TREND_SELFTEST_PASS,positive=1,negative=6")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--input",type=Path)
    p.add_argument("--kind",choices=tuple(MODES),default="256")
    a=p.parse_args()
    if a.selftest: selftest()
    elif a.input:
        need(a.input.stat().st_size<=8_000_000,"size")
        for line in report(parse(a.input.read_text(encoding="utf-8-sig"),a.kind),a.kind): print(line)
    else: p.error("mode required")
if __name__=="__main__": main()
