#!/usr/bin/env python3
"""Reanalyze *already archived* per-cycle PrivateUsage: Windows runs=0.

Control adjustment is within each Core or Combo 256-cycle original pair:
  D_i = (registry_i - registry_0) - (nochange_i - nochange_0)
Reg/unchanged were separate processes and run sequentially, so D_i is a
synthetic workload comparator, not a time-synchronized live memory trace.
Positive D_i is not by itself an allocation stack or endless leak slope.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import analyze_gio_combo_msvc256_saved as source

MODES = ("core", "combo")
ARMS = ("registry", "nochange")
N = 256
POINTS = (0, 64, 128, 192, 256)
FIELDS = ("handles", "private")
PROBE = re.compile(
    r"GIO_PROBE,(baseline|cycle|after_cleanup|settled_cleanup),"
    r"(\d+),(\d+),(\d+),(\d+)$"
)



# These counters are genuinely archived for EVERY cycle. This is a timing
# association ONLY: an AppInfo signal is neither a malloc stack nor proof
# that the generation-dependent native cache ran in the same cycle.
MONITOR = re.compile(
    r"GIO_PROBE,(baseline|cycle),(\d+),(\d+),(\d+),(\d+)$"
)
CACHE = re.compile(
    r"C545D_DISPLAY_CACHE,hits=(\d+),misses=(\d+),entries=(\d+)$"
)
BRIDGE = re.compile(
    r"C545D_WINRT_BRIDGE,scans=(\d+),injections=(\d+),"
    r"evictions=(\d+),errors=(\d+),ready=(\d+)$"
)


def monitor_readings(rows: list[str]) -> tuple[dict[int, int], dict[int, int]]:
    notifications: dict[int, int] = {}
    private: dict[int, int] = {}
    for row in rows:
        if not row.startswith("GIO_PROBE,"):
            continue
        m = MONITOR.fullmatch(row)
        if m is None:
            if row.startswith(("GIO_PROBE,baseline,", "GIO_PROBE,cycle,")):
                raise ValueError("malformed monitor-count process sample")
            continue  # two legitimate after-cleanup records
        label, index, monitor, _, memory = m.groups()
        cycle, count, usage = int(index), int(monitor), int(memory)
        if cycle not in range(N + 1) or (label == "baseline") != (cycle == 0):
            raise ValueError("incorrect monitor checkpoint phase")
        if cycle in notifications or count < 0 or usage < 0:
            raise ValueError("duplicate/negative monitor process sample")
        notifications[cycle] = count
        private[cycle] = usage
    if set(notifications) != set(range(N + 1)):
        raise ValueError("missing 256-cycle monitor samples")
    if any(notifications[i] < notifications[i - 1] for i in range(1, N + 1)):
        raise ValueError("monitor count decreased during the same process")
    return notifications, private



def completed_rebuild_timeline(rows: list[str]) -> dict[tuple[str, int], tuple]:
    """Align two *contiguous* numeric parser summaries to the next GIO_PROBE.

    The original Windows exporter preserved source output order. In the
    probe, enumerate_apps() completes before GIO_PROBE for each checkpoint.
    A paired cache/bridge summary marks an AppInfo package parser pass;
    no summary means no parser pass at that checkpoint. Reject ambiguous
    duplicate or unmatched summaries, never infer an allocation owner.
    """
    pending_cache = None
    pending_bridge = None
    seen: dict[tuple[str, int], tuple] = {}
    for row in rows:
        if m := CACHE.fullmatch(row):
            if pending_cache is not None:
                raise ValueError("more than one cache summary between checkpoints")
            pending_cache = tuple(map(int, m.groups()))
        elif m := BRIDGE.fullmatch(row):
            if pending_bridge is not None:
                raise ValueError("more than one bridge summary between checkpoints")
            pending_bridge = tuple(map(int, m.groups()))
        elif row.startswith("GIO_PROBE,"):
            m = PROBE.fullmatch(row)
            if m is None:
                raise ValueError("invalid checkpoint for rebuild alignment")
            phase, step = m.group(1), int(m.group(2))
            point = (phase, step)
            if point in seen or ((pending_cache is None) != (pending_bridge is None)):
                raise ValueError("ambiguous cache/bridge pairing at process checkpoint")
            seen[point] = ((pending_cache, pending_bridge)
                           if pending_cache is not None else None)
            pending_cache = pending_bridge = None
    if pending_cache is not None or pending_bridge is not None:
        raise ValueError("trailing unpaired cache/bridge summary")
    expected = {("baseline", 0), ("after_cleanup", 257),
                ("settled_cleanup", 258)}
    expected.update(("cycle", i) for i in range(1, N + 1))
    if set(seen) != expected:
        raise ValueError("incomplete 259-checkpoint rebuild timeline")
    return seen


def audit_cache_rebuild_epochs(group: dict[str, list[str]]) -> list[str]:
    """Fixture-specific identity, NOT a release invariant across other PCs."""
    out = []
    for arm in ARMS:
        seen = completed_rebuild_timeline(group[f"combo-{arm}-256"])
        # Do not PRESUME that baseline/cleanup or all individual 256 GIO
        # enumerations must schedule a parser scan. The first stricter audit
        # failed on precisely this unsupported checkpoint assumption, even
        # though every recorded cache/bridge row was internally valid.
        ordered = [("baseline", 0)] + [("cycle", i) for i in range(1, N+1)] + [
            ("after_cleanup", 257), ("settled_cleanup", 258)]
        all_samples = [seen[p] for p in ordered if seen[p] is not None]
        expected_total = 258 if arm == "registry" else 1
        if len(all_samples) != expected_total:
            raise ValueError("original parser-summary count changed")
        for number, (cache, bridge) in enumerate(all_samples):
            hits, misses, entries = cache
            scans, injections, evictions, errors, ready = bridge
            if not (misses == 32 and entries == 32 and
                    hits == number * 32 and scans == number + 1 and
                    injections == 0 and evictions == 0 and
                    errors == 0 and ready == 1):
                raise ValueError("original 32-package cache/bridge identity changed")
        cycle_scans = sum(seen[("cycle", i)] is not None for i in range(1, N+1))
        baseline_scans = int(seen[("baseline", 0)] is not None)
        cleanup_scans = int(seen[("after_cleanup", 257)] is not None)
        settled_scans = int(seen[("settled_cleanup", 258)] is not None)
        out.append(
            f"C545D_SAVED256_CACHE_REBUILD,source_run=44918598339,"
            f"arm={arm},baseline_scans={baseline_scans},"
            f"cycle_scans={cycle_scans},"
            f"after_cleanup_scans={cleanup_scans},"
            f"settled_scans={settled_scans},"
            f"cycle_misses={N-cycle_scans},packages_per_scan=32,"
            f"cache_entry_growth=0,native_evictions=0,"
            f"cache_copies_not_alloc_site=1,CI_only=1"
        )
    # A genuine additional GIO parse happened in the registry arm between
    # AFTER_CLEANUP(257) and SETTLED_CLEANUP(258); the nochange arm had none.
    # Quantify the matched resource changes in BOTH segments. Do not attribute
    # them entirely to the parser: all allocations and scheduler activity run.
    cohort = {arm: source.parse(group, "combo", arm) for arm in ARMS}
    for before, after in ((("cycle", 256), ("after_cleanup", 257)),
                          (("after_cleanup", 257), ("settled_cleanup", 258))):
        for metric in ("mem", "heap"):
            raw = {
                arm: cohort[arm][metric][after] - cohort[arm][metric][before]
                for arm in ARMS
            }
            # Preserve the actual source-run numbers; otherwise a later
            # changed or mixed archive could silently rewrite this finding.
            expected = {
                (256, 257, "mem"): (0, 0),
                (256, 257, "heap"): (-758460, 0),
                (257, 258, "mem"): (-57344, 0),
                (257, 258, "heap"): (749156, 0),
            }[before[1], after[1], metric]
            if (raw["registry"], raw["nochange"]) != expected:
                raise ValueError("pinned cleanup/rebuild resources changed")
            out.append(
                f"C545D_SAVED256_CLEANUP_RESOURCE,source_run=44918598339,"
                f"metric={metric},window={before[1]}_{after[1]},"
                f"registry_raw={raw['registry']},"
                f"nochange_raw={raw['nochange']},"
                f"control_adjusted={raw['registry']-raw['nochange']},"
                "late_parser_scan_not_unique_cause=1,CI_only=1"
            )
    out.append(
        "C545D_SAVED256_CACHE_REBUILD_PASS,source_run=44918598339,"
        "snapshot_order_preserved=1,registry_scans=258,nochange_scans=1,"
        "displayname_cache_entries_stay_32=1,allocation_owner_proven=0,"
        "new_windows_runs=0"
    )
    return out


def monitor_alignment(group: dict[str, list[str]]) -> list[str]:
    # Read the same original-run four arms, with no synthetic cross-run pair.
    # Explicitly keep 'signal-free memory steps' descriptive: asynchronous
    # notifications can be delayed and public GAppInfo calls can rescan without
    # a GAppInfoMonitor callback.
    out = []
    for mode in MODES:
        for arm in ARMS:
            rows = group[f"{mode}-{arm}-256"]
            counts, private = monitor_readings(rows)
            for start, end in zip(POINTS[:-1], POINTS[1:]):
                increments = [counts[i] - counts[i-1]
                              for i in range(start+1, end+1)]
                signaled = sum(n > 0 for n in increments)
                positive_without_signal = sum(
                    increments[i-start-1] == 0 and
                    private[i] > private[i-1]
                    for i in range(start+1, end+1))
                out.append(
                    f"C545D_SAVED256_MONITOR_ALIGNMENT,source_run=44918598339,"
                    f"mode={mode},arm={arm},window={start}_{end},"
                    f"monitor_increment={counts[end]-counts[start]},"
                    f"cycles_with_signal={signaled},"
                    f"cycles_without_signal={64-signaled},"
                    f"private_up_without_signal_cycles={positive_without_signal},"
                    "correlation_only=1,exact_360_owner_proven=0,CI_only=1"
                )
            if mode == "combo":
                cache = [tuple(map(int, m.groups())) for row in rows
                         if (m := CACHE.fullmatch(row))]
                bridge = [tuple(map(int, m.groups())) for row in rows
                          if (m := BRIDGE.fullmatch(row))]
                if not cache or not bridge:
                    raise ValueError("missing cumulative cache/bridge summaries")
                hits, misses, entries = cache[-1]
                scans, injections, evictions, errors, ready = bridge[-1]
                if entries > 1024 or errors != 0 or ready != 1:
                    raise ValueError("invalid cumulative cache/bridge snapshot")
                out.append(
                    f"C545D_SAVED256_COUNTER_SCOPE,source_run=44918598339,"
                    f"arm={arm},cache_records={len(cache)},"
                    f"bridge_records={len(bridge)},cache_hits_last={hits},"
                    f"cache_misses_last={misses},cache_entries_last={entries},"
                    f"bridge_scans_last={scans},bridge_injections_last={injections},"
                    f"bridge_evictions_last={evictions},"
                    "counter_cycle_alignment_not_proven=1,CI_only=1"
                )
    out.append(
        "C545D_SAVED256_MONITOR_ALIGNMENT_PASS,source_run=44918598339,"
        "arms=4,windows=4,windows_checked=16,combo_counters=2,"
        "new_windows_runs=0,notifications_are_not_alloc_stacks=1,"
        "real_device_untested=1"
    )
    return out


def readings(rows: list[str]) -> dict:
    cycles: dict[int, tuple[int, int]] = {}
    cleanup: dict[str, tuple[int, int]] = {}
    for line in rows:
        if not line.startswith("GIO_PROBE,"):
            continue
        match = PROBE.fullmatch(line)
        if not match:
            raise ValueError("malformed per-cycle GIO_PROBE")
        label, index, _, handles, private = match.groups()
        i, h, p = int(index), int(handles), int(private)
        if p < 0 or h < 0:
            raise ValueError("negative process resource count")
        if label == "baseline":
            if i != 0 or i in cycles:
                raise ValueError("invalid/duplicate baseline")
            cycles[i] = (h, p)
        elif label == "cycle":
            if not (1 <= i <= N) or i in cycles:
                raise ValueError("extra/duplicate process cycle")
            cycles[i] = (h, p)
        else:
            expected = 257 if label == "after_cleanup" else 258
            if i != expected or label in cleanup:
                raise ValueError("extra/duplicate cleanup sample")
            cleanup[label] = (h, p)
    if set(cycles) != set(range(N + 1)) or set(cleanup) != {
        "after_cleanup", "settled_cleanup"
    }:
        raise ValueError("incomplete 256-cycle process timeline")
    return {"cycles": cycles, "cleanup": cleanup}


def effects(group: dict[str, list[str]]) -> dict:
    data = {mode: {
        arm: readings(group[f"{mode}-{arm}-256"]) for arm in ARMS
    } for mode in MODES}
    result = {}
    for mode in MODES:
        no = data[mode]["nochange"]["cycles"]
        reg = data[mode]["registry"]["cycles"]
        for dim, field in enumerate(FIELDS):
            idx = dim
            b_reg, b_no = reg[0][idx], no[0][idx]
            series = [
                (reg[i][idx] - b_reg) - (no[i][idx] - b_no)
                for i in range(N + 1)
            ]
            settled_reg = data[mode]["registry"]["cleanup"]["settled_cleanup"][idx]
            settled_no = data[mode]["nochange"]["cleanup"]["settled_cleanup"][idx]
            settled = (settled_reg - b_reg) - (settled_no - b_no)
            result[mode, field] = (series, settled)
    return result


def summarize(data: dict, verbose: bool = True) -> list[str]:
    lines = []
    for metric in FIELDS:
        for start, end in zip(POINTS[:-1], POINTS[1:]):
            for mode in MODES:
                series, settled = data[mode, metric]
                steps = [series[i] - series[i - 1] for i in range(start + 1, end + 1)]
                pos = sum(x > 0 for x in steps)
                neg = sum(x < 0 for x in steps)
                flat = sum(x == 0 for x in steps)
                assert len(steps) == 64 and pos + neg + flat == 64
                window = f"{start}_{end}"
                lines.append(
                    f"C545D_SAVED256_STEP,metric={metric},mode={mode},"
                    f"window={window},net={series[end] - series[start]},"
                    f"positive={pos},negative={neg},flat={flat},"
                    f"largest_up={max(steps)},largest_down={min(steps)},"
                    f"range={max(series[start:end+1]) - min(series[start:end+1])},"
                    "host_modified=0"
                )
        for mode in MODES:
            series, settled = data[mode, metric]
            lines.append(
                f"C545D_SAVED256_END,metric={metric},mode={mode},"
                f"cycle256={series[256]},settled258={settled},"
                f"cleanup_change={settled-series[256]},"
                "causal_owner_known=0,zero_leak_proven=0"
            )
    lines.append(
        "C545D_SAVED256_STEP_ANALYSIS_PASS,source_run=44918598339,"
        "original_cycles=256,windows_runs=0,resource_metrics=2,"
        "counterfactuals_matched=1,zero_leak_proven=0,host_install_approved=0"
    )
    if verbose:
        print("\n".join(lines))
    return lines


def analyze(group: dict[str, list[str]]) -> list[str]:
    # Do not bypass old strict checks for complete 4 arms, 16-cycle native
    # parity, cache population/bridge validity and exact resource snapshots.
    original = source.analyze(group, print_output=False)
    if not original[-1].startswith("C545D_SAVED256_NUMERIC_ANALYSIS_PASS,"):
        raise ValueError("original pinned numeric archive failed source checks")
    measurements = effects(group)
    output = summarize(measurements, verbose=False)
    expected = {
        ("core", "private"): [1499136, 573440, 286720, 729088],
        ("combo", "private"): [151552, 233472, -12288, 53248],
        ("core", "handles"): [32, 3, 0, 4],
        ("combo", "handles"): [-1, 1, -1, -3],
    }
    for (mode, metric), deltas in expected.items():
        v, settled = measurements[mode, metric]
        for j, (left, right) in enumerate(zip(POINTS[:-1], POINTS[1:])):
            if v[right] - v[left] != deltas[j]:
                raise ValueError("pinned original 256-cycle effect mismatch")
    if measurements["core", "private"][1] != 3272704 or \
       measurements["combo", "private"][1] != 368640 or \
       measurements["core", "handles"][1] != 38 or \
       measurements["combo", "handles"][1] != -7:
        raise ValueError("pinned original settled memory/handle effect mismatch")
    output.extend(monitor_alignment(group))
    output.extend(audit_cache_rebuild_epochs(group))
    print("\n".join(output))
    return output


def selftest() -> None:
    def fake():
        o = {}
        for mode in MODES:
            for arm in ARMS:
                label = f"{mode}-{arm}-256"
                o[label] = [
                    f"GIO_PROBE,baseline,0,0,100,15000"
                ] + [
                    f"GIO_PROBE,cycle,{i},0,{100+i},{15000+4096*(i//32)}"
                    for i in range(1, N + 1)
                ] + [
                    "GIO_PROBE,after_cleanup,257,0,400,52000",
                    "GIO_PROBE,settled_cleanup,258,0,390,50000",
                ]
        return o
    clean = fake()
    for metric in FIELDS:
        assert all(len(effects(clean)[mode, metric][0]) == 257
                   for mode in MODES)
    tag = "combo-registry-256"
    baseline = clean[tag][:]
    variants = [
        [r for r in baseline if not r.startswith("GIO_PROBE,cycle,101,")],
        baseline + ["GIO_PROBE,cycle,101,0,201,25000"],
        baseline + ["GIO_PROBE,cycle,259,0,201,25000"],
        [x.replace("GIO_PROBE,cycle,103,0", "GIO_PROBE,cycle,103,WRONG")
         for x in baseline],
        [x.replace("GIO_PROBE,cycle,103,0,203,", "GIO_PROBE,cycle,103,0,-203,")
         for x in baseline],
    ]
    for bad in variants:
        clean[tag] = bad
        try:
            effects(clean)
        except ValueError:
            pass
        else:
            raise AssertionError("corrupted timeline accepted")
    clean[tag] = baseline
    # Synthetic, independent of the real WinRT/registry runner.
    fake_monitor = [
        "GIO_PROBE,baseline,0,0,100,1000"
    ] + [
        f"GIO_PROBE,cycle,{i},{i//10},100,{1000+4096*(i//16)}"
        for i in range(1, N + 1)
    ]
    count, usage = monitor_readings(fake_monitor)
    assert count[256] == 25 and usage[256] == 1000 + 16 * 4096
    bad_monitor = [
        fake_monitor[:-1],
        fake_monitor + [fake_monitor[100]],
        [r.replace("GIO_PROBE,cycle,128,12,",
                   "GIO_PROBE,cycle,128,0,") for r in fake_monitor],
        [r.replace("GIO_PROBE,cycle,64,6,",
                   "GIO_PROBE,cycle,64,-6,") for r in fake_monitor],
    ]
    rejected = 0
    for candidate in bad_monitor:
        try:
            monitor_readings(candidate)
        except ValueError:
            rejected += 1
        else:
            raise AssertionError("invalid monitor series accepted")
    assert rejected == 4

    # Minimal ordering fixture; test must reject unmatched, repeated or
    # out-of-order numeric cumulative parser summaries.
    aligned = ["C545D_DISPLAY_CACHE,hits=0,misses=32,entries=32",
               "C545D_WINRT_BRIDGE,scans=1,injections=0,evictions=0,errors=0,ready=1",
               "GIO_PROBE,baseline,0,0,100,1000"] + [
               f"GIO_PROBE,cycle,{i},0,100,1000" for i in range(1, N + 1)] + [
               "GIO_PROBE,after_cleanup,257,0,100,1000",
               "GIO_PROBE,settled_cleanup,258,0,100,1000"]
    assert completed_rebuild_timeline(aligned)[("baseline", 0)] is not None
    for broken in (
        aligned[:1] + aligned[2:],
        aligned[:2] + [aligned[0]] + aligned[2:],
        aligned + [aligned[0]],
    ):
        try:
            completed_rebuild_timeline(broken)
        except ValueError:
            pass
        else:
            raise AssertionError("ambiguous source-ordered scan passed")

    print("C545D_SAVED256_STEP_SELFTEST_PASS,negative_cases=5,"
          "monitor_negative_cases=4,original_windows_runs=0")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    elif len(sys.argv) == 3 and sys.argv[1] == "--root":
        analyze(source.load(Path(sys.argv[2])))
    else:
        raise SystemExit("usage: trend (--selftest | --root DIR)")
