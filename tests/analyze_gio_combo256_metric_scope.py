#!/usr/bin/env python3
"""Pin different measurement scopes in original Combo256 Windows archive.

Source Windows2022 #44918598339, four arms. No new Windows run.
HeapWalk busy cbData is allocated block DATA, PrivateUsage is private
committed bytes; a numerical ratio NEVER proves an allocation owner.
The original named settled_cleanup checkpoint was not true global idle.
"""
import argparse
from fractions import Fraction
from pathlib import Path
import analyze_gio_combo_msvc256_saved as saved

START = ("baseline", 0)
CYCLE = ("cycle", 256)
FINAL = ("settled_cleanup", 258)
SIZE = 360


def check_source(src):
    needles = (
        "if (entry.wFlags & PROCESS_HEAP_ENTRY_BUSY)",
        "busy_bytes += entry.cbData;",
        "size_slot = entry.cbData < 2048 ? (unsigned int)entry.cbData : 2048U;",
        "c545d_heap_sizes[size_slot]++;",
        "if (!HeapLock(heaps[i]))",
        "while (HeapWalk(heaps[i], &entry))",
        "if (!HeapUnlock(heaps[i]))",
        "PROCESS_MEMORY_COUNTERS_EX memory;",
        "GetProcessMemoryInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS *)&memory, sizeof(memory))",
        "(unsigned long long)memory.PrivateUsage",
        "GIO_HEAPSIZE,%s,%d,%u,%llu",
    )
    if any(src.count(n) != 1 for n in needles):
        raise ValueError("source not the pinned HeapWalk/PrivateUsage measurement")
    if not (src.index(needles[4]) < src.index(needles[5]) < src.index(needles[6])):
        raise ValueError("HeapWalk must be between HeapLock and HeapUnlock")


def effect(arms, kind, start, stop):
    def get(arm, point):
        data = arms[arm]
        if kind == "private":
            return data["mem"][point]
        if kind == "heap_busy":
            return data["heap"][point]
        if kind == "bucket":
            return data["bins"][SIZE][point]
        raise ValueError("invalid metric")
    return (get("registry", stop) - get("registry", start)
            - get("nochange", stop) + get("nochange", start))


def nominal(private, count):
    if private <= 0 or count < 0 or SIZE * count >= private:
        raise ValueError("not the archived residual")
    return SIZE * count, Fraction(SIZE * count, private)


def analyze(group, source):
    check_source(source)
    valid = saved.analyze(group, print_output=False)
    if not valid[-1].startswith("C545D_SAVED256_NUMERIC_ANALYSIS_PASS,"
                                     "source_windows_run=44918598339,"):
        raise ValueError("original four-arm completeness invalid")
    arms = {arm: saved.parse(group, "combo", arm) for arm in saved.ARMS}
    p256 = effect(arms, "private", START, CYCLE)
    p258 = effect(arms, "private", START, FINAL)
    b256 = effect(arms, "bucket", START, CYCLE)
    b258 = effect(arms, "bucket", START, FINAL)
    h256 = effect(arms, "heap_busy", START, CYCLE)
    h258 = effect(arms, "heap_busy", START, FINAL)
    # Existing four 64-cycle saved snapshots contain TOTAL busy cbData,
    # even though the archive kept only eight selected exact size bins.
    epochs = [START, ("cycle", 64), ("cycle", 128),
              ("cycle", 192), CYCLE]
    heap_epochs = [effect(arms, "heap_busy", a, b)
                   for a, b in zip(epochs[:-1], epochs[1:])]
    private_epochs = [effect(arms, "private", a, b)
                      for a, b in zip(epochs[:-1], epochs[1:])]
    if (p256, p258, b256, b258, h256, h258) != (
        425984, 368640, 4, 4, 35566, 26262
    ):
        raise ValueError("Combo256 original controlled totals changed")
    if heap_epochs != [-25350, 48382, -16066, 28600]:
        raise ValueError("original all-busy heap epoch controls changed")
    if private_epochs != [151552, 233472, -12288, 53248]:
        raise ValueError("original private epoch controls changed")
    if sum(heap_epochs) != h256 or sum(private_epochs) != p256:
        raise ValueError("saved epoch totals failed telescoping")
        raise ValueError("Combo256 original controlled deltas changed")
    data, frac = nominal(p258, b258)
    if p258 % 4096 or data != 1440 or frac != Fraction(1, 256):
        raise ValueError("unexpected original byte-scale comparison")
    return [
        "C545D_COMBO256_METRIC_SOURCE,heapwalk_busy_uses_cbData=1,"
        "heapwalk_locked=1,private_uses_GetProcessMemoryInfo=1,"
        "heap_payload_not_private_commit=1",
        "C545D_COMBO256_METRIC_NUMERIC,source_run=44918598339,"
        f"combo_controlled_private_0_256={p256},"
        f"combo_controlled_private_0_258={p258},"
        f"combo_controlled_private_256_258={p258-p256},"
        f"combo_controlled_360B_0_256={b256},"
        f"combo_controlled_360B_0_258={b258},"
        f"nominal_360B_data_delta={data},"
        f"combo_controlled_busy_0_256={h256},"
        f"combo_controlled_busy_0_258={h258},"
        f"combo_controlled_busy_256_258={h258-h256},"
        "same_window_nominal_data_ratio=1/256,"
        "private_final_equivalent_4KiB_pages=90",
        *[
            "C545D_COMBO256_METRIC_EPOCH,"
            f"window={epochs[i][1]}_{epochs[i+1][1]},"
            f"private_delta={private_epochs[i]},"
            f"heap_busy_delta={heap_epochs[i]},"
            "same_run_matched_arms=1,"
            "heap_commit_unmeasured=1"
            for i in range(4)
        ],
        "C545D_COMBO256_METRIC_INFERENCE,nominal_ratio_is_not_attribution=1,"
        "full_HeapWalk_busy_size_classes_unattributed=1,"
        "allocator_metadata_and_nonheap_commit_unattributed=1,"
        "heap_data_is_not_equivalent_to_heap_committed_pages=1,"
        "final_global_quiescence_proven=0,cohort_identity_preserved_proven=0,"
        "permanent_leak_rate_proven=0,"
        "exact_360B_owner_proven=0",
        "C545D_COMBO256_METRIC_SCOPE_PASS,source_run=44918598339,"
        "old_windows_processes=4,new_windows_runs=0,host_modified=0,"
        "real_camera=0,install_approved=0",
    ]


def selftest():
    assert nominal(368640, 4) == (1440, Fraction(1, 256))
    a = {
        "registry": {"mem": {START: 100, FINAL: 210}},
        "nochange": {"mem": {START: 100, FINAL: 160}},
    }
    assert effect(a, "private", START, FINAL) == 50
    b = {
        "registry": {"heap": {START: 80, FINAL: 150}},
        "nochange": {"heap": {START: 30, FINAL: 55}},
    }
    assert effect(b, "heap_busy", START, FINAL) == 45
    rejected = 0
    for p, n in ((0, 4), (-1, 4), (1440, 4), (100, -1)):
        try:
            nominal(p, n)
        except ValueError:
            rejected += 1
        else:
            raise AssertionError("invalid numerical comparison accepted")
    src = "\n".join((
        "if (entry.wFlags & PROCESS_HEAP_ENTRY_BUSY)",
        "busy_bytes += entry.cbData;",
        "size_slot = entry.cbData < 2048 ? (unsigned int)entry.cbData : 2048U;",
        "c545d_heap_sizes[size_slot]++;",
        "if (!HeapLock(heaps[i]))",
        "while (HeapWalk(heaps[i], &entry))",
        "if (!HeapUnlock(heaps[i]))",
        "PROCESS_MEMORY_COUNTERS_EX memory;",
        "GetProcessMemoryInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS *)&memory, sizeof(memory))",
        "(unsigned long long)memory.PrivateUsage",
        "GIO_HEAPSIZE,%s,%d,%u,%llu",
    ))
    check_source(src)
    for bad in (
        src.replace("busy_bytes += entry.cbData;", "busy_bytes += entry.cbOverhead;"),
        src.replace("HeapLock", "HeapNoLock"),
        src.replace("memory.PrivateUsage", "memory.WorkingSetSize"),
    ):
        try:
            check_source(bad)
        except ValueError:
            rejected += 1
        else:
            raise AssertionError("invalid source accepted")
    assert rejected == 7
    print("C545D_COMBO256_METRIC_SCOPE_SELFTEST_PASS,negative_cases=7,"
          "new_windows_runs=0,host_modified=0")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--root", type=Path)
    ap.add_argument("--probe-source", type=Path)
    args = ap.parse_args()
    if args.selftest:
        selftest()
    else:
        if args.root is None or args.probe_source is None:
            ap.error("require --root and --probe-source")
        for item in analyze(saved.load(args.root),
                            args.probe_source.read_text(encoding="utf-8")):
            print(item)


if __name__ == "__main__":
    main()
