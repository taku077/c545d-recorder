#!/usr/bin/env python3
"""Descriptive paired contrasts from a qualified four-arm native log.
No Windows run or raw ETL. Not a causal or long-run leak estimate.
"""
import argparse
from pathlib import Path
from audit_c545d_gio_matched_birth_compare import parse, GROUPS, MODES, ARMS, need

def total(rows, cut, groups, column):
    return sum(v[column] for (c, _, g), v in rows.items()
               if c == cut and g in groups)

def row_metric(data, groups, column, kind):
    out = {}
    for mode in MODES:
        for arm in ARMS:
            rows = data[mode, arm]["rows"]
            if kind == "baseline":
                value = total(rows, "baseline", groups, column)
            elif kind == "epoch2_net":
                value = total(rows, "cycle2", groups, column) - total(rows, "cycle1", groups, column)
            elif kind == "cycle1_survivors":
                value = sum(rows["cycle2", "cycle1", g][column] for g in groups)
            elif kind == "cycle2_new":
                value = sum(rows["cycle2", "cycle2", g][column] for g in groups)
            else:
                raise ValueError("unknown_metric")
            out[mode, arm] = value
    return out

def contrast(values):
    u0 = values["uncached", "nochange"]
    u1 = values["uncached", "registry"]
    c0 = values["event-cache", "nochange"]
    c1 = values["event-cache", "registry"]
    # Direction always cached minus uncached; negative is less, not proof of benefit.
    return (u0, u1, c0, c1, c0-u0, c1-u1, (c1-c0)-(u1-u0))

def emit(scope, metric, values):
    keys = ("uncached_nochange", "uncached_registry", "cached_nochange",
            "cached_registry", "nochange_difference", "registry_difference",
            "control_adjusted_difference")
    fields = ",".join(f"{k}={v}" for k, v in zip(keys, contrast(values)))
    return (f"C545D_GIO_MATCHED_CONTRAST,scope={scope},metric={metric},"
            f"{fields},direction=cache_minus_uncached,descriptive_only=1")

def summarize(data):
    out = []
    for scope, groups in [(g, (g,)) for g in GROUPS] + [("all", GROUPS)]:
        for kind in ("baseline", "epoch2_net", "cycle1_survivors", "cycle2_new"):
            for column, unit in enumerate(("count", "requested_bytes")):
                out.append(emit(scope, f"{kind}_{unit}", row_metric(data, groups, column, kind)))
    for metric, index in (("epoch2_private_bytes", 8), ("epoch2_handles", 10),
                          ("epoch2_cpu100ns", 7), ("epoch2_qpc", 6)):
        out.append(emit("resource", metric, {k: d["resource"][index] for k, d in data.items()}))
    return out

def selftest():
    keys = [(m, a) for m in MODES for a in ARMS]
    need(contrast(dict(zip(keys, (10, 50, 12, 25)))) == (10, 50, 12, 25, 2, -25, -27), "control")
    need(contrast(dict(zip(keys, (0, -4, -2, -8))))[-3:] == (-2, -4, -2), "signed")
    need(contrast(dict(zip(keys, (0, 0, 0, 0)))) == (0,)*7, "zero")
    data = {}
    for k in keys:
        rows = {}
        for g in GROUPS:
            for cut, births in (("baseline", ("baseline",)),
                                ("cycle1", ("baseline", "cycle1")),
                                ("cycle2", ("baseline", "cycle1", "cycle2"))):
                for birth in births:
                    rows[cut, birth, g] = (1, 10)
        data[k] = {"rows": rows, "resource": (0,)*12}
    need(set(row_metric(data, GROUPS, 1, "baseline").values()) == {40}, "baseline")
    need(set(row_metric(data, GROUPS, 1, "epoch2_net").values()) == {40}, "net")
    need(set(row_metric(data, GROUPS, 0, "cycle1_survivors").values()) == {4}, "survivors")
    need(set(row_metric(data, GROUPS, 0, "cycle2_new").values()) == {4}, "new")
    need(len(summarize(data)) == 44, "complete_metrics")
    print("C545D_GIO_MATCHED_CONTRAST_SELFTEST_PASS,checks=8,actual_qualified=0")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--input", type=Path)
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    if not a.input:
        ap.error("--input required")
    try:
        need(a.input.stat().st_size <= 16_000_000, "log_size")
        data = parse(a.input.read_text(encoding="utf-8-sig"))
        for line in summarize(data):
            print(line)
    except (ValueError, OSError, UnicodeError):
        raise SystemExit("C545D_GIO_MATCHED_CONTRAST_GAP,actual_qualified=0")
    print("C545D_GIO_MATCHED_CONTRAST_PASS,arms=4,metrics=44,long_run_proven=0")

if __name__ == "__main__":
    main()
