#!/usr/bin/env python3
"""Offline imported-symbol audit of EXACT GStreamer 1.28.8 Windows SDK PE files.

This does NOT run GStreamer, GIO, WinRT, plugin scanners or any package.
Enumerate PE standard and delay import symbol names (IAT) from the public
pinned SDK. Direct function calls linked via the GIO import library usually
appear here, but dlsym/GetProcAddress, in-module calls, forwarded exports,
unscanned external plugins and data-driven runtime dispatch remain UNKNOWN.

Print numeric category counts only, never host/user path lists or any
private runtime stack. A zero IAT count does NOT prove no invocation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re

RE_NAME = re.compile(r"^_?(g_app_info_dup|g_app_info_get_all)(?:@\d+)?$")
LIMIT=20000


def family(path: Path, sdk: Path) -> str:
    p = path.relative_to(sdk)
    parts = [x.lower() for x in p.parts]
    basename=path.name.lower()
    if basename=="gst-launch-1.0.exe":
        return "gst_launch"
    if basename=="gio-2.0-0.dll":
        return "gio_dll"
    if "gstreamer-1.0" in parts:
        return "gst_plugin"
    if basename.startswith("gst") or basename.startswith("gstreamer"):
        return "gst_binlib"
    return "sdk_other"


def names(pe) -> set[str]:
    found=set()
    for group in ("DIRECTORY_ENTRY_IMPORT","DIRECTORY_ENTRY_DELAY_IMPORT"):
        for descriptor in getattr(pe,group,[]):
            for imp in getattr(descriptor,"imports",[]):
                if imp.name is None:
                    continue
                try:
                    name=imp.name.decode("ascii",errors="strict")
                except (ValueError, UnicodeDecodeError):
                    continue
                m=RE_NAME.fullmatch(name)
                if m:
                    found.add(m.group(1))
    return found


def audit(sdk: Path) -> str:
    try:
        import pefile
    except ImportError as exc:
        raise ValueError("pefile_missing") from exc
    if not sdk.is_dir() or not (sdk / "bin" / "gio-2.0-0.dll").is_file():
        raise ValueError("unverified_sdk_layout")
    found=list(sdk.rglob("*.dll")) + list(sdk.rglob("*.exe"))
    files=sorted(set(found))
    if len(files)<25 or len(files)>LIMIT:
        raise ValueError("incomplete_or_unbounded_sdk_images")
    counts=Counter()
    per=Counter()
    invalid=0
    for path in files:
        try:
            pe=pefile.PE(str(path),fast_load=True)
            pe.parse_data_directories(directories=[
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
            ])
            syms=names(pe)
            pe.close()
        except pefile.PEFormatError:
            invalid+=1
            continue
        group=family(path,sdk)
        counts[group]+=1
        for symbol in syms:
            per[group,symbol]+=1
    if invalid>3 or sum(counts.values())<25:
        raise ValueError("too_many_unreadable_PE_images")
    if counts["gio_dll"]!=1 or counts["gst_launch"]!=1 or (
        counts["gst_plugin"]<1
    ):
        raise ValueError("expected_sdk_binary_groups_missing")
    chunks=[
        f"C545D_SDK_APPINFO_IMPORT_SCOPE,pe_images={sum(counts.values())},"
        f"bad_images={invalid},"
        f"direct_import_g_app_info_dup={sum(v for (g,n),v in per.items() if n=='g_app_info_dup')},"
        f"direct_import_g_app_info_get_all={sum(v for (g,n),v in per.items() if n=='g_app_info_get_all')},"
        "scope=IAT_and_delay_IAT_only,dynamic_calls_unobserved=1,"
        "private_alloc_owner_unknown=1,"
        "recorder_host_unmodified=1"
    ]
    for group in ("gst_launch","gst_plugin","gst_binlib","gio_dll","sdk_other"):
        chunks.append(
            "C545D_SDK_APPINFO_IMPORT_GROUP,"
            f"group={group},images={counts[group]},"
            f"imports_dup={per[group,'g_app_info_dup']},"
            f"imports_get_all={per[group,'g_app_info_get_all']},"
            "all_dynamic_calls_unknown=1"
        )
    return "\n".join(chunks)


def selftest() -> None:
    class I:
        def __init__(self,name):self.name=name
    class D:
        def __init__(self,*imports):self.imports=[I(x) for x in imports]
    class P:
        DIRECTORY_ENTRY_IMPORT=[
            D(b"g_app_info_dup",b"g_app_info_get_all",b"g_app_info_dup_extra",None)]
        DIRECTORY_ENTRY_DELAY_IMPORT=[D(b"_g_app_info_dup@4")]
    result=names(P)
    if result != {"g_app_info_dup","g_app_info_get_all"}:
        raise AssertionError("direct PE import audit names misparsed")
    patterns=[
        b"g_app_info_dup_wrong",
        b"g_app_info_dup_internal",
        b"some_g_app_info_dup",
        b"g_app_info_dup_wrong@4",
        b"g_app_info_dup@@NOT",
    ]
    for val in patterns:
        class Q:
            DIRECTORY_ENTRY_IMPORT=[D(val)]
            DIRECTORY_ENTRY_DELAY_IMPORT=[]
        if names(Q):
            raise AssertionError("unrelated symbol falsely matched")
    print("C545D_SDK_APPINFO_IMPORT_SELFTEST_PASS,"
          "positive=2,negative=5,paths_emitted=0,"
          "windows_processes_run=0,host_untouched=1")


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--sdk",type=Path)
    args=p.parse_args()
    try:
        if args.selftest:
            selftest()
        else:
            if args.sdk is None:
                p.error("--sdk required")
            print(audit(args.sdk))
    except (ValueError,OSError):
        print("C545D_SDK_APPINFO_IMPORT_FAIL,"
              "reason=INVALID_SDK_OR_PE_IMPORTS,"
              "no_allocator_owner_inferred=1")
        raise SystemExit(3) from None


if __name__=="__main__":
    main()
