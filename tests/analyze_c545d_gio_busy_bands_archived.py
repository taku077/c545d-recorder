#!/usr/bin/env python3
"""Strict frozen replay of sanitized Windows GIO16 eight-band BUSY evidence.

Actual source Windows2022 #45020938670, artifact #14754166140.
Counts and cbData are same-process snapshot facts only; never substitute
for PrivateUsage, allocator stack ownership or later 256-cycle conclusions.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

RUN = 45020938670
ARTIFACT = 14754166140
NO = (
    (6323,93550),(4958,210530),(5560,475077),(1639,240606),
    (264,80826),(88,54323),(23,31784),(44,256697),
)
REG0 = (
    (6303,93097),(4902,208690),(5546,473961),(1611,235338),
    (256,78618),(85,52139),(22,30760),(39,237399),
)
REG1 = (
    (6306,93135),(4902,208690),(5549,474283),(1612,235530),
    (256,78618),(85,52139),(22,30760),(35,220711),
)
REG2 = (
    (1621,23868),(1481,66838),(1466,123775),(423,64532),
    (268,83694),(83,51115),(20,28712),(26,194087),
)
EXPECT = {
    "nochange": (NO,NO,NO,NO),
    "registry": (REG0,REG1,REG2,REG1),
}
RESOURCE = {
    ("private","0_16"):151552,
    ("private","16_17"):40960,
    ("private","17_18"):4096,
    ("busy","0_16"):-16136,
    ("busy","16_17"):-757245,
    ("busy","17_18"):757245,
}
REGION = {"0_16":(69632,151552,-16136),
          "16_17":(40960,40960,-757245),
          "17_18":(40960,4096,757245)}
PAT_ARM = re.compile(
    r"C545D_GIO_BUSY_BAND_ARM,arm=(nochange|registry),"
    r"stage=([0-3]),band=([0-7]),count=(\d+),bytes=(\d+),"
    r"heapwalk_only=1,allocation_site_unknown=1$"
)
PAT_DIFF = re.compile(
    r"C545D_GIO_BUSY_BAND_CONTROLLED,window=([0-2])_([1-3]),"
    r"band=([0-7]),count_effect=(-?\d+),bytes_effect=(-?\d+),"
    r"same_run_only=1,heapwalk_busy_not_private_usage=1,"
    r"worker_quiescence_unproven=1$"
)
PAT_RESOURCE = re.compile(
    r"C545D_COMBO16_SCANFREE_RESOURCE,kind=(private|busy),"
    r"window=(0_16|16_17|17_18),registry_raw=(-?\d+),"
    r"nochange_raw=(-?\d+),controlled=(-?\d+),"
    r"new_alloc_site_proven=0,real_host_untested=1$"
)
PAT_REGION = re.compile(
    r"C545D_HEAP_REGION_CONTROLLED,window=(0_16|16_17|17_18),"
    r"region_commit_delta=(-?\d+),private_delta=(-?\d+),"
    r"busy_cbData_delta=(-?\d+),optional_data_incomplete=0,"
    r"heap_region_largemalloc_coverage_proven=0,"
    r"cause_of_private_delta_proven=0$"
)
SUCCESS = (
    "C545D_GIO_BUSY_BANDS_PAIR_PASS,"
    "arms=2,checkpoints_each=4,bands_each=8,"
    "exact_numeric_rows=64,controlled_rows=24,"
    "no_missing_busy_bytes=1,"
    "unmeasured_non_heap_commit_possible=1,"
    "allocation_owner_proven=0,plateau_proven=0,"
    "real_host_tested=0,original_256_rerun=0"
)


def extract(lines: list[str], prefix: str, pat: re.Pattern[str],
            keys: tuple[int, ...]):
    found = {}
    for line in lines:
        if not line.startswith(prefix):
            continue
        m = pat.fullmatch(line)
        if m is None:
            raise ValueError("original_numeric_schema_drift")
        bits = m.groups()
        key = tuple(bits[x] for x in keys)
        if key in found:
            raise ValueError("duplicate_numeric_evidence")
        found[key] = bits
    return found


def verify(content: str) -> str:
    lines = content.splitlines()
    if len(content) > 350000 or len(lines) > 3500:
        raise ValueError("unbounded_numeric_archive")
    if not lines or any(re.fullmatch(r"[A-Za-z0-9_,=\-]+", x) is None
                        for x in lines):
        raise ValueError("unexpected_raw_data_in_archived_summary")
    arms = extract(lines, "C545D_GIO_BUSY_BAND_ARM,", PAT_ARM, (0,1,2))
    if len(arms) != 64:
        raise ValueError("incomplete_original_64_band_rows")
    for arm, stages in EXPECT.items():
        for stage, row in enumerate(stages):
            for band, expected in enumerate(row):
                fields = arms.get((arm,str(stage),str(band)))
                if fields is None or tuple(map(int,fields[3:5])) != expected:
                    raise ValueError("changed_original_bucket_count_or_bytes")
    diffs = extract(lines, "C545D_GIO_BUSY_BAND_CONTROLLED,",
                    PAT_DIFF,(0,1,2))
    if len(diffs) != 24:
        raise ValueError("incomplete_original_24_diff_rows")
    for left,right in ((0,1),(1,2),(2,3)):
        effects=[]
        for band in range(8):
            no=EXPECT["nochange"]
            reg=EXPECT["registry"]
            expected=(
                (reg[right][band][0]-reg[left][band][0])-
                (no[right][band][0]-no[left][band][0]),
                (reg[right][band][1]-reg[left][band][1])-
                (no[right][band][1]-no[left][band][1]),
            )
            f=diffs.get((str(left),str(right),str(band)))
            if f is None or tuple(map(int,f[3:5])) != expected:
                raise ValueError("changed_controlled_band_arithmetic")
            effects.append(expected[1])
        if sum(effects) != RESOURCE["busy", f"{(0,16,17)[left]}_{(16,17,18)[left]}"]:
            raise ValueError("controlled_heapwalk_bytes_do_not_conserve")
    resource=extract(lines,"C545D_COMBO16_SCANFREE_RESOURCE,",
                     PAT_RESOURCE,(0,1))
    if len(resource)!=6:
        raise ValueError("source_resource_rows_missing")
    for k,v in RESOURCE.items():
        row=resource.get(k)
        if row is None or int(row[4])!=v or int(row[2])-int(row[3])!=v:
            raise ValueError("original_private_or_busy_resources_changed")
    region=extract(lines,"C545D_HEAP_REGION_CONTROLLED,",
                   PAT_REGION,(0,))
    if len(region)!=3:
        raise ValueError("original_region_rows_missing")
    for window, expected in REGION.items():
        row=region.get((window,))
        if row is None or tuple(map(int,row[1:4]))!=expected:
            raise ValueError("region_commit_or_private_mismatch")
    if lines.count(SUCCESS)!=1:
        raise ValueError("original_source_safety_marker_missing")
    return (
        "C545D_GIO_BUSY_BANDS_ARCHIVE_PASS,"
        f"source_run={RUN},artifact_id={ARTIFACT},"
        "arms=2,band_rows=64,diff_rows=24,"
        "busy_0_16=-16136,large_ge2048_0_16=-16688,"
        "small_lt2048_0_16=552,"
        "private_0_16=151552,region_commit_0_16=69632,"
        "nonheap_owner_unproven=1,allocator_retention_unproven=1,"
        "no_new_windows_runs=1,old_256_not_repeated=1,"
        "real_recorder_untested=1"
    )


def fixture() -> str:
    out=[SUCCESS]
    for arm,stages in EXPECT.items():
        for i,stage in enumerate(stages):
            for b,(count,bytes_) in enumerate(stage):
                out.append(
                    "C545D_GIO_BUSY_BAND_ARM,"
                    f"arm={arm},stage={i},band={b},"
                    f"count={count},bytes={bytes_},"
                    "heapwalk_only=1,allocation_site_unknown=1")
    for left,right in ((0,1),(1,2),(2,3)):
        for b in range(8):
            n=EXPECT["nochange"]
            r=EXPECT["registry"]
            c=(r[right][b][0]-r[left][b][0])-(n[right][b][0]-n[left][b][0])
            d=(r[right][b][1]-r[left][b][1])-(n[right][b][1]-n[left][b][1])
            out.append(
                "C545D_GIO_BUSY_BAND_CONTROLLED,"
                f"window={left}_{right},band={b},"
                f"count_effect={c},bytes_effect={d},"
                "same_run_only=1,heapwalk_busy_not_private_usage=1,"
                "worker_quiescence_unproven=1")
    for (kind,window),v in RESOURCE.items():
        out.append(
            "C545D_COMBO16_SCANFREE_RESOURCE,"
            f"kind={kind},window={window},registry_raw={v},"
            f"nochange_raw=0,controlled={v},"
            "new_alloc_site_proven=0,real_host_untested=1")
    for window,(committed,private,busy) in REGION.items():
        out.append(
            "C545D_HEAP_REGION_CONTROLLED,"
            f"window={window},region_commit_delta={committed},"
            f"private_delta={private},busy_cbData_delta={busy},"
            "optional_data_incomplete=0,"
            "heap_region_largemalloc_coverage_proven=0,"
            "cause_of_private_delta_proven=0")
    return "\n".join(out)


def selftest():
    original=fixture()
    assert verify(original).startswith("C545D_GIO_BUSY_BANDS_ARCHIVE_PASS,")
    corrupt=[
        original.replace("count=6306,bytes=93135","count=6307,bytes=93135",1),
        original.replace("bytes=220711","bytes=220712",1),
        original.replace("bytes_effect=-16688","bytes_effect=-16687",1),
        original.replace("controlled=151552","controlled=151553",1),
        original.replace("region_commit_delta=69632",
                         "region_commit_delta=69631",1),
        original.replace("allocation_site_unknown=1",
                         "allocation_site_unknown=0",1),
        original.replace("unmeasured_non_heap_commit_possible=1",
                         "unmeasured_non_heap_commit_possible=0",1),
        original + "\n" + original.splitlines()[1],
        "\n".join(original.splitlines()[:-1]),
        original + "\nC:\\Users\\Private\\heap.etl",
    ]
    for bad in corrupt:
        if bad == original:
            raise AssertionError("no mutation applied")
        try:
            verify(bad)
        except ValueError:
            continue
        raise AssertionError("altered saved original passed")
    print("C545D_GIO_BUSY_BANDS_ARCHIVE_SELFTEST_PASS,"
          "positive=1,negative=10,new_windows_runs=0,"
          "raw_uploaded=0")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--source",type=Path)
    args=parser.parse_args()
    try:
        if args.selftest: selftest()
        elif args.source is not None:
            print(verify(args.source.read_text(encoding="utf-8-sig")))
        else: parser.error("--selftest or --source required")
    except (OSError,ValueError):
        print("C545D_GIO_BUSY_BANDS_ARCHIVE_FAIL,"
              "reason=INVALID_OR_ALTERED_NUMERIC,raw_uploaded=0")
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
