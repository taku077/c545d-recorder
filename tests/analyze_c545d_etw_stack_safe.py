#!/usr/bin/env python3
"""Privacy-safe, non-attributive classifier for local xperf -a heap -stacks.

NEVER prints raw ETW, stack frames, file paths, addresses, PID or package names.
This deliberately counts module-family frame occurrences, NOT unique stacks,
not bytes owned by callers, not completeness or proof of a memory leak.
A top-N stack report is truncated by design. Input is disposable CI only.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

MAX_BYTES = 16 * 1024 * 1024
MAX_LINES = 100000
FRAME = re.compile(
    r"(?<![A-Za-z0-9_.-])([A-Za-z][A-Za-z0-9_.-]{1,70})!"
    r"(?=[A-Za-z0-9_?@$])", re.IGNORECASE
)
# Only hardcoded family names enter output, never a discovered module name.
FAMILIES = ("gio", "glib", "winrt", "crt", "system", "gstreamer", "other")


def decode(raw: bytes) -> str:
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("size_limit")
    try:
        if raw.startswith(b"\xff\xfe"):
            text = raw[2:].decode("utf-16-le", "strict")
        elif raw.startswith(b"\xfe\xff"):
            raise ValueError("unsupported_encoding")
        elif b"\x00" in raw[:256]:
            # Accept MSVC xperf UTF-16 LE without BOM, if well-formed.
            if len(raw) % 2 or len(raw) < 6:
                raise ValueError("unsupported_encoding")
            text = raw.decode("utf-16-le", "strict")
        else:
            text = raw.decode("utf-8-sig", "strict")
    except UnicodeError:
        raise ValueError("unsupported_encoding") from None
    if "\x00" in text or len(text.splitlines()) > MAX_LINES:
        raise ValueError("binary_or_oversized_lines")
    return text


def family(name: str) -> str:
    n = name.lower().removesuffix(".dll").removesuffix(".exe")
    if n in ("gio-2.0-0", "libgio-2.0-0", "gio-2.0"):
        return "gio"
    if n in (
        "glib-2.0-0", "gobject-2.0-0", "gmodule-2.0-0",
        "libglib-2.0-0", "libgobject-2.0-0", "libgmodule-2.0-0",
    ):
        return "glib"
    if n in (
        "combase", "ole32", "windowsapp", "windows.applicationmodel",
        "twinapi.appcore", "api-ms-win-core-winrt-l1-1-0"
    ):
        return "winrt"
    if n in ("ucrtbase", "msvcrt", "vcruntime140", "vcruntime140_1",
             "msvcp140"):
        return "crt"
    if n in ("ntdll", "kernelbase", "kernel32"):
        return "system"
    if n.startswith(("gst", "gstreamer-1.0", "libgst")):
        return "gstreamer"
    return "other"


def sanitize(text: str) -> str:
    counts = {x: 0 for x in FAMILIES}
    frame_lines = 0
    for line in text.splitlines():
        matches = FRAME.findall(line)
        if not matches:
            continue
        frame_lines += 1
        for module in matches:
            counts[family(module)] += 1
    count = sum(counts.values())
    # Nonzero can be all kernel/CRT frames. This is NOT a callsite test.
    if count == 0:
        raise ValueError("no_symbolized_module_frames")
    # Values are integers; no input substrings or discovered module names.
    fields = [
        "C545D_ETW_STACK_SAFE_SUMMARY",
        "classification=module_frame_occurrences",
        f"frame_lines={frame_lines}",
        f"frames={count}",
        *(f"{kind}_frames={counts[kind]}" for kind in FAMILIES),
        "top25_is_incomplete=1",
        "unsymbolized_frames_count_known=0",
        "allocation_bytes_owner_proven=0",
        "stack_owner_proven=0",
        "full_heap_coverage_proven=0",
        "raw_text_uploaded=0",
    ]
    result = ",".join(fields)
    if not re.fullmatch(r"[A-Za-z0-9_,=]+", result):
        raise ValueError("unsafe_output")
    return result


def selftest() -> None:
    sample = (
        "PrivateData C:\\Users\\SENSITIVE_NAME\\AppData\\secret.exe "
        "0x1234567890abcdef\n"
        "  ntdll.dll!RtlAllocateHeap\n"
        "  C:\\Users\\SENSITIVE_NAME\\Documents\\gio-2.0-0.dll!g_app_info_get_all\n"
        "  glib-2.0-0.dll!g_malloc\n"
        "  combase.dll!CoCreateInstance\n"
        "  my_private_package_id!VerySecretFunction\n"
    )
    report = sanitize(sample)
    assert "gio_frames=1" in report
    assert "glib_frames=1" in report
    assert "winrt_frames=1" in report
    assert "other_frames=1" in report
    assert "system_frames=1" in report
    for forbidden in (
        "SENSITIVE_NAME", "Documents", "secret", "0x123",
        "my_private_package_id", "RtlAllocateHeap", "g_malloc",
    ):
        assert forbidden not in report
    assert sanitize(decode(b"\xff\xfe" + sample.encode("utf-16-le"))) == report
    assert sanitize(decode(sample.encode("utf-16-le"))) == report
    negatives = (
        b"",
        b"\x00",
        b"\xff\xfe\x00",
        b"\xfe\xff" + sample.encode("utf-16-be"),
        b"0x1234567890abcdef\nRaw path only, no module call stacks",
        b"A" * (MAX_BYTES + 1),
        b"\xff\xfd\xfa",
    )
    for raw in negatives:
        try:
            sanitize(decode(raw))
        except ValueError:
            continue
        raise AssertionError("unsafe xperf fixture accepted")
    print("C545D_ETW_STACK_SANITIZER_SELFTEST_PASS,"
          "positive_cases=3,negative_cases=7,"
          "sensitive_paths_emitted=0,raw_stacks_emitted=0,"
          "bytes_owner_attributed=0")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--source", type=Path)
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    if a.source is None:
        ap.error("private --source required")
    try:
        print(sanitize(decode(a.source.read_bytes())))
        print("C545D_ETW_STACK_SANITIZER_PASS,"
              "module_only=1,source_owner_proven=0,"
              "real_recorder_untouched=1")
    except (OSError, ValueError) as exc:
        # Exactly a hard-coded reason or a fixed generic code, no raw exception.
        code = str(exc)
        if code not in (
            "size_limit", "unsupported_encoding", "binary_or_oversized_lines",
            "no_symbolized_module_frames", "unsafe_output",
        ):
            code = "UNEXPECTED_INPUT"
        print(f"C545D_ETW_STACK_SANITIZER_FAIL,reason={code},"
              "raw_uploaded=0")
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
