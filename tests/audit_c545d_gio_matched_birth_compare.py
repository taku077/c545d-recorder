#!/usr/bin/env python3
"""Offline compare sanitized output of the existing four-arm native CI.
No ETL, addresses, stack data, new Windows build or real recorder operation.
A qualified contrast is descriptive, not proof of causality or long-run slope.
"""
import argparse
from pathlib import Path
import re

MODES=("uncached","event-cache")
ARMS=("nochange","registry")
CUTS=("baseline","cycle1","cycle2")
GROUPS=("getter_package","getter_other","package_nongetter","other")
KEYS={(cut,birth,group) for i,cut in enumerate(CUTS)
      for birth in CUTS[:i+1] for group in GROUPS}
BEGIN=re.compile(r"C545D_GIO_BIRTH_COMPARE_BEGIN,mode=(uncached|event-cache),arm=(nochange|registry)")
END=re.compile(r"C545D_GIO_BIRTH_COMPARE_ARM_PASS,mode=(uncached|event-cache),arm=(nochange|registry),cache_activation_checked=1,real_camera=0")
ROW=re.compile(r"C545D_GIO_BIRTH_EPOCH_SURVIVAL,arm=(nochange|registry),cut=(baseline|cycle1|cycle2),birth=(baseline|cycle1|cycle2),group=(getter_package|getter_other|package_nongetter|other),live=(\d+),request_bytes_live=(\d+),original_lineage=1,realloc_preserved=1,leak_proven=0")
WORK=re.compile(r"C545D_GIO_ACTIVE_WORKER_EPOCH_AUDIT,arm=(nochange|registry),workers_epoch1=(\d+),workers_epoch2=(\d+),qpc_elapsed_epoch1=(\d+),qpc_elapsed_epoch2=(\d+),global_quiescence_not_proven=1,leak_slope_unproven=1,release_HOLD=1")
RES=re.compile(r"C545D_GIO_ACTIVE_TWO_EPOCH_RESOURCE_AUDIT,"+
    ",".join(f"epoch{i}_{k}=(-?\\d+)" for i in (1,2) for k in
             ("qpc","cpu100ns","private_delta","region_private_delta","handles_delta","notifications_delta"))+
    r",worker_completion_unproven=1,leak_slope_unproven=1,release_HOLD=1")
PASS="C545D_GIO_BIRTH_COMPARE_PASS,arms=4,event_locale_bridge=1,cache_permanent_only=0,same_build_runner=1,release_HOLD=1"

def need(ok,reason):
    if not ok: raise ValueError(reason)

def parse(text):
    need(len(text)<=16_000_000,"log_size")
    data={}; active=None; passed=0
    for raw in text.splitlines():
        # GitHub log prefix may include job, step and timestamp.
        pos=raw.find("C545D_GIO_")
        if pos<0: continue
        line=raw[pos:].strip()
        m=BEGIN.fullmatch(line)
        if m:
            key=m.groups()
            need(active is None and key not in data,"arm_boundary")
            active=key;data[key]={"rows":{},"workers":None,"resource":None}
            continue
        m=END.fullmatch(line)
        if m:
            need(active==m.groups(),"arm_end")
            d=data[active]
            need(set(d["rows"])==KEYS and d["workers"] is not None and d["resource"] is not None,"incomplete_arm")
            active=None
            continue
        if line==PASS:
            need(active is None,"early_pass")
            passed+=1;continue
        if active is None: continue
        d=data[active]
        m=ROW.fullmatch(line)
        if m:
            arm,cut,born,group,n,b=m.groups()
            key=(cut,born,group)
            need(arm==active[1] and key in KEYS and key not in d["rows"],"row_scope")
            d["rows"][key]=(int(n),int(b));continue
        m=WORK.fullmatch(line)
        if m:
            need(m[1]==active[1] and d["workers"] is None,"worker_scope")
            d["workers"]=tuple(map(int,m.groups()[1:]));continue
        m=RES.fullmatch(line)
        if m:
            need(d["resource"] is None,"resource_duplicate")
            d["resource"]=tuple(map(int,m.groups()))
    need(active is None and passed==1 and set(data)=={(m,a) for m in MODES for a in ARMS},"comparison_incomplete")
    for (mode,arm),d in data.items():
        w1,w2,t1,t2=d["workers"]
        need(t1>0 and t2>0 and (w1,w2)==((0,0) if arm=="nochange" else (w1,w1))
             and (arm!="registry" or w1>0),"worker_parity")
        need((d["resource"][0],d["resource"][6])==(t1,t2),"clock_parity")
        for (cut,born,g),(n,b) in d["rows"].items():
            need(n>0 or b==0,"zero_count_nonzero_bytes")
            i=CUTS.index(cut)
            if i> CUTS.index(born):
                need(n<=d["rows"][(CUTS[i-1],born,g)][0],"old_birth_growth")
    need(data[("uncached","registry")]["workers"][:2]==data[("event-cache","registry")]["workers"][:2],"cross_mode_worker_mismatch")
    return data

def summarize(data):
    output=[]
    for (mode,arm),d in data.items():
        for group in GROUPS:
            rows=d["rows"]
            n,b=rows[("cycle2","cycle1",group)]
            n2,b2=rows[("cycle2","cycle2",group)]
            prev=rows[("cycle1","baseline",group)]
            new=rows[("cycle1","cycle1",group)]
            baseline=rows[("cycle2","baseline",group)]
            output.append(f"C545D_GIO_MATCHED_BIRTH_SUMMARY,mode={mode},arm={arm},group={group},"
                          f"cycle1_surviving_n={n},cycle1_surviving_b={b},cycle2_new_n={n2},cycle2_new_b={b2},"
                          f"epoch2_net_n={baseline[0]+n+n2-prev[0]-new[0]},"
                          f"epoch2_net_b={baseline[1]+b+b2-prev[1]-new[1]}")
        r=d["resource"]
        output.append(f"C545D_GIO_MATCHED_RESOURCE_SUMMARY,mode={mode},arm={arm},"
                      f"workers={d['workers'][1]},epoch2_private_delta={r[8]},epoch2_handles_delta={r[10]},epoch2_cpu100ns={r[7]}")
    output.append("C545D_GIO_MATCHED_BIRTH_AUDIT_PASS,arms=4,cross_mode_worker_parity=1,order_randomized=0,long_run_proven=0")
    return output

def selftest():
    lines=[]
    for mode in MODES:
        for arm in ARMS:
            lines.append(f"C545D_GIO_BIRTH_COMPARE_BEGIN,mode={mode},arm={arm}")
            n=int(arm=="registry")
            lines.append(f"C545D_GIO_ACTIVE_WORKER_EPOCH_AUDIT,arm={arm},workers_epoch1={n},workers_epoch2={n},qpc_elapsed_epoch1=100,qpc_elapsed_epoch2=100,global_quiescence_not_proven=1,leak_slope_unproven=1,release_HOLD=1")
            lines.append("C545D_GIO_ACTIVE_TWO_EPOCH_RESOURCE_AUDIT,"+
                ",".join(f"epoch{i}_{k}={v}" for i in (1,2) for k,v in
                         zip(("qpc","cpu100ns","private_delta","region_private_delta","handles_delta","notifications_delta"),(100,0,0,0,0,0)))+
                ",worker_completion_unproven=1,leak_slope_unproven=1,release_HOLD=1")
            for c,b,g in sorted(KEYS):
                lines.append(f"C545D_GIO_BIRTH_EPOCH_SURVIVAL,arm={arm},cut={c},birth={b},group={g},live=0,request_bytes_live=0,original_lineage=1,realloc_preserved=1,leak_proven=0")
            lines.append(f"C545D_GIO_BIRTH_COMPARE_ARM_PASS,mode={mode},arm={arm},cache_activation_checked=1,real_camera=0")
    lines.append(PASS)
    good="\n".join(lines)
    need(len(summarize(parse(good)))==21,"selftest_summary")
    invalid=[good.replace(PASS,""),good+"\n"+PASS,
             good.replace("workers_epoch1=1,workers_epoch2=1","workers_epoch1=2,workers_epoch2=2",1),
             good.replace("qpc_elapsed_epoch2=100","qpc_elapsed_epoch2=99",1),
             good.replace("live=0,request_bytes_live=0","live=0,request_bytes_live=1",1),
             good.replace("cut=baseline,birth=baseline","cut=baseline,birth=cycle1",1)]
    for bad in invalid:
        try:parse(bad)
        except ValueError:continue
        raise AssertionError("negative_accepted")
    print("C545D_GIO_MATCHED_BIRTH_AUDIT_SELFTEST_PASS,positive=1,negative=6")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--input",type=Path)
    a=p.parse_args()
    if a.selftest:selftest();return
    if not a.input:p.error("--input required")
    try:
        need(a.input.stat().st_size<=16_000_000,"log_size")
        for line in summarize(parse(a.input.read_text(encoding="utf-8-sig"))):print(line)
    except (ValueError,OSError,UnicodeError):
        raise SystemExit("C545D_GIO_MATCHED_BIRTH_AUDIT_GAP,comparison_unqualified=1")
if __name__=="__main__":main()
