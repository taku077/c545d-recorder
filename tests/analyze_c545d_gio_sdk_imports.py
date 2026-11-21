#!/usr/bin/env python3
"""Read-only PE GIO ABI gate. Outputs aggregate numbers, never machine paths.

Scans all official GStreamer MSVC SDK DLLs and plugins for static GIO named
and ordinal imports, and checks the exact unchanged candidate's exports.
Dynamic GetProcAddress/LoadLibrary and actual Win10/Tapo remain untested.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import pefile

REFERENCE_SHA = "a875107c180fb248236d1e96e14f362f117124df2fee1237fa2142b7b363941b"
CANDIDATE_SHA = "67b9f7246e4744fef7ee1ead3bed4ce2179c6f0465ec68a92d01dd12b4a3ccad"
GIO_NAME = "gio-2.0-0.dll"
DIRECTORIES = [pefile.DIRECTORY_ENTRY[x] for x in
               ("IMAGE_DIRECTORY_ENTRY_IMPORT", "IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT")]

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()

def export_maps(path):
    pe = pefile.PE(str(path), fast_load=True)
    try:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
        if pe.FILE_HEADER.Machine != pefile.MACHINE_TYPE["IMAGE_FILE_MACHINE_AMD64"]:
            raise ValueError("GIO PE is not x64")
        d = getattr(pe, "DIRECTORY_ENTRY_EXPORT", None)
        if not d:
            raise ValueError("GIO export directory missing")
        names, ordinals = {}, {}
        for x in d.symbols:
            ordinals[int(x.ordinal)] = x.name
            if x.name is not None:
                if x.name in names:
                    raise ValueError("duplicate GIO export name")
                names[x.name] = int(x.ordinal)
        return names, ordinals
    finally:
        pe.close()

def static_imports(path):
    pe = pefile.PE(str(path), fast_load=True)
    try:
        pe.parse_data_directories(directories=DIRECTORIES)
        if pe.FILE_HEADER.Machine != pefile.MACHINE_TYPE["IMAGE_FILE_MACHINE_AMD64"]:
            raise ValueError("non-x64 SDK module")
        gio, deps = [], set()
        for kind in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
            for entry in getattr(pe, kind, ()):
                dll = entry.dll.decode("ascii", errors="replace").lower()
                deps.add(dll)
                if dll == GIO_NAME:
                    for imp in entry.imports:
                        gio.append((imp.name, int(imp.ordinal) if imp.ordinal is not None else None))
        return gio, deps
    finally:
        pe.close()

def validate_gio_imports(imports, sdk_names, cand_names, sdk_ordinals, cand_ordinals):
    c = Counter()
    for name, ordinal in imports:
        if name is not None:
            c["gio_name_imports"] += 1
            if name not in sdk_names:
                c["sdk_unresolved_name_imports"] += 1
            if name not in cand_names:
                c["candidate_unresolved_name_imports"] += 1
        else:
            c["gio_ordinal_imports"] += 1
            if ordinal is None or ordinal not in sdk_ordinals:
                c["sdk_unresolved_ordinal_imports"] += 1
            if ordinal is None or ordinal not in cand_ordinals:
                c["candidate_unresolved_ordinal_imports"] += 1
            elif sdk_ordinals.get(ordinal) != cand_ordinals[ordinal]:
                c["candidate_mismatched_ordinal_imports"] += 1
    return c

def scan(root, candidate):
    sdk_bin = root / "bin"
    plugin_dir = root / "lib" / "gstreamer-1.0"
    ref = sdk_bin / GIO_NAME
    if not candidate.is_file() or not ref.is_file() or not plugin_dir.is_dir():
        raise ValueError("missing SDK/candidate/plug-in directory")
    if sha(ref) != REFERENCE_SHA or sha(candidate) != CANDIDATE_SHA:
        raise ValueError("known reference/candidate SHA256 mismatch")
    sdk_names, sdk_ordinals = export_maps(ref)
    cand_names, cand_ordinals = export_maps(candidate)
    if len(sdk_names) != 2047 or len(cand_names) != 2047:
        raise ValueError("unexpected official 2047 export count")
    if set(sdk_names) != set(cand_names):
        raise ValueError("GIO export names do not match the official SDK")
    sdk_imp, sdk_deps = static_imports(ref)
    cand_imp, cand_deps = static_imports(candidate)
    if sdk_imp != cand_imp or cand_deps - sdk_deps:
        raise ValueError("candidate adds unproven direct dependency/import")
    files = list(sdk_bin.glob("*.dll")) + list(plugin_dir.glob("*.dll"))
    files.extend(sdk_bin.glob("gst-*.exe"))
    files = sorted(set(files), key=lambda x: str(x).casefold())
    if len(files) < 35:
        raise ValueError("official SDK module inventory unexpectedly small")
    c = Counter()
    for f in files:
        c["sdk_pe_files_scanned"] += 1
        try:
            imports, _ = static_imports(f)
        except (pefile.PEFormatError, OSError, ValueError):
            c["sdk_pe_parse_failures"] += 1
            continue
        if imports:
            c["sdk_modules_importing_gio"] += 1
            c.update(validate_gio_imports(imports, sdk_names, cand_names,
                                          sdk_ordinals, cand_ordinals))
    if c["sdk_pe_parse_failures"]:
        raise ValueError("official SDK module parsing incomplete, count=%d" % c["sdk_pe_parse_failures"])
    if c["sdk_modules_importing_gio"] < 1 or c["gio_name_imports"] + c["gio_ordinal_imports"] < 1:
        raise ValueError("no GIO static imports discovered; cannot claim graph test")
    bad = ("sdk_unresolved_name_imports", "candidate_unresolved_name_imports",
           "sdk_unresolved_ordinal_imports", "candidate_unresolved_ordinal_imports",
           "candidate_mismatched_ordinal_imports")
    if any(c[k] for k in bad):
        raise ValueError("GIO static import ABI mismatch: " +
                         ",".join(k+"="+str(c[k]) for k in bad if c[k]))
    return {
        "sdk_pe_files_scanned": c["sdk_pe_files_scanned"],
        "sdk_modules_importing_gio": c["sdk_modules_importing_gio"],
        "gio_name_imports": c["gio_name_imports"],
        "gio_ordinal_imports": c["gio_ordinal_imports"],
        "candidate_unresolved_name_imports": c["candidate_unresolved_name_imports"],
        "candidate_unresolved_ordinal_imports": c["candidate_unresolved_ordinal_imports"],
        "candidate_mismatched_ordinal_imports": c["candidate_mismatched_ordinal_imports"],
        "candidate_new_direct_dll_dependencies": len(cand_deps - sdk_deps),
        "sdk_exports": len(sdk_names),
        "candidate_exports": len(cand_names),
        "exact_sdk_hash_checked": True,
        "exact_candidate_hash_checked": True,
        "dynamic_imports_checked": False,
        "windows10_tapo_tested": False,
        "ci_only": True,
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sdk-root", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--numeric-summary", type=Path, required=True)
    a = p.parse_args()
    data = scan(a.sdk_root, a.candidate)
    a.numeric_summary.parent.mkdir(parents=True, exist_ok=True)
    a.numeric_summary.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    print("C545D_GIO_SDK_STATIC_IMPORTS_PASS," +
          ",".join("%s=%s" % (key, data[key]) for key in
                   ("sdk_pe_files_scanned", "sdk_modules_importing_gio",
                    "gio_name_imports", "gio_ordinal_imports",
                    "candidate_unresolved_name_imports", "candidate_unresolved_ordinal_imports",
                    "candidate_mismatched_ordinal_imports", "sdk_exports", "candidate_exports")) +
          ",CI_only=1,host_modified=0,dynamic_imports_NOT_proven=1")

if __name__ == "__main__":
    main()
