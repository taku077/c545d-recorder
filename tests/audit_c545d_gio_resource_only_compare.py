#!/usr/bin/env python3
"""Audit four matched resource-only arms from sanitized CI stdout.
No ETW allocation ownership, no causal estimate, no long-run claim.
"""
import argparse
from pathlib import Path
import re
from audit_c545d_gio_matched_birth_compare import MODES, ARMS, RES, WORK, need
from audit_c545d_gio_matched_birth_contrast import contrast

BEGIN = re.compile(r"C545D_GIO_RESOURCE_ONLY_BEGIN,mode=(uncached|event-cache),arm=(nochange|registry),etw=0,external_handle_census=0,heapwalk=0")
END = re.compile(r"C545D_GIO_RESOURCE_ONLY_ARM_PASS,mode=(uncached|event-cache),arm=(nochange|registry),elapsed_ms=(\d+),etw=0,lineage_proven=0")
CACHE = re.compile(r"C545D_DISPLAY_CACHE,hits=(\d+),misses=(\d+),entries=(\d+)")
BRIDGE = re.compile(r"C545D_WINRT_BRIDGE,scans=(\d+),injections=(\d+),evictions=(\d+),errors=(\d+),ready=([01])")
PASS = "C545D_GIO_RESOURCE_ONLY_COMPARE_PASS,arms=4,cross_mode_worker_parity=1,etw=0,lineage_proven=0,release_HOLD=1"
KEYS = [(m, a) for m in MODES for a in ARMS]
METRICS = ("qpc_ticks", "cpu100ns", "private_bytes", "region_private_bytes", "handles", "notifications")
PREFIXES = ("C545D_GIO_RESOURCE_ONLY_", "C545D_GIO_ACTIVE_TWO_EPOCH_RESOURCE_AUDIT,",
            "C545D_GIO_ACTIVE_WORKER_EPOCH_AUDIT,", "C545D_DISPLAY_CACHE,", "C545D_WINRT_BRIDGE,")

def parse_log(raw):
    need(len(raw) <= 16_000_000, "log_size")
    data = {}
    current = None
    passed = False
    for rawline in raw.splitlines():
        # GitHub job logs carry a timestamp. Ignore echoed shell scripts.
        line = re.sub(r"^(?:.*?\t)?\d{4}-\d\d-\d\dT\S+Z\s+", "", rawline).strip()
        if not line.startswith(PREFIXES):
            continue
        m = BEGIN.fullmatch(line)
        if m:
            key = m.groups()
            need(not passed and current is None and key not in data, "arm_start")
            current = key
            data[key] = {}
            continue
        m = END.fullmatch(line)
        if m:
            need(not passed and current == m.groups()[:2], "arm_end")
            d = data[current]
            need("resource" in d and "work" in d, "missing_arm_metrics")
            need(int(m[3]) > 0, "invalid_elapsed")
            d["elapsed"] = int(m[3])
            current = None
            continue
        if line == PASS:
            need(not passed and current is None and set(data) == set(KEYS), "comparison_boundary")
            passed = True
            continue
        need(not passed and current is not None, "unscoped_record")
        d = data[current]
        m = RES.fullmatch(line)
        if m:
            name, value = "resource", tuple(map(int, m.groups()))
        else:
            m = WORK.fullmatch(line)
            if m:
                need(m[1] == current[1], "worker_arm")
                name, value = "work", tuple(map(int, m.groups()[1:]))
            else:
                m = CACHE.fullmatch(line)
                if m:
                    name, value = "cache", tuple(map(int, m.groups()))
                else:
                    m = BRIDGE.fullmatch(line)
                    need(m is not None, "unexpected_record")
                    name, value = "bridge", tuple(map(int, m.groups()))
        need(name not in d, "duplicate_metric")
        d[name] = value
    need(passed and current is None and set(data) == set(KEYS), "incomplete")
    for (mode, arm), d in data.items():
        w1, w2, t1, t2 = d["work"]
        r = d["resource"]
        need(t1 > 0 and t2 > 0 and (r[0], r[6]) == (t1, t2), "clock")
        need(r[1] >= 0 and r[7] >= 0 and r[5] >= 0 and r[11] >= 0, "counter")
        need((w1 == w2 == 0) if arm == "nochange" else (w1 == w2 and w1 > 0), "worker_parity")
        if mode == "uncached":
            need("cache" not in d and "bridge" not in d, "unexpected_cache")
        else:
            need("cache" in d and "bridge" in d, "missing_cache")
            h, misses, entries = d["cache"]
            scans, injections, _, errors, ready = d["bridge"]
            need(misses > 0 and 0 < entries <= 1024 and (arm != "registry" or h > 0), "cache_activity")
            need(scans > 0 and injections == errors == 0 and ready == 1, "bridge_activity")
    need(data["uncached", "registry"]["work"][:2] == data["event-cache", "registry"]["work"][:2], "cross_mode_workers")
    return data

def summarize(data):
    output = []
    fields = ("uncached_nochange", "uncached_registry", "cached_nochange", "cached_registry",
              "nochange_difference", "registry_difference", "control_adjusted_difference")
    def emit(metric, vals):
        values = ",".join(f"{k}={v}" for k, v in zip(fields, contrast(vals)))
        output.append(f"C545D_GIO_RESOURCE_ONLY_CONTRAST,metric={metric},{values},descriptive_only=1")
    for epoch in (1, 2):
        for i, name in enumerate(METRICS):
            emit(f"epoch{epoch}_{name}", {k: d["resource"][(epoch-1)*6+i] for k, d in data.items()})
    # The arm stopwatch includes post-exit audit work; not pure probe duration.
    emit("arm_elapsed_including_audit_ms", {k: d["elapsed"] for k, d in data.items()})
    return output

def selftest():
    lines = []
    for mode, arm in KEYS:
        n = int(arm == "registry")
        lines.append(f"C545D_GIO_RESOURCE_ONLY_BEGIN,mode={mode},arm={arm},etw=0,external_handle_census=0,heapwalk=0")
        if mode == "event-cache":
            lines += ["C545D_DISPLAY_CACHE,hits=3,misses=2,entries=2",
                      "C545D_WINRT_BRIDGE,scans=3,injections=0,evictions=0,errors=0,ready=1"]
        lines.append("C545D_GIO_ACTIVE_TWO_EPOCH_RESOURCE_AUDIT,"+
            ",".join(f"epoch{i}_{k}={v}" for i in (1,2) for k,v in
                zip(("qpc","cpu100ns","private_delta","region_private_delta","handles_delta","notifications_delta"),
                    (100,10,-256,0,-1,n)))+
            ",worker_completion_unproven=1,leak_slope_unproven=1,release_HOLD=1")
        lines.append(f"C545D_GIO_ACTIVE_WORKER_EPOCH_AUDIT,arm={arm},workers_epoch1={n},workers_epoch2={n},qpc_elapsed_epoch1=100,qpc_elapsed_epoch2=100,global_quiescence_not_proven=1,leak_slope_unproven=1,release_HOLD=1")
        lines.append(f"C545D_GIO_RESOURCE_ONLY_ARM_PASS,mode={mode},arm={arm},elapsed_ms=8000,etw=0,lineage_proven=0")
    lines.append(PASS)
    good = "\n".join("2026-11-27T14:00:00.000Z "+line for line in lines)
    need(len(summarize(parse_log(good))) == 13, "summary_count")
    for bad in (good.replace(PASS,""), good+"\n"+PASS, good.replace("elapsed_ms=8000","elapsed_ms=0",1),
                good.replace("workers_epoch1=1,workers_epoch2=1","workers_epoch1=2,workers_epoch2=2",1),
                good.replace("qpc_elapsed_epoch2=100","qpc_elapsed_epoch2=99",1),
                good.replace("entries=2","entries=1025",1), good.replace("ready=1","ready=0",1),
                good.replace("etw=0,lineage_proven=0","etw=1,lineage_proven=0",1)):
        try:
            parse_log(bad)
        except ValueError:
            continue
        raise AssertionError("negative_accepted")
    print("C545D_GIO_RESOURCE_ONLY_AUDIT_SELFTEST_PASS,positive=1,negative=8,actual_qualified=0")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--input", type=Path)
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    if not a.input:
        p.error("--input required")
    try:
        need(a.input.stat().st_size <= 16_000_000, "log_size")
        for line in summarize(parse_log(a.input.read_text(encoding="utf-8-sig"))):
            print(line)
    except (ValueError, OSError, UnicodeError):
        raise SystemExit("C545D_GIO_RESOURCE_ONLY_AUDIT_GAP,actual_qualified=0")
    print("C545D_GIO_RESOURCE_ONLY_AUDIT_PASS,arms=4,metrics=13,lineage_proven=0,long_run_proven=0")

if __name__ == "__main__":
    main()
