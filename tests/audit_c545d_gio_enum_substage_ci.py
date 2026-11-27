#!/usr/bin/env python3
"""Analyze completed and timed-out arms, retaining only proven QPC intervals."""
import argparse
import re
from pathlib import Path

LABELS = ("core-off", "combo-off", "combo-on")
STAGES = ("get_begin", "get_end", "free_begin", "free_end", "context_begin", "context_end")
BEGIN = re.compile(r"C545D_GIO_ENUM_BEGIN,label=(core-off|combo-off|combo-on),cache=0,registry=0,etw=0")
ROW = re.compile(r"C545D_GIO_ENUM_SUBSTAGE,stage=(get_begin|get_end|free_begin|free_end|context_begin|context_end),index=([0-4]),qpc=(\d+)")
END = re.compile(r"C545D_GIO_ENUM_RESULT,label=(core-off|combo-off|combo-on),finished=([01]),valid=([01]),elapsed_ms=(\d+)")
DLL = re.compile(r"C545D_GIO_ENUM_DLL,label=(core-off|combo-off|combo-on),sample=5,match=([01])")
DONE = "C545D_GIO_ENUM_DISCRIMINATOR_DONE,arms=3,not_a_release_gate=1,release_HOLD=1"

def require(ok, reason):
    if not ok:
        raise ValueError(reason)

def parse(raw):
    require(len(raw) <= 16_000_000, "size")
    arms = {}
    active = None
    done = False
    for line in raw.splitlines():
        line = re.sub(r"^(?:.*?\t)?\d{4}-\d\d-\d\dT\S+Z\s+", "", line).strip()
        m = BEGIN.fullmatch(line)
        if m:
            require(not done and active is None and len(arms)<3 and m[1]==LABELS[len(arms)], "begin")
            active = m[1]
            arms[active] = {"rows": [], "identity": None}
            continue
        m = ROW.fullmatch(line)
        if m:
            require(active is not None and not done, "row_scope")
            rows = arms[active]["rows"]
            i = len(rows)
            qpc = int(m[3])
            require(i < 30 and m[1] == STAGES[i%6] and int(m[2]) == i//6, "order")
            require(qpc > 0 and (not rows or qpc >= rows[-1]), "clock")
            rows.append(qpc)
            continue
        m = DLL.fullmatch(line)
        if m:
            require(active == m[1] and not done and arms[active]["identity"] is None, "dll_scope")
            arms[active]["identity"] = int(m[2])
            continue
        m = END.fullmatch(line)
        if m:
            require(active == m[1] and not done, "end")
            finished, valid, elapsed = map(int,m.groups()[1:])
            d = arms[active]
            require(elapsed > 0 and (not valid or (finished and len(d["rows"])==30 and d["identity"]==1)), "qualification")
            d.update(finished=finished, valid=valid, elapsed=elapsed)
            active = None
            continue
        if line == DONE:
            require(not done and active is None and tuple(arms)==LABELS, "done")
            done = True
        elif line.startswith(("C545D_GIO_ENUM_BEGIN,","C545D_GIO_ENUM_SUBSTAGE,","C545D_GIO_ENUM_RESULT,","C545D_GIO_ENUM_DISCRIMINATOR_DONE,")):
            raise ValueError("malformed_record")
    require(done, "incomplete_run")
    return arms

def summarize(arms):
    out = []
    for label,d in arms.items():
        rows = d["rows"]
        qualified = d["identity"] == 1
        out.append(f"C545D_ENUM_AUDIT_ARM,label={label},finished={d['finished']},valid={d['valid']},elapsed_ms={d['elapsed']},boundaries={len(rows)},identity_verified={int(qualified)}")
        if not qualified:
            continue
        for offset,name in ((0,"get"),(2,"free"),(4,"context")):
            intervals = [rows[i+1]-rows[i] for i in range(offset,len(rows)-1,6)]
            out.append(f"C545D_ENUM_AUDIT_PHASE,label={label},phase={name},completed={len(intervals)},sum_qpc_ticks={sum(intervals)},max_qpc_ticks={max(intervals,default=0)},partial_arm={int(not d['valid'])}")
        if len(rows)<30:
            i=len(rows)
            out.append(f"C545D_ENUM_AUDIT_NEXT,label={label},index={i//6},missing_boundary={STAGES[i%6]},duration_unknown=1")
    return out

def selftest():
    lines=[]
    for label in LABELS:
        partial=label=="combo-on"
        lines += [f"C545D_GIO_ENUM_BEGIN,label={label},cache=0,registry=0,etw=0",
                  f"C545D_GIO_ENUM_DLL,label={label},sample=5,match=1"]
        lines += [f"C545D_GIO_ENUM_SUBSTAGE,stage={STAGES[i%6]},index={i//6},qpc={100+i*10}" for i in range(13 if partial else 30)]
        lines += [f"C545D_GIO_ENUM_RESULT,label={label},finished={int(not partial)},valid={int(not partial)},elapsed_ms={60000 if partial else 8000}"]
    lines.append(DONE)
    good="\n".join(lines)
    arms=parse(good)
    result=summarize(arms)
    require(any("label=combo-on,index=2,missing_boundary=get_end" in x for x in result),"partial")
    require(any("label=combo-on,phase=get,completed=2,sum_qpc_ticks=20" in x for x in result),"censored")
    require(any("label=core-off,phase=get,completed=5,sum_qpc_ticks=50" in x for x in result),"complete")
    for bad in (good.replace(DONE,""), good+"\n"+DONE, good.replace("stage=get_end,index=0","stage=free_end,index=0",1),
                good.replace("qpc=110","qpc=99",1),good.replace("finished=0,valid=0","finished=0,valid=1"),
                good.replace("sample=5,match=1","sample=5,match=0",1),good.replace("elapsed_ms=8000","elapsed_ms=0",1)):
        try:
            parse(bad)
        except ValueError:
            continue
        raise AssertionError("negative_accepted")
    print("C545D_ENUM_AUDIT_SELFTEST_PASS,positive=3,negative=7,actual_qualified=0")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--input",type=Path)
    a=p.parse_args()
    if a.selftest:
        selftest()
        return
    if not a.input:
        p.error("--input required")
    try:
        require(a.input.stat().st_size<=16_000_000,"size")
        for line in summarize(parse(a.input.read_text(encoding="utf-8-sig"))):
            print(line)
    except (ValueError,OSError,UnicodeError):
        raise SystemExit("C545D_ENUM_AUDIT_GAP,actual_qualified=0")
    print("C545D_ENUM_AUDIT_DONE,arms=3,causal_proof=0,release_HOLD=1")

if __name__=="__main__":
    main()
